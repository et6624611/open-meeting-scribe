"""
core/routing.py — 接入方式路由判定唯一入口 / Single source of routing truth

作者 / Author: 后端工程师（AM-B1 / REQ-ACCESS-MODE-CARDS T2；REQ-SETTINGS-IA 第 1/5 刀改造）
创建 / Created: 2026-09-25
版本 / Version: 3.0.0

职责 / Responsibilities:
  1. `get_routing_decision(context)`：路由判定的唯一入口。真相源 = 逐能力生效算力来源
     capability_source.{context}（trial/byok/local_endpoint(llm)/local(asr)/""=未设置）。
     不再有全局 access_mode；ASR 与 LLM 各自独立判定，互不联动。
     旧字段（engine.mode / asr.mode）仅为回滚兼容投影，不参与判定。
  2. 静默语义消灭：未登录 / 配额耗尽 / Key 缺失一律明示 `auto_switched=true` + `reason`，
     由界面用「自动改用」三级提示呈现（禁用「降级」词），并落本地事件记录
     （core/settings_events.py，关联账单争议）。
  3. 计费三路径口径（与 core/metering.py 一致）：trial → 体验配额计量；
     byok → 自有 Key 不计量；local / local_endpoint → 完全不计量且零出网。
  4. 逐能力未设置（source=""）时返回 `unconfigured=true`，由界面触发逐能力引导（不静默兜底）。

上下文 context:
  - "llm": route ∈ {"cloud", "direct", ""}
  - "asr": route ∈ {"cloud", "proxy", "direct", "local", ""}
"""

import logging

logger = logging.getLogger(__name__)

# 配额耗尽预警阈值（分钟，Q3 终裁：10 分钟预警）
QUOTA_WARN_MINUTES = 10

# 自动改用事件记录的转换态缓存（进程内；仅在状态跳变时落盘，避免每请求写盘）
_LAST_SWITCH_STATE: dict[str, str] = {}


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


def _decision(expert_mode, route, source="", auto_switched=False, reason="", unconfigured=False):
    return {
        "expert_mode": expert_mode,
        "route": route,
        # 算力来源（用户词；工程值注释由前端专家层呈现）
        "source": source,
        # 明示自动改用（取代旧 route_override 静默语义；字段保留一个兼容窗口同值镜像）
        "auto_switched": auto_switched,
        "route_override": auto_switched,
        "reason": reason,
        # 逐能力未设置（无默认，触发逐能力引导）
        "unconfigured": unconfigured,
    }


def _record_switch_once(context: str, from_src: str, to_src: str, reason: str) -> None:
    """仅在状态跳变时落一条自动改用事件（避免每请求写盘）。"""
    key = f"{context}:{reason}"
    state = "switched"
    if _LAST_SWITCH_STATE.get(key) == state:
        return
    _LAST_SWITCH_STATE[key] = state
    try:
        from core.settings_events import record_event
        record_event("auto_switch", capability=context, from_source=from_src,
                     to_source=to_src, reason=reason)
    except Exception:
        pass


def _switched_to_available_fallback(context: str, expert: bool) -> tuple[str, str] | None:
    """体验配额不可用（耗尽/未登录）时，寻找已就绪的替代来源。

    返回 (route, target_source) 或 None（无替代，保持原路由并明示原因）。
    口径：仅切换到用户已配置就绪的来源，绝不静默替用户花钱——
    byok 需有效 Key；local_endpoint 需 localhost base_url（仅 LLM）。
    """
    if context == "llm":
        if _is_localhost_base_url(_llm_base_url()):
            return ("direct", "local_endpoint")
        if _llm_key_available():
            return ("direct", "byok")
        return None
    asr_key = _asr_config().get("api_key", "") or _env_dashscope_key()
    if asr_key and not is_placeholder_key(asr_key):
        return ("direct", "byok")
    return None


def _trial_route(context: str, expert: bool, quota_state, allow_fallback: bool) -> dict:
    """体验配额来源：平台代付（消耗分钟数）。未登录/配额耗尽 → 按用户同意决定是否自动改用。

    allow_fallback=False（默认）：不替用户切换，保持 trial 并明示原因，
    由界面引导用户手动切换或开启自动改用。
    """
    logged_in, quota = quota_state

    if not logged_in:
        if allow_fallback:
            fb = _switched_to_available_fallback(context, expert)
            if fb:
                route, target = fb
                _record_switch_once(context, "trial", target, "trial_requires_login")
                return _decision(expert, route, source=target,
                                 auto_switched=True, reason="trial_requires_login")
        # 未同意（或无替代）：保持体验路由（将因登录门槛失败），原因明示供界面常驻
        transport = "cloud" if context == "llm" else _hosted_transport()
        return _decision(expert, transport, source="trial",
                         reason="trial_requires_login")

    if quota is not None and quota <= 0:
        if allow_fallback:
            fb = _switched_to_available_fallback(context, expert)
            if fb:
                route, target = fb
                _record_switch_once(context, "trial", target, "trial_quota_exhausted")
                return _decision(expert, route, source=target,
                                 auto_switched=True, reason="trial_quota_exhausted")
        transport = "cloud" if context == "llm" else _hosted_transport()
        return _decision(expert, transport, source="trial",
                         reason="trial_quota_exhausted_no_fallback")

    if context == "llm":
        return _decision(expert, "cloud", source="trial")
    return _decision(expert, _hosted_transport(), source="trial")


def _hosted_transport() -> str:
    """体验配额 ASR 传输：proxy/cloud 由 get_asr_config 解析；绝不由自有 Key 充当。"""
    transport = _asr_config().get("mode", "proxy")
    if transport == "direct":
        transport = "cloud" if _cloud_available() else "proxy"
        logger.info("capability_source=trial 但 asr.mode=direct（A2 投影分歧），按体验语义改用 %s", transport)
    return transport


def _trial_gate_state() -> tuple[bool, int | None]:
    """体验配额可用性：(是否登录, 剩余分钟数或 None=不受计量限制)。

    未登录 → (False, 0)；登录且不计量（非 SMS 档/配额 -1）→ (True, None)；
    否则 (True, remaining)。注意：不得调用 metering.is_metered（其内部回调本模块，
    会形成递归）；check_quota 纯读用户档与用量，无路由依赖。
    """
    try:
        from core.metering import check_quota
        from core.users import get_current_user
        user = get_current_user()
        if not user:
            return False, 0
        q = check_quota(user.get("id", ""))
        remaining = q.get("remaining")
        if remaining is None or remaining < 0:
            return True, None  # -1 = 不受计量限制
        return True, remaining
    except Exception:
        return True, None


# ============================================================
# 唯一入口 / single entry
# ============================================================


def get_routing_decision(context: str = "asr") -> dict:
    """路由判定唯一入口。真相源 = 逐能力生效来源 capability_source.{context}
    （trial / byok / local_endpoint(llm) / local(asr) / ""=未设置）。
    不再有全局 access_mode；两能力各自独立判定，互不联动。

    返回 dict:
      {
        "expert_mode": bool,
        "route": "local"|"cloud"|"proxy"|"direct"|"",
        "source": "local"|"trial"|"byok"|"local_endpoint"|"",
        "auto_switched": bool,  # True = 明示自动改用（界面禁用「降级」词）
        "route_override": bool, # 兼容窗口同值镜像
        "reason": str,          # "" | "source_not_set" | "trial_requires_login" | ...
        "unconfigured": bool,   # True = 该能力未设置来源，触发逐能力引导
      }
    """
    from app.settings_store import get_auto_fallback, get_capability_status, get_expert_mode

    expert = get_expert_mode()
    try:
        cap = get_capability_status()
        source = (cap.get(context) or {}).get("effective") or ""
    except Exception:
        source = ""
    # 自动改用需用户逐能力显式同意（默认关；不静默替用户花钱）
    try:
        allow_fallback = bool(get_auto_fallback().get(context, False))
    except Exception:
        allow_fallback = False

    if not source:
        # 逐能力未设置：不静默兜底，明示 unconfigured 供界面引导
        return _decision(expert, "", source="", reason="source_not_set", unconfigured=True)

    if source == "trial":
        return _trial_route(context, expert, _trial_gate_state(), allow_fallback)

    if source == "local_endpoint":
        # 仅 LLM 提供本机端点；localhost 端点零出网且不计量
        if context == "llm" and _is_localhost_base_url(_llm_base_url()):
            return _decision(expert, "direct", source="local_endpoint")
        return _decision(expert, "direct", source="local_endpoint",
                         reason="local_endpoint_misconfigured")

    if source == "local":
        # 仅 ASR 本机引擎（FunASR engine_host）；结构性零出网且不计量
        if context == "asr":
            return _decision(expert, "local", source="local")
        return _decision(expert, "local", source="local", reason="local_unsupported")

    # byok（自带 Key）：Key 缺失时仅在用户同意后才明示改用体验；否则保持并明示
    if context == "llm":
        if _is_localhost_base_url(_llm_base_url()) or _llm_key_available():
            return _decision(expert, "direct", source="byok")
        if allow_fallback:
            logged_in, quota = _trial_gate_state()
            if logged_in and (quota is None or quota > 0) and _cloud_available():
                _record_switch_once("llm", "byok", "trial", "byok_key_missing")
                return _decision(expert, "cloud", source="trial",
                                 auto_switched=True, reason="byok_key_missing")
        return _decision(expert, "direct", source="byok",
                         reason="byok_key_missing_cloud_unavailable")

    # ASR byok：有可用 Key → direct；否则按同意决定是否改用体验，都不可用则保持并明示
    try:
        cfg = _asr_config()
        asr_key = cfg.get("api_key", "") or _env_dashscope_key()
    except Exception:
        cfg, asr_key = {}, ""
    if asr_key and not is_placeholder_key(asr_key):
        return _decision(expert, "direct", source="byok")
    if allow_fallback:
        logged_in, quota = _trial_gate_state()
        if logged_in and (quota is None or quota > 0) and _cloud_available():
            _record_switch_once("asr", "byok", "trial", "byok_key_missing")
            return _decision(expert, "cloud", source="trial",
                             auto_switched=True, reason="byok_key_missing")
    return _decision(expert, cfg.get("mode", "proxy"), source="byok",
                     reason="byok_key_missing_cloud_unavailable")


def _env_dashscope_key() -> str:
    import os
    return os.getenv("DASHSCOPE_API_KEY", "")


def _llm_base_url() -> str:
    try:
        from app.store import get_llm_config
        return get_llm_config().get("base_url", "")
    except Exception:
        return ""
