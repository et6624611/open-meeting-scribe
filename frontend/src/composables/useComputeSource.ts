/**
 * 算力来源选择组合式（REQ-COMPUTE-CENTER · 仅前端重排）
 *
 * 把「当前使用的算力来源」选择/离线切换的写路径收敛到一处，供 API 配置 / ASR 配置两面板复用。
 * 映射到既有后端模型（不改路由 / 不改 schema）：
 *   - 联网侧来源（trial / byok / local_endpoint）→ capability_source.{cap}
 *   - 离线（本机引擎）→ access_mode = 'local'（整机接管，沿用切换事务）
 * 若当前处于离线态再选云端来源，走 applyAccess 原子携带 capability_source（避免两写中间态）。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEngineStore } from '@/stores/engine'
import { saveCapabilitySource, type CapSource } from '@/api/access'

export type ComputeCap = 'llm' | 'asr'

export function useComputeSource() {
  const { t } = useI18n()
  const engineStore = useEngineStore()

  const accessMode = computed(() => engineStore.accessMode)
  const capability = computed(() => engineStore.capability)
  const quotaRemaining = computed(() => engineStore.quotaRemaining)

  /** 该能力当前生效来源（离线态后端回 local） */
  function currentSource(cap: ComputeCap): CapSource {
    return (capability.value?.[cap]?.effective as CapSource) || ''
  }

  /** 来源用户词（复用现五词表；避免引入禁词） */
  function sourceLabel(src: string): string {
    if (!src) return '—'
    if (src === 'trial') return t('settings.access.src_trial')
    if (src === 'byok') return t('settings.access.src_byok')
    if (src === 'local_endpoint') return t('settings.access.src_local_ep')
    if (src === 'local') return t('settings.access.src_local')
    return src
  }

  /**
   * 选择联网侧来源（trial / byok / local_endpoint）。
   * 离线态下原子切联网并带上来源；否则直接显式保存来源。
   */
  async function pickCloudSource(cap: ComputeCap, src: CapSource) {
    if (accessMode.value === 'local') {
      await engineStore.applyAccess({ access_mode: 'cloud', capability_source: { [cap]: src } })
      return
    }
    await saveCapabilitySource({ [cap]: src })
    await engineStore.loadRouting(true)
    await engineStore.loadAccessSettings()
  }

  /** 离线：以本机引擎接管（整机离线，沿用切换事务与回滚） */
  async function pickLocalEngine() {
    await engineStore.applyAccess({ access_mode: 'local' })
  }

  /** 回到联网（安全方向，供离线态选任一云端来源前调用） */
  async function goCloud() {
    if (accessMode.value === 'local') await engineStore.applyAccess({ access_mode: 'cloud' })
  }

  return {
    engineStore,
    accessMode,
    capability,
    quotaRemaining,
    currentSource,
    sourceLabel,
    pickCloudSource,
    pickLocalEngine,
    goCloud,
  }
}
