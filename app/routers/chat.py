"""app/routers/chat.py — AI 对话路由聚合入口。

原 chat.py（1722 行，2026-11-05 拆分为 4 模块）：
  chat_shared.py          — 共享常量 / Pydantic 模型 / 工具函数 / 系统提示词
  chat_stream_routes.py  — /api/chat + /api/chat/stream + /api/chat/cancel + 智能体模式
  chat_actions_routes.py  — /api/optimize + /api/inline-edit + /api/chat/title + /api/models
  chat_history_routes.py  — /api/chat/attachments POST + GET

include_router 保持 URL 前缀与响应结构零变化；from app.routers.chat import X
通过 chat_shared re-export 保持向后兼容。
"""

from fastapi import APIRouter

from .chat_actions_routes import router as _actions_router
from .chat_history_routes import router as _history_router
from .chat_shared import *  # noqa: F401,F403
# ⚠️ from X import * 默认不导出 _ 开头的名字，显式 re-export 保持向后兼容
from .chat_shared import (  # noqa: F401
    ATTACHMENT_TEXT_CAP,
    CHAT_QA_SYSTEM_PROMPT,
    CHAT_SYSTEM_PROMPT,
    MAX_CHAT_MESSAGE_LEN,
    MENTION_TRANSCRIPT_CAP,
    _agent_system_prompt,
    _audit_reply_claims,
    _build_attachment_parts,
    _build_chat_context_blocks,
    _build_page_context,
    _chat_model_default,
    _detect_action,
    _execute_and_verify_edits,
    _executor_tag,
    _format_time_ms,
    _is_joblog_intent,
    _model_usage_meta,
    _sanitize_chat_title,
    _sanitize_edit_ops,
    _scan_mention_tokens,
    async_chat_completion,
    async_chat_completion_full,
    async_chat_completion_stream,
)
from .chat_stream_routes import router as _stream_router

router = APIRouter(tags=["chat"])
router.include_router(_stream_router)
router.include_router(_actions_router)
router.include_router(_history_router)
