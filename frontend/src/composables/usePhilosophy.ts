/**
 * usePhilosophy — 页面级价值主张管理 / Page-level value proposition management
 *
 * 根据当前页面（及可选 Tab）从后端获取对应的理念语录 / Fetch the matching philosophy from the backend based on current page (and optional tab).
 * 回退链：page+tab → page → 通用条目 / Fallback chain: page+tab → page → generic entry.
 * 各视图可在 Tab 切换时调用 updatePhilosophy() 刷新底部状态栏文字 / Views can call updatePhilosophy() on tab switch to refresh the footer status-bar text.
 */
import { ref, computed } from 'vue'
import { getLocale } from '@/i18n'

const variants = ref<Record<string, string>>({})

const text = computed(() => {
  const lang = getLocale().startsWith('zh') ? 'zh' : 'en'
  return variants.value[lang] || variants.value.zh || ''
})

// 按词分组，避免空格字符在 inline-block span 中丢失宽度 / Group by word so spaces are natural whitespace between inline-block word groups
const chars = computed(() => text.value.split(' ').filter(w => w.length > 0).map(w => w.split('')))

/** 缓存 key：page + tab 组合 / Cache key: combination of page + tab */
function cacheKey(page?: string, tab?: string): string {
  return `philosophy_cache_${page || '_'}_${tab || '_'}`
}

/** 从后端加载理念 / Load philosophy from backend */
async function fetchPhilosophy(page?: string, tab?: string): Promise<Record<string, string> | null> {
  const key = cacheKey(page, tab)
  const WEEK_MS = 7 * 24 * 60 * 60 * 1000
  try {
    const cached = JSON.parse(localStorage.getItem(key) || '{}')
    const now = Date.now()
    let v = cached.variants as Record<string, string> | undefined
    if (v && typeof v === 'object') {
      const hasStringValue = Object.values(v).some(val => typeof val === 'string')
      if (!hasStringValue) v = undefined
    }
    if (!v || !cached.ts || now - cached.ts > WEEK_MS) {
      const params = new URLSearchParams()
      if (page) params.set('page', page)
      if (tab) params.set('tab', tab)
      const qs = params.toString()
      const res = await fetch(`/api/philosophy/random${qs ? `?${qs}` : ''}`)
      if (!res.ok) return null
      const data = await res.json()
      v = data.variants
        || (typeof data.text === 'object' && data.text !== null ? data.text : { zh: String(data.text || '') })
      localStorage.setItem(key, JSON.stringify({ variants: v, ts: now }))
    }
    return v || null
  } catch {
    return null
  }
}

/** 触发动画效果 / Trigger reveal animation */
function triggerAnimation() {
  setTimeout(() => {
    const el = document.getElementById('philosophyText')
    if (el) {
      el.classList.remove('is-visible', 'is-shimmer')
      // 强制回流以重启动画 / Force reflow to restart animation
      void el.offsetWidth
      el.classList.add('is-visible')
    }
  }, 100)
  setTimeout(() => {
    const el = document.getElementById('philosophyText')
    if (el) el.classList.add('is-shimmer')
  }, 100 + text.value.length * 80 + 800)
}

/** 初始加载（应用启动时调用） / Initial load (called on app startup) */
async function loadPhilosophy() {
  const v = await fetchPhilosophy()
  if (v) {
    variants.value = v
    triggerAnimation()
  }
}

/** 页面/Tab 切换时更新理念 / Update philosophy on page/tab change */
async function updatePhilosophy(page?: string, tab?: string) {
  const v = await fetchPhilosophy(page, tab)
  if (v && JSON.stringify(v) !== JSON.stringify(variants.value)) {
    variants.value = v
    triggerAnimation()
  }
}

export function usePhilosophy() {
  return {
    philosophyVariants: variants,
    philosophyText: text,
    philosophyChars: chars,
    loadPhilosophy,
    updatePhilosophy,
  }
}
