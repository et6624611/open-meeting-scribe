import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/** 可用主题列表 */
export const THEMES = [
  { id: 'default', label: '默认' },
  { id: 'dark', label: '夜色' },
  { id: 'warm', label: '暖阳' },
  { id: 'forest', label: '森林' },
  { id: 'ocean', label: '海洋' },
  { id: 'lavender', label: '薰衣草' },
  { id: 'rose', label: '玫瑰' },
] as const

export type ThemeId = (typeof THEMES)[number]['id']

const STORAGE_KEY = 'oms_theme'

export const useThemeStore = defineStore('theme', () => {
  const current = ref<ThemeId>(loadTheme())
  const isStartMode = ref(false)

  const currentLabel = computed(() =>
    THEMES.find(t => t.id === current.value)?.label ?? '默认',
  )

  /** 切换主题 */
  function setTheme(id: ThemeId) {
    current.value = id
    document.documentElement.setAttribute('data-theme', id === 'default' ? 'default' : id)
    localStorage.setItem(STORAGE_KEY, id)
  }

  /** 从 localStorage 加载已保存的主题 */
  function loadTheme(): ThemeId {
    const saved = localStorage.getItem(STORAGE_KEY) as ThemeId | null
    if (saved && THEMES.some(t => t.id === saved)) {
      document.documentElement.setAttribute('data-theme', saved)
      return saved
    }
    return 'default'
  }

  return { current, currentLabel, isStartMode, setTheme }
})
