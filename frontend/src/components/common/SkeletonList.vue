<template>
  <!-- 统一骨架语言：卡片轮廓+呼吸条（对齐个人版 gen-skeleton 视觉），仅在"加载中且无在列数据"时由父级渲染 -->
  <div class="sk-list" :style="{ '--sk-gap': gap }" role="status" aria-busy="true" :aria-label="label">
    <div v-for="i in rows" :key="i" class="sk-card" :style="{ animationDelay: `${(i - 1) * 70}ms` }">
      <div class="sk-bar is-title"></div>
      <div class="sk-bar is-meta"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * SkeletonList — 企业列表加载骨架（B3 版式找回）
 *
 * 消费方：ContextsView（私有/团队两态）、TeamDecisionsView、ChangesView。
 * 纯呈现组件零数据依赖；颜色全走主题变量，个人形态不消费（不导入=不进个人包）。
 */
withDefaults(defineProps<{
  rows?: number
  gap?: string
  label?: string
}>(), {
  rows: 4,
  gap: '10px',
  label: 'loading',
})
</script>

<style scoped>
.sk-list { display: flex; flex-direction: column; gap: var(--sk-gap, 10px); }
.sk-card {
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e2e2de);
  border-radius: var(--radius-sm, 8px);
  padding: var(--s-3, 16px);
  display: flex; flex-direction: column; gap: 10px;
  animation: sk-fade-in 0.3s ease both;
}
.sk-bar {
  height: 12px; border-radius: 6px;
  background: linear-gradient(90deg, var(--surface-2, #f0f0ee) 25%, var(--border, #e6e6e2) 50%, var(--surface-2, #f0f0ee) 75%);
  background-size: 200% 100%;
  animation: sk-shimmer 1.4s ease-in-out infinite;
}
.sk-bar.is-title { width: 55%; height: 14px; }
.sk-bar.is-meta { width: 32%; }
@keyframes sk-shimmer { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }
@keyframes sk-fade-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) {
  .sk-card, .sk-bar { animation: none; }
}
</style>
