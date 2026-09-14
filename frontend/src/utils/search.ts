/**
 * 会议搜索工具 — 统一的多维度任务匹配 / Meeting search utility — unified multi-dimension task matching
 *
 * 搜索维度（按成本从低到高排列，命中即短路）： / Search dimensions (by cost, ascending; short-circuit on hit):
 *   1. 标题 / 音频文件名 / Title / audio filename
 *   2. 纪要摘要 / Summary text
 *   3. 说话人名称（speaker_mapping 的值） / Speaker names (speaker_mapping values)
 *   4. 章节标题 / Chapter titles
 *   5. 待办事项文本 / Todo item text
 *   6. 转写全文（dialogue） / Full transcript (dialogue)
 */
import type { Task } from '@/api/types'

/**
 * 判断单个 Task 是否匹配搜索词。 / Check if a single Task matches the search query.
 * 空字符串直接返回 true（全量展示）。 / Empty string returns true (show all).
 */
export function matchTask(task: Task, q: string): boolean {
  if (!q) return true
  const lower = q.toLowerCase()

  // 1. 标题 / 音频名 / 1. Title / audio name
  if ((task.title || task.audio_name || '').toLowerCase().includes(lower)) return true

  // 2. 纪要 / 2. Summary
  if ((task.summary || '').toLowerCase().includes(lower)) return true

  // 3. 说话人名称 / 3. Speaker names
  const mapping = task.speaker_mapping
  if (mapping) {
    for (const name of Object.values(mapping)) {
      if (name && name.toLowerCase().includes(lower)) return true
    }
  }

  // 4. 章节标题 / 4. Chapter titles
  const chapters = task.chapters
  if (chapters) {
    for (const ch of chapters) {
      if (ch.title && ch.title.toLowerCase().includes(lower)) return true
    }
  }

  // 5. 待办事项 / 5. Todo items
  const todos = task.todos
  if (todos) {
    for (const td of todos) {
      if (td.text && td.text.toLowerCase().includes(lower)) return true
    }
  }

  // 6. 转写全文（最重，放最后） / 6. Full transcript (heaviest; last)
  const dialogue = task.dialogue
  if (dialogue) {
    for (const line of dialogue) {
      if (line.text && line.text.toLowerCase().includes(lower)) return true
    }
  }

  return false
}

/**
 * 将文本中匹配搜索词的部分用 <mark> 标签高亮。 / Highlight matched portions of text with <mark> tags.
 * 返回 HTML 字符串，供 v-html 使用。 / Returns HTML string for v-html.
 * 空搜索词直接返回原文（无标签）。 / Empty query returns original text (no tags).
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

/** HTML 特殊字符转义 / HTML special character escape */
function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
