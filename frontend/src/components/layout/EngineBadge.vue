<template>
  <button
    class="engine-badge"
    :class="`is-${engine.badge}`"
    :title="tipText"
    :aria-label="t('topbar.engine_badge_aria', { state: labelText })"
    @click="goEngineSettings"
  >
    <span class="eb-dot"></span>
    <span class="eb-label">{{ labelText }}</span>
  </button>
</template>

<script setup lang="ts">
/**
 * 全局引擎状态徽章（R6 / PRD-LOCAL-ENGINE）。
 * Global engine status badge (R6 / PRD-LOCAL-ENGINE).
 *
 * 四态：本地引擎 / 体验代理 / 自持 Key / 未就绪。
 * 双因子判定：settings.engine.mode + 本地引擎目录存在性（stores/engine.ts）。
 * Four states derived from two factors: engine mode + local engine directory presence.
 */
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useEngineStore } from '@/stores/engine'

const { t } = useI18n()
const router = useRouter()
const engine = useEngineStore()

const labelText = computed(() => t(`topbar.engine_badge_${engine.badge}`))
const tipText = computed(() => t(`topbar.engine_badge_tip_${engine.badge}`))

function goEngineSettings() {
  // A3：与底部状态栏统一跳转接入方式入口（?cat=access）
  router.push({ name: 'settings', query: { cat: 'access' } })
}

onMounted(() => {
  engine.load()
  void engine.loadRouting()  // 徽章第一因子=access_mode（stores/engine.ts 单源收敛）
})
</script>
