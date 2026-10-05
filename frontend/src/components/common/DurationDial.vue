<template>
  <span class="dur-dial" role="img" :aria-label="t('common.duration.aria_label', { text })">
    <svg
      v-for="(seg, i) in segments"
      :key="i"
      class="dd-svg"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      aria-hidden="true"
    >
      <circle v-if="seg.full" cx="8" cy="8" r="7" class="dd-full" />
      <template v-else>
        <circle cx="8" cy="8" r="7" class="dd-track" />
        <path :d="seg.path" class="dd-part" />
      </template>
    </svg>
    <span class="dd-text">{{ text }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const props = defineProps<{ seconds: number }>()

const minutes = computed(() => Math.round(props.seconds / 60))
const hours = computed(() => Math.floor(minutes.value / 60))
const mins = computed(() => minutes.value % 60)

const text = computed(() => {
  const m = minutes.value
  if (m <= 0) return t('common.duration.zero')
  const h = hours.value
  const r = mins.value
  if (h === 0) return t('common.duration.minutes', { m: r })
  if (r === 0) return t('common.duration.hours', { h })
  return t('common.duration.hours_minutes', { h, m: r })
})

// 实心盘 = 1 小时，余数分钟为扇形盘；超过 3 小时封顶，由数字标注表达精确时长 / Solid dial = 1 hour, remainder minutes as pie sector; capped at 3 hours, exact duration shown as text
const segments = computed(() => {
  const list: Array<{ full: boolean; path: string }> = []
  for (let i = 0; i < Math.min(hours.value, 3); i++) {
    list.push({ full: true, path: '' })
  }
  if (mins.value > 0) list.push({ full: false, path: piePath(mins.value) })
  return list
})

function piePath(m: number): string {
  const angle = (m / 60) * 360
  const rad = ((angle - 90) * Math.PI) / 180
  const x = +(8 + 7 * Math.cos(rad)).toFixed(2)
  const y = +(8 + 7 * Math.sin(rad)).toFixed(2)
  const largeArc = angle > 180 ? 1 : 0
  return `M 8 8 L 8 1 A 7 7 0 ${largeArc} 1 ${x} ${y} Z`
}
</script>

<style scoped>
.dur-dial {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.dur-dial .dd-svg { display: block; }
.dur-dial .dd-full { fill: var(--fg); opacity: 0.85; }
.dur-dial .dd-track { fill: none; stroke: var(--border); stroke-width: 1; }
.dur-dial .dd-part { fill: var(--fg); opacity: 0.85; }
.dur-dial .dd-text {
  margin-left: 4px;
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1;
  color: var(--subtle);
  white-space: nowrap;
}
</style>
