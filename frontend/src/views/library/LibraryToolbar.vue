<template>
  <div class="lib-header-bar">
    <div class="lib-title-group">
      <h1>{{ t('library.title') }}</h1>
      <span v-if="hasLibFilter" class="lib-count">{{ t('library.count_matched', { matched: libCountDisplay, total: libTabTotal }) }}</span>
      <span v-else class="lib-count">{{ t('library.count', { count: libCountDisplay }) }}</span>
    </div>
    <div class="lib-search-wrap">
      <svg class="search-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input
        :value="searchQuery"
        class="lib-search-input"
        type="text"
        :placeholder="t('library.search_placeholder')"
        @input="$emit('update:searchQuery', ($event.target as HTMLInputElement).value)"
      />
    </div>
  </div>

  <!-- Tab 切换 -->
  <div class="lib-tabs">
    <button class="lib-tab" :class="{ active: !showArchived }" @click="$emit('switchTab', false)">
      {{ t('library.tab_active') }}
      <span class="lib-tab-count">{{ activeTabCount }}</span>
    </button>
    <button class="lib-tab" :class="{ active: showArchived }" @click="$emit('switchTab', true)">
      {{ t('library.tab_archived') }}
      <span class="lib-tab-count">{{ archivedTabCount }}</span>
    </button>
  </div>

  <!-- 筛选工具栏 -->
  <div class="lib-filter-bar" :class="{ 'is-active': hasActiveFilter }">
    <div class="lib-filter-group lib-date-group">
      <label class="lib-filter-label">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
      </label>
      <input type="date" :value="dateFrom" @input="$emit('update:dateFrom', ($event.target as HTMLInputElement).value)" class="lib-date-input" :title="t('library.filter_date_from')" />
      <span class="lib-date-sep">–</span>
      <input type="date" :value="dateTo" @input="$emit('update:dateTo', ($event.target as HTMLInputElement).value)" class="lib-date-input" :title="t('library.filter_date_to')" />
      <span class="lib-filter-divider"></span>
      <button class="lib-filter-chip" @click="$emit('quickRange', 7)">{{ t('library.filter_week') }}</button>
      <button class="lib-filter-chip" @click="$emit('quickRange', 30)">{{ t('library.filter_30days') }}</button>
    </div>
    <div class="lib-filter-group">
      <label class="lib-filter-label">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      </label>
      <button
        ref="triggerRef"
        type="button"
        class="lib-speaker-select lib-speaker-trigger"
        v-bind="triggerAttrs"
        @click="toggle"
      >
        <span class="lib-speaker-trigger-text" :class="{ 'is-placeholder': !filterSpeakerId }">
          {{ speakerTriggerLabel }}
        </span>
        <svg class="lib-speaker-caret" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
      <Teleport to="body">
        <div
          v-if="visible"
          ref="menuRef"
          v-bind="menuAttrs"
          class="pop-menu lib-speaker-menu"
        >
          <div class="lib-speaker-search">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input
              ref="searchRef"
              :value="speakerSearchQuery"
              @input="$emit('update:speakerSearchQuery', ($event.target as HTMLInputElement).value)"
              type="text"
              class="lib-speaker-search-input"
              :placeholder="t('library.filter_speaker_search')"
            />
          </div>
          <div class="lib-speaker-list">
            <button type="button" role="menuitem" class="lib-speaker-item" :class="{ 'is-active': filterSpeakerId === '' }" @click="onPick('')">
              {{ t('library.filter_speaker_all') }}
            </button>
            <button
              v-for="name in filteredSpeakerNames" :key="name"
              type="button" role="menuitem" class="lib-speaker-item"
              :class="{ 'is-active': filterSpeakerId === name }" @click="onPick(name)"
            >{{ name }}</button>
            <button
              v-if="libraryHasUnidentified && unidVisible"
              type="button" role="menuitem" class="lib-speaker-item"
              :class="{ 'is-active': filterSpeakerId === unidFilter }" @click="onPick(unidFilter)"
            >{{ t('library.filter_speaker_unidentified') }}</button>
            <div v-if="!filteredSpeakerNames.length && !unidVisible" class="lib-speaker-empty">
              {{ t('library.filter_speaker_empty') }}
            </div>
          </div>
        </div>
      </Teleport>
    </div>
    <div v-if="hasActiveFilter" class="lib-filter-actions">
      <button class="lib-filter-clear" @click="$emit('clearFilters')">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        {{ t('library.filter_clear') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePopMenu } from '@/composables/usePopMenu'

const { t } = useI18n()

defineProps<{
  searchQuery: string
  showArchived: boolean
  hasLibFilter: boolean
  libCountDisplay: number
  libTabTotal: number
  activeTabCount: number
  archivedTabCount: number
  dateFrom: string
  dateTo: string
  hasActiveFilter: boolean
  filterSpeakerId: string
  speakerTriggerLabel: string
  filteredSpeakerNames: string[]
  unidVisible: boolean
  libraryHasUnidentified: boolean
  speakerSearchQuery: string
  unidFilter: string
}>()

const emit = defineEmits<{
  (e: 'update:searchQuery', v: string): void
  (e: 'switchTab', showArchived: boolean): void
  (e: 'update:dateFrom', v: string): void
  (e: 'update:dateTo', v: string): void
  (e: 'quickRange', days: number): void
  (e: 'update:speakerSearchQuery', v: string): void
  (e: 'selectSpeaker', value: string): void
  (e: 'clearFilters'): void
}>()

// speaker menu refs — 本组件内部，与 usePopMenu 同组件
const triggerRef = ref<HTMLElement | null>(null)
const menuRef = ref<HTMLElement | null>(null)
const searchRef = ref<HTMLInputElement | null>(null)

const { visible, toggle, triggerAttrs, menuAttrs } = usePopMenu(menuRef, triggerRef)

watch(visible, (v) => {
  if (v) nextTick(() => searchRef.value?.focus())
  else emit('update:speakerSearchQuery', '')
})

function onPick(value: string) {
  emit('selectSpeaker', value)
  visible.value = false
}
</script>

<style scoped>
.lib-header-bar { display: flex; align-items: center; justify-content: space-between; gap: var(--s-4); margin-bottom: var(--s-5); }
.lib-title-group { display: flex; align-items: center; gap: var(--s-3); flex-shrink: 0; }
.lib-title-group h1 { font-size: 22px; font-weight: 700; margin: 0; letter-spacing: -0.01em; }
.lib-count { font-size: 13px; color: var(--subtle); }
.lib-search-wrap { position: relative; flex: 1; max-width: 480px; }
.lib-search-wrap .search-icon { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--subtle); pointer-events: none; }
.lib-search-input { width: 100%; padding: 10px var(--s-4) 10px 38px; border: none; border-bottom: 1px solid var(--border); border-radius: 0; background: transparent; font-size: 14px; outline: none; transition: border-color 0.15s, box-shadow 0.15s; }
.lib-search-input:focus { border-bottom-color: var(--accent); box-shadow: 0 1px 0 0 var(--accent); }

.lib-tabs { display: flex; gap: 0; margin-bottom: var(--s-4); border-bottom: 1px solid var(--border); }
.lib-tab { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-2) var(--s-4); border: none; border-radius: 0; background: transparent; color: var(--muted); font-size: 13px; cursor: pointer; transition: all 0.15s; border-bottom: 2px solid transparent; margin-bottom: -1px; }
.lib-tab:hover { background: transparent; color: var(--fg); }
.lib-tab.active { background: transparent; color: var(--accent); font-weight: 600; border-bottom-color: var(--accent); box-shadow: none; }
.lib-tab-count { font-size: 11px; padding: 1px 6px; border-radius: 10px; background: var(--surface-2); color: var(--subtle); line-height: 1.4; }
.lib-tab.active .lib-tab-count { background: var(--accent-soft); color: var(--accent); }

.lib-filter-bar { display: flex; align-items: center; gap: var(--s-4); margin-bottom: var(--s-4); padding: var(--s-2) var(--s-3); background: transparent; transition: border-color 0.15s; flex-wrap: wrap; }
.lib-filter-group { display: flex; align-items: center; gap: var(--s-2); }
.lib-date-group { flex-wrap: wrap; }
.lib-filter-divider { width: 1px; height: 16px; background: var(--border); margin: 0 2px; flex-shrink: 0; }
.lib-filter-label { color: var(--subtle); display: flex; align-items: center; flex-shrink: 0; }
.lib-date-input { border: none; border-bottom: 1px solid var(--border); border-radius: 0; padding: 4px 8px; font-size: 12px; background: transparent; color: var(--fg); outline: none; transition: border-color 0.12s; }
.lib-date-input:focus { border-bottom-color: var(--accent); box-shadow: 0 1px 0 0 var(--accent); }
.lib-date-sep { color: var(--subtle); font-size: 12px; }
.lib-speaker-select { border: none; border-bottom: 1px solid var(--border); border-radius: 0; padding: 4px 8px; font-size: 12px; background: transparent; color: var(--fg); outline: none; cursor: pointer; transition: border-color 0.12s; min-width: 120px; }
.lib-speaker-select:focus { border-bottom-color: var(--accent); box-shadow: 0 1px 0 0 var(--accent); }
.lib-speaker-trigger { display: inline-flex; align-items: center; justify-content: space-between; gap: 6px; }
.lib-speaker-trigger-text.is-placeholder { color: var(--muted); }
.lib-speaker-caret { flex-shrink: 0; color: var(--muted); transition: transform 0.15s; }
.lib-speaker-menu { position: fixed; z-index: var(--z-popover); min-width: 200px; max-width: 280px; background: var(--dropdown-bg); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18); overflow: hidden; display: flex; flex-direction: column; }
.lib-speaker-search { display: flex; align-items: center; gap: 6px; padding: 8px 12px; border-bottom: 1px solid var(--border); color: var(--muted); }
.lib-speaker-search-input { flex: 1; border: none; background: transparent; color: var(--fg); font-size: 13px; outline: none; min-width: 0; }
.lib-speaker-search-input::placeholder { color: var(--subtle); }
.lib-speaker-list { max-height: 240px; overflow-y: auto; padding: 4px 0; }
.lib-speaker-item { display: block; width: 100%; text-align: left; padding: 8px 12px; border: none; background: transparent; color: var(--fg); font-size: 13px; cursor: pointer; transition: background-color 0.1s; }
.lib-speaker-item:hover, .lib-speaker-item:focus-visible { background: var(--surface-2); outline: none; }
.lib-speaker-item.is-active { color: var(--accent); font-weight: 500; }
.lib-speaker-empty { padding: 16px 12px; text-align: center; color: var(--muted); font-size: 12px; }
.lib-filter-actions { display: flex; align-items: center; gap: var(--s-2); margin-left: auto; }
.lib-filter-chip { padding: 3px 10px; border-radius: 4px; font-size: 11px; border: none; background: transparent; color: var(--muted); cursor: pointer; transition: all 0.12s; }
.lib-filter-chip:hover { background: var(--surface-2); color: var(--fg); }
.lib-filter-clear { display: flex; align-items: center; gap: 4px; padding: 3px 8px; border: none; border-radius: var(--radius-sm); font-size: 11px; background: transparent; color: var(--subtle); cursor: pointer; transition: color 0.12s; }
.lib-filter-clear:hover { color: var(--fg); }

@media (max-width: 1000px) { .lib-search-wrap { max-width: 380px; } }
@media (max-width: 768px) { .lib-header-bar { flex-direction: column; align-items: stretch; gap: var(--s-3); } .lib-title-group { justify-content: space-between; } .lib-search-wrap { max-width: 100%; } }
</style>
