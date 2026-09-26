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
# 接入方式（REQ-SETTINGS-IA §3.1/§4 · 决策层收敛）/ Access mode v2
# ============================================================
# 用户侧决策层唯一字段：access_mode ∈ {local(离线), cloud(联网)} | None（未选态→触发引导）。
# 体验/自带随账户降为逐能力算力来源（第 5 刀）：
#   capability_source           当前选择值（迁移/切网时初始化，之后仅用户显式改选变动）
#   capability_source_override  true = 用户逐能力显式覆盖过，持久化生效，
#                               不被下次登录/账户勾选改回（AC-5）
# 生效值 = override ? capability_source : 账户默认（prefer_subscription 开=trial / 关=byok）。
# 旧字段（engine.mode / asr.mode）降级为 A2 投影：写路径继续同步以保持回滚能力，
# 但不再作为路由输入（路由唯一输入 = access_mode + 逐能力生效来源，见 core/routing.py）。

ACCESS_MODES = ("local", "cloud")
# 存量枚举（已废止：仅兼容读取/迁移输入，不再是合法写入值）
LEGACY_ACCESS_MODES = ("hosted", "byok")

# 能力级算力来源（裁决-4 五词中的三项用户词；工程值 proxy/direct 仅专家注释层出现）
LLM_CAP_SOURCES = ("trial", "byok", "local_endpoint")
ASR_CAP_SOURCES = ("trial", "byok")


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


def account_default_source(prefer_subscription: bool | None = None) -> str:
    """账户「优先使用体验配额」勾选 = 详情默认值来源（第 5 刀）：开→trial，关→byok。"""
    ps = _current_prefer_subscription() if prefer_subscription is None else bool(prefer_subscription)
    return "trial" if ps else "byok"


def _capability_defaults(source_seed: str | None = None, llm_localhost: bool = False) -> dict:
    """按种子来源生成两能力初始选择值（trial/byok 直映；llm 本机端点单独识别）。"""
    if source_seed == "trial":
        return {"llm": "trial", "asr": "trial"}
    if source_seed == "byok":
        return {"llm": "local_endpoint" if llm_localhost else "byok", "asr": "byok"}
    return {"llm": "", "asr": ""}


def derive_access_mode(settings: dict, prefer_subscription: bool | None = None) -> str | None:
    """旧客户端兼容窗口的反向投影（纯函数，不落盘；REQ-SETTINGS-IA §3.2 日落中）。

    新口径：决策层只剩两值，任何云端传输（local 除外）一律投影为 cloud（联网）；
    A1 裁决（direct+订阅开=托管）已废止——计费来源不再参与模式推导，
    prefer_subscription 参数保留仅为签名兼容，不再影响结论。

    | engine.mode=local                 | local |
    | engine.mode=proxy / cloud / direct | cloud |
    | 未配置                             | None  | → 触发引导
    """
    engine = settings.get("engine", {}) or {}
    mode = engine.get("mode")
    if mode == "local":
        return "local"
    if mode in ("proxy", "cloud", "direct"):
        return "cloud"
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
    # 非默认 Key 组合：旧版 flat api_key、以及代理模式下不应出现的自有 ASR Key
    # （声纹云配置分支已随 REQ-SETTINGS-IA 第 4 刀下架：voiceprint 字段不再存在于 schema）
    if settings.get("api_key"):
        return True
    asr_cfg = settings.get("asr", {}) or {}
    if asr_cfg.get("mode") != "direct" and asr_cfg.get("api_key"):
        return True
    return False


def migrate_access_mode(settings: dict, prefer_subscription: bool | None = None) -> bool:
    """就地执行一次性迁移（REQ-SETTINGS-IA §4）：存量三值收敛为两值 + 逐能力来源初始化。

    | 存量 access_mode | 迁移为 | 能力来源初始化 | A2 投影不变量 |
    | local            | local  | —（本机接管）      | engine.mode=local |
    | hosted           | cloud  | LLM/ASR=trial      | engine.mode=proxy |
    | byok             | cloud  | LLM/ASR=byok（llm 本机端点识别） | engine.mode=direct |
    | null / 未配置    | null   | 触发引导         | 不动旧字段 |

    混配存量（如 hosted + asr.mode=direct）按详情层逐能力读实际值并标 override，
    冲突明示不静默（§4）；A1 裁决已废止。
    已迁移（`_settings_ia_migrated` 标记）则不重复推导，返回 False。
    """
    if settings.get("_settings_ia_migrated"):
        return False

    legacy = settings.get("access_mode")
    if legacy is None and "access_mode" not in settings:
        legacy = derive_access_mode(settings, prefer_subscription)

    # 存量三值/旧字段投影 → 新两值 + 能力种子（trial/byok）
    seed: str | None = None
    if legacy == "local":
        seed = None
    elif legacy in ("hosted", "byok"):
        seed = "trial" if legacy == "hosted" else "byok"
    elif legacy == "cloud":
        # 已是新值（带 v1 标记的过渡态）：按旧字段反推种子
        seed = "trial" if (settings.get("engine", {}) or {}).get("mode") in ("proxy", "cloud") else "byok"
    settings["access_mode"] = "local" if legacy == "local" else ("cloud" if legacy else None)

    if settings["access_mode"] == "cloud":
        llm_localhost = seed == "byok" and _llm_base_is_localhost(settings)
        sources = _capability_defaults(seed, llm_localhost=llm_localhost)
        overrides = {"llm": False, "asr": False}
        # 混配存量：逐能力读实际值，与顶层种子分歧的能力显式标注（不静默）
        asr_mode = (settings.get("asr", {}) or {}).get("mode")
        if asr_mode == "direct" and sources["asr"] == "trial":
            sources["asr"] = "byok"
            overrides["asr"] = True
        elif asr_mode == "proxy" and sources["asr"] == "byok":
            sources["asr"] = "trial"
            overrides["asr"] = True
        settings["capability_source"] = sources
        settings["capability_source_override"] = overrides
    else:
        settings.setdefault("capability_source", {"llm": "", "asr": ""})
        settings.setdefault("capability_source_override", {"llm": False, "asr": False})

    if not isinstance(settings.get("expert_mode"), bool):
        settings["expert_mode"] = derive_expert_mode(settings)
    settings["_access_mode_migrated"] = True  # v1 标记保留（回滚兼容）
    settings["_settings_ia_migrated"] = True
    return True


def run_access_mode_migration() -> bool:
    """启动时迁移入口：加载 settings.json，如需迁移则持久化。返回是否发生变更。"""
    settings = load_settings()
    changed = migrate_access_mode(settings)
    # 第 4 刀：声纹云端路径下架，存量 voiceprint 字段随保存一次性丢弃（注册表无需迁移，
    # cam++-v1-cloud 标记特征与本机 cam++-v1 在 COMPATIBLE_VERSIONS 互兼容，见 ADR-0009）
    if "voiceprint" in settings:
        settings.pop("voiceprint", None)
        changed = True
    if changed:
        save_settings_to_disk(settings)
        logger.info(f"接入方式迁移完成: access_mode={settings.get('access_mode')}, expert_mode={settings.get('expert_mode')}, capability_source={settings.get('capability_source')}")
        return True
    return False


def _project_legacy_fields(settings: dict, mode: str | None, sources: dict) -> None:
    """A2 兼容窗口：将新模型投影到旧字段（仅供回滚后的旧版本读取，不参与路由判定）。"""
    if mode is None:
        return
    engine = dict(settings.get("engine", {}) or {})
    asr = dict(settings.get("asr", {}) or {})
    if mode == "local":
        engine["mode"] = "local"
    else:  # cloud：按生效来源投影传输层旧值
        llm_src = sources.get("llm") or ""
        if llm_src == "trial":
            engine["mode"] = "proxy"
        elif llm_src in ("byok", "local_endpoint"):
            engine["mode"] = "direct"
        asr_src = sources.get("asr") or ""
        if asr_src == "trial":
            asr["mode"] = "proxy"
        elif asr_src == "byok":
            asr["mode"] = "direct"
    settings["engine"] = engine
    settings["asr"] = asr


def get_access_mode() -> str | None:
    """当前接入方式（路由判定唯一数据源，见 core/routing.py）。

    已迁移 → 返回持久值（可能为 None=未选态，触发引导）；
    存量遗留值（hosted/byok）→ 防御性投影为 cloud，不写盘；
    未迁移（如 CLI 先于服务启动钩子读取）→ 惰性推导，不写盘。
    """
    settings = load_settings()
    if settings.get("_settings_ia_migrated") or settings.get("_access_mode_migrated"):
        mode = settings.get("access_mode")
        if mode in LEGACY_ACCESS_MODES:
            return "cloud"
        return mode if mode in ACCESS_MODES else None
    return derive_access_mode(settings)


def get_capability_status(prefer_subscription: bool | None = None) -> dict:
    """逐能力算力来源快照（详情层/路由共用，纯读不写盘）。

    返回 / Returns:
      {"llm": {explicit, override, default, effective},
       "asr": {...},
       "account_default": "trial"|"byok"}
    离线态（access_mode=local）下 effective 统一为 "local"（本机接管）。
    """
    settings = load_settings()
    default = account_default_source(prefer_subscription)
    access = get_access_mode()
    sources = settings.get("capability_source", {}) or {}
    overrides = settings.get("capability_source_override", {}) or {}
    result: dict = {"account_default": default}
    for cap in ("llm", "asr"):
        explicit = sources.get(cap) or ""
        overridden = bool(overrides.get(cap, False))
        if access == "local":
            # 离线态：本机接管（只读），勾选不参与生效值
            effective = "local"
        elif overridden and explicit:
            # 已覆盖：持久化显式值，不被登录/勾选改回（AC-5）
            effective = explicit
        else:
            # 未覆盖：跟随账户默认（勾选联动的显式默认生效值）
            effective = default
        result[cap] = {
            "explicit": explicit,
            "override": overridden,
            "default": default,
            "effective": effective,
        }
    return result


def get_expert_mode() -> bool:
    """专家模式开关。已迁移 → 持久值优先；未迁移 → 按存量配置惰性推导。"""
    settings = load_settings()
    if settings.get("_access_mode_migrated"):
        em = settings.get("expert_mode")
        return bool(em) if isinstance(em, bool) else derive_expert_mode(settings)
    return derive_expert_mode(settings)


def apply_access_mode(
    settings: dict,
    mode: str | None,
    sources: dict | None = None,
    overrides: dict | None = None,
    prefer_subscription: bool | None = None,
) -> None:
    """写入 access_mode（+ 逐能力来源）并同步 A2 投影旧字段。

    mode=None 表示未选态（触发引导），仅清除选择不影响旧字段。
    存量枚举（hosted/byok）作为旧客户端兼容输入归一化为 cloud + 对应来源，
    不报错不静默（投影后的模式 + 默认来源与旧语义等价）。
    sources 仅接受合法枚举；未传时切联网按账户默认初始化（override=False）。
    """
    if mode in LEGACY_ACCESS_MODES:
        settings["access_mode"] = "cloud"
        seed = "trial" if mode == "hosted" else "byok"
        settings["capability_source"] = _capability_defaults(seed, llm_localhost=(mode == "byok" and _llm_base_is_localhost(settings)))
        settings["capability_source_override"] = {"llm": False, "asr": False}
    else:
        if mode is not None and mode not in ACCESS_MODES:
            raise ValueError(f"非法 access_mode: {mode!r}，允许值: {ACCESS_MODES}")
        settings["access_mode"] = mode
    settings["_access_mode_migrated"] = True
    settings["_settings_ia_migrated"] = True

    if mode == "cloud" or (mode is None and settings.get("access_mode") == "cloud"):
        default = account_default_source(prefer_subscription)
        cur = dict(settings.get("capability_source", {}) or {})
        cur_ovr = dict(settings.get("capability_source_override", {}) or {"llm": False, "asr": False})
        if sources:
            for cap, allowed in (("llm", LLM_CAP_SOURCES), ("asr", ASR_CAP_SOURCES)):
                if cap in sources:
                    val = sources.get(cap)
                    if val in allowed:
                        cur[cap] = val
                        # 任何手动改选都视为显式覆盖（持久化，不被勾选改回）
                        cur_ovr[cap] = bool((overrides or {}).get(cap, True))
                    elif val is None or val == "":
                        cur[cap] = ""
                        cur_ovr[cap] = False
        settings["capability_source"] = {"llm": cur.get("llm", ""), "asr": cur.get("asr", "")}
        # 联网态下未初始化的能力补账户默认（显式联动，非静默 override）
        if not settings["capability_source"]["llm"]:
            settings["capability_source"]["llm"] = default
        if not settings["capability_source"]["asr"]:
            settings["capability_source"]["asr"] = default
        settings["capability_source_override"] = {"llm": bool(cur_ovr.get("llm", False)), "asr": bool(cur_ovr.get("asr", False))}
    elif mode is None:
        return

    _project_legacy_fields(settings, settings.get("access_mode"), settings.get("capability_source", {}) or {})


def set_access_mode(
    mode: str | None,
    sources: dict | None = None,
    overrides: dict | None = None,
    prefer_subscription: bool | None = None,
) -> None:
    """持久化 access_mode（含逐能力来源与旧字段投影）。非法值抛 ValueError，不落盘。"""
    settings = load_settings()
    apply_access_mode(settings, mode, sources=sources, overrides=overrides,
                      prefer_subscription=prefer_subscription)
    save_settings_to_disk(settings)


def set_expert_mode(enabled: bool) -> None:
    """持久化 expert_mode 开关。首次写入时顺带完成迁移，避免惰性推导覆盖显式选择。"""
    settings = load_settings()
    migrate_access_mode(settings)
    settings["expert_mode"] = bool(enabled)
    save_settings_to_disk(settings)
