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
import { fetchRouting, saveExpertMode, saveAutoFallback, saveCapabilitySource, type CapabilityStatus, type RoutingResponse } from '@/api/access'
import { fetchSettings, type Settings } from '@/api/settings'

/**
 * 状态栏单一结论态（REQ-SETTINGS-IA §3.1/§3.5 改版，单源判定同 core/routing）。
 * 主文案 = 结论(+原因/剩余量)，模型串与延迟降级到 hover（statusDetail）。
 */
export type AccessStatusState =
  | 'local_ready'        // 离线就绪
  | 'local_pending'      // 离线未就绪（本地模型未装齐）
  | 'cloud_ready'        // 联网就绪（体验配额有额度 / 自带 Key 就绪）
  | 'cloud_needs_login'  // 体验配额需登录（登录门槛前置明示）
  | 'cloud_needs_key'    // 自带 Key 未配置且无可用替代
  | 'cloud_auto_switched' // 已自动改用（L1-L3 三级提示同源；界面禁用「降级」词）
  | 'unconfigured'       // 未选态（强引导）

/** 下载进行中的任务状态 / Job states that count as in-flight */
const ACTIVE_JOB_STATES = ['pending', 'downloading', 'verifying']
const POLL_INTERVAL_MS = 2000

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

  // ─── 接入方式单一来源（AM-F1 T5 收敛） / Access-mode single source of truth ───
  const routing = ref<RoutingResponse | null>(null)
  const routingLoading = ref(false)
  /** 状态栏 hover 详情所需的原始设置快照（模型串），不驱动表单 / Snapshot for the hover detail only */
  const accessSettings = ref<Settings | null>(null)

  const expertMode = computed(() => routing.value?.expert_mode === true)
  /** 逐能力自动改用同意（后端缺省 false；不静默替用户花钱） */
  const autoFallback = computed<{ llm: boolean; asr: boolean }>(() => ({
    llm: routing.value?.auto_fallback?.llm ?? false,
    asr: routing.value?.auto_fallback?.asr ?? false,
  }))
  /** 逐能力算力来源快照（详情层三态徽章/联动单源） */
  const capability = computed<CapabilityStatus | null>(() => routing.value?.capability ?? null)
  /** 明示自动改用聚合（L2 横幅 / L3 联网卡角标单源） */
  const autoSwitch = computed(() => routing.value?.auto_switch ?? { count: 0, capabilities: [], reasons: {} })

  /** 状态栏主结论（逐能力派生，不再有全局 access_mode） */
  const statusState = computed<AccessStatusState>(() => {
    const r = routing.value
    if (!r) return 'unconfigured'
    // 任一能力未设置 → 待配置引导
    if (r.llm.unconfigured || r.asr.unconfigured) return 'unconfigured'
    const llmLocal = r.llm.source === 'local_endpoint'
    const asrLocal = r.asr.source === 'local'
    // 两能力均落本机 → 本机结论（引擎未就绪则 pending）
    if (llmLocal && asrLocal) return status.value?.local_ready ? 'local_ready' : 'local_pending'
    if (asrLocal && !status.value?.local_ready) return 'local_pending'
    if (autoSwitch.value.count > 0) return 'cloud_auto_switched'
    const reasons = [r.llm.reason, r.asr.reason]
    if (reasons.includes('trial_requires_login')) return 'cloud_needs_login'
    if (reasons.includes('byok_key_missing_cloud_unavailable')) return 'cloud_needs_key'
    return 'cloud_ready'
  })

  /**
   * 会话级对话模型选择（REQ-EXPERT-MODE §2.3）：'' = 跟随详情。
   * 单一共享态：对话面板选择器与接入方式页「使用面回显」卡双向联动。
   */
  const sessionModel = ref(localStorage.getItem('oms_chat_model') || '')
  function setSessionModel(v: string) {
    sessionModel.value = v || ''
    try {
      if (sessionModel.value) localStorage.setItem('oms_chat_model', sessionModel.value)
      else localStorage.removeItem('oms_chat_model')
    } catch { /* 隐私模式写失败仅影响持久 */ }
  }

  /** hover/详情文本：逐能力模型串（本机来源不泄露云模型名） */
  const statusDetail = computed(() => {
    const s = accessSettings.value
    const r = routing.value
    if (!s) return ''
    const asrLocal = r?.asr.source === 'local'
    const llmLocal = r?.llm.source === 'local_endpoint'
    const asrModel = asrLocal ? 'FunASR 本地' : ((s.asr as Record<string, any> | undefined)?.model || '—')
    const llm = s.llm as Record<string, any> | undefined
    const runtime = detectLocalLlmRuntime(llm || {})
    const llmModel = llmLocal
      ? (runtime ? `${runtime} + ${llm?.model || '本地模型'}` : (llm?.model || '本地模型'))
      : (llm?.model || '—')
    return `ASR: ${asrModel} · LLM: ${llmModel}`
  })

  /** 托管剩余量（供「联网就绪（剩余 n）」插值） / Remaining quota for the cloud-ready label */
  const quotaRemaining = computed<number | null>(() => routing.value?.quota?.remaining ?? null)

  /** 明示自动改用原因（兜底 toast 判定的数据源；主路径为 L1-L3 常驻提示） */
  const routeOverride = computed(() => {
    const r = routing.value
    if (!r) return null
    if (r.llm.auto_switched) return r.llm.reason
    if (r.asr.auto_switched) return r.asr.reason
    return null
  })

  async function loadRouting(force = false) {
    if (routingLoading.value || (routing.value && !force)) return
    routingLoading.value = true
    try {
      routing.value = await fetchRouting()
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

  /**
   * 逐能力算力来源切换事务（必经 /api/settings/capability；失败全量回滚）。
   * ASR 进入/离开 local 时后端会启停本机引擎；失败抛错且不动本地态。
   */
  async function applyCapabilitySource(sources: Partial<Record<'llm' | 'asr', string>>) {
    const res = await saveCapabilitySource(sources)
    if (!res.ok) {
      const err: Error & { failedStage?: string; errorCode?: string | null } = new Error(res.error || 'switch failed')
      err.failedStage = res.failed_stage
      err.errorCode = res.error_code ?? null
      throw err
    }
    await Promise.all([loadRouting(true), load(true), loadAccessSettings()].map(p => p.catch(() => undefined)))
    return res
  }

  /** 专家详情开关（页面级 switch，与 access_mode 正交；失败抛错由调用方回滚 UI 态） */
  async function applyExpertMode(on: boolean) {
    await saveExpertMode(on)
    routing.value = routing.value ? { ...routing.value, expert_mode: on } : routing.value
    await loadRouting(true)
  }

  /** 自动改用同意开关（逐能力；失败抛错由调用方回滚 UI 态） */
  async function applyAutoFallback(cap: 'llm' | 'asr', on: boolean) {
    await saveAutoFallback({ [cap]: on })
    await loadRouting(true)
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
      realtime_segments_enabled: status.value?.realtime_segments_enabled ?? false,
      source: status.value?.source ?? 'settings',
    }
    void loadRouting(true)
  }

  return {
    status, loading, loaded, load, applyMode, canManage,
    overview, overviewLoading, jobs, activeJobs, isDownloading, requiredNotReady, tamperedModels,
    loadOverview, stopPolling, download, cancel, verify, start, stop, saveStorage,
    // 逐能力算力来源 / Per-capability compute source
    routing, accessSettings, expertMode, statusState, statusDetail,
    quotaRemaining, routeOverride, autoSwitch, capability, autoFallback, loadRouting, loadAccessSettings,
    applyCapabilitySource, applyExpertMode, applyAutoFallback,
    sessionModel, setSessionModel,
  }
})
