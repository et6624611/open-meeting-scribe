/**
 * useBoardProposal.ts — 洞察板「建板提案」共享状态 / Board-creation proposal shared state
 *
 * 背景（回归原始 HTML 方案 §6.5）：一场会议可以有多份板，但**建板权属于用户**。
 * `create_insight_board` 工具是提案（persists=False，后端不落盘），这里把提案挂成
 * 会话侧确认卡；用户点「接受」才经 POST /api/insights/board/{task_id}/boards 建板
 * ——与随记/纪要的 propose_* 通道同一产品姿态：AI 保留提议权，执行权在用户手上。
 *
 * 与 useSummaryProposal/useNotesProposal 的差别：板没有"原文可原位 diff"，
 * 因此确认卡留在侧栏（内容就是「新建一份板 + 标题 + 理由」），不做起跳预览。
 */
import { ref } from 'vue'
import { createBoard } from '@/api/board'
import { notifyBoardsChanged } from '@/composables/useBoardSync'
import { useTaskStore } from '@/stores/task'
import { showToast } from '@/composables/useToast'
import { tt } from '@/i18n'

export interface BoardProposal {
  /** 期望的板 id；空串表示由服务端生成 board-2/board-3… */
  board_id: string
  title: string
  reason: string
}

/* ─── 模块级单例状态 / Module-level singleton state ─── */
const boardProposal = ref<BoardProposal | null>(null)

/** 接受提案并建板（唯一落盘点：POST .../boards，source=proposal 供审计区分通道） */
async function acceptBoardProposal(): Promise<boolean> {
  const p = boardProposal.value
  const taskStore = useTaskStore()
  const taskId = taskStore.currentTaskId
  if (!p || !taskId) return false
  try {
    const created = await createBoard(taskId, p.title, p.board_id || undefined)
    boardProposal.value = null
    notifyBoardsChanged({ board_id: created.board_id })
    showToast(tt('ai-panel.board_proposal_applied'), 'success')
    return true
  } catch {
    showToast(tt('ai-panel.chat_error_prefix') + tt('ai-panel.board_proposal_failed'), 'error')
    return false
  }
}

/** 拒绝提案：只丢弃建议，不建板、不动已有板 */
function rejectBoardProposal() {
  boardProposal.value = null
}

export function useBoardProposal() {
  return {
    boardProposal,
    acceptBoardProposal, rejectBoardProposal,
    clearBoardProposal() { boardProposal.value = null },
  }
}
