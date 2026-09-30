<template>
  <div ref="panelRef" class="rec-insights-panel">
    <div class="rec-insights-header">
      <div class="rec-insights-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
        {{ t('recording.insights.title') }}
        <span v-if="enabled && unreadCount > 0" class="rec-insights-badge">{{ unreadCount }}</span>
      </div>
      <div class="rec-insights-actions">
        <!-- 一页纸系数角标（洞察面）：有效卡位上限，超位旧卡入「历史观察」折叠层；只读态也可改档
             One-page badge (insights surface): active card-slot cap; overflow cards fold into history -->
        <PageBudgetBadge
          v-if="taskId"
          :task-id="taskId"
          surface="insights"
          :factor="onePageFactor"
          @changed="onBudgetChanged"
        />
        <!-- 开关承载动作语义（点击切换，tooltip 提示动作）；旁边文本如实显示当前状态；会后只读态隐藏 -->
        <div
          v-if="!readonly"
          class="toggle-switch"
          :class="{ 'is-on': enabled }"
          role="switch"
          tabindex="0"
          :aria-checked="enabled"
          :title="enabled ? t('ai-panel.insights.toggle_on') : t('ai-panel.insights.toggle_off')"
          :aria-label="enabled ? t('ai-panel.insights.toggle_on') : t('ai-panel.insights.toggle_off')"
          @click="$emit('toggleEnabled')"
          @keydown.enter.prevent="$emit('toggleEnabled')"
          @keydown.space.prevent="$emit('toggleEnabled')"
        >
          <div class="toggle-switch-track">
            <div class="toggle-switch-knob"></div>
          </div>
          <span class="toggle-switch-label">{{ enabled ? t('recording.insights.enabled') : t('recording.insights.disabled') }}</span>
        </div>
        <!-- 【已退役】自动频率旋钮与分析引擎标签：洞察改由会话面板人与 AI 共创驱动，本面板仅只读呈现 -->
        <!-- 扩展/收起按钮：扩展后洞察台占满内容区域；会后只读态整页即洞察，隐藏 -->
        <button
          v-if="!readonly"
          class="rec-insights-btn rec-insights-expand-btn"
          :class="{ 'is-expanded': expanded }"
          :title="expanded ? t('recording.insights.collapse') : t('recording.insights.expand')"
          :aria-label="expanded ? t('recording.insights.collapse') : t('recording.insights.expand')"
          @click="$emit('toggleExpand')"
        >
          <svg v-if="!expanded" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
        </button>
      </div>
    </div>
    <!-- 消息流 / Message stream（只读态无视能开关，始终展示历史；已有板时不受开关遮挡） -->
    <div class="rec-insights-body" v-if="readonly || enabled || board.html">
      <!-- 洞察板产物优先：会话「画入洞察台」落板的 HTML 直接呈现，卡片流降为后备
           Board artifact takes priority: the co-created HTML renders here; card stream is the fallback -->
      <InsightBoard
        v-if="board.html"
        :artifact="board"
        :loading="boardLoading"
        @seek="$emit('seekTo', $event)"
        @refresh="loadBoardData"
        @co-create="onBoardCoCreate"
      />
      <template v-else>
      <div v-if="messages.length === 0" class="rec-insights-empty">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.3"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
        <div class="rec-insights-empty-text">{{ readonly ? t('generating.insights.empty_title') : t('recording.insights.empty') }}</div>
        <div class="rec-insights-empty-hint">{{ readonly ? t('generating.insights.empty_desc') : t('recording.insights.empty_hint') }}</div>
        <!-- 【已退役】会后补分析 CTA：触发入口随「洞察共创 · 会话驱动」下线，历史消息仍只读呈现 -->
      </div>
      <div v-else class="rec-insights-list">
        <div
          v-for="msg in activeMessages" :key="msg.id"
          class="rec-insight-card"
          :class="{ 'is-expanded': msg.expanded, 'is-unread': !msg.read, 'is-acknowledged': msg.acknowledged }"
        >
          <div class="rec-insight-card-header" @click="$emit('toggleMessage', msg.id)">
            <span class="rec-insight-cat">{{ msg.category || t('ai-panel.insights.cat_insight') }}</span>
            <span v-if="msg.phase === 'post_meeting'" class="insights-phase-badge">{{ t('generating.insights.phase_post') }}</span>
            <span class="rec-insight-card-title">{{ msg.title }}</span>
            <svg v-if="!msg.expanded" class="rec-insight-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
            <svg v-else class="rec-insight-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="18 15 12 9 6 15"/></svg>
          </div>
          <div v-if="msg.expanded" class="rec-insight-card-body">
            <!-- 历史会话兼容：旧版结构化图谱（新分析不再产出 graph，仅旧消息重载时存在）
                 Legacy session compat: old structured graph (new analyses never emit graph, only reloaded legacy messages carry it) -->
            <div v-if="hasLegacyGraph(msg)" class="rec-insight-diagram-wrap">
              <InsightGraph
                :data="legacyGraphOf(msg)"
                class="rec-insight-diagram rec-insight-diagram-primary"
                @seek-to="$emit('seekTo', $event)"
              />
              <!-- 【已退役】图重生成按钮：单轮重生成不属于共创路径，修订改由会话发起 -->
            </div>
            <!-- 洞察台画布：受约束 Mermaid 解析成功时渲染 workflow 阶段卡 / Insight Deck canvas: workflow phase cards when constrained Mermaid parses -->
            <div v-else-if="flowOf(msg)" class="rec-insight-diagram-wrap">
              <InsightFlow
                :data="flowOf(msg)!"
                class="rec-insight-diagram rec-insight-diagram-primary"
                @seek-to="$emit('seekTo', $event)"
              />
              <!-- 图操作工具栏 / Diagram action toolbar -->
              <div class="rec-insight-diagram-toolbar">
                <button class="rec-insight-diagram-btn" :title="t('ai-panel.insights.diagram_copy')" @click.stop="onCopyDiagram(msg.diagram)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                  <span>{{ t('ai-panel.insights.diagram_copy') }}</span>
                </button>
                <button class="rec-insight-diagram-btn" :title="t('ai-panel.insights.diagram_edit_in_chat')" @click.stop="onEditInChat(msg.diagram)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  <span>{{ t('ai-panel.insights.diagram_edit_in_chat') }}</span>
                </button>
              </div>
            </div>
            <!-- 降级：不符合画布书写规范时用通用 Mermaid 渲染，用户永远有图看
                 Fallback: non-conforming Mermaid rendered generically — the user always sees a diagram -->
            <div v-else-if="msg.diagram" class="rec-insight-diagram-wrap">
              <MermaidDiagram
                :code="msg.diagram"
                class="rec-insight-diagram rec-insight-diagram-primary"
              />
              <!-- 图操作工具栏（重生成按钮已退役） / Diagram action toolbar (regenerate retired) -->
              <div class="rec-insight-diagram-toolbar">
                <button class="rec-insight-diagram-btn" :title="t('ai-panel.insights.diagram_copy')" @click.stop="onCopyDiagram(msg.diagram)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                  <span>{{ t('ai-panel.insights.diagram_copy') }}</span>
                </button>
                <button class="rec-insight-diagram-btn" :title="t('ai-panel.insights.diagram_edit_in_chat')" @click.stop="onEditInChat(msg.diagram)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  <span>{{ t('ai-panel.insights.diagram_edit_in_chat') }}</span>
                </button>
              </div>
            </div>
            <!-- 图的注释 / Diagram annotations -->
            <div class="rec-insight-body-text" v-html="renderInsightMarkdown(msg.body)"></div>
            <!-- 备查注释层（三层信息写作）：退可忽略、进可查看 / Note layer: skippable yet answerable -->
            <div v-if="msg.note" class="rec-insight-note">
              <span class="rec-insight-note-label">{{ t('ai-panel.insights.note_label') }}</span>
              <span class="rec-insight-note-text">{{ msg.note }}</span>
            </div>
            <div v-if="msg.solution" class="rec-insight-solution">
              <span class="rec-insight-solution-label">{{ t('ai-panel.insights.expand_detail') }}</span>
              <div class="rec-insight-solution-text" v-html="renderInsightMarkdown(msg.solution)"></div>
            </div>
            <div class="rec-insight-actions" v-if="msg.actions.length > 0">
              <button
                v-for="act in msg.actions" :key="act.key"
                class="rec-insight-action-btn"
                :class="{ 'is-primary': act.primary, 'is-done': actedActions[msg.id + ':' + act.key] }"
                @click.stop="$emit('action', msg, act)"
              >{{ act.label }}</button>
            </div>
            <div class="rec-insight-meta">
              {{ msg.source === 'user' ? t('ai-panel.insights.meta_manual') : t('ai-panel.insights.meta_auto') }} · {{ formatTime(msg.timestamp) }}
            </div>
          </div>
        </div>
        <!-- 历史观察折叠层：超出一页预算的降级卡（不删除，进可读退可略）
             History layer: deferred cards beyond the one-page budget -->
        <div v-if="deferredMessages.length > 0" class="rec-insights-deferred">
          <button class="rec-insights-deferred-toggle" :aria-expanded="openDeferred" @click="openDeferred = !openDeferred">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline v-if="!openDeferred" points="6 9 12 15 18 9"/><polyline v-else points="18 15 12 9 6 15"/></svg>
            {{ t('recording.insights.deferred_title', { count: deferredMessages.length }) }}
          </button>
          <div v-show="openDeferred" class="rec-insights-deferred-list">
            <div v-for="msg in deferredMessages" :key="'deferred-' + msg.id" class="rec-insights-deferred-item" :title="msg.body">
              <span class="rec-insights-deferred-dot"></span>
              <span class="rec-insights-deferred-item-title">{{ msg.title }}</span>
              <span class="rec-insights-deferred-time">{{ formatTime(msg.timestamp) }}</span>
            </div>
          </div>
        </div>
      </div>
      </template>
    </div>
    <!-- 未开启时的提示 / Prompt when disabled -->
    <div class="rec-insights-body" v-else>
      <div class="rec-insights-empty">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.3"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
        <div class="rec-insights-empty-text">{{ t('recording.insights.empty') }}</div>
        <div class="rec-insights-empty-hint">{{ t('recording.insights.empty_hint') }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { escapeHtml } from '@/utils/sanitize'
import type { InsightMessage, InsightAction } from '@/composables/useAiInsights'
import { useAiInsights } from '@/composables/useAiInsights'
import { loadBoard, loadBoardMeta, type BoardArtifact } from '@/api/board'
import { onBoardWritten } from '@/composables/useBoardSync'
import InsightBoard from '../generating/InsightBoard.vue'
import type { InsightFlowData } from '@/utils/parseInsightFlow'
import { parseInsightFlow, matchPhaseDescriptions } from '@/utils/parseInsightFlow'
import MermaidDiagram from '@/components/common/MermaidDiagram.vue'
import InsightFlow from '@/components/common/InsightFlow.vue'
import PageBudgetBadge from '@/components/common/PageBudgetBadge.vue'
// eslint-disable-next-line vue/multi-word-component-names -- 历史兼容组件，仅旧会话 graph 消息使用
import InsightGraph, { type InsightLegacyGraphData } from '@/components/common/InsightGraph.vue'

const { t } = useI18n()
const insights = useAiInsights()

/* 【已退役】分析引擎回显标签与频率旋钮：随「洞察共创 · 会话驱动」下线 */

/**
 * 将洞察台的 Markdown 文本渲染为 HTML。
 * 先 escapeHtml 防 XSS，再还原基础 Markdown 格式（标题/列表/粗体/斜体/换行）。
 * AI 生成内容可信，无需处理链接/图片等复杂语法。
 */
function renderInsightMarkdown(md: string): string {
  if (!md) return ''
  let html = escapeHtml(md)
  // 标题（### → h3, ## → h2, # → h1）
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>')
  // 粗体 / 斜体
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  // 无序列表
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  // 有序列表
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
  // 换行
  html = html.replace(/\n/g, '<br>')
  return html
}

const panelRef = ref<HTMLElement | null>(null)

/* 画布解析结果缓存：按消息对象引用复用，避免列表重渲染时重复解析
   Flow parse cache: keyed by message object identity, survives list re-renders */
const flowCache = new WeakMap<object, InsightFlowData | null>()

/** 消息是否携带旧版图谱数据 / Whether a message carries the legacy graph payload */
function hasLegacyGraph(msg: InsightMessage): boolean {
  const g = msg.graph as { nodes?: unknown } | undefined
  return !!g && Array.isArray(g.nodes) && g.nodes.length > 0
}

/** 历史消息的旧版图谱数据（新分析不再产出 graph，仅旧会话重载时存在）
    Legacy graph payload of a historical message (new analyses never emit graph) */
function legacyGraphOf(msg: InsightMessage): InsightLegacyGraphData {
  return msg.graph as InsightLegacyGraphData
}

/** 解析消息的 Mermaid 为画布结构；null = 不规范，降级通用渲染 / Parse message Mermaid into canvas flow; null = non-conforming, fall back */
function flowOf(msg: InsightMessage): InsightFlowData | null {
  if (!msg.diagram) return null
  if (flowCache.has(msg)) return flowCache.get(msg) ?? null
  let flow: InsightFlowData | null = null
  try {
    flow = parseInsightFlow(msg.diagram)
    if (flow) matchPhaseDescriptions(flow.phases, msg.body)
  } catch {
    flow = null
  }
  flowCache.set(msg, flow)
  return flow
}

const props = defineProps<{
  messages: InsightMessage[]
  enabled: boolean
  unreadCount: number
  actedActions: Record<string, boolean>
  expanded: boolean
  /** 面板模式（REQ-INSIGHT-DECK-POSTMEETING R1 v0.2.0 契约）：
      live = 录音页会中态（默认，行为与改造前一致）；readonly = 纪要页会后只读态
      live = in-meeting (default, unchanged); readonly = post-meeting review mode */
  mode?: 'live' | 'readonly'
  /** 一页纸系数所属任务 ID（角标 PATCH 目标） / Task id the one-page badge patches */
  taskId?: string
  /** 当前洞察面系数（宿主从 task.one_page.insights 解析） / Current insights-side factor */
  onePageFactor?: number | null
}>()

/** 只读态判定（模板内沿用 readonly 语义名） / Read-only flag derived from mode */
const readonly = computed(() => props.mode === 'readonly')

/* ── 一页纸系数：有效层/历史观察层拆分 / One-page budget: active vs deferred layers ── */
const activeMessages = computed(() => props.messages.filter(m => !m.deferred))
const deferredMessages = computed(() => props.messages.filter(m => !!m.deferred))
/** 历史观察层默认收起（退可略） / History layer collapsed by default */
const openDeferred = ref(false)

/** 系数同步到 composable：会中分析请求据此携带 card_slots / Sync factor so analyses carry card_slots */
watch(() => props.onePageFactor, (f) => { insights.setOnePageInsights(f) }, { immediate: true })

/** 改档后重拉消息：后端 PATCH 同请求内已重排卡集，前端取回最新 deferred 标记
    Reload after factor change: the PATCH response already rebalanced server-side */
function onBudgetChanged() {
  if (props.taskId) void insights.reloadTaskMessages(props.taskId)
}

defineEmits<{
  (e: 'toggleEnabled'): void
  (e: 'toggleMessage', id: string): void
  (e: 'action', message: InsightMessage, action: InsightAction): void
  (e: 'toggleExpand'): void
  (e: 'seekTo', ms: number): void
}>()

/* ── 洞察板产物呈现 / Board artifact（会中「画入洞察台」的落点） ──
   板唯一写入点在后端会话工具；本面板只读重拉——挂载即拉、board-written 即时重拉、
   10s 轻量版本探测盖住「写板发生在其它窗口」的缝隙（与 GeneratingView 洞察 Tab 同机制）。 */
const EMPTY_BOARD: BoardArtifact = { html: null, revision: 0, updated_at: null }
const board = ref<BoardArtifact>({ ...EMPTY_BOARD })
const boardLoading = ref(false)
const BOARD_POLL_MS = 10_000
let boardPollTimer: ReturnType<typeof setInterval> | null = null
let offBoardWritten: (() => void) | null = null

async function loadBoardData() {
  if (!props.taskId) return
  boardLoading.value = true
  try {
    board.value = await loadBoard(props.taskId)
  } catch {
    // 读板失败静默降级卡片视图 / Load failure silently falls back to cards
  } finally {
    boardLoading.value = false
  }
}

/** 轻量版本探测：版本号前进（或无板→有板）才拉整份正文 */
async function probeBoardRevision() {
  if (boardLoading.value || document.hidden || !props.taskId) return
  try {
    const meta = await loadBoardMeta(props.taskId)
    if (meta.revision !== board.value.revision || (meta.exists && !board.value.html)) {
      await loadBoardData()
    }
  } catch { /* 探测失败静默跳过 / Probe failure is silent */ }
}

/** 全文共创起跳：预填修订请求到 AI 面板输入框（与纪要页同文案） */
function onBoardCoCreate() {
  window.dispatchEvent(new CustomEvent('quote-to-ai', {
    detail: { prefill: t('generating.insights.board.co_create_msg'), coCreate: true },
  }))
}

onMounted(() => {
  loadBoardData()
  boardPollTimer = setInterval(probeBoardRevision, BOARD_POLL_MS)
  offBoardWritten = onBoardWritten(() => { loadBoardData() })
})

onUnmounted(() => {
  if (boardPollTimer) clearInterval(boardPollTimer)
  if (offBoardWritten) offBoardWritten()
})

// 切换任务（重新挂载路由复用组件等场景）时重置并重拉
watch(() => props.taskId, () => {
  board.value = { ...EMPTY_BOARD }
  loadBoardData()
})

/** 复制图源码到剪贴板 / Copy diagram source to clipboard */
async function onCopyDiagram(code: string | undefined) {
  if (!code) return
  try {
    await navigator.clipboard.writeText(code)
    // 简单反馈：短暂显示“已复制”（通过 title 变化） / Simple feedback
  } catch {
    // 剪贴板 API 不可用时降级 / Fallback when clipboard API unavailable
    console.warn('[RecInsightsPanel] Clipboard copy failed')
  }
}

/** 在 AI 对话中编辑图 / Edit diagram in AI chat */
function onEditInChat(code: string | undefined) {
  if (!code) return
  // 设置图编辑请求，AIPanel 监听后会预填输入框 / Set diagram edit request, AIPanel watches and pre-fills input
  insights.diagramEditPending.value = code
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<style scoped>
/* 会后只读态专属元素（其余样式沿用 recording-view.css 全局 .rec-insights-* 体系）
   Post-meeting read-only extras; base styles live in recording-view.css (global) */
.insights-phase-badge {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 6px;
  font-size: 10px;
  line-height: 1.5;
  /* 用色收敛 R2：阶段标记属装饰，中性化（紫色只留给域标识与状态信号） */
  color: var(--muted);
  background: var(--surface-2);
  border: 1px solid var(--border);
}

/* ── 历史观察折叠层（一页纸系数降级卡） / Deferred history layer ── */
.rec-insights-deferred {
  margin-top: var(--s-2);
  border-top: 1px dashed var(--border);
  padding-top: var(--s-1);
}
.rec-insights-deferred-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 0;
  border: none;
  background: transparent;
  color: var(--subtle);
  font-size: var(--fs-11);
  font-family: inherit;
  cursor: pointer;
}
.rec-insights-deferred-toggle:hover {
  color: var(--muted);
}
.rec-insights-deferred-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--s-1) 0 var(--s-1) var(--s-2);
}
.rec-insights-deferred-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: var(--fs-11);
  color: var(--muted);
}
.rec-insights-deferred-dot {
  flex-shrink: 0;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--border-strong, var(--border));
}
.rec-insights-deferred-item-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rec-insights-deferred-time {
  flex-shrink: 0;
  margin-left: auto;
  color: var(--subtle);
}
</style>
