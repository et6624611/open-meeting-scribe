/**
 * 洞察板变更信号 / Insight Board change signal
 *
 * 背景（洞察板自动同步）：板的唯一写入点在后端（会话工具 revise_insight_board 落盘 rev+1），
 * 而会后详情页不在实时转写 WebSocket 通道上，过去只能靠人工点「刷新」才可见新版本。
 * 本模块提供两件事：
 *   1. 识别「一次成功的落板工具调用」（内置引擎裸名 / CLI 引擎 mcp__<server>__<tool> 全名）；
 *   2. 跨组件通道 board-written（AI 面板发出信号 → 洞察板呈现侧重拉），沿用 quote-to-ai 的 CustomEvent 先例。
 */

/** 会写板的工具名（读语义的 revise_insight_board 不带 html 时不算写） */
const BOARD_WRITE_TOOLS = ['revise_insight_board', 'revise_insight_board_section']

/** 全局事件名：一次成功的落板发生 */
export const BOARD_WRITTEN_EVENT = 'board-written'

/** MCP 工具全名归一：mcp__<server>__<tool> → tool（内置引擎直接给裸名） */
function bareToolName(name: string): string {
  if (!name) return ''
  const i = name.lastIndexOf('__')
  return i >= 0 ? name.slice(i + 2) : name
}

/**
 * 该 tool_call 是否是一次「写板」（而非取基线的读）。
 * revise_insight_board 是读写双语义工具：不带 html 参数 = 只读当前板，不触发重拉。
 */
export function isBoardWriteCall(name: string, args?: Record<string, unknown> | null): boolean {
  const bare = bareToolName(name)
  if (!BOARD_WRITE_TOOLS.includes(bare)) return false
  if (bare === 'revise_insight_board') {
    const html = args?.html
    return typeof html === 'string' && html.trim().length > 0
  }
  return true
}

/**
 * 该 tool_result 是否对应一次写板。
 * 两引擎事件现均带 tool_use_id（内置引擎为本次补齐），优先按 id 回到具体 tool_call
 * 的 args 判定读/写；id 缺失时（历史流数据）降级按工具名判定。
 */
export function isBoardWriteResult(result: { name?: string; tool_use_id?: string }, writeIds: Set<string>): boolean {
  if (result.tool_use_id) return writeIds.has(result.tool_use_id)
  return !!result.name && BOARD_WRITE_TOOLS.includes(bareToolName(result.name))
}

/** 广播「板已更新」，detail.revision 为工具回执中的新版本号（缺省则订阅侧自行比对） */
export function notifyBoardWritten(detail: { revision?: number; tool?: string } = {}) {
  window.dispatchEvent(new CustomEvent(BOARD_WRITTEN_EVENT, { detail }))
}

/** 订阅「板已更新」，返回取消订阅函数 */
export function onBoardWritten(handler: (detail: { revision?: number; tool?: string }) => void): () => void {
  const listener = (e: Event) => handler(((e as CustomEvent).detail || {}) as { revision?: number; tool?: string })
  window.addEventListener(BOARD_WRITTEN_EVENT, listener)
  return () => window.removeEventListener(BOARD_WRITTEN_EVENT, listener)
}
