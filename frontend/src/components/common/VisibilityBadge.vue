<script setup lang="ts">
/**
 * 数据位置徽标（UI 规格 §5）——P0 唯一实际态"个人"。
 * 规则：徽标是数据属性的展示，不是导航分类；P0 界面不出现"团队/企业"任何文字。
 * 三态样式一次定义（team/enterprise 预留类不渲染），接口 visibility 字段单源驱动。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Visibility } from '@/api/context'

const props = defineProps<{ visibility: Visibility }>()
const { t } = useI18n()
// P1-WP-3 三态落地：personal=仅你可见 / team=团队可见（企业档无 UI 面——资产层零暴露红线，枚举不引入第三值）
const label = computed(() =>
  props.visibility === 'team' ? t('enterprise.settings.badge.team') : t('enterprise.settings.badge.personal'),
)
</script>

<template>
  <span class="vis-badge" :class="'is-' + (visibility || 'personal')">
    <svg class="vis-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <rect x="5" y="11" width="14" height="9" rx="2"/>
      <path d="M8 11V7a4 4 0 0 1 8 0v4"/>
    </svg>
    {{ label }}
  </span>
</template>

<style scoped>
.vis-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: var(--fs-11, 11px);
  background: var(--surface-2, #f2f2f0);
  color: var(--muted, #666);
  border: 1px solid var(--border, #e6e6e2);
}
.vis-icon { width: 11px; height: 11px; }
/* P1/P2 预留样式（不渲染内容，仅样式钩子）： */
.vis-badge.is-team { color: var(--accent, #2a6); }
.vis-badge.is-enterprise { color: var(--accent-mid, #4a7); }
</style>
