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
import { isPlaceholderName } from '@/utils/speakerDisplay'

/** 「未识别」搜索词（中英）命中含占位/空名任务的行为口径（设计稿 §4-L9） */
const UNID_QUERY_RE = /^\s*(未识别| unidentified|unid)\s*$/i

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
  // L9：占位串不作为可搜索文本（搜 Speaker/说话人N 不再命中占位任务）；
  // 搜「未识别」命中含任意占位/空名的任务。
  const mapping = task.speaker_mapping
  if (mapping) {
    const values = Object.values(mapping)
    if (UNID_QUERY_RE.test(lower)) {
      if (values.some(isPlaceholderName)) return true
    }
    for (const name of values) {
      if (isPlaceholderName(name)) continue
      if (name.toLowerCase().includes(lower)) return true
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
 * 判断搜索词是否命中「标题 / 音频名」维度。 / Check whether the query hits the title / audio-name dimension.
 * 用于区分「标题命中」与「靠纪要/转写等内容命中」，供来源标识展示。空词返回 true。
 */
export function matchesTitle(task: Task, q: string): boolean {
  if (!q) return true
  const lower = q.toLowerCase()
  return (task.title || task.audio_name || '').toLowerCase().includes(lower)
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
