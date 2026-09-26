/**
 * 接入方式 API — REQ-SETTINGS-IA（v0.2.0）契约层
 *
 * 新口径（取代 REQ-ACCESS-MODE-CARDS §13 契约）：
 * - 决策层：access_mode ∈ {'local'(离线), 'cloud'(联网)} | null（未选态触发强引导）
 * - 详情层：逐能力算力来源 capability_source.{llm,asr} ∈ trial | byok | local_endpoint(llm)
 *   配 capability_source_override.{llm,asr}（true = 显式覆盖持久化，不被登录/勾选改回）
 * - 写路径：切换决策卡走 POST /api/settings/access-mode（事务，失败全量回滚）；
 *   逐能力来源改选走 POST /api/settings { capability_source }（显式保存）
 * - 读路径：GET /api/settings/routing 返回路由结论 + capability + auto_switch 聚合
 *   （L1 行内/L2 横幅/L3 角标三级提示与事件记录的数据源）
 * 旧 mock 影子态与本地惰性推导分支随真接口上线整体废除。
 */
import client from './client'

/** 决策层接入方式（两卡：离线 / 联网） */
export type AccessMode = 'local' | 'cloud'

/** 逐能力算力来源（用户词五词中的三项 + 离线接管态） */
export type CapSource = 'trial' | 'byok' | 'local_endpoint' | 'local' | ''

/** 实际路由结论 */
export type RouteKind = 'local' | 'cloud' | 'proxy' | 'direct'

/** 明示自动改用 / 门槛原因枚举（界面文案禁用「降级」，用「自动改用」） */
export type RoutingReason =
  | '' | 'trial_requires_login' | 'trial_quota_exhausted'
  | 'trial_quota_exhausted_no_fallback' | 'byok_key_missing'
  | 'byok_key_missing_cloud_unavailable' | 'local_endpoint_misconfigured'
  | 'legacy_unconfigured'

export interface RouteDecision {
  configured_access_mode: AccessMode | null
  expert_mode: boolean
  route: RouteKind
  /** 该能力实际生效的算力来源 */
  source: CapSource
  /** true = 明示自动改用（取代旧 route_override 静默语义） */
  auto_switched: boolean
  /** 兼容窗口同值镜像（一个版本后随旧客户端日落删除） */
  route_override: boolean
  reason: RoutingReason | string
}

export interface CapabilityEntry {
  /** 用户显式选择值（未选过为空串） */
  explicit: string
  /** 是否已覆盖（三态徽章：override=true 已覆盖 / false 且非离线 默认生效或未设置） */
  override: boolean
  /** 账户默认值来源（prefer_subscription 开=trial / 关=byok） */
  default: string
  /** 生效值 */
  effective: CapSource
}

export interface CapabilityStatus {
  account_default: 'trial' | 'byok'
  llm: CapabilityEntry
  asr: CapabilityEntry
}

export interface RoutingQuota {
  allowed: boolean
  remaining: number | null
  quota: number | null
  used: number | null
  warning: string | null
}

/** 自动改用事件记录（core/settings_events.py 落盘，账单争议可查） */
export interface SettingsEvent {
  ts: string
  type: string
  capability?: string
  from_source?: string
  to_source?: string
  reason?: string
}

export interface RoutingResponse {
  ok: boolean
  access_mode: AccessMode | null
  expert_mode: boolean
  onboarding_required: boolean
  llm: RouteDecision
  asr: RouteDecision
  capability: CapabilityStatus
  quota: RoutingQuota | null
  /** 'low' = 剩余 ≤10 分钟预警（Q3 终裁阈值） */
  quota_warning: string | null
  auto_switch: {
    count: number
    capabilities: Array<'llm' | 'asr'>
    reasons: Record<string, string>
  }
  recent_events: SettingsEvent[]
}

/** 切换事务结果（裁决-1：任一环节失败 → settings.json 零写入，保持原模式） */
export interface SwitchAccessResult {
  ok: boolean
  access_mode?: AccessMode | null
  capability?: CapabilityStatus
  llm?: RouteDecision
  asr?: RouteDecision
  failed_stage?: 'validate' | 'engine_start' | 'engine_stop' | 'engine'
  error_code?: string | null
  error?: string
}

/**
 * 路由结论查询（决策卡 + 详情层 + 三级提示的唯一读源）。
 * 后端不可达时抛错，由调用方（stores/engine）保持上次结论并展示重试入口。
 */
export async function fetchRouting(): Promise<RoutingResponse> {
  const { data } = await client.get<RoutingResponse>('/api/settings/routing')
  if (!data || data.ok !== true) throw new Error('routing: unexpected payload')
  return data
}

/**
 * 接入方式切换事务（必经后果预览弹窗后调用；失败界面明示「未生效，已保持原模式」）。
 */
export async function switchAccessMode(payload: {
  access_mode: AccessMode | null
  capability_source?: Partial<Record<'llm' | 'asr', string>>
}): Promise<SwitchAccessResult> {
  const { data } = await client.post<SwitchAccessResult>('/api/settings/access-mode', payload)
  return data
}

/**
 * 逐能力算力来源显式保存（详情层来源下拉；任何手动改选后端都会标 override 持久化）。
 */
export async function saveCapabilitySource(sources: Partial<Record<'llm' | 'asr', string>>): Promise<void> {
  await client.post('/api/settings', { capability_source: sources })
}

/** 专家模式开关（页面级，不参与决策卡 radiogroup；写入仍走 /api/settings） */
export async function saveExpertMode(on: boolean): Promise<void> {
  await client.post('/api/settings', { expert_mode: on })
}
