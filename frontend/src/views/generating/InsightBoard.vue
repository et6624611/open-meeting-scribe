<template>
  <div class="ib-root" ref="rootEl">
    <!-- 板 tab 轨：板数 ≤1 时不显示，保持单板观感不变 / Board tab rail (hidden when ≤1 board) -->
    <nav v-if="showRail" class="ib-tabs" role="tablist" :aria-label="t('generating.insights.board.tabs_label')">
      <button
        v-for="b in boards"
        :key="b.board_id"
        type="button"
        role="tab"
        class="ib-tab"
        :class="{ 'is-active': b.board_id === activeBoardId }"
        :aria-selected="b.board_id === activeBoardId"
        @click="emit('switchBoard', b.board_id)"
      >
        {{ b.title || b.board_id }}
        <span v-if="!b.exists" class="ib-tab-empty">{{ t('generating.insights.board.tab_empty') }}</span>
      </button>
      <button v-if="!creating" type="button" class="ib-tab ib-tab-new" @click="startCreate">
        ＋ {{ t('generating.insights.board.new') }}
      </button>
      <span v-else class="ib-tab-create">
        <input
          ref="createInputEl"
          v-model="newTitle"
          type="text"
          maxlength="60"
          :placeholder="t('generating.insights.board.create_placeholder')"
          :aria-label="t('generating.insights.board.create_placeholder')"
          @keydown.enter.prevent="submitCreate"
          @keydown.esc="cancelCreate"
        />
        <button type="button" class="ib-tool-btn is-primary" :disabled="!newTitle.trim()" @click="submitCreate">
          {{ t('generating.insights.board.create_ok') }}
        </button>
        <button type="button" class="ib-tool-btn" @click="cancelCreate">
          {{ t('generating.insights.board.create_cancel') }}
        </button>
      </span>
    </nav>

    <!-- 板头：rev 角标 + 刷新 + 浏览器打开 + 共创起跳 / Board header -->
    <header v-if="artifact.html" class="ib-head">
      <span class="ib-eyebrow">{{ t('generating.insights.board.eyebrow') }}</span>
      <span class="ib-rev" :class="{ 'is-bumped': revBumped }">rev {{ artifact.revision }}</span>
      <span class="ib-head-spacer"></span>
      <button class="ib-tool-btn" :disabled="loading" @click="emit('refresh')">
        {{ loading ? t('generating.insights.board.loading') : t('generating.insights.board.refresh') }}
      </button>
      <button class="ib-tool-btn" :title="t('generating.insights.board.open_hint')" @click="emit('openInBrowser')">
        {{ t('generating.insights.board.open_in_browser') }}
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

    <!--
      呈现容器：sandbox iframe + 板自己的原始 HTML（版式归 CLI，应用不剥壳）。
      ⚠️ sandbox 必须是常量且**永不含 allow-same-origin**：两者同现时板文档回到站内
      origin，Origin 守卫与 opaque origin 防线全部失效（见 app/server.py 与方案 §4.2）。
      srcdoc 含内存拼接的桥接脚本；磁盘文件始终是 CLI 的原始字节。
    -->
    <iframe
      v-if="artifact.html"
      ref="frameEl"
      class="ib-frame"
      :srcdoc="docHtml"
      :sandbox="sandbox"
      :style="{ height: frameHeight + 'px' }"
      :title="t('generating.insights.board.eyebrow')"
      @load="onFrameLoad"
    />

    <!-- 板内悬停工具栏：悬停某个 <section data-ib-id> 时于其右上角浮现「共创此节」 -->
    <button
      v-if="hoverSec && artifact.html"
      class="ib-sec-cocreate"
      :style="{ top: buttonTop + 'px', right: buttonRight + 'px' }"
      @click="onSectionCoCreate"
    >✎ {{ t('generating.insights.board.co_create_section') }}</button>
  </div>
</template>

<script setup lang="ts">
/**
 * 洞察板呈现容器 / Insight Board viewer（原始 HTML + iframe 桥接版）
 *
 * 「洞察共创 · 会话驱动」：板是一份 AI 直出的自包含 HTML，本组件只做呈现与几件事——
 * 1. iframe 桥接：跨 opaque origin 只能走 postMessage，锚点跳转/悬停定位/高度/mermaid
 *    全部经 useBoardBridge（v-html 时代的父级 DOM 委托已整体退役）；
 * 2. 全文共创起跳：empty/header 按钮 emit('coCreate')；
 * 3. 单节共创：悬停顶层 <section data-ib-id> 浮现工具栏，点击 emit('coCreateSection', {id,title,boardId})；
 * 4. 多板：tab 轨 + 「＋ 新建板」（建板只由这里 emit 给持有 task_id 的父级执行）；
 * 5. 原始出口：emit('openInBrowser') 交给父级调后端（pywebview 里 window.open 不可靠）；
 * 6. 版本前进（会话落板/轮询发现）时 rev 徽标脉冲一下，作为“板刚刚自己变了”的轻提示。
 */
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import EmptyHint from '@/components/common/EmptyHint.vue'
import type { BoardArtifact, BoardSummary } from '@/api/board'
import { useThemeStore } from '@/stores/theme'
import { useBoardBridge } from '@/composables/useBoardBridge'

const { t } = useI18n()

const props = defineProps<{
  /** 板 HTML 产物（只读重拉语义）；html 已由后端做安全清洗（不再剥外壳） */
  artifact: BoardArtifact
  loading?: boolean
  /** 板清单（≤1 份时 tab 轨不显示，可不传） */
  boards?: BoardSummary[]
  /** 当前可见板 id */
  activeBoardId?: string
}>()

const emit = defineEmits<{
  (e: 'seek', ms: number): void
  (e: 'refresh'): void
  (e: 'coCreate'): void
  (e: 'coCreateSection', sec: { id: string; title: string; boardId: string }): void
  (e: 'switchBoard', boardId: string): void
  (e: 'createBoard', title: string): void
  (e: 'openInBrowser'): void
}>()

const rootEl = ref<HTMLElement | null>(null)
const frameEl = ref<HTMLElement | null>(null)

const themeStore = useThemeStore()
const htmlRef = computed(() => props.artifact.html || '')
// 读 activeTheme 而非 current：主题预览（TopBar / 设置页鼠标滑过色块）只改 DOM 属性时，
// 订阅 current 的桥接不会重发令牌，板就会停在旧配色上跟全站观感对不上。
const themeRef = computed(() => themeStore.activeTheme)

const { docHtml, frameHeight, hoverSec, sandbox, onFrameLoad } = useBoardBridge(
  frameEl, htmlRef, themeRef,
)

/** 悬停节 → 浮动按钮坐标：iframe 在 .ib-root 内的偏移 + 桥接上报的文档坐标 */
const buttonTop = computed(() => {
  const sec = hoverSec.value
  if (!sec) return 0
  const iframe = frameEl.value as HTMLIFrameElement | null
  const root = rootEl.value
  if (!iframe || !root) return sec.top + 8
  return iframe.getBoundingClientRect().top - root.getBoundingClientRect().top + sec.top + 8
})
const buttonRight = computed(() => {
  const sec = hoverSec.value
  const iframe = frameEl.value as HTMLIFrameElement | null
  const root = rootEl.value
  if (!sec || !iframe || !root) return 8
  const rr = root.getBoundingClientRect()
  return Math.max(rr.right - iframe.getBoundingClientRect().right + sec.right + 8, 4)
})

const boards = computed<BoardSummary[]>(() => props.boards || [])
const activeBoardId = computed(() => props.activeBoardId || props.artifact.board_id || 'main')
const showRail = computed(() => boards.value.length > 1)

/* ── 「＋ 新建板」内联输入：建板权属于用户，本组件只收集标题并上抛 ── */
const creating = ref(false)
const newTitle = ref('')
const createInputEl = ref<HTMLInputElement | null>(null)
function startCreate() {
  creating.value = true
  newTitle.value = ''
  void nextTick(() => createInputEl.value?.focus())
}
function cancelCreate() {
  creating.value = false
  newTitle.value = ''
}
function submitCreate() {
  const title = newTitle.value.trim()
  if (!title) return
  emit('createBoard', title)
  creating.value = false
  newTitle.value = ''
}

function onSectionCoCreate() {
  const s = hoverSec.value
  if (!s) return
  emit('coCreateSection', { id: s.id, title: s.title, boardId: activeBoardId.value })
  hoverSec.value = null
}

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
</script>
