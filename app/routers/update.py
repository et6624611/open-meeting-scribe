"""
app/routers/update.py — 软件版本更新接口

职责：
  1. 提供当前版本号查询
  2. 检查远端最新版本并比对
  3. 返回结构化的版本更新信息

端点：
  GET /api/update/version   — 获取当前版本号
  GET /api/update/check     — 检查是否有新版本
"""

import logging

from fastapi import APIRouter

from app.store import load_settings
from core.version_check import get_current_version, check_for_update

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/update", tags=["版本更新"])


@router.get("/version")
def get_version():
    """获取当前软件版本号。"""
    return {"version": get_current_version()}


@router.get("/check")
def check_update(force: bool = False):
    """
    检查是否有新版本可用。

    Query Params:
        force: 是否强制刷新（忽略缓存），默认 false
    """
    settings = load_settings()
    result = check_for_update(settings=settings, force=force)
    return result
