<template>
  <div class="ai" :class="{ 'is-collapsed': layout.aiCollapsed }">
    <button
      class="ai-toggle"
      :title="layout.aiCollapsed ? t('ai-panel.expand') : t('ai-panel.collapse')"
      :aria-label="layout.aiCollapsed ? t('ai-panel.expand') : t('ai-panel.collapse')"
      :aria-expanded="!layout.aiCollapsed"
      @mousedown="onToggleDown($event)"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
    </button>
    <div class="ai-collapsed-strip">
      <div class="ai-collapsed-icon" :class="{ 'is-proactive': proactive.proactiveEnabled.value && proactive.unreadCount.value > 0 }" @click="layout.toggleAi()" style="position:relative">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
        <!-- 呼吸灯 + 未读角标 -->
        <span v-if="proactive.proactiveEnabled.value && proactive.unreadCount.value > 0" class="breathing-dot"></span>
        <span v-if="proactive.proactiveEnabled.value && proactive.unreadCount.value > 0" class="unread-badge">{{ proactive.unreadCount.value }}</span>
      </div>
      <span class="ai-collapsed-label">{{ t('ai-panel.collapsed_label') }}</span>
    </div>
    <div class="ai-panel-header">
      <div class="ai-panel-header-left">
        <div class="ai-header-avatar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg></div>
        <span class="ai-header-title">{{ t('ai-panel.title') }}</span>
      </div>
      <div class="ai-panel-header-right">
        <IconButton class="ai-header-btn" :label="t('ai-panel.clear')" @click="chat.clearConversation()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </IconButton>
      </div>
    </div>
    <div class="ai-panel-context">
      <span>{{ contextLabel }}</span>
    </div>
    <!-- Tab 栏 -->
    <div class="ai-panel-tabs">
      <div class="ai-panel-tabs-list">
        <button class="ai-panel-tab" :class="{ 'is-active': aiTab === 'chat' }" @click="aiTab = 'chat'">{{ t('ai-panel.tab_chat') }}</button>
        <button class="ai-panel-tab" :class="{ 'is-active': aiTab === 'analysis' }" @click="aiTab = 'analysis'">{{ t('ai-panel.tab_analysis') }}</button>
        <button class="ai-panel-tab" :class="{ 'is-active': aiTab === 'context' }" @click="aiTab = 'context'">
          {{ t('ai-panel.tab_context') }}
          <span v-if="contextResourceCount > 0" class="tab-badge">{{ contextResourceCount }}</span>
        </button>
      </div>
      <!-- 主动 AI 统一控件组（胶囊） -->
      <div
        class="ai-proactive-group"
        :class="{
          'is-off': !proactive.proactiveEnabled.value,
          'is-on': proactive.proactiveEnabled.value && !showProactiveSettings,
          'is-settings': proactive.proactiveEnabled.value && showProactiveSettings,
        }"
      >
        <button
          class="pg-toggle"
          :title="proactive.proactiveEnabled.value ? t('ai-panel.proactive.disable') : t('ai-panel.proactive.enable')"
          :aria-label="t('ai-panel.proactive.sidebar_indicator')"
          @click="proactive.toggleEnabled(); if (showProactiveSettings) showProactiveSettings = false"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
          </svg>
        </button>
        <div class="pg-divider"></div>
        <button
          class="pg-settings"
          :title="t('ai-panel.proactive.settings_title')"
          :aria-label="t('ai-panel.proactive.settings_title')"
          @click="showProactiveSettings = !showProactiveSettings"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
      </div>
    </div>
    
    <!-- 主动 AI 设置面板（从胶囊下方展开） -->
    <div
      class="ai-proactive-settings"
      :class="{ 'is-open': proactive.proactiveEnabled.value && showProactiveSettings }"
    >
      <!-- 消息类别 -->
      <div class="ai-ps-section">
        <div class="ai-ps-section-title">{{ t('ai-panel.proactive.settings_section_categories') }}</div>
        <div class="ai-ps-checkboxes">
          <label v-for="(label, key) in categoryLabels" :key="key" class="ai-ps-checkbox">
            <input type="checkbox" :checked="proactive.proactiveConfig.value.categories[key]" @change="onCategoryToggle(key, ($event.target as HTMLInputElement).checked)" />
            <span>{{ label }}</span>
          </label>
        </div>
      </div>
      <!-- 触发灵敏度 -->
      <div class="ai-ps-section">
        <div class="ai-ps-section-title">{{ t('ai-panel.proactive.settings_section_sensitivity') }}</div>
        <div class="ai-ps-sliders">
          <div class="ai-ps-slider-row">
            <span class="ai-ps-slider-label">{{ t('ai-panel.proactive.sensitivity_idle') }}</span>
            <div class="ai-ps-slider-wrap">
              <input type="range" min="5" max="60" step="5" :value="proactive.proactiveConfig.value.sensitivity.idleMinutes" @input="onSensitivityChange('idleMinutes', Number(($event.target as HTMLInputElement).value))" />
              <span class="ai-ps-slider-value">{{ proactive.proactiveConfig.value.sensitivity.idleMinutes }} {{ t('ai-panel.proactive.sensitivity_idle_unit') }}</span>
            </div>
          </div>
          <div class="ai-ps-slider-row">
            <span class="ai-ps-slider-label">{{ t('ai-panel.proactive.sensitivity_deviation') }}</span>
            <div class="ai-ps-slider-wrap">
              <input type="range" min="20" max="60" step="5" :value="proactive.proactiveConfig.value.sensitivity.deviationThreshold" @input="onSensitivityChange('deviationThreshold', Number(($event.target as HTMLInputElement).value))" />
              <span class="ai-ps-slider-value">{{ proactive.proactiveConfig.value.sensitivity.deviationThreshold }}{{ t('ai-panel.proactive.sensitivity_deviation_unit') }}</span>
            </div>
          </div>
          <div class="ai-ps-slider-row">
            <span class="ai-ps-slider-label">{{ t('ai-panel.proactive.sensitivity_cooldown') }}</span>
            <div class="ai-ps-slider-wrap">
              <input type="range" min="10" max="120" step="10" :value="proactive.proactiveConfig.value.sensitivity.cooldownMinutes" @input="onSensitivityChange('cooldownMinutes', Number(($event.target as HTMLInputElement).value))" />
              <span class="ai-ps-slider-value">{{ proactive.proactiveConfig.value.sensitivity.cooldownMinutes }} {{ t('ai-panel.proactive.sensitivity_cooldown_unit') }}</span>
            </div>
          </div>
          <div class="ai-ps-slider-row">
            <span class="ai-ps-slider-label">{{ t('ai-panel.proactive.sensitivity_session_max') }}</span>
            <div class="ai-ps-slider-wrap">
              <input type="range" min="1" max="10" step="1" :value="proactive.proactiveConfig.value.sensitivity.sessionMax" @input="onSensitivityChange('sessionMax', Number(($event.target as HTMLInputElement).value))" />
              <span class="ai-ps-slider-value">{{ proactive.proactiveConfig.value.sensitivity.sessionMax }} {{ t('ai-panel.proactive.sensitivity_session_max_unit') }}</span>
            </div>
          </div>
        </div>
      </div>
      <!-- 通知方式 -->
      <div class="ai-ps-section">
        <div class="ai-ps-section-title">{{ t('ai-panel.proactive.settings_section_notifications') }}</div>
        <div class="ai-ps-checkboxes">
          <label class="ai-ps-checkbox">
            <input type="checkbox" :checked="proactive.proactiveConfig.value.notifications.sidebarIndicator" @change="onNotifToggle('sidebarIndicator', ($event.target as HTMLInputElement).checked)" />
            <span>{{ t('ai-panel.proactive.notif_sidebar') }}</span>
          </label>
          <label class="ai-ps-checkbox">
            <input type="checkbox" :checked="proactive.proactiveConfig.value.notifications.breathing" @change="onNotifToggle('breathing', ($event.target as HTMLInputElement).checked)" />
            <span>{{ t('ai-panel.proactive.notif_breathing') }}</span>
          </label>
          <label class="ai-ps-checkbox">
            <input type="checkbox" :checked="proactive.proactiveConfig.value.notifications.banner" @change="onNotifToggle('banner', ($event.target as HTMLInputElement).checked)" />
            <span>{{ t('ai-panel.proactive.notif_banner') }}</span>
          </label>
          <label class="ai-ps-checkbox">
            <input type="checkbox" :checked="proactive.proactiveConfig.value.notifications.autoExpand" @change="onNotifToggle('autoExpand', ($event.target as HTMLInputElement).checked)" />
            <span>{{ t('ai-panel.proactive.notif_auto_expand') }}</span>
          </label>
        </div>
      </div>
      <!-- 免打扰 -->
      <div class="ai-ps-section">
        <div class="ai-ps-section-title">{{ t('ai-panel.proactive.settings_section_dnd') }}</div>
        <label class="ai-ps-checkbox ai-ps-dnd-toggle">
          <input type="checkbox" :checked="proactive.proactiveConfig.value.dnd.enabled" @change="onDndToggle(($event.target as HTMLInputElement).checked)" />
          <span>{{ t('ai-panel.proactive.dnd_toggle') }}</span>
        </label>
        <div v-if="proactive.proactiveConfig.value.dnd.enabled" class="ai-ps-dnd-time">
          <span>{{ t('ai-panel.proactive.dnd_from') }}</span>
          <select :value="proactive.proactiveConfig.value.dnd.startHour" @change="onDndTimeChange('startHour', Number(($event.target as HTMLSelectElement).value))">
            <option v-for="h in 24" :key="h-1" :value="h-1">{{ String(h-1).padStart(2,'0') }}:00</option>
          </select>
          <span>{{ t('ai-panel.proactive.dnd_to') }}</span>
          <select :value="proactive.proactiveConfig.value.dnd.endHour" @change="onDndTimeChange('endHour', Number(($event.target as HTMLSelectElement).value))">
            <option v-for="h in 24" :key="h-1" :value="h-1">{{ String(h-1).padStart(2,'0') }}:00</option>
          </select>
        </div>
      </div>
    </div>

    <!-- 会话标签栏（分段控件） -->
    <div v-show="aiTab === 'chat'" class="ai-session-tabs">
      <div class="ai-session-tabs-scroll">
        <button
          v-for="s in visibleSessions" :key="s.id"
          class="ai-session-seg" :class="{ 'is-active': s.id === aiSessions.currentBucket.activeSessionId }"
          :title="s.name || t('ai-panel.session_default')"
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
            :aria-label="t('ai-panel.rename_session')"
          />
          <span v-else class="ai-session-seg-label">{{ s.name }}</span>
          <span class="ai-session-seg-dot"></span>
          <span v-if="segHover === s.id && s.id !== aiSessions.currentBucket.activeSessionId && renamingId !== s.id" class="ai-session-seg-actions">
            <IconButton class="ai-session-seg-action" :label="t('ai-panel.rename')" @click.stop="startRename(s.id)">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 1.5l3 3-9 9H2.5v-3z"/></svg>
            </IconButton>
            <IconButton class="ai-session-seg-action is-close" :label="t('ai-panel.delete')" @click.stop="onDeleteSession(s.id)">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8"/><path d="M12 4l-8 8"/></svg>
            </IconButton>
          </span>
        </button>
      </div>
      <div v-if="overflowSessions.length > 0" class="ai-session-overflow">
        <IconButton
          class="ai-session-overflow-btn"
          :class="{ 'is-active': showOverflowMenu }"
          :label="t('ai-panel.more_sessions', { count: overflowSessions.length })"
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
              <IconButton class="ai-session-seg-action" :label="t('ai-panel.rename')" @click.stop="startRename(s.id)">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 1.5l3 3-9 9H2.5v-3z"/></svg>
              </IconButton>
              <IconButton class="ai-session-seg-action is-close" :label="t('ai-panel.delete')" @click.stop="onDeleteSession(s.id); showOverflowMenu = false">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8"/><path d="M12 4l-8 8"/></svg>
              </IconButton>
            </span>
          </div>
        </div>
      </div>
      <IconButton class="ai-session-add" :label="t('ai-panel.new_session')" show-label @click="onNewSession()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
      </IconButton>
    </div>

    <!-- 对话 Tab -->
    <div v-show="aiTab === 'chat'" class="ai-feed" ref="feedRef">
      <div v-for="(msg, i) in chat.messages.value" :key="i" class="ai-msg" :class="{ 'is-user': msg.role === 'user' }">
        <div class="ai-bubble" v-html="fmt(msg.content)"></div>
        <!-- 插入纪要/随记按钮（仅 assistant 消息） -->
        <div v-if="msg.role === 'assistant' && msg.content" class="ai-msg-actions">
          <IconButton class="ai-insert-btn" :label="t('ai-panel.insert_summary')" show-label @click="onInsertToSummary(msg.content)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="12" y1="18" x2="12" y2="12"/><polyline points="9,15 12,12 15,15"/></svg>
          </IconButton>
          <IconButton class="ai-insert-btn" :label="t('ai-panel.insert_notes')" show-label @click="onInsertToNotes(msg.content)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          </IconButton>
        </div>
        <!-- 改写 Diff 视图（仅最后一条 assistant 消息且存在改写挂起） -->
        <div v-if="quoteRef.rewritePending.value && i === chat.messages.value.length - 1 && msg.role === 'assistant'" class="diff-view">
          <div class="diff-header">
            <span>{{ t('ai-panel.rewrite_label') }}</span>
            <span>{{ quoteRef.rewritePending.value.source }}</span>
          </div>
          <div class="diff-body">
            <p style="margin-bottom:8px;"><span class="diff-del">{{ shortText(quoteRef.rewritePending.value.originalText) }}</span></p>
            <p style="font-size:11px;color:var(--muted);font-style:italic;">{{ t('ai-panel.rewrite_hint') }}</p>
          </div>
          <div class="diff-actions">
            <IconButton class="diff-accept-btn" :label="t('ai-panel.accept_rewrite')" show-label @click="onAcceptRewrite(msg.content)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
            </IconButton>
            <button class="diff-reject-btn" @click="quoteRef.clearRewrite()">{{ t('ai-panel.reject_rewrite') }}</button>
          </div>
        </div>
        <!-- AI 操作校验结果展示 -->
        <div v-if="chat.verifiedChanges.value.length && i === chat.messages.value.length - 1 && msg.role === 'assistant'" class="verified-changes-block">
          <div class="vc-header">{{ t('ai-panel.verify_header') }}</div>
          <div class="vc-list">
            <div v-for="(change, ci) in chat.verifiedChanges.value" :key="ci" class="vc-item" :class="{ 'is-verified': change.verified }">
              <span class="vc-icon">{{ change.verified ? '✅' : '⚠️' }}</span>
              <span class="vc-desc">{{ chat.formatChangeDescription(change) }}</span>
              <span class="vc-status">{{ change.verified ? t('ai-panel.verify_pass') : t('ai-panel.verify_fail') }}</span>
            </div>
          </div>
        </div>
        <!-- 数据注入提示 -->
        <div v-if="chat.injectPrompt.value && i === chat.messages.value.length - 1 && msg.role === 'assistant'" class="inject-prompt">
          <span>{{ t('ai-panel.inject_detected', { desc: chat.injectPrompt.value.desc }) }}</span>
          <button class="btn-inject-all" @click="chat.doInjectAll()">{{ t('ai-panel.inject_all') }}</button>
          <button class="btn-dismiss" @click="chat.injectPrompt.value = null">{{ t('ai-panel.inject_dismiss') }}</button>
        </div>
      </div>
      <div v-if="chat.isLoading.value" class="ai-msg">
        <div class="ai-bubble" style="opacity:0.6">{{ t('ai-panel.thinking') }}</div>
      </div>
      <!-- AI 主动消息列表（折叠/展开卡片） -->
      <div v-for="pm in proactive.proactiveMessages.value" :key="pm.id" class="ai-msg is-proactive" :id="'proactive-' + pm.id" :class="{ 'is-expanded': pm.expanded }">
        <!-- 折叠态：紧凑卡片 -->
        <div class="proactive-card-header" @click="proactive.toggleExpanded(pm.id)">
          <span class="proactive-card-category">{{ pm.category }}</span>
          <span class="proactive-card-title">{{ pm.title }}</span>
          <span class="proactive-card-time">{{ formatProactiveTime(pm.timestamp) }}</span>
          <span class="proactive-card-chevron">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
          </span>
        </div>
        <!-- 展开态：完整内容 -->
        <div v-if="pm.expanded" class="proactive-card-body">
          <div class="proactive-card-summary" v-html="pm.body"></div>
          <div class="proactive-card-solution">
            <div class="proactive-solution-label">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:12px;height:12px">
                <path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
              </svg>
              {{ t('ai-panel.ai_suggestion') }}
            </div>
            <div class="proactive-solution-text">{{ pm.solution }}</div>
          </div>
          <div class="proactive-actions">
            <button
              v-for="act in pm.actions" :key="act.key"
              class="proactive-action-btn"
              :class="{ 'is-primary': act.primary, 'is-done': actedActions[pm.id + ':' + act.key] }"
              @click="onProactiveAction(pm, act)"
            >{{ actedActions[pm.id + ':' + act.key] ? t('ai-panel.proactive.action_done') : act.label }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 分析 Tab -->
    <div v-show="aiTab === 'analysis'" class="ai-feed">
      <div v-if="!analysis.hasData.value" class="ai-welcome">
        <p>{{ t('ai-panel.analysis.title') }}</p>
        <p class="ai-welcome-hint">{{ t('ai-panel.analysis.hint') }}</p>
      </div>
      <template v-else>
        <!-- 概览卡片 -->
        <div v-if="analysis.overview.value" class="ai-analysis-overview">
          <div class="ai-ao-item">
            <span class="ai-ao-value">{{ analysis.overview.value.speakerCount }}</span>
            <span class="ai-ao-label">{{ t('ai-panel.analysis.speakers') }}</span>
          </div>
          <div class="ai-ao-item">
            <span class="ai-ao-value">{{ analysis.overview.value.dialogueCount }}</span>
            <span class="ai-ao-label">{{ t('ai-panel.analysis.utterances') }}</span>
          </div>
          <div class="ai-ao-item">
            <span class="ai-ao-value">{{ formatCount(analysis.overview.value.wordCount) }}</span>
            <span class="ai-ao-label">{{ t('ai-panel.analysis.words') }}</span>
          </div>
          <div class="ai-ao-item">
            <span class="ai-ao-value">{{ analysis.overview.value.duration }}</span>
            <span class="ai-ao-label">{{ t('ai-panel.analysis.duration') }}</span>
          </div>
        </div>
        <!-- 发言占比 -->
        <div class="ai-analysis-section">
          <div class="ai-analysis-label">{{ t('ai-panel.analysis.speak_ratio') }}</div>
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
          <div class="ai-analysis-label">{{ t('ai-panel.analysis.todo_done') }}</div>
          <div class="ai-todo-bar">
            <div class="ai-todo-fill" :style="{ width: todoPercent + '%' }" :class="todoPercent >= 100 ? 'is-done' : ''"></div>
          </div>
          <div class="ai-todo-text">
            {{ t('ai-panel.analysis.todo_stat', { done: analysis.todoStats.value.done, total: analysis.todoStats.value.total }) }}
          </div>
        </div>
        <!-- 章节时间线 -->
        <div v-if="analysis.chapters.value.length > 1" class="ai-analysis-section">
          <div class="ai-analysis-label">{{ t('ai-panel.analysis.chapters') }}</div>
          <div class="ai-chapter-list">
            <div v-for="(ch, i) in analysis.chapters.value" :key="i" class="ai-chapter-item">
              <span class="ai-chapter-dot"></span>
              <span class="ai-chapter-info">
                <span class="ai-chapter-title">{{ ch.title }}</span>
                <span class="ai-chapter-meta">{{ t('ai-panel.analysis.chapter_meta', { lines: ch.lineCount, speakers: ch.speakers.size }) }}</span>
              </span>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 上下文 Tab -->
    <div v-show="aiTab === 'context'" class="ai-feed ai-context-feed">
      <!-- 空状态引导 -->
      <div v-if="isContextEmpty" class="ctx-empty">
        <div class="ctx-empty-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
          </svg>
        </div>
        <h4>{{ t('ai-panel.context.empty_title') }}</h4>
        <p>{{ t('ai-panel.context.empty_desc') }}</p>
        <div class="ctx-empty-actions">
          <button class="ctx-empty-action" @click="generateSummary" :title="t('ai-panel.context.action_generate_summary')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            <span>{{ t('ai-panel.context.action_generate_summary') }}</span>
            <span class="shortcut">⌘G</span>
          </button>
          <button class="ctx-empty-action" @click="addProjectFile" :title="t('ai-panel.context.action_upload_file')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <span>{{ t('ai-panel.context.action_upload_file') }}</span>
            <span class="shortcut">U</span>
          </button>
          <button class="ctx-empty-action" @click="linkRelatedMeeting" :title="t('ai-panel.context.action_link_meeting')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8"/>
              <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <span>{{ t('ai-panel.context.action_link_meeting') }}</span>
            <span class="shortcut">L</span>
          </button>
        </div>
      </div>

      <!-- 有数据时的正常布局 -->
      <template v-else>
        <!-- 引导横幅 -->
        <div v-if="!heroDismissed" class="ctx-hero">
          <div class="ctx-hero-inner">
            <div class="ctx-hero-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
              </svg>
            </div>
            <div class="ctx-hero-text">
              <h3>{{ t('ai-panel.context.hero_title') }}</h3>
              <p>{{ t('ai-panel.context.hero_desc') }}</p>
            </div>
          </div>
          <button class="ctx-hero-dismiss" @click="dismissHero" :title="t('ai-panel.context.hero_dismiss')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <!-- 概览统计 -->
        <div class="ctx-overview">
          <div v-if="contextStats.transcript > 0" class="ctx-stat">
            <div class="ctx-stat-num">{{ contextStats.transcript }}</div>
            <div class="ctx-stat-label">{{ t('ai-panel.context.stat_transcript') }}</div>
          </div>
          <div v-if="contextStats.summary > 0" class="ctx-stat">
            <div class="ctx-stat-num">{{ contextStats.summary }}</div>
            <div class="ctx-stat-label">{{ t('ai-panel.context.stat_summary') }}</div>
          </div>
          <div v-if="contextStats.todos > 0" class="ctx-stat">
            <div class="ctx-stat-num">{{ contextStats.todos }}</div>
            <div class="ctx-stat-label">{{ t('ai-panel.context.stat_todos') }}</div>
          </div>
          <div v-if="contextStats.files > 0" class="ctx-stat">
            <div class="ctx-stat-num">{{ contextStats.files }}</div>
            <div class="ctx-stat-label">{{ t('ai-panel.context.stat_files') }}</div>
          </div>
          <div v-if="relatedMeetingCount > 0" class="ctx-stat">
            <div class="ctx-stat-num">{{ relatedMeetingCount }}</div>
            <div class="ctx-stat-label">{{ t('ai-panel.context.stat_related') }}</div>
          </div>
        </div>

        <!-- 会议产出 -->
        <div class="ctx-section" :class="{ 'is-collapsed': !ctxSections.meeting }">
          <div class="ctx-section-header" @click="ctxSections.meeting = !ctxSections.meeting">
            <div class="ctx-section-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              <h4>{{ t('ai-panel.context.section_meeting') }}</h4>
            </div>
            <div class="ctx-section-header-right">
              <span class="ctx-section-count">{{ meetingOutputCount }} 项</span>
              <svg class="ctx-chevron" :class="{ 'is-collapsed': !ctxSections.meeting }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </div>
          </div>
          <div class="ctx-section-body">
            <!-- 转写原文 -->
            <div class="ctx-item" @click="goToTranscript" :title="t('ai-panel.context.transcript_title')">
              <div class="ctx-item-icon type-transcript">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/>
                  <line x1="16" y1="17" x2="8" y2="17"/>
                </svg>
              </div>
              <div class="ctx-item-body">
                <div class="ctx-item-title">{{ t('ai-panel.context.transcript_title') }}</div>
                <div class="ctx-item-meta">
                  <span>{{ currentTaskDuration }}</span>
                  <span class="dot"></span>
                  <span>{{ speakerCount }} {{ t('ai-panel.context.speakers_unit') }}</span>
                </div>
              </div>
              <span class="ctx-item-tag">{{ t('ai-panel.context.tag_transcript') }}</span>
            </div>

            <!-- 会议纪要 -->
            <div class="ctx-item" @click="goToSummary" :title="t('ai-panel.context.summary_title')">
              <div class="ctx-item-icon type-summary">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/>
                  <line x1="16" y1="17" x2="10" y2="17"/>
                  <polyline points="10 9 9 9 8 9"/>
                </svg>
              </div>
              <div class="ctx-item-body">
                <div class="ctx-item-title">{{ t('ai-panel.context.summary_title') }}</div>
                <div class="ctx-item-meta">
                  <span>{{ t('ai-panel.context.auto_generated') }}</span>
                  <span class="dot"></span>
                  <span>{{ chapterCount }} {{ t('ai-panel.context.chapters_unit') }}</span>
                </div>
              </div>
              <span :class="['status-tag', hasSummary ? 'is-ok' : 'is-warn']">
                {{ hasSummary ? t('ai-panel.context.status_generated') : t('ai-panel.context.status_pending') }}
              </span>
            </div>

            <!-- 待办事项 -->
            <div class="ctx-item" @click="goToTodos" :title="t('ai-panel.context.todo_title', { count: todoCount })">
              <div class="ctx-item-icon type-todo">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="9 11 12 14 22 4"/>
                  <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                </svg>
              </div>
              <div class="ctx-item-body">
                <div class="ctx-item-title">{{ t('ai-panel.context.todo_title_simple') }}</div>
                <div class="ctx-item-meta">
                  <span>{{ todoPending }} {{ t('ai-panel.context.todo_pending') }}</span>
                  <span class="dot"></span>
                  <span>{{ todoDone }} {{ t('ai-panel.context.todo_done_label') }}</span>
                </div>
              </div>
              <span :class="['status-tag', todoDone > 0 ? (todoPending > 0 ? 'is-warn' : 'is-ok') : 'is-muted']">
                {{ todoDone > 0 ? (todoPending > 0 ? t('ai-panel.context.status_in_progress') : t('ai-panel.context.status_completed')) : t('ai-panel.context.status_pending') }}
              </span>
            </div>
          </div>
        </div>

        <!-- 项目文件 -->
        <div class="ctx-section" :class="{ 'is-collapsed': !ctxSections.files }">
          <div class="ctx-section-header" @click="ctxSections.files = !ctxSections.files">
            <div class="ctx-section-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              <h4>{{ t('ai-panel.context.section_files') }}</h4>
            </div>
            <div class="ctx-section-header-right">
              <span class="ctx-section-count">{{ projectFileCount }} 项</span>
              <svg class="ctx-chevron" :class="{ 'is-collapsed': !ctxSections.files }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </div>
          </div>
          <div class="ctx-section-body">
            <div v-if="projectFiles.length === 0" class="ctx-empty-section">
              <p>{{ t('ai-panel.context.no_files') }}</p>
            </div>
            <div v-for="file in visibleProjectFiles" :key="file.id" class="ctx-item">
              <div class="ctx-item-icon type-file">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
                  <polyline points="13 2 13 9 20 9"/>
                </svg>
              </div>
              <div class="ctx-item-body">
                <div class="ctx-item-title" :title="file.name">{{ file.name }}</div>
                <div class="ctx-item-meta">
                  <span>{{ file.size }}</span>
                  <span class="dot"></span>
                  <span>{{ file.date }}</span>
                </div>
              </div>
              <span class="ctx-item-tag">{{ file.type }}</span>
            </div>
            <button v-if="projectFiles.length > MAX_VISIBLE_FILES" class="ctx-show-more" @click="showAllFiles = !showAllFiles">
              {{ showAllFiles ? t('ai-panel.context.show_less') : t('ai-panel.context.show_more', { count: projectFiles.length - MAX_VISIBLE_FILES }) }}
            </button>
          </div>
          <button class="ctx-add-btn" @click="addProjectFile">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            {{ t('ai-panel.context.add_file') }}
          </button>
        </div>

        <!-- 相关会议 -->
        <div class="ctx-section" :class="{ 'is-collapsed': !ctxSections.related }">
          <div class="ctx-section-header" @click="ctxSections.related = !ctxSections.related">
            <div class="ctx-section-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                <line x1="16" y1="2" x2="16" y2="6"/>
                <line x1="8" y1="2" x2="8" y2="6"/>
                <line x1="3" y1="10" x2="21" y2="10"/>
              </svg>
              <h4>{{ t('ai-panel.context.section_related') }}</h4>
            </div>
            <div class="ctx-section-header-right">
              <span class="ctx-section-count">{{ relatedMeetingCount }} 项</span>
              <svg class="ctx-chevron" :class="{ 'is-collapsed': !ctxSections.related }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </div>
          </div>
          <div class="ctx-section-body">
            <div v-if="relatedMeetings.length === 0" class="ctx-empty-section">
              <p>{{ t('ai-panel.context.no_related') }}</p>
            </div>
            <div v-for="meeting in visibleRelatedMeetings" :key="meeting.id" class="ctx-item">
              <div class="ctx-item-icon type-meeting">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                  <circle cx="9" cy="7" r="4"/>
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                  <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                </svg>
              </div>
              <div class="ctx-item-body">
                <div class="ctx-item-title" :title="meeting.title">{{ meeting.title }}</div>
                <div class="ctx-item-meta">
                  <span>{{ meeting.date }}</span>
                  <span class="dot"></span>
                  <span>{{ meeting.duration }}</span>
                </div>
              </div>
              <span class="ctx-item-tag">{{ meeting.tag }}</span>
            </div>
            <button v-if="relatedMeetings.length > MAX_VISIBLE_MEETINGS" class="ctx-show-more" @click="showAllMeetings = !showAllMeetings">
              {{ showAllMeetings ? t('ai-panel.context.show_less') : t('ai-panel.context.show_more', { count: relatedMeetings.length - MAX_VISIBLE_MEETINGS }) }}
            </button>
          </div>
        </div>

        <!-- 拖拽上传提示（功能开发中） -->
        <div class="ctx-drop-hint" style="display: none;">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="16 16 12 12 8 16"/>
            <line x1="12" y1="12" x2="12" y2="21"/>
            <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
          </svg>
          {{ t('ai-panel.context.drop_hint') }}
        </div>
      </template>
    </div>

    <!-- 输入区（仅对话 Tab） -->
    <div v-show="aiTab === 'chat'" class="ai-input-zone">
      <!-- AI 主动消息悬浮通知横幅 -->
      <div v-if="proactive.proactiveEnabled.value && proactive.latestUnread.value" class="proactive-banner-wrap">
        <div class="proactive-banner" @click="onBannerClick">
          <div class="proactive-banner-inner">
            <div class="proactive-banner-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
              </svg>
            </div>
            <div class="proactive-banner-text">
              <div class="proactive-banner-label">{{ t('ai-panel.proactive.banner_label') }}</div>
              <div class="proactive-banner-title">{{ proactive.latestUnread.value.title }}</div>
              <div class="proactive-banner-preview">{{ stripHtml(proactive.latestUnread.value.body) }}</div>
            </div>
            <button class="proactive-banner-close" :aria-label="t('ai-panel.proactive.banner_close')" @click.stop="onBannerClose">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
          <div class="proactive-banner-time">{{ t('ai-panel.proactive.banner_time') }}</div>
        </div>
      </div>
      <!-- 跟进建议（对话有内容时显示在输入框上方，滚动区外） -->
      <div v-show="chat.displaySuggestions.value.length > 0" class="ai-suggestions-bar">
        <button v-for="(s, si) in chat.displaySuggestions.value" :key="si" class="follow-up-chip" @click="chat.sendRaw(s.text)">
          <span v-html="s.icon"></span>{{ s.text }}
        </button>
      </div>
      <!-- 停止生成 -->
      <div class="ai-stop-gen" :class="{ 'is-visible': chat.isLoading.value }">
        <button class="ai-stop-gen-btn" @click="chat.stopGeneration()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>
          {{ t('ai-panel.stop_generating') }}
        </button>
      </div>
      <!-- 引用区域 -->
      <div v-if="quoteRef.quoteRef.value" class="quote-ref">
        <div class="quote-ref-text">{{ quoteRef.quoteRef.value.text }}</div>
        <div class="quote-ref-source">
          <span class="src-dot"></span>
          <span>{{ quoteRef.quoteRef.value.blockIndex >= 0 ? t('ai-panel.quote.source_block', { source: quoteRef.quoteRef.value.source, index: quoteRef.quoteRef.value.blockIndex + 1 }) : t('ai-panel.quote.source', { source: quoteRef.quoteRef.value.source }) }}</span>
        </div>
        <button class="quote-ref-remove" :title="t('ai-panel.quote.remove')" @click="quoteRef.clearQuote()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
      <!-- 指令面板 -->
      <div class="ai-cmd-palette" :class="{ 'is-open': cmds.cmdOpen.value && filteredCmds.length > 0 }">
        <template v-if="filteredCmds.length > 0">
          <button v-for="(c, ci) in filteredCmds" :key="c.key" class="ai-cmd-item" :class="{ 'is-active': cmds.cmdIndex.value === ci }" @click="runCommand(c)">
            <span class="cmd-key">{{ c.key }}</span>
            <span class="cmd-label">{{ c.desc }}</span>
          </button>
        </template>
        <div v-else-if="inputText.startsWith('/')" class="ai-cmd-empty">无匹配指令</div>
      </div>
      <div class="ai-input-box">
        <textarea
          v-model="inputText"
          :placeholder="t('ai-panel.input_placeholder')"
          rows="1"
          ref="inputRef"
          @keydown="handleInputKey"
          @input="handleInputChange"
          :aria-label="t('ai-panel.input_aria')"
        ></textarea>
        <button class="ai-send-btn" :disabled="!inputText.trim() || chat.isLoading.value" @click="onSend" :title="t('ai-panel.send')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { useLayoutStore } from '@/stores/layout'
import { useAiChat } from '@/composables/useAiChat'
import { useQuoteRef } from '@/composables/useQuoteRef'
import { useAiSessionsStore } from '@/stores/aiSessions'
import { useAiAnalysis } from '@/composables/useAiAnalysis'
import { useAiCommands } from '@/composables/useAiCommands'
import type { AiCommand } from '@/composables/useAiCommands'
import { showToast } from '@/composables/useToast'
import { beginResize } from '@/composables/useDivider'
import { useAiProactive } from '@/composables/useAiProactive'
import type { ProactiveMessage, ProactiveAction } from '@/composables/useAiProactive'
import IconButton from '@/components/common/IconButton.vue'

const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
const taskStore = useTaskStore()
const layout = useLayoutStore()

function onToggleDown(e: MouseEvent) {
  beginResize(e, 'right', { onClick: () => layout.toggleAi(), resizable: !layout.aiCollapsed })
}
const chat = useAiChat()
const quoteRef = useQuoteRef()
const aiSessions = useAiSessionsStore()
const analysis = useAiAnalysis()
const proactive = useAiProactive()
const cmds = useAiCommands()

const aiTab = ref('chat')
const inputText = ref('')
const inputRef = ref<HTMLTextAreaElement | null>(null)
const feedRef = ref<HTMLElement | null>(null)
const showProactiveSettings = ref(false)

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

// 上下文 Tab 数据
const ctxSections = ref({
  meeting: true,
  files: true,
  related: true,
})

const heroDismissed = ref(localStorage.getItem('ctx_hero_dismissed') === '1')

function dismissHero() {
  heroDismissed.value = true
  localStorage.setItem('ctx_hero_dismissed', '1')
}

const projectFiles = ref<Array<{ id: string; name: string; size: string; date: string; type: string }>>([])
const relatedMeetings = ref<Array<{ id: string; title: string; date: string; duration: string; tag: string }>>([])
const showAllFiles = ref(false)
const showAllMeetings = ref(false)
const MAX_VISIBLE_FILES = 5
const MAX_VISIBLE_MEETINGS = 5

const visibleProjectFiles = computed(() =>
  showAllFiles.value ? projectFiles.value : projectFiles.value.slice(0, MAX_VISIBLE_FILES)
)

const visibleRelatedMeetings = computed(() =>
  showAllMeetings.value ? relatedMeetings.value : relatedMeetings.value.slice(0, MAX_VISIBLE_MEETINGS)
)

const contextStats = computed(() => ({
  transcript: taskStore.currentTask ? 1 : 0,
  summary: analysis.hasData.value && taskStore.currentTask?.summary ? 1 : 0,
  todos: analysis.todoStats.value?.total || 0,
  files: projectFiles.value.length,
}))

const contextResourceCount = computed(() =>
  contextStats.value.transcript +
  contextStats.value.summary +
  contextStats.value.todos +
  contextStats.value.files +
  relatedMeetings.value.length
)

const meetingOutputCount = computed(() =>
  contextStats.value.transcript + contextStats.value.summary + (contextStats.value.todos > 0 ? 1 : 0)
)

const projectFileCount = computed(() => projectFiles.value.length)
const relatedMeetingCount = computed(() => relatedMeetings.value.length)

const currentTaskDuration = computed(() => {
  const task = taskStore.currentTask
  if (!task?.audio_duration) return '—'
  const mins = Math.floor(task.audio_duration / 60)
  const secs = Math.floor(task.audio_duration % 60)
  return `${mins}min ${secs.toString().padStart(2, '0')}s`
})

const speakerCount = computed(() => analysis.overview.value?.speakerCount || 0)
const chapterCount = computed(() => analysis.chapters.value?.length || 0)
const hasSummary = computed(() => !!taskStore.currentTask?.summary)
const todoCount = computed(() => analysis.todoStats.value?.total || 0)
const todoPending = computed(() => {
  const ts = analysis.todoStats.value
  return ts ? ts.total - ts.done : 0
})
const todoDone = computed(() => analysis.todoStats.value?.done || 0)

const currentStatus = computed(() => taskStore.currentTask?.status ?? null)

/** 会议相关路由名（这些页面优先显示会议标题） */
const MEETING_ROUTE_NAMES = ['recording', 'generating']

/** 上下文指示器：当前页面/会议标签 */
const contextLabel = computed(() => {
  const routeName = route.name as string
  // 会议相关路由且有当前任务 → 显示会议标题
  if (MEETING_ROUTE_NAMES.includes(routeName) && taskStore.currentTask) {
    return taskStore.currentTask.title || taskStore.currentTask.audio_name || t('ai-panel.current_meeting')
  }
  // 非会议路由 → 显示页面名称
  const pageKey = `ai-panel.page.${routeName || 'start'}`
  return t(pageKey)
})

const filteredCmds = computed(() => {
  if (!inputText.value.startsWith('/')) return []
  const query = inputText.value.slice(1).toLowerCase()
  return cmds.filterCommands(query, currentStatus.value)
})

const isContextEmpty = computed(() =>
  contextStats.value.transcript === 0 &&
  contextStats.value.summary === 0 &&
  contextStats.value.todos === 0 &&
  contextStats.value.files === 0 &&
  relatedMeetings.value.length === 0
)

function generateSummary() {
  // 触发 AI 生成纪要
  chat.sendRaw(t('ai-panel.context.action_generate_summary_text'))
  aiTab.value = 'chat'
}

function linkRelatedMeeting() {
  // 跳转到会议库选择相关会议
  showToast(t('ai-panel.context.toast_link_meeting'), 'info')
}

function goToTranscript() {
  const task = taskStore.currentTask
  if (task?.task_id) {
    // 跳转到转写页面（如果有）或显示提示
    showToast(t('ai-panel.context.toast_transcript'), 'info')
  }
}

function goToSummary() {
  const task = taskStore.currentTask
  if (task?.task_id) {
    // 跳转到纪要页面
    showToast(t('ai-panel.context.toast_summary'), 'info')
  }
}

function goToTodos() {
  const task = taskStore.currentTask
  if (task?.task_id) {
    // 跳转到待办页面
    showToast(t('ai-panel.context.toast_todos'), 'info')
  }
}

function addProjectFile() {
  // TODO: 实现文件上传
  showToast(t('ai-panel.context.toast_upload'), 'info')
}

/** 执行指令 */
function runCommand(cmd: AiCommand) {
  cmds.close()
  inputText.value = ''
  cmd.action()
}

/** 注册指令列表 —— 与 cli.py 的 CLI 命令保持一致 */
function buildCommands(): AiCommand[] {
  return [
    // 独立命令
    { key: '/transcribe', desc: '转写音频 + 生成纪要', when: 'all', action: () => router.push('/') },
    { key: '/normalize', desc: '归一化音频（16kHz/单声道）', when: 'all', action: () => showToast('CLI 专用命令：python cli.py normalize <音频文件>', 'warn') },
    { key: '/upload', desc: '上传音频到 DashScope（测试用）', when: 'all', action: () => showToast('CLI 专用命令：python cli.py upload <音频文件>', 'warn') },
    { key: '/server', desc: '启动 Web UI 服务', when: 'all', action: () => showToast('CLI 专用命令：python cli.py server', 'warn') },
    { key: '/build', desc: '构建前端（Vue 3 + Vite）', when: 'all', action: () => showToast('CLI 专用命令：python cli.py build', 'warn') },
    { key: '/admin', desc: '启动管理后台', when: 'all', action: () => showToast('CLI 专用命令：python cli.py admin', 'warn') },
    // record 录音控制
    { key: '/record start', desc: '开始录音', when: 'all', action: onRecordStart },
    { key: '/record stop', desc: '停止录音', when: 'all', action: onRecordStop },
    { key: '/record pause', desc: '暂停录音', when: 'all', action: onRecordPause },
    { key: '/record resume', desc: '恢复录音', when: 'all', action: onRecordResume },
    { key: '/record status', desc: '查看录音状态', when: 'all', action: onRecordStatus },
    // tasks 任务管理
    { key: '/tasks list', desc: '列出所有任务', when: 'all', action: () => router.push('/library') },
    { key: '/tasks show', desc: '查看任务详情', when: 'all', action: onTasksShow },
    { key: '/tasks delete', desc: '删除任务', when: 'all', action: onTasksDelete },
    // speakers 说话人管理
    { key: '/speakers list', desc: '列出所有说话人', when: 'all', action: () => router.push('/speakers') },
    { key: '/speakers add', desc: '添加说话人', when: 'all', action: onSpeakersAdd },
    // hotwords 热词管理
    { key: '/hotwords list', desc: '列出热词', when: 'all', action: () => router.push('/hotwords') },
    { key: '/hotwords add', desc: '添加热词', when: 'all', action: onHotwordsAdd },
    // settings 设置管理
    { key: '/settings show', desc: '查看设置', when: 'all', action: () => router.push('/settings') },
    { key: '/settings set', desc: '修改设置', when: 'all', action: () => router.push('/settings') },
    // chat AI 对话
    { key: '/chat', desc: 'AI 对话（直接输入消息发送）', when: 'all', action: () => inputRef.value?.focus() },
  ]
}

async function onRecordStart() {
  try {
    const { startRecord } = await import('@/api/record')
    const res = await startRecord()
    showToast('录音已开始', 'success')
    // [状态同步] 录音成功后刷新任务列表
    await taskStore.loadTasks()
    router.push(`/recording/${res.task_id}`)
  } catch (e: any) {
    // 后端提示"已在录制中"时，自动导航到已有录音页
    if (e?.response?.status === 400) {
      try {
        const { getRecordStatus } = await import('@/api/record')
        const status = await getRecordStatus()
        if (status.recording && status.task_id) {
          // [状态同步] 恢复活跃录音时刷新任务列表
          await taskStore.loadTasks()
          taskStore.selectTask(status.task_id)
          router.push(`/recording/${status.task_id}`)
          return
        }
      } catch { /* 静默 */ }
    }
    showToast(e?.response?.data?.detail || '操作失败', 'error')
  }
}
async function onRecordStop() {
  try {
    const { stopRecord } = await import('@/api/record')
    await stopRecord()
    showToast('录音已停止', 'success')
    // [状态同步] 停止录音后刷新任务列表
    taskStore.loadTasks()
  } catch (e: any) { showToast(e?.response?.data?.detail || '操作失败', 'error') }
}
async function onRecordPause() {
  try {
    const { pauseRecord } = await import('@/api/record')
    await pauseRecord()
    showToast('录音已暂停', 'success')
  } catch (e: any) { showToast(e?.response?.data?.detail || '操作失败', 'error') }
}
async function onRecordResume() {
  try {
    const { resumeRecord } = await import('@/api/record')
    await resumeRecord()
    showToast('录音已恢复', 'success')
  } catch (e: any) { showToast(e?.response?.data?.detail || '操作失败', 'error') }
}
async function onRecordStatus() {
  try {
    const { getRecordStatus } = await import('@/api/record')
    const s = await getRecordStatus()
    const text = s.recording
      ? `录制状态：进行中${s.paused ? '（已暂停）' : ''}\n已录时长：${s.elapsed.toFixed(1)} 秒\n任务 ID：${s.task_id ?? '-'}`
      : '录制状态：未录制'
    chat.messages.value.push({ role: 'assistant', content: text })
    aiSessions.persist()
  } catch (e: any) { showToast(e?.response?.data?.detail || '操作失败', 'error') }
}
function onTasksShow() {
  const id = taskStore.currentTaskId
  if (id) router.push(`/meeting/${id}`)
  else { showToast('未选择任务，已打开会议库', 'warn'); router.push('/library') }
}
async function onTasksDelete() {
  const id = taskStore.currentTaskId
  if (!id) { showToast('未选择任务', 'warn'); return }
  if (!confirm(`确认删除任务 ${id.slice(0, 8)}…？`)) return
  try {
    const { deleteTask } = await import('@/api/tasks')
    await deleteTask(id)
    showToast('任务已删除', 'success')
    // [状态同步] 删除任务后刷新任务列表
    taskStore.loadTasks()
  } catch (e: any) { showToast(e?.response?.data?.detail || '操作失败', 'error') }
}
async function onSpeakersAdd() {
  const name = prompt('输入说话人姓名：')
  if (!name?.trim()) return
  try {
    const { createSpeaker } = await import('@/api/speakers')
    await createSpeaker(name.trim())
    showToast(`已添加说话人：${name.trim()}`, 'success')
  } catch (e: any) { showToast(e?.response?.data?.detail || '操作失败', 'error') }
}
async function onHotwordsAdd() {
  const input = prompt('输入热词（多个用空格或逗号分隔）：')
  if (!input?.trim()) return
  try {
    const { fetchHotwords, saveHotwords } = await import('@/api/hotwords')
    const current = await fetchHotwords()
    const words = current.split('\n').map(w => w.trim()).filter(Boolean)
    const added: string[] = []
    for (const w of input.split(/[\s,，]+/).filter(Boolean)) {
      if (!words.includes(w)) { words.push(w); added.push(w) }
    }
    if (!added.length) { showToast('这些热词已存在', 'warn'); return }
    await saveHotwords(words.join('\n'))
    showToast(`已添加 ${added.length} 个热词`, 'success')
  } catch (e: any) { showToast(e?.response?.data?.detail || '操作失败', 'error') }
}

function formatCount(n: number): string {
  // 「万」为中文特有单位，仅中文 locale 下使用；其他语言统一走 k 分支
  if (n >= 10000 && String(locale.value).startsWith('zh')) return (n / 10000).toFixed(1) + t('ai-panel.unit_wan')
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

onMounted(() => {
  cmds.registerCommands(buildCommands())
  window.addEventListener('quote-to-ai', onQuoteToAiEvent)
  window.addEventListener('global-ai-focus', onGlobalAiFocus)
  window.addEventListener('ai-scroll-to-unread', onScrollToUnread)
  document.addEventListener('click', onDocClickCloseOverflow)
})

onBeforeUnmount(() => {
  window.removeEventListener('quote-to-ai', onQuoteToAiEvent)
  window.removeEventListener('global-ai-focus', onGlobalAiFocus)
  window.removeEventListener('ai-scroll-to-unread', onScrollToUnread)
  document.removeEventListener('click', onDocClickCloseOverflow)
})

function onDocClickCloseOverflow(e: MouseEvent) {
  showOverflowMenu.value = false
  // 点击外部收起主动 AI 设置面板
  if (showProactiveSettings.value) {
    const target = e.target as HTMLElement
    if (!target.closest('.ai-proactive-settings') && !target.closest('.ai-proactive-group')) {
      showProactiveSettings.value = false
    }
  }
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
        fullText = ctx.context + '\n' + t('ai-panel.user_instruction') + detail.action
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
    fullText = text ? ctx.context + '\n' + t('ai-panel.user_instruction') + text : ctx.context + '\n' + t('ai-panel.process_quote')
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

/** 输入变化 → 自动调整高度 + 触发指令面板 */
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
    showToast(t('ai-panel.toast.replaced'), 'success')
  } else {
    showToast(t('ai-panel.toast.locate_failed'), 'warn')
  }
}

/** 插入内容到纪要 */
function onInsertToSummary(content: string) {
  const ok = quoteRef.insertToSummary(content)
  if (ok) {
    showToast(t('ai-panel.toast.inserted_summary'), 'success')
  } else {
    showToast(t('ai-panel.toast.open_summary_first'), 'warn')
  }
}

/** 插入内容到随记 */
function onInsertToNotes(content: string) {
  const ok = quoteRef.insertToNotes(content)
  if (ok) {
    showToast(t('ai-panel.toast.inserted_notes'), 'success')
  } else {
    showToast(t('ai-panel.toast.open_notes_first'), 'warn')
  }
}

/** 消息变化时自动滚动 */
watch(() => chat.messages.value.length, () => scrollFeed())

/* ─── AI 主动消息交互 ─── */
const actedActions = reactive<Record<string, boolean>>({})

function onProactiveAction(pm: ProactiveMessage, act: ProactiveAction) {
  const key = pm.id + ':' + act.key
  if (actedActions[key]) return
  actedActions[key] = true
  proactive.markAsRead(pm.id)
  // 场景 A 操作回调
  if (act.key === 'view') {
    showToast(t('ai-panel.proactive.toast_view'), 'info')
  } else if (act.key === 'sync') {
    showToast(t('ai-panel.proactive.toast_sync'), 'success')
  } else if (act.key === 'generate') {
    chat.sendRaw(t('ai-panel.proactive.prompt_summary'))
    aiTab.value = 'chat'
  }
}

function formatProactiveTime(ts: number): string {
  const d = new Date(ts)
  const hh = d.getHours().toString().padStart(2, '0')
  const mm = d.getMinutes().toString().padStart(2, '0')
  return `${hh}:${mm}`
}

function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, '')
}

function onBannerClick() {
  // 标记已读并滚动到对话区底部的主动消息
  if (proactive.latestUnread.value) {
    proactive.markAsRead(proactive.latestUnread.value.id)
  }
  nextTick(() => scrollFeed())
}

function onBannerClose() {
  if (proactive.latestUnread.value) {
    proactive.dismissProactiveMessage(proactive.latestUnread.value.id)
  }
}

/** 滚动到第一条未读主动消息 */
function onScrollToUnread() {
  const firstUnread = proactive.getFirstUnread()
  if (!firstUnread) return
  // 先展开该消息
  if (!firstUnread.expanded) {
    proactive.toggleExpanded(firstUnread.id)
  }
  nextTick(() => {
    const el = document.getElementById('proactive-' + firstUnread.id)
    if (el && feedRef.value) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  })
}

/* ─── 主动 AI 设置面板 ─── */
const categoryLabels = computed(() => ({
  deviation: t('ai-panel.proactive.cat_deviation_label'),
  contradiction: t('ai-panel.proactive.cat_contradiction_label'),
  missing_topic: t('ai-panel.proactive.cat_missing_topic_label'),
  todo_extract: t('ai-panel.proactive.cat_todo_extract_label'),
  summary_suggest: t('ai-panel.proactive.cat_summary_suggest_label'),
  stuck: t('ai-panel.proactive.cat_stuck_label'),
}))

function onCategoryToggle(key: string, val: boolean) {
  proactive.proactiveConfig.value.categories[key] = val
  proactive.saveConfig()
}

function onSensitivityChange(field: string, val: number) {
  (proactive.proactiveConfig.value.sensitivity as Record<string, number>)[field] = val
  proactive.saveConfig()
}

function onNotifToggle(field: string, val: boolean) {
  (proactive.proactiveConfig.value.notifications as Record<string, boolean>)[field] = val
  proactive.saveConfig()
}

function onDndToggle(val: boolean) {
  proactive.proactiveConfig.value.dnd.enabled = val
  proactive.saveConfig()
}

function onDndTimeChange(field: 'startHour' | 'endHour', val: number) {
  proactive.proactiveConfig.value.dnd[field] = val
  proactive.saveConfig()
}
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
