<template>
  <div class="ib-root" ref="rootEl" @mousemove="onHtmlMove" @mouseleave="onHtmlLeave">
    <!-- 板头：rev 角标 + 刷新 + 共创起跳 / Board header: revision chip + refresh + co-create CTA -->
    <header v-if="artifact.html" class="ib-head">
      <span class="ib-eyebrow">{{ t('generating.insights.board.eyebrow') }}</span>
      <span class="ib-rev" :class="{ 'is-bumped': revBumped }">rev {{ artifact.revision }}</span>
      <span class="ib-head-spacer"></span>
      <button class="ib-tool-btn" :disabled="loading" @click="emit('refresh')">
        {{ loading ? t('generating.insights.board.loading') : t('generating.insights.board.refresh') }}
      </button>
      <button class="ib-tool-btn is-primary" @click="emit('coCreate')">
        {{ t('generating.insights.board.co_create') }}
      </button>
    </header>

    <!-- 空态：统一 EmptyHint，保留「共创」引导按钮（四面板中唯一带动作的空态） -->
    <div v-if="!artifact.html" class="ib-empty">
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

    <!-- HTML 产物呈现容器：后端已清洗（剥离 script/on*/危险 URL/全局 :root），此处仅静态渲染 -->
    <div v-if="artifact.html" class="ib-html" v-html="artifact.html" @click="onHtmlClick"></div>

    <!-- 板内悬停工具栏：鼠标悬停某个 <section data-ib-id> 时于其右上角浮现「共创此节」 -->
    <button
      v-if="hoverSec && artifact.html"
      class="ib-sec-cocreate"
      :style="{ top: hoverSec.top + 'px', right: hoverSec.right + 'px' }"
      @click="onSectionCoCreate"
    >✎ {{ t('generating.insights.board.co_create_section') }}</button>
  </div>
</template>

<script setup lang="ts">
/**
 * 洞察板呈现容器 / Insight Board viewer（HTML 产物版）
 *
 * 「洞察共创 · 会话驱动」：板是一份 AI 直出的自包含 HTML，本组件只做呈现与三件事——
 * 1. data-seek-ms 锚点点击委托 → 跳转转写原文（AI 只产锚点，接线在应用侧）；
 * 2. 全文共创起跳：empty/header 按钮 emit('coCreate')；
 * 3. 单节共创：悬停顶层 <section data-ib-id> 浮现工具栏，点击 emit('coCreateSection', {id,title})；
 * 4. 版本前进（会话落板/轮询发现）时 rev 徽标脉冲一下，作为“板刚刚自己变了”的轻提示。
 * 旧 Board Spec 渲染器（zone 导航/cell 动态组件/失败横幅）已整体退役。
 */
import { ref, watch, nextTick, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import EmptyHint from '@/components/common/EmptyHint.vue'
import type { BoardArtifact } from '@/api/board'
import { useThemeStore } from '@/stores/theme'
import { isDarkThemeId, normalizeMermaidSvg, renderMermaidToSvg } from '@/utils/renderMermaid'

const { t } = useI18n()

const props = defineProps<{
  /** 板 HTML 产物（只读重拉语义）；html 已由后端 sanitize 清洗 */
  artifact: BoardArtifact
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'seek', ms: number): void
  (e: 'refresh'): void
  (e: 'coCreate'): void
  (e: 'coCreateSection', sec: { id: string; title: string }): void
}>()

const rootEl = ref<HTMLElement | null>(null)

const themeStore = useThemeStore()

/** 尺寸归一化：图按自然尺寸 1:1 渲染（字号恒定），仅超容器时等比收窄 */
function stripSvgSize(box: HTMLElement) {
  const svgEl = box.querySelector('svg')
  if (svgEl) normalizeMermaidSvg(svgEl)
}

/**
 * 把板内 pre.ib-mermaid 源码块渲染为 SVG / Render mermaid source blocks inside the board
 *
 * 落盘存源码（AI 读基线时看到的也是源码），显示时渲染；渲染成功把源码存到
 * data-ib-mermaid-src 供主题切换重渲（DOM 已替换，不从 box 里反取）。
 * 不调 bindFunctions：mermaid click 语句天然失效。失败保留 pre 便于排查并挂错误框。
 */
async function renderMermaidBlocks() {
  const root = rootEl.value
  if (!root) return
  const pres = Array.from(root.querySelectorAll('pre.ib-mermaid'))
  await Promise.all(pres.map(async (pre) => {
    const code = (pre.textContent || '').trim()
    if (!code) return
    try {
      const { svg } = await renderMermaidToSvg(code, isDarkThemeId(themeStore.current))
      const box = document.createElement('div')
      box.className = 'ib-mermaid-box'
      box.setAttribute('data-ib-mermaid-src', code)
      box.innerHTML = svg
      stripSvgSize(box)
      pre.replaceWith(box)
    } catch (e) {
      if (!pre.nextElementSibling?.classList.contains('ib-mermaid-err')) {
        const err = document.createElement('div')
        err.className = 'ib-mermaid-err'
        err.textContent = t('generating.insights.board.mermaid_error')
          + (e instanceof Error ? e.message : String(e))
        pre.after(err)
      }
      console.warn('[InsightBoard] mermaid render failed:', e)
    }
  }))
}

/** 主题切换：用存好的源码重渲所有已渲染图；失败保留旧图不闪空 */
async function rethemeMermaidBlocks() {
  const root = rootEl.value
  if (!root) return
  const boxes = Array.from(root.querySelectorAll<HTMLElement>('.ib-mermaid-box[data-ib-mermaid-src]'))
  await Promise.all(boxes.map(async (box) => {
    const code = box.getAttribute('data-ib-mermaid-src') || ''
    if (!code) return
    try {
      const { svg } = await renderMermaidToSvg(code, isDarkThemeId(themeStore.current))
      box.innerHTML = svg
      stripSvgSize(box)
    } catch { /* 保留旧图 */ }
  }))
}

// v-html 重渲后 DOM 整体重建（旧 SVG 随之清理，无泄漏面），每次 html 变化重新扫描渲染
watch(() => props.artifact.html, async () => {
  await nextTick()
  renderMermaidBlocks()
}, { flush: 'post', immediate: true })

watch(() => themeStore.current, () => { rethemeMermaidBlocks() })

/** rev 徽标脉冲：静默替换的新版本不弹提示，仅徽标闪一下（首次赋值/持平不触发） */
const revBumped = ref(false)
let revBumpTimer: ReturnType<typeof setTimeout> | null = null
watch(() => props.artifact.revision, (next, prev) => {
  if (prev == null || next <= prev) return
  revBumped.value = true
  if (revBumpTimer) clearTimeout(revBumpTimer)
  revBumpTimer = setTimeout(() => { revBumped.value = false }, 1400)
})
onUnmounted(() => { if (revBumpTimer) clearTimeout(revBumpTimer) })

/** 当前悬停节：{id,title} + 相对 .ib-root 的 top/right 偏移（供浮动按钮定位） */
const hoverSec = ref<{ id: string; title: string; top: number; right: number } | null>(null)

/** 锚点委托：容器内任意 [data-seek-ms] 元素点击 → 跳回转写原文并定位时间轴 */
function onHtmlClick(e: MouseEvent) {
  const el = (e.target as HTMLElement | null)?.closest?.('[data-seek-ms]') as HTMLElement | null
  if (!el) return
  const ms = Number(el.getAttribute('data-seek-ms'))
  if (Number.isFinite(ms) && ms >= 0) {
    e.preventDefault()
    emit('seek', ms)
  }
}

/** 悬停追踪：命中顶层 [data-ib-id] 节则在其右上角定位工具栏 */
function onHtmlMove(e: MouseEvent) {
  const target = e.target as HTMLElement | null
  // 悬停在工具栏自身上不重算（否则鼠标移入按钮会因 target 不在节内而闪断）
  if (target?.closest?.('.ib-sec-cocreate')) return
  const sec = target?.closest?.('[data-ib-id]') as HTMLElement | null
  const root = rootEl.value
  if (!sec || !root || !sec.getAttribute('data-ib-id')) { hoverSec.value = null; return }
  const sr = sec.getBoundingClientRect()
  const rr = root.getBoundingClientRect()
  hoverSec.value = {
    id: sec.getAttribute('data-ib-id') || '',
    title: (sec.getAttribute('data-ib-title') || '').trim(),
    top: sr.top - rr.top + 8,
    right: rr.right - sr.right + 8,
  }
}

function onHtmlLeave() { hoverSec.value = null }

function onSectionCoCreate() {
  const s = hoverSec.value
  if (!s) return
  emit('coCreateSection', { id: s.id, title: s.title })
  hoverSec.value = null
}
</script>
