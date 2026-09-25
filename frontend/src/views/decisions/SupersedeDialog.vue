<template>
  <!-- 取代方检索弹层：全量决策中检索并选中一条，确认后置为 superseded
       Supersede picker: search all decisions, pick the superseder, confirm -->
  <div v-show="modelValue" class="oms-overlay" data-vue-overlay :class="{ 'is-open': modelValue }" @click.self="close">
    <div ref="dialogRef" class="oms-overlay-card ss-dialog" role="dialog" aria-modal="true" aria-labelledby="ssDialogTitle">
      <div class="ss-header">
        <h3 id="ssDialogTitle">{{ t('decisions.supersede_modal_title') }}</h3>
        <button class="ss-close" @click="close" :title="t('generating.archive_dialog.close')">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
        </button>
      </div>
      <div class="ss-body">
        <div class="ss-search-wrap">
          <svg class="ss-search-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            ref="searchInputRef"
            v-model="keyword"
            class="ss-search-input"
            type="text"
            :placeholder="t('decisions.supersede_search_placeholder')"
            @keydown.enter.prevent="confirm"
          />
        </div>
        <div class="ss-list" role="radiogroup" :aria-label="t('decisions.supersede_modal_title')">
          <button
            v-for="d in candidates"
            :key="d.id"
            class="ss-item"
            :class="{ 'is-selected': selectedId === d.id }"
            role="radio"
            :title="stripDecisionEmphasis(d.text)"
            :aria-checked="selectedId === d.id"
            @click="selectedId = d.id"
          >
            <span class="ss-radio" :class="{ on: selectedId === d.id }"></span>
            <span class="ss-item-main">
              <span class="ss-item-text">{{ stripDecisionEmphasis(d.text) }}</span>
              <span class="ss-item-meta">
                {{ d.meeting_title || d.task_id }} · {{ d.meeting_date }}
                <span v-if="pendingFlags.includes(d.id)" class="ss-item-tag">{{ t('decisions.badge_pending') }}</span>
              </span>
            </span>
          </button>
          <div v-if="!candidates.length" class="ss-empty">{{ t('decisions.supersede_empty') }}</div>
        </div>
      </div>
      <div class="ss-footer">
        <button class="btn-cancel" @click="close">{{ t('decisions.add_cancel') }} <kbd>ESC</kbd></button>
        <button class="btn-submit" :disabled="!selectedId" @click="confirm">{{ t('decisions.supersede_confirm') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AggregatedDecision, SupersedeRef } from '@/api/decisions'
import { stripDecisionEmphasis } from '@/utils/decisionText'
import { useDialog } from '@/composables/useDialog'

const { t } = useI18n()

const props = defineProps<{
  modelValue: boolean
  /** 被操作的决策（不可选自己） / The decision being marked; never a candidate itself */
  target: AggregatedDecision | null
  /** 候选池：全部生效中决策 / Candidates: all active decisions */
  pool: AggregatedDecision[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'confirm', by: SupersedeRef): void
}>()

const { dialogRef } = useDialog(computed(() => props.modelValue), () => close())

const keyword = ref('')
const selectedId = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)

watch(() => props.modelValue, (open) => {
  if (open) {
    keyword.value = ''
    selectedId.value = ''
    nextTick(() => searchInputRef.value?.focus())
  }
})

const candidates = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return props.pool
    .filter(d => d.id !== props.target?.id)
    // 检索同时命中原始与剥除符号后的文本，保证所见即可搜
    .filter(d => !kw || d.text.toLowerCase().includes(kw) || stripDecisionEmphasis(d.text).toLowerCase().includes(kw) || (d.meeting_title || '').toLowerCase().includes(kw))
    .slice(0, 50)
})

const pendingFlags = computed(() => props.pool.filter(d => d.pending_confirmation).map(d => d.id))

function close() {
  emit('update:modelValue', false)
}

function confirm() {
  const picked = props.pool.find(d => d.id === selectedId.value)
  if (!picked) return
  emit('confirm', { task_id: picked.task_id, decision_id: picked.id })
  close()
}
</script>

<style scoped>
.ss-dialog { width: 520px; max-width: 92vw; border-radius: var(--radius-lg); border: none; box-shadow: var(--dropdown-shadow); }
.ss-header { display: flex; align-items: center; justify-content: space-between; padding: var(--s-4) var(--s-5); border-bottom: 1px solid var(--border); }
.ss-header h3 { font-size: var(--fs-15, 15px); font-weight: 600; margin: 0; }
.ss-close { border: none; background: transparent; color: var(--muted); cursor: pointer; padding: 4px; border-radius: var(--radius-sm); }
.ss-close:hover { background: var(--surface-2); color: var(--fg); }
.ss-body { padding: var(--s-4) var(--s-5); }
.ss-search-wrap { position: relative; display: flex; align-items: center; }
.ss-search-icon { position: absolute; left: 10px; color: var(--muted); pointer-events: none; }
.ss-search-input {
  width: 100%; box-sizing: border-box; padding: 8px 10px 8px 30px; font-size: var(--fs-13, 13px);
  border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-1, transparent); color: var(--fg);
}
.ss-search-input:focus { outline: none; border-color: var(--accent); }
.ss-list { margin-top: var(--s-3); max-height: 320px; overflow-y: auto; display: flex; flex-direction: column; gap: var(--s-2); }
.ss-item {
  display: flex; gap: var(--s-3); align-items: flex-start; text-align: left; width: 100%;
  padding: var(--s-3); border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: transparent; color: var(--fg); cursor: pointer; transition: border-color 0.12s, background 0.12s;
}
.ss-item:hover { background: var(--surface-2); }
.ss-item.is-selected { border-color: var(--accent); background: var(--accent-soft); }
.ss-radio { width: 14px; height: 14px; border-radius: 50%; border: 1.5px solid var(--border-strong); margin-top: 2px; flex-shrink: 0; transition: all 0.12s; }
.ss-radio.on { border-color: var(--accent); background: var(--accent); box-shadow: inset 0 0 0 3px oklch(1 0 0 / 0.9); }
.ss-item-main { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.ss-item-text { font-size: var(--fs-13, 13px); line-height: 1.45; }
.ss-item-meta { font-size: var(--fs-12, 12px); color: var(--muted); display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.ss-item-tag { padding: 1px 6px; border-radius: 999px; background: oklch(0.94 0.04 70); color: var(--st-confirm); font-size: 11px; }
.ss-empty { text-align: center; color: var(--muted); font-size: var(--fs-13, 13px); padding: var(--s-5) 0; }
.ss-footer { display: flex; justify-content: flex-end; gap: var(--s-2); padding: var(--s-3) var(--s-5) var(--s-4); border-top: 1px solid var(--border); }
.btn-cancel, .btn-submit { padding: 6px 14px; font-size: var(--fs-13, 13px); border-radius: var(--radius-sm); cursor: pointer; }
.btn-cancel { border: 1px solid var(--border); background: transparent; color: var(--muted); }
.btn-cancel:hover { color: var(--fg); border-color: var(--border-strong); }
.btn-submit { border: none; background: var(--accent); color: var(--accent-fg); font-weight: 500; }
.btn-submit:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
