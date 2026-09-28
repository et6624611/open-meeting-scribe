<template>
  <!-- 知识库可检索下拉（F5 / DC-R2-a）：键入即过滤、键盘可选中、保留「全部 / 未关联」特殊项
       Searchable knowledge-base combobox: type-to-filter, keyboard selectable, special items kept -->
  <div class="kb-combo" ref="rootRef">
    <button
      type="button"
      class="kb-combo-trigger"
      role="combobox"
      aria-haspopup="listbox"
      :aria-expanded="open"
      aria-controls="kbComboList"
      :aria-label="`${label}: ${selectedLabel}`"
      @click="toggle"
      @keydown="onTriggerKeydown"
    >
      <span class="kb-combo-value">{{ selectedLabel }}</span>
      <svg class="kb-combo-chev" :class="{ open }" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
    </button>
    <div v-show="open" class="kb-combo-pop" id="kbComboPop">
      <div class="kb-combo-search-wrap">
        <svg class="kb-combo-search-icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input
          ref="searchRef"
          v-model="query"
          type="text"
          class="kb-combo-search"
          role="combobox"
          aria-expanded="true"
          aria-controls="kbComboList"
          :aria-activedescendant="focusedId || undefined"
          :placeholder="t('decisions.kb_search_placeholder')"
          @keydown="onSearchKeydown"
        />
      </div>
      <div class="kb-combo-list" id="kbComboList" role="listbox" :aria-label="label">
        <button
          v-for="(opt, i) in options"
          :key="opt.value || `all-${i}`"
          :id="`kb-opt-${i}`"
          class="kb-combo-opt"
          :class="{ 'is-focused': focusedId === `kb-opt-${i}`, 'is-selected': opt.value === modelValue }"
          role="option"
          :aria-selected="opt.value === modelValue"
          @click="select(opt.value)"
          @mouseenter="focusedId = `kb-opt-${i}`"
        >{{ opt.label }}</button>
        <div v-if="!options.length" class="kb-combo-empty">{{ t('decisions.kb_no_match') }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Project } from '@/api/projects'

const { t } = useI18n()

const props = defineProps<{
  /** '' = 全部知识库；'__none__' = 未关联；其余为 project id */
  modelValue: string
  projects: Project[]
  label: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
}>()

const rootRef = ref<HTMLElement | null>(null)
const searchRef = ref<HTMLInputElement | null>(null)
const open = ref(false)
const query = ref('')
const focusedId = ref('')

const options = computed(() => {
  const kw = query.value.trim().toLowerCase()
  const specials = [
    { value: '', label: t('decisions.kb_all') },
    { value: '__none__', label: t('decisions.kb_none') },
  ]
  // 特殊项不参与键入过滤：任何输入下都保留「全部 / 未关联」出口
  const list = props.projects
    .filter(p => !kw || p.name.toLowerCase().includes(kw))
    .map(p => ({ value: p.id, label: p.name }))
  return [...specials, ...list]
})

const selectedLabel = computed(() => {
  if (props.modelValue === '') return t('decisions.kb_all')
  if (props.modelValue === '__none__') return t('decisions.kb_none')
  return props.projects.find(p => p.id === props.modelValue)?.name ?? props.modelValue
})

function toggle() {
  open.value = !open.value
  if (open.value) {
    query.value = ''
    focusedId.value = ''
    nextTick(() => searchRef.value?.focus())
  }
}

function close() {
  open.value = false
}

function select(value: string) {
  emit('update:modelValue', value)
  close()
}

function moveFocus(delta: number) {
  const opts = options.value
  if (!opts.length) return
  const cur = opts.findIndex((_, i) => `kb-opt-${i}` === focusedId.value)
  const next = cur < 0 ? (delta > 0 ? 0 : opts.length - 1) : (cur + delta + opts.length) % opts.length
  focusedId.value = `kb-opt-${next}`
  document.getElementById(focusedId.value)?.scrollIntoView({ block: 'nearest' })
}

function onSearchKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') { e.preventDefault(); moveFocus(1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); moveFocus(-1) }
  else if (e.key === 'Enter') {
    e.preventDefault()
    const idx = options.value.findIndex((_, i) => `kb-opt-${i}` === focusedId.value)
    if (idx >= 0) select(options.value[idx].value)
    else if (options.value.length) select(options.value[0].value)
  } else if (e.key === 'Escape') { e.preventDefault(); close() }
  else if (query.value !== '' || ['Backspace', 'Delete'].includes(e.key)) {
    // 输入变化后焦点项可能失效：回退到首项由下一次 ArrowDown 定位，这里仅清焦点
    focusedId.value = ''
  }
}

function onTriggerKeydown(e: KeyboardEvent) {
  if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
    e.preventDefault()
    if (!open.value) toggle()
  } else if (e.key === 'Escape' && open.value) {
    // 消费事件：避免页面级 ESC（usePageBack）把「关闭下拉」误判为「返回上一页」
    e.preventDefault()
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
.kb-combo { position: relative; display: inline-flex; }
.kb-combo-trigger {
  display: inline-flex; align-items: center; gap: 6px; max-width: 200px;
  padding: 4px 8px; font-size: var(--fs-12, 12px); border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: transparent; color: var(--fg); cursor: pointer;
}
.kb-combo-trigger:hover { border-color: var(--border-strong); }
.kb-combo-trigger:focus-visible { outline: none; border-color: var(--accent); }
.kb-combo-value { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-combo-chev { flex-shrink: 0; color: var(--muted); transition: transform 0.15s; }
.kb-combo-chev.open { transform: rotate(180deg); }

.kb-combo-pop {
  position: absolute; top: calc(100% + 4px); left: 0; z-index: 30; min-width: 220px;
  border: 1px solid var(--border); border-radius: var(--radius-md, 8px); background: var(--surface-1, var(--bg, #fff));
  box-shadow: var(--dropdown-shadow); padding: var(--s-2);
}
.kb-combo-search-wrap { position: relative; display: flex; align-items: center; }
.kb-combo-search-icon { position: absolute; left: 8px; color: var(--muted); pointer-events: none; }
.kb-combo-search {
  width: 100%; box-sizing: border-box; padding: 5px 8px 5px 26px; font-size: var(--fs-12, 12px);
  border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--fg);
}
.kb-combo-search:focus { outline: none; border-color: var(--accent); }
.kb-combo-list { margin-top: 6px; max-height: 240px; overflow-y: auto; display: flex; flex-direction: column; }
.kb-combo-opt {
  text-align: left; padding: 6px 8px; font-size: var(--fs-12, 12px); border: none; border-radius: var(--radius-sm);
  background: transparent; color: var(--fg); cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.kb-combo-opt:hover, .kb-combo-opt.is-focused { background: var(--surface-2); }
.kb-combo-opt.is-selected { color: var(--accent); font-weight: 500; }
.kb-combo-empty { padding: var(--s-3); text-align: center; font-size: var(--fs-12, 12px); color: var(--muted); }
</style>
