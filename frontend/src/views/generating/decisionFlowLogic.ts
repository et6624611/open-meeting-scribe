/**
 * 决策流面板纯逻辑：节点状态归一 + 开放/闭档分组
 *
 * 从 DecisionFlowPanel.vue 抽出，便于单元测试；组件只保留渲染与 DOM 行为。
 */
import type { DecisionItem } from '@/api/types'

/** 节点有效状态 id：显式 status 优先；历史数据由 done 反推，再兜底进行中 */
export function statusOf(decision: DecisionItem): string {
  return decision.status || (decision.done ? 'done' : 'in_progress')
}

/** 按「是否闭档（完成类）」把节点分为开放组与闭档组（保持原数组顺序） */
export function partitionNodes(
  decisions: DecisionItem[],
  isClosingStatus: (id: string | undefined) => boolean,
): { active: DecisionItem[]; completed: DecisionItem[] } {
  const active: DecisionItem[] = []
  const completed: DecisionItem[] = []
  for (const decision of decisions) {
    if (isClosingStatus(statusOf(decision))) completed.push(decision)
    else active.push(decision)
  }
  return { active, completed }
}
