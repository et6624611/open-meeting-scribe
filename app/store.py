"""
app/store.py — 共享状态层（兼容入口） / Shared state layer (compatibility entry)

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 3.1.0

集中管理所有跨路由的共享状态、配置常量与辅助函数 / Centralized management of all cross-router shared state, config constants, and helper functions.

v3.1 重构：使用 __getattr__ 动态代理到 core.* 层，解决静态 import 导致的
常量更新（如 RECORD_DEVICE）在 re-export 层不可见的问题。
BASE_DIR/STATIC_DIR 留在本模块（PyInstaller 打包相关）。
"""

import logging
import sys

from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 仅本模块保留：PyInstaller 打包相关常量 /
# Only this module keeps PyInstaller packaging constants
# ============================================================

from pathlib import Path

# PyInstaller 打包后，可执行文件所在目录为 exe 位置；资源文件在 _MEIPASS 临时目录 /
# After packaging, exe dir is the executable location; resource files are in _MEIPASS temp dir
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # PyInstaller 模式：BASE_DIR = exe 所在目录（数据持久化），STATIC_DIR = _MEIPASS/app/static（资源读取）
    BASE_DIR = Path(sys.executable).parent
    STATIC_DIR = Path(sys._MEIPASS) / "app" / "static"
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

_logger = logging.getLogger(__name__)

# ============================================================
# 动态代理到 core.* 层（运行时可同步更新）/
# Dynamic proxy to core.* layer (syncs with runtime updates)
# ============================================================

import core.pipeline_runner as _pipeline_runner
import core.realtime_store as _realtime_store
import core.settings_store as _settings_store
import core.task_store as _task_store

_CORE_MODULES = {
    "_task_store": _task_store,
    "_settings_store": _settings_store,
    "_realtime_store": _realtime_store,
    "_pipeline_runner": _pipeline_runner,
}


def __getattr__(name):
    """动态代理到 core 层，保证运行时更新可见。"""
    if name in ("BASE_DIR", "STATIC_DIR", "_logger"):
        raise AttributeError(name)
    for mod in _CORE_MODULES.values():
        try:
            return getattr(mod, name)
        except AttributeError:
            continue
    raise AttributeError(f"module 'app.store' has no attribute {name!r}")


# ruff: noqa: F822 — re-export 层，__all__ 列出的名字通过 __getattr__ 动态转发到 core.*，静态分析无法识别
__all__ = [
    "BASE_DIR",
    "STATIC_DIR",
    # core.task_store
    "OUTPUT_DIR", "RECORDINGS_DIR", "TASKS_DIR", "UPLOAD_DIR",
    "cleanup_orphaned_intermediate_files", "infer_task_source",
    "load_tasks_from_disk", "recover_interrupted_tasks",
    "save_task_to_disk", "tasks",
    # core.settings_store
    "ASR_CAP_SOURCES", "DEFAULT_MODEL_DIR", "HOTWORD_MAPPINGS_FILE", "HOTWORDS_FILE",
    "LLM_CAP_SOURCES", "PHILOSOPHIES_FILE", "RECORD_DEVICE", "SETTINGS_FILE",
    "apply_auto_fallback", "apply_capability_source", "default_model_dir",
    "derive_expert_mode", "ensure_percap_migrated", "get_active_api_key",
    "get_asr_config", "get_auto_fallback", "get_capability_status",
    "get_chat_engine_config", "get_engine_config", "get_expert_mode",
    "get_feature_flags", "get_llm_config", "get_record_device",
    "get_silence_detection_config", "get_storage_config", "get_transcript_config",
    "get_web_search_config", "load_settings", "mask_api_key",
    "run_percap_migration", "save_record_device", "save_settings_to_disk",
    "save_web_search_config", "set_capability_source", "set_expert_mode",
    "set_record_device",
    # core.realtime_store
    "REALTIME_BUFFER_MAX", "event_loop", "push_realtime_msg",
    "realtime_chapter_generators", "realtime_diarizers", "realtime_full_sealed",
    "realtime_full_transcripts", "realtime_last_heartbeat", "realtime_last_sentence",
    "realtime_presence_scores", "realtime_queues", "realtime_silence_monitors",
    "realtime_silence_warnings", "realtime_speaker_maps", "realtime_summarizers",
    "realtime_transcript_buffers", "realtime_transcribers", "realtime_translations",
    "realtime_translators", "resolve_realtime_speaker_name",
    # core.pipeline_runner
    "PIPELINE_MAX_RETRIES", "PIPELINE_RETRY_DELAYS", "SPEAKER_COUNT_MAX",
    "SPEAKER_COUNT_MIN", "estimate_speaker_count", "run_pipeline_task",
    "run_stage2_task",
]
