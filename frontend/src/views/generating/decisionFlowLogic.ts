/**
 * 决策流面板纯逻辑：节点状态归一 + 开放/闭档分组
 *
 * 从 DecisionFlowPanel.vue 抽出，便于单元测试；组件只保留渲染与 DOM 行为。
 */
import type { TodoItem } from '@/api/types'

/** 节点有效状态 id：显式 status 优先；历史数据由 done 反推，再兜底进行中 */
export function statusOf(todo: TodoItem): string {
  return todo.status || (todo.done ? 'done' : 'in_progress')
}

/** 按「是否闭档（完成类）」把节点分为开放组与闭档组（保持原数组顺序） */
export function partitionNodes(
  todos: TodoItem[],
  isClosingStatus: (id: string | undefined) => boolean,
): { active: TodoItem[]; completed: TodoItem[] } {
  const active: TodoItem[] = []
  const completed: TodoItem[] = []
  for (const todo of todos) {
    if (isClosingStatus(statusOf(todo))) completed.push(todo)
    else active.push(todo)
  }
  return { active, completed }
}
