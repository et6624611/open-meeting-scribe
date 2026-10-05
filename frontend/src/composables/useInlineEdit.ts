/**
 * useInlineEdit.ts — 行间编辑状态管理 / Inline edit state management
 *
 * 管理划词改写功能的完整生命周期：
 * 划词 → 弹出指令输入 → AI 改写 → 原地替换 → 采纳/拒绝
 *
 * v2.0: 从块索引模式切换到 textarea 选区范围模式 / v2.0: from block index to textarea range mode
 *
 * 作者 / Author: Yongliang Wang
 * 创建 / Created: 2026-09-14
 * 版本 / Version: 2.0.0
 */

import { ref, computed } from 'vue'
import { inlineEdit as apiInlineEdit } from '@/api/chat'
import type { ModelUsage } from '@/api/chat'
import { showToast } from '@/composables/useToast'
import { useI18n } from 'vue-i18n'

/** 行间编辑状态类型 / Inline edit status type */
export type InlineEditStatus = 'idle' | 'input' | 'loading' | 'result'

/** 选区范围 / Selection range */
export interface TextRange {
  start: number
  end: number
}

// ── 模块级单例状态 / Module-level singleton state ──
const status = ref<InlineEditStatus>('idle')
const rangeStart = ref(0)
const rangeEnd = ref(0)
const originalText = ref('')
const source = ref('')
const instruction = ref('')
const editedText = ref('')
const anchorRect = ref<{ top: number; left: number } | null>(null)
/** 最近一次改写的执行方回显（AI 算力入口治理 §3）：确认卡角落展示 模型·来源·计费 */
const lastModelUsage = ref<ModelUsage | null>(null)

/** 范围替换回调 / Range replacer callback */
type RangeReplacer = (start: number, end: number, newText: string) => void
let rangeReplaceFn: RangeReplacer | null = null

export function useInlineEdit() {
  const { t } = useI18n()

  /** 是否正在显示输入框 / Whether the input popup is visible */
  const showInput = computed(() => status.value === 'input')

  /** 是否正在加载 / Whether loading AI response */
  const isLoading = computed(() => status.value === 'loading')

  /** 是否正在展示 diff / Whether showing diff result */
  const showDiff = computed(() => status.value === 'result')

  /** 启动行间编辑（由 SelectionToolbar 或 textarea 面板触发） / Start inline edit */
  function startInlineEdit(
    text: string,
    src: string,
    range: TextRange,
    rect?: { top: number; left: number },
  ) {
    originalText.value = text
    source.value = src
    rangeStart.value = range.start
    rangeEnd.value = range.end
    instruction.value = ''
    editedText.value = ''
    anchorRect.value = rect || null
    lastModelUsage.value = null
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
      // 执行回显：后端随响应携带实际消费方；失败分支的 detail 已自带 [model · source] 标签
      lastModelUsage.value = res.model_usage || null
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
    if (rangeReplaceFn) {
      rangeReplaceFn(rangeStart.value, rangeEnd.value, editedText.value)
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

  /** 注册范围替换回调 / Register range replacer callback */
  function registerRangeReplacer(fn: RangeReplacer | null) {
    rangeReplaceFn = fn
  }

  /** 清除状态 / Clear state */
  function clearState() {
    status.value = 'idle'
    rangeStart.value = 0
    rangeEnd.value = 0
    originalText.value = ''
    source.value = ''
    instruction.value = ''
    editedText.value = ''
    anchorRect.value = null
    lastModelUsage.value = null
  }

  return {
    // 状态 / State
    status,
    rangeStart,
    rangeEnd,
    originalText,
    source,
    instruction,
    editedText,
    anchorRect,
    lastModelUsage,
    // 计算属性 / Computed
    showInput,
    isLoading,
    showDiff,
    // 方法 / Methods
    registerRangeReplacer,
    startInlineEdit,
    submitInstruction,
    acceptEdit,
    rejectEdit,
    cancelEdit,
    clearState,
  }
}
