"""
app/routers/admin_config.py — 管理后台远程配置 API 路由 / Admin backend remote config API routes

职责 / Responsibilities:
  1. 消息管理（banner/toast/announcement CRUD + 启用/禁用） / Message management (banner/toast/announcement CRUD + enable/disable)
  2. 功能开关管理（feature flag CRUD + 启用/禁用） / Feature flag management (feature flag CRUD + enable/disable)

认证：复用 admin.py 的 require_admin 依赖 / Auth: reuses admin.py's require_admin dependency
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routers.admin import require_admin
from core import remote_config
from core.i18n import _

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["管理后台"])


# ============================================================
# 远程配置 — 消息管理 / Remote Config — Message Management
# ============================================================

class CreateMessageRequest(BaseModel):
    type: str = Field(default="banner", description="消息类型: banner/toast/announcement")
    title: str = Field(default="", description="标题（可选）")
    content: str = Field(..., description="消息内容")
    cta_text: str = Field(default="", description="行动按钮文案")
    cta_url: str = Field(default="", description="行动按钮链接")
    target: str = Field(default="guest", description="目标用户: all/guest/logged_in/tier:free")
    priority: int = Field(default=10, description="优先级（数字越大越优先）")
    enabled: bool = Field(default=True, description="是否启用")
    dismiss_mode: str = Field(default="delayed", description="关闭策略: session/delayed/permanent")
    dismiss_delay_days: int = Field(default=7, description="延迟重现天数")
    schedule_start: str | None = Field(default=None, description="生效开始时间（ISO 8601）")
    schedule_end: str | None = Field(default=None, description="生效结束时间（ISO 8601，null=长期）")


class UpdateMessageRequest(BaseModel):
    type: str = Field(default=None, description="消息类型")
    title: str = Field(default=None, description="标题")
    content: str = Field(default=None, description="消息内容")
    cta_text: str = Field(default=None, description="行动按钮文案")
    cta_url: str = Field(default=None, description="行动按钮链接")
    target: str = Field(default=None, description="目标用户")
    priority: int = Field(default=None, description="优先级")
    enabled: bool = Field(default=None, description="是否启用")
    dismiss_mode: str = Field(default=None, description="关闭策略")
    dismiss_delay_days: int = Field(default=None, description="延迟重现天数")
    schedule_start: str | None = Field(default=None, description="生效开始时间")
    schedule_end: str | None = Field(default=None, description="生效结束时间")


@router.get("/config/messages")
def admin_list_messages(_admin: dict = Depends(require_admin)):
    """消息列表（含已禁用的） / Message list (incl. disabled)"""
    messages = remote_config.list_messages()
    return {"messages": messages, "total": len(messages)}


@router.post("/config/messages")
def admin_create_message(
    req: CreateMessageRequest,
    _admin: dict = Depends(require_admin),
):
    """创建消息 / Create message"""
    valid_types = ("banner", "toast", "announcement")
    if req.type not in valid_types:
        raise HTTPException(400, _("Invalid type, options: {opts}").format(opts=', '.join(valid_types)))

    valid_targets = ("all", "guest", "logged_in")
    target_base = req.target.split(":")[0] if ":" in req.target else req.target
    if target_base not in valid_targets and not req.target.startswith("tier:"):
        raise HTTPException(400, _("Invalid target user, options: {opts} or tier:<name>").format(opts=', '.join(valid_targets)))

    valid_modes = ("session", "delayed", "permanent")
    if req.dismiss_mode not in valid_modes:
        raise HTTPException(400, _("Invalid dismissal policy, options: {opts}").format(opts=', '.join(valid_modes)))

    msg = remote_config.create_message(
        msg_type=req.type,
        title=req.title,
        content=req.content,
        cta_text=req.cta_text,
        cta_url=req.cta_url,
        target=req.target,
        priority=req.priority,
        enabled=req.enabled,
        dismiss_mode=req.dismiss_mode,
        dismiss_delay_days=req.dismiss_delay_days,
        schedule_start=req.schedule_start,
        schedule_end=req.schedule_end,
    )
    return {"success": True, "message": msg}


@router.put("/config/messages/{message_id}")
def admin_update_message(
    message_id: str,
    req: UpdateMessageRequest,
    _admin: dict = Depends(require_admin),
):
    """更新消息 / Update message"""
    existing = remote_config.get_message(message_id)
    if not existing:
        raise HTTPException(404, _("Message not found"))

    # 只传非 None 字段 / Only pass non-None fields
    kwargs = {}
    for key in ("type", "title", "content", "cta_text", "cta_url", "target", "priority", "enabled"):
        val = getattr(req, key, None)
        if val is not None:
            kwargs[key] = val
    if req.dismiss_mode is not None:
        kwargs["dismiss_mode"] = req.dismiss_mode
    if req.dismiss_delay_days is not None:
        kwargs["dismiss_delay_days"] = req.dismiss_delay_days
    if req.schedule_start is not None:
        kwargs["schedule_start"] = req.schedule_start
    if req.schedule_end is not None:
        kwargs["schedule_end"] = req.schedule_end

    msg = remote_config.update_message(message_id, **kwargs)
    return {"success": True, "message": msg}


@router.delete("/config/messages/{message_id}")
def admin_delete_message(
    message_id: str,
    _admin: dict = Depends(require_admin),
):
    """删除消息 / Delete message"""
    deleted = remote_config.delete_message(message_id)
    if not deleted:
        raise HTTPException(404, _("Message not found"))
    return {"success": True, "message_id": message_id}


@router.put("/config/messages/{message_id}/toggle")
def admin_toggle_message(
    message_id: str,
    _admin: dict = Depends(require_admin),
):
    """切换消息启用/禁用 / Toggle message enable/disable"""
    msg = remote_config.toggle_message(message_id)
    if not msg:
        raise HTTPException(404, _("Message not found"))
    return {"success": True, "message": msg}


# ============================================================
# 远程配置 — 功能开关 / Remote Config — Feature Flags
# ============================================================

class CreateFeatureFlagRequest(BaseModel):
    name: str = Field(..., description="标识名（唯一）")
    description: str = Field(default="", description="描述")
    enabled: bool = Field(default=True, description="是否启用")
    target: str = Field(default="all", description="生效对象: all/tier:xxx/users")
    target_users: list[str] = Field(default_factory=list, description="target=users 时的用户 ID 列表")


class UpdateFeatureFlagRequest(BaseModel):
    name: str = Field(default=None, description="标识名")
    description: str = Field(default=None, description="描述")
    enabled: bool = Field(default=None, description="是否启用")
    target: str = Field(default=None, description="生效对象")
    target_users: list[str] = Field(default=None, description="用户 ID 列表")


@router.get("/config/feature-flags")
def admin_list_feature_flags(_admin: dict = Depends(require_admin)):
    """功能开关列表 / Feature flag list"""
    flags = remote_config.list_feature_flags()
    return {"flags": flags, "total": len(flags)}


@router.post("/config/feature-flags")
def admin_create_feature_flag(
    req: CreateFeatureFlagRequest,
    _admin: dict = Depends(require_admin),
):
    """创建功能开关 / Create feature flag"""
    if not req.name.strip():
        raise HTTPException(400, _("Identifier name cannot be empty"))

    valid_targets = ("all", "users")
    target_base = req.target.split(":")[0] if ":" in req.target else req.target
    if target_base not in valid_targets and not req.target.startswith("tier:"):
        raise HTTPException(400, _("Invalid effective target, options: all, tier:<name>, users"))

    try:
        flag = remote_config.create_feature_flag(
            name=req.name.strip(),
            description=req.description,
            enabled=req.enabled,
            target=req.target,
            target_users=req.target_users,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"success": True, "flag": flag}


@router.put("/config/feature-flags/{flag_id}")
def admin_update_feature_flag(
    flag_id: str,
    req: UpdateFeatureFlagRequest,
    _admin: dict = Depends(require_admin),
):
    """更新功能开关 / Update feature flag"""
    existing = remote_config.get_feature_flag(flag_id)
    if not existing:
        raise HTTPException(404, _("Feature flag not found"))

    kwargs = {}
    for key in ("name", "description", "enabled", "target", "target_users"):
        val = getattr(req, key, None)
        if val is not None:
            if key == "name":
                val = val.strip()
            kwargs[key] = val

    try:
        flag = remote_config.update_feature_flag(flag_id, **kwargs)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"success": True, "flag": flag}


@router.delete("/config/feature-flags/{flag_id}")
def admin_delete_feature_flag(
    flag_id: str,
    _admin: dict = Depends(require_admin),
):
    """删除功能开关 / Delete feature flag"""
    deleted = remote_config.delete_feature_flag(flag_id)
    if not deleted:
        raise HTTPException(404, _("Feature flag not found"))
    return {"success": True, "flag_id": flag_id}


@router.put("/config/feature-flags/{flag_id}/toggle")
def admin_toggle_feature_flag(
    flag_id: str,
    _admin: dict = Depends(require_admin),
):
    """切换功能开关启用/禁用 / Toggle feature flag enable/disable"""
    flag = remote_config.toggle_feature_flag(flag_id)
    if not flag:
        raise HTTPException(404, _("Feature flag not found"))
    return {"success": True, "flag": flag}
