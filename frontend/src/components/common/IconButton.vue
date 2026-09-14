<template>
  <button
    class="icon-btn"
    :class="classes"
    :title="label"
    :aria-label="label"
    :data-tip="!showLabel ? label : undefined"
    :disabled="disabled"
    v-bind="$attrs"
  >
    <span class="icon-btn__icon">
      <slot />
    </span>
    <span v-if="showLabel" class="icon-btn__text">
      <slot name="label">{{ label }}</slot>
    </span>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<{
  /** 按钮文本名称（必填）—— 用于 tooltip / aria-label / 可见文本 / Button text label (required) — used for tooltip / aria-label / visible text */
  label: string
  /** 是否同时显示文本标签（false = 仅图标 + tooltip） / Whether to show text label (false = icon only + tooltip) */
  showLabel?: boolean
  /** 是否处于激活/选中态 / Whether in active/selected state */
  active?: boolean
  /** 是否禁用 / Whether disabled */
  disabled?: boolean
  /** tooltip 出现方向 / Tooltip position */
  tipPosition?: 'right' | 'bottom' | 'top'
}>(), {
  showLabel: false,
  active: false,
  disabled: false,
  tipPosition: 'right',
})

const classes = computed(() => ({
  'icon-btn--icon-only': !props.showLabel,
  'icon-btn--with-label': props.showLabel,
  'icon-btn--active': props.active,
  [`icon-btn--tip-${props.tipPosition}`]: !props.showLabel,
}))
</script>

<style scoped>
.icon-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2, 8px);
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--subtle, oklch(55% 0.02 250));
  border-radius: var(--radius-sm, 6px);
  transition: background 0.15s, color 0.15s;
  font-family: var(--font-body);
  line-height: 1;
}

.icon-btn--icon-only {
  width: 32px;
  height: 32px;
  padding: 0;
}

.icon-btn--with-label {
  width: auto;
  padding: 0 var(--s-2, 8px);
  gap: var(--s-1, 4px);
  font-size: var(--fs-11, 11px);
}

.icon-btn:hover {
  background: var(--surface-2, oklch(95% 0.01 250));
  color: var(--fg, oklch(20% 0.01 250));
}

.icon-btn:focus-visible {
  outline: 2px solid var(--accent, oklch(58% 0.18 255));
  outline-offset: 2px;
}

.icon-btn--active {
  color: var(--accent, oklch(58% 0.18 255));
  background: var(--accent-soft, oklch(58% 0.18 255 / 0.08));
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  pointer-events: none;
}

.icon-btn__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon-btn__icon :deep(svg) {
  width: 18px;
  height: 18px;
}

.icon-btn--with-label .icon-btn__icon :deep(svg) {
  width: 16px;
  height: 16px;
}

.icon-btn__text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Tooltip 由全局 #global-tooltip 统一渲染，不再使用 ::after 伪元素 / Tooltip rendered by global #global-tooltip, no longer using ::after pseudo-element */
</style>
