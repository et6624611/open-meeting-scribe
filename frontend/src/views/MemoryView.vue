<template>
  <div class="mem-page" :class="{ 'is-detail-open': mobileDetailOpen }">
    <div class="mem-inner">
      <header class="mem-head">
        <div>
          <h1 class="mem-title">{{ t('memory.title') }}</h1>
          <p class="mem-sub">{{ t('memory.subtitle') }}</p>
        </div>
        <button class="mem-btn" @click="onExport">{{ t('memory.export') }}</button>
      </header>

      <div class="mem-stats">
        <button class="mem-stat" @click="setView('open')">{{ t('memory.status.open') }} <b>{{ store.stats.open }}</b></button>
        <span class="mem-stat-sep">·</span>
        <button class="mem-stat" @click="setView('closed')">{{ t('memory.status.closed') }} <b>{{ store.stats.closed }}</b></button>
        <span class="mem-stat-sep">·</span>
        <button class="mem-stat" @click="setView('proposed')">{{ t('memory.status.proposed') }} <b>{{ store.stats.proposed }}</b></button>
      </div>

      <div v-if="store.stats.proposed > 0 && store.view !== 'proposed'" class="mem-banner">
        <span>{{ t('memory.banner.pending', { count: store.stats.proposed }) }}</span>
        <div class="mem-banner-actions">
          <button @click="startReview">{{ t('memory.banner.process') }}</button>
          <button @click="askIgnoreAll">{{ t('memory.banner.ignore_all') }}</button>
        </div>
      </div>

      <div class="mem-toolbar">
        <div class="mem-search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input ref="searchEl" v-model="searchText" class="mem-search-input" type="text" :placeholder="t('memory.search_ph')" />
        </div>
        <MemoryFilterPopover :namespaces="namespaces" />
        <button class="mem-btn mem-btn-primary" @click="startNew">+ {{ t('memory.add') }}</button>
      </div>

      <div class="mem-chips">
        <button
          v-for="v in VIEWS"
          :key="v"
          class="mem-chip"
          :class="{ 'is-active': store.view === v }"
          @click="setView(v)"
        >{{ t(`memory.status.${v}`) }} <span class="mem-chip-count">{{ countOf(v) }}</span></button>
      </div>

      <div class="mem-body">
        <section class="mem-pane mem-pane-list">
          <div v-if="store.error" class="mem-error" role="alert">
            <span>{{ store.error }}</span>
            <button class="mem-btn" @click="store.load()">{{ t('memory.action.retry') }}</button>
          </div>

          <div v-else-if="store.loading" class="mem-skeleton" aria-busy="true">
            <div v-for="n in 4" :key="n" class="mem-skeleton-row" />
          </div>

          <div v-else-if="store.items.length === 0" class="mem-empty">
            <p class="mem-empty-title">{{ hasFilter ? t('memory.search_empty') : t('memory.empty.title') }}</p>
            <p v-if="!hasFilter" class="mem-empty-desc">{{ t('memory.empty.desc') }}</p>
            <button v-else class="mem-btn" @click="clearFilters">{{ t('memory.action.clear_filters') }}</button>
          </div>

          <div v-else role="list" class="mem-list">
            <div
              v-for="it in store.items"
              :key="it.id"
              role="listitem"
              tabindex="0"
              class="mem-item"
              :class="[`is-${visualStatus(it)}`, { 'is-selected': it.id === store.selectedId }]"
              :data-mem-id="it.id"
              @click="onSelect(it)"
              @keydown.enter.prevent="startEdit(it)"
              @keydown.delete.prevent="askDelete(it)"
            >
              <div class="mem-item-text">{{ it.text }}</div>
              <div class="mem-item-meta">
                <span class="mem-kind-dot" :class="`k-${it.kind}`" aria-hidden="true" />
                <button
                  class="mem-kind-btn"
                  :aria-pressed="store.kind === it.kind"
                  @click.stop="pickKind(it.kind)"
                >{{ t(`memory.kind.${it.kind}`) }}</button>
                <span class="mem-ns">{{ nsLabel(it.namespace) }}</span>
                <span class="mem-date">{{ it.recorded_at.slice(0, 10) }}</span>
              </div>
            </div>
            <button v-if="store.hasMore" class="mem-more" @click="store.loadMore()">
              {{ store.loadingMore ? t('memory.loading') : t('memory.action.more') }}
            </button>
          </div>
        </section>

        <section class="mem-pane mem-pane-detail">
          <button class="mem-back" @click="mobileDetailOpen = false">← {{ t('memory.action.back') }}</button>

          <form v-if="store.draft" class="mem-form" @submit.prevent="saveDraft">
            <h2 class="mem-form-title">{{ store.draft.mode === 'new' ? t('memory.new_form.title') : t('memory.action.edit') }}</h2>
            <label class="mem-field">
              <span>{{ t('memory.fields.kind') }}</span>
              <select v-model="form.kind">
                <option v-for="k in KINDS" :key="k" :value="k">{{ t(`memory.kind.${k}`) }}</option>
              </select>
            </label>
            <label class="mem-field">
              <span>{{ t('memory.fields.scope') }}</span>
              <input v-model="form.namespace" class="mem-mono" placeholder="global / space:proj-a / role:pm" />
            </label>
            <label class="mem-field">
              <span>{{ t('memory.fields.text') }}</span>
              <textarea v-model="form.text" rows="4" maxlength="200" :placeholder="t('memory.new_form.text_ph')" />
              <em class="mem-counter">{{ form.text.length }}/200</em>
            </label>
            <p v-if="formError" class="mem-form-error">{{ formError }}</p>
            <div class="mem-form-actions">
              <button type="submit" class="mem-btn mem-btn-primary">{{ t('memory.action.save') }}</button>
              <button type="button" class="mem-btn" @click="cancelDraft">{{ t('memory.action.cancel') }}</button>
            </div>
          </form>

          <MemoryDetail
            v-else-if="store.selected"
            :item="store.selected"
            @edit="startEditSelected"
            @close="doClose"
            @reopen="doReopen"
            @delete="askDeleteSelected"
            @accept="doAccept"
            @reject="doReject"
          />

          <div v-else class="mem-placeholder">{{ t('memory.empty.title') }}</div>
        </section>
      </div>
    </div>

    <div v-if="deleteTarget" class="mem-overlay" @click.self="deleteTarget = null">
      <div class="mem-dialog" role="dialog" aria-modal="true">
        <h3>{{ t('memory.confirm.delete_title') }}</h3>
        <p>{{ t('memory.confirm.delete_desc', { text: snippet(deleteTarget.text) }) }}</p>
        <div class="mem-dialog-actions">
          <button class="mem-btn" @click="deleteTarget = null">{{ t('memory.confirm.cancel') }}</button>
          <button class="mem-btn mem-btn-danger" @click="confirmDelete">{{ t('memory.confirm.delete') }}</button>
        </div>
      </div>
    </div>

    <div v-if="ignoreAllCount > 0" class="mem-overlay" @click.self="ignoreAllCount = 0">
      <div class="mem-dialog" role="dialog" aria-modal="true">
        <h3>{{ t('memory.banner.ignore_all') }}</h3>
        <p>{{ t('memory.confirm.ignore_all_desc', { count: ignoreAllCount }) }}</p>
        <div class="mem-dialog-actions">
          <button class="mem-btn" @click="ignoreAllCount = 0">{{ t('memory.confirm.cancel') }}</button>
          <button class="mem-btn mem-btn-danger" @click="confirmIgnoreAll">{{ t('memory.banner.ignore_all') }}</button>
        </div>
      </div>
    </div>

    <div v-if="snack" class="mem-snack">
      <span>{{ snack.text }}</span>
      <button @click="runSnackUndo">{{ t('memory.action.undo') }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import MemoryDetail from '@/components/memory/MemoryDetail.vue'
import MemoryFilterPopover from '@/components/memory/MemoryFilterPopover.vue'
import { listMemory, type MemoryItem, type MemoryKind, type MemoryView } from '@/api/memory'
import { useMemoryStore } from '@/stores/memoryStore'
import { showToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/api/client'

const { t } = useI18n()
const store = useMemoryStore()

const VIEWS: MemoryView[] = ['open', 'closed', 'proposed', 'archived']
const KINDS: MemoryKind[] = ['preference', 'fact', 'decision', 'correction', 'habit', 'glossary']

const searchEl = ref<HTMLInputElement | null>(null)
const searchText = ref('')
const mobileDetailOpen = ref(false)
const deleteTarget = ref<MemoryItem | null>(null)
const ignoreAllCount = ref(0)
const formError = ref('')
const form = reactive({ kind: 'fact' as MemoryKind, namespace: 'global', text: '' })

const snack = ref<{ text: string; undo: () => void } | null>(null)
let snackTimer: ReturnType<typeof setTimeout> | null = null
let searchTimer: ReturnType<typeof setTimeout> | null = null
let ignoreTimer: ReturnType<typeof setTimeout> | null = null

const namespaces = computed(() => {
  const seen = new Set<string>()
  for (const item of store.items) seen.add(item.namespace)
  return [...seen].sort()
})

const hasFilter = computed(() => !!searchText.value.trim() || !!store.namespace || !!store.kind)

watch(searchText, (value) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    store.query = value
    void store.load()
  }, 300)
})

function visualStatus(item: MemoryItem): string {
  if (item.status === 'active') return item.valid_to ? 'closed' : 'open'
  return item.status
}

function nsLabel(ns: string): string {
  return ns === 'global' ? t('memory.scope_global') : ns
}

function countOf(v: MemoryView): number {
  return store.stats[v]
}

function setView(v: MemoryView) {
  store.view = v
  store.draft = null
  void store.load()
}

function pickKind(kind: MemoryKind) {
  store.kind = store.kind === kind ? '' : kind
  void store.load()
}

function clearFilters() {
  searchText.value = ''
  store.query = ''
  store.namespace = ''
  store.kind = ''
  void store.load()
}

function onSelect(item: MemoryItem) {
  store.select(item.id)
  mobileDetailOpen.value = true
}

function startReview() {
  store.view = 'proposed'
  void store.load().then(() => {
    if (store.items.length) {
      store.select(store.items[0].id)
      mobileDetailOpen.value = true
    }
  })
}

function startNew() {
  form.kind = 'fact'
  form.namespace = 'global'
  form.text = ''
  formError.value = ''
  store.draft = { mode: 'new' }
  mobileDetailOpen.value = true
  nextTick(() => document.querySelector<HTMLTextAreaElement>('.mem-form textarea')?.focus())
}

function startEdit(item: MemoryItem) {
  form.kind = item.kind
  form.namespace = item.namespace
  form.text = item.text
  formError.value = ''
  store.draft = { mode: 'edit', id: item.id }
  mobileDetailOpen.value = true
  nextTick(() => document.querySelector<HTMLTextAreaElement>('.mem-form textarea')?.focus())
}

function startEditSelected() {
  if (store.selected) startEdit(store.selected)
}

function cancelDraft() {
  store.draft = null
  formError.value = ''
}

async function saveDraft() {
  const text = form.text.trim()
  if (!text) {
    formError.value = t('memory.new_form.required')
    return
  }
  if (text.length > 200) {
    formError.value = t('memory.new_form.too_long')
    return
  }
  try {
    if (store.draft?.mode === 'edit') {
      await store.update(store.draft.id, { text, kind: form.kind, namespace: form.namespace })
    } else {
      await store.create({ text, kind: form.kind, namespace: form.namespace })
    }
    showToast(t('memory.toast.saved'), 'success')
  } catch (err) {
    formError.value = extractErrorMessage(err, t('memory.action.save'))
  }
}

function askDelete(item: MemoryItem) {
  deleteTarget.value = item
}

function askDeleteSelected() {
  if (store.selected) askDelete(store.selected)
}

function snippet(text: string): string {
  return text.length > 40 ? `${text.slice(0, 40)}…` : text
}

async function confirmDelete() {
  const item = deleteTarget.value
  deleteTarget.value = null
  if (!item) return
  try {
    await store.remove(item.id)
    showToast(t('memory.toast.deleted'), 'success')
  } catch (err) {
    showToast(extractErrorMessage(err), 'error')
  }
}

function flashSnack(text: string, undo: () => void) {
  if (snackTimer) clearTimeout(snackTimer)
  snack.value = { text, undo }
  snackTimer = setTimeout(() => { snack.value = null }, 5000)
}

function runSnackUndo() {
  const current = snack.value
  if (!current) return
  if (snackTimer) clearTimeout(snackTimer)
  snack.value = null
  current.undo()
}

async function doClose() {
  const item = store.selected
  if (!item) return
  const id = item.id
  try {
    await store.close(id)
    flashSnack(t('memory.toast.closed'), async () => {
      await store.reopen(id)
      await store.load()
      showToast(t('memory.toast.undone'))
    })
  } catch (err) {
    showToast(extractErrorMessage(err), 'error')
  }
}

async function doReopen() {
  const item = store.selected
  if (!item) return
  try {
    await store.reopen(item.id)
  } catch (err) {
    showToast(extractErrorMessage(err), 'error')
  }
}

async function doAccept() {
  const item = store.selected
  if (!item) return
  try {
    await store.accept(item.id)
    if (store.items.length) {
      store.select(store.items[0].id)
      mobileDetailOpen.value = true
    } else {
      showToast(t('memory.toast.batch_done'), 'success')
    }
  } catch (err) {
    showToast(extractErrorMessage(err), 'error')
  }
}

async function doReject() {
  const item = store.selected
  if (!item) return
  try {
    await store.reject(item.id)
    if (store.items.length) {
      store.select(store.items[0].id)
      mobileDetailOpen.value = true
    } else {
      showToast(t('memory.toast.batch_done'), 'success')
    }
  } catch (err) {
    showToast(extractErrorMessage(err), 'error')
  }
}

async function askIgnoreAll() {
  try {
    const result = await listMemory({ view: 'proposed', limit: 200 })
    ignoreAllCount.value = result.items.length
  } catch (err) {
    showToast(extractErrorMessage(err), 'error')
  }
}

async function confirmIgnoreAll() {
  const count = ignoreAllCount.value
  ignoreAllCount.value = 0
  if (!count) return

  let pending: MemoryItem[] = []
  try {
    pending = (await listMemory({ view: 'proposed', limit: 200 })).items
  } catch (err) {
    showToast(extractErrorMessage(err), 'error')
    return
  }
  const ids = pending.map(it => it.id)
  const idSet = new Set(ids)
  const before = store.items
  store.items = store.items.filter(it => !idSet.has(it.id))
  if (store.selectedId && idSet.has(store.selectedId)) {
    store.selectedId = store.items[0]?.id || null
  }

  const run = async () => {
    for (const id of ids) {
      try { await store.reject(id) } catch { /* 继续处理其余条目 */ }
    }
    showToast(t('memory.toast.batch_done'), 'success')
  }

  ignoreTimer = setTimeout(() => { void run() }, 5000)
  flashSnack(t('memory.toast.all_ignored'), () => {
    if (ignoreTimer) clearTimeout(ignoreTimer)
    ignoreTimer = null
    store.items = before
    void store.loadStats()
    showToast(t('memory.toast.undone'))
  })
}

async function onExport() {
  try {
    await store.exportAll()
  } catch (err) {
    showToast(extractErrorMessage(err), 'error')
  }
}

function moveSelection(delta: number) {
  if (!store.items.length) return
  const index = store.items.findIndex(it => it.id === store.selectedId)
  const nextIndex = index < 0 ? 0 : Math.max(0, Math.min(store.items.length - 1, index + delta))
  const next = store.items[nextIndex]
  if (!next) return
  store.select(next.id)
  mobileDetailOpen.value = true
  nextTick(() => {
    document.querySelector<HTMLElement>(`[data-mem-id="${next.id}"]`)?.scrollIntoView({ block: 'nearest' })
  })
}

function onGlobalKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (deleteTarget.value) { deleteTarget.value = null; return }
    if (ignoreAllCount.value) { ignoreAllCount.value = 0; return }
    if (store.draft) { cancelDraft(); return }
    if (searchText.value) { searchText.value = ''; return }
    return
  }

  const el = document.activeElement as HTMLElement | null
  const typing = !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)
  if (typing) return

  if (e.key === '/') {
    e.preventDefault()
    searchEl.value?.focus()
    return
  }
  if (e.key === 'ArrowDown') { e.preventDefault(); moveSelection(1) }
  if (e.key === 'ArrowUp') { e.preventDefault(); moveSelection(-1) }
}

onMounted(() => {
  void store.loadStats()
  void store.load()
  document.addEventListener('keydown', onGlobalKey)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onGlobalKey)
  if (searchTimer) clearTimeout(searchTimer)
  if (snackTimer) clearTimeout(snackTimer)
  if (ignoreTimer) clearTimeout(ignoreTimer)
})
</script>

<style scoped>
.mem-page { padding: var(--s-5); }
.mem-inner { width: 100%; max-width: 1080px; margin: 0 auto; display: flex; flex-direction: column; gap: var(--s-3); }

.mem-head { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--s-4); }
.mem-title { margin: 0; font-size: var(--fs-24); font-weight: 600; }
.mem-sub { margin: 4px 0 0; font-size: var(--fs-12); color: var(--muted); }
.mem-stats { display: flex; align-items: center; gap: var(--s-2); font-size: var(--fs-12); color: var(--muted); }
.mem-stat { color: var(--muted); font-size: var(--fs-12); }
.mem-stat b { color: var(--fg); font-weight: 600; }
.mem-stat:hover { color: var(--accent); }
.mem-stat-sep { color: var(--border-strong); }

.mem-banner {
  display: flex; align-items: center; justify-content: space-between; gap: var(--s-3);
  padding: var(--s-2) var(--s-3); border: 1px solid var(--warn-border);
  border-radius: var(--radius-sm); background: var(--warn-soft);
  font-size: var(--fs-12); color: var(--fg);
}
.mem-banner-actions { display: flex; gap: var(--s-2); }
.mem-banner-actions button { color: var(--accent); font-size: var(--fs-12); }
.mem-banner-actions button:hover { text-decoration: underline; }

.mem-toolbar { display: flex; align-items: center; gap: var(--s-2); }
.mem-search {
  flex: 1; display: flex; align-items: center; gap: 6px;
  padding: 6px 10px; border: 1px solid var(--border);
  border-radius: var(--radius-sm); background: var(--surface); color: var(--subtle);
}
.mem-search:focus-within { border-color: var(--accent); }
.mem-search-input { flex: 1; min-width: 0; border: 0; outline: none; background: transparent; font-size: var(--fs-13); color: var(--fg); }

.mem-chips { display: flex; gap: var(--s-1); flex-wrap: wrap; }
.mem-chip {
  padding: 4px 10px; border-radius: 4px; font-size: var(--fs-11);
  color: var(--muted); transition: background 0.12s, color 0.12s;
}
.mem-chip:hover { background: var(--surface-2); color: var(--fg); }
.mem-chip.is-active { background: var(--accent-soft); color: var(--accent); }
.mem-chip-count { margin-left: 4px; color: var(--subtle); }

.mem-body { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: var(--s-4); align-items: start; }
.mem-pane { min-width: 0; }

.mem-list { display: flex; flex-direction: column; gap: 2px; }
.mem-item {
  border-left: 3px solid transparent; border-radius: var(--radius-xs);
  padding: 8px 10px; cursor: pointer; transition: background 0.12s;
}
.mem-item:hover { background: var(--surface-2); }
.mem-item.is-proposed { border-left-color: var(--warn); }
.mem-item.is-closed { border-left-color: var(--muted); }
.mem-item.is-closed .mem-item-text { color: var(--muted); }
.mem-item.is-archived { border-left-color: var(--border-strong); }
.mem-item.is-archived .mem-item-text { color: var(--muted); }
.mem-item.is-selected { background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-mid); }
.mem-item-text {
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; font-size: var(--fs-13); color: var(--fg); line-height: 1.45; word-break: break-word;
}
.mem-item-meta { display: flex; align-items: center; gap: 6px; margin-top: 4px; font-size: var(--fs-11); color: var(--subtle); }
.mem-kind-dot { width: 6px; height: 6px; border-radius: 999px; background: var(--accent); flex-shrink: 0; }
.mem-kind-dot.k-preference { background: var(--info); }
.mem-kind-dot.k-fact { background: var(--accent); }
.mem-kind-dot.k-decision { background: var(--purple); }
.mem-kind-dot.k-correction { background: var(--warn); }
.mem-kind-dot.k-habit { background: var(--ok); }
.mem-kind-dot.k-glossary { background: var(--muted); }
.mem-kind-btn { font-size: var(--fs-11); color: var(--muted); }
.mem-kind-btn:hover { color: var(--accent); text-decoration: underline; }
.mem-kind-btn[aria-pressed="true"] { color: var(--accent); }
.mem-ns { font-family: var(--font-mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mem-date { margin-left: auto; white-space: nowrap; }
.mem-more { margin-top: var(--s-2); padding: 6px; font-size: var(--fs-12); color: var(--accent); }

.mem-pane-detail { border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); min-height: 240px; }
.mem-placeholder { padding: var(--s-7); text-align: center; color: var(--muted); font-size: var(--fs-12); }
.mem-back { display: none; padding: var(--s-2) var(--s-3); font-size: var(--fs-12); color: var(--accent); }

.mem-form { display: flex; flex-direction: column; gap: var(--s-3); padding: var(--s-5); }
.mem-form-title { margin: 0; font-size: var(--fs-15); font-weight: 600; }
.mem-field { display: flex; flex-direction: column; gap: 4px; font-size: var(--fs-12); color: var(--muted); }
.mem-field input, .mem-field select, .mem-field textarea {
  padding: 7px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface); color: var(--fg); font-size: var(--fs-13); outline: none;
}
.mem-field input:focus, .mem-field select:focus, .mem-field textarea:focus { border-color: var(--accent); box-shadow: var(--shadow-focus); }
.mem-field textarea { resize: vertical; min-height: 88px; }
.mem-mono { font-family: var(--font-mono); }
.mem-counter { align-self: flex-end; font-style: normal; font-size: var(--fs-11); color: var(--subtle); }
.mem-form-error { margin: 0; font-size: var(--fs-12); color: var(--error); }
.mem-form-actions { display: flex; gap: var(--s-2); }

.mem-btn {
  padding: 6px 12px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface); color: var(--fg); font-size: var(--fs-12);
  transition: border-color 0.15s, background 0.15s;
}
.mem-btn:hover { border-color: var(--border-strong); background: var(--surface-2); }
.mem-btn-primary { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
.mem-btn-primary:hover { background: var(--accent); border-color: var(--accent); opacity: 0.92; }
.mem-btn-danger { color: var(--error); border-color: var(--error-border); }
.mem-btn-danger:hover { background: var(--error-soft); border-color: var(--error); }

.mem-skeleton { display: flex; flex-direction: column; gap: var(--s-2); }
.mem-skeleton-row { height: 48px; border-radius: var(--radius-sm); background: var(--surface-2); animation: mem-pulse 1.2s ease-in-out infinite; }
@keyframes mem-pulse { 50% { opacity: 0.55; } }

.mem-empty { display: flex; flex-direction: column; align-items: center; gap: var(--s-2); padding: var(--s-7) var(--s-4); text-align: center; }
.mem-empty-title { margin: 0; font-size: var(--fs-13); color: var(--fg); }
.mem-empty-desc { margin: 0; font-size: var(--fs-12); color: var(--muted); }
.mem-error { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-4); font-size: var(--fs-12); color: var(--error); }

.mem-overlay {
  position: fixed; inset: 0; z-index: var(--z-modal);
  display: grid; place-items: center; background: var(--overlay-bg);
}
.mem-dialog {
  width: var(--modal-width-sm); max-width: calc(100% - var(--s-6));
  padding: var(--s-5); background: var(--surface);
  border: 1px solid var(--border-strong); border-radius: var(--radius-lg);
  box-shadow: var(--shadow-float);
}
.mem-dialog h3 { margin: 0 0 var(--s-2); font-size: var(--fs-15); }
.mem-dialog p { margin: 0 0 var(--s-4); font-size: var(--fs-13); color: var(--muted); word-break: break-word; }
.mem-dialog-actions { display: flex; justify-content: flex-end; gap: var(--s-2); }

.mem-snack {
  position: fixed; left: 50%; bottom: var(--s-7); transform: translateX(-50%);
  z-index: var(--z-toast); display: flex; align-items: center; gap: var(--s-3);
  padding: var(--s-2) var(--s-4); background: var(--surface);
  border: 1px solid var(--border-strong); border-radius: var(--radius-pill);
  box-shadow: var(--shadow-float); font-size: var(--fs-12); color: var(--fg);
}
.mem-snack button { color: var(--accent); font-size: var(--fs-12); }
.mem-snack button:hover { text-decoration: underline; }

@media (max-width: 900px) {
  .mem-body { grid-template-columns: 1fr; }
  .mem-back { display: inline-block; }
  .mem-page.is-detail-open .mem-pane-list { display: none; }
  .mem-page:not(.is-detail-open) .mem-pane-detail { display: none; }
}
</style>
