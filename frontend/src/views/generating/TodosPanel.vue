<template>
  <!-- 待办面板 / Todos panel -->
  <div class="gen-panel" :class="{ hidden: !visible }">
    <div class="todos-summary" v-if="todos.length">
      <span>{{ t('generating.todos.stat', { total: todos.length, done: todos.filter(x => x.done).length }) }}</span>
    </div>
    <div class="todos-list" v-if="todos.length">
      <div v-for="todo in todos" :key="todo.id" class="todo-item" :class="{ done: todo.done }">
        <input type="checkbox" :checked="todo.done" @change="emit('toggle', todo)">
        <span class="todo-text">{{ todo.text }}</span>
        <span v-if="todo.assignee" class="todo-assignee">{{ todo.assignee }}</span>
        <span v-if="todo.source" class="todo-source-badge" :class="'source-' + todo.source">{{ todo.source === 'ai' ? t('generating.todos.source_ai') : t('generating.todos.source_manual') }}</span>
        <button v-if="todo.source === 'ai'" class="todo-locate-btn" :title="t('generating.todos.locate')" @click="emit('locate', todo)" :aria-label="t('generating.todos.locate')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>
        </button>
        <button class="todo-delete-btn" :title="t('generating.todos.delete')" @click="emit('delete', todo)" :aria-label="t('generating.todos.delete')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
        </button>
      </div>
    </div>
    <div class="todos-empty" v-else>{{ t('generating.todos.empty') }}</div>
    <div class="todos-add-bar">
      <button class="todos-add-btn" @click="emit('toggle-form')" v-if="!showAddForm">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        {{ t('generating.todos.add') }}
      </button>
      <div class="todos-add-form" v-if="showAddForm">
        <textarea v-model="newTodoText" :placeholder="t('generating.todos.content_placeholder')" rows="2"></textarea>
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
import { useI18n } from 'vue-i18n'
import type { TodoItem } from '@/api/types'

const { t } = useI18n()

defineProps<{
  visible: boolean
  todos: TodoItem[]
  showAddForm: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle', todo: TodoItem): void
  (e: 'delete', todo: TodoItem): void
  (e: 'locate', todo: TodoItem): void
  (e: 'toggle-form'): void
  (e: 'add'): void
}>()

const newTodoText = defineModel<string>('newTodoText', { default: '' })
const newTodoAssignee = defineModel<string>('newTodoAssignee', { default: '' })
</script>
