"""
tests/test_page_budget.py — 一页纸系数：纪要篇幅预算块与生成链路接入

覆盖：
1. build_page_budget_block 四档文案与配额数字（含 0.5 档议题归类合并指令）
2. generate_summary 接入：默认 1 页追加、指定档位生效、非法值兜底、Agent 角色模板路径同点位
"""

import pytest

import app.settings_store as settings_store
from core.summarize import build_page_budget_block


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    """将 settings.json 重定向到临时目录 / Redirect settings.json to tmp dir."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "SETTINGS_FILE", path)
    return path


class TestBudgetBlock:
    def test_factor_1_quotas(self):
        block = build_page_budget_block(1.0)
        assert "一页纸系数 1" in block
        assert "约 900 字" in block
        assert "不超过 5 条" in block   # 主要结论 ≤5
        assert "不超过 4 条" in block   # 待办 ≤4
        assert "不超过 3 句话" in block
        assert "无需输出" not in block  # 1 页档议题归类保留（正向句式措辞，避开模板禁止行为条款）

    def test_factor_half_merges_topics(self):
        block = build_page_budget_block(0.5)
        assert "约 450 字" in block
        assert "不超过 3 条" in block   # 5×0.5=2.5 四舍五入 → 3
        assert "不超过 2 条" in block   # 4×0.5=2
        assert "不超过 1 句话" in block
        assert "仅保留一、二、三节" in block    # 0.5 档议题归类合并（结构性正向表述）
        assert "会议概要" in block

    def test_factor_2_quotas(self):
        block = build_page_budget_block(2.0)
        assert "约 1800 字" in block
        assert "不超过 10 条" in block
        assert "不超过 8 条" in block

    def test_factor_1_5_quotas(self):
        block = build_page_budget_block(1.5)
        assert "约 1350 字" in block
        assert "不超过 8 条" in block   # 7.5 → 8
        assert "不超过 6 条" in block

    def test_illegal_factor_falls_back_to_one(self):
        # 与合法档位口径一致：非 {0.5,1,1.5,2} 一律按 1 处理
        assert build_page_budget_block(0.8) == build_page_budget_block(1.0)
        assert build_page_budget_block(3) == build_page_budget_block(1.0)

    def test_deletion_rules_present(self):
        block = build_page_budget_block(1.0)
        assert "先裁过程性描述" in block
        assert "不得转移" in block
        assert "不要注水" in block
        # 反短路声明：小预算不得被模型误读为内容不足（实测曾触发「对话内容过短」兜底文案）
        assert "篇幅预算是人为的上限约束" in block
        assert "对话内容过短" in block


class TestGenerateSummaryWiring:
    def _dialogue(self):
        return [
            {"speaker_id": 0, "speaker_name": "张三", "text": "我们下周三发布新版本。", "sentences": [{"text": "我们下周三发布新版本。"}]},
            {"speaker_id": 1, "speaker_name": "李四", "text": "好的，我负责准备发布说明。", "sentences": [{"text": "好的，我负责准备发布说明。"}]},
            {"speaker_id": 0, "speaker_name": "张三", "text": "发布前跑一遍回归测试。", "sentences": [{"text": "发布前跑一遍回归测试。"}]},
        ]

    def _capture_system(self, monkeypatch, summarize, role_prompt=None):
        import core.agent_workspace as agent_workspace
        monkeypatch.setattr(agent_workspace, "get_role_summary_prompt", lambda: role_prompt)
        captured = {}

        def fake_chat_completion(messages, model=None, **kwargs):
            captured["system"] = messages[0]["content"]
            return "# 纪要\n（测试输出）"

        monkeypatch.setattr(summarize, "chat_completion", fake_chat_completion)
        return captured

    def test_default_factor_appends_block(self, settings_file, monkeypatch):
        import core.summarize as summarize
        captured = self._capture_system(monkeypatch, summarize)
        summarize.generate_summary(self._dialogue(), model="qwen-plus")
        assert summarize.build_page_budget_block(1.0) in captured["system"]

    def test_explicit_factor_injected(self, settings_file, monkeypatch):
        import core.summarize as summarize
        captured = self._capture_system(monkeypatch, summarize)
        summarize.generate_summary(self._dialogue(), model="qwen-plus", one_page_factor=2.0)
        assert "约 1800 字" in captured["system"]

    def test_role_template_path_also_gets_block(self, settings_file, monkeypatch):
        """Agent 角色模板路径与硬编码基座同点位追加，两条路径口径一致。"""
        import core.summarize as summarize
        captured = self._capture_system(monkeypatch, summarize, role_prompt="ROLE_TEMPLATE_BASE")
        summarize.generate_summary(self._dialogue(), model="qwen-plus", one_page_factor=0.5)
        assert captured["system"].startswith("ROLE_TEMPLATE_BASE")
        assert "仅保留一、二、三节" in captured["system"]


class TestPipelinePlumbing:
    def test_stage2_signature_accepts_factor(self):
        """run_pipeline_stage2 暴露 one_page_factor 参数（缺省 1.0，向后兼容）。"""
        import inspect

        from core.pipeline import run_pipeline_stage2
        sig = inspect.signature(run_pipeline_stage2)
        assert "one_page_factor" in sig.parameters
        assert sig.parameters["one_page_factor"].default == 1.0
