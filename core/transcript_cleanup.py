"""
core/transcript_cleanup.py — 转写口语清理（确定性规则，非 AI）

职责 / Responsibilities:
  在 ASR 原文之上派生「清理版」：去掉话语标记（嗯 / 呃 / 那个 / you know …）、
  合并口吃与相邻重复、整理标点。纯函数、无 I/O、无随机、离线可用、结果可复现。

边界（v1 硬约束，测试钉死）/ Hard boundaries:
  - 只处理「话语标记位置」的填充词：句首 / 标点之后、且后随标点或句尾。
    「那个孩子」「就是这个意思」中的限定 / 强调用法不匹配，不删。
  - 不碰否定（不 / 没 / 别 / 不是）、不碰自我纠正链（X，哦不对，Y）、
    不碰句尾情态词（吧 / 可能 / 应该 / 也许；好啊 / 行吧）。
  - 不重组语序、不改数字 / 日期 / 人名 / 专名。
  - 幂等：clean(clean(x)) == clean(x)。

事实源原则 / Source of truth:
  本模块只「派生」，永不持有原文。调用方负责保证 task.dialogue 与实时缓存
  仍是原文事实源（转写文本分层方案 §1 文本流向表）。
"""

from __future__ import annotations

import copy
import re

# ───────────────────────── 词表 ─────────────────────────

# 单字语气词：必须独立成标记（前为句首/标点，后为标点/句尾）。
# 不放「吧」：句尾情态词是态度证据（行吧 ≠ 行）。
# 「哦」不入表：自我纠正链「哦不对」必须整段保留。
MONO_FILLERS = "嗯呃诶哎唉啊呀嘛"

# 多字填充词（中文）：同样要求独立标记位置（后随标点/句尾）。
# 「就是说」几乎无实义，允许后不跟标点（句首发语），见 _FILLER_LEAD_RE。
# 不放「然后」：高频合法连接词，误杀代价高。
MULTI_FILLERS = ["怎么说呢", "你懂吧", "那个", "这个", "就是", "对吧"]
LEAD_FILLERS = ["就是说"]  # 句首/标点后即删，不要求后随标点

# 英文：独立单词（ASCII 邻接边界）
EN_WORD_FILLERS = ["uh", "um", "erm", "er", "ah"]
# 英文：插入语（必须两侧停顿边界，I like apples 不匹配）
EN_INSERT_FILLERS = ["you know", "i mean", "like", "sort of", "kind of"]

# 停顿边界：中英文标点 / 省略号 / 破折号 / 空白
_BOUND = r"，。！？、；：…—,.!?;:\s"
_BOUND_CLASS = f"[{_BOUND}]"
_PREV_BOUND = rf"(?:^|(?<=[{_BOUND}]))"
_NEXT_BOUND = rf"(?=[{_BOUND}]|$)"
# 严格标点边界（不含空白）：英文插入语必须逗号环绕，"I like apples" 不匹配
_PUNCT_BOUND = r"，。！？、；：…—,.!?;:"
_PREV_PUNCT = rf"(?:^|(?<=[{_PUNCT_BOUND}]))"
_NEXT_PUNCT = rf"(?=[{_PUNCT_BOUND}]|$)"

# 单字：前边界 + 单字 + 后必须停顿
_MONO_RE = re.compile(
    rf"{_PREV_BOUND}[{MONO_FILLERS}]{_NEXT_BOUND}"
)
# 句尾语气助词（中文字之后、句末标点/句尾）：好啊 / 定在十点啊 / Paraformer 嘛（空格边界已被上一规则覆盖）
# 不放「吧」：行吧是态度证据。
_FINAL_RE = re.compile(
    rf"(?<=[一-鿿])[{MONO_FILLERS}](?=[。！？!?]*$)"
)
# 多字独立标记：前边界 + 词 + 后必须停顿（长词优先，避免「怎么说呢」被别的规则切碎）
_MULTI_RE = re.compile(
    rf"{_PREV_BOUND}(?:{'|'.join(sorted(MULTI_FILLERS, key=len, reverse=True))}){_NEXT_BOUND}"
)
# 发语词：前边界即可（后不要求停顿）
_LEAD_RE = re.compile(
    rf"{_PREV_BOUND}(?:{'|'.join(sorted(LEAD_FILLERS, key=len, reverse=True))})"
)
# 英文独立单词（非字母邻接，大小写不敏感）
_EN_WORD_RE = re.compile(
    r"(?<![A-Za-z])(?:" + "|".join(EN_WORD_FILLERS) + r")(?![A-Za-z])",
    re.IGNORECASE,
)
# 英文插入语：前导（句首/标点 + 可选空白）捕获保留，词后必须标点/句尾。
# 单词间空格不构成边界（I like apples 不匹配）。
_EN_INSERT_RE = re.compile(
    rf"(^|[{_PUNCT_BOUND}])\s*((?:{'|'.join(sorted(EN_INSERT_FILLERS, key=len, reverse=True))}))\s*(?=[{_PUNCT_BOUND}]|$)",
    re.IGNORECASE,
)

# 切分：捕获标点分隔符（含省略号整体）
_SPLIT_RE = re.compile(r"(…+|\.{3,}|[，。！？、；：—,.!?;:]+)")
# 连续停顿标点（省略号除外，省略号在归一阶段已成型）
_DUP_SEP_RE = re.compile(r"([，、,；;])[，、,；;]+")
# 三个以上句号 / 点号 → 省略号
_ELLIPSIS_RE = re.compile(r"(?:。{3,}|\.{3,}|…+)")
# 片段边缘空白
_TRIM_RE = re.compile(r"^[\s]+|[\s]+$")


def _overlap_len(a: str, b: str) -> int:
    """a 的后缀与 b 的前缀的最长公共长度（0 表示不重叠）。"""
    upper = min(len(a), len(b))
    for length in range(upper, 1, -1):
        if a[-length:] == b[:length]:
            return length
    return 0


def clean_sentence(text: str) -> dict:
    """清理一句转写文本。

    返回 / Returns:
      {"text": str,            # 清理后文本（无变化时与输入相同）
       "changed": bool,
       "ops": [                 # 机器可读的处理明细（供前端回览）
         {"r": "filler", "n": int, "items": [被删词...]},
         {"r": "dup",    "n": int, "items": [被合并片段...]},
         {"r": "punct",  "n": int},
       ]}
    """
    if not text or not text.strip():
        return {"text": text or "", "changed": False, "ops": []}

    original = text
    ops: list[dict] = []

    # ── 1. 填充词：按「删除 → 计数」统一走，保留实际被删词形 ──
    removed: list[str] = []
    for pattern in (_MONO_RE, _FINAL_RE, _MULTI_RE, _LEAD_RE, _EN_WORD_RE):
        text = pattern.sub(lambda m: (removed.append(m.group(0).strip()), "")[1], text)
    # 英文插入语：保留前导标点（group1），只删词（group2）
    text = _EN_INSERT_RE.sub(
        lambda m: (removed.append(m.group(2).strip()), m.group(1))[1], text
    )
    if removed:
        ops.append({"r": "filler", "n": len(removed), "items": removed})

    # ── 2. 口吃 / 相邻重复：按标点切片后合并 ──
    # pieces 形态恒为 [seg, sep, seg, sep, …, seg]（sep 为捕获的标点）
    pieces = _SPLIT_RE.split(text)
    merged: list[str] = []
    dup_items: list[str] = []

    def _last_seg_idx() -> int:
        """merged 中最后一个非空片段的索引（片段恒在偶数位）。"""
        start = len(merged) - 1
        if start % 2:
            start -= 1
        for i in range(start, -1, -2):
            if merged[i] != "":
                return i
        return -1

    for tok in pieces:
        if tok is None:
            continue
        if _SPLIT_RE.fullmatch(tok):
            merged.append(tok)
            continue
        seg = _TRIM_RE.sub("", tok)
        if seg == "":
            # filler 删空的片段：占位空串，标点交给 punct 阶段合并
            merged.append("")
            continue

        prev_idx = _last_seg_idx()
        if prev_idx >= 0:
            prev = merged[prev_idx]
            sep_idx = prev_idx + 1  # prev 与其后片段之间的分隔符位置（若存在）
            if prev == seg:
                # 完全重复（下周三，下周三）：丢后者与其前导分隔符
                dup_items.append(seg)
                if len(merged) - 1 == sep_idx and _SPLIT_RE.fullmatch(merged[sep_idx]):
                    merged.pop()
                continue
            if len(prev) < len(seg) and seg.startswith(prev):
                # 前缀残段（得，得发出来）：prev 是被重述半句，置空残段
                dup_items.append(prev)
                merged[prev_idx] = ""
            elif len(prev) > len(seg) and prev.endswith(seg):
                # 后缀残段（下周三之前，下周三）：丢后者与其前导分隔符
                dup_items.append(seg)
                if len(merged) - 1 == sep_idx and _SPLIT_RE.fullmatch(merged[sep_idx]):
                    merged.pop()
                continue
            else:
                # 后缀-前缀重叠（我们下周三，下周三之前 → 我们下周三之前）
                overlap = _overlap_len(prev, seg)
                if overlap >= 2:
                    dup_items.append(seg[:overlap])
                    merged[prev_idx] = prev + seg[overlap:]  # 拼接为完整片段
                    if len(merged) - 1 == sep_idx and _SPLIT_RE.fullmatch(merged[sep_idx]):
                        merged[sep_idx] = ""  # 中间分隔符作废
                    continue
        merged.append(seg)
    if dup_items:
        ops.append({"r": "dup", "n": len(dup_items), "items": dup_items})

    # ── 3. 重组 + 标点整理 ──
    punct_hits = 0
    text = "".join(merged)

    new_text, n = _ELLIPSIS_RE.subn("……", text)
    punct_hits += n
    text = new_text

    # 连续停顿合一只留首个（往返多次，处理三段以上连号）
    while True:
        new_text, n = _DUP_SEP_RE.subn(r"\1", text)
        if n == 0:
            break
        punct_hits += n
        text = new_text
    # 停顿标点与句末标点相连时，删停顿侧（，。 → 。）
    new_text, n = re.subn(r"[，、,](?=[。！？!?])", "", text)
    punct_hits += n
    text = new_text
    # 去标点两侧空白：中文标点直接贴；ASCII 标点后接字母保留一个空格
    text = re.sub(r"\s*([，。！？、；：…—])\s*", r"\1", text)
    text = re.sub(
        r"(?<![\d])\s*([,;:.!?])\s*([A-Za-z]?)",
        lambda m: m.group(1) + (" " + m.group(2) if m.group(2) else ""),
        text,
    )
    # 句首标点剥离（含省略号：多为「嗯……」类 filler 删除后的悬挂残留）
    text = re.sub(r"^[，。！？、；：…—,.!?;:\s]+", "", text)
    text = text.strip()

    # 仅当标点整理真实改变了形态才计账（filler 删除产生的连号标点也算）
    if punct_hits and text != original:
        ops.append({"r": "punct", "n": punct_hits})

    return {"text": text, "changed": text != original.strip(), "ops": ops}


def clean_dialogue_for_consumers(dialogue: list[dict], *, enabled: bool) -> list[dict]:
    """为下游 LLM 消费者（纪要 / 标题 / 章节 / 实时摘要 / 翻译）准备对话稿。

    enabled=True：返回**深拷贝**，逐句把 text 替换为清理版；原 dialogue 不被触碰。
    enabled=False：原样返回同一对象（不拷贝，零行为变化）。

    清理后为空串的句子保留空文本（下游各自已有空句容忍；不删句，避免
    sentence_id 顺序与时间轴错位）。
    """
    if not enabled:
        return dialogue
    cloned = copy.deepcopy(dialogue)
    for block in cloned:
        if not isinstance(block, dict):
            continue
        for sent in block.get("sentences") or []:
            if isinstance(sent, dict) and isinstance(sent.get("text"), str):
                sent["text"] = clean_sentence(sent["text"])["text"]
    return cloned


def derive_layers(raw_text: str, *, enabled: bool) -> dict:
    """实时咽喉 / 回放共用的单句派生契约。

    返回 / Returns:
      {"clean_text": str | None,   # WS 附加字段；None = 不加该键
       "clean_ops": list | None,
       "feed_text": str}           # 下游摘要/章节/翻译输入（纯语气词句可能为空串，调用方跳过）

    enabled=False 时零行为变化：clean_* 为 None，feed_text 即原文。
    """
    if not enabled:
        return {"clean_text": None, "clean_ops": None, "feed_text": raw_text}
    result = clean_sentence(raw_text)
    if result["changed"]:
        return {
            "clean_text": result["text"],
            "clean_ops": result["ops"],
            "feed_text": result["text"],
        }
    return {"clean_text": None, "clean_ops": None, "feed_text": raw_text}


def enrich_sentence(sentence: dict) -> dict:
    """展示边界富化：原地附加 clean_text / clean_ops，返回同一 dict。

    - 无文本或清理无变化：不加 clean_text 键（前端按缺省＝原文处理）；
    - 调用方需先判断清理开关是否启用；本函数只做派生，不读设置。
    """
    text = sentence.get("text")
    if not isinstance(text, str) or not text.strip():
        return sentence
    result = clean_sentence(text)
    if result["changed"]:
        sentence["clean_text"] = result["text"]
        sentence["clean_ops"] = result["ops"]
    return sentence
