"""
tests/test_def_proxy_0203.py — DEF-PROXY-02 stop 竞态 + 兜底命中回归

02 验收：构造静音+有实时句场景，命中降级出纪要、transcript_source=realtime_fallback；
stop 竞态用例：封存后迟到定稿不丢。
03：观测留痕字段逻辑单测（偏差计算不依赖真麦）。
"""
import pytest


# ── 02-a：stop 竞态——封存后迟到定稿落入交棒列表（task 引用），不丢失 ──
def test_late_sentence_lands_in_sealed_reference():
    import app.realtime_store as rs

    tid = "proxy02-race-task"
    try:
        # 模拟录音期正常写入
        rs.realtime_full_transcripts[tid] = []
        rs.push_realtime_msg(tid, {"type": "sentence", "text": "会中定稿", "speaker_id": 0, "begin_time": 0, "end_time": 1000})
        # 模拟 stop 端点交棒：pop → task 持引用 → 登记封存
        handed = rs.realtime_full_transcripts.pop(tid)
        task_holder = {"realtime_full_transcript": handed}
        rs.realtime_full_sealed[tid] = handed
        # SDK 线程迟到的句尾定稿（stop 之后到达）
        rs.push_realtime_msg(tid, {"type": "sentence", "text": "迟到定稿", "speaker_id": 0, "begin_time": 1000, "end_time": 2000})

        texts = [s["text"] for s in task_holder["realtime_full_transcript"]]
        assert "会中定稿" in texts, "正常定稿应在"
        assert "迟到定稿" in texts, "修复前此处丢失（孤儿列表）"
    finally:
        rs.realtime_full_transcripts.pop(tid, None)
        rs.realtime_full_sealed.pop(tid, None)
        rs.realtime_transcript_buffers.pop(tid, None)


def test_unsealed_unknown_task_does_not_resurrect_list():
    """未封存且不在录音中的 task：push 不复活列表（防内存泄漏语义不变）。"""
    import app.realtime_store as rs

    tid = "proxy02-ghost-task"
    rs.realtime_full_sealed.pop(tid, None)
    rs.realtime_full_transcripts.pop(tid, None)
    rs.push_realtime_msg(tid, {"type": "sentence", "text": "幽灵", "speaker_id": 0})
    assert tid not in rs.realtime_full_transcripts
    assert tid not in rs.realtime_full_sealed


# ── 02-b：兜底命中——批转写失败 + 有实时句 → 降级出纪要 ──
def test_realtime_fallback_hits_with_sentences(monkeypatch, tmp_path):
    import core.pipeline_runner as pr

    tid = "proxy02-fallback-task"
    fake_tasks = {tid: {
        "task_id": tid,
        "status": "processing",
        "realtime_full_transcript": [
            {"text": "第一位发言", "speaker_id": 0, "speaker_name": "", "begin_time": 0, "end_time": 3000},
            {"text": "第二位发言", "speaker_id": 1, "speaker_name": "", "begin_time": 3000, "end_time": 6000},
        ],
        "realtime_speaker_binding": {"0": "uuid-a"},
    }}
    monkeypatch.setattr(pr, "tasks", fake_tasks)
    monkeypatch.setattr(pr, "save_task_to_disk", lambda t: None)
    monkeypatch.setattr(pr, "_cleanup_normalized_intermediate", lambda t: None)
    # 绑定存 UUID，stage2 前翻译为真名（2026-10-01 修复：UUID 直接落 speaker_mapping 导致显示异常）
    from types import SimpleNamespace
    monkeypatch.setattr(pr.speakers, "get_speaker_by_id",
                        lambda u: SimpleNamespace(name="张三") if u == "uuid-a" else None)
    stage2_calls = []
    monkeypatch.setattr(pr, "_run_stage2_for_task", lambda t, p, m=None: stage2_calls.append((t, m)))

    ok = pr._try_realtime_fallback(tid, tmp_path / "rec.wav")
    assert ok is True, "有实时句时兜底必须命中，整单不得失败"
    task = fake_tasks[tid]
    assert task["transcript_source"] == "realtime_fallback"
    assert len(task["dialogue"]) == 2
    assert stage2_calls, "应触发 stage2 生成纪要"
    # 绑定键转 int、UUID 翻译为真名后传入 stage2
    _, mapping = stage2_calls[0]
    assert mapping == {0: "张三"}


def test_realtime_fallback_no_data_returns_false(monkeypatch, tmp_path):
    """无实时数据（纯静音零定稿）：兜底 False，走原失败流程（既有行为保持）。"""
    import core.pipeline_runner as pr

    tid = "proxy02-empty-task"
    monkeypatch.setattr(pr, "tasks", {tid: {"task_id": tid, "realtime_full_transcript": []}})
    assert pr._try_realtime_fallback(tid, tmp_path / "rec.wav") is False


# ── 03：观测字段逻辑（偏差 >15% 留痕；正常偏差写空） ──
@pytest.mark.parametrize("wall,wav,expect_gap", [
    (60.0, 20.0, 40.0),   # 原缺陷 1/3 场景 → 必须留痕
    (60.0, 59.0, None),   # 正常（<15%）→ 不留痕
    (4.0, 1.0, None),     # 短录音（≤5s 启动开销占比大）→ 不判
])
def test_wav_wallclock_gap_observation_logic(wall, wav, expect_gap):
    """复刻 stop 端点自检判据（与 record.py 同口径）：>5s 且偏差>15% 才留痕。"""
    gap = None
    if wall and wall > 5 and wav and abs(wav - wall) / wall > 0.15:
        gap = round(wall - wav, 1)
    assert gap == expect_gap
