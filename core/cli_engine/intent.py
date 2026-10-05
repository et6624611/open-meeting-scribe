"""
core/cli_engine/intent.py — 智能体模式意图分流器 v1（规则版）
Rule-based intent classifier deciding built-in QA vs local CLI agent engine (auto mode).

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

【已退役】auto 规则分流已随「AI 算力入口治理」方案下线（会话模式收敛为问答/智能体两态，
用户选择即意图，不再替用户路由）；本模块保留供后续策略复用（如建议式路由/预检）。

对应方案 / See: Qoder CLI 引擎方案 §3.5（意图分流）+ D4（误判代价不对称）。

决策原则（D4 倾向）：轻请求误入 CLI 只是慢（可忍），重请求误入直连是答非所问（不可忍）；
故对"工程化信号"敏感、对"留内置"保守——命中任一工程化信号即建议智能体。

信号来源复用 chat.py 既有成熟范式（关键词/意图），不引入额外模型调用。
"""

from __future__ import annotations

# 工程化/文件产出/多步执行类信号 → 倾向智能体
_AGENT_SIGNALS = [
    # 文件与文档产出
    "生成文档", "正式报告", "按模板", "按…模板", "按公司", "写成报告", "导出",
    "保存到", "存到", "落成文件", "文件形式", "markdown 文件", "word", "docx", "excel", "表格",
    # 多步/跨会议/聚合分析
    "对比这", "比较这", "这几次会议", "跨会议", "多次会议", "行动项完成情况",
    "跟踪表", "汇总并", "整理成", "梳理成", "统计所有", "按类别整理",
    # 写回类（需要工具落库）
    "更新纪要", "重写纪要", "改写纪要", "追加决策", "补充待办", "修改纪要",
    "把纪要", "重新生成纪要并", "同步到项目", "写入项目",
    # 代码/执行
    "写个脚本", "跑一下", "运行命令", "执行命令", "写代码", "改代码", "重构",
]

# 明确轻问答信号 → 倾向内置（仅在无工程化信号时生效）
_QA_SIGNALS = [
    "谁说了", "谁提到", "什么时候", "多少钱", "多少个", "几条", "是否提到",
    "总结一下这段", "这段的要点", "这句话什么意思", "解释一下",
]


def classify_engine_intent(message: str) -> str:
    """
    返回 "agent" 或 "qa"。空/异常一律回退 "qa"（默认轻量路径最安全）。

    规则：命中任一工程化信号 → agent；否则 → qa。
    QA 信号不参与"抢占"，仅在调试/日志中体现倾向，保持对 agent 的宽容命中。
    """
    try:
        text = (message or "").lower()
    except Exception:  # noqa: BLE001
        return "qa"
    if not text.strip():
        return "qa"
    for kw in _AGENT_SIGNALS:
        if kw in text:
            return "agent"
    return "qa"
