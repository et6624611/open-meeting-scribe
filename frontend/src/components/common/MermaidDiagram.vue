<template>
  <div class="mermaid-diagram" ref="containerRef">
    <div v-if="error" class="mermaid-diagram-error">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      <span>{{ error }}</span>
    </div>
    <div v-if="loading && !error" class="mermaid-diagram-loading">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
    </div>
    <!-- SVG 容器常驻 DOM（v-show）：若用 v-else，异步渲染期间 loading 切换会卸载容器使 svgRef 置空，渲染结果丢失 / Keep SVG container mounted (v-show): with v-else the loading toggle unmounts it mid-render, nulling svgRef and losing the result -->
    <div v-show="!error && !loading" class="mermaid-diagram-svg" ref="svgRef"></div>
  </div>
</template>

<script setup lang="ts">
/**
 * Mermaid 图表渲染组件 / Mermaid diagram rendering component
 *
 * 接收 Mermaid 语法的 code prop，异步渲染为 SVG 图表。 / Accepts Mermaid syntax code prop, renders as SVG diagram asynchronously.
 * 自动适配亮色/暗色主题，渲染失败时降级显示错误提示。 / Auto-adapts to light/dark theme; falls back to error message on render failure.
 */
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useThemeStore } from '@/stores/theme'

const props = defineProps<{
  /** Mermaid 图语法 / Mermaid diagram syntax */
  code: string
}>()

const containerRef = ref<HTMLElement | null>(null)
const svgRef = ref<HTMLElement | null>(null)
const loading = ref(false)
const error = ref('')

const themeStore = useThemeStore()

/** 深色主题列表（匹配 theme store 中的 id） / Dark theme IDs (matching theme store ids) */
const DARK_THEMES = new Set(['standard-dark', 'dark', 'forest', 'moonlight'])

let renderCounter = 0

/**
 * 判断当前是否为深色主题 / Check if current theme is dark
 */
function isDarkTheme(): boolean {
  return DARK_THEMES.has(themeStore.current)
}

/** Mermaid 渲染超时时间（毫秒） / Mermaid render timeout (ms) */
const RENDER_TIMEOUT_MS = 15_000

/**
 * 渲染 Mermaid 图 / Render Mermaid diagram
 */
async function renderDiagram() {
  if (!props.code || !svgRef.value) return

  loading.value = true
  error.value = ''
  // 先持有容器引用：loading 切换触发重渲染时容器仍常驻（v-show），引用不会失效 / Hold container ref up front: v-show keeps it mounted across the loading re-render
  const target = svgRef.value

  try {
    const mermaid = (await import('mermaid')).default

    // 初始化配置（每次渲染前重新初始化以确保主题一致） / Initialize config (re-initialize before each render to ensure theme consistency)
    // 注意：不使用 'strict'，strict 模式会创建 sandbox iframe 导致跨域访问 contentDocument 报错 / Note: avoid 'strict' — it creates a sandbox iframe whose contentDocument access throws cross-origin error
    mermaid.initialize({
      startOnLoad: false,
      theme: isDarkTheme() ? 'dark' : 'default',
      securityLevel: 'loose',
      flowchart: {
        // 必须关闭 htmlLabels：开启时节点文字是 foreignObject 内 HTML，按临时容器（body 全宽）布局且不随 viewBox 缩放，
        // 导致图放大后文字溢出裁切；关闭后文字为纯 SVG text，与图形同步等比缩放
        // htmlLabels must stay off: HTML labels don't reflow with viewBox scaling and clip after enlargement; SVG text scales in lockstep with shapes
        htmlLabels: false,
        curve: 'basis',
      },
      themeVariables: {
        fontFamily: 'inherit',
        fontSize: '12px',
      },
    })

    // 生成唯一 ID 避免多次渲染冲突 / Generate unique ID to avoid conflicts from multiple renders
    const id = `mermaid-${Date.now()}-${++renderCounter}`

    // 不传容器元素：mermaid 在 document.body 创建临时 DOM 渲染，返回 SVG 字符串后我们再写入 target / Don't pass container: mermaid renders to document.body temp DOM, returns SVG string which we then write to target
    // 传入 target 会导致 mermaid 直接渲染到 target 中，与后续 target.innerHTML = svg 冲突 / Passing target causes mermaid to render directly into it, conflicting with the subsequent innerHTML assignment
    const renderPromise = mermaid.render(id, props.code)
    const timeoutPromise = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('Mermaid render timeout')), RENDER_TIMEOUT_MS)
    )
    const { svg, bindFunctions } = await Promise.race([renderPromise, timeoutPromise])
    target.innerHTML = svg
    // 移除尺寸限制：mermaid 按文字自然尺寸输出固定高和内联 max-width，两者都会阻止图表随容器宽度等比放大（CSS 侧 width:100%; height:auto 依赖 viewBox 缩放） / Strip size constraints: intrinsic height and inline max-width both block proportional scaling to container width
    const svgEl = target.querySelector('svg')
    if (svgEl) {
      svgEl.removeAttribute('height')
      svgEl.style.maxWidth = ''
    }
    bindFunctions?.(target)
  } catch (e) {
    // 渲染失败时显示错误信息 / Show error message on render failure
    error.value = e instanceof Error ? e.message : 'Diagram render failed'
    console.warn('[MermaidDiagram] Render failed:', e)
  } finally {
    loading.value = false
  }
}

// 监听 code 变化，重新渲染 / Watch code changes, re-render
watch(() => props.code, () => {
  renderDiagram()
})

// 监听主题变化，重新渲染 / Watch theme changes, re-render
watch(() => themeStore.current, () => {
  renderDiagram()
})

onMounted(() => {
  if (props.code) {
    renderDiagram()
  }
})

onUnmounted(() => {
  // 清理 DOM 内容防止内存泄漏 / Clean up DOM content to prevent memory leaks
  if (svgRef.value) {
    svgRef.value.innerHTML = ''
  }
})
</script>
