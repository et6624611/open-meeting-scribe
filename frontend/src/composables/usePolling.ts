/**
 * 轮询 composable — 定时拉取任务状态 / Polling composable — periodic task status fetching
 *
 * 链式 setTimeout + 在途防护：上一轮未返回时跳过本轮，回调永远不重叠、响应不乱序。
 * （旧实现用 setInterval，事件循环被慢请求阻塞时多个请求会并发，旧响应可能晚于
 * 新响应落地，导致任务状态回退闪屏。）
 * Chained setTimeout with in-flight guard: ticks never overlap, responses can't reorder.
 */
import { ref, onUnmounted } from 'vue'

export function usePolling(
  callback: () => Promise<void>,
  intervalMs = 3000,
) {
  const active = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let inFlight = false

  function clear() {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  async function tick() {
    if (!active.value) return
    if (inFlight) return
    inFlight = true
    try {
      await callback()
    } catch (err) {
      console.error(err)
    } finally {
      inFlight = false
      if (active.value) timer = setTimeout(tick, intervalMs)
    }
  }

  function start() {
    if (active.value) return
    active.value = true
    // 立即执行一次 / Execute immediately once
    void tick()
  }

  function stop() {
    active.value = false
    clear()
  }

  onUnmounted(stop)

  return { active, start, stop }
}
