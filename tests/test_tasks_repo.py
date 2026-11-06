"""
tests/test_tasks_repo.py — T-21 守护：tasks 映射写入口唯一化

覆盖：
1. 结构守护：core/ 与 app/ 中不得出现 `tasks[...] =` / `tasks.pop()` 等映射级写入
2. 行为：set_task / remove_task / get_task 与 core.task_store.tasks 同源
3. 并发：多线程增删不抛错、不破坏映射
"""

import ast
import re
import threading
from pathlib import Path

from core import task_store
from core.tasks_repo import get_task, remove_task, set_task

ROOT = Path(__file__).resolve().parents[1]
REPO_FILE = ROOT / "core" / "tasks_repo.py"
FORBIDDEN_METHODS = {"pop", "clear", "update", "setdefault", "__setitem__"}


def _is_tasks_ref(node: ast.AST) -> bool:
    """判断表达式是否直接指向 tasks 映射（tasks / xxx.tasks）"""
    if isinstance(node, ast.Name):
        return node.id == "tasks"
    return isinstance(node, ast.Attribute) and node.attr == "tasks"


def _scan_offenders() -> list[str]:
    offenders = []
    for pkg in ("core", "app"):
        for path in (ROOT / pkg).rglob("*.py"):
            if "__pycache__" in path.parts or path == REPO_FILE:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            rel = path.relative_to(ROOT)
            for node in ast.walk(tree):
                targets = []
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, ast.AugAssign):
                    targets = [node.target]
                for target in targets:
                    if isinstance(target, ast.Subscript) and _is_tasks_ref(target.value):
                        offenders.append(f"{rel}:{target.lineno} 直接赋值 tasks[...]")
                if isinstance(node, ast.Delete):
                    for target in node.targets:
                        if isinstance(target, ast.Subscript) and _is_tasks_ref(target.value):
                            offenders.append(f"{rel}:{target.lineno} del tasks[...]")
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in FORBIDDEN_METHODS
                    and _is_tasks_ref(node.func.value)
                ):
                    offenders.append(f"{rel}:{node.lineno} 调用 tasks.{node.func.attr}()")
    return offenders


def test_mapping_writes_only_in_repo():
    """映射级增删只允许出现在 core/tasks_repo.py"""
    offenders = _scan_offenders()
    assert not offenders, "绕过 tasks_repo 的映射写入：\n" + "\n".join(offenders)


def test_set_get_remove_share_task_store_mapping():
    """repo 读写与 core.task_store.tasks 同一对象"""
    original = dict(task_store.tasks)
    try:
        task_store.tasks.clear()
        set_task("t-repo", {"task_id": "t-repo", "status": "pending"})
        assert task_store.tasks["t-repo"]["status"] == "pending"
        assert get_task("t-repo") is task_store.tasks["t-repo"]

        removed = remove_task("t-repo")
        assert removed is not None and removed["task_id"] == "t-repo"
        assert get_task("t-repo") is None
        assert remove_task("t-repo") is None
    finally:
        task_store.tasks.clear()
        task_store.tasks.update(original)


def test_concurrent_set_remove_keeps_mapping_consistent():
    """录音线程/请求线程并发增删同一映射不抛错、不残留半写记录"""
    errors: list[Exception] = []

    def worker(worker_id: int) -> None:
        try:
            for i in range(200):
                task_id = f"t-{worker_id}-{i}"
                set_task(task_id, {"task_id": task_id, "status": "recording"})
                set_task(task_id, {"task_id": task_id, "status": "completed"})
                assert remove_task(task_id) is not None
        except Exception as exc:  # noqa: BLE001 — 收集线程内异常
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert not [tid for tid in task_store.tasks if re.fullmatch(r"t-\d+-\d+", tid)]
