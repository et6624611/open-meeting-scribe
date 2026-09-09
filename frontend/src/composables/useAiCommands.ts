/**
 * AI 指令系统
 *
 * 指令定义、按状态过滤、面板状态管理。
 * 执行逻辑由调用方注入（避免循环依赖）。
 */
import { ref } from 'vue'
import type { TaskStatus } from '@/api/types'

export interface AiCommand {
  key: string
  desc: string
  when: 'all' | 'recording' | 'completed'
  trigger?: boolean
  action: () => void
}

const AI_FREQUENT_KEYS = ['/待办', '/结论', '/发言']

export function useAiCommands() {
  const cmdIndex = ref(-1)
  const cmdOpen = ref(false)
  const commands = ref<AiCommand[]>([])

  /** 注册指令列表（由 AIPanel 在 setup 时调用，注入 action 回调） */
  function registerCommands(cmds: AiCommand[]) {
    commands.value = cmds
  }

  /** 按当前任务状态过滤可用指令 */
  function getAvailable(status: TaskStatus | null): AiCommand[] {
    const isRecording = status === 'recording'
    const isCompleted = status === 'completed' || status === 'awaiting_mapping'
    return commands.value.filter(cmd => {
      if (cmd.when === 'all') return true
      if (cmd.when === 'recording' && isRecording) return true
      if (cmd.when === 'completed' && isCompleted) return true
      return false
    })
  }

  /** 按输入过滤 */
  function filterCommands(query: string, status: TaskStatus | null): AiCommand[] {
    const available = getAvailable(status)
    const q = query.toLowerCase()
    return available.filter(c => c.key.slice(1).toLowerCase().includes(q))
  }

  /** 高频指令（用于面板分组） */
  function isFrequent(key: string): boolean {
    return AI_FREQUENT_KEYS.includes(key)
  }

  function open() { cmdOpen.value = true; cmdIndex.value = 0 }
  function close() { cmdOpen.value = false; cmdIndex.value = -1 }

  function moveDown(count: number) {
    cmdIndex.value = Math.min(cmdIndex.value + 1, count - 1)
  }
  function moveUp() {
    cmdIndex.value = Math.max(cmdIndex.value - 1, 0)
  }

  return {
    cmdIndex, cmdOpen, commands,
    registerCommands, getAvailable, filterCommands, isFrequent,
    open, close, moveDown, moveUp,
  }
}
