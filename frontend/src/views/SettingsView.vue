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

      <!-- 算力相关四段（REQ-COMPUTE-CENTER）：账户登录 / API 配置 / ASR 配置 / 本地引擎 -->
      <button class="settings-nav-item cc-nav" :class="{ 'is-active': activeCategory === 'account' }" @click="activeCategory = 'account'">
        <span class="cc-nav-dot" :class="userStore.isLoggedIn ? 'ok' : ''"></span>
        <span class="cc-nav-body"><span class="cc-nav-name">{{ t('settings.cat_account') }}</span><span class="cc-nav-sub">{{ navAccountSub }}</span></span>
      </button>
      <button class="settings-nav-item cc-nav" :class="{ 'is-active': activeCategory === 'ai' }" @click="activeCategory = 'ai'">
        <span class="cc-nav-dot" :class="navAiDot"></span>
        <span class="cc-nav-body"><span class="cc-nav-name">{{ t('settings.compute.ai_title') }}</span><span class="cc-nav-sub">{{ navAiSub }}</span></span>
      </button>
      <button class="settings-nav-item cc-nav" :class="{ 'is-active': activeCategory === 'asr' }" @click="activeCategory = 'asr'">
        <span class="cc-nav-dot" :class="navAsrDot"></span>
        <span class="cc-nav-body"><span class="cc-nav-name">{{ t('settings.compute.asr_title') }}</span><span class="cc-nav-sub">{{ navAsrSub }}</span></span>
      </button>
      <button class="settings-nav-item cc-nav" :class="{ 'is-active': activeCategory === 'engine' }" @click="activeCategory = 'engine'">
        <span class="cc-nav-dot" :class="navEngineDot"></span>
        <span class="cc-nav-body"><span class="cc-nav-name">{{ t('settings.compute.engine_title') }}</span><span class="cc-nav-sub">{{ navEngineSub }}</span></span>
      </button>

      <!-- 常规分类 / General categories -->
      <button class="settings-nav-item" :class="{ 'is-active': activeCategory === 'transcription' }" @click="activeCategory = 'transcription'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>
        {{ t('settings.cat_transcription') }}
      </button>
      <button class="settings-nav-item" :class="{ 'is-active': activeCategory === 'appearance' }" @click="activeCategory = 'appearance'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12.2z"/></svg>
        {{ t('settings.cat_appearance') }}
      </button>
      <button class="settings-nav-item" :class="{ 'is-active': activeCategory === 'features' }" @click="activeCategory = 'features'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        {{ t('settings.cat_features') }}
      </button>
      <button class="settings-nav-item" :class="{ 'is-active': activeCategory === 'system' }" @click="activeCategory = 'system'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1.1a1.7 1.7 0 0 0-1.8.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H2a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 1 1.8.3H9a1.7 1.7 0 0 0 1-1.5V2a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1.1a2 2 0 1 1 2.8 2.8l.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H22a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>
        {{ t('settings.cat_system') }}
      </button>
    </nav>

    <!-- 右栏：内容区 / Right: content area -->
    <div class="settings-content">

    <!-- ═══ 账户登录 / Account ═══ -->
    <div v-show="activeCategory === 'account'">
      <AccountPanel :initial-prefer="!!settings.prefer_subscription" />
    </div>

    <!-- ═══ API 配置 / AI compute source ═══ -->
    <div v-show="activeCategory === 'ai'">
      <AiSourcePanel :settings="settings" @refresh="reloadSettings" />
    </div>

    <!-- ═══ ASR 配置 / ASR compute source ═══ -->
    <div v-show="activeCategory === 'asr'">
      <AsrSourcePanel :settings="settings" @goto="onPanelGoto" @refresh="reloadSettings" />
    </div>

    <!-- ═══ 本地引擎 / Local engine ═══ -->
    <div v-show="activeCategory === 'engine'">
      <LocalEnginePanel />
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
      <div class="theme-grid" @mouseleave="themeStore.restoreTheme()">
        <button
          v-for="theme in THEMES"
          :key="theme.id"
          class="theme-chip"
          :class="{ 'is-active': themeStore.current === theme.id }"
          @mouseenter="themeStore.previewTheme(theme.id)"
          @focus="themeStore.previewTheme(theme.id)"
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

        <div class="storage-auto-archive">
          <div class="wm-setting-row">
            <label>{{ t('settings.storage_auto_clean') }}</label>
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
  </div><!-- .settings-layout -->
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useThemeStore, THEMES } from '@/stores/theme'
import { useWatermarkStore } from '@/stores/watermark'
import { useTaskStore } from '@/stores/task'
import { useEngineStore } from '@/stores/engine'
import AccountPanel from '@/components/settings/AccountPanel.vue'
import AiSourcePanel from '@/components/settings/AiSourcePanel.vue'
import AsrSourcePanel from '@/components/settings/AsrSourcePanel.vue'
import LocalEnginePanel from '@/components/settings/LocalEnginePanel.vue'
import { useComputeSource } from '@/composables/useComputeSource'
import { fetchSettings, saveSettings, fetchCliReference } from '@/api/settings'
import type { Settings, FeatureFlags } from '@/api/settings'
import { fetchStorageUsage, cleanIntermediateFiles, cleanOrphanedFiles } from '@/api/storage'
import type { StorageUsage } from '@/api/storage'
import { fetchAudioDevices, setRecordDevice } from '@/api/record'
import type { AudioDevice } from '@/api/record'
import { setI18nLocale, getLocale, type SupportedLocale } from '@/i18n'
import { usePageBack } from '@/composables/usePageBack'
import { modKey } from '@/utils/platform'
import { useUpdateCheck } from '@/composables/useUpdateCheck'

const { t } = useI18n()
const { goBack } = usePageBack()
const route = useRoute()
const userStore = useUserStore()
const themeStore = useThemeStore()
const watermarkStore = useWatermarkStore()
const taskStore = useTaskStore()
const engineStore = useEngineStore()
const { currentSource, sourceLabel } = useComputeSource()

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
    if (result.current_device) {
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

/** 分类导航（REQ-COMPUTE-CENTER）：账户/AI/ASR/引擎四段 + 常规四段 */
const SETTINGS_CATEGORIES = ['account', 'ai', 'asr', 'engine', 'transcription', 'appearance', 'features', 'system']
const LEGACY_CATEGORY_MAP: Record<string, string> = { access: 'ai', services: 'ai', cli: 'ai' }
const rawCat = typeof route.query.cat === 'string' ? route.query.cat : (typeof route.query.tab === 'string' ? route.query.tab : '')
const mappedCat = LEGACY_CATEGORY_MAP[rawCat] || rawCat
const deepLinkCat = SETTINGS_CATEGORIES.includes(mappedCat) ? mappedCat : ''
const activeCategory = ref<string>(deepLinkCat || 'account')

function onPanelGoto(category: string) {
  if (SETTINGS_CATEGORIES.includes(category)) activeCategory.value = category
}

// [状态同步] 本地引擎面板走 v-show，切走再切回不会重新挂载；而进程存活/PID 只存在于
// engineStore.status（不随模型 overview 轮询刷新），故在每次进入该分类时强制回读一次。
watch(activeCategory, (cat) => {
  if (cat === 'engine') engineStore.load(true)
})

// ─── 导航状态副标签（原型 nav-dot + mono sub） / Nav status sublabels ───
const navAccountSub = computed(() => userStore.isLoggedIn ? `${t('settings.compute.logged_in')} · ${userStore.user?.provider || 'local'}` : t('settings.compute.nav_not_logged_in'))
const navAiSub = computed(() => `AI · ${sourceLabel(currentSource('llm'))}`)
const navAsrSub = computed(() => `ASR · ${sourceLabel(currentSource('asr'))}`)
const navEngineSub = computed(() => {
  const models = engineStore.overview?.models || []
  const ready = models.filter(m => m.status === 'ready').length
  return models.length ? `模型 ${ready}/${models.length}` : t('settings.compute.engine_title')
})
const navAiDot = computed(() => (currentSource('llm') ? 'accent' : ''))
const navAsrDot = computed(() => (currentSource('asr') ? 'accent' : ''))
const navEngineDot = computed(() => {
  if (engineStore.status?.local_ready) return 'ok'
  return ''
})

// ─── 设置 / Settings ───
const settings = reactive<Settings>({ llm: {}, asr: {} })

const featureFlags = reactive<FeatureFlags>({
  realtime_chapters: true,
  realtime_summary: true,
  realtime_summary_interval: 60,
  update_check: true,
  voiceprint_auto_match: false,
  voiceprint_v2: true,
  chrome_autohide: true,
})

// ─── 分离 / Diarization ───
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

// ─── 水印氛围 / Watermark ambiance ───
const wmEnabled = computed(() => watermarkStore.enabled)
const wmOpacity = computed(() => watermarkStore.opacity)
function wmToggle() { watermarkStore.toggle() }
function onWmOpacityInput(e: Event) {
  const val = Number((e.target as HTMLInputElement).value)
  watermarkStore.setOpacity(val / 100)
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

// ─── 语言切换 / Language switch ───
const LANG_OPTIONS: { id: SupportedLocale; label: string }[] = [
  { id: 'zh-CN', label: '简体中文' },
  { id: 'en', label: 'English' },
]
const currentLocale = computed(() => getLocale())
async function onSwitchLang(locale: SupportedLocale) {
  await setI18nLocale(locale)
}

async function saveFeatureFlags() {
  await saveSettings({ feature_flags: { ...featureFlags } })
}
function toggleFlag(key: keyof FeatureFlags) {
  if (key === 'realtime_summary_interval') return
  featureFlags[key] = !featureFlags[key] as boolean
  saveFeatureFlags()
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
async function onRefreshStorage() { await loadStorageUsage() }
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

async function loadCliReference() {
  try {
    const data = await fetchCliReference()
    Object.assign(cliReference, data)
  } catch (e) {
    console.error('load cli reference failed:', e)
  }
}

async function loadSettingsIntoReactive() {
  const s = await fetchSettings()
  if (!s.llm) s.llm = {}
  if (!s.asr) s.asr = {}
  Object.assign(settings, s)
  if (s.feature_flags) {
    Object.assign(featureFlags, {
      realtime_chapters: s.feature_flags.realtime_chapters !== false,
      realtime_summary: s.feature_flags.realtime_summary !== false,
      realtime_summary_interval: s.feature_flags.realtime_summary_interval || 60,
      update_check: s.feature_flags.update_check !== false,
      voiceprint_auto_match: s.feature_flags.voiceprint_auto_match === true,
      voiceprint_v2: s.feature_flags.voiceprint_v2 !== false,
      chrome_autohide: s.feature_flags.chrome_autohide !== false,
    })
  }
  if (s.diarization) Object.assign(diarizationInfo, s.diarization)
  if (s.storage) {
    Object.assign(storageConfig, {
      auto_clean_intermediate: s.storage.auto_clean_intermediate !== false,
      auto_archive_days: s.storage.auto_archive_days || 0,
    })
  }
}

/** 面板保存后回读设置（保持脱敏 Key / 生效来源同步） */
async function reloadSettings() {
  try { await loadSettingsIntoReactive() } catch { /* 静默 */ }
}

onMounted(async () => {
  try {
    await loadSettingsIntoReactive()
  } catch (e) {
    console.error('load settings failed:', e)
  }
  loadStorageUsage()
  loadCliReference()
  updateLoadCurrentVersion()
  loadDevices()
  engineStore.load()
  engineStore.loadRouting(true)
  engineStore.loadOverview()
})

onUnmounted(() => {
  engineStore.stopPolling()
})
</script>

<style scoped>
/* ─── 两栏布局 / Two-column layout ─── */
.settings-layout { display: flex; height: 100%; min-height: 0; }
.settings-nav { flex: 0 0 220px; display: flex; flex-direction: column; gap: 2px; padding: var(--s-3) var(--s-2); border-right: 1px solid var(--border); overflow-y: auto; }
.settings-nav-title { font-size: 15px; font-weight: 600; padding: var(--s-2) var(--s-2); margin-bottom: var(--s-2); }
.settings-nav-item { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-2); border: none; background: none; color: var(--fg); font-size: 13px; cursor: pointer; text-align: left; border-radius: var(--radius-sm); transition: background 0.12s, color 0.12s; width: 100%; }
.settings-nav-item:hover { background: var(--surface-2); }
.settings-nav-item.is-active { background: var(--surface-3, var(--surface-2)); color: var(--accent); font-weight: 500; }
.settings-nav-item svg { width: 16px; height: 16px; flex-shrink: 0; }
.settings-content { flex: 1; min-width: 0; overflow-y: auto; padding: var(--s-4) var(--s-6); }

/* 算力四段导航项（dot + name + mono sub） */
.cc-nav { display: grid; grid-template-columns: 8px 1fr; align-items: start; gap: var(--s-2); }
.cc-nav-dot { width: 7px; height: 7px; border-radius: 50%; margin-top: 7px; background: var(--border-strong); }
.cc-nav-dot.ok { background: var(--ok); }
.cc-nav-dot.accent { background: var(--accent); }
.cc-nav-body { display: flex; flex-direction: column; min-width: 0; }
.cc-nav-name { display: block; font-size: 13px; }
.cc-nav-sub { display: block; font-size: 11px; font-family: var(--font-mono); color: var(--subtle); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.settings-nav-item.is-active .cc-nav-sub { color: var(--muted); }

.settings-section { margin-bottom: var(--s-7); }
.settings-title { font-size: 16px; font-weight: 600; margin-bottom: var(--s-3); padding-bottom: var(--s-2); border-bottom: 1px solid var(--border); }
.settings-field { margin-bottom: var(--s-4); }
.settings-label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.settings-input { width: 100%; max-width: 400px; padding: var(--s-2) var(--s-3); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); color: var(--fg); font-size: 14px; outline: none; }
.settings-input:focus { border-color: var(--accent); }
.theme-grid { display: flex; flex-wrap: wrap; gap: var(--s-2); }
.theme-chip { padding: 6px var(--s-4); border-radius: 20px; border: 1px solid var(--border); background: var(--surface); color: var(--fg); font-size: 13px; cursor: pointer; transition: all 0.15s; }
.theme-chip:hover { border-color: var(--border-strong); }
.theme-chip.is-active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); font-weight: 500; }
.settings-section-desc { font-size: 12px; color: var(--muted); margin: calc(-1 * var(--s-2)) 0 var(--s-4); }
.feature-toggles { display: flex; flex-direction: column; gap: var(--s-5); }
.toggle-desc { display: block; font-size: 11px; color: var(--muted); font-weight: 400; margin-top: 2px; }
.toggle-experimental { display: inline-block; font-size: 10px; color: var(--muted); background: var(--border); padding: 1px 6px; border-radius: 8px; margin-left: 6px; vertical-align: middle; }
.settings-empty { font-size: 13px; color: var(--muted); padding: var(--s-3) 0; }
.wm-toggle.is-disabled { opacity: 0.4; cursor: not-allowed; }

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
</style>
