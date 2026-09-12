<template>
  <!-- 对话消息流 -->
  <div class="ai-feed" ref="feedRef">
    <div v-for="(msg, i) in messages" :key="i" class="ai-msg" :class="{ 'is-user': msg.role === 'user' }">
      <div class="ai-bubble" v-html="fmt(msg.content)"></div>
      <!-- 插入纪要/随记按钮（仅 assistant 消息） -->
      <div v-if="msg.role === 'assistant' && msg.content" class="ai-msg-actions">
        <IconButton class="ai-insert-btn" :label="t('ai-panel.insert_summary')" show-label @click="$emit('insertToSummary', msg.content)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="12" y1="18" x2="12" y2="12"/><polyline points="9,15 12,12 15,15"/></svg>
        </IconButton>
        <IconButton class="ai-insert-btn" :label="t('ai-panel.insert_notes')" show-label @click="$emit('insertToNotes', msg.content)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
        </IconButton>
      </div>
      <!-- 改写 Diff 视图 -->
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
      <!-- AI 操作校验结果展示 -->
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
      <!-- 数据注入提示 -->
      <div v-if="injectPrompt && i === messages.length - 1 && msg.role === 'assistant'" class="inject-prompt">
        <span>{{ t('ai-panel.inject_detected', { desc: injectPrompt.desc }) }}</span>
        <button class="btn-inject-all" @click="$emit('injectAll')">{{ t('ai-panel.inject_all') }}</button>
        <button class="btn-dismiss" @click="$emit('dismissInject')">{{ t('ai-panel.inject_dismiss') }}</button>
      </div>
    </div>
    <div v-if="isLoading" class="ai-msg"><div class="ai-bubble" style="opacity:0.6">{{ t('ai-panel.thinking') }}</div></div>
    <!-- AI 主动消息列表 -->
    <div v-for="pm in proactiveMessages" :key="pm.id" class="ai-msg is-proactive" :id="'proactive-' + pm.id" :class="{ 'is-expanded': pm.expanded }">
      <div class="proactive-card-header" @click="$emit('toggleProactive', pm.id)">
        <span class="proactive-card-category">{{ pm.category }}</span>
        <span class="proactive-card-title">{{ pm.title }}</span>
        <span class="proactive-card-time">{{ formatTime(pm.timestamp) }}</span>
        <span class="proactive-card-chevron"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg></span>
      </div>
      <div v-if="pm.expanded" class="proactive-card-body">
        <div class="proactive-card-summary" v-html="pm.body"></div>
        <div class="proactive-card-solution">
          <div class="proactive-solution-label">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:12px;height:12px"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
            {{ t('ai-panel.ai_suggestion') }}
          </div>
          <div class="proactive-solution-text">{{ pm.solution }}</div>
        </div>
        <div class="proactive-actions">
          <button v-for="act in pm.actions" :key="act.key" class="proactive-action-btn" :class="{ 'is-primary': act.primary, 'is-done': actedActions[pm.id + ':' + act.key] }" @click="$emit('proactiveAction', pm, act)">{{ actedActions[pm.id + ':' + act.key] ? t('ai-panel.proactive.action_done') : act.label }}</button>
        </div>
      </div>
    </div>
  </div>

  <!-- 输入区 -->
  <div class="ai-input-zone">
    <!-- AI 主动消息悬浮通知横幅 -->
    <div v-if="proactiveEnabled && latestUnread" class="proactive-banner-wrap">
      <div class="proactive-banner" @click="$emit('bannerClick')">
        <div class="proactive-banner-inner">
          <div class="proactive-banner-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg></div>
          <div class="proactive-banner-text">
            <div class="proactive-banner-label">{{ t('ai-panel.proactive.banner_label') }}</div>
            <div class="proactive-banner-title">{{ latestUnread.title }}</div>
            <div class="proactive-banner-preview">{{ stripHtml(latestUnread.body) }}</div>
          </div>
          <button class="proactive-banner-close" :aria-label="t('ai-panel.proactive.banner_close')" @click.stop="$emit('bannerClose')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
        </div>
        <div class="proactive-banner-time">{{ t('ai-panel.proactive.banner_time') }}</div>
      </div>
    </div>
    <!-- 跟进建议 -->
    <div v-show="suggestions.length > 0" class="ai-suggestions-bar">
      <button v-for="(s, si) in suggestions" :key="si" class="follow-up-chip" @click="$emit('sendRaw', s.text)"><span v-html="s.icon"></span>{{ s.text }}</button>
    </div>
    <!-- 停止生成 -->
    <div class="ai-stop-gen" :class="{ 'is-visible': isLoading }">
      <button class="ai-stop-gen-btn" @click="$emit('stopGeneration')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>
        {{ t('ai-panel.stop_generating') }}
      </button>
    </div>
    <!-- 引用区域 -->
    <div v-if="quoteText" class="quote-ref">
      <div class="quote-ref-text">{{ quoteText }}</div>
      <div class="quote-ref-source"><span class="src-dot"></span><span>{{ quoteSource }}</span></div>
      <button class="quote-ref-remove" :title="t('ai-panel.quote.remove')" @click="$emit('clearQuote')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
    </div>
    <!-- 指令面板 -->
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
import { useI18n } from 'vue-i18n'
import IconButton from '@/components/common/IconButton.vue'
import type { AiCommand } from '@/composables/useAiCommands'
import type { ProactiveMessage, ProactiveAction } from '@/composables/useAiProactive'

const { t } = useI18n()

defineProps<{
  messages: Array<{ role: string; content: string }>
  isLoading: boolean
  rewritePending: { source: string; originalText: string } | null
  verifiedChanges: Array<{ verified: boolean; [key: string]: any }>
  injectPrompt: { desc: string } | null
  proactiveMessages: ProactiveMessage[]
  actedActions: Record<string, boolean>
  proactiveEnabled: boolean
  latestUnread: ProactiveMessage | null
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
  (e: 'toggleProactive', id: string): void
  (e: 'proactiveAction', pm: ProactiveMessage, act: ProactiveAction): void
  (e: 'bannerClick'): void
  (e: 'bannerClose'): void
  (e: 'clearQuote'): void
  (e: 'runCommand', cmd: AiCommand): void
  (e: 'inputKey', ev: KeyboardEvent): void
  (e: 'inputChange'): void
  (e: 'update:inputText', val: string): void
}>()

const inputRef = ref<HTMLTextAreaElement | null>(null)
const feedRef = ref<HTMLElement | null>(null)

defineExpose({ inputRef, feedRef })

function fmt(c: string): string {
  return c.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`(.+?)`/g, '<code>$1</code>').replace(/\n/g, '<br>')
}

function shortText(text: string): string {
  return text.length > 80 ? text.slice(0, 80) + '…' : text
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, '')
}
</script>
