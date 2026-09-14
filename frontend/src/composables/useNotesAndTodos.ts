/**
 * 随记 & 待办 CRUD / Notes & todos CRUD
 */
import { ref, watch, type ComputedRef, type Ref } from 'vue'
import { saveNotes, saveSummary, fetchTodos, toggleTodo, createTodo, deleteTodo, updateTodo, type TodoPatch } from '@/api/notes'
import type { TodoItem, Task, DecisionStatus } from '@/api/types'

export function useNotesAndTodos(
  taskId: string,
  notesContent: Ref<string>,
  notesSaved: Ref<boolean>,
  summaryMd: Ref<string>,
  todos: Ref<TodoItem[]>,
  activeTab: Ref<string>,
  _task: ComputedRef<Task | null>,
) {
  const showAddForm = ref(false)
  const newTodoText = ref('')
  const newTodoAssignee = ref('')
  let notesTimer: ReturnType<typeof setTimeout> | null = null
  let summaryTimer: ReturnType<typeof setTimeout> | null = null

  async function loadNotes() { notesContent.value = await (await import('@/api/notes')).fetchNotes(taskId) }
  async function loadTodos() { todos.value = await fetchTodos(taskId) }

  async function onSaveNotes() {
    try { await saveNotes(taskId, notesContent.value); notesSaved.value = true } catch { /* */ }
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
      try { await saveSummary(taskId, md) } catch { /* */ }
    }, 1000)
  }

  async function onToggleTodo(todo: TodoItem) {
    try {
      await toggleTodo(taskId, todo.id, !todo.done)
      todo.done = !todo.done
      // 同步决策流状态 / Keep decision-flow status in sync
      todo.status = todo.done ? 'done' : 'in_progress'
    } catch { /* */ }
  }

  async function onStatusChange(todo: TodoItem, status: DecisionStatus) {
    try {
      await updateTodo(taskId, todo.id, { status })
      todo.status = status
      todo.done = status === 'done'
    } catch { /* */ }
  }

  async function onAddTodo() {
    const text = newTodoText.value.trim()
    if (!text) return
    try {
      const t = await createTodo(taskId, text, newTodoAssignee.value.trim() || undefined)
      todos.value.push(t)
      newTodoText.value = ''; newTodoAssignee.value = ''; showAddForm.value = false
    } catch { /* */ }
  }

  async function onDeleteTodo(todo: TodoItem) {
    try { await deleteTodo(taskId, todo.id); todos.value = todos.value.filter(x => x.id !== todo.id) } catch { /* */ }
  }

  async function onEditTodo(todo: TodoItem, patch: TodoPatch) {
    try { await updateTodo(taskId, todo.id, patch); Object.assign(todo, patch) } catch { /* */ }
  }

  function locateTodoSource(_todo: TodoItem) { /* 由父组件 switchTab('transcript') 处理 / Handled by parent via switchTab('transcript') */ }

  // 自动加载（用 flag 区分「未加载」与「用户清空」） / Auto-load (flag distinguishes "not loaded" from "user cleared")
  let notesLoaded = false
  watch(activeTab, (tab) => {
    if (tab === 'notes' && !notesLoaded) { notesLoaded = true; loadNotes() }
    if (tab === 'todos' && todos.value.length === 0) loadTodos()
  })

  return {
    showAddForm, newTodoText, newTodoAssignee,
    loadNotes, loadTodos, onNotesChange, onSummaryChange,
    onToggleTodo, onAddTodo, onDeleteTodo, onEditTodo, onStatusChange, locateTodoSource,
  }
}
