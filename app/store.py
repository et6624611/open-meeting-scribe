"""
app/store.py — 应用静态资源路径 / Application static resource paths

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 4.0.0

T-22（2026-11-06）：四合一门面已拆分，本模块只保留 PyInstaller 相关的静态资源路径。
状态、配置、执行、实时四类能力分别直连 core 层：
  tasks / save_task_to_disk      → core.task_store
  get_llm_config 等配置函数        → core.settings_store
  run_pipeline_task / run_stage2_task → core.pipeline_runner
  realtime_* / push_realtime_msg  → core.realtime_store
"""

import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from pathlib import Path

from core.paths import BASE_DIR  # noqa: F401 — re-export，既有 app.store.BASE_DIR 路径不变

# PyInstaller 打包后，资源文件在 _MEIPASS 临时目录 /
# After packaging, resources are in _MEIPASS temp dir
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    STATIC_DIR = Path(sys._MEIPASS) / "app" / "static"
else:
    STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

_logger = logging.getLogger(__name__)

__all__ = ["BASE_DIR", "STATIC_DIR"]
