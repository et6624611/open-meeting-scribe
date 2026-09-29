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
      <!-- 头部右侧不再放操作：头部在 conv-layout 下不可见，清空/新建已收进会话弹层顶行 -->
    </div>
    <div class="ai-panel-context"><span>{{ contextLabel }}</span></div>
    <!-- Tab 栏 / Tab bar（会话入口常驻此行右端：面板头部在 conv-layout 下被隐藏，Tab 行才是可见顶部） -->
    <div class="ai-panel-tabs">
      <button class="ai-panel-tab" :class="{ 'is-active': aiTab === 'chat' }" @click="aiTab = 'chat'">{{ t('ai-panel.tab_chat') }}</button>
      <button class="ai-panel-tab" :class="{ 'is-active': aiTab === 'context' }" @click="aiTab = 'context'">
        {{ t('ai-panel.tab_context') }}
        <span v-if="ctx.contextResourceCount.value > 0" class="tab-badge">{{ ctx.contextResourceCount.value }}</span>
      </button>
      <AiSessionPopover
        v-if="aiTab === 'chat'"
        :sessions="aiSessions.sessions"
        :active-session-id="aiSessions.currentBucket.activeSessionId"
        :renaming-id="renamingId"
        :rename-input="renameInput"
        @switch="onSwitchSession"
        @new-session="onNewSession"
        @start-rename="startRename"
        @delete="onDeleteSession"
        @confirm-rename="confirmRename"
        @cancel-rename="cancelRename"
        @clear="onClearCurrent"
        @update:rename-input="renameInput = $event"
      />
    </div>

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
      :rewrite-not-persisted="chat.rewriteNotPersisted.value"
      :summary-proposal="chat.summaryProposal.value"
      :quote-text="quoteRef.quoteRef.value?.text || ''"
      :quote-source="quoteSourceLabel"
      :cmd-open="cmds.cmdOpen.value"
      :cmd-index="cmds.cmdIndex.value"
      :filtered-cmds="filteredCmds"
      :input-text="inputText"
      :format-change="chat.formatChangeDescription"
      :chat-mode="chat.chatMode.value"
      :active-engine="chat.activeEngine.value"
      :session-model="chat.sessionModel.value"
      :model-options="chat.modelCandidates.value"
      :detail-model-label="chat.detailModelLabel.value"
      :cli-probe="chat.cliProbe.value"
      :agent-available="chat.agentAvailable.value"
      :agent-engine-name="chat.agentEngineName.value"
      :agent-engine-model="chat.agentEngineModel.value"
      :agent-models="chat.agentModels.value"
      :agent-models-reason="chat.agentModelsReason.value"
      :agent-models-loading="chat.agentModelsLoading.value"
      @send="onSend"
      @stop-generation="chat.stopGeneration"
      @accept-rewrite="onAcceptRewrite"
      @clear-rewrite="quoteRef.clearRewrite"
      @inject-all="chat.doInjectAll"
      @dismiss-inject="chat.injectPrompt.value = null"
      @retry-write="onRetryWrite"
      @dismiss-not-persisted="chat.rewriteNotPersisted.value = null"
      @accept-summary="chat.acceptSummaryProposal()"
      @reject-summary="chat.rejectSummaryProposal()"
      @clear-quote="quoteRef.clearQuote"
      @run-command="runCommand"
      @input-key="handleInputKey"
      @input-change="handleInputChange"
      @update:input-text="inputText = $event"
      @update:chat-mode="chat.setChatMode($event)"
      @update:session-model="chat.setSessionModel($event)"
      @update:agent-model="chat.setAgentModel($event)"
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
      :linked-project="ctx.linkedProject.value"
      :related-meetings="ctx.relatedMeetings.value"
      :visible-related-meetings="ctx.visibleRelatedMeetings.value"
      :related-meeting-count="ctx.relatedMeetingCount.value"
      :context-source="ctx.contextSource.value"
      @show-all-meetings="ctx.showAllMeetings.value = !ctx.showAllMeetings.value"
      @generate-summary="ctx.generateSummary(chat.sendRaw, (tab: string) => aiTab = tab)"
      @link-meeting="ctx.linkRelatedMeeting"
      @go-transcript="ctx.goToTranscript"
      @go-summary="ctx.goToSummary"
      @go-todos="ctx.goToTodos"
      @go-project="ctx.goToProject"
      @go-meeting="ctx.goToMeeting"
    />

    <!-- AI 命令删除确认弹窗 / AI command delete confirm dialog -->
    <ConfirmDialog
      v-model="cmdActions.showDeleteConfirm.value"
      :title="t('ai-panel.delete_task_title')"
      :message="t('ai-panel.delete_task_confirm', { id: cmdActions.pendingDeleteTaskId.value?.slice(0, 8) ?? '' })"
      @confirm="cmdActions.confirmDeleteTask()"
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
import { cleanupAgentWorkspace } from '@/api/chat'
import { useQuoteRef } from '@/composables/useQuoteRef'
import { useAiSessionsStore } from '@/stores/aiSessions'
import { useAiCommands } from '@/composables/useAiCommands'
import type { AiCommand } from '@/composables/useAiCommands'
import { showToast } from '@/composables/useToast'
import { beginResize } from '@/composables/useDivider'

import { useAiContext } from '@/composables/useAiContext'
import { useAiCommandActions } from '@/composables/useAiCommandActions'
import { useAiInsights } from '@/composables/useAiInsights'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { modKey } from '@/utils/platform'

import AiSessionPopover from './ai/AiSessionPopover.vue'
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
// 重命名的聚焦/全选由 AiSessionPopover 内部完成
function startRename(id: string) {
  const s = aiSessions.sessions.find(s => s.id === id); if (!s) return
  renamingId.value = id; renameInput.value = s.name
}
function confirmRename() { if (renamingId.value && renameInput.value.trim()) aiSessions.renameSession(renamingId.value, renameInput.value.trim()); renamingId.value = null }
function cancelRename() { renamingId.value = null }
/** 清空当前会话（弹层顶行的内联确认已保证不会误触） */
function onClearCurrent() { chat.clearConversation(); nextTick(() => scrollFeed()) }
function onDeleteSession(id: string) { if (renamingId.value === id) renamingId.value = null; aiSessions.deleteSession(id); void cleanupAgentWorkspace(id, taskStore.currentTaskId || undefined); nextTick(() => scrollFeed()) }

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

/** 输入区高度重算：交给 AiChatPanel 的唯一入口（行数 × 整数行盒，上限转区内滚动）。
    这里不再自己算高度——原先 Math.min(scrollHeight, 120) 与 CSS 的 min-height:32px /
    max-height:150px 三处各写一套，且只在 input 事件上触发，导致会话恢复、插入引用、
    指令回填、洞察台图表预填等路径改值后高度停在单行，末行被切成半行。 */
function autoResize() {
  chatPanelRef.value?.resizeInput?.()
}

async function scrollFeed() {
  await nextTick()
  const feed = chatPanelRef.value?.feedRef
  if (feed) feed.scrollTop = feed.scrollHeight
}

function runCommand(cmd: AiCommand) { cmds.close(); inputText.value = ''; cmd.action() }

// ── 引用操作 / Quote operations ──
// 插入纪要/随记已下架（2026-09）：仅保留划词改写的替换原文入口
function onAcceptRewrite(content: string) { const ok = quoteRef.acceptRewrite(content); showToast(ok ? t('ai-panel.toast.replaced') : t('ai-panel.toast.locate_failed'), ok ? 'success' : 'warn') }

// ── 生命周期 / Lifecycle ──
onMounted(() => {
  cmds.registerCommands(cmdActions.buildCommands())
  window.addEventListener('quote-to-ai', onQuoteToAiEvent)
  window.addEventListener('global-ai-focus', onGlobalAiFocus)
})
onBeforeUnmount(() => {
  window.removeEventListener('quote-to-ai', onQuoteToAiEvent)
  window.removeEventListener('global-ai-focus', onGlobalAiFocus)
})

function onGlobalAiFocus() { aiTab.value = 'chat'; nextTick(() => chatPanelRef.value?.inputRef?.focus()) }
/** 完成护栏（§5.4）横幅重试：清横幅后原样重发，重新打轮级意图标 */
function onRetryWrite(text: string) {
  chat.rewriteNotPersisted.value = null
  chat.setRewriteIntent(true)
  void chat.sendRaw(text)
}
function onQuoteToAiEvent(e: Event) {
  const detail = (e as CustomEvent).detail || {}
  if (layout.aiCollapsed) layout.toggleAi()
  aiTab.value = 'chat'
  nextTick(() => {
    chatPanelRef.value?.inputRef?.focus()
    // prefill：只填输入框不发送（洞察板共创起跳用，用户可追加具体诉求后自己回车）
    if (detail.prefill) {
      inputText.value = detail.prefill
      // 模式即权限（§5.1）：共创只打「改写意图」轮级标（完成护栏输入），不再按按钮升档——
      // 智能体模式本身固有写回权；问答引擎无写工具通道，起跳时仍明确告知需切换。
      if (detail.coCreate) {
        chat.setRewriteIntent(true)
        if (chat.chatMode.value === 'agent') showToast(t('ai-panel.agent_mode_writable'), 'info')
        else showToast(t('ai-panel.board_cocreate_needs_agent'), 'warn')
      }
      return
    }
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
