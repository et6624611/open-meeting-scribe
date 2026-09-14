/**
 * 轮询 composable — 定时拉取任务状态 / Polling composable — periodic task status fetching
 */
import { ref, onUnmounted } from 'vue'

export function usePolling(
  callback: () => Promise<void>,
  intervalMs = 3000,
) {
  const active = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  function start() {
    if (active.value) return
    active.value = true
    // 立即执行一次 / Execute immediately once
    callback().catch(console.error)
    timer = setInterval(() => {
      callback().catch(console.error)
    }, intervalMs)
  }

  function stop() {
    active.value = false
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  onUnmounted(stop)

  return { active, start, stop }
}
