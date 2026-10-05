/**
 * 公告/横幅 API / Announcement/banner API
 *
 * 对接后端 /api/config/announcements / Backed by /api/config/announcements
 */

export interface DismissPolicy {
  mode: 'session' | 'permanent' | 'delayed'
  delay_days?: number
}

export interface Announcement {
  id: string
  type: 'banner' | 'toast' | 'announcement'
  title?: string
  content: string
  cta_text?: string
  cta_url?: string
  target: string
  priority: number
  dismiss_policy?: DismissPolicy
}

/** 获取当前有效的公告消息列表 / Fetch currently active announcement messages */
export async function fetchAnnouncements(): Promise<Announcement[]> {
  const res = await fetch('/api/config/announcements')
  if (!res.ok) return []
  const data = await res.json()
  return (data.messages || []) as Announcement[]
}
