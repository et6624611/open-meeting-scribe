"""
app/store.py — 共享状态层（兼容入口） / Shared state layer (compatibility entry)

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 2.0.0

集中管理所有跨路由的共享状态、配置常量与辅助函数 / Centralized management of all cross-router shared state, config constants, and helper functions.
各 router 模块通过 import 引用，避免循环依赖 / Each router module imports to avoid circular dependencies.

v2.0 重构：实际逻辑已拆分至以下子模块，本文件作为兼容层 / v2.0 refactor: actual logic split into following submodules; this file serves as compatibility layer
  统一 re-export，确保所有既有 import 路径不受影响 / Unified re-export, ensuring all existing import paths remain unaffected.
  - app/task_store.py       — 任务持久化与恢复 / Task persistence and recovery
  - app/settings_store.py   — 设置管理 / Settings management
  - app/realtime_store.py   — 实时消息推送状态 / Realtime message push state
  - core/pipeline_runner.py — 管线编排（后台执行） / Pipeline orchestration (background execution)
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 目录常量（保留在本模块，被多个路由直接引用） / Directory constants (kept here; directly referenced by multiple routers)
# ============================================================

# PyInstaller 打包后，可执行文件所在目录为 exe 位置；资源文件在 _MEIPASS 临时目录 /
# After packaging, exe dir is the executable location; resource files are in _MEIPASS temp dir
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # PyInstaller 模式：BASE_DIR = exe 所在目录（数据持久化），STATIC_DIR = _MEIPASS/app/static（资源读取）
    # PyInstaller mode: BASE_DIR = exe dir (data persistence), STATIC_DIR = _MEIPASS/app/static (resource reading)
    BASE_DIR = Path(sys.executable).parent
    STATIC_DIR = Path(sys._MEIPASS) / "app" / "static"
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

OUTPUT_DIR = Path("data/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

RECORDINGS_DIR = Path("data/recordings")
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

# 录制设备名（DEF-DEVICE-01-BE 持久化：settings.json record.device > 环境变量 RECORD_DEVICE > 平台默认）
# Recording device (persisted per DEF-DEVICE-01-BE; priority settings > env > platform default)
import logging as _logging

_logger = _logging.getLogger(__name__)


def _resolve_record_device() -> str:
    from app.settings_store import get_record_device
    device, source = get_record_device()
    # 验收④（按项目方裁决口径修订）：优先级判定结果落启动日志留痕
    _logger.info(f"[录制] 设备解析: '{device or '自动检测'}' 来源={source}（优先级 settings>env>平台默认，项目方 09-25 裁决）")
    return device


RECORD_DEVICE = _resolve_record_device()


def set_record_device(device: str) -> None:
    """更新录音设备并持久化到 settings.json（重启后恢复；空串=自动检测合法持久值）。
    Update recording device and persist to settings.json (restored on restart; empty = auto-detect is a valid persisted value).
    """
    global RECORD_DEVICE
    RECORD_DEVICE = device
    try:
        from app.settings_store import save_record_device
        save_record_device(device)
    except Exception as e:  # 持久化失败不阻断运行时生效（降级为升级前行为）
        _logger.error(f"[录制] 设备持久化失败（运行时值仍生效，重启后将丢失）: {e}")

# ============================================================
# 兼容 re-export：设置管理 / Compat re-export: Settings management
# ============================================================
# ============================================================
# 兼容 re-export：实时状态 / Compat re-export: Realtime state
# ============================================================
from app.realtime_store import (  # noqa: E402, F401
    REALTIME_BUFFER_MAX,
    event_loop,
    push_realtime_msg,
    realtime_chapter_generators,
    realtime_diarizers,
    realtime_full_sealed,
    realtime_full_transcripts,
    realtime_last_heartbeat,
    realtime_last_sentence,
    realtime_presence_scores,
    realtime_queues,
    realtime_silence_monitors,
    realtime_silence_warnings,
    realtime_speaker_maps,
    realtime_summarizers,
    realtime_transcribers,
    realtime_transcript_buffers,
    realtime_translations,
    realtime_translators,
    resolve_realtime_speaker_name,
)
from app.settings_store import (  # noqa: E402, F401
    HOTWORD_MAPPINGS_FILE,
    HOTWORDS_FILE,
    PHILOSOPHIES_FILE,
    SETTINGS_FILE,
    get_active_api_key,
    get_asr_config,
    get_capability_status,
    get_chat_engine_config,
    get_engine_config,
    get_feature_flags,
    get_llm_config,
    get_silence_detection_config,
    get_storage_config,
    get_transcript_config,
    load_settings,
    mask_api_key,
    save_settings_to_disk,
)

# ============================================================
# 兼容 re-export：任务持久化 / Compat re-export: Task persistence
# ============================================================
from app.task_store import (  # noqa: E402, F401
    TASKS_DIR,
    cleanup_orphaned_intermediate_files,
    infer_task_source,
    load_tasks_from_disk,
    recover_interrupted_tasks,
    save_task_to_disk,
    tasks,
)

# ============================================================
# 兼容 re-export：管线编排 / Compat re-export: Pipeline orchestration
# ============================================================
from core.pipeline_runner import (  # noqa: E402, F401
    PIPELINE_MAX_RETRIES,
    PIPELINE_RETRY_DELAYS,
    SPEAKER_COUNT_MAX,
    SPEAKER_COUNT_MIN,
    estimate_speaker_count,
    run_pipeline_task,
    run_stage2_task,
)
