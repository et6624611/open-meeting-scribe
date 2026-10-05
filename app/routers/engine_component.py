"""
app/routers/engine_component.py — 本地引擎组件安装路由（R8 / WP-G G-4b，D-G4 L2 层）

端点（与既有 /api/engine/*（模型资产，app/routers/models.py）平行，聚焦**组件本体**）：
  GET  /api/engine/component/status            组件三态 + 模型就绪 + 安装进度（只读，所有用户）
  POST /api/engine/component/install           一键安装：下载→校验→解包→落位锚点 engine/（变更面）
  POST /api/engine/component/install/cancel    取消进行中的安装（变更面）
  POST /api/engine/component/install-local     政企离线包：从本地 zip 安装（变更面）

权限：与 models.py 变更面同口径。管理员依赖采用合并容错导入——主干为
require_admin；本地单机放宽（require_admin_or_local，在途 WIP）合入后自动生效。

实现体：core/engine_installer.py（下载/校验/原子落位）；三态判定复用
core/engine_host.get_component_status()（G-5 首启引导同一数据源）。
"""

import logging

from fastapi import APIRouter, Depends

try:  # 合并容错：WIP（require_admin_or_local）先行合入则自动采用
    from app.routers.admin import require_admin_or_local as require_manage
except ImportError:
    from app.routers.admin import require_admin as require_manage

from core.engine_host import get_component_status, get_engine_host
from core.engine_installer import (
    cancel_install,
    get_install_state,
    install_from_zip,
    resolve_download_url,
    start_download_install,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/engine/component/status")
def get_component_install_status():
    """组件三态（not_installed / broken / protocol_mismatch / ready / dev_mode）
    + 模型就绪 + 安装任务进度——G-5 首启引导与『安装本地引擎』按钮的统一数据源。
    """
    component = get_component_status()
    try:
        models_ready = get_engine_host().status()["models_ready"]
    except Exception:
        models_ready = False
    return {
        "ok": True,
        "component": component,
        "models_ready": models_ready,
        "install": get_install_state(),
        "download_url": resolve_download_url() if component.get("state") != "dev_mode" else None,
    }


@router.post("/api/engine/component/install")
def post_component_install(data: dict = None, _: dict = Depends(require_manage)):
    """一键安装（后台执行，进度经 status 轮询）。

    body（可选）：{"source_url": "...", "sha256": "..."}——缺省按
    settings engine.local.component_url → GitHub Release 约定解析。
    """
    data = data or {}
    source_url = data.get("source_url") or None
    expected = data.get("sha256") or None
    result = start_download_install(source_url, expected)
    if not result.get("ok"):
        return {"ok": False, **result}
    return {"ok": True, "started": True, "url": resolve_download_url(source_url), "install": get_install_state()}


@router.post("/api/engine/component/install/cancel")
def post_component_install_cancel(_: dict = Depends(require_manage)):
    """取消进行中的下载/安装（解包落位阶段为秒级原子操作，取消点在下载与解包循环）。"""
    return {"ok": True, **cancel_install()}


@router.post("/api/engine/component/install-local")
def post_component_install_local(data: dict = None, _: dict = Depends(require_manage)):
    """政企离线包通道：从本地 zip 安装（同步执行，1GB 解包约 1–3 分钟）。

    body：{"zip_path": "...", "sha256"?: "..."}
    """
    data = data or {}
    zip_path = (data.get("zip_path") or "").strip()
    if not zip_path:
        return {"ok": False, "error_code": "bad_request", "error": "缺少 zip_path"}
    result = install_from_zip(zip_path, data.get("sha256") or None)
    return {"ok": bool(result.get("ok")), **result}
