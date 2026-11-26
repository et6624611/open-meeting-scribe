/**
 * Mermaid 渲染共享工具 / Shared mermaid render util
 *
 * MermaidDiagram 组件与 InsightBoard 板内嵌 pre.ib-mermaid 块共用一条渲染管线：
 * 动态 import（不增首屏体积）、按明暗主题 initialize（幂等缓存，主题切换时重建）、
 * 15s 超时、唯一 id 防并发冲突。调用方负责把返回的 SVG 字符串写入自己的容器，
 * 并决定是否 bindFunctions（InsightBoard 不绑定，click 语句天然失效）。
 */
/** mermaid default export 的类型 / Type of mermaid's default export */
type MermaidApi = (typeof import('mermaid'))['default']

/** 深色主题列表（匹配 theme store 中的 id） / Dark theme IDs (matching theme store ids) */
const DARK_THEMES = new Set(['standard-dark', 'dark', 'forest', 'moonlight'])

/** 判断主题 id 是否为深色 / Check if a theme id is dark */
export function isDarkThemeId(themeId: string): boolean {
  return DARK_THEMES.has(themeId)
}

/** Mermaid 渲染超时时间（毫秒） / Mermaid render timeout (ms) */
const RENDER_TIMEOUT_MS = 15_000

let mermaidPromise: Promise<MermaidApi> | null = null
let initializedForDark: boolean | null = null
let renderCounter = 0

/**
 * 取 mermaid 单例并按当前明暗主题完成初始化 / Get mermaid singleton initialized for current theme
 */
async function ensureMermaid(isDark: boolean): Promise<MermaidApi> {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then(m => m.default)
  }
  const mermaid = await mermaidPromise
  if (initializedForDark === isDark) return mermaid
  // 不使用 'strict'：strict 会创建 sandbox iframe，跨域访问 contentDocument 报错 / avoid 'strict': sandbox iframe throws on contentDocument access
  // htmlLabels 必须关闭：HTML 标签不随 viewBox 缩放，放大后文字溢出裁切 / htmlLabels off: HTML labels clip after enlargement
  mermaid.initialize({
    startOnLoad: false,
    // 关闭 mermaid 自带的错误图形：解析失败时它会把炸弹 SVG 画进 body 尾部残留且不清理 / Disable built-in error graphic: on parse failure it leaves a bomb SVG in body
    suppressErrorRendering: true,
    theme: isDark ? 'dark' : 'default',
    securityLevel: 'loose',
    flowchart: { htmlLabels: false, curve: 'basis' },
    themeVariables: { fontFamily: 'inherit', fontSize: '14px' },
  })
  initializedForDark = isDark
  return mermaid
}

/**
 * 渲染 mermaid 源码为 SVG 字符串 / Render mermaid source to an SVG string
 * 不传容器元素：mermaid 在 document.body 创建临时 DOM 渲染，返回 SVG 字符串由调用方写入，
 * 避免 mermaid 直接渲染进 target 与后续 innerHTML 赋值冲突。
 */
export async function renderMermaidToSvg(
  code: string,
  isDark: boolean,
): Promise<{ svg: string; bindFunctions?: (el: HTMLElement) => void }> {
  const mermaid = await ensureMermaid(isDark)
  const id = `mermaid-${Date.now()}-${++renderCounter}`
  const renderPromise = mermaid.render(id, code)
  const timeoutPromise = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error('Mermaid render timeout')), RENDER_TIMEOUT_MS)
  )
  const { svg, bindFunctions } = await Promise.race([renderPromise, timeoutPromise])
  return { svg, bindFunctions }
}

/**
 * 归一化 mermaid 输出的 SVG 尺寸 / Normalize mermaid SVG sizing
 *
 * mermaid 输出带 width="100%" 属性 + 固定 height + 内联 max-width。若直接强制
 * 容器宽，viewBox 等比缩放会把窄图文字放大、宽图文字缩没；而 svg 去掉 width
 * 属性后按规范默认宽=容器 100%，同样拉满。故显式设 viewBox 像素宽，按自然尺寸
 * 1:1 显示（图内字号恒定等于 themeVariables.fontSize），仅超出容器时由
 * max-width:100% 等比收窄。
 */
export function normalizeMermaidSvg(svgEl: SVGSVGElement): void {
  const vbWidth = svgEl.viewBox?.baseVal?.width ?? 0
  svgEl.removeAttribute('width')
  svgEl.removeAttribute('height')
  svgEl.style.width = vbWidth > 0 ? `${vbWidth}px` : 'auto'
  svgEl.style.height = 'auto'
  svgEl.style.maxWidth = '100%'
}
