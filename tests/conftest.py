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
def _isolate_settings_file(tmp_path_factory):
    """会话级隔离 settings.json：避免跨测试的残留配置污染（如 model_dir 自定义值）。
    T-13 下沉后，settings.json 真相源在 core.settings_store，app.settings_store 是 re-export 层。
    两层都需 patch SETTINGS_FILE，确保任何 import 路径都读到会话级临时文件。
    注：function 级测试若需要独立 SETTINGS_FILE，需显式 monkeypatch（两层都 patch）。
    """
    tmp_file = tmp_path_factory.mktemp("settings") / "settings.json"
    targets = []
    try:
        import core.settings_store as _core_ss
        targets.append((_core_ss, "SETTINGS_FILE"))
    except Exception:
        pass
    try:
        import app.settings_store as ss
        targets.append((ss, "SETTINGS_FILE"))
    except Exception:
        pass
    try:
        import app.store as store
        targets.append((store, "SETTINGS_FILE"))
    except Exception:
        pass

    originals = []
    for mod, attr in targets:
        if hasattr(mod, attr):
            originals.append((mod, attr, getattr(mod, attr)))
            setattr(mod, attr, tmp_file)
    yield
    for mod, attr, orig in originals:
        setattr(mod, attr, orig)


@pytest.fixture(scope="session", autouse=True)
def _isolate_tasks_dir(tmp_path_factory):
    """会话级隔离任务持久化目录：避免用例（retry-summary / retranscribe / 洞察 / 文本修正等）
    经 save_task_to_disk 把测试任务 JSON 写进真实 data/tasks/，在会议库遗留 test.wav / 会议记录 垃圾。

    所有写入 data/tasks 的模块级目录常量统一重定向到 pytest 临时目录，会话结束后还原。
    T-13 下沉后，core.task_store 是真相源；app.task_store 等是 re-export 层。
    两个层都需 patch，避免只改到 re-export 层而核心函数仍读原值。
    另：`from core.task_store import TASKS_DIR` 会在模块加载时静态绑定，
    patch 完 core.task_store 后还需 patch 所有已 import 进来的消费者模块。
    """
    tmp_dir = tmp_path_factory.mktemp("tasks")

    # (模块, 属性名) 清单：凡在调用时读取本模块全局目录常量进行落盘的，都需重定向
    targets = []
    try:
        import core.task_store as task_store
        targets.append((task_store, "TASKS_DIR"))
    except Exception:
        pass
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
    # T-13 新增：静态绑定 TASKS_DIR 的消费者模块
    # `from core.task_store import TASKS_DIR` 在模块加载时就绑定了引用，
    # 后续 patch 核心模块不会同步到这些模块
    try:
        import core.chat_edits as chat_edits
        targets.append((chat_edits, "TASKS_DIR"))
    except Exception:
        pass

    originals = [(mod, attr, getattr(mod, attr)) for mod, attr in targets]
    for mod, attr in targets:
        setattr(mod, attr, tmp_dir)
    yield
    for mod, attr, orig in originals:
        setattr(mod, attr, orig)


@pytest.fixture(scope="session", autouse=True)
def _isolate_users_file(tmp_path_factory):
    """会话级隔离用户数据文件（users.json）：任何触发登录路径的测试（SMS/OAuth/cloud sync
    等）会写 current_user_id 到真实 data/users.json，污染后续依赖「未登录」状态的用例
    （test_misc.py::TestAuthMeNotLoggedIn 即属此类）。重定向到 pytest 临时目录。
    """
    tmp_dir = tmp_path_factory.mktemp("users")
    users_file = tmp_dir / "users.json"

    try:
        import core.users as users_mod
        orig = users_mod.USERS_FILE
        users_mod.USERS_FILE = users_file
        yield
        users_mod.USERS_FILE = orig
    except Exception:
        yield
