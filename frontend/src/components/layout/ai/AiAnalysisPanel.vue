<template>
  <div class="ai-feed">
    <div v-if="!hasData" class="ai-welcome">
      <p>{{ t('ai-panel.analysis.title') }}</p>
      <p class="ai-welcome-hint">{{ t('ai-panel.analysis.hint') }}</p>
    </div>
    <template v-else>
      <!-- 概览卡片 -->
      <div v-if="overview" class="ai-analysis-overview">
        <div class="ai-ao-item">
          <span class="ai-ao-value">{{ overview.speakerCount }}</span>
          <span class="ai-ao-label">{{ t('ai-panel.analysis.speakers') }}</span>
        </div>
        <div class="ai-ao-item">
          <span class="ai-ao-value">{{ overview.dialogueCount }}</span>
          <span class="ai-ao-label">{{ t('ai-panel.analysis.utterances') }}</span>
        </div>
        <div class="ai-ao-item">
          <span class="ai-ao-value">{{ formatCount(overview.wordCount) }}</span>
          <span class="ai-ao-label">{{ t('ai-panel.analysis.words') }}</span>
        </div>
        <div class="ai-ao-item">
          <span class="ai-ao-value">{{ overview.duration }}</span>
          <span class="ai-ao-label">{{ t('ai-panel.analysis.duration') }}</span>
        </div>
      </div>
      <!-- 发言占比 -->
      <div class="ai-analysis-section">
        <div class="ai-analysis-label">{{ t('ai-panel.analysis.speak_ratio') }}</div>
        <div class="ai-analysis-bars">
          <div v-for="sp in speakerStats" :key="sp.name" class="ai-bar-row">
            <span class="ai-bar-name" :title="sp.name">{{ sp.name }}</span>
            <div class="ai-bar-track">
              <div class="ai-bar-fill" :style="{ width: sp.percent + '%' }"></div>
            </div>
            <span class="ai-bar-pct">{{ sp.percent }}%</span>
          </div>
        </div>
      </div>
      <!-- 待办完成 -->
      <div v-if="todoStats" class="ai-analysis-section">
        <div class="ai-analysis-label">{{ t('ai-panel.analysis.todo_done') }}</div>
        <div class="ai-todo-bar">
          <div class="ai-todo-fill" :style="{ width: todoPercent + '%' }" :class="todoPercent >= 100 ? 'is-done' : ''"></div>
        </div>
        <div class="ai-todo-text">
          {{ t('ai-panel.analysis.todo_stat', { done: todoStats.done, total: todoStats.total }) }}
        </div>
      </div>
      <!-- 章节时间线 -->
      <div v-if="chapters.length > 1" class="ai-analysis-section">
        <div class="ai-analysis-label">{{ t('ai-panel.analysis.chapters') }}</div>
        <div class="ai-chapter-list">
          <div v-for="(ch, i) in chapters" :key="i" class="ai-chapter-item">
            <span class="ai-chapter-dot"></span>
            <span class="ai-chapter-info">
              <span class="ai-chapter-title">{{ ch.title }}</span>
              <span class="ai-chapter-meta">{{ t('ai-panel.analysis.chapter_meta', { lines: ch.lineCount, speakers: ch.speakers.size }) }}</span>
            </span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t, locale } = useI18n()

const props = defineProps<{
  hasData: boolean
  overview: { speakerCount: number; dialogueCount: number; wordCount: number; duration: string } | null
  speakerStats: Array<{ name: string; percent: number }>
  todoStats: { done: number; total: number } | null
  chapters: Array<{ title: string; lineCount: number; speakers: Set<string> }>
}>()

const todoPercent = computed(() => {
  const ts = props.todoStats
  if (!ts || ts.total === 0) return 0
  return Math.round((ts.done / ts.total) * 100)
})

function formatCount(n: number): string {
  if (n >= 10000 && String(locale.value).startsWith('zh')) return (n / 10000).toFixed(1) + t('ai-panel.unit_wan')
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
</script>
