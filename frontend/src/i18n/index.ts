/**
 * i18n 国际化模块 / i18n internationalization module
 *
 * 基于 vue-i18n v11，采用 Composition API 模式（legacy: false）。 / Based on vue-i18n v11, Composition API mode (legacy: false).
 * 默认语言 en 静态导入（零延迟），其他语言按需动态加载。 / Default language en statically imported (zero delay); other languages dynamically loaded on demand.
 */
import { createI18n, type Composer } from 'vue-i18n'
import { nextTick } from 'vue'

// ─── 静态导入默认语言（en）所有模块 ─── / ─── Static import of default language (en) modules ───
import enCommon from './locales/en/common.json'
import enRecording from './locales/en/recording.json'
import enStart from './locales/en/start.json'
import enProcessing from './locales/en/processing.json'
import enLibrary from './locales/en/library.json'
import enSpeakers from './locales/en/speakers.json'
import enHotwords from './locales/en/hotwords.json'
import enSettings from './locales/en/settings.json'
import enProjects from './locales/en/projects.json'
import enSidebar from './locales/en/sidebar.json'
import enTopbar from './locales/en/topbar.json'
import enGenerating from './locales/en/generating.json'
import enTask from './locales/en/task.json'
import enLogin from './locales/en/login.json'
import enAiPanel from './locales/en/ai-panel.json'
import enAgents from './locales/en/agents.json'
import enDecisions from './locales/en/decisions.json'

/** 合并所有模块的翻译结构（按模块名命名空间包裹，与组件 t('common.xxx') 调用一致） / Merge all module translation structures (namespaced by module name, matching component t('common.xxx') calls) */
type MessageSchema = {
  common: typeof enCommon
  recording: typeof enRecording
  start: typeof enStart
  processing: typeof enProcessing
  library: typeof enLibrary
  speakers: typeof enSpeakers
  hotwords: typeof enHotwords
  settings: typeof enSettings
  projects: typeof enProjects
  sidebar: typeof enSidebar
  topbar: typeof enTopbar
  generating: typeof enGenerating
  task: typeof enTask
  login: typeof enLogin
  'ai-panel': typeof enAiPanel
  agents: typeof enAgents
  decisions: typeof enDecisions
}

/** 支持的语言列表 / Supported languages */
export const SUPPORT_LOCALES = ['zh-CN', 'en'] as const
export type SupportedLocale = typeof SUPPORT_LOCALES[number]

/** 所有语言模块文件名（用于按需加载） / All locale module filenames (for on-demand loading) */
const LOCALE_MODULES = [
  'common', 'recording', 'start', 'processing', 'library',
  'speakers', 'hotwords', 'settings', 'projects', 'sidebar', 'topbar',
  'generating', 'task', 'login', 'ai-panel', 'agents', 'decisions',
] as const

/** 默认语言的全量消息（按模块名命名空间包裹，各 JSON 内部不含模块名前缀） / Full messages for default language (namespaced by module name; each JSON contains no module name prefix) */
const defaultMessages: MessageSchema = {
  common: enCommon,
  recording: enRecording,
  start: enStart,
  processing: enProcessing,
  library: enLibrary,
  speakers: enSpeakers,
  hotwords: enHotwords,
  settings: enSettings,
  projects: enProjects,
  sidebar: enSidebar,
  topbar: enTopbar,
  generating: enGenerating,
  task: enTask,
  login: enLogin,
  'ai-panel': enAiPanel,
  agents: enAgents,
  decisions: enDecisions,
}

// ─── 创建 i18n 实例 ─── / ─── Create i18n instance ───
const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: 'en',
  messages: {
    'en': defaultMessages,
  },
})

/** 获取全局 Composer 实例（类型安全） / Get global Composer instance (type-safe) */
const composer = i18n.global as Composer

/**
 * 检测当前语言 / Detect current language
 * 优先级：localStorage > 默认 en / Priority: localStorage > default en
 */
function detectLocale(): SupportedLocale {
  const saved = localStorage.getItem('locale') as SupportedLocale | null
  if (saved && SUPPORT_LOCALES.includes(saved)) return saved

  return 'en'
}

/**
 * 按需加载语言包（动态 import，Vite 自动分包） / Load locale on demand (dynamic import; Vite auto code-splitting)
 */
export async function loadLocaleMessages(locale: SupportedLocale): Promise<void> {
  if (composer.availableLocales.includes(locale)) return

  const imports = await Promise.all(
    LOCALE_MODULES.map(m => import(`./locales/${locale}/${m}.json`))
  )

  // 按模块名包裹为命名空间：imports[i] 对应 LOCALE_MODULES[i]， / Wrap by module name as namespace: imports[i] corresponds to LOCALE_MODULES[i];
  // 组件调用 t('common.xxx') / t('settings.xxx') 依赖此层级结构 / component calls t('common.xxx') / t('settings.xxx') depend on this hierarchy
  const messages = LOCALE_MODULES.reduce(
    (acc: Record<string, unknown>, moduleName, i) => {
      acc[moduleName] = imports[i].default
      return acc
    },
    {}
  )
  composer.setLocaleMessage(locale, messages as MessageSchema)
  await nextTick()
}

/**
 * 切换语言 / Switch language
 * 自动加载语言包 → 切换 locale → 持久化到 localStorage → 更新 html lang 属性 / Auto-load locale messages → switch locale → persist to localStorage → update html lang attribute
 */
export async function setI18nLocale(locale: SupportedLocale): Promise<void> {
  await loadLocaleMessages(locale)
  composer.locale.value = locale
  localStorage.setItem('locale', locale)
  document.querySelector('html')?.setAttribute('lang', locale)
}

/** 获取当前 locale / Get current locale */
export function getLocale(): SupportedLocale {
  return composer.locale.value as SupportedLocale
}

/**
 * 供非组件 TS 文件（composables / stores）使用的翻译函数。 / Translation function for non-component TS files (composables / stores).
 * 组件内应优先用 useI18n() 的 t；此函数直接走全局 composer， / In components prefer useI18n()'s t; this function uses global composer directly,
 * 无组件上下文也可用，且随 locale 切换响应式更新（因读取的是同一 composer）。 / works without component context, and reactively updates on locale switch (reads same composer).
 */
export function tt(key: string, params?: Record<string, unknown>): string {
  return params
    ? (composer.t as (k: string, p: Record<string, unknown>) => string)(key, params)
    : (composer.t as (k: string) => string)(key)
}

export default i18n
