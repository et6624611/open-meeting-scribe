<template>
  <span class="playing-eq" :class="{ 'is-paused': !playing }" role="img" :aria-label="playing ? t('common.playing') : t('common.paused')">
    <span class="pe-bar"></span>
    <span class="pe-bar"></span>
    <span class="pe-bar"></span>
  </span>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
defineProps<{ playing?: boolean }>()
</script>

<style scoped>
.playing-eq {
  display: inline-flex;
  align-items: flex-end;
  gap: 2px;
  height: 12px;
  flex-shrink: 0;
}
.playing-eq .pe-bar {
  width: 2.5px;
  height: 100%;
  background: currentColor;
  border-radius: 2px;
  transform-origin: bottom;
  animation: pe-bar 0.9s ease-in-out infinite;
}
.playing-eq .pe-bar:nth-child(1) { animation-duration: 0.7s; }
.playing-eq .pe-bar:nth-child(2) { animation-duration: 0.95s; animation-delay: 0.12s; }
.playing-eq .pe-bar:nth-child(3) { animation-duration: 0.8s; animation-delay: 0.22s; }
.playing-eq.is-paused .pe-bar {
  animation-play-state: paused;
  transform: scaleY(0.4);
  opacity: 0.55;
}
@keyframes pe-bar {
  0%, 100% { transform: scaleY(0.35); }
  50% { transform: scaleY(1); }
}
</style>
