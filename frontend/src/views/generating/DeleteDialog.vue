<template>
  <!-- 删除确认对话框 / Delete confirmation dialog -->
  <div v-show="modelValue" class="oms-overlay delete-overlay" data-vue-overlay :class="{ 'is-open': modelValue }" @click.self="emit('update:modelValue', false)">
    <div ref="dialogRef" class="oms-overlay-card delete-dialog" role="dialog" aria-modal="true" aria-labelledby="deleteDialogTitle">
      <div class="delete-dialog-header">
        <h3 id="deleteDialogTitle">{{ t('generating.delete_dialog.title') }}</h3>
        <button class="delete-dialog-close" @click="emit('update:modelValue', false)" :title="t('generating.delete_dialog.close')">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
        </button>
      </div>
      <div class="delete-dialog-body">
        <p>{{ t('generating.delete_dialog.desc') }}</p>
      </div>
      <div class="delete-dialog-footer">
        <button class="btn-cancel" @click="emit('update:modelValue', false)">{{ t('generating.delete_dialog.cancel') }} <kbd>ESC</kbd></button>
        <button class="btn-danger" @click="emit('confirm')">{{ t('generating.delete_dialog.confirm') }}</button>
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
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'confirm'): void
}>()

const { dialogRef } = useDialog(computed(() => props.modelValue), () => emit('update:modelValue', false))
</script>

<style scoped>
/* 尺寸覆盖（全局 .oms-overlay-card 默认 480px） / Size override (global .oms-overlay-card defaults to 480px) */
.delete-dialog {
  min-width: 400px;
  max-width: 500px;
  border-radius: var(--radius-lg);
  border: none;
  box-shadow: var(--dropdown-shadow);
}

.delete-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-4) var(--s-5);
  border-bottom: 1px solid var(--border);
}

.delete-dialog-header h3 {
  margin: 0;
  font-size: var(--fs-15);
  font-weight: 600;
}

.delete-dialog-close {
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

.delete-dialog-close:hover {
  opacity: 1;
  background: var(--surface-2);
}

.delete-dialog-close svg {
  width: 12px;
  height: 12px;
}

.delete-dialog-close kbd {
  font-family: var(--font-mono);
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 3px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--subtle);
  line-height: 1.3;
}

.delete-dialog-body {
  padding: var(--s-5);
}

.delete-dialog-body p {
  margin: 0;
  color: var(--muted);
}

.delete-dialog-footer {
  display: flex;
  gap: var(--s-2);
  justify-content: flex-end;
  padding: var(--s-3) var(--s-4);
  border-top: 1px solid var(--border);
}

.btn-cancel,
.btn-danger {
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

.btn-danger {
  background: var(--error);
  border: 1px solid var(--error);
  /* 原为 #fff：暗色主题下 --error 提到 L66% 后白字不足 AA，
     --surface 在明暗两侧都能达到 ≥4.5:1 */
  color: var(--surface);
}

.btn-danger:hover {
  background: oklch(from var(--error) calc(l - 0.06) c h);
}
</style>
