"""app/routers/settings.py — 设置路由聚合入口。

原 settings.py（1349 行，2026-11-05 拆分为 4 模块）：
  settings_core.py    — 设置读写 + 逐能力算力来源切换（GET/POST /api/settings, /capability）
  settings_engines.py — chat-engine 状态/模型 + 路由结论 + 本地引擎探测 + CLI 参考
  settings_test.py    — API 连接测试（/api/settings/test, /test-llm）
  settings_extras.py  — 系统提示词查看 + 存储管理

include_router 保持 URL 前缀与响应结构零变化；from app.routers.settings import X
通过 re-export 保持向后兼容（测试 patch settings_router.get_llm_config 依赖）。

设置格式（v3 双服务版）：
{
  "asr": {"provider": "DashScope", "base_url": "...", "api_key": "sk-...", "model": "paraformer-v2"},
  "llm": {"provider": "DashScope", "base_url": ".../compatible-mode/v1", "api_key": "sk-...", "model": "qwen-plus"},
  "output_dir": "data/output/"
}

ASR 与 LLM 使用独立的 API Key，互不干扰 / ASR and LLM use independent API Keys.
API Key 在 GET 响应中脱敏返回（sk-****xxxx），仅在 POST 保存时接收明文 / API Key masked in GET responses; plaintext only in POST saves.
"""

from fastapi import APIRouter

# core.settings_store 配置读取函数 re-export：子模块直接 import core 层，不再经聚合模块穿透。
# 注意：运行时读取已直连 core.settings_store，测试须 patch core.settings_store。
from core.settings_store import (  # noqa: F401
    get_active_api_key,
    get_asr_config,
    get_chat_engine_config,
    get_llm_config,
    load_settings,
    save_settings_to_disk,
)

from .settings_core import (  # noqa: F401
    ASR_PROVIDER_PRESETS,
    PROVIDER_PRESETS,
    get_routing_decision_safe,
    get_settings,
    save_settings,
    switch_capability_source,
)
from .settings_core import (
    router as _core_router,
)
from .settings_engines import get_chat_engine_status  # noqa: F401
from .settings_engines import (
    router as _engines_router,
)
from .settings_extras import (
    router as _extras_router,
)
from .settings_test import (
    router as _test_router,
)

router = APIRouter(tags=["settings"])
router.include_router(_core_router)
router.include_router(_engines_router)
router.include_router(_test_router)
router.include_router(_extras_router)
