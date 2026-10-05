"""
app/routers/hotwords.py — 热词 + 映射管理 / Hotwords + mapping management
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.store import HOTWORD_MAPPINGS_FILE, HOTWORDS_FILE
from core import hotwords
from core.i18n import _

router = APIRouter(tags=["hotwords"])

# 映射文件的行格式：每组一行「错误识别→正确文本」（# 为注释）。
# 划词工具栏曾把多行选区原样写进来：一条映射被拆成 N 行，其中含→的那行又变成
# 一条真实生效的映射（如「对。比如说→ZZZ」），下一次转写就被静默改坏语料。
# 因此这里不接受「没有分隔符」或「左右任一侧为空」的行：把静默损坏换成响亮报错。
SEPARATORS = ("→", "->")


def _validate_mapping_lines(raw: str) -> list[str]:
    """校验并归一映射文本行 / Validate and normalize mapping lines.

    两类脏行区别对待：
      - 没有分隔符（多行选区的残段）→ 400。它们不是用户本意，写下去反而会在后续
        某行意外含分隔符时静默生效，必须阻断整次保存。
      - 有分隔符但右值空（行内编辑清掉了目标）→ 丢弃该条、不阻断整次保存。
        旧行为是写盘后在读取时被默默过滤（对用户等价于「不生效」），直接 400 会把
        一个可改回的小问题变成整页存不进去。

    Raises:
        HTTPException(400): 存在不含分隔符的行 / a line is not a mapping at all.
    """
    bad: list[str] = []
    kept: list[str] = []
    for line in raw.replace("\r", "").split("\n"):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        sep = next((s for s in SEPARATORS if s in text), None)
        if sep is None:
            bad.append(text)
            continue
        # 注意不要用 `_` 接 占位变量：会遮蔽 i18n 的翻译函数 `_()`
        parts = text.partition(sep)
        if not parts[0].strip() or not parts[2].strip():
            continue  # 退化映射：丢弃
        kept.append(text)
    if bad:
        preview = "、".join(b[:20] for b in bad[:3])
        raise HTTPException(
            400,
            _("{count} mapping line(s) are malformed (expected 「错误识别→正确文本」): {preview}").format(
                count=len(bad), preview=preview,
            ),
        )
    return kept


class HotwordsSaveRequest(BaseModel):
    hotwords: str = Field("", max_length=50000, description="热词文本，每行一个")


class HotwordMappingsSaveRequest(BaseModel):
    mappings: str = Field("", max_length=50000, description="热词映射文本，每行一组")


@router.get("/api/hotwords")
def get_hotwords():
    """获取热词列表 / Get hotwords list (read hotwords.txt)."""
    words = hotwords.load_hotwords(HOTWORDS_FILE)
    return {"hotwords": words, "count": len(words)}


@router.post("/api/hotwords")
def save_hotwords(data: HotwordsSaveRequest):
    """保存热词列表 / Save hotwords list (write hotwords.txt)."""
    raw = data.hotwords
    lines = [line.strip() for line in raw.split("\n") if line.strip() and not line.strip().startswith("#")]
    HOTWORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    HOTWORDS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "count": len(lines)}


@router.get("/api/hotword-mappings")
def get_hotword_mappings():
    """获取热词映射列表 / Get hotword mappings (read hotword_mappings.txt)."""
    mappings = hotwords.load_hotword_mappings(HOTWORD_MAPPINGS_FILE)
    return {
        "mappings": [{"from": k, "to": v} for k, v in mappings],
        "count": len(mappings),
    }


@router.post("/api/hotword-mappings")
def save_hotword_mappings(data: HotwordMappingsSaveRequest):
    """保存热词映射 / Save hotword mappings (write hotword_mappings.txt)."""
    kept = _validate_mapping_lines(data.mappings)
    HOTWORD_MAPPINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # 空列表也必须写成空文件（而非一个换行），否则会多出一个垃圾条目
    content = "\n".join(kept) + "\n" if kept else ""
    HOTWORD_MAPPINGS_FILE.write_text(content, encoding="utf-8")
    hotwords.invalidate_hotword_mappings_cache()
    mappings = hotwords.load_hotword_mappings(HOTWORD_MAPPINGS_FILE)
    return {"ok": True, "count": len(mappings)}
