/**
 * 说话人绑定引导弹窗 — 动画与持久化
 */
import { ref, reactive, computed, nextTick, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'

export function useOnboarding(
  _taskId: string,
  showBindingBar: ComputedRef<boolean>,
) {
  const { t } = useI18n()
  const showOnboarding = ref(false)
  const dontShowAgain = ref(false)

  /* 静态模板数据（语言无关字段）；label / name 通过 i18n 响应式解析 */
  const demoTemplate = [
    { ts: '23:15', labelKey: 'demo_label_1', nameKey: 'demo_name_1', color: 'oklch(55% 0.16 250)', isMe: false, bar1: '100%', bar2: '60%' },
    { ts: '23:18', labelKey: 'demo_label_2', nameKey: 'demo_name_2', color: 'oklch(55% 0.14 150)', isMe: false, bar1: '80%', bar2: '45%' },
    { ts: '23:20', labelKey: 'demo_label_1', nameKey: 'demo_name_1', color: 'oklch(55% 0.16 250)', isMe: true, bar1: '45%', bar2: '35%' },
  ] as const

  const animState = reactive(
    demoTemplate.map(() => ({ bound: false })),
  )

  const demoLines = computed(() =>
    demoTemplate.map((tpl, i) => ({
      ts: tpl.ts,
      label: t(`generating.onboarding.${tpl.labelKey}`),
      name: t(`generating.onboarding.${tpl.nameKey}`),
      color: tpl.color,
      bound: animState[i].bound,
      isMe: tpl.isMe,
      bar1: tpl.bar1,
      bar2: tpl.bar2,
    })),
  )

  let obAnimTimer: ReturnType<typeof setTimeout> | null = null
  let obLoopTimer: ReturnType<typeof setTimeout> | null = null
  const OB_CYCLE_MS = 4000
  const OB_PAUSE_MS = 1500

  function stopOnboardingAnim() {
    if (obAnimTimer) { clearTimeout(obAnimTimer); obAnimTimer = null }
    if (obLoopTimer) { clearTimeout(obLoopTimer); obLoopTimer = null }
  }

  function startOnboardingAnim() {
    stopOnboardingAnim()
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (prefersReduced) { animState.forEach(s => { s.bound = true }); return }
    animState.forEach(s => { s.bound = false })
    obAnimTimer = setTimeout(() => { animState.forEach(s => { s.bound = true }) }, 1500)
    obLoopTimer = setTimeout(() => { startOnboardingAnim() }, OB_CYCLE_MS + OB_PAUSE_MS)
  }

  function closeOnboarding() {
    stopOnboardingAnim()
    if (dontShowAgain.value) localStorage.setItem('spk_onboarding_dismissed', 'true')
    showOnboarding.value = false
  }

  function tryShowOnboarding() {
    if (showBindingBar.value && localStorage.getItem('spk_onboarding_dismissed') !== 'true') {
      showOnboarding.value = true
      nextTick(() => startOnboardingAnim())
    }
  }

  return {
    showOnboarding, dontShowAgain, demoLines,
    startOnboardingAnim, stopOnboardingAnim, closeOnboarding, tryShowOnboarding,
  }
}
