"""
app/routers/models.py — 本地引擎模型资产管理路由（R5 / WP-B）

权限（D-R2 已裁决：管理员级变更，普通用户只读；本地单机部署默认视为管理员）：
  - 只读：模型清单/状态、下载进度、引擎状态、存储信息 —— 所有用户可访问
  - 变更：启动/取消下载、校验、引擎启停、存储位置配置 —— require_admin_or_local

下载执行体见 core/model_downloader.py；常驻引擎子进程见 core/engine_host.py。
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.routers.admin import is_local_single_user, require_admin_or_local
from app.settings_store import load_settings, save_settings_to_disk
from core.engine_host import get_engine_host, invalidate_models_check
from core.model_downloader import (
    DISK_BUFFER_BYTES,
    cancel_download,
    get_jobs,
    models_overview,
    start_download,
    verify_model,
)
from core.model_registry import MODEL_BY_KEY, get_disk_free_bytes, get_model_dir

logger = logging.getLogger(__name__)

router = APIRouter(tags=["models"])


# ============================================================
# 只读面（所有用户） / Read-only surface (all users)
# ============================================================


# 命名空间说明：本地引擎模型资产统一挂在 /api/engine/* 下，避免与既有
# GET /api/models（chat 路由的 LLM 模型列表，且在 auth 白名单前缀内）冲突。
# Namespace: local-engine model assets live under /api/engine/* to avoid colliding
# with the existing GET /api/models (chat router's LLM model list, also auth-exempt).


@router.get("/api/engine/models")
def get_models():
    """模型清单 + 逐个状态 + 磁盘信息 + 活动下载 / Manifest, per-model status, disk info, active jobs."""
    return {"ok": True, **models_overview()}


@router.get("/api/engine/downloads")
def get_downloads():
    """下载任务进度（进度/速度/剩余/ETA） / Download job progress."""
    return {"ok": True, "jobs": get_jobs()}


@router.get("/api/engine/status")
def get_engine_status(request: Request):
    """引擎状态（模式/进程/模型就绪/篡改）——普通用户只读可见（D-R2）。

    can_manage 告知前端当前身份是否可操作变更面（本地单机模式或管理员 cookie），
    与 POST 变更面的 require_admin_or_local 判定保持一致，避免“看得到按钮却调不动”。
    """
    can_manage = is_local_single_user() or _admin_cookie_valid(request)
    return {"ok": True, "can_manage": can_manage, **get_engine_host().status()}


def _admin_cookie_valid(request: Request) -> bool:
    """不抛异常地判断请求是否携带有效管理员 cookie / Non-raising check for a valid admin cookie."""
    from app.routers.admin import ADMIN_COOKIE, _verify_admin_token
    token = request.cookies.get(ADMIN_COOKIE)
    return bool(token and _verify_admin_token(token))


@router.get("/api/engine/storage")
def get_storage():
    """模型存储位置与磁盘空间 / Model storage location and disk space."""
    model_dir = get_model_dir()
    return {
        "ok": True,
        "model_dir": str(model_dir),
        "disk_free_bytes": get_disk_free_bytes(model_dir),
    }


# ============================================================
# 变更面（管理员，D-R2） / Mutations (admin only)
# ============================================================


@router.post("/api/engine/download")
def post_download(data: dict = None, _: dict = Depends(require_admin_or_local)):
    """引导下载（model_key 或 "all"），后台执行；先做磁盘空间同步预检。"""
    data = data or {}
    model_key = (data.get("model_key") or "").strip()
    if not model_key:
        return {"ok": False, "error_code": "invalid_request", "error": "缺少 model_key（或传 'all'）"}
    if model_key != "all" and model_key not in MODEL_BY_KEY:
        return {"ok": False, "error_code": "unknown_model", "error": f"未知模型: {model_key}"}

    # 同步磁盘预检（下载线程内还有精确预检，此处提前给出行得通的错误）
    keys = list(MODEL_BY_KEY) if model_key == "all" else [model_key]
    declared = sum(MODEL_BY_KEY[k]["size_bytes"] for k in keys)
    free = get_disk_free_bytes(get_model_dir())
    if free < declared + DISK_BUFFER_BYTES:
        return {
            "ok": False,
            "error_code": "insufficient_disk",
            "error": (
                f"磁盘空间不足：下载 {model_key} 约需 {declared / 1024 / 1024:.0f}MB"
                f"（另需 {DISK_BUFFER_BYTES // 1024 // 1024}MB 缓冲），当前剩余 {free / 1024 / 1024:.0f}MB"
            ),
        }

    result = start_download(model_key)
    if not result.get("ok"):
        return result
    logger.info(f"[模型] 管理员启动下载: {model_key} → {len(result['jobs'])} 个任务")
    return result


@router.post("/api/engine/download/{job_id}/cancel")
def post_cancel_download(job_id: str, _: dict = Depends(require_admin_or_local)):
    """取消下载（保留 .part 分片，可续传）。"""
    result = cancel_download(job_id)
    if result.get("ok"):
        logger.info(f"[模型] 管理员取消下载任务: {job_id}")
    return result


@router.post("/api/engine/verify")
def post_verify(data: dict = None, _: dict = Depends(require_admin_or_local)):
    """完整性校验（篡改检测） / Integrity verification (tamper detection)."""
    data = data or {}
    model_key = (data.get("model_key") or "").strip()
    if model_key not in MODEL_BY_KEY:
        return {"ok": False, "error_code": "unknown_model", "error": f"未知模型: {model_key}"}
    result = verify_model(model_key)
    # 用户主动发起的实时校验完成后丢弃观测面缓存，避免 status 在 TTL 内继续回显旧结论。
    invalidate_models_check()
    return {"ok": result["status"] != "tampered", "model_key": model_key, **result}


@router.post("/api/engine/start")
def post_engine_start(_: dict = Depends(require_admin_or_local)):
    """启动常驻引擎子进程（含模型完整性预检，篡改拒载）。"""
    result = get_engine_host().start()
    logger.info(f"[引擎] 管理员启动引擎: ok={result.get('ok')} code={result.get('error_code', '')}")
    return result


@router.post("/api/engine/stop")
def post_engine_stop(_: dict = Depends(require_admin_or_local)):
    """停止常驻引擎子进程。"""
    return get_engine_host().stop()


@router.post("/api/engine/storage")
def post_storage(data: dict = None, _: dict = Depends(require_admin_or_local)):
    """配置模型存储位置（settings engine.local.model_dir，默认 data/models/）。"""
    data = data or {}
    model_dir = (data.get("model_dir") or "").strip()
    if not model_dir:
        return {"ok": False, "error_code": "invalid_request", "error": "model_dir 不能为空"}

    target = Path(model_dir).expanduser()
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        return {"ok": False, "error_code": "unwritable_dir", "error": f"目录不可写: {e}"}

    settings = load_settings()
    engine = settings.get("engine", {}) or {}
    local = engine.get("local", {}) or {}
    local["model_dir"] = model_dir
    engine["local"] = local
    settings["engine"] = engine
    save_settings_to_disk(settings)
    # 换目录等于换了一整套权重；缓存虽按目录锚定也会自然失效，此处显式清空以免歧义。
    invalidate_models_check()
    logger.info(f"[模型] 管理员更新存储位置: {model_dir}")
    return {"ok": True, "model_dir": model_dir, "disk_free_bytes": get_disk_free_bytes(target)}
