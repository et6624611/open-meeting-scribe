<template>
  <div class="ai" :class="{ 'is-collapsed': layout.aiCollapsed }">
    <button
      class="ai-toggle"
      :title="(layout.aiCollapsed ? t('ai-panel.expand') : t('ai-panel.collapse')) + ` (${modKey}J)`"
      :aria-label="layout.aiCollapsed ? t('ai-panel.expand') : t('ai-panel.collapse')"
      :aria-expanded="!layout.aiCollapsed"
      @mousedown="onToggleDown($event)"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
    </button>
    <div class="ai-collapsed-strip">
      <div class="ai-collapsed-icon" :class="{ 'is-insight': insights.unreadCount.value > 0 }" @click="layout.toggleAi()" style="position:relative">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
        <span v-if="insights.unreadCount.value > 0" class="breathing-dot"></span>
      </div>
      <span class="ai-collapsed-label">{{ t('ai-panel.collapsed_label') }}</span>
    </div>
    <div class="ai-panel-header">
      <div class="ai-panel-header-left">
        <div class="ai-header-avatar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg></div>
        <span class="ai-header-title">{{ t('ai-panel.title') }}</span>
      </div>
      <div class="ai-panel-header-right">
        <IconButton class="ai-header-btn" :label="t('ai-panel.clear')" @click="chat.clearConversation()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </IconButton>
      </div>
    </div>
    <div class="ai-panel-context"><span>{{ contextLabel }}</span></div>
    <!-- Tab 栏 / Tab bar -->
    <div class="ai-panel-tabs">
      <button class="ai-panel-tab" :class="{ 'is-active': aiTab === 'chat' }" @click="aiTab = 'chat'">{{ t('ai-panel.tab_chat') }}</button>
      <button class="ai-panel-tab" :class="{ 'is-active': aiTab === 'context' }" @click="aiTab = 'context'">
        {{ t('ai-panel.tab_context') }}
        <span v-if="ctx.contextResourceCount.value > 0" class="tab-badge">{{ ctx.contextResourceCount.value }}</span>
      </button>
    </div>

    <!-- 会话标签栏（仅对话 Tab） / Session tabs (chat Tab only) -->
    <AiSessionTabs
      v-show="aiTab === 'chat'"
      ref="sessionTabsRef"
      :sessions="aiSessions.sessions"
      :active-session-id="aiSessions.currentBucket.activeSessionId"
      :renaming-id="renamingId"
      :rename-input="renameInput"
      @switch="onSwitchSession"
      @new-session="onNewSession"
      @start-rename="startRename"
      @delete="onDeleteSession"
      @confirm-rename="confirmRename"
      @update:rename-input="renameInput = $event"
    />

    <!-- 对话 Tab / Chat Tab -->
    <AiChatPanel
      v-if="aiTab === 'chat'"
      ref="chatPanelRef"
      :messages="chat.messages.value"
      :is-loading="chat.isLoading.value"
      :is-streaming="chat.isStreaming.value"
      :thinking-elapsed="chat.thinkingElapsed.value"
      :stages="chat.stages.value"
      :rewrite-pending="quoteRef.rewritePending.value"
      :verified-changes="chat.verifiedChanges.value"
      :inject-prompt="chat.injectPrompt.value"
      :suggestions="chat.displaySuggestions.value"
      :quote-text="quoteRef.quoteRef.value?.text || ''"
      :quote-source="quoteSourceLabel"
      :cmd-open="cmds.cmdOpen.value"
      :cmd-index="cmds.cmdIndex.value"
      :filtered-cmds="filteredCmds"
      :input-text="inputText"
      :format-change="chat.formatChangeDescription"
      @send="onSend"
      @send-raw="chat.sendRaw"
      @stop-generation="chat.stopGeneration"
      @insert-to-summary="onInsertToSummary"
      @insert-to-notes="onInsertToNotes"
      @accept-rewrite="onAcceptRewrite"
      @clear-rewrite="quoteRef.clearRewrite"
      @inject-all="chat.doInjectAll"
      @dismiss-inject="chat.injectPrompt.value = null"
      @clear-quote="quoteRef.clearQuote"
      @run-command="runCommand"
      @input-key="handleInputKey"
      @input-change="handleInputChange"
      @update:input-text="inputText = $event"
    />

    <!-- 上下文 Tab / Context Tab -->
    <AiContextPanel
      v-if="aiTab === 'context'"
      :is-empty="ctx.isContextEmpty.value"
      :stats="ctx.contextStats.value"
      :meeting-output-count="ctx.meetingOutputCount.value"
      :current-task-duration="ctx.currentTaskDuration.value"
      :speaker-count="ctx.speakerCount.value"
      :chapter-count="ctx.chapterCount.value"
      :has-summary="ctx.hasSummary.value"
      :todo-count="ctx.todoCount.value"
      :todo-pending="ctx.todoPending.value"
      :todo-done="ctx.todoDone.value"
      :project-files="ctx.projectFiles.value"
      :visible-project-files="ctx.visibleProjectFiles.value"
      :project-file-count="ctx.projectFileCount.value"
      :related-meetings="ctx.relatedMeetings.value"
      :visible-related-meetings="ctx.visibleRelatedMeetings.value"
      :related-meeting-count="ctx.relatedMeetingCount.value"
      @show-all-files="ctx.showAllFiles.value = !ctx.showAllFiles.value"
      @show-all-meetings="ctx.showAllMeetings.value = !ctx.showAllMeetings.value"
      @generate-summary="ctx.generateSummary(chat.sendRaw, (tab: string) => aiTab = tab)"
      @add-file="ctx.addProjectFile"
      @link-meeting="ctx.linkRelatedMeeting"
      @go-transcript="ctx.goToTranscript"
      @go-summary="ctx.goToSummary"
      @go-todos="ctx.goToTodos"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useLayoutStore } from '@/stores/layout'
import { useTaskStore } from '@/stores/task'
import { useAiChat } from '@/composables/useAiChat'
import { useQuoteRef } from '@/composables/useQuoteRef'
import { useAiSessionsStore } from '@/stores/aiSessions'
import { useAiCommands } from '@/composables/useAiCommands'
import type { AiCommand } from '@/composables/useAiCommands'
import { showToast } from '@/composables/useToast'
import { beginResize } from '@/composables/useDivider'

import { useAiContext } from '@/composables/useAiContext'
import { useAiCommandActions } from '@/composables/useAiCommandActions'
import { useAiInsights } from '@/composables/useAiInsights'
import IconButton from '@/components/common/IconButton.vue'
import { modKey } from '@/utils/platform'

import AiSessionTabs from './ai/AiSessionTabs.vue'
import AiChatPanel from './ai/AiChatPanel.vue'
import AiContextPanel from './ai/AiContextPanel.vue'

const { t } = useI18n()
const route = useRoute()
const layout = useLayoutStore()
const taskStore = useTaskStore()

function onToggleDown(e: MouseEvent) {
  beginResize(e, 'right', { onClick: () => layout.toggleAi(), resizable: !layout.aiCollapsed })
}

const chat = useAiChat()
const quoteRef = useQuoteRef()
const aiSessions = useAiSessionsStore()
const cmds = useAiCommands()
const insights = useAiInsights()

// 上下文 Tab 数据 / Context Tab data
const ctx = useAiContext()

// 指令操作 / Command operations
const inputRef = ref<HTMLTextAreaElement | null>(null)
const cmdActions = useAiCommandActions(chat, inputRef)

// ── 本地状态 / Local state ──
const aiTab = ref('chat')
const inputText = ref('')
const renamingId = ref<string | null>(null)
const renameInput = ref('')
const sessionTabsRef = ref<InstanceType<typeof AiSessionTabs> | null>(null)
const chatPanelRef = ref<InstanceType<typeof AiChatPanel> | null>(null)

// ── 图编辑请求监听（从洞察台“在对话中编辑”按钮触发） / Diagram edit request watcher (triggered from Insight Deck "Edit in Chat" button) ──
watch(() => insights.diagramEditPending.value, (code) => {
  if (!code) return
  // 切换到对话 Tab / Switch to chat tab
  aiTab.value = 'chat'
  // 预填输入框 / Pre-fill input
  inputText.value = `请帮我修改这张图：\n${code}\n\n我想做的调整是：`
  // 清空请求 / Clear request
  insights.diagramEditPending.value = ''
  // 聚焦输入框 / Focus input
  nextTick(() => {
    const ta = chatPanelRef.value?.inputRef
    if (ta) {
      ta.focus()
      // 光标移到末尾（“我想做的调整是：”之后） / Move cursor to end
      ta.setSelectionRange(ta.value.length, ta.value.length)
    }
  })
})

// ── 计算属性 / Computed properties ──
const MEETING_ROUTE_NAMES = ['recording', 'generating']
const contextLabel = computed(() => {
  const routeName = route.name as string
  if (MEETING_ROUTE_NAMES.includes(routeName) && chat.messages.value) {
    if (taskStore.currentTask) return taskStore.currentTask.title || taskStore.currentTask.audio_name || t('ai-panel.current_meeting')
  }
  return t(`ai-panel.page.${routeName || 'start'}`)
})

const currentStatus = computed(() => {
  return taskStore.currentTask?.status ?? null
})

const filteredCmds = computed(() => {
  if (!inputText.value.startsWith('/')) return []
  return cmds.filterCommands(inputText.value.slice(1).toLowerCase(), currentStatus.value)
})

const quoteSourceLabel = computed(() => {
  const q = quoteRef.quoteRef.value
  if (!q) return ''
  return q.blockIndex >= 0
    ? t('ai-panel.quote.source_block', { source: q.source, index: q.blockIndex + 1 })
    : t('ai-panel.quote.source', { source: q.source })
})

// ── 会话管理 / Session management ──
function onNewSession() { aiSessions.createNewSession(); nextTick(() => scrollFeed()) }
function onSwitchSession(id: string) { chat.followUps.value = []; chat.injectPrompt.value = null; aiSessions.switchTo(id); nextTick(() => scrollFeed()) }
function startRename(id: string) {
  const s = aiSessions.sessions.find(s => s.id === id); if (!s) return
  renamingId.value = id; renameInput.value = s.name
  if (sessionTabsRef.value?.showOverflowMenu) sessionTabsRef.value.showOverflowMenu = false
  nextTick(() => { const el = sessionTabsRef.value?.renameInputRef; (Array.isArray(el) ? el[0] : el)?.focus(); (Array.isArray(el) ? el[0] : el)?.select() })
}
function confirmRename() { if (renamingId.value && renameInput.value.trim()) aiSessions.renameSession(renamingId.value, renameInput.value.trim()); renamingId.value = null }
function onDeleteSession(id: string) { if (renamingId.value === id) renamingId.value = null; aiSessions.deleteSession(id); nextTick(() => scrollFeed()) }

// ── 发送消息 / Send message ──
async function onSend() {
  const text = inputText.value.trim()
  if ((!text && !quoteRef.quoteRef.value) || chat.isLoading.value) return
  inputText.value = ''; autoResize()
  let fullText = text
  const qctx = quoteRef.getQuoteContext()
  if (qctx) fullText = text ? qctx.context + '\n' + t('ai-panel.user_instruction') + text : qctx.context + '\n' + t('ai-panel.process_quote')
  await chat.sendRaw(fullText); await scrollFeed()
}

// ── 输入处理 / Input handling ──
function handleInputKey(e: KeyboardEvent) {
  const isOpen = cmds.cmdOpen.value && filteredCmds.value.length > 0
  if (isOpen) {
    const items = filteredCmds.value
    if (e.key === 'ArrowDown') { e.preventDefault(); cmds.moveDown(items.length) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); cmds.moveUp() }
    else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (cmds.cmdIndex.value >= 0 && items[cmds.cmdIndex.value]) runCommand(items[cmds.cmdIndex.value]) }
    else if (e.key === 'Escape') { e.preventDefault(); cmds.close() }
    return
  }
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend() }
}

function handleInputChange() {
  autoResize()
  if (inputText.value.startsWith('/')) {
    const filtered = cmds.getAvailable(currentStatus.value).filter(c => c.key.slice(1).toLowerCase().includes(inputText.value.slice(1).toLowerCase()))
    filtered.length > 0 ? cmds.open() : cmds.close()
  } else cmds.close()
}

function autoResize() {
  // 从 chatPanel 获取 textarea 引用 / Get textarea ref from chatPanel
  const ta = chatPanelRef.value?.inputRef
  if (!ta) return
  ta.style.height = 'auto'
  ta.style.height = Math.min(ta.scrollHeight, 120) + 'px'
}

async function scrollFeed() {
  await nextTick()
  const feed = chatPanelRef.value?.feedRef
  if (feed) feed.scrollTop = feed.scrollHeight
}

function runCommand(cmd: AiCommand) { cmds.close(); inputText.value = ''; cmd.action() }

// ── 引用操作 / Quote operations ──
function onAcceptRewrite(content: string) { const ok = quoteRef.acceptRewrite(content); showToast(ok ? t('ai-panel.toast.replaced') : t('ai-panel.toast.locate_failed'), ok ? 'success' : 'warn') }
function onInsertToSummary(content: string) { const ok = quoteRef.insertToSummary(content); showToast(ok ? t('ai-panel.toast.inserted_summary') : t('ai-panel.toast.open_summary_first'), ok ? 'success' : 'warn') }
function onInsertToNotes(content: string) { const ok = quoteRef.insertToNotes(content); showToast(ok ? t('ai-panel.toast.inserted_notes') : t('ai-panel.toast.open_notes_first'), ok ? 'success' : 'warn') }

// ── 生命周期 / Lifecycle ──
onMounted(() => {
  cmds.registerCommands(cmdActions.buildCommands())
  window.addEventListener('quote-to-ai', onQuoteToAiEvent)
  window.addEventListener('global-ai-focus', onGlobalAiFocus)
  document.addEventListener('click', onDocClickCloseOverflow)
})
onBeforeUnmount(() => {
  window.removeEventListener('quote-to-ai', onQuoteToAiEvent)
  window.removeEventListener('global-ai-focus', onGlobalAiFocus)
  document.removeEventListener('click', onDocClickCloseOverflow)
})

function onDocClickCloseOverflow() {
  if (sessionTabsRef.value?.showOverflowMenu) sessionTabsRef.value.showOverflowMenu = false
}
function onGlobalAiFocus() { aiTab.value = 'chat'; nextTick(() => chatPanelRef.value?.inputRef?.focus()) }
function onQuoteToAiEvent(e: Event) {
  const detail = (e as CustomEvent).detail || {}
  if (layout.aiCollapsed) layout.toggleAi()
  aiTab.value = 'chat'
  nextTick(() => {
    chatPanelRef.value?.inputRef?.focus()
    if (detail.action) {
      const qctx = quoteRef.getQuoteContext()
      chat.sendRaw(qctx ? qctx.context + '\n' + t('ai-panel.user_instruction') + detail.action : detail.action)
    }
  })
}
watch(() => chat.messages.value.length, () => scrollFeed())
// 流式输出时自动滚动 / Auto-scroll during streaming
watch(() => chat.isStreaming.value, (streaming) => {
  if (streaming) {
    const interval = setInterval(() => scrollFeed(), 200)
    const stop = watch(() => chat.isStreaming.value, (v) => {
      if (!v) { clearInterval(interval); stop() }
    })
  }
})
</script>

<style scoped>
.ai-msg-actions { display: flex; gap: 6px; padding: 4px 0 2px; opacity: 0; transition: opacity 0.15s; }
.ai-msg:hover .ai-msg-actions { opacity: 1; }
.ai-insert-btn { display: inline-flex; align-items: center; gap: 3px; padding: 3px 8px; border-radius: 4px; font-size: 11px; color: var(--muted); background: transparent; border: 1px solid var(--border); cursor: pointer; transition: all 0.12s; }
.ai-insert-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft, oklch(95% 0.02 255)); }
.ai-insert-btn svg { width: 12px; height: 12px; flex-shrink: 0; }
.verified-changes-block { margin-top: 12px; padding: 12px; background: var(--bg-elevated, #f8f9fa); border-radius: 8px; border: 1px solid var(--border); }
.vc-header { font-size: 12px; font-weight: 600; color: var(--text-primary); margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.vc-list { display: flex; flex-direction: column; gap: 8px; }
.vc-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: var(--bg-card, #fff); border-radius: 6px; border-left: 3px solid var(--border); transition: all 0.15s; }
.vc-item.is-verified { border-left-color: #10b981; background: linear-gradient(90deg, rgba(16, 185, 129, 0.05) 0%, transparent 100%); }
.vc-item:not(.is-verified) { border-left-color: #f59e0b; background: linear-gradient(90deg, rgba(245, 158, 11, 0.05) 0%, transparent 100%); }
.vc-icon { font-size: 14px; flex-shrink: 0; }
.vc-desc { flex: 1; font-size: 12px; color: var(--text-secondary); line-height: 1.5; }
.vc-status { font-size: 11px; color: var(--muted); white-space: nowrap; padding: 2px 6px; border-radius: 3px; background: var(--bg-subtle, #f0f0f0); }
.vc-item.is-verified .vc-status { color: #059669; background: rgba(16, 185, 129, 0.1); }
.vc-item:not(.is-verified) .vc-status { color: #d97706; background: rgba(245, 158, 11, 0.1); }

</style>
