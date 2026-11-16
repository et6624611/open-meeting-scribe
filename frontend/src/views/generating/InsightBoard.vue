<template>
  <div class="ib-root" ref="rootEl">
    <!-- 板头：rev 角标 + 刷新 + 浏览器打开 + 共创起跳 -->
    <header v-if="artifact.markdown" class="ib-head">
      <span class="ib-eyebrow">{{ t('generating.insights.board.eyebrow') }}</span>
      <span class="ib-rev" :class="{ 'is-bumped': revBumped }">rev {{ artifact.revision }}</span>
      <span class="ib-head-spacer"></span>
      <button class="ib-tool-btn" :disabled="loading" @click="emit('refresh')">
        {{ loading ? t('generating.insights.board.loading') : t('generating.insights.board.refresh') }}
      </button>
      <button class="ib-tool-btn" @click="emit('openInBrowser')">
        {{ t('generating.insights.board.open_in_browser') }}
      </button>
      <button class="ib-tool-btn is-primary" @click="emit('coCreate')">
        {{ t('generating.insights.board.co_create') }}
      </button>
    </header>

    <!-- 空态 -->
    <div v-if="!artifact.markdown" class="ib-empty">
      <EmptyHint card :title="t('generating.insights.board.empty_title')" :body="t('generating.insights.board.empty_body')">
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.35"/></svg>
        </template>
        <template #action>
          <button class="btn btn-primary" @click="emit('coCreate')">
            {{ t('generating.insights.board.co_create') }}
          </button>
        </template>
      </EmptyHint>
    </div>

    <!-- Markdown 渲染容器：直接挂 DOM，不再 iframe 桥接 -->
    <article
      v-if="artifact.markdown"
      class="ib-md"
      ref="mdEl"
      v-html="renderedHtml"
      @click="onRootClick"
      @mouseenter="onSectionEnter"
      @mouseleave="onSectionLeave"
      @mousemove="onSectionMove"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 洞察板 Markdown 渲染器 / Insight Board Markdown renderer
 *
 * 2026-11-12 重构：不再 sandbox iframe + postMessage 桥接，改为 marked 直接渲染。
 * 职责：
 * 1. marked.parse 渲染 GFM + 自定义 renderer 处理 mermaid fence；
 * 2. DOM 后处理：
 *    - 扫描 HTML 注释锚点 <!-- section-id: s1 section-title: xxx -->，
 *      在紧邻的 h2/h3 上挂 data-section-id 属性；
 *    - ```mermaid fence → 调 renderMermaid 渲 SVG；
 *    - <a data-seek-ms="毫秒"> → 拦截 click 向上 emit('seek')；
 * 3. 悬停 section 高亮：鼠标进入某个 section 范围时，给整段 .ib-section 加高亮类；
 * 4. 版本前进时 rev 徽标脉冲提示。
 */
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { marked } from 'marked'
import { useI18n } from 'vue-i18n'
import EmptyHint from '@/components/common/EmptyHint.vue'
import { isDarkThemeId, renderMermaidToSvg } from '@/utils/renderMermaid'
import { useThemeStore } from '@/stores/theme'
import type { BoardArtifact } from '@/api/board'

const { t } = useI18n()
const themeStore = useThemeStore()

const props = defineProps<{
  artifact: BoardArtifact
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'seek', ms: number): void
  (e: 'refresh'): void
  (e: 'coCreate'): void
  (e: 'coCreateSection', sec: { id: string; title: string }): void
  (e: 'openInBrowser'): void
}>()

const rootEl = ref<HTMLElement | null>(null)
const mdEl = ref<HTMLElement | null>(null)

// ── Markdown → HTML（带 section 注释锚点处理） ──
/** 注释锚点正则（非全局，逐行匹配） */
const SECTION_COMMENT_RE = /<!--\s*section-id:\s*([\w-]+)(?:\s+section-title:\s*([^-]{1,120}?))?\s*-->/

/** 自定义 renderer：heading 抽文本 + 生成 id */
const renderer = new marked.Renderer()
renderer.heading = ({ tokens, depth }: { tokens: any; depth: number }) => {
  const headingText = typeof tokens === 'string'
    ? tokens
    : (tokens as any)?.map?.((t: any) => t.raw ?? t.text ?? '').join('') ?? ''
  const safeId = headingText.toLowerCase().replace(/[^\w\u4e00-\u9fa5]+/g, '-').replace(/^-|-$/g, '')
  return `<h${depth} id="${safeId}">${headingText}</h${depth}>`
}
// 保留 HTML 注释——marked 默认保留注释，我们在后处理里扫

marked.setOptions({
  gfm: true,
  breaks: true,
})

/** 把 mermaid fence 替换成占位 div，后处理时渲 SVG */
const _MERMAID_FENCE_RE = /```mermaid\s*\n([\s\S]*?)```/g

function renderMarkdown(md: string): string {
  // 先把 mermaid fence 换占位
  const placeholders: string[] = []
  const withPlaceholder = md.replace(_MERMAID_FENCE_RE, (_m, inner) => {
    const idx = placeholders.length
    placeholders.push(String(inner))
    return `\x00MMD_${idx}\x00`
  })
  // 渲染
  let html = marked.parse(withPlaceholder) as string
  // 占位符换回去：先收集所有注释锚点行（在 <p><!-- section-id... --></p> 里），
  // 让它们在渲染后的 HTML 里仍然保留
  html = html.replace(/\x00MMD_(\d+)\x00/g, (_m, idx) =>
    `<pre class="ib-mermaid-src" data-mermaid-src="${escapeAttr(placeholders[Number(idx)])}"></pre>`
  )
  return html
}

function escapeAttr(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}

const renderedHtml = computed(() => renderMarkdown(props.artifact.markdown || ''))

// ── DOM 后处理：mermaid 渲图 + section 锚点 + seek 接线 ──
watch(renderedHtml, async () => {
  await nextTick()
  applyPostProcessing()
})

async function applyPostProcessing() {
  const el = mdEl.value
  if (!el) return

  // 1. mermaid 渲 SVG
  const dark = isDarkThemeId(themeStore.activeTheme)
  const mermaidNodes = el.querySelectorAll('pre.ib-mermaid-src')
  for (const pre of Array.from(mermaidNodes)) {
    const src = (pre.getAttribute('data-mermaid-src') || '').trim()
    if (!src) continue
    try {
      const { svg } = await renderMermaidToSvg(src, dark)
      if (!svg) continue
      const container = document.createElement('div')
      container.className = 'ib-mermaid-box'
      container.dataset.mermaidSrc = src
      container.innerHTML = svg
      pre.replaceWith(container)
    } catch (e) {
      console.warn('[ib] mermaid render failed', e)
    }
  }

  // 2. 扫 HTML 注释锚点：<!-- section-id: s1 section-title: 审核阻塞 -->
  // marked 默认把注释留在 <p> 里，形态：<p><!-- section-id... --></p>
  // 我们把它作为 DOM 节点扫出来
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_COMMENT)
  const comments: Comment[] = []
  let cur: Node | null = walker.nextNode()
  while (cur) {
    comments.push(cur as Comment)
    cur = walker.nextNode()
  }
  for (const c of comments) {
    const m = SECTION_COMMENT_RE.exec(c.nodeValue || '')
    if (!m) continue
    const [, secId, secTitle] = m
    // 找到这个注释所在或紧邻的 section 范围
    // 策略：注释 → 其所在父节点 → 往后找第一个 h2/h3 作为 section 起点
    const parent = c.parentNode
    if (!parent) continue
    parent.removeChild(c)

    // 找 section 起点：向后遍历 sibling，第一个 h2/h3 或 mermaid 块
    let startEl: HTMLElement | null = null
    let node: Node | null = c.nextSibling
    while (node) {
      if (node.nodeType === 1) {
        const el2 = node as HTMLElement
        if (/^H[2-4]$/.test(el2.tagName)) { startEl = el2; break }
      }
      node = node.nextSibling
    }
    if (!startEl) continue

    // 包裹成 .ib-section
    wrapSection(startEl, secId, secTitle || '')
  }

  // 3. data-seek-ms 锚点：拦截 click
  el.querySelectorAll('a[data-seek-ms]').forEach(a => {
    a.addEventListener('click', (ev) => {
      const ms = Number((a as HTMLElement).getAttribute('data-seek-ms'))
      if (!Number.isNaN(ms) && ms > 0) {
        ev.preventDefault()
        emit('seek', ms)
      }
    })
  })
}

/** 把从 startEl 开始到下一个 h2/h3 之前的所有节点包成 .ib-section */
function wrapSection(startEl: HTMLElement, secId: string, secTitle: string) {
  const root = startEl.parentElement
  if (!root) return
  const wrap = document.createElement('section')
  wrap.className = 'ib-section'
  wrap.dataset.sectionId = secId
  if (secTitle) wrap.dataset.sectionTitle = secTitle
  wrap.dataset.ibId = secId  // 兼容老命名（悬停工具栏的 selector）

  // 收集要移动的节点：从 startEl 开始，直到遇到同层级的 h2/h3
  const nodes: Node[] = []
  let n: Node | null = startEl
  while (n) {
    nodes.push(n)
    const next: Node | null = n.nextSibling
    // 终止条件：同级下一个 h2/h3
    if (next && next.nodeType === 1) {
      const nxt = next as HTMLElement
      if (/^H[2-4]$/.test(nxt.tagName)) break
    }
    n = next
  }
  // 全部移进 wrap
  for (const n of nodes) wrap.appendChild(n)
  root.insertBefore(wrap, startEl)
}

// ── 根节点 click 委托（.ib-section 上的按钮） ──
function onRootClick(ev: MouseEvent) {
  const t = ev.target as HTMLElement
  // .ib-section 的某个快捷入口按钮（未来扩展用）
  if (t.classList?.contains('ib-section-cocreate')) {
    const sec = t.closest('.ib-section') as HTMLElement | null
    if (sec) {
      emit('coCreateSection', {
        id: sec.dataset.sectionId || '',
        title: sec.dataset.sectionTitle || '',
      })
    }
  }
}

// ── 悬停 section 高亮 + 浮层工具栏 ──
const hoveredSection = ref<HTMLElement | null>(null)
let hoverTimer: ReturnType<typeof setTimeout> | null = null

function _findSectionFromPoint(x: number, y: number): HTMLElement | null {
  const el = document.elementFromPoint(x, y) as HTMLElement | null
  return el?.closest('.ib-section') as HTMLElement | null
}

function onSectionEnter() { /* 鼠标移进根容器时，由 mousemove 驱动 */ }
function onSectionLeave() {
  if (hoverTimer) clearTimeout(hoverTimer)
  hoverTimer = setTimeout(() => {
    if (hoveredSection.value) hoveredSection.value.classList.remove('is-hovered')
    hoveredSection.value = null
  }, 100)
}
function onSectionMove(ev: MouseEvent) {
  const sec = _findSectionFromPoint(ev.clientX, ev.clientY)
  if (sec !== hoveredSection.value) {
    if (hoveredSection.value) hoveredSection.value.classList.remove('is-hovered')
    hoveredSection.value = sec
    if (sec) sec.classList.add('is-hovered')
  }
}

// ── rev 徽标脉冲 ──
const revBumped = ref(false)
let revBumpTimer: ReturnType<typeof setTimeout> | null = null
watch(() => props.artifact.revision, (next: number | null, prev: number | null) => {
  if (prev == null || next == null || next <= prev) return
  revBumped.value = true
  if (revBumpTimer) clearTimeout(revBumpTimer)
  revBumpTimer = setTimeout(() => { revBumped.value = false }, 1400)
})
onUnmounted(() => {
  if (revBumpTimer) clearTimeout(revBumpTimer)
  if (hoverTimer) clearTimeout(hoverTimer)
})
</script>

<style scoped>
/* ── 基础排版：GFM 常规色 + 紧凑字距 ── */
.ib-md {
  padding: 16px 24px 32px;
  font-size: 14px;
  line-height: 1.65;
  color: var(--fg);
  background: var(--surface);
  max-width: 960px;
  margin: 0 auto;
  word-wrap: anywhere;
}
.ib-md h1, .ib-md h2, .ib-md h3, .ib-md h4 {
  font-weight: 600;
  margin-top: 1.6em;
  margin-bottom: 0.5em;
  line-height: 1.35;
  color: var(--fg);
}
.ib-md h1 { font-size: 20px; }
.ib-md h2 { font-size: 16px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
.ib-md h3 { font-size: 14px; color: var(--fg-secondary); }
.ib-md p { margin: 0.6em 0; }
.ib-md ul, .ib-md ol { padding-left: 1.6em; margin: 0.4em 0; }
.ib-md li { margin: 0.15em 0; }
.ib-md a { color: var(--accent); text-decoration: none; }
.ib-md a:hover { text-decoration: underline; }
.ib-md code {
  background: var(--surface-2);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 0.9em;
}
.ib-md pre {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 14px;
  overflow-x: auto;
  font-size: 12.5px;
  line-height: 1.5;
}
.ib-md pre code { background: none; padding: 0; }
.ib-md blockquote {
  border-left: 3px solid var(--accent);
  padding: 6px 14px;
  color: var(--fg-muted);
  margin: 0.8em 0;
  background: var(--surface-2);
  border-radius: 0 6px 6px 0;
}
.ib-md table {
  border-collapse: collapse;
  margin: 0.8em 0;
  font-size: 13px;
}
.ib-md th, .ib-md td {
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
}
.ib-md th { background: var(--surface-2); font-weight: 600; color: var(--fg-secondary); }

/* ── section 结构 ── */
.ib-section {
  margin: 24px 0;
  padding: 16px 20px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  transition: border-color 120ms, box-shadow 120ms;
}
.ib-section.is-hovered {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 18%, transparent);
}
.ib-section > h2:first-child,
.ib-section > h3:first-child {
  margin-top: 0;
}

/* ── mermaid 图 ── */
.ib-mermaid-box {
  margin: 10px 0;
  overflow-x: auto;
  text-align: center;
}
.ib-mermaid-box svg {
  max-width: 100%;
  height: auto;
}

/* ── seek 锚点 ── */
.ib-md a[data-seek-ms] {
  display: inline-block;
  padding: 0 4px;
  font-size: 11px;
  color: var(--info);
  background: color-mix(in srgb, var(--info) 12%, transparent);
  border-radius: 3px;
  font-family: inherit;
}
.ib-md a[data-seek-ms]:hover { text-decoration: none; background: color-mix(in srgb, var(--info) 25%, transparent); }

/* ── 板头 ── */
.ib-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  position: sticky; top: 0; z-index: 10;
}
.ib-eyebrow { font-size: 11px; color: var(--fg-muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; }
.ib-rev { font-size: 11px; font-weight: 600; color: var(--fg-muted);
  padding: 2px 8px; background: var(--surface-2); border-radius: 10px; }
.ib-rev.is-bumped { color: var(--accent); }
.ib-head-spacer { flex: 1; }
.ib-tool-btn {
  font-size: 12px; padding: 4px 12px; border-radius: 4px;
  background: transparent; color: var(--fg-secondary);
  border: 1px solid var(--border); cursor: pointer;
  transition: all 120ms;
}
.ib-tool-btn:hover { color: var(--fg); border-color: var(--accent); }
.ib-tool-btn.is-primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.ib-tool-btn.is-primary:hover { opacity: 0.9; }
.ib-tool-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
