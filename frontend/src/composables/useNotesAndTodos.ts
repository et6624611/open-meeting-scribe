/**
 * 随记 & 待办 CRUD
 */
import { ref, watch, type ComputedRef, type Ref } from 'vue'
import { saveNotes, saveSummary, fetchTodos, toggleTodo, createTodo, deleteTodo } from '@/api/notes'
import type { TodoItem, Task } from '@/api/types'

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
    try { await toggleTodo(taskId, todo.id, !todo.done); todo.done = !todo.done } catch { /* */ }
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

  function locateTodoSource(_todo: TodoItem) { /* 由父组件 switchTab('transcript') 处理 */ }

  // 自动加载（用 flag 区分「未加载」与「用户清空」）
  let notesLoaded = false
  watch(activeTab, (tab) => {
    if (tab === 'notes' && !notesLoaded) { notesLoaded = true; loadNotes() }
    if (tab === 'todos' && todos.value.length === 0) loadTodos()
  })

  return {
    showAddForm, newTodoText, newTodoAssignee,
    loadNotes, loadTodos, onNotesChange, onSummaryChange,
    onToggleTodo, onAddTodo, onDeleteTodo, locateTodoSource,
  }
}
