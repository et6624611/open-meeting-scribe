/**
 * usePresenceDetection.ts — 存在性检测（静默检测第三层） / Presence detection (silence detection layer 3)
 *
 * 从 RecordingView.vue 拆分而来。 / Split from RecordingView.vue.
 * 通过监听用户交互事件（点击、键盘、滚动）和页面可见性变化， / Monitors user interaction events (click, keyboard, scroll) and page visibility changes,
 * 维护一个存在性评分（0~100），定期向后端发送心跳。 / Maintains a presence score (0~100), sends periodic heartbeats to backend.
 * 详见 docs/design/SILENCE_DETECTION.md。 / See docs/design/SILENCE_DETECTION.md.
 */

import { ref } from 'vue'

const PRESENCE_SCORE_MAX = 100
const PRESENCE_DECAY_PER_SEC = 1
const HEARTBEAT_INTERVAL_SEC = 30

export function usePresenceDetection(
  sendHeartbeat: (score: number, userAck?: boolean) => void,
) {
  const presenceScore = ref(PRESENCE_SCORE_MAX)
  let presenceDecayTimer: ReturnType<typeof setInterval> | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null

  function onUserInteraction() { presenceScore.value = PRESENCE_SCORE_MAX }

  function onVisibilityChange() {
    if (document.visibilityState === 'visible') {
      presenceScore.value = Math.min(PRESENCE_SCORE_MAX, presenceScore.value + 80)
    } else {
      presenceScore.value = Math.floor(presenceScore.value * 0.3)
    }
  }

  function onWindowBlur() { presenceScore.value = Math.floor(presenceScore.value * 0.5) }
  function onWindowFocus() { presenceScore.value = Math.min(PRESENCE_SCORE_MAX, presenceScore.value + 60) }

  function start() {
    document.addEventListener('visibilitychange', onVisibilityChange)
    window.addEventListener('blur', onWindowBlur)
    window.addEventListener('focus', onWindowFocus)
    document.addEventListener('click', onUserInteraction)
    document.addEventListener('keydown', onUserInteraction)
    document.addEventListener('scroll', onUserInteraction)

    presenceDecayTimer = setInterval(() => {
      if (presenceScore.value > 0) presenceScore.value = Math.max(0, presenceScore.value - PRESENCE_DECAY_PER_SEC)
    }, 1000)

    heartbeatTimer = setInterval(() => {
      sendHeartbeat(presenceScore.value)
    }, HEARTBEAT_INTERVAL_SEC * 1000)

    sendHeartbeat(presenceScore.value)
  }

  function stop() {
    document.removeEventListener('visibilitychange', onVisibilityChange)
    window.removeEventListener('blur', onWindowBlur)
    window.removeEventListener('focus', onWindowFocus)
    document.removeEventListener('click', onUserInteraction)
    document.removeEventListener('keydown', onUserInteraction)
    document.removeEventListener('scroll', onUserInteraction)
    if (presenceDecayTimer) { clearInterval(presenceDecayTimer); presenceDecayTimer = null }
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
  }

  /** 用户确认继续：重置评分并发送确认心跳 / User confirms continuation: reset score and send acknowledge heartbeat */
  function acknowledge() {
    presenceScore.value = PRESENCE_SCORE_MAX
    sendHeartbeat(presenceScore.value, true)
  }

  return { presenceScore, start, stop, acknowledge }
}
