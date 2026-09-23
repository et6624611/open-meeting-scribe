<template>
  <div ref="rootRef" class="insight-flow" :class="{ 'is-fullscreen': isFullscreen }">
    <!-- 画布视口：点阵背景 + 平移宿主 / Canvas viewport: dotted grid + pan host -->
    <div
      class="insight-flow-viewport"
      ref="viewportRef"
      :class="{ 'is-pannable': pannable }"
      @pointerdown="onPanStart"
    >
      <!-- 缩放平移层：卡片 + SVG 连线 / Zoom-pan layer: cards + SVG wires -->
      <div
        class="insight-flow-scene"
        ref="sceneRef"
        :style="{ transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})` }"
      >
        <svg class="insight-flow-wires" :width="contentWidth" :height="contentHeight" fill="none">
          <path v-for="(w, i) in wires" :key="i" :d="w" stroke-width="1.5" />
        </svg>

        <div
          v-for="(phase, i) in data.phases" :key="phase.id"
          class="insight-flow-phase"
          :ref="el => setCardRef(el as HTMLElement | null, i)"
          :style="{ left: `${positions[i].x}px`, top: `${positions[i].y}px` }"
        >
          <div class="insight-flow-phase-no">{{ t('recording.insights.flow_phase_no', { no: String(i + 1).padStart(2, '0') }) }}</div>
          <div class="insight-flow-phase-title" :title="phase.title">{{ phase.title }}</div>
          <div v-if="phase.desc" class="insight-flow-phase-desc">{{ phase.desc }}</div>
          <button
            v-for="(step, j) in phase.steps" :key="j"
            class="insight-flow-chip"
            :class="{ 'is-seekable': step.beginTime > 0 }"
            :title="chipTooltip(step)"
            @click="onChipClick(step)"
          >
            <span class="insight-flow-chip-title">{{ step.label }}</span>
            <span class="insight-flow-chip-sub">
              <svg class="insight-flow-chip-ic" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              <span class="insight-flow-chip-owner">{{ t('recording.insights.flow_step_owner') }}</span>
              <span v-if="step.beginTime > 0" class="insight-flow-chip-time">{{ formatFlowTime(step.beginTime) }}</span>
            </span>
          </button>
        </div>
      </div>
    </div>

    <!-- 左下角缩放控件 / Bottom-left zoom toolbar -->
    <div class="insight-flow-toolbar">
      <button :title="t('recording.insights.flow_fit')" @click="autoFit">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/></svg>
      </button>
      <button :title="t('recording.insights.flow_zoom_out')" @click="zoomBy(-ZOOM_STEP)">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>
      </button>
      <button :title="t('recording.insights.flow_zoom_in')" @click="zoomBy(ZOOM_STEP)">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      </button>
      <button :title="isFullscreen ? t('recording.insights.flow_exit_fullscreen') : t('recording.insights.flow_fullscreen')" @click="toggleFullscreen">
        <svg v-if="!isFullscreen" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 洞察台画布渲染器 / Insight Deck canvas renderer
 *
 * 将 parseInsightFlow 产物渲染为 QoderWake workflow 样式的阶段卡画布：
 * 点阵背景、卡片从左到右错行排布、SVG 直角连线（无箭头）、缩放/平移控件。
 * 芯片点击跳转转写（seekTo），行为与旧 G6 节点一致。
 * Renders the parseInsightFlow output as a QoderWake-style workflow canvas:
 * dotted grid, staggered phase cards, arrow-less right-angle SVG wires, zoom/pan controls.
 * Chip clicks emit seekTo, matching the legacy G6 node behavior.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { InsightFlowData, InsightStep } from '@/utils/parseInsightFlow'
import { formatFlowTime } from '@/utils/parseInsightFlow'

const props = defineProps<{
  /** 解析产物（描述应已由 matchPhaseDescriptions 填入） / Parsed flow data (descs already matched) */
  data: InsightFlowData
}>()

const emit = defineEmits<{
  /** 点击携带时间的芯片时触发跳转 / Emitted when a chip carrying time is clicked */
  (e: 'seekTo', ms: number): void
}>()

const { t } = useI18n()

/* ─── 布局常量 / Layout constants ─── */
const CARD_W = 224
const GAP_X = 40
const STAGGER_Y = 46   // 错行偏移：奇数列上移 / Zigzag offset applied to odd columns
const BASE_Y = 24
const FIT_PAD = 24     // autoFit 时四周留白 / Padding respected by autoFit

const MIN_SCALE = 0.3
const MAX_SCALE = 2.5
const ZOOM_STEP = 0.2

const rootRef = ref<HTMLElement | null>(null)
const viewportRef = ref<HTMLElement | null>(null)
const sceneRef = ref<HTMLElement | null>(null)

/* ─── 视图变换（scale + translate，transform-origin 左上） / View transform ─── */
const scale = ref(1)
const offsetX = ref(0)
const offsetY = ref(0)

/** autoFit 比例：放大超过该值前不允许平移 / Fit scale: panning unlocks only above it */
const fitScale = ref(1)
const pannable = computed(() => scale.value > fitScale.value + 0.001 && !hasMeasuredError.value)

/** 卡片静态坐标（含时间戳，用于同步布局） / Static card slots */
const positions = computed(() =>
  props.data.phases.map((_, i) => ({
    x: i * (CARD_W + GAP_X),
    y: BASE_Y + (i % 2 === 1 ? -STAGGER_Y : 0),
  }))
)

/* ─── 连线几何：渲染后按卡片真实尺寸测量 / Wire geometry: measured after render ─── */
const cardRefs: HTMLElement[] = []
function setCardRef(el: HTMLElement | null, i: number) {
  if (el) cardRefs[i] = el
}

const contentWidth = ref(800)
const contentHeight = ref(400)
const hasMeasuredError = ref(false)
const wires = ref<string[]>([])

/**
 * 测量卡片尺寸 → 生成直角连线路径 + 场景边界。
 * 连线聚合在阶段级：源卡右缘中点 → 目标卡左缘中点，中间折点取水平中分。
 * Measure cards, then build right-angle wires (source right edge → target left edge,
 * mid-point elbow) and scene bounds.
 */
async function measure() {
  await nextTick()
  const cols = props.data.phases.length
  if (cols === 0) return
  let maxBottom = 0
  const rects: Array<{ x: number; y: number; w: number; h: number }> = []
  for (let i = 0; i < cols; i++) {
    const el = cardRefs[i]
    if (!el) { hasMeasuredError.value = true; return }
    const p = positions.value[i]
    rects.push({ x: p.x, y: p.y, w: el.offsetWidth || CARD_W, h: el.offsetHeight || 120 })
    maxBottom = Math.max(maxBottom, p.y + (el.offsetHeight || 120))
  }
  hasMeasuredError.value = false
  contentWidth.value = rects[cols - 1].x + rects[cols - 1].w
  contentHeight.value = Math.max(maxBottom + BASE_Y, 200)

  const phaseIndex = new Map(props.data.phases.map((p, i) => [p.id, i]))
  const paths: string[] = []
  for (const link of props.data.links) {
    const fi = phaseIndex.get(link.from)
    const ti = phaseIndex.get(link.to)
    if (fi === undefined || ti === undefined) continue
    const a = rects[fi]
    const b = rects[ti]
    // 前进：A 右缘 → B 左缘；回退：A 左缘下方绕行 → B 右缘
    // Forward: right edge → left edge; backward links route around the bottom edges
    let d: string
    if (ti > fi) {
      const x1 = a.x + a.w, y1 = a.y + a.h / 2
      const x2 = b.x, y2 = b.y + b.h / 2
      const xm = x1 + (x2 - x1) / 2
      d = `M ${x1} ${y1} H ${xm} V ${y2} H ${x2}`
    } else {
      const x1 = a.x, y1 = a.y + a.h - 12
      const x2 = b.x + b.w, y2 = b.y + b.h - 12
      const ym = Math.max(y1, y2) + FIT_PAD
      d = `M ${x1} ${y1} H ${x1 - GAP_X / 2} V ${ym} H ${x2 + GAP_X / 2} V ${y2} H ${x2}`
    }
    paths.push(d)
  }
  wires.value = paths
}

/* ─── 缩放 / 平移 / 全屏 / Zoom / Pan / Fullscreen ─── */

/** 适应画布：整幅内容缩放进视口并居中 / Fit: scale content into the viewport, centered */
function autoFit() {
  const vp = viewportRef.value
  if (!vp) return
  const vw = vp.clientWidth - FIT_PAD * 2
  const vh = vp.clientHeight - FIT_PAD * 2
  if (vw <= 0 || vh <= 0) return
  const s = Math.min(vw / contentWidth.value, vh / contentHeight.value, 1)
  scale.value = Math.max(MIN_SCALE, s)
  fitScale.value = scale.value
  offsetX.value = (vp.clientWidth - contentWidth.value * scale.value) / 2
  offsetY.value = (vp.clientHeight - contentHeight.value * scale.value) / 2
}

/** 以视口中心为锚点缩放 / Zoom anchored at viewport center */
function zoomBy(delta: number) {
  const vp = viewportRef.value
  if (!vp) return
  const prev = scale.value
  const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, prev + delta))
  if (next === prev) return
  const cx = vp.clientWidth / 2
  const cy = vp.clientHeight / 2
  // 保持视口中心对应的场景坐标不动 / Keep the scene point under the viewport center fixed
  offsetX.value = cx - ((cx - offsetX.value) / prev) * next
  offsetY.value = cy - ((cy - offsetY.value) / prev) * next
  scale.value = next
}

let panStart: { x: number; y: number; ox: number; oy: number } | null = null
function onPanStart(e: PointerEvent) {
  if (!pannable.value) return
  // 芯片上不劫持点击 / Do not hijack chip interactions
  if ((e.target as HTMLElement).closest('.insight-flow-chip')) return
  panStart = { x: e.clientX, y: e.clientY, ox: offsetX.value, oy: offsetY.value }
  window.addEventListener('pointermove', onPanMove)
  window.addEventListener('pointerup', onPanEnd)
}
function onPanMove(e: PointerEvent) {
  if (!panStart) return
  offsetX.value = panStart.ox + (e.clientX - panStart.x)
  offsetY.value = panStart.oy + (e.clientY - panStart.y)
}
function onPanEnd() {
  panStart = null
  window.removeEventListener('pointermove', onPanMove)
  window.removeEventListener('pointerup', onPanEnd)
}

const isFullscreen = ref(false)
function toggleFullscreen() {
  const el = rootRef.value
  if (!el) return
  if (document.fullscreenElement) {
    document.exitFullscreen().catch(() => { /* 浏览器拒绝时忽略 */ })
  } else {
    el.requestFullscreen().catch(() => { /* 不支持全屏时忽略 */ })
  }
}
function onFsChange() {
  isFullscreen.value = document.fullscreenElement === rootRef.value
  // 尺寸变化后重新适应 / Re-fit after container resize
  nextTick(() => { measure().then(autoFit) })
}

/* ─── 芯片交互 / Chip behavior ─── */
function onChipClick(step: InsightStep) {
  if (step.beginTime > 0) emit('seekTo', step.beginTime)
}

function chipTooltip(step: InsightStep): string {
  return step.beginTime > 0
    ? `${step.label} (${formatFlowTime(step.beginTime)})`
    : step.label
}

/* ─── 生命周期 / Lifecycle ─── */
let resizeObserver: ResizeObserver | null = null

watch(() => props.data, () => {
  measure().then(autoFit)
}, { deep: true })

onMounted(() => {
  measure().then(autoFit)
  if (viewportRef.value && typeof ResizeObserver !== 'undefined') {
    // 容器宽度变化（并排态拖拽等）时重新适应 / Re-fit when viewport width changes (side-by-side resize etc.)
    resizeObserver = new ResizeObserver(() => autoFit())
    resizeObserver.observe(viewportRef.value)
  }
  document.addEventListener('fullscreenchange', onFsChange)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  document.removeEventListener('fullscreenchange', onFsChange)
  onPanEnd()
})
</script>
