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
  /**
   * 预览中的主题（不持久化）：设置页鼠标滑过色块时只改 DOM 属性、不动 `current`，
   * 导致订阅 `current` 的消费者（如洞察板 iframe 的主题令牌下发）收不到变化，
   * 出现「全站已经在预览新主题、板仍是旧配色」。预览态单独成变量，
   * 需要跟随实时观感的组件读 `activeTheme`，需要读“用户真正保存了哪套”的组件读 `current`。
   */
  const previewing = ref<ThemeId | null>(null)

  const currentLabel = computed(() =>
    THEMES.find(t => t.id === current.value)?.label ?? '标准浅色',
  )

  /** 当前屏幕上实际生效的主题（预览优先） / Theme currently painted (preview wins) */
  const activeTheme = computed<ThemeId>(() => previewing.value ?? current.value)

  /** 切换主题（持久化） / Switch theme (persisted) */
  function setTheme(id: ThemeId) {
    previewing.value = null
    current.value = id
    document.documentElement.setAttribute('data-theme', id)
    localStorage.setItem(STORAGE_KEY, id)
  }

  /** 预览主题（进 store 以保证响应式消费者同步收到，但仍不持久化） / Preview theme (reactive, no persist) */
  function previewTheme(id: ThemeId) {
    previewing.value = id
    document.documentElement.setAttribute('data-theme', id)
  }

  /** 恢复到当前已确认的主题 / Restore to confirmed theme */
  function restoreTheme() {
    previewing.value = null
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

  return { current, activeTheme, previewing, currentLabel, isStartMode, setTheme, previewTheme, restoreTheme }
})
