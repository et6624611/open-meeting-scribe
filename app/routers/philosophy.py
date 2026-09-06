"""
app/routers/philosophy.py — 理念传播

从 data/philosophies.json 随机返回一条理念，供前端在页面底部展示。
"""

import json
import random

from fastapi import APIRouter

from app.store import PHILOSOPHIES_FILE

router = APIRouter(tags=["philosophy"])


@router.get("/api/philosophy/random")
def get_random_philosophy():
    """随机返回一条理念文本"""
    if not PHILOSOPHIES_FILE.exists():
        return {"text": ""}
    items = json.loads(PHILOSOPHIES_FILE.read_text(encoding="utf-8"))
    if not items:
        return {"text": ""}
    return {"text": random.choice(items)}
