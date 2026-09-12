<template>
  <!-- 删除确认对话框 -->
  <div v-if="modelValue" class="delete-dialog-overlay" @click.self="emit('update:modelValue', false)">
    <div class="delete-dialog">
      <div class="delete-dialog-header">
        <h3>{{ t('generating.delete_dialog.title') }}</h3>
        <button class="delete-dialog-close" @click="emit('update:modelValue', false)" :title="t('generating.delete_dialog.close')">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
        </button>
      </div>
      <div class="delete-dialog-body">
        <p>{{ t('generating.delete_dialog.desc') }}</p>
      </div>
      <div class="delete-dialog-footer">
        <button class="btn-cancel" @click="emit('update:modelValue', false)">{{ t('generating.delete_dialog.cancel') }}</button>
        <button class="btn-danger" @click="emit('confirm')">{{ t('generating.delete_dialog.confirm') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'confirm'): void
}>()
</script>

<style scoped>
.delete-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.delete-dialog {
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--dropdown-shadow);
  min-width: 400px;
  max-width: 500px;
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
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.delete-dialog-close:hover {
  opacity: 1;
}

.delete-dialog-close svg {
  width: 12px;
  height: 12px;
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
  background: var(--rec);
  border: 1px solid var(--rec);
  color: #fff;
}

.btn-danger:hover {
  background: oklch(from var(--rec) calc(l - 0.06) c h);
}
</style>
