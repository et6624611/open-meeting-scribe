"""转写响应瘦身 / Transcript response slimming.

句级 words（词级时间戳）占 dialogue 序列化体积约 88%，前端不消费；
仅在响应层剔除，绝不写回内存 task / 磁盘。 /
Sentence-level `words` (word timings) is ~88% of the serialized dialogue size and
is never consumed by the frontend; stripped at the response layer only, never
written back to the in-memory task or disk.
"""


def drop_word_timings(dialogue: list) -> None:
    """原地剔除 sentences[].words；只删该键，不动 text / 时间码 / speaker。

    In-place removal of `sentences[].words`; nothing else is touched.
    """
    for block in dialogue or []:
        if not isinstance(block, dict):
            continue
        for sentence in block.get("sentences") or []:
            if isinstance(sentence, dict):
                sentence.pop("words", None)
