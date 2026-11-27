"""core/pipeline_runner.py 单元测试：Stage1/Stage2 正常路径、瞬时错误重试、永久错误不重试。

全部 mock，离线可跑，单文件 <20s。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import requests

import core.pipeline_runner as pr
from core import settings_store, task_store

# ── 通用 fixture：隔离 side effects ─────────────────────────────


@pytest.fixture(autouse=True)
def _runner_isolation(monkeypatch):
    """每个用例前清理 tasks dict，并屏蔽磁盘写入与 sleep。"""
    task_store.tasks.clear()
    monkeypatch.setattr(task_store, "save_task_to_disk", lambda tid: None)
    monkeypatch.setattr(pr.joblog, "append_event", lambda *a, **k: None)
    monkeypatch.setattr(pr.time, "sleep", lambda s: None)
    # _cleanup_normalized_intermediate 里读 storage config + 删文件，屏蔽
    monkeypatch.setattr(pr, "_cleanup_normalized_intermediate", lambda tid: None)
    # 分层匹配里的文本桥接/声纹/feature_flags —— 统一空壳
    monkeypatch.setattr(pr.speakers, "resolve_display_names", lambda uuid_list: {})
    monkeypatch.setattr(pr.text_bridge, "text_bridge_match", lambda **kw: ([], {}))
    monkeypatch.setattr(pr.voiceprint, "auto_identify_speakers", lambda **kw: [])
    monkeypatch.setattr(pr.voiceprint, "build_auto_mapping", lambda r: {})
    monkeypatch.setattr(pr.speakers, "get_speaker_by_id", lambda uid: None)
    # get_feature_flags 是模块级导入的函数，用 setattr(module, name, value) 形式
    monkeypatch.setattr(settings_store, "get_feature_flags", lambda: {"voiceprint_auto_match": False})
    # 用量计量 —— 吞掉
    try:
        import core.metering
        monkeypatch.setattr(core.metering, "is_metered", lambda: False)
    except Exception:
        pass
    # 自动书面化钩子 —— 吞掉
    try:
        import core.transcript_formal
        monkeypatch.setattr(core.transcript_formal, "maybe_auto_formalize", lambda tid: None)
    except Exception:
        pass
    # 知识库同步 —— 吞掉
    try:
        import core.projects
        monkeypatch.setattr(core.projects, "sync_meeting_to_folders", lambda t: None)
    except Exception:
        pass


def _mk_dialogue(speakers=1):
    return [
        {"speaker_id": i, "text": f"说话人{i}的发言内容。" * 3,
         "sentences": [{"text": f"说话人{i}的发言内容。"}], "speaker_name": f"用户{i}" if i == 0 else None}
        for i in range(speakers)
    ]


def _empty_dialogue():
    return []


# ================================================================
# Stage1（run_pipeline_task）
# ================================================================


class TestRunPipelineTaskStage1:
    def test_normal_success_first_attempt(self, monkeypatch, tmp_path):
        calls = []
        dialogue = _mk_dialogue(speakers=2)

        def fake_stage1(**kwargs):
            calls.append(kwargs)
            return {
                "dialogue": dialogue,
                "audio_duration": 120.0,
                "normalized_path": str(tmp_path / "audio_normalized.wav"),
            }

        def fake_stage2(**kwargs):
            return {
                "summary": "# 纪要",
                "title": "会议",
                "output_path": str(tmp_path / "x.md"),
                "dialogue": dialogue,
                "speaker_mapping": {},
                "speaker_uuid_mapping": {},
                "chapters": [],
            }

        monkeypatch.setattr(pr, "run_pipeline_stage1", fake_stage1)
        monkeypatch.setattr(pr, "run_pipeline_stage2", fake_stage2)
        monkeypatch.setattr(pr, "estimate_speaker_count", lambda p: 2)

        tid = "tsk-s1-ok"
        task_store.tasks[tid] = {"task_id": tid, "status": "processing"}
        fake_audio = tmp_path / "meeting.wav"
        fake_audio.write_bytes(b"\x00" * 1024)

        pr.run_pipeline_task(tid, fake_audio, "meeting.wav")

        task = task_store.tasks[tid]
        assert len(calls) == 1
        assert task["status"] == "completed"
        assert task.get("retry_count", 0) == 0
        assert len(task["dialogue"]) == 2
        assert task.get("audio_duration") == 120.0

    def test_transient_error_retries_then_succeeds(self, monkeypatch, tmp_path):
        """第一次瞬时失败、第二次成功 → retry_count=1，最终 completed。"""
        calls = []
        dialogue = _mk_dialogue(speakers=1)

        def fake_stage1(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise requests.exceptions.Timeout("Read timed out")
            return {
                "dialogue": dialogue,
                "audio_duration": 60.0,
            }

        def fake_stage2(**kwargs):
            return {
                "summary": "# 纪要", "title": "t",
                "output_path": "/tmp/x.md", "dialogue": dialogue,
                "speaker_mapping": {}, "speaker_uuid_mapping": {}, "chapters": [],
            }

        monkeypatch.setattr(pr, "run_pipeline_stage1", fake_stage1)
        monkeypatch.setattr(pr, "run_pipeline_stage2", fake_stage2)
        monkeypatch.setattr(pr, "estimate_speaker_count", lambda p: 1)

        tid = "tsk-s1-retry"
        task_store.tasks[tid] = {"task_id": tid, "status": "processing"}
        fake_audio = tmp_path / "m.wav"
        fake_audio.write_bytes(b"\x00" * 1024)

        pr.run_pipeline_task(tid, fake_audio, "m.wav")

        task = task_store.tasks[tid]
        assert len(calls) == 2
        assert task["status"] == "completed"
        assert task["retry_count"] == 1

    def test_permanent_error_no_retry(self, monkeypatch, tmp_path):
        """永久错误（如 ValueError）→ 只调 1 次 → 直接 failed，retry_count 未递增。"""
        calls = []

        def fake_stage1(**kwargs):
            calls.append(kwargs)
            raise ValueError("输入参数非法")

        monkeypatch.setattr(pr, "run_pipeline_stage1", fake_stage1)
        monkeypatch.setattr(pr, "estimate_speaker_count", lambda p: 1)
        monkeypatch.setattr(pr, "_try_realtime_fallback", lambda *a, **k: False)

        tid = "tsk-s1-perm"
        task_store.tasks[tid] = {"task_id": tid, "status": "processing"}
        fake_audio = tmp_path / "m.wav"
        fake_audio.write_bytes(b"\x00" * 1024)

        pr.run_pipeline_task(tid, fake_audio, "m.wav")

        task = task_store.tasks[tid]
        assert len(calls) == 1
        assert task["status"] == "failed"
        assert task["failed_stage"] == "transcribe"

    def test_transient_exhausted_all_retries(self, monkeypatch, tmp_path):
        """瞬时错误耗尽所有重试 → 最终 failed（PIPELINE_MAX_RETRIES=2，共 3 次尝试）。"""
        calls = []

        def fake_stage1(**kwargs):
            calls.append(kwargs)
            raise requests.exceptions.ConnectionError("connection reset")

        monkeypatch.setattr(pr, "run_pipeline_stage1", fake_stage1)
        monkeypatch.setattr(pr, "estimate_speaker_count", lambda p: 1)
        monkeypatch.setattr(pr, "_try_realtime_fallback", lambda *a, **k: False)

        tid = "tsk-s1-exhaust"
        task_store.tasks[tid] = {"task_id": tid, "status": "processing"}
        fake_audio = tmp_path / "m.wav"
        fake_audio.write_bytes(b"\x00" * 1024)

        pr.run_pipeline_task(tid, fake_audio, "m.wav")

        task = task_store.tasks[tid]
        assert len(calls) == 3  # 0,1,2 三次
        assert task["status"] == "failed"
        assert task["retry_count"] == 2


# ================================================================
# Stage2（_run_stage2_for_task）
# ================================================================


class TestRunStage2ForTask:
    def test_normal_success(self, monkeypatch, tmp_path):
        dialogue = _mk_dialogue(speakers=2)
        tid = "tsk-s2-ok"
        task_store.tasks[tid] = {
            "task_id": tid,
            "dialogue": dialogue,
            "status": "processing",
            "progress": 50,
        }

        calls = []

        def fake_stage2(**kwargs):
            calls.append(kwargs)
            return {
                "summary": "# 会议纪要\n\n## 主要结论\n大家决定继续推进。",
                "title": "本周例会",
                "output_path": str(tmp_path / "out.md"),
                "dialogue": dialogue,
                "speaker_mapping": {0: "张三"},
                "speaker_uuid_mapping": {},
                "chapters": [],
            }

        monkeypatch.setattr(pr, "run_pipeline_stage2", fake_stage2)

        pr._run_stage2_for_task(tid, tmp_path / "a.wav", None)

        task = task_store.tasks[tid]
        assert len(calls) == 1
        assert task["status"] == "completed"
        assert task["progress"] == 100
        assert task["title"] == "本周例会"
        assert task["speaker_mapping"] == {0: "张三"}

    def test_transient_retries_then_succeeds(self, monkeypatch, tmp_path):
        # 注意：requests.exceptions.Timeout 会触发 D018a 超时降级（body_only 重跑），
        # 不走 transient retry 循环；用 ConnectionError 才能测真正的 retry_count
        dialogue = _mk_dialogue()
        tid = "tsk-s2-retry"
        task_store.tasks[tid] = {"task_id": tid, "dialogue": dialogue, "status": "processing", "progress": 50}

        calls = []

        def fake_stage2(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise requests.exceptions.ConnectionError("connection reset")
            return {
                "summary": "# 纪要", "title": "t",
                "output_path": "/tmp/x.md", "dialogue": dialogue,
                "speaker_mapping": {}, "speaker_uuid_mapping": {}, "chapters": [],
            }

        monkeypatch.setattr(pr, "run_pipeline_stage2", fake_stage2)

        pr._run_stage2_for_task(tid, tmp_path / "a.wav", None)

        task = task_store.tasks[tid]
        assert len(calls) == 2
        assert task["status"] == "completed"
        assert task.get("retry_count", 0) == 1

    def test_permanent_error_no_retry(self, monkeypatch, tmp_path):
        dialogue = _mk_dialogue()
        tid = "tsk-s2-perm"
        task_store.tasks[tid] = {"task_id": tid, "dialogue": dialogue, "status": "processing"}

        calls = []

        def fake_stage2(**kwargs):
            calls.append(kwargs)
            raise RuntimeError("模型不可用")

        monkeypatch.setattr(pr, "run_pipeline_stage2", fake_stage2)

        pr._run_stage2_for_task(tid, tmp_path / "a.wav", None)

        task = task_store.tasks[tid]
        assert len(calls) == 1
        assert task["status"] == "failed"
        assert task["failed_stage"] == "summarize"

    def test_empty_dialogue_marks_failed_directly(self, monkeypatch, tmp_path):
        """空 dialogue 不应进 stage2 重试循环，直接 failed。"""
        tid = "tsk-s2-empty"
        task_store.tasks[tid] = {"task_id": tid, "dialogue": [], "status": "processing"}

        calls = []

        def fake_stage2(**kwargs):
            calls.append(kwargs)
            return {"summary": "# 空纪要"}

        monkeypatch.setattr(pr, "run_pipeline_stage2", fake_stage2)

        pr._run_stage2_for_task(tid, tmp_path / "a.wav", None)

        task = task_store.tasks[tid]
        assert len(calls) == 0  # 根本没调用 stage2
        assert task["status"] == "failed"
        assert task["failed_stage"] == "transcribe"


# ================================================================
# 错误分类 & is_transient_error 集成
# ================================================================


class TestErrorClassificationInPipeline:
    def test_classify_error_applied_on_failure(self, monkeypatch, tmp_path):
        dialogue = _mk_dialogue()
        tid = "tsk-classify"
        task_store.tasks[tid] = {"task_id": tid, "dialogue": dialogue, "status": "processing"}

        # 故意让 classify_error 返回一个带错误码的结构，验证任务状态字段被正确写入
        monkeypatch.setattr(pr, "classify_error", lambda e: {
            "category": "local_engine",
            "error_code": "engine_timeout",
            "can_fallback_cloud": True,
            "message": str(e),
            "suggestion": "请重试",
        })

        def fake_stage2(**kwargs):
            raise RuntimeError("引擎超时")

        monkeypatch.setattr(pr, "run_pipeline_stage2", fake_stage2)

        pr._run_stage2_for_task(tid, tmp_path / "a.wav", None)

        task = task_store.tasks[tid]
        assert task["status"] == "failed"
        assert task["error_category"] == "local_engine"
        assert task["error_suggestion"] == "请重试"
        assert task["failed_stage"] == "summarize"

    def test_transient_detected_by_keyword(self, monkeypatch, tmp_path):
        """is_transient_error 对包含 'timeout' 关键词的异常也能识别（英文关键词）。"""
        calls = []

        def fake_stage1(**kwargs):
            calls.append(kwargs)
            raise RuntimeError("LLM request timeout, please retry later")

        monkeypatch.setattr(pr, "run_pipeline_stage1", fake_stage1)
        monkeypatch.setattr(pr, "estimate_speaker_count", lambda p: 1)
        monkeypatch.setattr(pr, "_try_realtime_fallback", lambda *a, **k: False)

        tid = "tsk-keyword"
        task_store.tasks[tid] = {"task_id": tid, "status": "processing"}
        fake_audio = tmp_path / "m.wav"
        fake_audio.write_bytes(b"\x00" * 1024)

        pr.run_pipeline_task(tid, fake_audio, "m.wav")
        # 包含 'timeout' → 被归为瞬时 → 3 次尝试
        assert len(calls) == 3


# ================================================================
# 辅助函数
# ================================================================


class TestBuildDialogueFromRealtime:
    def test_groups_by_speaker(self):
        entries = [
            {"text": "大家好，欢迎。", "speaker_id": 0, "begin_time": 0, "end_time": 1500},
            {"text": "好的，开始吧。", "speaker_id": 0, "begin_time": 1550, "end_time": 2000},
            {"text": "议题是什么？", "speaker_id": 1, "begin_time": 2000, "end_time": 3000},
            {"text": "预算问题。", "speaker_id": 0, "begin_time": 3000, "end_time": 4000},
        ]
        result = pr._build_dialogue_from_realtime(entries)
        assert len(result) == 3  # 0, 1, 0（speaker 切换时开启新 block）
        # 第一块：speaker 0 的两句话合并
        assert result[0]["speaker_id"] == 0
        assert len(result[0]["sentences"]) == 2
        assert "大家好" in result[0]["text"]

    def test_skips_empty_text(self):
        entries = [
            {"text": "", "speaker_id": 0, "begin_time": 0, "end_time": 1000},
            {"text": "  ", "speaker_id": 0, "begin_time": 1000, "end_time": 2000},
            {"text": "真实内容。", "speaker_id": 0, "begin_time": 2000, "end_time": 3000},
        ]
        result = pr._build_dialogue_from_realtime(entries)
        assert len(result) == 1
        assert result[0]["text"] == "真实内容。"

    def test_default_none_speaker_to_zero(self):
        entries = [
            {"text": "嗨", "begin_time": 0, "end_time": 1000},  # 无 speaker_id
        ]
        result = pr._build_dialogue_from_realtime(entries)
        assert len(result) == 1
        assert result[0]["speaker_id"] == 0

    def test_preserves_realtime_speaker_name(self):
        entries = [
            {"text": "嗨", "speaker_id": 0, "speaker_name": "张三",
             "begin_time": 0, "end_time": 1000},
        ]
        result = pr._build_dialogue_from_realtime(entries)
        assert result[0]["speaker_name"] == "张三"

    def test_empty_input(self):
        assert pr._build_dialogue_from_realtime([]) == []
        assert pr._build_dialogue_from_realtime(None) == []


# ================================================================
# Stage 2 入口归一化（热词映射，全来源共用）
# ================================================================


class TestStage2DialogueNormalization:
    """热词映射收口到 Stage 2 入口：录音/上传/原文导入共用，且同一内容只施加一次。"""

    @staticmethod
    def _fake_stage2(seen):
        def fake(**kwargs):
            seen["dialogue"] = kwargs["dialogue"]
            return {
                "summary": "# 纪要",
                "title": "会议",
                "output_path": "",
                "dialogue": kwargs["dialogue"],
                "speaker_mapping": {},
                "speaker_uuid_mapping": {},
                "chapters": [],
            }
        return fake

    @staticmethod
    def _mk_task(tid, dialogue):
        task_store.tasks[tid] = {"task_id": tid, "status": "processing", "dialogue": dialogue}

    def test_imported_dialogue_gets_hotword_mapping(self, monkeypatch):
        """导入原文路径此前无映射入口，应在 Stage 2 入口补齐。"""
        import core.hotwords as hw
        from core import decision_extract

        monkeypatch.setattr(hw, "apply_hotword_mappings", lambda text: text.replace("万阳", "万洋"))
        monkeypatch.setattr(decision_extract, "extract_decisions", lambda *a, **k: [])
        seen: dict = {}
        monkeypatch.setattr(pr, "run_pipeline_stage2", self._fake_stage2(seen))

        tid = "tsk-norm-import"
        self._mk_task(tid, [{"speaker_id": 0, "text": "万阳在西区。", "sentences": [{"text": "万阳在西区。"}]}])

        pr._run_stage2_for_task(tid, Path(""), None)

        task = task_store.tasks[tid]
        assert task["dialogue"][0]["text"] == "万洋在西区。"
        assert task["dialogue"][0]["sentences"][0]["text"] == "万洋在西区。"
        assert seen["dialogue"][0]["text"] == "万洋在西区。"
        assert task.get("dialogue_normalized_sig")

    def test_same_content_applied_once(self, monkeypatch):
        """映射非幂等（A→B、B→C 链）时，同一份内容重复跑也只施加一次。"""
        import core.hotwords as hw
        from core import decision_extract

        calls: list[str] = []

        def non_idempotent(text):
            calls.append(text)
            return text + "!"

        monkeypatch.setattr(hw, "apply_hotword_mappings", non_idempotent)
        monkeypatch.setattr(decision_extract, "extract_decisions", lambda *a, **k: [])
        seen: dict = {}
        monkeypatch.setattr(pr, "run_pipeline_stage2", self._fake_stage2(seen))

        tid = "tsk-norm-once"
        self._mk_task(tid, [{"speaker_id": 0, "text": "原句", "sentences": [{"text": "原句"}]}])

        pr._run_stage2_for_task(tid, Path(""), None)
        pr._run_stage2_for_task(tid, Path(""), None)

        assert task_store.tasks[tid]["dialogue"][0]["text"] == "原句!"
        assert len(calls) == 2  # 块 + 句，仅第一轮

    def test_changed_dialogue_normalized_again(self, monkeypatch):
        """重转写后内容变化，签名失效应重新归一化。"""
        import core.hotwords as hw
        from core import decision_extract

        monkeypatch.setattr(hw, "apply_hotword_mappings", lambda text: text.replace("万阳", "万洋"))
        monkeypatch.setattr(decision_extract, "extract_decisions", lambda *a, **k: [])
        seen: dict = {}
        monkeypatch.setattr(pr, "run_pipeline_stage2", self._fake_stage2(seen))

        tid = "tsk-norm-re"
        self._mk_task(tid, [{"speaker_id": 0, "text": "万阳在西区。", "sentences": []}])
        pr._run_stage2_for_task(tid, Path(""), None)

        task_store.tasks[tid]["dialogue"] = [
            {"speaker_id": 0, "text": "万阳改到了东区。", "sentences": []}
        ]
        pr._run_stage2_for_task(tid, Path(""), None)

        assert task_store.tasks[tid]["dialogue"][0]["text"] == "万洋改到了东区。"
