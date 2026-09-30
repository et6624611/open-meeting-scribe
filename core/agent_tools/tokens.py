"""
core/agent_tools/tokens.py — 单轮短时工具令牌注册表 / Ephemeral per-turn tool-token registry

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
更新 / Updated: 2026-09-30
版本 / Version: 1.1.0

职责 / Responsibilities:
  - 为每个 CLI 引擎轮次签发一个进程内短时 bearer token，绑定任务上下文与授权范围
  - verify_token 供 /api/agent-tools/invoke 鉴权；轮次结束 revoke_token 立即失效
  - 令牌只存活于服务端内存（进程重启即清空），绝不落盘、绝不写进 settings.json（方案 §3.7-4）

安全 / Security:
  - 随机 32 字节 urlsafe；默认 TTL 15 分钟（远大于单轮 300s 上限，留人工取消余量）
  - 仅本机回环使用；调用方另受 /api/agent-tools 的 bearer 校验保护
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

# 默认令牌存活时间（秒）；比 CLI 单轮总超时（300s）宽裕，覆盖人工取消场景
DEFAULT_TTL_SECONDS = 900

_LOCK = threading.Lock()
# token → TokenContext
_STORE: dict[str, "TokenContext"] = {}


@dataclass
class TokenContext:
    """一次签发的工具令牌上下文 / A minted tool-token's bound context."""
    token: str
    task_id: str | None
    project_id: str | None
    auth_tier: str               # readonly | workspace_write | full_task
    writable: bool               # 是否允许写类工具（由 auth_tier 推导）
    expires_at: float
    allowed_tools: tuple[str, ...] = field(default=())
    # 轮次标识（完成护栏与按轮撤销的关联键）：写工具落盘时随快照记录 turn_id，
    # 前端据此一次请求回滚整轮（PROPOSAL §5.4 恢复入口）。
    turn_id: str = ""


def _can_write(auth_tier: str) -> bool:
    return auth_tier in ("workspace_write", "full_task")


def issue_token(*, task_id: str | None, project_id: str | None,
                auth_tier: str, ttl: int = DEFAULT_TTL_SECONDS,
                turn_id: str = "") -> TokenContext:
    """签发一个绑定任务上下文的短时令牌。 / Mint a short-lived, context-bound token."""
    token = secrets.token_urlsafe(32)
    ctx = TokenContext(
        token=token,
        task_id=task_id,
        project_id=project_id,
        auth_tier=auth_tier,
        writable=_can_write(auth_tier),
        expires_at=time.time() + ttl,
        turn_id=turn_id or "",
    )
    with _LOCK:
        _STORE[token] = ctx
        _sweep_locked()
    return ctx


def verify_token(token: str) -> TokenContext | None:
    """校验令牌并返回上下文；无效/过期返回 None（不抛异常）。"""
    if not token:
        return None
    now = time.time()
    with _LOCK:
        ctx = _STORE.get(token)
        if not ctx:
            return None
        if ctx.expires_at < now:
            _STORE.pop(token, None)
            return None
        return ctx


def revoke_token(token: str) -> None:
    """立即作废令牌（轮次结束时调用）。"""
    with _LOCK:
        _STORE.pop(token, None)


def active_token_count() -> int:
    """监控用：当前未过期令牌数。"""
    now = time.time()
    with _LOCK:
        return sum(1 for c in _STORE.values() if c.expires_at >= now)


def _sweep_locked() -> None:
    """惰性清理过期令牌（须在持锁时调用）。"""
    now = time.time()
    expired = [t for t, c in _STORE.items() if c.expires_at < now]
    for t in expired:
        _STORE.pop(t, None)
