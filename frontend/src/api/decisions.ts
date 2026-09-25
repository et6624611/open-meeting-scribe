/**
 * 决策中心 API 封装 / Decision-center API wrapper
 *
 * 契约事实源：docs/API_CONTRACTS.md §12（REQ-DECISION-CENTER B1 + R2-b/R2-c 修订）。
 * 后端交付前，开发/自测通过 VITE_DECISIONS_MOCK=1 切换到内存 mock（见 decisionsMock.ts）；
 * 默认走真实接口，联调无需改代码。
 * 注意：§12.3 的 status 为单值精确过滤（非法值 422），多状态走 fetchDecisionsMulti（本地筛选）。
 */
import client from './client'
import { isMockEnabled, mockApi } from './decisionsMock'

// ─── 类型（与 R1 数据模型对齐） / Types (aligned with the R1 data model) ───

/**
 * 决策状态值：DC-R2-c 后为状态字典 id（不再是封闭枚举）。
 * 内置锚点 active/done 不可删，其余由用户维护；字段保留别名以免改动存量引用。
 */
export type DecisionLifecycle = string
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

/** 聚合视图条目：决策全部字段 + 状态字典元信息 + 来源会议元信息（§12.3 平铺元素） */
export interface AggregatedDecision extends DecisionRecord {
  task_id: string
  /** 来源会议标题（DC-R2-b 契约修正：`title` 已让位给决策自身标题） */
  meeting_title: string
  meeting_date: string | null
  /** 所属知识库（= project_id），未关联为 null */
  kb_id: string | null
  kb_name: string | null
  /** DC-R2-c：状态名/颜色/闭档位随行下发，徽标与沉底不再写死枚举 */
  status_name: string
  status_name_en: string
  status_color: string
  status_closing: boolean
  /** mock 专属扩展：真实契约不返回已删除任务的决策，仅演示「来源会议已删除」降级 */
  task_deleted?: boolean
}

/** 聚合查询参数（§12.3）；status 为状态字典 id（单值精确过滤） */
export interface DecisionQuery {
  /** YYYY-MM-DD，闭区间；任务无 meeting_date 时在日期过滤下被排除 */
  since?: string
  until?: string
  /** 知识库（project）过滤 */
  kb_id?: string
  /** 单值精确过滤（契约约束）；多状态由客户端一次拉全量后本地筛选 */
  status?: string
  /** text 与 title 子串匹配（区分大小写） */
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
 * 多状态聚合查询（DC-R2-c 后改为一次拉全量 + 本地筛选）：
 * 状态字典可自定义后服务端单值过滤已不适合多状态场景（N 个状态 = N 次往返），
 * 且默认视图 = 非闭档全集，随用户新增状态变化，本地筛选更直白。
 */
export async function fetchDecisionsMulti(
  query: Omit<DecisionQuery, 'status'> & { statuses: string[] },
): Promise<AggregatedDecision[]> {
  const { statuses, ...base } = query
  const all = await fetchDecisions(base)
  if (!statuses.length) return all
  const wanted = new Set(statuses)
  return all.filter(d => wanted.has(d.status))
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

// DC-R2-c（D6）：supersedeTaskDecision 已随写回端点下线（取代/撤销不再是系统行为）。
