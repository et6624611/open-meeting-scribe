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
import { ref, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import EmptyHint from '@/components/common/EmptyHint.vue'
import type { BoardArtifact } from '@/api/board'

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
