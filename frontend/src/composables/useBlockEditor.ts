import { ref } from 'vue'
import { escapeHtml } from '@/utils/sanitize'

export interface MdBlock {
  source: string
  type: 'heading' | 'list' | 'blockquote' | 'hr' | 'paragraph'
  isAi: boolean
  index: number
}

function hasAiMarker(src: string): boolean {
  return /<!--\s*ai\s*-->/.test(src)
}

function cleanAiMarker(src: string): string {
  return src.replace(/<!--\s*ai\s*-->\s*/g, '').trim()
}

function classifyBlockSource(src: string): MdBlock['type'] {
  const trimmed = src.trim()
  if (/^#{1,3}\s+/.test(trimmed)) return 'heading'
  if (/^[-*]\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed)) return 'list'
  if (trimmed.startsWith('> ')) return 'blockquote'
  if (/^---+$/.test(trimmed)) return 'hr'
  return 'paragraph'
}

export function splitMdBlocks(md: string): MdBlock[] {
  const blocks: MdBlock[] = []
  const lines = md.split('\n')
  let i = 0
  while (i < lines.length) {
    const trimmed = lines[i].trim()
    if (trimmed === '') { i++; continue }
    let blockLines: string[] = []
    let type: MdBlock['type'] = 'paragraph'
    if (/^#{1,3}\s+/.test(trimmed)) {
      type = 'heading'
      blockLines = [lines[i]]
      i++
    } else if (/^[-*]\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed)) {
      type = 'list'
      while (i < lines.length && (/^[-*]\s+/.test(lines[i].trim()) || /^\d+\.\s+/.test(lines[i].trim()))) {
        blockLines.push(lines[i])
        i++
      }
    } else if (trimmed.startsWith('> ')) {
      type = 'blockquote'
      while (i < lines.length && lines[i].trim().startsWith('> ')) {
        blockLines.push(lines[i])
        i++
      }
    } else if (/^---+$/.test(trimmed)) {
      type = 'hr'
      blockLines = [lines[i]]
      i++
    } else {
      type = 'paragraph'
      blockLines = [lines[i]]
      i++
    }
    const source = blockLines.join('\n')
    blocks.push({ source, type, isAi: hasAiMarker(source), index: blocks.length })
  }
  return blocks
}

function renderBlockHtml(block: MdBlock): string {
  const clean = cleanAiMarker(block.source)
  let html = escapeHtml(clean)
    .replace(/```[\s\S]*?```/g, (m) => {
      // escapeHtml 已转义了反引号内的内容，此处重新包装 / escapeHtml already escaped code content; re-wrap here
      const inner = m.slice(3, -3).trim()
      return `<pre><code>${inner}</code></pre>`
    })
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^- \[x\] (.+)$/gm, '<li class="task-done">$1</li>')
    .replace(/^- \[ \] (.+)$/gm, '<li>$1</li>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    .replace(/^---$/gm, '<hr>')
  if (block.type === 'paragraph' && !html.startsWith('<')) {
    html = '<p>' + html.replace(/\n/g, '<br>') + '</p>'
  }
  return html
}

export function useBlockEditor(onChange?: (md: string) => void) {
  const blocks = ref<MdBlock[]>([])
  const editingIndex = ref<number | null>(null)

  function loadMarkdown(md: string) {
    blocks.value = splitMdBlocks(md)
    editingIndex.value = null
  }

  function getMarkdown(): string {
    return blocks.value.map(b => cleanAiMarker(b.source)).join('\n\n')
  }

  function enterEdit(idx: number) {
    editingIndex.value = idx
  }

  function exitEdit(idx: number, newSource: string) {
    const type = classifyBlockSource(newSource)
    const isAi = hasAiMarker(newSource)
    blocks.value[idx] = { source: newSource, type, isAi, index: idx }
    editingIndex.value = null
    if (onChange) onChange(getMarkdown())
  }

  function cancelEdit() {
    editingIndex.value = null
  }

  function updateBlock(idx: number, newSource: string) {
    const type = classifyBlockSource(newSource)
    const isAi = hasAiMarker(newSource)
    blocks.value[idx] = { source: newSource, type, isAi, index: idx }
    if (onChange) onChange(getMarkdown())
  }

  /** 在指定块内做文本替换 / Replace text within a specific block */
  function replaceTextInBlock(idx: number, oldText: string, newText: string) {
    const block = blocks.value[idx]
    if (!block) return
    const newSource = block.source.replace(oldText, newText)
    if (newSource !== block.source) {
      updateBlock(idx, newSource)
    }
  }

  function insertAfter(idx: number, source: string = ''): number {
    const newBlock: MdBlock = { source, type: classifyBlockSource(source), isAi: false, index: 0 }
    blocks.value.splice(idx + 1, 0, newBlock)
    // re-index / re-index
    for (let i = 0; i < blocks.value.length; i++) blocks.value[i].index = i
    if (onChange) onChange(getMarkdown())
    return idx + 1
  }

  function removeBlock(idx: number): number {
    blocks.value.splice(idx, 1)
    // re-index / re-index
    for (let i = 0; i < blocks.value.length; i++) blocks.value[i].index = i
    if (onChange) onChange(getMarkdown())
    return Math.max(0, idx - 1)
  }

  /** 将块内容转换为目标类型（strip 旧标记 + 加新标记） / Convert block content to target type (strip old markers + add new ones) */
  function convertBlock(idx: number, targetType: 'heading' | 'list' | 'paragraph') {
    const block = blocks.value[idx]
    if (!block) return
    // 去除现有类型标记 / Remove existing type markers
    let text = block.source
      .replace(/^#{1,3}\s+/gm, '')   // heading
      .replace(/^[-*]\s+/gm, '')     // unordered list
      .replace(/^\d+\.\s+/gm, '')    // ordered list
      .replace(/^>\s/gm, '')         // blockquote
    // 按目标类型添加新标记 / Add new markers by target type
    if (targetType === 'heading') {
      text = text.split('\n').map(l => l.trim() ? `## ${l}` : l).join('\n')
    } else if (targetType === 'list') {
      text = text.split('\n').map(l => l.trim() ? `- ${l}` : l).join('\n')
    }
    // paragraph: 不加标记 / paragraph: no markers added
    const newType = classifyBlockSource(text)
    blocks.value[idx] = { source: text, type: newType, isAi: block.isAi, index: idx }
    if (onChange) onChange(getMarkdown())
  }

  function renderBlock(block: MdBlock): string {
    return renderBlockHtml(block)
  }

  return {
    blocks,
    editingIndex,
    loadMarkdown,
    getMarkdown,
    enterEdit,
    exitEdit,
    cancelEdit,
    updateBlock,
    replaceTextInBlock,
    insertAfter,
    removeBlock,
    convertBlock,
    renderBlock,
  }
}
