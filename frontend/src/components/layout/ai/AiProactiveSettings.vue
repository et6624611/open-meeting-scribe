<template>
  <div
    class="ai-proactive-settings"
    :class="{ 'is-open': isOpen }"
  >
    <!-- 消息类别 -->
    <div class="ai-ps-section">
      <div class="ai-ps-section-title">{{ t('ai-panel.proactive.settings_section_categories') }}</div>
      <div class="ai-ps-checkboxes">
        <label v-for="(label, key) in categoryLabels" :key="key" class="ai-ps-checkbox">
          <input type="checkbox" :checked="config.categories[key]" @change="onCategoryToggle(key, ($event.target as HTMLInputElement).checked)" />
          <span>{{ label }}</span>
        </label>
      </div>
    </div>
    <!-- 触发灵敏度 -->
    <div class="ai-ps-section">
      <div class="ai-ps-section-title">{{ t('ai-panel.proactive.settings_section_sensitivity') }}</div>
      <div class="ai-ps-sliders">
        <div class="ai-ps-slider-row">
          <span class="ai-ps-slider-label">{{ t('ai-panel.proactive.sensitivity_idle') }}</span>
          <div class="ai-ps-slider-wrap">
            <input type="range" min="5" max="60" step="5" :value="config.sensitivity.idleMinutes" @input="onSensitivityChange('idleMinutes', Number(($event.target as HTMLInputElement).value))" />
            <span class="ai-ps-slider-value">{{ config.sensitivity.idleMinutes }} {{ t('ai-panel.proactive.sensitivity_idle_unit') }}</span>
          </div>
        </div>
        <div class="ai-ps-slider-row">
          <span class="ai-ps-slider-label">{{ t('ai-panel.proactive.sensitivity_deviation') }}</span>
          <div class="ai-ps-slider-wrap">
            <input type="range" min="20" max="60" step="5" :value="config.sensitivity.deviationThreshold" @input="onSensitivityChange('deviationThreshold', Number(($event.target as HTMLInputElement).value))" />
            <span class="ai-ps-slider-value">{{ config.sensitivity.deviationThreshold }}{{ t('ai-panel.proactive.sensitivity_deviation_unit') }}</span>
          </div>
        </div>
        <div class="ai-ps-slider-row">
          <span class="ai-ps-slider-label">{{ t('ai-panel.proactive.sensitivity_cooldown') }}</span>
          <div class="ai-ps-slider-wrap">
            <input type="range" min="10" max="120" step="10" :value="config.sensitivity.cooldownMinutes" @input="onSensitivityChange('cooldownMinutes', Number(($event.target as HTMLInputElement).value))" />
            <span class="ai-ps-slider-value">{{ config.sensitivity.cooldownMinutes }} {{ t('ai-panel.proactive.sensitivity_cooldown_unit') }}</span>
          </div>
        </div>
        <div class="ai-ps-slider-row">
          <span class="ai-ps-slider-label">{{ t('ai-panel.proactive.sensitivity_session_max') }}</span>
          <div class="ai-ps-slider-wrap">
            <input type="range" min="1" max="10" step="1" :value="config.sensitivity.sessionMax" @input="onSensitivityChange('sessionMax', Number(($event.target as HTMLInputElement).value))" />
            <span class="ai-ps-slider-value">{{ config.sensitivity.sessionMax }} {{ t('ai-panel.proactive.sensitivity_session_max_unit') }}</span>
          </div>
        </div>
      </div>
    </div>
    <!-- 通知方式 -->
    <div class="ai-ps-section">
      <div class="ai-ps-section-title">{{ t('ai-panel.proactive.settings_section_notifications') }}</div>
      <div class="ai-ps-checkboxes">
        <label class="ai-ps-checkbox">
          <input type="checkbox" :checked="config.notifications.sidebarIndicator" @change="onNotifToggle('sidebarIndicator', ($event.target as HTMLInputElement).checked)" />
          <span>{{ t('ai-panel.proactive.notif_sidebar') }}</span>
        </label>
        <label class="ai-ps-checkbox">
          <input type="checkbox" :checked="config.notifications.breathing" @change="onNotifToggle('breathing', ($event.target as HTMLInputElement).checked)" />
          <span>{{ t('ai-panel.proactive.notif_breathing') }}</span>
        </label>
        <label class="ai-ps-checkbox">
          <input type="checkbox" :checked="config.notifications.banner" @change="onNotifToggle('banner', ($event.target as HTMLInputElement).checked)" />
          <span>{{ t('ai-panel.proactive.notif_banner') }}</span>
        </label>
        <label class="ai-ps-checkbox">
          <input type="checkbox" :checked="config.notifications.autoExpand" @change="onNotifToggle('autoExpand', ($event.target as HTMLInputElement).checked)" />
          <span>{{ t('ai-panel.proactive.notif_auto_expand') }}</span>
        </label>
      </div>
    </div>
    <!-- 免打扰 -->
    <div class="ai-ps-section">
      <div class="ai-ps-section-title">{{ t('ai-panel.proactive.settings_section_dnd') }}</div>
      <label class="ai-ps-checkbox ai-ps-dnd-toggle">
        <input type="checkbox" :checked="config.dnd.enabled" @change="onDndToggle(($event.target as HTMLInputElement).checked)" />
        <span>{{ t('ai-panel.proactive.dnd_toggle') }}</span>
      </label>
      <div v-if="config.dnd.enabled" class="ai-ps-dnd-time">
        <span>{{ t('ai-panel.proactive.dnd_from') }}</span>
        <select :value="config.dnd.startHour" @change="onDndTimeChange('startHour', Number(($event.target as HTMLSelectElement).value))">
          <option v-for="h in 24" :key="h-1" :value="h-1">{{ String(h-1).padStart(2,'0') }}:00</option>
        </select>
        <span>{{ t('ai-panel.proactive.dnd_to') }}</span>
        <select :value="config.dnd.endHour" @change="onDndTimeChange('endHour', Number(($event.target as HTMLSelectElement).value))">
          <option v-for="h in 24" :key="h-1" :value="h-1">{{ String(h-1).padStart(2,'0') }}:00</option>
        </select>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'

const { t } = useI18n()

defineProps<{
  config: {
    categories: Record<string, boolean>
    sensitivity: Record<string, number>
    notifications: Record<string, boolean>
    dnd: { enabled: boolean; startHour: number; endHour: number }
  }
  isOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'categoryToggle', key: string, val: boolean): void
  (e: 'sensitivityChange', field: string, val: number): void
  (e: 'notifToggle', field: string, val: boolean): void
  (e: 'dndToggle', val: boolean): void
  (e: 'dndTimeChange', field: 'startHour' | 'endHour', val: number): void
}>()

const categoryLabels = computed(() => ({
  deviation: t('ai-panel.proactive.cat_deviation_label'),
  contradiction: t('ai-panel.proactive.cat_contradiction_label'),
  missing_topic: t('ai-panel.proactive.cat_missing_topic_label'),
  todo_extract: t('ai-panel.proactive.cat_todo_extract_label'),
  summary_suggest: t('ai-panel.proactive.cat_summary_suggest_label'),
  stuck: t('ai-panel.proactive.cat_stuck_label'),
}))

function onCategoryToggle(key: string, val: boolean) { emit('categoryToggle', key, val) }
function onSensitivityChange(field: string, val: number) { emit('sensitivityChange', field, val) }
function onNotifToggle(field: string, val: boolean) { emit('notifToggle', field, val) }
function onDndToggle(val: boolean) { emit('dndToggle', val) }
function onDndTimeChange(field: 'startHour' | 'endHour', val: number) { emit('dndTimeChange', field, val) }
</script>
