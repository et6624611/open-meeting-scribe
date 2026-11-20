<template>
  <!-- 对话消息流（外包一层承接左侧点状导航浮层） / Chat message feed -->
  <div class="ai-feed-wrap">
    <div class="ai-feed" ref="feedRef" @scroll.passive="syncActive">
      <div
        v-for="(msg, i) in messages" :key="i"
        class="ai-msg" :class="{ 'is-user': msg.role === 'user' }"
        :ref="(el) => setMsgEl(el, i)"
      >
        <!-- 编辑态：点击用户消息就地展开完整 composer（文本 + 模式 + 模型 + 发送），Esc/点击外部取消 -->
        <div v-if="editingIdx === i" class="composer-card is-edit">
          <textarea
            class="composer-input is-edit-input"
            :ref="(el) => setEditRef(el)"
            :value="editText"
            @input="onEditInput($event)"
            @keydown="onEditKey($event)"
            rows="1"
            :aria-label="t('ai-panel.edit_aria')"
          ></textarea>
          <ComposerBar
            :chat-mode="editMode"
            :session-tier="sessionTier"
            :pending-tier="pendingTier"
            :tier-menu-signal="tierMenuSignal"
            :session-model="editModel"
            :model-options="modelOptions"
            :detail-model-label="detailModelLabel"
            :is-loading="isLoading"
            :send-disabled="!editText.trim()"
            :cli-probe="cliProbe"
            :agent-engine-name="agentEngineName"
            :agent-engine-model="editAgentModel"
            :agent-models="agentModels"
            :agent-models-reason="agentModelsReason"
            :agent-models-loading="agentModelsLoading"
            @update:chat-mode="editMode = $event"
            @update:pending-tier="$emit('update:pendingTier', $event)"
            @apply-new-session="$emit('applyNewSession')"
            @update:session-model="editModel = $event"
            @update:agent-model="editAgentModel = $event"
            @send="submitEdit(i)"
            @stop="$emit('stopGeneration')"
          />
        </div>
        <!-- 占位气泡：assistant 消息在首个 token 前 content 为空，此时不渲染，避免 .ai-bubble 的 padding/border 撑出空白条 -->
        <div
          v-else-if="msg.content"
          class="ai-bubble"
          :class="{ 'is-editable': msg.role === 'user' }"
          :title="msg.role === 'user' ? t('ai-panel.edit_hint') : undefined"
          v-html="fmt(msg.content)"
          @click="msg.role === 'user' && startEdit(i)"
        ></div>
        <!-- 用户消息附件：图片缩略图（点击新窗预览）+ 文件行（点击下载） -->
        <div v-if="msg.role === 'user' && msg.attachments?.length" class="ai-msg-attachments">
          <template v-for="a in msg.attachments" :key="a.id">
            <a v-if="a.content_type.startsWith('image/')" :href="attachmentUrl(a)" target="_blank" rel="noopener" class="ai-msg-thumb-link">
              <img class="ai-msg-thumb" :src="attachmentUrl(a)" :alt="a.filename" loading="lazy">
            </a>
            <a v-else class="ai-msg-file" :href="attachmentUrl(a, true)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              <span class="ai-msg-file-name">{{ a.filename }}</span>
              <span class="ai-msg-file-size">{{ formatBytes(a.size) }}</span>
            </a>
          </template>
        </div>
        <!-- 回复尾部消费方/计费回显（REQ-EXPERT-MODE §2.3：与 routing 实际判定一致） -->
        <div v-if="msg.role === 'assistant' && msg.modelUsage" class="ai-usage-echo">
          {{ t('ai-panel.usage_echo', { model: msg.modelUsage.model, src: srcLabel(msg.modelUsage.source), billing: billingLabel(msg.modelUsage.billing) }) }}<span v-if="msg.modelUsage.auto_switched">{{ t('ai-panel.usage_echo_auto_switched') }}</span>
        </div>
        <!-- 本轮改写事实 + 恢复入口（模式即权限 §5.4）：说清改了哪个域，并给一键回退，
           不让用户对着已变化的数据猜"是谁改的、能不能改回去" -->
        <div v-if="msg.role === 'assistant' && msg.metadata?.rewritten && msg.metadata?.turn_id" class="rewrite-notice" :class="{ 'is-undone': undoneTurns.has(msg.metadata.turn_id) }">
          <span class="rewrite-text">{{ undoneTurns.has(msg.metadata.turn_id)
            ? t('ai-panel.chat_rewritten_undone_label')
            : t('ai-panel.chat_rewritten', { tools: rewriteLabel(msg.metadata.rewritten_tools) }) }}</span>
          <button
            v-if="!undoneTurns.has(msg.metadata.turn_id)"
            class="rewrite-undo"
            :disabled="!!undoingTurn"
            @click="onUndoTurn(msg.metadata.task_id || '', msg.metadata.turn_id || '')"
          >{{ undoingTurn === msg.metadata.turn_id ? t('ai-panel.chat_rewritten_undoing') : t('ai-panel.chat_rewritten_undo') }}</button>
        </div>
        <!-- 消息时间戳 / Message timestamp（空占位消息不显示，避免与用户消息时间重复出现） -->
        <div v-if="msg.timestamp && msg.content" class="ai-msg-ts">{{ fmtTime(msg.timestamp) }}</div>
        <!-- 截断警告 / Truncation warning -->
        <div v-if="msg.role === 'assistant' && msg.metadata?.finish_reason === 'length'" class="ai-trunc-warn">⚠️ 回复因 token 上限被截断，内容可能不完整</div>
        <!-- 元数据图标行：复制 + 三个可展开详情图标（模型与 Token / 性能 / 引用）
           插入纪要/随记按钮已下架（2026-09），插入类操作由纪要页划词工具栏承接 -->
        <div v-if="msg.role === 'assistant' && msg.content" class="ai-msg-meta">
          <div class="ai-meta-icons">
            <IconButton :label="copiedIdx === i ? t('ai-panel.meta_copied') : t('ai-panel.meta_copy')" @click="onCopyReply(msg.content, i)">
              <svg v-if="copiedIdx === i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect width="13" height="13" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
            </IconButton>
            <IconButton :active="detailOpen[i] === 'metadata'" :label="t('ai-panel.meta_model_tokens')" @click="toggleDetail(i, 'metadata')">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M4 1h5l4 4v9a1 1 0 01-1 1H4a1 1 0 01-1-1V2a1 1 0 011-1z"/><path d="M9 1v4h4"/></svg>
            </IconButton>
            <IconButton :active="detailOpen[i] === 'perf'" :label="t('ai-panel.meta_performance')" @click="toggleDetail(i, 'perf')">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M9 1L4 9h4l-1 6 5-8H9l1-6z"/></svg>
            </IconButton>
            <IconButton :active="detailOpen[i] === 'sources'" :label="t('ai-panel.meta_sources')" @click="toggleDetail(i, 'sources')">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M6 3a2 2 0 00-2 2v1a2 2 0 002 2h4a2 2 0 002-2V5a2 2 0 00-2-2H6z"/><path d="M6 8a2 2 0 00-2 2v1a2 2 0 002 2h4a2 2 0 002-2v-1a2 2 0 00-2-2H6z"/></svg>
            </IconButton>
          </div>
          <!-- 元数据详情面板 / Metadata detail panel：后端回显字段可能缺失（如 byok 链路只回 model），逐字段容错不留白 -->
          <div v-if="detailOpen[i] === 'metadata'" class="ai-meta-detail">
            <template v-if="msg.metadata">
              <div class="ai-meta-row"><span class="ai-meta-label">Model</span><span>{{ msg.metadata.model || '—' }}</span></div>
              <div class="ai-meta-row"><span class="ai-meta-label">Tokens</span><span>{{ fmtTokens(msg.metadata) }}</span></div>
              <div class="ai-meta-row"><span class="ai-meta-label">Finish</span><span>{{ msg.metadata.finish_reason || '—' }}</span></div>
              <div class="ai-meta-row"><span class="ai-meta-label">ID</span><span class="ai-meta-id">{{ msg.metadata.id || '—' }}</span></div>
            </template>
            <div v-else class="ai-meta-empty">{{ t('ai-panel.meta_empty_metadata') }}</div>
          </div>
          <!-- 性能面板 / Performance panel -->
          <div v-if="detailOpen[i] === 'perf'" class="ai-meta-detail">
            <template v-if="msg.performance">
              <div class="ai-meta-row"><span class="ai-meta-label">Latency</span><span>{{ msg.performance.latency_ms }}ms</span></div>
              <div class="ai-meta-row"><span class="ai-meta-label">Output</span><span>{{ msg.performance.char_count }} chars</span></div>
              <div class="ai-meta-row"><span class="ai-meta-label">Context</span><span>{{ msg.performance.context_block_count }} blocks, {{ msg.performance.message_count }} messages</span></div>
            </template>
            <div v-else class="ai-meta-empty">{{ t('ai-panel.meta_empty_performance') }}</div>
          </div>
          <!-- 引用来源面板 / Sources panel -->
          <div v-if="detailOpen[i] === 'sources'" class="ai-meta-detail">
            <template v-if="msg.sources?.length">
              <div v-for="(src, si) in msg.sources" :key="si" class="ai-meta-row">📎 {{ src.title || src.name }}</div>
            </template>
            <div v-else class="ai-meta-empty">{{ t('ai-panel.meta_empty_sources') }}</div>
          </div>
        </div>
        <AiExecutionTrace
          v-if="msg.role === 'assistant' && msg.stages?.length"
          :key="msg.executionId || msg.timestamp || i"
          :stages="msg.stages"
          :state="msg.executionState"
          :live="isLoading && msg.executionState === 'running'"
        />
        <!-- 改写 Diff 视图 / Rewrite diff view -->
        <div v-if="rewritePending && i === messages.length - 1 && msg.role === 'assistant'" class="diff-view">
          <div class="diff-header"><span>{{ t('ai-panel.rewrite_label') }}</span><span>{{ rewritePending.source }}</span></div>
          <div class="diff-body">
            <p style="margin-bottom:8px;"><span class="diff-del">{{ shortText(rewritePending.originalText) }}</span></p>
            <p style="font-size:11px;color:var(--muted);font-style:italic;">{{ t('ai-panel.rewrite_hint') }}</p>
          </div>
          <div class="diff-actions">
            <IconButton class="diff-accept-btn" :label="t('ai-panel.accept_rewrite')" show-label @click="$emit('acceptRewrite', msg.content)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
            </IconButton>
            <button class="diff-reject-btn" @click="$emit('clearRewrite')">{{ t('ai-panel.reject_rewrite') }}</button>
          </div>
        </div>
        <!-- 纪要提案入口卡（propose_summary，未落盘） -->
        <div v-if="summaryProposal && i === messages.length - 1 && msg.role === 'assistant'" class="sum-prop-view">
          <div class="diff-header"><span>{{ t('ai-panel.summary_proposal_label') }}</span></div>
          <p class="sum-prop-summary">{{ t('ai-panel.summary_proposal_summary', { hunks: summaryProposalStats.hunks, added: summaryProposalStats.added, removed: summaryProposalStats.removed }) }}</p>
          <div class="diff-actions">
            <button class="diff-accept-btn" @click="$emit('openSummaryPreview')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              {{ t('ai-panel.summary_proposal_view') }}
            </button>
            <button class="diff-reject-btn" @click="$emit('rejectSummary')">{{ t('ai-panel.summary_proposal_reject') }}</button>
          </div>
        </div>
        <!-- 随记提案入口卡（propose_notes，未落盘） -->
        <div v-if="notesProposal && i === messages.length - 1 && msg.role === 'assistant'" class="sum-prop-view">
          <div class="diff-header"><span>{{ t('ai-panel.notes_proposal_label') }}</span></div>
          <p class="sum-prop-summary">{{ t('ai-panel.notes_proposal_summary', { hunks: notesProposalStats.hunks, added: notesProposalStats.added, removed: notesProposalStats.removed }) }}</p>
          <div class="diff-actions">
            <button class="diff-accept-btn" @click="$emit('openNotesPreview')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              {{ t('ai-panel.notes_proposal_view') }}
            </button>
            <button class="diff-reject-btn" @click="$emit('rejectNotes')">{{ t('ai-panel.notes_proposal_reject') }}</button>
          </div>
        </div>
        <!-- 建板提案确认卡（create_insight_board，未落盘） -->
        <div v-if="boardProposal && i === messages.length - 1 && msg.role === 'assistant'" class="sum-prop-view">
          <div class="diff-header"><span>{{ t('ai-panel.board_proposal_label') }}</span></div>
          <p class="sum-prop-summary">
            {{ t('ai-panel.board_proposal_summary', { title: boardProposal.title }) }}
            <template v-if="boardProposal.reason">{{ boardProposal.reason }}</template>
          </p>
          <div class="diff-actions">
            <button class="diff-accept-btn" @click="$emit('acceptBoardProposal')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
              {{ t('ai-panel.board_proposal_accept') }}
            </button>
            <button class="diff-reject-btn" @click="$emit('rejectBoardProposal')">{{ t('ai-panel.board_proposal_reject') }}</button>
          </div>
        </div>
        <!-- AI 操作校验结果展示 / AI action verification results -->
        <div v-if="verifiedChanges.length && i === messages.length - 1 && msg.role === 'assistant'" class="verified-changes-block">
          <div class="vc-header">{{ t('ai-panel.verify_header') }}</div>
          <div class="vc-list">
            <div v-for="(change, ci) in verifiedChanges" :key="ci" class="vc-item" :class="{ 'is-verified': change.verified }">
              <span class="vc-icon">{{ change.verified ? '✅' : '⚠️' }}</span>
              <span class="vc-desc">{{ formatChange(change) }}</span>
              <span class="vc-status">{{ change.verified ? t('ai-panel.verify_pass') : t('ai-panel.verify_fail') }}</span>
            </div>
          </div>
        </div>
        <!-- 数据注入提示 / Data injection prompt -->
        <div v-if="injectPrompt && i === messages.length - 1 && msg.role === 'assistant'" class="inject-prompt">
          <span>{{ t('ai-panel.inject_detected', { desc: injectPrompt.desc }) }}</span>
          <button class="btn-inject-all" @click="$emit('injectAll')">{{ t('ai-panel.inject_all') }}</button>
          <button class="btn-dismiss" @click="$emit('dismissInject')">{{ t('ai-panel.inject_dismiss') }}</button>
        </div>
      </div>
      <!-- 无执行记录时保留轻量等待提示；执行过程已归属各条答复。 -->
      <Transition name="thinking">
        <div v-if="isLoading && stages.length === 0 && !isStreaming" class="ai-thinking" role="status" aria-live="polite">
          <svg class="ai-thinking-spinner" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M8 1a7 7 0 1 1-7 7" stroke-linecap="round"/></svg>
          <span class="ai-thinking-text">{{ t('ai-panel.thinking_elapsed', { sec: thinkingElapsed }) }}</span>
        </div>
      </Transition>

      <!-- 完成护栏横幅（模式即权限 §5.4） -->
      <div v-if="rewriteNotPersisted" class="guard-notice" role="alert">
        <span class="guard-text">{{ t('ai-panel.chat_not_persisted') }}</span>
        <button class="guard-retry" @click="$emit('retryWrite', rewriteNotPersisted.text)">{{ t('ai-panel.chat_not_persisted_retry') }}</button>
        <button class="guard-dismiss" @click="$emit('dismissNotPersisted')">{{ t('ai-panel.chat_not_persisted_dismiss') }}</button>
      </div>

      <!-- 授权档位拒绝卡 -->
      <div v-if="tierDenial" class="tier-deny-card" role="alert">
        <div class="tdc-head">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M4.9 4.9 19.1 19.1"/></svg>
          <span>{{ t('ai-panel.tier_deny_title') }}</span>
        </div>
        <div class="tdc-body">
          <code class="tdc-tool">{{ tierDenial.tool }}</code>
          <code class="tdc-code">403 · read_only</code>
        </div>
        <div class="tdc-hint">{{ t('ai-panel.tier_deny_hint') }}</div>
        <div class="tdc-actions">
          <button class="tdc-btn is-pri" @click="$emit('raiseTier')">{{ t('ai-panel.tier_deny_raise') }}</button>
          <button class="tdc-btn" @click="$emit('raiseTierPreset')">{{ t('ai-panel.tier_deny_new') }}</button>
        </div>
      </div>

      <!-- 空会话提示 -->
      <div v-if="showEmpty" class="ai-feed-empty">
        <EmptyHint :title="t('ai-panel.empty_title')" :body="t('ai-panel.empty_body')">
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>
          </template>
          <div class="ai-empty-hint">
            <span class="ai-empty-kbd"><kbd>/</kbd>{{ t('ai-panel.empty_hint_slash') }}</span>
            <span class="ai-empty-sep">·</span>
            <span class="ai-empty-kbd"><kbd>@</kbd>{{ t('ai-panel.empty_hint_at') }}</span>
          </div>
        </EmptyHint>
      </div>
    </div>

    <!-- 左侧中部聚集点状导航 -->
    <nav
      v-if="userEntries.length"
      class="ai-chat-nav"
      :aria-label="t('ai-panel.nav_user_messages')"
      @mouseenter="openNav"
      @mouseleave="scheduleCloseNav"
    >
      <div class="ai-chat-nav-rail">
        <button
          v-for="u in userEntries" :key="u.index"
          type="button"
          class="ai-chat-nav-dot"
          :class="{ 'is-active': u.index === activeIdx }"
          :aria-label="u.msg.content"
          @focus="openNav"
          @blur="scheduleCloseNav"
        ></button>
      </div>
      <div class="ai-chat-nav-bridge" :class="{ 'is-open': navOpen }"></div>
      <div
        class="ai-chat-nav-pop"
        :class="{ 'is-open': navOpen }"
        @mouseenter="openNav"
        @mouseleave="scheduleCloseNav"
      >
        <div class="acn-head">
          <span class="acn-title">{{ t('ai-panel.nav_user_messages') }}</span>
          <span class="acn-count">{{ userEntries.length }}</span>
        </div>
        <div class="acn-list">
          <button
            v-for="u in userEntries" :key="u.index"
            type="button"
            class="acn-item"
            :class="{ 'is-current': u.index === activeIdx }"
            :title="u.msg.content"
            @click="jumpTo(u.index)"
          >
            <span class="acn-mark"></span>
            <span class="acn-text">{{ u.msg.content }}</span>
            <span v-if="u.msg.timestamp" class="acn-time">{{ fmtTime(u.msg.timestamp) }}</span>
          </button>
        </div>
      </div>
    </nav>
  </div><!-- /.ai-feed-wrap -->
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { LlmMetadata, AgentStage, ChatMessage } from '@/api/chat'
import { attachmentUrl } from '@/api/chat'
import type { ChatEngineProbe } from '@/api/settings'
import { useI18n } from 'vue-i18n'
import IconButton from '@/components/common/IconButton.vue'
import EmptyHint from '@/components/common/EmptyHint.vue'
import AiExecutionTrace from './AiExecutionTrace.vue'
import { renderMarkdownWithMermaid, postProcessMermaid, clearMermaidCache } from '@/utils/renderChatMarkdown'
import { isDarkThemeId } from '@/utils/renderMermaid'
import { useThemeStore } from '@/stores/theme'
import ComposerBar from './ComposerBar.vue'
import type { AuthTier } from '@/composables/useAiChat'
import { useSummaryProposal } from '@/composables/useSummaryProposal'
import { useNotesProposal } from '@/composables/useNotesProposal'
import type { BoardProposal } from '@/composables/useBoardProposal'
import { showToast } from '@/composables/useToast'
import { restoreTaskRewrites } from '@/api/notes'
import { extractErrorMessage } from '@/api/client'

const { t } = useI18n()
const themeStore = useThemeStore()

/** 文件体积人类可读 */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const props = defineProps<{
  messages: ChatMessage[]
  isLoading: boolean
  isStreaming: boolean
  thinkingElapsed: number
  stages: AgentStage[]
  rewritePending: { source: string; originalText: string } | null
  verifiedChanges: Array<{ verified: boolean; [key: string]: any }>
  injectPrompt: { desc: string } | null
  formatChange: (change: any) => string
  rewriteNotPersisted: { text: string } | null
  tierDenial: { tool: string; summary: string } | null
  sessionTier: AuthTier
  pendingTier: AuthTier
  tierMenuSignal: number
  sessionModel: string
  modelOptions: Array<{ value: string; source: 'local' | 'trial' | 'byok' }>
  detailModelLabel: string
  cliProbe: ChatEngineProbe | null
  agentEngineName: string
  agentEngineModel: string
  agentModels: string[]
  agentModelsReason: string
  agentModelsLoading: boolean
  summaryProposal: { baseline: string; proposed: string } | null
  notesProposal: { baseline: string; proposed: string } | null
  boardProposal: BoardProposal | null
}>()

const emit = defineEmits<{
  (e: 'acceptRewrite', content: string): void
  (e: 'clearRewrite'): void
  (e: 'injectAll'): void
  (e: 'dismissInject'): void
  (e: 'retryWrite', text: string): void
  (e: 'dismissNotPersisted'): void
  (e: 'openSummaryPreview'): void
  (e: 'rejectSummary'): void
  (e: 'openNotesPreview'): void
  (e: 'rejectNotes'): void
  (e: 'acceptBoardProposal'): void
  (e: 'rejectBoardProposal'): void
  (e: 'update:pendingTier', val: AuthTier): void
  (e: 'applyNewSession'): void
  (e: 'stopGeneration'): void
  (e: 'editResend', index: number, text: string, override: { mode: 'qa' | 'agent'; model?: string; agentModel?: string }): void
  (e: 'raiseTier'): void
  (e: 'raiseTierPreset'): void
}>()

const feedRef = ref<HTMLElement | null>(null)
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointer, true)
})

// ── 左侧点状导航 ──
const showEmpty = computed(() =>
  !props.isLoading
  && !props.isStreaming
  && !props.messages.some(m => m.content && m.content.trim().length > 0),
)
type UserEntry = { msg: { role: string; content: string; timestamp?: string }; index: number }
const userEntries = computed<UserEntry[]>(() =>
  props.messages
    .map((msg, index) => ({ msg, index }))
    .filter(x => x.msg.role === 'user' && !!x.msg.content),
)
const userEls = new Map<number, HTMLElement>()
function setMsgEl(el: unknown, i: number) {
  const node = el as HTMLElement | null
  if (!node) { userEls.delete(i); return }
  const m = props.messages[i]
  if (m?.role === 'user' && m.content) userEls.set(i, node)
  else userEls.delete(i)
}
const activeIdx = ref(-1)
const navOpen = ref(false)
let navCloseTimer: ReturnType<typeof setTimeout> | null = null
function openNav() {
  if (navCloseTimer) { clearTimeout(navCloseTimer); navCloseTimer = null }
  navOpen.value = true
}
function scheduleCloseNav() {
  if (navCloseTimer) clearTimeout(navCloseTimer)
  navCloseTimer = setTimeout(() => { navOpen.value = false; navCloseTimer = null }, 120)
}
function jumpTo(globalIdx: number) {
  const feed = feedRef.value
  const el = userEls.get(globalIdx)
  if (!feed || !el) return
  const top = el.getBoundingClientRect().top - feed.getBoundingClientRect().top + feed.scrollTop - 12
  feed.scrollTo({ top, behavior: 'smooth' })
}
function syncActive() {
  const feed = feedRef.value
  if (!feed) return
  const topLine = feed.getBoundingClientRect().top + 24
  let active = -1
  for (const u of userEntries.value) {
    const el = userEls.get(u.index)
    if (el && el.getBoundingClientRect().top <= topLine) active = u.index
  }
  if (feed.scrollTop + feed.clientHeight >= feed.scrollHeight - 8) {
    active = userEntries.value[userEntries.value.length - 1]?.index ?? -1
  }
  activeIdx.value = active
}
watch(() => userEntries.value.length, () => void nextTick(syncActive))
onMounted(() => {
  void nextTick(syncActive)
  void nextTick(applyMermaidPost)
})

/** 提案规模摘要（入口卡文案用） */
const summaryProposalSingleton = useSummaryProposal()
const summaryProposalStats = computed(() => summaryProposalSingleton.summaryProposalStats.value)
const notesProposalSingleton = useNotesProposal()
const notesProposalStats = computed(() => notesProposalSingleton.notesProposalStats.value)

// ── 已发消息编辑再发送 ──
const editingIdx = ref<number | null>(null)
const editText = ref('')
const editMode = ref<'qa' | 'agent'>('qa')
const editModel = ref('')
const editAgentModel = ref('')
const editInputRef = ref<HTMLTextAreaElement | null>(null)

function setEditRef(el: unknown) {
  editInputRef.value = (el as HTMLTextAreaElement | null) ?? null
}

function startEdit(i: number) {
  if (props.isLoading) return
  const msg = props.messages[i]
  if (!msg || msg.role !== 'user') return
  const next = props.messages[i + 1]
  const inferredMode: 'qa' | 'agent'
    = msg.sendOptions?.mode ?? (next?.metadata?.engine ? 'agent' : 'qa')
  editingIdx.value = i
  editText.value = msg.content
  editMode.value = inferredMode
  editModel.value = msg.sendOptions?.model ?? (inferredMode === 'qa' ? props.sessionModel : '')
  editAgentModel.value = msg.sendOptions?.agentModel ?? (inferredMode === 'agent' ? props.agentEngineModel : '')
  void nextTick(() => {
    const ta = editInputRef.value
    if (ta) {
      ta.focus()
      ta.setSelectionRange(ta.value.length, ta.value.length)
      resizeEditInput()
    }
  })
}

function cancelEdit() { editingIdx.value = null }

function submitEdit(i: number) {
  const text = editText.value.trim()
  if (!text || props.isLoading) return
  editingIdx.value = null
  emit('editResend', i, text, {
    mode: editMode.value,
    model: editMode.value === 'qa' ? editModel.value : undefined,
    agentModel: editMode.value === 'agent' ? editAgentModel.value : undefined,
  })
}

function onEditInput(e: Event) {
  editText.value = (e.target as HTMLTextAreaElement).value
  resizeEditInput()
}

function onEditKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submitEdit(editingIdx.value ?? -1)
  } else if (e.key === 'Escape') {
    e.preventDefault()
    cancelEdit()
  }
}

function composerVar(name: string, fallback: number): number {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name))
  return Number.isFinite(v) && v > 0 ? v : fallback
}

function resizeEditInput() {
  const ta = editInputRef.value
  if (!ta) return
  ta.style.height = 'auto'
  if (ta.scrollHeight === 0) return
  const line = composerVar('--composer-line', 20)
  ta.style.height = Math.round(ta.scrollHeight / line) * line + 'px'
}

function onDocPointer(e: PointerEvent) {
  const t = e.target as HTMLElement | null
  if (!t) return
  if (t.closest('.is-edit') || t.closest('.ac-menu')) return
  cancelEdit()
}
watch(editingIdx, (v) => {
  if (v != null) document.addEventListener('pointerdown', onDocPointer, true)
  else document.removeEventListener('pointerdown', onDocPointer, true)
})

/** 每条消息展开的详情面板类型 */
const detailOpen = ref<Record<number, string | null>>({})

/** 本轮改写事实的呈现与撤销 */
const REWRITE_TOOL_KEYS: Record<string, string> = {
  update_decision_node: 'ai-panel.rewrite_tool_decision_node',
  delete_decision_node: 'ai-panel.rewrite_tool_decision_node',
  inject_items: 'ai-panel.rewrite_tool_inject',
  update_summary: 'ai-panel.rewrite_tool_summary',
  revise_insight_board: 'ai-panel.rewrite_tool_board',
  revise_insight_board_section: 'ai-panel.rewrite_tool_board',
}

function rewriteLabel(tools?: string[]): string {
  const names = new Set((tools || [])
    .map(x => (REWRITE_TOOL_KEYS[x] ? t(REWRITE_TOOL_KEYS[x]) : x))
    .filter(Boolean))
  return names.size ? Array.from(names).join('、') : t('ai-panel.rewrite_tool_generic')
}

const undoingTurn = ref('')
const undoneTurns = ref<Set<string>>(new Set())

async function onUndoTurn(taskId: string, turnId: string) {
  if (!taskId || !turnId || undoingTurn.value) return
  undoingTurn.value = turnId
  try {
    const res = await restoreTaskRewrites(taskId, { turnId })
    undoneTurns.value = new Set(undoneTurns.value).add(turnId)
    showToast(t('ai-panel.chat_rewritten_undone', { n: res.restored ?? 0 }), 'success')
  } catch (e) {
    showToast(t('ai-panel.chat_rewritten_undo_failed', { reason: extractErrorMessage(e, '') }), 'error')
  } finally {
    undoingTurn.value = ''
  }
}

const copiedIdx = ref<number | null>(null)
let copiedTimer: ReturnType<typeof setTimeout> | null = null
onBeforeUnmount(() => {
  if (copiedTimer) clearTimeout(copiedTimer)
})
async function onCopyReply(content: string, idx: number) {
  try {
    await navigator.clipboard.writeText(content)
  } catch {
    console.warn('[AiMessageList] Clipboard copy failed')
    return
  }
  copiedIdx.value = idx
  if (copiedTimer) clearTimeout(copiedTimer)
  copiedTimer = setTimeout(() => { copiedIdx.value = null; copiedTimer = null }, 1500)
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return '' }
}

function toggleDetail(idx: number, panel: string) {
  detailOpen.value[idx] = detailOpen.value[idx] === panel ? null : panel
}

function fmtTokens(meta: LlmMetadata): string {
  const u = meta.usage
  if (!u) return '—'
  return `${u.prompt_tokens ?? '—'} + ${u.completion_tokens ?? '—'} = ${u.total_tokens ?? '—'}`
}

function fmt(c: string): string {
  return renderMarkdownWithMermaid(c)
}

/** mermaid 后处理：messages 变化 + 主题变化 → 扫占位符渲 SVG */
async function applyMermaidPost() {
  const feed = feedRef.value
  if (!feed) return
  await postProcessMermaid(feed, isDarkThemeId(themeStore.current))
}

// 主题切换：清缓存 + 重新渲（明暗主题 SVG 不同）
watch(() => themeStore.current, () => {
  clearMermaidCache()
  void nextTick(applyMermaidPost)
})

// messages 变化：nextTick 后处理 mermaid 占位符
watch(() => props.messages, () => {
  void nextTick(applyMermaidPost)
}, { deep: false })

function shortText(text: string): string {
  return text.length > 80 ? text.slice(0, 80) + '…' : text
}

function srcLabel(source: string): string {
  if (source === 'local' || source === 'local_endpoint') return t('ai-panel.model_src_local')
  if (source === 'trial') return t('ai-panel.model_src_trial')
  if (source === 'byok') return t('ai-panel.model_src_byok')
  return source || '—'
}
function billingLabel(billing: string): string {
  if (billing === 'platform_quota') return t('ai-panel.usage_billing_platform_quota')
  if (billing === 'own_key') return t('ai-panel.usage_billing_own_key')
  if (billing === 'none') return t('ai-panel.usage_billing_none')
  return ''
}

defineExpose({ feedRef })
</script>

<style scoped>
/* ── 消息时间戳 ── */
.ai-msg-ts { font-size: 10px; color: var(--muted, #999); margin: 2px 0 0; opacity: 0.7; }
/* ── 截断警告 ── */
.ai-trunc-warn { font-size: 11px; color: var(--warn); background: var(--warn-soft); border-radius: 4px; padding: 3px 8px; margin: 4px 0 0; }
/* ── 元数据图标行 ── */
.ai-msg-meta { margin-top: 4px; }
.ai-meta-icons { display: flex; gap: 2px; }
.ai-meta-icons :deep(.icon-btn) { width: 22px; height: 22px; border-radius: 4px; color: var(--muted, #999); }
.ai-meta-icons :deep(.icon-btn__icon svg) { width: 14px; height: 14px; }
.ai-meta-icons :deep(.icon-btn--active) { background: var(--accent-soft); color: var(--accent); }
.ai-meta-detail { margin-top: 4px; padding: 6px 8px; background: var(--surface-2); border-radius: 6px; font-size: 11px; line-height: 1.6; color: var(--muted, #666); }
.ai-meta-row { display: flex; gap: 6px; align-items: baseline; }
.ai-meta-row + .ai-meta-row { margin-top: 2px; }
.ai-meta-label { color: var(--muted, #999); min-width: 50px; flex-shrink: 0; }
.ai-meta-id { font-family: monospace; font-size: 10px; word-break: break-all; }
.ai-meta-empty { font-style: italic; color: var(--subtle, #aaa); }
/* ─ 思考中指示器 ─ */
.ai-thinking { display: flex; align-items: center; gap: 6px; padding: 6px 10px; margin: 4px 0; font-size: 12px; color: var(--muted, #999); opacity: 0.7; }
.ai-thinking-spinner { width: 14px; height: 14px; animation: spin 1s linear infinite; flex-shrink: 0; }
@keyframes spin { to { transform: rotate(360deg); } }
.ai-thinking-text { font-variant-numeric: tabular-nums; }
/* ── 折叠过渡 ── */
.thinking-enter-active, .thinking-leave-active { transition: all 0.25s ease; }
.thinking-enter-from, .thinking-leave-to { opacity: 0; max-height: 0; margin: 0; padding: 0; overflow: hidden; }
.thinking-enter-to, .thinking-leave-from { opacity: 0.7; max-height: 40px; }
/* ── 已验证变更卡片 ── */
.verified-changes-block { margin-top: var(--s-3); padding: var(--s-3); background: var(--surface-2); border-radius: var(--radius); border: 1px solid var(--border); }
.vc-header { font-size: var(--fs-12); font-weight: 600; color: var(--fg); margin-bottom: 10px; padding-bottom: var(--s-2); border-bottom: 1px solid var(--border); }
.vc-list { display: flex; flex-direction: column; gap: var(--s-2); }
.vc-item { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-2) 10px; background: var(--surface); border-radius: var(--radius-sm); border-left: 3px solid var(--border-strong); transition: all 0.15s; }
.vc-item.is-verified { border-left-color: var(--ok); background: linear-gradient(90deg, var(--ok-soft) 0%, transparent 100%); }
.vc-item:not(.is-verified) { border-left-color: var(--warn); background: linear-gradient(90deg, var(--warn-soft) 0%, transparent 100%); }
.vc-icon { font-size: var(--fs-14); flex-shrink: 0; }
.vc-desc { flex: 1; font-size: var(--fs-12); color: var(--muted); line-height: 1.5; }
.vc-status { font-size: var(--fs-11); color: var(--muted); white-space: nowrap; padding: 2px var(--s-2); border-radius: var(--radius-xs); background: var(--surface-3); }
.vc-item.is-verified .vc-status { color: var(--ok); background: var(--ok-soft); }
.vc-item:not(.is-verified) .vc-status { color: var(--warn); background: var(--warn-soft); }
/* ── 回复尾部消费方/计费回显 ── */
.ai-usage-echo { font-size: 12px; color: var(--muted, #888); margin: 2px 0 0; padding: 1px 8px; border-left: 2px solid var(--border, #ddd); }
/* ── 本轮改写事实 ── */
.rewrite-notice { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 2px 0 4px; padding: 6px 10px; font-size: 12px; line-height: 1.5; color: var(--ok, #1c6b45); background: var(--ok-soft, #e7f4ec); border: 1px solid var(--ok-border); border-radius: var(--radius-sm, 6px); }
.rewrite-notice .rewrite-text { flex: 1 1 auto; }
.rewrite-notice .rewrite-undo { border: 1px solid var(--ok-border); background: transparent; color: inherit; font: inherit; font-weight: 600; border-radius: var(--radius-sm, 6px); padding: 2px 10px; cursor: pointer; }
.rewrite-notice .rewrite-undo:hover:not(:disabled) { background: var(--ok-soft); }
.rewrite-notice .rewrite-undo:disabled { opacity: 0.55; cursor: default; }
.rewrite-notice.is-undone { color: var(--muted, #888); background: transparent; border-color: var(--border, rgba(0, 0, 0, 0.12)); }
/* ── 完成护栏横幅 ── */
.guard-notice { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 6px 0 4px; padding: 7px 10px; border-radius: var(--radius-sm, 6px); font-size: 12px; line-height: 1.5; color: var(--warn, #8a5800); background: var(--warn-soft, #fdf3df); border: 1px solid var(--warn-border); }
.guard-notice .guard-text { flex: 1 1 auto; }
.guard-notice .guard-retry { border: 1px solid var(--warn-border); background: transparent; color: inherit; font: inherit; font-weight: 600; border-radius: var(--radius-sm, 6px); padding: 2px 10px; cursor: pointer; }
.guard-notice .guard-retry:hover { background: var(--warn-soft); }
.guard-notice .guard-dismiss { border: none; background: transparent; color: var(--muted, #888); font: inherit; cursor: pointer; padding: 2px 4px; }
/* ── 纪要提案入口卡 ── */
.sum-prop-view { margin-top: var(--s-2); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.sum-prop-summary { margin: 0; padding: 8px 10px; font-size: 12px; line-height: 1.5; color: var(--fg); }
/* ── 授权档位拒绝卡 ── */
.tier-deny-card { margin: 6px 0 4px; padding: 10px 12px; border-radius: var(--radius-lg, 12px); border: 1px solid var(--error-border); background: var(--error-soft); color: var(--error); font-size: 12px; line-height: 1.5; }
.tdc-head { display: flex; align-items: center; gap: 7px; font-weight: 600; font-size: 12.5px; }
.tdc-head svg { width: 15px; height: 15px; flex: 0 0 auto; }
.tdc-body { display: flex; align-items: center; gap: 6px; margin-top: 7px; flex-wrap: wrap; }
.tdc-tool, .tdc-code { font-family: var(--font-mono, ui-monospace, monospace); font-size: 11px; padding: 1px 6px; border-radius: 5px; background: var(--surface, #fff); border: 1px solid var(--error-border); color: var(--error); }
.tdc-hint { margin-top: 7px; color: var(--muted, #8a6a6a); }
.tdc-actions { display: flex; gap: 8px; margin-top: 9px; }
.tdc-btn { font: inherit; font-size: 12px; font-weight: 600; padding: 4px 12px; border-radius: var(--radius-sm, 6px); border: 1px solid var(--error-border); background: var(--surface, #fff); color: var(--error); cursor: pointer; transition: background 0.12s ease; }
.tdc-btn:hover { background: color-mix(in oklch, var(--error) 8%, var(--surface)); }
.tdc-btn.is-pri { background: var(--error); border-color: var(--error); color: var(--surface); }
.tdc-btn.is-pri:hover { background: color-mix(in oklch, var(--error) 88%, black); }

/* ── 编辑卡 ── */
.composer-card { display: flex; flex-direction: column; padding: var(--s-2) var(--s-3); border: 1px solid var(--border); border-radius: var(--radius, 10px); background: var(--surface); transition: border-color 0.15s ease, box-shadow 0.15s ease; }
.composer-card.is-edit { align-self: stretch; width: 100%; }
.ai-bubble.is-editable { cursor: pointer; transition: border-color 0.14s ease; }
.ai-bubble.is-editable:hover { border-color: var(--accent); }
.composer-input { flex: 0 0 auto; width: 100%; border: 0; background: transparent; color: var(--fg); font: inherit; font-size: var(--fs-13, 13px); line-height: var(--composer-line); resize: none; outline: none; height: calc(var(--composer-line) * var(--composer-min-lines)); min-height: calc(var(--composer-line) * var(--composer-min-lines)); max-height: calc(var(--composer-line) * var(--composer-max-lines)); padding: 0; overflow-y: auto; overflow-x: hidden; scrollbar-gutter: stable; scrollbar-width: thin; scrollbar-color: transparent transparent; }
.composer-input::placeholder { color: var(--subtle); }
.composer-input:hover { scrollbar-color: oklch(0% 0 0 / 0.18) transparent; }
.composer-input:hover::-webkit-scrollbar-thumb { background: oklch(0% 0 0 / 0.18); }
.composer-input.is-edit-input { height: var(--composer-line); min-height: var(--composer-line); }

/* ── Markdown 排版（v-html 渲染后的 GFM 元素） ── */
.ai-bubble :deep(h1), .ai-bubble :deep(h2), .ai-bubble :deep(h3), .ai-bubble :deep(h4) {
  font-weight: 600; line-height: 1.35; color: var(--fg); margin: 0.8em 0 0.4em;
}
.ai-bubble :deep(h1) { font-size: 17px; }
.ai-bubble :deep(h2) { font-size: 15px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
.ai-bubble :deep(h3) { font-size: 14px; }
.ai-bubble :deep(p) { margin: 0.4em 0; }
.ai-bubble :deep(ul), .ai-bubble :deep(ol) { padding-left: 1.6em; margin: 0.3em 0; }
.ai-bubble :deep(li) { margin: 0.1em 0; }
.ai-bubble :deep(a) { color: var(--accent); text-decoration: none; }
.ai-bubble :deep(a:hover) { text-decoration: underline; }
.ai-bubble :deep(blockquote) {
  border-left: 3px solid var(--border-strong); padding: 2px 10px; margin: 0.5em 0;
  color: var(--muted); background: var(--surface-2); border-radius: 0 4px 4px 0;
}
.ai-bubble :deep(code) {
  background: var(--surface-2); padding: 1px 5px; border-radius: 3px; font-size: 0.88em;
}
.ai-bubble :deep(pre) {
  background: var(--surface-2); border: 1px solid var(--border); border-radius: 5px;
  padding: 8px 12px; overflow-x: auto; font-size: 12.5px; line-height: 1.5; margin: 0.5em 0;
}
.ai-bubble :deep(pre code) { background: none; padding: 0; }
.ai-bubble :deep(table) { border-collapse: collapse; margin: 0.5em 0; font-size: 13px; }
.ai-bubble :deep(th), .ai-bubble :deep(td) {
  border: 1px solid var(--border); padding: 4px 8px; text-align: left;
}
.ai-bubble :deep(th) { background: var(--surface-2); font-weight: 600; }
.ai-bubble :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 0.8em 0; }

/* ── Mermaid 图 ── */
.ai-bubble :deep(.md-mermaid-box) {
  margin: 8px 0; overflow-x: auto; text-align: center;
}
.ai-bubble :deep(.md-mermaid-box svg) { max-width: 100%; height: auto; }
.ai-bubble :deep(pre.md-mermaid-error) {
  border-color: var(--warn); color: var(--warn); background: var(--warn-soft);
}
</style>
