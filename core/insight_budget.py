"""
core/insight_budget.py — 洞察台一页纸系数预算（卡位口径）

作者：Yongliang Wang
创建：2026-09-29
版本：1.0.0

职责：
1. 系数 → 有效卡位/图卡位换算（0.5→1 张、1→2 张、1.5→3 张、2→4 张；图卡 ≤ ceil(卡位/2)）
2. 对洞察消息列表执行预算重排：超预算旧卡打 deferred=true 降级，不删除
3. 已确认（acknowledged）的卡永不降级——人是最终作者；确认卡本身超容时有效层超容也不强降，仅记 warning

纯函数、无 IO；写盘由调用方（app/routers/insights.py、tasks.py PATCH）完成。
契约登记见 docs/API_CONTRACTS.md one_page / deferred 条目。
"""

import logging
import math

logger = logging.getLogger(__name__)

# 合法档位与纪要侧口径一致（core.summarize.PAGE_BUDGET_FACTORS）
PAGE_BUDGET_FACTORS = (0.5, 1.0, 1.5, 2.0)

# 系数 → 有效卡位换算表（设计对话定稿：1 页 = 2 张有效卡，图卡 ≤1）
_CARD_SLOT_TABLE = {0.5: 1, 1.0: 2, 1.5: 3, 2.0: 4}


def normalize_factor(value) -> float:
    """任意输入归一到合法档位；非法/缺失一律按 1.0 兜底（旧任务兼容口径）。"""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 1.0
    return f if f in PAGE_BUDGET_FACTORS else 1.0


def card_slots(factor) -> int:
    """系数换算有效卡位。"""
    return _CARD_SLOT_TABLE[normalize_factor(factor)]


def diagram_slots_for(slots: int) -> int:
    """有效卡位换算图卡上限：ceil(卡位/2)。2 张时图 ≤1、4 张时图 ≤2。"""
    return math.ceil(slots / 2)


def active_count(messages: list[dict]) -> int:
    """当前未降级（deferred 非 true）的有效卡数。"""
    return sum(1 for m in messages if not m.get("deferred"))


def _is_substantive(m: dict) -> bool:
    """实质洞察卡判定：有图/有建议/用户手动触发均算；
    无正文实质的系统占位卡（如手动检查后的正面反馈卡）优先级低于实质卡，
    避免占位卡挤占卡位把真实洞察踢入历史层。"""
    return bool(m.get("diagram") or m.get("solution") or m.get("source") == "user")


def apply_budget(messages: list[dict], factor) -> list[dict]:
    """按系数对消息列表重排可见层，返回新列表（每条消息浅拷贝，不改入参）。

    选卡规则：
    - acknowledged=true 的卡恒定留在有效层（永不降级，且优先占用卡位）；
    - 其余卡按「实质卡从新到旧 → 占位卡从新到旧」回填剩余卡位，图卡另受 diagram_slots 约束；
    - 未入选的卡打 deferred=true，入选的显式写 deferred=false（契约清洁）。
    """
    f = normalize_factor(factor)
    slots = card_slots(f)
    diagram_cap = diagram_slots_for(slots)

    protected = [m for m in messages if m.get("acknowledged")]
    if len(protected) > slots:
        # 确认卡超容：不强降（人是最终作者），仅观测
        logger.warning("[洞察预算] 已确认卡 %d 张超出卡位 %d（系数 %s），有效层超容不强降",
                       len(protected), slots, f)

    used = len(protected)
    used_diagrams = sum(1 for m in protected if m.get("diagram"))
    keep_ids: set = set()
    for m in protected:
        keep_ids.add(id(m))

    # 非确认卡回填剩余卡位：实质卡优先，占位反馈卡不挤占真实洞察
    others = [m for m in messages if not m.get("acknowledged")]
    candidates = ([m for m in reversed(others) if _is_substantive(m)]
                  + [m for m in reversed(others) if not _is_substantive(m)])
    for m in candidates:
        is_diagram = bool(m.get("diagram"))
        if used >= slots:
            break
        if is_diagram and used_diagrams >= diagram_cap:
            continue
        keep_ids.add(id(m))
        used += 1
        if is_diagram:
            used_diagrams += 1

    result = []
    for m in messages:
        item = dict(m)
        item["deferred"] = id(m) not in keep_ids
        result.append(item)
    return result


def budget_block(slots: int, active: int) -> str:
    """构造注入洞察 system prompt 的卡位预算短块（生成侧约束，与存储侧 apply_budget 同口径）。"""
    diagram_cap = diagram_slots_for(slots)
    full_line = "卡位已满：除非出现关键新发现，请输出 has_finding=false。" if active >= slots else ""
    return (
        "\n\n## 卡位预算（一页纸系数）\n"
        f"本场有效卡位共 {slots} 张（其中图卡不超过 {diagram_cap} 张），当前已使用 {active} 张。\n"
        "本轮至多新增 1 张卡片；若与既有卡片同主题，优先避免同义新开卡（输出 has_finding=false）。\n"
        + full_line
    )
