<template>
  <div
    class="ai-insights-settings"
    :class="{ 'is-open': isOpen }"
  >
    <!-- 消息类别 / Message categories -->
    <div class="ai-ps-section">
      <div class="ai-ps-section-title">{{ t('ai-panel.insights.settings_section_categories') }}</div>
      <div class="ai-ps-checkboxes">
        <div v-for="cat in categoryList" :key="cat.key" class="ai-ps-category-row">
          <label class="ai-ps-checkbox">
            <input type="checkbox" :checked="config.categories[cat.key]" @change="onCategoryToggle(cat.key, ($event.target as HTMLInputElement).checked)" />
            <span>{{ cat.label }}</span>
          </label>
          <button
            class="ai-ps-info-btn"
            :class="{ 'is-active': expandedInfo === cat.key }"
            :title="t('ai-panel.insights.info_tooltip')"
            :aria-label="t('ai-panel.insights.info_tooltip')"
            @click="expandedInfo = expandedInfo === cat.key ? '' : cat.key"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
          </button>
          <!-- 扫描频率选择器（仅类别开启时显示） / Scan frequency selector (only when category is enabled) -->
          <div v-if="config.categories[cat.key]" class="ai-ps-scan-freq">
            <span class="ai-ps-scan-freq-label">{{ t('ai-panel.insights.scan_interval') }}</span>
            <select
              class="ai-ps-scan-freq-select"
              :value="config.scanIntervals[cat.key] ?? 5"
              @change="onScanIntervalChange(cat.key, Number(($event.target as HTMLSelectElement).value))"
            >
              <option v-for="opt in scanIntervalOptions" :key="opt" :value="opt">{{ opt }} {{ t('ai-panel.insights.scan_interval_unit') }}</option>
            </select>
          </div>
          <div v-if="expandedInfo === cat.key" class="ai-ps-info-panel">
            <div class="ai-ps-info-block">
              <span class="ai-ps-info-label">{{ t('ai-panel.insights.info_what') }}</span>
              <span class="ai-ps-info-text">{{ cat.descWhat }}</span>
            </div>
            <div class="ai-ps-info-block">
              <span class="ai-ps-info-label">{{ t('ai-panel.insights.info_trigger') }}</span>
              <span class="ai-ps-info-text">{{ cat.descTrigger }}</span>
            </div>
            <div class="ai-ps-info-block">
              <span class="ai-ps-info-label">{{ t('ai-panel.insights.info_how') }}</span>
              <span class="ai-ps-info-text">{{ cat.descHow }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <!-- 触发灵敏度 / Trigger sensitivity -->
    <div class="ai-ps-section">
      <div class="ai-ps-section-title">{{ t('ai-panel.insights.settings_section_sensitivity') }}</div>
      <div class="ai-ps-sliders">
        <div class="ai-ps-slider-row">
          <span class="ai-ps-slider-label">{{ t('ai-panel.insights.sensitivity_idle') }}</span>
          <div class="ai-ps-slider-wrap">
            <input type="range" min="5" max="60" step="5" :value="config.sensitivity.idleMinutes" @input="onSensitivityChange('idleMinutes', Number(($event.target as HTMLInputElement).value))" />
            <span class="ai-ps-slider-value">{{ config.sensitivity.idleMinutes }} {{ t('ai-panel.insights.sensitivity_idle_unit') }}</span>
          </div>
        </div>
        <div class="ai-ps-slider-row">
          <span class="ai-ps-slider-label">{{ t('ai-panel.insights.sensitivity_insight') }}</span>
          <div class="ai-ps-slider-wrap">
            <input type="range" min="20" max="80" step="5" :value="config.sensitivity.insightThreshold" @input="onSensitivityChange('insightThreshold', Number(($event.target as HTMLInputElement).value))" />
            <span class="ai-ps-slider-value">{{ config.sensitivity.insightThreshold }}{{ t('ai-panel.insights.sensitivity_insight_unit') }}</span>
          </div>
        </div>
        <div class="ai-ps-slider-row">
          <span class="ai-ps-slider-label">{{ t('ai-panel.insights.sensitivity_cooldown') }}</span>
          <div class="ai-ps-slider-wrap">
            <input type="range" min="10" max="120" step="10" :value="config.sensitivity.cooldownMinutes" @input="onSensitivityChange('cooldownMinutes', Number(($event.target as HTMLInputElement).value))" />
            <span class="ai-ps-slider-value">{{ config.sensitivity.cooldownMinutes }} {{ t('ai-panel.insights.sensitivity_cooldown_unit') }}</span>
          </div>
        </div>
        <div class="ai-ps-slider-row">
          <span class="ai-ps-slider-label">{{ t('ai-panel.insights.sensitivity_session_max') }}</span>
          <div class="ai-ps-slider-wrap">
            <input type="range" min="1" max="10" step="1" :value="config.sensitivity.sessionMax" @input="onSensitivityChange('sessionMax', Number(($event.target as HTMLInputElement).value))" />
            <span class="ai-ps-slider-value">{{ config.sensitivity.sessionMax }} {{ t('ai-panel.insights.sensitivity_session_max_unit') }}</span>
          </div>
        </div>
      </div>
    </div>
    <!-- 通知方式 / Notification methods -->
    <div class="ai-ps-section">
      <div class="ai-ps-section-title">{{ t('ai-panel.insights.settings_section_notifications') }}</div>
      <div class="ai-ps-checkboxes">
        <label class="ai-ps-checkbox">
          <input type="checkbox" :checked="config.notifications.sidebarIndicator" @change="onNotifToggle('sidebarIndicator', ($event.target as HTMLInputElement).checked)" />
          <span>{{ t('ai-panel.insights.notif_sidebar') }}</span>
        </label>
        <label class="ai-ps-checkbox">
          <input type="checkbox" :checked="config.notifications.breathing" @change="onNotifToggle('breathing', ($event.target as HTMLInputElement).checked)" />
          <span>{{ t('ai-panel.insights.notif_breathing') }}</span>
        </label>
        <label class="ai-ps-checkbox">
          <input type="checkbox" :checked="config.notifications.banner" @change="onNotifToggle('banner', ($event.target as HTMLInputElement).checked)" />
          <span>{{ t('ai-panel.insights.notif_banner') }}</span>
        </label>
        <label class="ai-ps-checkbox">
          <input type="checkbox" :checked="config.notifications.autoExpand" @change="onNotifToggle('autoExpand', ($event.target as HTMLInputElement).checked)" />
          <span>{{ t('ai-panel.insights.notif_auto_expand') }}</span>
        </label>
      </div>
    </div>
    <!-- 免打扰 / Do not disturb -->
    <div class="ai-ps-section">
      <div class="ai-ps-section-title">{{ t('ai-panel.insights.settings_section_dnd') }}</div>
      <label class="ai-ps-checkbox ai-ps-dnd-toggle">
        <input type="checkbox" :checked="config.dnd.enabled" @change="onDndToggle(($event.target as HTMLInputElement).checked)" />
        <span>{{ t('ai-panel.insights.dnd_toggle') }}</span>
      </label>
      <div v-if="config.dnd.enabled" class="ai-ps-dnd-time">
        <span>{{ t('ai-panel.insights.dnd_from') }}</span>
        <select :value="config.dnd.startHour" @change="onDndTimeChange('startHour', Number(($event.target as HTMLSelectElement).value))">
          <option v-for="h in 24" :key="h-1" :value="h-1">{{ String(h-1).padStart(2,'0') }}:00</option>
        </select>
        <span>{{ t('ai-panel.insights.dnd_to') }}</span>
        <select :value="config.dnd.endHour" @change="onDndTimeChange('endHour', Number(($event.target as HTMLSelectElement).value))">
          <option v-for="h in 24" :key="h-1" :value="h-1">{{ String(h-1).padStart(2,'0') }}:00</option>
        </select>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'

const { t } = useI18n()

/** 当前展开说明的类别 key（空字符串表示全部收起） / Currently expanded info category key (empty string = all collapsed) */
const expandedInfo = ref('')

defineProps<{
  config: {
    categories: Record<string, boolean>
    scanIntervals: Record<string, number>
    sensitivity: Record<string, number>
    notifications: Record<string, boolean>
    dnd: { enabled: boolean; startHour: number; endHour: number }
  }
  isOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'categoryToggle', key: string, val: boolean): void
  (e: 'scanIntervalChange', key: string, val: number): void
  (e: 'sensitivityChange', field: string, val: number): void
  (e: 'notifToggle', field: string, val: boolean): void
  (e: 'dndToggle', val: boolean): void
  (e: 'dndTimeChange', field: 'startHour' | 'endHour', val: number): void
}>()

const categoryList = computed(() => [
  {
    key: 'context',
    label: t('ai-panel.insights.cat_context_label'),
    descWhat: t('ai-panel.insights.cat_context_desc_what'),
    descTrigger: t('ai-panel.insights.cat_context_desc_trigger'),
    descHow: t('ai-panel.insights.cat_context_desc_how'),
  },
  {
    key: 'blindspot',
    label: t('ai-panel.insights.cat_blindspot_label'),
    descWhat: t('ai-panel.insights.cat_blindspot_desc_what'),
    descTrigger: t('ai-panel.insights.cat_blindspot_desc_trigger'),
    descHow: t('ai-panel.insights.cat_blindspot_desc_how'),
  },
  {
    key: 'consensus',
    label: t('ai-panel.insights.cat_consensus_label'),
    descWhat: t('ai-panel.insights.cat_consensus_desc_what'),
    descTrigger: t('ai-panel.insights.cat_consensus_desc_trigger'),
    descHow: t('ai-panel.insights.cat_consensus_desc_how'),
  },
])

function onCategoryToggle(key: string, val: boolean) { emit('categoryToggle', key, val) }
function onScanIntervalChange(key: string, val: number) { emit('scanIntervalChange', key, val) }
function onSensitivityChange(field: string, val: number) { emit('sensitivityChange', field, val) }
function onNotifToggle(field: string, val: boolean) { emit('notifToggle', field, val) }
function onDndToggle(val: boolean) { emit('dndToggle', val) }
function onDndTimeChange(field: 'startHour' | 'endHour', val: number) { emit('dndTimeChange', field, val) }

/** 扫描频率可选项（分钟） / Scan interval options (minutes) */
const scanIntervalOptions = [1, 2, 3, 5, 10, 15, 30]
</script>
