<script setup lang="ts">
/**
 * 企业版设置·外观分区（B6 版式找回，UI-RESTORE-INVENTORY）
 *
 * 主题与语言都是**设备偏好**（localStorage 现键 oms_theme/locale，零新增键、不入团队、不上服务端）——
 * 与"设置不进团队空间"裁决不冲突：本分区只出现在私有面设备设置里。
 * 视觉语言对齐个人版 SettingsView 外观段（theme-chip 悬停预览+移出恢复同款交互），复用同名 locale 键。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useThemeStore, THEMES } from '@/stores/theme'
import { getLocale, setI18nLocale, type SupportedLocale } from '@/i18n'

const { t } = useI18n()
const themeStore = useThemeStore()

const LANG_OPTIONS: { id: SupportedLocale; label: string }[] = [
  { id: 'zh-CN', label: '简体中文' },
  { id: 'en', label: 'English' },
]
const currentLocale = computed(() => getLocale())
async function onSwitchLang(locale: SupportedLocale) {
  await setI18nLocale(locale)
}
</script>

<template>
  <div class="eap-root">
    <h1 class="eap-page-title">{{ t('settings.cat_appearance') }}</h1>

    <!-- 主题 / Theme：悬停即全站预览，移出恢复——与个人版外观段同一交互语言 -->
    <section class="eap-section">
      <h2 class="eap-title">{{ t('settings.appearance') }}</h2>
      <div class="eap-grid" @mouseleave="themeStore.restoreTheme()">
        <button
          v-for="theme in THEMES"
          :key="theme.id"
          class="eap-chip"
          :class="{ 'is-active': themeStore.current === theme.id }"
          @mouseenter="themeStore.previewTheme(theme.id)"
          @focus="themeStore.previewTheme(theme.id)"
          @click="themeStore.setTheme(theme.id)"
        >{{ t(`common.theme.${theme.id.replace(/-/g, '_')}`) }}</button>
      </div>
    </section>

    <!-- 语言 / Language -->
    <section class="eap-section">
      <h2 class="eap-title">{{ t('settings.language') }}</h2>
      <p class="eap-desc">{{ t('settings.language_subtitle') }}</p>
      <div class="eap-grid">
        <button
          v-for="lang in LANG_OPTIONS"
          :key="lang.id"
          class="eap-chip"
          :class="{ 'is-active': currentLocale === lang.id }"
          @click="onSwitchLang(lang.id)"
        >{{ lang.label }}</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.eap-root { max-width: 640px; color: var(--fg, #222); }
.eap-page-title { font-size: 16px; margin: 0 0 var(--s-4, 20px); }
.eap-section { margin-bottom: var(--s-6, 28px); }
.eap-title { font-size: var(--fs-13, 13px); margin: 0 0 var(--s-2, 8px); }
.eap-desc { font-size: var(--fs-12, 12px); color: var(--muted, #666); margin: 0 0 var(--s-2, 8px); }
.eap-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.eap-chip { padding: 7px 16px; border: 1px solid var(--border, #d8d8d4); border-radius: 999px; background: var(--surface, #fff); color: var(--fg, #222); font-size: var(--fs-12, 12px); cursor: pointer; transition: border-color 0.15s ease, background 0.15s ease; }
.eap-chip:hover { border-color: var(--accent, #2a6); }
.eap-chip:focus-visible { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.eap-chip.is-active { background: var(--accent, #2a6); border-color: var(--accent, #2a6); color: var(--accent-fg, #fff); font-weight: 600; }
</style>
