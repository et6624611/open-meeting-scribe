/**
 * 转写进度状态机 — 统一进度面板的数据源逻辑（REQ-TRANSCRIBE-PROGRESS P0 / R1·R2·R4-简）
 * Transcribe progress state machine — single source for the unified progress panel.
 *
 * 职责 / Responsibilities:
 *  - 后端细阶段 → 4 步步骤条归并映射（语音转写/原文整理/生成纪要/完成）
 *  - 百分比单调不回退 + 缓动过渡（3s 轮询 → 平滑动画）
 *  - 已用时长（localStorage 持久化起点，刷新后可恢复）与 ETA 线性外推
 *  - 停滞检测（>60s 无推进切换安抚文案，不显示假数字）
 */
import { ref, computed, watch, onUnmounted, type Ref } from 'vue'
import type { Task } from '@/api/types'

/** 4 步步骤条（§4 P0 裁决版）：语音转写 → 原文整理 → 生成纪要 → 完成 */
export const PROGRESS_STEPS = ['transcribe', 'organize', 'summarize', 'done'] as const
export type ProgressStep = typeof PROGRESS_STEPS[number]

/**
 * 后端 stage/percent 区间归并（core/pipeline.py:106-171, 225-300）：
 *  - audio(10-20)/hotwords(35-40)/transcribe(45-70) → 语音转写
 *  - speakers(75-80)（说话人分离/声纹匹配）        → 原文整理
 *  - summarize(85-90)/title(92-93)/chapters(94-96)/save(98) → 生成纪要
 *  - done(100)                                     → 完成
 */
function stepIndexFromPercent(pct: number): number {
  if (pct >= 100) return 3
  if (pct > 80) return 2
  if (pct > 70) return 1
  return 0
}

/** failed_stage（后端仅有 transcribe/summarize 两类）→ 步骤索引 */
function stepFromFailedStage(stage: string | null | undefined): number | null {
  if (!stage) return null
  if (stage === 'transcribe' || stage === 'audio' || stage === 'hotwords') return 0
  if (stage === 'speakers') return 1
  if (stage === 'summarize' || stage === 'title' || stage === 'chapters' || stage === 'save') return 2
  return null
}

const ACTIVE_STATUSES = ['pending', 'processing', 'transcribing', 'summarizing', 'awaiting_mapping']
const ELAPSED_KEY_PREFIX = 'oms_proc_started_'
/** ETA 显示门槛：当前步骤内进度推进 ≥10 个百分点（§4 R2） */
const ETA_MIN_ADVANCE = 10
/** 停滞判定：>60s 无任何推进 */
const STAGNATION_MS = 60_000

function nowMs(): number { return Date.now() }

/** 秒数 → 「X 分 Y 秒」/「Y 秒」（i18n 模板外只给数字串，语言无关的 m:ss 格式） */
export function formatElapsed(sec: number): string {
  const s = Math.max(0, Math.floor(sec))
  const m = Math.floor(s / 60)
  const r = s % 60
  if (m >= 60) {
    const h = Math.floor(m / 60)
    return `${h}:${String(m % 60).padStart(2, '0')}:${String(r).padStart(2, '0')}`
  }
  return m > 0 ? `${m}:${String(r).padStart(2, '0')}` : `${r}s`
}

export function useTranscribeProgress(task: Ref<Task | null | undefined>) {
  // ─── 单调百分比（渲染值） / Monotonic displayed percent ───
  const targetPercent = ref(0)     // 后端最新值（单调裁剪后）
  const displayPercent = ref(0)    // 缓动渲染值
  const maxSeen = ref(0)           // 本轮（run）内见过的最大值

  // 处理起点（epoch ms），localStorage 持久化以支持刷新恢复
  const elapsedSec = ref(0)
  let processingStartedAt = 0

  // ETA 采样：当前步骤起点 (t, targetPercent)
  let stepAnchor: { t: number; p: number; step: number } | null = null
  const etaMinutes = ref<number | null>(null)
  const stagnated = ref(false)
  let lastProgressChangeAt = nowMs()

  // 缓动动画（rAF，只增不减）
  let rafId: number | null = null
  let lastFrameAt = 0
  const reduceMotion = typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  function tweenTick(at: number) {
    const dt = lastFrameAt ? (at - lastFrameAt) / 1000 : 0.016
    lastFrameAt = at
    const target = targetPercent.value
    const cur = displayPercent.value
    if (cur >= target) {
      if (cur === target) { rafId = null; lastFrameAt = 0; return }
      displayPercent.value = target
      rafId = null; lastFrameAt = 0
      return
    }
    // 指数缓动：τ≈1.2s，2-3 秒内基本到位（匹配 3s 轮询节奏）
    const tau = reduceMotion ? 0.05 : 1.2
    const next = cur + (target - cur) * (1 - Math.exp(-dt / tau))
    displayPercent.value = Math.min(target, next)
    rafId = requestAnimationFrame(tweenTick)
  }

  function setTarget(pct: number) {
    if (pct <= maxSeen.value) return // 单调不回退（AC-2）：后端瞬时回退不透传
    maxSeen.value = pct
    targetPercent.value = pct
    lastProgressChangeAt = nowMs()
    stagnated.value = false
    if (reduceMotion) {
      displayPercent.value = pct
    } else if (rafId === null) {
      lastFrameAt = 0
      rafId = requestAnimationFrame(tweenTick)
    }
  }

  /** 重置一轮（重试/重新处理） / Reset for a fresh run after retry */
  function resetRun(pct = 0) {
    maxSeen.value = pct
    targetPercent.value = pct
    displayPercent.value = pct
    stepAnchor = null
    etaMinutes.value = null
    stagnated.value = false
    lastProgressChangeAt = nowMs()
  }

  let wasFailed = false
  watch(() => [task.value?.status, task.value?.progress, task.value?.retry_count] as const, ([status, pct]) => {
    const st = status ?? ''
    if (st === 'failed') {
      wasFailed = true
      // 失败态也要吸收 progress：刷新后直达失败页时「已处理至 X%」才有真实数字
      setTarget(pct ?? 0)
      return
    }
    if (ACTIVE_STATUSES.includes(st)) {
      // failed → 活跃：视为用户重试，重开一轮，允许百分比重新爬升
      if (wasFailed) { wasFailed = false; resetRun(pct ?? 0) }
      const percent = pct ?? 0
      setTarget(percent)
      // 处理起点持久化（已用时长跨刷新恢复）
      if (!processingStartedAt) {
        const key = ELAPSED_KEY_PREFIX + (task.value?.task_id ?? '')
        const saved = Number(localStorage.getItem(key) || 0)
        processingStartedAt = saved > 0 ? saved : nowMs()
        if (!saved && task.value?.task_id) localStorage.setItem(key, String(processingStartedAt))
      }
    } else if (st === 'completed' && task.value?.task_id) {
      setTarget(100)
      localStorage.removeItem(ELAPSED_KEY_PREFIX + task.value.task_id)
      // 章节补生成等完成后场景：从组件挂载起计时，心跳可证「在动」
      if (!processingStartedAt) processingStartedAt = nowMs()
    }
  }, { immediate: true })

  // 已用时长 + 停滞检测：1s 心跳（同时满足「UI 可见状态静默 ≤15s」——计时始终在动）
  const heartbeat = setInterval(() => {
    if (!processingStartedAt) return
    elapsedSec.value = Math.floor((nowMs() - processingStartedAt) / 1000)
    if (ACTIVE_STATUSES.includes(task.value?.status ?? '') && nowMs() - lastProgressChangeAt > STAGNATION_MS) {
      stagnated.value = true
    }
  }, 1000)
  onUnmounted(() => {
    clearInterval(heartbeat)
    if (rafId !== null) cancelAnimationFrame(rafId)
  })

  // ─── 派生状态 / Derived state ───
  const isActive = computed(() => ACTIVE_STATUSES.includes(task.value?.status ?? ''))
  const isFailed = computed(() => task.value?.status === 'failed')
  const isCompleted = computed(() => task.value?.status === 'completed')

  const currentStep = computed(() => {
    if (isCompleted.value) return 3
    const pct = maxSeen.value
    return stepIndexFromPercent(isFailed.value ? Math.max(0, Math.min(pct, 99)) : pct)
  })

  /** 失败停留步骤：failed_stage 映射优先，缺省用当前进度定位 */
  const failedStep = computed(() => {
    if (!isFailed.value) return null
    const mapped = stepFromFailedStage(task.value?.failed_stage)
    if (mapped !== null) return mapped
    return stepIndexFromPercent(Math.max(0, Math.min(maxSeen.value, 99)))
  })

  watch(currentStep, (step) => {
    if (!isActive.value) return
    if (!stepAnchor || stepAnchor.step !== step) {
      stepAnchor = { t: nowMs(), p: targetPercent.value, step }
    }
  }, { immediate: true })

  // ETA：阶段内推进 ≥10pp 后线性外推；估算不成立 → null（宁缺毋滥）
  watch(targetPercent, () => {
    if (!isActive.value || !stepAnchor || stagnated.value) { etaMinutes.value = null; return }
    const advanced = targetPercent.value - stepAnchor.p
    const elapsedMs = nowMs() - stepAnchor.t
    if (advanced < ETA_MIN_ADVANCE || elapsedMs <= 0) { etaMinutes.value = null; return }
    const rate = advanced / elapsedMs // pp per ms
    if (rate <= 0) { etaMinutes.value = null; return }
    const remainingMs = (100 - targetPercent.value) / rate
    const minutes = Math.max(1, Math.round(remainingMs / 60000))
    etaMinutes.value = minutes
  })

  return {
    displayPercent,       // 0-100 浮点，渲染用（缓动后）
    rawPercent: computed(() => targetPercent.value),
    currentStep,
    failedStep,
    isActive,
    isFailed,
    isCompleted,
    elapsedSec,
    etaMinutes,
    stagnated,
    formatElapsed,
  }
}
