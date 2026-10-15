"""
core/cli_engine/runner.py — CLI 无头进程编排：启动 → 逐行读流 → 规范事件 → 真取消
Orchestrate the headless CLI subprocess: launch, stream NDJSON, emit canonical events, cancel.

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

对应方案 / See: Qoder CLI 引擎方案 §3.2（生命周期）、§3.9-5（真取消）；
CLI 引擎 Spike 报告 §4（路径必须 resolve、prompt 用 -- 分隔、成败读 result 事件）。

设计取舍：
  - D2 维持"每轮一进程"（SPIKE 实测会话恢复无额外惩罚）
  - cancel(stream_id) kill 进程组，兑现 §3.9-5"终止任务"新语义（前端 fetch 断开不足以杀子进程）
  - 所有传入路径 .resolve()（M3/§3.3 相对路径按 -w 解析的陷阱）
  - 多 CLI 适配：绝不假设所有 CLI 同参数——capabilities.workspace_flag 为空时改用进程
    cwd 定位工作区；add_dir/会话恢复/系统提示词注入/无持久化标志均按 manifest 声明的
    capability 与 argv 标志分支，缺失即跳过（而非硬塞未知参数）
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from contextlib import contextmanager

from anyio import CancelScope

from core.cli_engine import event_bridge as bridge
from core.cli_engine.manifest import compile_auth_argv, load_manifest

logger = logging.getLogger(__name__)

# 活跃进程注册表：stream_id → Process（真取消用）；进程内单例
_ACTIVE: dict[str, asyncio.subprocess.Process] = {}
# 同一会话轮次可顺序执行主轮和补写；取消标记覆盖两进程之间的空档。
_CANCELLED: dict[str, bool] = {}


@contextmanager
def stream_scope(stream_id: str):
    """把主轮与补写绑定到同一个可取消生命周期。"""
    owner = stream_id not in _CANCELLED
    _CANCELLED.setdefault(stream_id, False)
    try:
        yield
    finally:
        if owner:
            _CANCELLED.pop(stream_id, None)


class _UserCancelledError(Exception):
    """用户主动停止，不当作引擎故障。"""


# 打字机切片节奏（M1）：每片字符数与片间延迟（秒）
_TYPEWRITER_SIZE = 18
_TYPEWRITER_DELAY = 0.02


class CliAgentError(RuntimeError):
    """引擎不可用/启动失败，供上层回退内置链路。 / Engine unavailable; caller should fall back.

    hint_key 为前端 ai-panel 命名空间的 i18n 键，detail 携带原始异常文案作插值参数。
    """

    def __init__(self, message: str, hint_key: str = "cli_engine_start_failed", detail: str = ""):
        super().__init__(message)
        self.hint_key = hint_key
        self.detail = detail


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
    first_event_timeout: float | None = None,
    idle_timeout: float | None = None,
    total_timeout: float | None = None,
    on_write_success=None,
):
    """
    异步生成器：yield 规范 SSE 事件字典。 / Async generator yielding canonical SSE event dicts.

    由 chat_stream 的 event_generator 直接转发；异常以 error 事件产出而非抛出（保持 SSE 流不破）。

    on_write_success：可选回调，参数为工具全名。当 tool_call 名字命中写工具（含 MCP 前缀
    mcp__<server>__<tool>）且其 tool_result 成功时触发（完成护栏 §5.4 的 rewritten 事实源）。
    """
    manifest = load_manifest(engine_id)
    argv = manifest.get("argv", {})
    caps = manifest.get("capabilities", {}) or {}
    timeouts = manifest.get("timeout") or {}
    first_event_timeout = float(first_event_timeout if first_event_timeout is not None else timeouts.get("first_event_seconds", 60))
    # CLI 常在整段生成完后才输出，后续等待不能沿用启动首帧预算。
    idle_timeout = float(idle_timeout if idle_timeout is not None else timeouts.get("idle_seconds", 180))
    total_timeout = float(total_timeout if total_timeout is not None else timeouts.get("total_seconds", 300))
    if min(first_event_timeout, idle_timeout, total_timeout) <= 0:
        raise ValueError("CLI 超时配置必须为正数")
    if _CANCELLED.get(stream_id):
        yield {"type": "done", "status": "cancelled", "cancelled": True}
        return

    cmd: list[str] = [cli_path, *argv.get("base", ["-p", "--output-format", "stream-json"])]
    model_flag = argv.get("model_flag", "-m")
    if model and model_flag:
        cmd += [model_flag, model]
    # 工作区定位：有标志则传参，无标志（如 Claude Code）则用进程 cwd 兜底
    proc_cwd: str | None = None
    workspace_flag = argv.get("workspace_flag")
    if workspace_flag:
        cmd += [workspace_flag, str(_resolve(workspace))]
    else:
        proc_cwd = str(_resolve(workspace))
    add_dir_flag = argv.get("add_dir_flag", "--add-dir")
    if caps.get("add_dir", True) and add_dir_flag:
        for d in add_dirs or []:
            cmd += [add_dir_flag, str(_resolve(d))]
    # 会话生命周期按 capability 分支；对应标志缺失（null）时静默跳过（不硬塞未知参数）
    resume_flag = argv.get("session_resume_flag")
    new_flag = argv.get("session_new_flag")
    if resume and session_id and caps.get("session_resume", True) and resume_flag:
        cmd += [resume_flag, session_id]
    elif session_id and new_flag:
        cmd += [new_flag, session_id]
    elif argv.get("no_persist_flag"):
        cmd += [argv["no_persist_flag"]]
    cmd += compile_auth_argv(manifest, auth_tier)
    if mcp_config and caps.get("mcp_injection"):
        strict_flag = argv.get("strict_mcp_flag", "--strict-mcp-config")
        if strict_flag:
            cmd.append(strict_flag)
        cmd += [argv.get("mcp_config_flag", "--mcp-config"), str(_resolve(mcp_config))]
    # 预授权本轮 MCP 工具（SPIKE §2：--allowed-tools 对 mcp__ 工具生效，消除运行时询问）
    allowed_flag = argv.get("allowed_tools_flag", "--allowed-tools")
    if allowed_flag:
        for tool in allowed_tools or []:
            cmd += [allowed_flag, tool]
    # 轻量任务说明追加到系统提示词（重内容已在工作区）；引擎不支持则跳过
    if caps.get("system_prompt_append", True):
        sp_flag = argv.get("system_prompt_flag", "--append-system-prompt")
        if sp_flag:
            cmd += [sp_flag, brief]
    # prompt 置于末尾；分隔符（如 "--"）由 manifest 声明，Claude 等直接尾传位置参数
    separator = argv.get("prompt_separator")
    if separator:
        cmd += [separator]
    cmd += [brief]

    logger.info("[CLI引擎] 启动 stream=%s engine=%s tier=%s resume=%s",
                stream_id, engine_id, auth_tier, resume)

    proc = None
    try:
        # limit=1MB：CLI stream-json 的单行 JSON 可能很大（如带长 text block 或 HTML），
        # asyncio 默认 64KB 会抛 LimitOverrunError，导致 readline() 直接崩溃整条 SSE 流。
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            stdin=asyncio.subprocess.DEVNULL,
            cwd=proc_cwd,
            start_new_session=True,  # 独立进程组，cancel 可整组 kill（§3.9-5）
            limit=1024 * 1024,
        )
    except (FileNotFoundError, PermissionError, OSError) as e:
        raise CliAgentError(f"无法启动 CLI 引擎：{e}", hint_key="cli_engine_start_failed", detail=str(e)) from e

    _ACTIVE[stream_id] = proc
    owns_cancel = stream_id not in _CANCELLED
    _CANCELLED.setdefault(stream_id, False)
    terminal: dict | None = None
    started = time.monotonic()
    total_deadline = started + total_timeout
    phase_deadline = started + first_event_timeout
    seen_event = False
    last_event = "none"
    timeout_kind = "first_event"
    # 完成护栏配对（§5.4）：tool_call 先行记录 id→name，tool_result 只带 tool_use_id，
    # 按 id 回溯名字后才能判定"写工具成功落盘"（读写双语义工具的读调用不在写工具集，自然排除）
    # persists=False 的是"名义 write、实际不落盘"的提案信号（propose_summary / propose_notes），
    # 必须从触发集剔除，否则提案轮被误标 rewritten=true；集合由 catalog 派生，不再硬写工具名
    from core.agent_tools.catalog import TOOL_CATALOG as _CATALOG
    write_names = {t["name"] for t in _CATALOG
                   if t.get("kind") == "write" and t.get("persists", True)}
    # 读写双语义工具：空参/缺关键字段时是读语义，不能触发 rewritten
    bidirectional_tools = {t["name"] for t in _CATALOG
                           if t.get("kind") == "write" and t.get("bidirectional")}
    call_info: dict[str, dict] = {}  # id → {name, args}
    try:
        while True:
            if _CANCELLED.get(stream_id):
                raise _UserCancelledError
            timeout_kind = "total" if total_deadline <= phase_deadline else "idle" if seen_event else "first_event"
            remaining = min(total_deadline, phase_deadline) - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            if _CANCELLED.get(stream_id):
                raise _UserCancelledError
            if not line:
                # 退出码为 0 也不能代替 CLI 的成功 result。
                terminal = {"type": "error", "status": "incomplete", "content": "引擎连接已结束，但未收到完成结果；已写入的内容不会自动撤销。",
                            "hint_key": "cli_engine_incomplete", "engine_error": "missing_result"}
                break
            raw = line.decode("utf-8", "replace")
            events = bridge.parse_line(raw, manifest)
            if events:
                seen_event = True
                phase_deadline = time.monotonic() + idle_timeout
            for evt in events:
                last_event = evt[bridge.EV_TYPE_KEY]
                if last_event == bridge.EV_TOKEN:
                    # 合成打字机也受总时限与取消控制，不因超长正文无限延迟终态。
                    timeout_kind = "total"
                    for piece in bridge.chunk_text(evt.get("content", ""), _TYPEWRITER_SIZE):
                        if _CANCELLED.get(stream_id):
                            raise _UserCancelledError
                        remaining = total_deadline - time.monotonic()
                        if remaining <= 0:
                            raise asyncio.TimeoutError
                        yield {bridge.EV_TYPE_KEY: bridge.EV_TOKEN, "content": piece}
                        await asyncio.sleep(min(_TYPEWRITER_DELAY, remaining))
                    phase_deadline = time.monotonic() + idle_timeout
                else:
                    if on_write_success is not None:
                        if evt[bridge.EV_TYPE_KEY] == bridge.EV_TOOL_CALL and evt.get("id"):
                            call_info[evt["id"]] = {
                                "name": str(evt.get("name") or ""),
                                "args": evt.get("args") or {},
                            }
                        elif evt[bridge.EV_TYPE_KEY] == bridge.EV_TOOL_RESULT and evt.get("success"):
                            call_id = evt.get("tool_use_id") or ""
                            info = call_info.get(call_id, {})
                            bare = str(evt.get("name") or info.get("name", ""))
                            short = bare.rsplit("__", 1)[-1]
                            if short in write_names:
                                # 读写双语义工具：只有带了"写"的关键字段才算真落盘
                                if short in bidirectional_tools:
                                    tool_spec = next((t for t in _CATALOG if t["name"] == short), None)
                                    write_arg = (tool_spec or {}).get("write_arg", "html")
                                    if write_arg not in (info.get("args") or {}):
                                        pass  # 读语义，不触发
                                    else:
                                        on_write_success(bare)
                                else:
                                    on_write_success(bare)
                    if evt[bridge.EV_TYPE_KEY] in (bridge.EV_DONE, bridge.EV_ERROR):
                        terminal = evt
                        terminal.setdefault("status", "completed" if last_event == bridge.EV_DONE else "error")
                        break
                    yield evt
            if terminal is not None:
                break
    except _UserCancelledError:
        terminal = {"type": "done", "status": "cancelled", "cancelled": True}
    except asyncio.TimeoutError:
        label = {"first_event": "等待首次输出超时", "idle": "等待后续输出超时", "total": "执行总时限已到"}[timeout_kind]
        terminal = {"type": "error", "status": "error", "content": f"引擎{label}；已写入的内容不会自动撤销。",
                    "hint_key": f"cli_engine_{timeout_kind}_timeout", "engine_error": f"{timeout_kind}_timeout"}
    except Exception as exc:
        terminal = {"type": "error", "status": "error", "content": "引擎输出读取失败",
                    "hint_key": "cli_engine_stream_error", "engine_error": "stream_error"}
        # 不记录原始工具参数/输出，避免日志泄漏业务数据。
        logger.warning("[CLI引擎] 读流失败 stream=%s exception=%s", stream_id, type(exc).__name__)
    finally:
        try:
            # ASGI 断连会持续取消 await；屏蔽清理阶段的取消，先确认子进程退出再回收桥。
            with CancelScope(shield=True):
                await _reap(proc)
        finally:
            _ACTIVE.pop(stream_id, None)
            if _CANCELLED.get(stream_id):
                terminal = {"type": "done", "status": "cancelled", "cancelled": True}
            if owns_cancel:
                _CANCELLED.pop(stream_id, None)

    if terminal is not None:
        terminal.setdefault("hint_params", {"engine": manifest.get("display_name", "CLI")})
        logger.info("[CLI引擎] 结束 stream=%s status=%s reason=%s last_event=%s elapsed=%.3f returncode=%s",
                    stream_id, terminal.get("status"), terminal.get("engine_error", ""), last_event,
                    time.monotonic() - started, proc.returncode)
        # 回收后只发送一个权威终态；错误/EOF 绝不再补成功 done。
        yield terminal


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
    if stream_id not in _CANCELLED:
        return False
    _CANCELLED[stream_id] = True
    proc = _ACTIVE.get(stream_id)
    if not proc or proc.returncode is not None:
        return True
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
