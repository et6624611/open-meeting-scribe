<template>
  <!-- 对话消息流 / Chat message feed -->
  <div class="ai-feed" ref="feedRef">
    <div v-for="(msg, i) in messages" :key="i" class="ai-msg" :class="{ 'is-user': msg.role === 'user' }">
      <div class="ai-bubble" v-html="fmt(msg.content)"></div>
      <!-- 消息时间戳 / Message timestamp -->
      <div v-if="msg.timestamp" class="ai-msg-ts">{{ fmtTime(msg.timestamp) }}</div>
      <!-- 截断警告 / Truncation warning -->
      <div v-if="msg.role === 'assistant' && msg.metadata?.finish_reason === 'length'" class="ai-trunc-warn">⚠️ 回复因 token 上限被截断，内容可能不完整</div>
      <!-- 插入纪要/随记按钮（仅 assistant 消息） / Insert summary/notes button (assistant messages only) -->
      <div v-if="msg.role === 'assistant' && msg.content" class="ai-msg-actions">
        <IconButton class="ai-insert-btn" :label="t('ai-panel.insert_summary')" show-label @click="$emit('insertToSummary', msg.content)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="12" y1="18" x2="12" y2="12"/><polyline points="9,15 12,12 15,15"/></svg>
        </IconButton>
        <IconButton class="ai-insert-btn" :label="t('ai-panel.insert_notes')" show-label @click="$emit('insertToNotes', msg.content)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
        </IconButton>
      </div>
      <!-- 元数据图标行 / Metadata icon row -->
      <div v-if="msg.role === 'assistant' && msg.metadata" class="ai-msg-meta">
        <div class="ai-meta-icons">
          <button class="ai-meta-icon-btn" :class="{ 'is-active': detailOpen[i] === 'metadata' }" title="模型与 Token" @click="toggleDetail(i, 'metadata')"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M4 1h5l4 4v9a1 1 0 01-1 1H4a1 1 0 01-1-1V2a1 1 0 011-1z"/><path d="M9 1v4h4"/></svg></button>
          <button v-if="msg.sources?.length" class="ai-meta-icon-btn" :class="{ 'is-active': detailOpen[i] === 'sources' }" title="引用来源" @click="toggleDetail(i, 'sources')"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M6 3a2 2 0 00-2 2v1a2 2 0 002 2h4a2 2 0 002-2V5a2 2 0 00-2-2H6z"/><path d="M6 8a2 2 0 00-2 2v1a2 2 0 002 2h4a2 2 0 002-2v-1a2 2 0 00-2-2H6z"/></svg></button>
          <button v-if="msg.performance" class="ai-meta-icon-btn" :class="{ 'is-active': detailOpen[i] === 'perf' }" title="性能指标" @click="toggleDetail(i, 'perf')"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M9 1L4 9h4l-1 6 5-8H9l1-6z"/></svg></button>
        </div>
        <!-- 元数据详情面板 / Metadata detail panel -->
        <div v-if="detailOpen[i] === 'metadata'" class="ai-meta-detail">
          <div class="ai-meta-row"><span class="ai-meta-label">Model</span><span>{{ msg.metadata.model }}</span></div>
          <div class="ai-meta-row"><span class="ai-meta-label">Tokens</span><span>{{ msg.metadata.usage.prompt_tokens }} + {{ msg.metadata.usage.completion_tokens }} = {{ msg.metadata.usage.total_tokens }}</span></div>
          <div class="ai-meta-row"><span class="ai-meta-label">Finish</span><span>{{ msg.metadata.finish_reason }}</span></div>
          <div class="ai-meta-row"><span class="ai-meta-label">ID</span><span class="ai-meta-id">{{ msg.metadata.id }}</span></div>
        </div>
        <!-- 引用来源面板 / Sources panel -->
        <div v-if="detailOpen[i] === 'sources'" class="ai-meta-detail">
          <div v-for="(src, si) in msg.sources" :key="si" class="ai-meta-row">📎 {{ src.title || src.name }}</div>
        </div>
        <!-- 性能面板 / Performance panel -->
        <div v-if="detailOpen[i] === 'perf' && msg.performance" class="ai-meta-detail">
          <div class="ai-meta-row"><span class="ai-meta-label">Latency</span><span>{{ msg.performance.latency_ms }}ms</span></div>
          <div class="ai-meta-row"><span class="ai-meta-label">Output</span><span>{{ msg.performance.char_count }} chars</span></div>
          <div class="ai-meta-row"><span class="ai-meta-label">Context</span><span>{{ msg.performance.context_block_count }} blocks, {{ msg.performance.message_count }} messages</span></div>
        </div>
      </div>
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
    <!-- Agent 思考阶段指示器 / Agent thinking stages indicator -->
    <Transition name="thinking">
      <div v-if="isLoading && stages.length > 0" class="ai-stages">
        <div v-for="(stage, si) in stages" :key="si" class="ai-stage-item" :class="{ 'is-done': stage.status === 'done', 'is-error': stage.status === 'error' }">
          <span v-if="stage.icon" class="ai-stage-icon">{{ stage.icon }}</span>
          <svg v-else-if="stage.status === 'running'" class="ai-stage-spinner" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 1a7 7 0 1 1-7 7" stroke-linecap="round"/></svg>
          <span v-else class="ai-stage-check">✓</span>
          <span class="ai-stage-label">{{ stage.label }}</span>
          <span v-if="stage.detail && stage.status !== 'running'" class="ai-stage-detail">{{ stage.detail }}</span>
        </div>
      </div>
      <!-- 回退：无阶段时显示简单思考指示器 / Fallback: simple thinking indicator when no stages -->
      <div v-else-if="isLoading && stages.length === 0 && !isStreaming" class="ai-thinking">
        <svg class="ai-thinking-spinner" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 1a7 7 0 1 1-7 7" stroke-linecap="round"/></svg>
        <span class="ai-thinking-text">思考中 · {{ thinkingElapsed }}s</span>
      </div>
    </Transition>
  </div>

  <!-- 输入区 / Input zone -->
  <div class="ai-input-zone">
    <!-- 跟进建议 / Follow-up suggestions -->
    <div v-show="suggestions.length > 0" class="ai-suggestions-bar">
      <button v-for="(s, si) in suggestions" :key="si" class="follow-up-chip" @click="$emit('sendRaw', s.text)"><span v-html="s.icon"></span>{{ s.text }}</button>
    </div>
    <!-- 停止生成 / Stop generation -->
    <div class="ai-stop-gen" :class="{ 'is-visible': isLoading }">
      <button class="ai-stop-gen-btn" @click="$emit('stopGeneration')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>
        {{ t('ai-panel.stop_generating') }}
      </button>
    </div>
    <!-- 引用区域 / Quote reference -->
    <div v-if="quoteText" class="quote-ref">
      <div class="quote-ref-text">{{ quoteText }}</div>
      <div class="quote-ref-source"><span class="src-dot"></span><span>{{ quoteSource }}</span></div>
      <button class="quote-ref-remove" :title="t('ai-panel.quote.remove')" @click="$emit('clearQuote')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
    </div>
    <!-- 指令面板 / Command palette -->
    <div class="ai-cmd-palette" :class="{ 'is-open': cmdOpen && filteredCmds.length > 0 }">
      <template v-if="filteredCmds.length > 0">
        <button v-for="(c, ci) in filteredCmds" :key="c.key" class="ai-cmd-item" :class="{ 'is-active': cmdIndex === ci }" @click="$emit('runCommand', c)"><span class="cmd-key">{{ c.key }}</span><span class="cmd-label">{{ c.desc }}</span></button>
      </template>
      <div v-else-if="inputText.startsWith('/')" class="ai-cmd-empty">无匹配指令</div>
    </div>
    <div class="ai-input-box">
      <textarea :value="inputText" @input="$emit('update:inputText', ($event.target as HTMLTextAreaElement).value); $emit('inputChange')" :placeholder="t('ai-panel.input_placeholder')" rows="1" ref="inputRef" @keydown="$emit('inputKey', $event)" :aria-label="t('ai-panel.input_aria')"></textarea>
      <button class="ai-send-btn" :disabled="!inputText.trim() || isLoading" @click="$emit('send')" :title="t('ai-panel.send')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg></button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { LlmMetadata, MessagePerformance, SourceFile, AgentStage } from '@/api/chat'
import { useI18n } from 'vue-i18n'
import IconButton from '@/components/common/IconButton.vue'
import { escapeHtml } from '@/utils/sanitize'
import type { AiCommand } from '@/composables/useAiCommands'


const { t } = useI18n()

defineProps<{
  messages: Array<{ role: string; content: string; timestamp?: string; metadata?: LlmMetadata; sources?: SourceFile[]; performance?: MessagePerformance; stages?: AgentStage[] }>
  isLoading: boolean
  isStreaming: boolean
  thinkingElapsed: number
  stages: AgentStage[]
  rewritePending: { source: string; originalText: string } | null
  verifiedChanges: Array<{ verified: boolean; [key: string]: any }>
  injectPrompt: { desc: string } | null
  suggestions: Array<{ icon: string; text: string }>
  quoteText: string
  quoteSource: string
  cmdOpen: boolean
  cmdIndex: number
  filteredCmds: AiCommand[]
  inputText: string
  formatChange: (change: any) => string
}>()

defineEmits<{
  (e: 'send'): void
  (e: 'sendRaw', text: string): void
  (e: 'stopGeneration'): void
  (e: 'insertToSummary', content: string): void
  (e: 'insertToNotes', content: string): void
  (e: 'acceptRewrite', content: string): void
  (e: 'clearRewrite'): void
  (e: 'injectAll'): void
  (e: 'dismissInject'): void
  (e: 'clearQuote'): void
  (e: 'runCommand', cmd: AiCommand): void
  (e: 'inputKey', ev: KeyboardEvent): void
  (e: 'inputChange'): void
  (e: 'update:inputText', val: string): void
}>()

const inputRef = ref<HTMLTextAreaElement | null>(null)
const feedRef = ref<HTMLElement | null>(null)

/** 每条消息展开的详情面板类型 / Expanded detail panel type per message index */
const detailOpen = ref<Record<number, string | null>>({})

defineExpose({ inputRef, feedRef })

/** 格式化 ISO 时间戳为 HH:MM:SS / Format ISO timestamp to HH:MM:SS */
function fmtTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return '' }
}

/** 切换消息的详情面板（互斥） / Toggle message detail panel (mutually exclusive) */
function toggleDetail(idx: number, panel: string) {
  detailOpen.value[idx] = detailOpen.value[idx] === panel ? null : panel
}

function fmt(c: string): string {
  const safe = escapeHtml(c)
  return safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`(.+?)`/g, '<code>$1</code>').replace(/\n/g, '<br>')
}

function shortText(text: string): string {
  return text.length > 80 ? text.slice(0, 80) + '…' : text
}


</script>

<style scoped>
/* ── 消息时间戳 / Message timestamp ── */
.ai-msg-ts {
  font-size: 10px;
  color: var(--muted, #999);
  margin: 2px 0 0;
  opacity: 0.7;
}
/* ── 截断警告 / Truncation warning ── */
.ai-trunc-warn {
  font-size: 11px;
  color: #b45309;
  background: #fef3c7;
  border-radius: 4px;
  padding: 3px 8px;
  margin: 4px 0 0;
}
/* ── 元数据图标行 / Metadata icon row ── */
.ai-msg-meta {
  margin-top: 4px;
}
.ai-meta-icons {
  display: flex;
  gap: 4px;
}
.ai-meta-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--muted, #999);
  cursor: pointer;
  transition: all 0.15s;
}
.ai-meta-icon-btn:hover {
  background: var(--hover-bg, rgba(0,0,0,0.06));
  color: var(--fg, #333);
}
.ai-meta-icon-btn.is-active {
  background: var(--accent-bg, rgba(59,130,246,0.1));
  color: var(--accent, #3b82f6);
}
.ai-meta-icon-btn svg {
  width: 14px;
  height: 14px;
}
/* ── 详情面板 / Detail panel ── */
.ai-meta-detail {
  margin-top: 4px;
  padding: 6px 8px;
  background: var(--bg-secondary, #f8f9fa);
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.6;
  color: var(--muted, #666);
}
.ai-meta-row {
  display: flex;
  gap: 6px;
  align-items: baseline;
}
.ai-meta-row + .ai-meta-row {
  margin-top: 2px;
}
.ai-meta-label {
  color: var(--muted, #999);
  min-width: 50px;
  flex-shrink: 0;
}
.ai-meta-id {
  font-family: monospace;
  font-size: 10px;
  word-break: break-all;
}
/* ─ 思考中指示器 / Thinking indicator ─ */
.ai-thinking {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  margin: 4px 0;
  font-size: 12px;
  color: var(--muted, #999);
  opacity: 0.7;
}
.ai-thinking-spinner {
  width: 14px;
  height: 14px;
  animation: spin 1s linear infinite;
  flex-shrink: 0;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.ai-thinking-text {
  font-variant-numeric: tabular-nums;
}
/* ── Agent 思考阶段 / Agent thinking stages ── */
.ai-stages {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  margin: 4px 0;
  background: var(--bg-secondary, #f8f9fa);
  border-radius: 8px;
  border: 1px solid var(--border, #e5e7eb);
}
.ai-stage-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary, #555);
  line-height: 1.5;
}
.ai-stage-item.is-done {
  color: var(--muted, #999);
}
.ai-stage-item.is-error {
  color: #b45309;
}
.ai-stage-icon {
  font-size: 13px;
  flex-shrink: 0;
  width: 16px;
  text-align: center;
}
.ai-stage-spinner {
  width: 14px;
  height: 14px;
  animation: spin 1s linear infinite;
  flex-shrink: 0;
  color: var(--accent, #3b82f6);
}
.ai-stage-check {
  font-size: 12px;
  color: #10b981;
  flex-shrink: 0;
  width: 16px;
  text-align: center;
  font-weight: 600;
}
.ai-stage-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ai-stage-detail {
  font-size: 11px;
  color: var(--muted, #999);
  max-width: 180px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* ── 折叠过渡 / Collapse transition ── */
.thinking-enter-active,
.thinking-leave-active {
  transition: all 0.25s ease;
}
.thinking-enter-from,
.thinking-leave-to {
  opacity: 0;
  max-height: 0;
  margin: 0;
  padding: 0;
  overflow: hidden;
}
.thinking-enter-to,
.thinking-leave-from {
  opacity: 0.7;
  max-height: 40px;
}
</style>
