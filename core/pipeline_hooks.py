"""
core/pipeline_hooks.py — 管线执行钩子（反转 core → pipeline_runner 反向依赖）

T-25：`core/task_store.py`（中断恢复）、`core/silence_detection.py`（静默自动关停）、
`core/chat_actions.py`（重新识别/重新生成）原本直接 import `core.pipeline_runner`，
使存储层与检测层反向依赖执行编排层。改为：三者只依赖本钩子模块，
真实 runner 由启动入口（app/server.py）显式注入。

未注册时调用方给出明确降级行为与错误日志，不静默失败。

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-06
"""

import logging
from typing import Callable

logger = logging.getLogger(__name__)

_run_pipeline_task: Callable | None = None
_run_stage2_task: Callable | None = None


class PipelineHookNotRegisteredError(RuntimeError):
    """管线钩子未注册——通常意味着进程不是从 app.server 启动的。"""


def register(*, run_pipeline_task: Callable, run_stage2_task: Callable) -> None:
    """由启动入口注入真实实现（幂等，重复注册以最后一次为准）。"""
    global _run_pipeline_task, _run_stage2_task
    _run_pipeline_task = run_pipeline_task
    _run_stage2_task = run_stage2_task
    logger.debug("[pipeline-hooks] 已注册管线执行钩子")


def is_registered() -> bool:
    return _run_pipeline_task is not None and _run_stage2_task is not None


def run_pipeline_task(*args, **kwargs):
    """转调 Stage1 全流程；未注册时抛 PipelineHookNotRegisteredError。"""
    if _run_pipeline_task is None:
        raise PipelineHookNotRegisteredError(
            "管线钩子未注册：请在启动入口调用 core.pipeline_hooks.register(...)"
        )
    return _run_pipeline_task(*args, **kwargs)


def run_stage2_task(*args, **kwargs):
    """转调 Stage2（纪要生成）；未注册时抛 PipelineHookNotRegisteredError。"""
    if _run_stage2_task is None:
        raise PipelineHookNotRegisteredError(
            "管线钩子未注册：请在启动入口调用 core.pipeline_hooks.register(...)"
        )
    return _run_stage2_task(*args, **kwargs)
