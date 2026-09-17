"""
core/insights.py — 洞察台引擎核心 / Insight Deck engine core

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
更新 / Updated: 2026-09-17
版本 / Version: 3.1.0

综合洞察分析：一次分析覆盖上下文关联、盲点揭示、共识提炼三个维度。 / Unified insight analysis: single analysis covering context, blindspot, and consensus dimensions.

设计理念 / Design philosophy：LLM 的核心优势在于对更大上下文的感知 / LLM's core advantage lies in perceiving larger context. 会议中探讨的共识 / Consensus explored in meetings
应基于更大的上下文环境，而非局限于某人的局部认知 / Should be based on larger context, not limited to someone's local awareness.
"""

import json
import logging

from core.llm import async_chat_completion

logger = logging.getLogger(__name__)

# ============================================================
# 统一洞察分析提示词（覆盖上下文、盲点、共识三维度）
# ============================================================

INSIGHT_ANALYSIS_PROMPT = """你是一位资深会议顾问。你的独特价值是：参会者沉浸在讨论细节中，而你能站在更高处看到他们看不到的关系网络。

请用图形思维来分析这场讨论——像画一张思维导图那样去理解：谁和谁有关联？哪些决策互相依赖？哪里有关键的缺失环节？

## 三个观察角度

### 上下文关联
这场讨论放在更大的组织背景中，会暴露出什么关联？
（历史先例、跨部门影响、未到场但受影响的利益相关者、外部约束）

### 盲点揭示
讨论中系统性缺失了什么？不是评判谁没想到，而是指出"这张关系图里缺了哪块"。
（未提及的关键依赖、被当作事实的隐含假设、决策链的断裂处、风险传导路径）

### 共识与待办
从讨论的混沌中提炼结构：谁该做什么？行动项之间有什么依赖关系？分歧的根源是什么？

## 输出方式

当你发现值得可视化的关系结构时，请选择最合适的 Mermaid 图类型来呈现。根据内容特征自动选型：

- **flowchart + subgraph 泳道图**：适合展示跨角色/跨部门的职责分工与协作流程。用 subgraph 划分不同角色或部门，节点为各自的任务，连线展示协作关系。这是会议场景中最实用的图类型。
- **flowchart**（graph TD/LR）：适合展示决策路径、任务依赖、因果关系。最通用的选择。
- **mindmap**：适合展示围绕一个核心主题的多维度发散（如影响因素、利益相关者地图）。
- **sequenceDiagram**：适合展示多方之间的交互时序（如审批流转、信息传递链）。
- **gantt**：适合展示行动项的时间安排和并行关系。

选型原则：如果讨论涉及不同人/部门各自的任务和协作关系，用泳道图（flowchart + subgraph）；如果涉及明确的先后步骤或依赖关系，用 flowchart；如果是围绕核心概念的多方向发散，用 mindmap；如果强调多方交互的时间顺序，用 sequenceDiagram；如果涉及时间安排，用 gantt。不确定时默认用 flowchart。

如果没有明显的关系结构可画，纯文字分析也可以——不要为了画图而画图。

## 结构化知识图谱（graph 字段）

当你发现讨论中存在清晰的概念/决策/行动项之间的关系网络时，额外输出一个结构化的知识图谱。
图谱节点应携带 begin_time（毫秒），指向讨论该节点的转写行，使用户可以点击节点跳转到原文对应位置。

节点 begin_time 提取规则：查看下方「最近讨论内容」中每条转写的 [说话人N] 行前面的时间戳（如果有的话），选择与该节点内容最相关的那条转写的时间戳。如果没有时间戳信息，begin_time 设为 0。

返回 JSON：
{"title": "一句话概括这个洞察", "body": "你的分析（Markdown 格式，自由组织）", "solution": "建议（如果有）", "has_finding": true/false, "diagram": "Mermaid 语法或空字符串", "graph": {"nodes": [{"id": "n1", "label": "概念名", "begin_time": 123000}], "edges": [{"from": "n1", "to": "n2", "label": "关系"}]}}

graph 字段：如果没有明显的关系网络可提取，设为 null。节点数控制在 3-12 个，边数控制在 3-15 条。

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
