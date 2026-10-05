/**
 * 算力来源选择组合式（逐能力真相源）
 *
 * 把「当前使用的算力来源」逐能力选择的写路径收敛到一处，供 API 配置 / ASR 配置两面板复用。
 * ASR 与 LLM 各自独立选择，互不联动；均经 /api/settings/capability 事务（ASR 进入/离开 local 启停引擎）。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEngineStore } from '@/stores/engine'
import type { CapSource } from '@/api/access'

export type ComputeCap = 'llm' | 'asr'

export function useComputeSource() {
  const { t } = useI18n()
  const engineStore = useEngineStore()

  const capability = computed(() => engineStore.capability)
  const quotaRemaining = computed(() => engineStore.quotaRemaining)

  /** 该能力当前生效来源（逐能力真相源） */
  function currentSource(cap: ComputeCap): CapSource {
    return (capability.value?.[cap]?.effective as CapSource) || ''
  }

  /** 来源用户词（复用现词表；避免引入禁词） */
  function sourceLabel(src: string): string {
    if (!src) return '—'
    if (src === 'trial') return t('settings.access.src_trial')
    if (src === 'byok') return t('settings.access.src_byok')
    if (src === 'local_endpoint') return t('settings.access.src_local_ep')
    if (src === 'local') return t('settings.access.src_local')
    return src
  }

  /** 选择该能力的算力来源（trial/byok/local_endpoint）；逐能力独立，经事务端点 */
  async function pickCloudSource(cap: ComputeCap, src: CapSource) {
    await engineStore.applyCapabilitySource({ [cap]: src })
  }

  /** ASR 本机引擎：只影响转写自身，不再翻全局 */
  async function pickLocalEngine() {
    await engineStore.applyCapabilitySource({ asr: 'local' })
  }

  return {
    engineStore,
    capability,
    quotaRemaining,
    currentSource,
    sourceLabel,
    pickCloudSource,
    pickLocalEngine,
  }
}
