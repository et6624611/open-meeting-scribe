/**
 * 接入方式 API — REQ-ACCESS-MODE-CARDS / AM-B1 契约（docs/API_CONTRACTS.md §13）
 *
 * mock 先行策略（参照 DC-DEC-F1 惯例，联调零代码切换）：
 * - 读：优先 GET /api/settings/routing（AM-B1 真接口）。404/异常（后端未合入）时
 *   走本地推导：localStorage 显式选择 > §13.2 旧字段惰性映射，quota 取 /api/usage/summary。
 * - 写：POST /api/settings 携带 access_mode/expert_mode + §13.4 旧字段同步（main 后端
 *   白名单合并，未知字段静默忽略，不报错）；同时落 localStorage 作为 mock 影子态。
 * - AM-B1 合入后真接口恒 200，mock 分支自然失效，无需改任何调用方代码。
 */
import client from './client'
import { fetchSettings, saveSettings, type Settings } from './settings'
import { fetchUsageSummary } from './usage'

/** 用户侧统一接入方式（需求书 §3） / User-facing access mode */
export type AccessMode = 'local' | 'hosted' | 'byok'

/** 实际路由结论（契约 §13.5 route 枚举） / Effective route */
export type RouteKind = 'local' | 'cloud' | 'proxy' | 'direct'

/** route_override 原因枚举（契约 §13.5） */
export type RouteOverrideReason =
  | '' | 'prefer_subscription' | 'byok_key_missing'
  | 'byok_key_missing_cloud_unavailable' | 'legacy_unconfigured'

export interface RouteDecision {
  configured_access_mode: AccessMode | null
  expert_mode: boolean
  route: RouteKind
  route_override: boolean
  reason: RouteOverrideReason
}

export interface RoutingQuota {
  allowed: boolean
  remaining: number | null
  quota: number | null
  used: number | null
  warning: string | null
}

export interface RoutingResponse {
  ok: boolean
  access_mode: AccessMode | null
  expert_mode: boolean
  onboarding_required: boolean
  llm: RouteDecision
  asr: RouteDecision
  quota: RoutingQuota | null
}

/** mock 影子态存储键 / Shadow-state key for the pre-integration mock */
const MOCK_STATE_KEY = 'oms_access_mode'

interface MockState {
  access_mode: AccessMode | null
  expert_mode: boolean
  /** 用户是否显式选过卡片（区分惰性推导） / Whether the user explicitly picked a card */
  chosen: boolean
}

function readMockState(): MockState | null {
  try {
    const raw = localStorage.getItem(MOCK_STATE_KEY)
    if (!raw) return null
    const v = JSON.parse(raw) as Partial<MockState>
    const mode = v.access_mode
    if (mode !== null && mode !== 'local' && mode !== 'hosted' && mode !== 'byok') return null
    return { access_mode: mode ?? null, expert_mode: !!v.expert_mode, chosen: !!v.chosen }
  } catch {
    return null
  }
}

function writeMockState(patch: Partial<Pick<MockState, 'access_mode' | 'expert_mode'>>, markChosen = false): void {
  const cur = readMockState() ?? { access_mode: null, expert_mode: false, chosen: false }
  const next: MockState = { ...cur, ...patch }
  if (markChosen && patch.access_mode !== undefined) next.chosen = true
  try {
    localStorage.setItem(MOCK_STATE_KEY, JSON.stringify(next))
  } catch {
    // 隐私模式写失败仅影响 dev 影子态 / Storage disabled: only affects dev shadow state
  }
}

const DEFAULT_LLM_BASE_URLS = new Set([
  '', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'https://api.openai.com/v1',
  'https://api.deepseek.com/v1', 'https://api.moonshot.cn/v1', 'https://api.lingyiwanwu.com/v1',
])

function isLocalhostUrl(url?: string): boolean {
  if (!url) return false
  return /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/i.test(url)
}

/**
 * §13.2 旧字段惰性迁移映射（与后端 run_access_mode_migration 同表）
 * Lazy legacy derivation mirroring the §13.2 migration table.
 */
function deriveLegacyAccess(s: Settings): AccessMode | null {
  const engineMode = (s.engine?.mode || '') as string
  const prefer = !!s.prefer_subscription
  if (engineMode === 'local') return 'local'
  if (engineMode === 'proxy' || engineMode === 'cloud') return 'hosted'
  if (engineMode === 'direct') return prefer ? 'hosted' : 'byok'
  // engine.mode 未落盘时按 llm/asr 组合推导；完全未配置 → null（触发引导）
  if (isLocalhostUrl(s.llm?.base_url) && !s.llm?.api_key_set) return 'local'
  return null
}

/**
 * §4 自动专家规则：存量含自定义 base_url/model 覆盖或非默认 Key 组合 → expert_mode=true
 * Auto-expert for custom overrides so card flow never swallows advanced configs.
 */
function deriveLegacyExpert(s: Settings): boolean {
  const llmBase = s.llm?.base_url || ''
  if (llmBase && !DEFAULT_LLM_BASE_URLS.has(llmBase)) return true
  if (s.asr?.mode === 'direct' && s.asr?.base_url && s.asr.base_url !== 'https://dashscope.aliyuncs.com') return true
  if (s.voiceprint?.provider && s.voiceprint.provider !== 'auto') return true
  return false
}

function decision(
  mode: AccessMode | null, expert: boolean, route: RouteKind,
  override = false, reason: RouteOverrideReason = '',
): RouteDecision {
  return { configured_access_mode: mode, expert_mode: expert, route, route_override: override, reason }
}

/** mock 态路由推导（后端未合入时的本地等价实现） / Local equivalent of get_routing_decision for the mock window */
function deriveRouting(s: Settings, isLoggedIn: boolean, quota: RoutingQuota | null): RoutingResponse {
  const mock = readMockState()
  const accessMode = mock?.chosen ? mock.access_mode : (mock?.access_mode ?? deriveLegacyAccess(s))
  const expertMode = mock ? mock.expert_mode : deriveLegacyExpert(s)
  const prefer = !!s.prefer_subscription

  let llm: RouteDecision
  let asr: RouteDecision
  if (accessMode === 'local') {
    llm = decision('local', expertMode, 'local')
    asr = decision('local', expertMode, 'local')
  } else if (accessMode === 'hosted') {
    llm = decision('hosted', expertMode, 'cloud')
    asr = decision('hosted', expertMode, 'proxy')
  } else if (accessMode === 'byok') {
    const llmKeyOk = !!s.llm?.api_key_set || isLocalhostUrl(s.llm?.base_url)
    const asrKeyOk = !!s.asr?.api_key_set
    if (prefer && isLoggedIn && (quota?.remaining ?? 0) > 0) {
      // D2：byok 开订阅优先 → 实际走云代理消耗配额，route_override 显性告知 / byok + prefer_subscription → cloud
      llm = decision('byok', expertMode, 'cloud', true, 'prefer_subscription')
      asr = decision('byok', expertMode, 'proxy', true, 'prefer_subscription')
    } else if (llmKeyOk && asrKeyOk) {
      llm = decision('byok', expertMode, isLocalhostUrl(s.llm?.base_url) ? 'local' : 'direct')
      asr = decision('byok', expertMode, 'direct')
    } else {
      llm = decision('byok', expertMode, 'cloud', true, 'byok_key_missing')
      asr = decision('byok', expertMode, 'proxy', true, 'byok_key_missing')
    }
  } else {
    const legacyRoute: RouteKind = isLocalhostUrl(s.llm?.base_url) ? 'local' : (s.engine?.mode === 'direct' ? 'direct' : 'proxy')
    llm = decision(null, expertMode, legacyRoute, false, 'legacy_unconfigured')
    asr = decision(null, expertMode, legacyRoute === 'direct' ? 'direct' : 'proxy', false, 'legacy_unconfigured')
  }
  return {
    ok: true,
    access_mode: accessMode,
    expert_mode: expertMode,
    onboarding_required: accessMode === null,
    llm, asr,
    // local 恒不计量（契约 §13.5 quota 口径） / local is never metered
    quota: accessMode === 'local' ? null : quota,
  }
}

/**
 * 路由结论查询（契约 §13.5；mock 先行 + 真接口优先）
 * Fetch the routing decision; real endpoint wins, local derivation is the pre-merge fallback.
 */
export async function fetchRouting(isLoggedIn: boolean): Promise<RoutingResponse> {
  try {
    const { data } = await client.get<RoutingResponse>('/api/settings/routing')
    if (data && data.ok === true && typeof data.access_mode !== 'undefined') {
      // 真接口可达后清除影子态，避免过期 mock 值干扰 / Real endpoint live: drop shadow state
      localStorage.removeItem(MOCK_STATE_KEY)
      return data
    }
    throw new Error('routing: unexpected payload')
  } catch {
    // AM-B1 未合入：本地推导兜底 / Pre-merge fallback: derive locally
  }
  let settings: Settings = {}
  let quota: RoutingQuota | null = null
  try {
    settings = await fetchSettings()
  } catch { /* 静默：按未配置推导 */ }
  if (isLoggedIn) {
    try {
      const u = await fetchUsageSummary()
      if (u.metered) {
        quota = { allowed: true, remaining: u.remaining ?? null, quota: u.quota ?? null, used: u.used ?? null, warning: null }
      }
    } catch { /* 额度不可得时按 null */ }
  }
  return deriveRouting(settings, isLoggedIn, quota)
}

/** §13.4 写路径旧字段同步映射（A2 兼容窗口，双写保回退） / Legacy field sync on access_mode writes */
function legacySync(mode: AccessMode | null): Partial<Settings> {
  if (mode === 'local') return { engine: { mode: 'local' } }
  if (mode === 'hosted') return { engine: { mode: 'proxy' }, asr: { mode: 'proxy' } }
  if (mode === 'byok') return { engine: { mode: 'direct' }, asr: { mode: 'direct' } }
  return {}
}

/**
 * 保存接入方式 / 专家模式（契约 §13.4）。main 后端会静默忽略新字段，
 * 旧字段同步照常生效；AM-B1 合入后新字段由后端接管。
 */
export async function saveAccess(patch: { access_mode?: AccessMode | null; expert_mode?: boolean }): Promise<void> {
  const body: Partial<Settings> & Record<string, unknown> = { ...patch }
  if (patch.access_mode !== undefined) Object.assign(body, legacySync(patch.access_mode))
  await saveSettings(body as Partial<Settings>)
  writeMockState(patch, patch.access_mode !== undefined)
}
