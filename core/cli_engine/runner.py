"""
core/cli_engine/runner.py — CLI 无头进程编排：启动 → 逐行读流 → 规范事件 → 真取消
Orchestrate the headless CLI subprocess: launch, stream NDJSON, emit canonical events, cancel.

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

对应方案 / See: docs/PROPOSAL-QODER-CLI-ENGINE.md §3.2（生命周期）、§3.9-5（真取消）；
docs/SPIKE-QODER-CLI-ENGINE.md §4（路径必须 resolve、prompt 用 -- 分隔、成败读 result 事件）。

设计取舍：
  - D2 维持"每轮一进程"（SPIKE 实测会话恢复无额外惩罚）
  - cancel(stream_id) kill 进程组，兑现 §3.9-5"终止任务"新语义（前端 fetch 断开不足以杀子进程）
  - 所有传入路径 .resolve()（M3/§3.3 相对路径按 -w 解析的陷阱）
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from core.cli_engine import event_bridge as bridge
from core.cli_engine.manifest import compile_auth_argv, load_manifest

logger = logging.getLogger(__name__)

# 活跃进程注册表：stream_id → Process（真取消用）；进程内单例
_ACTIVE: dict[str, asyncio.subprocess.Process] = {}

# 打字机切片节奏（M1）：每片字符数与片间延迟（秒）
_TYPEWRITER_SIZE = 18
_TYPEWRITER_DELAY = 0.02


class CliAgentError(RuntimeError):
    """引擎不可用/启动失败，供上层回退内置链路。 / Engine unavailable; caller should fall back."""


async def run_cli_agent(
    *,
    stream_id: str,
    engine_id: str,
    cli_path: str,
    workspace: str,
    add_dirs: list[str],
    brief: str,
    auth_tier: str,
    model: str | None = None,
    session_id: str | None = None,
    resume: bool = False,
    mcp_config: str | None = None,
    allowed_tools: list[str] | None = None,
    first_event_timeout: int = 60,
    total_timeout: int = 300,
):
    """
    异步生成器：yield 规范 SSE 事件字典。 / Async generator yielding canonical SSE event dicts.

    由 chat_stream 的 event_generator 直接转发；异常以 error 事件产出而非抛出（保持 SSE 流不破）。
    """
    manifest = load_manifest(engine_id)
    argv = manifest.get("argv", {})

    cmd: list[str] = [cli_path, *argv.get("base", ["-p", "--output-format", "stream-json"])]
    if model:
        cmd += [argv.get("model_flag", "-m"), model]
    cmd += [argv.get("workspace_flag", "-w"), str(_resolve(workspace))]
    for d in add_dirs or []:
        cmd += [argv.get("add_dir_flag", "--add-dir"), str(_resolve(d))]
    if resume and session_id:
        cmd += [argv.get("session_resume_flag", "-r"), session_id]
    elif session_id:
        cmd += [argv.get("session_new_flag", "--session-id"), session_id]
    else:
        cmd += [argv.get("no_persist_flag", "--no-session-persistence")]
    cmd += compile_auth_argv(manifest, auth_tier)
    if mcp_config and manifest.get("capabilities", {}).get("mcp_injection"):
        cmd += [argv.get("strict_mcp_flag", "--strict-mcp-config"),
                argv.get("mcp_config_flag", "--mcp-config"), str(_resolve(mcp_config))]
    # 预授权本轮 MCP 工具（SPIKE §2：--allowed-tools 对 mcp__ 工具生效，消除运行时询问）
    for tool in allowed_tools or []:
        cmd += [argv.get("allowed_tools_flag", "--allowed-tools"), tool]
    # 轻量任务说明追加到系统提示词（重内容已在工作区）
    cmd += ["--append-system-prompt", brief]
    # prompt 置于末尾并以 -- 分隔（§4：中文 prompt 不加 -- 偶发未传递）
    cmd += [argv.get("prompt_separator", "--"), brief]

    logger.info("[CLI引擎] 启动 stream=%s engine=%s tier=%s resume=%s",
                stream_id, engine_id, auth_tier, resume)

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            stdin=asyncio.subprocess.DEVNULL,
            start_new_session=True,  # 独立进程组，cancel 可整组 kill（§3.9-5）
        )
    except (FileNotFoundError, PermissionError, OSError) as e:
        raise CliAgentError(f"无法启动 CLI 引擎：{e}") from e

    _ACTIVE[stream_id] = proc
    got_result = False
    try:
        while True:
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=first_event_timeout)
            except asyncio.TimeoutError:
                yield {bridge.EV_TYPE_KEY: bridge.EV_ERROR,
                       "content": "引擎首帧超时，可能额度不足或环境异常", "engine_error": "timeout"}
                break
            if not line:
                break  # EOF
            raw = line.decode("utf-8", "replace")
            for evt in bridge.parse_line(raw, manifest):
                if evt[bridge.EV_TYPE_KEY] == bridge.EV_TOKEN:
                    # M1 打字机合成：整段 text 切片逐帧推
                    for piece in bridge.chunk_text(evt.get("content", ""), _TYPEWRITER_SIZE):
                        yield {bridge.EV_TYPE_KEY: bridge.EV_TOKEN, "content": piece}
                        await asyncio.sleep(_TYPEWRITER_DELAY)
                else:
                    if evt[bridge.EV_TYPE_KEY] in (bridge.EV_DONE, bridge.EV_ERROR):
                        got_result = True
                    yield evt
            if got_result:
                break
    finally:
        _ACTIVE.pop(stream_id, None)
        await _reap(proc)

    if not got_result:
        # 未见 result 事件即 EOF：进程被取消/异常终止，补一个 done 保持协议完整
        yield {bridge.EV_TYPE_KEY: bridge.EV_DONE, "metadata": {"model": model or engine_id},
               "cancelled": proc.returncode not in (0, None)}


def _resolve(path: str):
    from pathlib import Path
    return Path(path).resolve()


async def _reap(proc) -> None:
    """确保子进程与进程组回收，避免孤儿（§3.9-5）。 / Ensure the child process group is reaped."""
    if proc.returncode is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass


def cancel_stream(stream_id: str) -> bool:
    """
    真取消：kill 指定 stream 的进程组。 / Hard cancel: kill the process group for a stream.

    返回是否命中活跃进程。由 /api/chat/cancel 端点调用（fetch abort 不足以终止任务，§3.9-5）。
    """
    proc = _ACTIVE.get(stream_id)
    if not proc or proc.returncode is not None:
        return False
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except ProcessLookupError:
            return False
    logger.info("[CLI引擎] 已取消 stream=%s", stream_id)
    return True


def active_streams() -> list[str]:
    """调试/监控用：当前活跃 CLI 进程 stream_id 列表。"""
    return list(_ACTIVE.keys())
