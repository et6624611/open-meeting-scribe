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
