"""
core/cli_engine — 本地 CLI 工程化会话引擎适配层 / Local CLI agent-engine adapter layer

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

职责 / Responsibilities:
  为 AI 对话面板提供"智能体模式"（可选外部 Agent 引擎），当前唯一实现为 Qoder CLI。
  与 core/routing.py 的 access_mode（LLM/ASR 传输通道）正交（方案 D1）。

模块划分 / Modules:
  - manifest.py       声明式引擎清单 + 工具标签解析 + 授权档位编译
  - probe.py          CLI 可用性探针（which/version/login）
  - context_export.py 会议上下文序列化到工作区（物理隔离于 data/）
  - event_bridge.py   CLI stream-json → 软件规范 SSE 事件翻译
  - runner.py         无头进程编排 + 打字机合成 + 真取消注册表

对应方案 / See: Qoder CLI 引擎方案 §3.11 及 CLI 引擎 Spike 报告。
"""

from __future__ import annotations

from core.cli_engine.context_export import (
    cleanup_workspace,
    export_context,
    sweep_expired_workspaces,
    workspace_dir,
)
from core.cli_engine.event_bridge import parse_line
from core.cli_engine.intent import classify_engine_intent
from core.cli_engine.manifest import (
    available_engines,
    compile_auth_argv,
    load_manifest,
    resolve_tool_label,
)
from core.cli_engine.mcp_bridge import build_bridge_config, manifest_has_mcp, teardown_bridge
from core.cli_engine.probe import list_models, probe_engine
from core.cli_engine.runner import CliAgentError, cancel_stream, run_cli_agent

__all__ = [
    "available_engines",
    "load_manifest",
    "resolve_tool_label",
    "compile_auth_argv",
    "probe_engine",
    "list_models",
    "export_context",
    "workspace_dir",
    "cleanup_workspace",
    "sweep_expired_workspaces",
    "classify_engine_intent",
    "parse_line",
    "run_cli_agent",
    "cancel_stream",
    "CliAgentError",
    "build_bridge_config",
    "teardown_bridge",
    "manifest_has_mcp",
]
