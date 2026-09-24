<template>
  <div ref="panelRef" class="rec-insights-panel">
    <div class="rec-insights-header">
      <div class="rec-insights-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
        {{ t('recording.insights.title') }}
        <span v-if="enabled && unreadCount > 0" class="rec-insights-badge">{{ unreadCount }}</span>
      </div>
      <div class="rec-insights-actions">
        <!-- 开关承载动作语义（点击切换，tooltip 提示动作）；旁边文本如实显示当前状态 -->
        <div
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
        <!-- 自动频率选择（仅开启时显示）：唯一暴露给用户的旋钮 / Auto frequency selector (only when enabled): the single user-facing knob -->
        <div v-if="enabled" class="rec-insights-freq" :title="t('recording.insights.freq_tip')">
          <button
            v-for="opt in FREQ_OPTIONS" :key="opt"
            class="rec-insights-freq-opt"
            :class="{ 'is-active': autoFreq === opt }"
            :title="t('recording.insights.freq_' + opt)"
            @click="$emit('update:autoFreq', opt)"
          >{{ t('recording.insights.freq_' + opt) }}</button>
        </div>
        <button
          v-if="enabled"
          class="rec-insights-btn rec-insights-analyze-btn"
          :class="{ 'is-loading': analyzing }"
          :disabled="analyzing"
          :title="t('ai-panel.insights.manual_analysis')"
          :aria-label="t('ai-panel.insights.manual_analysis')"
          @click="$emit('manualCheck')"
        >
          <svg v-if="!analyzing" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
          <svg v-else class="rec-insights-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
        </button>
        <!-- 扩展/收起按钮：扩展后洞察台占满内容区域 / Expand button: insight deck takes over content area -->
        <button
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
    <!-- 消息流 / Message stream -->
    <div class="rec-insights-body" v-if="enabled">
      <div v-if="messages.length === 0" class="rec-insights-empty">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.3"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
        <div class="rec-insights-empty-text">{{ t('recording.insights.empty') }}</div>
        <div class="rec-insights-empty-hint">{{ t('recording.insights.empty_hint') }}</div>
      </div>
      <div v-else class="rec-insights-list">
        <div
          v-for="msg in messages" :key="msg.id"
          class="rec-insight-card"
          :class="{ 'is-expanded': msg.expanded, 'is-unread': !msg.read, 'is-acknowledged': msg.acknowledged }"
        >
          <div class="rec-insight-card-header" @click="$emit('toggleMessage', msg.id)">
            <span class="rec-insight-cat">{{ msg.category }}</span>
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
              <!-- 图操作工具栏 / Diagram action toolbar -->
              <div class="rec-insight-diagram-toolbar">
                <button class="rec-insight-diagram-btn" :title="t('ai-panel.insights.diagram_regenerate')" @click.stop="$emit('manualCheck')">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                  <span>{{ t('ai-panel.insights.diagram_regenerate') }}</span>
                </button>
              </div>
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
                <button class="rec-insight-diagram-btn" :title="t('ai-panel.insights.diagram_regenerate')" @click.stop="$emit('manualCheck')">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                  <span>{{ t('ai-panel.insights.diagram_regenerate') }}</span>
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
              <!-- 图操作工具栏 / Diagram action toolbar -->
              <div class="rec-insight-diagram-toolbar">
                <button class="rec-insight-diagram-btn" :title="t('ai-panel.insights.diagram_copy')" @click.stop="onCopyDiagram(msg.diagram)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                  <span>{{ t('ai-panel.insights.diagram_copy') }}</span>
                </button>
                <button class="rec-insight-diagram-btn" :title="t('ai-panel.insights.diagram_regenerate')" @click.stop="$emit('manualCheck')">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                  <span>{{ t('ai-panel.insights.diagram_regenerate') }}</span>
                </button>
                <button class="rec-insight-diagram-btn" :title="t('ai-panel.insights.diagram_edit_in_chat')" @click.stop="onEditInChat(msg.diagram)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  <span>{{ t('ai-panel.insights.diagram_edit_in_chat') }}</span>
                </button>
              </div>
            </div>
            <!-- 图的注释 / Diagram annotations -->
            <div class="rec-insight-body-text" v-html="renderInsightMarkdown(msg.body)"></div>
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
      </div>
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
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { escapeHtml } from '@/utils/sanitize'
import type { InsightMessage, InsightAction, AutoFreq } from '@/composables/useAiInsights'
import { useAiInsights } from '@/composables/useAiInsights'
import type { InsightFlowData } from '@/utils/parseInsightFlow'
import { parseInsightFlow, matchPhaseDescriptions } from '@/utils/parseInsightFlow'
import MermaidDiagram from '@/components/common/MermaidDiagram.vue'
import InsightFlow from '@/components/common/InsightFlow.vue'
// eslint-disable-next-line vue/multi-word-component-names -- 历史兼容组件，仅旧会话 graph 消息使用
import InsightGraph, { type InsightLegacyGraphData } from '@/components/common/InsightGraph.vue'

const { t } = useI18n()
const insights = useAiInsights()

/** 频率档位选项（从“关闭自动”到“高”） / Frequency options (from off to high) */
const FREQ_OPTIONS: AutoFreq[] = ['off', 'low', 'normal', 'high']

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

defineProps<{
  messages: InsightMessage[]
  enabled: boolean
  unreadCount: number
  actedActions: Record<string, boolean>
  analyzing: boolean
  expanded: boolean
  autoFreq: AutoFreq
}>()

defineEmits<{
  (e: 'toggleEnabled'): void
  (e: 'toggleMessage', id: string): void
  (e: 'action', message: InsightMessage, action: InsightAction): void
  (e: 'manualCheck'): void
  (e: 'toggleExpand'): void
  (e: 'seekTo', ms: number): void
  (e: 'update:autoFreq', value: AutoFreq): void
}>()

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
