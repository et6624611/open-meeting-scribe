"""
app/routers/settings.py — 设置读写、API 连接测试、CLI 参考与系统提示词查看 / Settings read/write, API connection test, CLI reference & system prompt viewer

设置格式（v3 双服务版）：
{
  "asr": {
    "provider": "DashScope",
    "base_url": "https://dashscope.aliyuncs.com",
    "api_key": "sk-...",
    "model": "paraformer-v2"
  },
  "llm": {
    "provider": "DashScope",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "sk-...",
    "model": "qwen-plus"
  },
  "output_dir": "data/output/"
}

ASR 与 LLM 使用独立的 API Key，互不干扰 / ASR and LLM use independent API Keys.
API Key 在 GET 响应中脱敏返回（sk-****xxxx），仅在 POST 保存时接收明文 / API Key masked in GET responses; plaintext only in POST saves.
"""

import logging
import os
import time
from copy import deepcopy
from pathlib import Path

import requests
from fastapi import APIRouter

from app.routers.chat import CHAT_SYSTEM_PROMPT
from app.settings_store import (
    ASR_CAP_SOURCES,
    LLM_CAP_SOURCES,
    apply_capability_source,
    ensure_percap_migrated,
    get_capability_status,
    get_expert_mode,
)
from app.store import (
    get_active_api_key,
    get_asr_config,
    get_chat_engine_config,
    get_engine_config,
    get_feature_flags,
    get_llm_config,
    get_storage_config,
    get_transcript_config,
    load_settings,
    mask_api_key,
    save_settings_to_disk,
)
from core.i18n import _
from core.llm import is_localhost_base_url
from core.realtime_summary import SUMMARY_SYSTEM_PROMPT
from core.summarize import SYSTEM_PROMPT, TITLE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])

# 常用 Provider 预设（前端下拉用） / Common provider presets (for frontend dropdown)
PROVIDER_PRESETS = [
    {
        "name": "DashScope（通义千问）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
    },
    {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    },
    {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    {
        "name": "Moonshot（月之暗面）",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    },
    {
        "name": "零一万物",
        "base_url": "https://api.lingyiwanwu.com/v1",
        "models": ["yi-large", "yi-medium", "yi-spark"],
    },
    {
        # R4（WP-A）：本地自持端点，Key 可留空 / Local self-hosted endpoint; key optional
        "name": "Ollama（本地）",
        "base_url": "http://localhost:11434/v1",
        "models": ["qwen3:8b", "qwen3:14b", "llama3.1:8b"],
        "key_optional": True,
        "localhost": True,
    },
    {
        # R4（WP-A）：本地自持端点，Key 可留空 / Local self-hosted endpoint; key optional
        "name": "LM Studio（本地）",
        "base_url": "http://localhost:1234/v1",
        "models": [],
        "key_optional": True,
        "localhost": True,
    },
    {
        "name": "自定义",
        "base_url": "",
        "models": [],
    },
]

# ASR Provider 预设（语音转写服务） / ASR provider presets (speech transcription)
# 当前仅支持 DashScope（Paraformer），保留扩展结构 / Currently DashScope only (Paraformer); extensible structure retained
ASR_PROVIDER_PRESETS = [
    {
        "name": "DashScope（通义实验室）",
        "base_url": "https://dashscope.aliyuncs.com",
        "models": ["paraformer-v2"],
    },
]


@router.get("/api/settings")
def get_settings():
    """
    获取当前设置 / Get current settings.

    返回 ASR（语音转写）和 LLM（纪要生成）两套独立配置 / Return separate ASR (transcription) and LLM (summary) configs.
    API Key 脱敏返回：仅显示前 3 位和后 4 位 / API Key masked: show only first 3 and last 4 chars.
    """
    settings = load_settings()
    llm = get_llm_config()
    asr = get_asr_config()
    feature_flags = get_feature_flags()

    # 声纹偏好：根据用户订阅状态决定 / Voiceprint preference: based on user subscription status
    from core.users import get_current_user, should_use_local_diarization
    current_user = get_current_user()
    if current_user:
        subscription = current_user.get("subscription", {"tier": "free"})
        prefs = current_user.get("prefs", {})
        tier = subscription.get("tier", "free")
        local_pref = prefs.get("local_diarization", False)
        use_local = should_use_local_diarization()
        prefer_subscription = prefs.get("prefer_subscription", False)
    else:
        tier = "free"
        local_pref = False
        use_local = True
        prefer_subscription = False

    asr_mode = asr.get("mode", "proxy")
    asr_response = {
        "mode": asr_mode,
        "provider": asr["provider"],
        "model": asr["model"],
    }
    if asr_mode == "direct":
        asr_response["base_url"] = asr.get("base_url", "")
        asr_response["api_key"] = mask_api_key(asr.get("api_key", ""))
        asr_response["api_key_set"] = bool(asr.get("api_key", ""))
        asr_response["api_key_managed_by_proxy"] = False
    else:
        asr_response["proxy_url"] = asr.get("proxy_url", "")
        asr_response["api_key_managed_by_proxy"] = True

    return {
        "asr": asr_response,
        "llm": {
            "provider": llm["provider"],
            "base_url": llm["base_url"],
            "api_key": mask_api_key(llm["api_key"]),
            "api_key_set": bool(llm["api_key"]),
            "model": llm["model"],
        },
        # 声纹配置面已随 REQ-SETTINGS-IA 第 4 刀下架（字段在 schema/UI/后端三处不存在）；
        # 声纹仅本机 CAM++，说话人分离行为由 diarization 块只读回显。
        "diarization": {
            "subscription_tier": tier,
            "local_diarization": local_pref,
            "effective": "local" if use_local else "cloud",
            "can_toggle": tier != "free",
        },
        "prefer_subscription": prefer_subscription,
        "expert_mode": get_expert_mode(),
        # 逐能力算力来源快照（详情层三态徽章/联动的数据源）
        "capability": get_capability_status(prefer_subscription),
        "output_dir": settings.get("output_dir", "data/output/"),
        "engine": get_engine_config(),
        "feature_flags": feature_flags,
        # 转写文本分层配置（清理版/书面版开关，前端会中/会后分层视图的数据源）
        "transcript": get_transcript_config(),
        "storage": get_storage_config(),
        "disabled_commands": settings.get("disabled_commands", []),
        "active_agent": settings.get("active_agent", "meeting-minutes"),
        "chat_engine": get_chat_engine_config(),
        "asr_provider_presets": ASR_PROVIDER_PRESETS,
        "llm_provider_presets": PROVIDER_PRESETS,
    }


_VALID_ENGINE_MODES = ("cloud", "proxy", "direct", "local")
_VALID_MODEL_TIERS = ("auto", "conservative", "standard")


def _coerce_int(value, lo: int, hi: int, default: int = 0) -> int:
    """将任意输入安全钳制为 [lo, hi] 整数（防脏配置写入 settings.json）。"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _merge_engine_config(incoming: dict | None, existing_engine: dict, existing_local: dict) -> dict:
    """合并计算引擎配置（R4/R5，PRD §9），带白名单校验 / Merge engine config with whitelist validation.

    非法 mode / model_tier 值回退到既有值或默认值，防止脏配置写入 settings.json。
    model_dir 默认值平台感知（D-G3 (a)）：冻结态不再持久化相对路径（B-2）。
    """
    from app.settings_store import default_model_dir

    incoming = incoming or {}
    incoming_local = incoming.get("local", {}) or {}

    mode = incoming.get("mode", existing_engine.get("mode", "cloud"))
    if mode not in _VALID_ENGINE_MODES:
        mode = existing_engine.get("mode", "cloud")

    model_dir = incoming_local.get("model_dir", existing_local.get("model_dir", ""))
    if not isinstance(model_dir, str) or not model_dir.strip():
        model_dir = existing_local.get("model_dir") or default_model_dir()

    model_tier = incoming_local.get("model_tier", existing_local.get("model_tier", "auto"))
    if model_tier not in _VALID_MODEL_TIERS:
        model_tier = existing_local.get("model_tier", "auto")

    # 引擎组件目录显式覆盖（D-G1 搜索序②；空串=自动定位，非法类型回退空）
    engine_dir = incoming_local.get("engine_dir", existing_local.get("engine_dir", ""))
    if not isinstance(engine_dir, str):
        engine_dir = ""

    # 引擎组件包下载 URL 覆盖（政企内网源；空串=默认 GitHub Release 约定，G-4b）
    component_url = incoming_local.get("component_url", existing_local.get("component_url", ""))
    if not isinstance(component_url, str):
        component_url = ""

    return {
        "mode": mode,
        "local": {
            "model_dir": model_dir,
            "model_tier": model_tier,
            "engine_dir": engine_dir.strip(),
            "component_url": component_url.strip(),
        },
    }


@router.post("/api/settings")
def save_settings(data: dict):
    """
    保存设置 / Save settings.

    同时处理 ASR（语音转写）和 LLM（纪要生成）两套配置 / Handle both ASR and LLM configs.
    前端传入的 api_key 若是脱敏值（含 ****）或空值，则保留原 key 不变 / If incoming api_key is masked (contains ****) or empty, keep original key.
    """
    existing = load_settings()

    # ── 向后兼容：迁移旧版 flat 格式 / Backward compat: migrate legacy flat format ──
    if "api_key" in existing and "llm" not in existing:
        existing["llm"] = {
            "provider": "DashScope",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": existing["api_key"],
            "model": existing.get("model", "qwen-plus"),
        }
        existing.pop("api_key", None)
        existing.pop("model", None)

    existing_llm = existing.get("llm", {})
    existing_asr = existing.get("asr", {})
    existing_ff = existing.get("feature_flags", {})
    existing_engine = existing.get("engine", {}) or {}
    existing_engine_local = existing_engine.get("local", {}) or {}

    # ── LLM 配置 / LLM config ──
    new_llm = data.get("llm", {})
    incoming_llm_key = new_llm.get("api_key", "")
    # R4（WP-A）：localhost 自持端点允许空 Key —— 保存后的 base_url 若指向本机，
    # 且用户未显式提供 Key，则保持为空，不从云端环境变量回填 / Local endpoint tolerates empty key.
    final_llm_base_url = new_llm.get("base_url", existing_llm.get("base_url", ""))
    if not incoming_llm_key or "****" in incoming_llm_key:
        if is_localhost_base_url(final_llm_base_url):
            final_llm_key = existing_llm.get("api_key", "")
        else:
            final_llm_key = existing_llm.get("api_key") or get_active_api_key()
    else:
        final_llm_key = incoming_llm_key

    # ── ASR 配置（双模式：代理 / 直连） / ASR config (dual mode: proxy / direct) ──
    new_asr = data.get("asr", {})
    asr_mode = new_asr.get("mode", existing_asr.get("mode", "proxy"))

    if asr_mode == "direct":
        # 直连模式：保存 base_url 和 api_key / Direct mode: save base_url and api_key
        incoming_asr_key = new_asr.get("api_key", "")
        if not incoming_asr_key or "****" in incoming_asr_key:
            final_asr_key = existing_asr.get("api_key", "")
        else:
            final_asr_key = incoming_asr_key
        merged_asr = {
            "mode": "direct",
            "provider": new_asr.get("provider", existing_asr.get("provider", "DashScope")),
            "base_url": new_asr.get("base_url", existing_asr.get("base_url", "https://dashscope.aliyuncs.com")),
            "api_key": final_asr_key,
            "model": new_asr.get("model", existing_asr.get("model", "paraformer-v2")),
        }
    else:
        # 代理模式：不回显但不删除 base_url 和 api_key / Proxy mode: hide, don't erase credentials.
        # api_key 与 mode 正交：GET 脱敏≠落盘丢弃——否则任何一次代理模式保存
        # （含来源选择器的 capability_source 显式保存）都会静默擦除已存 BYOK Key。
        merged_asr = {
            "mode": "proxy",
            "provider": new_asr.get("provider", existing_asr.get("provider", "DashScope")),
            "model": new_asr.get("model", existing_asr.get("model", "paraformer-v2")),
            "api_key": existing_asr.get("api_key", ""),
        }

    # ── 声纹配置已整体下架（REQ-SETTINGS-IA 第 4 刀）：POST 不再接收 voiceprint 字段，
    #    存量键在保存时一并丢弃（注册表特征经 COMPATIBLE_VERSIONS 继续可匹配，无用户数据迁移）

    merged = {
        **existing,
        "asr": merged_asr,
        "llm": {
            "provider": new_llm.get("provider", existing_llm.get("provider", "DashScope")),
            "base_url": new_llm.get("base_url", existing_llm.get("base_url", "")),
            "api_key": final_llm_key,
            "model": new_llm.get("model", existing_llm.get("model", "qwen-plus")),
        },
        "engine": _merge_engine_config(data.get("engine"), existing_engine, existing_engine_local),
        "output_dir": data.get("output_dir", existing.get("output_dir", "data/output/")),
        "feature_flags": {
            "realtime_chapters": data.get("feature_flags", {}).get("realtime_chapters", existing_ff.get("realtime_chapters", True)),
            "realtime_summary": data.get("feature_flags", {}).get("realtime_summary", existing_ff.get("realtime_summary", True)),
            "realtime_summary_interval": data.get("feature_flags", {}).get("realtime_summary_interval", existing_ff.get("realtime_summary_interval", 60)),
            "update_check": data.get("feature_flags", {}).get("update_check", existing_ff.get("update_check", True)),
            "voiceprint_auto_match": data.get("feature_flags", {}).get("voiceprint_auto_match", existing_ff.get("voiceprint_auto_match", False)),
            # 默认开、显式 false 为逃生通道（与 get_feature_flags 口径一致）
            "voiceprint_v2": data.get("feature_flags", {}).get("voiceprint_v2", existing_ff.get("voiceprint_v2", True)),
            "chrome_autohide": data.get("feature_flags", {}).get("chrome_autohide", existing_ff.get("chrome_autohide", True)),
        },
        "disabled_commands": data.get("disabled_commands", existing.get("disabled_commands", [])),
        "active_agent": data.get("active_agent", existing.get("active_agent", "meeting-minutes")),
        "storage": {
            "auto_clean_intermediate": data.get("storage", {}).get("auto_clean_intermediate", existing.get("storage", {}).get("auto_clean_intermediate", True)),
            "auto_archive_days": data.get("storage", {}).get("auto_archive_days", existing.get("storage", {}).get("auto_archive_days", 0)),
        },
    }

    # ── 逐能力算力来源（唯一真相源）/ Per-capability compute source handling ──
    # capability_source.{llm,asr} 由「API 配置 / ASR 配置」逐能力写入；非法值拒绝。
    # engine/asr.mode 仅作回滚兼容投影，由 apply_capability_source 同步；不再参与路由判定。
    merged.pop("voiceprint", None)  # 存量声纹配置键随任何一次保存丢弃

    if isinstance(data.get("expert_mode"), bool):
        merged["expert_mode"] = data["expert_mode"]

    # ── 转写文本分层配置（清理版默认开 / 书面版默认关，显式 false 为逃生通道） ──
    incoming_tr = data.get("transcript")
    if isinstance(incoming_tr, dict):
        existing_tr = existing.get("transcript", {}) or {}
        merged["transcript"] = {
            "cleanup": {
                "enabled": bool((incoming_tr.get("cleanup") or {}).get(
                    "enabled", (existing_tr.get("cleanup") or {}).get("enabled", True))),
            },
            "formal": {
                "auto_generate": bool((incoming_tr.get("formal") or {}).get(
                    "auto_generate", (existing_tr.get("formal") or {}).get("auto_generate", False))),
            },
        }

    if isinstance(data.get("capability_source"), dict):
        try:
            apply_capability_source(merged, data["capability_source"])
        except ValueError as e:
            logger.warning(f"忽略非法 capability_source: {e}")
    elif not merged.get("_percap_migrated"):
        ensure_percap_migrated(merged)

    # ── 智能体模式引擎（正交于 access_mode，方案 D1）/ Agent-mode chat engine ──
    # 仅白名单校验后写入 chat_engine 命名空间；缺省保留既有值，绝不触碰 LLM/ASR Key。
    # engine_id 白名单动态取自 manifests/ 目录（多 CLI 适配：新增清单即可选，无需改代码）。
    incoming_ce = data.get("chat_engine")
    if isinstance(incoming_ce, dict):
        existing_ce = existing.get("chat_engine", {}) or {}
        tier = incoming_ce.get("auth_tier", existing_ce.get("auth_tier", "readonly"))
        if tier not in ("readonly", "workspace_write", "full_task"):
            tier = "readonly"
        from core.cli_engine.manifest import available_engines
        engine_ids = available_engines()
        engine_id = incoming_ce.get("engine_id", existing_ce.get("engine_id", "qoder-cli"))
        if engine_id not in engine_ids:
            logger.warning(f"忽略非法 chat_engine.engine_id: {engine_id!r}（可用 {engine_ids}）")
            engine_id = existing_ce.get("engine_id") if existing_ce.get("engine_id") in engine_ids else (
                "qoder-cli" if "qoder-cli" in engine_ids else (engine_ids[0] if engine_ids else "qoder-cli"))
        merged["chat_engine"] = {
            "enabled": bool(incoming_ce.get("enabled", existing_ce.get("enabled", False))),
            "engine_id": engine_id,
            "model": incoming_ce.get("model", existing_ce.get("model")) or None,
            "auth_tier": tier,
            # 模式即权限（PROPOSAL-AGENT-REWRITE-CHANNEL §5.1）：携带 auth_tier 的保存视为用户显式声明，
            # 此后该档位从"选择"变为"降级/覆盖"语义；未显式声明过时按模式派生默认（agent→workspace_write）。
            "_auth_tier_explicit": bool(incoming_ce.get("auth_tier") is not None
                                        or existing_ce.get("_auth_tier_explicit", False)),
            "session_persistence": bool(incoming_ce.get("session_persistence",
                                                       existing_ce.get("session_persistence", True))),
            "retention_days": _coerce_int(incoming_ce.get("retention_days",
                                    existing_ce.get("retention_days", 7)), lo=0, hi=3650),
            "cli_path_override": incoming_ce.get("cli_path_override",
                                                  existing_ce.get("cli_path_override")) or None,
        }

    save_settings_to_disk(merged)

    # 同步到环境变量（供未改造的旧模块使用） / Sync to env vars (for legacy modules)
    if final_llm_key:
        os.environ["DASHSCOPE_API_KEY"] = final_llm_key

    logger.info(
        f"设置已更新: "
        f"asr_provider={merged['asr']['provider']}, "
        f"llm_provider={merged['llm']['provider']}, model={merged['llm']['model']}, "
        f"access_mode={merged.get('access_mode')}"
    )

    asr_resp = {
        "mode": merged["asr"].get("mode", "proxy"),
        "provider": merged["asr"]["provider"],
        "model": merged["asr"]["model"],
    }
    if merged["asr"].get("mode") == "direct":
        asr_resp["base_url"] = merged["asr"].get("base_url", "")
        asr_resp["api_key"] = mask_api_key(merged["asr"].get("api_key", ""))
        asr_resp["api_key_set"] = bool(merged["asr"].get("api_key", ""))
        asr_resp["api_key_managed_by_proxy"] = False
    else:
        asr_resp["api_key_managed_by_proxy"] = True

    return {
        "ok": True,
        "asr": asr_resp,
        "llm": {
            "provider": merged["llm"]["provider"],
            "base_url": merged["llm"]["base_url"],
            "api_key": mask_api_key(final_llm_key),
            "api_key_set": bool(final_llm_key),
            "model": merged["llm"]["model"],
        },
        "capability": get_capability_status(),
    }


@router.post("/api/settings/capability")
def switch_capability_source(data: dict):
    """逐能力算力来源切换事务（失败全量回滚）。

    流程：内存合并新来源 → 进程动作（ASR 进入/离开 local 时启停本机引擎）→ 全部成功才落盘。
    任一环节失败（引擎启动/停止失败、模型缺失、非法参数）：settings.json 零写入，
    界面据 ok=false + failed_stage 明示「未生效，已保持原来源」。
    """
    sources = data.get("capability_source")
    if not isinstance(sources, dict):
        return {"ok": False, "failed_stage": "validate", "error": "缺少 capability_source"}
    for cap, allowed in (("llm", LLM_CAP_SOURCES), ("asr", ASR_CAP_SOURCES)):
        if cap in sources and sources[cap] is not None and sources[cap] != "" and sources[cap] not in allowed:
            return {"ok": False, "failed_stage": "validate",
                    "error": f"非法 capability_source.{cap}: {sources[cap]!r}"}

    existing = load_settings()
    merged = deepcopy(existing)
    try:
        apply_capability_source(merged, sources)
    except ValueError as e:
        return {"ok": False, "failed_stage": "validate", "error": str(e)}

    prev_asr = (existing.get("capability_source") or {}).get("asr") or ""
    target_asr = (merged.get("capability_source") or {}).get("asr") or ""

    # ── 进程动作阶段：ASR 进入 local 启动本机引擎；离开 local 且引擎在跑则停止（失败回滚） ──
    try:
        from core.engine_host import get_engine_host
        host = get_engine_host()
        if target_asr == "local" and prev_asr != "local":
            res = host.start()
            if not res.get("ok", False):
                logger.warning(f"[来源切换] 本机引擎启动失败，事务回滚: {res}")
                return {"ok": False, "failed_stage": "engine_start",
                        "error_code": res.get("error_code"),
                        "error": res.get("error") or "本机引擎启动失败"}
        elif prev_asr == "local" and target_asr != "local" and host.is_running():
            res = host.stop()
            if not res.get("ok", False):
                logger.warning(f"[来源切换] 本机引擎停止失败，事务回滚: {res}")
                return {"ok": False, "failed_stage": "engine_stop",
                        "error_code": res.get("error_code"),
                        "error": res.get("error") or "本机引擎停止失败"}
    except Exception as e:
        logger.warning(f"[来源切换] 引擎进程动作异常，事务回滚: {e}")
        return {"ok": False, "failed_stage": "engine", "error": str(e)[:200]}

    # ── 全部成功：一次性落盘 ──
    save_settings_to_disk(merged)
    logger.info(f"[来源切换] 成功: capability_source {existing.get('capability_source')!r} → {merged.get('capability_source')!r}")
    return {
        "ok": True,
        "capability": get_capability_status(),
        "llm": get_routing_decision_safe("llm"),
        "asr": get_routing_decision_safe("asr"),
    }


def get_routing_decision_safe(context: str) -> dict:
    """路由判定异常安全包装（切换事务响应使用）。"""
    from core.routing import get_routing_decision
    try:
        return get_routing_decision(context)
    except Exception as e:
        return {"expert_mode": False, "route": "",
                "source": "", "auto_switched": False, "route_override": False,
                "reason": f"routing_error:{e}", "unconfigured": False}


@router.get("/api/settings/chat-engine")
def get_chat_engine_status(engine: str | None = None):
    """
    智能体模式引擎状态与可用性探针（就地引导用，方案 R2/§3.9-2）.

    返回当前 chat_engine 配置 + 探针结论（installed/version/logged_in）
    + 全量引擎清单 engines（数据驱动：前端下拉不再硬编码，新增 manifest 即可选）。
    engine 参数为预览探针：仅对指定已注册引擎跑只读探针回显，不改变已保存配置
    （设置页切换引擎下拉即见失败段，不撞错才知道）。
    探针为同步 subprocess（--version/status 只读），适用于本同步端点。
    """
    import shutil

    from core.cli_engine import load_manifest, probe_engine
    from core.cli_engine.manifest import MANIFEST_DIR, available_engines

    cfg = get_chat_engine_config()
    probe_engine_id = cfg["engine_id"]
    if engine and engine in available_engines():
        probe_engine_id = engine

    def _engine_info(eid: str) -> dict:
        """引擎枚举项：只读 manifest 元信息 + 快速安装判断（不跑完整探针）。"""
        try:
            m = load_manifest(eid)
        except FileNotFoundError:
            return {"engine_id": eid, "display_name": eid, "name_key": "",
                    "binary": "", "min_version": "", "capabilities": {}, "installed": False}
        binary = m.get("binary", "")
        return {
            "engine_id": eid,
            "display_name": m.get("display_name", eid),
            "name_key": m.get("name_key", ""),
            "binary": binary,
            "min_version": m.get("min_version", ""),
            "install_url": m.get("install_url", ""),
            "capabilities": m.get("capabilities", {}) or {},
            "installed": bool(shutil.which(binary)),
        }

    engines = [_engine_info(eid) for eid in sorted(
        p.stem for p in MANIFEST_DIR.glob("*.json")) if eid in set(available_engines())]

    try:
        manifest = load_manifest(probe_engine_id)
    except FileNotFoundError:
        return {"ok": True, "config": cfg, "engines": engines, "probe": {
            "available": False, "reason": "not_installed", "display_name": probe_engine_id,
            "name_key": "", "hint": "chatEngine.notInstalled", "path": None, "version": None, "logged_in": False,
            "login_skipped": False,
        }}
    pr = probe_engine(manifest, cli_path_override=cfg.get("cli_path_override") if probe_engine_id == cfg["engine_id"] else None)
    return {"ok": True, "config": cfg, "engines": engines, "probe": pr}


@router.get("/api/settings/chat-engine/models")
def get_chat_engine_models(engine: str | None = None):
    """
    列出智能体引擎当前用户可用模型（对话面板就地切换用）.

    跑 manifest 声明的 models_cmd（如 `qoder --list-models`），按用户订阅回显模型清单。
    未声明 models_cmd / 未登录 / 未安装时降级为空清单 + reason，前端回退到「引擎默认 + 跳设置」。
    同步 subprocess（只读列命令），适用于本同步端点。
    """
    from core.cli_engine import list_models, load_manifest
    from core.cli_engine.manifest import available_engines

    cfg = get_chat_engine_config()
    engine_id = engine if (engine and engine in available_engines()) else cfg["engine_id"]
    try:
        manifest = load_manifest(engine_id)
    except FileNotFoundError:
        return {"ok": False, "models": [], "reason": "not_installed", "engine_id": engine_id}
    override = cfg.get("cli_path_override") if engine_id == cfg["engine_id"] else None
    res = list_models(manifest, cli_path_override=override)
    return {"ok": res["ok"], "models": res["models"], "reason": res["reason"], "engine_id": engine_id}


@router.get("/api/settings/routing")
def get_routing_status():
    """
    查询当前接入方式路由结论（REQ-SETTINGS-IA §3.1/§3.5 改版）.

    路由判定唯一入口 core/routing.get_routing_decision 的只读投影，供前端：
      - 决策卡/详情卡逐能力回显「生效来源 + 原因」（L1 行内常驻提示的数据源）；
      - 明示自动改用（auto_switched）聚合计数 → 联网卡 L3 角标与 L2 页面横幅；
      - 配额 ≤10 分钟预警（Q3 终裁阈值）与最近自动改用事件记录（账单争议可查）；
      - 逐能力未设置（source=""）时回显 unconfigured，触发逐能力引导。
    计费口径（与 core/metering 一致）：体验配额消耗分钟数 / 自带 Key 走自有供应商 /
    本机（离线与本机端点）不计量且零出网。
    """
    from core.routing import QUOTA_WARN_MINUTES, get_routing_decision

    llm_decision = get_routing_decision("llm")
    asr_decision = get_routing_decision("asr")

    quota = None
    try:
        from core.metering import check_quota, is_metered
        from core.users import get_current_user
        user = get_current_user()
        if user and is_metered():
            quota = check_quota(user.get("id", ""))
    except Exception:
        pass

    # 逐能力自动改用聚合（L2/L3 提示与事件记录回显）
    auto_switched_caps = [c for c, d in (("llm", llm_decision), ("asr", asr_decision)) if d.get("auto_switched")]
    quota_warning = None
    if quota and isinstance(quota, dict):
        remaining = quota.get("remaining")
        if remaining is not None and 0 <= remaining <= QUOTA_WARN_MINUTES:
            quota_warning = "low"

    recent_events: list[dict] = []
    try:
        from core.settings_events import recent_events as _recent
        recent_events = _recent(limit=5)
    except Exception:
        pass

    return {
        "ok": True,
        "expert_mode": llm_decision["expert_mode"],
        "llm": llm_decision,
        "asr": asr_decision,
        "capability": get_capability_status(),
        "quota": quota,
        "quota_warning": quota_warning,
        "auto_switch": {
            "count": len(auto_switched_caps),
            "capabilities": auto_switched_caps,
            "reasons": {c: d.get("reason") for c, d in (("llm", llm_decision), ("asr", asr_decision))
                        if d.get("auto_switched") or d.get("reason") in ("trial_quota_exhausted_no_fallback", "trial_requires_login")},
        },
        "recent_events": recent_events,
    }


@router.post("/api/settings/test")
def test_api_connection(data: dict = None):
    """
    测试 API 连接 / Test API connection.

    通过 service_type 区分测试目标 / Distinguish test target via service_type:
    - "asr"：测试语音转写服务连接 / Test ASR service connection
    - "llm"（默认）：测试纪要生成服务连接 / Test LLM service connection (default)
    """
    if not data:
        data = {}

    service_type = data.get("service_type", "llm")

    if service_type == "asr":
        return _test_asr_connection(data.get("asr"))
    else:
        return _test_ll_connection(data.get("llm"))


def _test_asr_connection(asr_data: dict | None) -> dict:
    """测试 ASR 服务连接（支持代理模式和直连模式） / Test ASR service connection (proxy and direct modes)."""
    cfg = get_asr_config()
    mode = cfg.get("mode", "proxy")

    # 若前端传入了新配置，使用传入值覆盖 / Override with incoming config if provided
    if asr_data:
        mode = asr_data.get("mode", mode)

    if mode == "direct":
        return _test_asr_direct(asr_data)
    else:
        return _test_asr_proxy()


def _test_asr_proxy() -> dict:
    """测试 ASR 代理服务连接 / Test ASR proxy service connection."""
    cfg = get_asr_config()
    proxy_url = cfg.get("proxy_url", "")

    if not proxy_url:
        return {"ok": False, "error": _("ASR proxy URL not configured")}

    # 调用代理健康检查端点 / Call proxy health check endpoint
    url = f"{proxy_url.rstrip('/')}/health"

    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("dashscope_configured"):
                return {"ok": True, "message": _("ASR proxy service connected")}
            else:
                return {"ok": False, "error": _("Proxy server has no DASHSCOPE_API_KEY configured")}
        elif resp.status_code == 401:
            return {"ok": False, "error": _("Proxy signature verification failed")}
        else:
            return {"ok": False, "error": f"HTTP {resp.status_code}"}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": _("Connection timeout (15s), please check network")}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": _("Cannot connect to proxy service, please check the address")}
    except Exception as e:
        return {"ok": False, "error": _("Test failed: {err}").format(err=str(e)[:200])}


def _test_asr_direct(asr_data: dict | None) -> dict:
    """测试直连模式 ASR 连接 / Test direct-mode ASR connection (submit minimal task to DashScope)."""
    if asr_data:
        base_url = asr_data.get("base_url", "")
        api_key = asr_data.get("api_key", "")
    else:
        cfg = get_asr_config()
        base_url = cfg.get("base_url", "")
        api_key = cfg.get("api_key", "")

    if not api_key or "****" in api_key:
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": _("ASR API Key not configured")}
    if not base_url:
        base_url = "https://dashscope.aliyuncs.com"

    # 通过获取上传凭证来验证 API Key 有效性 / Verify API Key via upload credential (lightweight; no actual upload)
    url = f"{base_url.rstrip('/')}/api/v1/uploads"
    params = {"action": "getPolicy", "model": "paraformer-v2"}
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            return {"ok": True, "message": _("ASR direct connection successful")}
        elif resp.status_code == 401:
            return {"ok": False, "error": _("Invalid ASR API Key (401 Unauthorized)")}
        elif resp.status_code == 403:
            return {"ok": False, "error": _("No permission to access ASR service (403 Forbidden)")}
        else:
            error_msg = resp.text[:200]
            return {"ok": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": _("Connection timeout (15s), please check network")}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": _("Cannot connect to {url}, please check the address").format(url=base_url)}
    except Exception as e:
        return {"ok": False, "error": _("Test failed: {err}").format(err=str(e)[:200])}


def _test_ll_connection(llm_data: dict | None) -> dict:
    """测试 LLM（纪要生成）服务连接 / Test LLM (summary generation) service connection."""
    if llm_data:
        base_url = llm_data.get("base_url", "")
        api_key = llm_data.get("api_key", "")
        model = llm_data.get("model", "qwen-plus")
    else:
        cfg = get_llm_config()
        base_url = cfg["base_url"]
        api_key = cfg["api_key"]
        model = cfg["model"]

    if not api_key or "****" in api_key:
        api_key = get_active_api_key()

    if not api_key:
        return {"ok": False, "error": _("LLM API Key not configured")}
    if not base_url:
        return {"ok": False, "error": _("LLM API Base URL not configured")}

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5,
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=15)
        if resp.status_code == 200:
            return {"ok": True, "message": _("Connection successful, model {model} responding").format(model=model)}
        elif resp.status_code == 401:
            return {"ok": False, "error": _("Invalid LLM API Key (401 Unauthorized)")}
        elif resp.status_code == 403:
            return {"ok": False, "error": _("No permission to access LLM service (403 Forbidden)")}
        elif resp.status_code == 404:
            return {"ok": False, "error": _("Endpoint or model not found (404). Please check Base URL and model name")}
        elif resp.status_code == 429:
            return {"ok": False, "error": _("Too many requests (429 Rate Limited), the Key itself is valid")}
        else:
            error_msg = resp.text[:200]
            return {"ok": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": _("Connection timeout (15s), please check network or Base URL")}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": _("Cannot connect to {url}, please check the address").format(url=base_url)}
    except Exception as e:
        return {"ok": False, "error": _("Test failed: {err}").format(err=str(e)[:200])}


# ============================================================
# LLM 连通性测试（R4 / WP-A） / LLM connectivity test (R4 / WP-A)
# ============================================================

# PRD R4 边界：测试超时 10s / Test timeout per PRD R4
TEST_LLM_TIMEOUT_SECONDS = 10


@router.post("/api/settings/test-llm")
def test_llm_connection(data: dict = None):
    """
    LLM 连通性测试（PRD R4） / LLM connectivity test (PRD R4).

    发送一条最小 chat 请求，返回延迟与模型可达性；失败返回可行动排错文案
    （error_code: invalid_config / missing_key / service_down / model_not_pulled /
    auth_failed / rate_limited / timeout / http_error）。
    localhost 端点允许空 Key；非 localhost 的 http:// 端点返回显式安全警告。
    """
    incoming = (data or {}).get("llm") or data or {}
    cfg = get_llm_config()

    base_url = (incoming.get("base_url") or cfg.get("base_url") or "").strip()
    model = (incoming.get("model") or cfg.get("model") or "").strip()
    # PRD R4 口径：显式传入空串 = 本次测试「无 Key」，不回填存量 Key（DEF-RETEST-03/04）；
    # 仅字段缺失或为脱敏占位（含 ****）时才沿用已存配置。
    # Explicit empty string means "test without a key" (PRD R4); only a missing or
    # masked (****) field falls back to the stored config.
    raw_key = incoming.get("api_key")
    if raw_key is None or "****" in raw_key:
        api_key = cfg.get("api_key") or ""
    else:
        api_key = raw_key.strip()

    if not base_url:
        return {
            "ok": False,
            "error_code": "invalid_config",
            "error": _("LLM API Base URL not configured"),
        }

    localhost = is_localhost_base_url(base_url)
    if not localhost and not api_key and raw_key is None:
        # 未显式传 Key 时才兜底旧版全局 Key；显式空串按「无 Key」处理返回 missing_key
        api_key = get_active_api_key()
    if not api_key and not localhost:
        return {
            "ok": False,
            "error_code": "missing_key",
            "error": _("LLM API Key not configured"),
        }

    # R4 边界：非 localhost 端点要求 https，否则显式警告 / Non-localhost endpoints should use https
    warning = None
    if not localhost and base_url.startswith("http://"):
        warning = _("Non-localhost endpoint is not using HTTPS; the API Key will be sent in plaintext")

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {
        "model": model or "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
        "stream": False,
    }

    start = time.perf_counter()
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=TEST_LLM_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        return _test_llm_fail(
            "timeout",
            _("Connection timed out after {sec}s; the service may be overloaded or the model is still loading").format(sec=TEST_LLM_TIMEOUT_SECONDS),
            warning=warning,
        )
    except requests.exceptions.ConnectionError:
        if localhost:
            return _test_llm_fail(
                "service_down",
                _("Cannot connect to the local LLM service. Please make sure Ollama / LM Studio is running and listening on the configured port; if you call the endpoint directly from a browser, also check its CORS settings (for Ollama set OLLAMA_ORIGINS)"),
                warning=warning,
            )
        return _test_llm_fail(
            "service_down",
            _("Cannot connect to {url}; please check the address, network, and firewall settings").format(url=base_url),
            warning=warning,
        )
    except Exception as e:
        return _test_llm_fail("http_error", _("Test failed: {err}").format(err=str(e)[:200]), warning=warning)

    latency_ms = int((time.perf_counter() - start) * 1000)
    resp_text = (resp.text or "")[:500]
    resp_lower = resp_text.lower()

    if resp.status_code == 200:
        result = {
            "ok": True,
            "latency_ms": latency_ms,
            "model": model,
            "message": _("Connection successful, model {model} responding in {latency}ms").format(model=model, latency=latency_ms),
        }
        if warning:
            result["warning"] = warning
        return result

    # 模型未拉取/未加载：Ollama 404 "try pulling it first"；LM Studio 400/404 "model not found"
    model_missing_markers = ("not found", "pull", "does not exist", "no model", "load the model")
    if resp.status_code in (400, 404) and any(m in resp_lower for m in model_missing_markers):
        return _test_llm_fail(
            "model_not_pulled",
            _("Model '{model}' is not available on the server. Pull or load it first (for Ollama: `ollama pull {model}`; for LM Studio: load the model in the app), then retry").format(model=model),
            warning=warning,
        )
    if resp.status_code == 404:
        return _test_llm_fail(
            "invalid_config",
            _("Endpoint or model not found (404). Please check that Base URL ends with /v1 and the model name is correct"),
            warning=warning,
        )
    if resp.status_code in (401, 403):
        return _test_llm_fail(
            "auth_failed",
            _("Authentication failed (HTTP {code}). Please check the API Key").format(code=resp.status_code),
            warning=warning,
        )
    if resp.status_code == 429:
        return _test_llm_fail(
            "rate_limited",
            _("Too many requests (429 Rate Limited); the endpoint itself is reachable"),
            warning=warning,
        )
    return _test_llm_fail(
        "http_error",
        _("HTTP {code}: {detail}").format(code=resp.status_code, detail=resp_text[:200]),
        warning=warning,
    )


def _test_llm_fail(error_code: str, error: str, warning: str | None = None) -> dict:
    """构造 test-llm 失败响应 / Build test-llm failure response."""
    result = {"ok": False, "error_code": error_code, "error": error}
    if warning:
        result["warning"] = warning
    return result


# ============================================================
# 本地引擎自动探测（R4 / WP-A，PRD §7.2-4） / Local engine auto-probe
# ============================================================

# PRD §7.2-4：探测超时 ≤2s / Probe timeout must be ≤2s
PROBE_TIMEOUT_SECONDS = 2

# 探测目标固定为本机 Ollama / LM Studio 的 OpenAI 兼容 /v1/models 端点。
# 硬编码 localhost，绝不接受外部输入 → 无 SSRF 面（PRD：探测仅访问 localhost，不计作出网）。
# Hardcoded localhost targets only; never user-supplied → no SSRF surface.
LOCAL_ENGINE_PROBE_TARGETS = [
    {
        "key": "ollama",
        "name": "Ollama（本地）",
        "base_url": "http://localhost:11434/v1",
        "models_url": "http://localhost:11434/v1/models",
        "install_url": "https://ollama.com/download",
    },
    {
        "key": "lmstudio",
        "name": "LM Studio（本地）",
        "base_url": "http://localhost:1234/v1",
        "models_url": "http://localhost:1234/v1/models",
        "install_url": "https://lmstudio.ai/",
    },
]


def _probe_one_engine(target: dict) -> dict:
    """探测单个本地引擎的 /v1/models（OpenAI 兼容），返回可达性与已拉取模型列表。
    Probe one local engine's /v1/models; returns reachability + pulled model list.
    """
    base = {
        "key": target["key"],
        "name": target["name"],
        "base_url": target["base_url"],
        "install_url": target["install_url"],
    }
    # 防御性断言：探测目标必须是 localhost / Defensive: target must be localhost
    if not is_localhost_base_url(target["base_url"]):
        return {**base, "reachable": False, "models": [], "model_count": 0, "error_code": "non_local_target"}

    try:
        resp = requests.get(target["models_url"], timeout=PROBE_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        return {**base, "reachable": False, "models": [], "model_count": 0, "error_code": "timeout"}
    except requests.exceptions.ConnectionError:
        return {**base, "reachable": False, "models": [], "model_count": 0, "error_code": "unreachable"}
    except Exception:
        return {**base, "reachable": False, "models": [], "model_count": 0, "error_code": "unreachable"}

    if resp.status_code != 200:
        return {**base, "reachable": False, "models": [], "model_count": 0, "error_code": "http_error"}

    try:
        payload = resp.json()
    except Exception:
        # 端口可达但非 OpenAI 兼容响应 / Reachable but not an OpenAI-compatible response
        return {**base, "reachable": True, "models": [], "model_count": 0, "error_code": "invalid_response"}

    raw = payload.get("data") if isinstance(payload, dict) else None
    models = [m["id"] for m in (raw or []) if isinstance(m, dict) and m.get("id")]
    return {**base, "reachable": True, "models": models, "model_count": len(models), "error_code": ""}


@router.get("/api/settings/probe-local-engine")
def probe_local_engine():
    """
    本地引擎自动探测（PRD §7.2-4） / Local engine auto-probe.

    进入设置页时调用：并发探测本机 Ollama（:11434）与 LM Studio（:1234）的
    OpenAI 兼容 /v1/models 端点，单个超时 ≤2s。仅访问 localhost，不计作出网。
    返回每个引擎的可达性与已拉取模型列表，供前端置「已检测到」标记、回填 model 下拉、
    不可达时置灰并给安装指引。
    """
    import concurrent.futures

    engines: list[dict] = []
    # 并发探测，整体上限 ≈ 单探测超时（2s），避免设置页进入时串行等待 4s
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(LOCAL_ENGINE_PROBE_TARGETS)) as pool:
        futures = {pool.submit(_probe_one_engine, t): t for t in LOCAL_ENGINE_PROBE_TARGETS}
        for fut in concurrent.futures.as_completed(futures):
            try:
                engines.append(fut.result())
            except Exception as e:  # 探测体已自兜底，此处双保险 / Probe already guards; double safety
                t = futures[fut]
                engines.append({
                    "key": t["key"], "name": t["name"], "base_url": t["base_url"],
                    "install_url": t["install_url"], "reachable": False, "models": [],
                    "model_count": 0, "error_code": "probe_error",
                })
                logger.warning(f"[本地引擎探测] {t['key']} 异常: {e}")

    # 按 LOCAL_ENGINE_PROBE_TARGETS 顺序稳定排序 / Stable order matching target list
    order = {t["key"]: i for i, t in enumerate(LOCAL_ENGINE_PROBE_TARGETS)}
    engines.sort(key=lambda e: order.get(e["key"], 99))

    detected = [e["key"] for e in engines if e["reachable"]]
    logger.info(f"[本地引擎探测] 完成: 检测到 {detected or '无'}")
    return {
        "ok": True,
        "probed_at": time.time(),
        "timeout_seconds": PROBE_TIMEOUT_SECONDS,
        "engines": engines,
        "detected": detected,
    }


# CLI 命令参考（供前端展示与其他 Agent 工具调用） / CLI command reference
CLI_REFERENCE = {
    "server": "python cli.py server --host 127.0.0.1 --port 8000",
    "record": {
        "start": "python cli.py record start",
        "stop": "python cli.py record stop",
        "pause": "python cli.py record pause",
        "resume": "python cli.py record resume",
        "status": "python cli.py record status",
    },
    "tasks": {
        "list": "python cli.py tasks list",
        "show": "python cli.py tasks show <task_id>",
        "delete": "python cli.py tasks delete <task_id>",
    },
    "transcribe": "python cli.py transcribe <音频文件> [-o 输出路径] [--show]",
    "speakers": {
        "list": "python cli.py speakers list",
        "add": "python cli.py speakers add <姓名> [--role 角色] [--note 备注]",
    },
    "hotwords": {
        "list": "python cli.py hotwords list",
        "add": "python cli.py hotwords add <词1> [词2 ...]",
    },
    "settings": {
        "show": "python cli.py settings show",
        "set": "python cli.py settings set <键> <值>",
    },
    "chat": 'python cli.py chat "<消息>" [--task-id xxx] [--project-id xxx]',
}


@router.get("/api/cli-reference")
async def get_cli_reference():
    """获取 CLI 命令参考 / Get CLI command reference."""
    return CLI_REFERENCE


# ============================================================
# 系统提示词查看（只读，增加软件开放性） / System Prompt Viewer (read-only; for openness)
# ============================================================

# 提示词注册表：名称 → (来源模块, 提示词内容, 用途说明) / Prompt registry: name → (module, prompt, purpose)
SYSTEM_PROMPTS = {
    "会议纪要生成": {
        "module": "core/summarize.py",
        "description": "批处理管线生成会议纪要时使用的系统提示词，指导 LLM 按结构化模板输出纪要",
        "prompt": SYSTEM_PROMPT,
    },
    "会议标题生成": {
        "module": "core/summarize.py",
        "description": "根据对话内容自动生成会议标题",
        "prompt": TITLE_SYSTEM_PROMPT,
    },
    "实时增量总结": {
        "module": "core/realtime_summary.py",
        "description": "录音过程中每分钟触发一次增量总结，指导 LLM 在已有总结基础上整合新内容",
        "prompt": SUMMARY_SYSTEM_PROMPT,
    },
    "AI 对话助手": {
        "module": "app/routers/chat.py",
        "description": "右侧 AI 对话框的基础系统提示词，定义助手能力边界与回复风格",
        "prompt": CHAT_SYSTEM_PROMPT,
    },
}


@router.get("/api/system-prompts")
async def get_system_prompts():
    """获取系统级提示词列表 / Get system prompt list (read-only)."""
    return SYSTEM_PROMPTS


# ============================================================
# 存储管理 / Storage Management
# ============================================================

# 存储用量缓存（60 秒过期，避免频繁 I/O） / Storage usage cache (60s TTL; avoids frequent I/O)
_storage_usage_cache: dict = {}
_storage_usage_cache_time: float = 0
_STORAGE_CACHE_TTL = 60  # 秒 / seconds


def _scan_dir_usage(dir_path: Path) -> dict:
    """扫描目录 / Scan directory."""
    size = 0
    count = 0
    if dir_path.exists():
        for f in dir_path.iterdir():
            if f.is_file():
                size += f.stat().st_size
                count += 1
    return {"size_bytes": size, "file_count": count}


def _scan_intermediate_usage() -> dict:
    """扫描中间产物 / Scan intermediate artifacts."""
    normalized_size = 0
    normalized_count = 0
    raw_size = 0
    raw_count = 0
    dup_size = 0
    dup_count = 0

    for scan_dir in [Path("data/recordings"), Path("data/uploads")]:
        if not scan_dir.exists():
            continue
        for f in scan_dir.iterdir():
            if not f.is_file():
                continue
            if "_normalized_normalized" in f.name:
                dup_size += f.stat().st_size
                dup_count += 1
            elif f.suffix == ".raw":
                raw_size += f.stat().st_size
                raw_count += 1
            elif "_normalized" in f.name and f.suffix == ".wav":
                normalized_size += f.stat().st_size
                normalized_count += 1

    return {
        "normalized_files": {"size_bytes": normalized_size, "file_count": normalized_count},
        "raw_files": {"size_bytes": raw_size, "file_count": raw_count},
        "duplicate_normalized": {"size_bytes": dup_size, "file_count": dup_count},
    }


@router.get("/api/storage/usage")
def get_storage_usage():
    """获取存储用量统计（含 60 秒缓存） / Get storage usage stats (60s cache)."""
    global _storage_usage_cache, _storage_usage_cache_time

    now = time.time()
    if _storage_usage_cache and (now - _storage_usage_cache_time) < _STORAGE_CACHE_TTL:
        return _storage_usage_cache

    recordings = _scan_dir_usage(Path("data/recordings"))
    uploads = _scan_dir_usage(Path("data/uploads"))
    tasks_usage = _scan_dir_usage(Path("data/tasks"))
    output = _scan_dir_usage(Path("data/output"))
    intermediate = _scan_intermediate_usage()

    total = recordings["size_bytes"] + uploads["size_bytes"] + tasks_usage["size_bytes"] + output["size_bytes"]
    reclaimable = (
        intermediate["normalized_files"]["size_bytes"]
        + intermediate["raw_files"]["size_bytes"]
        + intermediate["duplicate_normalized"]["size_bytes"]
    )

    result = {
        "recordings": recordings,
        "uploads": uploads,
        "tasks": tasks_usage,
        "output": output,
        "intermediate": intermediate,
        "total_bytes": total,
        "reclaimable_bytes": reclaimable,
    }

    _storage_usage_cache = result
    _storage_usage_cache_time = now
    return result


@router.post("/api/storage/clean")
def clean_intermediate_files():
    """清理所有中间产物 / Cleanup all intermediate artifacts."""
    from app.store import cleanup_orphaned_intermediate_files

    # 先执行启动清理 / First run startup cleanup
    result = cleanup_orphaned_intermediate_files()

    # 再清理所有归一化文件 / Then cleanup all normalized files
    normalized_freed = 0
    normalized_count = 0
    for scan_dir in [Path("data/recordings"), Path("data/uploads")]:
        if not scan_dir.exists():
            continue
        for f in scan_dir.iterdir():
            if f.is_file() and "_normalized" in f.name and f.suffix == ".wav":
                size = f.stat().st_size
                try:
                    f.unlink()
                    normalized_count += 1
                    normalized_freed += size
                except Exception as e:
                    logger.warning(f"清理归一化文件失败: {f.name}: {e}")

    # 清除缓存 / Clear cache
    global _storage_usage_cache, _storage_usage_cache_time
    _storage_usage_cache = {}
    _storage_usage_cache_time = 0

    total_freed = result["freed_bytes"] + normalized_freed
    logger.info(
        f"[存储] 手动清理完成: "
        f"归一化 {normalized_count} 个 ({normalized_freed / 1024 / 1024:.1f} MB) + "
        f"冗余 {result['duplicate_normalized']} 个 + "
        f"孤儿 .raw {result['orphan_raw']} 个 = "
        f"总计 {total_freed / 1024 / 1024:.1f} MB"
    )

    return {
        "cleaned": {
            "normalized_files": {"count": normalized_count, "freed_bytes": normalized_freed},
            "duplicate_normalized": {"count": result["duplicate_normalized"], "freed_bytes": result["freed_bytes"] - result.get("_raw_freed", 0)},
            "orphan_raw": {"count": result["orphan_raw"]},
        },
        "total_freed_bytes": total_freed,
    }


@router.post("/api/storage/clean-orphaned")
def clean_orphaned_files():
    """仅清理冗余文件 / Cleanup redundant files only."""
    from app.store import cleanup_orphaned_intermediate_files

    result = cleanup_orphaned_intermediate_files()

    # 清除缓存 / Clear cache
    global _storage_usage_cache, _storage_usage_cache_time
    _storage_usage_cache = {}
    _storage_usage_cache_time = 0

    return {
        "cleaned": {
            "duplicate_normalized": result["duplicate_normalized"],
            "orphan_raw": result["orphan_raw"],
        },
        "freed_bytes": result["freed_bytes"],
    }
