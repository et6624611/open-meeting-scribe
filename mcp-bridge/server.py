#!/usr/bin/env python3
"""
mcp-bridge/server.py — OpenMeetingScribe 反向工具 MCP 桥（stdio, 零第三方依赖）
Reverse-tool MCP bridge for OpenMeetingScribe (stdio transport, no third-party deps).

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

作用 / Role:
  被 Qoder CLI 以 stdio MCP Server 拉起（--mcp-config 注入），把 OMS 的受控读写 API
  暴露为 MCP 工具；工具调用经 HTTP 回连本机 OMS 服务（/api/agent-tools/invoke），
  携带本轮短时 bearer 令牌。这样 CLI 对会议数据的写操作走软件既有的落盘/审计/状态同步，
  而非自由写文件（方案 §3.4 / R5）。

协议 / Protocol: MCP over stdio = JSON-RPC 2.0，换行分隔（newline-delimited）。
  实现 initialize / tools/list / tools/call，其余按无方法错误应答。

环境变量 / Env（由 mcp-config 注入，见 core/cli_engine 的桥接生成逻辑）:
  OMS_MCP_TOKEN      本轮短时 bearer（必填）
  OMS_BASE_URL       本机服务基址（默认 http://127.0.0.1:8000）

设计约束 / Constraints:
  - 只连 127.0.0.1 回环；令牌单轮有效，进程退出即失效
  - 绝不读取 settings.json / 任何凭据；只转发白名单工具
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# 允许以脚本方式从仓库根运行：把仓库根加入 sys.path 以 import core.agent_tools.catalog
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "oms-tools"
SERVER_VERSION = "1.0.0"

_TOKEN = os.environ.get("OMS_MCP_TOKEN", "")
_BASE_URL = (os.environ.get("OMS_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")


def _load_tool_specs() -> list[dict]:
    """从单一来源 catalog 读取工具声明；失败则空列表（桥仍可应答 initialize）。"""
    try:
        from core.agent_tools.catalog import mcp_tool_specs
        return mcp_tool_specs()
    except Exception:  # noqa: BLE001 - 桥不能因导入问题崩溃
        return []


def _call_invoke(name: str, arguments: dict) -> tuple[bool, str]:
    """POST /api/agent-tools/invoke，返回 (ok, text)。"""
    body = json.dumps({"name": name, "arguments": arguments}).encode("utf-8")
    req = urllib.request.Request(
        f"{_BASE_URL}/api/agent-tools/invoke",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_TOKEN}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # 仅本机回环
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return True, json.dumps(data.get("result", data), ensure_ascii=False)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail)
            detail = detail.get("detail", detail)
        except Exception:  # noqa: BLE001
            pass
        return False, json.dumps({"error": f"HTTP {e.code}", "detail": detail}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        return False, json.dumps({"error": "bridge_request_failed", "detail": str(e)}, ensure_ascii=False)


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(req_id, result: dict) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _error(req_id, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def handle(req: dict) -> None:
    method = req.get("method", "")
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        _result(rid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    elif method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return  # 通知无需应答
    elif method == "ping":
        _result(rid, {})
    elif method == "tools/list":
        _result(rid, {"tools": _load_tool_specs()})
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments") or {}
        if not _TOKEN:
            _result(rid, {"content": [{"type": "text",
                     "text": json.dumps({"error": "missing_token"}, ensure_ascii=False)}],
                     "isError": True})
            return
        ok, text = _call_invoke(name, args)
        _result(rid, {"content": [{"type": "text", "text": text}], "isError": not ok})
    elif rid is not None:
        _error(rid, -32601, f"method not found: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            handle(req)
        except Exception as e:  # noqa: BLE001 - 单请求异常不应终止服务
            sys.stderr.write(f"[oms-tools] handler error: {e}\n")


if __name__ == "__main__":
    main()
