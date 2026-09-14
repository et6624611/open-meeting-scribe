<template>
  <!-- 决策流面板 / Decision flow panel -->
  <div class="gen-panel" :class="{ hidden: !visible }">
    <!-- 顶部:点阵工具栏(方案 B) / Dot visualization toolbar (Proposal B) -->
    <div class="db-toolbar" v-if="todos.length">
      <div class="db-toolbar-left">
        <div class="db-progress-dots" role="img" :aria-label="t('generating.todos.flow_progress')">
          <span
            v-for="todo in todos"
            :key="todo.id"
            class="db-pdot"
            :class="'pd-' + statusOf(todo)"
          ></span>
        </div>
        <span class="db-summary" v-html="summaryText"></span>
      </div>
      <button class="db-add-btn" @click="emit('toggle-form')">+ {{ t('generating.todos.add_decision') }}</button>
    </div>

    <!-- 决策流列表 / Decision flow list -->
    <div class="db-flow" v-if="mainNodes.length">
      <DecisionNode
        v-for="todo in mainNodes"
        :key="todo.id"
        :todo="todo"
        :expanded="expandedIds.has(todo.id)"
        :draft="drafts[todo.id]"
        :editing-title="editingId === todo.id"
        :edit-title-text="editText"
        :status-menu-open="statusMenuId === todo.id"
        @toggle-expand="toggleExpand(todo)"
        @open-status="openStatusMenu(todo)"
        @close-status="statusMenuId = null"
        @select-status="(s) => selectStatus(todo, s)"
        @cycle-owner="cycleOwner(todo)"
        @start-edit-title="startEditTitle(todo)"
        @update-edit-title="editText = $event"
        @save-edit-title="saveEditTitle(todo)"
        @cancel-edit-title="cancelEdit"
        @update-draft="(patch) => onDraftChange(todo, patch)"
        @commit="flushDraft(todo)"
        @add-step="addStep(todo)"
        @remove-step="(i) => removeStep(todo, i)"
        @locate="emit('locate', todo)"
        @delete="emit('delete', todo)"
      />
    </div>

    <!-- 已完成分组(默认折叠沉底) / Completed group -->
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
          :expanded="expandedIds.has(todo.id)"
          :draft="drafts[todo.id]"
          :editing-title="editingId === todo.id"
          :edit-title-text="editText"
          :status-menu-open="statusMenuId === todo.id"
          @toggle-expand="toggleExpand(todo)"
          @open-status="openStatusMenu(todo)"
          @close-status="statusMenuId = null"
          @select-status="(s) => selectStatus(todo, s)"
          @cycle-owner="cycleOwner(todo)"
          @start-edit-title="startEditTitle(todo)"
          @update-edit-title="editText = $event"
          @save-edit-title="saveEditTitle(todo)"
          @cancel-edit-title="cancelEdit"
          @update-draft="(patch) => onDraftChange(todo, patch)"
          @commit="flushDraft(todo)"
          @add-step="addStep(todo)"
          @remove-step="(i) => removeStep(todo, i)"
          @locate="emit('locate', todo)"
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
import { ref, computed, reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TodoItem, DecisionStatus, OwnerType } from '@/api/types'
import type { TodoPatch } from '@/api/notes'
import DecisionNode from './DecisionNode.vue'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  todos: TodoItem[]
  showAddForm: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle', todo: TodoItem): void
  (e: 'delete', todo: TodoItem): void
  (e: 'locate', todo: TodoItem): void
  (e: 'update', todo: TodoItem, patch: TodoPatch): void
  (e: 'status-change', todo: TodoItem, status: DecisionStatus): void
  (e: 'toggle-form'): void
  (e: 'add'): void
}>()

const newTodoText = defineModel<string>('newTodoText', { default: '' })
const newTodoAssignee = defineModel<string>('newTodoAssignee', { default: '' })

// ─── 状态定义 / Status definitions ───
const ownerOrder: OwnerType[] = ['self', 'agent', 'colleague', 'enterprise']

function statusOf(todo: TodoItem): DecisionStatus {
  return todo.status ?? (todo.done ? 'done' : 'in_progress')
}

const counts = computed(() => {
  const c: Record<string, number> = { to_decide: 0, to_start: 0, in_progress: 0, to_confirm: 0, done: 0 }
  for (const todo of props.todos) c[statusOf(todo)] = (c[statusOf(todo)] || 0) + 1
  return c
})

// ─── 节点分组 / Node grouping ───
const completedNodes = computed(() => props.todos.filter(x => statusOf(x) === 'done'))
const activeNodes = computed(() => props.todos.filter(x => statusOf(x) !== 'done'))
const mainNodes = computed(() => activeNodes.value)

// 焦点引导:文字摘要(方案 B) / Focus guidance: text summary (Proposal B)
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

const showCompleted = ref(false)

// ─── 展开状态(多节点可同时展开) / Expand state (multi-expand) ───
const expandedIds = reactive(new Set<string>())
function toggleExpand(todo: TodoItem) {
  if (expandedIds.has(todo.id)) expandedIds.delete(todo.id)
  else { ensureDraft(todo); expandedIds.add(todo.id) }
}

// 首次加载:自动展开「待确认」节点(需人验收的磁石) / Auto-expand to_confirm nodes on first load
let autoExpanded = false
watch(() => props.todos, (list) => {
  if (autoExpanded || !list.length) return
  autoExpanded = true
  list.forEach(todo => { if (statusOf(todo) === 'to_confirm') { ensureDraft(todo); expandedIds.add(todo.id) } })
}, { immediate: true })

// ─── 草稿(why/how/outcome 编辑,防抖持久化) / Drafts with debounced persistence ───
interface Draft { why: string; outcome: string; how: string[] }
const drafts = reactive<Record<string, Draft>>({})
const timers: Record<string, ReturnType<typeof setTimeout>> = {}

function ensureDraft(todo: TodoItem) {
  if (drafts[todo.id]) return
  const how = todo.how && todo.how.length ? [...todo.how] : (todo.text ? [todo.text] : [])
  drafts[todo.id] = { why: todo.why || '', outcome: todo.outcome || '', how }
}

function onDraftChange(todo: TodoItem, patch: Partial<Draft>) {
  ensureDraft(todo)
  Object.assign(drafts[todo.id], patch)
  if (timers[todo.id]) clearTimeout(timers[todo.id])
  timers[todo.id] = setTimeout(() => flushDraft(todo), 800)
}

function flushDraft(todo: TodoItem) {
  const d = drafts[todo.id]
  if (!d) return
  const p: TodoPatch = {}
  if (d.why !== (todo.why || '')) p.why = d.why
  if (d.outcome !== (todo.outcome || '')) p.outcome = d.outcome
  const howClean = d.how.map(s => s.trim()).filter(Boolean)
  if (JSON.stringify(howClean) !== JSON.stringify(todo.how || [])) p.how = howClean
  if (Object.keys(p).length) emit('update', todo, p)
}

function addStep(todo: TodoItem) {
  ensureDraft(todo)
  drafts[todo.id].how.push('')
  if (!expandedIds.has(todo.id)) expandedIds.add(todo.id)
}

function removeStep(todo: TodoItem, idx: number) {
  ensureDraft(todo)
  drafts[todo.id].how.splice(idx, 1)
  flushDraft(todo)
}

// ─── 状态切换 / Status change ───
const statusMenuId = ref<string | null>(null)
function openStatusMenu(todo: TodoItem) {
  statusMenuId.value = statusMenuId.value === todo.id ? null : todo.id
}
function selectStatus(todo: TodoItem, s: DecisionStatus) {
  statusMenuId.value = null
  if (statusOf(todo) === s) return
  emit('status-change', todo, s)
}

// ─── 推进方切换(循环) / Owner cycling ───
function cycleOwner(todo: TodoItem) {
  const cur = todo.owner_type || 'self'
  const next = ownerOrder[(ownerOrder.indexOf(cur) + 1) % ownerOrder.length]
  emit('update', todo, { owner_type: next })
}

// ─── 标题行内编辑 / Inline title editing ───
const editingId = ref<string | null>(null)
const editText = ref('')
function startEditTitle(todo: TodoItem) {
  editingId.value = todo.id
  editText.value = todo.text
}
function saveEditTitle(todo: TodoItem) {
  if (editingId.value !== todo.id) return
  const v = editText.value.trim()
  editingId.value = null
  if (v && v !== todo.text) emit('update', todo, { text: v })
}
function cancelEdit() { editingId.value = null }

watch(() => props.visible, (v) => { if (!v) statusMenuId.value = null })
</script>
