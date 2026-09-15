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
}

export interface Settings {
  asr?: {
    /** 接入模式：proxy（代理）/ direct（直连） / Access mode: proxy / direct */
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
  voiceprint?: {
    provider?: string
    cloud_base_url?: string
    cloud_api_key?: string
    cloud_api_key_set?: boolean
  }
  diarization?: {
    subscription_tier?: string
    local_diarization?: boolean
    effective?: string
    can_toggle?: boolean
  }
  output_dir?: string
  disabled_commands?: string[]
  feature_flags?: Partial<FeatureFlags>
  /** 优先使用订阅流量 / Prefer subscription quota */
  prefer_subscription?: boolean
  /** 存储管理配置 / Storage management config */
  storage?: {
    auto_clean_intermediate?: boolean
    auto_archive_days?: number
  }
  /** 当前激活的 AI 助手角色名 / Currently active AI assistant role name */
  active_agent?: string
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
