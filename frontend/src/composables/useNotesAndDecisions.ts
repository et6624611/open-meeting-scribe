/**
 * 随记 & 决策 CRUD / Notes & decisions CRUD
 */
import { watch, type ComputedRef, type Ref } from 'vue'
import { saveNotes, saveSummary, fetchDecisions, toggleDecision, createDecision, deleteDecision, updateDecision, type DecisionCreatePayload, type DecisionPatch } from '@/api/notes'
import type { DecisionItem, Task, DecisionStatus } from '@/api/types'
import { useDecisionStatuses } from './useDecisionStatuses'

export function useNotesAndDecisions(
  taskId: string,
  notesContent: Ref<string>,
  notesSaved: Ref<boolean>,
  summaryMd: Ref<string>,
  decisions: Ref<DecisionItem[]>,
  activeTab: Ref<string>,
  _task: ComputedRef<Task | null>,
  onContentModified?: () => void,
) {
  // 状态字典：闭档位驱动 done 同步，开放首态作为取消勾选的回落（与后端口径一致）
  const { statuses, isClosing } = useDecisionStatuses()
  let notesTimer: ReturnType<typeof setTimeout> | null = null
  let summaryTimer: ReturnType<typeof setTimeout> | null = null

  async function loadNotes() {
    // 外部重拉（AI 提案被接受 / 写回后刷新）以服务端为准：先取消挂起的防抖自动保存，
    // 否则旧文本会在 1s 后回写、静默吞掉刚接受的提案内容
    if (notesTimer) { clearTimeout(notesTimer); notesTimer = null }
    notesContent.value = await (await import('@/api/notes')).fetchNotes(taskId)
  }
  async function loadDecisions() { decisions.value = await fetchDecisions(taskId) }

  async function onSaveNotes() {
    try { await saveNotes(taskId, notesContent.value); notesSaved.value = true; onContentModified?.() } catch { /* */ }
  }

  function onNotesChange(md: string) {
    notesContent.value = md; notesSaved.value = false
    if (notesTimer) clearTimeout(notesTimer)
    notesTimer = setTimeout(onSaveNotes, 1000)
  }

  function onSummaryChange(md: string) {
    summaryMd.value = md
    if (summaryTimer) clearTimeout(summaryTimer)
    summaryTimer = setTimeout(async () => {
      try { await saveSummary(taskId, md); onContentModified?.() } catch { /* */ }
    }, 1000)
  }

  async function onToggleDecision(decision: DecisionItem) {
    try {
      await toggleDecision(taskId, decision.id, !decision.done)
      decision.done = !decision.done
      // 同步决策流状态：完成态 = done，取消勾选回到首个开放态 / Keep decision-flow status in sync
      decision.status = decision.done ? 'done' : (statuses.value.find(s => !s.closing)?.id || 'in_progress')
      onContentModified?.()
    } catch { /* */ }
  }

  async function onStatusChange(decision: DecisionItem, status: DecisionStatus) {
    try {
      await updateDecision(taskId, decision.id, { status })
      decision.status = status
      // done 是旧兼容字段：闭档态（完成类）即为已完成，不再等价于 status === 'done'
      decision.done = isClosing(status)
      onContentModified?.()
    } catch { /* */ }
  }

  // DC-UNIFY-01 统一口径：添加决策与手动补录共用 AddDecisionDialog 表单（title/text/owner_id/status）
  // 归属会议由弹层选择：非当前任务时只写盘不更新本地列表；失败抛由调用方提示
  async function onAddDecision(payload: DecisionCreatePayload, targetTaskId?: string): Promise<DecisionItem> {
    const text = (payload.text || '').trim()
    const tid = targetTaskId || taskId
    const t = await createDecision(tid, { ...payload, text })
    if (tid === taskId) decisions.value.push(t)
    onContentModified?.()
    return t
  }

  async function onDeleteDecision(decision: DecisionItem) {
    try { await deleteDecision(taskId, decision.id); decisions.value = decisions.value.filter(x => x.id !== decision.id); onContentModified?.() } catch { /* */ }
  }

  async function onEditDecision(decision: DecisionItem, patch: DecisionPatch) {
    try { await updateDecision(taskId, decision.id, patch); Object.assign(decision, patch); onContentModified?.() } catch { /* */ }
  }

  function locateDecisionSource(_decision: DecisionItem) { /* 由父组件 switchTab('transcript') 处理 / Handled by parent via switchTab('transcript') */ }

  /** 强制 flush 挂起的防抖保存：清定时器 + 立即保存。
   *  在切 Tab / 编辑器重建 / 页面隐藏前调用，防止未落盘编辑被异步 loadNotes 覆盖。
   *  Force-flush pending debounced save: clear timer + save immediately.
   *  Call before tab switch, editor rebuild, or pagehide to prevent in-flight edits
   *  from being overwritten by an async loadNotes that returns first. */
  function flushPendingNotesSave() {
    if (notesTimer) {
      clearTimeout(notesTimer)
      notesTimer = null
      void onSaveNotes()
    }
  }

  // 自动加载（用 flag 区分「未加载」与「用户清空」） / Auto-load (flag distinguishes "not loaded" from "user cleared")
  let notesLoaded = false
  watch(activeTab, (tab, prev) => {
    // 从随记页切走时先 flush，防止 loadNotes 覆盖未落盘的编辑
    if (prev === 'notes' && tab !== 'notes') flushPendingNotesSave()
    if (tab === 'notes' && !notesLoaded) { notesLoaded = true; loadNotes() }
    if (tab === 'decisions' && decisions.value.length === 0) loadDecisions()
  })

  return {
    loadNotes, loadDecisions, onNotesChange, onSummaryChange, flushPendingNotesSave,
    onToggleDecision, onAddDecision, onDeleteDecision, onEditDecision, onStatusChange, locateDecisionSource,
  }
}
