<template>
  <div class="sc-picker-wrap">
    <!-- 顶部「当前使用的算力来源」选择器 / Current-source picker -->
    <div class="sc-source-picker">
      <div class="sc-sp-row">
        <span class="sc-sp-label">{{ label }}</span>
        <select class="sc-sp-select" :value="activeKey" :aria-label="label" @change="onSelect">
          <option v-for="s in sources" :key="s.key" :value="s.key">{{ s.idx }} {{ s.name }}</option>
        </select>
        <span class="sc-sp-state">
          <span class="sc-pill" :class="activeStateTone === 'warn' ? 'sc-pill-warn' : 'sc-pill-accent'"><span class="sc-dot"></span>{{ activeStateText || t('settings.compute.effective') }}</span>
          <span class="sc-sp-meta">{{ activeMeta }}</span>
        </span>
      </div>
      <p v-if="hint" class="sc-sp-hint">{{ hint }}</p>
    </div>

    <!-- 编号 Tab 栏 / Numbered source tabs -->
    <div class="sc-tablist" role="tablist" :aria-label="label">
      <button
        v-for="s in sources"
        :key="s.key"
        class="sc-tab"
        :class="{ 'is-active': s.key === viewKey, 'is-live': s.key === activeKey, 'is-ready': s.ready && s.key !== activeKey, 'is-down': !s.ready && s.key !== activeKey }"
        role="tab"
        :aria-selected="s.key === viewKey"
        :title="s.key === activeKey ? t('settings.compute.effective') : (s.ready ? t('settings.compute.state_ready') : t('settings.compute.state_down'))"
        @click="emit('view', s.key)"
      >
        <span class="sc-tab-idx">{{ s.idx }}</span>
        <span class="sc-tab-name">{{ s.name }}</span>
        <span class="sc-tab-dot"></span>
      </button>
    </div>

    <!-- 颜色图例（状态不只靠颜色，色+文双通道） / Color legend: state conveyed by color + text -->
    <div class="sc-legend">
      <span class="sc-lg-item"><i class="sc-lg-dot live"></i>{{ t('settings.compute.effective') }}</span>
      <span class="sc-lg-item"><i class="sc-lg-dot ok"></i>{{ t('settings.compute.state_ready') }}</span>
      <span class="sc-lg-item"><i class="sc-lg-dot down"></i>{{ t('settings.compute.state_down') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 算力来源选择器 + 编号 Tab 栏（可复用）。
 * - 顶部下拉「选择即生效」：emit('activate', key)，由父级判定就绪/引导。
 * - Tab 仅切换查看：emit('view', key)。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

export interface SourceItem {
  key: string
  idx: string
  name: string
  ready: boolean
  meta?: string
}

const props = defineProps<{
  label: string
  sources: SourceItem[]
  activeKey: string
  viewKey: string
  hint?: string
  /** 当前生效来头的语气覆盖（如 trial 未登录 → warn） / Header pill tone override */
  activeStateTone?: 'live' | 'warn'
  /** 当前生效来头的文案覆盖（缺省为「生效中」） / Header pill text override */
  activeStateText?: string
}>()

const emit = defineEmits<{
  (e: 'activate', key: string): void
  (e: 'view', key: string): void
}>()

const { t } = useI18n()

const activeMeta = computed(() => props.sources.find(s => s.key === props.activeKey)?.meta || '')

function onSelect(e: Event) {
  const val = (e.target as HTMLSelectElement).value
  emit('activate', val)
}
</script>

<style scoped>
.sc-picker-wrap { display: flex; flex-direction: column; }

/* 来源选择器 */
.sc-source-picker { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--s-3) var(--s-4); margin-bottom: var(--s-4); }
.sc-sp-row { display: flex; align-items: center; gap: var(--s-3); flex-wrap: wrap; }
.sc-sp-label { font-size: 13px; font-weight: 600; color: var(--fg); }
.sc-sp-select { width: auto; min-width: 190px; height: 34px; font-size: 13px; padding: 0 var(--s-3); background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--fg); }
.sc-sp-select:focus { outline: none; border-color: var(--accent); }
.sc-sp-state { display: inline-flex; align-items: center; gap: var(--s-2); font-size: 12px; color: var(--muted); }
.sc-sp-meta { font-family: var(--font-mono); color: var(--muted); }
.sc-sp-hint { margin-top: var(--s-2); font-size: 12px; color: var(--warn); font-weight: 500; }

/* 编号 Tab */
.sc-tablist { display: flex; gap: var(--s-1); border-bottom: 1px solid var(--border); margin-bottom: var(--s-5); overflow-x: auto; }
.sc-tab { position: relative; flex: 0 0 auto; display: inline-flex; align-items: center; gap: 8px; height: 38px; padding: 0 14px; border: none; background: transparent; color: var(--muted); border-radius: var(--radius-sm) var(--radius-sm) 0 0; cursor: pointer; }
.sc-tab:hover { background: var(--surface-2); color: var(--fg); }
.sc-tab.is-active { color: var(--fg); font-weight: 600; }
.sc-tab.is-active::after { content: ""; position: absolute; left: var(--s-3); right: var(--s-3); bottom: -1px; height: 2px; background: var(--accent); border-radius: 2px; }
.sc-tab-idx { font-family: var(--font-mono); font-size: 10px; color: var(--subtle); letter-spacing: 0.06em; }
.sc-tab-name { font-size: 13px; color: var(--muted); white-space: nowrap; }
.sc-tab.is-active .sc-tab-name { color: var(--fg); }
.sc-tab-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--border-strong); }
.sc-tab.is-live .sc-tab-dot { background: var(--accent); }
.sc-tab.is-ready .sc-tab-dot { background: var(--ok); }
.sc-tab.is-down .sc-tab-dot { background: var(--warn); }

/* 状态 pill */
.sc-pill { display: inline-flex; align-items: center; gap: 5px; font-family: var(--font-mono); font-size: 11px; border-radius: 5px; padding: 2px 7px; border: 1px solid var(--border-strong); color: var(--muted); background: var(--surface-2); white-space: nowrap; }
.sc-pill .sc-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.sc-pill-accent { color: var(--accent); background: var(--accent-soft); border-color: transparent; }
.sc-pill-warn { color: var(--warn); background: var(--warn-soft); border-color: transparent; }

/* 颜色图例 */
.sc-legend { display: flex; gap: var(--s-4); margin: calc(var(--s-1) * -1) 0 var(--s-4); font-size: 11px; color: var(--subtle); }
.sc-lg-item { display: inline-flex; align-items: center; gap: 5px; }
.sc-lg-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.sc-lg-dot.live { background: var(--accent); }
.sc-lg-dot.ok { background: var(--ok); }
.sc-lg-dot.down { background: var(--warn); }
</style>
