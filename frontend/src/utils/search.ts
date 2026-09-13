/**
 * 会议搜索工具 — 统一的多维度任务匹配
 *
 * 搜索维度（按成本从低到高排列，命中即短路）：
 *   1. 标题 / 音频文件名
 *   2. 纪要摘要
 *   3. 说话人名称（speaker_mapping 的值）
 *   4. 章节标题
 *   5. 待办事项文本
 *   6. 转写全文（dialogue）
 */
import type { Task } from '@/api/types'

/**
 * 判断单个 Task 是否匹配搜索词。
 * 空字符串直接返回 true（全量展示）。
 */
export function matchTask(task: Task, q: string): boolean {
  if (!q) return true
  const lower = q.toLowerCase()

  // 1. 标题 / 音频名
  if ((task.title || task.audio_name || '').toLowerCase().includes(lower)) return true

  // 2. 纪要
  if ((task.summary || '').toLowerCase().includes(lower)) return true

  // 3. 说话人名称
  const mapping = task.speaker_mapping
  if (mapping) {
    for (const name of Object.values(mapping)) {
      if (name && name.toLowerCase().includes(lower)) return true
    }
  }

  // 4. 章节标题
  const chapters = task.chapters
  if (chapters) {
    for (const ch of chapters) {
      if (ch.title && ch.title.toLowerCase().includes(lower)) return true
    }
  }

  // 5. 待办事项
  const todos = task.todos
  if (todos) {
    for (const td of todos) {
      if (td.text && td.text.toLowerCase().includes(lower)) return true
    }
  }

  // 6. 转写全文（最重，放最后）
  const dialogue = task.dialogue
  if (dialogue) {
    for (const line of dialogue) {
      if (line.text && line.text.toLowerCase().includes(lower)) return true
    }
  }

  return false
}

/**
 * 将文本中匹配搜索词的部分用 <mark> 标签高亮。
 * 返回 HTML 字符串，供 v-html 使用。
 * 空搜索词直接返回原文（无标签）。
 */
export function highlightText(text: string, q: string): string {
  if (!q || !text) return escapeHtml(text)
  const lower = text.toLowerCase()
  const ql = q.toLowerCase()
  const idx = lower.indexOf(ql)
  if (idx < 0) return escapeHtml(text)
  const before = text.slice(0, idx)
  const match = text.slice(idx, idx + q.length)
  const after = text.slice(idx + q.length)
  return escapeHtml(before) + '<mark>' + escapeHtml(match) + '</mark>' + escapeHtml(after)
}

/** HTML 特殊字符转义 */
function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
