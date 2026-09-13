<template>
  <!-- 纪要面板 -->
  <div class="gen-panel" :class="{ hidden: !visible }">
    <div class="gen-loading" v-if="loading">
      <div class="gen-loading-hint"><div class="gen-loading-spinner"></div>{{ t('generating.summary.loading') }}</div>
      <div class="gen-skeleton"><div class="gen-skeleton-bar"></div><div class="gen-skeleton-bar"></div><div class="gen-skeleton-bar"></div></div>
    </div>
    <div class="gen-empty" v-else-if="pending">
      <div class="gen-empty-hint">{{ t('generating.summary.pending') }}</div>
    </div>
    <MdBlockEditor
      v-else
      :markdown="summaryMd"
      @change="emit('change', $event)"
      ref="summaryEditor"
      :empty-text="t('generating.summary.placeholder')"
    />
    <!-- 章节回顾卡片 -->
    <div class="sum-section" v-if="hasSummary && chapters.length > 0">
      <div class="sum-section-label">{{ t('generating.chapter.review') }}</div>
      <div
        v-for="(ch, idx) in chapters" :key="'sum-ch-' + idx"
        class="sum-chapter-card"
        :class="{ 'is-open': expandedChapters.has(idx) }"
      >
        <button class="sum-chapter-header" @click="emit('toggle-chapter', idx)" :title="ch.title">
          <div class="sum-chapter-num">{{ ch.id || idx + 1 }}</div>
          <div class="sum-chapter-info">
            <div class="sum-chapter-title">{{ ch.title }}</div>
            <div class="sum-chapter-meta">
              <span>{{ formatTimeMs(ch.start_ms) }} – {{ formatTimeMs(ch.end_ms) }}</span>
              <span class="sep">·</span>
              <span>{{ t('generating.chapter.key_points_count', { count: (ch.key_points || []).length }) }}</span>
            </div>
          </div>
          <div class="sum-chapter-chevron">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
          </div>
        </button>
        <ul class="sum-chapter-points" v-if="ch.key_points?.length">
          <li v-for="(p, pi) in ch.key_points" :key="pi">{{ p }}</li>
        </ul>
      </div>
    </div>
    <!-- 行动项入口 -->
    <div class="sum-section" v-if="hasSummary">
      <div class="sum-section-label">{{ t('generating.summary.action_items') }}</div>
      <button class="sum-todos-link" @click="emit('switch-tab', 'todos')" :title="t('generating.summary.view_todos')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
        <span>{{ t('generating.summary.todos_stat', { total: todosCount || '—', done: todosDoneCount || '0' }) }}</span>
        <span class="go">{{ t('generating.summary.view_todos') }}
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
        </span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import MdBlockEditor from '@/components/MdBlockEditor.vue'
import type { Chapter } from '@/api/types'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  summaryMd: string
  chapters: Chapter[]
  expandedChapters: Set<number>
  /** 任务状态是否在处理中（loading 态） */
  processing: boolean
  /** 任务状态是否为 pending */
  pending: boolean
  /** 是否有纪要内容 */
  hasSummary: boolean
  todosCount: number
  todosDoneCount: number
}>()

const emit = defineEmits<{
  (e: 'change', md: string): void
  (e: 'toggle-chapter', idx: number): void
  (e: 'switch-tab', tabId: string): void
}>()

function formatTimeMs(ms: number): string {
  const sec = Math.floor(ms / 1000)
  const m = Math.floor(sec / 60), s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const loading = computed(() => props.processing)

const summaryEditor = ref<InstanceType<typeof MdBlockEditor> | null>(null)

defineExpose({
  updateBlock: (blockIndex: number, newSource: string) => summaryEditor.value?.updateBlock(blockIndex, newSource),
})
</script>
