/**
 * 洞察板 API 封装 / Insight Board API wrapper
 *
 * 「洞察共创 · 会话驱动（HTML 产物版）」：板是一份 AI 直出的自包含 HTML 文档，
 * 唯一写入路径为会话工具 revise_insight_board（后端清洗后整份落盘），前端只读重拉。
 * 旧 Board Spec v0.3 结构化契约（ops/zone/cell、BoardAnalyzeResult、BoardNotice）已退役。
 */
import client from './client'

/** 板 HTML 产物 / Board HTML artifact */
export interface BoardArtifact {
  html: string | null
  revision: number
  updated_at: number | null
}

/** 读取会议洞察板（HTML 产物）；无板 html 为 null / Load board artifact */
export async function loadBoard(taskId: string): Promise<BoardArtifact> {
  const { data } = await client.get<BoardArtifact>(`/api/insights/board/${taskId}`)
  return { html: data.html ?? null, revision: data.revision || 0, updated_at: data.updated_at ?? null }
}

/** 板版本信息（不含正文）/ Board revision metadata (no body) */
export interface BoardMeta {
  revision: number
  updated_at: number | null
  /** 是否已有板文件（首次生成需要从无到有拉正文） */
  exists: boolean
}

/** 轻量版本探测 / Probe board revision only.
 *  返体几十字节（meta=1 不回 HTML 正文），供洞察 Tab 轮询比对：
 *  覆盖「写板发生在其它窗口/设备、本标签页收不到对话流信号」的缝隙。 */
export async function loadBoardMeta(taskId: string): Promise<BoardMeta> {
  const { data } = await client.get<BoardMeta>(`/api/insights/board/${taskId}`, { params: { meta: 1 } })
  return { revision: data.revision || 0, updated_at: data.updated_at ?? null, exists: !!data.exists }
}
