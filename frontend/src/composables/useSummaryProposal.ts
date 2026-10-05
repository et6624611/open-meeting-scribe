/**
 * 纪要改写提案共享状态 / Summary proposal shared state
 *
 * 背景：useAiChat 每次调用创建独立 refs（非单例），AIPanel 与 GeneratingView
 * 双实例读不到同一份提案，因此「原位 diff 预览」（Layer 1）把提案状态下沉到
 * 本模块的模块级单例。提案生命周期仍由 useAiChat 驱动：propose_summary 工具调用
 * 置入、新一轮发送/任务切换清空；接受才经 saveSummary 落盘（提案式 diff 语义不变）。
 */
import { ref, computed, watch } from 'vue'
import { useTaskStore } from '@/stores/task'
import { saveSummary } from '@/api/notes'
import { useLayoutStore } from '@/stores/layout'
import { showToast } from '@/composables/useToast'
import { tt } from '@/i18n'
import { diffLines, diffStats, type DiffLine } from '@/utils/textDiff'

export interface SummaryProposal {
  baseline: string
  proposed: string
}

/** diff 行 + 原文行索引（渲染键） */
export interface DiffLineWithKey {
  /** 该行在 diff 序列中的索引 */
  key: number
  type: DiffLine['type']
  text: string
}

/** 渲染段：变更块（含上下文行）或可展开的无操作区间 */
export interface DiffSegment {
  kind: 'hunk' | 'gap'
  /** 全局唯一键（按输出序号编键） */
  key: number
  lines?: DiffLineWithKey[]
  /** gap 段：被省略的 same 行数与其在 diff 序列中的起始索引 */
  gapCount?: number
  gapStart?: number
  /** gap 段的展开登记键（= hunk 序号，尾部 gap 用 -1） */
  gapKey?: number
}

/* ─── 模块级单例状态 / Module-level singleton state ─── */
const summaryProposal = ref<SummaryProposal | null>(null)
const summaryPreviewMode = ref(false)
/** 原位预览中被用户展开的无操作区间（键 = hunk 序号，尾部 gap 用 -1） */
const expandedGaps = ref<Set<number>>(new Set())

/** 行级 diff 缓存（baseline → proposed），侧栏摘要与原位预览共用 */
const summaryProposalDiff = computed<DiffLine[]>(() => {
  const p = summaryProposal.value
  if (!p) return []
  return diffLines(p.baseline, p.proposed)
})

/** 提案规模摘要：变更块数 + 增/删行数（侧栏入口卡与原位预览条共用） */
const summaryProposalStats = computed(() => {
  const lines = summaryProposalDiff.value
  const { added, removed } = diffStats(lines)
  let hunks = 0
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].type !== 'same' && (i === 0 || lines[i - 1].type === 'same')) hunks++
  }
  return { hunks, added, removed }
})

/**
 * diff 行序列 → 渲染段列表（IDE diff 视图的常规形态）：
 * 相邻变更行合并为一个 hunk，hunk 之间距离 ≤ 2×context 时直接相连（上下文并入同一块），
 * 否则两侧各携带 context 行，中间归入可展开的「显示 N 行未修改」区间。
 */
export function buildDiffSegments(lines: DiffLine[], context = 3, expanded?: Set<number>): DiffSegment[] {
  const changed: number[] = []
  lines.forEach((l, i) => { if (l.type !== 'same') changed.push(i) })
  if (!changed.length) return []

  // 变更分组：把间距 ≤ 2*context 的变更行归为同一视觉块
  const groups: Array<[number, number]> = []  // [首变更, 尾变更]（闭区间）
  for (const idx of changed) {
    const last = groups[groups.length - 1]
    if (last && idx - last[1] <= context * 2 + 1) last[1] = idx
    else groups.push([idx, idx])
  }

  const out: DiffSegment[] = []
  let cursor = 0
  groups.forEach(([gStart, gEnd], gi) => {
    const from = Math.max(0, gStart - context)
    const to = Math.min(lines.length - 1, gEnd + context)
    const gapCount = from - cursor
    if (gapCount > 0) {
      const gapKey = gi
      if (expanded?.has(gapKey)) {
        out.push({ kind: 'hunk', key: out.length, lines: sliceLines(lines, cursor, from) })
      } else {
        out.push({ kind: 'gap', key: out.length, gapCount, gapStart: cursor, gapKey })
      }
    }
    out.push({ kind: 'hunk', key: out.length, lines: sliceLines(lines, from, to + 1) })
    cursor = to + 1
  })
  if (cursor < lines.length) {
    if (expanded?.has(-1)) {
      out.push({ kind: 'hunk', key: out.length, lines: sliceLines(lines, cursor, lines.length) })
    } else {
      out.push({ kind: 'gap', key: out.length, gapCount: lines.length - cursor, gapStart: cursor, gapKey: -1 })
    }
  }
  return out
}

function sliceLines(lines: DiffLine[], from: number, to: number): DiffLineWithKey[] {
  const out: DiffLineWithKey[] = []
  for (let i = from; i < to; i++) out.push({ key: i, type: lines[i].type, text: lines[i].text })
  return out
}

/** 原位预览的渲染段（随提案 diff 与展开状态派生） */
const summaryProposalSegments = computed<DiffSegment[]>(() =>
  buildDiffSegments(summaryProposalDiff.value, 3, expandedGaps.value),
)

/** 提案清空即退出预览并复位展开状态 */
watch(summaryProposal, (p) => {
  if (!p) {
    summaryPreviewMode.value = false
    expandedGaps.value = new Set()
  }
})

/** 新提案诞生：自动起跳到纪要 Tab 的原位预览（IDE 式“改动在哪就在哪确认”） */
watch(summaryProposal, (p) => {
  if (p) openSummaryPreview()
})

/**
 * 接受提案并落盘（唯一落盘点：PUT /summary + 本地乐观回写）。
 * baseline 漂移轻防护：提案产生后用户手动编辑过纪要时，仍保存提案全文但提示覆盖
 * 风险（Layer 2 逐 hunk 接受落地前，先保证不静默吞掉手动编辑）。
 */
async function acceptSummaryProposal(): Promise<boolean> {
  const p = summaryProposal.value
  const taskStore = useTaskStore()
  const taskId = taskStore.currentTaskId
  if (!p || !taskId) return false
  const ct = taskStore.currentTask as unknown as { user_summary?: string; summary?: string } | null
  const current = ct ? (ct.user_summary != null ? ct.user_summary : (ct.summary || '')) : ''
  const drifted = current !== p.baseline
  try {
    await saveSummary(taskId, p.proposed)
    // 乐观回写本地任务 → summaryMd watcher 触发 → 纪要面板即时刷新
    taskStore.patchTaskLocal(taskId, { user_summary: p.proposed } as never)
    summaryProposal.value = null
    showToast(tt(drifted ? 'ai-panel.summary_proposal_applied_drift' : 'ai-panel.summary_proposal_applied'), drifted ? 'warn' : 'success')
    return true
  } catch {
    showToast(tt('ai-panel.chat_error_prefix') + tt('ai-panel.summary_proposal_save_failed'), 'error')
    return false
  }
}

/** 拒绝提案：仅丢弃建议，不动数据（原位预览经 watch 自动退出） */
function rejectSummaryProposal() {
  summaryProposal.value = null
}

/** 切换某个无操作区间的展开/收起 */
function toggleGapExpanded(gapKey: number) {
  const s = new Set(expandedGaps.value)
  s.has(gapKey) ? s.delete(gapKey) : s.add(gapKey)
  expandedGaps.value = s
}

/** 起跳原位预览：切到纪要 Tab 并进入 diff 预览态（侧栏入口卡按钮调用） */
function openSummaryPreview() {
  if (!summaryProposal.value) return
  const layoutStore = useLayoutStore()
  layoutStore.pendingGenTab = 'summary'
  summaryPreviewMode.value = true
}

export function useSummaryProposal() {
  return {
    summaryProposal, summaryPreviewMode, expandedGaps,
    summaryProposalDiff, summaryProposalStats, summaryProposalSegments,
    acceptSummaryProposal, rejectSummaryProposal, openSummaryPreview, toggleGapExpanded,
    setSummaryProposal(v: SummaryProposal | null) { summaryProposal.value = v },
    clearSummaryProposal() { summaryProposal.value = null },
  }
}
