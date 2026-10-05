<template>
  <div class="responsive-btn-group" ref="containerEl">
    <!-- 可见按钮 / Visible buttons -->
    <button
      v-for="btn in visibleButtons"
      :key="btn.key"
      class="responsive-btn-item"
      :class="[
        `is-${btn.variant || 'primary'}`,
        { 'is-icon-only': mode !== 'full' }
      ]"
      :title="btn.label"
      @click="btn.onClick"
    >
      <component :is="btn.icon" v-if="btn.icon" class="btn-icon" />
      <span v-if="mode === 'full'" class="btn-label">{{ btn.label }}</span>
      <span v-if="mode === 'full' && btn.shortcut" class="btn-shortcut">{{ btn.shortcut }}</span>
    </button>

    <!-- 更多按钮 / More button -->
    <div v-if="hiddenButtons.length > 0" class="more-wrap">
      <button ref="moreBtnEl" class="responsive-btn-item is-more" v-bind="moreTriggerAttrs" @click="toggleMore" :title="t('common.action.more')" :aria-label="t('common.action.more')">
        <svg class="btn-icon" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/>
        </svg>
      </button>
      <!-- Teleport 到 body：避免祖先 transform/overflow 劫持 fixed 定位与层叠上下文 / Teleport to body: avoid ancestor transform/overflow hijacking fixed positioning and stacking context -->
      <Teleport to="body">
        <div ref="dropdownEl" class="more-dropdown" v-bind="moreMenuAttrs" :class="{ 'is-open': showMore }">
          <button
            v-for="btn in hiddenButtons"
            :key="btn.key"
            class="more-dropdown-item"
            :title="btn.label"
            @click="handleMoreClick(btn)"
            role="menuitem"
          >
            <component :is="btn.icon" v-if="btn.icon" class="dropdown-icon" />
            <span>{{ btn.label }}</span>
          </button>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePopMenu } from '@/composables/usePopMenu'
import { BREAKPOINTS } from '@/composables/useContainerSize'

export interface ButtonItem {
  key: string
  label: string
  icon?: Component
  variant?: 'primary' | 'secondary'
  shortcut?: string
  onClick: () => void
}

interface Props {
  buttons: ButtonItem[]
  /** 最小宽度阈值（px），低于此值进入 icon-only + more 模式 / Minimum width threshold (px), below this enters icon-only + more mode */
  iconThreshold?: number
  /** 中等宽度阈值（px），低于此值进入 icon-only 模式（全部显示为图标，无更多按钮） / Medium width threshold (px), below this enters icon-only mode (all shown as icons, no more button) */
  mixedThreshold?: number
}

const props = withDefaults(defineProps<Props>(), {
  iconThreshold: BREAKPOINTS.xs,
  mixedThreshold: BREAKPOINTS.sm,
})

const { t } = useI18n()

const containerEl = ref<HTMLElement | null>(null)
const moreBtnEl = ref<HTMLElement | null>(null)
const dropdownEl = ref<HTMLElement | null>(null)

const { visible: showMore, toggle: toggleMore, close: closeMore, triggerAttrs: moreTriggerAttrs, menuAttrs: moreMenuAttrs } = usePopMenu(dropdownEl, moreBtnEl)

/** 当前容器宽度 / Current container width */
const containerWidth = ref(0)
let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  if (!containerEl.value) return
  resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
      containerWidth.value = entry.contentRect.width
    }
  })
  resizeObserver.observe(containerEl.value)
})

onUnmounted(() => {
  resizeObserver?.disconnect()
})

/** 计算当前模式 / Compute current mode */
const mode = computed(() => {
  const w = containerWidth.value
  if (w <= props.iconThreshold) return 'icon-more'    // ≤480px: 仅图标 + 更多按钮 / icon-only + more button
  if (w <= props.mixedThreshold) return 'icon-only'   // 481-640px: 全部显示为图标，无更多按钮 / all icons, no more button
  return 'full'                                       // >640px: 图标 + 文字 / icon + text
})

/** 可见按钮列表 / Visible button list */
const visibleButtons = computed(() => {
  if (mode.value === 'full') return props.buttons
  if (mode.value === 'icon-only') return props.buttons
  // icon-more 模式：保留第一个按钮，其余进“更多” / icon-more mode: keep first button, rest go to "more"
  return props.buttons.slice(0, 1)
})

/** 隐藏到“更多”中的按钮 / Buttons hidden in "more" */
const hiddenButtons = computed(() => {
  if (mode.value !== 'icon-more') return []
  return props.buttons.slice(1)
})

function handleMoreClick(btn: ButtonItem) {
  closeMore()
  btn.onClick()
}
</script>

<style scoped>
.responsive-btn-group {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  position: relative;
  /* 必须撑满父容器可用宽度，ResizeObserver 测量的才是“可用空间”而非按钮内容宽度 / Must fill available parent width; ResizeObserver measures "available space" not button content width */
  flex: 1;
  min-width: 0;
}

.responsive-btn-item {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  padding: 12px 24px;
  border-radius: var(--radius-lg);
  font-size: var(--fs-14);
  font-weight: 500;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
  flex-shrink: 0;
}

/* Primary 变体 / Primary variant */
.responsive-btn-item.is-primary {
  background: var(--fg);
  color: var(--bg);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 4px 12px rgba(0, 0, 0, 0.06);
}

.responsive-btn-item.is-primary:hover {
  background: oklch(25% 0.012 250);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1), 0 8px 20px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
}

.responsive-btn-item.is-primary:active {
  transform: translateY(0);
}

/* Secondary 变体 / Secondary variant */
.responsive-btn-item.is-secondary {
  background: var(--surface);
  color: var(--fg);
  border: 1px solid var(--border-strong);
}

.responsive-btn-item.is-secondary:hover {
  border-color: var(--fg);
  background: var(--surface-2);
}

/* Icon-only 模式 / Icon-only mode */
.responsive-btn-item.is-icon-only {
  padding: 12px;
}

.responsive-btn-item.is-icon-only .btn-label {
  display: none;
}

.btn-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

.btn-shortcut {
  font-size: var(--fs-12);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: "SF Mono", Monaco, "Cascadia Code", monospace;
  line-height: 1.4;
}

.is-primary .btn-shortcut {
  background: rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.7);
}

.is-secondary .btn-shortcut {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--muted);
}

/* 更多按钮容器 / More button container */
.more-wrap {
  position: relative;
}

.more-dropdown {
  position: fixed;
  z-index: var(--z-popover);
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  padding: 6px 0;
  min-width: 160px;
  opacity: 0;
  transform: translateY(-4px);
  pointer-events: none;
  transition: opacity 0.15s, transform 0.15s;
}

.more-dropdown.is-open {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

.more-dropdown-item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  width: 100%;
  padding: 8px 14px;
  font-size: var(--fs-13);
  color: var(--fg);
  background: none;
  border: none;
  cursor: pointer;
  transition: background 0.12s;
}

.more-dropdown-item:hover {
  background: var(--surface-2);
}

.dropdown-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: var(--muted);
}
</style>
