/**
 * 计算引擎 API / Compute engine API
 *
 * R5/R6（PRD-LOCAL-ENGINE）：模型资产管理（/api/engine/models|downloads|storage|download|verify|start|stop）
 * 与引擎状态（/api/engine/status，徽章双因子之一）。契约见 app/routers/models.py。
 * R5/R6: model asset management and engine status; contract in app/routers/models.py.
 *
 * 权限（D-R2）：GET 面所有用户只读；POST 变更面仅管理员（后端 require_admin 兜底）。
 * Permissions (D-R2): GETs are read-only for all users; POST mutations admin-only (enforced backend-side).
 */
import client from './client'
import { fetchSettings } from './settings'

/** 引擎模式（settings.engine.mode 契约，PRD §9） / Engine mode (settings.engine.mode contract, PRD §9) */
export type EngineMode = 'cloud' | 'proxy' | 'direct' | 'local'

/** 模型状态（core/model_downloader.model_status 聚合） / Model status (aggregated by model_status) */
export type ModelStatus = 'not_downloaded' | 'partial' | 'downloading' | 'ready' | 'tampered' | 'missing'

/** 下载任务状态 / Download job state */
export type JobState = 'pending' | 'downloading' | 'verifying' | 'ready' | 'failed' | 'cancelled'

export interface DownloadJob {
  id: string
  model_key: string
  state: JobState
  total_bytes: number
  downloaded_bytes: number
  remaining_bytes: number
  /** 字节/秒 / bytes per second */
  speed_bps: number
  eta_seconds: number | null
  percent: number
  error: string | null
  error_code: string | null
  created_at: number
  updated_at: number
}

export interface EngineModelInfo {
  key: string
  name: string
  modelscope_id: string
  size_bytes: number
  purpose: string
  /** 可裁剪大件（ct-punc） / Optional heavy component (ct-punc) */
  optional: boolean
  license: string
  status: ModelStatus
  job: DownloadJob | null
}

export interface EngineModelsOverview {
  model_dir: string
  disk_free_bytes: number
  total_size_all_bytes: number
  total_size_required_bytes: number
  models: EngineModelInfo[]
  downloads: DownloadJob[]
}

/** R9/WP-I 本地分段增量上屏配置 / Local segmented incremental transcription config */
export interface RealtimeSegmentsConfig {
  enabled: boolean
  min_segment_s: number
  min_silence_s: number
  max_segment_s: number
}

export interface EngineHostStatus {
  mode: EngineMode
  model_dir: string
  modelscope_cache: string
  process_running: boolean
  pid: number | null
  models_ready: boolean
  missing_models: string[]
  tampered_models: string[]
  realtime_segments?: RealtimeSegmentsConfig
}

export interface EngineActionResult {
  ok: boolean
  error?: string
  error_code?: string
  [key: string]: unknown
}

export interface EngineStatus {
  /** 当前引擎模式 / Current engine mode */
  mode: EngineMode
  /** 本地引擎目录存在且模型就绪（双因子之一） / Local engine directory exists and models ready (factor 1 of 2) */
  local_ready: boolean
  /** 常驻引擎子进程是否在跑 / Whether the resident engine subprocess is running */
  process_running: boolean
  /** 子进程 PID（未运行为 null） / Subprocess PID (null when not running) */
  pid: number | null
  missing_models: string[]
  tampered_models: string[]
  /** 当前身份是否可操作变更面（本地单机模式或管理员） / Whether the current identity may perform mutations (local single-user or admin) */
  can_manage: boolean
  /** 本地模式分段增量上屏是否开启（关：录音后本机统一批转写，会中不出字） / Local segmented incremental display enabled (off: on-device batch transcription only after recording) */
  realtime_segments_enabled: boolean
  /** 数据来源：api=后端状态接口 / settings=占位回退 / Data source: api=status endpoint / settings=placeholder fallback */
  source: 'api' | 'settings'
}

interface EngineStatusResponse extends Partial<EngineHostStatus> {
  mode?: EngineMode
  local?: { ready?: boolean; model_dir?: string }
  can_manage?: boolean
}

/**
 * 获取引擎状态：优先 /api/engine/status，接口不可用时回退 settings 占位字段。
 * Fetch engine status: prefer /api/engine/status, fall back to settings placeholder fields.
 */
export async function fetchEngineStatus(): Promise<EngineStatus> {
  try {
    const { data } = await client.get<EngineStatusResponse>('/api/engine/status')
    if (data && typeof data.mode === 'string') {
      return {
        mode: data.mode,
        local_ready: data.models_ready === true || !!data.local?.ready,
        process_running: !!data.process_running,
        pid: data.pid ?? null,
        missing_models: data.missing_models || [],
        tampered_models: data.tampered_models || [],
        can_manage: data.can_manage === true,
        realtime_segments_enabled: data.realtime_segments?.enabled === true,
        source: 'api',
      }
    }
  } catch {
    // 接口未就绪，落入 settings 回退 / Endpoint unavailable, fall through to settings fallback
  }

  // TODO(WP-B 联调 / integration): settings.engine 为占位契约，后端 /api/engine/status 不可达时才走到这里。
  // settings.engine is a placeholder contract, reached only when the backend endpoint is unavailable.
  const settings = await fetchSettings()
  const engine = settings.engine as { mode?: EngineMode; local?: { ready?: boolean } } | undefined
  const mode: EngineMode = engine?.mode
    ?? (settings.asr?.mode === 'direct' ? 'direct' : 'proxy')
  return {
    mode,
    local_ready: !!engine?.local?.ready,
    process_running: false,
    pid: null,
    missing_models: [],
    tampered_models: [],
    can_manage: false,
    realtime_segments_enabled: false,
    source: 'settings',
  }
}

/** 模型清单 + 逐个状态 + 磁盘信息 + 活动下载（只读） / Manifest + per-model status + disk info + active jobs (read-only) */
export async function fetchEngineModels(): Promise<EngineModelsOverview> {
  const { data } = await client.get<EngineModelsOverview & { ok: boolean }>('/api/engine/models')
  return data
}

/** 下载任务进度 / Download job progress */
export async function fetchEngineDownloads(): Promise<DownloadJob[]> {
  const { data } = await client.get<{ ok: boolean; jobs: DownloadJob[] }>('/api/engine/downloads')
  return data.jobs
}

/** 模型存储位置与磁盘空间 / Model storage location and disk space */
export async function fetchEngineStorage(): Promise<{ model_dir: string; disk_free_bytes: number }> {
  const { data } = await client.get<{ ok: boolean; model_dir: string; disk_free_bytes: number }>('/api/engine/storage')
  return { model_dir: data.model_dir, disk_free_bytes: data.disk_free_bytes }
}

/** 引导下载（model_key 或 'all'，管理员） / Start guided download (model_key or 'all', admin) */
export async function startModelDownload(modelKey: string): Promise<EngineActionResult & { jobs?: DownloadJob[] }> {
  const { data } = await client.post<EngineActionResult & { jobs?: DownloadJob[] }>('/api/engine/download', { model_key: modelKey })
  return data
}

/** 取消下载（保留 .part 可续传，管理员） / Cancel download (keeps .part for resume, admin) */
export async function cancelModelDownload(jobId: string): Promise<EngineActionResult> {
  const { data } = await client.post<EngineActionResult>(`/api/engine/download/${encodeURIComponent(jobId)}/cancel`)
  return data
}

/** 完整性校验（篡改检测，管理员） / Integrity verification (tamper detection, admin) */
export async function verifyModel(modelKey: string): Promise<EngineActionResult & { status?: string; mismatched?: string[]; missing?: string[] }> {
  const { data } = await client.post<EngineActionResult & { status?: string; mismatched?: string[]; missing?: string[] }>('/api/engine/verify', { model_key: modelKey })
  return data
}

/** 启动常驻引擎子进程（含完整性预检，篡改拒载，管理员） / Start resident engine subprocess (integrity precheck, tamper rejection, admin) */
export async function startEngine(): Promise<EngineActionResult> {
  const { data } = await client.post<EngineActionResult>('/api/engine/start')
  return data
}

/** 停止常驻引擎子进程（管理员） / Stop resident engine subprocess (admin) */
export async function stopEngine(): Promise<EngineActionResult> {
  const { data } = await client.post<EngineActionResult>('/api/engine/stop')
  return data
}

/** 配置模型存储位置（管理员） / Configure model storage directory (admin) */
export async function setEngineStorage(modelDir: string): Promise<EngineActionResult & { model_dir?: string; disk_free_bytes?: number }> {
  const { data } = await client.post<EngineActionResult & { model_dir?: string; disk_free_bytes?: number }>('/api/engine/storage', { model_dir: modelDir })
  return data
}
