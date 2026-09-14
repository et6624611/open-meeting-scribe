/**
 * AI 洞察 API 封装 / AI insights API wrapper
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
  has_finding: boolean
}

/** 转写行（用于分析请求） / Transcript line (for analysis request) */
export interface InsightTranscriptLine {
  text: string
  speaker_id: number
  begin_time: number
}

/** 分析类型 / Analysis type */
export type InsightAnalysisType = 'context' | 'blindspot' | 'consensus'

/**
 * 洞察分析：调用 LLM 对当前讨论执行深度分析 / Insight analysis: invoke LLM for deep analysis of current discussion
 *
 * @param params.recent_lines 最近 N 条转写内容 / Recent N transcript lines
 * @param params.chapter_titles 章节标题列表 / Chapter title list
 * @param params.analysis_type 分析类型 / Analysis type: context | blindspot | consensus
 */
export async function runInsightAnalysis(params: {
  recent_lines: InsightTranscriptLine[]
  chapter_titles: string[]
  analysis_type: InsightAnalysisType
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
 * 保存指定会议的洞察消息列表 / Save insight messages for a meeting
 */
export async function saveInsightMessages(taskId: string, messages: any[]): Promise<{ ok: boolean; count: number }> {
  const { data } = await client.post<{ ok: boolean; count: number }>(
    `/api/insights/messages/${taskId}`,
    { messages }
  )
  return data
}
