/**
 * 聊天 & 洞察板共用的 Markdown + Mermaid 渲染管线
 *
 * 职责：
 * 1. 安全优先：先对原文做 escapeHtml（防 XSS），同时保护 mermaid fence 和 HTML 注释；
 * 2. marked 解析 GFM 语法（支持调用方传自定义 Renderer，如 InsightBoard 的 heading id）；
 * 3. mermaid fence 输出占位 <pre data-mermaid-src="...">，调用方在 DOM 后处理里
 *    调 renderMermaidToSvg 异步渲 SVG 替换。
 *
 * 为什么不直接在这一步渲 mermaid？
 * mermaid.render() 是异步的，会往 document.body 挂临时节点，纯字符串管线做不了。
 * 必须渲染后 DOM 后处理（marked 输出 HTML → 插入 DOM → 扫占位符 → 渲 SVG → 替换）。
 */
import { marked } from 'marked'
import { escapeHtml } from './sanitize'

marked.setOptions({
  gfm: true,
  breaks: true,
})

/** marked.Renderer 实例类型（marked 18 的泛型类型极复杂，此处用 any 简化） */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type MarkedRenderer = any

/** mermaid fence 正则（捕获 fence 内源码） */
const MERMAID_FENCE_RE = /```mermaid\s*\n([\s\S]*?)```/g
/** HTML 注释正则（用于 InsightBoard 的 <!-- section-id: ... --> 注释锚点） */
const HTML_COMMENT_RE = /<!--[\s\S]*?-->/g

/**
 * 渲染 markdown 为 HTML 字符串（含 mermaid 占位符）
 *
 * 安全顺序：先提 mermaid fence + HTML 注释 → 对剩余文本 escapeHtml → 还回所有占位
 * → marked.parse。这样 HTML 注入被 escapeHtml 防住，mermaid 源码和 HTML 注释保持原样。
 *
 * @param md 原始 markdown 文本
 * @param renderer 可选的自定义 marked.Renderer（如 InsightBoard 需要 heading 带 id）
 */
export function renderMarkdownWithMermaid(
  md: string,
  renderer?: MarkedRenderer,
): string {
  // 占位符计数器和存储
  const placeholders: string[] = []
  // 使用 \x01\x02 等不常见的控制字符作为前缀，避免与正文冲突
  const PREFIX = '\x01'
  const SUFFIX = '\x02'

  // 1. 提取 mermaid fence → \x01MMD_N\x02
  let text = md.replace(MERMAID_FENCE_RE, (_m, inner: string) => {
    const idx = placeholders.length
    placeholders.push(String(inner).trim())
    return `${PREFIX}MMD_${idx}${SUFFIX}`
  })

  // 2. 提取 HTML 注释 → \x01CMT_N\x02（InsightBoard 用来扫 section-id 锚点）
  text = text.replace(HTML_COMMENT_RE, (m) => {
    const idx = placeholders.length
    placeholders.push(m)
    return `${PREFIX}CMT_${idx}${SUFFIX}`
  })

  // 3. 对非占位符部分 escapeHtml（防 XSS）
  const safe = escapeHtml(text)

  // 4. 恢复占位符：escapeHtml 不会修改 \x01 和 \x02，占位符形态不变
  //    但注意 placeholders 里的内容——mermaid 源码和 HTML 注释在提取时已脱离原文，
  //    没有被 escapeHtml 处理，是原始文本。marked.parse 时 HTML 注释会正常保留。
  let html = marked.parse(safe, renderer ? { renderer } : undefined) as string

  // 5. mermaid 占位符 → <pre data-mermaid-src="..."> 供后处理扫描
  //    占位符在 marked.parse 后可能被包裹进 <p> 里，所以正则要宽松匹配
  html = html.replace(new RegExp(`<p>\\s*${PREFIX}MMD_(\\d+)${SUFFIX}\\s*</p>`, 'g'), (_m, idx) =>
    `<pre class="md-mermaid-src" data-mermaid-src="${escapeAttr(placeholders[Number(idx)])}"></pre>`
  )
  html = html.replace(new RegExp(`${PREFIX}MMD_(\\d+)${SUFFIX}`, 'g'), (_m, idx) =>
    `<pre class="md-mermaid-src" data-mermaid-src="${escapeAttr(placeholders[Number(idx)])}"></pre>`
  )

  // 6. HTML 注释占位符恢复
  html = html.replace(new RegExp(`${PREFIX}CMT_(\\d+)${SUFFIX}`, 'g'), (_m, idx) =>
    placeholders[Number(idx)]
  )

  return html
}

function escapeAttr(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}

/**
 * mermaid 源码 → SVG 缓存：相同源码（trim 后）只渲一次
 *
 * 为什么需要？AiMessageList 用 v-html 渲染流式输出，每次 content 变化都会重置 DOM，
 * 导致已渲好的 SVG 被新的占位符替换回去。缓存让相同源码跳过 renderMermaidToSvg 直接复用 SVG。
 */
const _mermaidSvgCache = new Map<string, string>()

/** 清空缓存（主题切换时调，因为 mermaid 明暗主题渲出来的 SVG 不同） */
export function clearMermaidCache(): void {
  _mermaidSvgCache.clear()
}

/**
 * DOM 后处理：扫描 root 下的 pre.md-mermaid-src，异步渲 SVG 替换
 *
 * 被 InsightBoard 和 AiMessageList 共用。
 * @param root 要扫描的容器元素
 * @param isDark 当前是否深色主题
 */
export async function postProcessMermaid(
  root: HTMLElement,
  isDark: boolean,
): Promise<void> {
  const preNodes = root.querySelectorAll('pre.md-mermaid-src')
  if (preNodes.length === 0) return
  const { renderMermaidToSvg, normalizeMermaidSvg } = await import('./renderMermaid')
  for (const pre of Array.from(preNodes)) {
    const src = (pre.getAttribute('data-mermaid-src') || '').trim()
    if (!src) continue
    let svg = _mermaidSvgCache.get(src)
    if (!svg) {
      try {
        const r = await renderMermaidToSvg(src, isDark)
        svg = r.svg
        if (!svg) continue
        _mermaidSvgCache.set(src, svg)
      } catch (e) {
        console.warn('[md] mermaid render failed:', e)
        pre.className = 'md-mermaid-error'
        pre.removeAttribute('data-mermaid-src')
        continue
      }
    }
    const box = document.createElement('div')
    box.className = 'md-mermaid-box'
    box.innerHTML = svg
    const svgEl = box.querySelector('svg')
    if (svgEl) normalizeMermaidSvg(svgEl)
    pre.replaceWith(box)
  }
}
