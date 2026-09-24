/**
 * 决策中心内存 mock / In-memory mock for the decision center
 *
 * 仅用于 REQ-DECISION-CENTER 前端（DC-DEC-F1）在 DC-DEC-B1 后端交付前的开发与自测。
 * 开关：dev 时设置环境变量 VITE_DECISIONS_MOCK=1（默认关闭，生产构建永不生效）。
 * 数据形状与 docs/API_CONTRACTS.md §12 契约一一对应（task_deleted 为 mock 专属扩展）；写操作直接改动内存态，
 * 使 supersede/revoke/补录 交互在同一页面会话内可完整走通。
 */
import type {
  AggregatedDecision, DecisionCreatePayload, DecisionMockQuery, DecisionPatchPayload,
  DecisionRecord, DecisionSource, SupersedeRef,
} from './decisions'

/** mock 仅在此开关下被引用；api/decisions.ts 通过同名函数消费 */
export function isMockEnabled(): boolean {
  return import.meta.env.DEV && import.meta.env.VITE_DECISIONS_MOCK === '1'
}

// ─── 时间工具：fixture 相对"今天"生成，保证 7天/30天 筛选可测 ───
const DAY = 24 * 3600 * 1000
function iso(daysAgo: number, hour = 10): string {
  const d = new Date(Date.now() - daysAgo * DAY)
  d.setHours(hour, 0, 0, 0)
  return d.toISOString()
}
function dateStr(daysAgo: number): string {
  return iso(daysAgo).slice(0, 10)
}

interface MockMeeting {
  task_id: string
  title: string
  meeting_date: string
  kb_id: string | null
  kb_name: string | null
  /** 模拟来源会议已被删除：聚合结果里其决策不再出现，但 superseded_by 可能仍指向它 */
  deleted?: boolean
}

const meetings: MockMeeting[] = [
  { task_id: 'mock-task-1', title: '投委会 · Q4 预算终审', meeting_date: dateStr(1), kb_id: 'kb-1', kb_name: '产品委员会' },
  { task_id: 'mock-task-2', title: 'OMS 双周迭代复盘', meeting_date: dateStr(3), kb_id: 'kb-2', kb_name: '研发管理' },
  { task_id: 'mock-task-3', title: '知识库架构评审', meeting_date: dateStr(12), kb_id: 'kb-2', kb_name: '研发管理' },
  { task_id: 'mock-task-4', title: '客户访谈 · 华东大区', meeting_date: dateStr(21), kb_id: 'kb-1', kb_name: '产品委员会' },
  { task_id: 'mock-task-5', title: '年度战略务虚会', meeting_date: dateStr(45), kb_id: null, kb_name: null },
  { task_id: 'mock-task-deleted', title: '', meeting_date: '', kb_id: null, kb_name: null, deleted: true },
]

let seq = 0
function newId(): string {
  seq += 1
  return `mock-dec-${Date.now().toString(36)}-${seq}`
}

interface SeedRow extends Omit<DecisionRecord, 'id' | 'created_at' | 'updated_at'> {
  task_id: string
  daysAgo: number
}

const seeds: SeedRow[] = [
  {
    task_id: 'mock-task-1', daysAgo: 1, text: 'Q4 市场预算维持 120 万，其中 40% 用于行业展会。',
    status: 'active', pending_confirmation: false, source: 'auto', superseded_by: null, related_todo_ids: [],
  },
  {
    task_id: 'mock-task-1', daysAgo: 1, text: '决策中心需求跳过 P0，直接按 P1 交付。',
    status: 'active', pending_confirmation: true, source: 'auto', superseded_by: null, related_todo_ids: [],
  },
  {
    task_id: 'mock-task-2', daysAgo: 3, text: 'v2.1 迭代范围冻结为转写进度与决策中心两条主线。',
    status: 'active', pending_confirmation: false, source: 'auto', superseded_by: null, related_todo_ids: [],
  },
  {
    task_id: 'mock-task-2', daysAgo: 3, text: '离线引擎默认模型切换为 paraformer-mini。',
    status: 'superseded', pending_confirmation: false, source: 'auto', related_todo_ids: [],
    superseded_by: { task_id: 'mock-task-1', decision_id: '' /* 运行时回填：指向 task-1 第一条 */ },
  },
  {
    task_id: 'mock-task-3', daysAgo: 12, text: '知识库同步采用脏检测触发，不做定时轮询。',
    status: 'active', pending_confirmation: false, source: 'backfill', superseded_by: null, related_todo_ids: [],
  },
  {
    task_id: 'mock-task-3', daysAgo: 12, text: '转写任务全部走 DashScope 临时存储上传。',
    status: 'superseded', pending_confirmation: false, source: 'auto', related_todo_ids: [],
    // 悬空引用：取代方所在会议已被删除 → 前端必须降级显示而非白屏
    superseded_by: { task_id: 'mock-task-deleted', decision_id: 'gone-decision-9' },
  },
  {
    task_id: 'mock-task-4', daysAgo: 21, text: '华东大区设驻场工程师 2 名，Q1 到位。',
    status: 'active', pending_confirmation: true, source: 'manual', superseded_by: null, related_todo_ids: [],
  },
  {
    task_id: 'mock-task-4', daysAgo: 21, text: '取消独立客户端安装包，统一走 Web 版。',
    status: 'revoked', pending_confirmation: false, source: 'auto', superseded_by: null, related_todo_ids: [],
  },
  {
    task_id: 'mock-task-5', daysAgo: 45, text: '明年主打「会议知识资产化」方向。',
    status: 'active', pending_confirmation: false, source: 'injection', superseded_by: null, related_todo_ids: [],
  },
]

// ─── 内存态 / In-memory state ───
const store: Map<string, DecisionRecord[]> = new Map()
function initStore() {
  for (const m of meetings) store.set(m.task_id, [])
  for (const s of seeds) {
    const rec: DecisionRecord = {
      id: newId(),
      text: s.text,
      status: s.status,
      pending_confirmation: s.pending_confirmation,
      source: s.source,
      created_at: iso(s.daysAgo),
      updated_at: iso(s.daysAgo),
      superseded_by: s.superseded_by,
      related_todo_ids: s.related_todo_ids,
    }
    store.get(s.task_id)!.push(rec)
  }
  // 回填「离线引擎」那条的取代目标 → task-1 的 paraformer/预算决策，演示有效取代链接
  const target = store.get('mock-task-1')?.find(r => r.text.includes('Q4 市场预算'))
  const superseding = store.get('mock-task-2')?.find(r => r.superseded_by && r.superseded_by.task_id === 'mock-task-1')
  if (target && superseding?.superseded_by) superseding.superseded_by.decision_id = target.id
}
initStore()

function latency<T>(value: T): Promise<T> {
  return new Promise(resolve => setTimeout(() => resolve(value), 220))
}

/** 仅 mock 通道：把真实任务注册为会议，使补录/跳转/取代链路可在真实数据上演示 */
export function registerMockMeetings(list: Array<{ task_id: string; title: string; meeting_date: string; kb_id: string | null; kb_name: string | null }>) {
  for (const m of list) {
    if (store.has(m.task_id) && meetings.some(x => x.task_id === m.task_id)) continue
    meetings.push({ task_id: m.task_id, title: m.title, meeting_date: m.meeting_date, kb_id: m.kb_id, kb_name: m.kb_name })
    if (!store.has(m.task_id)) store.set(m.task_id, [])
  }
}
function notFound(): Promise<never> {
  return Promise.reject(new Error('mock 404: decision not found'))
}
function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v))
}
function findRecord(decisionId: string): { taskId: string; rec: DecisionRecord } | null {
  for (const [taskId, list] of store) {
    const rec = list.find(r => r.id === decisionId)
    if (rec) return { taskId, rec }
  }
  return null
}

function toAggregated(taskId: string, rec: DecisionRecord): AggregatedDecision {
  const meeting = meetings.find(m => m.task_id === taskId)
  return clone({
    ...rec,
    task_id: taskId,
    task_deleted: !meeting || meeting.deleted === true,
    title: meeting && !meeting.deleted ? meeting.title : '',
    meeting_date: meeting && !meeting.deleted ? meeting.meeting_date : null,
    kb_id: meeting?.kb_id ?? null,
    kb_name: meeting && !meeting.deleted ? meeting.kb_name : null,
  })
}

// ─── mock API 实现（与 decisions.ts 函数签名一致） ───
export const mockApi = {
  async fetchDecisions(query: DecisionMockQuery = {}): Promise<AggregatedDecision[]> {
    let rows: AggregatedDecision[] = []
    for (const m of meetings) {
      if (m.deleted) continue
      for (const rec of store.get(m.task_id) || []) rows.push(toAggregated(m.task_id, rec))
    }
    if (query.since) rows = rows.filter(r => (r.meeting_date || '') >= query.since!.slice(0, 10))
    if (query.until) rows = rows.filter(r => (r.meeting_date || '') <= query.until!.slice(0, 10))
    if (query.kb_id) {
      rows = query.kb_id === '__none__'
        ? rows.filter(r => !r.kb_id)
        : rows.filter(r => r.kb_id === query.kb_id)
    }
    if (query.status) {
      const allowed = new Set(query.status.split(',').map(s => s.trim()))
      rows = rows.filter(r => allowed.has(r.status))
    }
    if (query.q) {
      const kw = query.q.toLowerCase()
      rows = rows.filter(r => r.text.toLowerCase().includes(kw))
    }
    rows.sort((a, b) => (b.meeting_date || '').localeCompare(a.meeting_date || '') || b.created_at.localeCompare(a.created_at))
    return latency(rows)
  },

  async fetchTaskDecisions(taskId: string): Promise<DecisionRecord[]> {
    const list = store.get(taskId)
    if (!list) return latency([])
    return latency(clone(list))
  },

  async createTaskDecision(taskId: string, payload: DecisionCreatePayload): Promise<DecisionRecord> {
    let list = store.get(taskId)
    if (!list) { list = []; store.set(taskId, list) }
    const now = new Date().toISOString()
    const rec: DecisionRecord = {
      id: newId(),
      text: payload.text,
      status: 'active',
      pending_confirmation: payload.pending_confirmation ?? false,
      source: 'manual' as DecisionSource,
      created_at: now,
      updated_at: now,
      superseded_by: null,
      related_todo_ids: [],
    }
    list.push(rec)
    return latency(clone(rec))
  },

  async updateTaskDecision(taskId: string, decisionId: string, patch: DecisionPatchPayload): Promise<DecisionRecord> {
    const list = store.get(taskId)
    const rec = list?.find(r => r.id === decisionId)
    if (!rec) return notFound()
    if (patch.text !== undefined) rec.text = patch.text
    if (patch.status !== undefined) rec.status = patch.status
    if (patch.pending_confirmation !== undefined) rec.pending_confirmation = patch.pending_confirmation
    rec.updated_at = new Date().toISOString()
    return latency(clone(rec))
  },

  async deleteTaskDecision(taskId: string, decisionId: string): Promise<void> {
    const list = store.get(taskId)
    const idx = list?.findIndex(r => r.id === decisionId) ?? -1
    if (!list || idx < 0) return notFound()
    list.splice(idx, 1)
    return latency(undefined)
  },

  async supersedeTaskDecision(taskId: string, decisionId: string, by: SupersedeRef): Promise<DecisionRecord> {
    const list = store.get(taskId)
    const rec = list?.find(r => r.id === decisionId)
    if (!rec) return notFound()
    const superseder = findRecord(by.decision_id)
    if (!superseder) return notFound()
    rec.status = 'superseded'
    rec.superseded_by = { task_id: superseder.taskId, decision_id: by.decision_id }
    rec.updated_at = new Date().toISOString()
    return latency(clone(rec))
  },

  /** 供 supersede 检索弹层取「取代方候选」：全量有效决策（active 优先） */
  async searchDecisions(q: string): Promise<AggregatedDecision[]> {
    const all = await this.fetchDecisions({ q: q || undefined })
    return all.filter(r => r.status === 'active')
  },
}
