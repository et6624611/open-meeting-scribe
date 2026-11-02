<script setup lang="ts">
/**
 * 企业版设置页（UI 规格 §2 两分区，档⑦）
 *
 * 企业形态不复用个人版 SettingsView：账户/算力四段依赖个人云端点（企业实例不挂载，契约 §4），
 * AI 能力由管理员管理台控制、员工端无开关。P0 员工 Settings=本机录音助手 / 数据位置两分区；
 * B6 版式找回追加第三分区"外观"（主题/语言=设备偏好，零上服务端、不入团队，与两分区裁决兼容）。
 * 深链 ?cat=assistant|data_location|appearance（头像菜单"我的数据在哪"→ data_location）。
 */
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { usePageBack } from '@/composables/usePageBack'
import EnterpriseAssistantPanel from '@/components/settings/enterprise/EnterpriseAssistantPanel.vue'
import DataLocationPanel from '@/components/settings/enterprise/DataLocationPanel.vue'
import EnterpriseAppearancePanel from '@/components/settings/enterprise/EnterpriseAppearancePanel.vue'

const { t } = useI18n()
const route = useRoute()
const { goBack } = usePageBack()

const CATS = ['assistant', 'appearance', 'data_location'] as const
const raw = typeof route.query.cat === 'string' ? route.query.cat : ''
const activeCategory = ref<string>(CATS.includes(raw as typeof CATS[number]) ? raw : 'assistant')
</script>

<template>
  <div class="es-layout">
    <nav class="es-nav">
      <button class="page-back-btn" @click="goBack">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        <span>{{ t('common.action.back') }}</span>
      </button>
      <h1 class="es-nav-title">{{ t('settings.title') }}</h1>
      <button class="es-nav-item" :class="{ 'is-active': activeCategory === 'assistant' }" @click="activeCategory = 'assistant'">
        {{ t('enterprise.settings.nav.assistant') }}
      </button>
      <button class="es-nav-item" :class="{ 'is-active': activeCategory === 'appearance' }" @click="activeCategory = 'appearance'">
        {{ t('enterprise.settings.nav.appearance') }}
      </button>
      <button class="es-nav-item" :class="{ 'is-active': activeCategory === 'data_location' }" @click="activeCategory = 'data_location'">
        {{ t('enterprise.settings.nav.data_location') }}
      </button>
    </nav>
    <div class="es-content">
      <EnterpriseAssistantPanel v-show="activeCategory === 'assistant'" />
      <EnterpriseAppearancePanel v-show="activeCategory === 'appearance'" />
      <DataLocationPanel v-show="activeCategory === 'data_location'" />
    </div>
  </div>
</template>

<style scoped>
.es-layout { display: flex; height: 100%; min-height: 0; }
.es-nav { width: 240px; flex: none; padding: var(--s-3, 16px); border-right: 1px solid var(--border, #e6e6e2); display: flex; flex-direction: column; gap: 4px; overflow: auto; }
.es-nav-title { font-size: 15px; margin: var(--s-3, 16px) 0 var(--s-2, 8px); }
.es-nav-item { padding: 9px 12px; border: none; border-radius: var(--radius-sm, 8px); background: none; text-align: left; cursor: pointer; font-size: var(--fs-12, 12px); color: var(--fg, #222); }
.es-nav-item:hover { background: var(--surface-2, #fafaf8); }
.es-nav-item.is-active { background: var(--surface-2, #f0f0ee); font-weight: 600; }
.es-content { flex: 1; padding: calc(var(--s-3, 16px) * 2); overflow: auto; }
</style>
