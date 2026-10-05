/**
 * useTaskWrites.ts — AI 写回任务的变更信号 / Task-domain write-back signal
 *
 * 背景（PROPOSAL-AGENT-REWRITE-CHANNEL §5.4）：决策节点/纪要/随记的会话写入点在后端
 * （集成工具直接落盘），而会后详情页不在实时转写 WebSocket 通道上，过去只能靠切 Tab
 * 才重拉，用户看着 AI 说"已更新"却对着旧数据。本模块沿用 board-written 的 CustomEvent
 * 先例，提供两件事：
 *   1. 识别「一次成功的任务写回工具调用」（内置引擎裸名 / CLI 引擎 mcp__<server>__<tool> 全名）；
 *   2. 跨组件通道 task-written（AI 面板发信号 → 会议呈现侧重拉对应域）。
 */

/** 受影响的展示域（与会议页 Tab 对应） */
export type TaskDomain = 'todos' | 'summary' | 'notes'

/** 全局事件名：一次成功的任务写回落盘 */
export const TASK_WRITTEN_EVENT = 'task-written'

/** 写回工具 → 受影响展示域（洞察板另有 board-written 通道，不在此列） */
const WRITE_TOOL_DOMAINS: Record<string, TaskDomain[]> = {
  update_decision_node: ['todos'],
  delete_decision_node: ['todos'],
  inject_items: ['todos'],
  update_summary: ['summary'],
}

/** MCP 工具全名归一：mcp__<server>__<tool> → tool（内置引擎直接给裸名） */
export function bareToolName(name?: string | null): string {
  if (!name) return ''
  const i = name.lastIndexOf('__')
  return i >= 0 ? name.slice(i + 2) : name
}

/** 该工具是否是一次任务数据写回；返回受影响域（非写回工具返回 null） */
export function writeDomainsOf(name?: string | null): TaskDomain[] | null {
  const bare = bareToolName(name)
  return WRITE_TOOL_DOMAINS[bare] || null
}

export interface TaskWrittenDetail {
  tool?: string
  domains?: TaskDomain[]
  /** 本轮标识：有值时呈现侧可挂「撤销本轮改写」 */
  turnId?: string
}

/** 广播「任务已写回」 */
export function notifyTaskWritten(detail: TaskWrittenDetail = {}) {
  window.dispatchEvent(new CustomEvent<TaskWrittenDetail>(TASK_WRITTEN_EVENT, { detail }))
}

/** 订阅「任务已写回」，返回取消订阅函数 */
export function onTaskWritten(handler: (detail: TaskWrittenDetail) => void): () => void {
  const listener = (e: Event) => handler(((e as CustomEvent).detail || {}) as TaskWrittenDetail)
  window.addEventListener(TASK_WRITTEN_EVENT, listener)
  return () => window.removeEventListener(TASK_WRITTEN_EVENT, listener)
}
