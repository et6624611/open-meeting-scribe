/**
 * 一页纸系数 — 前端共享常量与换算 / One-page factor — shared frontend constants & conversion
 *
 * 系数从属于单个会议（task.one_page.summary / task.one_page.insights），
 * 纪要与洞察各自一页、互不相加；与后端 core/insight_budget.py 换算表保持一致。
 */

/** 合法档位（与后端 PAGE_BUDGET_FACTORS 对齐） */
export const PAGE_FACTORS = [0.5, 1, 1.5, 2] as const

/** 系数 → 洞察有效卡位（与后端 _CARD_SLOT_TABLE 对齐：1 页 = 2 张，图卡 ≤1） */
const CARD_SLOT_TABLE: Record<number, number> = { 0.5: 1, 1: 2, 1.5: 3, 2: 4 }

/** 任意值归一到合法档位；缺失/非法按 1 兜底（旧任务兼容口径） */
export function normalizeFactor(value: number | null | undefined): number {
  return (PAGE_FACTORS as readonly number[]).includes(value ?? NaN) ? (value as number) : 1
}

/** 系数换算洞察有效卡位 */
export function cardSlots(factor: number | null | undefined): number {
  return CARD_SLOT_TABLE[normalizeFactor(factor)]
}
