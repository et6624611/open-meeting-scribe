/**
 * 随记 & 待办 CRUD / Notes & todos CRUD
 */
import { watch, type ComputedRef, type Ref } from 'vue'
import { saveNotes, saveSummary, fetchTodos, toggleTodo, createTodo, deleteTodo, updateTodo, type TodoCreatePayload, type TodoPatch } from '@/api/notes'
import type { TodoItem, Task, DecisionStatus } from '@/api/types'
import { useDecisionStatuses } from './useDecisionStatuses'

export function useNotesAndTodos(
  taskId: string,
  notesContent: Ref<string>,
  notesSaved: Ref<boolean>,
  summaryMd: Ref<string>,
  todos: Ref<TodoItem[]>,
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
  async function loadTodos() { todos.value = await fetchTodos(taskId) }

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

  async function onToggleTodo(todo: TodoItem) {
    try {
      await toggleTodo(taskId, todo.id, !todo.done)
      todo.done = !todo.done
      // 同步决策流状态：完成态 = done，取消勾选回到首个开放态 / Keep decision-flow status in sync
      todo.status = todo.done ? 'done' : (statuses.value.find(s => !s.closing)?.id || 'in_progress')
      onContentModified?.()
    } catch { /* */ }
  }

  async function onStatusChange(todo: TodoItem, status: DecisionStatus) {
    try {
      await updateTodo(taskId, todo.id, { status })
      todo.status = status
      // done 是旧兼容字段：闭档态（完成类）即为已完成，不再等价于 status === 'done'
      todo.done = isClosing(status)
      onContentModified?.()
    } catch { /* */ }
  }

  // DC-UNIFY-01 统一口径：添加决策与手动补录共用 AddDecisionDialog 表单（title/text/owner_id/status）
  // 归属会议由弹层选择：非当前任务时只写盘不更新本地列表；失败抛由调用方提示
  async function onAddTodo(payload: TodoCreatePayload, targetTaskId?: string): Promise<TodoItem> {
    const text = (payload.text || '').trim()
    const tid = targetTaskId || taskId
    const t = await createTodo(tid, { ...payload, text })
    if (tid === taskId) todos.value.push(t)
    onContentModified?.()
    return t
  }

  async function onDeleteTodo(todo: TodoItem) {
    try { await deleteTodo(taskId, todo.id); todos.value = todos.value.filter(x => x.id !== todo.id); onContentModified?.() } catch { /* */ }
  }

  async function onEditTodo(todo: TodoItem, patch: TodoPatch) {
    try { await updateTodo(taskId, todo.id, patch); Object.assign(todo, patch); onContentModified?.() } catch { /* */ }
  }

  function locateTodoSource(_todo: TodoItem) { /* 由父组件 switchTab('transcript') 处理 / Handled by parent via switchTab('transcript') */ }

  // 自动加载（用 flag 区分「未加载」与「用户清空」） / Auto-load (flag distinguishes "not loaded" from "user cleared")
  let notesLoaded = false
  watch(activeTab, (tab) => {
    if (tab === 'notes' && !notesLoaded) { notesLoaded = true; loadNotes() }
    if (tab === 'todos' && todos.value.length === 0) loadTodos()
  })

  return {
    loadNotes, loadTodos, onNotesChange, onSummaryChange,
    onToggleTodo, onAddTodo, onDeleteTodo, onEditTodo, onStatusChange, locateTodoSource,
  }
}
