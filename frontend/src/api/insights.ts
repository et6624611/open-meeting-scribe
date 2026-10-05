/**
 * 洞察台 API 封装 / Insight Deck API wrapper
 *
 * 提供洞察分析引擎 + 消息持久化的后端调用。 / Provides insight analysis engine + message persistence backend calls.
 * 洞察消息按会议（task）隔离存储。 / Insight messages stored isolated by meeting (task).
 */
import client from './client'

/** 洞察分析结果 / Insight analysis result */
export interface InsightAnalysisResult {
  title: string
  body: string
  solution: string
  /** 备查注释层（≤60字，可选；旧结果无此字段） / Note layer (optional, absent in legacy results) */
  note?: string
  has_finding: boolean
  /** Mermaid 图语法（可选） / Mermaid diagram syntax (optional) */
  diagram?: string
}

/* 旧版结构化图谱类型：仅供 InsightGraph.vue 渲染历史会话消息使用
   Legacy graph types: only used by InsightGraph.vue to render historical messages */
export interface InsightGraphData {
  nodes: InsightGraphNode[]
  edges: InsightGraphEdge[]
}

/** 图谱节点 / Graph node */
export interface InsightGraphNode {
  id: string
  label: string
  /** 对应转写时间戳（毫秒），0 表示无关联 / Corresponding transcript timestamp (ms), 0 means no association */
  begin_time: number
}

/** 图谱边 / Graph edge */
export interface InsightGraphEdge {
  from: string
  to: string
  label: string
}

/** 转写行（用于分析请求） / Transcript line (for analysis request) */
export interface InsightTranscriptLine {
  text: string
  speaker_id: number
  begin_time: number
}

/** 已有洞察摘要（只读累进上下文） / Existing insight digest (read-only progressive context) */
export interface InsightExistingDigestItem {
  title: string
  body: string
}

/**
 * 洞察分析：调用 LLM 对当前讨论执行综合洞察分析 / Insight analysis: invoke LLM for unified insight analysis of current discussion
 *
 * @param params.recent_lines 最近 N 条转写内容 / Recent N transcript lines
 * @param params.chapter_titles 章节标题列表 / Chapter title list
 * @param params.existing_insights 已有卡片 title/body 摘要（可选，使模型获得全局视角）
 *        Existing card title/body digest (optional, gives the model a global view)
 * @param params.card_slots 一页纸系数换算的有效卡位（可选；缺省后端不注入预算块）
 *        Card slots from the per-meeting one-page factor (optional; backend skips the budget block when absent)
 */
export async function runInsightAnalysis(params: {
  recent_lines: InsightTranscriptLine[]
  chapter_titles: string[]
  existing_insights?: InsightExistingDigestItem[]
  card_slots?: number
}): Promise<InsightAnalysisResult> {
  const { data } = await client.post<InsightAnalysisResult>('/api/insights/analyze', params)
  return data
}

/**
 * 加载指定会议的洞察消息列表 / Load insight messages for a meeting
 */
export async function loadInsightMessages(taskId: string): Promise<{ messages: any[] }> {
  const { data } = await client.get<{ messages: any[] }>(`/api/insights/messages/${taskId}`)
  return data
}

/**
 * 会后补分析：服务端基于任务全文 + 章节执行一轮洞察分析，有发现时后端已追加快照落盘 /
 * Post-meeting analysis: server analyzes from full task content and appends the snapshot on finding.
 * 返回完整消息列表，调用方以重拉语义替换本地列表 / Returns the full list; caller replaces local state with it.
 * 超时对齐后端 60s 守护（实测可达 52s，全局 30s 会「后端成功、前端报错」）
 */
export async function runPostMeetingAnalysis(taskId: string): Promise<{ result: InsightAnalysisResult; messages: any[] }> {
  const { data } = await client.post<{ result: InsightAnalysisResult; messages: any[] }>(
    `/api/insights/analyze/task/${taskId}`, null, { timeout: 70_000 }
  )
  return data
}

/**
 * 保存指定会议的洞察消息列表 / Save insight messages for a meeting
 * 后端写盘前按系数执行预算重排，响应回传重排后的全量列表（含 deferred 标记）；
 * 调用方以重拉语义替换本地列表，避免陈旧内存下次整体覆盖。
 * The backend rebalances by the one-page factor before persisting and returns the full
 * rebalanced list (with deferred flags); callers replace local state with it.
 */
export async function saveInsightMessages(taskId: string, messages: any[]): Promise<{ ok: boolean; count: number; messages?: any[] }> {
  const { data } = await client.post<{ ok: boolean; count: number; messages?: any[] }>(
    `/api/insights/messages/${taskId}`,
    { messages }
  )
  return data
}
