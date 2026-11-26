/**
 * 书面版（WP-2）状态机 / Formal-version sidecar state machine
 *
 * 书面版结果独立于 dialogue，绝不回写；仅在会后（completed）可读写。
 * 从 TranscriptPanel 拆出，供后续书面版迭代在此扩展。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FlatTranscriptLine, FormalItem, FormalVersion } from '@/api/types'
import { getFormal, formalize } from '@/api/transcriptLayers'
import { fetchSettings, saveSettings } from '@/api/settings'
import type { LayerView } from '@/utils/transcriptLayers'

export type FormalState = 'absent' | 'running' | 'done' | 'stale' | 'error'

export interface FormalVersionOptions {
  /** 任务状态（仅 completed 允许读写） */
  taskStatus: () => string | undefined
  taskId: () => string | null | undefined
  lines: () => FlatTranscriptLine[]
  layerView: () => LayerView
  /** 面板是否可见：重新可见时拉一次（后台自动生成可能已完成） */
  visible: () => boolean
  /** 进入书面视图（由面板转发给父页面的 layerView） */
  onEnterFormal: () => void
}

export function useFormalVersion(o: FormalVersionOptions) {
  const { t } = useI18n()

  const formalVersion = ref<FormalVersion | null>(null)
  const formalStarting = ref(false)
  const formalActionError = ref('')
  const autoFormalEnabled = ref(false)
  let formalTimer: number | null = null

  /** 只有会后（completed）才可读写书面版 */
  const formalTaskId = computed<string | null>(() =>
    o.taskStatus() === 'completed' ? o.taskId() ?? null : null)

  const formalState = computed<FormalState>(() => {
    const v = formalVersion.value
    if (!v) return 'absent'
    if (v.status === 'running') return 'running'
    if (v.status === 'stale') return 'stale'
    if (v.status === 'error') return 'error'
    return 'done'
  })

  const formalMap = computed(() => {
    const m = new Map<number, FormalItem>()
    for (const it of formalVersion.value?.items ?? []) m.set(it.sentence_id, it)
    return m
  })

  const toneCount = computed(() =>
    (formalVersion.value?.items ?? []).filter(i => i.tone_flag === 'weakened').length)

  const formalProgress = computed(() => {
    const total = o.lines().length || formalVersion.value?.progress?.total || 0
    return { done: formalVersion.value?.progress?.done ?? 0, total }
  })

  const formalPercent = computed(() => {
    const { done, total } = formalProgress.value
    return total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0
  })

  /** 预估值：原文字符数 / 1.6，仅作提示 */
  const estimatedTokens = computed(() => {
    const chars = o.lines().reduce((n, l) => n + l.text.length, 0)
    return Math.max(1, Math.round(chars / 1.6))
  })

  /** 本机算力不耗云额度（方案 §7 遗留 4） */
  const costNote = computed(() =>
    formalVersion.value?.source === 'local_endpoint'
      ? t('generating.layer.formal_cost_local')
      : t('generating.layer.formal_cost_cloud'))

  function formalItem(line: FlatTranscriptLine): FormalItem | undefined {
    return formalMap.value.get(line.sentence_id)
  }

  function isFormalView(line: FlatTranscriptLine): boolean {
    return o.layerView() === 'formal' && formalState.value === 'done' && formalMap.value.has(line.sentence_id)
  }

  function isToneFlagged(line: FlatTranscriptLine): boolean {
    return formalItem(line)?.tone_flag === 'weakened'
  }

  function formatFormalTime(s: string | undefined): string {
    if (!s) return ''
    const d = new Date(s)
    if (Number.isNaN(d.getTime())) return ''
    const p = (n: number) => String(n).padStart(2, '0')
    return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  }

  async function fetchFormal(id: string) {
    try {
      formalVersion.value = await getFormal(id)
    } catch {
      // 读取失败保持现状，不打断当前视图
    }
  }

  async function startFormal(sentenceIds?: number[]) {
    const id = formalTaskId.value
    if (!id || formalStarting.value) return
    formalStarting.value = true
    formalActionError.value = ''
    try {
      await formalize(id, sentenceIds)
      await fetchFormal(id)
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: { reason?: string } } } })?.response?.data?.detail
      const reason = detail?.reason
      formalActionError.value = reason
        ? t('generating.layer.formal_blocked', { reason: t(`generating.layer.formal_block_reason.${reason}`, reason) })
        : t('generating.layer.formal_blocked_generic')
      await fetchFormal(id)
    } finally {
      formalStarting.value = false
    }
  }

  /** WP-3 选区书面化入口（SelectionToolbar → 页面转发）：切书面视图并复用同一状态机 */
  function formalizeSelection(sentenceIds: number[]) {
    if (!formalTaskId.value || !sentenceIds.length) return
    o.onEnterFormal()
    void startFormal(sentenceIds)
  }

  async function onToggleAutoFormal(next: boolean) {
    const prev = autoFormalEnabled.value
    autoFormalEnabled.value = next
    try {
      await saveSettings({ transcript: { formal: { auto_generate: next } } })
    } catch {
      autoFormalEnabled.value = prev
    }
  }

  watch(formalTaskId, (id) => {
    if (id) void fetchFormal(id)
    else formalVersion.value = null
  }, { immediate: true })

  watch(o.visible, (v) => {
    if (v && formalTaskId.value) void fetchFormal(formalTaskId.value)
  })

  // running 时 2s 轮询，落定即停
  watch(formalState, (s) => {
    if (formalTimer) { window.clearInterval(formalTimer); formalTimer = null }
    if (s === 'running') {
      formalTimer = window.setInterval(() => {
        if (formalTaskId.value) void fetchFormal(formalTaskId.value)
      }, 2000)
    }
  })

  onMounted(async () => {
    try {
      const s = await fetchSettings()
      autoFormalEnabled.value = s.transcript?.formal?.auto_generate === true
    } catch { /* 设置不可达时保持默认关 */ }
  })

  onBeforeUnmount(() => {
    if (formalTimer) window.clearInterval(formalTimer)
  })

  return {
    formalVersion, formalState, formalMap, formalProgress, formalPercent,
    toneCount, estimatedTokens, costNote, formalItem, isFormalView, isToneFlagged,
    formatFormalTime, formalStarting, formalActionError, autoFormalEnabled,
    startFormal, formalizeSelection, onToggleAutoFormal,
  }
}
