"""
tests/test_text_correction.py — 划词映射全量回溯修正的行为契约

覆盖 core/text_correction 的四条承诺：
  1. 中文串走子串全量替换，ASCII 串走词边界（不被 FILES 之类误伤）
  2. 标识符 / 路径 / 时间戳 / 枚举值永不被改写（白名单按键名判定）
  3. 旁路产物（洞察 JSON、洞察板 HTML、导出纪要 md）一并落盘
  4. residual 归零，作为「REWRITE_KEYS 漏项」的自动告警信号
"""

import json
from pathlib import Path

import pytest

import core.text_correction as tc
from core.text_correction import correct_task_text, count_term, rewrite_task_payload

OLD, NEW = "怡岭", "以岭"


@pytest.fixture
def sample_task(tmp_path):
    """一份贴近真实形状的任务对象：嵌套 dialogue/sentences、list[str]、旁路文件路径。

    受保护字段（路径 / ID 映射）默认不含旧词，以便 residual 能干净地作为「白名单漏项」信号；
    它们含词时的行为另有用例覆盖。
    """
    export_md = tmp_path / "纪要.md"
    export_md.write_text(f"北京{OLD}商务酒店对接 EAS 系统", encoding="utf-8")
    return {
        "task_id": "t-1",
        "title": f"{OLD}专场沟通",
        "status": "completed",
        "summary": f"围绕{OLD}与{OLD}两条线展开",
        "user_notes": f"补充：{OLD}方参会",
        "audio_path": "/data/audio/t-1_raw.wav",
        "output_path": str(export_md),
        "created_at": "2026-09-22T17:16:32",
        "speaker_mapping": {"0": OLD},                 # 映射值是 ID 语义 → 必须不动
        "dialogue": [
            {"speaker_id": 0, "text": f"昨天去了{OLD}",
             "sentences": [{"begin_time": 0, "text": f"昨天去了{OLD}"},
                           {"begin_time": 100, "text": "另一句"}]},
        ],
        "chapters": [{"id": "ch1", "title": f"{OLD}议题", "key_points": [f"确认{OLD}排期", "其他"]}],
        "todos": [{"id": "d1", "text": f"联系{OLD}", "how": [f"约{OLD}见面"], "status": "to_start"}],
    }


def test_cjk_term_replaced_in_all_text_fields(sample_task):
    fields = rewrite_task_payload(sample_task, OLD, NEW)

    # title 1 + summary 2 + user_notes 1 + dialogue.text 1 + sentence.text 1
    # + chapter.title 1 + key_points 1 + todo.text 1 + todo.how 1
    assert sum(fields.values()) == 10
    assert sample_task["summary"] == f"围绕{NEW}与{NEW}两条线展开"
    assert sample_task["dialogue"][0]["sentences"][0]["text"] == f"昨天去了{NEW}"
    # speaker_mapping 的值是 uuid，白名单不认 → 故意保留原样（代价由 residual 显眼地报出）
    assert sample_task["speaker_mapping"] == {"0": OLD}


def test_list_str_fields_are_covered(sample_task):
    rewrite_task_payload(sample_task, OLD, NEW)

    assert sample_task["chapters"][0]["key_points"] == [f"确认{NEW}排期", "其他"]
    assert sample_task["todos"][0]["how"] == [f"约{NEW}见面"]


def test_identity_and_path_fields_never_touched(sample_task):
    sample_task["audio_path"] = f"/data/audio/{OLD}_raw.wav"   # 路径字面含旧词
    before = {k: sample_task[k] for k in ("audio_path", "created_at", "speaker_mapping", "status")}

    rewrite_task_payload(sample_task, OLD, NEW)

    for key, value in before.items():
        assert sample_task[key] == value, f"{key} 被误改，白名单应只覆盖内容字段"


def test_residual_surfaces_whitelist_gaps(sample_task, tmp_path, monkeypatch):
    """residual 的设计目的：白名单漏项 / 受保护字段含词时不静默，而是把残数报出来。"""
    monkeypatch.setattr(tc, "TASKS_DIR", tmp_path)   # 旁路文件均不存在，只看任务主体
    sample_task["margin_note"] = f"旁注：{OLD}"   # 假设的新增内容字段，尚未进 REWRITE_KEYS

    result = correct_task_text(sample_task, "t-1", OLD, NEW)

    assert result["hits"]["task"] == 10
    assert result["residual"] == 2, "margin_note 1 处 + speaker_mapping 1 处 → 提醒补录白名单"


def test_ascii_term_respects_word_boundary(sample_task):
    # 转写链路对纯 ASCII 词走邻接边界；回溯修正必须同一口径，否则 ES→EAS 会咬穿单词内部
    sample_task["summary"] = "EAS 与 FILES 里的 ES 都要对齐，讨论ES。与ES（星瀚）"

    rewrite_task_payload(sample_task, "ES", "EAS")

    # FILES 不伤、EAS 不伤；但紧贴汉字的「ES」必须命中（旧 \\b 规则下这两处会静默漏改）
    assert sample_task["summary"] == "EAS 与 FILES 里的 EAS 都要对齐，讨论EAS。与EAS（星瀚）"


def test_side_artifacts_and_residual_corrected(sample_task, tmp_path, monkeypatch):
    import core.insight_board as ib

    board_dir = tmp_path / "board"
    board_dir.mkdir()
    monkeypatch.setattr(ib, "BOARD_TASKS_DIR", board_dir)
    monkeypatch.setattr(tc, "TASKS_DIR", tmp_path)

    insights_file = tmp_path / "t-1.insights.json"
    insights_file.write_text(json.dumps({"messages": [
        {"id": "i1", "title": f"{OLD}的定位", "body": "…", "diagram": f"A[{OLD}] --> B",
         "actions": [{"key": "acknowledge", "label": f"{OLD} 收到"}]}
    ]}, ensure_ascii=False), encoding="utf-8")
    (board_dir / "t-1.board.html").write_text(
        f'<section data-ib-id="z1"><p>{OLD} 讨论</p></section>', encoding="utf-8"
    )

    result = correct_task_text(sample_task, "t-1", OLD, NEW)

    assert result["hits"] == {"task": 10, "insights": 3, "board": 1, "export_md": 1}
    assert result["replaced"] == 15
    # speaker_mapping 的值被故意不改，因此 residual 恰好报出这 1 处 —— 这就是漏项告警本应长成的样子
    assert result["residual"] == 1, count_term(json.dumps(sample_task, ensure_ascii=False), OLD)
    assert OLD not in insights_file.read_text(encoding="utf-8")
    assert OLD not in (board_dir / "t-1.board.html").read_text(encoding="utf-8")
    assert OLD not in Path(sample_task["output_path"]).read_text(encoding="utf-8")
    # 无命中时不得留下半成品：旁路产物也不应被重写
    sample_task["speaker_mapping"] = {"0": "spk-0"}
    again = correct_task_text(sample_task, "t-1", OLD, NEW)
    assert again["replaced"] == 0 and again["residual"] == 0


def test_board_rewritten_through_sanitizer_and_revision_bumped(sample_task, tmp_path, monkeypatch):
    """洞察板必须走 board_html_save 落盘：保留清洗防线与 revision 协议。"""
    import core.insight_board as ib

    board_dir = tmp_path / "board"
    board_dir.mkdir()
    monkeypatch.setattr(ib, "BOARD_TASKS_DIR", board_dir)
    monkeypatch.setattr(tc, "TASKS_DIR", tmp_path)
    (board_dir / "t-1.board.html").write_text(
        f'<section data-ib-id="z1"><p>{OLD} 讨论</p></section>', encoding="utf-8"
    )
    (board_dir / "t-1.board.meta.json").write_text('{"revision": 3}', encoding="utf-8")

    correct_task_text(sample_task, "t-1", OLD, NEW)

    meta = json.loads((board_dir / "t-1.board.meta.json").read_text(encoding="utf-8"))
    assert meta["revision"] == 4, "改写洞察板应升 revision，否则前端缓存判定会失效"
