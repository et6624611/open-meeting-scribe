"""
core/cli_engine/mcp_bridge.py — 为单轮 CLI 调用生成 MCP 桥配置 + 签发短时令牌
Mint the per-turn MCP-bridge config (pointing the CLI at the OMS reverse-tool bridge).

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

对应方案 / See: Qoder CLI 引擎方案 §3.4（鉴权：--mcp-config 每轮动态生成、
短时 token、只监听 127.0.0.1）、§3.10-③（mcp-config 落系统临时目录 0600、用后即删）。

流程 / Flow:
  1. 在（服务端）进程内签发一个绑定任务上下文的短时 token（core.agent_tools.tokens）
  2. 写 mcp-config JSON 到系统临时目录（0600），命令为本仓库 mcp-bridge/server.py，
     env 注入 OMS_MCP_TOKEN + OMS_BASE_URL
  3. 返回 (config_path, token, tool_allowlist)；轮次结束调用 teardown 删文件 + 撤令牌
"""

from __future__ import annotations

import json
import logging
import os
import stat
import sys
import tempfile
from pathlib import Path

from core.agent_tools.tokens import TokenContext, issue_token, revoke_token

logger = logging.getLogger(__name__)

# MCP server 名（决定工具全名 mcp__oms-tools__<tool>，与 CLI 侧一致）
BRIDGE_SERVER_NAME = "oms-tools"
_BRIDGE_SCRIPT = Path(__file__).resolve().parents[2] / "mcp-bridge" / "server.py"


def manifest_has_mcp(engine_id: str) -> bool:
    """引擎清单是否声明 mcp_injection 能力（能力驱动，方案 §3.11-3）。"""
    try:
        from core.cli_engine.manifest import load_manifest
        return bool(load_manifest(engine_id).get("capabilities", {}).get("mcp_injection"))
    except Exception:  # noqa: BLE001
        return False


def _tool_allowlist(auth_tier: str) -> list[str]:
    """按授权档返回要预授权的 MCP 工具全名（--allowed-tools）。"""
    from core.agent_tools.catalog import TOOL_CATALOG
    writable = auth_tier in ("workspace_write", "full_task")
    names = []
    for t in TOOL_CATALOG:
        if t["kind"] == "write" and not writable:
            continue
        names.append(f"mcp__{BRIDGE_SERVER_NAME}__{t['name']}")
    return names


def build_bridge_config(*, task_id: str | None, project_id: str | None,
                        auth_tier: str, base_url: str,
                        turn_id: str = "") -> tuple[str, TokenContext, list[str]]:
    """
    签发令牌并写出 mcp-config，返回 (config_path, token_ctx, tool_allowlist)。

    调用方（chat 事件生成器，运行于服务端进程）负责在轮次结束调用 teardown_bridge。
    turn_id：本轮会话流标识，写工具据此落快照 → 支持「撤销本轮改写」整轮回滚。
    """
    ctx = issue_token(task_id=task_id, project_id=project_id, auth_tier=auth_tier,
                      turn_id=turn_id)

    config = {
        "mcpServers": {
            BRIDGE_SERVER_NAME: {
                "command": sys.executable,           # 与主程序同一解释器（venv / 打包环境一致）
                "args": [str(_BRIDGE_SCRIPT)],
                "env": {
                    "OMS_MCP_TOKEN": ctx.token,
                    "OMS_BASE_URL": base_url,
                },
            }
        }
    }

    fd, path = tempfile.mkstemp(prefix="oms-mcp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False)
    # 收紧权限 0600（含令牌，虽在临时目录）
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass

    logger.info("[MCP桥] 已签发令牌 task=%s tier=%s tools=%d", task_id, auth_tier,
                len(_tool_allowlist(auth_tier)))
    return path, ctx, _tool_allowlist(auth_tier)


def teardown_bridge(config_path: str, token: str) -> None:
    """删除临时 mcp-config 并撤销令牌（用后即删，方案 §3.10-③）。"""
    revoke_token(token)
    try:
        if config_path and os.path.isfile(config_path):
            os.unlink(config_path)
    except OSError as e:
        logger.warning("[MCP桥] 临时配置删除失败 %s: %s", config_path, e)
