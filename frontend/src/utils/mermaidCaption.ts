/**
 * Mermaid 图注生成 / Mermaid diagram caption generation
 *
 * 从 Mermaid 语法中解析节点与关系，生成洞察卡片的简洁图注。
 * 卡片不再复制 AI 对话全文——散文解释留在对话侧，卡片只保留图 + 结构图例，两者互补不重复。
 * Parse nodes/relations from Mermaid syntax to build a concise caption for insight cards.
 * The card no longer duplicates the chat reply: prose stays in chat, the card keeps diagram + structural legend.
 */

export interface MermaidEdge {
  from: string
  to: string
  label: string
}

export interface MermaidSummary {
  /** 图类型声明行（如 graph TD） / Diagram type declaration line (e.g. graph TD) */
  kind: string
  /** 节点 id → 标签 / Node id → label */
  nodes: Record<string, string>
  edges: MermaidEdge[]
}

/** 独立节点定义行：A[标签] / A(标签) / A{标签} / Standalone node definition line */
const NODE_DEF_RE = /^\s*(\w+)\s*[\[({]([^\])}]*)[\])}]/
/** 边定义行：A[标签] -->|关系| B[标签]，兼容 ==> / -.-> / --- / Edge line with optional node labels and edge label */
const EDGE_RE = /^\s*(\w+)\s*(?:[\[({]([^\])}]*)[\])}])?\s*(-{2,}>|={2,}>|-\.->|---)\s*(?:\|([^|]*)\|)?\s*(\w+)\s*(?:[\[({]([^\])}]*)[\])}])?/

/** 图例最多展示的关系条数 / Max relation lines shown in the caption */
const MAX_EDGE_LINES = 10

/**
 * 解析 Mermaid 代码为节点/关系摘要。解析失败时返回空摘要，调用方降级为仅统计行。
 * Parse Mermaid code into node/edge summary; returns empty summary on unparsable input.
 */
export function parseMermaid(code: string): MermaidSummary {
  const summary: MermaidSummary = { kind: '', nodes: {}, edges: [] }
  if (!code) return summary
  for (const raw of code.split('\n')) {
    const line = raw.trim()
    if (!line || line.startsWith('%%')) continue
    if (!summary.kind) {
      summary.kind = line
      continue
    }
    const edge = line.match(EDGE_RE)
    if (edge) {
      const [, from, fromLabel, , edgeLabel, to, toLabel] = edge
      if (fromLabel) summary.nodes[from] = fromLabel
      if (toLabel) summary.nodes[to] = toLabel
      if (!summary.nodes[from]) summary.nodes[from] = from
      if (!summary.nodes[to]) summary.nodes[to] = to
      summary.edges.push({ from, to, label: (edgeLabel || '').trim() })
      continue
    }
    const node = line.match(NODE_DEF_RE)
    if (node) summary.nodes[node[1]] = node[2]
  }
  return summary
}

/**
 * 生成卡片图注（Markdown）：首行类型+统计，其后为关系图例列表。
 * Build caption (Markdown): first line type + stats, followed by a relation legend list.
 */
export function buildDiagramCaption(
  code: string,
  t: (key: string, params?: Record<string, unknown>) => string
): string {
  const { kind, nodes, edges } = parseMermaid(code)
  const typeKey = kind.startsWith('sequence')
    ? 'diagram_type_sequence'
    : kind.startsWith('mindmap')
      ? 'diagram_type_mindmap'
      : kind.startsWith('gantt')
        ? 'diagram_type_gantt'
        : kind.startsWith('graph') || kind.startsWith('flowchart')
          ? 'diagram_type_flowchart'
          : 'diagram_type_generic'
  const head = t('ai-panel.insights.diagram_caption_stats', {
    type: t(`ai-panel.insights.${typeKey}`),
    nodes: Object.keys(nodes).length,
    edges: edges.length,
  })
  const lines: string[] = [`**${head}**`]
  const shown = edges.slice(0, MAX_EDGE_LINES)
  for (const e of shown) {
    const rel = e.label ? ` (${e.label})` : ''
    lines.push(`- ${nodes[e.from] || e.from} → ${nodes[e.to] || e.to}${rel}`)
  }
  if (edges.length > shown.length) {
    lines.push(t('ai-panel.insights.diagram_caption_more', { n: edges.length - shown.length }))
  }
  return lines.join('\n')
}
