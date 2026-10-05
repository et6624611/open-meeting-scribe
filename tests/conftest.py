"""
tests/conftest.py — pytest 配置

确保项目根目录在 sys.path 中，使 `from app.xxx import ...` 可用。
"""

import sys
from pathlib import Path

import pytest

# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session", autouse=True)
def _isolate_decision_statuses(tmp_path_factory):
    """会话级隔离决策状态字典文件（DC-R2-c）：避免用例首次读取时写脏仓库 data/。"""
    import core.decision_status as ds

    orig_dir, orig_file = ds.DATA_DIR, ds.STATUSES_FILE
    tmp_dir = tmp_path_factory.mktemp("decision-statuses")
    ds.DATA_DIR = tmp_dir
    ds.STATUSES_FILE = tmp_dir / "decision_statuses.json"
    yield
    ds.DATA_DIR, ds.STATUSES_FILE = orig_dir, orig_file


@pytest.fixture(scope="session", autouse=True)
def _isolate_tasks_dir(tmp_path_factory):
    """会话级隔离任务持久化目录：避免用例（retry-summary / retranscribe / 洞察 / 文本修正等）
    经 save_task_to_disk 把测试任务 JSON 写进真实 data/tasks/，在会议库遗留 test.wav / 会议记录 垃圾。

    所有写入 data/tasks 的模块级目录常量统一重定向到 pytest 临时目录，会话结束后还原。
    """
    tmp_dir = tmp_path_factory.mktemp("tasks")

    # (模块, 属性名) 清单：凡在调用时读取本模块全局目录常量进行落盘的，都需重定向
    targets = []
    try:
        import app.task_store as task_store
        targets.append((task_store, "TASKS_DIR"))
    except Exception:
        pass
    try:
        import app.store as store
        targets.append((store, "TASKS_DIR"))
    except Exception:
        pass
    try:
        import app.routers.insights as insights
        targets.append((insights, "TASKS_DIR"))
    except Exception:
        pass
    try:
        import core.text_correction as text_correction
        targets.append((text_correction, "TASKS_DIR"))
    except Exception:
        pass
    try:
        import core.insight_board as insight_board
        targets.append((insight_board, "BOARD_TASKS_DIR"))
    except Exception:
        pass
    try:
        # AI 写回快照 sidecar（<task_id>.rewrites.jsonl）与任务 JSON 同目录，一并隔离
        import core.rewrite_snapshots as rewrite_snapshots
        targets.append((rewrite_snapshots, "SNAPSHOT_DIR"))
    except Exception:
        pass

    originals = [(mod, attr, getattr(mod, attr)) for mod, attr in targets]
    for mod, attr in targets:
        setattr(mod, attr, tmp_dir)
    yield
    for mod, attr, orig in originals:
        setattr(mod, attr, orig)
