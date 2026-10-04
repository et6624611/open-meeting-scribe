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
  /** i18n 裸键（ai-panel 命名空间）；缺省时面板回退展示 desc / Bare i18n key under ai-panel.*; falls back to desc */
  descKey?: string
  when: 'all' | 'recording' | 'completed'
  trigger?: boolean
  /** 行内参数（如 /speakers add 张三 → '张三'），无参指令可忽略 / Inline args after the command key */
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

  /**
   * 精确解析斜杠串（含行内参数，如 `/speakers add 张三`）。
   * 按词对齐：指令键词序列必须是输入词的前缀，取最长键命中，剩余词为 args；
   * 仅在当前状态可用指令中匹配，无命中返回 null（调用方转走面板候选/未知拦截）。
   */
  function resolveCommand(
    raw: string,
    status: TaskStatus | null,
  ): { cmd: AiCommand; args: string } | null {
    const body = raw.trim().slice(1)
    if (!body) return null
    const tokens = body.split(/\s+/).filter(Boolean)
    if (!tokens.length) return null
    let best: AiCommand | null = null
    for (const cmd of getAvailable(status)) {
      const keyTokens = cmd.key.slice(1).toLowerCase().split(/\s+/).filter(Boolean)
      if (keyTokens.length > tokens.length) continue
      if (!keyTokens.every((kt, i) => kt === tokens[i].toLowerCase())) continue
      if (!best || keyTokens.length > best.key.split(/\s+/).length) best = cmd
    }
    if (!best) return null
    const argCount = best.key.slice(1).split(/\s+/).filter(Boolean).length
    return { cmd: best, args: tokens.slice(argCount).join(' ') }
  }

  /** 直接设置面板高亮索引（相对过滤后的候选列表），由调用方保证范围 / Set highlight index against the filtered candidate list */
  function setIndex(i: number) {
    cmdIndex.value = Math.max(0, i)
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
