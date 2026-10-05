/**
 * useNotesProposal.ts — 随记改写提案（提案式 diff）共享状态
 * Notes rewrite proposal (proposal-style diff) shared state
 *
 * 背景（PROPOSAL-AGENT-REWRITE-CHANNEL §5.3 随记特殊口径）：`user_notes` 是**用户原创区**，
 * 与纪要（AI 产物）性质不同，因此 AI 侧的随记改写不做同构的直接写回，而走建议模式：
 * `propose_notes` 工具只产出建议正文（后端不落盘），前端在随记 Tab 原位展示旧/新行级 diff，
 * 用户点「接受」才经 `PUT /api/tasks/{id}/notes` 落盘、「拒绝」则丢弃。
 * 与 useSummaryProposal 同一交互语义（IDE 式锁定编辑 + 文内操作条），diff 计算复用其 buildDiffSegments。
 */
import { ref, computed, watch } from 'vue'
import { useTaskStore } from '@/stores/task'
import { useLayoutStore } from '@/stores/layout'
import { fetchNotes, saveNotes } from '@/api/notes'
import { showToast } from '@/composables/useToast'
import { tt } from '@/i18n'
import { diffLines, diffStats } from '@/utils/textDiff'
import { buildDiffSegments, type DiffSegment } from '@/composables/useSummaryProposal'
import { notifyTaskWritten } from '@/composables/useTaskWrites'

export interface NotesProposal {
  baseline: string
  proposed: string
}

/* ─── 模块级单例状态 / Module-level singleton state ─── */
const notesProposal = ref<NotesProposal | null>(null)
const notesPreviewMode = ref(false)
/** 原位预览中被用户展开的无操作区间（键 = hunk 序号，尾部 gap 用 -1） */
const expandedGaps = ref<Set<number>>(new Set())

/** 行级 diff 缓存（baseline → proposed） */
const notesProposalDiff = computed(() => {
  const p = notesProposal.value
  return p ? diffLines(p.baseline, p.proposed) : []
})

/** 提案规模摘要：变更块数 + 增/删行数 */
const notesProposalStats = computed(() => {
  const lines = notesProposalDiff.value
  const { added, removed } = diffStats(lines)
  let hunks = 0
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].type !== 'same' && (i === 0 || lines[i - 1].type === 'same')) hunks++
  }
  return { hunks, added, removed }
})

/** 原位预览的渲染段（随提案 diff 与展开状态派生） */
const notesProposalSegments = computed<DiffSegment[]>(() =>
  buildDiffSegments(notesProposalDiff.value, 3, expandedGaps.value),
)

/** 提案清空即退出预览并复位展开状态 */
watch(notesProposal, (p) => {
  if (!p) {
    notesPreviewMode.value = false
    expandedGaps.value = new Set()
  }
})

/** 新提案诞生：自动起跳到随记 Tab 的原位预览（改动在哪就在哪确认） */
watch(notesProposal, (p) => {
  if (p) openNotesPreview()
})

/** 起跳原位预览：切到随记 Tab 并进入 diff 预览态 */
function openNotesPreview() {
  if (!notesProposal.value) return
  useLayoutStore().pendingGenTab = 'notes'
  notesPreviewMode.value = true
}

/** 切换某个无操作区间的展开/收起 */
function toggleNotesGapExpanded(gapKey: number) {
  const s = new Set(expandedGaps.value)
  s.has(gapKey) ? s.delete(gapKey) : s.add(gapKey)
  expandedGaps.value = s
}

/**
 * 接受提案并落盘（唯一落盘点：PUT /notes）。
 *
 * 基线漂移轻防护：提案产生后用户又手改过随记时，仍保存提案全文但提示覆盖风险
 * （随记是用户原创区，静默吞掉手改内容是不可接受的）。
 * 成功后广播 task-written(notes)，让呈现侧（含本 Tab）以服务端为准刷新。
 */
async function acceptNotesProposal(): Promise<boolean> {
  const p = notesProposal.value
  const taskStore = useTaskStore()
  const taskId = taskStore.currentTaskId
  if (!p || !taskId) return false
  let drifted = false
  try {
    const current = await fetchNotes(taskId)
    drifted = (current || '') !== p.baseline
  } catch { /* 漂移探测失败按未漂移处理，不阻断接受 */ }
  try {
    await saveNotes(taskId, p.proposed)
    notesProposal.value = null
    notifyTaskWritten({ domains: ['notes'] })
    showToast(tt(drifted ? 'ai-panel.notes_proposal_applied_drift' : 'ai-panel.notes_proposal_applied'),
              drifted ? 'warn' : 'success')
    return true
  } catch {
    showToast(tt('ai-panel.chat_error_prefix') + tt('ai-panel.notes_proposal_save_failed'), 'error')
    return false
  }
}

/** 拒绝提案：仅丢弃建议，不动数据（原位预览经 watch 自动退出） */
function rejectNotesProposal() {
  notesProposal.value = null
}

export function useNotesProposal() {
  return {
    notesProposal, notesPreviewMode,
    notesProposalStats, notesProposalSegments,
    acceptNotesProposal, rejectNotesProposal, openNotesPreview, toggleNotesGapExpanded,
    clearNotesProposal() { notesProposal.value = null },
  }
}
