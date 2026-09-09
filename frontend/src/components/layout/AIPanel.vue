<template>
  <div class="ai" :class="{ 'is-collapsed': layout.aiCollapsed }">
    <button class="ai-toggle" @click="layout.toggleAi()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
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
        <button class="ai-header-btn" @click="chat.clearConversation()" title="清空对话">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
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
        <button class="ai-panel-tab" :class="{ 'is-active': aiTab === 'commands' }" @click="aiTab = 'commands'">指令</button>
      </div>
    </div>

    <!-- 会话标签栏 -->
    <div v-show="aiTab === 'chat'" class="ai-session-tabs">
      <div class="ai-session-tabs-scroll">
        <button
          v-for="s in aiSessions.sessions" :key="s.id"
          class="ai-session-tab" :class="{ 'is-active': s.id === aiSessions.currentBucket.activeSessionId }"
          @click="onSwitchSession(s.id)"
          :title="s.name"
        >
          <span class="ai-session-tab-label">{{ s.name }}</span>
          <span class="ai-session-tab-actions">
            <button class="ai-session-tab-rename" @click.stop="onRenameSession(s.id)" title="重命名" aria-label="重命名">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 1.5l3 3-9 9H2.5v-3z"/></svg>
            </button>
            <button class="ai-session-tab-close" @click.stop="onDeleteSession(s.id)" title="删除会话" aria-label="删除会话">&times;</button>
          </span>
        </button>
      </div>
      <button class="ai-session-add" @click="onNewSession()" title="新建会话" aria-label="新建会话">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
        <span>新建</span>
      </button>
    </div>

    <!-- 对话 Tab -->
    <div v-show="aiTab === 'chat'" class="ai-feed" ref="feedRef">
      <div v-if="chat.messages.value.length === 0" class="ai-guidance is-active">
        <div class="ai-guidance-header">
          <div class="ai-guidance-icon" v-html="guidance.guidance.value.icon"></div>
          <div class="ai-guidance-title">{{ guidance.guidance.value.title }}</div>
          <div class="ai-guidance-sub">{{ guidance.guidance.value.sub }}</div>
        </div>
        <div class="ai-guidance-context">
          <span v-for="ctx in guidance.guidance.value.contexts" :key="ctx" class="ai-guidance-ctx-tag">{{ ctx }}</span>
        </div>
        <div>
          <div class="ai-guidance-section-label">推荐提问</div>
          <div class="ai-guidance-prompts">
            <button v-for="(p, pi) in guidance.guidance.value.prompts" :key="pi" class="ai-guidance-prompt" @click="chat.sendRaw(p.text)">
              <span class="gp-icon" v-html="p.icon"></span>
              {{ p.text }}
            </button>
          </div>
        </div>
        <div class="conv-quick-cmds">
          <button class="conv-qcmd" @click="chat.sendRaw('请从会议内容中提取关键信息并生成结构化纪要。')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 6h16M4 12h10M4 18h14"/></svg>
            生成会议纪要
          </button>
          <button class="conv-qcmd" @click="chat.sendRaw('请从会议内容中提取所有待办事项，明确责任人和截止时间。')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
            提取待办事项
          </button>
          <button class="conv-qcmd" @click="chat.sendRaw('请分析本次会议中各发言人的核心观点和论据。')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
            分析发言要点
          </button>
          <button class="conv-qcmd" @click="chat.sendRaw('请总结本次会议做出的关键决策及决策依据。')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            总结关键决策
          </button>
          <button class="conv-qcmd" @click="chat.sendRaw('请识别会议讨论中提到的风险点和未解决的争议。')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            识别风险与争议
          </button>
        </div>
        <div class="ai-guidance-hint">
          输入 <kbd>/</kbd> 查看所有指令
        </div>
      </div>
      <div v-for="(msg, i) in chat.messages.value" :key="i" class="ai-msg" :class="{ 'is-user': msg.role === 'user' }">
        <div class="ai-bubble" v-html="fmt(msg.content)"></div>
        <!-- 插入纪要/笔记按钮（仅 assistant 消息） -->
        <div v-if="msg.role === 'assistant' && msg.content" class="ai-msg-actions">
          <button class="ai-insert-btn" @click="onInsertToSummary(msg.content)" title="插入到纪要">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="12" y1="18" x2="12" y2="12"/><polyline points="9,15 12,12 15,15"/></svg>
            插入纪要
          </button>
          <button class="ai-insert-btn" @click="onInsertToNotes(msg.content)" title="插入到笔记">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
            插入笔记
          </button>
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
            <button class="diff-accept-btn" @click="onAcceptRewrite(msg.content)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
              替换原文
            </button>
            <button class="diff-reject-btn" @click="quoteRef.clearRewrite()">放弃</button>
          </div>
        </div>
        <!-- 跟进建议（仅最后一条 assistant 消息） -->
        <div v-if="chat.followUps.value.length && i === chat.messages.value.length - 1 && msg.role === 'assistant'" class="follow-up-suggestions">
          <button v-for="(s, si) in chat.followUps.value" :key="si" class="follow-up-chip" @click="chat.sendRaw(s.text)">
            <span v-html="s.icon"></span>{{ s.text }}
          </button>
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

    <!-- 指令 Tab -->
    <div v-show="aiTab === 'commands'" class="ai-feed">
      <div class="ai-cmd-list">
        <div v-for="group in commandGroups" :key="group.label" class="ai-cmd-group">
          <div class="ai-cmd-group-label">{{ group.label }}</div>
          <button v-for="cmd in group.cmds" :key="cmd.key" class="ai-cmd-item" @click="runCommand(cmd)">
            <span class="cmd-key">{{ cmd.key }}</span>
            <span class="cmd-label">{{ cmd.desc }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 输入区（仅对话 Tab） -->
    <div v-show="aiTab === 'chat'" class="ai-input-zone">
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
      <!-- 指令面板 -->
      <div class="ai-cmd-palette" :class="{ 'is-open': cmds.cmdOpen.value && filteredCmds.length > 0 }">
        <template v-if="filteredCmds.length > 0">
          <!-- 高频指令 -->
          <template v-if="!isFiltered && frequentCmds.length > 0">
            <button v-for="(c, ci) in frequentCmds" :key="c.key" class="ai-cmd-item" :class="{ 'is-active': cmds.cmdIndex.value === ci }" @click="runCommand(c)">
              <span class="cmd-key">{{ c.key }}</span>
              <span class="cmd-label">{{ c.desc }}</span>
            </button>
          </template>
          <!-- 更多指令 -->
          <template v-if="!isFiltered && restCmds.length > 0">
            <div class="ai-cmd-group-header">
              <span>更多指令</span>
              <button class="ai-cmd-group-toggle" :class="{ 'is-expanded': cmdGroupExpanded }" @click="cmdGroupExpanded = !cmdGroupExpanded" aria-label="展开更多指令">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="9 6 15 12 9 18"/></svg>
                <span>{{ restCmds.length }}</span>
              </button>
            </div>
            <div class="ai-cmd-group-body" :class="{ 'is-expanded': cmdGroupExpanded }">
              <button v-for="(c, ci) in restCmds" :key="c.key" class="ai-cmd-item" :class="{ 'is-active': cmds.cmdIndex.value === frequentCmds.length + ci }" @click="runCommand(c)">
                <span class="cmd-key">{{ c.key }}</span>
                <span class="cmd-label">{{ c.desc }}</span>
              </button>
            </div>
          </template>
          <!-- 搜索结果（有过滤条件时直接平铺） -->
          <template v-if="isFiltered">
            <button v-for="(c, ci) in filteredCmds" :key="c.key" class="ai-cmd-item" :class="{ 'is-active': cmds.cmdIndex.value === ci }" @click="runCommand(c)">
              <span class="cmd-key">{{ c.key }}</span>
              <span class="cmd-label">{{ c.desc }}</span>
            </button>
          </template>
        </template>
        <div v-else-if="inputText.startsWith('/')" class="ai-cmd-empty">无匹配指令</div>
      </div>
      <div class="ai-input-box">
        <textarea
          v-model="inputText"
          placeholder="输入问题，/ 打开指令…"
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
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/task'
import { useLayoutStore } from '@/stores/layout'
import { useAiChat } from '@/composables/useAiChat'
import { useAiCommands } from '@/composables/useAiCommands'
import { useQuoteRef } from '@/composables/useQuoteRef'
import type { AiCommand } from '@/composables/useAiCommands'
import { useAiSessionsStore } from '@/stores/aiSessions'
import { useAiAnalysis } from '@/composables/useAiAnalysis'
import { useAiGuidance } from '@/composables/useAiGuidance'
import { showToast } from '@/composables/useToast'

const router = useRouter()
const taskStore = useTaskStore()
const layout = useLayoutStore()
const chat = useAiChat()
const cmds = useAiCommands()
const quoteRef = useQuoteRef()
const aiSessions = useAiSessionsStore()
const analysis = useAiAnalysis()
const guidance = useAiGuidance()

const aiTab = ref('chat')
const inputText = ref('')
const inputRef = ref<HTMLTextAreaElement | null>(null)
const feedRef = ref<HTMLElement | null>(null)
const cmdGroupExpanded = ref(false)

const currentStatus = computed(() => taskStore.currentTask?.status ?? null)

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

/** 注册指令列表 */
onMounted(() => {
  cmds.registerCommands(buildCommands())
  window.addEventListener('quote-to-ai', onQuoteToAiEvent)
  window.addEventListener('global-ai-focus', onGlobalAiFocus)
})

onBeforeUnmount(() => {
  window.removeEventListener('quote-to-ai', onQuoteToAiEvent)
  window.removeEventListener('global-ai-focus', onGlobalAiFocus)
})

function onGlobalAiFocus() {
  aiTab.value = 'chat'
  nextTick(() => {
    inputRef.value?.focus()
    // 如果输入框为空，插入 "/" 触发指令面板
    if (!inputText.value) {
      inputText.value = '/'
    }
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

/** 当任务变化时重新注册（action 闭包捕获最新状态） */
watch(() => taskStore.currentTaskId, () => {
  cmds.registerCommands(buildCommands())
})

function onNewSession() {
  aiSessions.createNewSession()
  nextTick(() => scrollFeed())
}

function onSwitchSession(sessionId: string) {
  aiSessions.switchTo(sessionId)
  followUps_reset()
  nextTick(() => scrollFeed())
}

function onDeleteSession(sessionId: string) {
  aiSessions.deleteSession(sessionId)
  nextTick(() => scrollFeed())
}

function onRenameSession(sessionId: string) {
  const session = aiSessions.sessions.find(s => s.id === sessionId)
  if (!session) return
  const newName = prompt('重命名会话', session.name)
  if (newName?.trim()) {
    aiSessions.renameSession(sessionId, newName)
  }
}

function followUps_reset() {
  chat.followUps.value = []
  chat.injectPrompt.value = null
}

function buildCommands(): AiCommand[] {
  return [
    { key: '/进度', desc: '目前讨论到哪了', when: 'all', action: () => chat.sendRaw('目前讨论到哪了？请精炼总结当前进度') },
    { key: '/回顾', desc: '回顾最近 N 分钟的讨论要点', when: 'all', action: () => chat.sendRaw('回顾最近 5 分钟的讨论要点') },
    { key: '/笔记', desc: '添加一条手动笔记', when: 'all', action: () => {
      const text = prompt('输入笔记内容：')
      if (text) chat.sendRaw(`笔记：${text}`)
    }},
    { key: '/对齐', desc: '将当前讨论与项目档案做差异比对', when: 'all', action: () => chat.sendRaw('对照项目档案，当前讨论有哪些偏离既定方案的地方？') },
    { key: '/待办', desc: '提取本次会议的待办事项', when: 'completed', action: () => chat.sendRaw('提取所有待办事项') },
    { key: '/结论', desc: '总结会议关键结论', when: 'completed', action: () => chat.sendRaw('总结关键结论') },
    { key: '/总结', desc: '生成结构化会议总结', when: 'completed', action: () => chat.sendRaw('生成结构化会议总结') },
    { key: '/发言', desc: '分析各发言人发言占比', when: 'completed', action: () => chat.sendRaw('分析各发言人的发言时长占比') },
    { key: '/导出', desc: '导出纪要到中心区域', when: 'completed', trigger: true, action: () => {
      chat.sendRaw('导出会议纪要')
      showToast('已触发「导出」→ 请在中心区域查看导出预览')
    }},
    { key: '/归档', desc: '归档本次会议记录', when: 'completed', trigger: true, action: () => {
      chat.sendRaw('归档本次会议')
      showToast('已触发「归档」→ 请在中心区域确认')
    }},
    { key: '/重新生成', desc: '重新生成章节摘要', when: 'completed', trigger: true, action: () => chat.sendRaw('重新生成纪要') },
    { key: '/录音', desc: '开始/停止录音', when: 'all', action: () => {
      const task = taskStore.currentTask
      if (task?.status === 'recording') {
        router.push(`/recording/${task.task_id}`)
      } else {
        router.push('/')
      }
    }},
    { key: '/历史', desc: '查看全部会议', when: 'all', action: () => { router.push('/library') }},
    { key: '/热词', desc: '打开热词管理', when: 'all', action: () => { router.push('/hotwords') }},
    { key: '/清除', desc: '清除当前对话历史', when: 'all', action: () => { chat.clearConversation() }},
    { key: '/帮助', desc: '查看所有可用指令', when: 'all', action: () => showCommandHelp() },
  ]
}

/** 当前过滤后的指令 */
const filteredCmds = computed(() => {
  if (!inputText.value.startsWith('/')) return []
  const query = inputText.value.slice(1).toLowerCase()
  return cmds.filterCommands(query, currentStatus.value)
})

const isFiltered = computed(() => filteredCmds.value.length < cmds.getAvailable(currentStatus.value).length)

const frequentCmds = computed(() => filteredCmds.value.filter(c => cmds.isFrequent(c.key)))
const restCmds = computed(() => filteredCmds.value.filter(c => !cmds.isFrequent(c.key)))

/** 指令 Tab 分组 */
const commandGroups = computed(() => {
  const available = cmds.getAvailable(currentStatus.value)
  return [
    { label: '通用', cmds: available.filter(c => c.when === 'all') },
    { label: '录制中', cmds: available.filter(c => c.when === 'recording') },
    { label: '已完成', cmds: available.filter(c => c.when === 'completed') },
  ].filter(g => g.cmds.length > 0)
})

/** 执行指令 */
function runCommand(cmd: AiCommand) {
  cmds.close()
  inputText.value = ''
  cmd.action()
}

/** 显示命令帮助 */
function showCommandHelp() {
  const available = cmds.getAvailable(currentStatus.value)
  const statusLabel = currentStatus.value === 'recording' ? '录制中' : currentStatus.value === 'completed' ? '已完成' : '通用'
  const text = `当前状态「${statusLabel}」可用指令：\n` + available.map(c => `${c.key} — ${c.desc}`).join('\n')
  chat.messages.value.push({ role: 'assistant', content: text })
  aiSessions.persist()
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
  const isOpen = cmds.cmdOpen.value && filteredCmds.value.length > 0

  if (isOpen) {
    const items = filteredCmds.value
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      cmds.moveDown(items.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      cmds.moveUp()
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (cmds.cmdIndex.value >= 0 && items[cmds.cmdIndex.value]) {
        runCommand(items[cmds.cmdIndex.value])
      }
    } else if (e.key === 'Escape') {
      e.preventDefault()
      cmds.close()
    }
    return
  }

  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    onSend()
  }
}

/** 输入变化 → 触发指令面板 */
function handleInputChange() {
  autoResize()
  const val = inputText.value
  if (val.startsWith('/')) {
    const query = val.slice(1).toLowerCase()
    const available = cmds.getAvailable(currentStatus.value)
    const filtered = available.filter(c => c.key.slice(1).toLowerCase().includes(query))
    if (filtered.length > 0) {
      cmds.open()
    } else {
      cmds.close()
    }
  } else {
    cmds.close()
  }
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

/** 插入内容到笔记 */
function onInsertToNotes(content: string) {
  const ok = quoteRef.insertToNotes(content)
  if (ok) {
    showToast('已插入到笔记', 'success')
  } else {
    showToast('请先打开一个会议的笔记页面', 'warn')
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
