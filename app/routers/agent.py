"""
app/routers/agent.py — Agent 角色工作区路由 / Agent role workspace routes

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-15
版本 / Version: 1.0.0

职责 / Responsibilities:
  - 列出可用角色（GET /api/agent/roles） / List available roles
  - 获取角色详情（GET /api/agent/roles/{name}） / Get role details
  - 获取角色文件内容（GET /api/agent/roles/{name}/files） / Get role file contents
  - Fork 预定义角色（POST /api/agent/roles/fork） / Fork a builtin role
  - 保存角色文件（PUT /api/agent/roles/{name}/files/{filename}） / Save role file
  - 删除自定义角色（DELETE /api/agent/roles/{name}） / Delete custom role

设计文档 / Design doc: docs/design/AGENT_ROLE_SYSTEM.md
架构决策 / ADR: docs/adr/0017-agent角色系统从硬编码提示词到md工作区.md
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.agent_workspace import (
    delete_role,
    fork_role,
    get_role_files,
    list_roles,
    resolve_agent_role,
    save_role_file,
)
from core.i18n import _
from app.settings_store import load_settings, save_settings_to_disk

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])

DEFAULT_ACTIVE_AGENT = "meeting-minutes"


@router.get("/api/agent/roles")
def get_agent_roles():
    """
    获取所有可用角色列表 / Get list of all available roles.

    返回预定义角色和用户自定义角色的元数据（不含完整提示词内容）。
    Returns metadata for built-in and custom roles (without full prompt content).
    """
    roles = list_roles()
    settings = load_settings()
    return {
        "roles": roles,
        "default": DEFAULT_ACTIVE_AGENT,
        "active_agent": settings.get("active_agent", DEFAULT_ACTIVE_AGENT),
    }


@router.get("/api/agent/active")
def get_active_agent():
    """
    获取当前激活的 AI 助手 / Get the currently active AI assistant.
    """
    settings = load_settings()
    return {"active_agent": settings.get("active_agent", DEFAULT_ACTIVE_AGENT)}


class SetActiveAgentRequest(BaseModel):
    agent: str  # 角色标识 / Role identifier


@router.put("/api/agent/active")
def set_active_agent(data: SetActiveAgentRequest):
    """
    设置当前激活的 AI 助手（持久化到 settings.json）。
    Set the currently active AI assistant (persisted to settings.json).
    """
    # 验证角色存在 / Validate role exists
    if resolve_agent_role(data.agent) is None:
        raise HTTPException(404, _("Role not found: {name}").format(name=data.agent))
    settings = load_settings()
    settings["active_agent"] = data.agent
    save_settings_to_disk(settings)
    logger.info("当前 AI 助手已切换为: %s", data.agent)
    return {"active_agent": data.agent}


@router.get("/api/agent/roles/{role_name}")
def get_agent_role(role_name: str):
    """
    获取指定角色的完整定义 / Get full definition of a specific role.

    包含 AGENT.md 正文和附带文件内容。
    Includes AGENT.md body and additional files content.
    """
    role = resolve_agent_role(role_name)
    if role is None:
        raise HTTPException(404, _("Role not found: {name}").format(name=role_name))
    return role


@router.get("/api/agent/roles/{role_name}/files")
def get_agent_role_files(role_name: str):
    """
    获取角色的所有文件内容（用于编辑器加载）。
    Get all file contents of a role (for editor loading).
    """
    result = get_role_files(role_name)
    if result is None:
        raise HTTPException(404, _("Role not found: {name}").format(name=role_name))
    return result


# ============================================================
# 角色管理（Fork / 编辑 / 删除） / Role management
# ============================================================

class ForkRoleRequest(BaseModel):
    source: str   # 源角色名（预定义） / Source role name (builtin)
    name: str     # 新角色名 / New role name


class SaveRoleFileRequest(BaseModel):
    content: str  # 文件内容 / File content


@router.post("/api/agent/roles/fork")
def post_fork_role(data: ForkRoleRequest):
    """
    从预定义角色 fork 为用户自定义角色。
    Fork a builtin role into a user custom role.
    """
    try:
        result = fork_role(data.source, data.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result


@router.put("/api/agent/roles/{role_name}/files/{filename}")
def put_save_role_file(role_name: str, filename: str, data: SaveRoleFileRequest):
    """
    保存用户自定义角色的 .md 文件。
    Save a .md file for a user custom role.
    """
    try:
        result = save_role_file(role_name, filename, data.content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result


@router.delete("/api/agent/roles/{role_name}")
def delete_agent_role(role_name: str):
    """
    删除用户自定义角色。预定义角色不可删除。
    Delete a user custom role. Builtin roles cannot be deleted.
    """
    try:
        result = delete_role(role_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result
