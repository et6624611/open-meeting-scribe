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


# 声纹配置 getter 已随 REQ-SETTINGS-IA 第 4 刀下架：voiceprint.provider / cloud_base_url /
# cloud_api_key 字段在 schema/UI/后端三处不存在，声纹结构性零出网（仅本机 CAM++）。


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
        "auth_tier_explicit": False,# 用户是否在设置页显式声明过授权档（模式即权限：未显式=按模式派生）
        "session_persistence": True,# 是否跨轮恢复 CLI 会话（D5）
        "retention_days": 7,        # 工作区保留天数（<=0 不自动清理，R7）
        "cli_path_override": None,  # CLI 路径覆盖（高级）
      }
      优先级链（智能体改写通道方案 §5.1）：请求级显式 auth_tier >
      用户在设置页显式降级（auth_tier_explicit=true 的存量值）> 模式派生默认（agent→workspace_write）。
      存量 settings.json 里的 auth_tier="readonly" 多为旧默认值而非用户选择，
      故仅当 auth_tier_explicit=true（保存过设置页）时才视为显式降级。
      Priority chain: request tier > explicit user downgrade > mode-derived default.
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
        "auth_tier_explicit": bool(ce.get("_auth_tier_explicit", False)),
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
        "voiceprint_v2": ff.get("voiceprint_v2", True),
        "chrome_autohide": ff.get("chrome_autohide", True),
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


# 本地引擎默认模型存储目录（开发态；gitignored，见 .gitignore data/models/）
# 冻结态按平台锚点（D-G3 (a)，B-2 修复：相对路径会解析进只读 bundle）——见 default_model_dir()
DEFAULT_MODEL_DIR = "data/models/"


def default_model_dir() -> str:
    """平台感知默认模型目录 / Platform-aware default model directory.

    开发态 → ``data/models/``；冻结态 → ``core.engine_paths.get_default_model_dir()``
    （Win ``%LOCALAPPDATA%\\OpenMeetingScribe\\models``、mac
    ``~/Library/Application Support/OpenMeetingScribe/models``）。
    """
    try:
        from core.engine_paths import get_default_model_dir, is_frozen
        if is_frozen():
            return str(get_default_model_dir())
    except Exception:
        pass
    # 开发态保持历史字面量（含尾部斜杠，settings.json 持久化值与旧版一致）
    return DEFAULT_MODEL_DIR


def get_engine_config() -> dict:
    """
    获取计算引擎配置（从 settings.json） / Get compute-engine config (from settings.json).

    R4/R5（PRD-LOCAL-ENGINE §9）：engine.mode 与 engine.local.{model_dir, model_tier, engine_dir}。
    R9/D-I3（REQ-LOCAL-REALTIME-INCR §6）：engine.local.realtime_segments 分段增量
    上屏参数——段长不拍固定数值，全部可配置。WP-I 验收后默认 enabled=true
    （本地模式即逐句上屏，无用户侧开关；仅保留 settings.json 显式置 false 的
    逃生通道，回到 WP-H 录音后批转写降级口径）。

    返回格式 / Returns:
      {
        "mode": "cloud",            # cloud | proxy | direct | local（默认 cloud，本地引擎为显式选择）
        "local": {
          "model_dir": "<平台默认锚点>",  # 模型权重存储目录（未配置→default_model_dir()）
          "model_tier": "auto",          # auto | conservative | standard（R4 小模型提示词档）
          "realtime_segments": {         # R9 分段增量上屏（WP-I 验收后默认开启）
            "enabled": True,             # 本地模式默认逐句上屏；显式置 false 回到录音后批转写
            "min_segment_s": 5.0,        # 段最短时长（低于此值不闭合，等待更多音频）
            "min_silence_s": 0.8,        # 判定段边界的静音时长（能量 VAD）
            "max_segment_s": 30.0        # 段最长时长（到达即强制闭合）
          },
          "engine_dir": ""              # 引擎组件目录显式覆盖（D-G1 搜索序②，空=自动定位）
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
            # 未配置/空值 → 平台默认锚点（冻结态禁止相对路径，B-2 / D-G3）
            "model_dir": local.get("model_dir") or default_model_dir(),
            "model_tier": local.get("model_tier", "auto"),
            "realtime_segments": {
                "enabled": bool(segments.get("enabled", True)),
                "min_segment_s": float(segments.get("min_segment_s", 5.0)),
                "min_silence_s": float(segments.get("min_silence_s", 0.8)),
                "max_segment_s": float(segments.get("max_segment_s", 30.0)),
            },
            "engine_dir": local.get("engine_dir", ""),
            # 引擎组件包下载 URL 覆盖（政企内网源；空=GitHub Release 约定，G-4b）
            "component_url": local.get("component_url", ""),
        },
    }


def get_transcript_config() -> dict:
    """
    获取转写文本分层配置（从 settings.json） / Get transcript layering config.

    详见转写文本分层设计文档。

    返回格式 / Returns:
      {
        "cleanup": {"enabled": True},        # 口语清理（本地规则），默认开；显式 false 为逃生通道
        "formal":  {"auto_generate": False}  # 会后自动生成 AI 书面版，默认关
      }
    """
    settings = load_settings()
    tr = settings.get("transcript", {}) or {}
    cleanup = tr.get("cleanup", {}) or {}
    formal = tr.get("formal", {}) or {}
    return {
        "cleanup": {
            "enabled": bool(cleanup.get("enabled", True)),
        },
        "formal": {
            "auto_generate": bool(formal.get("auto_generate", False)),
        },
    }


# ============================================================
# 逐能力算力来源（唯一真相源）/ Per-capability compute source (single source of truth)
# ============================================================
# 不再有全局 access_mode 决策层：ASR 与 LLM 各自独立选择算力来源，互不联动。
#   capability_source.{llm,asr}  逐能力生效来源；"" = 未设置（触发逐能力引导）。
# 旧字段（engine.mode / asr.mode）仅作回滚兼容投影，不参与路由判定（见 core/routing.py）。

# 逐能力合法来源枚举（用户词；工程值 proxy/direct 仅专家注释层出现）
LLM_CAP_SOURCES = ("trial", "byok", "local_endpoint")
ASR_CAP_SOURCES = ("trial", "byok", "local")


def _llm_base_is_localhost(settings: dict) -> bool:
    """LLM base_url 指向本机端点（以 URL 为准，不读 provider 字面量）。"""
    try:
        from core.llm import is_localhost_base_url
        return is_localhost_base_url(((settings.get("llm") or {}).get("base_url")) or "")
    except Exception:
        return False

# expert_mode 自动开启判定所用的「默认值」口径（与 get_llm_config / get_asr_config 默认一致）
_DEFAULT_EXPERT_BASELINES = {
    "llm": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    "asr": {"base_url": "https://dashscope.aliyuncs.com", "model": "paraformer-v2"},
}


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
    # 非默认 Key 组合：旧版 flat api_key、以及代理模式下不应出现的自有 ASR Key
    # （声纹云配置分支已随 REQ-SETTINGS-IA 第 4 刀下架：voiceprint 字段不再存在于 schema）
    if settings.get("api_key"):
        return True
    asr_cfg = settings.get("asr", {}) or {}
    if asr_cfg.get("mode") != "direct" and asr_cfg.get("api_key"):
        return True
    return False


def ensure_percap_migrated(settings: dict) -> bool:
    """就地执行一次性逐能力迁移：把存量 access_mode 映射为 capability_source，
    并移除 access_mode / capability_source_override 字段。幂等（_percap_migrated 标记）。

    | 存量 access_mode | 迁移结果 capability_source |
    | local            | asr=local；llm=local_endpoint(本机 base_url) 否则 byok |
    | cloud/hosted     | 沿用已存值，缺项补 trial |
    | byok             | 沿用已存值，缺项补 byok（llm 本机端点识别） |
    | null / 缺失      | 保留已存显式值，否则 ""（触发逐能力引导） |
    返回是否发生变更。
    """
    if settings.get("_percap_migrated"):
        return False

    legacy = settings.get("access_mode")
    cur = dict(settings.get("capability_source", {}) or {})

    if legacy == "local":
        llm = "local_endpoint" if _llm_base_is_localhost(settings) else (cur.get("llm") or "byok")
        cur = {"llm": llm, "asr": cur.get("asr") or "local"}
    elif legacy in ("cloud", "hosted"):
        cur = {"llm": cur.get("llm") or ("local_endpoint" if _llm_base_is_localhost(settings) else "trial"),
               "asr": cur.get("asr") or "trial"}
    elif legacy == "byok":
        cur = {"llm": cur.get("llm") or ("local_endpoint" if _llm_base_is_localhost(settings) else "byok"),
               "asr": cur.get("asr") or "byok"}
    else:
        cur = {"llm": cur.get("llm", ""), "asr": cur.get("asr", "")}

    settings["capability_source"] = cur
    settings.pop("access_mode", None)
    settings.pop("capability_source_override", None)
    if not isinstance(settings.get("expert_mode"), bool):
        settings["expert_mode"] = derive_expert_mode(settings)
    settings["_percap_migrated"] = True
    _project_capability_legacy(settings)
    return True


def run_percap_migration() -> bool:
    """启动时迁移入口：加载 settings.json，如需逐能力迁移则持久化。返回是否发生变更。"""
    settings = load_settings()
    changed = ensure_percap_migrated(settings)
    # 第 4 刀：声纹云端路径下架，存量 voiceprint 字段随保存一次性丢弃
    if "voiceprint" in settings:
        settings.pop("voiceprint", None)
        changed = True
    if changed:
        save_settings_to_disk(settings)
        logger.info(f"逐能力迁移完成: capability_source={settings.get('capability_source')}, expert_mode={settings.get('expert_mode')}")
        return True
    return False


def _project_capability_legacy(settings: dict) -> None:
    """回滚兼容投影：按逐能力来源写旧字段 engine.mode / asr.mode（不参与路由判定）。"""
    sources = settings.get("capability_source", {}) or {}
    engine = dict(settings.get("engine", {}) or {})
    asr = dict(settings.get("asr", {}) or {})
    llm_src = sources.get("llm") or ""
    if llm_src == "trial":
        engine["mode"] = "proxy"
    elif llm_src in ("byok", "local_endpoint"):
        engine["mode"] = "direct"
    asr_src = sources.get("asr") or ""
    if asr_src == "local":
        engine["mode"] = "local"
    elif asr_src == "trial":
        asr["mode"] = "proxy"
    elif asr_src == "byok":
        asr["mode"] = "direct"
    settings["engine"] = engine
    settings["asr"] = asr


def get_capability_status(prefer_subscription: bool | None = None) -> dict:
    """逐能力算力来源快照（详情层/路由共用，纯读不写盘）。

    真相源即 capability_source.{cap}（"" = 未设置）。为兼容既有前端类型，
    仍返回 {explicit, override, default, effective} 四键（均取显式值）。
    """
    settings = load_settings()
    sources = settings.get("capability_source", {}) or {}
    result: dict = {}
    for cap in ("llm", "asr"):
        eff = sources.get(cap) or ""
        result[cap] = {"explicit": eff, "override": bool(eff), "default": eff, "effective": eff}
    return result


def get_expert_mode() -> bool:
    """专家模式开关。已迁移 → 持久值优先；未迁移 → 按存量配置惰性推导。"""
    settings = load_settings()
    if settings.get("_access_mode_migrated"):
        em = settings.get("expert_mode")
        return bool(em) if isinstance(em, bool) else derive_expert_mode(settings)
    return derive_expert_mode(settings)


# ============================================================
# 自动改用同意开关（逐能力，默认关闭）/ Auto-fallback consent (per capability, default off)
# ============================================================
# 用户显式选择一个来源后，该来源不可用时是否允许自动改用其他已配置来源。
# 默认 False：不替用户做主（尤其不静默切到用户的付费 Key）；
# 关闭时 routing 保持原来源并明示不可用原因，由用户手动切换或开启开关。


def get_auto_fallback(settings: dict | None = None) -> dict:
    """读取逐能力自动改用同意：{llm: bool, asr: bool}，缺省均为 False（纯读不写盘）。"""
    s = settings if settings is not None else load_settings()
    cur = s.get("auto_fallback", {}) or {}
    if not isinstance(cur, dict):
        cur = {}
    return {"llm": bool(cur.get("llm", False)), "asr": bool(cur.get("asr", False))}


def apply_auto_fallback(settings: dict, vals: dict) -> None:
    """内存中合并自动改用开关（供 /api/settings 先合后落）。非布尔值忽略。"""
    if not isinstance(vals, dict):
        raise ValueError("auto_fallback 必须是 dict")
    cur = dict(settings.get("auto_fallback", {}) or {})
    for cap in ("llm", "asr"):
        if cap in vals and isinstance(vals[cap], bool):
            cur[cap] = vals[cap]
    settings["auto_fallback"] = {"llm": bool(cur.get("llm", False)), "asr": bool(cur.get("asr", False))}


def apply_capability_source(settings: dict, sources: dict) -> None:
    """内存中逐能力写入算力来源（供事务端点先算后落）。非法值抛 ValueError，"" 允许。"""
    if not isinstance(sources, dict):
        raise ValueError("capability_source 必须是 dict")
    cur = dict(settings.get("capability_source", {}) or {})
    for cap, allowed in (("llm", LLM_CAP_SOURCES), ("asr", ASR_CAP_SOURCES)):
        if cap in sources:
            val = sources.get(cap)
            if val is None:
                val = ""
            if val != "" and val not in allowed:
                raise ValueError(f"非法 capability_source.{cap}: {val!r}，允许 {allowed}")
            cur[cap] = val
    settings["capability_source"] = {"llm": cur.get("llm", ""), "asr": cur.get("asr", "")}
    settings["_percap_migrated"] = True
    _project_capability_legacy(settings)


def set_capability_source(sources: dict) -> dict:
    """持久化逐能力来源（无引擎副作用的普通写入）。返回更新后的 capability_source。"""
    settings = load_settings()
    apply_capability_source(settings, sources)
    save_settings_to_disk(settings)
    return settings["capability_source"]


def set_expert_mode(enabled: bool) -> None:
    """持久化 expert_mode 开关。首次写入时顺带完成迁移，避免惰性推导覆盖显式选择。"""
    settings = load_settings()
    ensure_percap_migrated(settings)
    settings["expert_mode"] = bool(enabled)
    save_settings_to_disk(settings)
