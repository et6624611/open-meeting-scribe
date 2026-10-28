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
import { isDarkThemeId, normalizeMermaidSvg, renderMermaidToSvg } from '@/utils/renderMermaid'

const props = defineProps<{
  /** Mermaid 图语法 / Mermaid diagram syntax */
  code: string
}>()

const containerRef = ref<HTMLElement | null>(null)
const svgRef = ref<HTMLElement | null>(null)
const loading = ref(false)
const error = ref('')

const themeStore = useThemeStore()

/**
 * 渲染 Mermaid 图（渲染管线共用 utils/renderMermaid，本组件只管装载与错误态） /
 * Render via the shared pipeline (utils/renderMermaid); this component only owns mounting and error state
 */
async function renderDiagram() {
  if (!props.code || !svgRef.value) return

  loading.value = true
  error.value = ''
  // 先持有容器引用：loading 切换触发重渲染时容器仍常驻（v-show），引用不会失效 / Hold container ref up front: v-show keeps it mounted across the loading re-render
  const target = svgRef.value

  try {
    const { svg, bindFunctions } = await renderMermaidToSvg(props.code, isDarkThemeId(themeStore.current))
    target.innerHTML = svg
    // 尺寸归一化：按 viewBox 自然尺寸 1:1 显示（图内字号恒定），仅超容器时等比收窄 / Normalize sizing: natural 1:1 (constant font size), shrink only beyond container
    const svgEl = target.querySelector('svg')
    if (svgEl) normalizeMermaidSvg(svgEl)
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
