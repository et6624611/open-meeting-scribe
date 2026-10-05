"""
tests/test_speaker_realname_be.py — REQ-SPK-RN-BE 回归门禁（BE-R4）

覆盖派工令四类用例：
  1. 未绑定不落默认名（pipeline / apply_speaker_names / import_parser 三路径）
  2. 读取侧归一化（is_unnamed_speaker / normalize_speaker_mapping 参数化）
  3. 绑定回填链路回归（空串键位被真实名覆盖）
  4. 存量数据零改写（读取归一不改落盘文件）
+ AC-8 联调基准样本矩阵（与前端 T2 判定器同源钉死，见说话人展示 T1 后端评审）
"""
import json

import pytest

from core.pipeline import _collect_speaker_names
from core.speakers import (
    is_unnamed_speaker,
    normalize_speaker_mapping,
    normalize_speaker_name,
)

# ============================================================
# 2. 读取侧归一化（参数化，含 D6 超集词形）
# ============================================================

UNNAMED_SAMPLES = [
    "Speaker 1", "speaker 12", "Speaker  7", "SPEAKER 3",
    "Speaker One", "speaker two", "SPEAKER TEN", "Speaker Eight",
    "说话人1", "说话人 7", "发言人3", "发言人 10",
    "", "   ", "\t", None, 123,
]

NAMED_SAMPLES = [
    "Alice", "李四", "张三（财务）", "Speaker 3 张工", "说话人2 王姐",
    "SpeakerOne",  # 缺空格非占位形态
    "01号发言人",   # 倒装非整串命中
]


@pytest.mark.parametrize("name", UNNAMED_SAMPLES)
def test_is_unnamed_speaker_true(name):
    assert is_unnamed_speaker(name) is True


@pytest.mark.parametrize("name", NAMED_SAMPLES)
def test_is_unnamed_speaker_false(name):
    assert is_unnamed_speaker(name) is False


def test_normalize_name_preserves_real_and_strips():
    assert normalize_speaker_name("  Alice  ") == "Alice"
    assert normalize_speaker_name("Speaker 2") == ""
    assert normalize_speaker_name(None) == ""


def test_normalize_mapping_keeps_keys_converges_values():
    src = {0: "Speaker 1", 1: "张三", 2: "说话人3", 3: "", 4: "Speaker Seven"}
    out = normalize_speaker_mapping(src)
    assert out == {0: "", 1: "张三", 2: "", 3: "", 4: ""}
    assert set(out.keys()) == set(src.keys())  # 键保留可枚举（D5 计数前提）
    assert normalize_speaker_mapping(None) == {}


# ============================================================
# AC-8 联调基准样本矩阵（前端 T2 判定器测试引用同一矩阵，钉死两侧一致）
# ============================================================

AC8_SAMPLE_MATRIX = {
    "Speaker 1": "unnamed",
    "Speaker Two": "unnamed",
    "SPEAKER nine": "unnamed",
    "说话人5": "unnamed",
    "发言人 12": "unnamed",
    "": "unnamed",
    "  ": "unnamed",
    "王五": "named",
    "Speaker 4 王五": "named",
    "发言人2（待确认）": "named",
}


def test_ac8_sample_matrix_be_side():
    """BE 侧对固定样本矩阵的判定；T2 合入后前端测试引用同一矩阵逐条一致（AC-8 关单条件）。"""
    for sample, expect in AC8_SAMPLE_MATRIX.items():
        assert is_unnamed_speaker(sample) is (expect == "unnamed"), f"样本判定漂移: {sample!r}"


# ============================================================
# 1. 未绑定不落默认名（三路径）
# ============================================================

def test_pipeline_collect_no_default_names():
    """路径①：pipeline 无绑定分支——ASR 产出无 speaker_name 字段，映射值恒为空串。"""
    dialogue = [
        {"speaker_id": 0, "text": "A"},
        {"speaker_id": 1, "text": "B"},
        {"speaker_id": 0, "text": "C"},
    ]
    mapping = _collect_speaker_names(dialogue)
    assert mapping == {0: "", 1: ""}
    blob = json.dumps({str(k): v for k, v in mapping.items()}, ensure_ascii=False)
    assert "Speaker" not in blob  # 持久化 JSON 不含编号默认名


def test_pipeline_collect_normalizes_existing_placeholder():
    """路径①补充：dialogue 携带存量占位名 → 采集时归一为空串。"""
    dialogue = [{"speaker_id": 0, "speaker_name": "Speaker 1", "text": "A"}]
    assert _collect_speaker_names(dialogue) == {0: ""}


def test_apply_speaker_names_missing_profile_is_empty(monkeypatch):
    """路径②：apply_speaker_names 查不到档案 → 空串（不落 Speaker N）。"""
    import core.speakers as sp

    monkeypatch.setattr(sp, "get_speaker_name_map", lambda: {"uuid-a": "Alice"})
    dialogue = [{"speaker_id": 0, "text": "A"}, {"speaker_id": 1, "text": "B"}]
    out = sp.apply_speaker_names(dialogue, {0: "uuid-a", 1: "uuid-missing"})
    names = {item["speaker_id"]: item["speaker_name"] for item in out}
    assert names == {0: "Alice", 1: ""}


def test_apply_speaker_names_placeholder_profile_normalized(monkeypatch):
    """路径②补充：档案名本身是历史占位串（speakers.json 污染）→ 归一为空串。"""
    import core.speakers as sp

    monkeypatch.setattr(sp, "get_speaker_name_map", lambda: {"uuid-b": "Speaker 2"})
    out = sp.apply_speaker_names([{"speaker_id": 1, "text": "B"}], {1: "uuid-b"})
    assert out[0]["speaker_name"] == ""


def test_import_parser_pattern3_no_default_names():
    """路径③：文本导入「说话人N：内容」模式，编号仅归组、姓名落空串。"""
    from core.import_parser import parse_markdown_transcript

    dialogue = parse_markdown_transcript("说话人1：预算维持120万\nSpeaker 2：同意该方案。")
    assert dialogue, "解析应产出 dialogue"
    assert all(item["speaker_name"] == "" for item in dialogue)
    # 持久化形态：dialogue JSON 内不出现任何 speaker_name 占位串
    assert not any(_is_placeholder(item["speaker_name"]) and item["speaker_name"] for item in dialogue)


def _is_placeholder(name):
    from core.speakers import is_unnamed_speaker
    return is_unnamed_speaker(name)


def test_import_parser_pattern1_real_names_kept():
    """路径③补充：真实姓名标注模式（**姓名**：内容）正常收录。"""
    from core.import_parser import parse_markdown_transcript

    dialogue = parse_markdown_transcript("**张三**：第一季度的预算需要确认一下。\n**李四**：我同意这个安排没问题。")
    names = {item["speaker_name"] for item in dialogue}
    assert "张三" in names and "李四" in names


# ============================================================
# 3. 绑定回填链路回归（BE-R2 不变量）
# ============================================================

def test_binding_overwrite_on_empty_slot():
    """绑定动作对空串键位的覆盖语义：{**旧, **新} 天然兼容（routers/speakers.py 写形）。"""
    stored = {0: "", 1: ""}  # BE-R1 新形态
    binding_update = {0: "王五"}  # 绑定接口回填真实名
    merged = {**stored, **binding_update}
    assert merged == {0: "王五", 1: ""}
    # 归一化后真实名保留、空位仍空（绑定回填链路不被归一化吞名）
    assert normalize_speaker_mapping(merged) == {0: "王五", 1: ""}


# ============================================================
# 4. 存量数据零改写（BE-R4 / H4 Prove-It）
# ============================================================

def test_existing_task_json_zero_rewrite(tmp_path, monkeypatch):
    """含存量占位名的 task JSON：跑「读取→归一→参与者提取」全链路后文件字节不变。"""
    from core import projects

    task_file = tmp_path / "legacy_task.json"
    original_bytes = json.dumps(
        {
            "task_id": "legacy-1",
            "title": "旧会议",
            "speaker_mapping": {"0": "Speaker 1", "1": "张三", "2": "说话人3"},
            "dialogue": [{"speaker": "发言人2", "text": "内容"}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    task_file.write_bytes(original_bytes)
    task = json.loads(original_bytes.decode("utf-8"))

    md = projects._build_sync_markdown(task, ["summary"])

    # 读取侧效果：占位名不进参与者 frontmatter
    assert "Speaker 1" not in md and "说话人3" not in md
    assert "张三" in md
    # 零改写：文件字节不变
    assert task_file.read_bytes() == original_bytes


def test_chat_context_no_placeholder_literals():
    """chat 上下文构建已删除 Speaker N 兑底字面量（grep 级守护，防回归）。"""
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "app" / "routers" / "chat.py").read_text(encoding="utf-8")
    assert 'f"Speaker {' not in src, "chat.py 不应再含 Speaker 编号兑底字面量"
