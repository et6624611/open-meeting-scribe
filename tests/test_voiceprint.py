"""
tests/test_voiceprint.py — 声纹域冒烟测试

覆盖声纹注册、匹配、重建、门槛、累积等关键路径。
从 test_smoke.py 拆分而来。

运行方式：
  pytest tests/test_voiceprint.py -v
"""

import pytest
from fastapi.testclient import TestClient

from app.server import app


@pytest.fixture
def client():
    """创建测试客户端"""
    with TestClient(app) as c:
        yield c


# ============================================================
# 声纹域（V3）
# ============================================================

class TestVoiceprintRegistry:
    """GET /api/voiceprint/registry 返回声纹注册表"""

    def test_registry_ok(self, client):
        resp = client.get("/api/voiceprint/registry")
        assert resp.status_code == 200
        data = resp.json()
        assert "voiceprints" in data
        assert "total" in data
        assert isinstance(data["voiceprints"], list)


class TestVoiceprintStatus:
    """GET /api/voiceprint/status/{uuid} 返回声纹状态"""

    def test_status_unknown_speaker(self, client):
        resp = client.get("/api/voiceprint/status/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_voiceprint"] is False
        assert data["speaker_uuid"] == "00000000-0000-0000-0000-000000000000"


class TestVoiceprintMatchNotFound:
    """POST /api/voiceprint/tasks/{task_id}/match 不存在时返回 404"""

    def test_match_not_found(self, client):
        resp = client.post("/api/voiceprint/tasks/nonexistent-id/match")
        assert resp.status_code == 404


class TestVoiceprintModuleLoad:
    """core.voiceprint 模块可正常加载"""

    def test_module_imports(self):
        from core.voiceprint import (  # noqa: F401
            MATCH_THRESHOLD,
            auto_identify_speakers,
            cosine_similarity,
            extract_embedding,
            load_registry,
            match_voiceprint,
        )
        assert MATCH_THRESHOLD > 0
        registry = load_registry()
        assert isinstance(registry, dict)


class TestVoiceprintRegisterFromBinding:
    """声纹自动注册闭环：绑定确认后补录注册表，并可被后续自动匹配命中"""

    def test_register_from_binding_then_auto_match(self, tmp_path, monkeypatch):
        import wave

        import numpy as np

        from core import voiceprint
        from core import voiceprint_registry as vp_reg

        # 注册表隔离到临时目录，避免污染真实数据
        # 注意：拆分后实际代码在 voiceprint_registry 中执行，必须 patch 源模块
        monkeypatch.setattr(vp_reg, "REGISTRY_FILE", tmp_path / "voiceprint_registry.json")

        # 模拟嵌入提取（避免加载重模型）：按调用次序交替返回两个正交 192 维向量
        vec_a = np.zeros(192, dtype=np.float32)
        vec_a[0] = 1.0
        vec_b = np.zeros(192, dtype=np.float32)
        vec_b[1] = 1.0
        calls = {"n": 0}

        def fake_extract(audio, sample_rate=vp_reg.SAMPLE_RATE):
            vec = vec_a if calls["n"] % 2 == 0 else vec_b
            calls["n"] += 1
            return vec.copy()

        monkeypatch.setattr(vp_reg, "extract_embedding", fake_extract)

        # 合成 16kHz 单声道 WAV（5 秒）
        sr = 16000
        wav_path = tmp_path / "normalized.wav"
        with wave.open(str(wav_path), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(np.zeros(sr * 5, dtype=np.int16).tobytes())

        dialogue = [
            {"speaker_id": 0, "sentences": [{"begin_time": 0, "end_time": 4000}]},
            {"speaker_id": 1, "sentences": [{"begin_time": 4000, "end_time": 5000}]},
        ]
        mapping = {0: "uuid-aaaa", 1: "uuid-bbbb"}

        # 注册：speaker 0 音频充足应入库；speaker 1 仅 1s 应被拒绝
        results = voiceprint.register_from_binding(wav_path, dialogue, mapping, meeting_id="m1")
        assert results["uuid-aaaa"]["status"] == "registered"
        assert results["uuid-bbbb"]["status"] == "insufficient_audio"
        assert voiceprint.get_voiceprint_status("uuid-aaaa") is True
        assert voiceprint.get_voiceprint_status("uuid-bbbb") is False

        # 自动匹配：speaker 0 提取向量与注册向量相同，应命中 uuid-aaaa
        calls["n"] = 0
        match_results = voiceprint.auto_identify_speakers(wav_path, dialogue)
        auto_mapping = voiceprint.build_auto_mapping(match_results)
        assert auto_mapping.get(0) == "uuid-aaaa"
        assert 1 not in auto_mapping  # 音频不足不参与匹配

    def test_auto_identify_skips_empty_registry(self, tmp_path, monkeypatch):
        """注册表为空时跳过自动匹配（不做无意义的嵌入提取）"""
        from core import voiceprint
        from core import voiceprint_registry as vp_reg

        monkeypatch.setattr(vp_reg, "REGISTRY_FILE", tmp_path / "empty_registry.json")
        extracted = {"called": False}

        def fake_extract(audio, sample_rate=vp_reg.SAMPLE_RATE):
            extracted["called"] = True
            return None

        monkeypatch.setattr(vp_reg, "extract_embedding", fake_extract)

        results = voiceprint.auto_identify_speakers(
            tmp_path,  # 路径不存在也无妨：注册表检查在前
            [{"speaker_id": 0, "sentences": [{"begin_time": 0, "end_time": 5000}]}],
        )
        assert results == []
        assert extracted["called"] is False


class TestVoiceprintRebuildAcrossMeetings:
    """跨会议声纹重建：人员独立于会议，聚合其参与的所有会议音频"""

    UUID = "11111111-2222-3333-4444-555555555555"

    def _prepare(self, tmp_path, monkeypatch, meeting_count):
        """隔离注册表、模拟嵌入提取、注入已完成会议任务"""
        import wave
        from types import SimpleNamespace

        import numpy as np

        from app import task_store
        from core import speakers
        from core import voiceprint_registry as vp_reg

        monkeypatch.setattr(vp_reg, "REGISTRY_FILE", tmp_path / "registry.json")

        vec = np.zeros(192, dtype=np.float32)
        vec[0] = 1.0
        monkeypatch.setattr(
            vp_reg, "extract_embedding",
            lambda audio, sample_rate=vp_reg.SAMPLE_RATE: vec.copy(),
        )
        monkeypatch.setattr(
            speakers, "get_speaker_by_id",
            lambda uid: SimpleNamespace(name="测试人") if uid == self.UUID else None,
        )

        fake_tasks = {}
        for i in range(meeting_count):
            wav = tmp_path / f"m{i}_normalized.wav"
            with wave.open(str(wav), 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(np.zeros(16000 * 5, dtype=np.int16).tobytes())
            fake_tasks[f"task-{i}"] = {
                "task_id": f"task-{i}",
                "status": "completed",
                "normalized_path": str(wav),
                "speaker_uuid_mapping": {"0": self.UUID},
                "dialogue": [
                    {"speaker_id": 0, "sentences": [{"begin_time": 0, "end_time": 4000}]},
                ],
            }
        monkeypatch.setattr(task_store, "tasks", fake_tasks)
        # 函数内 import 通过 app.store.tasks 获取引用，需同步 patch re-export 名称
        from app import store as store_mod
        monkeypatch.setattr(store_mod, "tasks", fake_tasks)

    def test_rebuild_aggregates_all_meetings(self, client, tmp_path, monkeypatch):
        """两场会议的发言片段均参与重建，样本数等于会议数"""
        from core import voiceprint

        self._prepare(tmp_path, monkeypatch, meeting_count=2)
        resp = client.post(f"/api/voiceprint/rebuild/{self.UUID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["meeting_count"] == 2
        assert data["sample_count"] == 2
        registry = voiceprint.load_registry()
        assert registry[self.UUID].sample_count == 2

    def test_rebuild_no_sufficient_audio(self, client, tmp_path, monkeypatch):
        """说话人存在但无足够发言音频时返回 400"""
        self._prepare(tmp_path, monkeypatch, meeting_count=0)
        resp = client.post(f"/api/voiceprint/rebuild/{self.UUID}")
        assert resp.status_code == 400

    def test_rebuild_unknown_speaker(self, client):
        """说话人不存在时返回 404"""
        resp = client.post("/api/voiceprint/rebuild/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


class TestVoiceprintMatchMargin:
    """匹配门槛：最佳与次优优势不足时拒绝匹配（防同通道录音误判）"""

    @staticmethod
    def _vec(angle_deg: float) -> list:
        """构造 192 维单位向量，前 2 维按角度旋转，其余为 0，保证 L2 范数 = 1"""
        import math
        rad = math.radians(angle_deg)
        v = [0.0] * 192
        v[0] = math.cos(rad)
        v[1] = math.sin(rad)
        return v

    def test_margin_gate(self, tmp_path, monkeypatch):
        import numpy as np

        from core import voiceprint
        from core import voiceprint_registry as vp_reg
        from core.voiceprint import VoiceprintRecord

        monkeypatch.setattr(vp_reg, "REGISTRY_FILE", tmp_path / "registry.json")
        # 注册两人，前 2 维余弦 ≈ 0.87（模拟高基线相似但 margin 足够）
        registry = {
            "uuid-a": VoiceprintRecord(speaker_uuid="uuid-a", embedding=self._vec(0.0)),
            "uuid-b": VoiceprintRecord(speaker_uuid="uuid-b", embedding=self._vec(30.0)),
        }
        voiceprint.save_registry(registry)

        # 查询与 a 完全一致：margin = 1 - 0.87 = 0.13 ≥ 门槛 → 命中 a
        hit = voiceprint.match_voiceprint(np.array(self._vec(0.0), dtype=np.float32))
        assert hit is not None and hit[0] == "uuid-a"

        # 查询落在两人正中间：双方相似度几乎相同，优势 ≈ 0 → 拒绝
        amb = voiceprint.match_voiceprint(np.array(self._vec(15.0), dtype=np.float32))
        assert amb is None


class TestVoiceprintSampleAccumulation:
    """多样本累积：重复注册按样本数加权平均，而非整体覆盖"""

    def test_accumulate_weighted_mean(self, tmp_path, monkeypatch):
        import numpy as np

        from core import voiceprint
        from core import voiceprint_registry as vp_reg

        monkeypatch.setattr(vp_reg, "REGISTRY_FILE", tmp_path / "registry.json")

        first = np.array([1.0, 0.0], dtype=np.float32)
        voiceprint.register_voiceprint("uuid-a", first)

        second = np.array([0.0, 1.0], dtype=np.float32)
        record = voiceprint.register_voiceprint("uuid-a", second)

        assert record.sample_count == 2
        merged = np.array(record.embedding, dtype=np.float32)
        # 两个正交样本累积后应落在中间方向，而非被第二个样本整体覆盖
        assert merged[0] > 0.4 and merged[1] > 0.4
        assert abs(float(np.linalg.norm(merged)) - 1.0) < 1e-3

        # accumulate=False 时整体覆盖
        rec2 = voiceprint.register_voiceprint("uuid-a", second, accumulate=False)
        assert np.allclose(np.array(rec2.embedding, dtype=np.float32), second)
