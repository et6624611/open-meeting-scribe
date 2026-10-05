"""
core/text_bridge.py — 文本桥接匹配（说话人绑定体验闭环 P0） / Text bridge matching (speaker binding experience loop P0)

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-07
版本 / Version: 1.0.0

职责 / Responsibilities:
  利用实时绑定阶段产出的文本内容（确定性证据），在批处理转写结果中 / Use text content from realtime binding (deterministic evidence) to search in batch transcription results
  搜索相同或高度相似的文本片段，从而继承说话人绑定关系 / for identical or highly similar text fragments, inheriting speaker binding relationships.

核心洞察 / Core insight:
  实时绑定与批处理是两条独立管线，speaker_id 无法直接对齐 / Realtime binding and batch processing are independent pipelines; speaker_ids cannot be directly aligned.
  但用户在实时阶段绑定的说话人「说了什么文本」是确定性证据—— / But "what text did the bound speaker say" from realtime binding is deterministic evidence —
  这些文本在批处理结果中仍可被搜索到，看它们被归到了哪个新 / These texts can still be found in batch results; by checking which new
  speaker_id，即可继承绑定关系 / speaker_id they belong to, we can inherit the binding.

匹配策略 / Matching strategy:
  1. 从实时全量转写中提取已绑定说话人的所有文本片段 / Extract all text fragments of bound speakers from realtime full transcription
  2. 在批处理 dialogue 中逐句搜索相似文本（字符级模糊匹配） / Search similar text sentence-by-sentence in batch dialogue (character-level fuzzy matching)
  3. 按命中次数投票，确定每个已绑定说话人对应的新 speaker_id
  4. 匹配置信度由文本相似度 × 命中数量共同决定

依赖：
  - difflib.SequenceMatcher（字符级模糊匹配）
"""

import logging
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 配置常量
# ============================================================

# 文本相似度阈值（SequenceMatcher.ratio() ≥ 此值视为匹配）
SIMILARITY_THRESHOLD = 0.75

# 参与匹配的文本最短长度（字符数），过短的文本容易产生误匹配
MIN_TEXT_LENGTH = 4

# 单个说话人至少需要的命中次数（避免单次巧合匹配）
MIN_HIT_COUNT = 1

# 匹配优势下限（最佳候选命中数 - 次优候选命中数 ≥ 此值才接受）
MIN_HIT_MARGIN = 0


@dataclass
class TextBridgeMatchResult:
    """文本桥接匹配结果"""
    old_speaker_id: int                        # 实时阶段的 speaker_id
    speaker_uuid: str                          # 绑定的说话人 UUID
    speaker_name: str                          # 说话人姓名
    new_speaker_id: Optional[int] = None       # 批处理阶段匹配到的新 speaker_id
    confidence: float = 0.0                    # 匹配置信度（0~1）
    hit_count: int = 0                         # 文本命中次数
    best_similarity: float = 0.0               # 最佳文本相似度
    status: str = "unmatched"                  # matched / unmatched / no_realtime_text

    def to_dict(self) -> dict:
        return {
            "old_speaker_id": self.old_speaker_id,
            "speaker_uuid": self.speaker_uuid,
            "speaker_name": self.speaker_name,
            "new_speaker_id": self.new_speaker_id,
            "confidence": round(self.confidence, 3),
            "hit_count": self.hit_count,
            "best_similarity": round(self.best_similarity, 3),
            "status": self.status,
        }


def _normalize_text(text: str) -> str:
    """
    文本标准化：去除空白、统一大小写（中文无影响）。

    实时 ASR 与批处理 ASR 的输出可能有细微差异（空格、标点），
    标准化后比较更鲁棒。
    """
    return "".join(text.split())


def _text_similarity(a: str, b: str) -> float:
    """
    计算两段文本的相似度（0~1）。

    使用 SequenceMatcher 的 ratio()，对中文按字符级比较。
    """
    na, nb = _normalize_text(a), _normalize_text(b)
    if not na or not nb:
        return 0.0
    # 长度差异过大时直接返回低分（避免 O(n*m) 开销）
    len_ratio = min(len(na), len(nb)) / max(len(na), len(nb))
    if len_ratio < 0.3:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def text_bridge_match(
    realtime_full_transcript: list[dict],
    realtime_speaker_binding: dict[str, str],
    dialogue: list[dict],
    speaker_names: Optional[dict[str, str]] = None,
) -> tuple[list[TextBridgeMatchResult], dict[int, str]]:
    """
    文本桥接匹配：利用实时阶段的文本证据继承绑定关系。

    算法：
      1. 从实时全量转写中，按 old_speaker_id 分组提取文本片段
         （仅取已绑定的说话人）
      2. 遍历批处理 dialogue 中的每句话，与每个已绑定说话人的
         文本片段比较相似度
      3. 对每个已绑定说话人，统计各 new_speaker_id 的命中次数
         （相似度 ≥ SIMILARITY_THRESHOLD 视为命中）
      4. 命中次数最多且有优势的 new_speaker_id 作为匹配结果

    Args:
        realtime_full_transcript: 实时全量转写记录
            [{text, speaker_id, speaker_name, begin_time, end_time}, ...]
        realtime_speaker_binding: 实时阶段的说话人绑定
            {"speaker_id(str)": speaker_uuid, ...}
        dialogue: 批处理转写结果的对话稿
            [{speaker_id, sentences: [{text, begin_time, end_time}]}, ...]
        speaker_names: {speaker_uuid: name} 说话人姓名映射（可选）

    Returns:
        (results_list, auto_mapping)
        - results_list: 每位已绑定说话人的匹配结果
        - auto_mapping: {new_speaker_id(int): speaker_uuid} 自动映射
    """
    if not realtime_full_transcript or not realtime_speaker_binding:
        return [], {}

    if speaker_names is None:
        speaker_names = {}

    # ── Step 1: 按 old_speaker_id 分组提取实时文本 ──────────
    # {old_speaker_id(int): [text, ...]}
    realtime_texts: dict[int, list[str]] = {}
    for entry in realtime_full_transcript:
        sid = entry.get("speaker_id")
        text = entry.get("text", "").strip()
        if sid is None or not text or len(text) < MIN_TEXT_LENGTH:
            continue
        realtime_texts.setdefault(sid, []).append(text)

    # 仅处理已绑定的说话人
    bound_sids: dict[int, str] = {}  # {old_speaker_id: speaker_uuid}
    for sid_str, uuid in realtime_speaker_binding.items():
        try:
            sid_int = int(sid_str)
        except (TypeError, ValueError):
            continue
        if sid_int in realtime_texts:
            bound_sids[sid_int] = uuid

    if not bound_sids:
        logger.info("[文本桥接] 无已绑定的说话人有实时文本，跳过匹配")
        return [], {}

    # ── Step 2: 展开批处理 dialogue 为 (new_speaker_id, text) 列表 ──
    batch_sentences: list[tuple[int, str]] = []
    for item in dialogue:
        new_sid = item.get("speaker_id", 0)
        for sent in item.get("sentences", []):
            text = sent.get("text", "").strip()
            if text and len(text) >= MIN_TEXT_LENGTH:
                batch_sentences.append((new_sid, text))

    if not batch_sentences:
        logger.info("[文本桥接] 批处理对话稿为空，跳过匹配")
        return [], {}

    # ── Step 3: 对每位已绑定说话人，统计各 new_speaker_id 的命中 ──
    results: list[TextBridgeMatchResult] = []
    auto_mapping: dict[int, str] = {}

    for old_sid, speaker_uuid in bound_sids.items():
        texts = realtime_texts[old_sid]
        # BE-R1/R3：不落 Speaker 编号兑底；档案名读取侧归一（绑定位正常路径必有真名，此为防御）
        from core.speakers import normalize_speaker_name
        speaker_name = normalize_speaker_name(speaker_names.get(speaker_uuid))

        # {new_speaker_id: {"hits": count, "best_sim": float}}
        hit_stats: dict[int, dict] = {}

        for rt_text in texts:
            best_match_sid = None
            best_match_sim = 0.0

            for new_sid, batch_text in batch_sentences:
                sim = _text_similarity(rt_text, batch_text)
                if sim >= SIMILARITY_THRESHOLD:
                    if sim > best_match_sim:
                        best_match_sim = sim
                        best_match_sid = new_sid

            if best_match_sid is not None:
                stats = hit_stats.setdefault(best_match_sid, {"hits": 0, "best_sim": 0.0})
                stats["hits"] += 1
                stats["best_sim"] = max(stats["best_sim"], best_match_sim)

        # ── Step 4: 确定匹配结果 ──────────────────────────
        if not hit_stats:
            results.append(TextBridgeMatchResult(
                old_speaker_id=old_sid,
                speaker_uuid=speaker_uuid,
                speaker_name=speaker_name,
                status="unmatched",
            ))
            continue

        # 按命中次数降序排列
        sorted_hits = sorted(hit_stats.items(), key=lambda x: x[1]["hits"], reverse=True)
        best_new_sid, best_stats = sorted_hits[0]
        best_hit_count = best_stats["hits"]
        second_hit_count = sorted_hits[1][1]["hits"] if len(sorted_hits) > 1 else 0
        hit_margin = best_hit_count - second_hit_count

        # 接受准则：命中次数 ≥ MIN_HIT_COUNT 且有优势
        if best_hit_count >= MIN_HIT_COUNT and hit_margin >= MIN_HIT_MARGIN:
            # 置信度 = 命中率（命中次数 / 总文本数）× 最佳相似度
            hit_rate = best_hit_count / max(len(texts), 1)
            confidence = hit_rate * best_stats["best_sim"]

            results.append(TextBridgeMatchResult(
                old_speaker_id=old_sid,
                speaker_uuid=speaker_uuid,
                speaker_name=speaker_name,
                new_speaker_id=best_new_sid,
                confidence=confidence,
                hit_count=best_hit_count,
                best_similarity=best_stats["best_sim"],
                status="matched",
            ))
            auto_mapping[best_new_sid] = speaker_uuid
        else:
            results.append(TextBridgeMatchResult(
                old_speaker_id=old_sid,
                speaker_uuid=speaker_uuid,
                speaker_name=speaker_name,
                hit_count=best_hit_count,
                best_similarity=best_stats["best_sim"],
                status="unmatched",
            ))

    matched_count = sum(1 for r in results if r.status == "matched")
    logger.info(
        f"[文本桥接] 匹配完成: {len(results)} 位已绑定说话人, "
        f"{matched_count} 位命中（阈值={SIMILARITY_THRESHOLD}）"
    )
    return results, auto_mapping
