<template>
  <!-- 说话人绑定引导弹窗 -->
  <div v-if="modelValue" class="spk-onboarding-overlay" @click.self="emit('close')" @keydown.esc="emit('close')">
    <div class="spk-onboarding-card" role="dialog" aria-modal="true" aria-labelledby="obDialogTitle">
      <!-- 标题区 -->
      <div class="spk-ob-header">
        <h3 id="obDialogTitle">{{ t('generating.onboarding.title') }}</h3>
      </div>
      <!-- 数据变化演示区 -->
      <div class="spk-ob-demo">
        <div class="spk-ob-transcript">
          <div class="spk-ob-line" v-for="(line, i) in demoLines" :key="i" :class="{ 'is-me': line.isMe }">
            <div class="spk-ob-head">
              <span class="spk-ob-ts">{{ line.ts }}</span>
              <span class="spk-ob-spk" :class="line.bound ? 'bound' : 'unbound'" :style="line.bound ? { background: line.color } : {}">{{ line.bound ? line.name : line.label }}</span>
            </div>
            <div class="spk-ob-text" :class="line.bound ? 'bound' : 'unbound'">
              <div class="spk-ob-skeleton">
                <div class="spk-ob-skel-bar" :style="{ width: line.bar1 }"></div>
                <div class="spk-ob-skel-bar" :style="{ width: line.bar2 }"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <!-- 底部操作区 -->
      <div class="spk-ob-footer">
        <label class="spk-ob-dont-show">
          <input type="checkbox" v-model="dontShowAgain"> {{ t('generating.onboarding.dont_show_again') }}
        </label>
        <button type="button" class="spk-ob-got-it" @click="emit('close')">{{ t('generating.onboarding.start') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{
  modelValue: boolean
  demoLines: Array<{
    ts: string
    label: string
    name: string
    color: string
    bound: boolean
    isMe: boolean
    bar1: string
    bar2: string
  }>
}>()

const dontShowAgain = defineModel<boolean>('dontShowAgain', { default: false })

const emit = defineEmits<{
  (e: 'close'): void
}>()
</script>
