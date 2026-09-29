"""
core/insights.py — 洞察台引擎核心 / Insight Deck engine core

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
更新 / Updated: 2026-09-28
版本 / Version: 5.2.0

洞察台定位为绘图面板：以受约束 Mermaid（workflow 阶段卡画布）为主要输出，
文字分析降级为图注。图定位为「思考支架而非结论」，三个观察角度以
「盲点揭示」为首要，其余（上下文关联、共识与待办）作为次要补充，
共同充当「画什么图」的内容选择指引，而非独立的分析类型。

设计理念 / Design philosophy：LLM 的核心优势在于对更大上下文的感知 / LLM's core advantage lies in perceiving larger context.
会议中探讨的共识 / Consensus explored in meetings 应基于更大的上下文环境，而非局限于某人的局部认知 / Should be based on larger context, not limited to someone's local awareness.

只读累进（Phase 1）：分析请求可携带当前洞察卡片集的 title/body 结构化摘要（已有洞察），
使模型在局部窗口之外获得全局视角，并约束「同主题优先增量、避免重复创建」；
仅影响提示词输入，不改动写入模型与持久化契约。
"""

import json
import logging

from core.llm import async_chat_completion

logger = logging.getLogger(__name__)

# ============================================================
# 统一洞察分析提示词（图优先输出）
# ============================================================

INSIGHT_ANALYSIS_PROMPT = """你是一位资深会议顾问。你的独特价值是：参会者沉浸在讨论细节中，而你能站在更高处看到他们看不到的关系网络。

## 你的核心能力：可视化绘图

你具备使用 Mermaid 语法绘制各类结构化图表的能力，包括但不限于：功能框架图、系统架构图、流程图、思维导图、时序图、甘特图等。
当用户请求绘制任何类型的图表时，你必须使用 Mermaid 语法输出 diagram 字段，而不是回复"我无法绘图"或"我无法输出图像"。
你的 diagram 字段会被前端自动渲染为可视化图形，所以请放心使用 Mermaid 语法。

请用图形思维来分析这场讨论——你的主要输出是一张图，用视觉化的方式呈现讨论中的关系结构。

## 定位：图是思考支架，不是结论

你产出的图不是给用户一个封闭的答案，而是给他们一个继续思考的脚手架。因此：
- 优先画出"缺失的那块"，而不是把已知内容画满；
- 允许留白：用虚线连线（-.->）、带问号的节点标签（如"负责人？""数据源？"）表达待确认之处；
- 图注（body）用启发式提问，引导用户自己发现盲区，而非替他下结论。

## 观察角度（盲点揭示优先，作为图的内容选择指引）

### 盲点揭示（首要）
讨论中系统性缺失了什么？指出"这张关系图里缺了哪块"。
（未提及的关键依赖、被当作事实的隐含假设、决策链的断裂处、风险传导路径、未分配负责人的待办）

### 上下文关联（次要补充）
这场讨论放在更大的组织背景中，会暴露出什么关联？
（历史先例、跨部门影响、未到场但受影响的利益相关者、外部约束）

### 共识与待办（次要补充）
从讨论的混沌中提炼结构：谁该做什么？行动项之间有什么依赖关系？

优先可视化盲点；仅当盲点确实不明显时，才退而画上下文关联或共识结构。

## 输出要求

### 主输出：Mermaid 图（diagram 字段）

图会被前端解析为「洞察台画布」上的 workflow 阶段卡（从左到右排布，阶段卡内堆叠步骤芯片）。

#### 洞察台画布书写规范（优先遵守）

示例：

flowchart LR
  subgraph S1["数据核对"]
    S1a["拉取费控数据 @@84000"]
    S1b["确认统计口径 @@461000"]
  end
  subgraph S2["差异讨论"]
    S2a["差旅超支归因 @@903000"]
  end
  S1a --- S2a

硬性约束（前端解析器依赖，违反任意一条都会导致降级为普通 Mermaid 渲染）：
- 方向固定 flowchart LR；
- 所有 subgraph 标题与节点标签必须用双引号包裹（如 ["数据核对"]）；
- 每个 subgraph = 一个阶段，ID 形如 S<序号>（S1、S2…），标题为不超过 6 字的阶段名；
- 阶段编号（“阶段 01”）由前端按序号自动生成，不要写进标题；
- 节点 ID 形如 S<序号><字母>（S1a、S1b…），标签不超过 14 字；
- 节点标签尾部用「 @@<毫秒数>」携带转写定位时间（取该步骤对应转写行的 begin_time；无对应时间戳则省略整个标记）；
- 阶段之间用 ---（无箭头）连接不同 subgraph 内的节点；禁止使用 -->；
- 阶段 2-5 个，每阶段节点 1-4 个，总节点不超过 12；
- 阶段描述：在 body（图注）中按「阶段名：一句话」逐段给出（「阶段名」必须替换为实际阶段标题，不要保留字面占位符），前端按阶段名匹配填入卡片描述。

#### 内容视角

优先用上述阶段卡格式呈现讨论的流程结构（盲点、缺口用带问号的标签或待确认节点表达）。
若讨论内容确实不适合阶段卡结构（如发散头脑风暴、纯时间线事件），可退而使用其他 Mermaid 图类型
（flowchart TD、mindmap、sequenceDiagram、gantt 等），前端会以通用 Mermaid 渲染兜底：
- **flowchart + subgraph 泳道图**：跨角色/跨部门的职责分工与协作流程（会议场景最实用）
- **mindmap**：围绕核心主题的多维度发散
- **sequenceDiagram**：多方交互的时间顺序
- **gantt**：行动项的时间安排和并行关系

通用要求：节点用中文标签，保持简洁（5-15 个节点）。如果讨论内容确实没有可画的关系结构，diagram 设为空字符串，用 body 文字分析代替。

### 辅助文字（body 字段）

用 1-3 句话点出图中最关键的盲区或缺口，并以启发式提问引导用户继续思考——这是图的说明文字，不是独立分析。
采用画布格式时，另按「阶段名：一句话」逐段给出阶段描述（可与提问式图注合并）。
避免替用户下结论；用"这里是否缺了……？""这条依赖由谁确认？"这样的追问，帮助用户自己发现问题。

### 备查注释（note 字段）

用≤60字承载备查明细，让读者「退可忽略、进可查看」。严格的内容资格：仅以下三类素材可入注——
① 依据出处（谁在什么时间说的，如「说话人2 07:34」）；② 构成明细（数量、覆盖范围、清单）；③ 例外与存疑（`[待确认]` 异写变体、未敲定点、适用边界）。
工程性元数据（置信度、内部字段名）与 body 重复的转述无资格入注；没有合格素材时 note 设为空字符串，不得为注而注。

## 返回 JSON

{"title": "一句话概括", "body": "图注（1-3 句话，画布格式时附「阶段名：一句话」描述）", "solution": "行动建议（可选）", "note": "备查明细（≤60字，可选）", "has_finding": true/false, "diagram": "Mermaid 语法或空字符串"}

仅返回 JSON。"""


# ============================================================
# 辅助函数
# ============================================================


def _fmt_ms(ms: int) -> str:
    """毫秒转 mm:ss 展示格式 / Format milliseconds as mm:ss display."""
    total_sec = int(ms) // 1000
    return f"{total_sec // 60:02d}:{total_sec % 60:02d}"


# 已有洞察摘要注入预算（字符）：防上下文膨胀挤占转写块
# Character budget for the existing-insights block, to not crowd out the transcript
EXISTING_INSIGHTS_MAX_ITEMS = 8
EXISTING_INSIGHTS_BODY_CHARS = 120
EXISTING_INSIGHTS_NOTE_CHARS = 40
EXISTING_INSIGHTS_MAX_CHARS = 2000
# 洞察卡备查注释层长度上限（与提示词契约一致） / Max length of the insight note layer
INSIGHT_NOTE_MAX_CHARS = 60


def _format_existing_insights(existing: list[dict] | None) -> str:
    """将已有洞察卡片集渲染为「已产出的洞察卡片」上下文块；无有效内容返回空串。
    Render existing insight cards as a context block; empty string when none."""
    if not existing:
        return ""
    lines: list[str] = []
    used = 0
    for m in existing[-EXISTING_INSIGHTS_MAX_ITEMS:]:
        title = str(m.get("title") or "").strip()
        if not title:
            continue
        body = str(m.get("body") or "").strip()[:EXISTING_INSIGHTS_BODY_CHARS]
        entry = f"- {title}" + (f"：{body}" if body else "")
        # 备查注释随卡携带（计入总额，单独截 40） / carry the note layer under the global cap
        note = str(m.get("note") or "").strip()[:EXISTING_INSIGHTS_NOTE_CHARS]
        if note:
            entry += f"（注：{note}）"
        if used + len(entry) + 1 > EXISTING_INSIGHTS_MAX_CHARS:
            break
        lines.append(entry)
        used += len(entry) + 1
    if not lines:
        return ""
    return (
        "## 已产出的洞察卡片（本轮分析的全局上下文，勿重复）\n"
        + "\n".join(lines)
        + "\n\n注意：若本轮讨论与上述卡片同主题，请勿再创建重复卡片（has_finding 设为 false），"
        "除非能补充明确的增量新发现；若确属新主题，可在图注中点出与既有卡片的关联。"
    )


def _build_user_message(
    recent_lines: list[dict],
    chapter_titles: list[str],
    existing_insights: list[dict] | None = None,
) -> str:
    """构建用户消息（可选携带已有洞察摘要，实现只读累进视角）"""
    transcript_text = "\n".join(
        f"[说话人{line.get('speaker_id', 0) + 1}] ({_fmt_ms(line.get('begin_time', 0))}) {line.get('text', '')}"
        for line in recent_lines
    )
    titles_text = "\n".join(f"- {t}" for t in chapter_titles)

    parts = [
        f"## 会议章节主题\n{titles_text}",
        f"## 最近讨论内容（{len(recent_lines)} 条）\n{transcript_text}",
    ]
    insights_block = _format_existing_insights(existing_insights)
    if insights_block:
        parts.insert(1, insights_block)
    parts.append("请基于以上讨论内容进行综合洞察分析。")
    return "\n\n".join(parts)


def _parse_analysis_result(reply: str) -> dict:
    """解析 LLM 分析结果 JSON，清理 markdown 代码块标记"""
    cleaned = reply.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    result = json.loads(cleaned)
    # graph 字段透传（兼容历史数据） / Pass through legacy graph field (historical data compatibility)
    # 新提示词已不再要求输出 graph；仅旧会话重载时可能携带，前端据此渲染旧版图谱。
    # New prompt no longer requests graph; only legacy session reloads may carry it, rendered by the legacy graph view.
    raw_graph = result.get("graph")
    graph = None
    if isinstance(raw_graph, dict):
        nodes = raw_graph.get("nodes", [])
        edges = raw_graph.get("edges", [])
        if nodes:  # 至少有节点才视为有效 / At least nodes required to be valid
            graph = {
                "nodes": [
                    {
                        "id": str(n.get("id", "")),
                        "label": str(n.get("label", n.get("id", ""))),
                        "begin_time": int(n.get("begin_time", 0)),
                    }
                    for n in nodes if n.get("id")
                ],
                "edges": [
                    {
                        "from": str(e.get("from", "")),
                        "to": str(e.get("to", "")),
                        "label": str(e.get("label", "")),
                    }
                    for e in edges if e.get("from") and e.get("to")
                ],
            }
    return {
        "title": str(result.get("title", "")),
        "body": str(result.get("body", "")),
        "solution": str(result.get("solution", "")),
        # 备查注释层：旧契约无此字段，缺省降级空串 / note layer: absent in legacy contracts, defaults to ""
        "note": str(result.get("note") or "").strip()[:INSIGHT_NOTE_MAX_CHARS],
        "has_finding": bool(result.get("has_finding", False)),
        "diagram": str(result.get("diagram", "")),
        "graph": graph,
    }


# ============================================================
# 统一分析入口
# ============================================================


async def run_analysis(
    recent_lines: list[dict],
    chapter_titles: list[str],
    role_name: str | None = None,
    existing_insights: list[dict] | None = None,
    card_budget: dict | None = None,
) -> dict:
    """
    执行综合洞察分析。

    参数：
      recent_lines: 最近的转写行 [{text, speaker_id, begin_time}]
      chapter_titles: 章节标题列表
      role_name: 当前角色名（可选），优先使用角色专属 prompt；
                 无角色或角色未定义 insight prompt 时回退到内置默认。
      existing_insights: 已有洞察卡片 [{title, body}]（可选），只读累进上下文；
                 注入 user message，不受角色 system prompt 覆盖影响。
      card_budget: 一页纸卡位预算 {"slots": int, "active": int}（可选）；
                 非空时在 system prompt 追加卡位约束块（含角色覆盖路径）。

    返回：
      {"title": str, "body": str, "solution": str, "note": str, "has_finding": bool, "diagram": str, "graph": dict|None}
      失败时返回 has_finding=False
    """
    if not recent_lines or not chapter_titles:
        return {"title": "", "body": "", "solution": "", "note": "", "has_finding": False, "diagram": "", "graph": None}

    # 角色感知：优先使用角色专属 prompt，回退到内置默认 / Role-aware: prefer role-specific prompt, fallback to built-in default
    system_prompt = None
    if role_name:
        from core.agent_workspace import get_role_insight_prompt
        system_prompt = get_role_insight_prompt(role_name)
        if system_prompt:
            logger.info("[洞察台] 使用角色 %s 的洞察 prompt", role_name)
    if not system_prompt:
        system_prompt = INSIGHT_ANALYSIS_PROMPT

    # R4（WP-A）：小模型保守档追加防幻觉约束；standard 档为空串，行为零变化
    from core.model_tier import get_tier_prompt_guard
    system_prompt += get_tier_prompt_guard()

    # 一页纸系数卡位预算：与存储侧 apply_budget 同口径，角色覆盖路径同点位生效
    if card_budget:
        from core.insight_budget import budget_block
        system_prompt += budget_block(
            int(card_budget.get("slots", 0)), int(card_budget.get("active", 0)))

    user_message = _build_user_message(recent_lines, chapter_titles, existing_insights)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    try:
        reply = await async_chat_completion(
            messages,
            model=None,
            temperature=0.3,
            max_tokens=1500,
        )
        parsed = _parse_analysis_result(reply)

        logger.info(
            "[洞察台] 分析完成: has_finding=%s title=%s",
            parsed["has_finding"], parsed["title"][:60],
        )
        return parsed

    except json.JSONDecodeError:
        logger.warning("[洞察台] 分析返回非 JSON: %s", reply[:200])
        return {"title": "", "body": "", "solution": "", "note": "", "has_finding": False, "diagram": "", "graph": None}
    except Exception as e:
        logger.warning("[洞察台] 分析失败: %s", e)
        return {"title": "", "body": "", "solution": "", "note": "", "has_finding": False, "diagram": "", "graph": None}
