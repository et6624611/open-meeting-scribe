"""
core/insights.py — AI 洞察引擎核心 / AI insights engine core

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-12
更新 / Updated: 2026-09-12
版本 / Version: 2.0.0

提供三类洞察分析 / Three types of insight analysis:
  - 上下文关联 / Context (context)：引入讨论之外的相关背景，帮助参会者看到更大图景 / Bring in relevant context beyond discussion, help participants see the bigger picture
  - 盲点揭示 / Blindspot (blindspot)：指出参与者局部认知之外的因素 / Point out factors beyond participants' local awareness
  - 共识提炼 / Consensus (consensus)：从散乱讨论中萃取真正的共识点与分歧根源 / Extract true consensus points and root of disagreements from scattered discussion

设计理念 / Design philosophy：LLM 的核心优势在于对更大上下文的感知 / LLM's core advantage lies in perceiving larger context. 会议中探讨的共识 / Consensus explored in meetings
应基于更大的上下文环境，而非局限于某人的局部认知 / Should be based on larger context, not limited to someone's local awareness.
"""

import json
import logging

from core.llm import async_chat_completion

logger = logging.getLogger(__name__)

# ============================================================
# 分析类型系统提示词
# ============================================================

CONTEXT_ANALYSIS_PROMPT = """你是一位资深会议顾问。你的任务是分析当前讨论，引入参会者可能未意识到的相关上下文，帮助他们基于更完整的信息达成共识。

你可以引入的上下文类型：
- 相关的历史决策或先例
- 行业趋势或市场动态
- 跨部门/跨项目的关联影响
- 利益相关者的视角
- 技术或业务的约束条件

分析要求：
1. 基于当前讨论内容，识别可以扩展认知的上下文信息
2. 确保引入的上下文对当前决策有实际价值
3. 避免泛泛而谈，要具体且可操作

返回 JSON 格式（不要包含 markdown 代码块标记）：
{"title": "简要标题", "body": "上下文分析内容", "solution": "基于上下文的建议", "has_finding": true}

如果没有有价值的上下文可补充（讨论已足够全面），返回：
{"title": "", "body": "", "solution": "", "has_finding": false}

仅返回 JSON，不要其他内容。"""

BLINDSPOT_ANALYSIS_PROMPT = """你是一位资深会议顾问。你的任务是识别当前讨论中参与者可能忽略的盲点，揭示局部认知之外的关键因素。

你应关注的盲点类型：
- 被忽视的利益相关者或受影响方
- 未考虑的外部约束或依赖
- 隐含的假设（未经验证的前提）
- 短期决策的长期影响
- 缺失的关键数据或证据
- 未被讨论的风险或机会

分析要求：
1. 仔细审视讨论内容，找出被遗漏但重要的因素
2. 只指出真正重要的盲点，不要为了显示而硬找
3. 解释为什么这个盲点重要，以及不处理的潜在后果

返回 JSON 格式（不要包含 markdown 代码块标记）：
{"title": "简要标题", "body": "盲点分析内容", "solution": "建议的应对措施", "has_finding": true}

如果没有发现重要盲点（讨论已充分覆盖关键因素），返回：
{"title": "", "body": "", "solution": "", "has_finding": false}

仅返回 JSON，不要其他内容。"""

CONSENSUS_ANALYSIS_PROMPT = """你是一位资深会议引导师。你的任务是从讨论中提炼真正的共识点，识别分歧的根源，帮助团队达成有意义的共识。

你的分析维度：
- 各方已达成的一致（显性和隐性共识）
- 分歧的核心根源（不是表面分歧，而是底层原因）
- 共识的基础和前提条件
- 推进共识所需的下一步

分析要求：
1. 识别讨论中真正的共识点，而非表面的附和
2. 定位分歧的根源——是信息不对称、价值观差异、还是利益冲突？
3. 提供推进共识的可操作建议

返回 JSON 格式（不要包含 markdown 代码块标记）：
{"title": "简要标题", "body": "共识与分歧分析", "solution": "推进共识的建议", "has_finding": true}

如果讨论尚未形成明确的共识或分歧（讨论太浅或太分散），返回：
{"title": "", "body": "", "solution": "", "has_finding": false}

仅返回 JSON，不要其他内容。"""


# ============================================================
# 分析类型注册
# ============================================================

ANALYSIS_PROMPTS = {
    "context": CONTEXT_ANALYSIS_PROMPT,
    "blindspot": BLINDSPOT_ANALYSIS_PROMPT,
    "consensus": CONSENSUS_ANALYSIS_PROMPT,
}


# ============================================================
# 辅助函数
# ============================================================


def _build_user_message(
    recent_lines: list[dict],
    chapter_titles: list[str],
) -> str:
    """构建用户消息（所有分析类型共用）"""
    transcript_text = "\n".join(
        f"[说话人{line.get('speaker_id', 0) + 1}] {line.get('text', '')}"
        for line in recent_lines
    )
    titles_text = "\n".join(f"- {t}" for t in chapter_titles)

    return (
        f"## 会议章节主题\n{titles_text}\n\n"
        f"## 最近讨论内容（{len(recent_lines)} 条）\n{transcript_text}\n\n"
        "请基于以上讨论内容进行分析。"
    )


def _parse_analysis_result(reply: str) -> dict:
    """解析 LLM 分析结果 JSON，清理 markdown 代码块标记"""
    cleaned = reply.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    result = json.loads(cleaned)
    return {
        "title": str(result.get("title", "")),
        "body": str(result.get("body", "")),
        "solution": str(result.get("solution", "")),
        "has_finding": bool(result.get("has_finding", False)),
    }


# ============================================================
# 统一分析入口
# ============================================================


async def run_analysis(
    recent_lines: list[dict],
    chapter_titles: list[str],
    analysis_type: str = "context",
) -> dict:
    """
    执行指定类型的洞察分析。

    参数：
      recent_lines: 最近的转写行 [{text, speaker_id, begin_time}]
      chapter_titles: 章节标题列表
      analysis_type: 分析类型 ('context' | 'blindspot' | 'consensus')

    返回：
      {"title": str, "body": str, "solution": str, "has_finding": bool}
      失败时返回 has_finding=False
    """
    if analysis_type not in ANALYSIS_PROMPTS:
        logger.warning("[AI洞察] 未知分析类型: %s", analysis_type)
        return {"title": "", "body": "", "solution": "", "has_finding": False}

    if not recent_lines or not chapter_titles:
        return {"title": "", "body": "", "solution": "", "has_finding": False}

    system_prompt = ANALYSIS_PROMPTS[analysis_type]
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
            max_tokens=500,
        )
        parsed = _parse_analysis_result(reply)

        logger.info(
            "[AI洞察] %s 分析完成: has_finding=%s title=%s",
            analysis_type, parsed["has_finding"], parsed["title"][:60],
        )
        return parsed

    except json.JSONDecodeError:
        logger.warning("[AI洞察] %s 分析返回非 JSON: %s", analysis_type, reply[:200])
        return {"title": "", "body": "", "solution": "", "has_finding": False}
    except Exception as e:
        logger.warning("[AI洞察] %s 分析失败: %s", analysis_type, e)
        return {"title": "", "body": "", "solution": "", "has_finding": False}
