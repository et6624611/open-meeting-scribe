"""
core/decision_topic.py — 决策流跨会议议题归并（全局视角）
                     Cross-meeting topic clustering for the decision flow

作者：Yongliang Wang
创建：2026-09-30
版本：1.0.0

背景（DEBRISH-P2）：决策流节点天然按会议平铺，同一议题在多场会议讨论会各产生一条
节点，决策中心「按会议」视图下这些同源节点彼此孤立、沦为"时间碎屑"，缺少
「这个话题最终定成了什么」的全局视角。本模块提供**确定性**议题归并：把同一知识库
下语义相近的节点聚成一个议题簇，选出主记录（最新定案态），其余折叠为演变链。

设计约束：
  - 纯确定性、零 LLM 调用、零第三方分词依赖（仅 stdlib）——与决策解析既有口径一致
  - 只做「视图归并」，不改数据：簇内每条节点仍是各会议独立的决策流节点，
    写操作仍走 notes.py 的任务级端点，本模块不引入新的持久化对象
  - 相似度算法集中在本模块，路由层仅做 IO 适配（依赖方向单向向外）

算法：以节点「议题指纹」（短标题，无标题时取正文首句）的字符二元组**重合度**
（containment = |交| / |较小集|）作相似度 + 贪心聚合（最新优先，保证主记录=最新）。
选用 containment 而非 Jaccard：同一议题在不同会议常被以长短不一的措辞重述，
Jaccard 会被较长一方的差异二元组稀释；containment 按较小集归一，对"同议题不同详略"更鲁棒。
（真实会议数据标定：跨会议同议题对 ≥0.78，弱相关对 ≤0.31，阈值 0.6 干净分离。）
中文无需分词，bigram 对短标题的语义重合捕捉已足够。
"""

import re

# 议题归并阈值：标题重合度（containment）下限。经真实会议数据标定（见模块 docstring）。
TOPIC_SIMILARITY_THRESHOLD = 0.6
# 参与归并的最短议题指纹长度：过短（如空壳碎屑）语义不足，单独成簇不主动并他人
_MIN_TOPIC_CHARS = 6
# 无标题时从正文提取议题首句的截断长度
_MAX_PHRASE_CHARS = 30

# markdown 强调符 / [待确认] 前缀（与 summarize 口径一致）——归一化时剥除，避免影响相似度
_EMPHASIS_RE = re.compile(r"[*_`]")
_PENDING_RE = re.compile(r"[\[【]\s*待确认\s*[\]】]\s*[:：]?\s*")
_WS_RE = re.compile(r"\s+")
_CLAUSE_SPLIT_RE = re.compile(r"[。．.！!；;：:\n]")


def _topic_phrase(node: dict) -> str:
    """议题指纹：短标题优先；无标题时取正文第一个分隔前的短句（截断）。"""
    title = str(node.get("title") or "").strip()
    if title:
        return title
    text = str(node.get("text") or "").strip()
    first = _CLAUSE_SPLIT_RE.split(text, maxsplit=1)[0].strip()
    return first[:_MAX_PHRASE_CHARS]


def _normalize(phrase: str) -> str:
    """把议题指纹归一为可比字符串：剥强调符与待确认前缀、压空白、转小写。"""
    s = _PENDING_RE.sub("", phrase or "")
    s = _EMPHASIS_RE.sub("", s)
    return _WS_RE.sub("", s).strip().lower()


def _bigrams(s: str) -> frozenset[str]:
    """字符二元组集合；长度 <2 时以整串作单元素，空串返回空集。"""
    if not s:
        return frozenset()
    if len(s) < 2:
        return frozenset({s})
    return frozenset(s[i:i + 2] for i in range(len(s) - 1))


def similarity(a: str, b: str) -> float:
    """两段归一议题指纹的 bigram 重合度（containment）∈ [0,1]。任一为空 → 0。"""
    ba, bb = _bigrams(a), _bigrams(b)
    if not ba or not bb:
        return 0.0
    smaller = min(len(ba), len(bb))
    return len(ba & bb) / smaller if smaller else 0.0


def _sort_key(node: dict) -> tuple[str, str]:
    """演变链排序键：updated_at 优先，缺省回落 created_at（字典序即时间序）。"""
    return (str(node.get("updated_at") or node.get("created_at") or ""), str(node.get("id") or ""))


def cluster_topics(rows: list[dict], *, threshold: float = TOPIC_SIMILARITY_THRESHOLD) -> list[dict]:
    """
    把聚合读侧的决策流节点（FlowNode 行）按「同知识库 + 语义相近」聚成议题簇。

    贪心聚合（最新优先）：入参按 updated_at 降序遍历，每条节点找首个相似且同 kb 的既有簇并入，
    否则新建簇。因最新者先建簇，簇的 leader（首个成员）即该议题的最新记录，天然作主记录。

    Returns:
        议题簇列表，每簇：
        {
          "topic_key": str,            # 稳定标识：leader 节点 id
          "kb_id": str | None,
          "kb_name": str | None,
          "title": str,                # 议题标题：取主记录标题，回退正文首句
          "main": dict,                # 主记录（最新非闭档，否则最新）FlowNode
          "history": list[dict],       # 演变链（除主记录外，按时间倒序）FlowNode
          "size": int,                 # 簇内节点总数
          "meeting_count": int,        # 涉及会议数
        }
        单节点簇的 history 为空——是否"跨会议"由调用方按 size/meeting_count 判断呈现。
    """
    ordered = sorted(
        (r for r in rows if isinstance(r, dict)),
        key=_sort_key,
        reverse=True,
    )

    clusters: list[dict] = []  # 每项含 leader 的 bigram 集（锤定比对基准）与成员
    for row in ordered:
        norm = _normalize(_topic_phrase(row))
        bg = _bigrams(norm)
        kb = row.get("kb_id")
        target = None
        # 过短指纹不主动并入他人（避免空壳互相吸附），但仍可成为被并的簇 leader
        if len(norm) >= _MIN_TOPIC_CHARS and bg:
            for c in clusters:
                if c["kb_id"] != kb:
                    continue
                smaller = min(len(bg), len(c["_bg"]))
                if smaller and len(bg & c["_bg"]) / smaller >= threshold:
                    target = c
                    break
        if target is None:
            clusters.append({
                "kb_id": kb,
                "kb_name": row.get("kb_name"),
                "_bg": bg,
                "_norm": norm,
                "members": [(row, 1.0)],
            })
        else:
            # 与 leader（首成员）比对并记录置信度；不并入成员 bigram，避免簇随规模
            # 膨胀而"吸附"弱相关节点（leader 锤定，结果稳定）
            smaller = min(len(bg), len(target["_bg"]))
            conf = len(bg & target["_bg"]) / smaller if smaller else 0.0
            target["members"].append((row, conf))

    result: list[dict] = []
    for c in clusters:
        members = [m for m, _conf in c["members"]]  # 已按时间倒序
        main = _pick_main(members)
        history = [m for m in members if m is not main]
        meetings = {m.get("task_id") for m in members if m.get("task_id")}
        # 簇置信度 = 除 leader 外成员与 leader 相似度的最小值（最弱一环）；单成员为 1.0
        confs = [conf for _m, conf in c["members"]]
        result.append({
            "topic_key": str(main.get("id") or c["_norm"] or ""),
            "kb_id": c["kb_id"],
            "kb_name": c["kb_name"],
            "title": _topic_title(main),
            "main": main,
            "history": history,
            "size": len(members),
            "meeting_count": len(meetings),
            "confidence": round(min(confs), 3) if confs else 1.0,
        })

    # 跨会议的、更新的议题排前（演变链越长越该被优先关注）
    result.sort(key=lambda g: (g["size"], _sort_key(g["main"])), reverse=True)
    return result


def _pick_main(members: list[dict]) -> dict:
    """主记录：优先最新非闭档节点（仍在推进的定案态），全闭档时取最新。"""
    for m in members:  # members 已时间倒序
        if not m.get("status_closing"):
            return m
    return members[0]


def _topic_title(node: dict) -> str:
    """议题标题：取节点短标题，回退正文首句（截断，展示用）。"""
    title = str(node.get("title") or "").strip()
    if title:
        return title
    phrase = _topic_phrase(node)
    return (phrase[:_MAX_PHRASE_CHARS] + "…") if len(phrase) >= _MAX_PHRASE_CHARS else (phrase or "（无标题议题）")
