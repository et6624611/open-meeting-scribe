<template>
  <div ref="panelRef" class="rec-insights-panel">
    <div class="rec-insights-header">
      <div class="rec-insights-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
        {{ t('recording.insights.title') }}
        <span v-if="enabled && unreadCount > 0" class="rec-insights-badge">{{ unreadCount }}</span>
        <span v-else-if="enabled" class="rec-insights-status">{{ t('recording.insights.enabled') }}</span>
        <span v-else class="rec-insights-status is-off">{{ t('recording.insights.disabled') }}</span>
      </div>
      <div class="rec-insights-actions">
        <div
          class="toggle-switch"
          :class="{ 'is-on': enabled }"
          :title="enabled ? t('ai-panel.insights.disable') : t('ai-panel.insights.enable')"
          :aria-label="enabled ? t('ai-panel.insights.disable') : t('ai-panel.insights.enable')"
          @click="$emit('toggleEnabled')"
        >
          <div class="toggle-switch-track">
            <div class="toggle-switch-knob"></div>
          </div>
          <span class="toggle-switch-label">{{ enabled ? t('ai-panel.insights.toggle_on') : t('ai-panel.insights.toggle_off') }}</span>
        </div>
        <button
          v-if="enabled"
          class="rec-insights-btn"
          :class="{ 'is-active': showSettings }"
          :title="t('recording.insights.settings')"
          :aria-label="t('recording.insights.settings')"
          @click="$emit('toggleSettings')"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        </button>
        <div v-if="enabled" class="rec-insights-dropdown-wrap">
          <button
            class="rec-insights-btn rec-insights-analyze-btn"
            :class="{ 'is-loading': analyzing, 'is-active': showAnalysisMenu }"
            :disabled="analyzing"
            :title="t('ai-panel.insights.manual_analysis')"
            :aria-label="t('ai-panel.insights.manual_analysis')"
            @click="showAnalysisMenu = !showAnalysisMenu"
          >
            <svg v-if="!analyzing" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
            <svg v-else class="rec-insights-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
          </button>
          <div v-if="showAnalysisMenu" class="rec-insights-dropdown">
            <button
              v-for="item in analysisMenuItems" :key="item.key"
              class="rec-insights-dropdown-item"
              @click="onSelectAnalysis(item.key); showAnalysisMenu = false"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <!-- 洞察设置面板 / Insights settings panel -->
    <AiInsightsSettings
      v-if="enabled"
      class="rec-insights-settings-wrap"
      @click.stop
      :config="config"
      :is-open="showSettings"
      @category-toggle="(k: string, v: boolean) => $emit('categoryToggle', k, v)"
      @scan-interval-change="(k: string, v: number) => $emit('scanIntervalChange', k, v)"
      @sensitivity-change="(f: string, v: number) => $emit('sensitivityChange', f, v)"
      @notif-toggle="(f: string, v: boolean) => $emit('notifToggle', f, v)"
      @dnd-toggle="(v: boolean) => $emit('dndToggle', v)"
      @dnd-time-change="(f: 'startHour' | 'endHour', v: number) => $emit('dndTimeChange', f, v)"
    />
    <!-- 消息流 / Message stream -->
    <div class="rec-insights-body" v-if="enabled">
      <div v-if="messages.length === 0" class="rec-insights-empty">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.3"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
        <div class="rec-insights-empty-text">{{ t('recording.insights.empty') }}</div>
        <div class="rec-insights-empty-hint">{{ t('recording.insights.empty_hint') }}</div>
      </div>
      <div v-else class="rec-insights-list">
        <div
          v-for="msg in messages" :key="msg.id"
          class="rec-insight-card"
          :class="{ 'is-expanded': msg.expanded, 'is-unread': !msg.read, 'is-acknowledged': msg.acknowledged }"
        >
          <div class="rec-insight-card-header" @click="$emit('toggleMessage', msg.id)">
            <span class="rec-insight-cat">{{ msg.category }}</span>
            <span class="rec-insight-card-title">{{ msg.title }}</span>
            <svg v-if="!msg.expanded" class="rec-insight-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
            <svg v-else class="rec-insight-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="18 15 12 9 6 15"/></svg>
          </div>
          <div v-if="msg.expanded" class="rec-insight-card-body">
            <div class="rec-insight-body-text" v-html="escapeHtml(msg.body)"></div>
            <div v-if="msg.solution" class="rec-insight-solution">
              <span class="rec-insight-solution-label">{{ t('ai-panel.insights.expand_detail') }}</span>
              <div class="rec-insight-solution-text" v-html="msg.solution ? escapeHtml(msg.solution) : ''"></div>
            </div>
            <div class="rec-insight-actions" v-if="msg.actions.length > 0">
              <button
                v-for="act in msg.actions" :key="act.key"
                class="rec-insight-action-btn"
                :class="{ 'is-primary': act.primary, 'is-done': actedActions[msg.id + ':' + act.key] }"
                @click.stop="$emit('action', msg, act)"
              >{{ act.label }}</button>
            </div>
            <div class="rec-insight-meta">
              {{ t('ai-panel.insights.meta_auto') }} · {{ formatTime(msg.timestamp) }}
            </div>
          </div>
        </div>
      </div>
    </div>
    <!-- 未开启时的提示 / Prompt when disabled -->
    <div class="rec-insights-body" v-else>
      <div class="rec-insights-empty">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.3"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
        <div class="rec-insights-empty-text">{{ t('recording.insights.empty') }}</div>
        <div class="rec-insights-empty-hint">{{ t('recording.insights.empty_hint') }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { escapeHtml } from '@/utils/sanitize'
import type { InsightMessage, InsightAction, InsightConfig } from '@/composables/useAiInsights'
import AiInsightsSettings from '@/components/layout/ai/AiInsightsSettings.vue'

const { t } = useI18n()

const showAnalysisMenu = ref(false)
const panelRef = ref<HTMLElement | null>(null)

/** 点击面板外部时关闭设置面板和分析菜单 / Close settings panel and analysis menu on outside click */
function onDocumentClick(e: MouseEvent) {
  if (!panelRef.value || panelRef.value.contains(e.target as Node)) return
  if (props.showSettings) emit('requestCloseSettings')
  if (showAnalysisMenu.value) showAnalysisMenu.value = false
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onUnmounted(() => document.removeEventListener('click', onDocumentClick))

/** 分析类型菜单项 / Analysis type menu items */
const analysisMenuItems = computed(() => [
  { key: 'context', label: t('ai-panel.insights.analysis_context') },
  { key: 'blindspot', label: t('ai-panel.insights.analysis_blindspot') },
  { key: 'consensus', label: t('ai-panel.insights.analysis_consensus') },
  { key: 'all', label: t('ai-panel.insights.analysis_all') },
])

function onSelectAnalysis(key: string) {
  showAnalysisMenu.value = false
  // emit 选择结果 / Emit selection result
  emit('manualCheck', key)
}

const props = defineProps<{
  messages: InsightMessage[]
  enabled: boolean
  unreadCount: number
  config: InsightConfig
  actedActions: Record<string, boolean>
  showSettings: boolean
  analyzing: boolean
}>()

const emit = defineEmits<{
  (e: 'toggleEnabled'): void
  (e: 'toggleSettings'): void
  (e: 'requestCloseSettings'): void
  (e: 'toggleMessage', id: string): void
  (e: 'action', message: InsightMessage, action: InsightAction): void
  (e: 'categoryToggle', key: string, val: boolean): void
  (e: 'scanIntervalChange', key: string, val: number): void
  (e: 'sensitivityChange', field: string, val: number): void
  (e: 'notifToggle', field: string, val: boolean): void
  (e: 'dndToggle', val: boolean): void
  (e: 'dndTimeChange', field: 'startHour' | 'endHour', val: number): void
  (e: 'manualCheck', category: string): void
}>()

function formatTime(ts: number): string {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>
