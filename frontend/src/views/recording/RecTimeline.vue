<template>
  <div class="rec-timeline">
    <div class="rec-timeline-bar">
      <!-- 时间轴色带 + 滑块 / Timeline color ribbon + scrubber -->
      <div class="rec-timeline-track" :title="hoverTimeLabel">
        <canvas ref="canvasRef" class="rec-timeline-canvas" @click="onCanvasClick" @mousemove="onCanvasHover" @mouseleave="hoverTimeLabel = ''"></canvas>
        <input
          v-if="totalDuration > 0"
          type="range"
          class="rec-timeline-scrubber"
          min="0"
          :max="totalDuration"
          :value="currentTime"
          @input="onScrubInput"
        />
        <!-- 章节刻度线 / Chapter tick marks -->
        <template v-if="totalDuration > 0">
          <div
            v-for="(ch, ci) in chapters"
            :key="ci"
            class="rec-timeline-ch-mark"
            :style="{ left: (ch.start_ms / totalDuration * 100) + '%' }"
          ></div>
        </template>
      </div>
      <!-- 跳转按钮 / Jump button -->
      <button class="rec-timeline-jump-btn" :title="t('recording.timeline.jump_title')" @click="showJumpInput = !showJumpInput">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
      </button>
    </div>
    <!-- 时间标签 + 跳转输入 / Time label + jump input -->
    <div class="rec-timeline-footer">
      <span class="rec-timeline-time">{{ formatTime(currentTime) }}</span>
      <div v-if="showJumpInput" class="rec-timeline-jump-form">
        <input
          ref="jumpInputRef"
          v-model="jumpInput"
          class="rec-timeline-jump-input"
          :placeholder="t('recording.timeline.jump_placeholder')"
          @keydown.enter="onJumpSubmit"
          @blur="onJumpBlur"
        />
        <button class="rec-timeline-jump-go" @click="onJumpSubmit">{{ t('recording.timeline.jump_go') }}</button>
      </div>
      <span class="rec-timeline-time rec-timeline-total">{{ formatTime(totalDuration) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { getSpeakerColor } from '@/utils/speakerColors'
import type { TranscriptLine } from '@/composables/useWebSocket'

const { t } = useI18n()

const props = defineProps<{
  lines: TranscriptLine[]
  chapters: Array<{ start_ms: number; end_ms?: number }>
  totalDurationMs: number
  currentTimeMs: number
  markerMode: boolean
  hasNoteAt: (idx: number) => boolean
}>()

const emit = defineEmits<{
  (e: 'seek-to-time', timeMs: number): void
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const jumpInputRef = ref<HTMLInputElement | null>(null)
const showJumpInput = ref(false)
const jumpInput = ref('')
const hoverTimeLabel = ref('')
let resizeObs: ResizeObserver | null = null

// ── 计算总时长 / Compute total duration ──
const totalDuration = computed(() => {
  if (props.totalDurationMs > 0) return props.totalDurationMs
  if (props.lines.length > 0) {
    const last = props.lines[props.lines.length - 1]
    if (last.end_time) return last.end_time
    if (last.begin_time) return last.begin_time + 30000
  }
  return 0
})

const currentTime = computed(() => Math.min(props.currentTimeMs, totalDuration.value || 1))

// ── 说话人分桶数据 / Speaker bucket data ──
interface Bucket { startMs: number; endMs: number; speakers: Map<number, number> }

const buckets = computed<Bucket[]>(() => {
  const dur = totalDuration.value
  if (dur <= 0 || props.lines.length === 0) return []
  const BUCKET_MS = 10000
  const count = Math.max(1, Math.ceil(dur / BUCKET_MS))
  const result: Bucket[] = []
  for (let i = 0; i < count; i++) {
    result.push({ startMs: i * BUCKET_MS, endMs: (i + 1) * BUCKET_MS, speakers: new Map() })
  }
  for (const line of props.lines) {
    const t = line.begin_time ?? 0
    const idx = Math.min(Math.floor(t / BUCKET_MS), count - 1)
    if (idx >= 0) {
      const cur = result[idx].speakers.get(line.speaker_id) || 0
      result[idx].speakers.set(line.speaker_id, cur + line.text.length)
    }
  }
  return result
})

// ── Canvas 渲染 / Canvas rendering ──
function renderCanvas() {
  const canvas = canvasRef.value
  if (!canvas) return
  const parent = canvas.parentElement
  if (!parent) return

  const w = parent.clientWidth
  const h = 28
  if (w <= 0) return

  const dpr = window.devicePixelRatio || 1
  canvas.width = w * dpr
  canvas.height = h * dpr
  canvas.style.width = w + 'px'
  canvas.style.height = h + 'px'

  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, w, h)

  // 背景 / Background
  ctx.fillStyle = 'rgba(128, 128, 128, 0.06)'
  ctx.beginPath()
  ctx.roundRect(0, 0, w, h, 4)
  ctx.fill()

  const bks = buckets.value
  const dur = totalDuration.value
  if (bks.length === 0 || dur <= 0) return

  const segW = w / bks.length

  for (let i = 0; i < bks.length; i++) {
    const bk = bks[i]
    if (bk.speakers.size === 0) continue

    const totalChars = Array.from(bk.speakers.values()).reduce((a, b) => a + b, 0)
    const maxChars = 500
    const intensity = Math.min(1, totalChars / maxChars)
    const barH = Math.max(3, h * 0.3 + (h * 0.65) * intensity)
    const y = (h - barH) / 2

    const sorted = [...bk.speakers.entries()].sort((a, b) => b[1] - a[1])
    let accumulated = 0

    for (const [sid, chars] of sorted) {
      const proportion = chars / totalChars
      const segH = barH * proportion
      const color = getSpeakerColor(sid)

      ctx.fillStyle = color
      ctx.globalAlpha = 0.55 + 0.35 * intensity
      ctx.fillRect(i * segW, y + accumulated, Math.max(segW + 0.5, 1), segH)

      accumulated += segH
    }
  }
  ctx.globalAlpha = 1
}

// ── 二分查找：时间 → 行索引 / Binary search: time → line index ──
function findLineIndexByTime(targetMs: number): number {
  const lines = props.lines
  if (lines.length === 0) return 0
  let lo = 0, hi = lines.length - 1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    const midTime = lines[mid].begin_time ?? 0
    if (midTime < targetMs) lo = mid + 1
    else if (midTime > targetMs) hi = mid - 1
    else return mid
  }
  return Math.min(lo, lines.length - 1)
}

// ── 交互事件 / Interaction events ──
function onScrubInput(e: Event) {
  const val = Number((e.target as HTMLInputElement).value)
  emit('seek-to-time', val)
}

function onCanvasClick(e: MouseEvent) {
  const canvas = canvasRef.value
  if (!canvas || totalDuration.value <= 0) return
  const rect = canvas.getBoundingClientRect()
  const ratio = (e.clientX - rect.left) / rect.width
  emit('seek-to-time', Math.max(0, ratio * totalDuration.value))
}

function onCanvasHover(e: MouseEvent) {
  const canvas = canvasRef.value
  if (!canvas || totalDuration.value <= 0) { hoverTimeLabel.value = ''; return }
  const rect = canvas.getBoundingClientRect()
  const ratio = (e.clientX - rect.left) / rect.width
  const timeMs = Math.max(0, ratio * totalDuration.value)
  hoverTimeLabel.value = formatTime(timeMs)
}

function onJumpSubmit() {
  const ms = parseTimeInput(jumpInput.value)
  if (ms !== null) {
    emit('seek-to-time', ms)
    showJumpInput.value = false
    jumpInput.value = ''
  }
}

function onJumpBlur() {
  setTimeout(() => { showJumpInput.value = false; jumpInput.value = '' }, 200)
}

function parseTimeInput(input: string): number | null {
  const trimmed = input.trim()
  if (!trimmed) return null
  const parts = trimmed.split(':').map(Number)
  if (parts.some(isNaN)) return null
  if (parts.length === 2) return (parts[0] * 60 + parts[1]) * 1000
  if (parts.length === 3) return (parts[0] * 3600 + parts[1] * 60 + parts[2]) * 1000
  return null
}

function formatTime(ms: number): string {
  const totalSec = Math.floor(ms / 1000)
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// ── 生命周期 / Lifecycle ──
watch([buckets, () => totalDuration.value], () => { nextTick(renderCanvas) }, { deep: true })

watch(() => showJumpInput.value, (v) => {
  if (v) nextTick(() => jumpInputRef.value?.focus())
})

onMounted(() => {
  renderCanvas()
  resizeObs = new ResizeObserver(() => renderCanvas())
  if (canvasRef.value?.parentElement) resizeObs.observe(canvasRef.value.parentElement)
})

onBeforeUnmount(() => {
  resizeObs?.disconnect()
  resizeObs = null
})

// ── 暴露二分查找方法供父组件使用 / Expose binary search method for parent component ──
defineExpose({ findLineIndexByTime })
</script>
