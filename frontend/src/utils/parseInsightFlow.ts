/**
 * 洞察台画布解析器 / Insight Deck canvas parser
 *
 * 将「受约束 Mermaid」（洞察台画布书写规范）解析为 workflow 阶段卡内部结构，
 * 供 InsightFlow.vue 自绘 DOM 卡片 + SVG 直角连线。
 * Parse constrained Mermaid (Insight Deck canvas writing spec) into the workflow
 * phase-card structure consumed by InsightFlow.vue (DOM cards + SVG right-angle wires).
 *
 * 任何违反书写规范的输入一律返回 null —— 调用方据此降级为通用 MermaidDiagram 渲染。
 * Any spec violation returns null — the caller falls back to generic MermaidDiagram rendering.
 */

/** 画布步骤芯片 / Canvas step chip */
export interface InsightStep {
  /** 剥离 @@ 标记后的步骤标题 / Step label with the @@ marker stripped */
  label: string
  /** 转写定位时间（毫秒），0 表示无 / Transcript seek time (ms), 0 means none */
  beginTime: number
}

/** 画布阶段卡 / Canvas phase card */
export interface InsightPhase {
  id: string
  /** 阶段名（来自 subgraph 标题） / Phase name (from subgraph title) */
  title: string
  /** 阶段描述（由调用方经 matchPhaseDescriptions 填入） / Phase description (filled by matchPhaseDescriptions) */
  desc?: string
  steps: InsightStep[]
}

/** 阶段级连线（聚合后） / Aggregated phase-level link */
export interface InsightLink {
  from: string
  to: string
}

/** 解析产物 / Parser output */
export interface InsightFlowData {
  phases: InsightPhase[]
  links: InsightLink[]
}

/* ─── 规范常量（与提示词「洞察台画布书写规范」一致） / Spec constants (aligned with the prompt's canvas writing rules) ─── */
const MAX_PHASES = 5
const MIN_PHASES = 2
const MAX_STEPS_PER_PHASE = 4
const MAX_TOTAL_NODES = 12
const MAX_PHASE_TITLE_LEN = 6
const MAX_STEP_LABEL_LEN = 14

/** subgraph 行：subgraph S1["数据核对"] / subgraph S1[数据核对]（引号推荐但实践中常缺失，两种都收） */
const SUBGRAPH_RE = /^subgraph\s+S(?<num>\d+)\s*\[\s*(?:(?<q>"[^"]*")|(?<bare>[^\]]+))\s*\]$/
/** 节点声明行：S1a["拉取费控数据 @@84000"] 或无引号变体 / node line, quoted or bare label */
const NODE_RE = /^(?<id>S\d+[a-z])\s*\[\s*(?:(?<q>"[^"]*")|(?<bare>[^\]]+))\s*\]$/
/** 连线行（允许形式：--- 与 -.->；两侧可带引号/裸标签定义，允许行内尾注释）
    Link line (--- or -.-> tolerated as undirected edge; either side may carry a label) */
const LINK_RE = /^(S\d+[a-z])(?:\s*\[\s*(?:"[^"]*"|[^\]]+)\s*\])?\s+(?:---+|-\.->+|-\.-+>)\s+(S\d+[a-z])(?:\s*\[\s*(?:"[^"]*"|[^\]]+)\s*\])?\s*(?:%%.*)?$/
/** 标签尾部时间标记（允许模型把 @@ 写成 @ 简写；仅剥离末尾一处）
    Trailing @@ time marker (single @ tolerated as model typo; stripped only once) */
const TIME_MARKER_RE = /\s@{1,2}(\d+)$/
/** 真正的箭头连线语法（--> / ==>）：规范禁止；-.-> 除外（见 LINK_RE）
    Forbidden arrow syntax (--> / ==>); -.-> is intentionally tolerated */
const FORBID_ARROW_RE = /(?<!\.)-{2,}>|=+>/

/** 去掉行内引号串，得到纯语法骨架（标签内的 → 等字符不参与连线判定）
    Strip quoted spans so label contents never affect syntax checks */
function skeleton(line: string): string {
  return line.replace(/"[^"]*"/g, '"x"')
}

/**
 * 解析受约束 Mermaid 文本。
 * Parse constrained Mermaid text.
 * @returns 合法时返回阶段结构；任何不规范输入返回 null（触发降级）
 */
export function parseInsightFlow(mermaid: string): InsightFlowData | null {
  if (!mermaid || !mermaid.trim()) return null

  const lines = mermaid
    .split('\n')
    .map(l => l.trim())
    .filter(l => l.length > 0 && !l.startsWith('%%'))

  // 方向固定 flowchart LR（允许 %%{init}%% 等指令行在前）
  // Direction must be exactly `flowchart LR` (directive lines like %%{init}%% allowed before)
  const headerIdx = lines.findIndex(l => /^(flowchart|graph)\s/.test(l))
  if (headerIdx === -1) return null
  if (!/^flowchart\s+LR$/.test(lines[headerIdx])) return null

  const phases = new Map<string, InsightPhase>()
  const nodePhase = new Map<string, string>()
  const links: Array<[string, string]> = []
  let currentPhase: string | null = null

  for (const rawLine of lines.slice(headerIdx + 1)) {
    // 允许行尾 %% 注释 / tolerate trailing %% comments
    const line = rawLine.replace(/\s*%%.*$/, '').trim()
    if (!line) continue
    if (line === 'end') {
      currentPhase = null
      continue
    }

    // 禁止真箭头语法（--> / ==>）；-.-> 宽容接受为无向连线；引号内内容不参与判定
    // Forbidden arrows checked on the syntax skeleton; -.-> is tolerated
    if (FORBID_ARROW_RE.test(skeleton(line))) return null

    const sg = line.match(SUBGRAPH_RE)
    if (sg?.groups) {
      if (currentPhase) return null // 嵌套 subgraph 非法 / nested subgraph is illegal
      const id = `S${sg.groups.num}`
      const title = (sg.groups.q ?? sg.groups.bare).replace(/^"|"$/g, '').trim()
      if (!title || title.length > MAX_PHASE_TITLE_LEN) return null
      if (phases.has(id)) return null // 重复阶段 ID / duplicate phase id
      phases.set(id, { id, title, steps: [] })
      currentPhase = id
      continue
    }

    const nd = line.match(NODE_RE)
    if (nd?.groups) {
      if (!currentPhase) return null // 裸节点（subgraph 之外）非法 / node outside any subgraph
      const id: string = nd.groups.id
      // 节点 ID 前缀必须匹配所属阶段（S1 内只允许 S1a/S1b…） / node id prefix must match its phase
      if (!id.startsWith(currentPhase)) return null
      // 引号形式取去引号后的 q 组，裸标签取 bare 组 / quoted path strips quotes, bare path uses raw text
      const rawLabel: string = (nd.groups.q ?? nd.groups.bare ?? '').replace(/^"|"$/g, '').trim()
      const m = rawLabel.match(TIME_MARKER_RE)
      const beginTime = m ? parseInt(m[1], 10) : 0
      const label = (m ? rawLabel.slice(0, m.index) : rawLabel).trim()
      if (!label) return null
      if (nodePhase.has(id)) return null // 重复节点 ID / duplicate node id
      // 超长标签截断而非降级（芯片本身单行省略号展示） / over-long labels truncate, never degrade
      phases.get(currentPhase)!.steps.push({
        label: label.length > MAX_STEP_LABEL_LEN ? label.slice(0, MAX_STEP_LABEL_LEN) : label,
        beginTime,
      })
      nodePhase.set(id, currentPhase)
      continue
    }

    const lk = line.match(LINK_RE)
    if (lk) {
      links.push([lk[1], lk[2]])
      continue
    }

    // 无法识别的语法一律视为不规范 → 降级 / Anything unrecognized violates the spec → degrade
    return null
  }

  if (currentPhase) return null // subgraph 未闭合 / unclosed subgraph block
  if (phases.size < MIN_PHASES || phases.size > MAX_PHASES) return null

  let totalNodes = 0
  for (const p of phases.values()) {
    if (p.steps.length < 1 || p.steps.length > MAX_STEPS_PER_PHASE) return null
    totalNodes += p.steps.length
  }
  if (totalNodes > MAX_TOTAL_NODES) return null

  // 连线校验 + 聚合为阶段级连线 / Validate links and aggregate to phase level
  const aggregated: InsightLink[] = []
  const seen = new Set<string>()
  for (const [from, to] of links) {
    const fp = nodePhase.get(from)
    const tp = nodePhase.get(to)
    if (!fp || !tp) return null // 连线引用未定义节点 / link references undefined node
    if (fp === tp) return null // 阶段内连线违反规范 / intra-phase link violates the spec
    const key = `${fp}->${tp}`
    if (!seen.has(key)) {
      seen.add(key)
      aggregated.push({ from: fp, to: tp })
    }
  }

  return { phases: [...phases.values()], links: aggregated }
}

/**
 * 从图注正文匹配各阶段描述：
 * 1. 「阶段名：一句话」精确匹配；
 * 2. 兼容模型把占位符原样拄抄的「阶段名：xxx」序列写法——按阶段顺序依次分配。
 * Match per-phase descriptions: exact "PhaseName: sentence" lines, plus a positional
 * fallback for the literal "阶段名：…" placeholder form the model sometimes copies verbatim.
 * 匹配不到的阶段保持无描述（合法降级）。Returns the same phases array for chaining.
 */
export function matchPhaseDescriptions(
  phases: InsightPhase[],
  body: string | undefined | null
): InsightPhase[] {
  if (!body || phases.length === 0) return phases
  // 记录已消费的阶段，避免同名重复覆盖 / track first match per phase
  const used = new Set<string>()
  const placeholderRe = /^阶段名\s*[：:]\s*(.+)$/
  let phCursor = 0
  const bodyHasExactNames = phases.some(p =>
    new RegExp(`^${escapeRegExp(p.title)}\s*[：:]`, 'm').test(body)
  )
  for (let raw of body.split('\n')) {
    // 兼容单行内多条「xxx：yyy。」拼接（仅在句末标点后接空白处切分，不打断句内句号）
    // Tolerate multiple entries squeezed onto one line: split only at sentence-end + whitespace
    for (const line of raw.split(/(?<=[。；;])\s+(?=\S)/)) {
      const text = line.replace(/^[-*•>\s]+/, '').trim()
      if (!text) continue
      for (const p of phases) {
        if (used.has(p.id)) continue
        const m = text.match(new RegExp(`^${escapeRegExp(p.title)}\\s*[：:]\\s*(.+)$`))
        if (m) {
          p.desc = m[1].trim()
          used.add(p.id)
          break
        }
      }
      // 占位符序列写法：仅在正文没有任何精确阶段名时启用，避免误配
      // Positional placeholder mode: only when no exact phase names exist in body
      if (!bodyHasExactNames) {
        const pm = text.match(placeholderRe)
        if (pm) {
          while (phCursor < phases.length && used.has(phases[phCursor].id)) phCursor++
          if (phCursor < phases.length) {
            phases[phCursor].desc = pm[1].trim()
            used.add(phases[phCursor].id)
            phCursor++
          }
        }
      }
    }
  }
  return phases
}

/** 毫秒数格式化为 mm:ss（超过 1 小时进 h:mm:ss） / Format ms as mm:ss (h:mm:ss beyond one hour) */
export function formatFlowTime(ms: number): string {
  const totalSec = Math.floor(ms / 1000)
  const h = Math.floor(totalSec / 3600)
  const min = Math.floor((totalSec % 3600) / 60)
  const sec = totalSec % 60
  const mm = String(min).padStart(2, '0')
  const ss = String(sec).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
