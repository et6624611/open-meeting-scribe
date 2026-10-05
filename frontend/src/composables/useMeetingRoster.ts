/**
 * 参会人名单逻辑 / Meeting roster logic
 *
 * 独立于说话人绑定，仅管理「谁参加了这次会议」的名字列表。 / Independent of speaker binding;
 * only manages the name list of "who attended this meeting".
 */
import { ref, watch, type ComputedRef } from 'vue'
import { updateRoster } from '@/api/speakers'
import type { Task } from '@/api/types'

export function useMeetingRoster(
  taskId: string,
  task: ComputedRef<Task | null>,
) {
  const roster = ref<string[]>([])
  const inputName = ref('')
  /** 手动添加的名字（区分自动同步 vs 手动添加） / Manually added names (distinguish from auto-synced) */
  const manualNames = new Set<string>()

  /** 从任务数据初始化参会人名单 / Initialize roster from task data */
  function initRoster() {
    roster.value = [...(task.value?.roster || [])]
    // 初始加载时无法区分自动/手动，全部视为手动（保守保留） / Treat all as manual on load (conservative)
    manualNames.clear()
    for (const n of roster.value) manualNames.add(n)
  }

  /** 添加参会人 / Add participant */
  async function addMember(name?: string) {
    const n = (name ?? inputName.value).trim()
    if (!n) return
    if (roster.value.includes(n)) {
      inputName.value = ''
      return
    }
    roster.value.push(n)
    manualNames.add(n)
    inputName.value = ''
    await persist()
  }

  /** 移除参会人 / Remove participant */
  async function removeMember(index: number) {
    const removed = roster.value.splice(index, 1)
    if (removed[0]) manualNames.delete(removed[0])
    await persist()
  }

  /** 持久化到后端 / Persist to backend */
  async function persist() {
    try {
      const result = await updateRoster(taskId, roster.value)
      roster.value = result.roster
    } catch (e) {
      console.error('Failed to update roster:', e)
    }
  }

  // 任务变化时重新初始化 / Re-initialize when task changes
  watch(task, (t) => {
    if (t) initRoster()
  }, { immediate: true })

  return {
    roster,
    inputName,
    manualNames,
    initRoster,
    addMember,
    removeMember,
    persist,
  }
}
