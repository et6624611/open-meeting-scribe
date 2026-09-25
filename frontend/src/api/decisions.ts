/**
 * 决策中心 API 封装 / Decision-center API wrapper
 *
 * 契约事实源：docs/API_CONTRACTS.md §12（REQ-DECISION-CENTER B1，origin/feat/req-decision-center-b1）。
 * 后端交付前，开发/自测通过 VITE_DECISIONS_MOCK=1 切换到内存 mock（见 decisionsMock.ts）；
 * 默认走真实接口，联调无需改代码。
 * 注意：§12.3 的 status 为单值精确过滤（非法值 422），多状态用 fetchDecisionsMulti 拆分合并。
 */
import client from './client'
import { isMockEnabled, mockApi } from './decisionsMock'

// ─── 类型（与 R1 数据模型对齐） / Types (aligned with the R1 data model) ───

/** 决策生效状态 / Decision lifecycle status */
export type DecisionLifecycle = 'active' | 'superseded' | 'revoked'
/** 决策来源标记；重新生成纪要只覆盖 auto / Origin tag; regeneration only replaces auto */
export type DecisionSource = 'auto' | 'backfill' | 'manual' | 'injection'

/** 跨会议取代引用：指向取代方决策 / Cross-meeting supersede reference */
export interface SupersedeRef {
  task_id: string
  decision_id: string
}

/** 决策执行人选人值：null = 未指派（DC-R2-b D4，合法态） */
export type OwnerValue = { id: string; name: string } | null

/** 单会议作用域内的决策对象 / A decision within its source task */
export interface DecisionRecord {
  id: string
  /** 决策自身标题（三要素之一，DC-R2-b）；auto/存量可为空串，展示侧降级 */
  title: string
  /** 决策内容（原单字段语义收窄） */
  text: string
  /** 执行人：说话人档案 id（D4，未指派为 null） */
  owner_id: string | null
  /** 执行人展示名：后端以档案为权威解析，档案缺失时回退写入时的快照 */
  owner_name: string
  status: DecisionLifecycle
  pending_confirmation: boolean
  source: DecisionSource
  created_at: string
  updated_at: string
  superseded_by: SupersedeRef | null
  related_todo_ids: string[]
}

/** 聚合视图条目：决策全部字段 + 来源会议元信息（§12.3 平铺元素） */
export interface AggregatedDecision extends DecisionRecord {
  task_id: string
  /** 来源会议标题（DC-R2-b 契约修正：`title` 已让位给决策自身标题） */
  meeting_title: string
  meeting_date: string | null
  /** 所属知识库（= project_id），未关联为 null */
  kb_id: string | null
  kb_name: string | null
  /** mock 专属扩展：真实契约不返回已删除任务的决策，仅演示「来源会议已删除」降级 */
  task_deleted?: boolean
}

/** 聚合查询参数（§12.3，全部可选、可叠加；group_by 未使用——分组在前端完成） */
export interface DecisionQuery {
  /** YYYY-MM-DD，闭区间；任务无 meeting_date 时在日期过滤下被排除 */
  since?: string
  until?: string
  /** 知识库（project）过滤 */
  kb_id?: string
  /** 单值精确过滤（契约约束）；多状态请走 fetchDecisionsMulti */
  status?: DecisionLifecycle
  /** text 子串匹配（区分大小写） */
  q?: string
}

/** mock 通道放宽 status 为逗号多值，便于 fetchDecisionsMulti 一次内存过滤 */
export type DecisionMockQuery = Omit<DecisionQuery, 'status'> & { status?: string }

/** 创建决策入参（§12.1：text 1..2000；三要素 title/owner 可空） */
export interface DecisionCreatePayload {
  text: string
  title?: string
  /** 执行人档案 id；空串 = 不指派 */
  owner_id?: string | null
  owner_name?: string | null
  pending_confirmation?: boolean
  related_todo_ids?: string[]
}

/** 更新决策入参 / Payload for decision update */
export interface DecisionPatchPayload {
  text?: string
  title?: string
  /** 传空串 = 清空指派；未传 = 保持原指派（后端语义） */
  owner_id?: string | null
  owner_name?: string | null
  status?: DecisionLifecycle
  pending_confirmation?: boolean
}

// ─── 跨会议聚合 / Cross-meeting aggregation ───

/** 前端伪值「未关联知识库」：契约 kb_id 过滤会排除未关联任务，故该值不下发、改客户端过滤 */
const KB_NONE = '__none__'

export async function fetchDecisions(query: DecisionQuery = {}): Promise<AggregatedDecision[]> {
  if (isMockEnabled()) return mockApi.fetchDecisions(query)
  const params: Record<string, string> = {}
  if (query.since) params.since = query.since
  if (query.until) params.until = query.until
  if (query.kb_id && query.kb_id !== KB_NONE) params.kb_id = query.kb_id
  if (query.status) params.status = query.status
  if (query.q) params.q = query.q
  const { data } = await client.get<{ decisions: AggregatedDecision[] }>('/api/decisions', { params })
  const rows = data.decisions || []
  if (query.kb_id === KB_NONE) return rows.filter(d => !d.kb_id)
  return rows
}

/**
 * 多状态聚合查询：§12.3 status 为单值精确过滤（逗号多值会 422），
 * 因此按值拆分并行请求、按 task_id+id 去重，并维持 meeting_date 倒序（无日期沉底）。
 * statuses 为空数组 = 不加状态过滤（全部）。
 */
export async function fetchDecisionsMulti(
  query: Omit<DecisionQuery, 'status'> & { statuses: DecisionLifecycle[] },
): Promise<AggregatedDecision[]> {
  const { statuses, ...base } = query
  if (isMockEnabled()) return mockApi.fetchDecisions({ ...base, status: statuses.join(',') })
  if (statuses.length <= 1) return fetchDecisions({ ...base, status: statuses[0] })
  const lists = await Promise.all(statuses.map(s => fetchDecisions({ ...base, status: s })))
  const seen = new Set<string>()
  const merged: AggregatedDecision[] = []
  for (const list of lists) {
    for (const d of list) {
      const key = `${d.task_id}:${d.id}`
      if (seen.has(key)) continue
      seen.add(key)
      merged.push(d)
    }
  }
  merged.sort((a, b) => (b.meeting_date || '').localeCompare(a.meeting_date || '') || b.created_at.localeCompare(a.created_at))
  return merged
}

// ─── 任务级 CRUD / Task-scoped CRUD ───

export async function fetchTaskDecisions(taskId: string): Promise<DecisionRecord[]> {
  if (isMockEnabled()) return mockApi.fetchTaskDecisions(taskId)
  const { data } = await client.get<{ decisions: DecisionRecord[] }>(`/api/tasks/${taskId}/decisions`)
  return data.decisions || []
}

export async function createTaskDecision(taskId: string, payload: DecisionCreatePayload): Promise<DecisionRecord> {
  if (isMockEnabled()) return mockApi.createTaskDecision(taskId, payload)
  const { data } = await client.post<{ decision: DecisionRecord }>(`/api/tasks/${taskId}/decisions`, payload)
  return data.decision
}

export async function updateTaskDecision(taskId: string, decisionId: string, patch: DecisionPatchPayload): Promise<DecisionRecord> {
  if (isMockEnabled()) return mockApi.updateTaskDecision(taskId, decisionId, patch)
  const { data } = await client.put<{ decision: DecisionRecord }>(`/api/tasks/${taskId}/decisions/${decisionId}`, patch)
  return data.decision
}

export async function deleteTaskDecision(taskId: string, decisionId: string): Promise<void> {
  if (isMockEnabled()) return mockApi.deleteTaskDecision(taskId, decisionId)
  await client.delete(`/api/tasks/${taskId}/decisions/${decisionId}`)
}

/** 标记取代：body 携带取代方 {task_id, decision_id} / Mark superseded with the superseder ref */
export async function supersedeTaskDecision(taskId: string, decisionId: string, by: SupersedeRef): Promise<DecisionRecord> {
  if (isMockEnabled()) return mockApi.supersedeTaskDecision(taskId, decisionId, by)
  const { data } = await client.patch<{ decision: DecisionRecord }>(`/api/tasks/${taskId}/decisions/${decisionId}/supersede`, by)
  return data.decision
}
