<template>
  <div class="ai" :class="{ 'is-collapsed': layout.aiCollapsed }">
    <button class="ai-toggle"
      :title="layout.aiCollapsed ? '展开助手' : '收起助手'"
      :aria-label="layout.aiCollapsed ? '展开助手' : '收起助手'"
      :aria-expanded="!layout.aiCollapsed"
      @mousedown="onToggleDown($event)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
    </button>
    <div class="ai-collapsed-strip">
      <div class="ai-collapsed-icon" @click="layout.toggleAi()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
      </div>
      <span class="ai-collapsed-label">会议助手</span>
    </div>
    <div class="ai-panel-header">
      <div class="ai-panel-header-left">
        <div class="ai-header-avatar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg></div>
        <span class="ai-header-title">AI 助手</span>
      </div>
      <div class="ai-panel-header-right">
        <IconButton class="ai-header-btn" label="清空对话" @click="chat.clearConversation()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </IconButton>
      </div>
    </div>
    <div class="ai-panel-context">
      <span v-if="taskStore.currentTask">{{ taskStore.currentTask.title || taskStore.currentTask.audio_name || '当前会议' }}</span>
      <span v-else style="color:var(--subtle)">未选择会议</span>
    </div>
    <!-- Tab 栏 -->
    <div class="ai-panel-tabs">
      <div class="ai-panel-tabs-list">
        <button class="ai-panel-tab" :class="{ 'is-active': aiTab === 'chat' }" @click="aiTab = 'chat'">对话</button>
        <button class="ai-panel-tab" :class="{ 'is-active': aiTab === 'analysis' }" @click="aiTab = 'analysis'">分析</button>
      </div>
    </div>

    <!-- 会话标签栏（分段控件） -->
    <div v-show="aiTab === 'chat'" class="ai-session-tabs">
      <div class="ai-session-tabs-scroll">
        <button
          v-for="s in visibleSessions" :key="s.id"
          class="ai-session-seg" :class="{ 'is-active': s.id === aiSessions.currentBucket.activeSessionId }"
          @click="onSwitchSession(s.id)"
          @mouseenter="segHover = s.id"
          @mouseleave="segHover = null"
        >
          <input
            v-if="renamingId === s.id"
            ref="renameInputRef"
            class="ai-session-seg-input"
            v-model="renameInput"
            @keydown="onRenameKey"
            @blur="confirmRename"
            @click.stop
            :aria-label="'重命名会话'"
          />
          <span v-else class="ai-session-seg-label">{{ s.name }}</span>
          <span class="ai-session-seg-dot"></span>
          <span v-if="segHover === s.id && s.id !== aiSessions.currentBucket.activeSessionId && renamingId !== s.id" class="ai-session-seg-actions">
            <IconButton class="ai-session-seg-action" label="重命名" @click.stop="startRename(s.id)">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 1.5l3 3-9 9H2.5v-3z"/></svg>
            </IconButton>
            <IconButton class="ai-session-seg-action is-close" label="删除" @click.stop="onDeleteSession(s.id)">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8"/><path d="M12 4l-8 8"/></svg>
            </IconButton>
          </span>
        </button>
      </div>
      <div v-if="overflowSessions.length > 0" class="ai-session-overflow">
        <IconButton
          class="ai-session-overflow-btn"
          :class="{ 'is-active': showOverflowMenu }"
          :label="'更多会话 (' + overflowSessions.length + ')'"
          @click.stop="showOverflowMenu = !showOverflowMenu"
        >
          <svg viewBox="0 0 16 16" fill="currentColor"><circle cx="3.5" cy="8" r="1.2"/><circle cx="8" cy="8" r="1.2"/><circle cx="12.5" cy="8" r="1.2"/></svg>
        </IconButton>
        <div v-if="showOverflowMenu" class="ai-session-overflow-menu" @click.stop>
          <div
            v-for="s in overflowSessions" :key="s.id"
            class="ai-session-overflow-item"
            :class="{ 'is-active': s.id === aiSessions.currentBucket.activeSessionId }"
            @click="onSwitchSession(s.id); showOverflowMenu = false"
          >
            <span class="ai-session-overflow-item-label">{{ s.name }}</span>
            <span class="ai-session-overflow-item-actions">
              <IconButton class="ai-session-seg-action" label="重命名" @click.stop="startRename(s.id)">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 1.5l3 3-9 9H2.5v-3z"/></svg>
              </IconButton>
              <IconButton class="ai-session-seg-action is-close" label="删除" @click.stop="onDeleteSession(s.id); showOverflowMenu = false">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8"/><path d="M12 4l-8 8"/></svg>
              </IconButton>
            </span>
          </div>
        </div>
      </div>
      <IconButton class="ai-session-add" label="新建会话" show-label @click="onNewSession()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
      </IconButton>
    </div>

    <!-- 对话 Tab -->
    <div v-show="aiTab === 'chat'" class="ai-feed" ref="feedRef">
      <div v-for="(msg, i) in chat.messages.value" :key="i" class="ai-msg" :class="{ 'is-user': msg.role === 'user' }">
        <div class="ai-bubble" v-html="fmt(msg.content)"></div>
        <!-- 插入纪要/随记按钮（仅 assistant 消息） -->
        <div v-if="msg.role === 'assistant' && msg.content" class="ai-msg-actions">
          <IconButton class="ai-insert-btn" label="插入纪要" show-label @click="onInsertToSummary(msg.content)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="12" y1="18" x2="12" y2="12"/><polyline points="9,15 12,12 15,15"/></svg>
          </IconButton>
          <IconButton class="ai-insert-btn" label="插入随记" show-label @click="onInsertToNotes(msg.content)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          </IconButton>
        </div>
        <!-- 改写 Diff 视图（仅最后一条 assistant 消息且存在改写挂起） -->
        <div v-if="quoteRef.rewritePending.value && i === chat.messages.value.length - 1 && msg.role === 'assistant'" class="diff-view">
          <div class="diff-header">
            <span>原文 → 改写</span>
            <span>{{ quoteRef.rewritePending.value.source }}</span>
          </div>
          <div class="diff-body">
            <p style="margin-bottom:8px;"><span class="diff-del">{{ shortText(quoteRef.rewritePending.value.originalText) }}</span></p>
            <p style="font-size:11px;color:var(--muted);font-style:italic;">AI 改写结果将替换上方删除内容</p>
          </div>
          <div class="diff-actions">
            <IconButton class="diff-accept-btn" label="替换原文" show-label @click="onAcceptRewrite(msg.content)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
            </IconButton>
            <button class="diff-reject-btn" @click="quoteRef.clearRewrite()">放弃</button>
          </div>
        </div>
        <!-- AI 操作校验结果展示 -->
        <div v-if="chat.verifiedChanges.value.length && i === chat.messages.value.length - 1 && msg.role === 'assistant'" class="verified-changes-block">
          <div class="vc-header">AI 操作校验结果</div>
          <div class="vc-list">
            <div v-for="(change, ci) in chat.verifiedChanges.value" :key="ci" class="vc-item" :class="{ 'is-verified': change.verified }">
              <span class="vc-icon">{{ change.verified ? '✅' : '⚠️' }}</span>
              <span class="vc-desc">{{ chat.formatChangeDescription(change) }}</span>
              <span class="vc-status">{{ change.verified ? '磁盘校验通过' : '校验未通过' }}</span>
            </div>
          </div>
        </div>
        <!-- 数据注入提示 -->
        <div v-if="chat.injectPrompt.value && i === chat.messages.value.length - 1 && msg.role === 'assistant'" class="inject-prompt">
          <span>检测到 {{ chat.injectPrompt.value.desc }}</span>
          <button class="btn-inject-all" @click="chat.doInjectAll()">全部注入</button>
          <button class="btn-dismiss" @click="chat.injectPrompt.value = null">忽略</button>
        </div>
      </div>
      <div v-if="chat.isLoading.value" class="ai-msg">
        <div class="ai-bubble" style="opacity:0.6">思考中…</div>
      </div>
    </div>

    <!-- 分析 Tab -->
    <div v-show="aiTab === 'analysis'" class="ai-feed">
      <div v-if="!analysis.hasData.value" class="ai-welcome">
        <p>会议分析</p>
        <p class="ai-welcome-hint">选择已完成的会议后可查看发言统计、议题分布等</p>
      </div>
      <template v-else>
        <!-- 概览卡片 -->
        <div v-if="analysis.overview.value" class="ai-analysis-overview">
          <div class="ai-ao-item">
            <span class="ai-ao-value">{{ analysis.overview.value.speakerCount }}</span>
            <span class="ai-ao-label">说话人</span>
          </div>
          <div class="ai-ao-item">
            <span class="ai-ao-value">{{ analysis.overview.value.dialogueCount }}</span>
            <span class="ai-ao-label">发言数</span>
          </div>
          <div class="ai-ao-item">
            <span class="ai-ao-value">{{ formatCount(analysis.overview.value.wordCount) }}</span>
            <span class="ai-ao-label">总字数</span>
          </div>
          <div class="ai-ao-item">
            <span class="ai-ao-value">{{ analysis.overview.value.duration }}</span>
            <span class="ai-ao-label">时长</span>
          </div>
        </div>
        <!-- 发言占比 -->
        <div class="ai-analysis-section">
          <div class="ai-analysis-label">发言占比</div>
          <div class="ai-analysis-bars">
            <div v-for="sp in analysis.speakerStats.value" :key="sp.name" class="ai-bar-row">
              <span class="ai-bar-name" :title="sp.name">{{ sp.name }}</span>
              <div class="ai-bar-track">
                <div class="ai-bar-fill" :style="{ width: sp.percent + '%' }"></div>
              </div>
              <span class="ai-bar-pct">{{ sp.percent }}%</span>
            </div>
          </div>
        </div>
        <!-- 待办完成 -->
        <div v-if="analysis.todoStats.value" class="ai-analysis-section">
          <div class="ai-analysis-label">待办完成</div>
          <div class="ai-todo-bar">
            <div class="ai-todo-fill" :style="{ width: todoPercent + '%' }" :class="todoPercent >= 100 ? 'is-done' : ''"></div>
          </div>
          <div class="ai-todo-text">
            {{ analysis.todoStats.value.done }} / {{ analysis.todoStats.value.total }} 已完成
          </div>
        </div>
        <!-- 章节时间线 -->
        <div v-if="analysis.chapters.value.length > 1" class="ai-analysis-section">
          <div class="ai-analysis-label">议题段落</div>
          <div class="ai-chapter-list">
            <div v-for="(ch, i) in analysis.chapters.value" :key="i" class="ai-chapter-item">
              <span class="ai-chapter-dot"></span>
              <span class="ai-chapter-info">
                <span class="ai-chapter-title">{{ ch.title }}</span>
                <span class="ai-chapter-meta">{{ ch.lineCount }} 条发言 · {{ ch.speakers.size }} 人参与</span>
              </span>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 输入区（仅对话 Tab） -->
    <div v-show="aiTab === 'chat'" class="ai-input-zone">
      <!-- 跟进建议（始终显示在输入框上方，滚动区外） -->
      <div class="ai-suggestions-bar">
        <button v-for="(s, si) in chat.displaySuggestions.value" :key="si" class="follow-up-chip" @click="chat.sendRaw(s.text)">
          <span v-html="s.icon"></span>{{ s.text }}
        </button>
      </div>
      <!-- 停止生成 -->
      <div class="ai-stop-gen" :class="{ 'is-visible': chat.isLoading.value }">
        <button class="ai-stop-gen-btn" @click="chat.stopGeneration()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>
          停止生成
        </button>
      </div>
      <!-- 引用区域 -->
      <div v-if="quoteRef.quoteRef.value" class="quote-ref">
        <div class="quote-ref-text">{{ quoteRef.quoteRef.value.text }}</div>
        <div class="quote-ref-source">
          <span class="src-dot"></span>
          <span>来源：{{ quoteRef.quoteRef.value.source }}{{ quoteRef.quoteRef.value.blockIndex >= 0 ? ' · 第 ' + (quoteRef.quoteRef.value.blockIndex + 1) + ' 块' : '' }}</span>
        </div>
        <button class="quote-ref-remove" title="移除引用" @click="quoteRef.clearQuote()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
      <div class="ai-input-box">
        <textarea
          v-model="inputText"
          placeholder="输入问题…"
          rows="1"
          ref="inputRef"
          @keydown="handleInputKey"
          @input="handleInputChange"
          aria-label="输入问题"
        ></textarea>
        <button class="ai-send-btn" :disabled="!inputText.trim() || chat.isLoading.value" @click="onSend">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { useTaskStore } from '@/stores/task'
import { useLayoutStore } from '@/stores/layout'
import { useAiChat } from '@/composables/useAiChat'
import { useQuoteRef } from '@/composables/useQuoteRef'
import { useAiSessionsStore } from '@/stores/aiSessions'
import { useAiAnalysis } from '@/composables/useAiAnalysis'
import { showToast } from '@/composables/useToast'
import { beginResize } from '@/composables/useDivider'
import IconButton from '@/components/common/IconButton.vue'

const taskStore = useTaskStore()
const layout = useLayoutStore()

function onToggleDown(e: MouseEvent) {
  beginResize(e, 'right', { onClick: () => layout.toggleAi(), resizable: !layout.aiCollapsed })
}
const chat = useAiChat()
const quoteRef = useQuoteRef()
const aiSessions = useAiSessionsStore()
const analysis = useAiAnalysis()

const aiTab = ref('chat')
const inputText = ref('')
const inputRef = ref<HTMLTextAreaElement | null>(null)
const feedRef = ref<HTMLElement | null>(null)

const showOverflowMenu = ref(false)
const segHover = ref<string | null>(null)
const renamingId = ref<string | null>(null)
const renameInput = ref('')
const renameInputRef = ref<HTMLInputElement | HTMLInputElement[] | null>(null)
const MAX_VISIBLE_SESSIONS = 3
const visibleSessions = computed(() => aiSessions.sessions.slice(0, MAX_VISIBLE_SESSIONS))
const overflowSessions = computed(() => aiSessions.sessions.slice(MAX_VISIBLE_SESSIONS))

const todoPercent = computed(() => {
  const ts = analysis.todoStats.value
  if (!ts || ts.total === 0) return 0
  return Math.round((ts.done / ts.total) * 100)
})

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

onMounted(() => {
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
  showOverflowMenu.value = false
}

function onGlobalAiFocus() {
  aiTab.value = 'chat'
  nextTick(() => {
    inputRef.value?.focus()
  })
}

function onQuoteToAiEvent(e: Event) {
  const detail = (e as CustomEvent).detail || {}
  if (layout.aiCollapsed) layout.toggleAi()
  aiTab.value = 'chat'
  nextTick(() => {
    inputRef.value?.focus()
    if (detail.action) {
      const ctx = quoteRef.getQuoteContext()
      let fullText = detail.action
      if (ctx) {
        fullText = ctx.context + '\n用户指令: ' + detail.action
      }
      chat.sendRaw(fullText)
    }
  })
}

function onNewSession() {
  aiSessions.createNewSession()
  nextTick(() => scrollFeed())
}

function onSwitchSession(sessionId: string) {
  aiSessions.switchTo(sessionId)
  followUps_reset()
  nextTick(() => scrollFeed())
}

function startRename(sessionId: string) {
  const session = aiSessions.sessions.find(s => s.id === sessionId)
  if (!session) return
  renamingId.value = sessionId
  renameInput.value = session.name
  showOverflowMenu.value = false
  nextTick(() => {
    const el = Array.isArray(renameInputRef.value) ? renameInputRef.value[0] : renameInputRef.value
    el?.focus()
    el?.select()
  })
}

function confirmRename() {
  if (renamingId.value && renameInput.value.trim()) {
    aiSessions.renameSession(renamingId.value, renameInput.value.trim())
  }
  renamingId.value = null
}

function cancelRename() {
  renamingId.value = null
}

function onRenameKey(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    confirmRename()
  } else if (e.key === 'Escape') {
    e.preventDefault()
    cancelRename()
  }
}

function onDeleteSession(sessionId: string) {
  if (renamingId.value === sessionId) cancelRename()
  aiSessions.deleteSession(sessionId)
  nextTick(() => scrollFeed())
}

function followUps_reset() {
  chat.followUps.value = []
  chat.injectPrompt.value = null
}

/** 发送消息 */
async function onSend() {
  const text = inputText.value.trim()
  if ((!text && !quoteRef.quoteRef.value) || chat.isLoading.value) return
  inputText.value = ''
  autoResize()

  let fullText = text
  const ctx = quoteRef.getQuoteContext()
  if (ctx) {
    fullText = text ? ctx.context + '\n用户指令: ' + text : ctx.context + '\n请帮我处理这段引用内容'
  }

  await chat.sendRaw(fullText)
  await scrollFeed()
}

/** 输入框键盘事件 */
function handleInputKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    onSend()
  }
}

/** 输入变化 → 自动调整高度 */
function handleInputChange() {
  autoResize()
}

function autoResize() {
  const ta = inputRef.value
  if (!ta) return
  ta.style.height = 'auto'
  ta.style.height = Math.min(ta.scrollHeight, 120) + 'px'
}

async function scrollFeed() {
  await nextTick()
  if (feedRef.value) feedRef.value.scrollTop = feedRef.value.scrollHeight
}

/** Markdown 简易格式化 */
function fmt(c: string): string {
  return c
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}

/** 截断文本用于 Diff 显示 */
function shortText(text: string): string {
  return text.length > 80 ? text.slice(0, 80) + '…' : text
}

/** 接受改写 — 用 AI 回复替换原文块 */
function onAcceptRewrite(aiContent: string) {
  const ok = quoteRef.acceptRewrite(aiContent)
  if (ok) {
    showToast('已替换原文', 'success')
  } else {
    showToast('无法定位原文块', 'warn')
  }
}

/** 插入内容到纪要 */
function onInsertToSummary(content: string) {
  const ok = quoteRef.insertToSummary(content)
  if (ok) {
    showToast('已插入到纪要', 'success')
  } else {
    showToast('请先打开一个会议的纪要页面', 'warn')
  }
}

/** 插入内容到随记 */
function onInsertToNotes(content: string) {
  const ok = quoteRef.insertToNotes(content)
  if (ok) {
    showToast('已插入到随记', 'success')
  } else {
    showToast('请先打开一个会议的随记页面', 'warn')
  }
}

/** 消息变化时自动滚动 */
watch(() => chat.messages.value.length, () => scrollFeed())
</script>

<style scoped>
.ai-welcome { text-align: center; padding: 40px 0; color: var(--muted); font-size: 14px; }
.ai-welcome-hint { font-size: 12px; color: var(--subtle); margin-top: 8px; }
.ai-cmd-list { padding: var(--s-2); display: flex; flex-direction: column; gap: var(--s-3); }
.ai-cmd-group { display: flex; flex-direction: column; gap: 2px; }
.ai-cmd-group-label { font-size: var(--fs-11); color: var(--subtle); font-weight: 500; letter-spacing: 0.02em; padding: 4px 10px; }
.ai-msg-actions { display: flex; gap: 6px; padding: 4px 0 2px; opacity: 0; transition: opacity 0.15s; }
.ai-msg:hover .ai-msg-actions { opacity: 1; }
.ai-insert-btn { display: inline-flex; align-items: center; gap: 3px; padding: 3px 8px; border-radius: 4px; font-size: 11px; color: var(--muted); background: transparent; border: 1px solid var(--border); cursor: pointer; transition: all 0.12s; }
.ai-insert-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft, oklch(95% 0.02 255)); }
.ai-insert-btn svg { width: 12px; height: 12px; flex-shrink: 0; }

/* AI 操作校验结果展示 */
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
