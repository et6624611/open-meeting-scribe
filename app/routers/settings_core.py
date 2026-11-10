"""app/routers/settings_core.py — 设置读写与逐能力算力来源切换。

端点：
  GET  /api/settings             — 获取当前设置
  POST /api/settings             — 保存设置
  POST /api/settings/capability  — 逐能力算力来源切换事务

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-05（从 settings.py 拆分）
"""

import logging
import os
from copy import deepcopy

from fastapi import APIRouter

from app.settings_store import (
    ASR_CAP_SOURCES,
    LLM_CAP_SOURCES,
    apply_capability_source,
    ensure_percap_migrated,
    get_capability_status,
    get_expert_mode,
)
from core import settings_store
from core.llm import is_localhost_base_url
from core.settings_store import (
    get_active_api_key,
    get_asr_config,
    get_chat_engine_config,
    get_engine_config,
    get_feature_flags,
    get_llm_config,
    get_storage_config,
    get_transcript_config,
    get_web_search_config,
    mask_api_key,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
    settings = settings_store.load_settings()
    llm = get_llm_config()
    asr = get_asr_config()
    feature_flags = get_feature_flags()
    web_search = get_web_search_config()

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
        # 联网搜索配置（Brave 默认，provider 预留）
        "web_search": {
            "provider": web_search["provider"],
            "api_key": mask_api_key(web_search["api_key"]),
            "api_key_set": web_search["api_key_set"],
        },
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


def _merge_web_search_config(incoming: dict | None, existing: dict | None) -> dict:
    """合并联网搜索配置（provider + api_key）。

    API key 脱敏回显（含 ****）或空值时保留存量 key，否则用新值覆盖。
    """
    incoming = incoming or {}
    existing = existing or {}
    provider = str(incoming.get("provider") or existing.get("provider") or "brave").strip() or "brave"
    incoming_key = str(incoming.get("api_key") or "").strip()
    if not incoming_key or "****" in incoming_key:
        final_key = str(existing.get("api_key") or "").strip()
    else:
        final_key = incoming_key
    return {"provider": provider, "api_key": final_key}


@router.post("/api/settings")
def save_settings(data: dict):
    """
    保存设置 / Save settings.

    同时处理 ASR（语音转写）和 LLM（纪要生成）两套配置 / Handle both ASR and LLM configs.
    前端传入的 api_key 若是脱敏值（含 ****）或空值，则保留原 key 不变 / If incoming api_key is masked (contains ****) or empty, keep original key.
    """
    existing = settings_store.load_settings()

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
        # ── 联网搜索配置 / Web search config ──
        "web_search": _merge_web_search_config(data.get("web_search"), existing.get("web_search")),
    }

    # ── 逐能力算力来源（唯一真相源）/ Per-capability compute source handling ──
    # capability_source.{llm,asr} 由「API 配置 / ASR 配置」逐能力写入；非法值拒绝。
    # engine/asr.mode 仅作回滚兼容投影，由 apply_capability_source 同步；不再参与路由判定。
    merged.pop("voiceprint", None)  # 存量声纹配置键随任何一次保存丢弃

    if isinstance(data.get("expert_mode"), bool):
        merged["expert_mode"] = data["expert_mode"]
        # 显式选择后固化迁移标记，否则 get_expert_mode() 仍按存量配置惰性推导，用户开不了也关不掉
        # Freeze the migration flag; otherwise lazy derivation keeps overriding the explicit choice
        merged["_access_mode_migrated"] = True

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

    settings_store.save_settings_to_disk(merged)

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

    existing = settings_store.load_settings()
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
    settings_store.save_settings_to_disk(merged)
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
