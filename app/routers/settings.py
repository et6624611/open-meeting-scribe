"""
app/routers/settings.py — 设置读写、API 连接测试、CLI 参考与系统提示词查看

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

ASR 与 LLM 使用独立的 API Key，互不干扰。
API Key 在 GET 响应中脱敏返回（sk-****xxxx），仅在 POST 保存时接收明文。
"""

import os
import json
import logging

import requests
from fastapi import APIRouter

from app.store import (
    SETTINGS_FILE, load_settings, save_settings_to_disk,
    mask_api_key, get_active_api_key, get_llm_config, get_asr_config,
    get_voiceprint_config, get_feature_flags,
)
from core.summarize import SYSTEM_PROMPT, TITLE_SYSTEM_PROMPT
from core.realtime_summary import SUMMARY_SYSTEM_PROMPT
from app.routers.chat import CHAT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])

# 常用 Provider 预设（前端下拉用）
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

# ASR Provider 预设（语音转写服务）
# 当前仅支持 DashScope（Paraformer），保留扩展结构
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
    获取当前设置。

    返回 ASR（语音转写）和 LLM（纪要生成）两套独立配置。
    API Key 脱敏返回：仅显示前 3 位和后 4 位。
    """
    settings = load_settings()
    llm = get_llm_config()
    asr = get_asr_config()
    voiceprint = get_voiceprint_config()
    feature_flags = get_feature_flags()

    # 声纹偏好：根据用户订阅状态决定
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

    return {
        "asr": {
            "provider": asr["provider"],
            "proxy_url": asr.get("proxy_url", ""),
            "model": asr["model"],
            "source": "platform",  # 代理模式下始终为 platform
            "api_key_managed_by_proxy": True,  # API Key 由代理服务器持有
        },
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
        "disabled_commands": settings.get("disabled_commands", []),
        "asr_provider_presets": ASR_PROVIDER_PRESETS,
        "llm_provider_presets": PROVIDER_PRESETS,
    }


@router.post("/api/settings")
def save_settings(data: dict):
    """
    保存设置。

    同时处理 ASR（语音转写）和 LLM（纪要生成）两套配置。
    前端传入的 api_key 若是脱敏值（含 ****）或空值，则保留原 key 不变。
    """
    existing = load_settings()

    # ── 向后兼容：迁移旧版 flat 格式 ──
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

    # ── LLM 配置 ──
    new_llm = data.get("llm", {})
    incoming_llm_key = new_llm.get("api_key", "")
    if not incoming_llm_key or "****" in incoming_llm_key:
        final_llm_key = existing_llm.get("api_key") or get_active_api_key()
    else:
        final_llm_key = incoming_llm_key

    # ── ASR 配置（代理模式：不再保存 API Key，仅保存模型选择）──
    new_asr = data.get("asr", {})

    # ── 声纹配置 ──
    new_vp = data.get("voiceprint", {})
    new_vp_cloud = new_vp.get("cloud", {})
    incoming_vp_key = new_vp_cloud.get("api_key", "")
    if not incoming_vp_key or "****" in incoming_vp_key:
        final_vp_key = existing_vp_cloud.get("api_key", "")
    else:
        final_vp_key = incoming_vp_key

    merged = {
        **existing,
        "asr": {
            "provider": new_asr.get("provider", existing_asr.get("provider", "DashScope")),
            "model": new_asr.get("model", existing_asr.get("model", "paraformer-v2")),
            # 代理模式下不再保存 base_url 和 api_key
        },
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
        },
        "disabled_commands": data.get("disabled_commands", existing.get("disabled_commands", [])),
    }

    save_settings_to_disk(merged)

    # 声纹配置变更后重置 provider 缓存，使下次调用重新选择
    try:
        from core.embedding_provider import reset_provider
        reset_provider()
    except Exception:
        pass

    # 同步到环境变量（供未改造的旧模块使用）
    if final_llm_key:
        os.environ["DASHSCOPE_API_KEY"] = final_llm_key

    logger.info(
        f"设置已更新: "
        f"asr_provider={merged['asr']['provider']}, "
        f"llm_provider={merged['llm']['provider']}, model={merged['llm']['model']}, "
        f"voiceprint_provider={merged['voiceprint']['provider']}"
    )

    return {
        "ok": True,
        "asr": {
            "provider": merged["asr"]["provider"],
            "model": merged["asr"]["model"],
            "api_key_managed_by_proxy": True,
        },
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
    测试 API 连接。

    通过 service_type 区分测试目标：
    - "asr"：测试语音转写服务连接（DashScope RESTful API）
    - "llm"（默认）：测试纪要生成服务连接（chat/completions 端点）
    """
    if not data:
        data = {}

    service_type = data.get("service_type", "llm")

    if service_type == "asr":
        return _test_asr_connection(data.get("asr"))
    else:
        return _test_ll_connection(data.get("llm"))


def _test_asr_connection(asr_data: dict | None) -> dict:
    """测试 ASR 代理服务连接"""
    cfg = get_asr_config()
    proxy_url = cfg.get("proxy_url", "")

    if not proxy_url:
        return {"ok": False, "error": "未配置 ASR 代理地址"}

    # 调用代理健康检查端点
    url = f"{proxy_url.rstrip('/')}/health"

    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("dashscope_configured"):
                return {"ok": True, "message": "ASR 代理服务连接正常"}
            else:
                return {"ok": False, "error": "代理服务端未配置 DASHSCOPE_API_KEY"}
        elif resp.status_code == 401:
            return {"ok": False, "error": "代理签名校验失败"}
        else:
            return {"ok": False, "error": f"HTTP {resp.status_code}"}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "连接超时（15s），请检查网络"}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"无法连接到 {base_url}，请检查地址是否正确"}
    except Exception as e:
        return {"ok": False, "error": f"测试失败: {str(e)[:200]}"}


def _test_ll_connection(llm_data: dict | None) -> dict:
    """测试 LLM（纪要生成）服务连接"""
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
        return {"ok": False, "error": "未配置 LLM API Key"}
    if not base_url:
        return {"ok": False, "error": "未配置 LLM API Base URL"}

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
            data_resp = resp.json()
            content = data_resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"ok": True, "message": f"连接成功，模型 {model} 响应正常"}
        elif resp.status_code == 401:
            return {"ok": False, "error": "LLM API Key 无效（401 Unauthorized）"}
        elif resp.status_code == 403:
            return {"ok": False, "error": "无权访问 LLM 服务（403 Forbidden）"}
        elif resp.status_code == 404:
            return {"ok": False, "error": f"端点或模型不存在（404）。请检查 Base URL 和模型名称"}
        elif resp.status_code == 429:
            return {"ok": False, "error": "请求过于频繁（429 Rate Limited），Key 本身是有效的"}
        else:
            error_msg = resp.text[:200]
            return {"ok": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "连接超时（15s），请检查网络或 Base URL"}
    except requests.exceptions.ConnectionError as e:
        return {"ok": False, "error": f"无法连接到 {base_url}，请检查地址是否正确"}
    except Exception as e:
        return {"ok": False, "error": f"测试失败: {str(e)[:200]}"}


# CLI 命令参考（供前端展示与其他 Agent 工具调用）
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
    """获取 CLI 命令参考（供前端展示与其他 Agent 工具调用）"""
    return CLI_REFERENCE


# ============================================================
# 系统提示词查看（只读，增加软件开放性）
# ============================================================

# 提示词注册表：名称 → (来源模块, 提示词内容, 用途说明)
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
    """获取系统级提示词列表（只读，供用户查看 AI 行为规则）"""
    return SYSTEM_PROMPTS
