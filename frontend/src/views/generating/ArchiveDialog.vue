<template>
  <!-- 归档确认对话框 / Archive confirmation dialog -->
  <div v-show="modelValue" class="oms-overlay archive-overlay" data-vue-overlay :class="{ 'is-open': modelValue }" @click.self="emit('update:modelValue', false)">
    <div ref="dialogRef" class="oms-overlay-card archive-dialog" role="dialog" aria-modal="true" aria-labelledby="archiveDialogTitle">
      <div class="archive-dialog-header">
        <h3 id="archiveDialogTitle">{{ isUnarchive ? t('generating.archive_dialog.unarchive_title') : t('generating.archive_dialog.title') }}</h3>
        <button class="archive-dialog-close" @click="emit('update:modelValue', false)" :title="t('generating.archive_dialog.close')">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
        </button>
      </div>
      <div class="archive-dialog-body">
        <p>{{ isUnarchive ? t('generating.archive_dialog.unarchive_desc') : t('generating.archive_dialog.desc') }}</p>
      </div>
      <div class="archive-dialog-footer">
        <button class="btn-cancel" @click="emit('update:modelValue', false)">{{ t('generating.archive_dialog.cancel') }} <kbd>ESC</kbd></button>
        <button class="btn-submit" @click="emit('confirm')">{{ isUnarchive ? t('generating.archive_dialog.unarchive_confirm') : t('generating.archive_dialog.confirm') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDialog } from '@/composables/useDialog'

const { t } = useI18n()

const props = defineProps<{
  modelValue: boolean
  isUnarchive?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'confirm'): void
}>()

const { dialogRef } = useDialog(computed(() => props.modelValue), () => emit('update:modelValue', false))
</script>

<style scoped>
/* 尺寸覆盖（全局 .oms-overlay-card 默认 480px） / Size override (global .oms-overlay-card defaults to 480px) */
.archive-dialog {
  min-width: 400px;
  max-width: 500px;
  border-radius: var(--radius-lg);
  border: none;
  box-shadow: var(--dropdown-shadow);
}

.archive-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-4) var(--s-5);
  border-bottom: 1px solid var(--border);
}

.archive-dialog-header h3 {
  margin: 0;
  font-size: var(--fs-15);
  font-weight: 600;
}

.archive-dialog-close {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.2s;
  border-radius: var(--radius-sm);
}

.archive-dialog-close:hover {
  opacity: 1;
  background: var(--surface-2);
}

.archive-dialog-close svg {
  width: 12px;
  height: 12px;
}

.archive-dialog-close kbd {
  font-family: var(--font-mono);
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 3px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--subtle);
  line-height: 1.3;
}

.archive-dialog-body {
  padding: var(--s-5);
}

.archive-dialog-body p {
  margin: 0;
  color: var(--muted);
}

.archive-dialog-footer {
  display: flex;
  gap: var(--s-2);
  justify-content: flex-end;
  padding: var(--s-3) var(--s-4);
  border-top: 1px solid var(--border);
}

.btn-cancel,
.btn-submit {
  padding: var(--s-2) var(--s-4);
  border-radius: var(--radius-sm);
  font-size: var(--fs-14);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-cancel {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--fg);
}

.btn-cancel:hover {
  background: var(--surface-2);
}

.btn-submit {
  background: var(--accent);
  border: 1px solid var(--accent);
  color: var(--accent-fg);
}

.btn-submit:hover {
  background: oklch(from var(--accent) calc(l - 0.06) c h);
}
</style>
