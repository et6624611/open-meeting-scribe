<template>
  <div class="hw-page">
    <div class="main-head">
      <div class="title-row">
        <h1>{{ t('hotwords.title') }}</h1>
        <span class="page-count">{{ t('hotwords.count', { count: hw.items.value.length }) }}</span>
      </div>
    </div>

    <!-- 统一输入框 + 过滤 / Unified input + filter -->
    <div class="hw-toolbar">
      <div class="hw-unified" ref="unifiedRef">
        <div class="hw-unified-field">
          <svg class="hw-unified-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <template v-if="showCreateOption">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </template>
            <template v-else>
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </template>
          </svg>
          <input
            v-model="inputText"
            class="hw-unified-input"
            type="text"
            :placeholder="t('hotwords.unified_placeholder')"
            @keyup.enter="onUnifiedEnter"
            @keydown.down.prevent="onArrowDown"
            @keydown.up.prevent="onArrowUp"
            @keydown.escape="onUnifiedEsc"
            @focus="openDropdown"
            role="combobox"
            :aria-expanded="showDropdown"
            aria-haspopup="listbox"
          />
        </div>
        <!-- 映射创建表单 / Mapping creation form -->
        <div v-if="pendingMapping" class="hw-mapping-form">
          <div class="hw-mapping-form-row">
            <input
              v-model="mappingFrom"
              class="hw-mapping-input"
              type="text"
              placeholder="错误词"
              @keyup.enter="onMappingConfirm"
              @keydown.escape.prevent="onMappingCancel"
              ref="mappingFromRef"
            />
            <span class="hw-mapping-arrow-icon">→</span>
            <input
              v-model="mappingTo"
              class="hw-mapping-input"
              type="text"
              placeholder="正确词"
              @keyup.enter="onMappingConfirm"
              @keydown.escape.prevent="onMappingCancel"
            />
            <button class="hw-mapping-btn hw-mapping-btn-confirm" @click="onMappingConfirm" title="确认">✓</button>
            <button class="hw-mapping-btn hw-mapping-btn-cancel" @click="onMappingCancel" title="取消">✕</button>
          </div>
        </div>
        <!-- 下拉列表 / Dropdown list -->
        <div
          v-if="showDropdown && showCreateOption"
          class="hw-dropdown"
          role="listbox"
        >
          <!-- 创建选项 / Create options（匹配项已在主列表中展示，不重复显示） -->
          <template v-if="showCreateOption">
            <!-- 添加热词 / Add hotword -->
            <div
              class="hw-dropdown-item hw-dropdown-create"
              :class="{ 'is-highlighted': highlightedIndex === 0 }"
              @click="onCreateAs('word')"
              @mouseenter="highlightedIndex = 0"
              role="option"
              :aria-selected="highlightedIndex === 0"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              <span>{{ t('hotwords.create_word_hint', { name: inputText.trim() }) }}</span>
            </div>
            <!-- 添加映射 / Add mapping -->
            <div
              class="hw-dropdown-item hw-dropdown-create"
              :class="{ 'is-highlighted': highlightedIndex === 1 }"
              @click="onCreateAs('mapping')"
              @mouseenter="highlightedIndex = 1"
              role="option"
              :aria-selected="highlightedIndex === 1"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              <span>{{ t('hotwords.create_mapping_hint', { content: inputText.trim() }) }}</span>
            </div>
          </template>
        </div>
      </div>
      <div class="hw-filter-chips">
        <button class="hw-filter-chip" :class="{ 'is-active': hw.filter.value === 'all' }" @click="hw.filter.value = 'all'">{{ t('hotwords.filter_all') }}</button>
        <button class="hw-filter-chip" :class="{ 'is-active': hw.filter.value === 'word' }" @click="hw.filter.value = 'word'">{{ t('hotwords.filter_word') }}</button>
        <button class="hw-filter-chip" :class="{ 'is-active': hw.filter.value === 'mapping' }" @click="hw.filter.value = 'mapping'">{{ t('hotwords.filter_mapping') }}</button>
      </div>
    </div>

    <!-- 表格 / Table -->
    <div class="hw-table-wrap">
      <table class="hw-table">
        <thead>
          <tr>
            <th style="width:70px">{{ t('hotwords.col_type') }}</th>
            <th>{{ t('hotwords.col_content') }}</th>
            <th style="width:80px">{{ t('hotwords.col_actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <!-- 数据行 / Data rows -->
          <tr v-for="it in hw.filteredItems.value" :key="it.id" :class="{ 'hw-row-editing': editingId === it.id }">
            <td><span class="hw-type-badge" :class="it.type === 'word' ? 'is-word' : 'is-mapping'">{{ it.type === 'word' ? t('hotwords.type_word') : t('hotwords.type_mapping') }}</span></td>
            <td class="hw-content-cell">
              <template v-if="editingId === it.id">
                <input ref="editInputRef" class="hw-inline-edit" v-model="editContent" @keydown.enter="confirmEdit" @keydown.escape.prevent="cancelEdit">
                <input v-if="it.type === 'mapping'" class="hw-inline-edit" style="margin-top:4px" v-model="editTarget" @keydown.enter="confirmEdit" @keydown.escape.prevent="cancelEdit">
              </template>
              <template v-else>
                <template v-if="it.type === 'word'">{{ it.content }}</template>
                <template v-else>
                  <span>{{ it.content }}</span><span class="hw-mapping-arrow"> → </span><span class="hw-mapping-target">{{ it.target }}</span>
                </template>
              </template>
            </td>
            <td>
              <div v-if="editingId !== it.id" class="hw-row-actions">
                <button :title="t('hotwords.edit')" @click="startEdit(it)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/></svg>
                </button>
                <button class="is-danger" :title="t('common.action.delete')" @click="hw.deleteItem(it.id)">
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
      <!-- 加载失败态 / Load-failure state -->
      <div v-if="hw.loadError.value" class="hw-error" role="alert">
        <p>{{ hw.loadError.value }}</p>
        <button type="button" class="hw-error-retry" @click="hw.loadAll()">{{ t('common.error.retry') }}</button>
      </div>
      <!-- 空状态 / Empty state -->
      <div v-else-if="hw.filteredItems.value.length === 0 && !inputText.trim()" class="hw-empty" :aria-busy="hw.loading.value">
        <svg v-if="hw.loading.value" class="hw-spinner" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9" stroke-linecap="round"/></svg>
        <svg v-else width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M9 5h6l5 5v11a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V5z"/><path d="M14 5v6h6"/></svg>
        <p>{{ hw.loading.value ? t('common.status.loading') : t('hotwords.empty') }}</p>
        <p v-if="!hw.loading.value" class="sub">{{ t('hotwords.empty_hint') }}</p>
      </div>
    </div>

    <!-- 统计栏 / Stats bar -->
    <div class="hw-stats-bar">
      <span>{{ t('hotwords.stat_words', { count: hw.stats.value.words }) }}</span>
      <span>{{ t('hotwords.stat_mappings', { count: hw.stats.value.mappings }) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useHotwords } from '@/composables/useHotwords'
import { usePageBack } from '@/composables/usePageBack'

const { t } = useI18n()
const hw = useHotwords()

// ESC 返回上一页（浮层/下拉/内联编辑打开时会先消费事件，不会触发返回） / ESC goes back (overlays/dropdown/inline-edit consume the event first, so back won't fire)
usePageBack()

// ─── 统一输入框 / Unified input ───
const inputText = ref('')
const unifiedRef = ref<HTMLElement | null>(null)

// 同步输入框到搜索过滤，使列表实时过滤 / Sync input to search filter for live list filtering
watch(inputText, (val) => {
  hw.searchQuery.value = val
  highlightedIndex.value = -1
  // 有文本且无精确匹配时自动弹出下拉 / Auto-show dropdown when text exists and no exact match
  if (val.trim() && !hasExactMatch.value) {
    showDropdown.value = true
  } else {
    showDropdown.value = false
  }
})

// ── 下拉列表 / Dropdown ──
const showDropdown = ref(false)
const highlightedIndex = ref(-1)

// 映射输入模式：选择「添加映射」后等待用户填写完整映射 / Mapping input mode: waiting for user to type full mapping
const pendingMapping = ref(false)
const mappingFrom = ref('')
const mappingTo = ref('')
const mappingFromRef = ref<HTMLInputElement | null>(null)

/** 是否显示创建选项 / Whether to show create option */
const showCreateOption = computed(() => {
  return inputText.value.trim().length > 0 && !hasExactMatch.value
})

/** 打开下拉列表 / Open dropdown */
function openDropdown() {
  if (inputText.value.trim()) {
    showDropdown.value = true
  }
}

/** 关闭下拉列表 / Close dropdown */
function closeDropdown() {
  showDropdown.value = false
  highlightedIndex.value = -1
  if (pendingMapping.value) {
    onMappingCancel()
  }
}

/** 统一输入框 ESC：仅当下拉/映射输入处于打开态时消费事件并关闭，否则交由页面级 ESC 返回上一页 / Unified input ESC: consume & close only when dropdown/mapping input is open; otherwise let page-level ESC go back */
function onUnifiedEsc(e: KeyboardEvent) {
  if (showDropdown.value || pendingMapping.value) {
    e.preventDefault()
    closeDropdown()
  }
}

/** 方向键下 / Arrow down */
function onArrowDown() {
  if (!showCreateOption.value) return
  showDropdown.value = true
  highlightedIndex.value = highlightedIndex.value < 1 ? highlightedIndex.value + 1 : 0
}

/** 方向键上 / Arrow up */
function onArrowUp() {
  if (!showCreateOption.value) return
  showDropdown.value = true
  highlightedIndex.value = highlightedIndex.value > 0 ? highlightedIndex.value - 1 : 1
}

/** 点击外部关闭 / Close on outside click */
function onDocClick(e: MouseEvent) {
  if (unifiedRef.value && !unifiedRef.value.contains(e.target as Node)) {
    closeDropdown()
  }
}

/** 解析输入文本 → 类型 + 内容 / Parse input text into type + content */
function parseInput(text: string): { type: 'word' | 'mapping'; content: string; target?: string } {
  const trimmed = text.trim()
  // 检测分隔符，有分隔符则解析为映射 / Detect separator; parse as mapping if found
  const arrowIdx = trimmed.indexOf('→')
  const eqIdx = trimmed.indexOf('=')
  const sepIdx = arrowIdx >= 0 ? arrowIdx : eqIdx
  if (sepIdx > 0) {
    const sep = arrowIdx >= 0 ? '→' : '='
    const content = trimmed.slice(0, sepIdx).trim()
    const target = trimmed.slice(sepIdx + sep.length).trim()
    if (content && target) return { type: 'mapping', content, target }
  }
  return { type: 'word', content: trimmed }
}

/** 是否存在精确匹配 / Whether an exact match exists */
const hasExactMatch = computed(() => {
  const q = inputText.value.trim().toLowerCase()
  if (!q) return true
  const parsed = parseInput(inputText.value)
  return hw.items.value.some(it => {
    if (it.type !== parsed.type) return false
    if (it.content.toLowerCase() !== parsed.content.toLowerCase()) return false
    if (parsed.type === 'mapping' && parsed.target) {
      return (it.target || '').toLowerCase() === parsed.target.toLowerCase()
    }
    return true
  })
})

/** 按指定类型创建 / Create item with specified type */
function onCreateAs(type: 'word' | 'mapping') {
  const trimmed = inputText.value.trim()
  if (!trimmed) return
  if (type === 'mapping') {
    // 进入映射输入模式，等待用户填写完整映射 / Enter mapping input mode
    pendingMapping.value = true
    mappingFrom.value = trimmed
    mappingTo.value = ''
    inputText.value = ''
    showDropdown.value = false
    highlightedIndex.value = -1
    nextTick(() => mappingFromRef.value?.focus())
    return
  }
  hw.addItem('word', trimmed)
  inputText.value = ''
}

/** 确认创建映射 / Confirm mapping creation */
function onMappingConfirm() {
  const from = mappingFrom.value.trim()
  const to = mappingTo.value.trim()
  if (!from || !to) return
  hw.addItem('mapping', from, to)
  mappingFrom.value = ''
  mappingTo.value = ''
  pendingMapping.value = false
}

/** 取消映射创建 / Cancel mapping creation */
function onMappingCancel() {
  mappingFrom.value = ''
  mappingTo.value = ''
  pendingMapping.value = false
}

/** Enter 键处理 / Enter key handler */
function onUnifiedEnter() {
  if (!showCreateOption.value) return
  // 有高亮时按高亮项创建，否则默认创建热词 / Create based on highlight or default to word
  if (showDropdown.value && highlightedIndex.value >= 0) {
    onCreateAs(highlightedIndex.value === 1 ? 'mapping' : 'word')
  } else {
    onCreateAs('word')
  }
}

// ─── 内联编辑 / Inline edit ───
const editingId = ref<number | null>(null)
const editContent = ref('')
const editTarget = ref('')
const editInputRef = ref<HTMLInputElement | null>(null)

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

onMounted(() => {
  hw.loadAll()
  document.addEventListener('mousedown', onDocClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocClick)
})
</script>

<style scoped>
.hw-page { padding: var(--s-5) var(--s-5) var(--s-6); display: flex; flex-direction: column; height: 100%; }

/* 工具栏 / Toolbar */
.hw-toolbar { display: flex; align-items: center; gap: var(--s-4); margin-bottom: var(--s-4); flex-shrink: 0; }
.hw-unified { flex: 1; min-width: 0; position: relative; }
.hw-unified-field { display: flex; align-items: center; position: relative; }
.hw-unified-icon { position: absolute; left: 10px; color: var(--subtle); pointer-events: none; transition: color 0.15s; }
.hw-unified-input { width: 100%; max-width: 400px; padding: 8px 10px 8px 32px; border: none; border-bottom: 1px solid var(--border); border-radius: 0; font-size: 14px; outline: none; background: transparent; color: var(--fg); transition: border-color 0.15s; }
.hw-unified-input:focus { border-bottom-color: var(--accent); box-shadow: 0 1px 0 0 var(--accent); }
.hw-unified-input:focus ~ .hw-unified-icon,
.hw-unified-field:focus-within .hw-unified-icon { color: var(--accent); }
.hw-unified-input::placeholder { color: var(--subtle); }
/* 映射创建表单 / Mapping creation form */
.hw-mapping-form { position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; z-index: 100; }
.hw-mapping-form-row { display: flex; align-items: center; gap: 6px; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; box-shadow: var(--shadow-float); }
.hw-mapping-input { flex: 1; min-width: 0; padding: 6px 8px; border: 1px solid var(--border); border-radius: 4px; font-size: 13px; outline: none; background: var(--surface-2); color: var(--fg); transition: border-color 0.15s; }
.hw-mapping-input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft); }
.hw-mapping-input::placeholder { color: var(--subtle); }
.hw-mapping-arrow-icon { color: var(--accent); font-size: 14px; flex-shrink: 0; }
.hw-mapping-btn { width: 28px; height: 28px; border: none; border-radius: 4px; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; transition: all 0.12s; }
.hw-mapping-btn-confirm { background: var(--accent); color: #fff; }
.hw-mapping-btn-confirm:hover { background: oklch(from var(--accent) calc(l - 0.06) c h); }
.hw-mapping-btn-cancel { background: var(--surface-2); color: var(--muted); border: 1px solid var(--border); }
.hw-mapping-btn-cancel:hover { background: var(--border); color: var(--fg); }
/* 下拉列表 / Dropdown */
.hw-dropdown { position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; box-shadow: var(--shadow-float); z-index: 100; max-height: 240px; overflow-y: auto; }
.hw-dropdown-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; transition: background 0.1s; font-size: 13px; }
.hw-dropdown-item:hover, .hw-dropdown-item.is-highlighted { background: var(--surface-2); }
.hw-dropdown-create { color: var(--accent); border-top: 1px solid var(--border); }
.hw-dropdown-create:hover, .hw-dropdown-create.is-highlighted { background: var(--accent-soft); }
.hw-dropdown-type { flex-shrink: 0; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 500; }
.hw-dropdown-type.is-word { background: oklch(92% 0.04 250); color: oklch(45% 0.12 250); }
.hw-dropdown-type.is-mapping { background: oklch(92% 0.06 150); color: oklch(40% 0.12 150); }
.hw-dropdown-content { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--font-mono); }
.hw-filter-chips { display: flex; gap: var(--s-1); flex-shrink: 0; }
.hw-filter-chip { padding: 4px 10px; border-radius: 4px; font-size: var(--fs-11); color: var(--muted); border: none; background: transparent; cursor: pointer; transition: all 0.12s; white-space: nowrap; }
.hw-filter-chip:hover { background: var(--surface-2); color: var(--fg); }
.hw-filter-chip.is-active { background: var(--accent-soft); color: var(--accent); }

/* 表格 / Table */
.hw-table-wrap { flex: 1; overflow-x: auto; overflow-y: auto; min-height: 0; }
.hw-table { width: 100%; border-collapse: collapse; }
.hw-table th { position: sticky; top: 0; z-index: 1; text-align: left; font-size: 11px; font-weight: 500; color: var(--subtle); text-transform: uppercase; letter-spacing: 0.04em; padding: var(--s-2) var(--s-3); border-bottom: 1px solid var(--border); background: var(--surface-2); }
.hw-table td { padding: 10px var(--s-3); border-bottom: 1px solid var(--border); font-size: var(--fs-13); vertical-align: middle; }
.hw-table tr:last-child td { border-bottom: none; }
.hw-table tr:hover td { background: var(--surface-2); }

/* 类型徽章 / Type badge */
.hw-type-badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; white-space: nowrap; }
.hw-type-badge.is-word { background: oklch(92% 0.04 250); color: oklch(45% 0.12 250); }
.hw-type-badge.is-mapping { background: oklch(92% 0.06 150); color: oklch(40% 0.12 150); }

/* 内容列 / Content cell */
.hw-content-cell { font-family: var(--font-mono); font-size: var(--fs-13); font-weight: 500; color: var(--fg); }
.hw-mapping-arrow { color: var(--subtle); font-size: 12px; margin: 0 4px; }
.hw-mapping-target { font-family: var(--font-mono); font-size: var(--fs-13); color: oklch(40% 0.12 150); font-weight: 500; }

/* 行操作 / Row actions */
.hw-row-actions { display: flex; gap: 2px; opacity: 0; transition: opacity 0.1s; }
.hw-table tr:hover .hw-row-actions { opacity: 1; }
.hw-row-actions button { width: 26px; height: 26px; border: none; background: transparent; color: var(--subtle); cursor: pointer; border-radius: 4px; display: flex; align-items: center; justify-content: center; padding: 0; }
.hw-row-actions button:hover { background: var(--border); color: var(--fg); }
.hw-row-actions button.is-danger:hover { background: oklch(92% 0.06 25); color: oklch(50% 0.18 25); }

/* 内联编辑 / Inline edit */
.hw-inline-edit { border: 1px solid var(--accent); border-radius: 4px; padding: 2px 6px; font-size: var(--fs-13); font-family: var(--font-mono); outline: none; background: var(--surface); color: var(--fg); width: 100%; box-shadow: var(--shadow-focus); }
.hw-inline-edit:focus { border-color: var(--accent); }
.hw-row-editing td { background: oklch(97% 0.02 250) !important; }
.hw-row-editing .hw-row-actions { opacity: 1 !important; }
.hw-edit-actions { display: inline-flex; gap: 4px; margin-left: 8px; }
.hw-edit-actions button { width: 26px; height: 26px; border: none; border-radius: 4px; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; padding: 0; }
.hw-edit-save { background: var(--accent); color: #fff; }
.hw-edit-save:hover { background: oklch(from var(--accent) calc(l - 0.06) c h); }
.hw-edit-cancel { background: var(--surface-2); color: var(--muted); border: 1px solid var(--border) !important; }
.hw-edit-cancel:hover { background: var(--border); color: var(--fg); }

/* 空状态 / Empty state */
.hw-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: var(--s-7); color: var(--muted); text-align: center; }
.hw-empty svg { width: 40px; height: 40px; color: var(--subtle); margin-bottom: var(--s-3); }
.hw-empty p { font-size: var(--fs-12); margin: 0; }

/* 加载失败态 / Load-failure state */
.hw-error { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); padding: var(--s-7); color: var(--error); text-align: center; font-size: var(--fs-12); }
.hw-error p { margin: 0; }
.hw-error-retry { padding: var(--s-2) var(--s-3); font: inherit; font-size: var(--fs-12); color: var(--error); background: transparent; border: 1px solid var(--error); border-radius: var(--radius-sm); cursor: pointer; transition: background 0.15s, color 0.15s; }
.hw-error-retry:hover { background: var(--error); color: var(--surface); }

/* 加载中：复用空态容器，图标改为旋转 / Loading reuses the empty container with a spinning glyph */
.hw-empty .hw-spinner { width: 24px; height: 24px; color: var(--accent); animation: hw-spin 0.9s linear infinite; }
@keyframes hw-spin { to { transform: rotate(360deg); } }

/* 统计栏 / Stats bar */
.hw-stats-bar { display: flex; align-items: center; gap: var(--s-4); padding: var(--s-2) var(--s-4); border-top: 1px solid var(--border); font-size: var(--fs-11); color: var(--muted); background: var(--surface-2); flex-shrink: 0; }
.hw-stats-bar span { display: flex; align-items: center; gap: 4px; }
</style>
