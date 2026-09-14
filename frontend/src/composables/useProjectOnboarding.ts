/**
 * 知识库关联引导弹窗 — 动画与展示控制 / Knowledge base association onboarding modal — animation and display control
 */
import { ref, nextTick } from 'vue'

export function useProjectOnboarding() {
  const showProjectOnboarding = ref(false)
  const connected = ref(false)

  let animTimer: ReturnType<typeof setTimeout> | null = null
  let loopTimer: ReturnType<typeof setTimeout> | null = null
  const CYCLE_MS = 4000
  const PAUSE_MS = 1500

  function stopAnim() {
    if (animTimer) { clearTimeout(animTimer); animTimer = null }
    if (loopTimer) { clearTimeout(loopTimer); loopTimer = null }
  }

  function startAnim() {
    stopAnim()
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (prefersReduced) { connected.value = true; return }
    connected.value = false
    animTimer = setTimeout(() => { connected.value = true }, 1500)
    loopTimer = setTimeout(() => { startAnim() }, CYCLE_MS + PAUSE_MS)
  }

  function openOnboarding() {
    showProjectOnboarding.value = true
    nextTick(() => startAnim())
  }

  function closeOnboarding() {
    stopAnim()
    connected.value = false
    showProjectOnboarding.value = false
  }

  return {
    showProjectOnboarding, connected,
    startAnim, stopAnim, openOnboarding, closeOnboarding,
  }
}
