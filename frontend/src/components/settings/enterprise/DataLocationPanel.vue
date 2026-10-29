<script setup lang="ts">
/**
 * 数据位置只读说明（UI 规格 §2 分区 B，档⑦）——P0 隐私指示核心。
 * 图标化三行表 + §7 锁定三行原文（经 LockedPrivacyBlock 单源）；只读无开关（P0 上云行为不可关闭）。
 */
import { useI18n } from 'vue-i18n'
import LockedPrivacyBlock from '@/components/common/LockedPrivacyBlock.vue'

const { t } = useI18n()
</script>

<template>
  <div class="dl-root">
    <h2>{{ t('enterprise.settings.data_location.title') }}</h2>
    <table class="dl-table">
      <thead>
        <tr>
          <th>{{ t('enterprise.settings.data_location.col_content') }}</th>
          <th>{{ t('enterprise.settings.data_location.col_location') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>
            <svg class="dl-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
            {{ t('enterprise.settings.data_location.row1_content') }}
          </td>
          <td class="is-local">{{ t('enterprise.settings.data_location.row1_location') }}</td>
        </tr>
        <tr>
          <td>
            <svg class="dl-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
            {{ t('enterprise.settings.data_location.row2_content') }}
          </td>
          <td class="is-local">{{ t('enterprise.settings.data_location.row2_location') }}</td>
        </tr>
        <tr>
          <td>
            <svg class="dl-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            {{ t('enterprise.settings.data_location.row3_content') }}
          </td>
          <td class="is-server">{{ t('enterprise.settings.data_location.row3_location') }}</td>
        </tr>
      </tbody>
    </table>
    <LockedPrivacyBlock />
    <p class="dl-hint">{{ t('enterprise.settings.data_location.readonly_hint') }}</p>
  </div>
</template>

<style scoped>
.dl-root { display: flex; flex-direction: column; gap: var(--s-3, 16px); max-width: 640px; }
.dl-root h2 { font-size: 15px; margin: 0; }
.dl-table { width: 100%; border-collapse: collapse; background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); font-size: var(--fs-12, 12px); overflow: hidden; }
.dl-table th, .dl-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border, #eee); }
.dl-table th { color: var(--muted, #666); font-weight: 500; }
.dl-icon { width: 13px; height: 13px; vertical-align: -2px; margin-right: 6px; color: var(--subtle, #999); }
.dl-table td.is-local { color: var(--accent, #2a6); font-weight: 600; }
.dl-table td.is-server { color: var(--fg, #222); font-weight: 600; }
.dl-hint { font-size: var(--fs-11, 11px); color: var(--subtle, #999); margin: 0; }
</style>
