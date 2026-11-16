/**
 * 洞察板 API 封装 / Insight Board API wrapper
 *
 * 2026-11-12 重构：洞察板从 HTML 产物改为一场会议一份 Markdown 文件。
 * 不再多板、不再 sandbox iframe、不再 postMessage 桥接。
 * 前端用 marked/markdown-it 渲染 GFM + mermaid fence。
 */
import client from './client'

/** 板 Markdown 产物 / Board Markdown artifact */
export interface BoardArtifact {
  markdown: string | null
  revision: number
  updated_at: number | null
  /** 本场会议固定 "main"，多板已废弃 */
  board_id?: string
  title?: string
}

/** 单份板的清单条目（固定单板） */
export interface BoardSummary {
  board_id: string
  title: string
  revision: number
  updated_at: number | null
  exists: boolean
}

/** 板集合（固定单板，为兼容保留数组） */
export interface BoardsManifest {
  boards: BoardSummary[]
  default_board_id: string
}

/** 板版本信息（不含正文） */
export interface BoardMeta {
  revision: number
  updated_at: number | null
  exists: boolean
  board_id?: string
  boards?: BoardSummary[]
  default_board_id?: string
}

/** 读取会议洞察板（Markdown）；无板 markdown 为 null */
export async function loadBoard(taskId: string): Promise<BoardArtifact> {
  const { data } = await client.get<BoardArtifact>(`/api/insights/board/${taskId}`)
  return {
    markdown: data.markdown ?? null,
    revision: data.revision || 0,
    updated_at: data.updated_at ?? null,
    board_id: data.board_id || 'main',
    title: data.title || '主看板',
  }
}

/** 轻量版本探测 / Probe board revision only. 轮询用 */
export async function loadBoardMeta(taskId: string): Promise<BoardMeta> {
  const { data } = await client.get<BoardMeta>(`/api/insights/board/${taskId}`, {
    params: { meta: 1 },
  })
  return {
    revision: data.revision || 0, updated_at: data.updated_at ?? null, exists: !!data.exists,
    board_id: data.board_id || 'main',
    boards: data.boards || [{ board_id: 'main', title: '主看板', revision: data.revision || 0, updated_at: data.updated_at ?? null, exists: !!data.exists }],
    default_board_id: data.default_board_id || 'main',
  }
}

/** 板清单（固定单板，兼容保留） */
export async function listBoards(taskId: string): Promise<BoardsManifest> {
  const { data } = await client.get<BoardsManifest>(`/api/insights/board/${taskId}/boards`)
  return { boards: data.boards || [], default_board_id: data.default_board_id || 'main' }
}

/** 已废弃：多板拆分不再支持 */
export async function createBoard(_taskId: string, _title: string, _boardId?: string): Promise<{ board_id: string; title: string }> {
  return { board_id: 'main', title: '主看板' }
}

/** 独立浏览页路由（SPA 路径） */
export function boardViewerUrl(taskId: string): string {
  return `/board/${encodeURIComponent(taskId)}`
}

/** 原始 Markdown URL（调试/复制用） */
export function boardRawUrl(taskId: string, rev?: number): string {
  const qs = `rev=${rev ?? ''}`
  return `/api/insights/board/${taskId}/raw?${qs}`
}

/** 请后端用系统浏览器打开浏览页 */
export async function openBoardInBrowser(taskId: string): Promise<boolean> {
  const { data } = await client.post(`/api/insights/board/${taskId}/open`)
  return !!data?.ok
}
