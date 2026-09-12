<template>
  <div class="ai" :class="{ 'is-collapsed': layout.aiCollapsed }">
    <button
      class="ai-toggle"
      :title="layout.aiCollapsed ? t('ai-panel.expand') : t('ai-panel.collapse')"
      :aria-label="layout.aiCollapsed ? t('ai-panel.expand') : t('ai-panel.collapse')"
      :aria-expanded="!layout.aiCollapsed"
      @mousedown="onToggleDown($event)"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
    </button>
    <div class="ai-collapsed-strip">
      <div class="ai-collapsed-icon" :class="{ 'is-proactive': proactive.proactiveEnabled.value && proactive.unreadCount.value > 0 }" @click="layout.toggleAi()" style="position:relative">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
        <span v-if="proactive.proactiveEnabled.value && proactive.unreadCount.value > 0" class="breathing-dot"></span>
        <span v-if="proactive.proactiveEnabled.value && proactive.unreadCount.value > 0" class="unread-badge">{{ proactive.unreadCount.value }}</span>
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
    <!-- Tab 栏 -->
    <div class="ai-panel-tabs">
      <div class="ai-panel-tabs-list">
        <button class="ai-panel-tab" :class="{ 'is-active': aiTab === 'chat' }" @click="aiTab = 'chat'">{{ t('ai-panel.tab_chat') }}</button>
        <button class="ai-panel-tab" :class="{ 'is-active': aiTab === 'analysis' }" @click="aiTab = 'analysis'">{{ t('ai-panel.tab_analysis') }}</button>
        <button class="ai-panel-tab" :class="{ 'is-active': aiTab === 'context' }" @click="aiTab = 'context'">
          {{ t('ai-panel.tab_context') }}
          <span v-if="ctx.contextResourceCount.value > 0" class="tab-badge">{{ ctx.contextResourceCount.value }}</span>
        </button>
      </div>
      <!-- 主动 AI 统一控件组（胶囊） -->
      <div class="ai-proactive-group" :class="{ 'is-off': !proactive.proactiveEnabled.value, 'is-on': proactive.proactiveEnabled.value && !showProactiveSettings, 'is-settings': proactive.proactiveEnabled.value && showProactiveSettings }">
        <button class="pg-toggle" :title="proactive.proactiveEnabled.value ? t('ai-panel.proactive.disable') : t('ai-panel.proactive.enable')" :aria-label="t('ai-panel.proactive.sidebar_indicator')" @click="proactive.toggleEnabled(); if (showProactiveSettings) showProactiveSettings = false">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
        </button>
        <div class="pg-divider"></div>
        <button class="pg-settings" :title="t('ai-panel.proactive.settings_title')" :aria-label="t('ai-panel.proactive.settings_title')" @click="showProactiveSettings = !showProactiveSettings">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        </button>
      </div>
    </div>

    <!-- 主动 AI 设置面板 -->
    <AiProactiveSettings
      :config="proactive.proactiveConfig.value"
      :is-open="proactive.proactiveEnabled.value && showProactiveSettings"
      @category-toggle="onCategoryToggle"
      @sensitivity-change="onSensitivityChange"
      @notif-toggle="onNotifToggle"
      @dnd-toggle="onDndToggle"
      @dnd-time-change="onDndTimeChange"
    />

    <!-- 会话标签栏（仅对话 Tab） -->
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

    <!-- 对话 Tab -->
    <AiChatPanel
      v-show="aiTab === 'chat'"
      ref="chatPanelRef"
      :messages="chat.messages.value"
      :is-loading="chat.isLoading.value"
      :rewrite-pending="quoteRef.rewritePending.value"
      :verified-changes="chat.verifiedChanges.value"
      :inject-prompt="chat.injectPrompt.value"
      :proactive-messages="proactive.proactiveMessages.value"
      :acted-actions="actedActions"
      :proactive-enabled="proactive.proactiveEnabled.value"
      :latest-unread="proactive.latestUnread.value"
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
      @toggle-proactive="proactive.toggleExpanded"
      @proactive-action="onProactiveAction"
      @banner-click="onBannerClick"
      @banner-close="onBannerClose"
      @clear-quote="quoteRef.clearQuote"
      @run-command="runCommand"
      @input-key="handleInputKey"
      @input-change="handleInputChange"
      @update:input-text="inputText = $event"
    />

    <!-- 分析 Tab -->
    <AiAnalysisPanel
      v-show="aiTab === 'analysis'"
      :has-data="analysis.hasData.value"
      :overview="analysis.overview.value"
      :speaker-stats="analysis.speakerStats.value"
      :todo-stats="analysis.todoStats.value"
      :chapters="analysis.chapters.value"
    />

    <!-- 上下文 Tab -->
    <AiContextPanel
      v-show="aiTab === 'context'"
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
import { ref, computed, reactive, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useLayoutStore } from '@/stores/layout'
import { useAiChat } from '@/composables/useAiChat'
import { useQuoteRef } from '@/composables/useQuoteRef'
import { useAiSessionsStore } from '@/stores/aiSessions'
import { useAiAnalysis } from '@/composables/useAiAnalysis'
import { useAiCommands } from '@/composables/useAiCommands'
import type { AiCommand } from '@/composables/useAiCommands'
import { showToast } from '@/composables/useToast'
import { beginResize } from '@/composables/useDivider'
import { useAiProactive } from '@/composables/useAiProactive'
import type { ProactiveMessage, ProactiveAction } from '@/composables/useAiProactive'
import { useAiContext } from '@/composables/useAiContext'
import { useAiCommandActions } from '@/composables/useAiCommandActions'
import IconButton from '@/components/common/IconButton.vue'
import AiProactiveSettings from './ai/AiProactiveSettings.vue'
import AiSessionTabs from './ai/AiSessionTabs.vue'
import AiChatPanel from './ai/AiChatPanel.vue'
import AiAnalysisPanel from './ai/AiAnalysisPanel.vue'
import AiContextPanel from './ai/AiContextPanel.vue'

const { t } = useI18n()
const route = useRoute()
const layout = useLayoutStore()

function onToggleDown(e: MouseEvent) {
  beginResize(e, 'right', { onClick: () => layout.toggleAi(), resizable: !layout.aiCollapsed })
}

const chat = useAiChat()
const quoteRef = useQuoteRef()
const aiSessions = useAiSessionsStore()
const analysis = useAiAnalysis()
const proactive = useAiProactive()
const cmds = useAiCommands()

// 上下文 Tab 数据
const ctx = useAiContext({
  overview: computed(() => analysis.overview.value),
  todoStats: computed(() => analysis.todoStats.value),
  chapters: computed(() => analysis.chapters.value),
})

// 指令操作
const inputRef = ref<HTMLTextAreaElement | null>(null)
const cmdActions = useAiCommandActions(chat, inputRef)

// ── 本地状态 ──
const aiTab = ref('chat')
const inputText = ref('')
const showProactiveSettings = ref(false)
const renamingId = ref<string | null>(null)
const renameInput = ref('')
const sessionTabsRef = ref<InstanceType<typeof AiSessionTabs> | null>(null)
const chatPanelRef = ref<InstanceType<typeof AiChatPanel> | null>(null)
const actedActions = reactive<Record<string, boolean>>({})

// ── 计算属性 ──
const MEETING_ROUTE_NAMES = ['recording', 'generating']
const contextLabel = computed(() => {
  const routeName = route.name as string
  if (MEETING_ROUTE_NAMES.includes(routeName) && chat.messages.value) {
    const taskStore = (window as any).__taskStore
    if (taskStore?.currentTask) return taskStore.currentTask.title || taskStore.currentTask.audio_name || t('ai-panel.current_meeting')
  }
  return t(`ai-panel.page.${routeName || 'start'}`)
})

const currentStatus = computed(() => {
  const taskStore = (window as any).__taskStore
  return taskStore?.currentTask?.status ?? null
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

// ── 会话管理 ──
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

// ── 发送消息 ──
async function onSend() {
  const text = inputText.value.trim()
  if ((!text && !quoteRef.quoteRef.value) || chat.isLoading.value) return
  inputText.value = ''; autoResize()
  let fullText = text
  const qctx = quoteRef.getQuoteContext()
  if (qctx) fullText = text ? qctx.context + '\n' + t('ai-panel.user_instruction') + text : qctx.context + '\n' + t('ai-panel.process_quote')
  await chat.sendRaw(fullText); await scrollFeed()
}

// ── 输入处理 ──
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
  // 从 chatPanel 获取 textarea 引用
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

// ── 引用操作 ──
function onAcceptRewrite(content: string) { const ok = quoteRef.acceptRewrite(content); showToast(ok ? t('ai-panel.toast.replaced') : t('ai-panel.toast.locate_failed'), ok ? 'success' : 'warn') }
function onInsertToSummary(content: string) { const ok = quoteRef.insertToSummary(content); showToast(ok ? t('ai-panel.toast.inserted_summary') : t('ai-panel.toast.open_summary_first'), ok ? 'success' : 'warn') }
function onInsertToNotes(content: string) { const ok = quoteRef.insertToNotes(content); showToast(ok ? t('ai-panel.toast.inserted_notes') : t('ai-panel.toast.open_notes_first'), ok ? 'success' : 'warn') }

// ── 主动 AI ──
function onProactiveAction(pm: ProactiveMessage, act: ProactiveAction) {
  const key = pm.id + ':' + act.key; if (actedActions[key]) return; actedActions[key] = true; proactive.markAsRead(pm.id)
  if (act.key === 'view') showToast(t('ai-panel.proactive.toast_view'), 'info')
  else if (act.key === 'sync') showToast(t('ai-panel.proactive.toast_sync'), 'success')
  else if (act.key === 'generate') { chat.sendRaw(t('ai-panel.proactive.prompt_summary')); aiTab.value = 'chat' }
}
function onBannerClick() { if (proactive.latestUnread.value) proactive.markAsRead(proactive.latestUnread.value.id); nextTick(() => scrollFeed()) }
function onBannerClose() { if (proactive.latestUnread.value) proactive.dismissProactiveMessage(proactive.latestUnread.value.id) }

// ── 主动 AI 设置 ──
function onCategoryToggle(key: string, val: boolean) { proactive.proactiveConfig.value.categories[key] = val; proactive.saveConfig() }
function onSensitivityChange(field: string, val: number) { (proactive.proactiveConfig.value.sensitivity as Record<string, number>)[field] = val; proactive.saveConfig() }
function onNotifToggle(field: string, val: boolean) { (proactive.proactiveConfig.value.notifications as Record<string, boolean>)[field] = val; proactive.saveConfig() }
function onDndToggle(val: boolean) { proactive.proactiveConfig.value.dnd.enabled = val; proactive.saveConfig() }
function onDndTimeChange(field: 'startHour' | 'endHour', val: number) { proactive.proactiveConfig.value.dnd[field] = val; proactive.saveConfig() }

// ── 生命周期 ──
onMounted(() => {
  cmds.registerCommands(cmdActions.buildCommands())
  window.addEventListener('quote-to-ai', onQuoteToAiEvent)
  window.addEventListener('global-ai-focus', onGlobalAiFocus)
  window.addEventListener('ai-scroll-to-unread', onScrollToUnread)
  document.addEventListener('click', onDocClickCloseOverflow)
})
onBeforeUnmount(() => {
  window.removeEventListener('quote-to-ai', onQuoteToAiEvent)
  window.removeEventListener('global-ai-focus', onGlobalAiFocus)
  window.removeEventListener('ai-scroll-to-unread', onScrollToUnread)
  document.removeEventListener('click', onDocClickCloseOverflow)
})

function onDocClickCloseOverflow(e: MouseEvent) {
  if (sessionTabsRef.value?.showOverflowMenu) sessionTabsRef.value.showOverflowMenu = false
  if (showProactiveSettings.value) {
    const target = e.target as HTMLElement
    if (!target.closest('.ai-proactive-settings') && !target.closest('.ai-proactive-group')) showProactiveSettings.value = false
  }
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
function onScrollToUnread() {
  const first = proactive.getFirstUnread(); if (!first) return
  if (!first.expanded) proactive.toggleExpanded(first.id)
  nextTick(() => { const el = document.getElementById('proactive-' + first.id); if (el && chatPanelRef.value?.feedRef) el.scrollIntoView({ behavior: 'smooth', block: 'center' }) })
}

watch(() => chat.messages.value.length, () => scrollFeed())
</script>

<style scoped>
.ai-welcome { text-align: center; padding: 40px 0; color: var(--muted); font-size: 14px; }
.ai-welcome-hint { font-size: 12px; color: var(--subtle); margin-top: 8px; }
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
