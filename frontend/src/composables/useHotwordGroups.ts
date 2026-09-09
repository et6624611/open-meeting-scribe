/**
 * 热词分组管理 composable
 * 管理分组 CRUD、词条 CRUD、AI 自动分组、搜索筛选、自动保存
 */
import { ref, computed } from 'vue'
import { fetchHotwords, saveHotwords, fetchHotwordMappings, saveHotwordMappings } from '@/api/hotwords'
import { showToast } from './useToast'

const HW_STORAGE_KEY = 'oms-hotword-groups'
const HW_ASSIGN_KEY = 'oms-hotword-assign'

interface HwGroup {
  id: string
  name: string
  order: number
}

interface HwItem {
  id: number
  type: 'word' | 'mapping'
  content: string
  target?: string
  groupId: string
}

const groups = ref<HwGroup[]>([{ id: 'ungrouped', name: '未分组', order: 0 }])
const items = ref<HwItem[]>([])
const activeGroup = ref('all')
const filter = ref<'all' | 'word' | 'mapping'>('all')
const searchQuery = ref('')
const groupSearch = ref('')
let idCounter = 0
let isLoading = false

function nextId() { return ++idCounter }

function loadGroupsFromStorage() {
  try {
    const raw = localStorage.getItem(HW_STORAGE_KEY)
    if (raw) { groups.value = JSON.parse(raw); return }
  } catch { /* ignore */ }
  groups.value = [{ id: 'ungrouped', name: '未分组', order: 0 }]
  saveGroupsToStorage()
}

function saveGroupsToStorage() {
  localStorage.setItem(HW_STORAGE_KEY, JSON.stringify(groups.value))
}

function loadAssignments(): Record<string, string> {
  try {
    const raw = localStorage.getItem(HW_ASSIGN_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return {}
}

function saveAssignments() {
  const map: Record<string, string> = {}
  items.value.forEach(it => {
    const key = it.type === 'word' ? `w:${it.content}` : `m:${it.content}→${it.target || ''}`
    map[key] = it.groupId
  })
  localStorage.setItem(HW_ASSIGN_KEY, JSON.stringify(map))
}

const filteredItems = computed(() => {
  let result = items.value
  if (activeGroup.value !== 'all') {
    result = result.filter(it => it.groupId === activeGroup.value)
  }
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

const filteredGroups = computed(() => {
  const q = groupSearch.value.trim().toLowerCase()
  if (!q) return groups.value
  return groups.value.filter(g => g.name.toLowerCase().includes(q))
})

const groupCounts = computed(() => {
  const counts: Record<string, number> = {}
  items.value.forEach(it => { counts[it.groupId] = (counts[it.groupId] || 0) + 1 })
  return counts
})

const stats = computed(() => ({
  words: items.value.filter(it => it.type === 'word').length,
  mappings: items.value.filter(it => it.type === 'mapping').length,
  groups: groups.value.length,
}))

function getGroupName(groupId: string): string {
  return groups.value.find(g => g.id === groupId)?.name || '未分组'
}

async function loadAll() {
  isLoading = true
  loadGroupsFromStorage()
  const assignMap = loadAssignments()
  items.value = []
  try {
    const [wordsText, mapsText] = await Promise.all([fetchHotwords(), fetchHotwordMappings()])
    const newItems: HwItem[] = []
    if (wordsText.trim()) {
      wordsText.split('\n').map(l => l.trim()).filter(Boolean).forEach(w => {
        const key = `w:${w}`
        newItems.push({ id: nextId(), type: 'word', content: w, groupId: assignMap[key] || 'ungrouped' })
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
            const key = `m:${from}→${to}`
            newItems.push({ id: nextId(), type: 'mapping', content: from, target: to, groupId: assignMap[key] || 'ungrouped' })
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
    saveAssignments()
    if (!silent) showToast('热词已保存，下次转写生效', 'success')
  } catch (e: any) {
    if (!silent) showToast('保存失败: ' + e.message, 'error')
  }
}

function addGroup() {
  const name = prompt('输入新区块名称：')
  if (!name || !name.trim()) return
  const id = 'g_' + Date.now()
  groups.value.push({ id, name: name.trim(), order: groups.value.length })
  saveGroupsToStorage()
}

function renameGroup(id: string) {
  const g = groups.value.find(x => x.id === id)
  if (!g) return
  const name = prompt('重命名区块：', g.name)
  if (!name || !name.trim()) return
  g.name = name.trim()
  saveGroupsToStorage()
}

function deleteGroup(id: string) {
  const g = groups.value.find(x => x.id === id)
  if (!g) return
  if (!confirm(`删除区块「${g.name}」？其中的内容将移到「未分组」。`)) return
  items.value.forEach(it => { if (it.groupId === id) it.groupId = 'ungrouped' })
  groups.value = groups.value.filter(x => x.id !== id)
  if (activeGroup.value === id) activeGroup.value = 'all'
  saveGroupsToStorage()
  saveAssignments()
  scheduleSave()
}

function moveItem(itemId: number, targetGroupId: string) {
  const it = items.value.find(x => x.id === itemId)
  if (it) {
    it.groupId = targetGroupId
    saveAssignments()
    scheduleSave()
  }
}

function addItem(type: 'word' | 'mapping', content: string, target?: string) {
  const groupId = activeGroup.value === 'all' ? 'ungrouped' : activeGroup.value
  items.value.push({ id: nextId(), type, content, target, groupId })
  saveAssignments()
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

function aiAutoGroup() {
  const target = items.value.slice()
  if (!target.length) { showToast('没有可分组的内容', 'warn'); return }

  const surnames = '赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹'

  const newGroups: Record<string, HwItem[]> = {}
  target.forEach(it => {
    let groupName = '未分组'
    const text = it.content
    if (/^[A-Za-z][A-Za-z0-9]{1,6}$/.test(text)) {
      groupName = '缩写词'
    } else if (/[\u4e00-\u9fa5]/.test(text)) {
      if (text.length >= 2 && text.length <= 4 && surnames.includes(text[0])) {
        groupName = '人名'
      } else {
        groupName = '业务术语'
      }
    } else {
      groupName = '其他'
    }
    if (!newGroups[groupName]) newGroups[groupName] = []
    newGroups[groupName].push(it)
  })

  Object.keys(newGroups).forEach(name => {
    if (name === '未分组' || name === '其他') return
    if (!groups.value.find(g => g.name === name)) {
      groups.value.push({
        id: 'g_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6),
        name,
        order: groups.value.length,
      })
    }
  })

  Object.entries(newGroups).forEach(([name, groupItems]) => {
    if (name === '未分组') return
    const g = groups.value.find(x => x.name === name)
    if (g) groupItems.forEach(it => { it.groupId = g.id })
  })

  saveGroupsToStorage()
  saveAssignments()
  scheduleSave()

  const groupedCount = target.length - (newGroups['未分组']?.length || 0) - (newGroups['其他']?.length || 0)
  const groupCount = Object.keys(newGroups).filter(n => n !== '未分组' && n !== '其他').length
  showToast(`已智能分组 ${groupedCount} 项到 ${groupCount} 个区块`, 'success')
}

export function useHotwordGroups() {
  return {
    groups, items, activeGroup, filter, searchQuery, groupSearch,
    filteredItems, filteredGroups, groupCounts, stats,
    getGroupName, loadAll, saveAll, scheduleSave,
    addGroup, renameGroup, deleteGroup,
    moveItem, addItem, updateItem, deleteItem,
    aiAutoGroup,
  }
}
