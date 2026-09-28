<template>
  <!-- 决策面板：唯一的决策对象——决策流（DC-UNIFY-01，2026-09-27 项目方裁决）
       Decisions panel: the decision flow is the one and only decision object -->
  <div class="gen-panel" :class="{ hidden: !visible }">
    <!-- 顶部：进度摘要 + 决策中心入口 + 添加 / Top: progress summary + center link + add -->
    <div class="db-toolbar" v-if="todos.length">
      <div class="db-toolbar-left">
        <span class="db-summary" v-html="summaryText"></span>
      </div>
      <RouterLink class="db-center-link" :to="{ name: 'decisions' }">
        {{ t('generating.decisions_panel_link') }}
        <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
      </RouterLink>
      <button class="db-add-btn" @click="emit('add')">+ {{ t('generating.todos.add_decision') }}</button>
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
        @patch="(p) => emit('update', todo, p)"
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
          @patch="(p) => emit('update', todo, p)"
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

    <!-- 添加决策：与决策中心手动补录共用同一弹层表单（DC-UNIFY-01） / Add decision: same dialog as the center's manual entry -->
    <div class="todos-add-bar">
      <button class="todos-add-btn" @click="emit('add')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        {{ t('generating.todos.add_decision') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TodoItem } from '@/api/types'
import type { TodoPatch } from '@/api/notes'
import { useDecisionStatuses } from '@/composables/useDecisionStatuses'
import DecisionNode from './DecisionNode.vue'

const { t, locale } = useI18n()

const props = defineProps<{
  visible: boolean
  taskId: string
  todos: TodoItem[]
}>()

const emit = defineEmits<{
  (e: 'delete', todo: TodoItem): void
  (e: 'update', todo: TodoItem, patch: TodoPatch): void
  (e: 'status-change', todo: TodoItem, status: string): void
  (e: 'add'): void
}>()

// ── 状态字典：分组与摘要都由它驱动（闭档 = 完成类，沉底折叠） ──
const { statuses, load, labelOf, isClosing } = useDecisionStatuses()
onMounted(() => { void load() })

function statusOf(todo: TodoItem): string {
  return todo.status || (todo.done ? 'done' : 'in_progress')
}

// ── 节点分组 / Node grouping ──
const completedNodes = computed(() => props.todos.filter(x => isClosing(statusOf(x))))
const activeNodes = computed(() => props.todos.filter(x => !isClosing(statusOf(x))))
const mainNodes = computed(() => activeNodes.value)

const showCompleted = ref(false)

// ── 进度摘要：按字典顺序列出有量的非闭档态 + 总数 / Progress summary ──
const summaryText = computed(() => {
  const counts = new Map<string, number>()
  for (const todo of props.todos) {
    const sid = statusOf(todo)
    counts.set(sid, (counts.get(sid) || 0) + 1)
  }
  const parts = statuses.value
    .filter(s => !s.closing && counts.get(s.id))
    .map(s => `<strong>${counts.get(s.id)}</strong> ${labelOf(s.id, String(locale.value || 'zh-CN'))}`)
  // 字典外的历史状态（用户删过项）也要被数进去，避免总数与分项对不上
  const covered = new Set(statuses.value.map(s => s.id))
  let stray = 0
  for (const [sid, n] of counts) if (!covered.has(sid) && !isClosing(sid)) stray += n
  if (stray) parts.push(`<strong>${stray}</strong> ${t('generating.todos.status_other')}`)
  const total = t('generating.todos.total_count', { count: props.todos.length })
  return parts.length ? `${parts.join(' · ')} · ${total}` : total
})
</script>

<style scoped>
/* 决策中心入口：与添加按钮同处工具栏右侧，弱化为文字链接 */
.db-center-link {
  display: inline-flex; align-items: center; gap: 3px; flex-shrink: 0;
  font-size: var(--fs-12); color: var(--muted); text-decoration: none; white-space: nowrap;
}
.db-center-link:hover { color: var(--accent); text-decoration: underline; }
</style>
