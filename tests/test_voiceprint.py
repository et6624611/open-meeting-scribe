"""
tests/test_voiceprint.py — 声纹域冒烟测试

覆盖声纹注册、匹配、重建、门槛、累积等关键路径。
从 test_smoke.py 拆分而来。

运行方式：
  pytest tests/test_voiceprint.py -v
"""

import numpy as np
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


# ============================================================
# v2.1：chunk 样本群 + 个人阈值 + 锚点排除
# ============================================================

class TestChunkSegments:
    """_chunk_segments 按有效时长攒块，尾块按规则合并或独立"""

    def test_full_chunks_and_independent_tail(self):
        from core import voiceprint_identify as vi

        segs = [(0, 20), (20, 40), (40, 50)]  # 50s
        chunks = vi._chunk_segments(segs, cap_sec=180, chunk_sec=20, min_tail_sec=5)
        assert len(chunks) == 3
        assert sum(e - b for b, e in chunks[2]) == 10  # 尾块 10s ≥5 独立

    def test_short_tail_merges_into_previous(self):
        from core import voiceprint_identify as vi

        segs = [(0, 20), (20, 40), (40, 43)]  # 尾块 3s
        chunks = vi._chunk_segments(segs, cap_sec=180, chunk_sec=20, min_tail_sec=5)
        assert len(chunks) == 2
        assert sum(e - b for b, e in chunks[-1]) == 23

    def test_short_audio_single_chunk(self):
        from core import voiceprint_identify as vi

        segs = [(0, 4), (4, 8)]  # 8s 不足一块 → 整体一块
        chunks = vi._chunk_segments(segs, cap_sec=180, chunk_sec=20)
        assert len(chunks) == 1

    def test_cap_applied_before_chunking(self):
        from core import voiceprint_identify as vi

        segs = [(i, i + 1) for i in range(180)]  # 180s 的 1s 句
        chunks = vi._chunk_segments(segs, cap_sec=30, chunk_sec=20)
        total = sum(e - b for ch in chunks for b, e in ch)
        assert total == 30
        assert len(chunks) == 2


class TestPersonalThreshold:
    """个人阈值由本人样本 LOO 自比对分布标定"""

    @staticmethod
    def _vec(angle_deg: float) -> "np.ndarray":
        import math
        import numpy as np
        rad = math.radians(angle_deg)
        v = np.zeros(192, dtype=np.float32)
        v[0] = math.cos(rad)
        v[1] = math.sin(rad)
        return v

    def test_needs_min_samples(self):
        from core import voiceprint_registry as vp_reg

        samples = [{"e": self._vec(0).tolist(), "d": 20.0, "m": "m1"}]
        assert vp_reg.compute_personal_threshold(samples) is None

    def test_threshold_within_clamp_range(self, tmp_path, monkeypatch):
        from core import voiceprint
        from core import voiceprint_registry as vp_reg

        monkeypatch.setattr(vp_reg, "REGISTRY_FILE", tmp_path / "registry.json")
        # 三个高度一致样本 → 阈值被 cap 到 0.62
        rec = voiceprint.register_voiceprint_samples("uuid-a", [
            (self._vec(0), 20, "m1"),
            (self._vec(2), 20, "m1"),
            (self._vec(-2), 20, "m1"),
        ])
        assert rec.personal_threshold is not None
        assert vp_reg.PERSONAL_THR_FLOOR <= rec.personal_threshold <= vp_reg.PERSONAL_THR_CAP
        assert len(rec.samples) == 3

    def test_loose_distribution_lowers_threshold(self, tmp_path, monkeypatch):
        from core import voiceprint
        from core import voiceprint_registry as vp_reg

        monkeypatch.setattr(vp_reg, "REGISTRY_FILE", tmp_path / "registry.json")
        rec = voiceprint.register_voiceprint_samples("uuid-a", [
            (self._vec(0), 20, "m1"),
            (self._vec(45), 20, "m2"),
            (self._vec(-45), 20, "m3"),
            (self._vec(10), 20, "m4"),
        ])
        # 分布松散 → 阈值应低于紧分布的 cap
        assert rec.personal_threshold < vp_reg.PERSONAL_THR_CAP


class TestSampleDedupAndCap:
    """同会议重复注册刷新去重；跨会议追加并受全局上限裁剪"""

    def test_same_meeting_refresh(self, tmp_path, monkeypatch):
        import numpy as np

        from core import voiceprint
        from core import voiceprint_registry as vp_reg

        monkeypatch.setattr(vp_reg, "REGISTRY_FILE", tmp_path / "registry.json")
        v0 = vp_reg._l2(np.array([1.0, 0.0], dtype=np.float32))
        v1 = vp_reg._l2(np.array([0.0, 1.0], dtype=np.float32))

        voiceprint.register_voiceprint_samples("uuid-a", [(v0, 20, "m1")] * 5)
        rec = voiceprint.register_voiceprint_samples("uuid-a", [(v1, 20, "m1")] * 3)
        # 同会议旧样本被整体刷新，只剩新 3 条
        assert len(rec.samples) == 3
        assert all(s["m"] == "m1" for s in rec.samples)

    def test_replace_path_also_capped(self, tmp_path, monkeypatch):
        """accumulate=False（跨会议重建）同样受单会议 9 条与全局 36 条裁剪"""
        import numpy as np

        from core import voiceprint
        from core import voiceprint_registry as vp_reg

        monkeypatch.setattr(vp_reg, "REGISTRY_FILE", tmp_path / "registry.json")
        v = vp_reg._l2(np.array([1.0, 0.0], dtype=np.float32))
        items = []
        for m in ("m1", "m2", "m3", "m4", "m5"):
            items += [(v, 20, m)] * 12  # 每场 12 → 单会议裁到 9，5 场共 45 → 全局裁到 36
        rec = voiceprint.register_voiceprint_samples("uuid-a", items, accumulate=False)
        # 单会议不超过 9；全局 36：最早的 m1 被 FIFO 整体淘汰，最新 m5 完整保留
        meetings = [s["m"] for s in rec.samples]
        assert all(meetings.count(m) <= vp_reg.MAX_SAMPLES_PER_MEETING for m in set(meetings))
        assert len(rec.samples) == vp_reg.MAX_SAMPLES_PER_SPEAKER
        assert "m1" not in set(meetings)
        assert meetings.count("m5") == vp_reg.MAX_SAMPLES_PER_MEETING

    def test_cross_meeting_accumulates(self, tmp_path, monkeypatch):
        import numpy as np

        from core import voiceprint
        from core import voiceprint_registry as vp_reg

        monkeypatch.setattr(vp_reg, "REGISTRY_FILE", tmp_path / "registry.json")
        v = vp_reg._l2(np.array([1.0, 0.0], dtype=np.float32))

        voiceprint.register_voiceprint_samples("uuid-a", [(v, 20, "m1")] * 3)
        rec = voiceprint.register_voiceprint_samples("uuid-a", [(v, 20, "m2")] * 3)
        assert len(rec.samples) == 6
        assert {s["m"] for s in rec.samples} == {"m1", "m2"}


class TestAutoIdentifyV2:
    """v2 自动识别：群表决 + 锚点排除 + 个人阈值门槛"""

    WAV_SECONDS = 60

    def _setup(self, tmp_path, monkeypatch, extract_sequence):
        import wave
        import numpy as np

        from core import voiceprint_identify as vi
        from core import voiceprint_registry as vp_reg

        monkeypatch.setattr(vp_reg, "REGISTRY_FILE", tmp_path / "registry.json")
        monkeypatch.setattr(vi, "_v2_enabled", lambda: True)

        sr = 16000
        wav_path = tmp_path / "normalized.wav"
        with wave.open(str(wav_path), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(np.zeros(sr * self.WAV_SECONDS, dtype=np.int16).tobytes())

        calls = {"n": 0}

        def fake_extract(audio, sample_rate=vp_reg.SAMPLE_RATE):
            vec = extract_sequence[calls["n"] % len(extract_sequence)]
            calls["n"] += 1
            return vec.copy()

        monkeypatch.setattr(vp_reg, "extract_embedding", fake_extract)
        return wav_path

    @staticmethod
    def _vec(angle_deg: float) -> "np.ndarray":
        import math
        import numpy as np
        rad = math.radians(angle_deg)
        v = np.zeros(192, dtype=np.float32)
        v[0] = math.cos(rad)
        v[1] = math.sin(rad)
        return v

    def _dialogue_three_chunks(self):
        # 三段各 20s → v2 切出 3 个 chunk
        return [{
            "speaker_id": 0,
            "sentences": [
                {"begin_time": 0, "end_time": 20000},
                {"begin_time": 20000, "end_time": 40000},
                {"begin_time": 40000, "end_time": 60000},
            ],
        }]

    def test_group_majority_personal_gate(self, tmp_path, monkeypatch):
        """3 chunk 中 2 个支持 a（个人阈值已标定），多数通过 → 命中 a，gate=personal"""
        from core import voiceprint
        from core import voiceprint_registry as vp_reg

        vec_a, vec_b = self._vec(0), self._vec(90)
        wav_path = self._setup(tmp_path, monkeypatch, [vec_a, vec_a, vec_b])

        # a 有 3 个紧样本（个人阈值生效）；b 无个人阈值
        voiceprint.register_voiceprint_samples("uuid-a", [
            (self._vec(0), 20, "m1"),
            (self._vec(2), 20, "m1"),
            (self._vec(-2), 20, "m1"),
        ])
        voiceprint.register_voiceprint("uuid-b", vec_b)

        results = voiceprint.auto_identify_speakers(wav_path, self._dialogue_three_chunks())
        assert len(results) == 1
        r = results[0]
        assert r.status == "matched"
        assert r.matched_uuid == "uuid-a"
        assert r.gate == "personal"
        assert r.group_size == 3
        assert r.majority >= voiceprint.GROUP_MAJORITY_RATIO

    def test_anchor_exclusion_removes_locked_speaker(self, tmp_path, monkeypatch):
        """已在本场锁定的注册人不参与候选"""
        from core import voiceprint

        vec_a, vec_b = self._vec(0), self._vec(90)
        # 4s 单句 → 单 chunk
        wav_path = self._setup(tmp_path, monkeypatch, [vec_a])
        voiceprint.register_voiceprint("uuid-a", vec_a)
        voiceprint.register_voiceprint("uuid-b", vec_b)

        dialogue = [{"speaker_id": 0, "sentences": [{"begin_time": 0, "end_time": 4000}]}]
        results = voiceprint.auto_identify_speakers(
            wav_path, dialogue, exclude_uuids={"uuid-a"},
        )
        assert len(results) == 1
        r = results[0]
        assert r.status == "unmatched"
        # a 被排除后，最佳候选只能是 b（相似度 0）
        assert r.similarity < 0.5

    def test_bound_sids_skip_identified_speakers(self, tmp_path, monkeypatch):
        """已确认绑定的 ASR speaker_id 不再产出任何识别结果"""
        from core import voiceprint

        vec_a = self._vec(0)
        wav_path = self._setup(tmp_path, monkeypatch, [vec_a])
        voiceprint.register_voiceprint("uuid-a", vec_a)

        dialogue = [{"speaker_id": 7, "sentences": [{"begin_time": 0, "end_time": 4000}]}]
        results = voiceprint.auto_identify_speakers(wav_path, dialogue, bound_sids={7})
        assert results == []

    def test_v1_fallback_uses_global_gate(self, tmp_path, monkeypatch):
        """voiceprint_v2=false 时回退单向量+全局口径"""
        from core import voiceprint
        from core import voiceprint_identify as vi

        vec_a, vec_b = self._vec(0), self._vec(90)
        wav_path = self._setup(tmp_path, monkeypatch, [vec_a, vec_a, vec_b])
        monkeypatch.setattr(vi, "_v2_enabled", lambda: False)

        voiceprint.register_voiceprint_samples("uuid-a", [
            (self._vec(0), 20, "m1"),
            (self._vec(2), 20, "m1"),
            (self._vec(-2), 20, "m1"),
        ])
        voiceprint.register_voiceprint("uuid-b", vec_b)

        results = voiceprint.auto_identify_speakers(wav_path, self._dialogue_three_chunks())
        r = results[0]
        # v1 整段一块：取序列首向量 vec_a；单人会议退化为 global 口径
        assert r.group_size == 1
        assert r.gate in ("global", "margin_only")
        assert r.status == "matched"
        assert r.matched_uuid == "uuid-a"
