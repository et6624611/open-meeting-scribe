import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'oms_watermark'

interface WatermarkPrefs {
  enabled: boolean
  opacity: number
}

const DEFAULTS: WatermarkPrefs = {
  enabled: false,
  opacity: 1.0,
}

/**
 * 水印氛围层状态管理 / Watermark atmosphere layer state management
 *
 * 控制全局光晕氛围效果的开关与透明度。 / Control global glow atmosphere effect on/off and opacity.
 * 偏好持久化到 localStorage，主题切换时 --wm.opacity / --wm.glow 由主题 CSS 控制， / Prefs persisted to localStorage; on theme switch --wm.opacity / --wm.glow controlled by theme CSS;
 * 此处仅管理用户级别的总开关与透明度倍率。 / this only manages user-level master toggle and opacity multiplier.
 */
export const useWatermarkStore = defineStore('watermark', () => {
  const saved = loadPrefs()

  const enabled = ref(saved.enabled)
  const opacity = ref(saved.opacity)

  /** 切换开/关 / Toggle on/off */
  function toggle() {
    enabled.value = !enabled.value
    persist()
  }

  /** 设置透明度（0.1 ~ 1.0） / Set opacity (0.1 ~ 1.0) */
  function setOpacity(val: number) {
    opacity.value = Math.max(0.1, Math.min(1.0, val))
    persist()
  }

  function persist() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      enabled: enabled.value,
      opacity: opacity.value,
    }))
  }

  return { enabled, opacity, toggle, setOpacity }
})

function loadPrefs(): WatermarkPrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        enabled: typeof parsed.enabled === 'boolean' ? parsed.enabled : DEFAULTS.enabled,
        opacity: typeof parsed.opacity === 'number' ? parsed.opacity : DEFAULTS.opacity,
      }
    }
  } catch { /* 忽略损坏数据 / Ignore corrupted data */ }
  return { ...DEFAULTS }
}
