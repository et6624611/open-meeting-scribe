<template>
  <AiMessageList
    ref="messageListRef"
    :messages="messages"
    :is-loading="isLoading"
    :is-streaming="isStreaming"
    :thinking-elapsed="thinkingElapsed"
    :stages="stages"
    :rewrite-pending="rewritePending"
    :verified-changes="verifiedChanges"
    :inject-prompt="injectPrompt"
    :format-change="formatChange"
    :rewrite-not-persisted="rewriteNotPersisted"
    :tier-denial="tierDenial"
    :session-tier="sessionTier"
    :pending-tier="pendingTier"
    :tier-menu-signal="tierMenuSignal"
    :session-model="sessionModel"
    :model-options="modelOptions"
    :detail-model-label="detailModelLabel"
    :cli-probe="cliProbe"
    :agent-engine-name="agentEngineName"
    :agent-engine-model="agentEngineModel"
    :agent-models="agentModels"
    :agent-models-reason="agentModelsReason"
    :agent-models-loading="agentModelsLoading"
    :summary-proposal="summaryProposal"
    :notes-proposal="notesProposal"
    :board-proposal="boardProposal"
    @accept-rewrite="$emit('acceptRewrite', $event)"
    @clear-rewrite="$emit('clearRewrite')"
    @inject-all="$emit('injectAll')"
    @dismiss-inject="$emit('dismissInject')"
    @retry-write="$emit('retryWrite', $event)"
    @dismiss-not-persisted="$emit('dismissNotPersisted')"
    @open-summary-preview="$emit('openSummaryPreview')"
    @reject-summary="$emit('rejectSummary')"
    @open-notes-preview="$emit('openNotesPreview')"
    @reject-notes="$emit('rejectNotes')"
    @accept-board-proposal="$emit('acceptBoardProposal')"
    @reject-board-proposal="$emit('rejectBoardProposal')"
    @update:pending-tier="$emit('update:pendingTier', $event)"
    @apply-new-session="$emit('applyNewSession')"
    @stop-generation="$emit('stopGeneration')"
    @edit-resend="$emit('editResend', $event)"
    @raise-tier="$emit('raiseTier')"
    @raise-tier-preset="$emit('raiseTierPreset')"
  />
  <AiChatComposer
    ref="composerRef"
    :quote-text="quoteText"
    :quote-source="quoteSource"
    :cmd-open="cmdOpen"
    :cmd-index="cmdIndex"
    :filtered-cmds="filteredCmds"
    :mention-open="mentionOpen"
    :mention-index="mentionIndex"
    :filtered-mentions="filteredMentions"
    :pending-attachments="pendingAttachments"
    :uploading-attachments="uploadingAttachments"
    :input-text="inputText"
    :chat-mode="chatMode"
    :chat-scope="chatScope"
    :cli-probe="cliProbe"
    :session-tier="sessionTier"
    :pending-tier="pendingTier"
    :tier-menu-signal="tierMenuSignal"
    :session-model="sessionModel"
    :model-options="modelOptions"
    :detail-model-label="detailModelLabel"
    :agent-engine-name="agentEngineName"
    :agent-engine-model="agentEngineModel"
    :agent-models="agentModels"
    :agent-models-reason="agentModelsReason"
    :agent-models-loading="agentModelsLoading"
    :is-loading="isLoading"
    @send="$emit('send')"
    @stop-generation="$emit('stopGeneration')"
    @clear-quote="$emit('clearQuote')"
    @run-command="$emit('runCommand', $event)"
    @select-mention="$emit('selectMention', $event)"
    @remove-attachment="$emit('removeAttachment', $event)"
    @input-key="$emit('inputKey', $event)"
    @input-change="$emit('inputChange')"
    @update:input-text="$emit('update:inputText', $event)"
    @update:chat-mode="$emit('update:chatMode', $event)"
    @update:chat-scope="$emit('update:chatScope', $event)"
    @update:pending-tier="$emit('update:pendingTier', $event)"
    @apply-new-session="$emit('applyNewSession')"
    @update:session-model="$emit('update:sessionModel', $event)"
    @update:agent-model="$emit('update:agentModel', $event)"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { AttachmentMeta, ChatMessage, AgentStage, ChatScope } from '@/api/chat'
import type { ChatEngineProbe } from '@/api/settings'
import AiMessageList from './AiMessageList.vue'
import AiChatComposer from './AiChatComposer.vue'
import type { AiCommand } from '@/composables/useAiCommands'
import type { MentionSource } from '@/composables/useAiMentions'
import type { AuthTier } from '@/composables/useAiChat'
import type { BoardProposal } from '@/composables/useBoardProposal'

const messageListRef = ref<InstanceType<typeof AiMessageList> | null>(null)
const composerRef = ref<InstanceType<typeof AiChatComposer> | null>(null)

defineProps<{
  messages: ChatMessage[]
  isLoading: boolean
  isStreaming: boolean
  thinkingElapsed: number
  stages: AgentStage[]
  rewritePending: { source: string; originalText: string } | null
  verifiedChanges: Array<{ verified: boolean; [key: string]: any }>
  injectPrompt: { desc: string } | null
  quoteText: string
  quoteSource: string
  cmdOpen: boolean
  cmdIndex: number
  filteredCmds: AiCommand[]
  mentionOpen: boolean
  mentionIndex: number
  filteredMentions: MentionSource[]
  pendingAttachments: AttachmentMeta[]
  uploadingAttachments: boolean
  inputText: string
  formatChange: (change: any) => string
  chatMode: 'qa' | 'agent'
  chatScope: ChatScope
  sessionTier: AuthTier
  pendingTier: AuthTier
  tierMenuSignal: number
  tierDenial: { tool: string; summary: string } | null
  activeEngine: { display_name: string; auth_tier: string; auto_selected: boolean } | null
  sessionModel: string
  modelOptions: Array<{ value: string; source: 'local' | 'trial' | 'byok' }>
  detailModelLabel: string
  cliProbe: ChatEngineProbe | null
  agentAvailable: boolean
  agentEngineName: string
  agentEngineModel: string
  agentModels: string[]
  agentModelsReason: string
  agentModelsLoading: boolean
  rewriteNotPersisted: { text: string } | null
  summaryProposal: { baseline: string; proposed: string } | null
  notesProposal: { baseline: string; proposed: string } | null
  boardProposal: BoardProposal | null
}>()

defineEmits<{
  (e: 'send'): void
  (e: 'stopGeneration'): void
  (e: 'acceptRewrite', content: string): void
  (e: 'clearRewrite'): void
  (e: 'injectAll'): void
  (e: 'dismissInject'): void
  (e: 'retryWrite', text: string): void
  (e: 'dismissNotPersisted'): void
  (e: 'acceptSummary'): void
  (e: 'rejectSummary'): void
  (e: 'openSummaryPreview'): void
  (e: 'acceptNotes'): void
  (e: 'rejectNotes'): void
  (e: 'openNotesPreview'): void
  (e: 'acceptBoardProposal'): void
  (e: 'rejectBoardProposal'): void
  (e: 'clearQuote'): void
  (e: 'runCommand', cmd: AiCommand): void
  (e: 'selectMention', src: MentionSource): void
  (e: 'removeAttachment', id: string): void
  (e: 'inputKey', ev: KeyboardEvent): void
  (e: 'inputChange'): void
  (e: 'update:inputText', val: string): void
  (e: 'update:chatMode', val: 'qa' | 'agent'): void
  (e: 'update:chatScope', val: ChatScope): void
  (e: 'update:pendingTier', val: AuthTier): void
  (e: 'applyNewSession'): void
  (e: 'raiseTier'): void
  (e: 'raiseTierPreset'): void
  (e: 'update:sessionModel', val: string): void
  (e: 'update:agentModel', val: string): void
  (e: 'editResend', index: number, text: string, override: { mode: 'qa' | 'agent'; model?: string; agentModel?: string; scope?: ChatScope }): void
}>()

/** 对外暴露：feedRef（消息流滚动）、inputRef（聚焦/选点）、resizeInput（高度重算） */
defineExpose({
  get feedRef() { return messageListRef.value?.feedRef },
  get inputRef() { return composerRef.value?.inputRef },
  resizeInput: () => composerRef.value?.resizeInput?.(),
})
</script>
