<template>
  <div class="rec-summary-panel" :class="{ 'is-hidden-narrow': !isActive }">
    <div class="rec-summary-header">
      <div class="rec-summary-title">
        <div class="rec-summary-countdown-ring" v-if="countdown > 0 && !paused">
          <svg width="28" height="28" viewBox="0 0 28 28">
            <circle class="ring-bg" cx="14" cy="14" r="11"/>
            <circle class="ring-fg" :class="{ 'is-warning': countdown <= 10 }" cx="14" cy="14" r="11" :stroke-dasharray="69.115" :stroke-dashoffset="69.115 * (1 - progressPercent / 100)" />
          </svg>
          <span class="ring-text" :class="{ 'is-warning': countdown <= 10 }">{{ countdown }}</span>
        </div>
        {{ t('recording.summary.title') }}
        <span class="rec-summary-status">{{ statusText }}</span>
      </div>
      <div class="rec-summary-actions">
        <button class="rec-summary-btn" @click="$emit('togglePause')" :title="paused ? t('recording.summary.resume_title') : t('recording.summary.pause_title')">
          <svg v-if="!paused" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg>
        </button>
        <div class="more-menu-wrap">
          <button ref="moreBtn" class="rec-summary-btn" @click="toggleMore" :title="t('common.action.more')" aria-haspopup="menu" :aria-label="t('common.action.more')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
          </button>
          <div ref="dropdown" class="more-menu-dropdown" :class="{ 'is-open': showMore }" role="menu">
            <button class="more-menu-item" @click="$emit('stopSummary'); closeMore()" role="menuitem">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>
              {{ t('recording.summary.stop') }}
            </button>
            <div style="height:1px;background:var(--border);margin:4px 0"></div>
            <div style="padding:4px 6px;font-size:11px;color:var(--muted);font-weight:500">{{ t('recording.summary.frequency') }}</div>
            <button v-for="f in freqOptions" :key="f" class="more-menu-item summary-interval-item" :class="{ 'is-selected': interval === f }" @click="$emit('setFrequency', f); closeMore()" role="menuitem">
              <span class="opt-check"><svg v-if="interval === f" class="ic ic-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>
              {{ f }}s <span class="opt-hint">{{ getFreqHint(f) }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="rec-summary-body" id="recSummaryBody">
      <div class="rec-summary-content" v-html="summaryHtml"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePopMenu } from '@/composables/usePopMenu'

const { t } = useI18n()

defineProps<{
  isActive: boolean
  summaryHtml: string
  paused: boolean
  statusText: string
  countdown: number
  progressPercent: number
  interval: number
}>()

defineEmits<{
  (e: 'togglePause'): void
  (e: 'stopSummary'): void
  (e: 'setFrequency', f: number): void
}>()

const moreBtn = ref<HTMLElement | null>(null)
const dropdown = ref<HTMLElement | null>(null)
const { visible: showMore, toggle: toggleMore, close: closeMore } = usePopMenu(dropdown, moreBtn)

const freqOptions = [30, 60, 120, 300]

function getFreqHint(f: number): string {
  const hints: Record<number, string> = {
    30: t('recording.summary.freq_frequent'),
    60: t('recording.summary.freq_default'),
    120: t('recording.summary.freq_moderate'),
    300: t('recording.summary.freq_economical'),
  }
  return hints[f] || ''
}
</script>
