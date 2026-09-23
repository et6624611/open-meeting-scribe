<template>
  <div class="insight-graph">
    <svg class="insight-graph-svg" :viewBox="`0 0 ${width} ${height}`" fill="none" role="img">
      <!-- 边：直角连线 + 关系标签 / Edges: right-angle wires with relation labels -->
      <g v-for="(e, i) in edgeGeoms" :key="`e${i}`">
        <path :d="e.d" />
        <text v-if="e.label" :x="e.mx" :y="e.my - 4" class="insight-graph-edge-label">{{ e.label }}</text>
      </g>
      <!-- 节点：圆点 + 标签 / Nodes: dots with labels -->
      <g
        v-for="n in nodeGeoms" :key="n.id"
        :class="{ 'is-seekable': n.beginTime > 0 }"
        :transform="`translate(${n.x}, ${n.y})`"
        @click="n.beginTime > 0 && emit('seekTo', n.beginTime)"
        @mouseenter="hover = { text: n.tip, x: n.x, y: n.y }"
        @mouseleave="hover = null"
      >
        <circle r="9" stroke-width="1.5" />
        <text y="24" class="insight-graph-node-label">{{ n.label }}</text>
      </g>
    </svg>
    <!-- 节点信息 tooltip / Node info tooltip -->
    <div v-if="hover" class="insight-graph-tooltip" :style="{ left: `${hover.x}px`, top: `${hover.y - 18}px` }">
      {{ hover.text }}
    </div>
  </div>
</template>

<script lang="ts">
/** 旧版图谱数据契约（供调用方历史消息转型使用） / Legacy graph contract (for callers casting historical messages) */
export interface InsightLegacyGraphData {
  nodes: Array<{ id: string; label?: string; begin_time?: number }>
  edges: Array<{ from: string; to: string; label?: string }>
}
</script>

<script setup lang="ts">
/**
 * 旧版结构化知识图谱（历史会话兼容） / Legacy structured knowledge graph (historical session compatibility)
 *
 * 原基于 AntV G6 的交互式图谱已随画布改造下线（@antv/g6 依赖移除）。
 * 本组件重写为零依赖的静态 SVG 渲染：仅保留节点点击跳转转写（seekTo）
 * 与 hover tooltip，不再支持力导向布局/拖拽/缩放。新分析不再产出 graph 数据，
 * 仅历史会话消息重载时会命中本组件。
 * The G6-based interactive graph was retired with the canvas restyle (@antv/g6 removed).
 * This component is now a dependency-free static SVG render keeping only node click → seekTo
 * and hover tooltips; no force layout/drag/zoom. New analyses never emit graph data —
 * only reloaded historical messages reach this component.
 */
import { computed, ref } from 'vue'

/** 图谱数据（与旧后端契约一致） / Graph data (aligned with the legacy backend contract) */
type LegacyGraphData = InsightLegacyGraphData

const props = defineProps<{
  /** 图谱数据 / Graph data */
  data: LegacyGraphData
}>()

const emit = defineEmits<{
  /** 点击节点时触发跳转（begin_time > 0 时） / Emitted on node click (when begin_time > 0) */
  (e: 'seekTo', ms: number): void
}>()

const COL_W = 150
const ROW_H = 64
const PAD = 28

const hover = ref<{ text: string; x: number; y: number } | null>(null)

interface NodeGeom { id: string; x: number; y: number; label: string; beginTime: number; tip: string }

/** 按拓扑深度分层的节点坐标 / Node coordinates layered by topological depth */
const nodeGeoms = computed<NodeGeom[]>(() => {
  const nodes = props.data?.nodes ?? []
  const edges = props.data?.edges ?? []
  const ids = nodes.map(n => n.id)
  const depth = new Map<string, number>()
  ids.forEach(id => depth.set(id, 0))
  // 松弛迭代求最长路径深度（限次防环） / Bellman-style relaxation, capped to survive cycles
  for (let iter = 0; iter < ids.length; iter++) {
    let changed = false
    for (const e of edges) {
      if (!depth.has(e.from) || !depth.has(e.to)) continue
      if (depth.get(e.to)! < depth.get(e.from)! + 1) {
        depth.set(e.to, depth.get(e.from)! + 1)
        changed = true
      }
    }
    if (!changed) break
  }
  const rows = new Map<number, number>()
  return nodes.map(n => {
    const d = depth.get(n.id) ?? 0
    const row = rows.get(d) ?? 0
    rows.set(d, row + 1)
    const label = (n.label || n.id).slice(0, 10)
    const bt = n.begin_time ?? 0
    return {
      id: n.id,
      x: PAD + d * COL_W,
      y: PAD + row * ROW_H,
      label,
      beginTime: bt,
      tip: bt > 0 ? `${label} (${formatTime(bt)})` : label,
    }
  })
})

const edgeGeoms = computed(() => {
  const byId = new Map(nodeGeoms.value.map(n => [n.id, n]))
  const out: Array<{ d: string; mx: number; my: number; label: string }> = []
  for (const e of props.data?.edges ?? []) {
    const a = byId.get(e.from)
    const b = byId.get(e.to)
    if (!a || !b) continue
    const x1 = a.x + 12, x2 = b.x - 12
    const xm = (x1 + x2) / 2
    out.push({
      d: `M ${x1} ${a.y} H ${xm} V ${b.y} H ${x2}`,
      mx: xm,
      my: (a.y + b.y) / 2,
      label: e.label ?? '',
    })
  }
  return out
})

const width = computed(() => {
  const xs = nodeGeoms.value.map(n => n.x)
  return Math.max(...xs, 0) + PAD * 2
})
const height = computed(() => {
  const ys = nodeGeoms.value.map(n => n.y)
  return Math.max(...ys, 0) + PAD * 2 + 14
})

function formatTime(ms: number): string {
  const totalSec = Math.floor(ms / 1000)
  const min = Math.floor(totalSec / 60)
  const sec = totalSec % 60
  return `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}
</script>
