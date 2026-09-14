/**
 * useInlineEdit.ts — 行间编辑状态管理 / Inline edit state management
 *
 * 管理划词改写功能的完整生命周期：
 * 划词 → 弹出指令输入 → AI 改写 → 原地 diff 展示 → 采纳/拒绝
 *
 * 作者 / Author: Yongliang Wang
 * 创建 / Created: 2026-09-14
 * 版本 / Version: 1.0.0
 */

import { ref, computed } from 'vue'
import { inlineEdit as apiInlineEdit } from '@/api/chat'
import { showToast } from '@/composables/useToast'
import { useI18n } from 'vue-i18n'

/** 行间编辑状态类型 / Inline edit status type */
export type InlineEditStatus = 'idle' | 'input' | 'loading' | 'result'

/** 行间编辑状态 / Inline edit state */
export interface InlineEditState {
  blockIndex: number
  originalText: string
  source: string
  instruction: string
  editedText: string
  status: InlineEditStatus
}

/** 块更新回调类型 / Block updater callback type */
type BlockUpdater = (blockIndex: number, newSource: string) => void

// ── 模块级单例状态 / Module-level singleton state ──
const status = ref<InlineEditStatus>('idle')
const blockIndex = ref(-1)
const originalText = ref('')
const source = ref('')
const instruction = ref('')
const editedText = ref('')
const anchorRect = ref<{ top: number; left: number } | null>(null)

let blockUpdateFn: BlockUpdater | null = null

export function useInlineEdit() {
  const { t } = useI18n()

  /** 是否正在显示输入框 / Whether the input popup is visible */
  const showInput = computed(() => status.value === 'input')

  /** 是否正在加载 / Whether loading AI response */
  const isLoading = computed(() => status.value === 'loading')

  /** 是否正在展示 diff / Whether showing diff result */
  const showDiff = computed(() => status.value === 'result')

  /** 当前 diff 的目标块索引 / Current diff target block index */
  const diffBlockIndex = computed(() => blockIndex.value)

  /** 注册块更新回调 / Register block updater callback */
  function registerBlockUpdater(fn: BlockUpdater | null) {
    blockUpdateFn = fn
  }

  /** 启动行间编辑（由 SelectionToolbar 触发） / Start inline edit (triggered by SelectionToolbar) */
  function startInlineEdit(
    text: string,
    src: string,
    blkIdx: number,
    rect?: { top: number; left: number },
  ) {
    originalText.value = text
    source.value = src
    blockIndex.value = blkIdx
    instruction.value = ''
    editedText.value = ''
    anchorRect.value = rect || null
    status.value = 'input'
  }

  /** 提交用户指令，调用 AI 改写 / Submit user instruction, call AI rewrite */
  async function submitInstruction(inst: string) {
    if (!inst.trim()) return
    instruction.value = inst.trim()
    status.value = 'loading'
    try {
      const res = await apiInlineEdit(originalText.value, instruction.value)
      editedText.value = res.edited
      status.value = 'result'
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || String(err)
      showToast(t('common.inline_edit_failed', { err: msg }), 'error')
      status.value = 'idle'
    }
  }

  /** 采纳改写结果 / Accept edit result */
  function acceptEdit() {
    if (status.value !== 'result' || !editedText.value) return
    if (blockIndex.value >= 0 && blockUpdateFn) {
      blockUpdateFn(blockIndex.value, editedText.value + ' <!--ai-->')
      showToast(t('common.inline_edit_accepted'), 'success')
    } else {
      showToast(t('common.inline_edit_locate_failed'), 'warn')
    }
    clearState()
  }

  /** 拒绝改写结果 / Reject edit result */
  function rejectEdit() {
    showToast(t('common.inline_edit_rejected'), 'info')
    clearState()
  }

  /** 取消整个流程 / Cancel the entire flow */
  function cancelEdit() {
    clearState()
  }

  /** 清除状态 / Clear state */
  function clearState() {
    status.value = 'idle'
    blockIndex.value = -1
    originalText.value = ''
    source.value = ''
    instruction.value = ''
    editedText.value = ''
    anchorRect.value = null
  }

  return {
    // 状态 / State
    status,
    blockIndex,
    originalText,
    source,
    instruction,
    editedText,
    anchorRect,
    // 计算属性 / Computed
    showInput,
    isLoading,
    showDiff,
    diffBlockIndex,
    // 方法 / Methods
    registerBlockUpdater,
    startInlineEdit,
    submitInstruction,
    acceptEdit,
    rejectEdit,
    cancelEdit,
    clearState,
  }
}
