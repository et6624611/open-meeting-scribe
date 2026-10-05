"""
core/agent_tools — 智能体模式反向工具面（供本地 CLI 经 MCP 回连调用）
Agent-tools: the reverse control surface that a local CLI engine calls back into via MCP.

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

对应方案 / See: Qoder CLI 引擎方案 §3.4（MCP Bridge 双向集成）。

设计：
  - MCP bridge 是独立进程（由 CLI 拉起），无法共享服务端内存 tasks，只能经 HTTP 回连本机服务；
  - 每个 CLI 轮次由服务端签发一个"单轮短时 bearer token"（core/agent_tools/tokens），
    绑定 task_id / project_id / 授权档；bridge 用它调用 /api/agent-tools/invoke；
  - invoke 路由复用既有受控入口：读走 core.agent_tools.impl.execute_tool，写走 app.routers.notes
    的同一函数（继承 save_task_to_disk + 脏标记 + 审计），绝不另开写路径（方案 R5）。
"""

from __future__ import annotations

from core.agent_tools.tokens import (
    TokenContext,
    issue_token,
    revoke_token,
    verify_token,
)

__all__ = ["TokenContext", "issue_token", "revoke_token", "verify_token"]
