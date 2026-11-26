<script setup lang="ts">
/**
 * 书面版状态卡 / Formal-version state card
 *
 * 纯展示：状态、进度、成本预估、自动开关。轮询与请求在 useFormalVersion。
 */
import { useI18n } from 'vue-i18n'
import type { FormalVersion } from '@/api/types'
import type { FormalState } from './useFormalVersion'

const props = defineProps<{
  state: FormalState
  progress: { done: number; total: number }
  percent: number
  version: FormalVersion | null
  starting: boolean
  actionError: string
  autoEnabled: boolean
  estimatedTokens: number
  costNote: string
  toneCount: number
}>()

const emit = defineEmits<{
  (e: 'start'): void
  (e: 'toggle-auto', next: boolean): void
}>()

const { t } = useI18n()

function formatFormalTime(s: string | undefined): string {
  if (!s) return ''
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return ''
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
</script>

<template>
  <div class="gen-formal-panel">
    <!-- 生成中 / Running -->
    <div v-if="props.state === 'running'" class="rec-formal-lock gen-formal-card is-running">
      <div class="gen-formal-spinner"></div>
      <div class="rec-formal-lock-title">{{ t('generating.layer.formal_running_title') }}</div>
      <div class="rec-formal-lock-desc">{{ t('generating.layer.formal_progress', { done: props.progress.done, total: props.progress.total }) }}</div>
      <div class="gen-formal-bar"><div class="gen-formal-bar-fill" :style="{ width: props.percent + '%' }"></div></div>
    </div>
    <!-- 失败 / Error -->
    <div v-else-if="props.state === 'error'" class="rec-formal-lock gen-formal-card is-error">
      <div class="rec-formal-lock-title">{{ t('generating.layer.formal_error_title') }}</div>
      <div class="rec-formal-lock-desc">{{ props.version?.error || 'error' }}</div>
      <button type="button" class="gen-formal-btn" @click="emit('start')">{{ t('generating.layer.formal_retry') }}</button>
    </div>
    <!-- 失效 / Stale -->
    <div v-else-if="props.state === 'stale'" class="rec-formal-lock gen-formal-card is-stale">
      <div class="rec-formal-lock-title">{{ t('generating.layer.formal_stale_title') }}</div>
      <div class="rec-formal-lock-desc">{{ t('generating.layer.formal_stale_desc') }}</div>
      <button type="button" class="gen-formal-btn" @click="emit('start')">{{ t('generating.layer.formal_regenerate') }}</button>
    </div>
    <!-- 未生成 / Absent -->
    <template v-else-if="props.state === 'absent'">
      <div class="rec-formal-lock gen-formal-idle">
        <div class="rec-formal-lock-title">{{ t('generating.layer.formal_idle_title') }}</div>
        <div class="rec-formal-lock-desc">{{ t('generating.layer.formal_idle_desc') }}</div>
        <div class="gen-formal-estimate">
          {{ t('generating.layer.formal_estimate', { tokens: props.estimatedTokens }) }}
          <span class="gen-formal-cost-note">{{ props.costNote }}</span>
        </div>
        <div v-if="props.actionError" class="gen-formal-action-err" role="alert">{{ props.actionError }}</div>
        <button type="button" class="gen-formal-btn is-primary" :disabled="props.starting" @click="emit('start')">
          {{ props.starting ? t('generating.layer.formal_starting') : t('generating.layer.formal_generate') }}
        </button>
      </div>
      <label class="gen-formal-auto">
        <input type="checkbox" :checked="props.autoEnabled" @change="emit('toggle-auto', ($event.target as HTMLInputElement).checked)" />
        <span>{{ t('generating.layer.formal_auto') }}</span>
      </label>
    </template>
    <!-- 完成留痕条 / Done meta bar -->
    <div v-else-if="props.state === 'done'" class="gen-formal-meta">
      <span class="gen-formal-meta-item">{{ props.version?.model || 'AI' }}</span>
      <span class="gen-formal-meta-sep">·</span>
      <span class="gen-formal-meta-item">{{ t('generating.layer.formal_meta_tokens', { tokens: props.version?.usage.total_tokens ?? 0 }) }}</span>
      <span class="gen-formal-meta-sep">·</span>
      <span class="gen-formal-meta-item">{{ formatFormalTime(props.version?.finished_at) }}</span>
      <template v-if="props.toneCount > 0">
        <span class="gen-formal-meta-sep">·</span>
        <span class="gen-formal-meta-tone">{{ t('generating.layer.formal_tone_count', { n: props.toneCount }) }}</span>
      </template>
      <button type="button" class="gen-formal-regen" :disabled="props.starting" @click="emit('start')">{{ t('generating.layer.formal_regenerate') }}</button>
      <label class="gen-formal-auto is-inline">
        <input type="checkbox" :checked="props.autoEnabled" @change="emit('toggle-auto', ($event.target as HTMLInputElement).checked)" />
        <span>{{ t('generating.layer.formal_auto_short') }}</span>
      </label>
    </div>
    <div v-if="props.actionError && props.state !== 'absent'" class="gen-formal-action-err is-banner" role="alert">{{ props.actionError }}</div>
  </div>
</template>
