import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/** 可用主题列表 / Available themes */
export const THEMES = [
  { id: 'standard-light', label: '标准浅色', group: 'standard' },
  { id: 'standard-dark', label: '标准深色', group: 'standard' },
  { id: 'default', label: '晨曦', group: 'nature' },
  { id: 'dark', label: '夜色', group: 'nature' },
  { id: 'warm', label: '晚霞', group: 'nature' },
  { id: 'forest', label: '森林', group: 'nature' },
  { id: 'mist', label: '薄雾', group: 'nature' },
  { id: 'moss', label: '苔藓', group: 'nature' },
  { id: 'wheat', label: '麦浪', group: 'nature' },
  { id: 'moonlight', label: '月白', group: 'nature' },
] as const

export type ThemeId = (typeof THEMES)[number]['id']

const STORAGE_KEY = 'oms_theme'

export const useThemeStore = defineStore('theme', () => {
  const current = ref<ThemeId>(loadTheme())
  const isStartMode = ref(false)

  const currentLabel = computed(() =>
    THEMES.find(t => t.id === current.value)?.label ?? '标准浅色',
  )

  /** 切换主题（持久化） / Switch theme (persisted) */
  function setTheme(id: ThemeId) {
    current.value = id
    document.documentElement.setAttribute('data-theme', id)
    localStorage.setItem(STORAGE_KEY, id)
  }

  /** 预览主题（仅改 DOM，不持久化） / Preview theme (DOM only, no persist) */
  function previewTheme(id: ThemeId) {
    document.documentElement.setAttribute('data-theme', id)
  }

  /** 恢复到当前已确认的主题 / Restore to confirmed theme */
  function restoreTheme() {
    document.documentElement.setAttribute('data-theme', current.value)
  }

  /** 从 localStorage 加载已保存的主题 / Load saved theme from localStorage */
  function loadTheme(): ThemeId {
    const saved = localStorage.getItem(STORAGE_KEY) as ThemeId | null
    if (saved && THEMES.some(t => t.id === saved)) {
      document.documentElement.setAttribute('data-theme', saved)
      return saved
    }
    return 'standard-light'
  }

  return { current, currentLabel, isStartMode, setTheme, previewTheme, restoreTheme }
})
