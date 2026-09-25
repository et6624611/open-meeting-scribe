/**
 * 计算引擎状态 store / Compute engine status store
 *
 * R6：顶栏徽章四态 = 本地引擎 / 体验代理 / 自持 Key / 未就绪（双因子：engine.mode + 模型就绪）。
 * R5（WP-F）：模型清单/下载任务/存储信息 + 下载中轮询；下载完成即时刷新徽章与引擎状态。
 * R6: four-state badge (two factors). R5 (WP-F): model manifest, download jobs, storage,
 * polling while downloading; badge and engine status refresh as soon as downloads settle.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  fetchEngineStatus, fetchEngineModels,
  startModelDownload, cancelModelDownload, verifyModel,
  startEngine, stopEngine, setEngineStorage,
  type EngineStatus, type EngineMode, type EngineModelsOverview, type DownloadJob, type EngineActionResult,
} from '@/api/engine'
import { fetchRouting, saveAccess, type AccessMode, type RoutingResponse } from '@/api/access'
import { fetchSettings, type Settings } from '@/api/settings'

/** 徽章四态 / Four badge states */
export type EngineBadgeState = 'local' | 'proxy' | 'selfkey' | 'unready'

/**
 * 状态栏单一结论态（REQ-ACCESS-MODE-CARDS T5 / AC-T5①）。
 * 主文案 = 结论(+原因/剩余量)，模型串与延迟降级到 hover（statusDetail）。
 * Single-source status-bar conclusion; model string & latency move to hover.
 */
export type AccessStatusState =
  | 'local_ready'      // 离线就绪
  | 'local_pending'    // 离线未就绪（本地模型未装齐）
  | 'hosted_ready'     // 托管就绪（剩余 n）
  | 'hosted_needs_login' // 还需登录
  | 'byok_ready'       // 自带 Key 就绪
  | 'byok_needs_key'   // 还需配置 Key
  | 'unconfigured'     // 未配置（触发引导）

/** 下载进行中的任务状态 / Job states that count as in-flight */
const ACTIVE_JOB_STATES = ['pending', 'downloading', 'verifying']
const POLL_INTERVAL_MS = 2000

/**
 * dev 模式手工覆盖（验证用）：localStorage.oms_engine_badge ∈ local|proxy|selfkey|unready。
 * Dev-only manual override for verification: localStorage.oms_engine_badge.
 */
const DEV_OVERRIDE_KEY = 'oms_engine_badge'

function readDevOverride(): EngineBadgeState | null {
  if (!import.meta.env.DEV) return null
  const v = localStorage.getItem(DEV_OVERRIDE_KEY)
  return v === 'local' || v === 'proxy' || v === 'selfkey' || v === 'unready' ? v : null
}

/** 识别本地 LLM 运行时名（Ollama / LM Studio）；原 App.vue DEF-FE-05 逻辑收敛至此 */
function detectLocalLlmRuntime(llm: Record<string, any>): string {
  const provider = String(llm?.provider || '').toLowerCase()
  const baseUrl = String(llm?.base_url || '')
  if (provider.includes('ollama') || baseUrl.includes(':11434')) return 'Ollama'
  if (provider.includes('lm studio') || provider.includes('lmstudio') || baseUrl.includes(':1234')) return 'LM Studio'
  return ''
}

export const useEngineStore = defineStore('engine', () => {
  const status = ref<EngineStatus | null>(null)
  const loading = ref(false)
  const loaded = ref(false)
  const devOverride = ref<EngineBadgeState | null>(readDevOverride())

  // ─── 接入方式单一来源（AM-F1 T5 收敛） / Access-mode single source of truth ───
  const routing = ref<RoutingResponse | null>(null)
  const routingLoading = ref(false)
  /** 状态栏 hover 详情所需的原始设置快照（模型串），不驱动表单 / Snapshot for the hover detail only */
  const accessSettings = ref<Settings | null>(null)

  const accessMode = computed<AccessMode | null>(() => routing.value?.access_mode ?? null)
  const expertMode = computed(() => routing.value?.expert_mode === true)
  const onboardingRequired = computed(() => routing.value?.onboarding_required === true)

  /**
   * 双因子徽章态；合入 access_mode 后以接入方式为第一因子（契约 §13.5 单源判定），
   * routing 未就绪时回退旧 engine.mode 推导。
   * Badge state; access_mode is the primary factor once routing is loaded.
   */
  const badge = computed<EngineBadgeState>(() => {
    if (devOverride.value) return devOverride.value
    const mode = routing.value?.access_mode
    if (mode === 'local') return status.value?.local_ready ? 'local' : 'unready'
    if (mode === 'hosted') return 'proxy'
    if (mode === 'byok') return 'selfkey'
    const s = status.value
    if (!s) return 'unready'
    if (s.mode === 'local') return s.local_ready ? 'local' : 'unready'
    if (s.mode === 'direct') return 'selfkey'
    // cloud / proxy 均为项目方共享代理链路（体验代理） / cloud & proxy both route through the shared trial proxy
    return 'proxy'
  })

  /** 状态栏主结论 / Status-bar conclusion (AC-T5①) */
  const statusState = computed<AccessStatusState>(() => {
    const r = routing.value
    if (!r) return 'unconfigured'
    switch (r.access_mode) {
      case 'local':
        return status.value?.local_ready ? 'local_ready' : 'local_pending'
      case 'hosted':
        return userLoggedIn.value ? 'hosted_ready' : 'hosted_needs_login'
      case 'byok':
        // 无 Key 被回退云代理（byok_key_missing）不算就绪 / missing key falling back is not "ready"
        return r.llm.reason === 'byok_key_missing' ? 'byok_needs_key' : 'byok_ready'
      default:
        return 'unconfigured'
    }
  })

  /** 登录态由 App 启动注入（store 不直接依赖 user store，避免环形引用） / Login flag injected by the app shell */
  const userLoggedIn = ref(false)
  function setUserLoggedIn(v: boolean) {
    userLoggedIn.value = v
    if (loaded.value) void loadRouting(true)
  }

  /** hover/详情文本：模型串（本地模式绝不泄露云模型名，沿 AC-T6③ 约束） / Hover detail: model string */
  const statusDetail = computed(() => {
    const s = accessSettings.value
    if (!s) return ''
    if (accessMode.value === 'local') {
      const llm = s.llm as Record<string, any> | undefined
      const runtime = detectLocalLlmRuntime(llm || {})
      const model = llm?.model || '本地模型'
      return `ASR: FunASR 本地模型 · LLM: ${runtime ? `${runtime} + ${model}` : model}`
    }
    const asrModel = (s.asr as Record<string, any> | undefined)?.model || '—'
    const llmModel = (s.llm as Record<string, any> | undefined)?.model || '—'
    return `ASR: ${asrModel} · LLM: ${llmModel}`
  })

  /** 托管剩余量（供「托管就绪（剩余 n）」插值） / Remaining quota for the hosted label */
  const quotaRemaining = computed<number | null>(() => routing.value?.quota?.remaining ?? null)

  /** 跨模式路由是否偏离（D2 toast 判定的数据源） / Route override flag (D2 toast source) */
  const routeOverride = computed(() => {
    const r = routing.value
    if (!r) return null
    if (r.llm.route_override) return r.llm.reason
    if (r.asr.route_override) return r.asr.reason
    return null
  })

  async function loadRouting(force = false) {
    if (routingLoading.value || (routing.value && !force)) return
    routingLoading.value = true
    try {
      routing.value = await fetchRouting(userLoggedIn.value)
    } catch (e) {
      console.error('[engine] load routing failed:', e)
    } finally {
      routingLoading.value = false
    }
  }

  async function loadAccessSettings() {
    try {
      accessSettings.value = await fetchSettings()
    } catch {
      /* 静默：仅影响 hover 详情 */
    }
  }

  /** 切换接入方式 / 专家模式并刷新派生态（乐观本地 → 后端权威回读） */
  async function applyAccess(patch: { access_mode?: AccessMode | null; expert_mode?: boolean }) {
    await saveAccess(patch)
    if (patch.access_mode !== undefined) {
      routing.value = routing.value
        ? { ...routing.value, access_mode: patch.access_mode, onboarding_required: patch.access_mode === null }
        : routing.value
    }
    if (patch.expert_mode !== undefined) {
      routing.value = routing.value
        ? { ...routing.value, expert_mode: patch.expert_mode }
        : routing.value
    }
    await Promise.all([loadRouting(true), load(true), loadAccessSettings()].map(p => p.catch(() => undefined)))
  }

  // ─── R5 模型资产面 / R5 model asset surface ───
  const overview = ref<EngineModelsOverview | null>(null)
  const overviewLoading = ref(false)
  let pollTimer: ReturnType<typeof setInterval> | null = null

  const jobs = computed<DownloadJob[]>(() => overview.value?.downloads ?? [])
  /**
   * 是否可操作变更面（下载/引擎启停/存储/模式切换）。
   * 两来源任一成立即可：后端状态接口的 can_manage（本地单机模式或管理员 cookie），
   * 或登录用户 role==='admin'。与后端 require_admin_or_local 判定对齐。
   */
  const canManage = computed(() => status.value?.can_manage === true)
  const activeJobs = computed(() => jobs.value.filter(j => ACTIVE_JOB_STATES.includes(j.state)))
  const isDownloading = computed(() => activeJobs.value.length > 0)
  /** 必装模型中未就绪者（启用本地引擎的前置条件） / Required models not ready (precondition for local engine) */
  const requiredNotReady = computed(() =>
    (overview.value?.models ?? []).filter(m => !m.optional && m.status !== 'ready'))
  const tamperedModels = computed(() =>
    (overview.value?.models ?? []).filter(m => m.status === 'tampered'))

  async function load(force = false) {
    if (loading.value || (loaded.value && !force)) return
    loading.value = true
    try {
      status.value = await fetchEngineStatus()
      loaded.value = true
    } catch (e) {
      console.error('[engine] load status failed:', e)
      status.value = null
    } finally {
      loading.value = false
    }
  }

  async function loadOverview(force = false) {
    if (overviewLoading.value || (overview.value && !force)) return
    overviewLoading.value = true
    try {
      overview.value = await fetchEngineModels()
      syncPolling()
    } catch (e) {
      console.error('[engine] load models overview failed:', e)
    } finally {
      overviewLoading.value = false
    }
  }

  /** 有活动下载时轮询； settled 后刷新徽章与引擎状态 / Poll while downloads are in flight; refresh badge/status once settled */
  function syncPolling() {
    const active = activeJobs.value.length > 0
    if (active && !pollTimer) {
      pollTimer = setInterval(async () => {
        try {
          const before = activeJobs.value.length
          overview.value = await fetchEngineModels()
          if (before > 0 && activeJobs.value.length === 0) await onDownloadsSettled()
        } catch (e) {
          console.error('[engine] poll downloads failed:', e)
        }
      }, POLL_INTERVAL_MS)
    } else if (!active && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  /** 下载收尾：刷新引擎状态（徽章即时联动） / Downloads settled: refresh engine status (badge linkage) */
  async function onDownloadsSettled() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
    await load(true)
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }

  // ─── 变更面（管理员，D-R2；后端 require_admin 兜底） / Mutations (admin, D-R2; enforced backend-side) ───
  async function download(modelKey: string): Promise<EngineActionResult> {
    const result = await startModelDownload(modelKey)
    if (result.ok) await loadOverview(true)
    return result
  }

  async function cancel(jobId: string): Promise<EngineActionResult> {
    const result = await cancelModelDownload(jobId)
    if (result.ok) await loadOverview(true)
    return result
  }

  async function verify(modelKey: string): Promise<EngineActionResult> {
    const result = await verifyModel(modelKey)
    await loadOverview(true)
    return result
  }

  async function start(): Promise<EngineActionResult> {
    const result = await startEngine()
    await load(true)
    return result
  }

  async function stop(): Promise<EngineActionResult> {
    const result = await stopEngine()
    await load(true)
    return result
  }

  async function saveStorage(modelDir: string): Promise<EngineActionResult> {
    const result = await setEngineStorage(modelDir)
    if (result.ok) await loadOverview(true)
    return result
  }

  /** 设置引擎模式（管理员，D-R2）后本地同步并回读路由（专家改旧字段 → access_mode 重对齐，§13.4 兼容窗口） */
  function applyMode(mode: EngineMode) {
    status.value = {
      mode,
      local_ready: status.value?.local_ready ?? false,
      process_running: status.value?.process_running ?? false,
      pid: status.value?.pid ?? null,
      missing_models: status.value?.missing_models ?? [],
      tampered_models: status.value?.tampered_models ?? [],
      can_manage: status.value?.can_manage ?? false,
      source: status.value?.source ?? 'settings',
    }
    void loadRouting(true)
  }

  /** dev 验证用：手工切换徽章态（传 null 恢复真实判定） / Dev verification: override badge state (null restores real derivation) */
  function setDevOverride(state: EngineBadgeState | null) {
    if (!import.meta.env.DEV) return
    devOverride.value = state
    if (state) localStorage.setItem(DEV_OVERRIDE_KEY, state)
    else localStorage.removeItem(DEV_OVERRIDE_KEY)
  }

  return {
    status, loading, loaded, badge, devOverride, load, applyMode, setDevOverride, canManage,
    overview, overviewLoading, jobs, activeJobs, isDownloading, requiredNotReady, tamperedModels,
    loadOverview, stopPolling, download, cancel, verify, start, stop, saveStorage,
    // 接入方式（AM-F1） / Access mode (AM-F1)
    routing, accessSettings, accessMode, expertMode, onboardingRequired, statusState, statusDetail,
    quotaRemaining, routeOverride, loadRouting, loadAccessSettings, applyAccess, setUserLoggedIn,
  }
})
