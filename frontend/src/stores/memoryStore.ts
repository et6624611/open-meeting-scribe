/**
 * 长期记忆状态 / Long-term memory state
 *
 * 列表、筛选、选中与乐观更新。写入一律走后端 REST，本层不拼接条目字段。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  acceptMemory,
  closeMemory,
  createMemory,
  deleteMemory,
  exportMemory,
  fetchMemoryStats,
  listMemory,
  rejectMemory,
  reopenMemory,
  updateMemory,
  type MemoryCreatePayload,
  type MemoryItem,
  type MemoryKind,
  type MemoryStats,
  type MemoryView,
} from '@/api/memory'

const EMPTY_STATS: MemoryStats = {
  open: 0, closed: 0, proposed: 0, archived: 0, deleted: 0, total: 0,
}

export type MemoryDraft =
  | { mode: 'new' }
  | { mode: 'edit'; id: string }

function matchesView(item: MemoryItem, view: MemoryView): boolean {
  if (view === 'open') return item.status === 'active' && !item.valid_to
  if (view === 'closed') return item.status === 'active' && !!item.valid_to
  return item.status === view
}

export const useMemoryStore = defineStore('memory', () => {
  const items = ref<MemoryItem[]>([])
  const stats = ref<MemoryStats>({ ...EMPTY_STATS })
  const view = ref<MemoryView>('open')
  const namespace = ref('')
  const kind = ref<MemoryKind | ''>('')
  const query = ref('')
  const cursor = ref<string | null>(null)
  const hasMore = ref(false)
  const loading = ref(false)
  const loadingMore = ref(false)
  const error = ref('')
  const selectedId = ref<string | null>(null)
  const draft = ref<MemoryDraft | null>(null)

  const selected = computed(() => items.value.find(it => it.id === selectedId.value) || null)
  const isEmpty = computed(() => !loading.value && !error.value && items.value.length === 0)

  let loadSeq = 0

  function select(id: string | null) {
    selectedId.value = id
    if (id) draft.value = null
  }

  async function loadStats() {
    try {
      stats.value = await fetchMemoryStats()
    } catch {
      /* 统计失败不阻断列表 */
    }
  }

  async function load() {
    const seq = ++loadSeq
    loading.value = true
    error.value = ''
    try {
      const result = await listMemory({
        view: view.value,
        namespace: namespace.value || undefined,
        kind: kind.value || undefined,
        q: query.value.trim() || undefined,
        limit: 50,
      })
      if (seq !== loadSeq) return
      items.value = result.items
      cursor.value = result.next_cursor
      hasMore.value = !!result.next_cursor
      if (selectedId.value && !items.value.some(it => it.id === selectedId.value)) {
        selectedId.value = items.value[0]?.id || null
      }
      if (!selectedId.value && items.value.length) selectedId.value = items.value[0].id
    } catch (err) {
      if (seq === loadSeq) error.value = (err as Error)?.message || 'load_failed'
    } finally {
      if (seq === loadSeq) loading.value = false
    }
  }

  async function loadMore() {
    if (!hasMore.value || loadingMore.value) return
    loadingMore.value = true
    try {
      const result = await listMemory({
        view: view.value,
        namespace: namespace.value || undefined,
        kind: kind.value || undefined,
        q: query.value.trim() || undefined,
        cursor: cursor.value,
        limit: 50,
      })
      const seen = new Set(items.value.map(it => it.id))
      items.value = [...items.value, ...result.items.filter(it => !seen.has(it.id))]
      cursor.value = result.next_cursor
      hasMore.value = !!result.next_cursor
    } catch (err) {
      error.value = (err as Error)?.message || 'load_failed'
    } finally {
      loadingMore.value = false
    }
  }

  /** 本地改条目；不再满足当前视图时移出列表并顺延选中。 */
  function applyLocal(id: string, patch: Partial<MemoryItem>) {
    const index = items.value.findIndex(it => it.id === id)
    if (index < 0) return
    const next = { ...items.value[index], ...patch }
    if (matchesView(next, view.value)) {
      items.value.splice(index, 1, next)
      return
    }
    items.value.splice(index, 1)
    if (selectedId.value === id) {
      selectedId.value = items.value[index]?.id || items.value[index - 1]?.id || null
    }
  }

  async function create(payload: MemoryCreatePayload) {
    const item = await createMemory(payload)
    view.value = 'open'
    await Promise.all([load(), loadStats()])
    selectedId.value = item.id
    draft.value = null
    return item
  }

  async function update(id: string, patch: Partial<MemoryItem>) {
    const item = await updateMemory(id, patch)
    const index = items.value.findIndex(it => it.id === id)
    if (index >= 0) items.value.splice(index, 1, item)
    draft.value = null
    await loadStats()
    return item
  }

  async function close(id: string) {
    const item = await closeMemory(id)
    applyLocal(id, item)
    await loadStats()
    return item
  }

  async function reopen(id: string) {
    const item = await reopenMemory(id)
    applyLocal(id, item)
    await loadStats()
    return item
  }

  async function remove(id: string) {
    const item = await deleteMemory(id)
    applyLocal(id, item)
    await loadStats()
    return item
  }

  async function accept(id: string) {
    const item = await acceptMemory(id)
    applyLocal(id, item)
    await loadStats()
    return item
  }

  async function reject(id: string) {
    const item = await rejectMemory(id)
    applyLocal(id, item)
    await loadStats()
    return item
  }

  async function exportAll() {
    const { blob, filename } = await exportMemory()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  }

  return {
    items, stats, view, namespace, kind, query, cursor, hasMore,
    loading, loadingMore, error, selectedId, draft, selected, isEmpty,
    loadStats, load, loadMore, select, create, update, close, reopen,
    remove, accept, reject, exportAll,
  }
})
