"""
app/routers/update.py — 软件版本更新接口 / Software version update API

职责 / Responsibilities:
  1. 提供当前版本号查询 / Provide current version query
  2. 检查远端最新版本并比对 / Check and compare remote latest version
  3. 返回结构化的版本更新信息 / Return structured version update info

端点 / Endpoints:
  GET /api/update/version   — 获取当前版本号 / Get current version
  GET /api/update/check     — 检查是否有新版本 / Check for new version
"""

import logging

from fastapi import APIRouter

from app.store import load_settings
from core.version_check import check_for_update, get_current_version

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/update", tags=["版本更新"])


@router.get("/version")
def get_version():
    """获取当前软件版本号 / Get current software version."""
    return {"version": get_current_version()}


@router.get("/check")
def check_update(force: bool = False):
    """
    检查是否有新版本可用 / Check if new version is available.

    Query Params:
        force: 是否强制刷新（忽略缓存），默认 false / Force refresh (ignore cache); default false
    """
    settings = load_settings()
    result = check_for_update(settings=settings, force=force)
    return result
