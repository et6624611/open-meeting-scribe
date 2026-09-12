"""
app/routers/chat.py — AI 对话路由端点

作者：王永亮
创建：2026-09-03
版本：2.0.0

v2.0 重构：业务逻辑已拆分至 core 层子模块，本文件仅保留端点定义与编排逻辑。
  - core/chat_actions.py  — 动作检测与执行
  - core/chat_edits.py    — 编辑意图解析、执行与审计
  - core/chat_context.py  — 上下文构建与注入提取
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.store import (
    tasks, TASKS_DIR,
    realtime_transcript_buffers, REALTIME_BUFFER_MAX,
)
from core.chat_actions import detect_action, execute_action
from core.chat_edits import has_edit_intent, parse_edit_intent, execute_and_verify_edits, describe_change, audit_reply_claims
from core.chat_edits import _sanitize_edit_ops
from core.chat_context import is_joblog_intent, build_speaker_name_map, build_page_context, extract_injectable_items
from core.llm import async_chat_completion
from core import joblog

# 向后兼容别名（测试与外部引用）
_detect_action = detect_action
_is_joblog_intent = is_joblog_intent
_build_page_context = build_page_context
_execute_and_verify_edits = execute_and_verify_edits
_audit_reply_claims = audit_reply_claims
from core.i18n import _

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


# ============================================================
# 请求模型
# ============================================================

class ChatRequest(BaseModel):
    message: str
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    history: Optional[list[dict]] = None
    realtime_transcripts: Optional[list[dict]] = None
    mode: Optional[str] = None
    model: Optional[str] = None
    current_page: Optional[str] = None


class OptimizeRequest(BaseModel):
    text: str
    model: Optional[str] = None


# ============================================================
# 系统提示词
# ============================================================

CHAT_SYSTEM_PROMPT = """<role>
你是 Open Meeting Scribe 的 AI 会议助手，专注于帮助用户高效处理会议录音、生成结构化纪要、并从项目资料中提取关键信息。
</role>

<capabilities>
## 核心能力
1. **会议处理**：录音控制、转写、说话人分离、纪要生成
2. **内容分析**：提取待办、总结结论、分析发言占比
3. **项目问答**：基于用户关联的项目资料文件夹，回答业务问题
4. **动作执行**：系统自动检测用户意图并执行操作（录音、分析、主题等）
5. **数据编辑**：待办修改由系统解析、执行、磁盘回读校验，你只转述结果
</capabilities>

<constraints>
## 操作权限边界（最高优先级）
- 你**没有执行权**：不能修改、删除、写入任何数据
- 操作结果只能引用「系统动作执行结果」块，那是系统验证过的唯一事实
- 若该块不存在或标明失败，禁止使用"已修正/已更新/已删除"等表述
- 不要在回复中复述待办清单或纪要全文（系统界面已展示）

## 已支持的操作（全部已实现，禁止回答"不支持"）
- 录音控制：开始/停止/暂停/恢复录音
- 会议分析：提取待办、总结结论、发言分析
- 任务管理：列出所有会议任务
- 信息查询：热词、热词映射、系统设置、录制状态
- 重新处理：重新识别音频、重新生成纪要
- 主题配色：创建/删除自定义主题

当用户描述命中上述操作时，必须视为操作触发，绝不能回答"暂不支持"。
</constraints>

<output_format>
## 回复规范（第一优先级：简洁）

本系统已承载大量信息（转写全文、结构化纪要、待办清单、项目资料），用户不缺信息，缺的是提炼。

1. **直击要点**：第一句话就是答案或结论，不要铺垫
2. **不复述已知信息**：系统已展示的内容不要重复搬运
3. **不复述动作流程**：系统已执行动作时，只说结果，不说"我已经帮你做了 XX"
4. **不寒不客套**：不用"好的""当然可以""没问题"开头
5. **控制篇幅**：简单问题 1-2 句；列举时用精简列表，每条不超过一行
6. **不解释自身能力**：除非用户问"你能做什么"，否则不主动介绍
</output_format>

<instructions>
## 项目资料回答规范（关键）

当用户询问项目相关问题时，系统会注入相关文件的完整内容（最多 5 个文件，每个最多 2000 字符）。

### 回答步骤
1. **识别问题类型**：
   - "有哪些..." → 列举 + 每项给出具体内容
   - "怎么做..." → 给出步骤/流程
   - "是什么..." → 给出定义 + 关键属性

2. **从文件内容中提取信息**：
   - 不要只说"见 XX 文件"
   - 直接引用文件中的具体内容（定义、字段、流程等）
   - 如果文件中有表格/列表，用````格式````还原

3. **组织回答**：
   - 先给结论（1 句话）
   - 再展开细节（列表/表格）
   - 最后标注来源（📎 文件名）

### 示例对比

❌ 错误回答：
"客商主数据需要治理，来源：/04_数据治理/客商/README.md"

✅ 正确回答：
"客商主数据包括客户和供应商两类，需要治理的内容：
- 客户编码：统一为 10 位数字，前 3 位为区域码
- 供应商资质：需审核营业执照、税务登记证
- 合并规则：同一统一社会信用代码视为同一供应商
📎 客商/README.md"
</instructions>

<examples>
## 其他规范
- 引用项目资料用「📎 文件名」标注来源
- 当前有会议上下文时，优先基于会议内容回答
- 不确定时，诚实说明
</examples>

<context>
## 当前状态
- 软件版本：v1 云方案
- ASR 模型：paraformer-v2
- 纪要模型：qwen-plus
- 系统会注入「当前页面」上下文，据此调整回复的侧重点
"""

CHAT_QA_SYSTEM_PROMPT = """<role>
你是 Open Meeting Scribe 的智能问答模式。你的唯一职责是基于当前会议的转写内容、纪要、项目资料等上下文信息回答用户问题。
</role>

<constraints>
## 严格限制
- 你**不能执行任何操作**：不能修改设置、不能编辑纪要、不能控制录音、不能创建主题
- 你**只能基于提供的上下文回答**：包括会议转写、会议纪要、项目资料
- 如果上下文中没有相关信息，诚实告知用户「当前会议资料中未找到相关内容」
- 不要猜测或编造上下文中不存在的信息
- 如果用户要求执行操作（如「帮我修改」「开始录音」），告知用户当前处于智能问答模式，建议切换到智能体模式
</constraints>

<output_format>
## 回复规范
1. 直击要点，不铺垫
2. 引用上下文中的具体内容，标注来源
3. 简单问题 1-2 句；复杂问题用精简列表
4. 不确定时诚实说明
</output_format>
"""

OPTIMIZE_SYSTEM_PROMPT = """你是一位专业的中文文稿润色助手。请对用户提供的文本进行优化，遵循以下原则：

1. **保持原意**：不改变原文的核心意思和观点
2. **语言流畅**：修正语病、消除冗余、改善句式结构
3. **逻辑清晰**：确保论述有条理，段落衔接自然
4. **用词准确**：替换模糊或不当的措辞
5. **格式规范**：修正标点符号、数字格式等细节

规则：
- 直接输出优化后的文本，不要添加解释或说明
- 如果原文已经是高质量的，保持原文不变
- 保留原文的段落结构
- 如果原文包含代码、公式等专业内容，保持原样"""


# ============================================================
# AI 对话端点
# ============================================================

@router.post("/api/chat")
async def chat(data: ChatRequest):
    """AI 对话端点（含动作检测与执行）。"""
    user_message = data.message.strip()
    if not user_message:
        raise HTTPException(400, _("Message cannot be empty"))

    is_qa_mode = data.mode == "qa"
    system_prompt = CHAT_QA_SYSTEM_PROMPT if is_qa_mode else CHAT_SYSTEM_PROMPT
    context_blocks = []
    action_result: dict | None = None
    chat_model = data.model or "qwen-plus"

    # ── 步骤 0: 数据编辑意图 ──
    edit_changes: list[dict] = []
    edit_turn = False
    if not is_qa_mode and data.task_id and data.task_id in tasks and has_edit_intent(user_message):
        ops = await parse_edit_intent(user_message, tasks[data.task_id])
        if ops:
            edit_turn = True
            edit_changes = await asyncio.to_thread(execute_and_verify_edits, data.task_id, ops)
            if edit_changes:
                result_text = "\n".join(
                    f"- {describe_change(ch)}：{'校验通过' if ch.get('verified') else '校验未通过'}"
                    for ch in edit_changes
                )
            else:
                result_text = "未产生实际变更（当前状态已符合用户要求）"
            context_blocks.append(
                "## 系统动作执行结果（已验证，唯一事实）\n"
                f"系统已执行待办编辑并磁盘回读校验：\n{result_text}\n"
                "回复中的操作结果只能引用以上内容，不得声称其他变更。"
            )
            joblog.append_event(
                data.task_id, joblog.STAGE_CHAT_ACTION,
                f"会议助手执行待办编辑: {len(edit_changes)} 项变更（校验通过 {sum(1 for c in edit_changes if c.get('verified'))}）",
                level="info" if edit_changes else "warn",
            )

    # ── 步骤 1: 关键词动作检测与执行 ──
    detected_action = None if (edit_turn or is_qa_mode) else detect_action(user_message)
    if detected_action:
        logger.info(f"[AI对话] 检测到动作意图: {detected_action.name} (关键词匹配)")
        action_result = execute_action(detected_action, data.task_id, data.message)
        if action_result:
            status = "成功" if action_result.get("success") else "失败"
            context_blocks.append(
                f"## 系统动作执行结果\n"
                f"动作: {detected_action.description}\n"
                f"状态: {status}\n"
                f"结果: {action_result.get('message', '无')}"
            )
            tid = (action_result.get("data") or {}).get("task_id") or data.task_id
            if tid:
                joblog.append_event(
                    tid, joblog.STAGE_CHAT_ACTION,
                    f"会议助手执行动作 {detected_action.name}: {status} — {action_result.get('message', '')}",
                    level="info" if action_result.get("success") else "error",
                )

    # ── 维度 1: 实时转写流 ──
    realtime_entries = []
    if data.realtime_transcripts:
        realtime_entries = data.realtime_transcripts[-REALTIME_BUFFER_MAX:]
    elif data.task_id and data.task_id in realtime_transcript_buffers:
        realtime_entries = realtime_transcript_buffers[data.task_id]

    if realtime_entries:
        speaker_name_map = build_speaker_name_map(data.task_id) if data.task_id else {}
        lines = []
        for entry in realtime_entries[-10:]:
            sid = entry.get("speaker_id")
            name = speaker_name_map.get(sid, f"Speaker {sid + 1}" if sid else "Unknown")
            text = entry.get("text", "").strip()
            if text:
                lines.append(f"{name}：{text}")
        if lines:
            context_blocks.append("## 实时会议对话（最近发言）\n" + "\n".join(lines))

    # ── 维度 2: 当前会议上下文 ──
    if data.task_id and data.task_id in tasks:
        task = tasks[data.task_id]
        meta_lines = [
            f"- 会议标题：{task.get('title') or task.get('audio_name') or '未命名'}",
            f"- 会议状态：{task.get('status', '未知')}",
        ]
        if task.get("audio_duration"):
            dur = task["audio_duration"]
            meta_lines.append(f"- 音频时长：{int(dur // 60)} 分 {int(dur % 60)} 秒")
        if task.get("speaker_count"):
            meta_lines.append(f"- 说话人数量：{task['speaker_count']}")
        audio_path = task.get("audio_path", "")
        if audio_path and Path(audio_path).exists():
            meta_lines.append(f"- 音频文件：{Path(audio_path).name}（已存在）")
        elif audio_path:
            meta_lines.append(f"- 音频文件：{Path(audio_path).name}（路径记录但文件不存在）")
        if task.get("error"):
            meta_lines.append(f"- 错误信息：{task['error']}")
        context_blocks.append("## 当前会议信息\n" + "\n".join(meta_lines))

        summary = task.get("summary") or ""
        is_summary_error = "内容过短" in summary or "无法生成有效纪要" in summary
        if summary and not is_summary_error:
            context_blocks.append(f"## 当前会议纪要\n{summary[:2000]}")
        elif task.get("dialogue") and not realtime_entries:
            dialogue_lines = []
            for item in task["dialogue"]:
                name = item.get("speaker_name", f"Speaker {item.get('speaker_id', 0) + 1}")
                sents = item.get("sentences") or []
                for s in sents:
                    text = s.get("text", "").strip()
                    if text:
                        dialogue_lines.append(f"{name}：{text}")
                if not sents:
                    text = item.get("text", "").strip()
                    if text:
                        dialogue_lines.append(f"{name}：{text}")
            dialogue_text = "\n".join(dialogue_lines)
            if dialogue_text:
                context_blocks.append(f"## 当前会议对话\n{dialogue_text[:3000]}")

        todos = task.get("todos") or []
        if todos:
            todo_lines = []
            for t in todos:
                status = "✅" if t.get("done") else "⬜"
                assignee = t.get("assignee", "未分配")
                todo_lines.append(f"- [{status}] {t.get('text', '')}（责任人：{assignee}）")
            context_blocks.append("## 当前会议待办事项\n" + "\n".join(todo_lines))

        if is_joblog_intent(user_message):
            joblog_ctx = joblog.build_context(data.task_id, user_message)
            if joblog_ctx:
                context_blocks.append(joblog_ctx)

    # ── 维度 3: 关联项目资料 ──
    source_files = []
    resolved_project_id = data.project_id
    if not resolved_project_id and data.task_id and data.task_id in tasks:
        resolved_project_id = tasks[data.task_id].get("project_id")
    if resolved_project_id:
        from core import projects
        context_text, source_files = projects.get_project_context_for_chat(resolved_project_id, user_message)
        if context_text:
            context_blocks.append(context_text)

    # ── 维度 5: 页面上下文 ──
    if data.current_page:
        page_ctx = build_page_context(data.current_page)
        if page_ctx:
            context_blocks.append(page_ctx)

    if context_blocks:
        system_prompt += "\n\n" + "\n\n---\n\n".join(context_blocks)

    logger.info("[AI对话] 注入块 task=%s mode=%s blocks=%d 详情=%s", data.task_id, data.mode, len(context_blocks), [{"head": b[:120].replace("\n", " "), "len": len(b)} for b in context_blocks])

    # ── 维度 4: 对话历史 ──
    messages = [{"role": "system", "content": system_prompt}]
    if data.history:
        for msg in data.history[-10:]:
            role = "user" if msg.get("role") == "user" else "assistant"
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    try:
        reply = await async_chat_completion(messages, model=chat_model, max_tokens=2048)
        reply = audit_reply_claims(reply, edit_changes)
        existing_todos = tasks.get(data.task_id, {}).get("todos", []) if data.task_id else []
        extracted_items = [] if edit_changes else extract_injectable_items(reply, existing_todos)
        return {
            "reply": reply,
            "sources": source_files,
            "extracted_items": extracted_items,
            "verified_changes": edit_changes,
            "action": {
                "name": detected_action.name if detected_action else None,
                "success": action_result.get("success") if action_result else None,
                "data": action_result.get("data") if action_result else None,
            } if detected_action else None,
        }
    except Exception as e:
        logger.error("AI 对话失败: %s", e)
        raise HTTPException(500, _("AI conversation failed: {err}").format(err=e))


# ============================================================
# 文稿优化端点
# ============================================================

@router.post("/api/optimize")
async def optimize_text(data: OptimizeRequest):
    """文稿优化端点。"""
    text = data.text.strip()
    if not text:
        raise HTTPException(400, _("Text cannot be empty"))
    model = data.model or "qwen-plus"
    messages = [
        {"role": "system", "content": OPTIMIZE_SYSTEM_PROMPT},
        {"role": "user", "content": f"请优化以下文本：\n\n{text}"},
    ]
    try:
        optimized = await async_chat_completion(messages, model=model, max_tokens=4096, temperature=0.3)
        return {"ok": True, "original": text, "optimized": optimized.strip()}
    except Exception as e:
        logger.error("文稿优化失败: %s", e)
        raise HTTPException(500, _("Text refinement failed: {err}").format(err=e))


# ============================================================
# 可用模型列表
# ============================================================

DASHSCOPE_MODELS = [
    {"id": "qwen-plus", "name": "Qwen3.7-Plus", "provider": "DashScope"},
    {"id": "qwen-max", "name": "Qwen3.7-Max", "provider": "DashScope"},
    {"id": "qwen-turbo", "name": "Qwen3.7-Turbo", "provider": "DashScope"},
    {"id": "qwen-long", "name": "Qwen-Long", "provider": "DashScope"},
    {"id": "qwen2.5-72b-instruct", "name": "Qwen2.5-72B", "provider": "DashScope"},
    {"id": "qwen2.5-32b-instruct", "name": "Qwen2.5-32B", "provider": "DashScope"},
]

OTHER_MODELS = [
    {"id": "gpt-4o", "name": "GPT-4o", "provider": "OpenAI"},
    {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "OpenAI"},
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "provider": "Anthropic"},
    {"id": "deepseek-chat", "name": "DeepSeek Chat", "provider": "DeepSeek"},
    {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner", "provider": "DeepSeek"},
]


@router.get("/api/models")
async def list_models():
    """获取可用模型列表。"""
    return {
        "models": DASHSCOPE_MODELS + OTHER_MODELS,
        "dashscope_models": DASHSCOPE_MODELS,
    }
