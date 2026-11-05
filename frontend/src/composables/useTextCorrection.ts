import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchTask, correctTaskText } from '@/api/tasks'
import { extractErrorMessage } from '@/api/client'
import { showToast } from '@/composables/useToast'
import { useTaskStore } from '@/stores/task'

type ReloadFn = () => Promise<void>

export function useTextCorrection(taskId: string) {
  const { t } = useI18n()
  const taskStore = useTaskStore()
  const correcting = ref(false)

  let _reloadDecision: ReloadFn | null = null
  let _reloadNotes: ReloadFn | null = null
  let _reloadInsights: ((tid: string) => Promise<void>) | null = null
  let _reloadBoard: (() => void) | null = null

  function configure(reloaders: {
    reloadDecision: ReloadFn
    reloadNotes: ReloadFn
    reloadInsights: (tid: string) => Promise<void>
    reloadBoard: () => void
  }) {
    _reloadDecision = reloaders.reloadDecision
    _reloadNotes = reloaders.reloadNotes
    _reloadInsights = reloaders.reloadInsights
    _reloadBoard = reloaders.reloadBoard
  }

  async function refreshAfterCorrection() {
    try {
      const updated = await fetchTask(taskId)
      taskStore.patchTaskLocal(taskId, updated)
    } catch { /* keep old state, next polling still picks it */ }
    try { await _reloadDecision?.() } catch { /* */ }
    try { await _reloadNotes?.() } catch { /* */ }
    try { await _reloadInsights?.(taskId) } catch { /* */ }
    _reloadBoard?.()
  }

  async function applyTextCorrection(oldText: string, newText: string, createdMapping = false) {
    if (correcting.value) return
    correcting.value = true
    try {
      const result = await correctTaskText(taskId, oldText, newText)
      await refreshAfterCorrection()
      const scope = createdMapping ? t('generating.correction.mapping_saved') : ''
      if (result.replaced > 0) showToast(t('generating.correction.applied', { scope, text: newText, n: result.replaced }), 'success')
      else showToast(t('generating.correction.no_match', { scope, text: oldText }), 'warn')
    } catch (e) {
      showToast(t('generating.correction.failed', { reason: extractErrorMessage(e) }), 'error')
    } finally {
      correcting.value = false
    }
  }

  function onSelectionAction(action: string, text: string, _source: string, _blockIndex: number, replacement?: string, createdMapping?: boolean) {
    // 工具栏 rewrite/summarize/extract 已下架，仅保留划词热词修正 / Toolbar rewrite/summarize/extract retired.
    if (action === 'correct' && replacement) void applyTextCorrection(text, replacement, createdMapping)
  }

  return { correcting, configure, refreshAfterCorrection, applyTextCorrection, onSelectionAction }
}
