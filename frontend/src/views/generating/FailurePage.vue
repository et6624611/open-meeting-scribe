<template>
  <!-- 失败态：整页替换为居中大卡片 / Failed state: full-page replacement with centered card -->
  <!-- 背景：录音管线失败后 output_path/audio_path 均为空，若仍渲染工具栏，用户点击导出会触发 /api/download 404，
       新标签页展示原始 JSON {"detail":"Not Found"}。此处统一拦截，按 error_category 展示友好失败页。
       Context: after pipeline failure output_path/audio_path are null; rendering the toolbar would let users
       hit /api/download 404 and see raw JSON in a new tab. Intercept here with a category-aware failure page. -->
  <div class="gen-failure-page">
    <div class="gen-failure-card">
      <div class="gen-failure-icon" :class="failureInfo.iconClass">
        <svg v-if="failureInfo.icon === 'refresh'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
        <svg v-else-if="failureInfo.icon === 'settings'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H2a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V2a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H22a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>
        <svg v-else-if="failureInfo.icon === 'audio'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      </div>
      <h2 class="gen-failure-title">{{ t('generating.failure.title') }}</h2>
      <p class="gen-failure-message">{{ failureInfo.message }}</p>
      <p v-if="failureInfo.suggestion" class="gen-failure-suggestion">{{ failureInfo.suggestion }}</p>
      <!-- R4-简（REQ-TRANSCRIBE-PROGRESS）：失败阶段标红 + 已处理百分比；重试入口沿用卡片按钮 -->
      <!-- Failed stage highlighted red with processed percent; retry actions stay on the card buttons -->
      <ProgressDialog :task="task" compact hide-retry class="gen-failure-progress" />
      <details v-if="failureInfo.rawError" class="gen-failure-raw">
        <summary>{{ t('generating.failure.show_raw') }}</summary>
        <code>{{ failureInfo.rawError }}</code>
      </details>
      <div class="gen-failure-actions">
        <button class="btn btn-primary" @click="$emit('retry')">{{ t('task.failure.transient_action') }}</button>
        <!-- AC-4（QA-R1 DEF-04）：本地引擎失败时按 can_fallback_cloud 渲染云端回退。
             True ⇒ 「切云端重试」+ 显式确认（数据上云告知）；False ⇒ 置灰 + 纯内网原因。
             AC-4: cloud fallback gated on can_fallback_cloud; explicit confirm dialog before uploading data. -->
        <button
          v-if="canFallbackCloud"
          class="btn btn-secondary gen-fallback-cloud-btn"
          @click="$emit('update:showCloudFallbackConfirm', true)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>
          {{ t('generating.failure.cloud_retry') }}
        </button>
        <template v-else-if="cloudFallbackBlocked">
          <button
            class="btn btn-secondary gen-fallback-cloud-btn"
            disabled
            :aria-disabled="true"
            :title="t('generating.failure.cloud_retry_blocked_reason')"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/><line x1="2" y1="2" x2="22" y2="22"/></svg>
            {{ t('generating.failure.cloud_retry') }}
          </button>
          <p class="gen-fallback-blocked-reason">{{ t('generating.failure.cloud_retry_blocked_reason') }}</p>
        </template>
        <button class="btn btn-secondary" @click="$emit('backToLibrary')">{{ t('generating.failure.back_to_library') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import ProgressDialog from './ProgressDialog.vue'

const { t } = useI18n()

defineProps<{
  failureInfo: {
    icon: string
    iconClass: string
    message: string
    suggestion?: string
    rawError?: string
  }
  task: any
  canFallbackCloud: boolean
  cloudFallbackBlocked: boolean
  showCloudFallbackConfirm: boolean
}>()

defineEmits<{
  retry: []
  backToLibrary: []
  'update:showCloudFallbackConfirm': [value: boolean]
}>()
</script>
