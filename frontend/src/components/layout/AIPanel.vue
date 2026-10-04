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
      <div class="ai-collapsed-icon" @click="layout.toggleAi()" style="position:relative">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m11 17 2 2a1 1 0 1 0 3-3"/><path d="m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 0 0 0 1.42.25L21 4"/><path d="m21 3 1 11h-2"/><path d="M3 3 2 14l6.5 6.5a1 1 0 1 0 3-3"/><path d="M3 4h8"/></svg>
      </div>
      <span class="ai-collapsed-label">{{ t('ai-panel.collapsed_label') }}</span>
    </div>
    <!-- 极简顶部：左侧位置标题，右侧三图标（上下文 / 历史任务 / 新建）。
         对话与上下文不再用 Tab 行：点脑形图标整区切换，图标在上下文态变形为返回箭头 -->
    <div class="ai-panel-header">
      <div class="ai-panel-header-left">
        <div class="ai-header-avatar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m11 17 2 2a1 1 0 1 0 3-3"/><path d="m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 0 0 0 1.42.25L21 4"/><path d="m21 3 1 11h-2"/><path d="M3 3 2 14l6.5 6.5a1 1 0 1 0 3-3"/><path d="M3 4h8"/></svg></div>
        <span class="ai-header-title" :title="contextLabel">{{ contextLabel }}</span>
      </div>
      <div class="ai-panel-header-right">
        <!-- 上下文：对话态脑形，上下文态同槽位变形为返回箭头 -->
        <button
          class="ai-header-icon"
          :class="{ 'is-ctx': aiTab === 'context' }"
          :title="aiTab === 'context' ? t('ai-panel.back_to_chat') : t('ai-panel.tab_context')"
          :aria-label="aiTab === 'context' ? t('ai-panel.back_to_chat') : t('ai-panel.tab_context')"
          :aria-pressed="aiTab === 'context'"
          @click="toggleContext"
        >
          <svg class="ic-brain" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/>
            <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 0 12 18Z"/>
            <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/>
            <path d="M17.6 6.5a3 3 0 0 0 .4-1.4"/><path d="M6 5.1A3 3 0 0 0 6.4 6.5"/>
            <path d="M6 18a4 4 0 0 1-2-.5"/><path d="M20 17.5A4 4 0 0 1 18 18"/>
          </svg>
          <svg class="ic-back" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m15 18-6-6 6-6"/>
          </svg>
        </button>
        <AiSessionPopover
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
        <!-- 新建任务：圈内加号 -->
        <button
          class="ai-header-icon"
          :title="t('ai-panel.new_session')"
          :aria-label="t('ai-panel.new_session')"
          @click="onNewSession"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
            <circle cx="12" cy="12" r="9.2"/>
            <path d="M12 8.5v7"/><path d="M8.5 12h7"/>
          </svg>
        </button>
      </div>
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
      :notes-proposal="chat.notesProposal.value"
      :quote-text="quoteRef.quoteRef.value?.text || ''"
      :quote-source="quoteSourceLabel"
      :cmd-open="cmds.cmdOpen.value"
      :cmd-index="cmds.cmdIndex.value"
      :filtered-cmds="filteredCmds"
      :mention-open="mentions.mentionOpen.value"
      :mention-index="mentions.mentionIndex.value"
      :filtered-mentions="filteredMentions"
      :pending-attachments="pendingAttachments"
      :uploading-attachments="uploadingAttachments"
      :input-text="inputText"
      :format-change="chat.formatChangeDescription"
      :chat-mode="chat.chatMode.value"
      :session-tier="chat.sessionAuthTier.value"
      :pending-tier="chat.pendingAuthTier.value"
      :tier-menu-signal="chat.tierMenuSignal.value"
      :tier-denial="chat.tierDenial.value"
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
      @open-summary-preview="chat.openSummaryPreview()"
      @accept-notes="chat.acceptNotesProposal()"
      @reject-notes="chat.rejectNotesProposal()"
      @open-notes-preview="chat.openNotesPreview()"
      @clear-quote="quoteRef.clearQuote"
      @run-command="runCommand"
      @select-mention="selectMention"
      @remove-attachment="removePendingAttachment"
      @input-key="handleInputKey"
      @input-change="handleInputChange"
      @update:input-text="inputText = $event"
      @update:chat-mode="chat.setChatMode($event)"
      @update:pending-tier="chat.setPendingAuthTier($event)"
      @apply-new-session="onTierApplyNewSession"
      @raise-tier="chat.requestTierMenu()"
      @raise-tier-preset="chat.requestTierMenu('workspace_write')"
      @update:session-model="chat.setSessionModel($event)"
      @update:agent-model="chat.setAgentModel($event)"
      @edit-resend="chat.editAndResend"
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
      :has-notes="ctx.hasNotes.value"
      :notes-char-count="ctx.notesCharCount.value"
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
      @go-notes="ctx.goToNotes"
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

    <!-- @附件：隐藏的系统文件选择器（图片多选 + 常见文档类型） -->
    <input
      ref="fileInputRef"
      type="file"
      multiple
      accept="image/*,.pdf,.docx,.txt,.md,.markdown,.csv,.tsv,.json,.log,.xml,.yaml,.yml,.xlsx,.pptx"
      style="display:none"
      @change="onFilesPicked"
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
import { cleanupAgentWorkspace, uploadChatAttachments } from '@/api/chat'
import type { AttachmentMeta } from '@/api/chat'
import { useQuoteRef } from '@/composables/useQuoteRef'
import { useAiSessionsStore } from '@/stores/aiSessions'
import { useAiCommands } from '@/composables/useAiCommands'
import type { AiCommand } from '@/composables/useAiCommands'
import { useAiMentions, MENTION_SOURCES, parseMention, mentionToken } from '@/composables/useAiMentions'
import type { MentionSource } from '@/composables/useAiMentions'
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

const { t, locale } = useI18n()
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
const mentions = useAiMentions()
const insights = useAiInsights()

// 上下文 Tab 数据 / Context Tab data
const ctx = useAiContext()

// 指令操作 / Command operations
const inputRef = ref<HTMLTextAreaElement | null>(null)
const cmdActions = useAiCommandActions(chat, inputRef)

// ── 本地状态 / Local state ──
const aiTab = ref('chat')
/** 上下文整区切换：脑形图标即开关，上下文态图标变形为返回箭头 */
function toggleContext() {
  aiTab.value = aiTab.value === 'context' ? 'chat' : 'context'
}
/** Esc 从上下文视图返回对话（对话视图的 Esc 由指令面板/编辑态自行处理） */
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && aiTab.value === 'context') aiTab.value = 'chat'
}
const inputText = ref('')
// ── @附件：待发送附件（上传成功后挂起，发送随当前轮消费） / Pending @附件 attachments ──
const pendingAttachments = ref<AttachmentMeta[]>([])
const uploadingAttachments = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

/** 唤起系统文件选择器 */
function openFilePicker() {
  // 允许总数不超过 6（含已挂起）
  if (pendingAttachments.value.length >= 6) {
    showToast(t('ai-panel.attachment_limit', { max: 6 }), 'warn')
    return
  }
  fileInputRef.value?.click()
}

/** 文件选定 → 立即上传 → 挂起；失败 toast，不残留 */
async function onFilesPicked(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''  // 重置，允许重复选同一文件
  if (!files.length) return
  const room = 6 - pendingAttachments.value.length
  const picked = files.slice(0, room)
  if (files.length > room) showToast(t('ai-panel.attachment_limit', { max: 6 }), 'warn')

  uploadingAttachments.value = true
  try {
    const metas = await uploadChatAttachments(picked)
    pendingAttachments.value.push(...metas)
  } catch {
    showToast(t('ai-panel.attachment_upload_failed'), 'warn')
  } finally {
    uploadingAttachments.value = false
  }
}

/** 发送前移除单个挂起附件（服务端文件暂不物理删除，属临时数据） */
function removePendingAttachment(id: string) {
  pendingAttachments.value = pendingAttachments.value.filter(a => a.id !== id)
}
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
  return cmds.filterCommands(inputText.value.slice(1), currentStatus.value)
})

// ── @ 引用面板：与 / 指令面板同构互斥（parseMention 只认尾部 @query） ──
const filteredMentions = computed<MentionSource[]>(() => {
  const m = parseMention(inputText.value)
  if (!m) return []
  const task = taskStore.currentTask
  const recording = task?.status === 'recording' || task?.status === 'paused'
  // 可用性跟当前任务数据走：原文=已落盘对话或录音中；纪要/随记按上下文口径
  const availability: Record<string, boolean> = {
    '@原文': (task?.dialogue?.length ?? 0) > 0 || !!recording,
    '@纪要': ctx.hasSummary.value,
    '@随记': ctx.hasNotes.value,
    // 附件随时可上传，不依赖会议数据
    '@附件': true,
  }
  const q = m.query.toLowerCase()
  // 过滤按当前语言令牌匹配（英文环境输入 @tra 命中 @transcript）
  return MENTION_SOURCES.filter(s => availability[s.token] && mentionToken(s, locale.value).slice(1).toLowerCase().includes(q))
})

const quoteSourceLabel = computed(() => {
  const q = quoteRef.quoteRef.value
  if (!q) return ''
  return q.blockIndex >= 0
    ? t('ai-panel.quote.source_block', { source: q.source, index: q.blockIndex + 1 })
    : t('ai-panel.quote.source', { source: q.source })
})

// ── 会话管理 / Session management ──
// 新建即锁定当前待生效档位（chat.startNewSession 内 createNewSession(pendingTier)）
function onNewSession() { chat.startNewSession(); nextTick(() => scrollFeed()) }
/** 档位弹层「开新会话应用」：与头部新建同一路径 */
function onTierApplyNewSession() { onNewSession() }
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

/**
 * 斜杠串统一执行入口：精确解析（含行内参数，如 /speakers add 张三）→ 面板高亮候选 → 未知拦截。
 * 未知串只 toast 不发送，绝不让 `/foo` 落进模型。返回 true=已消费（含未知），调用方应中止发送。
 */
function tryRunSlashCommand(raw: string): boolean {
  const resolved = cmds.resolveCommand(raw, currentStatus.value)
  if (resolved) { runCommand(resolved.cmd, resolved.args); return true }
  const items = filteredCmds.value
  const picked = items[cmds.cmdIndex.value >= 0 ? cmds.cmdIndex.value : 0]
  if (picked) { runCommand(picked); return true }
  showToast(t('ai-panel.cmd_unknown', { cmd: raw.trim().split(/\s/)[0] }), 'warn')
  return true
}

// ── 发送消息 / Send message ──
async function onSend() {
  const text = inputText.value.trim()
  // 斜杠开头一律走指令链路（含未知串拦截），不进入普通消息发送
  if (text.startsWith('/')) { tryRunSlashCommand(text); return }
  if ((!text && !quoteRef.quoteRef.value && pendingAttachments.value.length === 0) || chat.isLoading.value) return
  const attachments = pendingAttachments.value.slice()
  inputText.value = ''; pendingAttachments.value = []; autoResize()
  let fullText = text
  const qctx = quoteRef.getQuoteContext()
  if (qctx) fullText = text ? qctx.context + '\n' + t('ai-panel.user_instruction') + text : qctx.context + '\n' + t('ai-panel.process_quote')
  await chat.sendRaw(fullText, undefined, attachments); await scrollFeed()
}

// ── 输入处理 / Input handling ──
function handleInputKey(e: KeyboardEvent) {
  // IME 组合期不接管任何键（ Enter 是选字确认，不是发送/选中）
  if (e.isComposing) return
  const isCmdOpen = cmds.cmdOpen.value && filteredCmds.value.length > 0
  const isMentionOpen = mentions.mentionOpen.value && filteredMentions.value.length > 0
  if (isMentionOpen) {
    const items = filteredMentions.value
    if (e.key === 'ArrowDown') { e.preventDefault(); mentions.moveDown(items.length) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); mentions.moveUp() }
    else if (e.key === 'Enter') { e.preventDefault(); if (mentions.mentionIndex.value >= 0 && items[mentions.mentionIndex.value]) selectMention(items[mentions.mentionIndex.value]) }
    else if (e.key === 'Escape') { e.preventDefault(); mentions.close() }
    return
  }
  if (isCmdOpen) {
    const items = filteredCmds.value
    if (e.key === 'ArrowDown') { e.preventDefault(); cmds.moveDown(items.length) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); cmds.moveUp() }
    else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); tryRunSlashCommand(inputText.value) }
    else if (e.key === 'Escape') { e.preventDefault(); cmds.close() }
    return
  }
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend() }
}

function handleInputChange() {
  autoResize()
  if (inputText.value.startsWith('/')) {
    mentions.close()
    // 单一数据源：候选只认 filteredCmds；输入精确等于（或是某指令的带参数形式）时高亮定位到该项
    const items = filteredCmds.value
    if (items.length) {
      cmds.open()
      const q = inputText.value.slice(1).trim().toLowerCase()
      const exact = items.findIndex((c) => {
        const head = c.key.slice(1).toLowerCase()
        return q === head || q.startsWith(head + ' ')
      })
      cmds.setIndex(exact >= 0 ? exact : 0)
    } else {
      cmds.close()
    }
  } else {
    cmds.close()
    // @ 引用面板：尾部存在 @query 即激活（无可用源时保持关闭，不挡输入）
    parseMention(inputText.value) && filteredMentions.value.length > 0 ? mentions.open() : mentions.close()
  }
}

/** 选中引用源：尾部 @query 替换为完整令牌，面板关闭，焦点留在输入框。
    @附件 不插令牌——唤起文件选择器，尾部残留的 @附 等残缺串清掉。 */
function selectMention(src: MentionSource) {
  mentions.close()
  if (src.token === '@附件') {
    const m = parseMention(inputText.value)
    if (m) inputText.value = inputText.value.slice(0, m.at)
    autoResize()
    openFilePicker()
    nextTick(() => chatPanelRef.value?.inputRef?.focus())
    return
  }
  inputText.value = mentions.applyMention(inputText.value, mentionToken(src, locale.value))
  autoResize()
  nextTick(() => {
    const ta = chatPanelRef.value?.inputRef
    if (ta) {
      ta.focus()
      ta.setSelectionRange(ta.value.length, ta.value.length)
    }
  })
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

function runCommand(cmd: AiCommand, args?: string) { cmds.close(); inputText.value = ''; autoResize(); cmd.action(args) }

// ── 引用操作 / Quote operations ──
// 插入纪要/随记已下架（2026-09）：仅保留划词改写的替换原文入口
function onAcceptRewrite(content: string) { const ok = quoteRef.acceptRewrite(content); showToast(ok ? t('ai-panel.toast.replaced') : t('ai-panel.toast.locate_failed'), ok ? 'success' : 'warn') }

// ── 生命周期 / Lifecycle ──
onMounted(() => {
  cmds.registerCommands(cmdActions.buildCommands())
  window.addEventListener('quote-to-ai', onQuoteToAiEvent)
  window.addEventListener('global-ai-focus', onGlobalAiFocus)
  window.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  window.removeEventListener('quote-to-ai', onQuoteToAiEvent)
  window.removeEventListener('global-ai-focus', onGlobalAiFocus)
  window.removeEventListener('keydown', onKeydown)
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
