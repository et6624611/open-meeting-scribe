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
from pathlib import Path

import requests
from fastapi import APIRouter

from app.routers.chat import CHAT_SYSTEM_PROMPT
from app.store import (
    get_active_api_key,
    get_asr_config,
    get_feature_flags,
    get_llm_config,
    get_storage_config,
    get_voiceprint_config,
    load_settings,
    mask_api_key,
    save_settings_to_disk,
)
from core.i18n import _
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
    voiceprint = get_voiceprint_config()
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
    else:
        tier = "free"
        local_pref = False
        use_local = True

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
        "voiceprint": {
            "provider": voiceprint["provider"],
            "cloud_base_url": voiceprint["cloud"]["base_url"],
            "cloud_api_key": mask_api_key(voiceprint["cloud"]["api_key"]),
            "cloud_api_key_set": bool(voiceprint["cloud"]["api_key"]),
        },
        "diarization": {
            "subscription_tier": tier,
            "local_diarization": local_pref,
            "effective": "local" if use_local else "cloud",
            "can_toggle": tier != "free",
        },
        "output_dir": settings.get("output_dir", "data/output/"),
        "feature_flags": feature_flags,
        "storage": get_storage_config(),
        "disabled_commands": settings.get("disabled_commands", []),
        "asr_provider_presets": ASR_PROVIDER_PRESETS,
        "llm_provider_presets": PROVIDER_PRESETS,
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
    existing_vp = existing.get("voiceprint", {})
    existing_vp_cloud = existing_vp.get("cloud", {})
    existing_ff = existing.get("feature_flags", {})

    # ── LLM 配置 / LLM config ──
    new_llm = data.get("llm", {})
    incoming_llm_key = new_llm.get("api_key", "")
    if not incoming_llm_key or "****" in incoming_llm_key:
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
        # 代理模式：不保存 base_url 和 api_key / Proxy mode: don't save base_url and api_key
        merged_asr = {
            "mode": "proxy",
            "provider": new_asr.get("provider", existing_asr.get("provider", "DashScope")),
            "model": new_asr.get("model", existing_asr.get("model", "paraformer-v2")),
        }

    # ── 声纹配置 / Voiceprint config ──
    new_vp = data.get("voiceprint", {})
    new_vp_cloud = new_vp.get("cloud", {})
    incoming_vp_key = new_vp_cloud.get("api_key", "")
    if not incoming_vp_key or "****" in incoming_vp_key:
        final_vp_key = existing_vp_cloud.get("api_key", "")
    else:
        final_vp_key = incoming_vp_key

    merged = {
        **existing,
        "asr": merged_asr,
        "llm": {
            "provider": new_llm.get("provider", existing_llm.get("provider", "DashScope")),
            "base_url": new_llm.get("base_url", existing_llm.get("base_url", "")),
            "api_key": final_llm_key,
            "model": new_llm.get("model", existing_llm.get("model", "qwen-plus")),
        },
        "voiceprint": {
            "provider": new_vp.get("provider", existing_vp.get("provider", "auto")),
            "cloud": {
                "base_url": new_vp_cloud.get("base_url", existing_vp_cloud.get("base_url", "")),
                "api_key": final_vp_key,
            },
        },
        "output_dir": data.get("output_dir", existing.get("output_dir", "data/output/")),
        "feature_flags": {
            "realtime_chapters": data.get("feature_flags", {}).get("realtime_chapters", existing_ff.get("realtime_chapters", True)),
            "realtime_summary": data.get("feature_flags", {}).get("realtime_summary", existing_ff.get("realtime_summary", True)),
            "realtime_summary_interval": data.get("feature_flags", {}).get("realtime_summary_interval", existing_ff.get("realtime_summary_interval", 60)),
            "update_check": data.get("feature_flags", {}).get("update_check", existing_ff.get("update_check", True)),
            "voiceprint_auto_match": data.get("feature_flags", {}).get("voiceprint_auto_match", existing_ff.get("voiceprint_auto_match", False)),
        },
        "disabled_commands": data.get("disabled_commands", existing.get("disabled_commands", [])),
        "storage": {
            "auto_clean_intermediate": data.get("storage", {}).get("auto_clean_intermediate", existing.get("storage", {}).get("auto_clean_intermediate", True)),
            "auto_archive_days": data.get("storage", {}).get("auto_archive_days", existing.get("storage", {}).get("auto_archive_days", 0)),
        },
    }

    save_settings_to_disk(merged)

    # 声纹配置变更后重置 provider 缓存，使下次调用重新选择 / Reset provider cache after voiceprint config change
    try:
        from core.embedding_provider import reset_provider
        reset_provider()
    except Exception:
        pass

    # 同步到环境变量（供未改造的旧模块使用） / Sync to env vars (for legacy modules)
    if final_llm_key:
        os.environ["DASHSCOPE_API_KEY"] = final_llm_key

    logger.info(
        f"设置已更新: "
        f"asr_provider={merged['asr']['provider']}, "
        f"llm_provider={merged['llm']['provider']}, model={merged['llm']['model']}, "
        f"voiceprint_provider={merged['voiceprint']['provider']}"
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
        "voiceprint": {
            "provider": merged["voiceprint"]["provider"],
            "cloud_base_url": merged["voiceprint"]["cloud"]["base_url"],
            "cloud_api_key": mask_api_key(final_vp_key),
            "cloud_api_key_set": bool(final_vp_key),
        },
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
