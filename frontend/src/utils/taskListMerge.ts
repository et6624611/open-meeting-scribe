/**
 * 任务列表快照合并 / Task-list snapshot merging
 *
 * 背景：完成侦测器 5s 轮询与会议页详情轮询并发。旧实现用全量列表整体替换 store，
 * 当慢列表（35MB、2~3s）的旧 processing 快照晚于详情轮询的 completed 落地时，
 * 页面会「显示纪要 → 闪回进度 → 再完成」。本模块提供纯函数合并与终态防回退。
 */
import type { Task } from '@/api/types'

/** 管线进行态 / Pipeline-active states */
export const ACTIVE_STATUSES = new Set([
  'pending', 'processing', 'transcribing', 'summarizing', 'awaiting_mapping',
])
/** 管线终态 / Terminal states */
export const TERMINAL_STATUSES = new Set(['completed', 'failed'])

/** 过期快照到达时需保护的字段：状态面 + 已生成产物（重生成期间服务端保留旧产物）
 *  Fields protected when a stale snapshot regresses a terminal task back to active */
export const GUARDED_FIELDS = [
  'status', 'progress', 'message', 'error', 'error_category', 'error_suggestion',
  'failed_stage', 'retry_count', 'summary', 'title', 'output_path', 'chapters', 'todos',
] as const

/**
 * 过期快照防护：本地已终态、incoming 却是进行态（请求在途时状态已推进），
 * 剥离状态面与产物字段，防止终态被回退覆盖。 /
 * Strip status/artifact fields from a stale snapshot that regresses a terminal task.
 */
export function guardStaleFields<T extends Partial<Task>>(incoming: T, current: Task): T {
  if (
    TERMINAL_STATUSES.has(current.status) &&
    incoming.status &&
    ACTIVE_STATUSES.has(incoming.status)
  ) {
    const safe = { ...incoming }
    for (const f of GUARDED_FIELDS) {
      delete (safe as Record<string, unknown>)[f]
    }
    return safe
  }
  return incoming
}

/**
 * 合并后端列表快照 / Merge a backend list snapshot into current store tasks.
 *
 * @param current  当前 store 列表 / current store tasks
 * @param incoming 后端返回的任务列表（可能是过期快照）/ incoming tasks (possibly stale)
 * @param lite     true=只原地更新已知任务的状态字段，不新增、不删除（完成侦测器）；
 *                 false=权威全量列表，按返回顺序重建，不在名单内的任务移除（已删除）
 */
export function mergeTaskLists(current: Task[], incoming: Task[], lite: boolean): Task[] {
  const indexById = new Map(current.map((tk, i) => [tk.task_id, i]))

  if (lite) {
    // 复制后原地合并，保持既有顺序与引用稳定 / Copy then merge in place; keep order
    const next = current.slice()
    for (const snap of incoming) {
      const idx = indexById.get(snap.task_id)
      if (idx === undefined) continue
      next[idx] = { ...next[idx], ...guardStaleFields(snap, next[idx]) }
    }
    return next
  }

  return incoming.map((snap) => {
    const idx = indexById.get(snap.task_id)
    const local = idx !== undefined ? current[idx] : undefined
    return local ? { ...local, ...guardStaleFields(snap, local) } : snap
  })
}
