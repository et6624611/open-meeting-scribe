<template>
  <!-- 控制区：Tab / Control zone: Tabs -->
  <div class="gen-control-zone">
    <div class="gen-tabs-group">
      <div class="gen-tabs" id="genTabsContainer">
        <button v-for="tab in tabs" :key="tab.id" class="gen-tab" :class="{ 'is-active': activeTab === tab.id }" :title="tab.label" @click="$emit('switch-tab', tab.id)" @mouseenter="$emit('tab-hover', tab.id)">
          <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" v-html="tab.icon"></svg>
          <span class="tab-label">{{ tab.label }}</span>
          <span class="tab-dot" :class="tabDotClass(tab.id)"></span>
        </button>
      </div>
    </div>
    <!-- 原文三层视图下拉（仅原文 tab 显示；替代原面板内固定分段控件）/ Transcript layer dropdown (transcript tab only; replaces the in-panel segmented control) -->
    <div class="gen-layer-picker" v-if="activeTab === 'transcript'">
      <button
        ref="layerPickerBtn" class="gen-layer-trigger" v-bind="layerPickerTriggerAttrs"
        :aria-label="t('generating.layer.picker_label')" :title="t('generating.layer.picker_label')"
        @click="$emit('toggle-layer-picker')"
      >
        <span>{{ t(`generating.layer.${layerView}`) }}</span>
        <span v-if="layerView === 'formal'" class="rec-layer-ai">AI</span>
        <svg class="gen-layer-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
      <div ref="layerPickerMenu" class="gen-toolbar-more-menu gen-layer-menu" v-bind="layerPickerMenuAttrs" :class="{ 'is-open': showLayerPicker }" :aria-label="t('generating.layer.picker_label')">
        <button class="gen-toolbar-more-item" :class="{ 'is-selected': layerView === 'formal' }" role="menuitem" @click="$emit('select-layer', 'formal')">
          {{ t('generating.layer.formal') }}
          <span class="rec-layer-ai">AI</span>
        </button>
        <button class="gen-toolbar-more-item" :class="{ 'is-selected': layerView === 'clean' }" role="menuitem" :disabled="!cleanupAvailable" @click="$emit('select-layer', 'clean')">
          {{ t('generating.layer.clean') }}
        </button>
        <button class="gen-toolbar-more-item" :class="{ 'is-selected': layerView === 'raw' }" role="menuitem" @click="$emit('select-layer', 'raw')">
          {{ t('generating.layer.raw') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { LayerView } from '@/utils/transcriptLayers'

const { t } = useI18n()

interface Tab {
  id: string
  label: string
  icon: string
}

defineProps<{
  tabs: Tab[]
  activeTab: string
  tabDotClass: (tabId: string) => string
  layerView: LayerView
  cleanupAvailable: boolean
  showLayerPicker: boolean
  layerPickerTriggerAttrs: Record<string, unknown>
  layerPickerMenuAttrs: Record<string, unknown>
}>()

defineEmits<{
  'switch-tab': [tabId: string]
  'tab-hover': [tabId: string]
  'toggle-layer-picker': []
  'select-layer': [layer: LayerView]
}>()

defineExpose<{
  layerPickerBtn: HTMLElement | null
  layerPickerMenu: HTMLElement | null
}>()
</script>
