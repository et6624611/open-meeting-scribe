<template>
  <Teleport to="body">
    <div v-if="open" class="leg-overlay" data-vue-overlay role="dialog" aria-modal="true" :aria-label="t('settings.engine_guide_title')">
      <div class="leg-dialog">
        <div class="leg-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        </div>
        <div class="leg-title">{{ t('settings.engine_guide_title') }}</div>
        <div class="leg-desc">{{ t('settings.engine_guide_desc') }}</div>

        <div class="leg-reasons">
          <div v-if="diskShort" class="leg-reason is-disk">
            <div class="leg-reason-title">{{ t('settings.engine_guide_disk_title') }}</div>
            <div class="leg-reason-body">{{ t('settings.engine_guide_disk_body', { required: requiredText, buffer: bufferText, free: freeText }) }}</div>
            <div class="leg-reason-hint">{{ t('settings.engine_guide_disk_hint') }}</div>
          </div>
          <div v-if="missing.length" class="leg-reason is-missing">
            <div class="leg-reason-title">{{ t('settings.engine_guide_missing_title') }}</div>
            <div class="leg-reason-body">{{ t('settings.engine_guide_missing_body', { names: missingNames }) }}</div>
          </div>
          <div v-if="tampered.length" class="leg-reason is-tampered">
            <div class="leg-reason-title">{{ t('settings.engine_guide_tampered_title') }}</div>
            <div class="leg-reason-body">{{ t('settings.engine_guide_tampered_body', { names: tamperedNames }) }}</div>
          </div>
        </div>

        <div class="leg-actions">
          <button class="btn btn-secondary" @click="$emit('close')">{{ t('settings.engine_guide_cancel') }}</button>
          <button v-if="canDownload" class="btn btn-primary" @click="$emit('download-all')">{{ t('settings.engine_guide_download_all') }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * 首次启用本地引擎引导弹窗（R5 / PRD §7.1）：磁盘预检失败 / 权重缺失 / 校验失败拒载的排错出口。
 * First-enable guide dialog (R5 / PRD §7.1): troubleshooting entry for disk precheck failure,
 * missing weights, and integrity-verification rejection.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEscClose } from '@/composables/useEscClose'
import type { EngineModelInfo } from '@/api/engine'

const props = defineProps<{
  open: boolean
  diskFreeBytes: number
  diskRequiredBytes: number
  diskBufferBytes: number
  missing: EngineModelInfo[]
  tampered: EngineModelInfo[]
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'download-all'): void
}>()

const { t } = useI18n()

useEscClose(computed(() => props.open), () => emit('close'))

const diskShort = computed(() => props.diskFreeBytes < props.diskRequiredBytes + props.diskBufferBytes)
const missingNames = computed(() => props.missing.map(m => m.name).join('、'))
const tamperedNames = computed(() => props.tampered.map(m => m.name).join('、'))
const canDownload = computed(() => props.missing.length > 0 || props.tampered.length > 0)

function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  return `${Math.round(bytes / 1024 ** 2)} MB`
}
const requiredText = computed(() => formatBytes(props.diskRequiredBytes))
const bufferText = computed(() => formatBytes(props.diskBufferBytes))
const freeText = computed(() => formatBytes(props.diskFreeBytes))
</script>

<style scoped>
.leg-overlay { position: fixed; inset: 0; z-index: var(--z-modal, 1000); display: grid; place-items: center; background: oklch(10% 0.02 260 / 0.45); backdrop-filter: blur(2px); }
.leg-dialog { width: min(480px, calc(100vw - 48px)); max-height: calc(100vh - 96px); overflow-y: auto; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg, 12px); padding: var(--s-5); box-shadow: 0 12px 40px oklch(10% 0.02 260 / 0.25); }
.leg-icon { width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; color: var(--warn); background: var(--warn-soft); margin-bottom: var(--s-3); }
.leg-title { font-size: 15px; font-weight: 600; margin-bottom: var(--s-2); }
.leg-desc { font-size: 12px; color: var(--muted); margin-bottom: var(--s-4); line-height: 1.6; }
.leg-reasons { display: flex; flex-direction: column; gap: var(--s-3); }
.leg-reason { border: 1px solid var(--border); border-radius: var(--radius); padding: var(--s-3); border-left-width: 3px; }
.leg-reason.is-disk { border-left-color: var(--warn); }
.leg-reason.is-missing { border-left-color: var(--accent); }
.leg-reason.is-tampered { border-left-color: var(--error); }
.leg-reason-title { font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.leg-reason.is-tampered .leg-reason-title { color: var(--error); }
.leg-reason-body { font-size: 12px; color: var(--muted); line-height: 1.6; }
.leg-reason-hint { font-size: 11px; color: var(--subtle); margin-top: 4px; line-height: 1.5; }
.leg-actions { display: flex; justify-content: flex-end; gap: var(--s-2); margin-top: var(--s-4); }
</style>
