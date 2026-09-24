<template>
  <!-- 行动项面板（原「决策」Tab，REQ-DECISION-CENTER R5 术语消歧） / Action-items panel (formerly "Decisions" tab) -->
  <div class="gen-panel" :class="{ hidden: !visible }">
    <!-- 本会议决策只读区：决策对象归决策中心管理，此处只读展示 + 入口
         Read-only section of this meeting's structured decisions, with a link to the Decision Center -->
    <section class="fp-decisions" :aria-label="t('generating.decisions_panel_title')">
      <div class="fp-decisions-head">
        <span class="fp-decisions-title">{{ t('generating.decisions_panel_title') }}</span>
        <RouterLink class="fp-decisions-link" :to="{ name: 'decisions' }">
          {{ t('generating.decisions_panel_link') }}
          <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
        </RouterLink>
      </div>
      <ul class="fp-decisions-list" v-if="meetingDecisions.length">
        <li v-for="d in meetingDecisions" :key="d.id" class="fp-decision-item" :class="'fp-st-' + d.status">
          <span class="fp-decision-dot"></span>
          <span class="fp-decision-text" :title="stripDecisionEmphasis(d.text)">{{ stripDecisionEmphasis(d.text) }}</span>
          <span v-if="d.pending_confirmation && d.status === 'active'" class="fp-decision-badge">{{ t('generating.decisions_panel_pending') }}</span>
          <span v-else-if="d.status !== 'active'" class="fp-decision-badge fp-decision-badge-muted">{{ t('generating.decisions_panel_' + d.status) }}</span>
        </li>
      </ul>
      <div class="fp-decisions-none" v-else>{{ t('generating.decisions_panel_none') }}</div>
    </section>

    <!-- 顶部：进度摘要 + 添加 / Top: progress summary + add -->
    <div class="db-toolbar" v-if="todos.length">
      <div class="db-toolbar-left">
        <span class="db-summary" v-html="summaryText"></span>
      </div>
      <button class="db-add-btn" @click="emit('toggle-form')">+ {{ t('generating.todos.add_decision') }}</button>
    </div>

    <!-- 决策卡片列表 / Decision card list -->
    <div class="db-flow" v-if="mainNodes.length">
      <DecisionNode
        v-for="todo in mainNodes"
        :key="todo.id"
        :todo="todo"
        @select-status="(s) => emit('status-change', todo, s)"
        @select-owner="(o) => emit('update', todo, { owner_type: o })"
        @commit-content="(c) => emit('update', todo, { why: c })"
        @delete="emit('delete', todo)"
      />
    </div>

    <!-- 已完成分组（默认折叠） / Completed group (collapsed by default) -->
    <div class="db-completed" v-if="completedNodes.length">
      <button class="flow-completed-toggle" @click="showCompleted = !showCompleted">
        <svg class="chev" :class="{ open: showCompleted }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
        {{ t('generating.todos.completed_group', { count: completedNodes.length }) }}
      </button>
      <div class="db-flow" v-if="showCompleted">
        <DecisionNode
          v-for="todo in completedNodes"
          :key="todo.id"
          :todo="todo"
          @select-status="(s) => emit('status-change', todo, s)"
          @select-owner="(o) => emit('update', todo, { owner_type: o })"
          @commit-content="(c) => emit('update', todo, { why: c })"
          @delete="emit('delete', todo)"
        />
      </div>
    </div>

    <!-- 空状态 / Empty state -->
    <div class="flow-empty" v-if="!todos.length">
      <div class="flow-empty-title">{{ t('generating.todos.flow_empty') }}</div>
      <div class="flow-empty-hint">{{ t('generating.todos.flow_empty_hint') }}</div>
    </div>
    <div class="flow-empty" v-else-if="!mainNodes.length && !completedNodes.length">
      {{ t('generating.todos.empty') }}
    </div>

    <!-- 添加决策表单 / Add decision form -->
    <div class="todos-add-bar">
      <button class="todos-add-btn" @click="emit('toggle-form')" v-if="!showAddForm">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        {{ t('generating.todos.add_decision') }}
      </button>
      <div class="todos-add-form" v-if="showAddForm">
        <textarea v-model="newTodoText" :placeholder="t('generating.todos.decision_title_placeholder')" rows="2"></textarea>
        <textarea v-model="newTodoContent" :placeholder="t('generating.todos.content_placeholder')" rows="3"></textarea>
        <div class="add-form-row">
          <input type="text" v-model="newTodoAssignee" :placeholder="t('generating.todos.assignee_placeholder')" style="flex:1">
        </div>
        <div class="add-form-actions">
          <button class="btn-cancel" @click="emit('toggle-form')">{{ t('generating.todos.cancel') }}</button>
          <button class="btn-submit" @click="emit('add')">{{ t('generating.todos.submit') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TodoItem, DecisionStatus } from '@/api/types'
import type { TodoPatch } from '@/api/notes'
import type { DecisionRecord } from '@/api/decisions'
import { fetchTaskDecisions } from '@/api/decisions'
import { stripDecisionEmphasis } from '@/utils/decisionText'
import DecisionNode from './DecisionNode.vue'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  taskId: string
  todos: TodoItem[]
  showAddForm: boolean
}>()

const emit = defineEmits<{
  (e: 'delete', todo: TodoItem): void
  (e: 'update', todo: TodoItem, patch: TodoPatch): void
  (e: 'status-change', todo: TodoItem, status: DecisionStatus): void
  (e: 'toggle-form'): void
  (e: 'add'): void
}>()

const newTodoText = defineModel<string>('newTodoText', { default: '' })
const newTodoAssignee = defineModel<string>('newTodoAssignee', { default: '' })
const newTodoContent = defineModel<string>('newTodoContent', { default: '' })

// ── 状态循环已移除，改为 DecisionNode 内下拉直选 / Status cycling removed, now dropdown-select in DecisionNode ──

function statusOf(todo: TodoItem): DecisionStatus {
  return todo.status ?? (todo.done ? 'done' : 'in_progress')
}

// ── 节点分组 / Node grouping ──
const completedNodes = computed(() => props.todos.filter(x => statusOf(x) === 'done'))
const activeNodes = computed(() => props.todos.filter(x => statusOf(x) !== 'done'))
const mainNodes = computed(() => activeNodes.value)

const showCompleted = ref(false)

// ── 本会议决策（只读，首次展开面板时拉取；后端 DC-DEC-B1 未就绪时静默降级） ──
// This meeting's decisions: fetched lazily on first open, failures degrade to the empty hint
const meetingDecisions = ref<DecisionRecord[]>([])
let decisionsLoaded = false
watch(() => props.visible, async (v) => {
  if (!v || decisionsLoaded) return
  decisionsLoaded = true
  try {
    meetingDecisions.value = await fetchTaskDecisions(props.taskId)
  } catch {
    meetingDecisions.value = []
  }
}, { immediate: true })

// ── 进度摘要 / Progress summary ──
const counts = computed(() => {
  const c: Record<string, number> = { to_decide: 0, to_start: 0, in_progress: 0, to_confirm: 0, done: 0 }
  for (const todo of props.todos) c[statusOf(todo)] = (c[statusOf(todo)] || 0) + 1
  return c
})

const summaryText = computed(() => {
  const c = counts.value
  const total = props.todos.length
  const parts: string[] = []
  if (c.to_confirm) parts.push(`<strong>${c.to_confirm}</strong> ${t('generating.todos.status_to_confirm')}`)
  if (c.in_progress) parts.push(`<strong>${c.in_progress}</strong> ${t('generating.todos.status_in_progress')}`)
  if (c.to_decide) parts.push(`<strong>${c.to_decide}</strong> ${t('generating.todos.status_to_decide')}`)
  if (c.to_start) parts.push(`<strong>${c.to_start}</strong> ${t('generating.todos.status_to_start')}`)
  const summary = parts.join(' · ')
  return summary ? `${summary} · ${t('generating.todos.total_count', { count: total })}` : t('generating.todos.total_count', { count: total })
})

</script>

<style scoped>
/* 只读决策区：紧凑列表 + 状态点/徽标复用决策流基元色 / Read-only decisions section */
.fp-decisions { margin-bottom: var(--s-4); padding: var(--s-3); border: 1px solid var(--border); border-radius: var(--radius-sm); }
.fp-decisions-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2); }
.fp-decisions-title { font-size: var(--fs-12); color: var(--muted); font-weight: 600; }
.fp-decisions-link { display: inline-flex; align-items: center; gap: 3px; font-size: var(--fs-12); color: var(--accent); text-decoration: none; }
.fp-decisions-link:hover { text-decoration: underline; }
.fp-decisions-list { list-style: none; margin: var(--s-2) 0 0; padding: 0; display: flex; flex-direction: column; gap: 5px; }
.fp-decision-item { display: flex; align-items: center; gap: var(--s-2); font-size: var(--fs-13); color: var(--fg); min-width: 0; }
.fp-decision-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; background: var(--st-done); }
.fp-decision-item.fp-st-superseded .fp-decision-dot { background: var(--st-decide); }
.fp-decision-item.fp-st-revoked .fp-decision-dot { background: var(--error); }
.fp-decision-item.fp-st-superseded .fp-decision-text, .fp-decision-item.fp-st-revoked .fp-decision-text { color: var(--subtle); text-decoration: line-through; }
.fp-decision-text { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fp-decision-badge { flex-shrink: 0; font-size: 11px; line-height: 1; padding: 3px 6px; border-radius: 999px; background: oklch(0.94 0.04 70); color: var(--st-confirm); }
.fp-decision-badge-muted { background: var(--surface-2); color: var(--muted); border: 1px solid var(--border); }
.fp-decisions-none { margin-top: 4px; font-size: var(--fs-12); color: var(--subtle); }
</style>
