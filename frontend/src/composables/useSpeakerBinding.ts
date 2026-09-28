/**
 * 说话人身份绑定逻辑 / Speaker identity binding logic
 *
 * 管理绑定映射、下拉框、增量保存、确认/跳过关联。 / Manages binding mapping, dropdowns, incremental save, confirm/skip association.
 */
import { ref, computed, reactive, nextTick, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { createSpeaker, submitSpeakerMapping, saveSpeakerMapping, applySpeakerNames, type Speaker } from '@/api/speakers'
import { getSpeakerColor } from '@/utils/speakerColors'
import { normalizeSpeakerName } from '@/utils/speakerDisplay'
import { showToast } from '@/composables/useToast'
import type { FlatTranscriptLine, Task } from '@/api/types'

export function useSpeakerBinding(
  taskId: string,
  task: ComputedRef<Task | null>,
  flatTranscript: ComputedRef<FlatTranscriptLine[]>,
  speakers: Ref<Speaker[]>,
  switchTab: (tabId: string) => void,
  startPolling: () => void,
) {
  const { t } = useI18n()
  const taskStore = useTaskStore()

  const currentBindingMapping = reactive<Record<number, string>>({})
  const bindingDropdown = reactive<{
    visible: boolean; speakerId: number; x: number; y: number; search: string; focusIdx: number
  }>({ visible: false, speakerId: -1, x: 0, y: 0, search: '', focusIdx: -1 })
  let dropdownEl: HTMLElement | null = null

  // 默认不展示绑定横幅（不给用户待办压力）：页面以只读可编辑态打开，
  // 用户点击人员栏「编辑关联」按钮（reenterBinding）后主动进入绑定态。
  const bindingBarHidden = ref(true)
  const bindBarDismissed = ref(localStorage.getItem(`oms_bind_bar_dismissed:${taskId}`) === 'true')

  function initBindingMapping() {
    const m = task.value?.speaker_uuid_mapping
    Object.keys(currentBindingMapping).forEach(k => delete currentBindingMapping[Number(k)])
    if (m) {
      for (const [k, v] of Object.entries(m)) {
        if (v) currentBindingMapping[Number(k)] = v
      }
    }
  }

  // 统一的说话人展示数据源：同时驱动「绑定态交互 chip」与「只读态名单」，
  // 避免与旧的 speakerStats 重复计算。displayName 解析优先级：
  // 已绑定真人名 > ASR 分配名(speaker_mapping) > 默认「说话人N」。
  const bindingLegend = computed(() => {
    const lines = flatTranscript.value
    if (!lines.length) return []
    const totalMs = lines.reduce((sum, l) => sum + (l.end_time - l.begin_time), 0)
    const speakerMap = new Map<number, number>()
    for (const l of lines) {
      speakerMap.set(l.speaker_id, (speakerMap.get(l.speaker_id) || 0) + (l.end_time - l.begin_time))
    }
    const mapping = task.value?.speaker_mapping
    return Array.from(speakerMap.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([sid, durMs]) => {
        const uuid = currentBindingMapping[sid]
        const bound = uuid ? speakers.value.find(s => s.id === uuid) : null
        const pct = totalMs > 0 ? Math.round((durMs / totalMs) * 100) : 0
        // REQ-SPK-RN H1/D5：存量占位名（mapping 直存 Speaker N）经判定器收敛，未绑定态统一中性文案
        const displayName = normalizeSpeakerName(bound?.name) || normalizeSpeakerName(mapping?.[String(sid)]) || t('generating.speaker_default')
        return { sid, durMs, pct, color: getSpeakerColor(String(sid)), name: normalizeSpeakerName(bound?.name), displayName, bound: !!bound }
      })
  })

  const unboundCount = computed(() => bindingLegend.value.filter(b => !b.bound).length)

  const canBind = computed(() => {
    const s = task.value?.status
    return s === 'awaiting_mapping' || s === 'completed'
  })

  const showBindingBar = computed(() => canBind.value && !bindingBarHidden.value && !bindBarDismissed.value)

  const dropdownSpeakers = computed(() => {
    const q = bindingDropdown.search.toLowerCase()
    if (!q) return speakers.value
    return speakers.value.filter(s => s.name.toLowerCase().includes(q) || (s.role || '').toLowerCase().includes(q))
  })

  function openBindingDropdown(e: MouseEvent, speakerId: number) {
    e.stopPropagation()
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    bindingDropdown.speakerId = speakerId
    bindingDropdown.x = rect.left
    bindingDropdown.y = rect.bottom + 4
    bindingDropdown.search = ''
    bindingDropdown.focusIdx = -1
    bindingDropdown.visible = true
    nextTick(() => {
      const dd = document.querySelector('.bt-dropdown') as HTMLElement
      if (dd) {
        dropdownEl = dd
        const input = dd.querySelector('input') as HTMLInputElement
        input?.focus()
        adjustDropdownPosition(dd)
      }
    })
  }

  function adjustDropdownPosition(dd: HTMLElement) {
    const vw = window.innerWidth, vh = window.innerHeight
    const r = dd.getBoundingClientRect()
    if (r.right > vw - 8) bindingDropdown.x = vw - r.width - 8
    if (r.bottom > vh - 8) bindingDropdown.y = bindingDropdown.y - r.height - 28
  }

  function closeBindingDropdown() { bindingDropdown.visible = false; dropdownEl = null }

  async function incrementalSave() {
    if (!['awaiting_mapping', 'completed'].includes(task.value?.status ?? '')) return
    const mapping = Object.fromEntries(Object.entries(currentBindingMapping).map(([k, v]) => [String(k), v]))
    try {
      await saveSpeakerMapping(taskId, mapping)
      taskStore.patchTaskLocal(taskId, { speaker_uuid_mapping: { ...currentBindingMapping } })
    } catch (e) { console.error('incremental save mapping failed:', e) }
  }

  async function selectBinding(speakerId: number, uuid: string) {
    if (uuid) currentBindingMapping[speakerId] = uuid
    else delete currentBindingMapping[speakerId]
    closeBindingDropdown()
    await incrementalSave()
  }

  async function createAndBind(speakerId: number, suggestedName: string) {
    // L2 写库源头（AC-7）：空名不再落占位档案，改必填引导；确保新档案永不写入编号占位名
    const name = (suggestedName || '').trim()
    if (!name || normalizeSpeakerName(name) === '') {
      showToast(t('generating.binding.name_required'), 'error')
      return
    }
    try {
      const newSpk = await createSpeaker(name)
      currentBindingMapping[speakerId] = newSpk.id
      speakers.value.push(newSpk)
      closeBindingDropdown()
      await incrementalSave()
    } catch (e) { console.error('create speaker failed:', e) }
  }

  async function confirmMapping() {
    bindingBarHidden.value = true
    switchTab('summary')
    const mapping = Object.fromEntries(Object.entries(currentBindingMapping).map(([k, v]) => [String(k), v]))
    const status = task.value?.status
    const hasSummary = !!task.value?.summary
    try {
      if (status === 'completed' && hasSummary) {
        // 解耦路径：已有纪要 → 原地替换说话人姓名，不重跑 LLM、不轮询、不覆盖用户编辑
        const result = await applySpeakerNames(taskId, mapping)
        const patch: Record<string, unknown> = {
          speaker_uuid_mapping: { ...currentBindingMapping },
          speaker_mapping: result.speaker_mapping ?? task.value?.speaker_mapping,
        }
        if (result.summary != null) patch.summary = result.summary
        if (result.user_summary !== undefined) patch.user_summary = result.user_summary
        if (result.dialogue) patch.dialogue = result.dialogue
        if (result.todos) patch.todos = result.todos
        // [状态同步] 原地替换后刷新本地任务，驱动纪要正文/原文/待办响应式更新
        taskStore.patchTaskLocal(taskId, patch as Partial<Task>)
      } else {
        // 兜底：尚无纪要（如历史 awaiting_mapping）→ 沿用触发 Stage 2 生成的老路径
        await submitSpeakerMapping(taskId, mapping)
        taskStore.patchTaskLocal(taskId, { speaker_uuid_mapping: { ...currentBindingMapping }, status: 'summarizing' })
        startPolling()
      }
    } catch (e) { console.error('confirm mapping failed:', e); bindingBarHidden.value = false }
  }

  function skipMapping() {
    bindingBarHidden.value = true
    bindBarDismissed.value = true
    localStorage.setItem(`oms_bind_bar_dismissed:${taskId}`, 'true')
  }

  // 从只读态重新进入绑定横幅（用户点击「编辑关联」按钮时调用）
  function reenterBinding() {
    bindingBarHidden.value = false
    bindBarDismissed.value = false
    localStorage.removeItem(`oms_bind_bar_dismissed:${taskId}`)
  }

  function onDropdownKeydown(e: KeyboardEvent) {
    const items = dropdownSpeakers.value
    const hasCreateBtn = bindingDropdown.search && items.length === 0
    const total = hasCreateBtn ? 1 : items.length
    if (e.key === 'ArrowDown') { e.preventDefault(); bindingDropdown.focusIdx = total > 0 ? (bindingDropdown.focusIdx + 1) % total : 0 }
    else if (e.key === 'ArrowUp') { e.preventDefault(); bindingDropdown.focusIdx = total > 0 ? (bindingDropdown.focusIdx <= 0 ? total - 1 : bindingDropdown.focusIdx - 1) : 0 }
    else if (e.key === 'Enter') {
      e.preventDefault()
      if (hasCreateBtn && bindingDropdown.focusIdx === 0) createAndBind(bindingDropdown.speakerId, bindingDropdown.search)
      else if (bindingDropdown.focusIdx >= 0 && bindingDropdown.focusIdx < items.length) selectBinding(bindingDropdown.speakerId, items[bindingDropdown.focusIdx].id)
    } else if (e.key === 'Escape') { e.preventDefault(); closeBindingDropdown() }
  }

  function onDocClickForDropdown(e: MouseEvent) {
    if (bindingDropdown.visible && dropdownEl && !dropdownEl.contains(e.target as Node)) closeBindingDropdown()
  }

  return {
    currentBindingMapping, bindingDropdown, bindingBarHidden,
    bindingLegend, unboundCount, canBind, showBindingBar, dropdownSpeakers,
    initBindingMapping, openBindingDropdown, closeBindingDropdown: closeBindingDropdown,
    selectBinding, createAndBind, confirmMapping, skipMapping, reenterBinding,
    onDropdownKeydown, onDocClickForDropdown,
  }
}
