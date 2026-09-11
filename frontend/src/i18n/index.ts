/**
 * i18n 国际化模块
 *
 * 基于 vue-i18n v11，采用 Composition API 模式（legacy: false）。
 * 默认语言 zh-CN 静态导入（零延迟），其他语言按需动态加载。
 */
import { createI18n, type Composer } from 'vue-i18n'
import { nextTick } from 'vue'

// ─── 静态导入默认语言（zh-CN）所有模块 ───
import zhCommon from './locales/zh-CN/common.json'
import zhRecording from './locales/zh-CN/recording.json'
import zhStart from './locales/zh-CN/start.json'
import zhProcessing from './locales/zh-CN/processing.json'
import zhLibrary from './locales/zh-CN/library.json'
import zhSpeakers from './locales/zh-CN/speakers.json'
import zhHotwords from './locales/zh-CN/hotwords.json'
import zhSettings from './locales/zh-CN/settings.json'
import zhProjects from './locales/zh-CN/projects.json'
import zhSidebar from './locales/zh-CN/sidebar.json'
import zhTopbar from './locales/zh-CN/topbar.json'
import zhGenerating from './locales/zh-CN/generating.json'
import zhTask from './locales/zh-CN/task.json'
import zhLogin from './locales/zh-CN/login.json'
import zhAiPanel from './locales/zh-CN/ai-panel.json'

/** 合并所有模块的翻译结构（按模块名命名空间包裹，与组件 t('common.xxx') 调用一致） */
type MessageSchema = {
  common: typeof zhCommon
  recording: typeof zhRecording
  start: typeof zhStart
  processing: typeof zhProcessing
  library: typeof zhLibrary
  speakers: typeof zhSpeakers
  hotwords: typeof zhHotwords
  settings: typeof zhSettings
  projects: typeof zhProjects
  sidebar: typeof zhSidebar
  topbar: typeof zhTopbar
  generating: typeof zhGenerating
  task: typeof zhTask
  login: typeof zhLogin
  'ai-panel': typeof zhAiPanel
}

/** 支持的语言列表 */
export const SUPPORT_LOCALES = ['zh-CN', 'en'] as const
export type SupportedLocale = typeof SUPPORT_LOCALES[number]

/** 所有语言模块文件名（用于按需加载） */
const LOCALE_MODULES = [
  'common', 'recording', 'start', 'processing', 'library',
  'speakers', 'hotwords', 'settings', 'projects', 'sidebar', 'topbar',
  'generating', 'task', 'login', 'ai-panel',
] as const

/** 默认语言的全量消息（按模块名命名空间包裹，各 JSON 内部不含模块名前缀） */
const defaultMessages: MessageSchema = {
  common: zhCommon,
  recording: zhRecording,
  start: zhStart,
  processing: zhProcessing,
  library: zhLibrary,
  speakers: zhSpeakers,
  hotwords: zhHotwords,
  settings: zhSettings,
  projects: zhProjects,
  sidebar: zhSidebar,
  topbar: zhTopbar,
  generating: zhGenerating,
  task: zhTask,
  login: zhLogin,
  'ai-panel': zhAiPanel,
}

// ─── 创建 i18n 实例 ───
const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': defaultMessages,
  },
})

/** 获取全局 Composer 实例（类型安全） */
const composer = i18n.global as Composer

/**
 * 检测当前语言
 * 优先级：localStorage > 浏览器语言 > 默认 zh-CN
 */
function detectLocale(): SupportedLocale {
  const saved = localStorage.getItem('locale') as SupportedLocale | null
  if (saved && SUPPORT_LOCALES.includes(saved)) return saved

  const browserLang = navigator.language
  if (browserLang.startsWith('zh')) return 'zh-CN'
  if (browserLang.startsWith('en')) return 'en'

  return 'zh-CN'
}

/**
 * 按需加载语言包（动态 import，Vite 自动分包）
 */
export async function loadLocaleMessages(locale: SupportedLocale): Promise<void> {
  if (composer.availableLocales.includes(locale)) return

  const imports = await Promise.all(
    LOCALE_MODULES.map(m => import(`./locales/${locale}/${m}.json`))
  )

  // 按模块名包裹为命名空间：imports[i] 对应 LOCALE_MODULES[i]，
  // 组件调用 t('common.xxx') / t('settings.xxx') 依赖此层级结构
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
 * 切换语言
 * 自动加载语言包 → 切换 locale → 持久化到 localStorage → 更新 html lang 属性
 */
export async function setI18nLocale(locale: SupportedLocale): Promise<void> {
  await loadLocaleMessages(locale)
  composer.locale.value = locale
  localStorage.setItem('locale', locale)
  document.querySelector('html')?.setAttribute('lang', locale)
}

/** 获取当前 locale */
export function getLocale(): SupportedLocale {
  return composer.locale.value as SupportedLocale
}

/**
 * 供非组件 TS 文件（composables / stores）使用的翻译函数。
 * 组件内应优先用 useI18n() 的 t；此函数直接走全局 composer，
 * 无组件上下文也可用，且随 locale 切换响应式更新（因读取的是同一 composer）。
 */
export function tt(key: string, params?: Record<string, unknown>): string {
  return params
    ? (composer.t as (k: string, p: Record<string, unknown>) => string)(key, params)
    : (composer.t as (k: string) => string)(key)
}

export default i18n
