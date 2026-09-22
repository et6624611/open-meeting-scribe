"""
core/insights.py — 洞察台引擎核心 / Insight Deck engine core

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
更新 / Updated: 2026-09-21
版本 / Version: 4.1.0

洞察台定位为绘图面板：以 Mermaid 图 / 结构化知识图谱为主要输出，
文字分析降级为图注。图定位为「思考支架而非结论」，三个观察角度以
「盲点揭示」为首要，其余（上下文关联、共识与待办）作为次要补充，
共同充当「画什么图」的内容选择指引，而非独立的分析类型。

设计理念 / Design philosophy：LLM 的核心优势在于对更大上下文的感知 / LLM's core advantage lies in perceiving larger context.
会议中探讨的共识 / Consensus explored in meetings 应基于更大的上下文环境，而非局限于某人的局部认知 / Should be based on larger context, not limited to someone's local awareness.
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

选择最合适的 Mermaid 图类型来呈现你发现的关系结构：

- **flowchart + subgraph 泳道图**：跨角色/跨部门的职责分工与协作流程（会议场景最实用）
- **flowchart**（graph TD/LR）：决策路径、任务依赖、因果关系（最通用，默认选择）
- **mindmap**：围绕核心主题的多维度发散
- **sequenceDiagram**：多方交互的时间顺序
- **gantt**：行动项的时间安排和并行关系

不确定时默认用 flowchart。节点用中文标签，保持简洁（5-15 个节点），在连线上标注关系类型。
如果讨论内容确实没有可画的关系结构，diagram 设为空字符串，用 body 文字分析代替。

### 辅助文字（body 字段）

用 1-3 句话点出图中最关键的盲区或缺口，并以启发式提问引导用户继续思考——这是图的说明文字，不是独立分析。
避免替用户下结论；用"这里是否缺了……？""这条依赖由谁确认？"这样的追问，帮助用户自己发现问题。

### 结构化知识图谱（graph 字段，可选）

当讨论中存在清晰的节点-边关系网络时，额外输出结构化图谱。
节点携带 begin_time（毫秒），指向讨论该内容的转写行，支持点击跳转。
begin_time 提取规则：查看「最近讨论内容」中对应转写的时间戳，选最相关的那条。无时间戳则设为 0。

## 返回 JSON

{"title": "一句话概括", "body": "图注（1-3 句话）", "solution": "行动建议（可选）", "has_finding": true/false, "diagram": "Mermaid 语法或空字符串", "graph": {"nodes": [{"id": "n1", "label": "概念", "begin_time": 123000}], "edges": [{"from": "n1", "to": "n2", "label": "关系"}]}}

graph 无有效关系网络时设为 null。节点 3-12 个，边 3-15 条。
仅返回 JSON。"""


# ============================================================
# 辅助函数
# ============================================================


def _build_user_message(
    recent_lines: list[dict],
    chapter_titles: list[str],
) -> str:
    """构建用户消息"""
    transcript_text = "\n".join(
        f"[说话人{line.get('speaker_id', 0) + 1}] {line.get('text', '')}"
        for line in recent_lines
    )
    titles_text = "\n".join(f"- {t}" for t in chapter_titles)

    return (
        f"## 会议章节主题\n{titles_text}\n\n"
        f"## 最近讨论内容（{len(recent_lines)} 条）\n{transcript_text}\n\n"
        "请基于以上讨论内容进行综合洞察分析。"
    )


def _parse_analysis_result(reply: str) -> dict:
    """解析 LLM 分析结果 JSON，清理 markdown 代码块标记"""
    cleaned = reply.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    result = json.loads(cleaned)
    # 解析 graph 字段（可选） / Parse graph field (optional)
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
) -> dict:
    """
    执行综合洞察分析。

    参数：
      recent_lines: 最近的转写行 [{text, speaker_id, begin_time}]
      chapter_titles: 章节标题列表
      role_name: 当前角色名（可选），优先使用角色专属 prompt；
                 无角色或角色未定义 insight prompt 时回退到内置默认。

    返回：
      {"title": str, "body": str, "solution": str, "has_finding": bool, "diagram": str, "graph": dict|None}
      失败时返回 has_finding=False
    """
    if not recent_lines or not chapter_titles:
        return {"title": "", "body": "", "solution": "", "has_finding": False, "diagram": "", "graph": None}

    # 角色感知：优先使用角色专属 prompt，回退到内置默认 / Role-aware: prefer role-specific prompt, fallback to built-in default
    system_prompt = None
    if role_name:
        from core.agent_workspace import get_role_insight_prompt
        system_prompt = get_role_insight_prompt(role_name)
        if system_prompt:
            logger.info("[洞察台] 使用角色 %s 的洞察 prompt", role_name)
    if not system_prompt:
        system_prompt = INSIGHT_ANALYSIS_PROMPT

    user_message = _build_user_message(recent_lines, chapter_titles)

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
        return {"title": "", "body": "", "solution": "", "has_finding": False, "diagram": "", "graph": None}
    except Exception as e:
        logger.warning("[洞察台] 分析失败: %s", e)
        return {"title": "", "body": "", "solution": "", "has_finding": False, "diagram": "", "graph": None}
