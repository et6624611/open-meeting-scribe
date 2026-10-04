"""
tests/test_model_tier.py — R4 model_tier 档位判定与防幻觉提示词接入测试（WP-A）

运行方式：
  pytest tests/test_model_tier.py -v
"""

import json

import pytest

import app.settings_store as settings_store
from core import model_tier


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    """将 settings.json 重定向到临时目录 / Redirect settings.json to tmp dir."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", path)
    return path


def _write_settings(path, data: dict):
    path.write_text(json.dumps(data), encoding="utf-8")


# ============================================================
# 模型名参数规模解析
# ============================================================

class TestParseModelSize:
    @pytest.mark.parametrize("name,size", [
        ("qwen3:8b", 8.0),
        ("qwen3:14b", 14.0),
        ("llama-3.1-8b", 8.0),
        ("deepseek-r1:70b", 70.0),
        ("qwen2.5-coder-32b-instruct", 32.0),
        ("gemma-2-2.5b", 2.5),
    ])
    def test_parse_size(self, name, size):
        assert model_tier.parse_model_size_b(name) == size

    @pytest.mark.parametrize("name", ["qwen-plus", "gpt-4o", "deepseek-chat", "", None])
    def test_unparseable_returns_none(self, name):
        assert model_tier.parse_model_size_b(name) is None


# ============================================================
# 档位判定（auto / 显式覆盖）
# ============================================================

class TestResolveTier:
    def test_auto_small_model_is_conservative(self, settings_file):
        _write_settings(settings_file, {"engine": {"local": {"model_tier": "auto"}}})
        assert model_tier.resolve_model_tier("qwen3:8b") == "conservative"
        assert model_tier.resolve_model_tier("qwen3:14b") == "conservative"

    def test_auto_large_model_is_standard(self, settings_file):
        _write_settings(settings_file, {})
        assert model_tier.resolve_model_tier("deepseek-r1:70b") == "standard"

    def test_auto_cloud_model_is_standard(self, settings_file):
        """云端默认模型（无法解析规模）走 standard，行为零变化"""
        _write_settings(settings_file, {})
        assert model_tier.resolve_model_tier("qwen-plus") == "standard"

    def test_default_tier_is_auto(self, settings_file):
        """未配置 engine 块时默认 auto"""
        _write_settings(settings_file, {})
        assert model_tier.get_configured_model_tier() == "auto"

    def test_explicit_standard_overrides_auto(self, settings_file):
        _write_settings(settings_file, {"engine": {"local": {"model_tier": "standard"}}})
        assert model_tier.resolve_model_tier("qwen3:8b") == "standard"

    def test_explicit_conservative_overrides_auto(self, settings_file):
        _write_settings(settings_file, {"engine": {"local": {"model_tier": "conservative"}}})
        assert model_tier.resolve_model_tier("qwen-plus") == "conservative"

    def test_invalid_tier_falls_back_to_auto(self, settings_file):
        _write_settings(settings_file, {"engine": {"local": {"model_tier": "bogus"}}})
        assert model_tier.get_configured_model_tier() == "auto"

    def test_auto_reads_model_from_settings(self, settings_file):
        """model=None 时从 llm 配置读取模型名"""
        _write_settings(settings_file, {"llm": {"model": "qwen3:8b"}})
        assert model_tier.resolve_model_tier(None) == "conservative"


# ============================================================
# 提示词守卫
# ============================================================

class TestPromptGuard:
    def test_guard_nonempty_for_conservative(self, settings_file):
        _write_settings(settings_file, {})
        guard = model_tier.get_tier_prompt_guard("qwen3:8b")
        assert "防幻觉" in guard
        assert guard.startswith("\n")

    def test_guard_empty_for_standard(self, settings_file):
        _write_settings(settings_file, {})
        assert model_tier.get_tier_prompt_guard("qwen-plus") == ""


# ============================================================
# 纪要管线接入（core/summarize.py）
# ============================================================

class TestSummarizeWiring:
    def _dialogue(self):
        return [
            {"speaker_id": 0, "speaker_name": "张三", "text": "我们下周三发布新版本。", "sentences": [{"text": "我们下周三发布新版本。"}]},
            {"speaker_id": 1, "speaker_name": "李四", "text": "好的，我负责准备发布说明。", "sentences": [{"text": "好的，我负责准备发布说明。"}]},
            {"speaker_id": 0, "speaker_name": "张三", "text": "发布前跑一遍回归测试。", "sentences": [{"text": "发布前跑一遍回归测试。"}]},
        ]

    def test_conservative_guard_injected(self, settings_file, monkeypatch):
        _write_settings(settings_file, {})
        import core.agent_workspace as agent_workspace
        import core.summarize as summarize

        monkeypatch.setattr(agent_workspace, "get_role_summary_prompt", lambda: None)
        captured = {}

        def fake_chat_completion(messages, model=None, **kwargs):
            captured["system"] = messages[0]["content"]
            return "# 纪要\n（测试输出）"

        monkeypatch.setattr(summarize, "chat_completion", fake_chat_completion)
        summarize.generate_summary(self._dialogue(), model="qwen3:8b")
        assert model_tier.CONSERVATIVE_PROMPT_GUARD in captured["system"]

    def test_standard_model_prompt_unchanged(self, settings_file, monkeypatch):
        _write_settings(settings_file, {})
        import core.agent_workspace as agent_workspace
        import core.summarize as summarize

        monkeypatch.setattr(agent_workspace, "get_role_summary_prompt", lambda: None)
        captured = {}

        def fake_chat_completion(messages, model=None, **kwargs):
            captured["system"] = messages[0]["content"]
            return "# 纪要\n（测试输出）"

        monkeypatch.setattr(summarize, "chat_completion", fake_chat_completion)
        summarize.generate_summary(self._dialogue(), model="qwen-plus")
        # 一页纸系数上线后的新不变量：标准档 = 基座提示词 + 默认 1 页预算块（防幻觉守卫仍为空）
        assert captured["system"] == summarize.SYSTEM_PROMPT + summarize.build_page_budget_block(1.0)
        assert model_tier.CONSERVATIVE_PROMPT_GUARD not in captured["system"]
