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
      <div class="hw-unified">
        <div class="hw-unified-field">
          <svg class="hw-unified-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <template v-if="showCreateHint">
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
          />
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
      <!-- 新建提示 / Create hint -->
      <div v-if="showCreateHint" class="hw-create-hint" @click="onCreate">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        <span>{{ createHintLabel }}</span>
      </div>
      <!-- 空状态 / Empty state -->
      <div v-if="hw.filteredItems.value.length === 0 && !showCreateHint" class="hw-empty">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 5h6l5 5v11a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V5z"/><path d="M14 5v6h6"/></svg>
        <p>{{ t('hotwords.empty') }}</p>
        <p class="sub">{{ t('hotwords.empty_hint') }}</p>
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
import { ref, computed, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useHotwords } from '@/composables/useHotwords'

const { t } = useI18n()
const hw = useHotwords()

// ─── 统一输入框 / Unified input ───
const inputText = ref('')

/** 解析输入文本 → 类型 + 内容 / Parse input text into type + content */
function parseInput(text: string): { type: 'word' | 'mapping'; content: string; target?: string } {
  const trimmed = text.trim()
  // 检测映射分隔符 → 或 =
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

/** 是否显示新建提示 / Whether to show create hint */
const showCreateHint = computed(() => inputText.value.trim().length > 0 && !hasExactMatch.value)

/** 新建提示文案 / Create hint label */
const createHintLabel = computed(() => {
  const parsed = parseInput(inputText.value)
  if (parsed.type === 'mapping') {
    return t('hotwords.create_mapping_hint', { content: `${parsed.content} → ${parsed.target}` })
  }
  return t('hotwords.create_word_hint', { name: parsed.content })
})

/** 创建词条 / Create item */
function onCreate() {
  const parsed = parseInput(inputText.value)
  if (!parsed.content) return
  hw.addItem(parsed.type, parsed.content, parsed.target)
  inputText.value = ''
}

/** Enter 键处理 / Enter key handler */
function onUnifiedEnter() {
  if (showCreateHint.value) onCreate()
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

onMounted(() => hw.loadAll())
</script>

<style scoped>
.hw-page { padding: var(--s-5) var(--s-5) var(--s-6); display: flex; flex-direction: column; height: 100%; }

/* 工具栏 / Toolbar */
.hw-toolbar { display: flex; align-items: center; gap: var(--s-4); margin-bottom: var(--s-4); flex-shrink: 0; }
.hw-unified { flex: 1; min-width: 0; }
.hw-unified-field { display: flex; align-items: center; position: relative; }
.hw-unified-icon { position: absolute; left: 10px; color: var(--subtle); pointer-events: none; transition: color 0.15s; }
.hw-unified-input { width: 100%; max-width: 400px; padding: 8px 10px 8px 32px; border: none; border-bottom: 1px solid var(--border); border-radius: 0; font-size: 14px; outline: none; background: transparent; color: var(--fg); transition: border-color 0.15s; }
.hw-unified-input:focus { border-bottom-color: var(--accent); box-shadow: 0 1px 0 0 var(--accent); }
.hw-unified-input:focus ~ .hw-unified-icon,
.hw-unified-field:focus-within .hw-unified-icon { color: var(--accent); }
.hw-unified-input::placeholder { color: var(--subtle); }
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

/* 新建提示行 / Create hint row */
.hw-create-hint { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-3) var(--s-4); cursor: pointer; transition: background 0.12s; color: var(--accent); font-size: 13px; border-top: 1px dashed var(--border); }
.hw-create-hint:hover { background: var(--accent-soft); }
.hw-create-hint svg { flex-shrink: 0; }

/* 空状态 / Empty state */
.hw-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: var(--s-7); color: var(--muted); text-align: center; }
.hw-empty svg { width: 40px; height: 40px; color: var(--subtle); margin-bottom: var(--s-3); }
.hw-empty p { font-size: var(--fs-12); margin: 0; }

/* 统计栏 / Stats bar */
.hw-stats-bar { display: flex; align-items: center; gap: var(--s-4); padding: var(--s-2) var(--s-4); border-top: 1px solid var(--border); font-size: var(--fs-11); color: var(--muted); background: var(--surface-2); flex-shrink: 0; }
.hw-stats-bar span { display: flex; align-items: center; gap: 4px; }
</style>
