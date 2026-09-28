<template>
  <!-- 对话消息流 / Chat message feed -->
  <div class="ai-feed" ref="feedRef">
    <div v-for="(msg, i) in messages" :key="i" class="ai-msg" :class="{ 'is-user': msg.role === 'user' }">
      <div class="ai-bubble" v-html="fmt(msg.content)"></div>
      <!-- 回复尾部消费方/计费回显（REQ-EXPERT-MODE §2.3：与 routing 实际判定一致） -->
      <div v-if="msg.role === 'assistant' && msg.modelUsage" class="ai-usage-echo">
        {{ t('ai-panel.usage_echo', { model: msg.modelUsage.model, src: srcLabel(msg.modelUsage.source), billing: billingLabel(msg.modelUsage.billing) }) }}<span v-if="msg.modelUsage.auto_switched">{{ t('ai-panel.usage_echo_auto_switched') }}</span>
      </div>
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
          <!-- 工具图标：lucide 名命中则内联 SVG（多 CLI 引擎双语标签体系），未命中降级为文本/emoji（历史消息兼容） -->
          <svg v-if="stageIcon(stage)" class="ai-stage-icon" :viewBox="stageIcon(stage)!.viewBox" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="stageIcon(stage)!.body"></svg>
          <span v-else-if="stage.icon" class="ai-stage-icon">{{ stage.icon }}</span>
          <svg v-else-if="stage.status === 'running'" class="ai-stage-spinner" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 1a7 7 0 1 1-7 7" stroke-linecap="round"/></svg>
          <span v-else class="ai-stage-check">✓</span>
          <span class="ai-stage-label">{{ stage.label }}</span>
          <span v-if="stage.detail && stage.status !== 'running'" class="ai-stage-detail">{{ stage.detail }}</span>
        </div>
      </div>
      <!-- 回退：无阶段时显示简单思考指示器 / Fallback: simple thinking indicator when no stages -->
      <div v-else-if="isLoading && stages.length === 0 && !isStreaming" class="ai-thinking" role="status" aria-live="polite">
        <svg class="ai-thinking-spinner" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M8 1a7 7 0 1 1-7 7" stroke-linecap="round"/></svg>
        <span class="ai-thinking-text">{{ t('ai-panel.thinking_elapsed', { sec: thinkingElapsed }) }}</span>
      </div>
    </Transition>
  </div>

  <!-- 输入区 / Input zone -->
  <div class="ai-input-zone">
    <!-- 跟进建议 / Follow-up suggestions -->
    <div v-show="suggestions.length > 0" class="ai-suggestions-bar">
      <button v-for="(s, si) in suggestions" :key="si" class="follow-up-chip" @click="$emit('sendRaw', s.text)"><span v-html="s.icon"></span>{{ s.text }}</button>
    </div>
    <!-- 停止输入由 composer 发送/停止按钮承接（原型 ai-panel-composer-prototype） -->
    <!-- 引用区域 / Quote reference -->
    <div v-if="quoteText" class="quote-ref">
      <div class="quote-ref-text">{{ quoteText }}</div>
      <div class="quote-ref-source"><span class="src-dot"></span><span>{{ quoteSource }}</span></div>
      <button class="quote-ref-remove" :title="t('ai-panel.quote.remove')" @click="$emit('clearQuote')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
    </div>
    <!-- 指令面板 / Command palette -->
    <div class="ai-cmd-palette" :class="{ 'is-open': cmdOpen && filteredCmds.length > 0 }">
      <template v-if="filteredCmds.length > 0">
        <button v-for="(c, ci) in filteredCmds" :key="c.key" class="ai-cmd-item" :class="{ 'is-active': cmdIndex === ci }" :aria-label="c.desc" @click="$emit('runCommand', c)"><span class="cmd-key">{{ c.key }}</span><span class="cmd-label">{{ c.desc }}</span></button>
      </template>
      <div v-else-if="inputText.startsWith('/')" class="ai-cmd-empty">无匹配指令</div>
    </div>
    <!-- 算力探针前置警告（§2.2 AC-4：失败段定位 + 一键改用问答） / CLI probe notice -->
    <div v-if="chatMode !== 'qa' && cliProbe && !cliProbe.available" class="ai-cli-probe-warn">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01"/><circle cx="12" cy="12" r="9"/></svg>
      <span>{{ probeHintText }}<a class="cpw-switch" href="#" @click.prevent="$emit('update:chatMode', 'qa')">{{ t('ai-panel.mode_notice_switch_qa') }}</a></span>
    </div>
    <!-- 输入框（原型 composer：无边框 textarea 居上） / Input on top -->
    <textarea class="composer-input" :value="inputText" @input="$emit('update:inputText', ($event.target as HTMLTextAreaElement).value); $emit('inputChange')" :placeholder="t('ai-panel.input_placeholder')" rows="1" ref="inputRef" @keydown="$emit('inputKey', $event)" :aria-label="t('ai-panel.input_aria')"></textarea>
    <!-- Composer 栏（原型 ai-panel-composer-prototype）：模式触发器 + 资源触发器（左）+ 提示 + 发送/停止（右），同一栏 -->
    <div class="composer-bar">
      <!-- 对话模式触发器（会话级，与“角色”正交） / Mode trigger -->
      <div class="cb-trigger-wrap">
        <button ref="modeTriggerEl" class="ac-trigger" :class="{ 'is-open': modeMenuVisible }" v-bind="modeTriggerAttrs" :aria-label="t('ai-panel.mode_label')" :title="t('ai-panel.mode_label')" @click="toggleModeMenu">
          <svg class="ac-tr-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20 12a7 7 0 0 1-7 7H8l-4 3v-3.5A7 7 0 0 1 11 5h2a7 7 0 0 1 7 7Z"/></svg>
          <span class="ac-tr-txt">
            <span class="ac-tr-name">{{ t('ai-panel.mode_' + chatMode) }}</span>
            <span class="ac-tr-sub">{{ chatMode === 'agent' ? 'CLI' : chatMode === 'auto' ? 'AUTO' : t('ai-panel.mode_sub_builtin') }}</span>
          </span>
          <svg class="ac-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
        </button>
        <div ref="modeMenuEl" v-show="modeMenuVisible" class="ac-menu" style="width: 288px;" v-bind="modeMenuAttrs">
          <div class="ac-group">
            <div class="ac-label"><span>{{ t('ai-panel.mode_label') }}</span><span>3</span></div>
            <button v-for="m in (['auto', 'qa', 'agent'] as const)" :key="m" class="ac-row" role="menuitem" :class="{ 'is-sel': chatMode === m }" :aria-label="t('ai-panel.mode_' + m)" @click="onPickMode(m)">
              <span class="ac-badge">{{ m === 'auto' ? 'A' : m === 'qa' ? 'Q' : '>_' }}</span>
              <span class="ac-it"><span class="ac-it-name">{{ t('ai-panel.mode_' + m) }}</span><span class="ac-it-sub">{{ t('ai-panel.mode_' + m + '_hint') }}</span></span>
              <span class="ac-right">
                <svg v-if="chatMode === m" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
              </span>
            </button>
          </div>
        </div>
      </div>

      <!-- 模型/引擎模型触发器：智能体模式选 CLI 引擎模型（写 chat_engine.model），其余选 LLM 模型（class ai-model-select 为契约测试锚点） -->
      <div class="cb-trigger-wrap">
        <button ref="modelTriggerEl" class="ac-trigger ai-model-select" :class="{ 'is-open': modelMenuVisible }" v-bind="modelTriggerAttrs" :aria-label="isAgentMode ? t('ai-panel.model_cli_engine_label') : t('ai-panel.model_label')" @click="toggleModelMenu">
          <svg class="ac-tr-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 3v3M14 3v3M10 18v3M14 18v3M3 10h3M3 14h3M18 10h3M18 14h3"/></svg>
          <span class="ac-tr-txt">
            <span class="ac-tr-name">{{ isAgentMode ? (agentEngineModel || t('ai-panel.model_cli_engine_default')) : (sessionModel || detailModelLabel) }}</span>
            <span class="ac-tr-sub">{{ isAgentMode ? (agentEngineName || 'CLI') : (sessionModel ? sourceLabel(menuModelSource) : t('ai-panel.model_follow_plain')) }}</span>
          </span>
          <svg class="ac-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
        </button>
        <div ref="modelMenuEl" v-show="modelMenuVisible" class="ac-menu" style="width: 322px;" v-bind="modelMenuAttrs">
          <!-- 智能体模式：CLI 引擎可用模型（--list-models 探测，就地写回 chat_engine.model） -->
          <template v-if="isAgentMode">
            <div class="ac-group">
              <div class="ac-label"><span>{{ agentEngineName || 'CLI' }}</span><span>{{ agentModels.length }}</span></div>
              <button class="ac-row" role="menuitem" :class="{ 'is-sel': !agentEngineModel }" :aria-label="t('ai-panel.model_cli_engine_default')" @click="onPickAgentModel('')">
                <span class="ac-badge">⇄</span>
                <span class="ac-it"><span class="ac-it-name">{{ t('ai-panel.model_cli_engine_default') }}</span><span class="ac-it-sub">{{ t('ai-panel.model_cli_engine_default_hint') }}</span></span>
                <span class="ac-right">
                  <svg v-if="!agentEngineModel" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
                </span>
              </button>
            </div>
            <div v-if="agentModels.length" class="ac-group">
              <button v-for="m in agentModels" :key="m" class="ac-row" role="menuitem" :class="{ 'is-sel': agentEngineModel === m }" :aria-label="m" @click="onPickAgentModel(m)">
                <span class="ac-badge">M</span>
                <span class="ac-it"><span class="ac-it-name">{{ m }}</span><span class="ac-it-sub">{{ t('ai-panel.model_cli_available') }}</span></span>
                <span class="ac-right">
                  <svg v-if="agentEngineModel === m" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
                </span>
              </button>
            </div>
            <div v-else class="ac-empty">{{ agentModelsLoading ? t('ai-panel.model_cli_loading') : (agentModelsReason === 'not_logged_in' ? t('ai-panel.model_cli_need_login') : t('ai-panel.model_cli_unavailable')) }}</div>
            <button class="ac-foot" role="menuitem" :aria-label="t('ai-panel.model_cli_goto')" @click="onGotoCliSettings">
              <span>{{ t('ai-panel.model_cli_goto') }}</span>
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg>
            </button>
          </template>
          <!-- 问答/自动模式：LLM 模型清单（按来源分组） -->
          <template v-else>
            <div class="ac-group">
              <button class="ac-row" role="menuitem" :class="{ 'is-sel': !sessionModel }" :aria-label="t('ai-panel.model_follow', { model: detailModelLabel })" @click="onPickModel('', '')">
                <span class="ac-badge">⇄</span>
                <span class="ac-it"><span class="ac-it-name">{{ t('ai-panel.model_follow_plain') }}</span><span class="ac-it-sub">{{ t('ai-panel.model_follow', { model: detailModelLabel }) }}</span></span>
                <span class="ac-right">
                  <svg v-if="!sessionModel" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
                </span>
              </button>
            </div>
            <div v-for="g in modelGroups" :key="g.source" class="ac-group">
              <div class="ac-label"><span>{{ srcLabel(g.source) }}</span><span>{{ g.opts.length }}</span></div>
              <button v-for="opt in g.opts" :key="opt.value" class="ac-row" role="menuitem" :class="{ 'is-sel': sessionModel === opt.value && menuModelSource === g.source }" :aria-label="opt.value + ' · ' + srcLabel(g.source)" @click="onPickModel(opt.value, g.source)">
                <span class="ac-badge">{{ srcLabel(g.source).slice(0, 1) }}</span>
                <span class="ac-it">
                  <span class="ac-it-name">{{ opt.value }}</span>
                  <span class="ac-it-sub">{{ g.source === 'local' ? t('ai-panel.model_local_endpoint') : t('ai-panel.model_configured') }}</span>
                </span>
                <span class="ac-right">
                  <svg v-if="sessionModel === opt.value && menuModelSource === g.source" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
                </span>
              </button>
            </div>
            <button class="ac-foot" role="menuitem" :aria-label="t('ai-panel.model_manage_sources')" @click="onGotoComputeSettings">
              <span>{{ t('ai-panel.model_manage_sources') }}</span>
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg>
            </button>
          </template>
        </div>
      </div>

      <div class="cb-right">
        <span v-if="!isLoading && chatMode !== 'agent'" class="cb-hint">⏎ · ⇧⏎</span>
        <!-- 发送 / 停止（合一按钮，与触发器同栏，原型 composer） / Send / Stop -->
        <button class="composer-send" :class="{ 'is-stop': isLoading }" :disabled="!isLoading && !inputText.trim()" :aria-label="isLoading ? t('ai-panel.stop_generating') : t('ai-panel.send')" :title="isLoading ? t('ai-panel.stop_generating') : t('ai-panel.send')" @click="onSendOrStop">
          <span>{{ isLoading ? t('ai-panel.stop_generating') : t('ai-panel.send') }}</span>
          <svg v-if="isLoading" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { LlmMetadata, MessagePerformance, SourceFile, AgentStage, ModelUsage } from '@/api/chat'
import type { ChatEngineProbe } from '@/api/settings'
import { useI18n } from 'vue-i18n'
import IconButton from '@/components/common/IconButton.vue'
import { escapeHtml } from '@/utils/sanitize'
import { lucideIcon, type IconDef } from '@/utils/lucideIcons'
import type { AiCommand } from '@/composables/useAiCommands'
import { usePopMenu } from '@/composables/usePopMenu'


const { t } = useI18n()

/** 阶段图标：按 lucide 名取 SVG 定义（非 lucide 名返回 null 走文本降级） */
function stageIcon(stage: AgentStage): IconDef | null {
  return lucideIcon(stage.icon)
}

const props = defineProps<{
  messages: Array<{ role: string; content: string; timestamp?: string; metadata?: LlmMetadata; sources?: SourceFile[]; performance?: MessagePerformance; stages?: AgentStage[]; modelUsage?: ModelUsage }>
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
  /** 当前会话模式：qa=问答、agent=智能体、auto=自动分流 */
  chatMode: 'qa' | 'agent' | 'auto'
  /** 本次回复实际使用的引擎回显 */
  activeEngine: { display_name: string; auth_tier: string; auto_selected: boolean } | null
  /** 会话级模型选择器（REQ-EXPERT-MODE §2.3）：'' = 跟随详情 */
  sessionModel: string
  /** 模型候选（预设 + 本机探测，每项标注来源） */
  modelOptions: Array<{ value: string; source: 'local' | 'trial' | 'byok' }>
  /** 详情层 LLM 当前生效模型（跟随标签插值） */
  detailModelLabel: string
  /** CLI 引擎探针前置回显（§2.2 AC-4：失败段定位） */
  cliProbe: ChatEngineProbe | null
  /** 智能体模式是否可选（探针不通则置灰 + 指引） */
  agentAvailable: boolean
  /** 智能体引擎展示名（如 Qoder CLI） */
  agentEngineName: string
  /** 当前 chat_engine.model（'' = 引擎默认） */
  agentEngineModel: string
  /** CLI 引擎可用模型清单（--list-models） */
  agentModels: string[]
  /** 模型清单获取结果原因（ok/not_logged_in/unsupported/...） */
  agentModelsReason: string
  /** 模型清单加载中 */
  agentModelsLoading: boolean
}>()

const emit = defineEmits<{
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
  (e: 'update:chatMode', val: 'qa' | 'agent' | 'auto'): void
  (e: 'update:sessionModel', val: string): void
  (e: 'update:agentModel', val: string): void
}>()

const inputRef = ref<HTMLTextAreaElement | null>(null)
const feedRef = ref<HTMLElement | null>(null)

// ─── Composer 触发器菜单（原型 ai-panel-composer-prototype）：usePopMenu 统一开合/定位/隐式收起 ───
const router = useRouter()
const modeTriggerEl = ref<HTMLElement | null>(null)
const modeMenuEl = ref<HTMLElement | null>(null)
const modelTriggerEl = ref<HTMLElement | null>(null)
const modelMenuEl = ref<HTMLElement | null>(null)
const { visible: modeMenuVisible, toggle: toggleModeMenu, close: closeModeMenu, triggerAttrs: modeTriggerAttrs, menuAttrs: modeMenuAttrs } = usePopMenu(modeMenuEl, modeTriggerEl, { align: 'start' })
const { visible: modelMenuVisible, toggle: toggleModelMenu, close: closeModelMenu, triggerAttrs: modelTriggerAttrs, menuAttrs: modelMenuAttrs } = usePopMenu(modelMenuEl, modelTriggerEl, { align: 'start' })

type ModelSource = 'local' | 'trial' | 'byok'
/** 资源候选按来源分组（本机 CLI → 体验配额 → 自带 Key），组间横线分隔 */
const MODEL_GROUP_ORDER: ModelSource[] = ['local', 'trial', 'byok']
const modelGroups = computed(() => MODEL_GROUP_ORDER
  .map(source => ({ source, opts: props.modelOptions.filter(o => o.source === source) }))
  .filter(g => g.opts.length > 0))
/** 会话级选中项的来源（同值跨源时跟随候选表；未命中则保留菜单上次选择） */
const menuModelSource = computed<ModelSource | ''>(() =>
  (menuModelOverride.value && menuModelOverride.value.value === props.sessionModel
    ? menuModelOverride.value.source
    : props.modelOptions.find(o => o.value === props.sessionModel)?.source) ?? '')

function sourceLabel(source: ModelSource | ''): string {
  return source ? srcLabel(source) : ''
}

function onPickMode(m: 'qa' | 'agent' | 'auto') {
  closeModeMenu()
  if (m !== props.chatMode) emit('update:chatMode', m)
}
function onPickModel(value: string, source: ModelSource | '') {
  closeModelMenu()
  emit('update:sessionModel', value)
  // 同值跨源无法由候选表定位时，跟随菜单选择临时标记
  if (value && source && props.modelOptions.find(o => o.value === value)?.source !== source) {
    menuModelOverride.value = { value, source }
  } else {
    menuModelOverride.value = null
  }
}
/** 菜单内显式选择的 (value, source)，会话级状态只存 value，跨源同名模型时需额外记源 */
const menuModelOverride = ref<{ value: string; source: ModelSource } | null>(null)
function onGotoComputeSettings() {
  closeModelMenu()
  void router.push({ name: 'settings', query: { cat: 'ai' } })
}
/** 智能体模式：模型位切换为 CLI 引擎模型语义（写 chat_engine.model） */
const isAgentMode = computed(() => props.chatMode === 'agent')
function onPickAgentModel(v: string) {
  closeModelMenu()
  if (v !== props.agentEngineModel) emit('update:agentModel', v)
}
function onGotoCliSettings() {
  closeModelMenu()
  void router.push({ name: 'settings', query: { cat: 'ai' } })
}
/** 发送/停止合一（原型 composer：加载态下同一按钮切换为停止） */
function onSendOrStop() {
  if (props.isLoading) emit('stopGeneration')
  else emit('send')
}

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

// ─── 使用面闭环辅助（REQ-EXPERT-MODE §2.3）：来源/计费标签 + 探针指引文案 ───
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
const probeHintText = computed(() => {
  const p = props.cliProbe
  if (!p) return ''
  if (p.failed_stage === 'version' || p.reason === 'version_low') return t('ai-panel.cli_probe_version_low')
  if (p.failed_stage === 'login' || p.reason === 'not_logged_in') return t('ai-panel.cli_probe_not_logged_in')
  return t('ai-panel.cli_probe_not_installed')
})


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
  color: var(--warn);
  background: var(--warn-soft);
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
  background: var(--surface-2);
  color: var(--fg);
}
.ai-meta-icon-btn.is-active {
  background: var(--accent-soft);
  color: var(--accent);
}
.ai-meta-icon-btn svg {
  width: 14px;
  height: 14px;
}
/* ── 详情面板 / Detail panel ── */
.ai-meta-detail {
  margin-top: 4px;
  padding: 6px 8px;
  background: var(--surface-2);
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
  background: var(--surface-2);
  border-radius: 8px;
  border: 1px solid var(--border, #e5e7eb);
}
.ai-stage-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
}
.ai-stage-item.is-done {
  color: var(--subtle);
}
.ai-stage-item.is-error {
  color: var(--error);
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
/* ── 已验证变更卡片 / Verified changes ──
   原先定义在 AIPanel.vue 的 <style scoped> 中，但标记在本子组件内，
   scoped 选择器无法命中 → 该卡片此前完全无样式。迁移至实际拥有者。
   Previously declared in the parent's scoped block while the markup lives here,
   so the selectors never matched and the card rendered unstyled. */
.verified-changes-block {
  margin-top: var(--s-3);
  padding: var(--s-3);
  background: var(--surface-2);
  border-radius: var(--radius);
  border: 1px solid var(--border);
}
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

/* ── Composer 栏（原型 ai-panel-composer-prototype）── */
.composer-bar {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  flex-wrap: wrap;
  padding-top: 2px;
}
.cb-trigger-wrap { position: relative; min-width: 0; }
.ac-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 190px;
  height: 34px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 6px);
  background: var(--surface-2);
  color: var(--fg);
  cursor: pointer;
  transition: background 0.14s ease, border-color 0.14s ease;
}
.ac-trigger:hover { background: var(--surface-3); border-color: var(--border-strong); }
.ac-trigger.is-open { background: var(--surface-3); border-color: var(--fg); }
.ac-tr-icon {
  width: 14px; height: 14px; flex: 0 0 auto;
  color: var(--muted); fill: none; stroke: currentColor;
  stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round;
}
.ac-trigger.is-open .ac-tr-icon { color: var(--fg); }
.ac-tr-txt { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.25; min-width: 0; }
.ac-tr-name { font-size: var(--fs-12, 12px); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 124px; }
.ac-tr-sub { font-family: var(--font-mono); font-size: var(--fs-11, 11px); color: var(--muted); white-space: nowrap; }
.ac-chev {
  width: 12px; height: 12px; flex: 0 0 auto;
  color: var(--subtle); fill: none; stroke: currentColor;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
  transition: transform 0.14s ease;
}
.ac-trigger.is-open .ac-chev { transform: rotate(180deg); }

/* ── 触发器弹出菜单：usePopMenu fixed 定位，z-index 取全局阶梯 ── */
.ac-menu {
  position: fixed;
  top: 0; left: 0;
  z-index: var(--z-popover, 500);
  max-height: 420px;
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg, 12px);
  box-shadow: 0 10px 28px oklch(18% 0.012 250 / 0.14), 0 2px 6px oklch(18% 0.012 250 / 0.06);
  padding: 6px;
}
.ac-group + .ac-group { border-top: 1px solid var(--border); margin-top: 6px; padding-top: 6px; }
.ac-label {
  display: flex; align-items: center; justify-content: space-between; gap: var(--s-2);
  padding: 6px 8px 4px;
  font-family: var(--font-mono); font-size: var(--fs-11, 11px);
  letter-spacing: 0.06em; color: var(--subtle);
}
.ac-row {
  display: grid;
  grid-template-columns: 26px 1fr auto;
  align-items: center;
  gap: var(--s-2);
  width: 100%;
  text-align: left;
  min-height: 40px;
  padding: 6px 8px;
  border: none;
  border-radius: var(--radius-sm, 6px);
  background: transparent;
  color: var(--fg);
  font: inherit;
  cursor: pointer;
  transition: background 0.12s ease;
}
.ac-row:hover { background: var(--surface-3); }
.ac-row.is-sel { background: var(--accent-soft); }
.ac-row.is-sel:hover { background: var(--accent-soft); filter: brightness(0.97); }
.ac-badge {
  width: 26px; height: 26px;
  display: grid; place-items:center;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 6px);
  background: var(--surface-2);
  font-family: var(--font-mono); font-size: var(--fs-11, 11px); font-weight: 600;
  color: var(--muted);
}
.ac-row.is-sel .ac-badge { background: var(--surface); border-color: var(--border-strong); color: var(--fg); }
.ac-it { min-width: 0; }
.ac-it-name { display: block; font-size: var(--fs-13, 13px); font-weight: 600; line-height: 1.35; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ac-it-sub { display: block; font-family: var(--font-mono); font-size: var(--fs-11, 11px); color: var(--muted); margin-top: 1px; line-height: 1.4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ac-right { display: flex; align-items: center; gap: 6px; justify-self: end; }
.ac-check { width: 14px; height: 14px; color: var(--accent); flex: 0 0 auto; }
.ac-pill {
  display: inline-flex; align-items: center;
  font-family: var(--font-mono); font-size: var(--fs-11, 11px);
  border-radius: 5px; padding: 2px 6px;
  border: 1px solid var(--border-strong);
  color: var(--muted); background: var(--surface-2); white-space: nowrap;
}
.ac-foot {
  display: flex; align-items: center; justify-content: space-between; gap: var(--s-2);
  width: calc(100% - 12px); margin: 0 6px;
  padding: 9px 8px;
  border: none; border-top: 1px solid var(--border); border-radius: 0;
  background: transparent; color: var(--muted);
  font: inherit; font-size: var(--fs-12, 12px);
  cursor: pointer; transition: all 0.12s;
}
.ac-foot:hover { color: var(--fg); }
.ac-empty {
  padding: 10px 8px;
  font-size: var(--fs-11, 11px);
  color: var(--muted, #888);
  line-height: 1.5;
}

.cb-right { margin-left: auto; display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; }
.cb-hint { font-family: var(--font-mono); font-size: var(--fs-11, 11px); color: var(--subtle); white-space: nowrap; }

/* ── Composer 输入区（无边框 textarea + 右对齐发送/停止）── */
.composer-input {
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-size: var(--fs-13, 13px);
  line-height: 1.6;
  resize: none;
  outline: none;
  min-height: 32px;
  max-height: 150px;
  padding: 4px 0;
}
.composer-input::placeholder { color: var(--subtle); }
.composer-send-row { display: none; }
.composer-send {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid transparent;
  background: var(--fg);
  color: var(--surface);
  font-size: var(--fs-12, 12px);
  font-weight: 600;
  cursor: pointer;
  transition: background 0.14s ease, opacity 0.12s ease, transform 0.05s ease;
}
.composer-send:hover { opacity: 0.85; }
.composer-send:active { transform: translateY(1px); }
.composer-send:disabled { background: var(--surface-3); color: var(--subtle); cursor: not-allowed; transform: none; opacity: 1; }
.composer-send.is-stop { background: var(--surface); color: var(--fg); border-color: var(--border-strong); }
.composer-send.is-stop:hover { background: var(--surface-2); }
.composer-send svg { width: 13px; height: 13px; flex: 0 0 auto; }

/* ── 回复尾部消费方/计费回显（≥12px，裁决-5） ── */
.ai-usage-echo {
  font-size: 12px;
  color: var(--muted, #888);
  margin: 2px 0 0;
  padding: 1px 8px;
  border-left: 2px solid var(--border, #ddd);
}
/* ── CLI 探针前置警告（amber 不用红；置灰前先告知）── */
.ai-cli-probe-warn {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 2px 0 4px;
  padding: 6px 10px;
  border-radius: var(--radius-sm, 6px);
  font-size: 12px;
  line-height: 1.5;
  color: var(--warn, #8a5800);
  background: var(--warn-soft, #fdf3df);
  border: 1px solid var(--warn-border, rgba(138,88,0,0.25));
}
.ai-cli-probe-warn svg { width: 13px; height: 13px; flex: 0 0 auto; margin-top: 2px; }
.ai-cli-probe-warn .cpw-switch {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 2px;
  margin-left: 6px;
  white-space: nowrap;
  cursor: pointer;
}
</style>
