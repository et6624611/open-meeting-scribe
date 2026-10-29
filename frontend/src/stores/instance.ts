/**
 * 企业实例状态 store（契约 §1.6/§1.7 横幅位）+ 同步队列轮询（§1.4 队列侧权威态）
 *
 * service_open=false → 顶部常驻横幅（辅助口径"企业服务已暂停，仅可查看已同步内容"），
 * 全部写操作由服务端 503 service_closed 兜底，前端据 store 做界面禁用（档位②③消费点）。
 * sync queue 数据源是 local plane GET /api/sync/queue；助手不可达时静默（档⑦状态卡负责引导）。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { isEnterprise } from '@/edition'
import { fetchInstanceInfo, type InstanceInfo } from '@/api/enterpriseAuth'
import { getSyncQueue, type SyncQueueItem } from '@/api/context'

const QUEUE_POLL_MS = 30_000

export const useInstanceStore = defineStore('instance', () => {
  const info = ref<InstanceInfo | null>(null)
  const queue = ref<SyncQueueItem[]>([])
  let pollTimer: ReturnType<typeof setInterval> | null = null

  const serviceOpen = computed(() => info.value?.service_open ?? true)
  const aiEnabled = computed(() => info.value?.ai_enabled ?? false)
  const pendingCount = computed(() => queue.value.filter(q => q.status === 'pending' || q.status === 'syncing').length)
  const hasError = computed(() => queue.value.some(q => q.status === 'error'))

  async function refreshInfo() {
    if (!isEnterprise) return
    try { info.value = await fetchInstanceInfo() } catch { /* 保留上次状态 */ }
  }

  async function refreshQueue() {
    if (!isEnterprise) return
    try { queue.value = await getSyncQueue() } catch { queue.value = [] /* 助手未连接：非错误场景，档⑦状态卡呈现 */ }
  }

  function startPolling() {
    if (!isEnterprise || pollTimer) return
    void refreshInfo()
    void refreshQueue()
    pollTimer = setInterval(() => { void refreshInfo(); void refreshQueue() }, QUEUE_POLL_MS)
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }

  return { info, queue, serviceOpen, aiEnabled, pendingCount, hasError, refreshInfo, refreshQueue, startPolling, stopPolling }
})
