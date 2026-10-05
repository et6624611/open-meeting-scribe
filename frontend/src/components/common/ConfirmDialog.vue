<template>
  <Teleport to="body">
    <div v-show="modelValue" class="confirm-overlay" data-vue-overlay :class="{ 'is-open': modelValue }" @click.self="onCancel">
      <div ref="dialogRef" class="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirmDialogTitle">
        <div class="confirm-header">
          <h3 id="confirmDialogTitle">{{ resolvedTitle }}</h3>
          <button class="confirm-close" :aria-label="t('common.action.close')" @click="onCancel">
            <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
          </button>
        </div>
        <div class="confirm-body">
          <p>{{ message }}</p>
        </div>
        <div class="confirm-footer">
          <button class="confirm-cancel" @click="onCancel">{{ resolvedCancelText }} <kbd>ESC</kbd></button>
          <button class="confirm-action" :class="{ 'is-danger': danger }" @click="onConfirm">{{ resolvedConfirmText }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDialog } from '@/composables/useDialog'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  modelValue: boolean
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}>(), {
  title: undefined,
  confirmText: undefined,
  cancelText: undefined,
  danger: true,
})

const resolvedTitle = computed(() => props.title ?? t('common.confirm_dialog.default_title'))
const resolvedConfirmText = computed(() => props.confirmText ?? t('common.confirm_dialog.confirm'))
const resolvedCancelText = computed(() => props.cancelText ?? t('common.confirm_dialog.cancel'))

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'confirm'): void
}>()

function onCancel() {
  emit('update:modelValue', false)
}

function onConfirm() {
  emit('confirm')
  emit('update:modelValue', false)
}

const { dialogRef } = useDialog(computed(() => props.modelValue), onCancel)
</script>

<style scoped>
.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  background: var(--overlay-bg);
  display: grid;
  place-items: center;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
}

.confirm-overlay.is-open {
  opacity: 1;
  pointer-events: auto;
}

.confirm-dialog {
  min-width: 400px;
  max-width: 500px;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 60px oklch(0% 0 0 / 0.10), 0 4px 16px oklch(0% 0 0 / 0.05);
  transform: translateY(8px);
  opacity: 0;
  transition: transform 0.25s ease, opacity 0.2s ease;
}

.confirm-overlay.is-open .confirm-dialog {
  transform: translateY(0);
  opacity: 1;
}

.confirm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-4) var(--s-5);
  border-bottom: 1px solid var(--border);
}

.confirm-header h3 {
  margin: 0;
  font-size: var(--fs-15);
  font-weight: 600;
}

.confirm-close {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.2s;
  border-radius: var(--radius-sm);
}

.confirm-close:hover {
  opacity: 1;
  background: var(--surface-2);
}

.confirm-close svg {
  width: 12px;
  height: 12px;
}

.confirm-body {
  padding: var(--s-5);
}

.confirm-body p {
  margin: 0;
  color: var(--muted);
}

.confirm-footer {
  display: flex;
  gap: var(--s-2);
  justify-content: flex-end;
  padding: var(--s-3) var(--s-4);
  border-top: 1px solid var(--border);
}

.confirm-cancel,
.confirm-action {
  padding: var(--s-2) var(--s-4);
  border-radius: var(--radius-sm);
  font-size: var(--fs-14);
  cursor: pointer;
  transition: all 0.2s;
}

.confirm-cancel {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--fg);
}

.confirm-cancel:hover {
  background: var(--surface-2);
}

.confirm-cancel kbd {
  font-family: var(--font-mono);
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 3px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--subtle);
  line-height: 1.3;
  margin-left: 4px;
}

.confirm-action {
  background: var(--accent);
  border: 1px solid var(--accent);
  color: #fff;
}

.confirm-action:hover {
  background: oklch(from var(--accent) calc(l - 0.06) c h);
}

.confirm-action.is-danger {
  background: var(--error);
  border-color: var(--error);
}

.confirm-action.is-danger:hover {
  background: oklch(from var(--error) calc(l - 0.06) c h);
}
</style>
