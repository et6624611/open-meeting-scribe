/**
 * 笔记 + 决策 API 封装 / Notes + decisions API wrapper
 */
import client from './client'
import type { DecisionItem, DecisionStatus, OwnerType } from './types'

/** 决策流节点可更新字段 / Patchable fields for a decision-flow node */
export interface DecisionPatch {
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
export interface DecisionCreatePayload {
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
export async function fetchDecisions(taskId: string): Promise<DecisionItem[]> {
  const { data } = await client.get<{ decisions: DecisionItem[] }>(`/api/tasks/${taskId}/decisions`)
  return data.decisions || []
}

/** 切换决策完成状态 / Toggle decision completion status */
export async function toggleDecision(taskId: string, decisionId: string, done: boolean): Promise<void> {
  await client.post(`/api/tasks/${taskId}/decisions/${decisionId}/toggle`, { done })
}

/** 新建决策流节点 / Create a decision-flow node */
export async function createDecision(
  taskId: string,
  payload: DecisionCreatePayload | string,
  assignee?: string,
  why?: string,
): Promise<DecisionItem> {
  const body: DecisionCreatePayload = typeof payload === 'string'
    ? { text: payload, assignee, why }
    : payload
  const { data } = await client.post<{ decision: DecisionItem }>(`/api/tasks/${taskId}/decisions`, body)
  return data.decision
}

/** 删除决策流节点 / Delete a decision-flow node */
export async function deleteDecision(taskId: string, decisionId: string): Promise<void> {
  await client.delete(`/api/tasks/${taskId}/decisions/${decisionId}`)
}

/** 编辑决策流节点 / Update a decision-flow node */
export async function updateDecision(
  taskId: string,
  decisionId: string,
  patch: DecisionPatch,
): Promise<void> {
  await client.put(`/api/tasks/${taskId}/decisions/${decisionId}`, patch)
}

// ─── 决策演变链：标记/撤销「已被替代」 / Evolution: supersede & revert ───

/** 标记旧决策已被新决策替代（写入 superseded_by 快照，返回更新后节点） */
export async function supersedeDecision(
  taskId: string,
  decisionId: string,
  by: { taskId: string; decisionId: string },
): Promise<DecisionItem> {
  const { data } = await client.post<{ decision: DecisionItem }>(
    `/api/tasks/${taskId}/decisions/${decisionId}/supersede`,
    { by_task_id: by.taskId, by_decision_id: by.decisionId },
  )
  return data.decision
}

/** 撤销替代标记（恢复 prev_status，已删除则安全降级），返回更新后节点 */
export async function revertSupersede(taskId: string, decisionId: string): Promise<DecisionItem> {
  const { data } = await client.delete<{ decision: DecisionItem }>(
    `/api/tasks/${taskId}/decisions/${decisionId}/supersede`,
  )
  return data.decision
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
