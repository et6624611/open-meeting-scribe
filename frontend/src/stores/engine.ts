/**
 * 计算引擎状态 store / Compute engine status store
 *
 * R6（PRD-LOCAL-ENGINE）：顶栏徽章四态 = 本地引擎 / 体验代理 / 自持 Key / 未就绪。
 * 判定为双因子：settings.engine.mode + 本地引擎目录存在性（local_ready）。
 * R6 badge has four states, derived from two factors: engine.mode + local engine directory presence.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchEngineStatus, type EngineStatus, type EngineMode } from '@/api/engine'

/** 徽章四态 / Four badge states */
export type EngineBadgeState = 'local' | 'proxy' | 'selfkey' | 'unready'

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

  /** 设置引擎模式（管理员，D-R2）后本地同步，避免等待后端刷新 / Sync mode locally after admin save (D-R2) */
  function applyMode(mode: EngineMode) {
    status.value = {
      mode,
      local_ready: status.value?.local_ready ?? false,
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

  return { status, loading, loaded, badge, devOverride, load, applyMode, setDevOverride }
})
