"""
core/tasks_repo.py — 任务字典写入口 / Task mapping write gateway

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-06
版本 / Version: 1.0.0

T-21：`tasks` 是进程内唯一任务集合，录音线程、后台管线、请求线程三方共用。
此前有 17 处直接 `tasks[...] = ...` / `tasks.pop(...)`，字段契约与并发行为无处集中约束。
本模块是**唯一**允许对映射本身做增删的入口；字段级读写（`task["status"] = ...`）不受限。

设计要点 / Design notes:
- 运行时解析 `core.task_store.tasks`，不缓存引用：测试 monkeypatch 替换字典后仍生效。
- 不持有锁：GIL 下 dict 的 set/pop 是原子操作；跨线程一致性问题在字段级，由调用方语义保证。
"""

from __future__ import annotations


def _tasks() -> dict[str, dict]:
    """运行时取任务字典（不缓存引用，兼容测试替换） / Resolve mapping at call time (no cached ref)."""
    from core import task_store

    return task_store.tasks


def set_task(task_id: str, task: dict) -> dict:
    """写入/覆盖一个任务记录 / Insert or replace a task record."""
    _tasks()[task_id] = task
    return task


def remove_task(task_id: str) -> dict | None:
    """删除并返回任务记录；不存在返回 None / Remove and return a task; None if absent."""
    return _tasks().pop(task_id, None)


def get_task(task_id: str) -> dict | None:
    """读取任务记录；不存在返回 None / Get a task; None if absent."""
    return _tasks().get(task_id)
