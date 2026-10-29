/**
 * 决策流面板纯逻辑：节点状态归一
 *
 * 从 DecisionFlowPanel.vue 抽出，便于单元测试；组件只保留渲染与 DOM 行为。
 * 原「开放/闭档分组」的 partitionNodes 已随面板分组功能下线（决策流按产生顺序平铺）。
 */
import type { DecisionItem } from '@/api/types'

/** 节点有效状态 id：显式 status 优先；历史数据由 done 反推，再兜底进行中 */
export function statusOf(decision: DecisionItem): string {
  return decision.status || (decision.done ? 'done' : 'in_progress')
}
