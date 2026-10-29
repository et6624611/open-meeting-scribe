<script setup lang="ts">
/**
 * §7 锁定文案块渲染组件（QA B5 断言基准）
 * 登录页隐私说明 / Settings「数据位置」三行表 / 上传知情同意卡正文 三处共用本组件，
 * 保证逐字一致；文案唯一来源是 constants/lockedCopy.ts（规格 §7），任何表面禁止手抄。
 */
import { LOCKED_PRIVACY_LINES } from '@/constants/lockedCopy'
</script>

<template>
  <ul class="locked-privacy" aria-label="数据位置承诺">
    <li v-for="(line, i) in LOCKED_PRIVACY_LINES" :key="i">{{ line }}</li>
  </ul>
</template>

<style scoped>
.locked-privacy {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--s-2, 8px);
}
.locked-privacy li {
  position: relative;
  padding-left: 18px;
  font-size: var(--fs-12, 12px);
  line-height: 1.6;
  color: var(--muted, #666);
}
.locked-privacy li::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 7px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent, #4a7);
  opacity: 0.7;
}
</style>
