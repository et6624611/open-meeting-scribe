"""
tests/test_hotword_mapping_lines.py — 映射文件按行格式的写入门禁

背景：data/hotword_mappings.txt 是「一行一组映射」的行式文件。划词工具栏曾经把多行
选区原样序列化成一条映射写入，结果一行变 N 行，其中恰好含分隔符的那行又被解析成一条
真实生效的映射（如「对。比如说→ZZZ」）——下一次转写就会静默改坏语料。POST 端点现拒绝
任何不构成「左→右」的行，把静默损坏换成 400。
"""

import pytest
from fastapi import HTTPException

from app.routers import hotwords as hw_router
from app.routers.hotwords import HotwordMappingsSaveRequest, _validate_mapping_lines


def test_well_formed_lines_are_kept_verbatim():
    raw = "怡岭→以岭\nES->EAS\n# 注释行\n\n"

    assert _validate_mapping_lines(raw) == ["怡岭→以岭", "ES->EAS"]


@pytest.mark.parametrize("raw, expected", [
    # 有分隔符但某一侧为空（行内编辑清掉了目标）：丢弃该条，不阻断整次保存
    ("怡岭→", []),
    ("→以岭", []),
    ("怡岭→以岭\n圣一→", ["怡岭→以岭"]),
    # 空输入归一为空列表，而非一个换行
    ("", []),
    ("\r\n", []),
])
def test_degenerate_mappings_are_dropped_not_fatal(raw, expected):
    assert _validate_mapping_lines(raw) == expected


@pytest.mark.parametrize("raw", [
    "怡岭\n以岭",          # 多行选区被拆成两行：两行都不是映射 → 真正的损坏源
    "对。比如说→ZZZ\n随便一句话",   # 半合法：合法行也不能替脏行开绿灯
])
def test_lines_without_separator_raise_400(raw):
    with pytest.raises(HTTPException) as exc:
        _validate_mapping_lines(raw)

    assert exc.value.status_code == 400
    assert "mapping line(s)" in exc.value.detail


def test_save_endpoint_rejects_and_never_touches_the_file(tmp_path, monkeypatch):
    """校验必须先于写文件：坏请求不得留下半个文件。"""
    target = tmp_path / "hotword_mappings.txt"
    monkeypatch.setattr(hw_router, "HOTWORD_MAPPINGS_FILE", target)

    with pytest.raises(HTTPException):
        hw_router.save_hotword_mappings(HotwordMappingsSaveRequest(mappings="怡岭\n以岭"))

    assert not target.exists()


def test_save_endpoint_normalizes_crlf_and_writes_clean_file(tmp_path, monkeypatch):
    target = tmp_path / "hotword_mappings.txt"
    monkeypatch.setattr(hw_router, "HOTWORD_MAPPINGS_FILE", target)

    result = hw_router.save_hotword_mappings(
        HotwordMappingsSaveRequest(mappings="怡岭→以岭\r\n圣一→胜意\r\n")
    )

    assert result == {"ok": True, "count": 2}
    assert target.read_text(encoding="utf-8") == "怡岭→以岭\n圣一→胜意\n"
