import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { runVoiceprintMatch, dismissVoiceprintSuggestion } from '@/api/voiceprint'
import { showToast } from '@/composables/useToast'
import type { VoiceprintMatchItem } from '@/api/types'

interface TaskRefLike { value?: { voiceprint_match?: VoiceprintMatchItem[] | null; voiceprint_dismissed?: number[] | null } | null | undefined }

export function useVoiceprintMatch(taskId: string, task: TaskRefLike, canRun: () => boolean, emitSelectBinding?: (speakerId: number, uuid: string) => Promise<void>) {
  const { t } = useI18n()
  const voiceprintRunning = ref(false)

  const visibleVoiceprintItems = computed<VoiceprintMatchItem[] | null>(() => {
    const items = task.value?.voiceprint_match ?? null
    if (!items) return null
    const dismissed = new Set(task.value?.voiceprint_dismissed ?? [])
    return dismissed.size ? items.filter(it => !dismissed.has(it.speaker_id)) : items
  })

  async function runVoiceprint() {
    if (voiceprintRunning.value || !canRun()) return
    voiceprintRunning.value = true
    try {
      const res = await runVoiceprintMatch(taskId)
      // 让调用方通过 taskStore.patchTaskLocal 落盘：
      // taskStore.patchTaskLocal(taskId, { voiceprint_match, voiceprint_auto_mapping, voiceprint_dismissed })
      return res
    } catch {
      showToast(t('generating.voiceprint.failed'), 'error')
      return null
    } finally {
      voiceprintRunning.value = false
    }
  }

  async function onVoiceprintApply(speakerId: number, uuid: string) {
    if (emitSelectBinding) await emitSelectBinding(speakerId, uuid)
  }

  async function onVoiceprintDismiss(speakerId: number) {
    const item = (task.value?.voiceprint_match ?? []).find(it => it.speaker_id === speakerId)
    let undoBind = false
    if (item?.status === 'matched' && item.matched_uuid) {
      // 调用方负责撤销绑定：binding.selectBinding(speakerId, '')
      undoBind = true
    }
    const dismissed = new Set(task.value?.voiceprint_dismissed ?? [])
    dismissed.add(speakerId)
    try { await dismissVoiceprintSuggestion(taskId, speakerId) }
    catch { showToast(t('generating.voiceprint.failed'), 'error') }
    return { dismissedIds: [...dismissed].sort((a, b) => a - b), undoBind, matchedUuid: item?.matched_uuid ?? '' }
  }

  return {
    voiceprintRunning, visibleVoiceprintItems,
    runVoiceprint, onVoiceprintApply, onVoiceprintDismiss,
  }
}
