/**
 * 笔记 + 待办 API 封装 / Notes + todos API wrapper
 */
import client from './client'
import type { TodoItem, DecisionStatus, OwnerType } from './types'

/** 决策流节点可更新字段 / Patchable fields for a decision-flow node */
export interface TodoPatch {
  text?: string
  assignee?: string
  why?: string
  how?: string[]
  outcome?: string
  /** DC-UNIFY-01：状态为状态字典 id（不再是封闭枚举） */
  status?: DecisionStatus
  owner_type?: OwnerType
  /** 决策短标题与执行人档案 id（承接原 decision 对象能力） */
  title?: string
  owner_id?: string | null
}

/** 新建决策流节点的载荷 / Payload for creating a decision-flow node */
export interface TodoCreatePayload {
  text: string
  assignee?: string
  why?: string
  title?: string
  owner_id?: string | null
  status?: DecisionStatus
  /** 等待方（决策由谁推进）：新表单采集项，取代执行人 */
  owner_type?: OwnerType
}

/** 获取笔记 / Fetch notes */
export async function fetchNotes(taskId: string): Promise<string> {
  const { data } = await client.get<{ notes: string }>(`/api/tasks/${taskId}/notes`)
  return data.notes || ''
}

/** 保存笔记 / Save notes */
export async function saveNotes(taskId: string, notes: string): Promise<void> {
  await client.put(`/api/tasks/${taskId}/notes`, { notes })
}

/** 保存用户编辑的纪要 / Save user-edited summary */
export async function saveSummary(taskId: string, summary: string): Promise<void> {
  await client.put(`/api/tasks/${taskId}/summary`, { notes: summary })
}

/** 获取决策流节点列表（附状态字典元信息） / Fetch decision-flow nodes with status meta */
export async function fetchTodos(taskId: string): Promise<TodoItem[]> {
  const { data } = await client.get<{ todos: TodoItem[] }>(`/api/tasks/${taskId}/todos`)
  return data.todos || []
}

/** 切换待办完成状态 / Toggle todo completion status */
export async function toggleTodo(taskId: string, todoId: string, done: boolean): Promise<void> {
  await client.post(`/api/tasks/${taskId}/todos/${todoId}/toggle`, { done })
}

/** 新建决策流节点 / Create a decision-flow node */
export async function createTodo(
  taskId: string,
  payload: TodoCreatePayload | string,
  assignee?: string,
  why?: string,
): Promise<TodoItem> {
  const body: TodoCreatePayload = typeof payload === 'string'
    ? { text: payload, assignee, why }
    : payload
  const { data } = await client.post<{ todo: TodoItem }>(`/api/tasks/${taskId}/todos`, body)
  return data.todo
}

/** 删除决策流节点 / Delete a decision-flow node */
export async function deleteTodo(taskId: string, todoId: string): Promise<void> {
  await client.delete(`/api/tasks/${taskId}/todos/${todoId}`)
}

/** 编辑决策流节点 / Update a decision-flow node */
export async function updateTodo(
  taskId: string,
  todoId: string,
  patch: TodoPatch,
): Promise<void> {
  await client.put(`/api/tasks/${taskId}/todos/${todoId}`, patch)
}

// ─── 决策演变链：标记/撤销「已被替代」 / Evolution: supersede & revert ───

/** 标记旧决策已被新决策替代（写入 superseded_by 快照，返回更新后节点） */
export async function supersedeTodo(
  taskId: string,
  todoId: string,
  by: { taskId: string; todoId: string },
): Promise<TodoItem> {
  const { data } = await client.post<{ todo: TodoItem }>(
    `/api/tasks/${taskId}/todos/${todoId}/supersede`,
    { by_task_id: by.taskId, by_todo_id: by.todoId },
  )
  return data.todo
}

/** 撤销替代标记（恢复 prev_status，已删除则安全降级），返回更新后节点 */
export async function revertSupersede(taskId: string, todoId: string): Promise<TodoItem> {
  const { data } = await client.delete<{ todo: TodoItem }>(
    `/api/tasks/${taskId}/todos/${todoId}/supersede`,
  )
  return data.todo
}

// ─── AI 写回快照与撤销 / AI write-back snapshots & undo（PROPOSAL §5.4） ───

/** 一条 AI 写回快照的摘要（不回旧值全文） */
export interface RewriteSnapshot {
  id: string
  target: string
  tool?: string
  turn_id?: string
  ts?: string
  description?: string
}

/** 列出本会议的 AI 写回快照，可按节点/本轮过滤 */
export async function fetchTaskRewrites(
  taskId: string,
  filter?: { target?: string; turnId?: string },
): Promise<RewriteSnapshot[]> {
  const { data } = await client.get<{ snapshots: RewriteSnapshot[] }>(
    `/api/tasks/${taskId}/rewrites`,
    { params: { target: filter?.target, turn_id: filter?.turnId } },
  )
  return data.snapshots || []
}

/**
 * 撤销 AI 写回：传 turnId 整轮逆序回滚，传 snapshotId 单点恢复。
 * 返回后端恢复条数与明细（供 toast 与重拉判定）。
 */
export async function restoreTaskRewrites(
  taskId: string,
  target: { turnId?: string; snapshotId?: string },
): Promise<{ ok: boolean; restored: number; detail?: string[] }> {
  const { data } = await client.post(`/api/tasks/${taskId}/rewrites/restore`, {
    turn_id: target.turnId,
    snapshot_id: target.snapshotId,
  })
  return data
}
