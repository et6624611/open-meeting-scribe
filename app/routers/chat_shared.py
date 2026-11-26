"""app/routers/chat_shared.py — AI 对话路由共享模块。

共享内容：常量 / 兼容别名 / Pydantic 模型 / 系统提示词 /
  @mention / @附件 / Mermaid 工具 / 上下文构建 / 模型选择。
作者 / Author: Yongliang Wang
创建 / Created: 2026-11-05（从 chat.py 拆分）
"""

import base64
import logging
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from app import chat_attachment_store
from core import joblog, prompts
from core.agent_workspace import resolve_agent_role
from core.chat_actions import detect_action
from core.chat_context import (
    build_insights_context_block,
    build_page_context,
    build_speaker_name_map,
    is_joblog_intent,
    task_final_summary,
    task_notes,
)
from core.chat_edits import (  # noqa: F401
    _sanitize_edit_ops,
    audit_reply_claims,
    describe_change,
    execute_and_verify_edits,
    has_edit_intent,
    parse_edit_intent,
)
from core.insights import sanitize_mermaid_diagram
from core.llm import (  # noqa: F401
    async_chat_completion,
    async_chat_completion_full,
    async_chat_completion_stream,
)
from core.meeting_search import build_scope_context
from core.realtime_store import (  # noqa: F401
    REALTIME_BUFFER_MAX,
    realtime_transcript_buffers,
)
from core.speakers import normalize_speaker_name
from core.task_store import (  # noqa: F401
    TASKS_DIR,
    tasks,
)

# 向后兼容别名（测试与外部引用） / Backward-compatible aliases
_detect_action = detect_action
_is_joblog_intent = is_joblog_intent
_build_page_context = build_page_context
_execute_and_verify_edits = execute_and_verify_edits
_audit_reply_claims = audit_reply_claims


# noqa: E402 — 底部 re-export 兼容层：供 chat.py 的 from .chat_shared import * 透出
from core.settings_store import get_chat_engine_config  # noqa: F401

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)
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
# ── @ 引用令牌（用户显式引用，升级替换自动采样口径） / @ mention tokens (explicit citation overrides sampled auto-injection) ──
# 令牌随消息进 history 不展开（防每轮重复注入全文）；只扫当前轮 user_message。
# 英文环境前端插入英文别名（@transcript/@summary/@notes），扫描后归一为中文令牌。
_MENTION_TOKEN_RE = re.compile(r"(?:^|\s)@(原文|纪要|随记|transcript|summary|notes)", re.IGNORECASE)
_MENTION_TOKEN_ALIASES = {"transcript": "原文", "summary": "纪要", "notes": "随记"}
# @原文 全量原文封顶 / @纪要·@随记 全量文档封顶（字符）
MENTION_TRANSCRIPT_CAP = 20000
MENTION_DOC_CAP = 12000


def _scan_mention_tokens(user_message: str) -> set[str]:
    """扫描当前轮用户消息中的 @ 引用令牌，返回含 @ 的完整令牌集（如 {'@原文'}）。
    英文别名归一为中文令牌；残缺令牌如 @原 忽略。"""
    return {f"@{_MENTION_TOKEN_ALIASES.get(t.lower(), t)}" for t in _MENTION_TOKEN_RE.findall(user_message)}


def _truncate_mention_text(text: str, cap: int, label: str) -> str:
    """全量引用块封顶截断，尾注声明截断事实（防模型把截断当全量）。"""
    if len(text) <= cap:
        return text
    return text[:cap] + f"\n…（{label}过长，已截断至前 {cap} 字）"
def _flatten_dialogue_entries(task: dict) -> list[tuple[int, str, str, int]]:
    """展平任务对话为 (begin_time, 行文本, 说话人, 句序) 列表，按时间排序。

    采样时间轴块与 @原文 全量块共用此展平结果，避免两处各写一套遍历。
    """
    all_lines: list[tuple[int, str, str, int]] = []
    idx = 0
    for item in task.get("dialogue") or []:
        # BE-R3：归一后空名走中性措辞
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
    all_lines.sort(key=lambda x: x[0])
    return all_lines
# @附件：本地文件与图片展开（当前轮） / @attachment: local files & images (current turn only)
# 可直接当文本读取的扩展名（UTF-8 解码失败则降级为不可读声明）
_ATTACHMENT_TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".log", ".xml",
    ".yaml", ".yml", ".ini", ".conf", ".py", ".js", ".ts", ".html", ".css",
    ".java", ".go", ".rs", ".c", ".h", ".cpp", ".sh", ".sql",
}
ATTACHMENT_TEXT_CAP = 8000  # 单个非图片附件抽取文本封顶（字符）


def _extract_attachment_text(filename: str, data: bytes) -> str | None:
    """抽取附件文本；无法解析的类型返回 None。"""
    ext = Path(filename).suffix.lower()
    try:
        if ext in _ATTACHMENT_TEXT_EXTS:
            return data.decode("utf-8", errors="strict")
        if ext == ".docx":
            import io

            from docx import Document  # python-docx
            doc = Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        if ext == ".pdf":
            import io

            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as e:  # 解码/解析失败：不可读，不编造
        logger.info("附件文本抽取失败 name=%s: %s", filename, e)
        return None
    return None
def _build_attachment_parts(attachment_refs: list[dict]) -> tuple[list[dict], str]:
    """把当前轮附件展开为 OpenAI 风格 user content parts，并返回系统侧说明块。

    - 图片：image_url + base64 data URI（要求视觉模型）
    - 可抽取文本：text part（封顶，带截断声明）
    - 不可读：text part 仅声明文件名/类型/大小，要求模型不臆测内容
    """
    parts: list[dict] = []
    listed: list[str] = []
    image_count = 0

    for ref in attachment_refs:
        meta, data = chat_attachment_store.load_bytes(str(ref.get("id", "")))
        name, ctype, size = meta["filename"], meta["content_type"], meta["size"]
        listed.append(f"- {name}（{ctype}，{size} 字节）")

        if ctype.startswith("image/"):
            b64 = base64.b64encode(data).decode("ascii")
            parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{ctype};base64,{b64}"},
            })
            image_count += 1
            continue

        text = _extract_attachment_text(name, data)
        if text is not None and text.strip():
            body = text
            if len(body) > ATTACHMENT_TEXT_CAP:
                body = body[:ATTACHMENT_TEXT_CAP] + f"\n…（附件 {name} 内容过长，已截断至前 {ATTACHMENT_TEXT_CAP} 字）"
            parts.append({"type": "text", "text": f"[用户附件 {name} 的内容]\n{body}"})
        else:
            parts.append({"type": "text", "text": (
                f"[用户附件 {name}] 类型 {ctype}，大小 {size} 字节，系统无法解析其内容。"
                "你看不到该文件的实际内容，禁止根据文件名臆测或编造其内容。")})

    notice = (
        "## 用户本轮上传的附件（用户显式提供，优先级高于猜测）\n"
        + "\n".join(listed)
        + (f"\n其中 {image_count} 张图片以视觉内容直接提供；其余可解析附件内容随本轮用户消息展开，"
           "标注「无法解析」的文件只有文件名——禁止编造其内容。" if image_count
           else "\n可解析附件内容随本轮用户消息展开；标注「无法解析」的文件只有文件名——禁止编造其内容。")
    )
    return parts, notice
# 图形化意图检测与 Mermaid 生成 / Diagram intent detection & Mermaid generation

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
        # 非 Mermaid 语法（模型返回说明文字等）直接降级为空串，避免前端渲染必失败 / Degrade non-Mermaid output to empty
        cleaned = sanitize_mermaid_diagram(cleaned)
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
        # 非 Mermaid 语法（模型返回说明文字等）直接降级为空串，避免前端渲染必失败 / Degrade non-Mermaid output to empty
        cleaned = sanitize_mermaid_diagram(cleaned)
        logger.info("[Mermaid] 生成完成 len=%d", len(cleaned))
        return cleaned
    except Exception as e:
        logger.warning("[AI对话] Mermaid 生成失败: %s", e)
        return ""
# 请求模型 / Request Models

class ChatRequest(BaseModel):
    message: str
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    # 提问范围（按问题检索）：meeting=本场会议（默认）/ all=全部会议
    scope: Optional[str] = None
    history: Optional[list[dict]] = None
    realtime_transcripts: Optional[list[dict]] = None
    mode: Optional[str] = None
    model: Optional[str] = None
    current_page: Optional[str] = None
    role: Optional[str] = None  # Agent 角色标识 / Agent role identifier
    current_diagram: Optional[str] = None  # 当前可见的 Mermaid 图源码（用于图修改） / Current visible Mermaid diagram source (for diagram modification)
    # ── 智能体模式（本地 CLI 引擎，方案 §3.5/§3.9-1）/ Agent mode via local CLI engine ──
    engine: Optional[str] = None            # None/qa=内置链路；"agent"=本地 CLI 工程化引擎（auto 规则分流已退役：AI 算力入口治理 §1）
    stream_id: Optional[str] = None         # 本轮流标识，供 /api/chat/cancel 真取消
    auth_tier: Optional[str] = None         # 本轮授权档覆盖（可选，缺省取设置）
    resume_session: Optional[bool] = None   # 是否恢复上一 CLI 会话（多轮深度对话）
    chat_session_id: Optional[str] = None   # 面板会话标签 id，令 CLI 会话与面板会话对齐（方案 §3.6）
    agent_model: Optional[str] = None       # 智能体轮级模型覆盖（已发消息编辑再发送），缺省取 chat_engine.model
    attachments: Optional[list[dict]] = None  # 当前轮 @附件 引用（每项至少 {"id": ...}），仅当前轮展开


class OptimizeRequest(BaseModel):
    text: str
    model: Optional[str] = None


class InlineEditRequest(BaseModel):
    text: str           # 选中的原文 / Selected original text
    instruction: str    # 用户指令（如"润色"、"补充预算相关内容"） / User instruction
    model: Optional[str] = None


class ChatTitleRequest(BaseModel):
    first_message: str                    # 会话首条用户消息 / First user message of the session
    reply: Optional[str] = ""             # 首轮 AI 回复（截断后片段） / First AI reply snippet
    model: Optional[str] = None


# T-24：提示词常量下沉 core/prompts.py，此处仅 re-export 供既有按符号 import 兼容
CHAT_SYSTEM_PROMPT = prompts.CHAT_SYSTEM_PROMPT

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
""" + "\n\n" + prompts.RETRIEVAL_DISCIPLINE
def _agent_system_prompt(role_name: str | None) -> str:
    """组装智能体模式系统提示词：角色 AGENT.md + 角色洞察板职责补充（insights.md）。

    洞察板内容契约放在角色文件中、随每次智能体会话全程可见，而非只在模型决定
    调用 revise_insight_board 时经工具描述看到；自定义角色无 insights.md 时自然降级。
    问答模式不走此函数（无工具调用权，不承载洞察板职责）。
    """
    role = resolve_agent_role(role_name)
    if not role:
        return CHAT_SYSTEM_PROMPT
    prompt = role["agent_md"]
    insight_prompt = (role.get("extra_files") or {}).get("insights.md")
    if insight_prompt:
        # insights.md 同时供洞察台分析器使用（get_role_insight_prompt 读全文）；
        # 其「输出格式」节是分析器的 JSON 返回契约，注入对话会让聊天回复退化为裸 JSON，
        # 对话链路只保留职责与观察角度，剥离该节（无此节的角色文件原样注入）。
        insight_prompt = insight_prompt.split("\n## 输出格式", 1)[0]
        prompt += "\n\n---\n\n" + insight_prompt
    return prompt
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
TITLE_SYSTEM_PROMPT = """你为一段简短的 AI 对话生成一个会话标题。

规则：
1. 只输出标题文本，不要引号、编号、解释
2. 标题不超过 12 个汉字（或 20 个英文字符），越短越好
3. 与对话使用同一语言；优先提取用户原始问题的核心词，不要过度包装
4. 如果内容涉及会议，直接提取主题（如"项目排期"、"预算评审"）
5. 严禁使用"关于"、"针对"等前缀，不要用"问题"、"话题"等泛化词结尾
6. 仅返回一行标题，不要换行"""


async def build_web_reference_block(data: ChatRequest, is_qa_mode: bool) -> str:
    """联网检索增强（内置问答路径）：讨论涉及会外专业知识时先行检索并注入「外部参考」块。

    复用 core.insights._augment_with_web_search（预判-注入式，与洞察卡分析同口径）。
    内置问答为单轮补全、无工具循环，故以注入块而非工具调用提供外部知识；
    CLI 智能体路径不经此函数（其工具循环可直接调 web_search）。
    问答模式 / 无任务 / 未配置搜索 key / 任一环节失败一律返回空串，绝不阻断问答主流程。
    """
    if is_qa_mode or not data.task_id or data.task_id not in tasks:
        return ""
    try:
        task = tasks[data.task_id]
        recent_lines: list[dict] = []
        for item in task.get("dialogue") or []:
            for s in item.get("sentences") or []:
                text = (s.get("text") or "").strip()
                if text:
                    recent_lines.append({"text": text, "begin_time": s.get("begin_time", 0)})
        recent_lines = recent_lines[-30:]
        if not recent_lines:
            return ""
        chapter_titles = [
            str(c.get("title", "")).strip()
            for c in (task.get("chapters") or []) if c.get("title")
        ]
        from core.insights import _augment_with_web_search
        return await _augment_with_web_search(recent_lines, chapter_titles)
    except Exception as e:
        logger.warning("[AI对话] 联网检索增强失败（退化为无检索问答）: %s", e)
        return ""


def _build_chat_context_blocks(
    data: ChatRequest, is_qa_mode: bool,
) -> tuple[list[str], list[dict], dict]:
    """为聊天请求构建上下文块（供 /api/chat 和 /api/chat/stream 共用）。
    Build context blocks for chat request (shared by /api/chat and /api/chat/stream).

    Returns:
        (context_blocks, source_files, retrieval)
        retrieval 为提问范围检索统计，两条链路共用同一份结果。
    """
    user_message = data.message.strip()
    context_blocks: list[str] = []
    source_files: list[dict] = []

    # ── 维度 0: @ 引用令牌 / @ mention tokens ──
    # 用户显式引用升级替换自动采样口径：@原文 跳过采样时间轴与实时 10 句块，@纪要/@随记 全量。
    mention_tokens = _scan_mention_tokens(user_message)
    full_transcript_emitted = False  # @原文 全量块是否已注入（会中实时流优先，落空则回退落盘对话）

    # ── 维度 1: 实时转写流 / Realtime transcript stream ──
    # 后端内存缓冲优先（SDK 回调线程持续写入，不受前端上报滞后/缺漏影响），前端快照兜底
    realtime_entries = []
    if data.task_id and data.task_id in realtime_transcript_buffers:
        realtime_entries = realtime_transcript_buffers[data.task_id]
    elif data.realtime_transcripts:
        realtime_entries = data.realtime_transcripts[-REALTIME_BUFFER_MAX:]

    if realtime_entries:
        speaker_name_map = build_speaker_name_map(data.task_id) if data.task_id else {}
        if "@原文" in mention_tokens:
            # 显式引用 @原文（会中）：实时流全量入场，替代自动注入的最近 10 句
            lines = []
            for entry in realtime_entries:
                sid = entry.get("speaker_id")
                name = normalize_speaker_name(speaker_name_map.get(sid)) or "未识别发言人"
                text = entry.get("text", "").strip()
                ts = _format_time_ms(entry.get("begin_time", 0))
                if text:
                    prefix = f"[{ts}] " if ts else ""
                    lines.append(f"{prefix}{name}：{text}")
            if lines:
                full_text = _truncate_mention_text("\n".join(lines), MENTION_TRANSCRIPT_CAP, "逐字稿原文")
                context_blocks.append(f"## 用户显式引用（@原文）——全量实时转写，优先于采样摘要\n{full_text}")
                full_transcript_emitted = True
        else:
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

        # 纪要取定稿口径（用户编辑过则为编辑版），与前端纪要 Tab 一致；
        # @纪要 显式引用时取全量（升级替换采样截断口径）
        summary = task_final_summary(task)
        is_summary_error = "内容过短" in summary or "无法生成有效纪要" in summary
        if summary and not is_summary_error:
            if "@纪要" in mention_tokens:
                context_blocks.append(
                    "## 用户显式引用（@纪要）——全量纪要，优先于采样摘要\n"
                    + _truncate_mention_text(summary, MENTION_DOC_CAP, "纪要")
                )
            else:
                context_blocks.append(f"## 当前会议纪要\n{summary[:2000]}")
        elif "@纪要" in mention_tokens:
            context_blocks.append("## 用户显式引用（@纪要）\n当前会议暂无可用纪要。直接如实告知用户，不要编造纪要内容。")
        # 随记：用户手写要点，此前只有纪要生成链路能读到，会话侧一直缺失（2026-09-30 复盘）；
        # @随记 显式引用时取全量（升级替换采样截断口径）
        notes = task_notes(task)
        if notes:
            if "@随记" in mention_tokens:
                context_blocks.append(
                    "## 用户显式引用（@随记）——全量随记，优先于采样摘要\n"
                    + _truncate_mention_text(notes, MENTION_DOC_CAP, "随记")
                )
            else:
                context_blocks.append(f"## 用户随记（录音期间手写原文，可信度高于转写推断）\n{notes[:2000]}")
        elif "@随记" in mention_tokens:
            context_blocks.append("## 用户显式引用（@随记）\n当前会议暂无用户随记。直接如实告知用户，不要编造随记内容。")
        if "@原文" in mention_tokens and not full_transcript_emitted:
            # 显式引用 @原文（会后或实时流为空回退）：落盘对话全量入场，替代智能采样块；无落盘对话给说明块
            all_lines = _flatten_dialogue_entries(task)
            if all_lines:
                dialogue_text = _truncate_mention_text(
                    "\n".join(line for _, line, _spk, _li in all_lines), MENTION_TRANSCRIPT_CAP, "逐字稿原文")
                context_blocks.append(f"## 用户显式引用（@原文）——全量对话时间轴，优先于采样摘要\n{dialogue_text}")
            else:
                context_blocks.append("## 用户显式引用（@原文）\n当前会议暂无逐字稿原文。直接如实告知用户，不要编造原文内容。")
        elif task.get("dialogue") and not realtime_entries:
            all_lines = _flatten_dialogue_entries(task)
            if all_lines:
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

        decisions = task.get("decisions") or []
        if decisions:
            decision_lines = []
            for t in decisions:
                status = "✅" if t.get("done") else "⬜"
                assignee = t.get("assignee", "未分配")
                decision_lines.append(f"- [{status}] {t.get('text', '')}（责任人：{assignee}）")
            context_blocks.append("## 当前会议决策事项\n" + "\n".join(decision_lines))

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

    # ── 维度 3.5: 提问范围检索 / Scope retrieval ──
    # 唯一检索器：问答注入上下文块，智能体复用同一份块（见 chat_stream_routes）。
    # 范围只决定是否跨会议检索，不接管项目资料等常驻注入。
    scope_block, retrieval = build_scope_context(
        data.scope, user_message, exclude_task_id=data.task_id)
    if scope_block:
        context_blocks.append(scope_block)
    for hit in retrieval.get("meetings") or []:
        source_files.append({
            "title": hit.get("title", ""),
            "path": f"meeting/{hit.get('task_id', '')}",
            "name": hit.get("title", ""),
        })

    # ── 维度 4: 页面上下文 / Page context ──
    if data.current_page:
        page_ctx = build_page_context(data.current_page)
        if page_ctx:
            context_blocks.append(page_ctx)

    return context_blocks, source_files, retrieval
def _chat_model_default() -> str:
    """会话未逐条指定 model 时的默认值：跟随详情 llm.model 设置（REQ-EXPERT-MODE §2.3）。

    「跟随详情」语义下 llm.model 变更即时反映到下一轮；设置缺失才落 qwen-plus。
    """
    try:
        from core.settings_store import get_llm_config
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
        # 回显与实际执行对齐：云端链路会守护性替换本地 tag 模型名（_cloud_safe_model）
        if meta["route"] == "cloud" and ":" in (model or ""):
            from core.llm import CLOUD_FALLBACK_MODEL
            meta["model"] = CLOUD_FALLBACK_MODEL
    except Exception:
        pass
    return meta
def _executor_tag(model: str) -> str:
    """执行方标识尾巴（AI 算力入口治理 §3）：面板外函数类端点失败提示附
    「谁跑的」，与 model_usage 同源但用语言中立的括号标签，免新增译文词条。"""
    src = _model_usage_meta(model).get("source") or ""
    return f"[{model} · {src}]" if src else f"[{model}]"
def _sanitize_chat_title(raw: str) -> str:
    """清洗 LLM 返回的会话标题：取首行、去引号包裹、去结尾标点、硬限长。

    模型不守规矩时（多行/带引号/带句号）兜底，保证标题可直接落 UI。
    """
    if not raw:
        return ""
    stripped = raw.strip()
    if not stripped:
        return ""
    line = stripped.splitlines()[0]
    # 引号包裹与结尾标点可能嵌套（如 "标题"。），循环剥离直至稳定
    prev = None
    while prev != line:
        prev = line
        line = line.strip("\"'「」『』《》“”‘’ ")
        line = line.rstrip("。！？!?.,，、；;：:…—~ ")
    return line[:20]
