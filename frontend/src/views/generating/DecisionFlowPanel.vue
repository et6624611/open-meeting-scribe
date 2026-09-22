<template>
  <!-- 决策流面板 / Decision flow panel -->
  <div class="gen-panel" :class="{ hidden: !visible }">
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
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TodoItem, DecisionStatus } from '@/api/types'
import type { TodoPatch } from '@/api/notes'
import DecisionNode from './DecisionNode.vue'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
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

// ── 状态循环已移除，改为 DecisionNode 内下拉直选 / Status cycling removed, now dropdown-select in DecisionNode ──

function statusOf(todo: TodoItem): DecisionStatus {
  return todo.status ?? (todo.done ? 'done' : 'in_progress')
}

// ── 节点分组 / Node grouping ──
const completedNodes = computed(() => props.todos.filter(x => statusOf(x) === 'done'))
const activeNodes = computed(() => props.todos.filter(x => statusOf(x) !== 'done'))
const mainNodes = computed(() => activeNodes.value)

const showCompleted = ref(false)

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
