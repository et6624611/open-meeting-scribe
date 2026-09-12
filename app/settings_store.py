"""
app/settings_store.py — 设置管理

作者：王永亮
创建：2026-09-12
版本：1.0.0

职责：
  - 设置文件（settings.json）的加载与持久化
  - API Key 脱敏与获取
  - LLM / ASR / 声纹 / 功能开关 / 静默检测 配置读取

从 app/store.py 拆分而来，与原模块通过 re-export 保持向后兼容。
"""

import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================================
# 数据文件路径
# ============================================================

HOTWORDS_FILE = Path("data/hotwords.txt")
HOTWORD_MAPPINGS_FILE = Path("data/hotword_mappings.txt")
SETTINGS_FILE = Path("data/settings.json")
PHILOSOPHIES_FILE = Path("data/philosophies.json")


# ============================================================
# 设置读写
# ============================================================


def load_settings() -> dict:
    """
    加载设置（从 settings.json）。

    返回空 dict 若文件不存在。
    """
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"加载 settings.json 失败: {e}")
            return {}
    return {}


def save_settings_to_disk(settings: dict) -> None:
    """持久化设置到 settings.json"""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# API Key 管理
# ============================================================


def mask_api_key(key: str) -> str:
    """
    API Key 脱敏：仅显示前 3 位和后 4 位，中间用 **** 替代。

    示例：sk-abc...xyz → sk-****xyz
    若 key 长度不足 8 位，全部用 **** 替代。
    """
    if not key or len(key) < 8:
        return "****"
    return f"{key[:3]}****{key[-4:]}"


def get_active_api_key() -> str:
    """
    获取当前生效的 LLM API Key。

    优先级：
      1. settings.json 中的 llm.api_key
      2. 旧版 settings.json 中的 api_key（向后兼容）
      3. 环境变量 DASHSCOPE_API_KEY
      4. 空字符串

    注意：ASR 模块请使用 get_asr_config() 获取独立的 ASR Key。
    """
    settings = load_settings()

    # 新版格式：llm.api_key
    llm_config = settings.get("llm", {})
    if llm_config.get("api_key"):
        return llm_config["api_key"]

    # 旧版格式：api_key（向后兼容）
    if settings.get("api_key"):
        return settings["api_key"]

    # 环境变量兜底
    return os.getenv("DASHSCOPE_API_KEY", "")


# ============================================================
# 各领域配置
# ============================================================


def get_llm_config() -> dict:
    """
    获取 LLM 配置（从 settings.json）。

    返回格式：
      {
        "provider": "DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "sk-...",  # 明文（仅内部使用）
        "model": "qwen-plus"
      }

    若未配置，返回默认值（DashScope）。
    """
    settings = load_settings()
    llm_config = settings.get("llm", {})

    # 向后兼容：若 llm 不存在但 api_key 存在，迁移为新版格式
    if not llm_config and settings.get("api_key"):
        llm_config = {
            "provider": "DashScope",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": settings["api_key"],
            "model": settings.get("model", "qwen-plus"),
        }

    # 默认值
    return {
        "provider": llm_config.get("provider", "DashScope"),
        "base_url": llm_config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "api_key": llm_config.get("api_key", get_active_api_key()),
        "model": llm_config.get("model", "qwen-plus"),
    }


def get_asr_config() -> dict:
    """
    获取 ASR（语音转写）配置。

    代理模式下，客户端不再持有 DashScope API Key，所有 ASR 请求通过代理服务器中转。
    返回格式：
      {
        "provider": "DashScope",
        "proxy_url": "http://your-asr-proxy-server:8200",
        "model": "paraformer-v2",
        "source": "platform"  # 始终为 platform（代理模式）
      }

    详见 docs/adr/0012-ASR转写走云端代理.md
    """
    return {
        "provider": "DashScope",
        "proxy_url": os.getenv("ASR_PROXY_URL", ""),
        "model": "paraformer-v2",
        "source": "platform",
    }


def get_voiceprint_config() -> dict:
    """
    获取声纹识别配置（从 settings.json）。

    返回格式：
      {
        "provider": "auto",       # "local" / "cloud" / "auto"
        "cloud": {
          "base_url": "",
          "api_key": ""
        }
      }

    环境变量 VOICEPRINT_PROVIDER / VOICEPRINT_API_KEY / VOICEPRINT_BASE_URL
    可覆盖 settings.json 中的对应字段。
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
    获取功能开关配置（从 settings.json）。

    返回格式：
      {
        "realtime_chapters": true,   # 实时章节生成
        "realtime_summary": true,    # 实时总结生成
        "realtime_summary_interval": 60,  # 总结间隔（秒），可选 30/60/120/300
        "update_check": true,        # 软件更新提示
        "voiceprint_auto_match": false  # 声纹自动识别（实验性，默认关闭）
      }

    未配置的字段：realtime_* / update_check 默认启用（true），
    voiceprint_auto_match 默认关闭（false）——CAM++ 模型精度尚未达标。
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
    获取静默检测配置（从 settings.json）。

    详见 docs/design/SILENCE_DETECTION.md。

    返回格式：
      {
        "enabled": true,
        "presence": { ... },   # 存在性评分参数
        "audio": { ... },      # 音频层阈值
        "action": { ... }      # 提醒与关停参数
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
