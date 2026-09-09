"""
app/routers/hotwords.py — 热词 + 映射管理
"""

from fastapi import APIRouter

from app.store import HOTWORDS_FILE, HOTWORD_MAPPINGS_FILE
from core import hotwords

router = APIRouter(tags=["hotwords"])


@router.get("/api/hotwords")
def get_hotwords():
    """获取热词列表（读 hotwords.txt）"""
    words = hotwords.load_hotwords(HOTWORDS_FILE)
    return {"hotwords": words, "count": len(words)}


@router.post("/api/hotwords")
def save_hotwords(data: dict):
    """保存热词列表（写 hotwords.txt）"""
    raw = data.get("hotwords", "")
    lines = [line.strip() for line in raw.split("\n") if line.strip() and not line.strip().startswith("#")]
    HOTWORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    HOTWORDS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "count": len(lines)}


@router.get("/api/hotword-mappings")
def get_hotword_mappings():
    """获取热词映射列表（读 hotword_mappings.txt）"""
    mappings = hotwords.load_hotword_mappings(HOTWORD_MAPPINGS_FILE)
    return {
        "mappings": [{"from": k, "to": v} for k, v in mappings],
        "count": len(mappings),
    }


@router.post("/api/hotword-mappings")
def save_hotword_mappings(data: dict):
    """保存热词映射（写 hotword_mappings.txt）"""
    raw = data.get("mappings", "")
    lines = raw.split("\n")
    HOTWORD_MAPPINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    HOTWORD_MAPPINGS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    hotwords.invalidate_hotword_mappings_cache()
    mappings = hotwords.load_hotword_mappings(HOTWORD_MAPPINGS_FILE)
    return {"ok": True, "count": len(mappings)}
