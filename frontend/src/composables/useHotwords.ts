/**
 * 热词管理 composable / Hotword management composable
 * 管理词条 CRUD、搜索筛选、自动保存 / Manages item CRUD, search filtering, auto-save
 */
import { ref, computed } from 'vue'
import { fetchHotwords, saveHotwords, fetchHotwordMappings, saveHotwordMappings } from '@/api/hotwords'
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
let idCounter = 0
let isLoading = false

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
  isLoading = true
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
  } finally {
    isLoading = false
  }
}

let saveTimer: ReturnType<typeof setTimeout> | null = null
function scheduleSave() {
  if (isLoading) return
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
  items.value.push({ id: nextId(), type, content, target })
  scheduleSave()
}

function updateItem(id: number, updates: Partial<Pick<HwItem, 'content' | 'target'>>) {
  const it = items.value.find(x => x.id === id)
  if (it) {
    Object.assign(it, updates)
    scheduleSave()
  }
}

function deleteItem(id: number) {
  items.value = items.value.filter(x => x.id !== id)
  scheduleSave()
}

export function useHotwords() {
  return {
    items, filter, searchQuery,
    filteredItems, stats,
    loadAll, saveAll, scheduleSave,
    addItem, updateItem, deleteItem,
  }
}
