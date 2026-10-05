/**
 * 热词管理 composable / Hotword management composable
 * 管理词条 CRUD、搜索筛选、自动保存 / Manages item CRUD, search filtering, auto-save
 */
import { ref, computed } from 'vue'
import { fetchHotwords, saveHotwords, fetchHotwordMappings, saveHotwordMappings } from '@/api/hotwords'
import { extractErrorMessage } from '@/api/client'
import { showToast } from './useToast'
import { tt } from '@/i18n'

interface HwItem {
  id: number
  type: 'word' | 'mapping'
  content: string
  target?: string
}

const items = ref<HwItem[]>([])
const filter = ref<'all' | 'word' | 'mapping'>('all')
const searchQuery = ref('')
/** 此前 isLoading 是普通 boolean，不参与响应式，视图无法绑定 → 热词页没有加载态。
    Plain booleans are not reactive, which is why this view had no loading state at all. */
const loading = ref(false)
/** 加载失败原因；null 表示成功。失败必须与「没有词条」区分开。
    Load failure, distinct from "no hotwords configured". */
const loadError = ref<string | null>(null)
let idCounter = 0

function nextId() { return ++idCounter }

const filteredItems = computed(() => {
  let result = items.value
  if (filter.value !== 'all') {
    result = result.filter(it => it.type === filter.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    result = result.filter(it =>
      it.content.toLowerCase().includes(q) ||
      (it.target && it.target.toLowerCase().includes(q))
    )
  }
  return result
})

const stats = computed(() => ({
  words: items.value.filter(it => it.type === 'word').length,
  mappings: items.value.filter(it => it.type === 'mapping').length,
}))

async function loadAll() {
  loading.value = true
  loadError.value = null
  items.value = []
  try {
    const [wordsText, mapsText] = await Promise.all([fetchHotwords(), fetchHotwordMappings()])
    const newItems: HwItem[] = []
    if (wordsText.trim()) {
      wordsText.split('\n').map(l => l.trim()).filter(Boolean).forEach(w => {
        newItems.push({ id: nextId(), type: 'word', content: w })
      })
    }
    if (mapsText.trim()) {
      mapsText.split('\n').map(l => l.trim()).filter(Boolean).forEach(line => {
        const idx = line.indexOf('→')
        const eqIdx = line.indexOf('=')
        const sep = idx >= 0 ? '→' : (eqIdx >= 0 ? '=' : null)
        if (sep) {
          const parts = line.split(sep)
          const from = parts[0].trim()
          const to = parts.slice(1).join(sep).trim()
          if (from && to) {
            newItems.push({ id: nextId(), type: 'mapping', content: from, target: to })
          }
        }
      })
    }
    items.value = newItems
  } catch (e) {
    console.error('加载热词失败:', e)
    loadError.value = extractErrorMessage(e) || tt('hotwords.load_failed')
  } finally {
    loading.value = false
  }
}

let saveTimer: ReturnType<typeof setTimeout> | null = null
function scheduleSave() {
  if (loading.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => saveAll(true), 800)
}

async function saveAll(silent = false) {
  const words = items.value.filter(i => i.type === 'word').map(i => i.content).join('\n')
  const mappings = items.value.filter(i => i.type === 'mapping').map(i => `${i.content}→${i.target || ''}`).join('\n')
  try {
    await Promise.all([saveHotwords(words), saveHotwordMappings(mappings)])
    if (!silent) showToast(tt('hotwords.saved'), 'success')
  } catch (e: any) {
    if (!silent) showToast(tt('hotwords.save_failed', { err: e.message }), 'error')
  }
}

function addItem(type: 'word' | 'mapping', content: string, target?: string) {
  // 新词条插入头部，保持最近添加/修改的在最前 / Insert at top so newest items appear first
  items.value.unshift({ id: nextId(), type, content, target })
  scheduleSave()
}

function updateItem(id: number, updates: Partial<Pick<HwItem, 'content' | 'target'>>) {
  const idx = items.value.findIndex(x => x.id === id)
  if (idx < 0) return
  Object.assign(items.value[idx], updates)
  // 编辑后移到头部，保持最近维护的在最前 / Move to top after edit
  const [it] = items.value.splice(idx, 1)
  items.value.unshift(it)
  scheduleSave()
}

function deleteItem(id: number) {
  items.value = items.value.filter(x => x.id !== id)
  scheduleSave()
}

export function useHotwords() {
  return {
    items, filter, searchQuery, loading, loadError,
    filteredItems, stats,
    loadAll, saveAll, scheduleSave,
    addItem, updateItem, deleteItem,
  }
}
