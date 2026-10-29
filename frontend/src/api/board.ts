/**
 * 洞察板 API 封装 / Insight Board API wrapper
 *
 * 「洞察共创 · 会话驱动（原始 HTML 版）」：板是一份 AI 直出的自包含 HTML 文档，
 * 唯一写入路径为会话工具 revise_insight_board（后端安全清洗后整份落盘），前端只读重拉。
 * 一场会议可有多份板：清单（manifest）是板集合的唯一权威，建板只能由用户显式发起。
 * 旧 Board Spec v0.3 结构化契约（ops/zone/cell、BoardAnalyzeResult、BoardNotice）已退役。
 */
import client from './client'

/** 板 HTML 产物 / Board HTML artifact */
export interface BoardArtifact {
  html: string | null
  revision: number
  updated_at: number | null
  /** 本次读取命中的板（多板下重拉与共创都要按它寻址） */
  board_id?: string
  title?: string
}

/** 单份板的清单条目 / One manifest entry */
export interface BoardSummary {
  board_id: string
  title: string
  revision: number
  updated_at: number | null
  /** 是否已有 HTML 落盘（刚建未写的板 revision=0 且 exists=false） */
  exists: boolean
}

/** 板集合 / Boards manifest */
export interface BoardsManifest {
  boards: BoardSummary[]
  default_board_id: string
}

/** 板版本信息（不含正文）/ Board revision metadata (no body) */
export interface BoardMeta {
  revision: number
  updated_at: number | null
  exists: boolean
  board_id?: string
  /** 多板轮询：一次请求拿全部板的版本（变化时只重拉当前可见板） */
  boards?: BoardSummary[]
  default_board_id?: string
}

/** 读取会议洞察板（HTML 产物）；无板 html 为 null / Load board artifact */
export async function loadBoard(taskId: string, boardId?: string): Promise<BoardArtifact> {
  const { data } = await client.get<BoardArtifact>(`/api/insights/board/${taskId}`, {
    params: boardId ? { board_id: boardId } : {},
  })
  return {
    html: data.html ?? null, revision: data.revision || 0, updated_at: data.updated_at ?? null,
    board_id: data.board_id, title: data.title,
  }
}

/**
 * 轻量版本探测 / Probe board revision only.
 *  返体几十字节（meta=1 不回 HTML 正文），供洞察 Tab 轮询比对：
 *  覆盖「写板发生在其它窗口/设备、本标签页收不到对话流信号」的缝隙。
 *  不带 boardId 时返回全部板的 revision 清单（多板下一次请求探全部）。 */
export async function loadBoardMeta(taskId: string, boardId?: string): Promise<BoardMeta> {
  const { data } = await client.get<BoardMeta>(`/api/insights/board/${taskId}`, {
    params: { meta: 1, ...(boardId ? { board_id: boardId } : {}) },
  })
  return {
    revision: data.revision || 0, updated_at: data.updated_at ?? null, exists: !!data.exists,
    board_id: data.board_id, boards: data.boards || [], default_board_id: data.default_board_id,
  }
}

/** 板清单 / List boards manifest（供 tab 轨渲染与轮询比对） */
export async function listBoards(taskId: string): Promise<BoardsManifest> {
  const { data } = await client.get<BoardsManifest>(`/api/insights/board/${taskId}/boards`)
  return { boards: data.boards || [], default_board_id: data.default_board_id || 'main' }
}

/**
 * 建板（用户意志的出口）/ Create a board — user intent only.
 * 只写 manifest 条目（revision=0，不产生 0 字节 HTML 文件）。
 * source 用于审计区分「＋ 新建板」与「提案被接受」。
 */
export async function createBoard(
  taskId: string, title: string, boardId?: string,
  source: 'ui' | 'proposal' = 'ui',
): Promise<{ board_id: string; title: string }> {
  const { data } = await client.post(`/api/insights/board/${taskId}/boards`, {
    title, ...(boardId ? { board_id: boardId } : {}), source,
  })
  return { board_id: data.board_id, title: data.title }
}

/** 独立浏览页路由（SPA 路径）：图能渲染、主题能下发，与站内同一观感 / Standalone viewer route */
export function boardViewerUrl(taskId: string, boardId?: string): string {
  const q = boardId ? `?board_id=${encodeURIComponent(boardId)}` : ''
  return `/board/${encodeURIComponent(taskId)}${q}`
}

/** 原始字节出口 URL（导出/调试用；这条路径不跑桥接，mermaid 以源码显示）/ Raw bytes URL */
export function boardRawUrl(taskId: string, boardId?: string, rev?: number): string {
  const qs = [`board_id=${encodeURIComponent(boardId || '')}`, `rev=${rev ?? ''}`].join('&')
  return `/api/insights/board/${taskId}/raw?${qs}`
}

/** 请后端用系统浏览器打开浏览页 / Ask the backend to open the viewer in the system browser
 *
 * 不再传 raw_url：浏览器入口从「原始字节」换成「浏览页」后，图与主题才会跟随；
 * 且目标路径由后端自己按 task_id 拼，不让客户端自由指定跳转（避免开放重定向）。 */
export async function openBoardInBrowser(taskId: string, boardId?: string, _rev?: number): Promise<boolean> {
  const { data } = await client.post(`/api/insights/board/${taskId}/open`, {
    board_id: boardId || '',
  })
  return !!data?.ok
}
