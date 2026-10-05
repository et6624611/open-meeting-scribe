/**
 * AI 指令系统 / AI command system
 *
 * 指令定义、按状态过滤、面板状态管理。 / Command definitions, status-based filtering, panel state management.
 * 执行逻辑由调用方注入（避免循环依赖）。 / Execution logic injected by caller (avoids circular dependencies).
 */
import { ref } from 'vue'
import type { TaskStatus } from '@/api/types'

export interface AiCommand {
  key: string
  desc: string
  /** i18n 裸键（面板显示 t('ai-panel.' + descKey)） / Bare i18n key for panel display */
  descKey?: string
  when: 'all' | 'recording' | 'completed'
  trigger?: boolean
  action: (args?: string) => void
}

const AI_FREQUENT_KEYS = ['/待办', '/结论', '/发言']

export function useAiCommands() {
  const cmdIndex = ref(-1)
  const cmdOpen = ref(false)
  const commands = ref<AiCommand[]>([])

  /** 注册指令列表（由 AIPanel 在 setup 时调用，注入 action 回调） / Register command list (called by AIPanel during setup, injects action callbacks) */
  function registerCommands(cmds: AiCommand[]) {
    commands.value = cmds
  }

  /** 按当前任务状态过滤可用指令 / Filter available commands by current task status */
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

  /** 按输入过滤 / Filter by input */
  function filterCommands(query: string, status: TaskStatus | null): AiCommand[] {
    const available = getAvailable(status)
    const q = query.toLowerCase()
    return available.filter(c => c.key.slice(1).toLowerCase().includes(q))
  }

  /** 高频指令（用于面板分组） / Frequent commands (for panel grouping) */
  function isFrequent(key: string): boolean {
    return AI_FREQUENT_KEYS.includes(key)
  }

  function open() { cmdOpen.value = true; cmdIndex.value = 0 }
  function close() { cmdOpen.value = false; cmdIndex.value = -1 }

  /** 直接定位高亮项（输入精确匹配指令时调用） / Set highlight index directly (exact input match) */
  function setIndex(i: number) { cmdIndex.value = i }

  /**
   * 精确解析斜杠串（含行内参数）→ 指令 + 参数。
   * 词序列匹配：key 按空格分词，从输入头部逐词对齐；多词 key 优先（最长匹配），
   * 剩余词作为 args 原样传入。限定当前状态可用指令；无匹配返回 null。
   * Exact-parse a slash string (incl. inline args) into command + args.
   */
  function resolveCommand(raw: string, status: TaskStatus | null): { cmd: AiCommand; args?: string } | null {
    const words = raw.trim().split(/\s+/).filter(Boolean)
    if (!words.length || !words[0].startsWith('/')) return null
    const available = getAvailable(status)
    // 最长 key 优先，保证 /record start 不被 /record 截胡（若后者存在）
    const sorted = [...available].sort((a, b) => b.key.split(/\s+/).length - a.key.split(/\s+/).length)
    for (const cmd of sorted) {
      const kw = cmd.key.split(/\s+/)
      if (kw.length > words.length) continue
      if (kw.every((w, i) => words[i].toLowerCase() === w.toLowerCase())) {
        const args = words.slice(kw.length).join(' ')
        return { cmd, args: args || undefined }
      }
    }
    return null
  }

  function moveDown(count: number) {
    cmdIndex.value = Math.min(cmdIndex.value + 1, count - 1)
  }
  function moveUp() {
    cmdIndex.value = Math.max(cmdIndex.value - 1, 0)
  }

  return {
    cmdIndex, cmdOpen, commands,
    registerCommands, getAvailable, filterCommands, isFrequent,
    resolveCommand, setIndex,
    open, close, moveDown, moveUp,
  }
}
