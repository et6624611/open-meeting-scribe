/**
 * 实时翻译 composable / Realtime translation composable
 *
 * 管理录音页的翻译功能状态：启用/关闭、目标语言选择、译文映射。 / Manages recording page translation state: enable/disable, target language, translation mapping.
 * 通过 WebSocket 与后端 RealtimeTranslator 通信。 / Communicates with backend RealtimeTranslator via WebSocket.
 *
 * 状态持久化：enabled / targetLang / displayMode 存入 localStorage。 / State persistence: enabled / targetLang / displayMode saved to localStorage.
 */
import { ref, computed } from 'vue'
import type { useWebSocketTranscript, TranslationEntry } from './useWebSocket'

export type TranslationDisplayMode = 'original' | 'translation' | 'bilingual'
export type TranslationStatus = 'inactive' | 'active' | 'translating' | 'stopped'

const STORAGE_KEY = 'oms_translation_prefs'

interface TranslationPrefs {
  enabled: boolean
  targetLang: string
  displayMode: TranslationDisplayMode
}

export interface SupportedLanguage {
  code: string
  label: string
}

/** 支持的目标语言列表 / Supported target languages */
const SUPPORTED_LANGUAGES: SupportedLanguage[] = [
  { code: 'en', label: 'English' },
  { code: 'ja', label: '日本語' },
  { code: 'ko', label: '한국어' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'es', label: 'Español' },
  { code: 'zh-CN', label: '中文' },
]

export function useTranslation(ws: ReturnType<typeof useWebSocketTranscript>) {
  // ── 响应式状态 / Reactive state ──
  const enabled = ref(false)
  const targetLang = ref('en')
  const status = ref<TranslationStatus>('inactive')
  const displayMode = ref<TranslationDisplayMode>('bilingual')

  /** 译文映射：lines 数组索引 → 译文文本 / Translation mapping: lines array index → translated text */
  const translationMap = ref<Map<number, string>>(new Map())

  /** 当前目标语言的显示标签 / Display label for current target language */
  const targetLangLabel = computed(() => {
    const lang = SUPPORTED_LANGUAGES.find(l => l.code === targetLang.value)
    return lang?.label || targetLang.value
  })

  /** 是否正在翻译中（后端正在调用 LLM） / Whether translating (backend calling LLM) */
  const isTranslating = computed(() => status.value === 'translating')

  // ── 持久化 / Persistence ──

  function loadPreferences() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const prefs: TranslationPrefs = JSON.parse(raw)
        if (typeof prefs.enabled === 'boolean') enabled.value = prefs.enabled
        if (prefs.targetLang) targetLang.value = prefs.targetLang
        if (prefs.displayMode) displayMode.value = prefs.displayMode
      }
    } catch {
      // 解析失败使用默认值 / Use defaults on parse failure
    }
  }

  function savePreferences() {
    try {
      const prefs: TranslationPrefs = {
        enabled: enabled.value,
        targetLang: targetLang.value,
        displayMode: displayMode.value,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
    } catch {
      // 存储失败静默 / Silent on storage failure
    }
  }

  // ── 控制方法 / Control methods ──

  /** 切换翻译开/关 / Toggle translation on/off */
  function toggle() {
    if (enabled.value) {
      disable()
    } else {
      enable()
    }
  }

  /** 启用翻译 / Enable translation */
  function enable() {
    enabled.value = true
    status.value = 'active'
    translationMap.value.clear()
    ws.sendTranslationControl('start', targetLang.value)
    savePreferences()
  }

  /** 关闭翻译 / Disable translation */
  function disable() {
    enabled.value = false
    status.value = 'inactive'
    ws.sendTranslationControl('stop')
    savePreferences()
  }

  /** 设置目标语言 / Set target language */
  function setTargetLang(lang: string) {
    if (lang === targetLang.value) return
    targetLang.value = lang
    // 清空已有译文（语言切换后旧译文无意义） / Clear existing translations (old translations meaningless after language switch)
    translationMap.value.clear()
    if (enabled.value) {
      // 已启用时通知后端切换语言 / Notify backend to switch language when already enabled
      ws.sendTranslationControl('set_lang', lang)
    }
    savePreferences()
  }

  /** 切换显示模式 / Switch display mode */
  function setDisplayMode(mode: TranslationDisplayMode) {
    displayMode.value = mode
    savePreferences()
  }

  /** 循环切换显示模式：original → bilingual → translation → original / Cycle display mode: original → bilingual → translation → original */
  function cycleDisplayMode() {
    const modes: TranslationDisplayMode[] = ['original', 'bilingual', 'translation']
    const idx = modes.indexOf(displayMode.value)
    displayMode.value = modes[(idx + 1) % modes.length]
    savePreferences()
  }

  // ── WebSocket 回调处理 / WebSocket callback handling ──

  /** 处理后端推送的批量译文 / Handle batch translations pushed by backend */
  function handleTranslationUpdate(translations: TranslationEntry[]) {
    for (const entry of translations) {
      translationMap.value.set(entry.index, entry.translated_text)
    }
    // 触发响应式更新 / Trigger reactive update
    translationMap.value = new Map(translationMap.value)
  }

  /** 处理后端推送的翻译状态 / Handle translation status pushed by backend */
  function handleTranslationStatus(msg: { status: string; target_lang: string }) {
    if (msg.status === 'active' || msg.status === 'idle') {
      status.value = 'active'
      if (msg.target_lang && msg.target_lang !== targetLang.value) {
        targetLang.value = msg.target_lang
      }
    } else if (msg.status === 'translating') {
      status.value = 'translating'
    } else if (msg.status === 'stopped') {
      status.value = enabled.value ? 'active' : 'inactive'
    }
  }

  /** 录音结束时调用：清理状态 / Called when recording ends: clean up state */
  function reset() {
    status.value = 'inactive'
    translationMap.value.clear()
  }

  return {
    // 状态 / State
    enabled,
    targetLang,
    targetLangLabel,
    status,
    displayMode,
    translationMap,
    isTranslating,
    // 常量 / Constants
    supportedLanguages: SUPPORTED_LANGUAGES,
    // 方法 / Methods
    toggle,
    enable,
    disable,
    setTargetLang,
    setDisplayMode,
    cycleDisplayMode,
    handleTranslationUpdate,
    handleTranslationStatus,
    loadPreferences,
    savePreferences,
    reset,
  }
}
