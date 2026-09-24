"""
core/routing.py — 接入方式路由判定唯一入口 / Single source of routing truth

作者 / Author: 后端工程师（AM-B1 / REQ-ACCESS-MODE-CARDS T2）
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

职责 / Responsibilities:
  1. `get_routing_decision(context)`：路由判定的唯一入口，只以 access_mode 为配置语义
     （T2 收口：`core/llm.py::_should_use_cloud`、`core/transcribe.py::_get_asr_mode`
     不再各自读 engine.mode + prefer_subscription 组合）。
  2. D2/R3 显性化：byok 用户开启 prefer_subscription（或未配有效 Key 回落云代理）导致的
     跨模式路由变化，通过 `route_override` + `reason` 可被前端经
     `GET /api/settings/routing` 查询（供 AM-F1 toast）。
  3. 计费三路径口径（与 core/metering.py 一致）：
     hosted → 云代理消耗配额；byok → 自有 Key 不消耗；local → 完全不计量。
  4. 未配置（access_mode=null）时按升级前逻辑兜底判定（AC-6：不改变未引导用户的行为），
     兜底逻辑同样收敛在本模块内。

上下文 context:
  - "llm": route ∈ {"cloud", "direct", "local"}（LLM 无独立 proxy 传输）
  - "asr": route ∈ {"cloud", "proxy", "direct", "local"}（proxy/cloud 为托管传输细节）
"""

import logging

logger = logging.getLogger(__name__)


def is_placeholder_key(key: str) -> bool:
    """检测 API Key 是否为空/模板占位符（自 core/llm.py 收敛，两处判定共用口径）。"""
    if not key:
        return True
    k = key.lower()
    return (
        "xxxx" in k
        or "sk-xxx" in k
        or k.startswith("your-")
        or "your_api_key" in k
        or "your-api-key" in k
        or len(k) < 20  # 真实 Key 通常较长 / Real keys are usually longer
    )


def _is_localhost_base_url(base_url: str) -> bool:
    from core.llm import is_localhost_base_url
    return is_localhost_base_url(base_url)


def _user_subscription_state() -> tuple[bool, int]:
    """返回 (prefer_subscription, quota)。quota 缺省按 DEFAULT_QUOTA 口径（与 metering 一致）。"""
    try:
        from core.metering import DEFAULT_QUOTA
        from core.users import get_current_user
        user = get_current_user()
        if user:
            ps = bool(user.get("prefs", {}).get("prefer_subscription", False))
            quota = user.get("quota", DEFAULT_QUOTA)
            return ps, (quota if quota is not None else DEFAULT_QUOTA)
    except Exception:
        pass
    return False, 0


def _cloud_available() -> bool:
    try:
        from core.cloud_client import is_cloud_enabled
        return bool(is_cloud_enabled())
    except Exception:
        return False


def _llm_key_available() -> bool:
    try:
        from app.store import get_active_api_key
        key = get_active_api_key()
        return bool(key) and not is_placeholder_key(key)
    except Exception:
        return False


def _asr_config() -> dict:
    from app.store import get_asr_config
    return get_asr_config()


def _decision(access_mode, expert_mode, route, route_override=False, reason=""):
    return {
        "configured_access_mode": access_mode,
        "expert_mode": expert_mode,
        "route": route,
        "route_override": route_override,
        "reason": reason,
    }


# ============================================================
# 唯一入口 / single entry
# ============================================================


def get_routing_decision(context: str = "asr") -> dict:
    """路由判定唯一入口。任何 engine.mode / prefer_subscription 的读取只允许发生在本模块。

    返回 dict:
      {
        "configured_access_mode": "local"|"hosted"|"byok"|None,
        "expert_mode": bool,
        "route": "local"|"cloud"|"proxy"|"direct",
        "route_override": bool,   # True = 实际路由偏离所配置的接入方式语义（D2 须显性告知）
        "reason": str,            # "" | "prefer_subscription" | "byok_key_missing"
                                  # | "byok_key_missing_cloud_unavailable"
                                  # | "legacy_unconfigured" | ...
      }
    """
    from app.settings_store import get_access_mode, get_expert_mode

    access = get_access_mode()
    expert = get_expert_mode()

    if access is None:
        return _legacy_decision(context, expert)

    if access == "local":
        return _decision(access, expert, "local")

    if access == "hosted":
        if context == "llm":
            # LLM 托管 = 云代理（proxy 传输仅 ASR 存在）
            return _decision(access, expert, "cloud")
        # ASR 托管传输：proxy/cloud 由 get_asr_config 现有解析（含无 URL 自动降级），
        # 但绝不回落 direct——direct 意味着自有 Key，与托管计费语义冲突（静默组合消除）。
        transport = _asr_config().get("mode", "proxy")
        if transport == "direct":
            transport = "cloud" if _cloud_available() else "proxy"
            logger.info("access_mode=hosted 但 asr.mode=direct（旧配置分歧），按托管语义改为 %s", transport)
        return _decision(access, expert, transport)

    # byok：自有 Key 直连。两个偏离口径（均置 route_override=True 供前端 toast）：
    #   1) D2：prefer_subscription 开启且配额>0 且云端可用 → 走云代理消耗配额；
    #   2) Key 缺失/占位 → 升级前即有的云代理回退（若云端可用），避免直接不可用。
    # localhost 自持端点（Ollama/LM Studio）永不切云（R4 绝不回退云端，先于一切 override）。
    if _is_localhost_base_url(_llm_base_url()):
        return _decision(access, expert, "direct")

    ps, quota = _user_subscription_state()
    if ps and quota > 0 and _cloud_available():
        return _decision(access, expert, "cloud", route_override=True, reason="prefer_subscription")

    if context == "llm":
        if _llm_key_available():
            return _decision(access, expert, "direct")
        if _cloud_available():
            return _decision(access, expert, "cloud", route_override=True, reason="byok_key_missing")
        return _decision(access, expert, "direct", reason="byok_key_missing_cloud_unavailable")

    # ASR byok：有可用 Key → direct；否则沿升级前 get_asr_config 传输判定兜底
    try:
        cfg = _asr_config()
        asr_key = cfg.get("api_key", "") or _env_dashscope_key()
    except Exception:
        cfg, asr_key = {}, ""
    if asr_key and not is_placeholder_key(asr_key):
        return _decision(access, expert, "direct")
    if _cloud_available():
        return _decision(access, expert, "cloud", route_override=True, reason="byok_key_missing")
    return _decision(access, expert, cfg.get("mode", "proxy"), reason="byok_key_missing_cloud_unavailable")


def _env_dashscope_key() -> str:
    import os
    return os.getenv("DASHSCOPE_API_KEY", "")


def _llm_base_url() -> str:
    try:
        from app.store import get_llm_config
        return get_llm_config().get("base_url", "")
    except Exception:
        return ""


# ============================================================
# 未配置兜底（AC-6：行为与升级前逐项等价）
# ============================================================


def _legacy_decision(context: str, expert: bool) -> dict:
    """access_mode=null（未配置/迁移未落盘）时的升级前等价判定。

    判定逻辑自 core/llm.py / core/transcribe.py 原样迁移至此，保证双头读取彻底收敛。
    """
    if context == "llm":
        return _decision(None, expert, _legacy_llm_route(), reason="legacy_unconfigured")
    return _decision(None, expert, _legacy_asr_route(), reason="legacy_unconfigured")


def _legacy_llm_route() -> str:
    """core/llm.py::_should_use_cloud 升级前逻辑的等价迁移（"cloud"|"direct"）。"""
    # R4（WP-A）：localhost 自持端点显式本地直连，绝不回退云端
    if _is_localhost_base_url(_llm_base_url()):
        return "direct"
    # 用户偏好覆盖：prefer_subscription 开启且配额>0 且云端可用 → 云代理
    ps, quota = _user_subscription_state()
    if ps and quota > 0 and _cloud_available():
        return "cloud"
    if _llm_key_available():
        return "direct"
    return "cloud" if _cloud_available() else "direct"


def _legacy_asr_route() -> str:
    """core/transcribe.py::_get_asr_mode 升级前逻辑的等价迁移。"""
    # 本地引擎优先（R1）：engine.mode==local → 本地 FunASR 管线
    try:
        from app.settings_store import get_engine_config
        if get_engine_config().get("mode") == "local":
            return "local"
    except Exception:
        pass
    try:
        mode = _asr_config().get("mode", "proxy")
        # prefer_subscription 开启且直连模式 → 云代理消耗配额
        if mode == "direct":
            ps, quota = _user_subscription_state()
            if ps and quota > 0 and _cloud_available():
                logger.info("用户开启优先使用订阅流量，ASR 从 direct 切换为 cloud 模式")
                return "cloud"
        # 自动回退：proxy 无 URL 且云端可用 → cloud
        if mode == "proxy" and not _asr_config().get("proxy_url", ""):
            if _cloud_available():
                logger.info("ASR proxy URL 为空且云端可用，自动切换到 cloud 模式")
                return "cloud"
        return mode
    except Exception:
        return "proxy"
