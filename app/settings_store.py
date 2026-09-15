"""
app/settings_store.py — 设置管理 / Settings management

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
版本 / Version: 1.0.0

职责 / Responsibilities:
  - 设置文件（settings.json）的加载与持久化 / Settings file (settings.json) loading and persistence
  - API Key 脱敏与获取 / API Key masking and retrieval
  - LLM / ASR / 声纹 / 功能开关 / 静默检测 配置读取 / LLM / ASR / voiceprint / feature toggles / silence detection config reading

从 app/store.py 拆分而来，与原模块通过 re-export 保持向后兼容 / Split from app/store.py; backward-compatible via re-export.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================================
# 数据文件路径 / Data file paths
# ============================================================

HOTWORDS_FILE = Path("data/hotwords.txt")
HOTWORD_MAPPINGS_FILE = Path("data/hotword_mappings.txt")
SETTINGS_FILE = Path("data/settings.json")
PHILOSOPHIES_FILE = Path("data/philosophies.json")


# ============================================================
# 设置读写 / Settings read/write
# ============================================================


def load_settings() -> dict:
    """
    加载设置（从 settings.json） / Load settings (from settings.json).

    返回空 dict 若文件不存在 / Return empty dict if file not found.
    """
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"加载 settings.json 失败: {e}")
            return {}
    return {}


def save_settings_to_disk(settings: dict) -> None:
    """持久化设置到 settings.json（原子写入） / Persist settings to settings.json (atomic write)."""
    from core.fs_atomic import atomic_write_json
    atomic_write_json(SETTINGS_FILE, settings)


# ============================================================
# API Key 管理 / API Key Management
# ============================================================


def mask_api_key(key: str) -> str:
    """
    API Key 脱敏 / API Key masking：仅显示前 3 位和后 4 位，中间用 **** 替代 / Show only first 3 and last 4 chars; middle replaced with ****.

    示例 / Example：sk-abc...xyz → sk-****xyz
    若 key 长度不足 8 位，全部用 **** 替代 / If key length < 8, all replaced with ****.
    """
    if not key or len(key) < 8:
        return "****"
    return f"{key[:3]}****{key[-4:]}"


def get_active_api_key() -> str:
    """
    获取当前生效的 LLM API Key / Get currently active LLM API Key.

    优先级 / Priority:
      1. settings.json 中的 llm.api_key / llm.api_key in settings.json
      2. 旧版 settings.json 中的 api_key（向后兼容） / Legacy api_key in settings.json (backward compat)
      3. 环境变量 DASHSCOPE_API_KEY / Environment variable DASHSCOPE_API_KEY
      4. 空字符串 / Empty string

    注意 / Note：ASR 模块请使用 get_asr_config() 获取独立的 ASR Key / For ASR module, use get_asr_config() for independent ASR Key.
    """
    settings = load_settings()

    # 新版格式：llm.api_key / New format: llm.api_key
    llm_config = settings.get("llm", {})
    if llm_config.get("api_key"):
        return llm_config["api_key"]

    # 旧版格式：api_key（向后兼容） / Legacy format: api_key (backward compat)
    if settings.get("api_key"):
        return settings["api_key"]

    # 环境变量兆底 / Environment variable fallback
    return os.getenv("DASHSCOPE_API_KEY", "")


# ============================================================
# 各领域配置 / Domain Configurations
# ============================================================


def get_llm_config() -> dict:
    """
    获取 LLM 配置（从 settings.json） / Get LLM config (from settings.json).

    返回格式 / Returns:
      {
        "provider": "DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "sk-...",  # 明文（仅内部使用） / Plaintext (internal use only)
        "model": "qwen-plus"
      }

    若未配置，返回默认值（DashScope） / Return defaults (DashScope) if not configured.
    """
    settings = load_settings()
    llm_config = settings.get("llm", {})

    # 向后兼容：若 llm 不存在但 api_key 存在，迁移为新版格式 / Backward compat: if llm missing but api_key exists, migrate to new format
    if not llm_config and settings.get("api_key"):
        llm_config = {
            "provider": "DashScope",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": settings["api_key"],
            "model": settings.get("model", "qwen-plus"),
        }

    # 默认值 / Defaults
    return {
        "provider": llm_config.get("provider", "DashScope"),
        "base_url": llm_config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "api_key": llm_config.get("api_key", get_active_api_key()),
        "model": llm_config.get("model", "qwen-plus"),
    }


def get_asr_config() -> dict:
    """
    获取 ASR（语音转写）配置（从 settings.json） / Get ASR (speech transcription) config (from settings.json).

    支持三种接入模式 / Supports three access modes:
      - proxy（默认） / (default)：通过 ASR 代理服务器中转 / Via ASR proxy
      - direct：用户自持 API Key，直连 DashScope / User's own API Key; direct connection
      - cloud：通过云端服务器代理（桌面客户端默认） / Via cloud server proxy (desktop client default)

    返回格式 / Returns:
      {
        "mode": "proxy" | "direct" | "cloud",
        "provider": "DashScope",
        "base_url": "https://...",
        "api_key": "sk-...",
        "proxy_url": "http://...",
        "model": "paraformer-v2",
      }
    """
    settings = load_settings()
    asr_config = settings.get("asr", {})
    # 环境变量 ASR_MODE 优先于 settings.json（桌面端通过 .env 设置）
    mode = os.getenv("ASR_MODE", "") or asr_config.get("mode", "proxy")

    if mode == "direct":
        return {
            "mode": "direct",
            "provider": asr_config.get("provider", "DashScope"),
            "base_url": asr_config.get("base_url", "https://dashscope.aliyuncs.com"),
            "api_key": asr_config.get("api_key", "") or os.getenv("DASHSCOPE_API_KEY", ""),
            "model": asr_config.get("model", "paraformer-v2"),
            "proxy_url": "",
        }

    if mode == "cloud":
        return {
            "mode": "cloud",
            "provider": "DashScope（云端代理）",
            "base_url": "",
            "api_key": "",
            "proxy_url": os.getenv("CLOUD_API_URL", ""),
            "model": asr_config.get("model", "paraformer-v2"),
        }

    # 代理模式（默认） / Proxy mode (default)
    proxy_url = os.getenv("ASR_PROXY_URL", "")

    # ── 自动降级 ──
    # proxy 无 URL 时：先尝试 cloud，再尝试 direct
    if not proxy_url:
        # 尝试 cloud 模式
        try:
            from core.cloud_client import is_cloud_enabled
            if is_cloud_enabled():
                logger.info("ASR proxy URL empty, cloud enabled; auto-switching to cloud mode")
                return {
                    "mode": "cloud",
                    "provider": "DashScope（云端代理）",
                    "base_url": "",
                    "api_key": "",
                    "proxy_url": os.getenv("CLOUD_API_URL", ""),
                    "model": asr_config.get("model", "paraformer-v2"),
                }
        except Exception:
            pass
        # 尝试 direct 模式
        dashscope_key = os.getenv("DASHSCOPE_API_KEY", "")
        if dashscope_key:
            logger.info("ASR proxy URL empty, DASHSCOPE_API_KEY available; auto-switching to direct mode")
            return {
                "mode": "direct",
                "provider": asr_config.get("provider", "DashScope"),
                "base_url": asr_config.get("base_url", "https://dashscope.aliyuncs.com"),
                "api_key": dashscope_key,
                "model": asr_config.get("model", "paraformer-v2"),
                "proxy_url": "",
            }

    return {
        "mode": "proxy",
        "provider": "DashScope",
        "proxy_url": proxy_url,
        "model": asr_config.get("model", "paraformer-v2"),
        "base_url": "",
        "api_key": "",
    }


def get_voiceprint_config() -> dict:
    """
    获取声纹识别配置（从 settings.json） / Get voiceprint recognition config (from settings.json).

    返回格式 / Returns:
      {
        "provider": "auto",       # "local" / "cloud" / "auto"
        "cloud": {
          "base_url": "",
          "api_key": ""
        }
      }

    环境变量 VOICEPRINT_PROVIDER / VOICEPRINT_API_KEY / VOICEPRINT_BASE_URL
    可覆盖 settings.json 中的对应字段 / Can override corresponding fields in settings.json.
    """
    settings = load_settings()
    vp_config = settings.get("voiceprint", {})
    cloud_config = vp_config.get("cloud", {})

    return {
        "provider": vp_config.get("provider", "auto"),
        "cloud": {
            "base_url": cloud_config.get("base_url", ""),
            "api_key": cloud_config.get("api_key", ""),
        },
    }


def get_feature_flags() -> dict:
    """
    获取功能开关配置（从 settings.json） / Get feature flag config (from settings.json).

    返回格式 / Returns:
      {
        "realtime_chapters": true,   # 实时章节生成 / Realtime chapter generation
        "realtime_summary": true,    # 实时总结生成 / Realtime summary generation
        "realtime_summary_interval": 60,  # 总结间隔（秒），可选 30/60/120/300 / Summary interval (sec); options: 30/60/120/300
        "update_check": true,        # 软件更新提示 / Software update notification
        "voiceprint_auto_match": false  # 声纹自动识别（实验性，默认关闭） / Auto voiceprint matching (experimental; default off)
      }

    未配置的字段 / Unconfigured fields: realtime_* / update_check 默认启用（true） / default on (true),
    voiceprint_auto_match 默认关闭（false）——CAM++ 模型精度尚未达标 / default off (false) — CAM++ model accuracy not yet sufficient.
    """
    settings = load_settings()
    ff = settings.get("feature_flags", {})
    return {
        "realtime_chapters": ff.get("realtime_chapters", True),
        "realtime_summary": ff.get("realtime_summary", True),
        "realtime_summary_interval": ff.get("realtime_summary_interval", 60),
        "update_check": ff.get("update_check", True),
        "voiceprint_auto_match": ff.get("voiceprint_auto_match", False),
    }


def get_silence_detection_config() -> dict:
    """
    获取静默检测配置（从 settings.json） / Get silence detection config (from settings.json).

    详见 / See docs/design/SILENCE_DETECTION.md。

    返回格式 / Returns:
      {
        "enabled": true,
        "presence": { ... },   # 存在性评分参数 / Presence scoring params
        "audio": { ... },      # 音频层阈值 / Audio layer thresholds
        "action": { ... }      # 提醒与关停参数 / Warning and shutdown params
      }
    """
    settings = load_settings()
    sd = settings.get("silence_detection", {})
    return {
        "enabled": sd.get("enabled", True),
        "presence": {
            "score_max": sd.get("presence", {}).get("score_max", 100),
            "score_decay_per_sec": sd.get("presence", {}).get("score_decay_per_sec", 1),
            "score_interaction_boost": sd.get("presence", {}).get("score_interaction_boost", 100),
            "score_visibility_return": sd.get("presence", {}).get("score_visibility_return", 80),
            "score_focus_return": sd.get("presence", {}).get("score_focus_return", 60),
            "score_heartbeat": sd.get("presence", {}).get("score_heartbeat", 20),
            "score_visibility_hidden_multiplier": sd.get("presence", {}).get("score_visibility_hidden_multiplier", 0.3),
            "score_blur_multiplier": sd.get("presence", {}).get("score_blur_multiplier", 0.5),
            "threshold_warning": sd.get("presence", {}).get("threshold_warning", 20),
            "heartbeat_interval_sec": sd.get("presence", {}).get("heartbeat_interval_sec", 30),
            "heartbeat_timeout_sec": sd.get("presence", {}).get("heartbeat_timeout_sec", 90),
        },
        "audio": {
            "rms_silence_db": sd.get("audio", {}).get("rms_silence_db", -45),
            "asr_no_sentence_timeout_sec": sd.get("audio", {}).get("asr_no_sentence_timeout_sec", 300),
        },
        "action": {
            "gentle_countdown_sec": sd.get("action", {}).get("gentle_countdown_sec", 120),
            "urgent_countdown_sec": sd.get("action", {}).get("urgent_countdown_sec", 60),
            "max_warnings_per_session": sd.get("action", {}).get("max_warnings_per_session", 2),
        },
    }


def get_storage_config() -> dict:
    """
    获取存储管理配置（从 settings.json） / Get storage management config (from settings.json).

    返回格式 / Returns:
      {
        "auto_clean_intermediate": true,   # 转写完成后自动清理归一化中间文件 / Auto-cleanup normalized intermediate files after transcription
        "auto_archive_days": 0             # 0=关闭 / 0=off; N=N天前的已完成会议自动删除音频 / N=auto-delete audio for completed meetings older than N days
      }
    """
    settings = load_settings()
    sc = settings.get("storage", {})
    return {
        "auto_clean_intermediate": sc.get("auto_clean_intermediate", True),
        "auto_archive_days": sc.get("auto_archive_days", 0),
    }
