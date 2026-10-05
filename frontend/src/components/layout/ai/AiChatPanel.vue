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
           不让用户对着已变化的数据猜“是谁改的、能不能改回去" -->
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
        <!-- 纪要提案入口卡（propose_summary，未落盘）：完整 diff 已搬入原文面板原位预览（Layer 1），
           侧栏只留规模摘要 + 起跳入口 + 拒绝，避免两处渲染 diff 不一致 /
           Proposal entry card: full diff lives in the summary panel's in-place preview now. -->
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
        <!-- 随记提案入口卡（propose_notes，未落盘）：随记是用户原创区，AI 只能建议；
           完整 diff 在随记 Tab 原位预览，侧栏只留规模摘要 + 起跳 + 拒绝（与纪要入口卡同一形状） -->
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

      <!-- 授权档位拒绝卡：智能体工具 403 read_only 时就地呈现，拒绝不静默；
           档位会话级锁定，当前会话无法中途提权——两条路：就地预选档位，或预选后开新会话 -->
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

      <!-- 空会话提示：真·无消息且不在加载/流式中才出现，有消息立即让位（克制：仅提示词，无功能按钮） -->
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

    <!-- 左侧中部聚集点状导航：悬浮即展开全部用户消息列表，点选跳转；滚动同步当前项 -->
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
      <!-- 透明桥：填补点列与浮层间缝隙，鼠标横移不收起 -->
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
        <button v-for="(c, ci) in filteredCmds" :key="c.key" class="ai-cmd-item" :class="{ 'is-active': cmdIndex === ci }" :aria-label="t('ai-panel.' + c.descKey)" @click="$emit('runCommand', c)"><span class="cmd-key">{{ c.key }}</span><span class="cmd-label">{{ t('ai-panel.' + c.descKey) }}</span></button>
      </template>
      <div v-else-if="inputText.startsWith('/')" class="ai-cmd-empty">{{ t('ai-panel.cmd_no_match') }}</div>
    </div>
    <!-- @ 引用面板：与指令面板同构互斥（打 @ 唤起，选定插入令牌，后端展开全量上下文）。
         分组：会议内容（原文/纪要/随记）与本地文件（附件）分区展示。 -->
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
    <!-- 算力探针前置警告（§2.2 AC-4：失败段定位 + 一键改用问答） / CLI probe notice -->
    <div v-if="chatMode !== 'qa' && cliProbe && !cliProbe.available" class="ai-cli-probe-warn">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01"/><circle cx="12" cy="12" r="9"/></svg>
      <span>{{ probeHintText }}<a class="cpw-switch" href="#" @click.prevent="$emit('update:chatMode', 'qa')">{{ t('ai-panel.mode_notice_switch_qa') }}</a></span>
    </div>
    <!-- @附件 待发送 chips：图片缩略图 + 文件行，可逐个移除 -->
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
      <!-- Composer 栏：模式 + 资源（左）+ 发送/停止（右），与消息编辑态共用同一组件 -->
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { AttachmentMeta, LlmMetadata, MessagePerformance, SourceFile, AgentStage, ModelUsage, SendSnapshot } from '@/api/chat'
import { attachmentUrl } from '@/api/chat'
import type { ChatEngineProbe } from '@/api/settings'
import { useI18n } from 'vue-i18n'
import IconButton from '@/components/common/IconButton.vue'
import EmptyHint from '@/components/common/EmptyHint.vue'
import { escapeHtml } from '@/utils/sanitize'
import { lucideIcon, type IconDef } from '@/utils/lucideIcons'
import type { AiCommand } from '@/composables/useAiCommands'
import { parseMention, mentionToken } from '@/composables/useAiMentions'
import type { MentionSource } from '@/composables/useAiMentions'
import type { AuthTier } from '@/composables/useAiChat'
import { useSummaryProposal } from '@/composables/useSummaryProposal'
import { useNotesProposal } from '@/composables/useNotesProposal'
import { showToast } from '@/composables/useToast'
import { notifyTaskWritten } from '@/composables/useTaskWrites'
import { restoreTaskRewrites } from '@/api/notes'
import { extractErrorMessage } from '@/api/client'
import ComposerBar from './ComposerBar.vue'


const { t, locale } = useI18n()

/** 阶段图标：按 lucide 名取 SVG 定义（非 lucide 名返回 null 走文本降级） */
function stageIcon(stage: AgentStage): IconDef | null {
  return lucideIcon(stage.icon)
}

/** 文件体积人类可读 / Human-readable file size */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** @ 面板分组：本场会议内容 / 本地文件（顺序与 filteredMentions 一致，索引跨组连续） */
const meetingMentions = computed(() => props.filteredMentions.filter(m => m.group === 'meeting'))
const localMentions = computed(() => props.filteredMentions.filter(m => m.group === 'local'))

const props = defineProps<{
  messages: Array<{ role: string; content: string; timestamp?: string; metadata?: LlmMetadata; sources?: SourceFile[]; performance?: MessagePerformance; stages?: AgentStage[]; modelUsage?: ModelUsage; sendOptions?: SendSnapshot; attachments?: AttachmentMeta[] }>
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
  /** @ 引用面板（与指令面板同构互斥）：打 @ 唤起，选定插入令牌 */
  mentionOpen: boolean
  mentionIndex: number
  filteredMentions: MentionSource[]
  /** @附件：待发送附件 chips（发送前可移除） */
  pendingAttachments: AttachmentMeta[]
  /** 附件上传中（发送钮置灰） */
  uploadingAttachments: boolean
  inputText: string
  formatChange: (change: any) => string
  /** 当前会话模式：qa=问答、agent=智能体（auto 规则分流已退役，AI 算力入口治理 §1） */
  chatMode: 'qa' | 'agent'
  /** 本会话锁定授权档（快照，发送时透传后端） */
  sessionTier: AuthTier
  /** 待生效授权档（会中预选，新会话应用） */
  pendingTier: AuthTier
  /** 外部唤起档位菜单的信号（403 拒绝卡） */
  tierMenuSignal: number
  /** 最近一轮智能体工具的档位拦截信息（null=无拒绝） */
  tierDenial: { tool: string; summary: string } | null
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
  /** 随记提案式 diff（propose_notes，未落盘）：完整 diff 在随记 Tab 原位预览，侧栏只留入口 */
  notesProposal: { baseline: string; proposed: string } | null
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
  (e: 'openSummaryPreview'): void
  (e: 'acceptNotes'): void
  (e: 'rejectNotes'): void
  (e: 'openNotesPreview'): void
  (e: 'clearQuote'): void
  (e: 'runCommand', cmd: AiCommand): void
  (e: 'selectMention', src: MentionSource): void
  /** 移除待发送附件 */
  (e: 'removeAttachment', id: string): void
  (e: 'inputKey', ev: KeyboardEvent): void
  (e: 'inputChange'): void
  (e: 'update:inputText', val: string): void
  (e: 'update:chatMode', val: 'qa' | 'agent'): void
  (e: 'update:pendingTier', val: AuthTier): void
  /** 档位弹层脚钮：开新会话并应用待生效档 */
  (e: 'applyNewSession'): void
  /** 403 拒绝卡：就地唤起档位弹层（不改预选） */
  (e: 'raiseTier'): void
  /** 403 拒绝卡：预选「提案写入」并唤起弹层 */
  (e: 'raiseTierPreset'): void
  (e: 'update:sessionModel', val: string): void
  (e: 'update:agentModel', val: string): void
  /** 编辑再发送：截断 index（含）之后，以轮级覆盖重发，不改全局 */
  (e: 'editResend', index: number, text: string, override: { mode: 'qa' | 'agent'; model?: string; agentModel?: string }): void
}>()

const inputRef = ref<HTMLTextAreaElement | null>(null)
const feedRef = ref<HTMLElement | null>(null)

// ── 左侧点状导航：用户消息全览 + 点击跳转 + 滚动同步 ──
/** 空会话：无任何有正文的消息，且不在加载/流式等待中（空态唯一判断入口，有消息立即让位） */
const showEmpty = computed(() =>
  !props.isLoading
  && !props.isStreaming
  && !props.messages.some(m => m.content && m.content.trim().length > 0),
)
type UserEntry = { msg: { role: string; content: string; timestamp?: string }; index: number }
/** 有正文的用户消息（保留全量 index，用于映射 DOM 与跳转） */
const userEntries = computed<UserEntry[]>(() =>
  props.messages
    .map((msg, index) => ({ msg, index }))
    .filter(x => x.msg.role === 'user' && !!x.msg.content),
)
/** v-for 函数 ref 收集用户消息 DOM；重渲染时 Vue 以 null 回调旧节点，须删除失效项 */
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
/** 跳转到指定用户消息起始位置（相对滚动容器测量，避免 offsetParent 歧义） */
function jumpTo(globalIdx: number) {
  const feed = feedRef.value
  const el = userEls.get(globalIdx)
  if (!feed || !el) return
  const top = el.getBoundingClientRect().top - feed.getBoundingClientRect().top + feed.scrollTop - 12
  feed.scrollTo({ top, behavior: 'smooth' })
}
/** 当前所处用户消息：最后一个顶边越过可视区上沿的；滚到底部锚定最后一条 */
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
onMounted(() => { void nextTick(syncActive) })

/** 提案规模摘要（入口卡文案用）；diff 本体已在原文面板原位预览渲染 */
const summaryProposalSingleton = useSummaryProposal()
const summaryProposalStats = computed(() => summaryProposalSingleton.summaryProposalStats.value)
const notesProposalSingleton = useNotesProposal()
const notesProposalStats = computed(() => notesProposalSingleton.notesProposalStats.value)

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

// 值变化即重算：会话恢复 / 插入引用 / 指令回填 / 洞察台图表预填等都不经过 input 事件
watch(() => props.inputText, () => { void nextTick(resizeInput) })

/** 剪贴板反馈定时器：非键入路径，卸载时清理 */
let copiedTimer: ReturnType<typeof setTimeout> | null = null
onMounted(() => { resizeInput() })
onBeforeUnmount(() => {
  if (copiedTimer) clearTimeout(copiedTimer)
  document.removeEventListener('pointerdown', onDocPointer, true)
})

// ── 已发消息编辑再发送（截断后续 + 轮级覆盖；模式/模型菜单在 ComposerBar 内自治）──
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
  // 旧消息无快照：从紧随的 assistant 引擎标记推断模式，再缺省回落全局
  const next = props.messages[i + 1]
  const inferredMode: 'qa' | 'agent'
    = msg.sendOptions?.mode ?? (next?.metadata?.engine ? 'agent' : props.chatMode)
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

function cancelEdit() {
  editingIdx.value = null
}

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

/** 编辑态 textarea 高度重算（与底部同一行盒口径） */
function resizeEditInput() {
  const ta = editInputRef.value
  if (!ta) return
  ta.style.height = 'auto'
  if (ta.scrollHeight === 0) return
  const line = composerVar('--composer-line', 20)
  ta.style.height = Math.round(ta.scrollHeight / line) * line + 'px'
}

/** 点击编辑卡之外取消；fixed 菜单在卡片外，需排除（否则点菜即误取消） */
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

/** 每条消息展开的详情面板类型 / Expanded detail panel type per message index */
const detailOpen = ref<Record<number, string | null>>({})

/** 本轮改写事实的呈现与撤销（PROPOSAL §5.4 恢复入口） */
const REWRITE_TOOL_KEYS: Record<string, string> = {
  update_decision_node: 'ai-panel.rewrite_tool_decision_node',
  delete_decision_node: 'ai-panel.rewrite_tool_decision_node',
  inject_items: 'ai-panel.rewrite_tool_inject',
  update_summary: 'ai-panel.rewrite_tool_summary',
  revise_insight_board: 'ai-panel.rewrite_tool_board',
  revise_insight_board_section: 'ai-panel.rewrite_tool_board',
}

/** 写工具集 → 人类可读的域名称列表（同域多工具去重） */
function rewriteLabel(tools?: string[]): string {
  const names = new Set((tools || [])
    .map(x => (REWRITE_TOOL_KEYS[x] ? t(REWRITE_TOOL_KEYS[x]) : x))
    .filter(Boolean))
  return names.size ? Array.from(names).join('、') : t('ai-panel.rewrite_tool_generic')
}

const undoingTurn = ref('')
const undoneTurns = ref<Set<string>>(new Set())

/** 撤销本轮改写：整轮逆序回滚后广播重拉，本轮条目标为已撤销（不可重复点） */
async function onUndoTurn(taskId: string, turnId: string) {
  if (!taskId || !turnId || undoingTurn.value) return
  undoingTurn.value = turnId
  try {
    const res = await restoreTaskRewrites(taskId, { turnId })
    undoneTurns.value = new Set(undoneTurns.value).add(turnId)
    notifyTaskWritten({ turnId })
    showToast(t('ai-panel.chat_rewritten_undone', { n: res.restored ?? 0 }), 'success')
  } catch (e) {
    showToast(t('ai-panel.chat_rewritten_undo_failed', { reason: extractErrorMessage(e, '') }), 'error')
  } finally {
    undoingTurn.value = ''
  }
}

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

/* 编辑卡宽度：用户消息容器 align-items:flex-end 会让 flex 子项按 textarea 固有宽度收缩，
   这里强制横向拉满，保持与原气泡等宽（不因进编辑态而变窄） */
.composer-card.is-edit { align-self: stretch; width: 100%; }

/* 用户消息可编辑：指针与悬停边框给点击 affordance（编辑入口无额外按钮） */
.ai-bubble.is-editable { cursor: pointer; transition: border-color 0.14s ease; }
.ai-bubble.is-editable:hover { border-color: var(--accent); }


/* ── Composer 输入区（无边框 textarea + 右对齐发送/停止）──
   高度 = 行数 × --composer-line，由 JS 写入；超过 --composer-max-lines 行由这里的
   max-height 接管并转区内滚动，末行不再被切成半行，也不会顶到控制行上。
   默认两行：min-height 取 --composer-min-lines × 行盒 = 40px，是整数倍，安全
   （旧的 32px 不是整数倍，会把空态推回半行边界，别照搬那个值）。
   下限只写在 CSS 里，JS 的 resizeInput() 不重复表达「两行」这条规则。 */
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
  height: calc(var(--composer-line) * var(--composer-min-lines));
  min-height: calc(var(--composer-line) * var(--composer-min-lines));
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
/* 编辑态输入框：单行起高（消息通常短），高度仍由 JS 按行盒整数倍写，不沿用底部两行下限 */
.composer-input.is-edit-input {
  height: var(--composer-line);
  min-height: var(--composer-line);
}
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
/* ── 本轮改写事实（§5.4 恢复入口）：ok 绿系，与 amber 护栏横幅形成"已成事/未成事"的对偶 ── */
.rewrite-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 2px 0 4px;
  padding: 6px 10px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ok, #1c6b45);
  background: var(--ok-soft, #e7f4ec);
  border: 1px solid var(--ok-border, rgba(28, 107, 69, 0.22));
  border-radius: var(--radius-sm, 6px);
}
.rewrite-notice .rewrite-text { flex: 1 1 auto; }
.rewrite-notice .rewrite-undo {
  border: 1px solid var(--ok-border, rgba(28, 107, 69, 0.3));
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 600;
  border-radius: var(--radius-sm, 6px);
  padding: 2px 10px;
  cursor: pointer;
}
.rewrite-notice .rewrite-undo:hover:not(:disabled) { background: var(--ok-border, rgba(28, 107, 69, 0.12)); }
.rewrite-notice .rewrite-undo:disabled { opacity: 0.55; cursor: default; }
.rewrite-notice.is-undone {
  color: var(--muted, #888);
  background: transparent;
  border-color: var(--border, rgba(0, 0, 0, 0.12));
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
/* ── 纪要提案入口卡（sum-prop，复用 diff-header/diff-actions 全局类）：
   diff 本体已迁至原文面板原位预览（Layer 1），侧栏只留规模摘要与起跳 ── */
.sum-prop-view {
  margin-top: var(--s-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.sum-prop-summary {
  margin: 0;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--fg);
}

/* ── 授权档位拒绝卡（403 read_only 就地呈现，红系，与警告横幅区分） ── */
.tier-deny-card {
  margin: 6px 0 4px;
  padding: 10px 12px;
  border-radius: var(--radius-lg, 12px);
  border: 1px solid var(--err-border, #eccaca);
  background: var(--err-soft, #fbeaea);
  color: var(--err, #c23a3a);
  font-size: 12px;
  line-height: 1.5;
}
.tdc-head {
  display: flex; align-items: center; gap: 7px;
  font-weight: 600; font-size: 12.5px;
}
.tdc-head svg { width: 15px; height: 15px; flex: 0 0 auto; }
.tdc-body { display: flex; align-items: center; gap: 6px; margin-top: 7px; flex-wrap: wrap; }
.tdc-tool, .tdc-code {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 5px;
  background: var(--surface, #fff);
  border: 1px solid var(--err-border, #eccaca);
  color: var(--err, #c23a3a);
}
.tdc-hint { margin-top: 7px; color: var(--muted, #8a6a6a); }
.tdc-actions { display: flex; gap: 8px; margin-top: 9px; }
.tdc-btn {
  font: inherit; font-size: 12px; font-weight: 600;
  padding: 4px 12px;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--err-border, #eccaca);
  background: var(--surface, #fff);
  color: var(--err, #c23a3a);
  cursor: pointer;
  transition: background 0.12s ease;
}
.tdc-btn:hover { background: color-mix(in srgb, var(--err, #c23a3a) 8%, #fff); }
.tdc-btn.is-pri { background: var(--err, #c23a3a); border-color: var(--err, #c23a3a); color: #fff; }
.tdc-btn.is-pri:hover { background: color-mix(in srgb, var(--err, #c23a3a) 88%, #000); }
</style>
