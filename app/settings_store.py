"""
app/settings_store.py — 兼容 re-export 层 / Compatibility re-export layer

实际实现已下沉至 core/settings_store.py；本文件保留以维持既有 import 路径。
/ Implementation sunk to core/settings_store.py; this file remains for backward-compat import paths.

使用模块 __getattr__ 动态代理，保证 set_record_device 等更新 core 层常量后，
动态访问（如 import app.store as store; store.RECORD_DEVICE）能看到最新值。
/ Uses module __getattr__ dynamic proxy so set_record_device updates to core-layer constants
are visible through dynamic access (e.g. import app.store; store.RECORD_DEVICE).
"""

import sys
import core.settings_store as _core


def __getattr__(name):
    """动态代理到 core.settings_store — 支持运行时常量更新可见。"""
    if name.startswith("_"):
        raise AttributeError(name)
    try:
        return getattr(_core, name)
    except AttributeError:
        raise AttributeError(f"module 'app.settings_store' has no attribute {name!r}")


__all__ = [
    "ASR_CAP_SOURCES",
    "DEFAULT_MODEL_DIR",
    "HOTWORD_MAPPINGS_FILE",
    "HOTWORDS_FILE",
    "LLM_CAP_SOURCES",
    "PHILOSOPHIES_FILE",
    "RECORD_DEVICE",
    "SETTINGS_FILE",
    "apply_auto_fallback",
    "apply_capability_source",
    "default_model_dir",
    "derive_expert_mode",
    "ensure_percap_migrated",
    "get_active_api_key",
    "get_asr_config",
    "get_auto_fallback",
    "get_capability_status",
    "get_chat_engine_config",
    "get_engine_config",
    "get_expert_mode",
    "get_feature_flags",
    "get_llm_config",
    "get_record_device",
    "get_silence_detection_config",
    "get_storage_config",
    "get_transcript_config",
    "get_web_search_config",
    "load_settings",
    "mask_api_key",
    "run_percap_migration",
    "save_record_device",
    "save_settings_to_disk",
    "save_web_search_config",
    "set_capability_source",
    "set_expert_mode",
    "set_record_device",
]
