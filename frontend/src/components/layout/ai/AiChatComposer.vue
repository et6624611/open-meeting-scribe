<template>
  <!-- 输入区 / Input zone -->
  <div class="ai-input-zone">
    <!-- 引用区域 / Quote reference -->
    <div v-if="quoteText" class="quote-ref">
      <div class="quote-ref-text">{{ quoteText }}</div>
      <div class="quote-ref-source"><span class="src-dot"></span><span>{{ quoteSource }}</span></div>
      <button class="quote-ref-remove" :title="t('ai-panel.quote.remove')" @click="$emit('clearQuote')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
    </div>
    <!-- 指令面板 / Command palette -->
    <div class="ai-cmd-palette" :class="{ 'is-open': cmdOpen && filteredCmds.length > 0 }">
      <template v-if="filteredCmds.length > 0">
        <button v-for="(c, ci) in filteredCmds" :key="c.key" class="ai-cmd-item" :class="{ 'is-active': cmdIndex === ci }" :aria-label="t('ai-panel.' + c.descKey)" @click="$emit('runCommand', c)"><span class="cmd-key">{{ c.key }}</span><span class="cmd-label">{{ t('ai-panel.' + c.descKey) }}</span></button>
      </template>
      <div v-else-if="inputText.startsWith('/')" class="ai-cmd-empty">{{ t('ai-panel.cmd_no_match') }}</div>
    </div>
    <!-- @ 引用面板 -->
    <div class="ai-cmd-palette" :class="{ 'is-open': mentionOpen && filteredMentions.length > 0 }">
      <template v-if="filteredMentions.length > 0">
        <template v-if="meetingMentions.length > 0">
          <div class="ai-cmd-group">{{ t('ai-panel.mention_group_meeting') }}</div>
          <button
            v-for="m in meetingMentions" :key="m.token" class="ai-cmd-item"
            :class="{ 'is-active': mentionIndex === filteredMentions.indexOf(m) }"
            :aria-label="t('ai-panel.' + m.descKey)"
            @click="$emit('selectMention', m)"
          ><span class="cmd-key">{{ mentionToken(m, locale) }}</span><span class="cmd-label">{{ t('ai-panel.' + m.descKey) }}</span></button>
        </template>
        <template v-if="localMentions.length > 0">
          <div class="ai-cmd-group">{{ t('ai-panel.mention_group_local') }}</div>
          <button
            v-for="m in localMentions" :key="m.token" class="ai-cmd-item"
            :class="{ 'is-active': mentionIndex === filteredMentions.indexOf(m) }"
            :aria-label="t('ai-panel.' + m.descKey)"
            @click="$emit('selectMention', m)"
          ><span class="cmd-key">{{ mentionToken(m, locale) }}</span><span class="cmd-label">{{ t('ai-panel.' + m.descKey) }}</span></button>
        </template>
      </template>
      <div v-else-if="parseMention(inputText)" class="ai-cmd-empty">{{ t('ai-panel.mention_empty') }}</div>
    </div>
    <!-- 算力探针前置警告 / CLI probe notice -->
    <div v-if="chatMode !== 'qa' && cliProbe && !cliProbe.available" class="ai-cli-probe-warn">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01"/><circle cx="12" cy="12" r="9"/></svg>
      <span>{{ probeHintText }}<a class="cpw-switch" href="#" @click.prevent="$emit('update:chatMode', 'qa')">{{ t('ai-panel.mode_notice_switch_qa') }}</a></span>
    </div>
    <!-- @附件 待发送 chips -->
    <div v-if="pendingAttachments.length > 0 || uploadingAttachments" class="ai-attach-chips">
      <div v-for="a in pendingAttachments" :key="a.id" class="ai-attach-chip">
        <img v-if="a.content_type.startsWith('image/')" class="ai-attach-thumb" :src="attachmentUrl(a)" :alt="a.filename" loading="lazy">
        <span class="ai-attach-name" :title="a.filename">{{ a.filename }}</span>
        <span class="ai-attach-size">{{ formatBytes(a.size) }}</span>
        <button class="ai-attach-remove" :title="t('ai-panel.attachment_remove')" @click="$emit('removeAttachment', a.id)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
      <div v-if="uploadingAttachments" class="ai-attach-chip is-uploading">
        <span class="ai-attach-name">{{ t('ai-panel.attachment_uploading') }}</span>
      </div>
    </div>
    <!-- 输入卡片：textarea + composer 栏整体包边框 -->
    <div class="composer-card">
      <textarea
        class="composer-input"
        :class="{ 'is-more-below': moreBelow, 'is-more-above': moreAbove }"
        :value="inputText"
        @input="$emit('update:inputText', ($event.target as HTMLTextAreaElement).value); $emit('inputChange')"
        @scroll.passive="onComposerScroll"
        :placeholder="t('ai-panel.input_placeholder')"
        rows="1"
        ref="inputRef"
        @keydown="$emit('inputKey', $event)"
        :aria-label="t('ai-panel.input_aria')"
      ></textarea>
      <!-- 智能体模式常驻轻提示 -->
      <div v-if="chatMode === 'agent'" class="ai-agent-mode-hint">{{ t('ai-panel.agent_mode_writable') }}</div>
      <!-- Composer 栏 -->
      <ComposerBar
        :chat-mode="chatMode"
        :session-tier="sessionTier"
        :pending-tier="pendingTier"
        :tier-menu-signal="tierMenuSignal"
        :session-model="sessionModel"
        :model-options="modelOptions"
        :detail-model-label="detailModelLabel"
        :is-loading="isLoading"
        :send-disabled="(!inputText.trim() && pendingAttachments.length === 0) || uploadingAttachments"
        :cli-probe="cliProbe"
        :agent-engine-name="agentEngineName"
        :agent-engine-model="agentEngineModel"
        :agent-models="agentModels"
        :agent-models-reason="agentModelsReason"
        :agent-models-loading="agentModelsLoading"
        @update:chat-mode="$emit('update:chatMode', $event)"
        @update:pending-tier="$emit('update:pendingTier', $event)"
        @apply-new-session="$emit('applyNewSession')"
        @update:session-model="$emit('update:sessionModel', $event)"
        @update:agent-model="$emit('update:agentModel', $event)"
        @send="$emit('send')"
        @stop="$emit('stopGeneration')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import type { AttachmentMeta } from '@/api/chat'
import { attachmentUrl } from '@/api/chat'
import type { ChatEngineProbe } from '@/api/settings'
import { useI18n } from 'vue-i18n'
import ComposerBar from './ComposerBar.vue'
import type { AiCommand } from '@/composables/useAiCommands'
import { parseMention, mentionToken } from '@/composables/useAiMentions'
import type { MentionSource } from '@/composables/useAiMentions'
import type { AuthTier } from '@/composables/useAiChat'

const { t, locale } = useI18n()

/** 文件体积人类可读 */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const props = defineProps<{
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
  chatMode: 'qa' | 'agent'
  cliProbe: ChatEngineProbe | null
  sessionTier: AuthTier
  pendingTier: AuthTier
  tierMenuSignal: number
  sessionModel: string
  modelOptions: Array<{ value: string; source: 'local' | 'trial' | 'byok' }>
  detailModelLabel: string
  agentEngineName: string
  agentEngineModel: string
  agentModels: string[]
  agentModelsReason: string
  agentModelsLoading: boolean
  isLoading: boolean
}>()

defineEmits<{
  (e: 'send'): void
  (e: 'stopGeneration'): void
  (e: 'clearQuote'): void
  (e: 'runCommand', cmd: AiCommand): void
  (e: 'selectMention', src: MentionSource): void
  (e: 'removeAttachment', id: string): void
  (e: 'inputKey', ev: KeyboardEvent): void
  (e: 'inputChange'): void
  (e: 'update:inputText', val: string): void
  (e: 'update:chatMode', val: 'qa' | 'agent'): void
  (e: 'update:pendingTier', val: AuthTier): void
  (e: 'applyNewSession'): void
  (e: 'update:sessionModel', val: string): void
  (e: 'update:agentModel', val: string): void
}>()

/** @ 面板分组 */
const meetingMentions = computed(() => props.filteredMentions.filter(m => m.group === 'meeting'))
const localMentions = computed(() => props.filteredMentions.filter(m => m.group === 'local'))

const inputRef = ref<HTMLTextAreaElement | null>(null)

// ─── Composer 尺寸契约 ───
function composerVar(name: string, fallback: number): number {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name))
  return Number.isFinite(v) && v > 0 ? v : fallback
}
const moreBelow = ref(false)
const moreAbove = ref(false)
function syncOverflow(ta: HTMLTextAreaElement) {
  moreBelow.value = ta.scrollHeight - ta.clientHeight - ta.scrollTop > 1
  moreAbove.value = ta.scrollTop > 1
}
function onComposerScroll(e: Event) { syncOverflow(e.target as HTMLTextAreaElement) }

function resizeInput() {
  const ta = inputRef.value
  if (!ta) return
  ta.style.height = 'auto'
  if (ta.scrollHeight === 0) return
  const line = composerVar('--composer-line', 20)
  ta.style.height = Math.round(ta.scrollHeight / line) * line + 'px'
  syncOverflow(ta)
}

watch(() => props.inputText, () => { void nextTick(resizeInput) })

const probeHintText = computed(() => {
  const p = props.cliProbe
  if (!p) return ''
  if (p.failed_stage === 'version' || p.reason === 'version_low') return t('ai-panel.cli_probe_version_low')
  if (p.failed_stage === 'login' || p.reason === 'not_logged_in') return t('ai-panel.cli_probe_not_logged_in')
  return t('ai-panel.cli_probe_not_installed')
})

onMounted(() => { resizeInput() })

defineExpose({ inputRef, resizeInput })
</script>

<style scoped>
/* ── 输入卡片 ── */
.composer-card {
  display: flex; flex-direction: column; padding: var(--s-2) var(--s-3);
  border: 1px solid var(--border); border-radius: var(--radius, 10px);
  background: var(--surface);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.composer-card:focus-within { border-color: var(--accent); box-shadow: var(--shadow-focus); }
/* 智能体模式常驻轻提示 */
.ai-agent-mode-hint {
  font-size: 11px; color: var(--subtle, oklch(0% 0 0 / 0.55));
  line-height: 1.4; margin: 2px 0 0; user-select: none;
}
/* ── Composer 输入区 ── */
.composer-input {
  flex: 0 0 auto; width: 100%; border: 0; background: transparent; color: var(--fg);
  font: inherit; font-size: var(--fs-13, 13px); line-height: var(--composer-line);
  resize: none; outline: none;
  height: calc(var(--composer-line) * var(--composer-min-lines));
  min-height: calc(var(--composer-line) * var(--composer-min-lines));
  max-height: calc(var(--composer-line) * var(--composer-max-lines));
  padding: 0; overflow-y: auto; overflow-x: hidden;
  scrollbar-gutter: stable; scrollbar-width: thin; scrollbar-color: transparent transparent;
}
.composer-input::placeholder { color: var(--subtle); }
.composer-input:hover { scrollbar-color: oklch(0% 0 0 / 0.18) transparent; }
.composer-input:hover::-webkit-scrollbar-thumb { background: oklch(0% 0 0 / 0.18); }
/* 溢出渐隐遮罩 */
.composer-input.is-more-below {
  -webkit-mask-image: linear-gradient(to bottom, black calc(100% - var(--composer-fade)), transparent);
  mask-image: linear-gradient(to bottom, black calc(100% - var(--composer-fade)), transparent);
}
.composer-input.is-more-above {
  -webkit-mask-image: linear-gradient(to bottom, transparent, black var(--composer-fade));
  mask-image: linear-gradient(to bottom, transparent, black var(--composer-fade));
}
.composer-input.is-more-above.is-more-below {
  -webkit-mask-image: linear-gradient(to bottom, transparent, black var(--composer-fade), black calc(100% - var(--composer-fade)), transparent);
  mask-image: linear-gradient(to bottom, transparent, black var(--composer-fade), black calc(100% - var(--composer-fade)), transparent);
}
/* ── CLI 探针前置警告 ── */
.ai-cli-probe-warn {
  display: flex; align-items: flex-start; gap: 6px; margin: 2px 0 4px;
  padding: 6px 10px; border-radius: var(--radius-sm, 6px);
  font-size: 12px; line-height: 1.5;
  color: var(--warn, #8a5800); background: var(--warn-soft, #fdf3df);
  border: 1px solid var(--warn-border);
}
.ai-cli-probe-warn svg { width: 13px; height: 13px; flex: 0 0 auto; margin-top: 2px; }
.ai-cli-probe-warn .cpw-switch {
  color: inherit; text-decoration: underline; text-underline-offset: 2px;
  margin-left: 6px; white-space: nowrap; cursor: pointer;
}
</style>
