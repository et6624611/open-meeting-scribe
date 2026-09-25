<template>
  <!-- 执行人选人控件（DC-R2-b / D4）：以说话人档案为数据源，可搜索、可手打即时建档
       Owner combobox backed by the speaker archive: search, select, or type-to-create -->
  <div class="own-combo" ref="rootRef">
    <button
      type="button"
      class="own-combo-trigger"
      :class="{ 'is-empty': !modelValue }"
      role="combobox"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-label="`${label}: ${selectedLabel}`"
      @click="toggle"
      @keydown="onTriggerKeydown"
    >
      <svg class="own-combo-icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      <span class="own-combo-value">{{ selectedLabel }}</span>
      <svg class="own-combo-chev" :class="{ open }" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
    </button>
    <div v-show="open" class="own-combo-pop">
      <div class="own-combo-search-wrap">
        <svg class="own-combo-search-icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input
          ref="searchRef"
          v-model="query"
          type="text"
          class="own-combo-search"
          role="combobox"
          aria-expanded="true"
          :aria-activedescendant="focusedId || undefined"
          :placeholder="t('decisions.owner_search_placeholder')"
          @keydown="onSearchKeydown"
        />
      </div>
      <div class="own-combo-list" role="listbox" :aria-label="label">
        <!-- 档案里没有这个名字：手打即建档（不跳页、不断流） -->
        <button
          v-if="canCreate"
          id="own-opt-create"
          class="own-combo-opt own-combo-create"
          :class="{ 'is-focused': focusedId === 'own-opt-create' }"
          role="option"
          @click="createAndSelect"
          @mouseenter="focusedId = 'own-opt-create'"
        >
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          {{ t('decisions.owner_create_hint', { name: query.trim() }) }}
        </button>
        <button
          v-for="(sp, i) in filtered"
          :id="`own-opt-${i}`"
          :key="sp.id"
          class="own-combo-opt"
          :class="{ 'is-focused': focusedId === `own-opt-${i}`, 'is-selected': modelValue?.id === sp.id }"
          role="option"
          :aria-selected="modelValue?.id === sp.id"
          @click="selectSpeaker(sp)"
          @mouseenter="focusedId = `own-opt-${i}`"
        >
          <span class="own-combo-name">{{ sp.name }}</span>
          <span v-if="sp.role" class="own-combo-role">{{ sp.role }}</span>
        </button>
        <div v-if="!filtered.length && !canCreate && !loading" class="own-combo-empty">{{ t('decisions.owner_no_match') }}</div>
        <div v-if="loading" class="own-combo-empty">{{ t('decisions.owner_loading') }}</div>
        <!-- 清空指派：执行人可留空（D4，auto 决策一律为空） -->
        <button v-if="modelValue" class="own-combo-opt own-combo-clear" @click="clearOwner">
          {{ t('decisions.owner_clear') }}
        </button>
      </div>
      <p v-if="createError" class="own-combo-error" role="alert">{{ createError }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { createSpeaker, fetchSpeakers, type Speaker } from '@/api/speakers'
import type { OwnerValue } from '@/api/decisions'
import { isPlaceholderName } from '@/utils/speakerDisplay'

const { t } = useI18n()

const props = defineProps<{
  modelValue: OwnerValue
  label: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: OwnerValue): void
}>()

const rootRef = ref<HTMLElement | null>(null)
const searchRef = ref<HTMLInputElement | null>(null)
const open = ref(false)
const query = ref('')
const focusedId = ref('')
const loading = ref(false)
const createError = ref('')

// 档案列表按需拉取：首次展开控件时才请求，同一实例内缓存
const speakers = ref<Speaker[]>([])
let loaded = false

async function ensureLoaded() {
  if (loaded || loading.value) return
  loading.value = true
  try {
    const list = await fetchSpeakers()
    // 占位档案名（Speaker N 等）不作为执行人候选（REQ-SPK-RN 口径同源）
    speakers.value = list.filter(s => s.name && !isPlaceholderName(s.name))
    loaded = true
  } catch {
    /* 档案拉取失败时仍可手打建档，不阻断补录 / archive fetch failure never blocks entry */
  } finally {
    loading.value = false
  }
}

const filtered = computed(() => {
  const kw = query.value.trim().toLowerCase()
  const list = kw ? speakers.value.filter(s => s.name.toLowerCase().includes(kw)) : speakers.value
  return [...list].sort((a, b) => a.name.localeCompare(b.name, 'zh-Hans-CN'))
})

/** 键入内容在档案中无同名 → 提供「即时建档」出口 */
const canCreate = computed(() => {
  const kw = query.value.trim()
  if (!kw || isPlaceholderName(kw)) return false
  return !speakers.value.some(s => s.name === kw)
})

const selectedLabel = computed(() => props.modelValue?.name || t('decisions.owner_none'))

function toggle() {
  open.value = !open.value
  if (open.value) {
    query.value = ''
    focusedId.value = ''
    createError.value = ''
    void ensureLoaded()
    nextTick(() => searchRef.value?.focus())
  }
}

function close() {
  open.value = false
}

function selectSpeaker(sp: Speaker) {
  emit('update:modelValue', { id: sp.id, name: sp.name })
  close()
}

function clearOwner() {
  emit('update:modelValue', null)
  close()
}

async function createAndSelect() {
  const name = query.value.trim()
  if (!name || createError.value === '__pending__') return
  createError.value = '__pending__'
  try {
    const created = await createSpeaker(name)
    // 本实例去重插入，保证重开时新档案已在列
    if (!speakers.value.some(s => s.id === created.id)) speakers.value.push(created)
    emit('update:modelValue', { id: created.id, name: created.name })
    createError.value = ''
    close()
  } catch {
    createError.value = t('decisions.owner_create_failed')
  }
}

/** 焦点项序列：建档行（若有）优先，其后档案，与列表 DOM 顺序一致 */
const focusable = computed<string[]>(() => {
  const ids: string[] = []
  if (canCreate.value) ids.push('own-opt-create')
  filtered.value.forEach((_, i) => ids.push(`own-opt-${i}`))
  return ids
})

function moveFocus(delta: number) {
  const ids = focusable.value
  if (!ids.length) return
  const cur = ids.indexOf(focusedId.value)
  const next = cur < 0 ? (delta > 0 ? 0 : ids.length - 1) : (cur + delta + ids.length) % ids.length
  focusedId.value = ids[next]
  document.getElementById(ids[next])?.scrollIntoView({ block: 'nearest' })
}

function activateFocused() {
  const id = focusedId.value
  if (id === 'own-opt-create') { void createAndSelect(); return }
  const m = /^own-opt-(\d+)$/.exec(id)
  if (m) {
    const sp = filtered.value[Number(m[1])]
    if (sp) selectSpeaker(sp)
    return
  }
  // 未显式聚焦：有建档出口优先走建档，否则选中首个同名档案
  if (canCreate.value) { void createAndSelect(); return }
  if (filtered.value.length) selectSpeaker(filtered.value[0])
}

function onSearchKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') { e.preventDefault(); moveFocus(1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); moveFocus(-1) }
  else if (e.key === 'Enter') { e.preventDefault(); activateFocused() }
  else if (e.key === 'Escape') { e.preventDefault(); close() }
  else { focusedId.value = ''; createError.value = '' }
}

function onTriggerKeydown(e: KeyboardEvent) {
  if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
    e.preventDefault()
    if (!open.value) toggle()
  } else if (e.key === 'Escape' && open.value) {
    close()
  }
}

function onDocClick(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) close()
}
onMounted(() => document.addEventListener('click', onDocClick, true))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick, true))
</script>

<style scoped>
.own-combo { position: relative; display: block; width: 100%; }
.own-combo-trigger {
  display: flex; align-items: center; gap: 6px; width: 100%; box-sizing: border-box;
  padding: 8px 10px; font-size: var(--fs-13, 13px); border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface-1, transparent); color: var(--fg); cursor: pointer; text-align: left;
}
.own-combo-trigger:hover { border-color: var(--border-strong); }
.own-combo-trigger:focus-visible { outline: none; border-color: var(--accent); }
.own-combo-trigger.is-empty { color: var(--muted); }
.own-combo-icon { flex-shrink: 0; color: var(--muted); }
.own-combo-value { min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.own-combo-chev { flex-shrink: 0; color: var(--muted); transition: transform 0.15s; }
.own-combo-chev.open { transform: rotate(180deg); }

.own-combo-pop {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 40; min-width: 240px;
  border: 1px solid var(--border); border-radius: var(--radius-md, 8px); background: var(--surface-1, var(--bg, #fff));
  box-shadow: var(--dropdown-shadow); padding: var(--s-2);
}
.own-combo-search-wrap { position: relative; display: flex; align-items: center; }
.own-combo-search-icon { position: absolute; left: 8px; color: var(--muted); pointer-events: none; }
.own-combo-search {
  width: 100%; box-sizing: border-box; padding: 6px 8px 6px 26px; font-size: var(--fs-13, 13px);
  border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--fg);
}
.own-combo-search:focus { outline: none; border-color: var(--accent); }
.own-combo-list { margin-top: 6px; max-height: 220px; overflow-y: auto; display: flex; flex-direction: column; }
.own-combo-opt {
  display: flex; align-items: center; gap: 6px; text-align: left; padding: 6px 8px; font-size: var(--fs-13, 13px);
  border: none; border-radius: var(--radius-sm); background: transparent; color: var(--fg); cursor: pointer;
}
.own-combo-opt:hover, .own-combo-opt.is-focused { background: var(--surface-2); }
.own-combo-opt.is-selected { color: var(--accent); font-weight: 500; }
.own-combo-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.own-combo-role { margin-left: auto; font-size: var(--fs-11, 11px); color: var(--subtle); white-space: nowrap; }
.own-combo-create { color: var(--accent); }
.own-combo-clear { color: var(--muted); border-top: 1px solid var(--border); border-radius: 0; margin-top: 4px; }
.own-combo-empty { padding: var(--s-3); text-align: center; font-size: var(--fs-12, 12px); color: var(--muted); }
.own-combo-error { margin: 6px 0 0; font-size: var(--fs-12, 12px); color: var(--error); }
</style>
