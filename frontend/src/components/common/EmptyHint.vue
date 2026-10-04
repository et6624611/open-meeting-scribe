<template>
  <!-- 统一空态语言：图标 · 标题 · 说明 · 可选动作；垂直居中，仅在真·无内容时由父级渲染 -->
  <div class="empty-hint" :class="{ 'is-compact': compact, 'is-card': card }" role="status">
    <div v-if="$slots.icon || icon" class="eh-icon">
      <slot name="icon">
        <svg v-if="icon === 'inbox'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>
      </slot>
    </div>
    <p v-if="title" class="eh-title">{{ title }}</p>
    <p v-if="body" class="eh-body">{{ body }}</p>
    <div v-if="$slots.action" class="eh-action"><slot name="action" /></div>
    <slot />
  </div>
</template>

<script setup lang="ts">
/**
 * EmptyHint — 全应用统一空态 / App-wide unified empty-state block
 *
 * 结构固定为「图标 → 标题 → 说明 → 动作（可选）」，四处会话/内容面板共用同一视觉：
 * AI 会话 / 随记 / 决策 只给提示词不传 action；洞察通过 action 插槽保留「共创」按钮。
 * 仅在父级确认真·无内容时渲染——有数据立即让位，空态判断收敛在父级单一入口。
 */
withDefaults(defineProps<{
  title?: string
  body?: string
  /** 内置图标名（目前仅 inbox 兜底）；复杂图标走 #icon 插槽 */
  icon?: string
  /** 紧凑模式：缩小图标与间距，用于低高度容器 */
  compact?: boolean
  /** 卡片模式：虚线边框卡片（与随记空态 notes-empty-guide 同视觉），用于大空白内容区 */
  card?: boolean
}>(), {
  title: '',
  body: '',
  icon: '',
  compact: false,
  card: false,
})
</script>

<style scoped>
.empty-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--s-8, 32px) var(--s-6, 24px);
  width: 100%;
  height: 100%;
}
.eh-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  margin-bottom: var(--s-4, 14px);
  background: var(--surface-2);
  color: var(--subtle);
  flex-shrink: 0;
}
.eh-icon :deep(svg) { width: 22px; height: 22px; }
.eh-title {
  font-size: var(--fs-13, 13px);
  font-weight: 600;
  color: var(--fg);
  margin: 0 0 6px;
}
.eh-body {
  font-size: var(--fs-12, 12px);
  line-height: 1.7;
  color: var(--muted);
  max-width: 300px;
  margin: 0;
}
.eh-action { margin-top: var(--s-4, 16px); display: flex; align-items: center; gap: 8px; }
.empty-hint.is-compact { padding: var(--s-6, 24px) var(--s-4, 16px); }
.empty-hint.is-compact .eh-icon { width: 36px; height: 36px; margin-bottom: var(--s-3, 10px); }
.empty-hint.is-compact .eh-icon :deep(svg) { width: 18px; height: 18px; }
/* 卡片模式：与随记空态 notes-empty-guide 同一视觉（虚线卡片 · 38px 图标 · 居中限宽） */
.empty-hint.is-card {
  width: min(440px, 100%);
  box-sizing: border-box;
  height: auto;
  gap: 8px;
  padding: 28px 32px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-lg, 12px);
  background: var(--surface);
}
.empty-hint.is-card .eh-icon { width: 38px; height: 38px; border-radius: 10px; margin-bottom: 4px; }
.empty-hint.is-card .eh-icon :deep(svg) { width: 19px; height: 19px; }
.empty-hint.is-card .eh-title { margin: 0; }
.empty-hint.is-card .eh-body { max-width: 360px; }
.empty-hint.is-card .eh-action { margin-top: var(--s-2, 8px); }
</style>
