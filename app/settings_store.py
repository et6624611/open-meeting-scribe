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
import platform
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


def get_chat_engine_config() -> dict:
    """
    获取"智能体模式"引擎配置（从 settings.json 的 chat_engine 命名空间）。
    Get the agent-mode chat engine config (chat_engine namespace in settings.json).

    与 access_mode（LLM/ASR 传输通道）正交（方案 D1）：本命名空间只管 AI 面板是否
    调用本地 CLI 工程化引擎，不影响 hosted/byok/local 三卡。默认关闭。

    返回 / Returns:
      {
        "enabled": False,           # 智能体模式总开关 / master switch
        "engine_id": "qoder-cli",   # 引擎 id / engine id
        "model": None,              # CLI 侧模型（可选覆盖）/ CLI model override
        "auth_tier": "readonly",    # readonly|workspace_write|full_task（§3.9-3 授权档）
        "session_persistence": True,# 是否跨轮恢复 CLI 会话（D5）
        "retention_days": 7,        # 工作区保留天数（<=0 不自动清理，R7）
        "cli_path_override": None,  # CLI 路径覆盖（高级）
      }
    """
    settings = load_settings()
    ce = settings.get("chat_engine", {}) or {}
    tier = ce.get("auth_tier", "readonly")
    if tier not in ("readonly", "workspace_write", "full_task"):
        tier = "readonly"
    try:
        retention = int(ce.get("retention_days", 7))
    except (TypeError, ValueError):
        retention = 7
    return {
        "enabled": bool(ce.get("enabled", False)),
        "engine_id": ce.get("engine_id", "qoder-cli"),
        "model": ce.get("model") or None,
        "auth_tier": tier,
        "session_persistence": bool(ce.get("session_persistence", True)),
        "retention_days": retention,
        "cli_path_override": ce.get("cli_path_override") or None,
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


# ============================================================
# 录音设备持久化（DEFECT-PROXY-TEST §2 根因 B 裁决，DEF-DEVICE-01-BE）
# ============================================================

def get_record_device() -> tuple[str, str]:
    """解析录音设备：优先级 settings.json record.device > 环境变量 RECORD_DEVICE > 平台默认。

    项目方 09-25 裁决口径（缺陷单 §2 根因 B）：用户显式选择（含空串「自动检测」合法持久值）
    优先于部署级环境变量；返回 (device, source)，source ∈ {settings, env, platform-default}。
    """
    settings = load_settings()
    rec = settings.get("record")
    if isinstance(rec, dict) and "device" in rec:
        return str(rec.get("device") or ""), "settings"
    env_val = os.getenv("RECORD_DEVICE")
    if env_val is not None:
        return env_val, "env"
    default_device = "" if platform.system() == "Windows" else "MacBook Pro麦克风"
    return default_device, "platform-default"


def save_record_device(device: str) -> None:
    """持久化录音设备到 settings.json（原子写；空串=自动检测，同样合法落盘）。"""
    settings = load_settings()
    rec = settings.get("record") if isinstance(settings.get("record"), dict) else {}
    rec["device"] = device
    settings["record"] = rec
    save_settings_to_disk(settings)


# 本地引擎默认模型存储目录（gitignored，见 .gitignore data/models/）
# Default local-engine model storage directory
DEFAULT_MODEL_DIR = "data/models/"


def get_engine_config() -> dict:
    """
    获取计算引擎配置（从 settings.json） / Get compute-engine config (from settings.json).

    R4/R5（PRD-LOCAL-ENGINE §9）：engine.mode 与 engine.local.{model_dir, model_tier}。
    R9/D-I3（REQ-LOCAL-REALTIME-INCR §6）：engine.local.realtime_segments 分段增量
    上屏参数——段长不拍固定数值，全部可配置；默认值为临时口径（enabled=false，
    待真机 20s/60s 各一场会带回延迟分布后由产品定默认值并开启）。

    返回格式 / Returns:
      {
        "mode": "cloud",            # cloud | proxy | direct | local（默认 cloud，本地引擎为显式选择）
        "local": {
          "model_dir": "data/models/",   # 模型权重存储目录 / Model weights directory
          "model_tier": "auto",          # auto | conservative | standard（R4 小模型提示词档）
          "realtime_segments": {         # R9 分段增量上屏（D-I3：可配置，默认值为临时口径）
            "enabled": False,            # 默认关闭：未开启时本地模式保持 WP-H 降级状态声明
            "min_segment_s": 5.0,        # 段最短时长（低于此值不闭合，等待更多音频）
            "min_silence_s": 0.8,        # 判定段边界的静音时长（能量 VAD）
            "max_segment_s": 30.0        # 段最长时长（到达即强制闭合）
          }
        }
      }
    """
    settings = load_settings()
    engine = settings.get("engine", {}) or {}
    local = engine.get("local", {}) or {}
    segments = local.get("realtime_segments", {}) or {}
    mode = os.getenv("ENGINE_MODE", "") or engine.get("mode", "cloud")
    return {
        "mode": mode,
        "local": {
            "model_dir": local.get("model_dir", DEFAULT_MODEL_DIR),
            "model_tier": local.get("model_tier", "auto"),
            "realtime_segments": {
                "enabled": bool(segments.get("enabled", False)),
                "min_segment_s": float(segments.get("min_segment_s", 5.0)),
                "min_silence_s": float(segments.get("min_silence_s", 0.8)),
                "max_segment_s": float(segments.get("max_segment_s", 30.0)),
            },
        },
    }


# ============================================================
# 接入方式（REQ-ACCESS-MODE-CARDS · T1）/ Access mode
# ============================================================
# 用户侧统一字段：access_mode ∈ {local, hosted, byok} | None（未配置→null 触发引导）
# 与 expert_mode（布尔）。旧字段（engine.mode / asr.mode / prefer_subscription /
# provider / base_url / model / 各 api_key）降级为底层实现细节，兼容窗口一个版本（A2）：
# 写路径继续同步旧字段以保持回滚能力。

ACCESS_MODES = ("local", "hosted", "byok")

# expert_mode 自动开启判定所用的「默认值」口径（与 get_llm_config / get_asr_config 默认一致）
_DEFAULT_EXPERT_BASELINES = {
    "llm": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    "asr": {"base_url": "https://dashscope.aliyuncs.com", "model": "paraformer-v2"},
}


def _current_prefer_subscription() -> bool:
    """读取当前登录用户的 prefer_subscription 偏好（无登录/异常 → False）。"""
    try:
        from core.users import get_current_user
        user = get_current_user()
        if user:
            return bool(user.get("prefs", {}).get("prefer_subscription", False))
    except Exception:
        pass
    return False


def derive_access_mode(settings: dict, prefer_subscription: bool | None = None) -> str | None:
    """需求书 §4 一次性迁移映射（纯函数，不落盘）。

    | 存量组合                                   | 迁移为  |
    | engine.mode=local                          | local   |
    | engine.mode=proxy                          | hosted  |
    | engine.mode=cloud（A-i1 延伸：同为云代理计费）| hosted  |
    | engine.mode=direct 且 prefer_subscription=F | byok    |
    | engine.mode=direct 且 prefer_subscription=T | hosted  |  ← A1 裁决
    | 未配置                                     | None    |  → 触发引导

    prefer_subscription=None 时读取当前登录用户偏好。
    """
    engine = settings.get("engine", {}) or {}
    mode = engine.get("mode")
    if mode == "local":
        return "local"
    if mode in ("proxy", "cloud"):
        return "hosted"
    if mode == "direct":
        ps = _current_prefer_subscription() if prefer_subscription is None else bool(prefer_subscription)
        return "hosted" if ps else "byok"
    return None


def derive_expert_mode(settings: dict) -> bool:
    """存量配置含自定义 base_url/model 覆盖或非默认 Key 组合时自动置 True（§4，保证高级用户配置不被卡片化吞掉）。"""
    for svc in ("llm", "asr"):
        svc_cfg = settings.get(svc, {}) or {}
        baseline = _DEFAULT_EXPERT_BASELINES[svc]
        base_url = svc_cfg.get("base_url", "")
        model = svc_cfg.get("model", "")
        if base_url and base_url != baseline["base_url"]:
            return True
        if model and model != baseline["model"]:
            return True
    # 非默认 Key 组合：旧版 flat api_key、声纹云配置、以及代理模式下不应出现的自有 ASR Key
    if settings.get("api_key"):
        return True
    vp = settings.get("voiceprint", {}) or {}
    vp_cloud = vp.get("cloud", {}) or {}
    if vp.get("provider") not in (None, "auto") or vp_cloud.get("base_url") or vp_cloud.get("api_key"):
        return True
    asr_cfg = settings.get("asr", {}) or {}
    if asr_cfg.get("mode") != "direct" and asr_cfg.get("api_key"):
        return True
    return False


def migrate_access_mode(settings: dict, prefer_subscription: bool | None = None) -> bool:
    """就地执行一次性迁移：补充 access_mode / expert_mode / 迁移标记；旧字段原样保留（回滚用）。

    已迁移（存在 `_access_mode_migrated` 标记）则不重复推导，返回 False。
    """
    if settings.get("_access_mode_migrated"):
        return False
    if "access_mode" not in settings:
        settings["access_mode"] = derive_access_mode(settings, prefer_subscription)
    if not isinstance(settings.get("expert_mode"), bool):
        settings["expert_mode"] = derive_expert_mode(settings)
    settings["_access_mode_migrated"] = True
    return True


def run_access_mode_migration() -> bool:
    """启动时迁移入口：加载 settings.json，如需迁移则持久化。返回是否发生变更。"""
    settings = load_settings()
    if migrate_access_mode(settings):
        save_settings_to_disk(settings)
        logger.info(f"接入方式迁移完成: access_mode={settings.get('access_mode')}, expert_mode={settings.get('expert_mode')}")
        return True
    return False


def get_access_mode() -> str | None:
    """当前接入方式（路由判定唯一数据源，见 core/routing.py）。

    已迁移 → 返回持久值（可能为 None=未配置，触发引导）；
    未迁移（如 CLI 先于服务启动钩子读取）→ 按 §4 惰性推导，不写盘。
    """
    settings = load_settings()
    if settings.get("_access_mode_migrated"):
        mode = settings.get("access_mode")
        return mode if mode in ACCESS_MODES else None
    return derive_access_mode(settings)


def get_expert_mode() -> bool:
    """专家模式开关。已迁移 → 持久值优先；未迁移 → 按存量配置惰性推导。"""
    settings = load_settings()
    if settings.get("_access_mode_migrated"):
        em = settings.get("expert_mode")
        return bool(em) if isinstance(em, bool) else derive_expert_mode(settings)
    return derive_expert_mode(settings)


def apply_access_mode(settings: dict, mode: str | None) -> None:
    """写入 access_mode 并同步旧字段（A2 兼容窗口：回滚后旧版本可直接读取生效）。

    mode=None 表示未配置（触发引导），仅清除选择不动旧字段。
    """
    if mode is not None and mode not in ACCESS_MODES:
        raise ValueError(f"非法 access_mode: {mode!r}，允许值: {ACCESS_MODES}")
    settings["access_mode"] = mode
    settings["_access_mode_migrated"] = True
    if mode is None:
        return
    engine = dict(settings.get("engine", {}) or {})
    asr = dict(settings.get("asr", {}) or {})
    if mode == "local":
        engine["mode"] = "local"
    elif mode == "hosted":
        engine["mode"] = "proxy"
        asr["mode"] = "proxy"
    elif mode == "byok":
        engine["mode"] = "direct"
        asr["mode"] = "direct"
    settings["engine"] = engine
    settings["asr"] = asr


def set_access_mode(mode: str | None) -> None:
    """持久化 access_mode（含旧字段同步）。非法值抛 ValueError，不落盘。"""
    settings = load_settings()
    apply_access_mode(settings, mode)
    save_settings_to_disk(settings)


def set_expert_mode(enabled: bool) -> None:
    """持久化 expert_mode 开关。首次写入时顺带完成迁移，避免惰性推导覆盖显式选择。"""
    settings = load_settings()
    migrate_access_mode(settings)
    settings["expert_mode"] = bool(enabled)
    save_settings_to_disk(settings)
