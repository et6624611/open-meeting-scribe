"""app/routers/chat_actions_routes.py — AI 辅助动作端点。

端点：
  POST /api/optimize     — 文稿润色
  POST /api/inline-edit  — 行间 AI 改写
  POST /api/chat/title   — 会话自动命名
  GET  /api/models       — 可用模型列表

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-05（从 chat.py 拆分）
"""

import logging

from fastapi import APIRouter, HTTPException

from core.i18n import _

from .chat_shared import (
    INLINE_EDIT_SYSTEM_PROMPT,
    OPTIMIZE_SYSTEM_PROMPT,
    TITLE_SYSTEM_PROMPT,
    ChatTitleRequest,
    InlineEditRequest,
    OptimizeRequest,
    _chat_model_default,
    _executor_tag,
    _model_usage_meta,
    _sanitize_chat_title,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _chat_mod():
    """延迟获取 chat 模块（让测试 monkeypatch chat.async_chat_completion 生效）。"""
    import app.routers.chat as _chat  # noqa: E402
    return _chat


DASHSCOPE_MODELS = [
    {"id": "qwen-plus", "name": "Qwen3.7-Plus", "provider": "DashScope"},
    {"id": "qwen-max", "name": "Qwen3.7-Max", "provider": "DashScope"},
    {"id": "qwen-turbo", "name": "Qwen3.7-Turbo", "provider": "DashScope"},
    {"id": "qwen-long", "name": "Qwen-Long", "provider": "DashScope"},
    {"id": "qwen2.5-72b-instruct", "name": "Qwen2.5-72B", "provider": "DashScope"},
    {"id": "qwen2.5-32b-instruct", "name": "Qwen2.5-32B", "provider": "DashScope"},
]

OTHER_MODELS = [
    {"id": "gpt-4o", "name": "GPT-4o", "provider": "OpenAI"},
    {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "OpenAI"},
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "provider": "Anthropic"},
    {"id": "deepseek-chat", "name": "DeepSeek Chat", "provider": "DeepSeek"},
    {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner", "provider": "DeepSeek"},
]
@router.post("/api/optimize")
async def optimize_text(data: OptimizeRequest):
    """文稿优化端点。 / Text optimization endpoint."""
    text = data.text.strip()
    if not text:
        raise HTTPException(400, _("Text cannot be empty"))
    model = data.model or _chat_model_default()  # 使用配置默认模型（与 /api/chat 对齐）
    messages = [
        {"role": "system", "content": OPTIMIZE_SYSTEM_PROMPT},
        {"role": "user", "content": f"请优化以下文本：\n\n{text}"},
    ]
    try:
        optimized = await _chat_mod().async_chat_completion(messages, model=model, max_tokens=4096, temperature=0.3)
        # 执行回显（AI 算力入口治理 §3）：成功响应携带实际消费方/计费口径
        return {"ok": True, "original": text, "optimized": optimized.strip(),
                "model_usage": _model_usage_meta(model)}
    except RuntimeError as e:
        # LLM 配置/服务错误 — 提示用户检查设置 + 执行方标识 / LLM config/service error → actionable hint + executor
        logger.error("文稿优化失败（LLM 配置/服务）: %s", e)
        raise HTTPException(
            503,
            _("AI service unavailable. Please check LLM configuration in Settings. ({err})").format(err=e)
            + " " + _executor_tag(model),
        )
    except Exception as e:
        logger.error("文稿优化失败: %s", e)
        raise HTTPException(500, _("Text refinement failed: {err}").format(err=e) + " " + _executor_tag(model))
@router.post("/api/inline-edit")
async def inline_edit(data: InlineEditRequest):
    """行间编辑端点。根据用户指令对选中文本进行 AI 改写。 / Inline edit endpoint. Rewrite selected text based on user instruction."""
    text = data.text.strip()
    instruction = data.instruction.strip()
    if not text:
        raise HTTPException(400, _("Text cannot be empty"))
    if not instruction:
        raise HTTPException(400, _("Instruction cannot be empty"))
    model = data.model or _chat_model_default()  # 使用配置默认模型（与 /api/chat 对齐）
    messages = [
        {"role": "system", "content": INLINE_EDIT_SYSTEM_PROMPT},
        {"role": "user", "content": f"改写指令：{instruction}\n\n原文：\n{text}"},
    ]
    try:
        edited = await _chat_mod().async_chat_completion(messages, model=model, max_tokens=4096, temperature=0.3)
        # 执行回显（AI 算力入口治理 §3）：成功响应携带实际消费方/计费口径
        return {"ok": True, "original": text, "edited": edited.strip(),
                "model_usage": _model_usage_meta(model)}
    except RuntimeError as e:
        # LLM 配置/服务错误 — 提示用户检查设置 + 执行方标识 / LLM config/service error → actionable hint + executor
        logger.error("行间编辑失败（LLM 配置/服务）: %s", e)
        raise HTTPException(
            503,
            _("AI service unavailable. Please check LLM configuration in Settings. ({err})").format(err=e)
            + " " + _executor_tag(model),
        )
    except Exception as e:
        logger.error("行间编辑失败: %s", e)
        raise HTTPException(500, _("Inline edit failed: {err}").format(err=e) + " " + _executor_tag(model))
@router.post("/api/chat/title")
async def chat_title(data: ChatTitleRequest):
    """会话自动命名（首轮完成后前端后台调用）。

    失败不回 5xx：命名是锦上添花，异常时回 ok=false 让前端静默保留默认名，
    避免后台任务把「AI 不可用」的错误横幅糊到用户脸上。
    """
    first = data.first_message.strip()
    if not first:
        raise HTTPException(400, _("Message cannot be empty"))
    model = data.model or _chat_model_default()
    user_content = f"用户提问：{first[:500]}"
    reply_snippet = (data.reply or "").strip()[:500]
    if reply_snippet:
        user_content += f"\n\nAI 回复：{reply_snippet}"
    messages = [
        {"role": "system", "content": TITLE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        raw = await _chat_mod().async_chat_completion(messages, model=model, max_tokens=40, temperature=0.3)
        return {"ok": True, "title": _sanitize_chat_title(raw)}
    except Exception as e:  # noqa: BLE001 - 命名失败静默降级，见端点 docstring
        logger.warning("[会话命名] 生成失败: %s", e)
        return {"ok": False, "title": ""}
@router.get("/api/models")
async def list_models():
    """获取可用模型列表。 / Get available model list."""
    return {
        "models": DASHSCOPE_MODELS + OTHER_MODELS,
        "dashscope_models": DASHSCOPE_MODELS,
    }
