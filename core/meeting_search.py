"""跨会议关键词检索（提问范围的唯一检索器）。

问答与智能体两条链路都只通过 ``build_scope_context`` 获取检索结果，
避免为两种模式各维护一套检索口径。纯关键词 + 中文 bigram + IDF，不引入向量库。

契约见 docs/specs/context-asset-management/spec.md：
  - 可检索集合统一入口 ``_eligible_tasks``（权限 / 生命周期 / 内容就绪）
  - 候选数 ``candidates`` / 相关数 ``matched`` / 注入数 ``injected`` 三计数分离
  - 时间、项目、排除本场在打分前过滤
  - 每个实际注入片段都带确定性 ``evidence`` 锚点
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from typing import Any

from core.chat_context import task_final_summary
from core.decision_flow import status_of
from core.decision_status import load_statuses
from core.decision_topic import cluster_topics
from core.task_store import tasks
from core.time_query import in_range, parse_time_range

logger = logging.getLogger(__name__)

SCOPES = ("meeting", "all")
DEFAULT_SCOPE = "meeting"
# 结构化检索块起始标记（chat_stream 复用时按前缀识别）
SCOPE_BLOCK_HEADER = "<retrieval"
# 后端已核验统计块起始标记（聚合查询没有检索块，智能体需同样拿到）
FACTS_BLOCK_HEADER = "<verified_facts"

# 相关度阈值：默认 score >= 3.0 才计入 matched。单个泛词即使多字段命中也不得过阈值。
MATCH_THRESHOLD = 3.0
# 注入字符预算：limit=None 时仅按此预算截断
INJECT_MAX_CHARS = 6000
# 每场片段数上限
MAX_SNIPPETS = 4
# 薄清单单页上限（工具入参上限，防一次拉全库）
LIST_MAX_LIMIT = 50
# 薄清单命中过多时的收窄提示阈值
LIST_NARROW_HINT_TOTAL = 60
# 注入块里「未展开命中」最多列出场数（只给标题/日期/id，不占主证据预算）
DROPPED_PREVIEW_MAX = 30

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[a-z0-9]+")
_DECISION_INTENT_RE = re.compile(r"决定|拍板|采用|启用|决议|通过|同意|结论|定下来")
_CURRENT_DECISION_RE = re.compile(r"当前|最新|最终|怎么定|定了|定案|拍板")
_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "我", "你", "他", "这", "那",
    "什么", "如何", "怎么", "为什么", "呢", "吗", "吧", "啊", "嘛", "哦", "嗯", "呀",
    "a", "an", "the", "is", "are", "of",
}
# 时间词不参与关键词打分（时间由 parse_time_range 承担硬过滤）
_TIME_NOISE_RE = re.compile(
    r"本月|这个月|当月|上个月|上月|本季度|这季度|上季度|本周|这周|上周|"
    r"最近\s*\d+\s*[次场天]|近\s*\d+\s*[次场天]|\d{4}\s*[-/年]\s*\d{1,2}\s*月?|"
    r"\d{1,2}\s*月份?"
)
# 泛词：本身不携带检索意图。先剔除再生成 bigram，避免「目相」「关有」「键决」
# 这类短语碎片拿到高 IDF，把泛词组合推过阈值（141 事故的直接成因）。
_GENERIC_TERMS = (
    "项目", "相关", "关键", "决策", "会议", "内容", "情况", "问题", "工作",
    "讨论", "安排", "计划", "进度", "需求", "方案", "哪些", "有哪", "什么",
    "怎么", "如何", "是否", "以及", "我们", "这个", "那个", "具体", "一下", "多少",
)


def normalize_scope(value: str | None) -> str:
    """缺省/非法一律回落本场会议。"""
    return value if value in SCOPES else DEFAULT_SCOPE


def _has_decision_intent(query: str) -> bool:
    """决策类提问：优先把决策项摆到证据最前。"""
    return bool(_DECISION_INTENT_RE.search(query or ""))


def _has_current_decision_intent(query: str) -> bool:
    """「当前 / 最新 / 最终怎么定」：只要有效主记录，已替代节点不得当结论。"""
    return bool(_CURRENT_DECISION_RE.search(query or ""))


def _query_terms(query: str) -> list[str]:
    """中文连续串 + bigram + 英文词，去时间词、泛词与停用词并保序去重。"""
    text = _TIME_NOISE_RE.sub(" ", (query or "").lower())
    for generic in _GENERIC_TERMS:
        text = text.replace(generic, " ")
    # 「与星瀚」的前缀连词不构成检索语义，剥离后避免「与星」这种碎片词反复计分
    text = re.sub(r"(^|\s)[与和跟同]", " ", text)
    terms: list[str] = []
    for run in _CJK_RE.findall(text):
        if len(run) >= 2:
            terms.extend(run[i:i + 2] for i in range(len(run) - 1))
            if run not in _STOPWORDS:
                terms.append(run)
    terms.extend(w for w in _WORD_RE.findall(text) if len(w) >= 2 and w not in _STOPWORDS)
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        if term in _STOPWORDS or term in seen:
            continue
        seen.add(term)
        ordered.append(term)
    return ordered


def _snippet(text: str, limit: int = 160) -> str:
    cleaned = " ".join(str(text or "").split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + "…"


def _meeting_date(task: dict) -> str:
    raw = task.get("meeting_date") or task.get("created_at") or ""
    return str(raw)[:10]


def _dialogue_entries(task: dict) -> list[dict]:
    """对话句子及其稳定定位索引（不迁移、不改写逐字稿）。"""
    entries: list[dict] = []
    for di, item in enumerate(task.get("dialogue") or []):
        if not isinstance(item, dict):
            continue
        for si, sentence in enumerate(item.get("sentences") or []):
            if not isinstance(sentence, dict):
                continue
            text = str(sentence.get("text") or "").strip()
            if not text:
                continue
            entry = {"text": text, "dialogue_index": di, "sentence_index": si}
            if sentence.get("begin_time") is not None:
                entry["begin_time"] = sentence.get("begin_time")
            if sentence.get("end_time") is not None:
                entry["end_time"] = sentence.get("end_time")
            entries.append(entry)
    return entries


def _decision_items(task: dict) -> list[dict]:
    return [d for d in (task.get("decisions") or []) if isinstance(d, dict)]


def _has_content(task: dict) -> bool:
    """内容就绪：标题、纪要、决策、对话至少有一项已持久化内容。"""
    if str(task.get("title") or task.get("audio_name") or "").strip():
        return True
    try:
        if str(task_final_summary(task) or "").strip():
            return True
    except Exception:  # noqa: BLE001 - 单场纪要异常不影响内容判定
        pass
    if any(str(d.get("text") or "").strip() for d in _decision_items(task)):
        return True
    return bool(_dialogue_entries(task))


def _is_deleted(task: dict) -> bool:
    """生命周期：已删除 / 回收站排除；已归档仍可只读检索。"""
    if task.get("deleted") or task.get("trashed") or task.get("is_trash"):
        return True
    return bool(task.get("deleted_at") or task.get("trashed_at"))


def _access_allows(task_id: str, task: dict, access_context: dict | None) -> bool:
    """访问判定：复用外部访问层，检索器不另写角色规则。

    access_context=None 仅允许既有单机本地路径。传入上下文却无法判定时 fail closed，
    绝不回退成全库读取。
    """
    if access_context is None:
        return True
    checker = access_context.get("can_access")
    if callable(checker):
        try:
            return bool(checker({**task, "task_id": task_id}))
        except Exception:  # noqa: BLE001 - 访问判定异常一律关闭访问
            logger.warning("[范围检索] 访问判定异常，按无权处理 task=%s", task_id)
            return False
    visible = access_context.get("visible_task_ids")
    if visible is not None:
        return task_id in set(visible)
    space_id = access_context.get("space_id")
    if space_id:
        return task.get("space_id") == space_id
    return False


def _eligible_tasks(access_context: dict | None = None) -> list[tuple[str, dict]]:
    """可检索集合：检索、IDF 与聚合必须消费同一份结果。

    过滤顺序：访问与生命周期、内容就绪。
    """
    result: list[tuple[str, dict]] = []
    for task_id, task in list(tasks.items()):
        if not isinstance(task, dict) or not task_id:
            continue
        if _is_deleted(task):
            continue
        if not _has_content(task):
            continue
        if not _access_allows(task_id, task, access_context):
            continue
        result.append((task_id, {**task, "id": task_id}))
    return result


def _resolve_project_filter(query: str) -> dict | None:
    """已建档项目名最长匹配（长度 ≥ 2 且完整出现在 query 中）。

    未匹配到项目名时不过滤——「星瀚」这类未建档名称交给 IDF，不硬编。
    """
    try:
        from core.projects import list_projects
        projects = list_projects()
    except Exception:  # noqa: BLE001 - 项目读取失败不阻断检索
        return None
    best: dict | None = None
    for project in projects:
        if not isinstance(project, dict):
            continue
        name = str(project.get("name") or "").strip()
        if len(name) < 2 or name not in query:
            continue
        if best is None or len(name) > len(best["project"]):
            best = {"project": name, "project_id": str(project.get("id") or "")}
    return best


def _public_filters(filters: dict | None) -> dict:
    if not filters:
        return {}
    return {k: v for k, v in filters.items() if k != "project_id" and v}


def _filter_candidates(
    eligible: list[tuple[str, dict]],
    time_range: dict,
    filters: dict | None,
    exclude_task_id: str | None = None,
) -> tuple[list[tuple[str, dict]], int]:
    """时间 / 项目 / 排除本场过滤；返回 (候选, 无日期被排除数)。"""
    project_id = (filters or {}).get("project_id") or ""
    candidates: list[tuple[str, dict]] = []
    undated = 0
    for task_id, task in eligible:
        if exclude_task_id and task_id == exclude_task_id:
            continue
        if project_id and str(task.get("project_id") or "") != project_id:
            continue
        if time_range.get("kind") == "range":
            day = _meeting_date(task)
            if not day:
                undated += 1
                continue
            if not in_range(day, time_range):
                continue
        candidates.append((task_id, task))
    return candidates, undated


def _idf_weights(eligible: list[tuple[str, dict]], terms: list[str]) -> dict[str, float]:
    """df 只在可检索集合上统计；无权会议不影响 N/df。"""
    total = len(eligible)
    df = {term: 0 for term in terms}
    if terms:
        for _task_id, task in eligible:
            text = _task_text(task).lower()
            for term in terms:
                if term in text:
                    df[term] += 1
    return {
        term: max(0.15, math.log((total + 1) / (df.get(term, 0) + 1)))
        for term in terms
    }


def _task_text(task: dict) -> str:
    try:
        summary = task_final_summary(task) or ""
    except Exception:  # noqa: BLE001
        summary = ""
    decisions = " ".join(str(d.get("text") or "") for d in _decision_items(task))
    dialogue = " ".join(e["text"] for e in _dialogue_entries(task))
    title = str(task.get("title") or task.get("audio_name") or "")
    # 已绑定 speaker 姓名 + 手工录入参会人（过滤未命名占位/空串）——让按人名检索能命中会议
    from core.speakers import normalize_speaker_mapping
    mapping = normalize_speaker_mapping(task.get("speaker_mapping"))
    bound_names = [name for name in mapping.values() if name]
    manual_roster = [str(n).strip() for n in (task.get("roster") or []) if str(n).strip()]
    speaker_names = " ".join(bound_names + manual_roster)
    return "\n".join((title, summary, decisions, dialogue, speaker_names))


def _status_meta() -> dict[str, dict]:
    try:
        return {str(s.get("id")): s for s in load_statuses() if isinstance(s, dict)}
    except Exception:  # noqa: BLE001 - 状态字典不可用时按 id 原样降级
        return {}


def _decision_current_map(eligible: list[tuple[str, dict]]) -> dict[str, bool]:
    """跨会议议题归并结果 → 节点是否为当前主记录。

    权限与结构化过滤先于归并；已替代节点只能作为历史证据。
    """
    status_meta = _status_meta()
    rows: list[dict] = []
    for task_id, task in eligible:
        for node in _decision_items(task):
            sid = status_of(node)
            rows.append({
                **node,
                "task_id": task_id,
                "kb_id": task.get("project_id"),
                "kb_name": None,
                "status_closing": bool((status_meta.get(sid) or {}).get("closing", False)),
            })
    if not rows:
        return {}
    mapping: dict[str, bool] = {}
    for cluster in cluster_topics(rows):
        main = cluster.get("main") or {}
        main_id = str(main.get("id") or "")
        for node in [main, *(cluster.get("history") or [])]:
            node_id = str(node.get("id") or "")
            if node_id:
                mapping[node_id] = node_id == main_id
    return mapping


def _node_status(node: dict, status_meta: dict[str, dict]) -> dict:
    sid = status_of(node)
    meta = status_meta.get(sid) or {}
    return {
        "status": sid,
        "status_name": str(meta.get("name") or sid),
        "status_closing": bool(meta.get("closing", False)),
    }


def _evidence(
    task_id: str,
    asset_type: str,
    asset_id: str,
    excerpt: str,
    locator: dict,
    *,
    status_info: dict | None = None,
    is_current: bool | None = None,
    superseded_by: dict | None = None,
) -> dict:
    item: dict[str, Any] = {
        "evidence_id": f"{task_id}:{asset_type}:{asset_id}",
        "task_id": task_id,
        "asset_type": asset_type,
        "asset_id": asset_id,
        "excerpt": excerpt,
        "locator": locator,
    }
    if status_info:
        item.update(status_info)
    if is_current is not None:
        item["is_current"] = bool(is_current)
    if superseded_by:
        item["superseded_by"] = superseded_by
    return item


def _decision_is_current(node: dict, current_map: dict[str, bool], status_info: dict) -> bool:
    if status_info["status"] == "superseded" or node.get("superseded_by"):
        return False
    node_id = str(node.get("id") or "")
    return current_map.get(node_id, True) if node_id else True


def _score_task(
    task_id: str,
    task: dict,
    query: str,
    terms: list[str],
    idf: dict[str, float],
    *,
    decision_intent: bool,
    current_intent: bool,
    current_map: dict[str, bool],
    status_meta: dict[str, dict],
    compact: bool = False,
) -> dict | None:
    title = str(task.get("title") or task.get("audio_name") or "未命名会议")
    try:
        summary = task_final_summary(task) or ""
    except Exception:  # noqa: BLE001 - 单场摘要异常不影响其他会议
        summary = ""
    decision_items = _decision_items(task)
    dialogue_entries = _dialogue_entries(task)

    title_l = title.lower()
    summary_l = summary.lower()
    decisions_l = " ".join(str(d.get("text") or "") for d in decision_items).lower()
    dialogue_l = " ".join(e["text"] for e in dialogue_entries).lower()

    score = 0.0
    for term in terms:
        weight = idf.get(term, 0.15)
        score += weight * min(title_l.count(term), 2)
        score += weight * min(summary_l.count(term), 2)
        score += weight * min(decisions_l.count(term), 3)
        score += weight * min(dialogue_l.count(term), 2)
    title_hit = bool(query and query.lower() in title_l)
    if title_hit:
        score += 3.0
    if any(term in title_l for term in terms):
        score += 1.0

    if score < MATCH_THRESHOLD:
        return None

    title_matched = title_hit or any(term in title_l for term in terms)
    summary_matched = any(term in summary_l for term in terms)

    priorities = ({"decision": 0, "summary": 1, "dialogue": 2, "title": 3}
                  if decision_intent
                  else {"title": 0, "summary": 1, "decision": 2, "dialogue": 3})

    entries: list[dict] = []

    def add(priority: int, label: str, text: str, evidence: dict) -> None:
        cleaned = " ".join(str(text or "").split())
        if not cleaned:
            return
        entries.append({
            "priority": priority,
            "label": label,
            "text": _snippet(cleaned),
            "evidence": evidence,
        })

    if title_matched:
        add(priorities["title"], "", title,
            _evidence(task_id, "title", "title", _snippet(title), {}))
    if summary_matched:
        add(priorities["summary"], "纪要摘录：", summary,
            _evidence(task_id, "summary", "task_final_summary",
                      _snippet(summary), {"field": "task_final_summary"}))

    for index, node in enumerate(decision_items):
        text = str(node.get("text") or "").strip()
        if not text:
            continue
        status_info = _node_status(node, status_meta)
        is_current = _decision_is_current(node, current_map, status_info)
        # 已替代节点不得作为当前结论；当前类追问只给有效主记录
        if current_intent and not is_current:
            continue
        matched = any(term in text.lower() for term in terms)
        if not matched and not decision_intent and not current_intent:
            continue
        node_id = str(node.get("id") or f"d{index}")
        locator = {"decision_id": node_id}
        superseded = node.get("superseded_by")
        add(
            priorities["decision"],
            "决策项：",
            f"{text}（{status_info['status_name']}，当前结论={str(is_current).lower()}）",
            _evidence(
                task_id, "decision", node_id, _snippet(text), locator,
                status_info=status_info,
                is_current=is_current,
                superseded_by=superseded if isinstance(superseded, dict) else None,
            ),
        )

    dialogue_matches: list[dict] = []
    for entry in dialogue_entries:
        if any(term in entry["text"].lower() for term in terms):
            dialogue_matches.append(entry)
            if len(dialogue_matches) >= 5:
                break
    for entry in dialogue_matches:
        asset_id = f"d{entry['dialogue_index']}:s{entry['sentence_index']}"
        locator = {
            "dialogue_index": entry["dialogue_index"],
            "sentence_index": entry["sentence_index"],
        }
        if entry.get("begin_time") is not None:
            locator["begin_time"] = entry["begin_time"]
        if entry.get("end_time") is not None:
            locator["end_time"] = entry["end_time"]
        add(priorities["dialogue"], "", entry["text"],
            _evidence(task_id, "dialogue", asset_id, _snippet(entry["text"]), locator))

    entries.sort(key=lambda item: item["priority"])
    seen: set[str] = set()
    lines: list[dict] = []
    for entry in entries:
        if entry["text"] in seen:
            continue
        seen.add(entry["text"])
        lines.append(entry)
        if len(lines) >= MAX_SNIPPETS:
            break

    # 薄清单（工具分页）：每场只留最高优先一段，跳过补充决策/纪要的加厚渲染，
    # 让一次调用能覆盖几十场而不是几场。
    if compact:
        # 已绑定 speaker 姓名 + 手工录入参会人（过滤未命名占位/空串，去重）
        from core.speakers import normalize_speaker_mapping
        _map = normalize_speaker_mapping(task.get("speaker_mapping"))
        bound_names = [name for name in _map.values() if name]
        manual_roster = [str(n).strip() for n in (task.get("roster") or []) if str(n).strip()]
        seen: set[str] = set()
        speakers: list[str] = []
        for name in bound_names + manual_roster:
            if name not in seen:
                seen.add(name)
                speakers.append(name)
        return {
            "task_id": task_id,
            "title": title,
            "date": _meeting_date(task),
            "score": round(score, 2),
            "lines": lines[:1],
            "summary": "",
            "speakers": speakers,
        }

    # 决策项与纪要摘录：确保「谁定的 / 结论是什么」的证据随命中一起给出
    covered = " ".join(line["text"] for line in lines)
    for index, node in enumerate(decision_items):
        text = str(node.get("text") or "").strip()
        if not text or text[:30] in covered:
            continue
        status_info = _node_status(node, status_meta)
        is_current = _decision_is_current(node, current_map, status_info)
        if current_intent and not is_current:
            continue
        node_id = str(node.get("id") or f"d{index}")
        line = {
            "priority": 99,
            "label": "决策项：",
            "text": _snippet(f"{text}（{status_info['status_name']}，当前结论={str(is_current).lower()}）"),
            "evidence": _evidence(
                task_id, "decision", node_id, _snippet(text), {"decision_id": node_id},
                status_info=status_info, is_current=is_current,
                superseded_by=node.get("superseded_by") if isinstance(node.get("superseded_by"), dict) else None,
            ),
        }
        lines.append(line)
        covered += " " + line["text"]
        if len([line for line in lines if line["label"] == "决策项："]) >= 5:
            break
    if summary and summary[:30] not in covered:
        lines.append({
            "priority": 100,
            "label": "纪要摘录：",
            "text": _snippet(summary, 300),
            "evidence": _evidence(
                task_id, "summary", "task_final_summary", _snippet(summary, 300),
                {"field": "task_final_summary"},
            ),
        })

    return {
        "task_id": task_id,
        "title": title,
        "date": _meeting_date(task),
        "score": round(score, 2),
        "lines": lines,
        "summary": summary,
    }


def _search_prepared(
    query: str,
    eligible: list[tuple[str, dict]],
    candidates: list[tuple[str, dict]],
    *,
    current_intent: bool | None = None,
    decision_intent: bool | None = None,
    compact: bool = False,
) -> list[dict]:
    terms = _query_terms(query)
    if not terms:
        return []
    idf = _idf_weights(eligible, terms)
    status_meta = _status_meta()
    current_map = _decision_current_map(eligible)
    if current_intent is None:
        current_intent = _has_current_decision_intent(query)
    if decision_intent is None:
        decision_intent = _has_decision_intent(query)

    scored: list[dict] = []
    for task_id, task in candidates:
        result = _score_task(
            task_id, task, query, terms, idf,
            decision_intent=decision_intent,
            current_intent=current_intent,
            current_map=current_map,
            status_meta=status_meta,
            compact=compact,
        )
        if result:
            scored.append(result)

    # 相关度降序 → 日期降序（新会优先）→ task_id 稳定
    scored.sort(key=lambda item: item["task_id"])
    scored.sort(key=lambda item: item["date"] or "", reverse=True)
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored


def search_meetings(
    query: str,
    *,
    exclude_task_id: str | None = None,
    limit: int | None = None,
    time_range: dict | None = None,
    filters: dict | None = None,
    access_context: dict | None = None,
    now=None,
) -> list[dict]:
    """全库会议关键词检索（可单独调用），返回按相关度降序的命中。"""
    eligible = _eligible_tasks(access_context)
    if time_range is None:
        time_range = parse_time_range(query, now)
    if filters is None:
        filters = _resolve_project_filter(query)
    candidates, _undated = _filter_candidates(eligible, time_range, filters, exclude_task_id)
    hits = _search_prepared(query, eligible, candidates)
    return hits[:limit] if limit is not None else hits


def search_meeting_list(
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
    exclude_task_id: str | None = None,
    access_context: dict | None = None,
    now=None,
) -> dict[str, Any]:
    """跨全库薄清单检索：每场一条摘录 + 稳定定位，供模型分页取全。

    与注入块共用同一套过滤、阈值与排序，只换渲染粒度：
    每场仅保留最高优先一段，天然可一页覆盖几十场；``offset`` 让调用方翻页。
    这是 spec §4 第 5 级「原文回捞」的入口——先拿清单，再按 task_id 取详情。
    """
    eligible = _eligible_tasks(access_context)
    time_range = parse_time_range(query, now)
    filters = _resolve_project_filter(query)
    candidates, _undated = _filter_candidates(eligible, time_range, filters, exclude_task_id)
    hits = _search_prepared(query, eligible, candidates, compact=True)

    page_size = max(1, min(int(limit or 20), LIST_MAX_LIMIT))
    start = max(0, int(offset or 0))
    page = hits[start:start + page_size]
    result: dict[str, Any] = {
        "query": query,
        "total": len(hits),
        "offset": start,
        "limit": page_size,
        "returned": len(page),
        "has_more": start + len(page) < len(hits),
        "time_label": time_range.get("label") or "未限定",
        "items": [
            {
                "task_id": hit["task_id"],
                "title": hit["title"],
                "date": hit["date"],
                "score": hit["score"],
                "snippet": hit["lines"][0]["text"] if hit["lines"] else "",
                "speakers": hit.get("speakers", []),
            }
            for hit in page
        ],
    }
    if len(hits) > LIST_NARROW_HINT_TOTAL:
        result["hint"] = (
            f"命中 {len(hits)} 场，建议在 query 里加时间或项目名缩小范围，"
            "避免逐页翻完全库。"
        )
    return result


def _xml_attr(value: object) -> str:
    return str(value).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def _render_meeting(index: int, hit: dict) -> str:
    title = " ".join(str(hit.get("title") or "未命名会议").split())
    lines = [f"### {index}. {title}（{hit.get('date') or '日期未知'}，相关度 {hit.get('score')}）"]
    for line in hit.get("lines") or []:
        lines.append(f"- {line.get('label') or ''}{line['text']} [evidence:{line['evidence']['evidence_id']}]")
    return "\n".join(lines) + "\n"


def _retrieval_header(retrieval: dict[str, Any]) -> str:
    filters = retrieval.get("filters") or {}
    filter_text = ";".join(f"{k}:{v}" for k, v in filters.items()) or "none"
    return (
        f'<retrieval scope="{retrieval.get("scope")}" status="{retrieval.get("status")}" '
        f'query_kind="{retrieval.get("query_kind")}" '
        f'time_range="{_xml_attr(retrieval.get("time_range") or "none")}" '
        f'time_label="{_xml_attr(retrieval.get("time_label") or "未限定")}" '
        f'filters="{_xml_attr(filter_text)}" '
        f'candidates="{retrieval.get("candidates")}" matched="{retrieval.get("matched")}" '
        f'injected="{retrieval.get("injected")}" '
        f'truncated="{str(bool(retrieval.get("truncated"))).lower()}" '
        f'dropped_reason="{retrieval.get("dropped_reason") or "none"}">'
    )


_RETRIEVAL_NOTE = (
    "说明：以上为历史会议证据。检索遥测只读，禁止复述、改写或自行计算会议与决策统计；\n"
    "引用时标注会议标题与日期，并保持决策的当前/历史/已替代状态；time_range=\"none\" 表示用户未指定时间范围，\n"
    "不得假定为「本月」；证据不足时直接回答「未找到」，不得按时间线推断。\n"
    "dropped_meetings 只是未展开命中的标题清单，不含内容：需要细节时用检索工具按 task_id 取回；"
    "工具不可用（问答模式）时如实说明「另有 N 场未展开」，不得据标题推断内容。"
)
_FACTS_NOTE = (
    "说明：此块为后端已核验的用户事实，可原值引用；不得据此计算或推断其他统计。\n"
    "本轮统计以本块为唯一口径，禁止沿用历史对话中的数字或自行改写。"
)


def _format_facts_block(facts: list[dict]) -> str:
    if not facts:
        return ""
    payload = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
    return f"<verified_facts>\n{payload}\n</verified_facts>\n{_FACTS_NOTE}"


def _empty_retrieval(scope: str) -> dict[str, Any]:
    return {
        "scope": scope,
        "status": "disabled",
        "query_kind": "retrieval",
        "searched": False,
        "time_range": "none",
        "time_label": "未限定",
        "filters": {},
        "candidates": 0,
        "matched": 0,
        "injected": 0,
        "truncated": False,
        "dropped_reason": "none",
        "undated_excluded": 0,
        "hits": 0,
        "shown": 0,
        "dropped_total": 0,
        "dropped_meetings": [],
        "meetings": [],
        "verified_facts": [],
        "latency_ms": 0,
    }


def _error_retrieval(scope: str, kind: str, error_kind: str) -> dict[str, Any]:
    retrieval = _empty_retrieval(scope)
    retrieval.update({
        "query_kind": kind,
        "status": "error",
        "error_kind": error_kind,
        "candidates": None,
        "matched": None,
        "injected": None,
    })
    return retrieval


def build_scope_context(
    scope: str | None,
    query: str,
    *,
    exclude_task_id: str | None = None,
    limit: int | None = None,
    now=None,
    access_context: dict | None = None,
) -> tuple[str, dict[str, Any]]:
    """唯一入口：返回 (上下文块, retrieval)。

    meeting → 空块 + status=disabled；all → 检索/聚合按查询种类执行。
    limit=None 时仅按字符预算截断；显式整数同时受场次数与预算约束。
    检索或聚合异常不阻断对话，但返回 status=error，新计数为 null，绝不伪装零结果。
    """
    from core.meeting_facts import aggregate_from, classify_query

    resolved = normalize_scope(scope)
    if resolved != "all":
        return "", _empty_retrieval(resolved)

    kind = classify_query(query)
    started = time.perf_counter()
    try:
        eligible = _eligible_tasks(access_context)
        time_range = parse_time_range(query, now)
        filters = _resolve_project_filter(query)
    except Exception as exc:  # noqa: BLE001 - 访问/解析失败关闭访问
        logger.warning("[范围检索] 可检索集合构建失败: %s", exc)
        return "", _error_retrieval(resolved, kind, "access")

    retrieval = _empty_retrieval(resolved)
    retrieval.update({
        "status": "ok",
        "query_kind": kind,
        "time_range": (
            f"{time_range.get('start')}..{time_range.get('end')}"
            if time_range.get("kind") == "range" else "none"
        ),
        "time_label": time_range.get("label") or "未限定",
        "filters": _public_filters(filters),
    })

    facts: list[dict] = []
    if kind in ("aggregate", "mixed"):
        try:
            facts = aggregate_from(query, eligible, time_range, filters)
        except Exception as exc:  # noqa: BLE001 - 聚合失败不得返回默认 0
            logger.warning("[范围检索] 统计失败: %s", exc)
            return "", _error_retrieval(resolved, kind, "aggregation")
        retrieval["verified_facts"] = facts

    blocks: list[str] = []
    if kind in ("retrieval", "mixed"):
        try:
            candidates, undated = _filter_candidates(
                eligible, time_range, filters, exclude_task_id)
            matched_hits = _search_prepared(query, eligible, candidates)
        except Exception as exc:  # noqa: BLE001 - 检索失败不得伪装零命中
            logger.warning("[范围检索] 检索失败: %s", exc)
            return "", _error_retrieval(resolved, kind, "retrieval")

        retrieval.update({
            "searched": True,
            "candidates": len(candidates),
            "matched": len(matched_hits),
            "undated_excluded": undated,
        })

        injected_hits: list[dict] = []
        used_chars = 0
        dropped_reason = "none"
        truncated = False
        for hit in matched_hits:
            body = _render_meeting(len(injected_hits) + 1, hit)
            if limit is not None and len(injected_hits) >= limit:
                truncated = True
                dropped_reason = "limit"
                break
            if injected_hits and used_chars + len(body) > INJECT_MAX_CHARS:
                truncated = True
                dropped_reason = "budget"
                break
            injected_hits.append(hit)
            used_chars += len(body)

        # 未展开命中：只留标题/日期/id，让模型能如实告知「另有 N 场」并按需下钻，
        # 而不是拿注入的几场冒充全量（此前这些场次名次在注入后被整体丢弃）。
        dropped_hits = matched_hits[len(injected_hits):]
        retrieval.update({
            "injected": len(injected_hits),
            "truncated": truncated,
            "dropped_reason": dropped_reason,
            "hits": len(matched_hits),
            "shown": len(injected_hits),
            "dropped_total": len(dropped_hits),
            "dropped_meetings": [
                {"task_id": hit["task_id"], "title": hit["title"], "date": hit["date"]}
                for hit in dropped_hits[:DROPPED_PREVIEW_MAX]
            ],
            "meetings": [
                {
                    "task_id": hit["task_id"],
                    "title": hit["title"],
                    "date": hit["date"],
                    "score": hit["score"],
                    "evidence": [line["evidence"] for line in hit["lines"]],
                }
                for hit in injected_hits
            ],
        })

        if injected_hits:
            header = _retrieval_header(retrieval)
            lines = [header, f"检索问题：{query}"]
            for index, hit in enumerate(injected_hits, start=1):
                lines.append(_render_meeting(index, hit).rstrip("\n"))
            if retrieval["dropped_total"]:
                lines.append(
                    f'<dropped_meetings total="{retrieval["dropped_total"]}" '
                    f'shown="{len(retrieval["dropped_meetings"])}">')
                for index, item in enumerate(retrieval["dropped_meetings"], start=1):
                    title = " ".join(str(item["title"] or "未命名会议").split())
                    lines.append(
                        f'{index}. {title}（{item["date"] or "日期未知"}，'
                        f'task_id={item["task_id"]}）')
                lines.append("</dropped_meetings>")
            lines.append("</retrieval>")
            lines.append(_RETRIEVAL_NOTE)
            blocks.append("\n".join(lines))

    facts_block = _format_facts_block(facts)
    if facts_block:
        blocks.append(facts_block)

    retrieval["latency_ms"] = round((time.perf_counter() - started) * 1000)
    if kind in ("retrieval", "mixed") and retrieval.get("matched") == 0:
        # 零命中：不生成检索证据块，但遥测照常返回
        retrieval["meetings"] = []
    return "\n\n".join(block for block in blocks if block), retrieval
