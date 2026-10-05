"""WP-E（R1/R2/R3）本地引擎主干接线 — 契约与回退测试（替身/打桩，无需真机断网环境）。

主 venv 不含 funasr/torch，故本套件全程打桩：
  - 桩掉 core.engine_worker._get_asr_model / _get_spk_model（替身 FunASR AutoModel），
    验证 _handle_infer 的 asr / embedding 响应整形与错误分类；
  - 桩掉 core.engine_host.get_engine_host（替身常驻子进程），验证 _transcribe_local、
    LocalCamPlusProvider 的端到端契约与 AC-4 回退；
  - 声纹/转写数据层用 tmp_path + monkeypatch 隔离，绝不污染真实 data/。

────────────────────────────────────────────────────────────────────────
真实推理验收清单（断网真机，留待 QA/项目方执行，非本打桩套件覆盖）：
  环境：Spike 隔离 venv（.spike_local_engine/venv，funasr 1.4.16 / torch 2.14.0）
        + 已下载权重（MODELSCOPE_CACHE→data/models/，全家桶四模型 ≈2.0GB）。
  R1/R2（AC-1/AC-2）：
    1. settings.engine.mode=local，启动应用，录音/导入 samples/ ≥3 段（2/4/6 人）；
    2. 触发转写 → 经 EngineHost.infer("asr") 走 FunASR 全管线（seaco+vad+punc+cam++）；
    3. 抓包验证除 localhost 外零出网；转写结果字段对齐 docs/API_CONTRACTS.md §4；
    4. 本地 WER 与 paraformer-v2 差距 ≤15% 相对值（复用 tests/eval_local_engine/
       run_local_asr.py + compute_metrics.py）；热词映射（data/hotword_mappings.txt）生效。
  R3（AC-6）：
    5. 离线注册声纹 → LocalCamPlusProvider 经 EngineHost.infer("embedding") 出 192 维；
    6. 云/本地注册表零迁移互用；同组说话人匹配 FPR 相对差 ≤5%
       （复用 tests/eval_local_engine/vp_extract_local.py + vp_cmn_fix_regression.py，
        CMN 口径一致性证据：tests/eval_local_engine/results/vp_cmn_fix.json，cos=1.0）。
  AC-3（资源）：16GB 机型 30 分钟会议峰值内存 ≤8GB（Spike 参考 RSS 3.3GB/10min）。
────────────────────────────────────────────────────────────────────────
"""

import wave

import numpy as np
import pytest

from core import voiceprint_registry as vp_reg
from core.errors import LocalEngineError, classify_error

# ── 替身与工具 / Stubs and helpers ──

def _write_wav(path, seconds=1.0, sample_rate=16000):
    """写一个最小合法 16k 单声道 wav（供 audio_path 存在性校验与桩推理）。"""
    n = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n)
    return str(path)


class _FakeAsrModel:
    """替身 FunASR ASR 全管线模型：generate() 回传 canned sentence_info。"""

    def __init__(self, sentence_info, text):
        self._sentence_info = sentence_info
        self._text = text
        self.last_kwargs = None

    def generate(self, **kwargs):
        self.last_kwargs = kwargs
        return [{"text": self._text, "sentence_info": self._sentence_info}]


class _FakeSpkModel:
    """替身 FunASR CAM++ 声纹模型：generate() 回传 192 维 spk_embedding。"""

    def __init__(self, embedding):
        self._embedding = np.array(embedding, dtype=np.float32)

    def generate(self, **kwargs):
        return [{"spk_embedding": self._embedding}]


class _FakeEngineHost:
    """替身常驻子进程宿主：infer() 回传 canned 响应或抛 LocalEngineError。"""

    def __init__(self, asr_resp=None, embedding_resp=None, raise_exc=None):
        self._asr_resp = asr_resp
        self._embedding_resp = embedding_resp
        self._raise = raise_exc
        self.calls = []

    def infer(self, task, params=None, timeout=None):
        self.calls.append((task, params))
        if self._raise is not None:
            raise self._raise
        if task == "asr":
            return self._asr_resp
        if task == "embedding":
            return self._embedding_resp
        raise AssertionError(f"unexpected task: {task}")


# ============================================================
# R1 — engine_worker._handle_infer 契约（替身 FunASR）
# ============================================================

class TestEngineWorkerInfer:
    def test_infer_asr_shapes_sentence_info(self, tmp_path, monkeypatch):
        import core.engine_worker as w

        wav = _write_wav(tmp_path / "a.wav")
        sent = [
            {"start": 0, "end": 1200, "spk": 0, "text": "大家好"},
            {"start": 1200, "end": 2600, "spk": 1, "text": "你好"},
        ]
        fake = _FakeAsrModel(sent, "大家好你好")
        monkeypatch.setattr(w, "_get_asr_model", lambda: fake)

        out = w._handle_infer({"task": "asr", "audio_path": wav})
        assert out["ok"] is True
        assert out["task"] == "asr"
        assert out["engine"] == "local-funasr"
        assert out["text"] == "大家好你好"
        assert len(out["sentence_info"]) == 2
        assert out["sentence_info"][0] == {"start": 0, "end": 1200, "spk": 0, "text": "大家好"}
        # merge_vad 批处理参数按 PRD 分段批处理口径传入
        assert fake.last_kwargs["merge_vad"] is True
        assert "infer_seconds" in out

    def test_infer_embedding_returns_192_dim(self, tmp_path, monkeypatch):
        import core.engine_worker as w

        wav = _write_wav(tmp_path / "vp.wav")
        emb = np.zeros(192, dtype=np.float32)
        emb[0] = 1.0
        monkeypatch.setattr(w, "_get_spk_model", lambda: _FakeSpkModel(emb))

        out = w._handle_infer({"task": "embedding", "audio_path": wav})
        assert out["ok"] is True
        assert out["task"] == "embedding"
        assert out["dim"] == 192
        assert out["model_version"] == "cam++-v1"
        assert len(out["embedding"]) == 192

    def test_infer_unsupported_task(self):
        import core.engine_worker as w

        out = w._handle_infer({"task": "bogus"})
        assert out["ok"] is False
        assert out["error_code"] == "unsupported_task"

    def test_infer_asr_missing_audio_path(self):
        import core.engine_worker as w

        out = w._handle_infer({"task": "asr"})
        assert out["ok"] is False
        assert out["error_code"] == "bad_request"

    def test_infer_asr_audio_not_found(self):
        import core.engine_worker as w

        out = w._handle_infer({"task": "asr", "audio_path": "/no/such/file.wav"})
        assert out["ok"] is False
        assert out["error_code"] == "audio_not_found"


# ============================================================
# R1 — sentence_info → API_CONTRACTS 转写结构映射
# ============================================================

class TestLocalTranscriptionContract:
    def test_maps_to_contract_fields(self):
        from core.transcribe import _local_sentence_info_to_transcription

        sent = [
            {"start": 0, "end": 1000, "spk": 0, "text": "甲"},
            {"start": 1000, "end": 2500, "spk": 1, "text": "乙"},
        ]
        t = _local_sentence_info_to_transcription(sent, diarization_enabled=True)
        assert "transcripts" in t
        sentences = t["transcripts"][0]["sentences"]
        assert len(sentences) == 2
        s0 = sentences[0]
        # 契约字段（docs/API_CONTRACTS.md §4）：begin_time/end_time(ms)/text/sentence_id/speaker_id/words[]
        assert s0["begin_time"] == 0
        assert s0["end_time"] == 1000
        assert s0["text"] == "甲"
        assert s0["sentence_id"] == 0
        assert s0["speaker_id"] == 0
        assert s0["words"] == []
        assert sentences[1]["speaker_id"] == 1
        assert t["properties"]["channels"] == 1
        assert t["properties"]["original_duration_in_milliseconds"] == 2500

    def test_diarization_disabled_pins_speaker_zero(self):
        from core.transcribe import _local_sentence_info_to_transcription

        sent = [{"start": 0, "end": 1000, "spk": 3, "text": "x"}]
        t = _local_sentence_info_to_transcription(sent, diarization_enabled=False)
        assert t["transcripts"][0]["sentences"][0]["speaker_id"] == 0


# ============================================================
# R1 — _get_asr_mode 本地路由 + _transcribe_local 端到端（替身子进程）
# ============================================================

class TestLocalRouting:
    def test_get_asr_mode_returns_local_when_engine_local(self, tmp_path, monkeypatch):
        import app.settings_store as ss
        import core.transcribe as t

        # 逐能力真相源：asr 生效来源=local → 路由 local（不再由 engine.mode 推导）。
        monkeypatch.setattr(ss, "SETTINGS_FILE", tmp_path / "isolated-settings.json")
        ss.save_settings_to_disk({"capability_source": {"llm": "trial", "asr": "local"}})
        assert t._get_asr_mode() == "local"

    def test_get_asr_mode_not_local_when_engine_cloud(self, tmp_path, monkeypatch):
        import app.settings_store as ss
        import app.store as store
        import core.transcribe as t

        # asr 生效来源=trial（非本机）→ 路由不为 local（proxy/cloud/direct 皆可）。
        monkeypatch.setattr(ss, "SETTINGS_FILE", tmp_path / "isolated-settings.json")
        ss.save_settings_to_disk({"capability_source": {"llm": "trial", "asr": "trial"}})
        monkeypatch.setattr(store, "get_asr_config", lambda: {"mode": "proxy", "proxy_url": "http://x", "api_key": ""})
        assert t._get_asr_mode() != "local"

    def test_transcribe_local_end_to_end(self, tmp_path, monkeypatch):
        import core.engine_host as eh
        import core.transcribe as t

        wav = _write_wav(tmp_path / "m.wav")
        asr_resp = {
            "ok": True,
            "task": "asr",
            "engine": "local-funasr",
            "text": "今天我们讨论本地引擎方案。我认为这个离线计划完全可行。",
            "sentence_info": [
                {"start": 0, "end": 4000, "spk": 0, "text": "今天我们讨论本地引擎方案。"},
                {"start": 9000, "end": 14000, "spk": 1, "text": "我认为这个离线计划完全可行。"},
            ],
            "infer_seconds": 1.0,
        }
        fake_host = _FakeEngineHost(asr_resp=asr_resp)
        monkeypatch.setattr(eh, "get_engine_host", lambda: fake_host)

        dialogue, transcription = t._transcribe_local(
            __import__("pathlib").Path(wav), "paraformer-v2", True, None, None, None
        )
        # 子进程收到 asr 推理请求，audio_path 透传
        assert fake_host.calls[0][0] == "asr"
        assert fake_host.calls[0][1]["audio_path"] == wav
        # 对话稿按 speaker_id 归并，契约字段齐备
        assert isinstance(dialogue, list) and dialogue
        assert {b["speaker_id"] for b in dialogue} == {0, 1}
        assert transcription["transcripts"][0]["sentences"][0]["begin_time"] == 0


# ============================================================
# R2 — 本地热词映射（转写后替换）必配 + 差距
# ============================================================

class TestLocalHotwords:
    def test_apply_local_hotword_mappings_replaces_and_counts(self, monkeypatch):
        import core.hotwords as hw
        import core.transcribe as t

        monkeypatch.setattr(hw, "load_hotword_mappings", lambda *a, **k: [("其他科技", "云端科技")])
        monkeypatch.setattr(
            hw, "apply_hotword_mappings",
            lambda text, *a, **k: text.replace("其他科技", "云端科技"),
        )

        dialogue = [{
            "speaker_id": 0,
            "text": "其他科技全面预算",
            "sentences": [{"text": "其他科技全面预算"}],
        }]
        n = t._apply_local_hotword_mappings(dialogue)
        assert n == 1
        assert dialogue[0]["text"] == "云端科技全面预算"
        assert dialogue[0]["sentences"][0]["text"] == "云端科技全面预算"

    def test_local_transcribe_applies_hotwords(self, tmp_path, monkeypatch):
        """_transcribe_local 必施热词映射（必配项，非降级）。"""
        import core.engine_host as eh
        import core.hotwords as hw
        import core.transcribe as t

        wav = _write_wav(tmp_path / "h.wav")
        asr_resp = {
            "ok": True, "task": "asr", "engine": "local-funasr", "text": "其他科技",
            "sentence_info": [{"start": 0, "end": 1000, "spk": 0, "text": "其他科技"}],
            "infer_seconds": 0.5,
        }
        monkeypatch.setattr(eh, "get_engine_host", lambda: _FakeEngineHost(asr_resp=asr_resp))
        monkeypatch.setattr(hw, "load_hotword_mappings", lambda *a, **k: [("其他科技", "云端科技")])
        monkeypatch.setattr(
            hw, "apply_hotword_mappings",
            lambda text, *a, **k: text.replace("其他科技", "云端科技"),
        )

        dialogue, _ = t._transcribe_local(
            __import__("pathlib").Path(wav), "paraformer-v2", True, None, None, None
        )
        assert "云端科技" in dialogue[0]["text"]
        assert "其他科技" not in dialogue[0]["text"]


# ============================================================
# R3 — LocalCamPlusProvider（替身子进程）+ 选择逻辑 + 零迁移
# ============================================================

class TestLocalCamPlusProvider:
    def test_extract_returns_l2_normalized_192(self, monkeypatch):
        import core.embedding_provider as ep
        import core.engine_host as eh

        emb = np.zeros(192, dtype=np.float32)
        emb[0] = 3.0  # 非归一化，provider 应 L2 归一化
        monkeypatch.setattr(
            eh, "get_engine_host",
            lambda: _FakeEngineHost(embedding_resp={"ok": True, "embedding": emb.tolist(), "dim": 192}),
        )
        prov = ep.LocalCamPlusProvider()
        audio = np.zeros(16000, dtype=np.float32)  # 1s
        vec = prov.extract(audio, 16000)
        assert vec is not None
        assert vec.shape == (192,)
        assert vec.dtype == np.float32
        assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-5

    def test_extract_too_short_returns_none(self):
        import core.embedding_provider as ep

        prov = ep.LocalCamPlusProvider()
        assert prov.extract(np.zeros(1600, dtype=np.float32), 16000) is None  # 0.1s < 0.5s

    def test_extract_from_pcm(self, monkeypatch):
        import core.embedding_provider as ep
        import core.engine_host as eh

        emb = np.ones(192, dtype=np.float32)
        monkeypatch.setattr(
            eh, "get_engine_host",
            lambda: _FakeEngineHost(embedding_resp={"ok": True, "embedding": emb.tolist(), "dim": 192}),
        )
        prov = ep.LocalCamPlusProvider()
        pcm = (np.zeros(16000, dtype=np.float32) * 32767).astype(np.int16).tobytes()
        vec = prov.extract_from_pcm(pcm, 16000)
        assert vec is not None and vec.shape == (192,)

    def test_extract_graceful_on_engine_error(self, monkeypatch):
        import core.embedding_provider as ep
        import core.engine_host as eh

        monkeypatch.setattr(
            eh, "get_engine_host",
            lambda: _FakeEngineHost(raise_exc=LocalEngineError("模型未就绪", "models_missing", True)),
        )
        prov = ep.LocalCamPlusProvider()
        assert prov.extract(np.zeros(16000, dtype=np.float32), 16000) is None

    def test_contract_dim_and_version(self):
        import core.embedding_provider as ep

        prov = ep.LocalCamPlusProvider()
        assert prov.dim == 192
        assert prov.model_version == "cam++-v1"

    def test_provider_selection_camplus_available(self, monkeypatch):
        """REQ-SETTINGS-IA 第 4 刀后两级选择：CAM++ 就绪 → 本机 CAM++。"""
        import core.embedding_provider as ep

        monkeypatch.setattr(ep.LocalCamPlusProvider, "is_available", lambda self: True)
        ep.reset_provider()
        prov = ep.get_embedding_provider()
        assert isinstance(prov, ep.LocalCamPlusProvider)
        ep.reset_provider()

    def test_provider_selection_camplus_unavailable_falls_to_mfcc_never_cloud(self, monkeypatch):
        """CAM++ 未就绪 → 直接 MFCC；声纹不存在任何云端代码路径（结构性零出网）。"""
        import core.embedding_provider as ep

        monkeypatch.setattr(ep.LocalCamPlusProvider, "is_available", lambda self: False)
        ep.reset_provider()
        prov = ep.get_embedding_provider()
        assert isinstance(prov, ep.MfccFallbackProvider)
        ep.reset_provider()

    def test_cloud_provider_and_settings_surface_removed(self):
        """第 4 刀硬指标：CloudEmbeddingProvider / provider 配置读取均不存在。"""
        import core.embedding_provider as ep

        assert not hasattr(ep, "CloudEmbeddingProvider")
        assert not hasattr(ep, "_load_voiceprint_settings")
        assert not hasattr(ep, "_local_engine_active")

    def test_voiceprint_config_getter_removed_from_store(self):
        """AC-3：voiceprint.provider 字段在 schema/后端不存在——getter 已下架。"""
        import app.store as store

        assert not hasattr(store, "get_voiceprint_config")


class TestZeroMigrationCompat:
    """AC-6：cam++-v1（本地）与 cam++-v1-cloud（云端）注册表双向零迁移互用。"""

    def test_versions_mutually_compatible(self):
        assert vp_reg._is_compatible_version("cam++-v1") is True
        assert vp_reg._is_compatible_version("cam++-v1-cloud") is True

    def test_local_registered_record_matchable(self, tmp_path, monkeypatch):
        """本地 cam++-v1 注册的记录，可被注册表（encoder 常量现为 cam++-v1）匹配命中。"""
        monkeypatch.setattr(vp_reg, "REGISTRY_FILE", tmp_path / "registry.json")
        vec = np.zeros(192, dtype=np.float32)
        vec[0] = 1.0
        rec = vp_reg.VoiceprintRecord(
            speaker_uuid="spk-local-1", embedding=vec.tolist(), model_version="cam++-v1"
        )
        vp_reg.save_registry({"spk-local-1": rec})

        detail = vp_reg.match_voiceprint_detail(vec)
        assert detail.accepted is True
        assert detail.best_uuid == "spk-local-1"


# ============================================================
# AC-4 — 本地失败分类 + 显式回退云端
# ============================================================

class TestAc4Fallback:
    def test_transcribe_local_propagates_classified_error(self, tmp_path, monkeypatch):
        import core.engine_host as eh
        import core.transcribe as t

        wav = _write_wav(tmp_path / "f.wav")
        monkeypatch.setattr(
            eh, "get_engine_host",
            lambda: _FakeEngineHost(raise_exc=LocalEngineError("模型未就绪", "models_missing", True)),
        )
        with pytest.raises(LocalEngineError) as ei:
            t._transcribe_local(__import__("pathlib").Path(wav), "paraformer-v2", True, None, None, None)
        assert ei.value.error_code == "models_missing"
        assert ei.value.can_fallback_cloud is True

    def test_classify_error_local_engine_category(self):
        info = classify_error(LocalEngineError("模型未就绪", "models_missing", True))
        assert info["category"] == "local_engine"
        assert info["error_code"] == "models_missing"
        assert info["can_fallback_cloud"] is True
        assert info["suggestion"]

    def test_engine_override_cloud_bypasses_local(self, tmp_path, monkeypatch):
        """AC-4：用户确认后 engine_override='cloud' 重跑，绕过 local 判定。"""
        import core.transcribe as t

        wav = _write_wav(tmp_path / "o.wav")
        monkeypatch.setattr(t, "_get_asr_mode", lambda: "local")
        routed = {}
        monkeypatch.setattr(t, "_transcribe_cloud", lambda *a, **k: routed.setdefault("cloud", True) and ([], {}))
        monkeypatch.setattr(t, "_transcribe_local", lambda *a, **k: routed.setdefault("local", True) and ([], {}))

        t.transcribe_audio(__import__("pathlib").Path(wav), engine_override="cloud")
        assert routed.get("cloud") is True
        assert "local" not in routed


# ============================================================
# R1 — 实时链路本地模式降级声明（拒绝云端 WS）
# ============================================================

class TestRealtimeDegradation:
    def test_realtime_mode_local(self, monkeypatch):
        import app.settings_store as ss
        import core.realtime_asr as ra

        monkeypatch.setattr(ss, "get_engine_config", lambda: {"mode": "local", "local": {}})
        assert ra._get_asr_mode() == "local"

    def test_realtime_start_raises_in_local_mode(self, monkeypatch):
        import core.realtime_asr as ra

        monkeypatch.setattr(ra, "_get_asr_mode", lambda: "local")
        tr = ra.RealtimeTranscriber()
        with pytest.raises(LocalEngineError) as ei:
            tr.start()
        assert ei.value.error_code == "realtime_degraded_to_batch"
        assert ei.value.can_fallback_cloud is False
