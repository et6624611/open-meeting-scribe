<script setup lang="ts">
/**
 * 企业版顶部状态横幅（UI 规格 §1/§3 + 裁决④）：
 * 服务暂停常驻横幅（读放行/写拒绝的全局告知）+ "X 条文字待同步到公司服务器"（队列侧数据源）。
 * 文案为辅助口径（非 §7 锁定块）：待同步用中性提示，不用"上传失败"红色告警；error 才红色可重试。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useInstanceStore } from '@/stores/instance'
import { isEnterprise } from '@/edition'

const { t } = useI18n()
const instance = useInstanceStore()

const showPaused = computed(() => isEnterprise && !instance.serviceOpen)
const showPending = computed(() => isEnterprise && instance.pendingCount > 0 && instance.serviceOpen)
const showError = computed(() => isEnterprise && instance.hasError)
// D020 销项：契约句"AI 助手未开启，联系管理员"（enterprise.banner.ai_off）原为零消费孤儿键——
// info 未到达前不判（防启动瞬间误显）；服务开放但实例 AI 关闭时呈现
const showAiOff = computed(() => isEnterprise && !!instance.info && instance.serviceOpen && !instance.aiEnabled)
</script>

<template>
  <div v-if="showPaused" class="ent-banner is-paused" role="status">{{ t('enterprise.banner.service_paused') }}</div>
  <div v-else-if="showAiOff" class="ent-banner is-pending" role="status">{{ t('enterprise.banner.ai_off') }}</div>
  <div v-else-if="showError" class="ent-banner is-error" role="alert">{{ t('enterprise.banner.sync_error') }}</div>
  <div v-else-if="showPending" class="ent-banner is-pending" role="status">
    {{ t('enterprise.banner.sync_pending', { count: instance.pendingCount }) }}
  </div>
</template>

<style scoped>
.ent-banner {
  padding: 6px var(--s-3, 16px);
  text-align: center;
  font-size: var(--fs-12, 12px);
  line-height: 1.5;
}
.ent-banner.is-paused { background: color-mix(in srgb, var(--warn, #b60) 14%, var(--surface, #fff)); color: var(--fg, #222); }
.ent-banner.is-pending { background: color-mix(in srgb, var(--accent, #2a6) 10%, var(--surface, #fff)); color: var(--fg, #222); }
.ent-banner.is-error { background: color-mix(in srgb, var(--warn, #c33) 16%, var(--surface, #fff)); color: var(--fg, #222); }
</style>
