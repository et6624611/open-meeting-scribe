"""
app/task_store.py — 兼容 re-export 层 / Compatibility re-export layer

实际实现已下沉至 core/task_store.py；本文件保留以维持既有 import 路径。
/ Implementation sunk to core/task_store.py; this file remains for backward-compat import paths.

使用模块 __getattr__ 动态代理，保证运行时 setattr(core.task_store, ...) 能在本层可见。
"""

import core.task_store as _core


def __getattr__(name):
    """动态代理到 core.task_store。"""
    if name.startswith("_"):
        raise AttributeError(name)
    try:
        return getattr(_core, name)
    except AttributeError:
        raise AttributeError(f"module 'app.task_store' has no attribute {name!r}")


__all__ = [
    "OUTPUT_DIR",
    "RECORDINGS_DIR",
    "TASKS_DIR",
    "UPLOAD_DIR",
    "cleanup_orphaned_intermediate_files",
    "infer_task_source",
    "load_tasks_from_disk",
    "recover_interrupted_tasks",
    "save_task_to_disk",
    "tasks",
]
