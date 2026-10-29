"""录音助手（assistant 形态）本地控制面路由（契约 §4/§1.8 v1.1）。

挂载条件：``OMS_EDITION=assistant``——即装了企业配对能力的桌面助手进程。
个人版（不设 OMS_EDITION）与企业实例（enterprise）均不挂载本模块，零行为变化。
监听边界：本路由组仅在 127.0.0.1 服务上可达（部署边界由启动方式保证，同录音控制面纪律）。
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse

from ..local_sync import get_plane

router = APIRouter()


def assistant_mode() -> bool:
    return os.environ.get("OMS_EDITION", "").strip().lower() == "assistant"


class LocalAuthError(Exception):
    pass


def require_local_token(request: Request) -> str:
    """HTTP 面守卫：X-OMS-Local-Token 头或 oms_local_token 查询参数（WS 只能查询参数，v1.1 裁决）。"""
    token = request.headers.get("x-oms-local-token") or request.query_params.get("oms_local_token")
    if not get_plane().verify_local_token(token):
        raise LocalAuthError()
    return token or ""


@router.get("/api/local/handshake")
def handshake():
    """浏览器首连换 local_token（仅内存态，TTL 1h；重复握手旧 token 过期清理）。"""
    return get_plane().handshake()


@router.post("/api/local/register")
def register(body: dict):
    """助手配对：凭 Web 展示的一次性 pairing_code 兑换 device token 并持久化（0600）。"""
    try:
        return get_plane().register(
            server_url=body.get("server_url") or "", pairing_code=body.get("pairing_code") or ""
        )
    except ValueError as exc:
        return JSONResponse(status_code=404, content={"error": {"code": "pairing_invalid", "message": str(exc)}})
    except Exception as exc:
        return JSONResponse(
            status_code=502,
            content={"error": {"code": "register_failed", "message": f"实例不可达或拒绝（{type(exc).__name__}）"}},
        )


@router.get("/api/sync/queue")
def sync_queue(token: str = Depends(require_local_token)):
    """队列权威态（契约 v1.0 插单②）：前端"待同步到公司服务器"提示数据源。"""
    return {"queue": get_plane().queue_view()}


@router.post("/api/local/sync/enqueue")
def enqueue(body: dict, token: str = Depends(require_local_token)):
    """助手侧入队定稿快照（录音助手生成定稿后调用；离线安全，flush 由循环触发）。"""
    task_id = body.get("task_id")
    payload = body.get("payload")
    if not task_id or not isinstance(payload, dict):
        raise ValueError("task_id/payload 必填")
    item = get_plane().enqueue(task_id=task_id, payload=payload, base_rev=int(body.get("base_rev", 0)))
    return {"mutation_id": item["mutation_id"], "status": item["status"]}


@router.post("/api/local/sync/flush")
def flush(token: str = Depends(require_local_token)):
    """立即执行一轮推送（后台循环之外供手动触发/测试）。"""
    return get_plane().flush_once()


@router.get("/api/local/state")
def state(token: str = Depends(require_local_token)):
    st = get_plane().state()
    return {
        "paired": get_plane().paired,
        "server_url": st.get("server_url"),
        "paired_user_id": st.get("paired_user_id"),
        "device_id": st.get("device_id"),
    }  # device token 永不明文回显


@router.get("/api/local/storage")
def storage(token: str = Depends(require_local_token)):
    """本机数据目录用量与可写性（档位⑦设置页"数据位置/存储"数据源）。"""
    from ..local_storage import storage_snapshot

    return storage_snapshot()


@router.post("/api/local/storage/migrate")
def storage_migrate(body: dict, token: str = Depends(require_local_token)):
    """迁移本机数据目录：复制-校验-保留源（幂等可重跑）；切换生效=重启注入 OMS_DATA_ROOT。"""
    from fastapi.responses import JSONResponse

    from ..local_storage import migrate_data_dir

    target = body.get("target_dir") or ""
    try:
        return migrate_data_dir(target=target)
    except ValueError as exc:
        return JSONResponse(status_code=422, content={"error": {"code": "migrate_rejected", "message": str(exc)}})


def register_assistant_routes(app: FastAPI) -> None:
    app.include_router(router)

    @app.exception_handler(LocalAuthError)
    async def _lfe(request: Request, exc: LocalAuthError):  # noqa: ARG001
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=401, content={"error": {"code": "local_unauthenticated", "message": "需要有效 local_token"}})


def verify_ws_local_token(websocket: WebSocket) -> bool:
    """WS 承载裁决（v1.1）：浏览器 WebSocket 不能自定义头 → 查询参数 oms_local_token。"""
    token = websocket.query_params.get("oms_local_token")
    return get_plane().verify_local_token(token)
