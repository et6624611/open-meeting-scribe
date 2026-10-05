"""
core/chat_edits.py — 数据编辑意图：LLM 结构化解析 → 后端执行 → 磁盘回读校验 / Data edit intent: LLM structured parsing → backend execution → disk read-back verification

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
版本 / Version: 1.0.0

设计原则（见 ADR-0008） / Design principle (see ADR-0008)：AI 无执行权，也无操作结果的单方叙述权 / AI has no execution power, nor unilateral narration of operation results.
数据修改由 LLM 解析为结构化操作、后端统一执行并回读磁盘校验 / Data modifications are parsed by LLM into structured operations, executed by backend with disk read-back verification,
回复叙述以校验结果为准，系统事后追加校验结论，杜绝幻觉操作声称 / Reply narration is based on verification results; system appends verification conclusions post-facto, preventing hallucinated operation claims.

从 app/routers/chat.py 拆分而来 / Split from app/routers/chat.py.
"""

import json
import logging
import re

from app.task_store import TASKS_DIR, save_task_to_disk, tasks
from core.llm import async_chat_completion

logger = logging.getLogger(__name__)

# ============================================================
# 常量
# ============================================================

# 编辑意图门槛关键词：仅命中消息进入意图解析
EDIT_INTENT_KEYWORDS = [
    "改为", "改成", "应该是", "应为", "修正", "修改", "更正", "换成", "更新为",
    "重命名", "删除待办", "去掉待办", "标记完成", "标记为", "勾选", "勾上", "改回", "写错", "名字错",
]

# 允许的编辑操作白名单
EDIT_OP_FIELDS = {"todo_assignee": "assignee", "todo_text": "text", "todo_done": "done"}

EDIT_INTENT_SYSTEM_PROMPT = """你是 Open Meeting Scribe 会议助手的意图解析器。唯一任务：判断用户消息是否包含对当前会议待办清单的数据编辑意图，并输出结构化操作。

允许的操作（op 仅限以下四种）：
- todo_assignee：修改待办责任人，value 为新姓名
- todo_text：修改待办内容，value 为新内容
- todo_done：修改待办完成状态，value 为 true 或 false
- todo_delete：删除待办，无需 value

规则：
- todo_id 必须取自给定待办清单中的 id，不得编造
- 用户提到旧姓名/旧值且多条待办命中时，对每条命中的待办各出一条操作
- 无编辑意图、或编辑对象不在待办清单中时，返回空操作
- 只输出 JSON，格式：{"ops": [{"op": "...", "todo_id": "...", "value": "..."}]}"""

# 回复中的操作声称词
CLAIM_PATTERN = re.compile(r"已(修正|修改|更新|删除|添加|新增|重命名|勾选|替换|更改|改写|同步)")
_FIELD_LABELS = {"assignee": "责任人", "text": "待办内容", "done": "完成状态"}


# ============================================================
# 意图检测
# ============================================================


def has_edit_intent(message: str) -> bool:
    """判断用户消息是否包含编辑意图关键词。"""
    return any(kw in message for kw in EDIT_INTENT_KEYWORDS)


# ============================================================
# LLM 解析
# ============================================================


def _sanitize_edit_ops(raw: str, valid_ids: set) -> list[dict]:
    """解析 LLM 返回的 JSON，按操作白名单与合法 todo_id 过滤。"""
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        text = m.group(1) if m else text
    start = text.find("{")
    if start < 0:
        return []
    try:
        data = json.loads(text[start:])
    except Exception:
        return []
    ops = data.get("ops") if isinstance(data, dict) else None
    if not isinstance(ops, list):
        return []
    cleaned = []
    for op in ops[:20]:
        if not isinstance(op, dict):
            continue
        name = op.get("op")
        todo_id = op.get("todo_id")
        if name not in EDIT_OP_FIELDS and name != "todo_delete":
            continue
        if todo_id not in valid_ids:
            continue
        if name != "todo_delete" and "value" not in op:
            continue
        cleaned.append({"op": name, "todo_id": todo_id, "value": op.get("value")})
    return cleaned


async def parse_edit_intent(message: str, task: dict) -> list[dict]:
    """用 LLM 从用户消息解析待办编辑意图，失败返回空列表（降级为普通对话）。"""
    todos = task.get("todos") or []
    if not todos:
        return []
    brief = [
        {"todo_id": t.get("id"), "text": t.get("text", ""), "assignee": t.get("assignee", ""), "done": bool(t.get("done"))}
        for t in todos
    ]
    messages = [
        {"role": "system", "content": EDIT_INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": f"用户消息：{message}\n\n当前待办清单（JSON）：\n{json.dumps(brief, ensure_ascii=False)}"},
    ]
    try:
        raw = await async_chat_completion(messages, model=None, temperature=0.1, max_tokens=512)
    except Exception as e:
        logger.warning(f"编辑意图解析失败（降级为普通对话）: {e}")
        return []
    ops = _sanitize_edit_ops(raw, {t.get("id") for t in todos})
    if ops:
        logger.info(f"[AI对话] 解析到编辑意图: {ops}")
    return ops


# ============================================================
# 执行与校验
# ============================================================


def execute_and_verify_edits(task_id: str, ops: list[dict]) -> list[dict]:
    """执行待办编辑操作，并回读磁盘逐条校验结果。

    返回变更记录列表，每条带 verified 标记。
    """
    task = tasks.get(task_id)
    if not task:
        return []
    todos = task.setdefault("todos", [])
    changes: list[dict] = []
    for op in ops:
        name, todo_id = op["op"], op["todo_id"]
        if name == "todo_delete":
            target = next((t for t in todos if t.get("id") == todo_id), None)
            if not target:
                continue
            old = target.get("text", "")
            task["todos"] = [t for t in task["todos"] if t.get("id") != todo_id]
            todos = task["todos"]
            changes.append({"op": name, "todo_id": todo_id, "field": "delete", "old": old, "new": None})
        else:
            field = EDIT_OP_FIELDS[name]
            target = next((t for t in todos if t.get("id") == todo_id), None)
            if not target:
                continue
            old = target.get(field)
            new = bool(op.get("value")) if field == "done" else op.get("value")
            if old == new:
                continue
            target[field] = new
            changes.append({"op": name, "todo_id": todo_id, "field": field, "old": old, "new": new})
    if not changes:
        return []
    save_task_to_disk(task_id)
    # 磁盘回读校验
    disk_todos: dict = {}
    try:
        disk = json.loads((TASKS_DIR / f"{task_id}.json").read_text(encoding="utf-8"))
        disk_todos = {t.get("id"): t for t in disk.get("todos", [])}
    except Exception as e:
        logger.error(f"编辑校验失败（磁盘回读异常）: {e}")
    for ch in changes:
        if ch["op"] == "todo_delete":
            ch["verified"] = ch["todo_id"] not in disk_todos
        else:
            dt = disk_todos.get(ch["todo_id"])
            ch["verified"] = dt is not None and dt.get(ch["field"]) == ch["new"]
    return changes


# ============================================================
# 辅助函数
# ============================================================


def describe_change(ch: dict) -> str:
    """单条变更记录的人类可读描述。"""
    if ch["op"] == "todo_delete":
        return f"删除待办「{ch['old']}」"
    return f"待办{_FIELD_LABELS.get(ch['field'], ch['field'])}「{ch['old']}」→「{ch['new']}」"


def audit_reply_claims(reply: str, changes: list[dict]) -> str:
    """事后审计 AI 回复中的操作声称，按实际执行结果追加系统校验结论。"""
    if changes:
        lines = [
            f"- {describe_change(ch)}：{'磁盘回读校验通过' if ch.get('verified') else '校验未通过，请刷新页面核对'}"
            for ch in changes
        ]
        return reply + "\n\n---\n✅ 系统校验（本轮执行结果，磁盘回读确认）：\n" + "\n".join(lines)
    if CLAIM_PATTERN.search(reply):
        logger.warning("[AI对话] 回复含操作声称但系统本轮未执行任何写操作，已追加校验提示")
        return reply + "\n\n---\n⚠️ 系统校验：本轮系统未执行任何数据写操作，上述操作描述与实际状态不符，数据保持不变。"
    return reply
