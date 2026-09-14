<template>
  <!-- 方案 B:焦点引导 — 两行卡片 + 左侧轨道 / Proposal B: two-row card + left rail -->
  <div class="db-node" :class="['st-' + status, { expanded, 'is-focus': isFocus, 'is-done': status === 'done' }]">
    <!-- 左侧轨道:状态圆点 / Left rail: status dot -->
    <div class="db-rail">
      <span class="db-dot"></span>
    </div>

    <!-- 卡片主体 / Card body -->
    <div class="db-card" :class="{ focus: isFocus }">
      <!-- 第一行:标题 / Row 1: title -->
      <div class="db-row1" @click="emit('toggle-expand')">
        <textarea
          v-if="editingTitle"
          class="db-title-edit"
          :value="editTitleText"
          rows="1"
          @click.stop
          @input="emit('update-edit-title', ($event.target as HTMLTextAreaElement).value)"
          @blur="emit('save-edit-title')"
          @keydown.enter.exact.prevent="emit('save-edit-title')"
          @keydown.esc.prevent="emit('cancel-edit-title')"
        ></textarea>
        <span v-else class="db-title" @dblclick.stop="emit('start-edit-title')">{{ todo.text }}</span>
      </div>

      <!-- 第二行:元信息(muted 弱化) / Row 2: meta info (muted) -->
      <div class="db-row2" @click="emit('toggle-expand')">
        <!-- 状态(彩色点 + 文字,可点击切换) -->
        <button class="db-meta-btn" @click.stop="emit('open-status')">
          <span class="db-meta-dot" :class="'dot-' + status"></span>
          {{ t('generating.todos.status_' + status) }}
        </button>
        <!-- 状态菜单 -->
        <template v-if="statusMenuOpen">
          <div class="db-status-backdrop" @click="emit('close-status')"></div>
          <div class="db-status-menu">
            <button v-for="s in statusOrder" :key="s" class="db-status-menu-item" :class="['pill-' + s, { current: s === status }]" @click="emit('select-status', s)">{{ t('generating.todos.status_' + s) }}</button>
          </div>
        </template>
        <span class="db-sep">·</span>
        <!-- 负责人 -->
        <span class="db-meta-text" :title="ownerTitle" @click.stop="emit('cycle-owner')">{{ ownerLabel }}</span>
        <!-- AI 来源 -->
        <template v-if="isAi">
          <span class="db-sep">·</span>
          <span class="db-meta-ai">{{ t('generating.todos.source_ai') }}</span>
        </template>
        <!-- 完整度微提示 -->
        <template v-if="completenessHint">
          <span class="db-sep">·</span>
          <span class="db-meta-hint">{{ completenessHint }}</span>
        </template>
      </div>

      <!-- 展开详情:why / how / outcome / Expanded detail -->
      <div class="db-detail" v-if="expanded" @click.stop>
        <!-- meta 行:动作按钮 -->
        <div class="db-detail-actions">
          <span class="db-detail-spacer"></span>
          <div class="db-detail-btns">
            <button v-if="isAi" class="db-act-btn" :title="t('generating.todos.locate')" @click="emit('locate')" :aria-label="t('generating.todos.locate')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>
            </button>
            <button class="db-act-btn" :title="t('generating.todos.edit_save')" @click="emit('start-edit-title')" :aria-label="t('generating.todos.edit_save')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
            </button>
            <button class="db-act-btn db-act-delete" :title="t('generating.todos.delete')" @click="emit('delete')" :aria-label="t('generating.todos.delete')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
            </button>
          </div>
        </div>

        <!-- 为什么 -->
        <div class="db-field">
          <span class="db-field-label">{{ t('generating.todos.why_label') }}</span>
          <textarea
            class="db-field-input"
            :value="draft?.why ?? todo.why ?? ''"
            :placeholder="hasWhy ? '' : t('generating.todos.why_placeholder')"
            rows="2"
            @input="emit('update-draft', { why: ($event.target as HTMLTextAreaElement).value })"
            @blur="emit('commit')"
          ></textarea>
        </div>

        <!-- 如何完成 -->
        <div class="db-field">
          <span class="db-field-label">{{ t('generating.todos.how_label') }}</span>
          <div class="db-field-value">
            <div class="db-how-steps">
              <div class="db-how-step" v-for="(step, i) in howList" :key="i">
                <span class="db-step-idx">{{ i + 1 }}.</span>
                <input
                  class="db-step-input"
                  type="text"
                  :value="step"
                  :placeholder="t('generating.todos.how_placeholder')"
                  @input="onStepInput(i, ($event.target as HTMLInputElement).value)"
                  @blur="emit('commit')"
                >
                <button class="db-step-remove" :title="t('generating.todos.delete')" @click="emit('remove-step', i)">×</button>
              </div>
              <button class="db-how-add" @click="emit('add-step')">+ {{ t('generating.todos.add_step') }}</button>
            </div>
          </div>
        </div>

        <!-- 带来什么 -->
        <div class="db-field">
          <span class="db-field-label">{{ t('generating.todos.outcome_label') }}</span>
          <textarea
            class="db-field-input"
            :value="draft?.outcome ?? todo.outcome ?? ''"
            :placeholder="hasOutcome ? '' : t('generating.todos.outcome_placeholder')"
            rows="2"
            @input="emit('update-draft', { outcome: ($event.target as HTMLTextAreaElement).value })"
            @blur="emit('commit')"
          ></textarea>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TodoItem, DecisionStatus, OwnerType } from '@/api/types'

interface Draft { why: string; outcome: string; how: string[] }

const { t } = useI18n()

const props = defineProps<{
  todo: TodoItem
  expanded: boolean
  draft?: Draft
  editingTitle: boolean
  editTitleText: string
  statusMenuOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-expand'): void
  (e: 'open-status'): void
  (e: 'close-status'): void
  (e: 'select-status', s: DecisionStatus): void
  (e: 'cycle-owner'): void
  (e: 'start-edit-title'): void
  (e: 'update-edit-title', v: string): void
  (e: 'save-edit-title'): void
  (e: 'cancel-edit-title'): void
  (e: 'update-draft', patch: { why?: string; outcome?: string; how?: string[] }): void
  (e: 'commit'): void
  (e: 'add-step'): void
  (e: 'remove-step', i: number): void
  (e: 'locate'): void
  (e: 'delete'): void
}>()

const statusOrder: DecisionStatus[] = ['to_decide', 'to_start', 'in_progress', 'to_confirm', 'done']

const status = computed<DecisionStatus>(() => props.todo.status ?? (props.todo.done ? 'done' : 'in_progress'))
const ownerType = computed<OwnerType>(() => props.todo.owner_type || 'self')
const isAi = computed(() => !!props.todo.source && props.todo.source !== 'manual')
const isFocus = computed(() => status.value === 'to_confirm' || status.value === 'in_progress')

// 负责人文字标签 / Owner text label
const ownerLabel = computed(() => t('generating.todos.owner_waiting_' + ownerType.value))
const ownerTitle = computed(() => t('generating.todos.owner_' + ownerType.value))

// 完整度微提示 / Completeness hint
const completenessHint = computed(() => {
  const parts: string[] = []
  const hasWhy = !!(props.draft?.why ?? props.todo.why)?.trim()
  const howCount = (props.draft?.how ?? props.todo.how ?? (props.todo.text ? [props.todo.text] : [])).filter(s => s.trim()).length
  const hasOutcome = !!(props.draft?.outcome ?? props.todo.outcome)?.trim()
  parts.push(t('generating.todos.meta_why') + (hasWhy ? '✓' : '—'))
  if (howCount > 0) parts.push(t('generating.todos.meta_how') + t('generating.todos.meta_steps', { count: howCount }))
  parts.push(t('generating.todos.meta_outcome') + (hasOutcome ? '✓' : '—'))
  return parts.join(' · ')
})

const howList = computed<string[]>(() => {
  if (props.draft) return props.draft.how
  return props.todo.how && props.todo.how.length ? props.todo.how : (props.todo.text ? [props.todo.text] : [])
})
const hasWhy = computed(() => !!(props.draft ? props.draft.why : props.todo.why)?.trim())
const hasOutcome = computed(() => !!(props.draft ? props.draft.outcome : props.todo.outcome)?.trim())

function onStepInput(i: number, v: string) {
  const next = [...howList.value]
  next[i] = v
  emit('update-draft', { how: next })
}
</script>
