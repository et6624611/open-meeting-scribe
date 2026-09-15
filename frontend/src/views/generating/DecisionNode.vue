<template>
  <!-- 决策卡片（骨架 + textarea） / Decision card (skeleton + textarea) -->
  <div class="db-node" :class="['st-' + status, { 'is-done': status === 'done' }]">
    <!-- 第一行：状态点 + 标题 + 状态 + 负责人 / Row 1: status dot + title + status + owner -->
    <div class="db-row1">
      <span class="db-dot" :class="'dot-' + status"></span>
      <span class="db-title">{{ todo.text }}</span>
      <button class="db-status-btn" :class="'pill-' + status" @click.stop="emit('cycle-status')">
        {{ t('generating.todos.status_' + status) }}
      </button>
      <span class="db-owner-btn" :title="ownerTitle" @click.stop="emit('cycle-owner')">{{ ownerLabel }}</span>
    </div>

    <!-- 第二行：Markdown textarea / Row 2: Markdown textarea -->
    <div class="db-content">
      <textarea
        class="db-card-textarea"
        :value="content"
        :placeholder="t('generating.todos.content_placeholder')"
        :rows="Math.max(content.split('\n').length, 2)"
        spellcheck="false"
        @input="onContentInput"
        @blur="emit('commit-content', content)"
      ></textarea>
    </div>

    <!-- 底部：操作 / Footer: actions -->
    <div class="db-footer">
      <span class="db-footer-spacer"></span>
      <button class="db-delete-btn" :title="t('generating.todos.delete')" @click="emit('delete')" :aria-label="t('generating.todos.delete')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TodoItem, DecisionStatus, OwnerType } from '@/api/types'

const { t } = useI18n()

const props = defineProps<{
  todo: TodoItem
}>()

const emit = defineEmits<{
  (e: 'cycle-status'): void
  (e: 'cycle-owner'): void
  (e: 'commit-content', content: string): void
  (e: 'delete'): void
}>()

const statusOrder: DecisionStatus[] = ['to_decide', 'to_start', 'in_progress', 'to_confirm', 'done']
const ownerOrder: OwnerType[] = ['self', 'agent', 'colleague', 'enterprise']

const status = computed<DecisionStatus>(() => props.todo.status ?? (props.todo.done ? 'done' : 'in_progress'))
const ownerType = computed<OwnerType>(() => props.todo.owner_type || 'self')

// 负责人文字标签 / Owner text label
const ownerLabel = computed(() => t('generating.todos.owner_waiting_' + ownerType.value))
const ownerTitle = computed(() => t('generating.todos.owner_' + ownerType.value))

// 决策内容（使用 why 字段存储 Markdown） / Decision content (stored in why field as Markdown)
const content = ref(props.todo.why || '')

// 同步外部变化 / Sync external changes
watch(() => props.todo.why, (val) => {
  content.value = val || ''
})

function onContentInput(e: Event) {
  content.value = (e.target as HTMLTextAreaElement).value
}

// 自动调整高度 / Auto-grow
function autoGrow(el: HTMLTextAreaElement) {
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}
</script>
