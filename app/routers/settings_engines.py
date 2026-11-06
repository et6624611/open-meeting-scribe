"""app/routers/settings_engines.py — 引擎状态 / 路由结论 / 本地引擎探测 / CLI 参考。

端点：
  GET /api/settings/chat-engine          — 智能体引擎状态与可用性探针
  GET /api/settings/chat-engine/models   — 引擎可用模型清单
  GET /api/settings/routing              — 接入方式路由结论
  GET /api/settings/probe-local-engine   — 本地引擎自动探测（Ollama / LM Studio）
  GET /api/cli-reference                 — CLI 命令参考

作者 / Author: Yongliang Wang
创建 / Created: 2026-11-05（从 settings.py 拆分）
"""

import logging
import time

import requests
from fastapi import APIRouter

from app.settings_store import get_capability_status
from core import settings_store
from core.llm import is_localhost_base_url

logger = logging.getLogger(__name__)

router = APIRouter()


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

    cfg = settings_store.get_chat_engine_config()
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

    cfg = settings_store.get_chat_engine_config()
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
