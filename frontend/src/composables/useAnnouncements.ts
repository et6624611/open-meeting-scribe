/**
 * 公告横幅 composable / Announcement banner composable
 *
 * 职责 / Responsibilities:
 *  - 启动时拉取公告 / Fetch announcements on startup
 *  - 按关闭策略判断是否显示 / Determine visibility based on dismiss policy
 *  - 关闭时记录到 storage / Record dismissal to storage
 *  - 登录状态联动（已登录不显示 guest 公告） / Login state coordination (don't show guest announcements when logged in)
 */
import { ref, watch } from 'vue'
import { fetchAnnouncements, type Announcement, type DismissPolicy } from '@/api/announcements'
import { useUserStore } from '@/stores/user'

const currentMessage = ref<Announcement | null>(null)
const visible = ref(false)

let initialized = false

function isDismissed(msg: Announcement): boolean {
  const policy: DismissPolicy = msg.dismiss_policy || { mode: 'permanent' }
  const mode = policy.mode || 'permanent'
  const key = `dismiss_${msg.id}`

  if (mode === 'session') {
    return sessionStorage.getItem(key) === '1'
  }

  if (mode === 'permanent') {
    return localStorage.getItem(key) === '1'
  }

  if (mode === 'delayed') {
    const raw = localStorage.getItem(key)
    if (!raw) return false
    try {
      const record = JSON.parse(raw)
      const delayDays = policy.delay_days || 7
      const elapsed = (Date.now() - record.dismissed_at) / (1000 * 60 * 60 * 24)
      return elapsed < delayDays
    } catch {
      return false
    }
  }

  return false
}

function recordDismiss(msg: Announcement) {
  const policy: DismissPolicy = msg.dismiss_policy || { mode: 'permanent' }
  const mode = policy.mode || 'permanent'
  const key = `dismiss_${msg.id}`

  if (mode === 'session') {
    sessionStorage.setItem(key, '1')
  } else if (mode === 'permanent') {
    localStorage.setItem(key, '1')
  } else if (mode === 'delayed') {
    localStorage.setItem(key, JSON.stringify({ dismissed_at: Date.now() }))
  }
}

export function useAnnouncements() {
  const userStore = useUserStore()

  async function load() {
    try {
      const messages = await fetchAnnouncements()
      const banner = messages.find(m => m.type === 'banner')
      if (!banner || isDismissed(banner)) {
        visible.value = false
        currentMessage.value = null
        return
      }
      currentMessage.value = banner
      visible.value = true
    } catch {
      visible.value = false
      currentMessage.value = null
    }
  }

  function dismiss() {
    visible.value = false
    if (currentMessage.value) {
      recordDismiss(currentMessage.value)
    }
  }

  function getCtaUrl(): string {
    const msg = currentMessage.value
    if (!msg?.cta_url) return ''
    const url = msg.cta_url.trim()
    if (url && !/^https?:\/\//i.test(url)) {
      return 'https://' + url
    }
    return url
  }

  if (!initialized) {
    initialized = true
    watch(() => userStore.isLoggedIn, () => {
      load()
    })
  }

  return {
    visible,
    currentMessage,
    load,
    dismiss,
    getCtaUrl,
  }
}
