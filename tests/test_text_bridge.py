"""
tests/test_text_bridge.py — 文本桥接匹配域冒烟测试

覆盖文本归一化、相似度计算、桥接匹配逻辑、输入校验边界。
从 test_smoke.py 拆分而来。

运行方式：
  pytest tests/test_text_bridge.py -v
"""

import pytest
from fastapi.testclient import TestClient

from app.server import app


@pytest.fixture
def client():
    """创建测试客户端"""
    with TestClient(app) as c:
        yield c


# ============================================================
# 文本桥接匹配（core/text_bridge.py）
# ============================================================

class TestNormalizeText:
    """_normalize_text 去除空白字符"""

    def test_remove_spaces(self):
        from core.text_bridge import _normalize_text
        assert _normalize_text("hello world") == "helloworld"
        assert _normalize_text("  你好  世界  ") == "你好世界"

    def test_empty_string(self):
        from core.text_bridge import _normalize_text
        assert _normalize_text("") == ""
        assert _normalize_text("   ") == ""


class TestTextSimilarity:
    """_text_similarity 文本相似度计算"""

    def test_exact_match(self):
        from core.text_bridge import _text_similarity
        assert _text_similarity("完全相同的文本", "完全相同的文本") == 1.0

    def test_high_similarity(self):
        from core.text_bridge import _text_similarity
        # 仅差一两个字
        sim = _text_similarity("今天讨论预算方案", "今天讨论预算方案吧")
        assert sim > 0.75

    def test_low_similarity(self):
        from core.text_bridge import _text_similarity
        sim = _text_similarity("今天天气很好", "股票市场大跌")
        assert sim < 0.5

    def test_empty_input(self):
        from core.text_bridge import _text_similarity
        assert _text_similarity("", "有内容") == 0.0
        assert _text_similarity("有内容", "") == 0.0
        assert _text_similarity("", "") == 0.0

    def test_length_ratio_filter(self):
        from core.text_bridge import _text_similarity
        # 长度差异超过 70% 时直接返回 0
        sim = _text_similarity("abc", "这是一段非常长的中文文本内容")
        assert sim == 0.0


class TestTextBridgeMatch:
    """text_bridge_match 核心匹配逻辑"""

    def _make_realtime(self, speaker_id, texts):
        """构造实时全量转写记录"""
        return [{"speaker_id": speaker_id, "text": t, "begin_time": i * 1000, "end_time": (i + 1) * 1000}
                for i, t in enumerate(texts)]

    def _make_dialogue(self, mappings):
        """构造批处理对话稿。mappings: {speaker_id: [text, ...]}"""
        dialogue = []
        for sid, texts in mappings.items():
            sentences = [{"text": t, "begin_time": i * 1000, "end_time": (i + 1) * 1000}
                         for i, t in enumerate(texts)]
            dialogue.append({"speaker_id": sid, "sentences": sentences})
        return dialogue

    def test_empty_inputs(self):
        from core.text_bridge import text_bridge_match
        results, mapping = text_bridge_match([], {}, [])
        assert results == [] and mapping == {}

    def test_no_bindings(self):
        from core.text_bridge import text_bridge_match
        rt = self._make_realtime(0, ["测试文本内容"])
        results, mapping = text_bridge_match(rt, {}, self._make_dialogue({0: ["测试文本内容"]}))
        assert results == [] and mapping == {}

    def test_perfect_match(self):
        """实时文本与批处理文本完全一致时正确匹配"""
        from core.text_bridge import text_bridge_match
        rt = self._make_realtime(0, ["讨论预算方案", "确认实施计划"])
        dialogue = self._make_dialogue({
            5: ["讨论预算方案", "其他内容"],
            6: ["无关话题"],
        })
        binding = {"0": "uuid-alice"}
        names = {"uuid-alice": "张三"}

        results, mapping = text_bridge_match(rt, binding, dialogue, names)
        assert len(results) == 1
        assert results[0].status == "matched"
        assert results[0].new_speaker_id == 5
        assert results[0].speaker_name == "张三"
        assert mapping[5] == "uuid-alice"

    def test_multiple_speakers_voting(self):
        """多位说话人各自独立匹配"""
        from core.text_bridge import text_bridge_match
        rt = (
            self._make_realtime(0, ["讨论预算方案", "确认实施计划", "审核财务报表"])
            + self._make_realtime(1, ["市场推广策略", "用户增长方案"])
        )
        dialogue = self._make_dialogue({
            3: ["讨论预算方案", "确认实施计划", "审核财务报表"],
            4: ["市场推广策略", "用户增长方案"],
        })
        binding = {"0": "uuid-alice", "1": "uuid-bob"}

        results, mapping = text_bridge_match(rt, binding, dialogue)
        assert len(results) == 2
        matched = [r for r in results if r.status == "matched"]
        assert len(matched) == 2
        assert mapping.get(3) == "uuid-alice"
        assert mapping.get(4) == "uuid-bob"

    def test_no_match_when_texts_differ(self):
        """实时文本与批处理文本完全不同时无匹配"""
        from core.text_bridge import text_bridge_match
        rt = self._make_realtime(0, ["今天天气很好"])
        dialogue = self._make_dialogue({0: ["股票市场大跌"]})
        binding = {"0": "uuid-alice"}

        results, mapping = text_bridge_match(rt, binding, dialogue)
        assert len(results) == 1
        assert results[0].status == "unmatched"
        assert mapping == {}

    def test_short_text_filtered(self):
        """过短的文本（< MIN_TEXT_LENGTH）被过滤不参与匹配"""
        from core.text_bridge import text_bridge_match
        rt = self._make_realtime(0, ["好", "嗯"])
        dialogue = self._make_dialogue({0: ["好", "嗯"]})
        binding = {"0": "uuid-alice"}

        results, mapping = text_bridge_match(rt, binding, dialogue)
        # 所有文本都短于 MIN_TEXT_LENGTH=4，无有效文本
        assert results == [] and mapping == {}

    def test_to_dict_output(self):
        """TextBridgeMatchResult.to_dict() 输出格式正确"""
        from core.text_bridge import TextBridgeMatchResult
        result = TextBridgeMatchResult(
            old_speaker_id=0,
            speaker_uuid="uuid-test",
            speaker_name="测试人",
            new_speaker_id=3,
            confidence=0.8567,
            hit_count=5,
            best_similarity=0.9234,
            status="matched",
        )
        d = result.to_dict()
        assert d["confidence"] == 0.857  # 四舍五入到 3 位
        assert d["best_similarity"] == 0.923
        assert d["status"] == "matched"
        assert d["new_speaker_id"] == 3


# ============================================================
# 输入校验边界测试
# ============================================================

class TestInputValidationSpeaker:
    """说话人名称长度限制"""

    def test_speaker_name_too_long(self, client):
        """名称超过 100 字返回 422"""
        resp = client.post("/api/speakers", json={"name": "A" * 101})
        assert resp.status_code == 422

    def test_speaker_name_empty_string(self, client):
        """空字符串名称返回 400（业务层校验）"""
        resp = client.post("/api/speakers", json={"name": ""})
        assert resp.status_code in (400, 422)


class TestInputValidationHotwords:
    """热词接口 Pydantic 模型校验"""

    def test_hotwords_save_accepts_valid_input(self, client):
        """正常热词保存应成功"""
        resp = client.post("/api/hotwords", json={"hotwords": "热词A\n热词B"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

    def test_hotwords_save_rejects_oversized_input(self, client):
        """超大文本应被 Pydantic 拒绝（422）"""
        resp = client.post("/api/hotwords", json={"hotwords": "A" * 50001})
        assert resp.status_code == 422
