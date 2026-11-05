import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { listBoards, loadBoard, loadBoardMeta, openBoardInBrowser, type BoardArtifact, type BoardSummary } from '@/api/board'
import { notifyBoardsChanged, onBoardWritten, onBoardsChanged } from '@/composables/useBoardSync'
import { showToast } from '@/composables/useToast'

export function useInsightBoardPolling(opts: {
  taskId: string
  activeTab: ReturnType<typeof ref<string>>
  dotClass: (tabId: string) => string
}) {
  const { t } = useI18n()
  const BOARD_POLL_MS = 10_000

  const board = ref<BoardArtifact>({ html: null, revision: 0, updated_at: null })
  const boards = ref<BoardSummary[]>([])
  const activeBoardId = ref('')
  const boardFetched = ref(false)
  const boardLoading = ref(false)
  const boardDirty = ref(false)

  let boardPollTimer: ReturnType<typeof setInterval> | null = null
  let boardSig = ''

  function boardSignature(bs: BoardSummary[]): string {
    return bs.map(b => `${b.board_id}:${b.revision}`).join('|')
  }

  function onTabHover(tabId: string) {
    if (tabId === 'insights' && !boardFetched.value && !boardLoading.value) loadBoardData()
  }

  function tabDotClass(tabId: string): string {
    const base = opts.dotClass(tabId)
    if (tabId === 'insights') return board.value.html ? 'is-done' : base
    return base
  }

  async function loadBoardData() {
    boardFetched.value = true
    boardLoading.value = true
    try {
      const manifest = await listBoards(opts.taskId)
      boards.value = manifest.boards
      boardSig = boardSignature(manifest.boards)
      if (!activeBoardId.value || !manifest.boards.some(b => b.board_id === activeBoardId.value)) {
        activeBoardId.value = manifest.default_board_id || 'main'
      }
      board.value = await loadBoard(opts.taskId, activeBoardId.value)
    } catch {
      /* load failure silent */
    } finally {
      boardLoading.value = false
    }
  }

  async function probeBoardRevision() {
    if (boardLoading.value || document.hidden) return
    try {
      const meta = await loadBoardMeta(opts.taskId)
      const list = meta.boards || []
      const sig = boardSignature(list)
      const current = list.find(b => b.board_id === activeBoardId.value)
      const changed = sig !== boardSig
      boardSig = sig
      if (list.length) boards.value = list
      if (changed && (!current || current.board_id !== activeBoardId.value)) {
        activeBoardId.value = meta.default_board_id || list[0]?.board_id || 'main'
      }
      if (changed || (meta.exists && !board.value.html)) await loadBoardData()
    } catch { /* probe failure silent */ }
  }

  function startBoardPolling() {
    stopBoardPolling()
    boardPollTimer = setInterval(probeBoardRevision, BOARD_POLL_MS)
  }

  function stopBoardPolling() {
    if (boardPollTimer) { clearInterval(boardPollTimer); boardPollTimer = null }
  }

  function onBoardSwitch(bid: string) {
    if (!bid || bid === activeBoardId.value) return
    activeBoardId.value = bid
    board.value = { html: null, revision: 0, updated_at: null, board_id: bid }
    void loadBoardData()
  }

  async function onBoardCreate(title: string) {
    try {
      // lazy import to avoid circular dep with @/api/board — actually direct import above; createBoard from api/board
      const { createBoard } = await import('@/api/board')
      const created = await createBoard(opts.taskId, title, undefined, 'ui')
      activeBoardId.value = created.board_id
      await loadBoardData()
      notifyBoardsChanged({ board_id: created.board_id })
      showToast(t('generating.insights.board.toast_created', { title: created.title }), 'success')
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail?.message
      showToast(msg || t('generating.insights.board.toast_create_failed'), 'error')
    }
  }

  async function onBoardOpenInBrowser() {
    try {
      const ok = await openBoardInBrowser(opts.taskId, activeBoardId.value, board.value.revision)
      if (!ok) showToast(t('generating.insights.board.toast_open_failed'), 'warn')
    } catch {
      showToast(t('generating.insights.board.toast_open_failed'), 'error')
    }
  }

  // Tab 切换联动
  watch(opts.activeTab, (tab) => {
    if (tab === 'insights') {
      if (!boardFetched.value || boardDirty.value) loadBoardData()
      boardDirty.value = false
      startBoardPolling()
    } else {
      stopBoardPolling()
    }
  }, { immediate: true })

  // 落板信号
  const cleanup: Array<() => void> = []
  function bindSignals() {
    cleanup.push(onBoardWritten((detail) => {
      if (detail.board_id && activeBoardId.value && detail.board_id !== activeBoardId.value) return
      if (opts.activeTab.value === 'insights') probeBoardRevision()
      else boardDirty.value = true
    }))
    cleanup.push(onBoardsChanged(() => {
      if (opts.activeTab.value === 'insights') probeBoardRevision()
      else boardDirty.value = true
    }))
  }
  function bindVisibilityChange() {
    const h = () => { if (!document.hidden && opts.activeTab.value === 'insights') probeBoardRevision() }
    document.addEventListener('visibilitychange', h)
    cleanup.push(() => document.removeEventListener('visibilitychange', h))
  }

  function dispose() {
    stopBoardPolling()
    cleanup.forEach(fn => fn())
    cleanup.length = 0
  }

  return {
    board, boards, activeBoardId, boardLoading, boardFetched, boardDirty,
    loadBoardData,
    onTabHover, tabDotClass,
    onBoardSwitch, onBoardCreate, onBoardOpenInBrowser,
    bindSignals, bindVisibilityChange, dispose,
  }
}
