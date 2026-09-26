/**
 * 设置 API 封装 / Settings API wrapper
 */
import client from './client'

export interface FeatureFlags {
  realtime_chapters: boolean
  realtime_summary: boolean
  realtime_summary_interval: number
  update_check: boolean
  voiceprint_auto_match: boolean
}

/** LLM 提供商预设 / LLM provider preset */
export interface ProviderPreset {
  name: string
  base_url: string
  models: string[]
  /** 本地端点 Key 可留空（R4） / Key optional for local endpoints */
  key_optional?: boolean
  /** 是否本机端点（localhost/127.0.0.1） / Whether this is a localhost endpoint */
  localhost?: boolean
}

/** 单个本地引擎探测结果 / One local-engine probe result */
export interface LocalEngineProbe {
  key: string
  name: string
  base_url: string
  install_url: string
  reachable: boolean
  models: string[]
  model_count: number
  /** unreachable / timeout / http_error / invalid_response / ''（可达且正常） */
  error_code: string
}

/** 本地引擎探测响应 / Local-engine probe response */
export interface LocalEngineProbeResult {
  ok: boolean
  probed_at: number
  timeout_seconds: number
  engines: LocalEngineProbe[]
  detected: string[]
}

export interface Settings {
  asr?: {
    /** 接入模式（A2 投影旧字段；唯一写入口在接入方式详情层） / Legacy projection field */
    mode?: 'proxy' | 'direct'
    provider?: string
    base_url?: string
    api_key?: string
    api_key_set?: boolean
    model?: string
    /** 代理模式下由服务器持有，前端仅展示 / Held by server in proxy mode; frontend displays only */
    api_key_managed_by_proxy?: boolean
    proxy_url?: string
  }
  llm?: {
    provider?: string
    base_url?: string
    api_key?: string
    api_key_set?: boolean
    model?: string
  }
  // voiceprint 配置面已随 REQ-SETTINGS-IA 第 4 刀下架：声纹仅本机 CAM++，无字段可配
  diarization?: {
    subscription_tier?: string
    local_diarization?: boolean
    effective?: string
    can_toggle?: boolean
  }
  output_dir?: string
  disabled_commands?: string[]
  feature_flags?: Partial<FeatureFlags>
  /** 优先使用体验配额（详情默认值来源） / Prefer trial quota (capability default source) */
  prefer_subscription?: boolean
  /** 接入方式决策层（离线/联网/null 未选态）/ Access mode decision layer */
  access_mode?: 'local' | 'cloud' | null
  /** 专家详情开关（页面级，与 access_mode 正交）/ Expert detail toggle */
  expert_mode?: boolean
  /** 逐能力算力来源快照 / Per-capability compute source snapshot */
  capability?: import('./access').CapabilityStatus
  /** 存储管理配置 / Storage management config */
  storage?: {
    auto_clean_intermediate?: boolean
    auto_archive_days?: number
  }
  /** 当前激活的 AI 助手角色名 / Currently active AI assistant role name */
  active_agent?: string
  /**
   * 计算引擎配置（PRD-LOCAL-ENGINE §9，R6 徽章双因子之一）。
   * Compute engine config (PRD-LOCAL-ENGINE §9; factor 1 of the R6 badge).
   * TODO(WP-B 联调 / integration): 后端 settings.engine 契约落地前为占位字段。
   */
  engine?: {
    mode?: 'cloud' | 'proxy' | 'direct' | 'local'
    local?: {
      /** 本地引擎目录存在且模型就绪 / Local engine directory exists and models ready */
      ready?: boolean
      model_dir?: string
    }
  }
  /** 后端返回的 LLM Provider 预设列表 / LLM provider presets returned by backend */
  llm_provider_presets?: ProviderPreset[]
  [key: string]: unknown
}

export async function fetchSettings(): Promise<Settings> {
  const { data } = await client.get<Settings>('/api/settings')
  return data
}

export async function saveSettings(settings: Partial<Settings>): Promise<void> {
  await client.post('/api/settings', settings)
}

export async function testApiConnection(params?: { service_type?: string; asr?: Record<string, unknown>; llm?: Record<string, unknown> }): Promise<{ success: boolean; message?: string; ok?: boolean; error?: string }> {
  const { data } = await client.post<{ success: boolean; message?: string; ok?: boolean; error?: string }>('/api/settings/test', params || {})
  return data
}

export async function fetchModels(): Promise<{ asr: string[]; llm: string[] }> {
  const { data } = await client.get('/api/models')
  return data
}

/**
 * 探测本机 Ollama / LM Studio（仅 localhost，超时 ≤2s）。
 * Probe local Ollama / LM Studio (localhost only, ≤2s timeout).
 */
export async function probeLocalEngine(): Promise<LocalEngineProbeResult> {
  const { data } = await client.get<LocalEngineProbeResult>('/api/settings/probe-local-engine')
  return data
}

/** 系统提示词条目 / System prompt item */
export interface SystemPromptItem {
  module: string
  description: string
  prompt: string
}

/** 获取系统提示词列表（只读） / Fetch system prompts (read-only) */
export async function fetchSystemPrompts(): Promise<Record<string, SystemPromptItem>> {
  const { data } = await client.get<Record<string, SystemPromptItem>>('/api/system-prompts')
  return data
}

/** 获取 CLI 命令参考 / Fetch CLI command reference */
export async function fetchCliReference(): Promise<Record<string, unknown>> {
  const { data } = await client.get<Record<string, unknown>>('/api/cli-reference')
  return data
}

/** CLI 引擎探针结论（三段：路径解析 → 版本下限 → 登录态） / CLI engine probe verdict */
export interface ChatEngineProbe {
  available: boolean
  reason?: string
  display_name?: string
  hint?: string
  path?: string | null
  version?: string | null
  logged_in?: boolean
  /** 失败段定位（EXPERT-MODE 三段探针回显）：null=全通过 */
  failed_stage?: 'path' | 'version' | 'login' | null
}

/** 智能体引擎配置 + 探针状态（详情层 CLI 卡与对话面板前置回显共用） */
export interface ChatEngineStatus {
  ok: boolean
  config: {
    enabled: boolean
    engine_id: string
    model?: string | null
    auth_tier: string
    session_persistence?: boolean
    retention_days?: number
    cli_path_override?: string | null
  }
  probe: ChatEngineProbe
}

export async function fetchChatEngineStatus(): Promise<ChatEngineStatus> {
  const { data } = await client.get<ChatEngineStatus>('/api/settings/chat-engine')
  return data
}
