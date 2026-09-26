<template>
  <div class="settings-layout">
    <!-- 左栏：类别导航 / Left: category navigation -->
    <nav class="settings-nav">
      <button class="page-back-btn" @click="goBack">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        <span>{{ t('common.action.back') }}</span>
        <kbd>ESC</kbd>
      </button>
      <h1 class="settings-nav-title">{{ t('settings.title') }}</h1>
      <!-- 导航按配置栈 L0→L5 六层重排（REQ-EXPERT-MODE §2.2）：
           L0 套餐/账户 → L1 接入方式决策 → L2 服务参数 → L3 本地资产 → L4 CLI 引擎 →（后续常规分类） -->
      <button class="settings-nav-item" :class="{ 'is-active': activeCategory === 'account' }" @click="activeCategory = 'account'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        {{ t('settings.cat_account') }}
      </button>
      <button class="settings-nav-item" :class="{ 'is-active': activeCategory === 'access' }" @click="activeCategory = 'access'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M17.5 14v7M14 17.5h7"/></svg>
        {{ t('settings.cat_access') }}
      </button>
      <button class="settings-nav-item" :class="{ 'is-active': activeCategory === 'services' }" @click="activeCategory = 'services'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>
        {{ t('settings.cat_services') }}
      </button>
      <button class="settings-nav-item" :class="{ 'is-active': activeCategory === 'engine' }" @click="activeCategory = 'engine'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3"/><path d="M15 1v3"/><path d="M9 20v3"/><path d="M15 20v3"/><path d="M20 9h3"/><path d="M20 14h3"/><path d="M1 9h3"/><path d="M1 14h3"/></svg>
        {{ t('settings.cat_engine') }}
      </button>
      <button class="settings-nav-item" :class="{ 'is-active': activeCategory === 'cli' }" @click="activeCategory = 'cli'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
        {{ t('settings.cat_cli') }}
      </button>
      <button class="settings-nav-item" :class="{ 'is-active': activeCategory === 'transcription' }" @click="activeCategory = 'transcription'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>
        {{ t('settings.cat_transcription') }}
      </button>
      <button class="settings-nav-item" :class="{ 'is-active': activeCategory === 'appearance' }" @click="activeCategory = 'appearance'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/></svg>
        {{ t('settings.cat_appearance') }}
      </button>
      <button class="settings-nav-item" :class="{ 'is-active': activeCategory === 'features' }" @click="activeCategory = 'features'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        {{ t('settings.cat_features') }}
      </button>
      <button class="settings-nav-item" :class="{ 'is-active': activeCategory === 'system' }" @click="activeCategory = 'system'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1.1a1.7 1.7 0 0 0-1.8.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H2a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V2a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1.1a2 2 0 1 1 2.8 2.8l.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H22a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>
        {{ t('settings.cat_system') }}
      </button>
    </nav>

    <!-- 右栏：内容区 / Right: content area -->
    <div class="settings-content">

    <!-- 数据安全说明入口（静态，不可关闭） / Data security notice entry (static, non-closable) -->
    <div class="settings-privacy-bar">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
      <span>{{ t('settings.privacy_notice.text') }}</span>
      <a class="settings-privacy-link" href="https://github.com/et6624611/open-meeting-scribe/blob/main/SECURITY.md" target="_blank" rel="noopener">{{ t('settings.privacy_notice.learn_more') }}</a>
    </div>

    <!-- ═══ 接入方式 / Access mode（REQ-SETTINGS-IA：决策两卡 + 从属详情层） ═══ -->
    <div v-show="activeCategory === 'access'">
      <AccessModeCards
        :settings="settings"
        @goto="onAccessGoto"
        @guide-request="onGuideRequest"
      />
    </div>

    <!-- ═══ 账户 / Account ═══ -->
    <div v-show="activeCategory === 'account'">
    <!-- 账户信息 / Account info -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.account') }}</h2>
      <div v-if="userStore.isLoggedIn" class="settings-account">
        <span class="settings-avatar">{{ userStore.avatarLetter }}</span>
        <div class="settings-account-info">
          <div class="settings-name">{{ userStore.displayName }}</div>
          <div class="settings-account-meta">
            <span class="settings-role">{{ userStore.user?.provider || 'local' }}</span>
            <span class="usage-tier-badge" :class="'tier-' + (usageSummary.tier || 'free')">{{ tierName(usageSummary.tier) }}</span>
          </div>
        </div>
        <button class="settings-logout-btn" @click="onLogout" :title="t('settings.logout')">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          {{ t('settings.logout') }}
        </button>
      </div>
      <div v-else class="settings-login-prompt">
        <p>{{ t('settings.not_logged_in') }}</p>
        <button class="btn btn-primary" @click="showLogin">{{ t('settings.login') }}</button>
      </div>
    </div>

    <!-- 优先使用订阅流量 / Prefer subscription quota -->
    <div v-if="userStore.isLoggedIn" class="settings-section">
      <h2 class="settings-title">{{ t('settings.subscription_preference') }}</h2>
      <p class="settings-section-desc">{{ t('settings.subscription_preference_desc') }}</p>
      <div class="wm-setting-row">
        <label>
          {{ t('settings.prefer_subscription') }}
          <span class="toggle-desc">{{ t('settings.prefer_subscription_desc') }}</span>
        </label>
        <div class="wm-toggle-wrap">
          <div
            class="wm-toggle"
            :class="{ 'is-on': preferSubscription }"
            role="switch"
            :aria-checked="preferSubscription"
            tabindex="0"
            @click="onTogglePreferSubscription"
            @keydown.enter.prevent="onTogglePreferSubscription"
            @keydown.space.prevent="onTogglePreferSubscription"
          ></div>
          <span class="wm-setting-val">{{ preferSubscription ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
        </div>
      </div>
    </div>

    <!-- 用量与配额 / Usage and quota -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.usage') }}</h2>

      <!-- 未登录 / Not logged in -->
      <div v-if="!userStore.isLoggedIn" class="usage-not-metered">
        <p>{{ t('settings.usage_login_hint') }}</p>
        <button class="btn btn-primary" style="margin-top:12px;padding:0 16px;height:32px;font-size:12px" @click="showLogin">{{ t('settings.login') }}</button>
      </div>

      <!-- 计量模式 / Metered mode -->
      <div v-else-if="usageSummary.metered" class="usage-panel">
        <div style="display:flex;align-items:center;justify-content:space-between">
          <span class="usage-tier-badge" :class="'tier-' + (usageSummary.tier || 'free')">{{ tierName(usageSummary.tier) }}</span>
          <span style="font-size:12px;color:var(--muted);font-family:var(--font-mono)">{{ usageSummary.month }}</span>
        </div>
        <div class="usage-summary-row">
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.quota || 0) }}</div>
            <div class="stat-label">{{ t('settings.monthly_quota') }}</div>
          </div>
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.used || 0) }}</div>
            <div class="stat-label">{{ t('settings.used') }}</div>
          </div>
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.remaining || 0) }}</div>
            <div class="stat-label">{{ t('settings.remaining') }}</div>
          </div>
        </div>
        <div class="usage-progress">
          <div class="usage-progress-fill" :style="progressStyle"></div>
        </div>
        <div style="font-size:12px;color:var(--muted);margin-bottom:8px">{{ t('settings.recent_30_days') }}</div>
        <div class="usage-chart">
          <div
            v-for="d in usageHistory"
            :key="d.date"
            class="usage-chart-bar"
            :style="{ height: barHeight(d.minutes) + 'px' }"
            :data-tip="t('settings.usage_tooltip', { date: d.date.slice(5), minutes: formatMinutes(d.minutes), tasks: d.tasks })"
          ></div>
          <div v-if="!usageHistory.length" style="font-size:12px;color:var(--muted);padding:8px">{{ t('settings.no_usage') }}</div>
        </div>
      </div>

      <!-- 非计量模式 / Non-metered mode -->
      <div v-else class="usage-panel">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <span class="usage-tier-badge" :class="'tier-' + (usageSummary.tier || 'free')">{{ tierName(usageSummary.tier) }}</span>
          <span style="font-size:12px;color:var(--muted);font-family:var(--font-mono)">{{ t('settings.self_key') }}</span>
        </div>
        <div class="usage-summary-row">
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.quota || 0) }}</div>
            <div class="stat-label">{{ t('settings.monthly_quota') }}</div>
          </div>
          <div class="usage-stat">
            <div class="stat-value" style="color:var(--muted)">∞</div>
            <div class="stat-label">{{ t('settings.used_self') }}</div>
          </div>
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.quota || 0) }}</div>
            <div class="stat-label">{{ t('settings.platform_remaining') }}</div>
          </div>
        </div>
        <p style="margin:12px 0 0;font-size:12px;color:var(--muted)">{{ t('settings.cloud_mode_hint') }}</p>
      </div>
    </div>
    </div>

    <!-- ═══ 服务 / Services（参数唯一编辑面 · 显式保存，REQ-SETTINGS-IA 第 2 刀） ═══ -->
    <div v-show="activeCategory === 'services'">
    <!-- API 配置 / API configuration -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.api_config') }}</h2>

      <!-- LLM 纪要生成服务 / LLM summary generation service -->
      <div class="api-subsection">
        <h3 class="api-subsection-title">{{ t('settings.llm_service') }}</h3>
        <div class="settings-field">
          <label class="settings-label">{{ t('settings.llm_provider') }}</label>
          <select v-model="settings.llm!.provider" class="settings-input" @change="onLlmProviderChange">
            <option
              v-for="p in llmPresetsOrdered"
              :key="p.name"
              :value="p.name"
              :disabled="isPresetDisabled(p)"
            >{{ presetLabel(p) }}</option>
          </select>
          <span v-if="probeLoading" class="api-proxy-hint">{{ t('settings.llm_probe_running') }}</span>
          <a
            v-else-if="selectedInstallUrl"
            class="api-proxy-hint"
            :href="selectedInstallUrl"
            target="_blank"
            rel="noopener"
          >{{ t('settings.llm_install_guide') }}</a>
        </div>
        <div class="settings-field">
          <label class="settings-label">{{ t('settings.llm_base_url') }}</label>
          <input v-model="settings.llm!.base_url" class="settings-input" :placeholder="t('settings.llm_base_url_placeholder')" />
        </div>
        <div class="settings-field">
          <label class="settings-label">{{ t('settings.api_key') }}</label>
          <input v-model="settings.llm!.api_key" type="password" class="settings-input" :placeholder="t('settings.llm_api_key_placeholder')" />
          <span v-if="selectedIsLocal" class="api-proxy-hint">{{ t('settings.llm_local_no_key') }}</span>
        </div>
        <div class="settings-field">
          <label class="settings-label">{{ t('settings.llm_model') }}</label>
          <input v-model="settings.llm!.model" class="settings-input" list="llm-model-options" placeholder="qwen-plus" />
          <datalist id="llm-model-options">
            <option v-for="m in modelOptions" :key="m" :value="m" />
          </datalist>
          <span v-if="probeModelsLoaded" class="api-proxy-hint">{{ t('settings.llm_probe_models_hint') }}</span>
        </div>
      </div>

      <!-- ASR 语音转写服务 / ASR speech-to-text service -->
      <div class="api-subsection">
        <h3 class="api-subsection-title">{{ t('settings.asr_service') }}</h3>
        <!-- 算力来源只读回显（REQ-SETTINGS-IA 第 2 刀：来源唯一写入口 = 接入方式详情层） -->
        <div class="settings-field">
          <label class="settings-label">{{ t('settings.asr_source_readonly') }}</label>
          <span class="api-readonly">{{ asrSourceLabel }}<span class="api-proxy-hint">{{ t('settings.asr_source_hint') }}</span></span>
        </div>

        <!-- 自带 Key 时才可配端点与 Key / Key & endpoint only editable when the ASR source is "own key" -->
        <template v-if="settings.asr?.mode === 'direct'">
          <div class="settings-field">
            <label class="settings-label">{{ t('settings.asr_base_url') }}</label>
            <input v-model="settings.asr!.base_url" class="settings-input" placeholder="https://dashscope.aliyuncs.com" />
          </div>
          <div class="settings-field">
            <label class="settings-label">{{ t('settings.api_key') }}</label>
            <input v-model="settings.asr!.api_key" type="password" class="settings-input" :placeholder="t('settings.asr_api_key_placeholder')" />
          </div>
        </template>
        <template v-else>
          <div class="settings-field">
            <label class="settings-label">{{ t('settings.asr_provider') }}</label>
            <span class="api-readonly">{{ settings.asr?.provider || 'Cloud AI' }}<span class="api-proxy-hint">{{ t('settings.asr_proxy_managed') }}</span></span>
          </div>
        </template>
        <div class="settings-field">
          <label class="settings-label">{{ t('settings.asr_model') }}</label>
          <input v-model="settings.asr!.model" class="settings-input" placeholder="paraformer-v2" />
        </div>
      </div>

      <div class="settings-actions">
        <button class="btn btn-secondary" @click="onTest" :disabled="testing">{{ testing ? t('settings.testing') : t('settings.test_connection') }}</button>
        <button class="btn btn-primary" @click="onSave">{{ t('settings.save') }}</button>
      </div>
      <p v-if="testResult" class="settings-test-result" :class="{ 'is-error': testIsError }">{{ testResult }}</p>
    </div>

    <!-- 声纹服务区块已随 REQ-SETTINGS-IA 第 4 刀下架：声纹仅本机 CAM++，无配置面 -->
    </div>

    <!-- ═══ 计算引擎 / Compute engine（R5 资产面；模式为只读回显，唯一写入口在接入方式页） ═══ -->
    <div v-show="activeCategory === 'engine'">
    <!-- 引擎状态 / Engine status -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.engine_status') }}</h2>
      <p class="settings-section-desc">{{ t('settings.engine_status_desc') }}</p>
      <div class="engine-status-panel">
        <div class="engine-status-row">
          <span class="engine-status-label">{{ t('settings.engine_current') }}</span>
          <span class="engine-badge" :class="`is-${engineStore.badge}`"><span class="eb-dot"></span><span class="eb-label">{{ t(`topbar.engine_badge_${engineStore.badge}`) }}</span></span>
        </div>
        <div class="engine-status-row">
          <span class="engine-status-label">{{ t('settings.engine_mode') }}</span>
          <span class="engine-status-value">{{ engineStore.status ? t(`settings.engine_mode_${engineStore.status.mode}`) : '—' }}</span>
        </div>
        <div class="engine-status-row">
          <span class="engine-status-label">{{ t('settings.engine_local_ready') }}</span>
          <span class="engine-status-value" :class="engineStore.status?.local_ready ? 'is-ok' : 'is-warn'">
            {{ engineStore.status?.local_ready ? t('settings.engine_local_ready_yes') : t('settings.engine_local_ready_no') }}
          </span>
        </div>
        <div class="engine-status-row">
          <span class="engine-status-label">{{ t('settings.engine_process') }}</span>
          <span class="engine-status-value" :class="engineStore.status?.process_running ? 'is-ok' : ''">
            {{ engineStore.status?.process_running ? t('settings.engine_process_running', { pid: engineStore.status?.pid ?? '-' }) : t('settings.engine_process_stopped') }}
          </span>
          <template v-if="(userStore.isAdmin || engineStore.canManage)">
            <button v-if="!engineStore.status?.process_running" class="btn btn-primary btn-sm" :disabled="engineBusy" @click="onStartEngine">{{ t('settings.engine_action_start') }}</button>
            <button v-else class="btn btn-secondary btn-sm" :disabled="engineBusy" @click="onStopEngine">{{ t('settings.engine_action_stop') }}</button>
          </template>
        </div>
        <p v-if="engineStore.status?.mode === 'local' && engineStore.status.local_ready && !engineStore.status.process_running" class="engine-ready-hint">{{ t('settings.engine_ready_not_running') }}</p>

        <!-- 引擎模式只读徽章（REQ-SETTINGS-IA 第 2 刀：原可写 dropdown 改只读回显，
             避免参数页静默改写用户选过的接入模式；切换唯一入口在决策卡事务） -->
        <div class="engine-status-row">
          <span class="engine-status-label">{{ t('settings.engine_mode') }}</span>
          <span class="engine-status-value"><span class="ai-mode-badge">{{ engineModeLabel }}</span><span class="engine-mode-readonly-hint">{{ t('settings.engine_mode_readonly') }}</span></span>
        </div>
      </div>

      <!-- dev 四态手工切换（仅开发模式，验证 R6 徽章用） / Dev-only four-state switch (verification aid) -->
      <div v-if="isDev" class="engine-dev-panel">
        <span class="engine-dev-label">DEV {{ t('settings.engine_dev_override') }}</span>
        <div class="engine-dev-btns">
          <button v-for="s in ENGINE_BADGE_STATES" :key="s" class="theme-chip" :class="{ 'is-active': engineStore.devOverride === s }" @click="engineStore.setDevOverride(engineStore.devOverride === s ? null : s)">
            {{ t(`topbar.engine_badge_${s}`) }}
          </button>
          <button class="theme-chip" :class="{ 'is-active': !engineStore.devOverride }" @click="engineStore.setDevOverride(null)">{{ t('settings.engine_dev_auto') }}</button>
        </div>
      </div>
    </div>

    <!-- 本地引擎模型资产（R5） / Local engine model assets (R5) -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.engine_models_title') }}</h2>
      <p class="settings-section-desc">{{ t('settings.engine_models_desc') }}</p>

      <div v-if="!engineStore.overview" class="settings-empty">{{ t('common.loading') }}</div>
      <template v-else>
        <!-- 存储位置与容量提示 / Storage location & capacity hint -->
        <div class="engine-storage-block">
          <label class="settings-label">{{ t('settings.engine_storage') }}</label>
          <div class="engine-storage-controls">
            <input v-model="storageDraft" class="settings-input" :disabled="!(userStore.isAdmin || engineStore.canManage)" />
            <button v-if="(userStore.isAdmin || engineStore.canManage)" class="btn btn-secondary btn-sm" :disabled="storageSaving || storageDraft === engineStore.overview.model_dir" @click="onSaveStorage">{{ t('settings.engine_storage_save') }}</button>
          </div>
          <div class="engine-disk-hint" :class="{ 'is-short': diskShort }">
            <span>{{ t('settings.engine_disk_free', { size: fmtBytes(engineStore.overview.disk_free_bytes) }) }}</span>
            <span class="engine-disk-sep">·</span>
            <span>{{ t('settings.engine_disk_required', { size: fmtBytes(engineStore.overview.total_size_required_bytes), optional: fmtBytes(engineStore.overview.total_size_all_bytes - engineStore.overview.total_size_required_bytes) }) }}</span>
            <span v-if="diskShort" class="engine-disk-short">{{ t('settings.engine_disk_short') }}</span>
          </div>
        </div>

        <!-- 模型清单 / Model manifest -->
        <div class="engine-model-list">
          <div v-for="m in engineStore.overview.models" :key="m.key" class="engine-model-row">
            <div class="engine-model-head">
              <span class="engine-model-name">{{ m.name }}</span>
              <span v-if="m.optional" class="engine-model-optional">{{ t('settings.engine_model_optional') }}</span>
              <span class="engine-model-size">{{ fmtBytes(m.size_bytes) }}</span>
              <span class="engine-model-status" :class="`is-${m.status}`">{{ t(`settings.engine_model_status_${m.status}`) }}</span>
            </div>
            <div class="engine-model-purpose">{{ m.purpose }}</div>
            <!-- 下载中：进度 + 速度 + ETA + 取消 / Downloading: progress + speed + ETA + cancel -->
            <div v-if="m.status === 'downloading' && m.job" class="engine-model-progress">
              <div class="engine-progress-bar" role="progressbar" :aria-valuenow="m.job.percent" aria-valuemin="0" aria-valuemax="100">
                <div class="engine-progress-fill" :style="{ width: m.job.percent + '%' }"></div>
              </div>
              <span class="engine-progress-pct">{{ m.job.percent }}%</span>
              <span class="engine-progress-meta">{{ fmtSpeed(m.job.speed_bps) }}</span>
              <span v-if="m.job.eta_seconds != null" class="engine-progress-meta">{{ t('settings.engine_progress_eta', { eta: fmtDuration(m.job.eta_seconds) }) }}</span>
              <button v-if="(userStore.isAdmin || engineStore.canManage)" class="btn btn-sm btn-secondary" :disabled="busyKey === m.job.id" @click="onCancel(m.job.id)">{{ t('settings.engine_action_cancel') }}</button>
            </div>
            <div v-if="(userStore.isAdmin || engineStore.canManage) && m.status !== 'downloading'" class="engine-model-actions">
              <button v-if="m.status === 'not_downloaded' || m.status === 'missing'" class="btn btn-sm btn-secondary" :disabled="busyKey === m.key" @click="onDownload(m.key)">{{ t('settings.engine_action_download') }}</button>
              <button v-else-if="m.status === 'partial'" class="btn btn-sm btn-secondary" :disabled="busyKey === m.key" @click="onDownload(m.key)">{{ t('settings.engine_action_resume') }}</button>
              <button v-else-if="m.status === 'ready'" class="btn btn-sm btn-secondary" :disabled="busyKey === m.key" @click="onVerify(m.key)">{{ t('settings.engine_action_verify') }}</button>
              <button v-else-if="m.status === 'tampered'" class="btn btn-sm btn-secondary" :disabled="busyKey === m.key" @click="onDownload(m.key)">{{ t('settings.engine_action_redownload') }}</button>
            </div>
          </div>
        </div>

        <!-- 失败任务排错 / Failed job troubleshooting -->
        <div v-for="j in failedJobs" :key="j.id" class="engine-job-failed">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <span>{{ jobErrorText(j) }}</span>
        </div>

        <div class="engine-models-actions">
          <button v-if="(userStore.isAdmin || engineStore.canManage)" class="btn btn-primary btn-sm" :disabled="busyKey === 'all' || engineStore.isDownloading" @click="onDownload('all')">{{ t('settings.engine_download_all') }}</button>
          <button class="btn btn-secondary btn-sm" :disabled="engineStore.overviewLoading" @click="engineStore.loadOverview(true)">{{ t('settings.engine_refresh') }}</button>
        </div>
      </template>
    </div>

    <!-- 数据处理流向矩阵已搬入「接入方式」页（REQ-SETTINGS-IA 第 3 刀：四列用户词、逐能力高亮、
         出网双通道徽章；专家详情开启时显示），本资产页不再重复呈现 -->

    </div>

    <!-- ═══ CLI 引擎 / CLI engine（L4 层，REQ-EXPERT-MODE §2.2：探针三段状态前置回显） ═══ -->
    <div v-show="activeCategory === 'cli'">
      <CliEnginePanel />
    </div>

    <!-- ═══ 转写 / Transcription ═══ -->
    <div v-show="activeCategory === 'transcription'">
    <!-- 说话人分离 / Speaker diarization -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.diarization') }}</h2>
      <p class="settings-section-desc">{{ t('settings.diarization_desc') }}</p>
      <div class="wm-setting-row">
        <label>
          {{ t('settings.diarization_effective') }}
          <span class="toggle-desc">
            {{ diarizationInfo.effective === 'local' ? t('settings.diarization_effective_local') : t('settings.diarization_effective_cloud') }}
          </span>
        </label>
      </div>
      <div class="wm-setting-row">
        <label>
          {{ t('settings.diarization_local_toggle') }}
          <span class="toggle-desc">{{ t('settings.diarization_local_toggle_desc') }}</span>
        </label>
        <div class="wm-toggle-wrap">
          <div
            class="wm-toggle"
            :class="{ 'is-on': diarizationInfo.local_diarization, 'is-disabled': !diarizationInfo.can_toggle }"
            role="switch"
            :aria-checked="diarizationInfo.local_diarization"
            :tabindex="diarizationInfo.can_toggle ? 0 : -1"
            @click="onToggleDiarization"
            @keydown.enter.prevent="onToggleDiarization"
            @keydown.space.prevent="onToggleDiarization"
          ></div>
          <span class="wm-setting-val">{{ diarizationInfo.local_diarization ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
        </div>
        <span v-if="!diarizationInfo.can_toggle" class="toggle-experimental">{{ t('settings.diarization_requires_subscription') }}</span>
      </div>
    </div>

    <!-- 输出目录 / Output directory -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.output_dir') }}</h2>
      <p class="settings-section-desc">{{ t('settings.output_dir_desc') }}</p>
      <div class="settings-field">
        <input v-model="settings.output_dir" class="settings-input" :placeholder="t('settings.output_dir_placeholder')" />
      </div>
    </div>

    <!-- 录音设备 / Recording device -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.recording_device') }}</h2>
      <p class="settings-section-desc">{{ t('settings.recording_device_desc') }}</p>
      <div class="settings-field">
        <select v-model="selectedDevice" class="settings-input" :disabled="devicesLoading">
          <option value="">{{ t('settings.recording_device_auto') }}</option>
          <option v-for="d in audioDevices" :key="d.index" :value="d.name">{{ d.name }}</option>
        </select>
      </div>
      <div class="version-actions">
        <button class="btn btn-secondary btn-sm" @click="loadDevices" :disabled="devicesLoading">
          <svg v-if="devicesLoading" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:4px;animation:spin 1s linear infinite"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
          {{ devicesLoading ? t('settings.recording_device_loading') : t('settings.recording_device_refresh') }}
        </button>
        <span v-if="!devicesLoading && audioDevices.length === 0 && devicesLoaded" class="version-msg is-error">{{ t('settings.recording_device_none') }}</span>
        <span v-if="!devicesLoading && !ffmpegAvailable && devicesLoaded" class="version-msg is-error">{{ t('settings.recording_device_ffmpeg_missing') }}</span>
      </div>
    </div>
    </div>

    <!-- ═══ 外观 / Appearance ═══ -->
    <div v-show="activeCategory === 'appearance'">
    <!-- 主题 / Theme -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.appearance') }}</h2>
      <div class="theme-grid">
        <button
          v-for="theme in THEMES"
          :key="theme.id"
          class="theme-chip"
          :class="{ 'is-active': themeStore.current === theme.id }"
          @click="themeStore.setTheme(theme.id)"
        >{{ t(`common.theme.${theme.id.replace(/-/g, '_')}`) }}</button>
      </div>
    </div>

    <!-- 水印氛围 / Watermark ambiance -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.watermark') }}</h2>
      <p class="settings-section-desc">{{ t('settings.watermark_desc') }}</p>
      <div class="wm-setting-row">
        <label>{{ t('settings.watermark_enabled') }}</label>
        <div class="wm-toggle-wrap">
          <div
            class="wm-toggle"
            :class="{ 'is-on': wmEnabled }"
            role="switch"
            :aria-checked="wmEnabled"
            tabindex="0"
            @click="wmToggle"
            @keydown.enter.prevent="wmToggle"
            @keydown.space.prevent="wmToggle"
          ></div>
          <span class="wm-setting-val">{{ wmEnabled ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
        </div>
      </div>
      <div class="wm-setting-row">
        <label>{{ t('settings.watermark_opacity') }}</label>
        <input type="range" min="10" max="100" step="5" :value="Math.round(wmOpacity * 100)" @input="onWmOpacityInput" />
        <span class="wm-setting-val">{{ Math.round(wmOpacity * 100) }}%</span>
      </div>
    </div>

    <!-- 语言 / Language -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.language') }}</h2>
      <p class="settings-section-desc">{{ t('settings.language_subtitle') }}</p>
      <div class="theme-grid">
        <button
          v-for="lang in LANG_OPTIONS"
          :key="lang.id"
          class="theme-chip"
          :class="{ 'is-active': currentLocale === lang.id }"
          @click="onSwitchLang(lang.id)"
        >{{ lang.label }}</button>
      </div>
    </div>
    </div>

    <!-- ═══ 功能 / Features ═══ -->
    <div v-show="activeCategory === 'features'">
    <!-- 功能开关 / Feature toggles -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.features') }}</h2>
      <p class="settings-section-desc">{{ t('settings.features_desc') }}</p>
      
      <div class="feature-toggles">
        <div class="wm-setting-row">
          <label>
            {{ t('settings.realtime_chapters') }}
            <span class="toggle-desc">{{ t('settings.realtime_chapters_desc') }}</span>
          </label>
          <div class="wm-toggle-wrap">
            <div 
              class="wm-toggle" 
              :class="{ 'is-on': featureFlags.realtime_chapters }" 
              role="switch" 
              :aria-checked="featureFlags.realtime_chapters"
              tabindex="0"
              @click="toggleFlag('realtime_chapters')"
              @keydown.enter.prevent="toggleFlag('realtime_chapters')"
              @keydown.space.prevent="toggleFlag('realtime_chapters')"
            ></div>
            <span class="wm-setting-val">{{ featureFlags.realtime_chapters ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
          </div>
        </div>

        <div class="wm-setting-row">
          <label>
            {{ t('settings.realtime_summary') }}
            <span class="toggle-desc">{{ t('settings.realtime_summary_desc') }}</span>
          </label>
          <div class="wm-toggle-wrap">
            <div 
              class="wm-toggle" 
              :class="{ 'is-on': featureFlags.realtime_summary }" 
              role="switch" 
              :aria-checked="featureFlags.realtime_summary"
              tabindex="0"
              @click="toggleFlag('realtime_summary')"
              @keydown.enter.prevent="toggleFlag('realtime_summary')"
              @keydown.space.prevent="toggleFlag('realtime_summary')"
            ></div>
            <span class="wm-setting-val">{{ featureFlags.realtime_summary ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
          </div>

        </div>

        <div class="wm-setting-row">
          <label>
            {{ t('settings.update_check') }}
            <span class="toggle-desc">{{ t('settings.update_check_desc') }}</span>
          </label>
          <div class="wm-toggle-wrap">
            <div 
              class="wm-toggle" 
              :class="{ 'is-on': featureFlags.update_check }" 
              role="switch" 
              :aria-checked="featureFlags.update_check"
              tabindex="0"
              @click="toggleFlag('update_check')"
              @keydown.enter.prevent="toggleFlag('update_check')"
              @keydown.space.prevent="toggleFlag('update_check')"
            ></div>
            <span class="wm-setting-val">{{ featureFlags.update_check ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
          </div>
        </div>

        <div class="wm-setting-row">
          <label>
            {{ t('settings.voiceprint_auto_match') }}
            <span class="toggle-desc">{{ t('settings.voiceprint_auto_match_desc') }}</span>
            <span class="toggle-experimental">{{ t('settings.experimental') }}</span>
          </label>
          <div class="wm-toggle-wrap">
            <div 
              class="wm-toggle" 
              :class="{ 'is-on': featureFlags.voiceprint_auto_match }" 
              role="switch" 
              :aria-checked="featureFlags.voiceprint_auto_match"
              tabindex="0"
              @click="toggleFlag('voiceprint_auto_match')"
              @keydown.enter.prevent="toggleFlag('voiceprint_auto_match')"
              @keydown.space.prevent="toggleFlag('voiceprint_auto_match')"
            ></div>
            <span class="wm-setting-val">{{ featureFlags.voiceprint_auto_match ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
          </div>
        </div>
      </div>
    </div>
    </div>

    <!-- ═══ 系统 / System ═══ -->
    <div v-show="activeCategory === 'system'">
    <!-- 版本信息 / Version info -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.version_info') }}</h2>
      <p class="settings-section-desc">{{ t('settings.version_info_desc') }}</p>
      <div class="version-panel">
        <div class="version-row">
          <span class="version-label">{{ t('settings.current_version') }}</span>
          <span class="version-value">{{ settingsCurrentVersion || '—' }}</span>
        </div>
        <div v-if="settingsLatestVersion" class="version-row">
          <span class="version-label">{{ t('settings.latest_version') }}</span>
          <span class="version-value" :class="{ 'is-newer': settingsHasUpdate }">{{ settingsLatestVersion }}</span>
        </div>
        <div class="version-actions">
          <button class="btn btn-secondary btn-sm" @click="onManualCheck" :disabled="settingsChecking">
            <svg v-if="settingsChecking" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:4px;animation:spin 1s linear infinite"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            {{ settingsChecking ? t('settings.checking_update') : t('settings.check_update_btn') }}
          </button>
          <a v-if="settingsHasUpdate && settingsReleaseUrl" class="btn btn-primary btn-sm" :href="settingsReleaseUrl" target="_blank" rel="noopener" style="margin-left:8px">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:4px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            {{ settingsDownloadLabel ? t('settings.download_for_platform', { platform: settingsDownloadLabel }) : t('settings.go_to_download') }}
          </a>
          <span v-if="settingsCheckMessage" class="version-msg" :class="{ 'is-error': settingsCheckError }">{{ settingsCheckMessage }}</span>
        </div>
      </div>
    </div>

    <!-- CLI 命令参考 / CLI command reference -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.cli_reference') }}</h2>
      <p class="settings-section-desc">{{ t('settings.cli_reference_desc') }}</p>
      <div class="cli-ref-list">
        <template v-for="(val, key) in cliReference" :key="key">
          <div v-if="typeof val === 'string'" class="cli-ref-item">
            <span class="cli-ref-cmd">{{ key }}</span>
            <code>{{ val }}</code>
          </div>
          <div v-else-if="typeof val === 'object'" class="cli-ref-group">
            <div class="cli-ref-group-title">{{ key }}</div>
            <div v-for="(subVal, subKey) in (val as Record<string, string>)" :key="subKey" class="cli-ref-item">
              <span class="cli-ref-cmd">{{ subKey }}</span>
              <code>{{ subVal }}</code>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 键盘快捷键参考 / Keyboard shortcut reference -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.keyboard_shortcuts') }}</h2>
      <p class="settings-section-desc">{{ t('settings.keyboard_shortcuts_desc') }}</p>
      <div class="kbd-shortcut-list">
        <div v-for="s in shortcutList" :key="s.key" class="kbd-shortcut-item">
          <span class="kbd-shortcut-label">{{ s.label }}</span>
          <kbd class="kbd-shortcut-key">{{ s.key }}</kbd>
        </div>
      </div>
    </div>

    <!-- 重新加载页面 / Reload page -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.reload_page') }}</h2>
      <p class="settings-section-desc">{{ t('settings.reload_page_desc') }}</p>
      <button class="btn btn-secondary" @click="onReloadPage">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:4px"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
        {{ t('settings.reload_page_btn') }}
      </button>
    </div>

    <!-- 禁用快捷指令 / Disabled commands -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.disabled_commands') }}</h2>
      <p class="settings-section-desc">{{ t('settings.disabled_commands_desc') }}</p>
      <div v-if="!settings.disabled_commands?.length" class="settings-empty">{{ t('settings.no_disabled_commands') }}</div>
      <div v-else class="disabled-cmd-list">
        <div v-for="cmd in settings.disabled_commands" :key="cmd" class="disabled-cmd-item">
          <code>{{ cmd }}</code>
          <button class="btn btn-sm btn-secondary" @click="onEnableCommand(cmd)">{{ t('settings.command_enable') }}</button>
        </div>
      </div>
    </div>

    <!-- 存储空间 / Storage -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.storage') }}</h2>
      <p class="settings-section-desc">{{ t('settings.storage_desc') }}</p>

      <div v-if="storageLoading" class="settings-empty">{{ t('common.loading') }}</div>
      <div v-else-if="storageUsage" class="storage-panel">
        <!-- 总览 / Overview -->
        <div class="storage-overview">
          <div class="storage-stat">
            <div class="storage-stat-value">{{ formatBytes(storageUsage.total_bytes) }}</div>
            <div class="storage-stat-label">{{ t('settings.storage_total') }}</div>
          </div>
          <div class="storage-stat">
            <div class="storage-stat-value" style="color:var(--accent)">{{ formatBytes(storageUsage.reclaimable_bytes) }}</div>
            <div class="storage-stat-label">{{ t('settings.storage_reclaimable') }}</div>
          </div>
        </div>

        <!-- 分类明细 / Category breakdown -->
        <div class="storage-breakdown">
          <div class="storage-breakdown-item">
            <span class="storage-breakdown-label">{{ t('settings.storage_recordings') }}</span>
            <span class="storage-breakdown-value">{{ formatBytes(storageUsage.recordings.size_bytes) }} <small>({{ storageUsage.recordings.file_count }})</small></span>
          </div>
          <div class="storage-breakdown-item">
            <span class="storage-breakdown-label">{{ t('settings.storage_uploads') }}</span>
            <span class="storage-breakdown-value">{{ formatBytes(storageUsage.uploads.size_bytes) }} <small>({{ storageUsage.uploads.file_count }})</small></span>
          </div>
          <div class="storage-breakdown-item">
            <span class="storage-breakdown-label">{{ t('settings.storage_tasks') }}</span>
            <span class="storage-breakdown-value">{{ formatBytes(storageUsage.tasks.size_bytes) }} <small>({{ storageUsage.tasks.file_count }})</small></span>
          </div>
          <div class="storage-breakdown-item">
            <span class="storage-breakdown-label">{{ t('settings.storage_output') }}</span>
            <span class="storage-breakdown-value">{{ formatBytes(storageUsage.output.size_bytes) }} <small>({{ storageUsage.output.file_count }})</small></span>
          </div>
        </div>

        <!-- 中间产物 / Intermediate files -->
        <div v-if="storageUsage.intermediate" class="storage-intermediate">
          <div class="storage-intermediate-title">{{ t('settings.storage_intermediate') }}</div>
          <div class="storage-breakdown-item">
            <span class="storage-breakdown-label">{{ t('settings.storage_normalized') }}</span>
            <span class="storage-breakdown-value">{{ formatBytes(storageUsage.intermediate.normalized_files.size_bytes) }} <small>({{ storageUsage.intermediate.normalized_files.file_count }})</small></span>
          </div>
          <div class="storage-breakdown-item">
            <span class="storage-breakdown-label">{{ t('settings.storage_raw_files') }}</span>
            <span class="storage-breakdown-value">{{ formatBytes(storageUsage.intermediate.raw_files.size_bytes) }} <small>({{ storageUsage.intermediate.raw_files.file_count }})</small></span>
          </div>
          <div class="storage-breakdown-item">
            <span class="storage-breakdown-label">{{ t('settings.storage_duplicate') }}</span>
            <span class="storage-breakdown-value">{{ formatBytes(storageUsage.intermediate.duplicate_normalized.size_bytes) }} <small>({{ storageUsage.intermediate.duplicate_normalized.file_count }})</small></span>
          </div>
        </div>

        <!-- 操作按钮 / Action buttons -->
        <div class="storage-actions">
          <button class="btn btn-secondary" @click="onCleanIntermediate" :disabled="cleaning">
            {{ cleaning ? t('settings.storage_cleaning') : t('settings.storage_clean_btn') }}
          </button>
          <button class="btn btn-secondary" @click="onCleanOrphaned" :disabled="cleaning">
            {{ cleaning ? t('settings.storage_cleaning') : t('settings.storage_clean_orphaned_btn') }}
          </button>
          <button class="btn btn-sm btn-secondary" @click="onRefreshStorage" :disabled="storageLoading" style="margin-left:auto">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            {{ t('common.action.refresh') }}
          </button>
        </div>
        <p v-if="cleanResult" class="storage-clean-result">{{ cleanResult }}</p>

        <!-- 自动归档设置 / Auto-archive settings -->
        <div class="storage-auto-archive">
          <div class="wm-setting-row">
            <label>
              {{ t('settings.storage_auto_clean') }}
            </label>
            <div class="wm-toggle-wrap">
              <div 
                class="wm-toggle" 
                :class="{ 'is-on': storageConfig.auto_clean_intermediate }" 
                role="switch" 
                :aria-checked="storageConfig.auto_clean_intermediate"
                tabindex="0"
                @click="storageConfig.auto_clean_intermediate = !storageConfig.auto_clean_intermediate"
                @keydown.enter.prevent="storageConfig.auto_clean_intermediate = !storageConfig.auto_clean_intermediate"
                @keydown.space.prevent="storageConfig.auto_clean_intermediate = !storageConfig.auto_clean_intermediate"
              ></div>
              <span class="wm-setting-val">{{ storageConfig.auto_clean_intermediate ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
            </div>
          </div>
          <div class="wm-setting-row" style="margin-top:var(--s-3)">
            <label>
              {{ t('settings.storage_auto_archive') }}
              <span class="toggle-desc">{{ t('settings.storage_auto_archive_desc') }}</span>
            </label>
            <select v-model="storageConfig.auto_archive_days" class="settings-input" style="max-width:160px;padding:4px 8px;font-size:12px">
              <option :value="0">{{ t('settings.storage_auto_archive_off') }}</option>
              <option :value="7">7 {{ t('settings.storage_days') }}</option>
              <option :value="30">30 {{ t('settings.storage_days') }}</option>
              <option :value="90">90 {{ t('settings.storage_days') }}</option>
              <option :value="180">180 {{ t('settings.storage_days') }}</option>
            </select>
          </div>
        </div>
      </div>
    </div>
    </div>

    </div><!-- .settings-content -->

    <!-- 首次启用本地引擎引导弹窗（磁盘预检 / 权重缺失 / 校验失败排错）；
         视图级挂载：接入方式页切换失败直达与引擎页共用 -->
    <LocalEngineGuideDialog
      :open="guideOpen"
      :disk-free-bytes="engineStore.overview?.disk_free_bytes ?? 0"
      :disk-required-bytes="engineStore.overview?.total_size_required_bytes ?? 0"
      :disk-buffer-bytes="DISK_BUFFER_BYTES"
      :missing="engineStore.requiredNotReady"
      :tampered="engineStore.tamperedModels"
      @close="guideOpen = false"
      @download-all="onGuideDownloadAll"
    />
  </div><!-- .settings-layout -->
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useThemeStore, THEMES } from '@/stores/theme'
import { useWatermarkStore } from '@/stores/watermark'
import { useTaskStore } from '@/stores/task'
import { useEngineStore } from '@/stores/engine'
import type { EngineBadgeState } from '@/stores/engine'
import type { DownloadJob } from '@/api/engine'
import LocalEngineGuideDialog from '@/components/modals/LocalEngineGuideDialog.vue'
import AccessModeCards from '@/components/settings/AccessModeCards.vue'
import CliEnginePanel from '@/components/settings/CliEnginePanel.vue'
import { showToast } from '@/composables/useToast'
import { fetchSettings, saveSettings, testApiConnection, fetchCliReference, probeLocalEngine } from '@/api/settings'
import type { Settings, FeatureFlags, ProviderPreset, LocalEngineProbe, LocalEngineProbeResult } from '@/api/settings'
import { fetchUsageSummary, fetchUsageHistory, updateUserPrefs } from '@/api/usage'
import type { UsageSummary, UsageHistoryItem } from '@/api/usage'
import { fetchStorageUsage, cleanIntermediateFiles, cleanOrphanedFiles } from '@/api/storage'
import type { StorageUsage } from '@/api/storage'
import { fetchAudioDevices, setRecordDevice } from '@/api/record'
import type { AudioDevice } from '@/api/record'
import { setI18nLocale, getLocale, type SupportedLocale } from '@/i18n'
import { usePageBack } from '@/composables/usePageBack'
import { modKey } from '@/utils/platform'
import { useUpdateCheck } from '@/composables/useUpdateCheck'

const { t, te } = useI18n()
const { goBack } = usePageBack()
const route = useRoute()
const userStore = useUserStore()
const themeStore = useThemeStore()
const watermarkStore = useWatermarkStore()
const taskStore = useTaskStore()
const engineStore = useEngineStore()

// 版本检查 / Version check
const {
  checking: updateChecking,
  hasUpdate: updateHasUpdate,
  latestVersion: updateLatestVersion,
  currentVersion: updateCurrentVersion,
  releaseUrl: updateReleaseUrl,
  downloadUrl: updateDownloadUrl,
  downloadPlatformLabel: updateDownloadPlatformLabel,
  checkError: updateCheckError,
  manualCheck: updateManualCheck,
  loadCurrentVersion: updateLoadCurrentVersion,
  resetDismiss: updateResetDismiss,
} = useUpdateCheck()

const settingsChecking = computed(() => updateChecking.value)
const settingsHasUpdate = computed(() => updateHasUpdate.value)
const settingsCurrentVersion = computed(() => updateCurrentVersion.value)
const settingsLatestVersion = computed(() => updateLatestVersion.value)
const settingsReleaseUrl = computed(() => updateDownloadUrl.value || updateReleaseUrl.value)
const settingsDownloadLabel = computed(() => updateDownloadPlatformLabel.value)
const settingsCheckError = computed(() => !!updateCheckError.value)
const settingsCheckMessage = computed(() => {
  if (updateCheckError.value) return t('settings.check_update_error')
  if (updateChecking.value) return ''
  if (updateHasUpdate.value) return t('settings.update_available_settings', { version: updateLatestVersion.value })
  if (updateLatestVersion.value) return t('settings.is_latest')
  return ''
})

async function onManualCheck() {
  updateResetDismiss()
  await updateManualCheck()
}

// ─── 录音设备选择 / Recording device selection ───
const audioDevices = ref<AudioDevice[]>([])
const selectedDevice = ref('')
const devicesLoading = ref(false)
const devicesLoaded = ref(false)
const ffmpegAvailable = ref(true)

async function loadDevices() {
  devicesLoading.value = true
  try {
    const result = await fetchAudioDevices()
    audioDevices.value = result.devices
    ffmpegAvailable.value = result.ffmpeg_available
    // 如果后端已有配置的设备，回显到下拉框
    // If backend has a configured device, reflect it in the dropdown
    if (result.current_device) {
      // 回显赋值前置位显式标志：watch 仅放行这一次赋值，其余变更一律 POST（DEF-DEVICE-01-A）
      echoDeviceValue = result.current_device
      selectedDevice.value = result.current_device
    }
    devicesLoaded.value = true
  } catch (e) {
    console.error('load audio devices failed:', e)
    devicesLoaded.value = true
  } finally {
    devicesLoading.value = false
  }
}

// 设备选择变更时立即应用到后端 / Apply device selection to backend immediately on change
// 旧「首次触发=回显」守卫在 current_device 为空时会吞掉用户第一次真实选择（DEF-DEVICE-01），
// 改为显式标志：仅当本次变更正是 loadDevices 刚写入的回显值时跳过一次 POST。
let echoDeviceValue: string | null = null
watch(selectedDevice, async (newVal) => {
  if (newVal === echoDeviceValue) {
    echoDeviceValue = null
    return
  }
  try {
    await setRecordDevice(newVal)
  } catch (e) {
    console.error('set record device failed:', e)
  }
})

/** 当前选中的设置类别（支持 ?cat= 深链；A3：状态栏/徽章统一跳 ?cat=access） / Active settings category (deep link) */
const SETTINGS_CATEGORIES = ['access', 'account', 'services', 'engine', 'cli', 'transcription', 'appearance', 'features', 'system']
const queryCat = typeof route.query.cat === 'string' ? route.query.cat : ''
const queryTab = typeof route.query.tab === 'string' ? route.query.tab : ''
const deepLinkCat = SETTINGS_CATEGORIES.includes(queryCat) ? queryCat : (SETTINGS_CATEGORIES.includes(queryTab) ? queryTab : '')
const activeCategory = ref<string>(deepLinkCat || 'access')

/**
 * 详情卡「在服务页编辑 / 直达资产清单」导航（REQ-SETTINGS-IA 第 2 刀：参数编辑面收敛一处）。
 * 专家开关不再控制分类可见性（废除「平行旧版视图」形态）。
 */
function onAccessGoto(category: 'services' | 'engine') {
  if (SETTINGS_CATEGORIES.includes(category)) activeCategory.value = category
}

/** 切换事务因模型缺失/磁盘不足/校验失败回滚 → 直达本地引擎引导弹窗（不静默半启动态） */
async function onGuideRequest() {
  await engineStore.loadOverview(true)
  guideOpen.value = true
}

/** 联网态下 ASR 来源只读回显（写入口在接入方式详情层） */
const asrSourceLabel = computed(() => {
  const src = engineStore.capability?.asr?.effective || settings.asr?.mode || ''
  if (src === 'trial' || src === 'proxy') return t('settings.access.src_trial')
  if (src === 'byok' || src === 'direct') return t('settings.access.src_byok')
  if (src === 'local') return t('settings.access.src_local')
  return src || '—'
})

// ─── 计算引擎（R5 资产面；模式只读回显） / Compute engine (R5 assets; mode read-only) ───
const isDev = import.meta.env.DEV
const ENGINE_BADGE_STATES: EngineBadgeState[] = ['local', 'proxy', 'selfkey', 'unready']

/** 引擎模式只读标签（五词表；工程值仅悬停提示） */
const engineModeLabel = computed(() => {
  const mode = engineStore.status?.mode || ''
  if (mode === 'local') return t('settings.engine_mode_local')
  if (mode === 'proxy' || mode === 'cloud') return t('settings.engine_mode_proxy')
  if (mode === 'direct') return t('settings.engine_mode_direct')
  return mode || '—'
})

// ─── R5 模型资产管理 / R5 model asset management ───
/** 与后端 core/model_downloader.DISK_BUFFER_BYTES 对齐（500MB 磁盘缓冲） / Mirrors backend DISK_BUFFER_BYTES (500MB) */
const DISK_BUFFER_BYTES = 500 * 1024 * 1024

const storageDraft = ref('')
const storageSaving = ref(false)
const busyKey = ref('')
const engineBusy = ref(false)
const guideOpen = ref(false)

/** 磁盘预检：剩余空间 < 必装体积 + 缓冲 / Disk precheck: free < required + buffer */
const diskShort = computed(() => {
  const o = engineStore.overview
  if (!o) return false
  return o.disk_free_bytes < o.total_size_required_bytes + DISK_BUFFER_BYTES
})

/** 失败任务（排错文案展示） / Failed jobs (troubleshooting rows) */
const failedJobs = computed(() => engineStore.jobs.filter(j => j.state === 'failed'))

// 存储位置回显（overview 加载/刷新后同步草稿） / Reflect storage dir into draft after overview loads
watch(() => engineStore.overview?.model_dir, (dir) => {
  if (dir && !storageSaving.value) storageDraft.value = dir
}, { immediate: true })

/** error_code → i18n 排错文案（下载/校验/启停/存储共用） / error_code → i18n troubleshooting text (shared) */
function engineErrText(code?: string | null, error?: string | null): string {
  const map: Record<string, string> = {
    insufficient_disk: 'settings.engine_err_insufficient_disk',
    unwritable_dir: 'settings.engine_err_unwritable_dir',
    unknown_model: 'settings.engine_err_unknown_model',
    invalid_request: 'settings.engine_err_generic',
    models_tampered: 'settings.engine_err_models_tampered',
    models_missing: 'settings.engine_err_models_missing',
    download_failed: 'settings.engine_err_download_failed',
  }
  const key = code ? map[code] : undefined
  if (key && key !== 'settings.engine_err_generic') return t(key)
  return t('settings.engine_err_generic', { error: error || code || '-' })
}

function jobErrorText(j: DownloadJob): string {
  return engineErrText(j.error_code, j.error)
}

function fmtBytes(bytes: number): string { return formatBytes(bytes) }

function fmtSpeed(bps: number): string { return `${fmtBytes(bps)}/s` }

function fmtDuration(sec: number): string {
  if (sec == null || !isFinite(sec)) return '—'
  if (sec < 60) return `${Math.max(1, Math.round(sec))}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}m${Math.round(sec % 60)}s`
  return `${Math.floor(sec / 3600)}h${Math.round((sec % 3600) / 60)}m`
}

async function onDownload(key: string) {
  busyKey.value = key
  try {
    const r = await engineStore.download(key)
    if (!r.ok) showToast(engineErrText(r.error_code, r.error), 'error')
  } catch (e) {
    showToast(engineErrText(null, String(e)), 'error')
  } finally {
    busyKey.value = ''
  }
}

async function onCancel(jobId: string) {
  busyKey.value = jobId
  try {
    const r = await engineStore.cancel(jobId)
    if (!r.ok) showToast(engineErrText(r.error_code, r.error), 'error')
  } catch (e) {
    showToast(engineErrText(null, String(e)), 'error')
  } finally {
    busyKey.value = ''
  }
}

async function onVerify(key: string) {
  busyKey.value = key
  try {
    const r = await engineStore.verify(key)
    if (r.ok && r.status !== 'tampered') showToast(t('settings.engine_verify_ok'), 'success')
    else if (r.status === 'tampered') showToast(t('settings.engine_verify_tampered'), 'error')
    else showToast(engineErrText(r.error_code, r.error), 'error')
  } catch (e) {
    showToast(engineErrText(null, String(e)), 'error')
  } finally {
    busyKey.value = ''
  }
}

async function onSaveStorage() {
  const dir = storageDraft.value.trim()
  if (!dir) return
  storageSaving.value = true
  try {
    const r = await engineStore.saveStorage(dir)
    if (r.ok) showToast(t('settings.engine_storage_saved'), 'success')
    else showToast(engineErrText(r.error_code, r.error), 'error')
  } catch (e) {
    showToast(t('settings.engine_storage_failed'), 'error')
  } finally {
    storageSaving.value = false
  }
}

async function onStartEngine() {
  engineBusy.value = true
  try {
    const r = await engineStore.start()
    if (r.ok) {
      showToast(t('settings.engine_started'), 'success')
    } else if (r.error_code === 'models_tampered' || r.error_code === 'models_missing') {
      // 篡改拒载 / 权重缺失 → 打开引导弹窗排错 / Tamper rejection or missing weights → open guide dialog
      await engineStore.loadOverview(true)
      guideOpen.value = true
    } else {
      showToast(engineErrText(r.error_code, r.error), 'error')
    }
  } catch (e) {
    showToast(t('settings.engine_start_failed'), 'error')
  } finally {
    engineBusy.value = false
  }
}

async function onStopEngine() {
  engineBusy.value = true
  try {
    const r = await engineStore.stop()
    if (r.ok) showToast(t('settings.engine_stopped'), 'success')
    else showToast(engineErrText(r.error_code, r.error), 'error')
  } catch (e) {
    showToast(t('settings.engine_stop_failed'), 'error')
  } finally {
    engineBusy.value = false
  }
}

function onGuideDownloadAll() {
  guideOpen.value = false
  onDownload('all')
}

// ─── 水印氛围 / Watermark ambiance ───
const wmEnabled = computed(() => watermarkStore.enabled)
const wmOpacity = computed(() => watermarkStore.opacity)

function wmToggle() {
  watermarkStore.toggle()
}

function onWmOpacityInput(e: Event) {
  const val = Number((e.target as HTMLInputElement).value)
  watermarkStore.setOpacity(val / 100)
}
// DEF-02: 补全嵌套空对象，避免 fetchSettings() 返回前模板非空断言触发 TypeError
// DEF-02: Pre-fill nested objects so template non-null assertions are safe before async load
const settings = reactive<Settings>({ llm: {}, asr: {} })
const testing = ref(false)
const testResult = ref('')
const testIsError = ref(false)

/** LLM Provider 预设列表（从后端加载） / LLM Provider preset list (loaded from backend) */
const llmPresets = computed<ProviderPreset[]>(() => settings.llm_provider_presets || [
  { name: 'DashScope（通义千问）', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen-plus', 'qwen-max', 'qwen-turbo'] },
  { name: 'OpenAI', base_url: 'https://api.openai.com/v1', models: ['gpt-4o', 'gpt-4o-mini'] },
  { name: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', models: ['deepseek-chat', 'deepseek-reasoner'] },
  { name: '自定义', base_url: '', models: [] },
])

// ─── 本地引擎自动探测（§7.2-4） / Local engine auto-probe (§7.2-4) ───
/** 探测结果；null 表示尚未探测 / Probe result; null means not probed yet */
const localProbe = ref<LocalEngineProbeResult | null>(null)
const probeLoading = ref(false)

/** 本机地址判定（与后端 is_localhost_base_url 对齐） / Localhost check (mirrors backend) */
function isLocalUrl(url?: string): boolean {
  if (!url) return false
  return /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/i.test(url)
}

/** 按 base_url 匹配探测引擎记录 / Match a probed engine record by base_url */
function engineForBase(base?: string): LocalEngineProbe | undefined {
  if (!base || !localProbe.value) return undefined
  return localProbe.value.engines.find(e => e.base_url === base)
}

const selectedPreset = computed<ProviderPreset | undefined>(
  () => llmPresets.value.find(p => p.name === settings.llm?.provider)
)

/** 当前是否选中本机端点 / Whether a localhost endpoint is selected */
const selectedIsLocal = computed<boolean>(
  () => selectedPreset.value?.localhost === true || isLocalUrl(settings.llm?.base_url)
)

/** 探测到可达本地预设后置顶排序（稳定排序，保留其余原序） / Pin detected local presets to top (stable) */
const llmPresetsOrdered = computed<ProviderPreset[]>(() => {
  const list = [...llmPresets.value]
  if (!localProbe.value) return list
  const detected = new Set<string>()
  for (const e of localProbe.value.engines) {
    if (e.reachable) {
      const p = list.find(pp => pp.base_url === e.base_url)
      if (p) detected.add(p.name)
    }
  }
  return list.sort((a, b) => (detected.has(a.name) ? 0 : 1) - (detected.has(b.name) ? 0 : 1))
})

/** 下拉标签：本地预设追加检测状态后缀 / Dropdown label with detection suffix for local presets */
function presetLabel(p: ProviderPreset): string {
  if (!p.localhost || !localProbe.value) return p.name
  const e = engineForBase(p.base_url)
  if (e?.reachable) return `${p.name} · ${t('settings.llm_probe_detected')}`
  return `${p.name} · ${t('settings.llm_probe_unavailable')}`
}

/** 不可达本地预设置灰（保留当前已选项可选） / Grey out unreachable local presets (keep current selectable) */
function isPresetDisabled(p: ProviderPreset): boolean {
  if (!p.localhost || !localProbe.value) return false
  if (p.name === settings.llm?.provider) return false
  return !engineForBase(p.base_url)?.reachable
}

/** 不可达本地端点的安装指引链接 / Install-guide URL for an unreachable local endpoint */
const selectedInstallUrl = computed<string>(() => {
  if (!selectedIsLocal.value) return ''
  const e = engineForBase(settings.llm?.base_url)
  return e && !e.reachable ? e.install_url : ''
})

/** model 下拉候选：优先探测到的本地模型，其次预设建议模型 / Model options: probed local models first, then preset suggestions */
const modelOptions = computed<string[]>(() => {
  const e = engineForBase(settings.llm?.base_url)
  if (e?.reachable && e.models.length) return e.models
  return selectedPreset.value?.models || []
})

/** 是否已回填本地模型（用于提示文案） / Whether probed local models were loaded */
const probeModelsLoaded = computed<boolean>(() => {
  const e = engineForBase(settings.llm?.base_url)
  return !!(e?.reachable && e.models.length)
})

/** 执行本地引擎探测（仅 localhost，失败静默） / Run local engine probe (localhost only, silent on failure) */
async function runLocalProbe() {
  probeLoading.value = true
  try {
    localProbe.value = await probeLocalEngine()
  } catch (e) {
    console.error('probe local engine failed:', e)
    localProbe.value = null
  } finally {
    probeLoading.value = false
  }
}

/** 本地端点占位 Key（无需真实密钥） / Placeholder key for local endpoints (no real key needed) */
const LOCAL_PLACEHOLDER_KEYS = ['ollama', 'lm-studio']
function placeholderKeyFor(p: ProviderPreset): string {
  return p.name.includes('LM Studio') ? 'lm-studio' : 'ollama'
}

/**
 * Provider 切换时自动填充 Base URL；本地预设无真实 Key 时自动填占位 Key（§7.2-5）。
 * 切回云端预设时清除遗留占位，避免占位被误存为真实云端 Key。
 * Auto-fill Base URL on provider change; fill a placeholder key for local presets when no real key
 * exists (§7.2-5). Clear any leftover placeholder when switching back to a cloud preset so it is
 * never persisted as a bogus cloud key.
 */
function onLlmProviderChange() {
  const preset = llmPresets.value.find(p => p.name === settings.llm?.provider)
  if (!preset) return
  if (preset.base_url) {
    settings.llm!.base_url = preset.base_url
  }
  const cur = settings.llm!.api_key || ''
  const isPlaceholder = LOCAL_PLACEHOLDER_KEYS.includes(cur)
  if (preset.localhost) {
    // 本地端点无需真实密钥：无真实 Key（或已是占位）时填占位 / No real key (or already a placeholder): fill placeholder
    if (!settings.llm!.api_key_set || isPlaceholder) {
      settings.llm!.api_key = placeholderKeyFor(preset)
    }
  } else if (isPlaceholder) {
    // 切回云端：清除遗留占位 / Switching to cloud: clear leftover placeholder
    settings.llm!.api_key = ''
  }
}

const featureFlags = reactive<FeatureFlags>({
  realtime_chapters: true,
  realtime_summary: true,
  realtime_summary_interval: 60,
  update_check: true,
  voiceprint_auto_match: false,
})

const usageSummary = reactive<UsageSummary>({ metered: false })
const usageHistory = ref<UsageHistoryItem[]>([])

// ─── 优先使用订阅流量 / Prefer subscription quota ───
const preferSubscription = ref(false)

async function onTogglePreferSubscription() {
  preferSubscription.value = !preferSubscription.value
  try {
    await updateUserPrefs({ prefer_subscription: preferSubscription.value })
  } catch (e) {
    // 回滚 / Rollback on failure
    preferSubscription.value = !preferSubscription.value
    console.error('Failed to update prefer_subscription:', e)
  }
}

// ─── 声纹 / 分离 / 输出目录 / Voiceprint / Diarization / Output dir ───
const diarizationInfo = reactive({
  subscription_tier: 'free',
  local_diarization: true,
  effective: 'local',
  can_toggle: false,
})

function onToggleDiarization() {
  if (!diarizationInfo.can_toggle) return
  diarizationInfo.local_diarization = !diarizationInfo.local_diarization
  saveSettings({ diarization: { local_diarization: diarizationInfo.local_diarization } } as any)
}

// ─── CLI 参考 / CLI reference ───
const cliReference = reactive<Record<string, unknown>>({})

// ─── 键盘快捷键参考 / Keyboard shortcut reference ───
const shortcutList = computed(() => [
  { key: `${modKey}B`, label: t('settings.shortcut_toggle_sidebar') },
  { key: `${modKey}J`, label: t('settings.shortcut_toggle_ai') },
  { key: `${modKey}K`, label: t('settings.shortcut_focus_search') },
  { key: `${modKey}N`, label: t('settings.shortcut_new_meeting') },
  { key: `${modKey}R`, label: t('settings.shortcut_start_recording') },
  { key: `${modKey}U`, label: t('settings.shortcut_upload_audio') },
  { key: 'F5', label: t('settings.shortcut_reload') },
  { key: 'ESC', label: t('settings.shortcut_close_dialog') },
])

// ─── 重新加载页面 / Reload page ───
function onReloadPage() {
  const now = Date.now()
  const oneDayAgo = now - 24 * 60 * 60 * 1000
  const hasRecording = taskStore.tasks.some(t => {
    if (t.status !== 'recording' && t.status !== 'paused') return false
    if (t.created_at) {
      const created = new Date(t.created_at).getTime()
      if (created < oneDayAgo) return false
    }
    return true
  })
  if (hasRecording) {
    if (!window.confirm(t('common.reload_recording_confirm'))) return
  }
  window.location.reload()
}

// ─── 禁用指令 / Disabled commands ───
function onEnableCommand(cmd: string) {
  if (!settings.disabled_commands) return
  settings.disabled_commands = settings.disabled_commands.filter(c => c !== cmd)
  saveSettings({ disabled_commands: settings.disabled_commands })
}

function tierName(tier?: string) {
  // 去写死（REQ-EXPERT-MODE §2.2）：读账户真实档位，未来付费档接入即正确显示；
  // 未知档位降级显示原始 tier 值，不再恒返「体验期」说谎。
  const key = `settings.tier_names.${tier || 'free'}`
  return te(key) ? t(key) : (tier || t('settings.tier_names.free'))
}

// ─── 语言切换 / Language switch ───
const LANG_OPTIONS: { id: SupportedLocale; label: string }[] = [
  { id: 'zh-CN', label: '简体中文' },
  { id: 'en', label: 'English' },
]
const currentLocale = computed(() => getLocale())

async function onSwitchLang(locale: SupportedLocale) {
  await setI18nLocale(locale)
}

function formatMinutes(min: number): string {
  if (min >= 60) {
    const h = Math.floor(min / 60)
    const m = Math.round(min % 60)
    return m > 0 ? `${h}h${m}m` : `${h}h`
  }
  return Math.round(min) + 'm'
}

const progressStyle = computed(() => {
  const used = usageSummary.used || 0
  const quota = usageSummary.quota || 1
  const pct = Math.round(used / quota * 100)
  let color = 'oklch(55% 0.15 155)'
  if (pct > 80) color = 'oklch(55% 0.2 25)'
  else if (pct > 50) color = 'oklch(65% 0.16 80)'
  return { width: Math.min(pct, 100) + '%', background: color }
})

const maxHistoryMinutes = computed(() => {
  if (!usageHistory.value.length) return 1
  return Math.max(...usageHistory.value.map(d => d.minutes), 1)
})

function barHeight(minutes: number): number {
  return Math.max(2, Math.round(minutes / maxHistoryMinutes.value * 56))
}

function showLogin() {
  window.dispatchEvent(new CustomEvent('oms:show-login'))
}

async function onLogout() {
  await userStore.logout()
}

async function onSave() {
  await saveSettings({
    asr: { ...settings.asr },
    llm: { ...settings.llm },
    output_dir: settings.output_dir,
    feature_flags: { ...featureFlags },
    storage: { ...storageConfig },
  })
  alert(t('settings.saved'))
}

async function onTest() {
  testing.value = true
  testResult.value = ''
  try {
    // 测试 ASR 连接（传递当前模式配置） / Test ASR connection (pass current mode config)
    const asrParams = {
      service_type: 'asr',
      asr: {
        mode: settings.asr?.mode || 'proxy',
        base_url: settings.asr?.base_url,
        api_key: settings.asr?.api_key,
      },
    }
    const asrRes = await testApiConnection(asrParams)
    const asrOk = asrRes.ok ?? asrRes.success
    const asrMsg = asrRes.message || asrRes.error || ''

    // 测试 LLM 连接 / Test LLM connection
    const llmParams = {
      service_type: 'llm',
      llm: {
        base_url: settings.llm?.base_url,
        api_key: settings.llm?.api_key,
        model: settings.llm?.model,
      },
    }
    const llmRes = await testApiConnection(llmParams)
    const llmOk = llmRes.ok ?? llmRes.success
    const llmMsg = llmRes.message || llmRes.error || ''

    // 合并结果 / Merge results
    const parts: string[] = []
    if (asrOk) {
      parts.push(`ASR: ${asrMsg || t('settings.connection_success')}`)
    } else {
      parts.push(`ASR: ${asrMsg || t('settings.connection_failed')}`)
    }
    if (llmOk) {
      parts.push(`LLM: ${llmMsg || t('settings.connection_success')}`)
    } else {
      parts.push(`LLM: ${llmMsg || t('settings.connection_failed')}`)
    }
    testResult.value = parts.join(' | ')
    testIsError.value = !asrOk || !llmOk
  } catch {
    testResult.value = t('settings.connection_failed')
    testIsError.value = true
  } finally {
    testing.value = false
  }
}

function toggleFlag(key: keyof FeatureFlags) {
  if (key === 'realtime_summary_interval') return
  featureFlags[key] = !featureFlags[key] as boolean
  saveFeatureFlags()
}



async function saveFeatureFlags() {
  await saveSettings({ feature_flags: { ...featureFlags } })
}

// ─── 存储管理 / Storage management ───
const storageUsage = ref<StorageUsage | null>(null)
const storageLoading = ref(false)
const cleaning = ref(false)
const cleanResult = ref('')
const storageConfig = reactive({
  auto_clean_intermediate: true,
  auto_archive_days: 0,
})

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  const val = bytes / Math.pow(1024, i)
  return `${val.toFixed(i > 0 ? 1 : 0)} ${units[i]}`
}

async function loadStorageUsage() {
  storageLoading.value = true
  try {
    storageUsage.value = await fetchStorageUsage()
  } catch (e) {
    console.error('[Storage] 加载用量失败:', e)
  } finally {
    storageLoading.value = false
  }
}

async function onRefreshStorage() {
  await loadStorageUsage()
}

async function onCleanIntermediate() {
  cleaning.value = true
  cleanResult.value = ''
  try {
    const result = await cleanIntermediateFiles()
    const freed = formatBytes(result.total_freed_bytes || result.freed_bytes || 0)
    cleanResult.value = t('settings.storage_cleaned', { freed })
    await loadStorageUsage()
  } catch (e) {
    console.error('[Storage] 清理失败:', e)
    cleanResult.value = t('settings.storage_clean_failed')
  } finally {
    cleaning.value = false
  }
}

async function onCleanOrphaned() {
  cleaning.value = true
  cleanResult.value = ''
  try {
    const result = await cleanOrphanedFiles()
    const freed = formatBytes(result.freed_bytes || 0)
    cleanResult.value = t('settings.storage_cleaned', { freed })
    await loadStorageUsage()
  } catch (e) {
    console.error('[Storage] 清理失败:', e)
    cleanResult.value = t('settings.storage_clean_failed')
  } finally {
    cleaning.value = false
  }
}

onMounted(async () => {
  // 深链 ?cat=/?tab= 已在 setup 期解析（deepLinkCat），此处不再重复处理
  const s = await fetchSettings()
  // 确保嵌套对象存在，避免模板中 settings.llm!.xxx 报错 / Ensure nested objects exist, avoid template errors
  if (!s.llm) s.llm = {}
  if (!s.asr) s.asr = {}

  // BUG-008 修复：后端返回的 provider 可能是短名称（如 "DashScope"），
  // 但下拉选项使用全名（如 "DashScope（通义千问）"）。需要映射匹配。
  // Fix: Backend may return short provider name (e.g. "DashScope"),
  // but dropdown options use full names (e.g. "DashScope（通义千问）"). Map to match.
  const defaultPresets = [
    { name: 'DashScope（通义千问）', shortName: 'DashScope' },
    { name: 'OpenAI', shortName: 'OpenAI' },
    { name: 'DeepSeek', shortName: 'DeepSeek' },
    { name: 'Moonshot（月之暗面）', shortName: 'Moonshot' },
    { name: '自定义', shortName: '自定义' },
  ]
  if (s.llm?.provider) {
    const matched = defaultPresets.find(
      p => p.name === s.llm!.provider || p.shortName === s.llm!.provider
    )
    if (matched) s.llm.provider = matched.name
  }

  Object.assign(settings, s)
  if (s.feature_flags) {
    Object.assign(featureFlags, {
      realtime_chapters: s.feature_flags.realtime_chapters !== false,
      realtime_summary: s.feature_flags.realtime_summary !== false,
      realtime_summary_interval: s.feature_flags.realtime_summary_interval || 60,
      update_check: s.feature_flags.update_check !== false,
      voiceprint_auto_match: s.feature_flags.voiceprint_auto_match === true,
    })
  }
  // 分离配置 / Diarization config
  if (s.diarization) {
    Object.assign(diarizationInfo, s.diarization)
  }
  // 输出目录 / Output directory
  if (s.output_dir) {
    settings.output_dir = s.output_dir
  }
  // 优先使用订阅流量 / Prefer subscription
  preferSubscription.value = !!s.prefer_subscription
  // 存储配置 / Storage config
  if (s.storage) {
    Object.assign(storageConfig, {
      auto_clean_intermediate: s.storage.auto_clean_intermediate !== false,
      auto_archive_days: s.storage.auto_archive_days || 0,
    })
  }
  loadUsage()
  loadCliReference()
  loadStorageUsage()
  updateLoadCurrentVersion()
  loadDevices()
  engineStore.load()
  engineStore.loadRouting(true)  // AM-F1：接入方式派生态（含专家模式/引导判定）
  engineStore.loadOverview()  // R5：模型清单 + 下载任务（有活动下载会自动轮询） / Model manifest + jobs (auto-polls if active)
  runLocalProbe()  // 探测本机 Ollama / LM Studio（§7.2-4） / Probe local Ollama / LM Studio
})

onUnmounted(() => {
  engineStore.stopPolling()
})

async function loadUsage() {
  if (!userStore.isLoggedIn) return
  try {
    const [summary, history] = await Promise.all([
      fetchUsageSummary(),
      fetchUsageHistory(30),
    ])
    Object.assign(usageSummary, summary)
    usageHistory.value = history.history || []
  } catch (e) {
    console.error('load usage failed:', e)
  }
}

async function loadCliReference() {
  try {
    const data = await fetchCliReference()
    Object.assign(cliReference, data)
  } catch (e) {
    console.error('load cli reference failed:', e)
  }
}
</script>

<style scoped>
/* ─── 两栏布局 / Two-column layout ─── */
.settings-layout { display: flex; height: 100%; min-height: 0; }
.settings-nav { flex: 0 0 160px; display: flex; flex-direction: column; gap: 2px; padding: var(--s-3) var(--s-2); border-right: 1px solid var(--border); overflow-y: auto; }
.settings-nav-title { font-size: 15px; font-weight: 600; padding: var(--s-2) var(--s-2); margin-bottom: var(--s-2); }
.settings-nav-item { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-2) var(--s-2); border: none; background: none; color: var(--fg); font-size: 13px; cursor: pointer; text-align: left; border-radius: var(--radius-sm); transition: background 0.12s, color 0.12s; width: 100%; }
.settings-nav-item:hover { background: var(--surface-2); }
.settings-nav-item.is-active { background: var(--surface-3, var(--surface-2)); color: var(--accent); font-weight: 500; }
.settings-nav-item svg { width: 16px; height: 16px; flex-shrink: 0; }
.settings-content { flex: 1; min-width: 0; overflow-y: auto; padding: var(--s-4) var(--s-6); }

.settings-section { margin-bottom: var(--s-7); }
.settings-title { font-size: 16px; font-weight: 600; margin-bottom: var(--s-3); padding-bottom: var(--s-2); border-bottom: 1px solid var(--border); }
.settings-account { display: flex; align-items: center; gap: var(--s-3); }
.settings-logout-btn { margin-left: auto; display: flex; align-items: center; gap: 6px; padding: 6px 12px; border: 1px solid var(--border); border-radius: var(--radius); background: transparent; color: var(--muted); font-size: 13px; cursor: pointer; transition: all 0.15s ease; }
.settings-logout-btn:hover { color: var(--error); border-color: var(--error); background: var(--error-soft); }
.settings-logout-btn svg { flex-shrink: 0; }
.settings-avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--border); color: var(--muted); display: grid; place-items: center; font-size: 16px; font-weight: 600; flex-shrink: 0; }
.settings-account-info { display: flex; flex-direction: column; gap: 2px; }
.settings-account-meta { display: flex; align-items: center; gap: var(--s-2); }
.settings-name { font-size: 15px; font-weight: 500; }
.settings-role { font-size: 12px; color: var(--subtle); }
.settings-login-prompt { display: flex; align-items: center; gap: var(--s-3); }
.settings-login-prompt p { margin: 0; color: var(--muted); }
.settings-field { margin-bottom: var(--s-4); }
.settings-label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.settings-input { width: 100%; max-width: 400px; padding: var(--s-2) var(--s-3); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); color: var(--fg); font-size: 14px; outline: none; }
.settings-input:focus { border-color: var(--accent); }
.settings-actions { display: flex; gap: var(--s-2); margin-top: var(--s-4); }
.api-subsection { margin-bottom: var(--s-5); padding-left: var(--s-3); border-left: 2px solid var(--border); }
.api-subsection-title { font-size: 13px; font-weight: 600; margin-bottom: var(--s-3); color: var(--fg); }
.api-readonly { font-size: 13px; color: var(--muted); display: flex; align-items: center; gap: var(--s-2); }
.api-proxy-hint { font-size: 11px; color: var(--subtle); }
.settings-test-result { font-size: 12px; margin-top: var(--s-2); }
.settings-test-result.is-error { color: var(--error); }
.theme-grid { display: flex; flex-wrap: wrap; gap: var(--s-2); }
.theme-chip { padding: 6px var(--s-4); border-radius: 20px; border: 1px solid var(--border); background: var(--surface); color: var(--fg); font-size: 13px; cursor: pointer; transition: all 0.15s; }
.theme-chip:hover { border-color: var(--border-strong); }
.theme-chip.is-active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); font-weight: 500; }
.settings-section-desc { font-size: 12px; color: var(--muted); margin: calc(-1 * var(--s-2)) 0 var(--s-4); }
.feature-toggles { display: flex; flex-direction: column; gap: var(--s-5); }
.toggle-desc { display: block; font-size: 11px; color: var(--muted); font-weight: 400; margin-top: 2px; }
.toggle-experimental { display: inline-block; font-size: 10px; color: var(--muted); background: var(--border); padding: 1px 6px; border-radius: 8px; margin-left: 6px; vertical-align: middle; }
.interval-selector { display: flex; align-items: center; gap: var(--s-2); margin-top: var(--s-2); }
.interval-label { font-size: 12px; color: var(--muted); }
.freq-btns { display: flex; gap: 2px; }
.interval-hint { font-size: 11px; color: var(--subtle); }
.settings-empty { font-size: 13px; color: var(--muted); padding: var(--s-3) 0; }
.wm-toggle.is-disabled { opacity: 0.4; cursor: not-allowed; }
/* 声纹 / 分离 / 输出目录 / Voiceprint / Diarization / Output dir */
/* 系统提示词 / System prompts */
.prompt-list { display: flex; flex-direction: column; gap: var(--s-3); }
.prompt-item { border: 1px solid var(--border); border-radius: var(--radius); padding: var(--s-3); }
.prompt-item-header { display: flex; align-items: center; gap: var(--s-3); flex-wrap: wrap; }
.prompt-item-name { font-weight: 600; font-size: 13px; }
.prompt-item-source { font-size: 11px; color: var(--muted); font-family: var(--font-mono); }
.prompt-item-desc { font-size: 12px; color: var(--subtle); margin: 4px 0 0; }
.prompt-item-content { font-size: 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: var(--s-3); margin: var(--s-2) 0 0; white-space: pre-wrap; word-break: break-word; max-height: 300px; overflow-y: auto; font-family: var(--font-mono); line-height: 1.5; }
/* CLI 参考 / CLI reference */
.cli-ref-list { display: flex; flex-direction: column; gap: var(--s-2); }
.cli-ref-group { margin-bottom: var(--s-3); }
.cli-ref-group-title { font-size: 13px; font-weight: 600; margin-bottom: var(--s-2); color: var(--fg); }
.cli-ref-item { display: flex; align-items: baseline; gap: var(--s-3); padding: 4px 0; font-size: 13px; }
.cli-ref-cmd { font-weight: 500; min-width: 80px; color: var(--fg); }
.cli-ref-item code { font-family: var(--font-mono); font-size: 12px; color: var(--muted); background: var(--surface-2); padding: 2px 6px; border-radius: var(--radius-sm); word-break: break-all; }
/* 键盘快捷键参考 / Keyboard shortcut reference */
.kbd-shortcut-list { display: flex; flex-direction: column; gap: 0; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.kbd-shortcut-item { display: flex; align-items: center; justify-content: space-between; padding: var(--s-2) var(--s-4); font-size: 13px; }
.kbd-shortcut-item + .kbd-shortcut-item { border-top: 1px solid var(--border); }
.kbd-shortcut-label { color: var(--fg); }
.kbd-shortcut-key { font-family: var(--font-mono); font-size: 11px; color: var(--muted); background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 2px 8px; min-width: 48px; text-align: center; }
/* 禁用指令 / Disabled commands */
.disabled-cmd-list { display: flex; flex-direction: column; gap: var(--s-2); }
.disabled-cmd-item { display: flex; align-items: center; justify-content: space-between; padding: var(--s-2) var(--s-3); border: 1px solid var(--border); border-radius: var(--radius); }
.disabled-cmd-item code { font-family: var(--font-mono); font-size: 12px; color: var(--fg); }
/* 存储管理 / Storage management */
.storage-panel { display: flex; flex-direction: column; gap: var(--s-4); }
.storage-overview { display: flex; gap: var(--s-6); padding: var(--s-4); background: var(--surface-2); border-radius: var(--radius); border: 1px solid var(--border); }
.storage-stat { flex: 1; text-align: center; }
.storage-stat-value { font-size: 22px; font-weight: 700; font-family: var(--font-mono); color: var(--fg); line-height: 1.3; }
.storage-stat-label { font-size: 11px; color: var(--muted); margin-top: 4px; font-family: var(--font-mono); text-transform: uppercase; letter-spacing: 0.04em; }
.storage-breakdown { display: flex; flex-direction: column; gap: 0; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.storage-breakdown-item { display: flex; align-items: center; justify-content: space-between; padding: var(--s-2) var(--s-3); font-size: 13px; }
.storage-breakdown-item + .storage-breakdown-item { border-top: 1px solid var(--border); }
.storage-breakdown-label { color: var(--fg); }
.storage-breakdown-value { font-family: var(--font-mono); font-size: 12px; color: var(--muted); }
.storage-breakdown-value small { font-size: 11px; opacity: 0.7; }
.storage-intermediate { border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.storage-intermediate-title { font-size: 12px; font-weight: 600; color: var(--muted); padding: var(--s-2) var(--s-3); background: var(--surface-2); border-bottom: 1px solid var(--border); text-transform: uppercase; letter-spacing: 0.04em; }
.storage-actions { display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; }
.storage-clean-result { font-size: 12px; color: var(--accent); margin: 0; font-weight: 500; }
/* 版本信息 / Version info */
.version-panel { display: flex; flex-direction: column; gap: var(--s-2); }
.version-row { display: flex; align-items: center; gap: var(--s-3); font-size: 13px; }
.version-label { color: var(--muted); min-width: 80px; }
.version-value { font-family: var(--font-mono); font-weight: 600; color: var(--fg); }
.version-value.is-newer { color: var(--accent); }
.version-actions { display: flex; align-items: center; gap: var(--s-2); margin-top: var(--s-2); flex-wrap: wrap; }
.version-msg { font-size: 12px; color: var(--accent); font-weight: 500; }
.version-msg.is-error { color: var(--error); }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

/* ─── 计算引擎（R6） / Compute engine (R6) ─── */
.engine-status-panel { display: flex; flex-direction: column; gap: var(--s-3); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--s-4); background: var(--surface-2); }
.engine-status-row { display: flex; align-items: center; gap: var(--s-3); font-size: 13px; flex-wrap: wrap; }
.engine-status-label { color: var(--muted); min-width: 96px; }
.engine-status-value { font-weight: 500; color: var(--fg); }
.engine-status-value.is-ok { color: var(--ok); }
.engine-status-value.is-warn { color: var(--warn); }
.engine-mode-select { max-width: 220px; padding: 4px 8px; font-size: 12px; }
.engine-save-msg { font-size: 12px; color: var(--accent); margin: 0; font-weight: 500; }
.engine-save-msg.is-error { color: var(--error); }
.engine-readonly-hint { font-size: 12px; color: var(--subtle); margin: 0; }
.engine-dev-panel { display: flex; align-items: center; gap: var(--s-3); margin-top: var(--s-3); padding: var(--s-2) var(--s-3); border: 1px dashed var(--border-strong); border-radius: var(--radius); flex-wrap: wrap; }
.engine-dev-label { font-family: var(--font-mono); font-size: 11px; color: var(--warn); text-transform: uppercase; letter-spacing: 0.04em; }
.engine-dev-btns { display: flex; gap: var(--s-2); flex-wrap: wrap; }
.engine-matrix-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: var(--radius); }
.engine-matrix { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 640px; }
.engine-matrix th, .engine-matrix td { padding: var(--s-3); text-align: left; vertical-align: top; border-bottom: 1px solid var(--border); border-right: 1px solid var(--border); }
.engine-matrix th:last-child, .engine-matrix td:last-child { border-right: none; }
.engine-matrix thead th { background: var(--surface-2); font-weight: 600; }
.engine-matrix tbody tr:last-child th, .engine-matrix tbody tr:last-child td { border-bottom: none; }
.engine-matrix .em-corner { font-size: 11px; color: var(--subtle); font-weight: 500; }
.engine-matrix .em-col-name { display: block; font-size: 13px; color: var(--fg); }
.engine-matrix .em-col-sub { display: block; font-size: 11px; color: var(--muted); font-weight: 400; margin-top: 2px; }
.engine-matrix thead th.is-local .em-col-name { color: var(--ok); }
.engine-matrix .em-row-name { font-weight: 500; color: var(--fg); background: var(--surface); min-width: 96px; }
.engine-matrix td { color: var(--muted); line-height: 1.5; }
.em-tag { display: inline-block; font-size: 10px; font-weight: 600; padding: 1px 8px; border-radius: 999px; margin-bottom: 4px; letter-spacing: 0.02em; }
.em-tag.is-stay { color: var(--ok); background: var(--ok-soft); border: 1px solid oklch(from var(--ok) l c h / 0.25); }
.em-tag.is-proxy { color: var(--accent); background: var(--accent-soft); border: 1px solid var(--accent-mid); }
.em-tag.is-cloud { color: var(--fg); background: var(--surface-2); border: 1px solid var(--border-strong); }
.em-tag.is-endpoint { color: var(--warn); background: var(--warn-soft); border: 1px solid oklch(from var(--warn) l c h / 0.3); }
.em-cell { display: block; }
.engine-matrix-note { font-size: 12px; color: var(--muted); margin: var(--s-3) 0 0; padding-left: var(--s-3); border-left: 2px solid var(--accent-mid); line-height: 1.6; }

/* ─── R5：模型资产管理 / R5: model asset management ─── */
.engine-ready-hint { font-size: 12px; color: var(--warn); margin: 0; }
.engine-storage-block { margin-bottom: var(--s-4); }
.engine-storage-controls { display: flex; align-items: center; gap: var(--s-2); }
.engine-storage-controls .settings-input { font-family: var(--font-mono); font-size: 12px; }
.engine-disk-hint { display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; font-size: 12px; color: var(--muted); margin-top: 6px; }
.engine-disk-hint.is-short { color: var(--warn); }
.engine-disk-sep { color: var(--subtle); }
.engine-disk-short { font-weight: 600; }
.engine-model-list { display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.engine-model-row { padding: var(--s-3) var(--s-4); }
.engine-model-row + .engine-model-row { border-top: 1px solid var(--border); }
.engine-model-head { display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; }
.engine-model-name { font-size: 13px; font-weight: 600; color: var(--fg); }
.engine-model-optional { font-size: 10px; color: var(--muted); background: var(--surface-2); border: 1px solid var(--border); padding: 1px 6px; border-radius: 999px; }
.engine-model-size { font-size: 12px; color: var(--muted); font-family: var(--font-mono); }
.engine-model-status { margin-left: auto; font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 999px; letter-spacing: 0.02em; }
.engine-model-status.is-ready { color: var(--ok); background: var(--ok-soft); }
.engine-model-status.is-downloading { color: var(--accent); background: var(--accent-soft); }
.engine-model-status.is-partial { color: var(--warn); background: var(--warn-soft); }
.engine-model-status.is-tampered { color: var(--error); background: var(--error-soft, var(--surface-2)); }
.engine-model-status.is-not_downloaded, .engine-model-status.is-missing { color: var(--muted); background: var(--surface-2); }
.engine-model-purpose { font-size: 12px; color: var(--muted); margin-top: 4px; line-height: 1.5; }
.engine-model-progress { display: flex; align-items: center; gap: var(--s-2); margin-top: var(--s-2); flex-wrap: wrap; }
.engine-progress-bar { flex: 1; min-width: 140px; height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.engine-progress-fill { height: 100%; background: var(--accent); border-radius: 999px; transition: width 0.3s ease; }
.engine-progress-pct { font-size: 12px; font-weight: 600; font-family: var(--font-mono); color: var(--accent); min-width: 36px; }
.engine-progress-meta { font-size: 11px; color: var(--muted); font-family: var(--font-mono); }
.engine-model-actions { display: flex; gap: var(--s-2); margin-top: var(--s-2); }
.engine-job-failed { display: flex; align-items: flex-start; gap: 6px; font-size: 12px; color: var(--error); margin-top: var(--s-2); line-height: 1.5; }
.engine-job-failed svg { flex-shrink: 0; margin-top: 2px; }
.engine-models-actions { display: flex; gap: var(--s-2); margin-top: var(--s-4); }


</style>
