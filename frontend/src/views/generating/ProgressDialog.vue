<template>
  <!-- 统一进度面板（REQ-TRANSCRIBE-PROGRESS P0）：步骤条 + 百分比 + 已用时长/ETA + 安心文案
       Unified progress panel: stepper + percent + elapsed/ETA + reassurance. message 调试语不透传，全部文案走 i18n。 -->
  <div class="tp-panel" :class="{ 'tp-panel--compact': compact }" role="group" :aria-label="t('processing.title')">
    <!-- 4 步步骤条 / 4-step stepper -->
    <ol class="tp-steps" :aria-label="t('processing.steps_aria')">
      <li
        v-for="(step, i) in stepKeys" :key="step"
        class="tp-step"
        :class="{
          'is-done': stepState(i) === 'done',
          'is-active': stepState(i) === 'active',
          'is-failed': stepState(i) === 'failed',
        }"
        :aria-current="stepState(i) === 'active' ? 'step' : undefined"
      >
        <span class="tp-step-marker" aria-hidden="true">
          <svg v-if="stepState(i) === 'done'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          <svg v-else-if="stepState(i) === 'failed'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          <span v-else class="tp-step-num">{{ i + 1 }}</span>
        </span>
        <span class="tp-step-label">{{ t(`processing.step_${step}`) }}</span>
      </li>
    </ol>

    <!-- 失败态（R4-简）：停留阶段标红 + 已处理百分比 + 重试 / Failed state: red stage + processed percent + retry -->
    <template v-if="progress.isFailed.value">
      <p class="tp-failed-caption" role="alert">
        {{ t('processing.failed_caption', { stage: t(`processing.step_${stepKeys[failedIdx] ?? stepKeys[0]}`), percent: Math.round(progress.rawPercent.value) }) }}
      </p>
      <button v-if="!hideRetry" class="tp-retry-btn" @click="emit('retry')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
        {{ t('processing.retry') }}
      </button>
    </template>

    <!-- 进行态：百分比进度条 + 计时行 + 安心文案 / In-progress state -->
    <template v-else-if="!hideRunning && (progress.isActive.value || backfill)">
      <div
        class="tp-bar" role="progressbar"
        :aria-valuenow="Math.round(progress.displayPercent.value)"
        aria-valuemin="0" aria-valuemax="100"
        :aria-label="t('processing.title')"
      >
        <div class="tp-bar-fill" :style="{ width: progress.displayPercent.value + '%' }"></div>
      </div>
      <div class="tp-meta-row">
        <span v-if="!backfill" class="tp-percent">{{ Math.round(progress.displayPercent.value) }}%</span>
        <span class="tp-elapsed">{{ t('processing.elapsed', { time: progress.formatElapsed(progress.elapsedSec.value) }) }}</span>
        <template v-if="!backfill">
          <span class="tp-sep" v-if="etaText">·</span>
          <span v-if="etaText" class="tp-eta">{{ etaText }}</span>
          <span v-else-if="!progress.stagnated.value" class="tp-eta-unknown">{{ t('processing.eta_unknown') }}</span>
        </template>
        <span v-if="backfill" class="tp-eta-unknown">{{ t('processing.chapter_backfill') }}</span>
      </div>
      <!-- 停滞 >60s：安抚文案，不显示失败（R2 边界） / Stagnation: soothing copy, never a false failure -->
      <p v-if="progress.stagnated.value && !backfill" class="tp-stagnation">{{ t('processing.stagnation') }}</p>
      <p class="tp-reassure">{{ t('processing.reassure') }}</p>
    </template>

    <slot></slot>
  </div>
</template>

<script setup lang="ts">
/**
 * ProgressDialog — 原文/纪要/章节三处加载态统一消费的进度面板。
 * 单一数据源：task（GET /api/tasks/{id} 轮询补丁后的 store 对象）；禁止各面板自判状态（需求 §9 风险缓解）。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTranscribeProgress } from '@/composables/useTranscribeProgress'
import type { Task } from '@/api/types'

const { t } = useI18n()

const props = defineProps<{
  task: Task | null | undefined
  /** 章节补生成态：无管线进度信号，仅步骤定位 + 已用时长 + 章节文案 */
  backfill?: boolean
  /** 紧凑模式（失败卡片内嵌）：隐藏进度条与文案，仅步骤条 + 失败说明 */
  compact?: boolean
  /** 外层已有重试入口时隐藏内置按钮 */
  hideRetry?: boolean
  /** 失败态下隐藏进行态（整页失败卡片场景已由外层接管文案与操作） */
  hideRunning?: boolean
}>()

const emit = defineEmits<{ (e: 'retry'): void }>()

const stepKeys = ['transcribe', 'organize', 'summarize', 'done'] as const

const progress = useTranscribeProgress(computed(() => props.task))

const activeIdx = computed(() => (props.backfill ? 2 : progress.currentStep.value))
const failedIdx = computed(() => progress.failedStep.value ?? progress.currentStep.value)

function stepState(i: number): 'done' | 'active' | 'failed' | 'waiting' {
  if (progress.isFailed.value && !props.hideRunning) {
    if (i < failedIdx.value) return 'done'
    if (i === failedIdx.value) return 'failed'
    return 'waiting'
  }
  if (props.backfill) {
    return i < 2 ? 'done' : (i === 2 ? 'active' : 'waiting')
  }
  const cur = activeIdx.value
  if (i < cur) return 'done'
  if (i === cur) return progress.isCompleted.value ? 'done' : 'active'
  return 'waiting'
}

/** ETA 文本：估算不成立时返回空串（显示安抚文案而非假数字） */
const etaText = computed(() => {
  const m = progress.etaMinutes.value
  if (m === null || progress.stagnated.value) return ''
  return t('processing.eta', { minutes: m })
})
</script>
