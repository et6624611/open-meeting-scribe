"""
tests/test_expert_mode.py — REQ-EXPERT-MODE 后端契约 + 注释层静态门禁

覆盖：
  - §2.2 CLI 探针三段失败段定位（failed_stage，AC-4 后端侧）
  - §2.3 会话级模型透传：默认值跟随详情 llm.model（AC-3 后端侧）+
    回复尾部消费方/计费回显 meta（与 routing 判定一致）
  - AC-2 注释层最小字号静态门禁（≥12px，裁决-5 产品级规则落地样本）
  - §2.2 导航 L0→L5 重排 + CLI 分类页接线（静态源检）
运行：pytest tests/test_expert_mode.py -v
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend" / "src"


# ============================================================
# §2.2 探针三段失败段定位
# ============================================================


class TestProbeFailedStage:
    def test_missing_binary_reports_path_stage(self):
        """① 段失败：可执行文件解析不到 → failed_stage=path（AC-4 三段定位）。"""
        from core.cli_engine import load_manifest, probe_engine

        manifest = dict(load_manifest("qoder-cli"))
        manifest["binary"] = "definitely-not-installed-cli-xyz"
        pr = probe_engine(manifest)
        assert pr["available"] is False
        assert pr["failed_stage"] == "path"
        assert pr["reason"] == "not_installed"

    def test_probe_result_always_carries_failed_stage_key(self):
        from core.cli_engine import load_manifest, probe_engine

        manifest = dict(load_manifest("qoder-cli"))
        manifest["binary"] = "definitely-not-installed-cli-xyz"
        pr = probe_engine(manifest)
        assert "failed_stage" in pr


# ============================================================
# §2.3 会话级模型默认跟随详情 + 使用回显 meta
# ============================================================


class TestChatModelResolution:
    def test_default_follows_llm_settings(self, monkeypatch):
        import app.routers.chat as chat_mod
        import app.store as store

        monkeypatch.setattr(store, "get_llm_config",
                            lambda: {"model": "qwen-max", "base_url": "", "api_key": "", "provider": ""},
                            raising=True)
        assert chat_mod._chat_model_default() == "qwen-max"

    def test_default_falls_back_when_unconfigured(self, monkeypatch):
        import app.routers.chat as chat_mod
        import app.store as store

        monkeypatch.setattr(store, "get_llm_config",
                            lambda: {"model": "", "base_url": "", "api_key": "", "provider": ""},
                            raising=True)
        assert chat_mod._chat_model_default() == "qwen-plus"

    def test_model_usage_meta_maps_billing_from_routing(self, monkeypatch):
        import app.routers.chat as chat_mod
        import core.routing as rt

        monkeypatch.setattr(rt, "get_routing_decision", lambda ctx="asr": {
            "configured_access_mode": "cloud", "expert_mode": False, "route": "cloud",
            "source": "trial", "auto_switched": False, "route_override": False, "reason": "",
        }, raising=True)
        meta = chat_mod._model_usage_meta("qwen-plus")
        assert meta["source"] == "trial"
        assert meta["billing"] == "platform_quota"
        assert meta["auto_switched"] is False

    def test_model_usage_meta_survives_routing_failure(self, monkeypatch):
        import app.routers.chat as chat_mod
        import core.routing as rt

        def _boom(ctx="asr"):
            raise RuntimeError("routing unavailable")
        monkeypatch.setattr(rt, "get_routing_decision", _boom, raising=True)
        meta = chat_mod._model_usage_meta("m1")
        assert meta == {"model": "m1", "source": "", "route": "", "billing": "", "auto_switched": False}


# ============================================================
# AC-2 注释层字号门禁（裁决-5：≥12px）+ §2.2 前端接线静态源检
# ============================================================

ANNOTATION_BLOCKS = [
    # (文件, CSS 选择器, 声明块必须含 font-size ≥12px)
    (FE / "components/layout/ai/AiChatPanel.vue", ".ai-usage-echo"),
    (FE / "components/layout/ai/AiChatPanel.vue", ".ai-cli-probe-warn"),
    (FE / "components/settings/CliEnginePanel.vue", ".cp-stage"),
]


@pytest.mark.parametrize("path,selector", ANNOTATION_BLOCKS,
                         ids=lambda v: v.name if isinstance(v, Path) else v)
def test_annotation_block_font_size_at_least_12px(path, selector):
    css = path.read_text(encoding="utf-8")
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, f"{path.name} 缺少 {selector} 样式块"
    fs = re.search(r"font-size:\s*(\d+)px", m.group(1))
    assert fs, f"{selector} 未声明 font-size（注释层必须显式字号）"
    assert int(fs.group(1)) >= 12, f"{selector} font-size {fs.group(1)}px < 12px（违反裁决-5）"


def test_settings_nav_reordered_l0_to_l5_with_cli():
    # REQ-COMPUTE-CENTER：算力相关四段按 账户登录 → API 配置(AI) → ASR 配置 → 本地引擎 排序；
    # CLI 面收敛进「API 配置」面板（与纪要正交），不再占独立导航位。
    src = (FE / "views/SettingsView.vue").read_text(encoding="utf-8")
    nav = src.split("<nav", 1)[1].split("</nav>", 1)[0]
    order = [c for c in ("account", "ai", "asr", "engine")
             if f"activeCategory === '{c}'" in nav]
    assert order == ["account", "ai", "asr", "engine"], \
        f"导航未按算力四段重排: {order}"
    ai = (FE / "components/settings/AiSourcePanel.vue").read_text(encoding="utf-8")
    assert "CliEnginePanel" in ai, "CLI 面应从 API 配置面板可达"


def test_tier_name_not_hardcoded():
    # REQ-COMPUTE-CENTER：账户面（含 tier 名）从 SettingsView 迁出到 AccountPanel。
    src = (FE / "components/settings/AccountPanel.vue").read_text(encoding="utf-8")
    assert "settings.tier_names.${tier" in src or "tier_names.${tier" in src
    # AC-5（EXPERT-MODE）：mock 付费档即显示正确档位名（未知档降级显原值不再恒谎）
    m = re.search(r"function tierName\(tier\?: string\)[\s\S]{0,300}?\n\}", src)
    assert m and "te(key)" in m.group(0)


def test_chat_panel_model_picker_wired():
    # 模型选择器已抽入 ComposerBar（ai-model-select 契约锚点在该组件）；
    # AiChatPanel 负责把 update:session-model 事件中转给外层。
    picker = (FE / "components/layout/ai/ComposerBar.vue").read_text(encoding="utf-8")
    assert "ai-model-select" in picker
    panel = (FE / "components/layout/ai/AiChatPanel.vue").read_text(encoding="utf-8")
    assert "update:sessionModel" in panel
    assert "<ComposerBar" in panel
    chat = (FE / "composables/useAiChat.ts").read_text(encoding="utf-8")
    # 轮级 override 优先，缺省回落 sessionModel；空串一律转 undefined（不发空 model）
    assert "override?.model ?? sessionModel.value" in chat
    assert "effectiveQaModel || undefined" in chat
    # 回显消费链：done.model_usage → assistantMsg.modelUsage
    assert "model_usage" in chat and "modelUsage" in chat


def test_access_mode_cards_removed_as_orphan():
    """逐能力化后 AccessModeCards 孤儿组件已删除（不在 SettingsView 导航）；回归守卫。"""
    assert not (FE / "components/settings/AccessModeCards.vue").exists(), "孤儿决策卡页应已删除"
    src = (FE / "views/SettingsView.vue").read_text(encoding="utf-8")
    assert "AccessModeCards" not in src, "SettingsView 不应再引用 AccessModeCards"
