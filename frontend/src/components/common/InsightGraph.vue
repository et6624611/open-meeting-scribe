<template>
  <div class="insight-graph" ref="containerRef">
    <div v-if="error" class="insight-graph-error">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      <span>{{ error }}</span>
    </div>
    <div v-if="loading && !error" class="insight-graph-loading">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
    </div>
    <div v-show="!error && !loading" class="insight-graph-canvas" ref="canvasRef"></div>
    <!-- 节点信息 tooltip / Node info tooltip -->
    <div v-if="tooltipVisible" class="insight-graph-tooltip" :style="tooltipStyle">
      {{ tooltipText }}
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 交互式知识图谱组件 / Interactive knowledge graph component
 *
 * 使用 AntV G6 渲染结构化节点-边图谱。 / Renders structured node-edge graph using AntV G6.
 * 节点携带 begin_time 时，点击可跳转到转写原文对应位置。 / When nodes carry begin_time, clicking seeks to the corresponding transcript position.
 * 支持力导向布局、拖拽、缩放、主题适配。 / Supports force layout, drag, zoom, theme adaptation.
 */
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { useThemeStore } from '@/stores/theme'
import type { InsightGraphData } from '@/api/insights'

const props = defineProps<{
  /** 图谱数据 / Graph data */
  data: InsightGraphData
}>()

const emit = defineEmits<{
  /** 点击节点时触发跳转（begin_time > 0 时） / Emitted on node click (when begin_time > 0) */
  (e: 'seekTo', ms: number): void
}>()

const containerRef = ref<HTMLElement | null>(null)
const canvasRef = ref<HTMLElement | null>(null)
const loading = ref(false)
const error = ref('')

const themeStore = useThemeStore()

/** 深色主题列表 / Dark theme IDs */
const DARK_THEMES = new Set(['standard-dark', 'dark', 'forest', 'moonlight'])

function isDarkTheme(): boolean {
  return DARK_THEMES.has(themeStore.current)
}

/** 节点 begin_time 索引（id → ms） / Node begin_time index (id → ms) */
const beginTimeMap = computed(() => {
  const map = new Map<string, number>()
  for (const n of props.data.nodes) {
    map.set(n.id, n.begin_time ?? 0)
  }
  return map
})

/** 节点标签索引 / Node label index */
const labelMap = computed(() => {
  const map = new Map<string, string>()
  for (const n of props.data.nodes) {
    map.set(n.id, n.label || n.id)
  }
  return map
})

/* ─── Tooltip 状态 / Tooltip state ─── */
const tooltipVisible = ref(false)
const tooltipStyle = ref<Record<string, string>>({})
const tooltipText = ref('')

let graph: any = null

/**
 * 获取主题色 / Get theme colors
 */
function getThemeColors() {
  const dark = isDarkTheme()
  return {
    nodeFill: dark ? '#3b3f5a' : '#e8eaf6',
    nodeStroke: dark ? '#7c83c4' : '#5c6bc0',
    nodeLabel: dark ? '#e0e0e0' : '#333333',
    edgeStroke: dark ? '#555' : '#bbb',
    edgeLabel: dark ? '#999' : '#666',
    hoverStroke: dark ? '#a0a8e0' : '#3949ab',
    selectedFill: dark ? '#4a5080' : '#c5cae9',
  }
}

/**
 * 初始化并渲染 G6 图谱 / Initialize and render G6 graph
 */
async function renderGraph() {
  if (!props.data?.nodes?.length || !canvasRef.value) return

  loading.value = true
  error.value = ''

  try {
    const { Graph } = await import('@antv/g6')
    const colors = getThemeColors()

    // 销毁旧实例 / Destroy old instance
    if (graph) {
      graph.destroy()
      graph = null
    }

    // 构造 G6 数据 / Build G6 data
    const g6Data = {
      nodes: props.data.nodes.map(n => ({
        id: n.id,
        data: { begin_time: n.begin_time ?? 0, label: n.label },
        style: {
          labelText: n.label || n.id,
          labelFill: colors.nodeLabel,
          labelFontSize: 11,
          labelPlacement: 'bottom' as const,
          labelMaxWidth: 80,
          size: 32,
          fill: colors.nodeFill,
          stroke: colors.nodeStroke,
          lineWidth: 1.5,
        },
      })),
      edges: props.data.edges.map((e, i) => ({
        id: `e-${i}`,
        source: e.from,
        target: e.to,
        data: { label: e.label },
        style: {
          stroke: colors.edgeStroke,
          lineWidth: 1,
          endArrow: true,
          endArrowSize: 6,
          labelText: e.label || '',
          labelFill: colors.edgeLabel,
          labelFontSize: 9,
          labelBackground: true,
          labelBackgroundFill: isDarkTheme() ? '#2a2d3e' : '#f5f5f5',
          labelBackgroundPadding: [2, 4, 2, 4],
        },
      })),
    }

    graph = new Graph({
      container: canvasRef.value,
      data: g6Data,
      autoFit: 'view',
      node: {
        style: {
          lineWidth: 1.5,
        },
        state: {
          active: {
            stroke: colors.hoverStroke,
            lineWidth: 2.5,
          },
          selected: {
            fill: colors.selectedFill,
            stroke: colors.hoverStroke,
            lineWidth: 2,
          },
        },
      },
      edge: {
        style: {
          lineWidth: 1,
        },
        state: {
          active: {
            stroke: colors.hoverStroke,
            lineWidth: 2,
          },
        },
      },
      layout: {
        type: 'dagre',
        rankdir: 'LR',
        nodesep: 40,
        ranksep: 80,
      },
      behaviors: [
        'drag-canvas',
        {
          type: 'drag-element',
          enable: () => true,
        },
        'zoom-canvas',
        {
          type: 'hover-activate',
          state: 'active',
        },
      ],
      animation: false,
    })

    // 节点点击 → 跳转 / Node click → seek
    graph.on('node:click', (evt: any) => {
      const nodeId = evt.target?.id
      if (!nodeId) return
      const bt = beginTimeMap.value.get(nodeId)
      if (bt && bt > 0) {
        emit('seekTo', bt)
      }
    })

    // 节点 hover → tooltip / Node hover → tooltip
    graph.on('node:pointerenter', (evt: any) => {
      const nodeId = evt.target?.id
      if (!nodeId) return
      const label = labelMap.value.get(nodeId) || nodeId
      const bt = beginTimeMap.value.get(nodeId) || 0
      tooltipText.value = bt > 0
        ? `${label} (${formatTime(bt)})`
        : label
      tooltipVisible.value = true
      // 定位到鼠标附近 / Position near cursor
      const { client } = evt
      if (client && containerRef.value) {
        const rect = containerRef.value.getBoundingClientRect()
        tooltipStyle.value = {
          left: `${client.x - rect.left + 12}px`,
          top: `${client.y - rect.top - 8}px`,
        }
      }
    })

    graph.on('node:pointerleave', () => {
      tooltipVisible.value = false
    })

    await graph.render()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Graph render failed'
    console.warn('[InsightGraph] Render failed:', e)
  } finally {
    loading.value = false
  }
}

function formatTime(ms: number): string {
  const totalSec = Math.floor(ms / 1000)
  const min = Math.floor(totalSec / 60)
  const sec = totalSec % 60
  return `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

// 监听数据变化 / Watch data changes
watch(() => props.data, () => {
  renderGraph()
}, { deep: true })

// 监听主题变化 / Watch theme changes
watch(() => themeStore.current, () => {
  renderGraph()
})

onMounted(() => {
  if (props.data?.nodes?.length) {
    renderGraph()
  }
})

onUnmounted(() => {
  if (graph) {
    graph.destroy()
    graph = null
  }
})
</script>
