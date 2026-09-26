"""
app/routers/chat.py — AI 对话路由端点 / AI chat route endpoints

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 2.0.0

v2.0 重构：业务逻辑已拆分至 core 层子模块，本文件仅保留端点定义与编排逻辑 / v2.0 refactor: business logic split to core submodules; this file retains only endpoint definitions and orchestration.
  - core/chat_actions.py  — 动作检测与执行 / Action detection and execution
  - core/chat_edits.py    — 编辑意图解析、执行与审计 / Edit intent parsing, execution and audit
  - core/chat_context.py  — 上下文构建与注入提取 / Context building and injection extraction
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.store import (  # noqa: F401
    REALTIME_BUFFER_MAX,
    TASKS_DIR,
    realtime_transcript_buffers,
    tasks,
)
from core import joblog
from core.agent_loop import run_agent_loop
from core.agent_workspace import resolve_agent_role
from core.chat_actions import detect_action, execute_action
from core.chat_context import (
    build_insights_context_block,
    build_page_context,
    build_speaker_name_map,
    extract_injectable_items,
    is_joblog_intent,
)
from core.chat_edits import (  # noqa: F401
    _sanitize_edit_ops,
    audit_reply_claims,
    describe_change,
    execute_and_verify_edits,
    has_edit_intent,
    parse_edit_intent,
)
from core.llm import async_chat_completion, async_chat_completion_full
from core.speakers import normalize_speaker_name

# 向后兼容别名（测试与外部引用） / Backward-compatible aliases (for tests and external references)
_detect_action = detect_action
_is_joblog_intent = is_joblog_intent
_build_page_context = build_page_context
_execute_and_verify_edits = execute_and_verify_edits
_audit_reply_claims = audit_reply_claims
# ── 智能体模式（本地 CLI 引擎，可选接入）/ Agent mode (local CLI engine, optional) ──
from app.store import get_chat_engine_config  # noqa: E402
from core.cli_engine import (  # noqa: E402
    CliAgentError,
    cancel_stream,
    export_context,
    load_manifest,
    probe_engine,
    run_cli_agent,
)
from core.cli_engine.intent import classify_engine_intent  # noqa: E402
from core.cli_engine.mcp_bridge import build_bridge_config, manifest_has_mcp, teardown_bridge  # noqa: E402
from core.i18n import _

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# 单条用户消息最大长度（字符），防止超长输入耗尽 LLM token / 内存 / Max single user message length (chars); prevent exhausting LLM token/memory
MAX_CHAT_MESSAGE_LEN = 8000


def _format_time_ms(ms: int | float) -> str:
    """将毫秒时间戳格式化为 HH:MM:SS 或 MM:SS（不足 1 小时省略小时位）。"""
    if not ms or ms < 0:
        return ""
    total_sec = int(ms / 1000)
    h, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ============================================================
# 图形化意图检测与 Mermaid 生成 / Diagram intent detection & Mermaid generation
# ============================================================

_DIAGRAM_KEYWORDS = [
    "流程图", "流程", "图表", "画图", "绘制", "画一个", "画个",
    "diagram", "flowchart", "mermaid", "图形", "可视化", "关系图",
    "思维导图", "结构图", "拓扑", "网络图",
    # 图修改关键词 / Diagram modification keywords
    "修改图", "改一下", "调整图", "换个方向", "改成", "把图", "这张图",
    "这个图", "重新画", "重画", "再生成一个", "换一种", "加一个节点",
    "去掉", "改成从左到右", "改成从上到下",
]

# 图修改意图关键词 / Diagram modification intent keywords
_MODIFY_DIAGRAM_KEYWORDS = [
    "修改图", "改一下", "调整图", "换个方向", "改成", "把图",
    "这张图", "这个图", "重新画", "重画", "再生成一个", "换一种",
    "加一个节点", "去掉", "调整一下", "帮我改", "帮我调",
]


def _detect_diagram_intent(message: str) -> bool:
    """检测用户是否要求生成图形化内容。"""
    lower = message.lower()
    return any(kw in lower for kw in _DIAGRAM_KEYWORDS)


def _detect_diagram_modify_intent(message: str) -> bool:
    """检测用户是否要求修改已有的图。"""
    lower = message.lower()
    return any(kw in lower for kw in _MODIFY_DIAGRAM_KEYWORDS)


_MERMAID_GEN_PROMPT = """你是 Mermaid 图表生成器。根据用户请求，选择最合适的 Mermaid 图类型并生成代码。

规则：
1. 只返回 Mermaid 代码，不要 markdown 代码块标记
2. 根据内容选择图类型：
   - flowchart + subgraph 泳道图：跨角色/跨部门的职责分工与协作流程（用 subgraph 划分不同角色或部门）
   - flowchart（graph TD/LR）：决策路径、任务依赖、因果关系（最通用）
   - mindmap：围绕核心主题的多维度发散
   - sequenceDiagram：多方交互的时间顺序
   - gantt：时间安排和并行关系
3. 节点用中文标签
4. 保持简洁，5-15 个节点（根据内容复杂度调整）
5. 在连线上标注关系类型
6. 如果无法生成有意义的图，返回空字符串

用户请求：{user_message}

仅返回 Mermaid 代码："""

_MODIFY_DIAGRAM_PROMPT = """你是 Mermaid 图表修改器。用户希望基于现有的图进行修改。

规则：
1. 只返回修改后的完整 Mermaid 代码，不要 markdown 代码块标记
2. 保持原图的整体结构和风格，只按用户要求做局部调整
3. 节点标签用中文
4. 如果用户要求不明确，尽量保持原图不变
5. 如果无法按要求修改，返回空字符串

当前图的 Mermaid 代码：
{current_diagram}

用户的修改要求：{user_message}

仅返回修改后的 Mermaid 代码："""


async def _modify_mermaid_diagram(user_message: str, current_diagram: str, model: str) -> str:
    """调用 LLM 基于当前图和用户指令生成修改后的 Mermaid 代码。"""
    try:
        messages = [
            {"role": "system", "content": "你是 Mermaid 图表修改器。只输出修改后的 Mermaid 代码，不要其他内容。"},
            {"role": "user", "content": _MODIFY_DIAGRAM_PROMPT.format(
                current_diagram=current_diagram, user_message=user_message
            )},
        ]
        logger.info("[Mermaid] 开始修改图，model=%s, message_len=%d, diagram_len=%d", model, len(user_message), len(current_diagram))
        reply = await async_chat_completion(messages, model=model, temperature=0.3, max_tokens=800)
        cleaned = reply.strip() if reply else ""
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()
        logger.info("[Mermaid] 修改完成 len=%d", len(cleaned))
        return cleaned
    except Exception as e:
        logger.warning("[AI对话] Mermaid 修改失败: %s", e)
        return ""


async def _generate_mermaid_diagram(user_message: str, model: str) -> str:
    """调用 LLM 生成 Mermaid 图语法。"""
    try:
        messages = [
            {"role": "system", "content": "你是 Mermaid 图表生成器。只输出 Mermaid 代码，不要其他内容。"},
            {"role": "user", "content": _MERMAID_GEN_PROMPT.format(user_message=user_message)},
        ]
        logger.info("[Mermaid] 开始生成，model=%s, message_len=%d", model, len(user_message))
        reply = await async_chat_completion(messages, model=model, temperature=0.3, max_tokens=800)
        # 清理可能的 markdown 代码块标记
        cleaned = reply.strip() if reply else ""
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()
        logger.info("[Mermaid] 生成完成 len=%d", len(cleaned))
        return cleaned
    except Exception as e:
        logger.warning("[AI对话] Mermaid 生成失败: %s", e)
        return ""


# ============================================================
# 请求模型 / Request Models
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
    role: Optional[str] = None  # Agent 角色标识 / Agent role identifier
    current_diagram: Optional[str] = None  # 当前可见的 Mermaid 图源码（用于图修改） / Current visible Mermaid diagram source (for diagram modification)
    # ── 智能体模式（本地 CLI 引擎，方案 §3.5/§3.9-1）/ Agent mode via local CLI engine ──
    engine: Optional[str] = None            # None/qa=内置链路；"agent"=本地 CLI 工程化引擎；"auto"=规则分流
    stream_id: Optional[str] = None         # 本轮流标识，供 /api/chat/cancel 真取消
    auth_tier: Optional[str] = None         # 本轮授权档覆盖（可选，缺省取设置）
    resume_session: Optional[bool] = None   # 是否恢复上一 CLI 会话（多轮深度对话）
    chat_session_id: Optional[str] = None   # 面板会话标签 id，令 CLI 会话与面板会话对齐（方案 §3.6）


class OptimizeRequest(BaseModel):
    text: str
    model: Optional[str] = None


class InlineEditRequest(BaseModel):
    text: str           # 选中的原文 / Selected original text
    instruction: str    # 用户指令（如"润色"、"补充预算相关内容"） / User instruction
    model: Optional[str] = None


# ============================================================
# 系统提示词 / System Prompts
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

## 时间戳感知
- 当对话上下文包含 `[MM:SS]` 或 `[HH:MM:SS]` 格式的时间戳前缀时，表示该句发言发生在录音的对应时刻
- 用户询问"什么时候说了什么""多少秒时打的电话"等时间定位问题时，必须引用时间戳回答，而非说"未记录时间点"
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

INLINE_EDIT_SYSTEM_PROMPT = """你是一位专业的文稿编辑助手。用户会给你一段原文和一条改写指令，你需要按照指令对原文进行改写。

规则：
- 严格按照用户的指令执行改写，不要超出指令范围
- 保持原文的语言（中文或英文），除非用户明确要求翻译
- 保持 Markdown 格式（如标题、列表、加粗等）
- 只输出改写后的文本，不要添加任何解释、说明或前缀
- 如果指令不明确，尽量保持原文不变
- 改写后的文本应当可以直接替换原文，无需额外处理"""


# ============================================================
# 共享上下文构建 / Shared Context Building
# ============================================================


def _build_chat_context_blocks(data: ChatRequest, is_qa_mode: bool) -> tuple[list[str], list[dict]]:
    """为聊天请求构建上下文块（供 /api/chat 和 /api/chat/stream 共用）。
    Build context blocks for chat request (shared by /api/chat and /api/chat/stream).

    Returns:
        (context_blocks, source_files)
    """
    user_message = data.message.strip()
    context_blocks: list[str] = []
    source_files: list[dict] = []

    # ── 维度 1: 实时转写流 / Realtime transcript stream ──
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
            # BE-R3：删除 Speaker N 兑底字面量，未命名走中性措辞（聊天回复不复读编号）
            name = normalize_speaker_name(speaker_name_map.get(sid)) or "未识别发言人"
            text = entry.get("text", "").strip()
            ts = _format_time_ms(entry.get("begin_time", 0))
            if text:
                prefix = f"[{ts}] " if ts else ""
                lines.append(f"{prefix}{name}：{text}")
        if lines:
            context_blocks.append("## 实时会议对话（最近发言，含时间戳）\n" + "\n".join(lines))

    # ── 维度 2: 当前会议上下文 / Current meeting context ──
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
        if task.get("dialogue") and not realtime_entries:
            all_lines = []
            idx = 0
            for item in task["dialogue"]:
                # BE-R3：同上，归一后空名走中性措辞
                name = normalize_speaker_name(item.get("speaker_name")) or "未识别发言人"
                sents = item.get("sentences") or []
                for s in sents:
                    text = s.get("text", "").strip()
                    if text:
                        ts = _format_time_ms(s.get("begin_time", 0))
                        prefix = f"[{ts}] " if ts else ""
                        all_lines.append((s.get("begin_time", 0), f"{prefix}{name}：{text}", name, idx))
                        idx += 1
                if not sents:
                    text = item.get("text", "").strip()
                    if text:
                        all_lines.append((0, f"{name}：{text}", name, idx))
                        idx += 1
            if all_lines:
                all_lines.sort(key=lambda x: x[0])
                seen_speakers = set()
                first_per_speaker = []
                for ts_ms, line, spk, li in all_lines:
                    if spk not in seen_speakers:
                        seen_speakers.add(spk)
                        first_per_speaker.append((ts_ms, line, li))
                limit = 3000 if (summary and not is_summary_error) else 5000
                included = set()
                output_parts = []
                char_count = 0
                for ts_ms, line, li in first_per_speaker:
                    output_parts.append((ts_ms, line))
                    included.add(li)
                    char_count += len(line) + 1
                for ts_ms, line, _spk, li in all_lines:
                    if li in included:
                        continue
                    if char_count + len(line) + 1 > limit:
                        break
                    output_parts.append((ts_ms, line))
                    included.add(li)
                    char_count += len(line) + 1
                output_parts.sort(key=lambda x: x[0])
                dialogue_text = "\n".join(line for _, line in output_parts)
                if dialogue_text:
                    context_blocks.append(f"## 当前会议对话时间轴（含时间戳，智能采样覆盖所有说话人）\n{dialogue_text}")

        todos = task.get("todos") or []
        if todos:
            todo_lines = []
            for t in todos:
                status = "✅" if t.get("done") else "⬜"
                assignee = t.get("assignee", "未分配")
                todo_lines.append(f"- [{status}] {t.get('text', '')}（责任人：{assignee}）")
            context_blocks.append("## 当前会议待办事项\n" + "\n".join(todo_lines))

        # 洞察台观察结论（持久化文件，供参考非事实源） / Insight Deck observations (persisted; advisory, not source of truth)
        insights_block = build_insights_context_block(data.task_id)
        if insights_block:
            context_blocks.append(insights_block)

        if is_joblog_intent(user_message):
            joblog_ctx = joblog.build_context(data.task_id, user_message)
            if joblog_ctx:
                context_blocks.append(joblog_ctx)

    # ── 维度 3: 关联项目资料 / Linked project materials ──
    resolved_project_id = data.project_id
    if not resolved_project_id and data.task_id and data.task_id in tasks:
        resolved_project_id = tasks[data.task_id].get("project_id")
    if resolved_project_id:
        from core import projects
        context_text, source_files = projects.get_project_context_for_chat(resolved_project_id, user_message)
        if context_text:
            context_blocks.append(context_text)
        if not source_files and context_text:
            from core.project_index import get_project_index
            index = get_project_index(resolved_project_id)
            if index:
                source_files = [
                    {"title": f.get("title", f.get("name", "")), "path": f.get("relative_path", ""), "name": f.get("name", "")}
                    for f in index.get("files", [])
                ]

    # ── 维度 4: 页面上下文 / Page context ──
    if data.current_page:
        page_ctx = build_page_context(data.current_page)
        if page_ctx:
            context_blocks.append(page_ctx)

    return context_blocks, source_files


# ============================================================
# AI 对话端点 / AI Chat Endpoints
# ============================================================


def _chat_model_default() -> str:
    """会话未逐条指定 model 时的默认值：跟随详情 llm.model 设置（REQ-EXPERT-MODE §2.3）。

    「跟随详情」语义下 llm.model 变更即时反映到下一轮；设置缺失才落 qwen-plus。
    """
    try:
        from app.store import get_llm_config
        return get_llm_config().get("model") or "qwen-plus"
    except Exception:
        return "qwen-plus"


def _model_usage_meta(model: str) -> dict:
    """本轮实际消费方与计费口径回显（与 core/routing 判定同源，AC-3）。

    billing 枚举：platform_quota=消耗体验分钟数 / own_key=自有供应商计费 /
    none=本机算力不计量 / ""=判定不可得（前端隐藏计费段）。
    """
    meta = {"model": model, "source": "", "route": "", "billing": "", "auto_switched": False}
    try:
        from core.routing import get_routing_decision
        d = get_routing_decision("llm")
        meta["source"] = d.get("source") or ""
        meta["route"] = d.get("route") or ""
        meta["auto_switched"] = bool(d.get("auto_switched"))
        meta["billing"] = {"trial": "platform_quota", "byok": "own_key",
                           "local_endpoint": "none", "local": "none"}.get(meta["source"], "")
    except Exception:
        pass
    return meta

@router.post("/api/chat")
async def chat(data: ChatRequest):
    """AI 对话端点（含动作检测与执行）。 / AI chat endpoint (incl. action detection and execution)."""
    user_message = data.message.strip()
    if not user_message:
        raise HTTPException(400, _("Message cannot be empty"))
    if len(user_message) > MAX_CHAT_MESSAGE_LEN:
        raise HTTPException(
            400,
            _("Message too long (max {max} characters)").format(max=MAX_CHAT_MESSAGE_LEN),
        )

    is_qa_mode = data.mode == "qa"
    if is_qa_mode:
        system_prompt = CHAT_QA_SYSTEM_PROMPT
    else:
        # Agent 角色工作区：优先从 .md 文件加载，回退到硬编码常量 / Agent workspace: prefer .md files, fallback to hardcoded constant
        role = resolve_agent_role(data.role)
        system_prompt = role["agent_md"] if role else CHAT_SYSTEM_PROMPT
    context_blocks = []
    action_result: dict | None = None
    chat_model = data.model or _chat_model_default()

    # ── 步骤 0: 数据编辑意图 ── / ── Step 0: Data edit intent ──
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

    # ── 步骤 1: 关键词动作检测与执行 ── / ── Step 1: Keyword action detection and execution ──
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

    # ── 使用共享函数构建上下文 / Use shared function to build context ──
    ctx_blocks, src_files = _build_chat_context_blocks(data, is_qa_mode)
    context_blocks.extend(ctx_blocks)
    source_files = src_files

    if context_blocks:
        system_prompt += "\n\n" + "\n\n---\n\n".join(context_blocks)

    logger.info("[AI对话] 注入块 task=%s mode=%s blocks=%d", data.task_id, data.mode, len(context_blocks))
    # 注入块内容含会议原文/纪要，仅在 DEBUG 级别落盘，避免 INFO 日志泄露敏感内容 / Injection blocks contain meeting originals/summaries; only log at DEBUG level to avoid INFO log leaking sensitive content
    logger.debug("[AI对话] 注入块详情=%s", [{"head": b[:120].replace("\n", " "), "len": len(b)} for b in context_blocks])

    # ── 维度 4: 对话历史 ── / ── Dimension 4: Conversation history ──
    messages = [{"role": "system", "content": system_prompt}]
    if data.history:
        for msg in data.history[-10:]:
            role = "user" if msg.get("role") == "user" else "assistant"
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    try:
        llm_start = time.perf_counter()
        llm_result = await async_chat_completion_full(messages, model=chat_model, max_tokens=2048)
        llm_latency_ms = round((time.perf_counter() - llm_start) * 1000)
        reply = audit_reply_claims(llm_result.content, edit_changes)
        existing_todos = tasks.get(data.task_id, {}).get("todos", []) if data.task_id else []
        extracted_items = [] if edit_changes else extract_injectable_items(reply, existing_todos)

        # 图形化意图检测：用户要求画图或修改当前图时，生成 Mermaid 代码
        diagram = ""
        if data.current_diagram and _detect_diagram_modify_intent(user_message):
            logger.info("[AI对话] 检测到图修改意图，基于当前图生成修改")
            diagram = await _modify_mermaid_diagram(user_message, data.current_diagram, chat_model)
        elif _detect_diagram_intent(user_message):
            logger.info("[AI对话] 检测到画图意图，生成 Mermaid 图")
            diagram = await _generate_mermaid_diagram(user_message, chat_model)

        return {
            "reply": reply,
            "diagram": diagram,
            "model_usage": _model_usage_meta(llm_result.model or chat_model),
            "metadata": {
                "model": llm_result.model,
                "usage": llm_result.usage,
                "finish_reason": llm_result.finish_reason,
                "id": llm_result.id,
            },
            "latency_ms": llm_latency_ms,
            "context_block_count": len(context_blocks),
            "message_count": len(messages),
            "sources": source_files,
            "extracted_items": extracted_items,
            "verified_changes": edit_changes,
            "action": {
                "name": detected_action.name if detected_action else None,
                "success": action_result.get("success") if action_result else None,
                "data": action_result.get("data") if action_result else None,
            } if detected_action else None,
        }
    except RuntimeError as e:
        # LLM 配置错误、云端降级失败等 — 返回用户可理解的错误信息
        # LLM config errors, cloud fallback failures — return user-friendly error
        logger.error("AI 对话失败（配置/降级错误）: %s", e)
        raise HTTPException(
            503,
            {
                "error": "llm_unavailable",
                "message": str(e),
                "hint": _("Please configure API Key in Settings, or check cloud service availability."),
            },
        )
    except Exception as e:
        logger.error("AI 对话失败: %s", e)
        raise HTTPException(500, _("AI conversation failed: {err}").format(err=e))


# ============================================================
# AI 对话流式端点 / AI Chat Streaming Endpoint
# ============================================================

def _build_chat_messages(data: ChatRequest) -> tuple[list[dict], str, list]:
    """从请求数据构建 LLM 消息列表（供 /api/chat 和 /api/chat/stream 共用）。
    Build LLM messages from request data (shared by /api/chat and /api/chat/stream).

    Returns:
        (messages, chat_model, source_files)
    """
    user_message = data.message.strip()
    is_qa_mode = data.mode == "qa"
    if is_qa_mode:
        system_prompt = CHAT_QA_SYSTEM_PROMPT
    else:
        role = resolve_agent_role(data.role)
        system_prompt = role["agent_md"] if role else CHAT_SYSTEM_PROMPT
    context_blocks: list[str] = []
    chat_model = data.model or _chat_model_default()

    # ── 实时转写流 / Realtime transcript stream ──
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
            # BE-R3：删除 Speaker N 兑底字面量，未命名走中性措辞（聊天回复不复读编号）
            name = normalize_speaker_name(speaker_name_map.get(sid)) or "未识别发言人"
            text = entry.get("text", "").strip()
            ts = _format_time_ms(entry.get("begin_time", 0))
            if text:
                prefix = f"[{ts}] " if ts else ""
                lines.append(f"{prefix}{name}：{text}")
        if lines:
            context_blocks.append("## 实时会议对话（最近发言，含时间戳）\n" + "\n".join(lines))

    # ── 当前会议上下文 / Current meeting context ──
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
        if task.get("dialogue") and not realtime_entries:
            all_lines = []
            idx = 0
            for item in task["dialogue"]:
                # BE-R3：同上，归一后空名走中性措辞
                name = normalize_speaker_name(item.get("speaker_name")) or "未识别发言人"
                sents = item.get("sentences") or []
                for s in sents:
                    text = s.get("text", "").strip()
                    if text:
                        ts = _format_time_ms(s.get("begin_time", 0))
                        prefix = f"[{ts}] " if ts else ""
                        all_lines.append((s.get("begin_time", 0), f"{prefix}{name}：{text}", name, idx))
                        idx += 1
                if not sents:
                    text = item.get("text", "").strip()
                    if text:
                        all_lines.append((0, f"{name}：{text}", name, idx))
                        idx += 1
            if all_lines:
                all_lines.sort(key=lambda x: x[0])
                seen_speakers = set()
                first_per_speaker = []
                for ts_ms, line, spk, li in all_lines:
                    if spk not in seen_speakers:
                        seen_speakers.add(spk)
                        first_per_speaker.append((ts_ms, line, li))
                limit = 3000 if (summary and not is_summary_error) else 5000
                included = set()
                output_parts = []
                char_count = 0
                for ts_ms, line, li in first_per_speaker:
                    output_parts.append((ts_ms, line))
                    included.add(li)
                    char_count += len(line) + 1
                for ts_ms, line, _spk, li in all_lines:
                    if li in included:
                        continue
                    if char_count + len(line) + 1 > limit:
                        break
                    output_parts.append((ts_ms, line))
                    included.add(li)
                    char_count += len(line) + 1
                output_parts.sort(key=lambda x: x[0])
                dialogue_text = "\n".join(line for _, line in output_parts)
                if dialogue_text:
                    context_blocks.append(f"## 当前会议对话时间轴（含时间戳，智能采样覆盖所有说话人）\n{dialogue_text}")

        todos = task.get("todos") or []
        if todos:
            todo_lines = []
            for t in todos:
                status = "✅" if t.get("done") else "⬜"
                assignee = t.get("assignee", "未分配")
                todo_lines.append(f"- [{status}] {t.get('text', '')}（责任人：{assignee}）")
            context_blocks.append("## 当前会议待办事项\n" + "\n".join(todo_lines))

        # 洞察台观察结论（与 _build_chat_context_blocks 对等） / Insight Deck observations (parity with shared builder)
        insights_block = build_insights_context_block(data.task_id)
        if insights_block:
            context_blocks.append(insights_block)

    # ── 关联项目资料 / Linked project materials ──
    source_files: list[dict] = []
    resolved_project_id = data.project_id
    if not resolved_project_id and data.task_id and data.task_id in tasks:
        resolved_project_id = tasks[data.task_id].get("project_id")
    if resolved_project_id:
        from core import projects
        context_text, source_files = projects.get_project_context_for_chat(resolved_project_id, user_message)
        if context_text:
            context_blocks.append(context_text)
        if not source_files and context_text:
            from core.project_index import get_project_index
            index = get_project_index(resolved_project_id)
            if index:
                source_files = [
                    {"title": f.get("title", f.get("name", "")), "path": f.get("relative_path", ""), "name": f.get("name", "")}
                    for f in index.get("files", [])
                ]

    # ── 页面上下文 / Page context ──
    if data.current_page:
        page_ctx = build_page_context(data.current_page)
        if page_ctx:
            context_blocks.append(page_ctx)

    if context_blocks:
        system_prompt += "\n\n" + "\n\n---\n\n".join(context_blocks)

    # ── 对话历史 / Conversation history ──
    messages = [{"role": "system", "content": system_prompt}]
    if data.history:
        for msg in data.history[-10:]:
            role = "user" if msg.get("role") == "user" else "assistant"
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    return messages, chat_model, source_files


# ============================================================
# 智能体模式（本地 CLI 引擎）/ Agent mode (local CLI engine)
# ============================================================

def _deterministic_session_id(task_id: str | None, project_id: str | None,
                              chat_session_id: str | None = None) -> str:
    """由 chat_session_id（优先）/task_id/project_id 派生稳定会话 id，与面板会话对齐（方案 §3.6）。"""
    import uuid
    seed = chat_session_id or task_id or project_id or "general"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "oms-agent:" + seed))


def _resolve_project_path(project_id: str | None) -> str | None:
    """解析项目关联文件夹首个存在的目录，供 --add-dir 挂载（不复制）。"""
    if not project_id:
        return None
    try:
        from core import projects
        proj = projects.get_project(project_id)
        for f in (proj or {}).get("folders") or []:
            p = f.get("path")
            if p and Path(p).is_dir():
                return p
    except Exception as e:  # noqa: BLE001
        logger.debug("[智能体模式] 项目路径解析失败 project=%s: %s", project_id, e)
    return None


async def _agent_engine_events(data: ChatRequest, user_message: str, resolved_project_id: str | None,
                               base_url: str = "http://127.0.0.1:8000", auto_selected: bool = False):
    """
    智能体模式事件生成器：探针 → 上下文导出 → CLI 流式事件。
    引擎不可用/启动失败时 yield ``{"type":"__fallback__"}`` 哨兵，由外层回退内置链路。
    """
    cfg = get_chat_engine_config()
    loop = asyncio.get_running_loop()

    # ① 可用性探针（同步 subprocess → 线程池，避免阻塞事件循环）
    probe_result: dict
    try:
        manifest = load_manifest(cfg["engine_id"])
        probe_result = await loop.run_in_executor(
            None, lambda: probe_engine(manifest, cfg.get("cli_path_override")))
    except FileNotFoundError:
        probe_result = {"available": False, "reason": "not_installed",
                        "display_name": cfg["engine_id"], "hint": "chatEngine.notInstalled"}
    if not probe_result.get("available"):
        name = probe_result.get("display_name", "CLI")
        hint = probe_result.get("hint", "chatEngine.probeError")
        logger.info("[智能体模式] 引擎不可用 reason=%s，回退内置", probe_result.get("reason"))
        yield {"type": "stage", "stage": "thinking", "label": f"⚠️ 智能体引擎（{name}）不可用，已回退内置问答"}
        yield {"type": "__fallback__", "hint": hint}
        return

    # ② 上下文导出到工作区（物理隔离于 data/，M3）
    task = dict(tasks[data.task_id]) if (data.task_id and data.task_id in tasks) else None
    if task is not None and resolved_project_id and not task.get("project_path"):
        ppath = _resolve_project_path(resolved_project_id)
        if ppath:
            task["project_path"] = ppath
    speaker_map = build_speaker_name_map(data.task_id) if data.task_id else {}
    role = resolve_agent_role(data.role)
    role_prompt = role["agent_md"] if role else ""
    page_ctx = build_page_context(data.current_page) if data.current_page else ""

    export = await loop.run_in_executor(None, lambda: export_context(
        engine_id=cfg["engine_id"], task=task, task_id=data.task_id, user_message=user_message,
        page_context=page_ctx, role_prompt=role_prompt, speaker_map=speaker_map,
        workspace_key=data.chat_session_id or data.task_id))

    session_id = _deterministic_session_id(data.task_id, resolved_project_id, data.chat_session_id) if cfg["session_persistence"] else None
    auth_tier = data.auth_tier if data.auth_tier in ("readonly", "workspace_write", "full_task") else cfg["auth_tier"]

    # ③ 路由回显（§3.9-1）：明示本次由智能体执行 + 授权档，静默分流摧毁信任
    yield {"type": "engine_route", "engine": cfg["engine_id"], "display_name": probe_result.get("display_name"),
           "auth_tier": auth_tier, "session_id": session_id, "auto_selected": auto_selected}

    # ④ MCP 桥：签发单轮短时令牌 + 写临时 mcp-config（回连 base_url），轮次结束回收
    mcp_config_path: str | None = None
    bridge_token: str | None = None
    allowed_tools: list[str] = []
    if manifest_has_mcp(cfg["engine_id"]):
        try:
            mcp_config_path, tok_ctx, allowed_tools = build_bridge_config(
                task_id=data.task_id, project_id=resolved_project_id,
                auth_tier=auth_tier, base_url=base_url)
            bridge_token = tok_ctx.token
        except Exception as e:  # noqa: BLE001 - 桥不可用不阻断只读深度问答
            logger.warning("[智能体模式] MCP 桥初始化失败（降级为无工具）：%s", e)

    stream_id = data.stream_id or session_id or f"adhoc-{id(data)}"
    try:
        async for evt in run_cli_agent(
            stream_id=stream_id, engine_id=cfg["engine_id"], cli_path=probe_result["path"],
            workspace=export["workspace"], add_dirs=export["add_dirs"], brief=export["brief"],
            auth_tier=auth_tier, model=cfg.get("model"), session_id=session_id,
            resume=bool(data.resume_session and session_id),
            mcp_config=mcp_config_path, allowed_tools=allowed_tools,
        ):
            if evt.get("type") == "done":
                evt.setdefault("metadata", {})
                evt["metadata"]["engine"] = cfg["engine_id"]
            yield evt
    except CliAgentError as e:
        logger.warning("[智能体模式] CLI 启动失败：%s，回退内置", e)
        yield {"type": "__fallback__", "hint": str(e)}
    finally:
        if mcp_config_path and bridge_token:
            teardown_bridge(mcp_config_path, bridge_token)


@router.post("/api/chat/cancel")
async def chat_cancel(data: dict):
    """真取消端点（方案 §3.9-5）：kill CLI 进程组，前端 fetch abort 不足以终止任务。"""
    stream_id = (data or {}).get("stream_id") or ""
    hit = cancel_stream(stream_id) if stream_id else False
    return {"ok": True, "cancelled": hit, "stream_id": stream_id}


@router.post("/api/chat/stream")
async def chat_stream(data: ChatRequest, request: Request):
    """AI 对话流式端点（SSE + Agent 循环）。 / AI chat streaming endpoint (SSE + Agent loop).

    使用 ReAct Agent 循环：LLM 自主决策调用工具 → 执行 → 结果回传 → 最终流式回复。
    Uses ReAct agent loop: LLM decides tool calls → execute → feed back → final streaming answer.
    """
    user_message = data.message.strip()
    if not user_message:
        raise HTTPException(400, _("Message cannot be empty"))
    if len(user_message) > MAX_CHAT_MESSAGE_LEN:
        raise HTTPException(
            400,
            _("Message too long (max {max} characters)").format(max=MAX_CHAT_MESSAGE_LEN),
        )

    # 解析系统提示词（Agent 角色） / Resolve system prompt (agent role)
    is_qa_mode = data.mode == "qa"
    if is_qa_mode:
        system_prompt = CHAT_QA_SYSTEM_PROMPT
    else:
        role = resolve_agent_role(data.role)
        system_prompt = role["agent_md"] if role else CHAT_SYSTEM_PROMPT

    # 使用共享函数构建上下文并注入系统提示词 / Use shared function to build context and inject into system prompt
    context_blocks, source_files = _build_chat_context_blocks(data, is_qa_mode)
    if context_blocks:
        system_prompt += "\n\n" + "\n\n---\n\n".join(context_blocks)

    logger.info("[AI对话-流式] 注入块 task=%s mode=%s blocks=%d", data.task_id, data.mode, len(context_blocks))
    logger.debug("[AI对话-流式] 注入块详情=%s", [{"head": b[:120].replace("\n", " "), "len": len(b)} for b in context_blocks])

    chat_model = data.model or _chat_model_default()

    # 解析项目 ID / Resolve project ID
    resolved_project_id = data.project_id
    if not resolved_project_id and data.task_id and data.task_id in tasks:
        resolved_project_id = tasks[data.task_id].get("project_id")

    async def event_generator():
        # ── 引擎选择：agent=强制、auto=规则分流（§3.5/D4）；不可用时自动回退内置 ──
        if get_chat_engine_config()["enabled"] and (
                data.engine == "agent" or (data.engine == "auto" and classify_engine_intent(user_message) == "agent")):
            need_fallback = False
            async for evt in _agent_engine_events(data, user_message, resolved_project_id,
                                                   base_url=str(request.base_url).rstrip("/"),
                                                   auto_selected=(data.engine == "auto")):
                if evt.get("type") == "__fallback__":
                    need_fallback = True
                    break
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
            if not need_fallback:
                return
            # 需要回退：继续下方内置 agent_loop（已构建的 system_prompt/context 复用）

        full_content = ""
        try:
            async for event in run_agent_loop(
                user_message=user_message,
                system_prompt=system_prompt,
                history=data.history or [],
                task_id=data.task_id,
                project_id=resolved_project_id,
                model=chat_model,
            ):
                evt_type = event.get("type")

                if evt_type == "token":
                    full_content += event.get("content", "")
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                elif evt_type == "done":
                    # 后处理：提取可注入项 / Post-processing: extract injectable items
                    existing_todos = tasks.get(data.task_id, {}).get("todos", []) if data.task_id else []
                    extracted_items = extract_injectable_items(full_content, existing_todos)
                    event["extracted_items"] = extracted_items
                    # 回复尾部消费方/计费回显（REQ-EXPERT-MODE §2.3：与 routing 实际判定一致）
                    event["model_usage"] = _model_usage_meta(chat_model)

                    # 图形化意图检测：用户要求画图或修改当前图时，生成 Mermaid 代码
                    diagram = ""
                    if data.current_diagram and _detect_diagram_modify_intent(user_message):
                        logger.info("[AI对话] 检测到图修改意图，基于当前图生成修改")
                        diagram = await _modify_mermaid_diagram(user_message, data.current_diagram, chat_model)
                    elif _detect_diagram_intent(user_message):
                        logger.info("[AI对话] 检测到画图意图，生成 Mermaid 图")
                        diagram = await _generate_mermaid_diagram(user_message, chat_model)
                    if diagram:
                        event["diagram"] = diagram
                        logger.info("[AI对话] diagram 长度=%d, 随 done 事件发送", len(diagram))

                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                else:
                    # stage / tool_call / tool_result / error — 直接转发
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error("AI Agent 对话流式失败: %s", e)
            err_msg = str(e)
            if not full_content:
                yield f"data: {json.dumps({'type': 'error', 'content': err_msg}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'done', 'metadata': {'model': chat_model}, 'error': err_msg}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# 文稿优化端点 / Text Optimization Endpoint
# ============================================================

@router.post("/api/optimize")
async def optimize_text(data: OptimizeRequest):
    """文稿优化端点。 / Text optimization endpoint."""
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
# 行间编辑端点 / Inline Edit Endpoint
# ============================================================

@router.post("/api/inline-edit")
async def inline_edit(data: InlineEditRequest):
    """行间编辑端点。根据用户指令对选中文本进行 AI 改写。 / Inline edit endpoint. Rewrite selected text based on user instruction."""
    text = data.text.strip()
    instruction = data.instruction.strip()
    if not text:
        raise HTTPException(400, _("Text cannot be empty"))
    if not instruction:
        raise HTTPException(400, _("Instruction cannot be empty"))
    model = data.model or "qwen-plus"
    messages = [
        {"role": "system", "content": INLINE_EDIT_SYSTEM_PROMPT},
        {"role": "user", "content": f"改写指令：{instruction}\n\n原文：\n{text}"},
    ]
    try:
        edited = await async_chat_completion(messages, model=model, max_tokens=4096, temperature=0.3)
        return {"ok": True, "original": text, "edited": edited.strip()}
    except Exception as e:
        logger.error("行间编辑失败: %s", e)
        raise HTTPException(500, _("Inline edit failed: {err}").format(err=e))


# ============================================================
# 可用模型列表 / Available Model List
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
    """获取可用模型列表。 / Get available model list."""
    return {
        "models": DASHSCOPE_MODELS + OTHER_MODELS,
        "dashscope_models": DASHSCOPE_MODELS,
    }
