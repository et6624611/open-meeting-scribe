/**
 * 笔记 + 待办 API 封装
 */
import client from './client'
import type { TodoItem } from './types'

/** 获取笔记 */
export async function fetchNotes(taskId: string): Promise<string> {
  const { data } = await client.get<{ notes: string }>(`/api/tasks/${taskId}/notes`)
  return data.notes || ''
}

/** 保存笔记 */
export async function saveNotes(taskId: string, notes: string): Promise<void> {
  await client.put(`/api/tasks/${taskId}/notes`, { notes })
}

/** 获取待办列表 */
export async function fetchTodos(taskId: string): Promise<TodoItem[]> {
  const { data } = await client.get<{ todos: TodoItem[] }>(`/api/tasks/${taskId}/todos`)
  return data.todos || []
}

/** 切换待办完成状态 */
export async function toggleTodo(taskId: string, todoId: string, done: boolean): Promise<void> {
  await client.post(`/api/tasks/${taskId}/todos/${todoId}/toggle`, { done })
}

/** 新建待办 */
export async function createTodo(
  taskId: string,
  text: string,
  assignee?: string,
): Promise<TodoItem> {
  const { data } = await client.post<TodoItem>(`/api/tasks/${taskId}/todos`, { text, assignee })
  return data
}

/** 删除待办 */
export async function deleteTodo(taskId: string, todoId: string): Promise<void> {
  await client.delete(`/api/tasks/${taskId}/todos/${todoId}`)
}

/** 编辑待办 */
export async function updateTodo(
  taskId: string,
  todoId: string,
  patch: { text?: string; assignee?: string },
): Promise<void> {
  await client.put(`/api/tasks/${taskId}/todos/${todoId}`, patch)
}
