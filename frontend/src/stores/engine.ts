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

/** 徽章四态 / Four badge states */
export type EngineBadgeState = 'local' | 'proxy' | 'selfkey' | 'unready'

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

export const useEngineStore = defineStore('engine', () => {
  const status = ref<EngineStatus | null>(null)
  const loading = ref(false)
  const loaded = ref(false)
  const devOverride = ref<EngineBadgeState | null>(readDevOverride())

  // ─── R5 模型资产面 / R5 model asset surface ───
  const overview = ref<EngineModelsOverview | null>(null)
  const overviewLoading = ref(false)
  let pollTimer: ReturnType<typeof setInterval> | null = null

  /** 双因子派生徽章态 / Derive badge state from the two factors */
  const badge = computed<EngineBadgeState>(() => {
    if (devOverride.value) return devOverride.value
    const s = status.value
    if (!s) return 'unready'
    if (s.mode === 'local') return s.local_ready ? 'local' : 'unready'
    if (s.mode === 'direct') return 'selfkey'
    // cloud / proxy 均为项目方共享代理链路（体验代理） / cloud & proxy both route through the shared trial proxy
    return 'proxy'
  })

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

  /** 设置引擎模式（管理员，D-R2）后本地同步，避免等待后端刷新 / Sync mode locally after admin save (D-R2) */
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
  }
})
