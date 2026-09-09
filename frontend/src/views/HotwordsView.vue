<template>
  <div>
    <div class="main-head">
      <h1>热词管理</h1>
      <p class="sub">管理转写识别词汇与纠错映射，按区块分组组织</p>
    </div>

    <div class="hw-layout">
      <!-- 左侧：区块列表 -->
      <div class="hw-sidebar">
        <div class="hw-sidebar-head">
          <h3>区块</h3>
          <input class="hw-sidebar-search" v-model="hw.groupSearch.value" type="text" placeholder="搜索区块…">
        </div>
        <div class="hw-group-list">
          <div v-if="hw.filteredGroups.value.length === 0" class="hw-group-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            <span>暂无区块</span>
          </div>
          <!-- 全部 -->
          <div
            class="hw-group-item"
            :class="{ 'is-active': hw.activeGroup.value === 'all' }"
            @click="hw.activeGroup.value = 'all'"
          >
            <svg class="hw-group-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
            <span>全部</span>
            <span class="hw-group-count">{{ hw.items.value.length }}</span>
          </div>
          <!-- 各分组 -->
          <div
            v-for="g in hw.filteredGroups.value"
            :key="g.id"
            class="hw-group-item"
            :class="{ 'is-active': hw.activeGroup.value === g.id }"
          >
            <svg class="hw-group-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            <span @click="hw.activeGroup.value = g.id">{{ g.name }}</span>
            <span class="hw-group-count">{{ hw.groupCounts.value[g.id] || 0 }}</span>
            <span v-if="g.id !== 'ungrouped'" class="hw-group-actions">
              <button title="重命名" @click.stop="hw.renameGroup(g.id)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/></svg>
              </button>
              <button title="删除" @click.stop="hw.deleteGroup(g.id)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              </button>
            </span>
          </div>
        </div>
        <div class="hw-sidebar-foot">
          <button class="hw-add-group-btn" @click="hw.addGroup()">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            新建区块
          </button>
        </div>
      </div>

      <!-- 右侧：热词表格 -->
      <div class="hw-main">
        <!-- 工具栏 -->
        <div class="hw-toolbar" ref="toolbarRef">
          <div class="hw-toolbar-left" ref="toolbarLeftRef">
            <div class="hw-search-box">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input type="text" v-model="hw.searchQuery.value" placeholder="搜索热词…" style="border:none;background:transparent;outline:none;font-size:13px;color:var(--fg);width:100%">
            </div>
            <button class="hw-filter-chip" :class="{ 'is-active': hw.filter.value === 'all' }" @click="hw.filter.value = 'all'">全部</button>
            <button class="hw-filter-chip" :class="{ 'is-active': hw.filter.value === 'word' }" @click="hw.filter.value = 'word'">热词</button>
            <button class="hw-filter-chip" :class="{ 'is-active': hw.filter.value === 'mapping' }" @click="hw.filter.value = 'mapping'">映射</button>
          </div>
          <div class="hw-toolbar-right">
            <!-- 宽屏：完整文本按钮 -->
            <template v-if="toolbarMode === 'full'">
              <button class="hw-ai-btn" @click="hw.aiAutoGroup()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a4 4 0 0 1 4 4v2a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M16 14H8a4 4 0 0 0-4 4v2h16v-2a4 4 0 0 0-4-4z"/></svg>
                AI 智能分组
              </button>
              <div class="hw-add-wrap">
                <button class="hw-add-btn" @click="showAddDropdown = !showAddDropdown">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                  添加
                </button>
                <div class="hw-add-dropdown" :class="{ 'is-open': showAddDropdown }">
                  <button @click="startAdd('word')">添加热词</button>
                  <button @click="startAdd('mapping')">添加映射</button>
                </div>
              </div>
            </template>
            <!-- 中屏：图标按钮 -->
            <template v-if="toolbarMode === 'compact'">
              <button class="hw-icon-btn" @click="hw.aiAutoGroup()" title="AI 智能分组">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a4 4 0 0 1 4 4v2a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M16 14H8a4 4 0 0 0-4 4v2h16v-2a4 4 0 0 0-4-4z"/></svg>
              </button>
              <div class="hw-add-wrap">
                <button class="hw-icon-btn" @click="showAddDropdown = !showAddDropdown" title="添加">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                </button>
                <div class="hw-add-dropdown" :class="{ 'is-open': showAddDropdown }">
                  <button @click="startAdd('word')">添加热词</button>
                  <button @click="startAdd('mapping')">添加映射</button>
                </div>
              </div>
            </template>
            <!-- 窄屏：省略号菜单 -->
            <div class="hw-overflow-wrap" v-if="toolbarMode === 'minimal'">
              <button class="hw-icon-btn" @click="showOverflowMenu = !showOverflowMenu" title="更多操作">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
              </button>
              <div class="hw-overflow-menu" :class="{ 'is-open': showOverflowMenu }">
                <button @click="hw.aiAutoGroup(); showOverflowMenu = false">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a4 4 0 0 1 4 4v2a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M16 14H8a4 4 0 0 0-4 4v2h16v-2a4 4 0 0 0-4-4z"/></svg>
                  AI 智能分组
                </button>
                <button @click="startAdd('word'); showOverflowMenu = false">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                  添加热词
                </button>
                <button @click="startAdd('mapping'); showOverflowMenu = false">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                  添加映射
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 表格 -->
        <div class="hw-table-wrap">
          <table class="hw-table">
            <thead>
              <tr>
                <th style="width:70px">类型</th>
                <th>内容</th>
                <th style="width:120px">区块</th>
                <th style="width:80px">操作</th>
              </tr>
            </thead>
            <tbody>
              <!-- 新增行 -->
              <tr v-if="addingType" class="hw-add-row">
                <td><span class="hw-type-badge" :class="addingType === 'word' ? 'is-word' : 'is-mapping'">{{ addingType === 'word' ? '热词' : '映射' }}</span></td>
                <td>
                  <input ref="addInputRef" class="hw-inline-edit" v-model="addContent" placeholder="输入内容…" @keydown.enter="confirmAdd" @keydown.escape="cancelAdd">
                  <input v-if="addingType === 'mapping'" class="hw-inline-edit" style="margin-top:4px" v-model="addTarget" placeholder="映射目标…" @keydown.enter="confirmAdd" @keydown.escape="cancelAdd">
                </td>
                <td><span class="hw-group-tag">{{ hw.getGroupName(hw.activeGroup.value === 'all' ? 'ungrouped' : hw.activeGroup.value) }}</span></td>
                <td>
                  <div class="hw-edit-actions">
                    <button class="hw-type-badge hw-edit-save" @click="confirmAdd">✓</button>
                    <button class="hw-type-badge hw-edit-cancel" @click="cancelAdd">✕</button>
                  </div>
                </td>
              </tr>
              <!-- 编辑行 -->
              <tr v-for="it in hw.filteredItems.value" :key="it.id" :class="{ 'hw-row-editing': editingId === it.id }">
                <td><span class="hw-type-badge" :class="it.type === 'word' ? 'is-word' : 'is-mapping'">{{ it.type === 'word' ? '热词' : '映射' }}</span></td>
                <td class="hw-content-cell">
                  <template v-if="editingId === it.id">
                    <input ref="editInputRef" class="hw-inline-edit" v-model="editContent" @keydown.enter="confirmEdit" @keydown.escape="cancelEdit">
                    <input v-if="it.type === 'mapping'" class="hw-inline-edit" style="margin-top:4px" v-model="editTarget" @keydown.enter="confirmEdit" @keydown.escape="cancelEdit">
                  </template>
                  <template v-else>
                    <template v-if="it.type === 'word'">{{ it.content }}</template>
                    <template v-else>
                      <span>{{ it.content }}</span><span class="hw-mapping-arrow"> → </span><span class="hw-mapping-target">{{ it.target }}</span>
                    </template>
                  </template>
                </td>
                <td>
                  <span v-if="editingId !== it.id" class="hw-group-tag" @click="openMoveMenu($event, it.id)">
                    {{ hw.getGroupName(it.groupId) }}
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                  </span>
                </td>
                <td>
                  <div v-if="editingId !== it.id" class="hw-row-actions">
                    <button title="编辑" @click="startEdit(it)">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/></svg>
                    </button>
                    <button class="is-danger" title="删除" @click="hw.deleteItem(it.id)">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>
                  </div>
                  <div v-else class="hw-edit-actions">
                    <button class="hw-type-badge hw-edit-save" @click="confirmEdit">✓</button>
                    <button class="hw-type-badge hw-edit-cancel" @click="cancelEdit">✕</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="hw.filteredItems.value.length === 0 && !addingType" class="hw-empty">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 5h6l5 5v11a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V5z"/><path d="M14 5v6h6"/></svg>
            <p>暂无热词</p>
            <p class="sub">点击右上角「添加」按钮新增热词或映射</p>
          </div>
        </div>

        <!-- 统计栏 -->
        <div class="hw-stats-bar">
          <span>热词 <span class="hw-stat-num">{{ hw.stats.value.words }}</span></span>
          <span>映射 <span class="hw-stat-num">{{ hw.stats.value.mappings }}</span></span>
          <span>区块 <span class="hw-stat-num">{{ hw.stats.value.groups }}</span></span>
        </div>
      </div>
    </div>

    <!-- 移动菜单 -->
    <teleport to="body">
      <div v-if="moveMenu.visible" class="hw-move-dropdown" :style="{ top: moveMenu.y + 'px', left: moveMenu.x + 'px' }">
        <button v-for="g in hw.groups.value" :key="g.id" :class="{ 'is-current': moveMenu.itemId > 0 && hw.items.value.find(i => i.id === moveMenu.itemId)?.groupId === g.id }" @click="doMove(g.id)">
          {{ g.name }}
        </button>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, nextTick } from 'vue'
import { useHotwordGroups } from '@/composables/useHotwordGroups'

const hw = useHotwordGroups()

const toolbarRef = ref<HTMLElement | null>(null)
const toolbarLeftRef = ref<HTMLElement | null>(null)
const toolbarMode = ref<'full' | 'compact' | 'minimal'>('full')
const showOverflowMenu = ref(false)
let resizeObs: ResizeObserver | null = null

function updateToolbarMode() {
  const totalW = toolbarRef.value?.clientWidth || 0
  const leftW = toolbarLeftRef.value?.clientWidth || 0
  const available = totalW - leftW - 16
  if (available >= 220) toolbarMode.value = 'full'
  else if (available >= 80) toolbarMode.value = 'compact'
  else toolbarMode.value = 'minimal'
}

const showAddDropdown = ref(false)
const addingType = ref<'word' | 'mapping' | null>(null)
const addContent = ref('')
const addTarget = ref('')
const addInputRef = ref<HTMLInputElement | null>(null)

const editingId = ref<number | null>(null)
const editContent = ref('')
const editTarget = ref('')
const editInputRef = ref<HTMLInputElement | null>(null)

const moveMenu = reactive({ visible: false, x: 0, y: 0, itemId: 0 })

function startAdd(type: 'word' | 'mapping') {
  addingType.value = type
  addContent.value = ''
  addTarget.value = ''
  showAddDropdown.value = false
  nextTick(() => addInputRef.value?.focus())
}

function confirmAdd() {
  if (!addContent.value.trim()) return
  if (addingType.value === 'mapping' && !addTarget.value.trim()) return
  hw.addItem(addingType.value!, addContent.value.trim(), addTarget.value.trim() || undefined)
  addingType.value = null
  addContent.value = ''
  addTarget.value = ''
}

function cancelAdd() {
  addingType.value = null
  addContent.value = ''
  addTarget.value = ''
}

function startEdit(item: { id: number; content: string; target?: string }) {
  editingId.value = item.id
  editContent.value = item.content
  editTarget.value = item.target || ''
  nextTick(() => editInputRef.value?.focus())
}

function confirmEdit() {
  if (!editContent.value.trim()) return
  const updates: Record<string, string> = { content: editContent.value.trim() }
  if (editTarget.value !== undefined) updates.target = editTarget.value.trim()
  hw.updateItem(editingId.value!, updates)
  editingId.value = null
}

function cancelEdit() {
  editingId.value = null
}

function openMoveMenu(event: MouseEvent, itemId: number) {
  event.stopPropagation()
  moveMenu.visible = true
  moveMenu.x = event.clientX
  moveMenu.y = event.clientY
  moveMenu.itemId = itemId
}

function doMove(groupId: string) {
  hw.moveItem(moveMenu.itemId, groupId)
  moveMenu.visible = false
}

function closeMoveMenu() {
  moveMenu.visible = false
}

function closeAddDropdown(e: MouseEvent) {
  if (showAddDropdown.value) {
    const target = e.target as HTMLElement
    if (!target.closest('.hw-add-wrap')) showAddDropdown.value = false
  }
}

function closeOverflowMenu(e: MouseEvent) {
  if (showOverflowMenu.value) {
    const target = e.target as HTMLElement
    if (!target.closest('.hw-overflow-wrap')) showOverflowMenu.value = false
  }
}

onMounted(() => {
  hw.loadAll()
  document.addEventListener('click', closeMoveMenu)
  document.addEventListener('click', closeAddDropdown)
  document.addEventListener('click', closeOverflowMenu)
  nextTick(() => {
    updateToolbarMode()
    resizeObs = new ResizeObserver(() => updateToolbarMode())
    if (toolbarRef.value) resizeObs.observe(toolbarRef.value)
    if (toolbarLeftRef.value) resizeObs.observe(toolbarLeftRef.value)
  })
})

onUnmounted(() => {
  document.removeEventListener('click', closeMoveMenu)
  document.removeEventListener('click', closeAddDropdown)
  document.removeEventListener('click', closeOverflowMenu)
  resizeObs?.disconnect()
})
</script>
