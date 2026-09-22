<template>
  <!-- 决策卡片（骨架 + textarea） / Decision card (skeleton + textarea) -->
  <div class="db-node" :class="['st-' + status, { 'is-done': status === 'done' }]">
    <!-- 第一行：状态点 + 标题 + 状态下拉 + 负责人下拉 / Row 1: status dot + title + status dropdown + owner dropdown -->
    <div class="db-row1">
      <span class="db-dot" :class="'dot-' + status"></span>
      <span class="db-title">{{ todo.text }}</span>
      <!-- 状态下拉 / Status dropdown -->
      <div class="db-dropdown-wrap" ref="statusDropRef">
        <button class="db-status-btn" :class="'pill-' + status" :aria-expanded="statusOpen" aria-haspopup="menu" @click.stop="statusOpen = !statusOpen">
          {{ t('generating.todos.status_' + status) }}
          <svg class="db-dd-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <div class="db-dropdown" :class="{ 'is-open': statusOpen }">
          <button
            v-for="s in statusOptions"
            :key="s"
            class="db-dd-item"
            :class="{ 'is-active': s === status }"
            @click.stop="onSelectStatus(s)"
          >
            <span class="db-dd-dot" :class="'dot-' + s"></span>
            {{ t('generating.todos.status_' + s) }}
            <svg v-if="s === status" class="db-dd-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
          </button>
        </div>
      </div>
      <!-- 负责人下拉 / Owner dropdown -->
      <div class="db-dropdown-wrap" ref="ownerDropRef">
        <button class="db-owner-btn" :aria-expanded="ownerOpen" aria-haspopup="menu" @click.stop="ownerOpen = !ownerOpen">
          {{ ownerLabel }}
          <svg class="db-dd-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <div class="db-dropdown" :class="{ 'is-open': ownerOpen }">
          <button
            v-for="o in ownerOptions"
            :key="o"
            class="db-dd-item"
            :class="{ 'is-active': o === ownerType }"
            @click.stop="onSelectOwner(o)"
          >
            {{ t('generating.todos.owner_waiting_' + o) }}
            <svg v-if="o === ownerType" class="db-dd-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
          </button>
        </div>
      </div>
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
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TodoItem, DecisionStatus, OwnerType } from '@/api/types'
import { useEscClose } from '@/composables/useEscClose'

const { t } = useI18n()

const props = defineProps<{
  todo: TodoItem
}>()

const emit = defineEmits<{
  (e: 'select-status', status: DecisionStatus): void
  (e: 'select-owner', owner: OwnerType): void
  (e: 'commit-content', content: string): void
  (e: 'delete'): void
}>()

// ── 下拉选项 / Dropdown options ──
const statusOptions: DecisionStatus[] = ['to_decide', 'to_start', 'in_progress', 'to_confirm', 'done']
const ownerOptions: OwnerType[] = ['self', 'agent', 'colleague', 'enterprise']

// ── 下拉状态 / Dropdown open state ──
const statusOpen = ref(false)
const ownerOpen = ref(false)
// ESC 关闭下拉需落到状态上，仅剥 class 会让下次渲染重新打开
// ESC must clear state, not just the class, or the next render reopens the surface.
useEscClose(statusOpen, () => { statusOpen.value = false })
useEscClose(ownerOpen, () => { ownerOpen.value = false })
const statusDropRef = ref<HTMLElement | null>(null)
const ownerDropRef = ref<HTMLElement | null>(null)

const status = computed<DecisionStatus>(() => props.todo.status ?? (props.todo.done ? 'done' : 'in_progress'))
const ownerType = computed<OwnerType>(() => props.todo.owner_type || 'self')

// 负责人文字标签 / Owner text label
const ownerLabel = computed(() => t('generating.todos.owner_waiting_' + ownerType.value))

// 决策内容（使用 why 字段存储 Markdown） / Decision content (stored in why field as Markdown)
const content = ref(props.todo.why || '')

// 同步外部变化 / Sync external changes
watch(() => props.todo.why, (val: string | undefined) => {
  content.value = val || ''
})

function onContentInput(e: Event) {
  content.value = (e.target as HTMLTextAreaElement).value
}

function onSelectStatus(s: DecisionStatus) {
  statusOpen.value = false
  if (s !== status.value) emit('select-status', s)
}

function onSelectOwner(o: OwnerType) {
  ownerOpen.value = false
  if (o !== ownerType.value) emit('select-owner', o)
}

// ── 点击外部关闭下拉 / Click-outside to close dropdowns ──
function onDocClick(e: MouseEvent) {
  if (statusDropRef.value && !statusDropRef.value.contains(e.target as Node)) statusOpen.value = false
  if (ownerDropRef.value && !ownerDropRef.value.contains(e.target as Node)) ownerOpen.value = false
}

onMounted(() => document.addEventListener('click', onDocClick, true))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick, true))
</script>
