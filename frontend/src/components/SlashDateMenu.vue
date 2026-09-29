<template>
  <!-- 斜杠日期候选菜单：纯展示，交互状态与落位由宿主 useSlashDateMenu 提供 -->
  <div
    v-if="open"
    class="slash-menu"
    role="menu"
    :aria-label="t('generating.todos.date_menu_aria')"
    :style="{ left: pos.left + 'px', top: pos.top + 'px' }"
  >
    <button
      v-for="(it, i) in items"
      :key="it.token"
      type="button"
      role="menuitem"
      class="slash-menu-item"
      :class="{ 'is-active': i === activeIndex }"
      :aria-label="t('generating.todos.date_menu_' + it.key) + ' ' + it.preview"
      @mousedown.prevent="$emit('select', i)"
      @mouseenter="$emit('hover', i)"
    >
      <span class="slash-menu-name">{{ t('generating.todos.date_menu_' + it.key) }}</span>
      <span class="slash-menu-token">{{ it.token }}</span>
      <span class="slash-menu-preview">{{ it.preview }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { SlashMenuItem } from '@/composables/useSlashDateMenu'

defineProps<{
  open: boolean
  items: SlashMenuItem[]
  activeIndex: number
  pos: { left: number; top: number }
}>()

defineEmits<{
  (e: 'select', idx: number): void
  (e: 'hover', idx: number): void
}>()

const { t } = useI18n()
</script>

<style scoped>
.slash-menu {
  position: absolute;
  z-index: var(--z-popover, 500);
  min-width: 200px;
  padding: 4px;
  background: var(--surface, oklch(99% 0 0));
  border: 1px solid var(--border, oklch(88% 0.01 250));
  border-radius: var(--radius-md, 8px);
  box-shadow: 0 6px 20px oklch(0% 0 0 / 0.12);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.slash-menu-item {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 5px 8px;
  border: none;
  border-radius: var(--radius-sm, 6px);
  background: transparent;
  color: var(--fg, oklch(20% 0.01 250));
  font-family: inherit;
  font-size: var(--fs-13, 13px);
  text-align: left;
  cursor: pointer;
}
.slash-menu-item.is-active {
  background: var(--surface-2, oklch(92% 0 0));
}
.slash-menu-name { white-space: nowrap; }
.slash-menu-token {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: var(--fs-11, 11px);
  color: var(--muted, oklch(50% 0 0));
}
.slash-menu-preview {
  font-variant-numeric: tabular-nums;
  color: var(--accent, oklch(55% 0.15 250));
  white-space: nowrap;
}
</style>
