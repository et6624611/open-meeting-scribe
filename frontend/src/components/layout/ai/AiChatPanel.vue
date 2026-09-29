<template>
  <!-- 对话消息流 / Chat message feed -->
  <div class="ai-feed" ref="feedRef">
    <div v-for="(msg, i) in messages" :key="i" class="ai-msg" :class="{ 'is-user': msg.role === 'user' }">
      <!-- 占位气泡：assistant 消息在首个 token 前 content 为空，此时不渲染，避免 .ai-bubble 的 padding/border 撑出空白条 -->
      <div v-if="msg.content" class="ai-bubble" v-html="fmt(msg.content)"></div>
      <!-- 回复尾部消费方/计费回显（REQ-EXPERT-MODE §2.3：与 routing 实际判定一致） -->
      <div v-if="msg.role === 'assistant' && msg.modelUsage" class="ai-usage-echo">
        {{ t('ai-panel.usage_echo', { model: msg.modelUsage.model, src: srcLabel(msg.modelUsage.source), billing: billingLabel(msg.modelUsage.billing) }) }}<span v-if="msg.modelUsage.auto_switched">{{ t('ai-panel.usage_echo_auto_switched') }}</span>
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
      <!-- 纪要提案式 diff（propose_summary，未落盘） / Summary proposal diff (accept to persist) -->
      <div v-if="summaryProposal && i === messages.length - 1 && msg.role === 'assistant'" class="sum-prop-view">
        <div class="diff-header"><span>{{ t('ai-panel.summary_proposal_label') }}</span></div>
        <div class="sum-prop-body">
          <template v-for="(line, li) in summaryProposalDiff" :key="li">
            <div v-if="line.type !== 'same'" class="sum-prop-line" :class="line.type === 'add' ? 'is-add' : 'is-del'">{{ line.text || '\u00A0' }}</div>
          </template>
        </div>
        <p class="sum-prop-hint">{{ t('ai-panel.summary_proposal_hint') }}</p>
        <div class="diff-actions">
          <IconButton class="diff-accept-btn" :label="t('ai-panel.summary_proposal_accept')" show-label @click="$emit('acceptSummary')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
          </IconButton>
          <button class="diff-reject-btn" @click="$emit('rejectSummary')">{{ t('ai-panel.summary_proposal_reject') }}</button>
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

    <!-- 完成护栏横幅（模式即权限 §5.4）：改写意图轮零写回 → 显式告知，不让用户对着旧版本猜 -->
    <div v-if="rewriteNotPersisted" class="guard-notice" role="alert">
      <span class="guard-text">{{ t('ai-panel.chat_not_persisted') }}</span>
      <button class="guard-retry" @click="$emit('retryWrite', rewriteNotPersisted.text)">{{ t('ai-panel.chat_not_persisted_retry') }}</button>
      <button class="guard-dismiss" @click="$emit('dismissNotPersisted')">{{ t('ai-panel.chat_not_persisted_dismiss') }}</button>
    </div>
  </div>

  <!-- 输入区 / Input zone -->
  <div class="ai-input-zone">
    <!-- 跟进建议提示板已下架（2026-09）：不再在输入区展示建议 chips，sendRaw 入口由引用提问等路径保留 -->
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
    <!-- 输入卡片：textarea + composer 栏整体包边框，跟随焦点高亮（提示板下架后恢复输入区边界感） -->
    <div class="composer-card">
      <!-- 输入框（无边框 textarea 居上）：高度 = 行数 × 整数行盒，超过上限转区内滚动（Composer 尺寸契约）。
           快捷键提示 ⏎/⇧⏎ 已并入占位文案，不再单独展示 -->
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
      <!-- Composer 栏（原型 ai-panel-composer-prototype）：模式触发器 + 资源触发器（左）+ 发送/停止（右），同一栏 -->
      <div class="composer-bar" ref="barRef" :class="{ 'is-compact': compact }">
      <!-- 对话模式触发器（会话级，与“角色”正交）：图标化展示，图标形状随模式变化；无障碍由 aria-label（模式通用名）+ data-tip（当前模式名）承载，多语言 key 不变 -->
      <div class="cb-trigger-wrap">
        <button ref="modeTriggerEl" class="ac-trigger is-icon" :class="{ 'is-open': modeMenuVisible }" v-bind="modeTriggerAttrs" :aria-label="t('ai-panel.mode_label')" :data-tip="t('ai-panel.mode_' + chatMode)" @click="toggleModeMenu">
          <!-- 图标随当前模式换形状（自动=星芒/问答=问号/智能体=终端），与菜单行徽标为同一套图标 -->
          <svg class="ac-tr-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" v-html="modeIconBody"></svg>
        </button>
        <div ref="modeMenuEl" v-show="modeMenuVisible" class="ac-menu" style="width: 288px;" v-bind="modeMenuAttrs">
          <div class="ac-group">
            <div class="ac-label"><span>{{ t('ai-panel.mode_label') }}</span><span>{{ MODE_LIST.length }}</span></div>
            <button v-for="m in MODE_LIST" :key="m" class="ac-row" role="menuitem" :class="{ 'is-sel': chatMode === m }" :aria-label="t('ai-panel.mode_' + m)" @click="onPickMode(m)">
              <!-- 行徽标与外部触发器图标一一对应（同一套 lucide 图标），保证内外符号一致 -->
              <span class="ac-badge"><svg class="ac-badge-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="MODE_ICONS[m].body"></svg></span>
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
        <button ref="modelTriggerEl" class="ac-trigger ai-model-select" :class="{ 'is-open': modelMenuVisible }" v-bind="modelTriggerAttrs" :aria-label="isAgentMode ? t('ai-panel.model_cli_engine_label') : t('ai-panel.model_label')" :title="isAgentMode ? (agentEngineModel || t('ai-panel.model_cli_engine_default')) : (sessionModel || detailModelLabel)" @click="toggleModelMenu">
          <svg class="ac-tr-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 3v3M14 3v3M10 18v3M14 18v3M3 10h3M3 14h3M18 10h3M18 14h3"/></svg>
          <span class="ac-tr-txt">
            <span class="ac-tr-name">{{ isAgentMode ? (agentEngineModel || t('ai-panel.model_cli_engine_default')) : (sessionModel || `${t('ai-panel.model_builtin_default')} · ${detailModelLabel}`) }}</span>
            <span class="ac-tr-sub">{{ isAgentMode ? (agentEngineName || 'CLI') : (sessionModel ? sourceLabel(menuModelSource) : t('ai-panel.model_builtin_default')) }}</span>
          </span>
          <svg class="ac-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
        </button>
        <div ref="modelMenuEl" v-show="modelMenuVisible" class="ac-menu" style="width: 322px;" v-bind="modelMenuAttrs">
          <!-- ══ 统一资源清单（AI 算力入口治理 §2）：全集恒定呈现，模式只切换可选性 ══ -->
          <!-- ── 内置 LLM 组：智能体模式下整组置灰 ── -->
          <div class="ac-group" :class="{ 'is-group-disabled': isAgentMode }">
            <div class="ac-label"><span>{{ t('ai-panel.model_group_builtin') }}</span><span>{{ modelOptions.length + 1 }}</span></div>
            <div v-if="isAgentMode" class="ac-hint">{{ t('ai-panel.model_hint_unavailable_builtin') }}</div>
            <!-- 内置默认：全部对话默认算力 + 面板外函数类操作（原「跟随详情」） -->
            <button class="ac-row" role="menuitem" :class="{ 'is-disabled': isAgentMode, 'is-sel': !isAgentMode && !sessionModel }" :aria-label="t('ai-panel.model_builtin_default')" @click="onPickModel('', '')">
              <span class="ac-badge">⇄</span>
              <span class="ac-it"><span class="ac-it-name">{{ t('ai-panel.model_builtin_default') }}</span><span class="ac-it-sub">{{ t('ai-panel.model_builtin_default_hint', { model: detailModelLabel }) }}</span></span>
              <span class="ac-right">
                <svg v-if="!isAgentMode && !sessionModel" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
                <span v-else-if="isAgentMode && !sessionModel" class="ac-pill">{{ t('ai-panel.badge_current') }}</span>
              </span>
            </button>
            <div class="ac-note">{{ t('ai-panel.model_scope_note') }}</div>
          </div>
          <!-- 会话级 LLM 候选（按来源分组） -->
          <div v-for="g in modelGroups" :key="g.source" class="ac-group" :class="{ 'is-group-disabled': isAgentMode }">
            <div class="ac-label"><span>{{ srcLabel(g.source) }}</span><span>{{ g.opts.length }}</span></div>
            <button v-for="opt in g.opts" :key="opt.value" class="ac-row" role="menuitem" :class="{ 'is-disabled': isAgentMode, 'is-sel': !isAgentMode && sessionModel === opt.value && menuModelSource === g.source }" :aria-label="opt.value + ' · ' + srcLabel(g.source)" @click="onPickModel(opt.value, g.source)">
              <span class="ac-badge">{{ srcLabel(g.source).slice(0, 1) }}</span>
              <span class="ac-it">
                <span class="ac-it-name">{{ opt.value }}</span>
                <span class="ac-it-sub">{{ g.source === 'local' ? t('ai-panel.model_local_endpoint') : t('ai-panel.model_configured') }}</span>
              </span>
              <span class="ac-right">
                <svg v-if="!isAgentMode && sessionModel === opt.value && menuModelSource === g.source" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
                <span v-else-if="isAgentMode && sessionModel === opt.value" class="ac-pill">{{ t('ai-panel.badge_current') }}</span>
              </span>
            </button>
          </div>
          <!-- ── CLI 引擎组：问答模式下整组置灰（常驻呈现，探测仍懒加载） ── -->
          <div class="ac-group" :class="{ 'is-group-disabled': !isAgentMode }">
            <div class="ac-label"><span>{{ agentEngineName || 'CLI' }}</span><span>{{ agentModels.length }}</span></div>
            <div v-if="!isAgentMode" class="ac-hint">{{ t('ai-panel.model_hint_cli_disabled') }}</div>
            <button class="ac-row" role="menuitem" :class="{ 'is-disabled': !isAgentMode, 'is-sel': isAgentMode && !agentEngineModel }" :aria-label="t('ai-panel.model_cli_engine_default')" @click="onPickAgentModel('')">
              <span class="ac-badge">⇄</span>
              <span class="ac-it"><span class="ac-it-name">{{ t('ai-panel.model_cli_engine_default') }}</span><span class="ac-it-sub">{{ t('ai-panel.model_cli_engine_default_hint') }}</span></span>
              <span class="ac-right">
                <svg v-if="isAgentMode && !agentEngineModel" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
                <span v-else-if="!isAgentMode && !agentEngineModel" class="ac-pill">{{ t('ai-panel.badge_default') }}</span>
              </span>
            </button>
          </div>
          <div v-if="agentModels.length" class="ac-group" :class="{ 'is-group-disabled': !isAgentMode }">
            <button v-for="m in agentModels" :key="m" class="ac-row" role="menuitem" :class="{ 'is-disabled': !isAgentMode, 'is-sel': isAgentMode && agentEngineModel === m }" :aria-label="m" @click="onPickAgentModel(m)">
              <span class="ac-badge">M</span>
              <span class="ac-it"><span class="ac-it-name">{{ m }}</span><span class="ac-it-sub">{{ t('ai-panel.model_cli_available') }}</span></span>
              <span class="ac-right">
                <svg v-if="isAgentMode && agentEngineModel === m" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
                <span v-else-if="!isAgentMode && agentEngineModel === m" class="ac-pill">{{ t('ai-panel.badge_current') }}</span>
              </span>
            </button>
          </div>
          <div v-else class="ac-empty">{{ cliGroupEmptyText }}</div>
          <button class="ac-foot" role="menuitem" :aria-label="t('ai-panel.model_cli_goto')" @click="onGotoCliSettings">
            <span>{{ t('ai-panel.model_cli_goto') }}</span>
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg>
          </button>
          <!-- 统一底部入口（原两侧各自的 footer 合并） -->
          <button class="ac-foot" role="menuitem" :aria-label="t('ai-panel.model_manage_all')" @click="onGotoComputeSettings">
            <span>{{ t('ai-panel.model_manage_all') }}</span>
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg>
          </button>
        </div>
      </div>

      <div class="cb-right">
        <!-- 发送 / 停止（合一按钮，图标化展示，文字文案由 title/aria-label（多语言 key 不变）承载，与触发器同栏，原型 composer） / Send / Stop -->
        <button class="composer-send is-icon" :class="{ 'is-stop': isLoading }" :disabled="!isLoading && !inputText.trim()" :aria-label="isLoading ? t('ai-panel.stop_generating') : t('ai-panel.send')" :title="isLoading ? t('ai-panel.stop_generating') : t('ai-panel.send')" @click="onSendOrStop">
          <svg v-if="isLoading" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
        </button>
      </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { LlmMetadata, MessagePerformance, SourceFile, AgentStage, ModelUsage } from '@/api/chat'
import type { ChatEngineProbe } from '@/api/settings'
import { useI18n } from 'vue-i18n'
import IconButton from '@/components/common/IconButton.vue'
import { escapeHtml } from '@/utils/sanitize'
import { lucideIcon, type IconDef } from '@/utils/lucideIcons'
import { diffLines, type DiffLine } from '@/utils/textDiff'
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
  quoteText: string
  quoteSource: string
  cmdOpen: boolean
  cmdIndex: number
  filteredCmds: AiCommand[]
  inputText: string
  formatChange: (change: any) => string
  /** 当前会话模式：qa=问答、agent=智能体（auto 规则分流已退役，AI 算力入口治理 §1） */
  chatMode: 'qa' | 'agent'
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
  /** 完成护栏（§5.4）：改写意图轮零写回时的横幅态 */
  rewriteNotPersisted: { text: string } | null
  /** 纪要提案式 diff（提案式，未落盘）：baseline=当前纪要，proposed=AI 建议全文 */
  summaryProposal: { baseline: string; proposed: string } | null
}>()

const emit = defineEmits<{
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
  (e: 'clearQuote'): void
  (e: 'runCommand', cmd: AiCommand): void
  (e: 'inputKey', ev: KeyboardEvent): void
  (e: 'inputChange'): void
  (e: 'update:inputText', val: string): void
  (e: 'update:chatMode', val: 'qa' | 'agent'): void
  (e: 'update:sessionModel', val: string): void
  (e: 'update:agentModel', val: string): void
}>()

const inputRef = ref<HTMLTextAreaElement | null>(null)
const feedRef = ref<HTMLElement | null>(null)
const barRef = ref<HTMLElement | null>(null)

/** 纪要提案的行级 diff（供 diff 卡渲染）；无提案时空数组 */
const summaryProposalDiff = computed<DiffLine[]>(() => {
  const p = props.summaryProposal
  if (!p) return []
  return diffLines(p.baseline, p.proposed)
})

// ─── Composer 尺寸契约（2026-09-29）：输入区高度与控制行高度解耦，两个高度由同一组 CSS 变量推导 ───
// 行盒必须取整数（--composer-line: 20px）。原先 line-height:1.6 = 20.8px，任何高度都落在半行上，
// 末行必然被切成半行；且高度同时被 min-height:32px / max-height:150px / JS 的 120 三处决定，
// 任一非键入路径（会话恢复 / 插入引用 / 指令回填 / 图表预填）改值后不重算，就停在一行的高度上。
/** 从 :root 读尺寸变量：CSS 与 JS 共用同一事实来源，改一处即可整栏升降 */
function composerVar(name: string, fallback: number): number {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name))
  return Number.isFinite(v) && v > 0 ? v : fallback
}
/** 溢出渐隐状态：下方还有内容 → 底边渐隐；已滚动过 → 顶边渐隐。遮罩只作用于输入框内部，不进入控制行 */
const moreBelow = ref(false)
const moreAbove = ref(false)
function syncOverflow(ta: HTMLTextAreaElement) {
  moreBelow.value = ta.scrollHeight - ta.clientHeight - ta.scrollTop > 1
  moreAbove.value = ta.scrollTop > 1
}
function onComposerScroll(e: Event) { syncOverflow(e.target as HTMLTextAreaElement) }

/** 输入区高度重算（唯一入口）：高度 = 行数 × 行盒；超出上限由 CSS max-height 接管并转区内滚动。
    挂在值变化 + 控制行宽度变化上，覆盖所有写入路径，不再只依赖 input 事件。 */
function resizeInput() {
  const ta = inputRef.value
  if (!ta) return
  ta.style.height = 'auto'
  // 面板折叠（display:none）时测得 0，跳过以免把高度写成 0；展开后由 ResizeObserver 重新触发
  if (ta.scrollHeight === 0) return
  const line = composerVar('--composer-line', 20)
  ta.style.height = Math.round(ta.scrollHeight / line) * line + 'px'
  syncOverflow(ta)
}

/** 窄档：控制行可用宽度不足时，模型触发器降级为纯图标。
    收缩顺序固定为 ① 触发器文字省略 → ② 触发器降级为纯图标 → ③ 发送键永不收缩、永不换行。 */
const compact = ref(false)
function syncDensity() {
  const bar = barRef.value
  if (!bar) return
  compact.value = bar.clientWidth > 0 && bar.clientWidth < composerVar('--composer-compact-below', 288)
}

// 值变化即重算：会话恢复 / 插入引用 / 指令回填 / 洞察台图表预填等都不经过 input 事件
watch(() => props.inputText, () => { void nextTick(resizeInput) })
// 触发器标签随模式与模型变化，长度变了就重新判定窄档
watch(
  () => [props.chatMode, props.sessionModel, props.agentEngineModel, props.agentEngineName],
  () => { void nextTick(syncDensity) },
)

let composerRo: ResizeObserver | null = null
/** 剪贴板反馈定时器：非键入路径，卸载时清理 */
let copiedTimer: ReturnType<typeof setTimeout> | null = null
onMounted(() => {
  resizeInput()
  syncDensity()
  // 只观察控制行：其高度恒为 --composer-bar-h，不会因输入区高度回写而被循环触发
  if (typeof ResizeObserver !== 'undefined' && barRef.value) {
    composerRo = new ResizeObserver(() => { resizeInput(); syncDensity() })
    composerRo.observe(barRef.value)
  }
})
onBeforeUnmount(() => { composerRo?.disconnect(); composerRo = null; if (copiedTimer) clearTimeout(copiedTimer) })

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

function onPickMode(m: 'qa' | 'agent') {
  closeModeMenu()
  if (m !== props.chatMode) emit('update:chatMode', m)
}
function onPickModel(value: string, source: ModelSource | '') {
  // 智能体模式下内置组整组置灰，点击 no-op（不自动切模式，避免隐式改变执行引擎）
  if (isAgentMode.value) return
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
/** CLI 组空态文案：问答模式未探测时明示懒加载时机，智能体模式下区分加载/未登录/不可用 */
const cliGroupEmptyText = computed(() => {
  if (props.agentModelsLoading) return t('ai-panel.model_cli_loading')
  if (!isAgentMode.value) return t('ai-panel.model_cli_not_probed')
  return props.agentModelsReason === 'not_logged_in' ? t('ai-panel.model_cli_need_login') : t('ai-panel.model_cli_unavailable')
})
function onPickAgentModel(v: string) {
  // 问答模式下 CLI 组整组置灰，点击 no-op
  if (!isAgentMode.value) return
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

/** 对话模式清单（两态）：模式菜单渲染与徒标/计数单一来源 */
const MODE_LIST = ['qa', 'agent'] as const

/** 对话模式图标：外部触发器与菜单行徽标共用同一套 lucide 图标，保证内外一致 */
const MODE_ICONS: Record<'qa' | 'agent', IconDef> = {
  qa: lucideIcon('help-circle')!,
  agent: lucideIcon('terminal')!,
}
const modeIconBody = computed(() => MODE_ICONS[props.chatMode].body)

/** 每条消息展开的详情面板类型 / Expanded detail panel type per message index */
const detailOpen = ref<Record<number, string | null>>({})

/** 刚复制过的消息下标：图标短暂切换为对钩作反馈（剪贴板不可用时静默降级） */
const copiedIdx = ref<number | null>(null)
async function onCopyReply(content: string, idx: number) {
  try {
    await navigator.clipboard.writeText(content)
  } catch {
    console.warn('[AiChatPanel] Clipboard copy failed')
    return
  }
  copiedIdx.value = idx
  if (copiedTimer) clearTimeout(copiedTimer)
  copiedTimer = setTimeout(() => { copiedIdx.value = null; copiedTimer = null }, 1500)
}

defineExpose({ inputRef, feedRef, resizeInput })

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

/** Tokens 行格式化：usage 可能整体或部分缺失（byok 回显链路），缺位用 — 占位 */
function fmtTokens(meta: LlmMetadata): string {
  const u = meta.usage
  if (!u) return '—'
  return `${u.prompt_tokens ?? '—'} + ${u.completion_tokens ?? '—'} = ${u.total_tokens ?? '—'}`
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
/* ── 元数据图标行 / Metadata icon row ──
   按钮统一用 IconButton（图标按钮规范）；此处把它压缩回元数据行的 22px 密度：
   父作用域 :deep 选择器特异性高于 IconButton 自带的 .icon-btn--icon-only，能稳定覆盖 */
.ai-msg-meta {
  margin-top: 4px;
}
.ai-meta-icons {
  display: flex;
  gap: 2px;
}
.ai-meta-icons :deep(.icon-btn) {
  width: 22px;
  height: 22px;
  border-radius: 4px;
  color: var(--muted, #999);
}
.ai-meta-icons :deep(.icon-btn__icon svg) {
  width: 14px;
  height: 14px;
}
.ai-meta-icons :deep(.icon-btn--active) {
  background: var(--accent-soft);
  color: var(--accent);
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
/* 详情面板空态：图标常驻，数据缺失时展开可见原因，不留白屏 */
.ai-meta-empty {
  font-style: italic;
  color: var(--subtle, #aaa);
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

/* ── 输入卡片：textarea + composer 栏整体的可见边框（提示板下架后恢复输入区边界感）──
   卡片不再用 gap 串起两者：文本区与控制行的间距改由 .composer-bar 的 margin-top 承担，
   保证任何状态下末行文字与按钮之间都有 --composer-gap 的硬间距。 */
.composer-card {
  display: flex;
  flex-direction: column;
  padding: var(--s-2) var(--s-3);
  border: 1px solid var(--border);
  border-radius: var(--radius, 10px);
  background: var(--surface);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.composer-card:focus-within { border-color: var(--accent); box-shadow: var(--shadow-focus); }

/* ── Composer 栏（原型 ai-panel-composer-prototype）──
   高度恒定 --composer-bar-h、恒为单行：折行会把栏高从 34px 变成两行，反向挤压文本区。
   原先的 flex-wrap:wrap 与「保证单行不换行」的注释本就冲突，且被 .cb-trigger-wrap 的
   min-width:0 短路成死代码——真正的失效是触发器不收缩、直接溢出压到发送键上。 */
.composer-bar {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  flex: 0 0 auto;
  flex-wrap: nowrap;
  height: var(--composer-bar-h);
  min-height: var(--composer-bar-h);
  margin-top: var(--composer-gap);
}
/* 收缩链：外层能缩、内层才跟着缩。缺了 display:flex / min-width:0 时，
   只有 wrap 会被压窄，里面的 .ac-trigger 仍按内容宽渲染并溢出到发送键上。 */
.cb-trigger-wrap { position: relative; display: flex; min-width: 0; flex: 0 1 auto; }
/* 对话模式触发器是图标态，尺寸固定，不参与收缩 */
.cb-trigger-wrap:has(.ac-trigger.is-icon) { flex: 0 0 auto; }
/* 模型触发器先让位：先文字省略，宽度仍不够时由 .is-compact 降级为纯图标 */
.cb-trigger-wrap:has(.ai-model-select) { flex-shrink: 1; }
.ac-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  /* min-width:0 让触发器能跟着外层一起收缩；max-width 用 min() 保证再窄也不溢出栏宽 */
  min-width: 0;
  max-width: min(190px, 100%);
  height: var(--composer-bar-h);
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
.ac-tr-txt { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.25; min-width: 0; overflow: hidden; }
.ac-tr-name { font-size: var(--fs-12, 12px); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 124px; }
/* 副标题与标题同样要能省略：否则它的 min-content 宽度会把整栏顶到装不下（如长引擎名 / 长模型 id） */
.ac-tr-sub { font-family: var(--font-mono); font-size: var(--fs-11, 11px); color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 124px; }
.ac-chev {
  width: 12px; height: 12px; flex: 0 0 auto;
  color: var(--subtle); fill: none; stroke: currentColor;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
  transition: transform 0.14s ease;
}
.ac-trigger.is-open .ac-chev { transform: rotate(180deg); }
/* 图标化触发器（对话模式）：仅保留图标（形状随模式变化），固定方形尺寸，不随面板宽度伸缩；
   提示文案由 aria-label / data-tip 承载，全局 tooltip 对无可见文字的按钮会显示提示 */
.ac-trigger.is-icon { flex: 0 0 auto; width: var(--composer-bar-h); max-width: var(--composer-bar-h); justify-content: center; padding: 0; }
.ac-trigger.is-icon .ac-tr-txt,
.ac-trigger.is-icon .ac-chev { display: none; }
.ac-trigger.is-icon .ac-tr-icon { width: 16px; height: 16px; }

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
.ac-badge-icon { width: 14px; height: 14px; flex-shrink: 0; }
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
/* ── 统一资源清单：非生效引擎组整组置灰（点击 no-op，提示行说明原因）── */
.ac-row.is-disabled { opacity: 0.45; cursor: not-allowed; }
.ac-row.is-disabled:hover { background: transparent; }
.ac-row.is-disabled.is-sel { background: transparent; }
.ac-hint {
  padding: 2px 8px 4px;
  font-size: var(--fs-11, 11px);
  color: var(--muted, #888);
  font-style: italic;
}
.ac-note {
  padding: 4px 8px 2px;
  font-size: var(--fs-11, 11px);
  color: var(--subtle, #aaa);
  line-height: 1.5;
}

/* 发送/停止永远最后让位：不收缩、不换行、始终贴右 */
.cb-right { margin-left: auto; display: flex; align-items: center; gap: var(--s-2); flex: 0 0 auto; flex-wrap: nowrap; }

/* ── Composer 输入区（无边框 textarea + 右对齐发送/停止）──
   高度 = 行数 × --composer-line，由 JS 写入；超过 --composer-max-lines 行由这里的
   max-height 接管并转区内滚动，末行不再被切成半行，也不会顶到控制行上。
   注意：不要再补 min-height —— 32px 不是行盒的整数倍，会让单行态又落回半行边界。 */
.composer-input {
  flex: 0 0 auto;
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-size: var(--fs-13, 13px);
  line-height: var(--composer-line);
  resize: none;
  outline: none;
  height: var(--composer-line);
  max-height: calc(var(--composer-line) * var(--composer-max-lines));
  padding: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
}
.composer-input::placeholder { color: var(--subtle); }
/* 滚动条沿用产品约定：默认隐藏，悬停才显形（base.css 的 hover 触发规则不含本元素，在此补齐） */
.composer-input:hover { scrollbar-color: oklch(0% 0 0 / 0.18) transparent; }
.composer-input:hover::-webkit-scrollbar-thumb { background: oklch(0% 0 0 / 0.18); }
/* 溢出渐隐：遮罩只作用于输入框本身，边界严格止于文本区，不进入 --composer-gap 与控制行 */
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
/* 窄档（控制行可用宽度 < --composer-compact-below）：模型触发器降级为纯图标，
   发送键位置与尺寸不变；标题与副标题改由 aria-label / title 承载 */
.composer-bar.is-compact .ai-model-select .ac-tr-txt,
.composer-bar.is-compact .ai-model-select .ac-chev { display: none; }
.composer-bar.is-compact .ai-model-select { flex: 0 0 auto; width: var(--composer-bar-h); max-width: var(--composer-bar-h); padding: 0; justify-content: center; }
/* 图标态下外层也不再参与收缩，避免把 34px 的图标挤出栏外 */
.composer-bar.is-compact .cb-trigger-wrap:has(.ai-model-select) { flex: 0 0 auto; }
.composer-send-row { display: none; }
.composer-send {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  /* 与控制行同轴：栏高 = 触发器高 = 发送键高，不再出现 34 / 32 两种高度并列 */
  height: var(--composer-bar-h);
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
/* 图标化发送/停止按钮：固定方形尺寸，文字文案由 title/aria-label 承载 */
.composer-send.is-icon { flex: 0 0 auto; width: var(--composer-bar-h); padding: 0; justify-content: center; }
.composer-send.is-icon svg { width: 15px; height: 15px; }

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
/* ── 完成护栏横幅（模式即权限 §5.4）： amber 系，与探针警告同一视觉语言 ── */
.guard-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 6px 0 4px;
  padding: 7px 10px;
  border-radius: var(--radius-sm, 6px);
  font-size: 12px;
  line-height: 1.5;
  color: var(--warn, #8a5800);
  background: var(--warn-soft, #fdf3df);
  border: 1px solid var(--warn-border, rgba(138,88,0,0.25));
}
.guard-notice .guard-text { flex: 1 1 auto; }
.guard-notice .guard-retry {
  border: 1px solid var(--warn-border, rgba(138,88,0,0.35));
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 600;
  border-radius: var(--radius-sm, 6px);
  padding: 2px 10px;
  cursor: pointer;
}
.guard-notice .guard-retry:hover { background: var(--warn-border, rgba(138,88,0,0.12)); }
.guard-notice .guard-dismiss {
  border: none;
  background: transparent;
  color: var(--muted, #888);
  font: inherit;
  cursor: pointer;
  padding: 2px 4px;
}
/* ── 纪要提案式 diff（sum-prop，复用 diff-header/diff-actions 全局类） ── */
.sum-prop-view {
  margin-top: var(--s-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.sum-prop-body {
  max-height: 220px;
  overflow-y: auto;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.sum-prop-line { padding: 1px 4px; border-radius: 2px; }
.sum-prop-line.is-add { background: var(--diff-add, oklch(92% 0.08 155)); color: var(--diff-add-fg, oklch(30% 0.1 155)); }
.sum-prop-line.is-del { background: var(--diff-del, oklch(94% 0.06 25)); color: var(--diff-del-fg, oklch(40% 0.12 25)); text-decoration: line-through; }
.sum-prop-hint { margin: 0; padding: 4px 10px 8px; font-size: 11px; color: var(--muted); font-style: italic; }
</style>
