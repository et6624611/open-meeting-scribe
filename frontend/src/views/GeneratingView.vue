<template>
  <div class="gen-view">
    <!-- 紧凑图标工具栏 -->
    <div class="gen-toolbar">
      <div class="gen-toolbar-left">
        <nav class="gen-breadcrumb" id="genBreadcrumb" :aria-label="t('generating.breadcrumb.nav')">
          <template v-for="(crumb, i) in breadcrumbs" :key="i">
            <button class="gen-breadcrumb-item" :title="crumb.label" @click="router.push(crumb.to)">
              <svg v-if="crumb.icon === 'folder'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
              <span class="gen-breadcrumb-label">{{ crumb.label }}</span>
            </button>
            <span class="gen-breadcrumb-sep">/</span>
          </template>
          <span class="gen-breadcrumb-current" :title="breadcrumbTitle">{{ breadcrumbTitle }}</span>
        </nav>
      </div>
      <div class="gen-toolbar-right">
        <button class="gen-toolbar-icon" @click="onCopy" :title="t('generating.toolbar.copy')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          <span class="tb-tip">{{ t('generating.toolbar.copy') }}</span>
        </button>
        <button class="gen-toolbar-icon" @click="onExport" :title="t('generating.toolbar.export_title')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
          <span class="tb-tip">{{ t('generating.toolbar.export') }}</span>
        </button>
        <button class="gen-toolbar-icon" @click="onFullscreen" :title="t('generating.toolbar.fullscreen')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
          <span class="tb-tip">{{ t('generating.toolbar.fullscreen') }}</span>
        </button>
        <div class="gen-toolbar-divider"></div>
        <div class="gen-toolbar-more-wrap">
          <button ref="genMoreBtn" class="gen-toolbar-icon" @click="toggleGenMore" :aria-label="t('generating.toolbar.more')" aria-haspopup="menu">
            <svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg>
          </button>
          <div ref="genMoreDropdown" class="gen-toolbar-more-menu" :class="{ 'is-open': showMoreMenu }">
            <button class="gen-toolbar-more-item" @click="onEditSummary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              {{ t('generating.toolbar.edit') }}
            </button>
            <button class="gen-toolbar-more-item" @click="onRetrySummary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
              {{ t('generating.toolbar.regenerate') }}
            </button>
            <button class="gen-toolbar-more-item" @click="onRetranscribe">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
              {{ t('generating.toolbar.retranscribe') }}
            </button>
            <div class="gen-toolbar-more-divider"></div>
            <button class="gen-toolbar-more-item" @click="onArchiveConfirm">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>
              {{ t('generating.toolbar.archive') }}
            </button>
            <button class="gen-toolbar-more-item is-danger" @click="onDelete">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
              {{ t('generating.toolbar.delete') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 元信息行 + 说话人区 -->
    <div class="gen-meta" id="genMeta">
      <div class="gen-meta-row">
        <div class="gen-meta-group">
          <span class="gen-meta-item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            <span class="gen-meta-val">{{ metaDuration }}</span>
          </span>
          <span class="gen-meta-sep"></span>
          <span class="gen-meta-item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
            <span class="gen-meta-val">{{ speakerNames.length }}</span> {{ t('generating.meta.person') }}
          </span>
          <span class="gen-meta-sep"></span>
          <span class="gen-meta-item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
            <span class="gen-meta-val gen-meta-date-btn" :title="t('generating.meta.edit_date')" @click.stop="openDatePicker">{{ metaDateShort }}</span>
          </span>
        </div>
        <span class="gen-meta-project" v-if="projects.length > 0">
          <span class="gen-meta-project-chip" :class="{ 'is-unbound': !task?.project_id }" role="button" tabindex="0" @click.stop="showProjectDropdown = !showProjectDropdown">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            <span>{{ currentProjectName }}</span>
          </span>
          <div class="gen-meta-proj-dropdown" :class="{ hidden: !showProjectDropdown }">
            <button v-for="p in projects" :key="p.id" class="gen-meta-proj-item" :class="{ 'is-selected': task?.project_id === p.id }" @click="onSelectProject(p.id)">
              {{ p.name }}
            </button>
            <div class="gen-meta-proj-divider"></div>
            <button class="gen-meta-proj-item" :class="{ 'is-selected': !task?.project_id }" @click="onSelectProject('')">
              {{ t('generating.meta.no_project') }}
            </button>
          </div>
        </span>
      </div>

      <!-- 说话人名单（含占比横条） -->
      <div class="gen-speaker-zone" v-if="speakerStats.length > 0">
        <div class="gen-speaker-labels" id="genSpeakerLabels">
          <span v-for="(sp, idx) in speakerStats" :key="idx" class="gen-spk-label">
            <span class="gen-spk-name" :style="{ color: sp.color }">{{ sp.name }}</span>
            <span class="gen-spk-bar"><span class="gen-spk-bar-fill" :style="{ width: sp.pct + '%', background: sp.color }"></span></span>
          </span>
        </div>
      </div>
    </div>

    <!-- 说话人身份关联横幅（还原 1.0 版本） -->
    <div class="gen-binding-bar" :class="{ hidden: !showBindingBar }">
      <div class="gbb-main">
        <div class="gbb-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        </div>
        <div class="gbb-body">
          <div class="gbb-title">{{ t('generating.binding.title') }}</div>
          <div class="gbb-desc">
            {{ t('generating.binding.detected', { count: bindingLegend.length }) }}<span v-if="unboundCount > 0" class="gbb-unbound-hint">{{ t('generating.binding.unbound_hint', { count: unboundCount }) }}</span>
          </div>
          <div class="gbb-legend" v-if="bindingLegend.length > 0">
            <div
              v-for="item in bindingLegend" :key="item.sid"
              class="binding-legend-item"
              :class="{ 'is-bound': item.bound }"
              :style="{ background: getSpeakerBg(item.sid) }"
              @click="openBindingDropdown($event, item.sid)"
            >
              <span class="bl-name" :style="{ color: item.color }" :class="{ 'bl-unbound': !item.bound }">{{ item.name || t('generating.speaker_default', { id: item.sid + 1 }) }}</span>
              <span class="bl-locate" :title="t('generating.binding.locate')" @click.stop="toggleLocateSpeaker(item.sid)">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="7"/><line x1="12" y1="1" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="23"/><line x1="1" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="23" y2="12"/></svg>
              </span>
            </div>
          </div>
        </div>
        <div class="gbb-actions">
          <a class="gbb-skip" href="javascript:void(0)" @click="skipMapping">{{ t('generating.binding.skip') }}</a>
          <button class="btn btn-primary btn-sm" @click="confirmMapping">{{ t('generating.binding.confirm') }}</button>
          <button class="gbb-close" @click="bindingBarHidden = true" :title="t('generating.binding.close')">
            <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
          </button>
        </div>
      </div>
      <div class="gbb-hint-bar">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        <span>{{ t('generating.binding.hint') }}</span>
      </div>
    </div>

    <!-- 绑定下拉框（Teleport 到 body） -->
    <Teleport to="body">
      <div v-if="bindingDropdown.visible" class="bt-dropdown" :style="{ left: bindingDropdown.x + 'px', top: bindingDropdown.y + 'px' }" @click.stop>
        <div class="bt-dd-search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input type="text" :placeholder="t('generating.binding.search_placeholder')" autocomplete="off" v-model="bindingDropdown.search" @keydown="onDropdownKeydown">
        </div>
        <div class="bt-dd-list">
          <!-- 不关联选项（无搜索词时显示） -->
          <template v-if="!bindingDropdown.search">
            <div class="bt-dropdown-item" :class="{ 'is-selected': !currentBindingMapping[bindingDropdown.speakerId] }" @click="selectBinding(bindingDropdown.speakerId, '')">
              <span class="bt-di-name">{{ t('generating.binding.no_bind') }}</span>
            </div>
            <div class="bt-dropdown-sep"></div>
          </template>
          <!-- 说话人列表 -->
          <template v-if="dropdownSpeakers.length > 0">
            <div
              v-for="(s, idx) in dropdownSpeakers" :key="s.id"
              class="bt-dropdown-item"
              :class="{ 'is-selected': currentBindingMapping[bindingDropdown.speakerId] === s.id, 'is-focused': bindingDropdown.focusIdx === idx }"
              @click="selectBinding(bindingDropdown.speakerId, s.id)"
            >
              <span class="bt-di-name" :style="{ color: currentBindingMapping[bindingDropdown.speakerId] === s.id ? getSpeakerColor(String(bindingDropdown.speakerId)) : undefined }">{{ s.name }}<span v-if="s.role" class="bt-di-role">({{ s.role }})</span></span>
            </div>
          </template>
          <div v-else class="bt-dd-empty">{{ t('generating.binding.no_match') }}</div>
        </div>
        <div class="bt-dd-footer" v-if="bindingDropdown.search && dropdownSpeakers.length === 0">
          <div class="bt-dropdown-item" :class="{ 'is-focused': bindingDropdown.focusIdx === 0 }" @click="createAndBind(bindingDropdown.speakerId, bindingDropdown.search)" style="color: var(--accent)">
            <span style="font-weight: 500">{{ t('generating.binding.create_named') }}</span>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 控制区：Tab + 音频控件 -->
    <div class="gen-control-zone">
      <!-- 左侧：Tab + 原文控制（亲疏原则分组） -->
      <div class="gen-tabs-group">
        <div class="gen-tabs" id="genTabsContainer">
          <button v-for="tab in TABS" :key="tab.id" class="gen-tab" :class="{ 'is-active': activeTab === tab.id }" :title="tab.label" @click="switchTab(tab.id)">
            <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" v-html="tab.icon"></svg>
            <span class="tab-label">{{ tab.label }}</span>
            <span class="tab-dot" :class="dotClass(tab.id)"></span>
          </button>
        </div>
      </div>
      <!-- 右侧：音频播放控制（亲疏原则分组） -->
      <div class="gen-audio-bar" v-if="audioUrl">
        <button class="gen-audio-play" @click="toggleAudio" :title="player.playing ? t('generating.transcript.pause_title') : t('generating.transcript.play_title')" :aria-label="player.playing ? t('generating.transcript.pause_title') : t('generating.transcript.play_title')">
          <svg v-if="!player.playing" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg>
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
          <span class="gen-audio-play-text">{{ player.playing ? t('generating.transcript.pause') : t('generating.transcript.play') }}</span>
        </button>
        <span class="gen-audio-time">{{ player.timeStr }}</span>
        <div class="gen-audio-progress" @click="seekAudio">
          <div class="gen-audio-progress-fill" :style="{ width: player.progress + '%' }"></div>
        </div>
        <button class="gen-audio-speed" @click="player.cycleSpeed()">{{ player.speed }}×</button>
      </div>
    </div>

    <!-- 章节导航条（提升到 gen-content 外层，紧贴 control-zone 下方，消除缝隙） -->
    <div class="chapter-overview" v-if="chapters.length > 0 && activeTab === 'transcript'" id="chapterOverview">
      <span class="chapter-overview-label">{{ t('generating.chapter.overview_label') }}</span>
      <div class="chapter-nav-dots" id="chapterNavDots">
        <div v-for="(ch, i) in chapters" :key="i" class="chapter-nav-dot" :class="{ 'is-active': activeChapterIdx === i, 'is-done': i < activeChapterIdx }" :data-tip="ch.title" @click="scrollToChapter(i)">
        </div>
      </div>
      <div class="chapter-current-info">
        <span>{{ t('generating.chapter.index_prefix') }}</span>
        <span class="ch-name">{{ activeChapterIdx + 1 }}</span>
        <span>{{ t('generating.chapter.index_suffix', { count: chapters.length }) }}</span>
      </div>
      <button class="chapter-transcript-toggle" :class="{ 'is-active': allChaptersVisible }" @click="toggleAllTranscript">
        <svg class="toggle-icon-on" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
        <svg class="toggle-icon-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
      </button>
    </div>

    <!-- 内容区 -->
    <div class="gen-content">
      <!-- 原文面板 -->
      <div class="gen-panel spk-layout-active" v-show="activeTab === 'transcript'">
        <div class="spk-transcript-layout">
          <div class="spk-transcript-area" id="spkTranscriptArea" ref="transcriptAreaEl">
            <!-- 章节生成中提示 -->
            <div class="chapter-loading" v-if="task?.status === 'completed' && !chapters.length">
              <div class="chapter-loading-spinner"></div>
              <span>{{ t('generating.chapter.dividing') }}</span>
            </div>

            <!-- 聚焦模式横幅 -->
            <div class="spk-solo-banner" v-if="speakerFilterSet.size === 1 && focusSpeaker">
              <div class="spk-solo-id">
                <span class="spk-solo-name" :style="{ color: focusSpeaker.color }">{{ focusSpeaker.name }}</span>
                <span class="spk-solo-count">{{ t('generating.speaker_solo.turns', { count: focusSpeaker.turns }) }}</span>
              </div>
              <div class="spk-solo-sep"></div>
              <div class="spk-solo-nav">
                <button class="spk-solo-nav-btn" :title="t('generating.speaker_solo.prev')" @click="navFocusLine(-1)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"/></svg>
                </button>
                <span class="spk-solo-pos">{{ focusLineIdx + 1 }} / {{ focusSpeaker.turns }}</span>
                <button class="spk-solo-nav-btn" :title="t('generating.speaker_solo.next')" @click="navFocusLine(1)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                </button>
              </div>
              <div class="spk-solo-sep"></div>
              <button class="spk-solo-close" :title="t('generating.speaker_solo.exit_focus')" @click="clearSpeakerFilter">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>

            <!-- 原文隐藏提示条 -->
            <div class="gen-hidden-indicator" v-if="visibleChapterIndices.size === 0 && flatTranscript.length">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                <line x1="1" y1="1" x2="23" y2="23"/>
              </svg>
              <span>{{ t('generating.transcript.hidden_indicator', { count: flatTranscript.length }) }}</span>
              <button class="gen-hidden-show-btn" @click="showAllChapters()">{{ t('generating.transcript.show') }}</button>
            </div>

            <div class="gen-loading" v-if="!flatTranscript.length && task?.status && ['recording', 'processing', 'transcribing', 'summarizing'].includes(task.status)">
              <div class="gen-loading-hint"><div class="gen-loading-spinner"></div>{{ t('generating.transcript.loading') }}</div>
              <div class="gen-skeleton"><div class="gen-skeleton-bar"></div><div class="gen-skeleton-bar"></div><div class="gen-skeleton-bar"></div></div>
            </div>
            <div class="gen-empty" v-else-if="!flatTranscript.length && task?.status === 'pending'">
              <div class="gen-empty-hint">{{ t('generating.transcript.pending') }}</div>
            </div>
            <div class="gen-transcript-list" v-else-if="flatTranscript.length" ref="transcriptListEl">
              <template v-for="item in transcriptItems" :key="item.type === 'chapter' ? 'ch-' + item.chapterIdx : 'line-' + item.lineIdx">
                <!-- 章节分隔卡片 -->
                <div v-if="item.type === 'chapter'" class="chapter-divider" :class="{ 'is-current': item.chapterIdx === activeChapterIdx, 'is-expanded': expandedChapters.has(item.chapterIdx) }" :data-chapter="item.chapterIdx">
                  <div class="chapter-header" @click="toggleChapterExpand(item.chapterIdx)">
                    <div class="chapter-number">{{ chapters[item.chapterIdx].id }}</div>
                    <div class="chapter-info">
                      <div class="chapter-title">{{ chapters[item.chapterIdx].title }}</div>
                      <div class="chapter-meta">
                        <span>{{ formatTimeMs(chapters[item.chapterIdx].start_ms) }} – {{ formatTimeMs(chapters[item.chapterIdx].end_ms) }}</span>
                        <span class="sep">·</span>
                        <span>{{ t('generating.chapter.key_points_count', { count: (chapters[item.chapterIdx].key_points || []).length }) }}</span>
                      </div>
                      <div v-if="chapters[item.chapterIdx].summary" class="chapter-summary-text">{{ chapters[item.chapterIdx].summary }}</div>
                    </div>
                    <div class="chapter-chevron">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
                    </div>
                  </div>
                  <div class="chapter-progress-bar">
                    <div class="chapter-progress-fill" :style="{ width: chapterProgress(item.chapterIdx) + '%' }"></div>
                  </div>
                  <div class="chapter-body">
                    <div class="chapter-body-inner">
                      <div class="chapter-key-points" v-if="chapters[item.chapterIdx].key_points?.length">
                        <div class="chapter-key-points-title">{{ t('generating.chapter.key_points') }}</div>
                        <div v-for="(p, pi) in chapters[item.chapterIdx].key_points" :key="pi" class="chapter-key-point">{{ p }}</div>
                      </div>
                      <!-- 展开的章节卡片内始终显示原文显隐切换按钮 -->
                      <button
                        v-if="expandedChapters.has(item.chapterIdx)"
                        class="chapter-view-transcript-btn"
                        :class="{ 'is-active': visibleChapterIndices.has(item.chapterIdx) }"
                        @click="toggleChapterTranscript(item.chapterIdx)"
                      >
                        <svg class="toggle-icon-on" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                          <circle cx="12" cy="12" r="3"/>
                        </svg>
                        <svg class="toggle-icon-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                          <line x1="1" y1="1" x2="23" y2="23"/>
                        </svg>
                        {{ visibleChapterIndices.has(item.chapterIdx) ? t('generating.chapter.hide_transcript') : t('generating.chapter.view_transcript') }}
                      </button>
                    </div>
                  </div>
                </div>
                <!-- 转写行 -->
                <div
                  v-else class="ts-line" v-show="isChapterVisible(getChapterIdxAtTime(chapters, flatTranscript[item.lineIdx].begin_time))"
                  :class="{ 
                    'is-me': isMeSpeakerId(flatTranscript[item.lineIdx].speaker_id),
                    'is-located': isLineLocated(flatTranscript[item.lineIdx].speaker_id),
                    'is-dimmed': isLineDimmed(flatTranscript[item.lineIdx].speaker_id),
                    'is-playing': item.lineIdx === playingLineIdx
                  }"
                  :data-begin-time="flatTranscript[item.lineIdx].begin_time"
                  :data-line-idx="item.lineIdx"
                  @click="seekFromTranscriptClick(flatTranscript[item.lineIdx].begin_time)"
                >
                  <div class="ts-line-head">
                    <span class="spk-wrapper" @click.stop>
                      <span
                        class="spk"
                        :class="[
                          getBindingSpeakerName(flatTranscript[item.lineIdx].speaker_id) ? 'spk-bound' : 'spk-unbound',
                          { 'spk-bindable': canBind }
                        ]"
                        :style="{ color: getSpeakerColor(String(flatTranscript[item.lineIdx].speaker_id)) }"
                        @click="onSpeakerLabelClick($event, flatTranscript[item.lineIdx].speaker_id)"
                      >
                        {{ getBindingSpeakerName(flatTranscript[item.lineIdx].speaker_id) || t('generating.speaker_default', { id: flatTranscript[item.lineIdx].speaker_id + 1 }) }}
                      </span>
                      <button
                        class="spk-locate-btn"
                        :class="{ 'is-active': locateSpeakerId === flatTranscript[item.lineIdx].speaker_id }"
                        v-if="!canBind"
                        @click.stop="toggleLocateSpeaker(flatTranscript[item.lineIdx].speaker_id)"
                        :title="locateSpeakerId === flatTranscript[item.lineIdx].speaker_id ? t('generating.speaker_solo.exit_focus_all') : t('generating.speaker_solo.focus_speaker')"
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>
                      </button>
                      <span class="spk-bind-arrow" v-if="canBind">▾</span>
                    </span>
                    <span class="ts" @click.stop="seekFromTranscriptClick(flatTranscript[item.lineIdx].begin_time)">{{ formatTimeMs(flatTranscript[item.lineIdx].begin_time) }}</span>
                  </div>
                  <div class="ts-line-body">
                    <span class="txt">{{ flatTranscript[item.lineIdx].text }}</span>
                  </div>
                </div>
              </template>
            </div>
          </div>

          <!-- 播放跟随恢复按钮：用户手动滚动后出现 -->
          <button
            class="ts-follow-btn" :class="{ 'is-visible': player.playing && !followPlayback }"
            @click="resumeFollowPlayback" :title="t('generating.speaker_solo.back_to_playback_title')" :aria-label="t('generating.speaker_solo.back_to_playback_title')"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polygon points="10,8 16,12 10,16" fill="currentColor" stroke="none"/></svg>
            {{ t('generating.speaker_solo.back_to_playback') }}
          </button>

          <!-- 右侧说话人面板 -->
          <div class="spk-panel" v-if="speakerPanelVisible">
            <div class="spk-panel-head">
              <span class="spk-panel-title">
                {{ t('generating.speaker_panel.title') }}
              </span>
              <div class="spk-panel-head-actions">
                <button class="spk-panel-btn spk-search-trigger" :class="{ 'is-active': searchExpanded }" @click="toggleSearch" :title="t('generating.speaker_panel.search')">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                </button>
                <button class="spk-panel-btn" :title="t('generating.speaker_panel.collapse')" @click="speakerPanelVisible = false">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
                </button>
              </div>
            </div>
            <div class="spk-search" v-show="searchExpanded || speakerPanelSearch">
              <div class="spk-search-wrap">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                <input type="text" class="spk-search-input" :placeholder="t('generating.speaker_panel.search_placeholder')" v-model="speakerPanelSearch" @blur="onSearchBlur" ref="searchInputEl">
              </div>
            </div>
            <div class="spk-list">
              <div
                v-for="sp in panelSpeakerList" :key="sp.speakerId"
                class="spk-item"
                :class="{ 'is-on': speakerFilterSet.has(sp.speakerId), 'is-active': locateSpeakerId === sp.speakerId, 'is-playing': playingSpeakerId === sp.speakerId }"
                @click="toggleSpeakerFilter(sp.speakerId)"
              >
                <div class="spk-item-check">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
                <div class="spk-item-info">
                  <div class="spk-item-name" :style="{ color: sp.color }">{{ sp.name }}</div>
                  <div class="spk-item-role" :class="{ 'is-me-label': sp.isMe }">{{ sp.isMe ? t('generating.speaker_panel.me_label') : (sp.role || '') }}</div>
                </div>
                <div class="spk-item-stats">
                  <span class="spk-item-dur">{{ sp.durationStr }}</span>
                  <span class="spk-item-sep">|</span>
                  <span class="spk-item-turns">{{ sp.turns }}</span>
                </div>
              </div>
            </div>
            <div class="spk-panel-footer">
              <span class="spk-footer-summary">
                {{ t('generating.speaker_panel.total', { duration: panelTotalDuration, turns: panelTotalTurns }) }}
              </span>
            </div>
          </div>

          <!-- 面板收起时的展开按钮 -->
          <button class="spk-panel-toggle" v-if="!speakerPanelVisible" @click="speakerPanelVisible = true" :title="t('generating.speaker_panel.expand')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
            <span>{{ t('generating.speaker_panel.expand') }}</span>
          </button>
        </div>
      </div>

      <!-- 纪要面板 -->
      <div class="gen-panel" v-show="activeTab === 'summary'" :class="{ hidden: activeTab !== 'summary' }">
        <div class="gen-loading" v-if="!task?.summary && task?.status && ['recording', 'processing', 'transcribing', 'summarizing', 'awaiting_mapping'].includes(task.status)">
          <div class="gen-loading-hint"><div class="gen-loading-spinner"></div>{{ t('generating.summary.loading') }}</div>
          <div class="gen-skeleton"><div class="gen-skeleton-bar"></div><div class="gen-skeleton-bar"></div><div class="gen-skeleton-bar"></div></div>
        </div>
        <div class="gen-empty" v-else-if="!task?.summary && task?.status === 'pending'">
          <div class="gen-empty-hint">{{ t('generating.summary.pending') }}</div>
        </div>
        <MdBlockEditor
          v-else-if="task?.summary"
          :markdown="summaryMd"
          @change="onSummaryChange"
          ref="summaryEditor"
        />
        <!-- 章节回顾卡片 -->
        <div class="sum-section" v-if="task?.summary && chapters.length > 0">
          <div class="sum-section-label">{{ t('generating.chapter.review') }}</div>
          <div
            v-for="(ch, idx) in chapters" :key="'sum-ch-' + idx"
            class="sum-chapter-card"
            :class="{ 'is-open': summaryExpandedChapters.has(idx) }"
          >
            <button class="sum-chapter-header" @click="toggleSummaryChapter(idx)" :title="ch.title">
              <div class="sum-chapter-num">{{ ch.id || idx + 1 }}</div>
              <div class="sum-chapter-info">
                <div class="sum-chapter-title">{{ ch.title }}</div>
                <div class="sum-chapter-meta">
                  <span>{{ formatTimeMs(ch.start_ms) }} – {{ formatTimeMs(ch.end_ms) }}</span>
                  <span class="sep">·</span>
                  <span>{{ t('generating.chapter.key_points_count', { count: (ch.key_points || []).length }) }}</span>
                </div>
              </div>
              <div class="sum-chapter-chevron">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
              </div>
            </button>
            <ul class="sum-chapter-points" v-if="ch.key_points?.length">
              <li v-for="(p, pi) in ch.key_points" :key="pi">{{ p }}</li>
            </ul>
          </div>
        </div>
        <!-- 行动项入口 -->
        <div class="sum-section" v-if="task?.summary">
          <div class="sum-section-label">{{ t('generating.summary.action_items') }}</div>
          <button class="sum-todos-link" @click="switchTab('todos')" :title="t('generating.summary.view_todos')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
            <span>{{ t('generating.summary.todos_stat', { total: todos.length || '—', done: todos.filter(x => x.done).length || '0' }) }}</span>
            <span class="go">{{ t('generating.summary.view_todos') }}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
            </span>
          </button>
        </div>
        <div class="gen-pending" v-else>
          <div class="gen-pending-text">{{ t('generating.summary.pending') }}</div>
        </div>
      </div>

      <!-- 随记面板 -->
      <div class="gen-panel" v-show="activeTab === 'notes'" :class="{ hidden: activeTab !== 'notes' }">
        <div class="md-toolbar">
          <button class="md-toolbar-btn" @click="insertMd('bold')" :title="t('generating.md_toolbar.bold')"><strong>B</strong></button>
          <button class="md-toolbar-btn" @click="insertMd('italic')" :title="t('generating.md_toolbar.italic')"><em>I</em></button>
          <button class="md-toolbar-btn" @click="insertMd('code')" :title="t('generating.md_toolbar.code')">&lt;/&gt;</button>
          <span class="md-toolbar-sep"></span>
          <button class="md-toolbar-btn" @click="insertMd('heading')" :title="t('generating.md_toolbar.heading')">H</button>
          <button class="md-toolbar-btn" @click="insertMd('list')" :title="t('generating.md_toolbar.list')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
          </button>
          <button class="md-toolbar-btn" @click="insertMd('quote')" :title="t('generating.md_toolbar.quote')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V21z"/><path d="M15 21c3 0 7-1 7-8V5c0-1.25-.757-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2h.75c0 2.25.25 4-2.75 4v3z"/></svg>
          </button>
          <span class="md-toolbar-hint">{{ t('generating.md_toolbar.hint') }}</span>
        </div>
        <MdBlockEditor
          :markdown="notesContent"
          @change="onNotesChange"
          ref="notesEditor"
          :empty-text="t('generating.notes.placeholder')"
        />
        <span class="task-notes-saved" :class="{ show: notesSaved }">{{ t('generating.notes.saved') }}</span>
      </div>

      <!-- 待办面板 -->
      <div class="gen-panel" v-show="activeTab === 'todos'" :class="{ hidden: activeTab !== 'todos' }">
        <div class="todos-summary" v-if="todos.length">
          <span>{{ t('generating.todos.stat', { total: todos.length, done: todos.filter(x => x.done).length }) }}</span>
        </div>
        <div class="todos-list" v-if="todos.length">
          <div v-for="todo in todos" :key="todo.id" class="todo-item" :class="{ done: todo.done }">
            <input type="checkbox" :checked="todo.done" @change="onToggleTodo(todo)">
            <span class="todo-text">{{ todo.text }}</span>
            <span v-if="todo.assignee" class="todo-assignee">{{ todo.assignee }}</span>
            <span v-if="todo.source" class="todo-source-badge" :class="'source-' + todo.source">{{ todo.source === 'ai' ? t('generating.todos.source_ai') : t('generating.todos.source_manual') }}</span>
            <button v-if="todo.source === 'ai'" class="todo-locate-btn" :title="t('generating.todos.locate')" @click="locateTodoSource(todo)" :aria-label="t('generating.todos.locate')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>
            </button>
            <button class="todo-delete-btn" :title="t('generating.todos.delete')" @click="onDeleteTodo(todo)" :aria-label="t('generating.todos.delete')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
            </button>
          </div>
        </div>
        <div class="todos-empty" v-else>{{ t('generating.todos.empty') }}</div>
        <div class="todos-add-bar">
          <button class="todos-add-btn" @click="showAddForm = !showAddForm" v-if="!showAddForm">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            {{ t('generating.todos.add') }}
          </button>
          <div class="todos-add-form" v-if="showAddForm">
            <textarea v-model="newTodoText" :placeholder="t('generating.todos.content_placeholder')" rows="2"></textarea>
            <div class="add-form-row">
              <input type="text" v-model="newTodoAssignee" :placeholder="t('generating.todos.assignee_placeholder')" style="flex:1">
            </div>
            <div class="add-form-actions">
              <button class="btn-cancel" @click="showAddForm = false">{{ t('generating.todos.cancel') }}</button>
              <button class="btn-submit" @click="onAddTodo">{{ t('generating.todos.submit') }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <!-- 浮动选中工具栏 -->
    <SelectionToolbar
      container-selector=".gen-content"
      @action="onSelectionAction"
    />

    <!-- 说话人绑定引导弹窗（数据变化感知版） -->
    <div v-if="showOnboarding" class="spk-onboarding-overlay" @click.self="closeOnboarding" @keydown.esc="closeOnboarding">
      <div class="spk-onboarding-card" role="dialog" aria-modal="true" aria-labelledby="obDialogTitle">
        <!-- 标题区 -->
        <div class="spk-ob-header">
          <h3 id="obDialogTitle">{{ t('generating.onboarding.title') }}</h3>
        </div>
        <!-- 数据变化演示区 -->
        <div class="spk-ob-demo">
          <div class="spk-ob-transcript">
            <div class="spk-ob-line" v-for="(line, i) in demoLines" :key="i" :class="{ 'is-me': line.isMe }">
              <div class="spk-ob-head">
                <span class="spk-ob-ts">{{ line.ts }}</span>
                <span class="spk-ob-spk" :class="line.bound ? 'bound' : 'unbound'" :style="line.bound ? { background: line.color } : {}">{{ line.bound ? line.name : line.label }}</span>
              </div>
              <div class="spk-ob-text" :class="line.bound ? 'bound' : 'unbound'">
                <div class="spk-ob-skeleton">
                  <div class="spk-ob-skel-bar" :style="{ width: line.bar1 }"></div>
                  <div class="spk-ob-skel-bar" :style="{ width: line.bar2 }"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <!-- 底部操作区 -->
        <div class="spk-ob-footer">
          <label class="spk-ob-dont-show">
            <input type="checkbox" v-model="dontShowAgain"> {{ t('generating.onboarding.dont_show_again') }}
          </label>
          <button type="button" class="spk-ob-got-it" @click="closeOnboarding">{{ t('generating.onboarding.start') }}</button>
        </div>
      </div>
    </div>

    <!-- 归档确认对话框 -->
    <div v-if="showArchiveDialog" class="archive-dialog-overlay" @click.self="showArchiveDialog = false">
      <div class="archive-dialog">
        <div class="archive-dialog-header">
          <h3>{{ t('generating.archive_dialog.title') }}</h3>
          <button class="archive-dialog-close" @click="showArchiveDialog = false" :title="t('generating.archive_dialog.close')">
            <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
          </button>
        </div>
        <div class="archive-dialog-body">
          <p>{{ t('generating.archive_dialog.desc') }}</p>
        </div>
        <div class="archive-dialog-footer">
          <button class="btn-cancel" @click="showArchiveDialog = false">{{ t('generating.archive_dialog.cancel') }}</button>
          <button class="btn-submit" @click="onArchive">{{ t('generating.archive_dialog.confirm') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, reactive, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { usePlayerStore } from '@/stores/player'
import { useUserStore } from '@/stores/user'
import { usePolling } from '@/composables/usePolling'
import { fetchTask, deleteTask, retranscribe, retrySummary, updateTask } from '@/api/tasks'
import { fetchNotes, saveNotes, fetchTodos, toggleTodo, createTodo, deleteTodo } from '@/api/notes'
import { fetchSpeakers, createSpeaker, submitSpeakerMapping, saveSpeakerMapping, type Speaker } from '@/api/speakers'
import { fetchProjects, type Project } from '@/api/projects'
import { useQuoteRef } from '@/composables/useQuoteRef'
import { usePopMenu } from '@/composables/usePopMenu'
import { getSpeakerColor } from '@/utils/speakerColors'
import type { DialogueLine, TodoItem, Chapter, FlatTranscriptLine } from '@/api/types'
import MdBlockEditor from '@/components/MdBlockEditor.vue'
import SelectionToolbar from '@/components/SelectionToolbar.vue'

const { t } = useI18n()

const TABS = computed(() => [
  { id: 'transcript', label: t('generating.tabs.transcript'), icon: '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/>' },
  { id: 'notes', label: t('generating.tabs.notes'), icon: '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>' },
  { id: 'summary', label: t('generating.tabs.summary'), icon: '<path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><line x1="9" y1="12" x2="15" y2="12"/><line x1="9" y1="16" x2="13" y2="16"/>' },
  { id: 'todos', label: t('generating.tabs.todos'), icon: '<polyline points="9,11 12,14 22,4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>' },
])

const route = useRoute()
const router = useRouter()
const taskStore = useTaskStore()
const userStore = useUserStore()
const taskId = route.params.taskId as string

const activeTab = ref('transcript')

// Restore saved tab from localStorage
onMounted(() => {
  const saved = localStorage.getItem('oms_gen_active_tab')
  if (saved) activeTab.value = saved
})
const genMoreBtn = ref<HTMLElement | null>(null)
const genMoreDropdown = ref<HTMLElement | null>(null)
const { visible: showMoreMenu, toggle: toggleGenMore, close: closeGenMore } = usePopMenu(genMoreDropdown, genMoreBtn)
const notesContent = ref('')
const notesSaved = ref(false)
const notesArea = ref<HTMLTextAreaElement | null>(null)
const summaryEditor = ref<InstanceType<typeof MdBlockEditor> | null>(null)
const notesEditor = ref<InstanceType<typeof MdBlockEditor> | null>(null)
const summaryMd = ref('')
const { setQuote, startRewrite, rewritePending, registerBlockUpdater, registerSummaryAppender, registerNotesAppender } = useQuoteRef()
const todos = ref<TodoItem[]>([])
const showAddForm = ref(false)
const newTodoText = ref('')
const newTodoAssignee = ref('')
let notesTimer: ReturnType<typeof setTimeout> | null = null

// 说话人绑定引导
const showOnboarding = ref(false)
const dontShowAgain = ref(false)

// 引导弹窗演示数据
const demoLines = reactive([
  { ts: '23:15', label: '说话人 1', name: '赵里海', color: 'oklch(55% 0.16 250)', bound: false, isMe: false, bar1: '100%', bar2: '60%' },
  { ts: '23:18', label: '说话人 2', name: '沈天雅', color: 'oklch(55% 0.14 150)', bound: false, isMe: false, bar1: '80%', bar2: '45%' },
  { ts: '23:20', label: '说话人 1', name: '赵里海', color: 'oklch(55% 0.16 250)', bound: false, isMe: true, bar1: '45%', bar2: '35%' },
])
let obAnimTimer: ReturnType<typeof setTimeout> | null = null
let obLoopTimer: ReturnType<typeof setTimeout> | null = null
const OB_CYCLE_MS = 4000
const OB_PAUSE_MS = 1500

const speakers = ref<Speaker[]>([])

// 按章节控制原文显隐（Set 中的章节索引对应的原文行可见）
const visibleChapterIndices = reactive(new Set<number>())

// 定位高亮说话人
const locateSpeakerId = ref<number | null>(null)

// 归档确认对话框
const showArchiveDialog = ref(false)

// 项目关联
const projects = ref<Project[]>([])
const showProjectDropdown = ref(false)
const currentProjectName = computed(() => {
  if (!task.value?.project_id) return t('generating.meta.link_project')
  const p = projects.value.find(p => p.id === task.value?.project_id)
  return p?.name || t('generating.meta.link_project')
})

const breadcrumbTitle = computed(() => task.value?.title || task.value?.audio_name || t('generating.breadcrumb.default_title'))

/** 面包屑祖先层级：已关联项目时展示 项目 / 项目名，否则展示 会议库 */
const breadcrumbs = computed(() => {
  const pid = task.value?.project_id
  const proj = pid ? projects.value.find(p => p.id === pid) : null
  if (proj) {
    return [
      { label: t('generating.breadcrumb.project'), icon: 'folder' as const, to: { name: 'projects' } },
      { label: proj.name, icon: null, to: { name: 'projects' } },
    ]
  }
  return [{ label: t('generating.breadcrumb.library'), icon: 'list' as const, to: { name: 'library' } }]
})

// 绑定横幅关闭
const bindingBarHidden = ref(false)
// 任务级「暂不关联」：跨会话持久隐藏绑定栏
const bindBarDismissed = ref(localStorage.getItem(`oms_bind_bar_dismissed:${taskId}`) === 'true')

// ─── 右侧说话人面板 ───
const speakerPanelVisible = ref(true)
const speakerPanelSearch = ref('')
const searchExpanded = ref(false)
const searchInputEl = ref<HTMLInputElement | null>(null)
const speakerFilterSet = reactive(new Set<number>())
const focusLineIdx = ref(0)

/** 切换搜索栏展开/收起 */
function toggleSearch() {
  searchExpanded.value = !searchExpanded.value
  if (searchExpanded.value) {
    nextTick(() => searchInputEl.value?.focus())
  }
}

/** 搜索框失焦时，若无搜索词则收起 */
function onSearchBlur() {
  if (!speakerPanelSearch.value) {
    searchExpanded.value = false
  }
}

/** 隐式收起：点击说话人搜索栏外部自动关闭 */
function onDocClickCloseSearch(e: MouseEvent) {
  if (!searchExpanded.value) return
  const target = e.target as HTMLElement
  if (!target.closest('.spk-search') && !target.closest('.spk-search-trigger')) {
    searchExpanded.value = false
  }
}

/** 面板中的说话人列表（含时长/次数/角色统计） */
const panelSpeakerList = computed(() => {
  const lines = flatTranscript.value
  if (!lines.length) return []
  const q = speakerPanelSearch.value.toLowerCase()
  const speakerMap = new Map<number, { durMs: number; turns: number }>()
  for (const l of lines) {
    const cur = speakerMap.get(l.speaker_id) || { durMs: 0, turns: 0 }
    cur.durMs += l.end_time - l.begin_time
    cur.turns += 1
    speakerMap.set(l.speaker_id, cur)
  }
  return Array.from(speakerMap.entries())
    .sort((a, b) => b[1].durMs - a[1].durMs)
    .map(([sid, stats]) => {
      const uuid = currentBindingMapping[sid] || task.value?.speaker_uuid_mapping?.[String(sid)]
      const spk = uuid ? speakers.value.find(s => s.id === uuid) : null
      const name = spk?.name || t('generating.speaker_default', { id: sid + 1 })
      const role = spk?.role || ''
      const isMe = spk?.linked_user_id ? spk.linked_user_id === userStore.user?.id : false
      const m = Math.floor(stats.durMs / 60000)
      const s = Math.floor((stats.durMs % 60000) / 1000)
      return {
        speakerId: sid,
        name,
        role,
        isMe,
        color: getSpeakerColor(String(sid)),
        durationStr: `${m}:${String(s).padStart(2, '0')}`,
        turns: stats.turns,
      }
    })
    .filter(item => {
      if (!q) return true
      return item.name.toLowerCase().includes(q) || item.role.toLowerCase().includes(q)
    })
})

const panelTotalDuration = computed(() => {
  const lines = flatTranscript.value
  if (!lines.length) return '00:00'
  const totalMs = lines.reduce((sum, l) => sum + (l.end_time - l.begin_time), 0)
  const m = Math.floor(totalMs / 60000)
  const s = Math.floor((totalMs % 60000) / 1000)
  return `${m}:${String(s).padStart(2, '0')}`
})

const panelTotalTurns = computed(() => flatTranscript.value.length)

/** 聚焦模式下的目标说话人 */
const focusSpeaker = computed(() => {
  if (speakerFilterSet.size !== 1) return null
  const sid = Array.from(speakerFilterSet)[0]
  return panelSpeakerList.value.find(sp => sp.speakerId === sid) || null
})

/** 聚焦模式下的行列表 */
const focusLines = computed(() => {
  if (speakerFilterSet.size !== 1) return []
  const sid = Array.from(speakerFilterSet)[0]
  return flatTranscript.value
    .map((l, i) => ({ ...l, idx: i }))
    .filter(l => l.speaker_id === sid)
})

/** 切换说话人筛选 */
function toggleSpeakerFilter(id: number) {
  if (speakerFilterSet.has(id)) {
    speakerFilterSet.delete(id)
  } else {
    speakerFilterSet.add(id)
  }
  focusLineIdx.value = 0
  locateSpeakerId.value = speakerFilterSet.size === 1 ? Array.from(speakerFilterSet)[0] : null
}

/** 清除筛选 */
function clearSpeakerFilter() {
  speakerFilterSet.clear()
  locateSpeakerId.value = null
  focusLineIdx.value = 0
}

/** 判断原文行是否高亮 */
function isLineLocated(speakerId: number): boolean {
  if (speakerFilterSet.size > 0) return speakerFilterSet.has(speakerId)
  return locateSpeakerId.value !== null && speakerId === locateSpeakerId.value
}

/** 判断原文行是否淡化 */
function isLineDimmed(speakerId: number): boolean {
  if (speakerFilterSet.size > 0) return !speakerFilterSet.has(speakerId)
  return locateSpeakerId.value !== null && speakerId !== locateSpeakerId.value
}

/** 聚焦模式上下条导航 */
function navFocusLine(delta: number) {
  const lines = focusLines.value
  if (!lines.length) return
  focusLineIdx.value = (focusLineIdx.value + delta + lines.length) % lines.length
  const targetLine = lines[focusLineIdx.value]
  nextTick(() => {
    const el = transcriptListEl.value?.querySelector(`[data-begin-time="${targetLine.begin_time}"]`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
}

// ─── 说话人绑定核心状态 ───
const currentBindingMapping = reactive<Record<number, string>>({})
const bindingDropdown = reactive<{
  visible: boolean
  speakerId: number
  x: number
  y: number
  search: string
  focusIdx: number
}>({ visible: false, speakerId: -1, x: 0, y: 0, search: '', focusIdx: -1 })
let dropdownEl: HTMLElement | null = null

/** 从 speaker_uuid_mapping 初始化绑定映射 */
function initBindingMapping() {
  const m = task.value?.speaker_uuid_mapping
  Object.keys(currentBindingMapping).forEach(k => delete currentBindingMapping[Number(k)])
  if (m) {
    for (const [k, v] of Object.entries(m)) {
      if (v) currentBindingMapping[Number(k)] = v
    }
  }
}

/** 绑定栏中的说话人芯片列表（按时长降序） */
const bindingLegend = computed(() => {
  const lines = flatTranscript.value
  if (!lines.length) return []
  const totalMs = lines.reduce((sum, l) => sum + (l.end_time - l.begin_time), 0)
  const speakerMap = new Map<number, number>()
  for (const l of lines) {
    speakerMap.set(l.speaker_id, (speakerMap.get(l.speaker_id) || 0) + (l.end_time - l.begin_time))
  }
  return Array.from(speakerMap.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([sid, durMs]) => {
      const uuid = currentBindingMapping[sid]
      const bound = uuid ? speakers.value.find(s => s.id === uuid) : null
      const pct = totalMs > 0 ? Math.round((durMs / totalMs) * 100) : 0
      return { sid, durMs, pct, color: getSpeakerColor(String(sid)), name: bound?.name || '', bound: !!bound }
    })
})

const unboundCount = computed(() => bindingLegend.value.filter(b => !b.bound).length)

/** 可绑定状态：转写已完成且仍有未关联说话人（纪要生成不再等待绑定，绑定为事后补充） */
const canBind = computed(() => {
  const s = task.value?.status
  return unboundCount.value > 0 && (s === 'awaiting_mapping' || s === 'completed')
})

/** 绑定栏可见：可绑定且未会话级关闭、未任务级「暂不关联」 */
const showBindingBar = computed(() => canBind.value && !bindingBarHidden.value && !bindBarDismissed.value)

/** 下拉框中过滤后的说话人列表 */
const dropdownSpeakers = computed(() => {
  const q = bindingDropdown.search.toLowerCase()
  if (!q) return speakers.value
  return speakers.value.filter(s => s.name.toLowerCase().includes(q) || (s.role || '').toLowerCase().includes(q))
})

/** 打开绑定下拉框 */
function openBindingDropdown(e: MouseEvent, speakerId: number) {
  e.stopPropagation()
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  bindingDropdown.speakerId = speakerId
  bindingDropdown.x = rect.left
  bindingDropdown.y = rect.bottom + 4
  bindingDropdown.search = ''
  bindingDropdown.focusIdx = -1
  bindingDropdown.visible = true

  nextTick(() => {
    const dd = document.querySelector('.bt-dropdown') as HTMLElement
    if (dd) {
      dropdownEl = dd
      const input = dd.querySelector('input') as HTMLInputElement
      input?.focus()
      adjustDropdownPosition(dd)
    }
  })
}

function adjustDropdownPosition(dd: HTMLElement) {
  const vw = window.innerWidth, vh = window.innerHeight
  const r = dd.getBoundingClientRect()
  if (r.right > vw - 8) bindingDropdown.x = vw - r.width - 8
  if (r.bottom > vh - 8) bindingDropdown.y = bindingDropdown.y - r.height - 28
}

function closeBindingDropdown() {
  bindingDropdown.visible = false
  dropdownEl = null
}

/** 选择绑定选项 */
async function selectBinding(speakerId: number, uuid: string) {
  if (uuid) {
    currentBindingMapping[speakerId] = uuid
  } else {
    delete currentBindingMapping[speakerId]
  }
  closeBindingDropdown()
  await incrementalSave()
}

/** 新建说话人并绑定 */
async function createAndBind(speakerId: number, suggestedName: string) {
  const name = suggestedName || t('generating.speaker_default', { id: speakerId + 1 })
  try {
    const newSpk = await createSpeaker(name)
    currentBindingMapping[speakerId] = newSpk.id
    speakers.value.push(newSpk)
    closeBindingDropdown()
    await incrementalSave()
  } catch (e) {
    console.error('create speaker failed:', e)
  }
}

/** 增量保存（不触发重新生成） */
async function incrementalSave() {
  if (!['awaiting_mapping', 'completed'].includes(task.value?.status ?? '')) return
  const mapping = Object.fromEntries(Object.entries(currentBindingMapping).map(([k, v]) => [String(k), v]))
  try {
    await saveSpeakerMapping(taskId, mapping)
    taskStore.patchTaskLocal(taskId, { speaker_uuid_mapping: { ...currentBindingMapping } })
  } catch (e) {
    console.error('incremental save mapping failed:', e)
  }
}

/** 确认关联 → 提交映射并触发纪要生成 */
async function confirmMapping() {
  bindingBarHidden.value = true
  switchTab('summary')
  const mapping = Object.fromEntries(Object.entries(currentBindingMapping).map(([k, v]) => [String(k), v]))
  try {
    await submitSpeakerMapping(taskId, mapping)
    taskStore.patchTaskLocal(taskId, { speaker_uuid_mapping: { ...currentBindingMapping }, status: 'summarizing' })
    startPolling()
  } catch (e) {
    console.error('submit mapping failed:', e)
    bindingBarHidden.value = false
  }
}

/** 暂不关联 → 任务级持久隐藏绑定栏（纪要保留通用说话人标签） */
function skipMapping() {
  bindingBarHidden.value = true
  bindBarDismissed.value = true
  localStorage.setItem(`oms_bind_bar_dismissed:${taskId}`, 'true')
}

/** 下拉框键盘导航 */
function onDropdownKeydown(e: KeyboardEvent) {
  const items = dropdownSpeakers.value
  const hasCreateBtn = bindingDropdown.search && items.length === 0
  const total = hasCreateBtn ? 1 : items.length
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    bindingDropdown.focusIdx = total > 0 ? (bindingDropdown.focusIdx + 1) % total : 0
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    bindingDropdown.focusIdx = total > 0 ? (bindingDropdown.focusIdx <= 0 ? total - 1 : bindingDropdown.focusIdx - 1) : 0
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (hasCreateBtn && bindingDropdown.focusIdx === 0) {
      createAndBind(bindingDropdown.speakerId, bindingDropdown.search)
    } else if (bindingDropdown.focusIdx >= 0 && bindingDropdown.focusIdx < items.length) {
      selectBinding(bindingDropdown.speakerId, items[bindingDropdown.focusIdx].id)
    }
  } else if (e.key === 'Escape') {
    e.preventDefault()
    closeBindingDropdown()
  }
}

// 点击外部关闭下拉框
function onDocClickForDropdown(e: MouseEvent) {
  if (bindingDropdown.visible && dropdownEl && !dropdownEl.contains(e.target as Node)) {
    closeBindingDropdown()
  }
}

// 音频（全局 player store：路由切换后播放不中断，列表/侧边栏/顶栏共享状态）
const player = usePlayerStore()

/** 当前播放时间对应的原文行下标，-1 表示无 */
const playingLineIdx = ref(-1)
/** 是否随播放进度自动滚动原文；用户手动滚动后置 false */
const followPlayback = ref(true)

/** 当前播放行对应的说话人 ID（用于面板高亮），无播放时为 null */
const playingSpeakerId = computed<number | null>(() => {
  if (playingLineIdx.value < 0) return null
  return flatTranscript.value[playingLineIdx.value]?.speaker_id ?? null
})

const task = computed(() => taskStore.tasks.find(t => t.task_id === taskId) ?? null)
// 任务进入 store 时初始化绑定映射：刷新时 store 异步装载可能晚于 onMounted 的初始化
watch(() => task.value?.task_id, () => initBindingMapping(), { immediate: true })
const dialogue = computed<DialogueLine[]>(() => task.value?.dialogue ?? [])
const audioUrl = computed(() => task.value ? `/api/audio/${task.value.task_id}` : '')

// 本会议音频载入全局播放器：同任务保持状态，切换任务时释放旧音频
watch(audioUrl, (url) => { if (url) player.load(taskId, url) }, { immediate: true })

// 播放进度驱动原文跟随；播放器离开本会议时清除当前行标记
watch(() => player.currentTime, (sec) => {
  if (player.taskId === taskId) syncPlayingLine(sec * 1000)
})
watch(() => player.taskId, (id) => {
  if (id !== taskId) playingLineIdx.value = -1
})
const metaDateShort = computed(() => {
  const d = task.value?.meeting_date || task.value?.created_at?.slice(0, 10) || ''
  return d
})

const metaDuration = computed(() => {
  const sec = task.value?.audio_duration
  if (!sec || sec <= 0) return '00:00'
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
})

const speakerNames = computed(() => {
  const m = task.value?.speaker_mapping
  return m ? Object.values(m).filter(Boolean) : []
})

const speakerStats = computed(() => {
  const mapping = task.value?.speaker_mapping
  if (!mapping) return []
  const lines = flatTranscript.value
  if (!lines.length) return []
  const totalMs = lines.reduce((sum, l) => sum + (l.end_time - l.begin_time), 0)
  if (totalMs <= 0) return []
  const speakerIds = Object.keys(mapping).sort((a, b) => Number(a) - Number(b))
  return speakerIds.map((sid) => {
    const sidNum = Number(sid)
    // 优先从绑定映射解析真实姓名，其次用 ASR 返回的 speaker_mapping，最后 i18n 兜底
    const uuid = currentBindingMapping[sidNum]
    const boundSpk = uuid ? speakers.value.find(s => s.id === uuid) : null
    const name = boundSpk?.name || mapping[sid] || t('generating.speaker_default', { id: sidNum + 1 })
    const durMs = lines.filter(l => String(l.speaker_id) === sid)
      .reduce((sum, l) => sum + (l.end_time - l.begin_time), 0)
    const pct = Math.round((durMs / totalMs) * 100)
    return { name, pct, color: getSpeakerColor(sid) }
  })
})

// 章节
const transcriptAreaEl = ref<HTMLElement | null>(null)
const transcriptListEl = ref<HTMLElement | null>(null)
const activeChapterIdx = ref(0)
const expandedChapters = reactive(new Set<number>())
const summaryExpandedChapters = reactive(new Set<number>())

const chapters = computed<Chapter[]>(() => task.value?.chapters ?? [])

// 章节首次加载时初始化可见集合（默认全部可见），仅执行一次
watch(chapters, (chs) => {
  if (chs.length > 0 && visibleChapterIndices.size === 0) {
    chs.forEach((_, idx) => visibleChapterIndices.add(idx))
  }
}, { immediate: true })

function toggleSummaryChapter(idx: number) {
  if (summaryExpandedChapters.has(idx)) summaryExpandedChapters.delete(idx)
  else summaryExpandedChapters.add(idx)
}

/** 将 dialogue.sentences 展开为扁平列表，按 begin_time 排序 */
const flatTranscript = computed<FlatTranscriptLine[]>(() => {
  const all: FlatTranscriptLine[] = []
  for (const d of dialogue.value) {
    if (!d.sentences) continue
    for (const s of d.sentences) {
      all.push({
        begin_time: s.begin_time,
        end_time: s.end_time,
        text: s.text,
        speaker_id: s.speaker_id,
        sentence_id: s.sentence_id,
      })
    }
  }
  all.sort((a, b) => a.begin_time - b.begin_time)
  return all
})

type TranscriptItem = { type: 'chapter'; chapterIdx: number } | { type: 'line'; lineIdx: number }

const transcriptItems = computed<TranscriptItem[]>(() => {
  const items: TranscriptItem[] = []
  const lines = flatTranscript.value
  if (!lines.length) return items
  const chs = chapters.value
  let lastChIdx = -2

  for (let lineIdx = 0; lineIdx < lines.length; lineIdx++) {
    const lineMs = lines[lineIdx].begin_time
    const chIdx = getChapterIdxAtTime(chs, lineMs)

    if (chs.length > 0 && chIdx !== lastChIdx && chIdx >= 0) {
      items.push({ type: 'chapter', chapterIdx: chIdx })
      lastChIdx = chIdx
    }
    items.push({ type: 'line', lineIdx })
  }
  return items
})

function getChapterIdxAtTime(chs: Chapter[], ms: number): number {
  for (let i = chs.length - 1; i >= 0; i--) {
    if (ms >= chs[i].start_ms) return i
  }
  return -1
}

function formatTimeMs(ms: number): string {
  const sec = Math.floor(ms / 1000)
  const m = Math.floor(sec / 60), s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function toggleChapterExpand(idx: number) {
  if (expandedChapters.has(idx)) expandedChapters.delete(idx)
  else expandedChapters.add(idx)
}

function scrollToChapter(idx: number) {
  activeChapterIdx.value = idx
  nextTick(() => {
    const el = transcriptListEl.value?.querySelector(`.chapter-divider[data-chapter="${idx}"]`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

/** 切换单个章节原文显隐（章节卡片按钮调用，带滚动定位） */
function toggleChapterTranscript(idx: number) {
  if (idx < 0) return
  if (visibleChapterIndices.has(idx)) {
    visibleChapterIndices.delete(idx)
  } else {
    visibleChapterIndices.add(idx)
  }
  nextTick(() => {
    const el = transcriptListEl.value?.querySelector(`.chapter-divider[data-chapter="${idx}"]`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

/** 全局切换所有章节原文显隐（导航栏按钮调用） */
function toggleAllTranscript() {
  if (allChaptersVisible.value) {
    visibleChapterIndices.clear()
  } else {
    chapters.value.forEach((_, idx) => visibleChapterIndices.add(idx))
  }
}

/** 显示所有章节原文 */
function showAllChapters() {
  chapters.value.forEach((_, idx) => visibleChapterIndices.add(idx))
}

/** 判断章节原文是否可见 */
function isChapterVisible(chapterIdx: number): boolean {
  if (chapterIdx < 0) return true // 无章节归属的行始终显示
  return visibleChapterIndices.has(chapterIdx)
}

/** 是否所有章节原文都可见 */
const allChaptersVisible = computed(() => {
  if (chapters.value.length === 0) return true
  return visibleChapterIndices.size === chapters.value.length
})

function chapterProgress(idx: number): number {
  const ch = chapters.value[idx]
  if (!ch || !flatTranscript.value.length) return 0
  const linesInChapter = flatTranscript.value.filter(l => {
    return l.begin_time >= ch.start_ms && l.begin_time <= ch.end_ms
  })
  return linesInChapter.length > 0 ? 100 : 0
}

/** 获取绑定状态下的说话人名称（优先从 currentBindingMapping 查） */
function getBindingSpeakerName(speakerId: number): string {
  const uuid = currentBindingMapping[speakerId]
  if (!uuid) return ''
  const spk = speakers.value.find(s => s.id === uuid)
  return spk?.name || ''
}

/** 说话人标签点击：绑定模式下打开下拉框，否则切换定位 */
function onSpeakerLabelClick(e: MouseEvent, speakerId: number) {
  if (canBind.value) {
    openBindingDropdown(e, speakerId)
  } else {
    toggleLocateSpeaker(speakerId)
  }
}

/** 获取说话人背景色（用于绑定栏芯片） */
function getSpeakerBg(speakerId: number): string {
  const color = getSpeakerColor(String(speakerId))
  return `${color}18`
}

/** 判断某个 speaker_id 是否是"我"（通过 linked_user_id 比较） */
function isMeSpeakerId(speakerId: number): boolean {
  const uuid = currentBindingMapping[speakerId] || task.value?.speaker_uuid_mapping?.[String(speakerId)]
  if (!uuid) return false
  const spk = speakers.value.find(s => s.id === uuid)
  if (!spk?.linked_user_id || !userStore.user?.id) return false
  return spk.linked_user_id === userStore.user.id
}

/** 切换定位高亮说话人 */
function toggleLocateSpeaker(id: number) {
  if (locateSpeakerId.value === id) {
    // 取消聚焦：清除所有关联状态，确保视觉完全还原
    clearSpeakerFilter()
  } else {
    locateSpeakerId.value = id
    speakerFilterSet.clear()
    speakerFilterSet.add(id)
    focusLineIdx.value = 0
  }
}

/** 点击原文（时间戳或整行）跳转到该句播放；拖选文本时让位给划词工具栏 */
function seekFromTranscriptClick(ms: number) {
  const sel = window.getSelection()
  if (sel && !sel.isCollapsed && sel.toString().trim()) return
  player.seekToMs(ms)
}

function updateActiveChapterOnScroll() {
  const area = transcriptAreaEl.value
  if (!area || !chapters.value.length) return
  const areaTop = area.getBoundingClientRect().top
  let bestIdx = 0
  area.querySelectorAll('.chapter-divider').forEach((el) => {
    const idx = Number(el.getAttribute('data-chapter'))
    const rect = el.getBoundingClientRect()
    if (rect.top < areaTop + 120) bestIdx = idx
  })
  activeChapterIdx.value = bestIdx
}

function dotClass(tabId: string): string {
  if (!task.value) return ''
  if (tabId === 'summary' && task.value.summary) return 'is-done'
  if (tabId === 'todos' && todos.value.length > 0) return 'is-done'
  return ''
}

function switchTab(tabId: string) {
  activeTab.value = tabId
  localStorage.setItem('oms_gen_active_tab', tabId)
  if (tabId === 'notes' && !notesContent.value) loadNotes()
  if (tabId === 'todos' && todos.value.length === 0) loadTodos()
}

async function loadNotes() { notesContent.value = await fetchNotes(taskId) }
async function loadTodos() { todos.value = await fetchTodos(taskId) }

async function onSaveNotes() {
  try { await saveNotes(taskId, notesContent.value); notesSaved.value = true } catch { /* */ }
}

async function onToggleTodo(todo: TodoItem) {
  try { await toggleTodo(taskId, todo.id, !todo.done); todo.done = !todo.done } catch { /* */ }
}

async function onAddTodo() {
  const text = newTodoText.value.trim()
  if (!text) return
  try {
    const t = await createTodo(taskId, text, newTodoAssignee.value.trim() || undefined)
    todos.value.push(t)
    newTodoText.value = ''; newTodoAssignee.value = ''; showAddForm.value = false
  } catch { /* */ }
}

async function onDeleteTodo(todo: TodoItem) {
  try {
    await deleteTodo(taskId, todo.id)
    todos.value = todos.value.filter(x => x.id !== todo.id)
  } catch { /* */ }
}


function locateTodoSource(_todo: TodoItem) {
  switchTab('transcript')
}

function insertMd(type: string) {
  const area = notesArea.value
  if (!area) return
  const start = area.selectionStart, end = area.selectionEnd
  const sel = notesContent.value.substring(start, end)
  const map: Record<string, [string, string]> = { bold: ['**', '**'], italic: ['*', '*'], code: ['`', '`'], heading: ['## ', ''], list: ['- ', ''], quote: ['> ', ''] }
  const [pre, post] = map[type] || ['', '']
  notesContent.value = notesContent.value.substring(0, start) + pre + sel + post + notesContent.value.substring(end)
}

let summaryTimer: ReturnType<typeof setTimeout> | null = null

function onSummaryChange(md: string) {
  summaryMd.value = md
  if (summaryTimer) clearTimeout(summaryTimer)
  summaryTimer = setTimeout(async () => {
    try { await saveNotes(taskId + ':summary', md) } catch { /* */ }
  }, 2000)
}

function onNotesChange(md: string) {
  notesContent.value = md
  notesSaved.value = false
  if (notesTimer) clearTimeout(notesTimer)
  notesTimer = setTimeout(onSaveNotes, 2000)
}

function onSelectionAction(action: string, text: string, source: string, blockIndex: number) {
  if (action === 'rewrite') {
    startRewrite(text, source, blockIndex)
    setQuote(text, source, blockIndex)
    window.dispatchEvent(new CustomEvent('quote-to-ai', { detail: { action: t('generating.ai_actions.rewrite') } }))
  } else if (action === 'summarize') {
    setQuote(text, source, blockIndex)
    window.dispatchEvent(new CustomEvent('quote-to-ai', { detail: { action: t('generating.ai_actions.summarize') } }))
  } else if (action === 'extract-todo') {
    setQuote(text, source, blockIndex)
    window.dispatchEvent(new CustomEvent('quote-to-ai', { detail: { action: t('generating.ai_actions.extract_todo') } }))
  }
}

function onCopy() {
  const md = summaryMd.value || task.value?.summary
  if (md) navigator.clipboard.writeText(md)
}

function onExport() { window.open(`/api/download/${taskId}`, '_blank') }

function onFullscreen() {
  if (!document.fullscreenElement) document.documentElement.requestFullscreen()
  else document.exitFullscreen()
}

function onEditSummary() {
  closeGenMore()
  switchTab('summary')
}

async function onRetrySummary() { closeGenMore(); await retrySummary(taskId); await taskStore.loadTasks() /* [状态同步] 重试纪要后刷新任务列表 */ }
async function onRetranscribe() { closeGenMore(); await retranscribe(taskId); router.push({ name: 'generating', params: { taskId } }) }
async function onDelete() {
  closeGenMore()
  if (!confirm(t('generating.errors.confirm_delete'))) return
  await deleteTask(taskId); await taskStore.loadTasks() /* [状态同步] 删除任务后刷新任务列表 */; router.push('/')
}

async function onArchive() {
  showArchiveDialog.value = false
  // TODO: 实现归档 API 调用
  console.log('archive task:', taskId)
}

function onArchiveConfirm() {
  closeGenMore()
  showArchiveDialog.value = true
}

function toggleAudio() {
  const willPlay = !player.playing
  player.toggle()
  if (!willPlay) return
  followPlayback.value = true
  if (activeTab.value !== 'transcript') switchTab('transcript')
  playingLineIdx.value = findLineIdxAt(player.currentTime * 1000)
  scrollToPlayingLine()
}

/** 二分查找播放时间落在哪一行（flatTranscript 已按 begin_time 升序） */
function findLineIdxAt(ms: number): number {
  const lines = flatTranscript.value
  let lo = 0, hi = lines.length - 1, found = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (lines[mid].begin_time <= ms) { found = mid; lo = mid + 1 } else { hi = mid - 1 }
  }
  return found
}

/** 播放进度推进时更新当前行，跟随模式下滚动定位 */
function syncPlayingLine(ms: number) {
  const idx = findLineIdxAt(ms)
  if (idx === playingLineIdx.value) return
  playingLineIdx.value = idx
  if (followPlayback.value) scrollToPlayingLine()
}

function scrollToPlayingLine() {
  const idx = playingLineIdx.value
  if (idx < 0) return
  const line = flatTranscript.value[idx]
  if (!line) return
  const chIdx = getChapterIdxAtTime(chapters.value, line.begin_time)
  if (chIdx >= 0 && !visibleChapterIndices.has(chIdx)) return
  nextTick(() => {
    const el = transcriptListEl.value?.querySelector(`[data-line-idx="${idx}"]`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
}

/** 恢复自动跟随并立即定位到当前播放行 */
function resumeFollowPlayback() {
  followPlayback.value = true
  scrollToPlayingLine()
}

/** 用户主动滚动原文时停止自动跟随，阅读位置交还给用户 */
function onUserScrollIntent() {
  if (player.playing) followPlayback.value = false
}
function seekAudio(e: MouseEvent) {
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  player.seekPercent(((e.clientX - rect.left) / rect.width) * 100)
}

function stopOnboardingAnim() {
  if (obAnimTimer) { clearTimeout(obAnimTimer); obAnimTimer = null }
  if (obLoopTimer) { clearTimeout(obLoopTimer); obLoopTimer = null }
}

function startOnboardingAnim() {
  stopOnboardingAnim()
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (prefersReduced) {
    demoLines.forEach(l => { l.bound = true })
    return
  }
  demoLines.forEach(l => { l.bound = false })
  obAnimTimer = setTimeout(() => {
    demoLines.forEach(l => { l.bound = true })
  }, 1500)
  obLoopTimer = setTimeout(() => {
    startOnboardingAnim()
  }, OB_CYCLE_MS + OB_PAUSE_MS)
}

function closeOnboarding() {
  stopOnboardingAnim()
  if (dontShowAgain.value) {
    localStorage.setItem('spk_onboarding_dismissed', 'true')
  }
  showOnboarding.value = false
}

// ─── 项目关联 ───
async function onSelectProject(projectId: string) {
  showProjectDropdown.value = false
  try {
    await updateTask(taskId, { project_id: projectId || undefined })
    taskStore.patchTaskLocal(taskId, { project_id: projectId || null })
  } catch (e) {
    console.error('update project link failed:', e)
  }
}

// ─── 日期编辑 ───
function openDatePicker() {
  const input = document.createElement('input')
  input.type = 'date'
  input.value = task.value?.meeting_date || task.value?.created_at?.slice(0, 10) || new Date().toISOString().slice(0, 10)
  input.style.position = 'absolute'
  input.style.opacity = '0'
  input.style.pointerEvents = 'none'
  document.body.appendChild(input)
  input.showPicker?.()
  input.addEventListener('change', async () => {
    const newDate = input.value
    if (newDate && newDate !== (task.value?.meeting_date || task.value?.created_at?.slice(0, 10))) {
      try {
        await updateTask(taskId, { meeting_date: newDate })
        taskStore.patchTaskLocal(taskId, { meeting_date: newDate })
      } catch (e) {
        console.error('save date failed:', e)
      }
    }
    input.remove()
  })
  input.addEventListener('blur', () => { setTimeout(() => input.remove(), 200) })
}

watch(activeTab, (tab) => { if (tab === 'notes' && !notesContent.value) loadNotes(); if (tab === 'todos' && todos.value.length === 0) loadTodos() })

watch(() => task.value?.summary, (s) => { if (s) summaryMd.value = s }, { immediate: true })

onMounted(async () => {
  // 始终获取最新任务数据（确保 dialogue/summary/chapters 等字段是最新的）
  try { const t = await fetchTask(taskId); taskStore.patchTaskLocal(taskId, t) } catch { /* */ }
  taskStore.selectTask(taskId)

  // 任务未完成时启动轮询，完成后自动刷新
  if (task.value && !['completed', 'failed'].includes(task.value.status)) {
    startPolling()
  }

  // 已完成但缺少章节时，轮询等待后台补生成
  document.addEventListener('click', onDocClickCloseSearch)
  if (task.value?.status === 'completed' && !task.value?.chapters?.length) {
    startChapterPolling()
  }

  // 加载说话人列表
  try { speakers.value = await fetchSpeakers() } catch { /* */ }

  // 初始化绑定映射
  initBindingMapping()

  // 注册全局点击监听（关闭绑定下拉框）
  document.addEventListener('click', onDocClickForDropdown)

  // 加载项目列表
  try { projects.value = await fetchProjects() } catch { /* */ }

  // 说话人绑定引导：绑定栏可见且未关闭过时显示
  if (showBindingBar.value && localStorage.getItem('spk_onboarding_dismissed') !== 'true') {
    showOnboarding.value = true
    nextTick(() => startOnboardingAnim())
  }

  // 章节滚动追踪 + 用户主动滚动时停止播放跟随
  nextTick(() => {
    const area = transcriptAreaEl.value
    if (!area) return
    area.addEventListener('scroll', updateActiveChapterOnScroll, { passive: true })
    area.addEventListener('wheel', onUserScrollIntent, { passive: true })
    area.addEventListener('touchmove', onUserScrollIntent, { passive: true })
  })

  registerBlockUpdater((blockIndex: number, newSource: string) => {
    const source = rewritePending.value?.source || '纪要'
    if (source === '随记' && notesEditor.value) {
      notesEditor.value.updateBlock(blockIndex, newSource)
    } else if (summaryEditor.value) {
      summaryEditor.value.updateBlock(blockIndex, newSource)
    }
  })

  registerSummaryAppender((markdown: string) => {
    const current = summaryMd.value
    summaryMd.value = current ? current + '\n\n' + markdown : markdown
  })

  registerNotesAppender((markdown: string) => {
    const current = notesContent.value
    notesContent.value = current ? current + '\n\n' + markdown : markdown
  })
})

// 轮询兜底：当任务未完成时，自动轮询状态直到完成或失败
const { start: startPolling, stop: stopPolling } = usePolling(async () => {
  const updated = await fetchTask(taskId)
  taskStore.patchTaskLocal(taskId, updated)

  if (updated.status === 'completed') {
    stopPolling()
    // 重新加载页面数据
    window.location.reload()
  } else if (updated.status === 'failed') {
    stopPolling()
  }
}, 3000)

// 章节补生成轮询：已完成但缺少章节时，等待后台生成
const { start: startChapterPolling, stop: stopChapterPolling } = usePolling(async () => {
  const updated = await fetchTask(taskId)
  taskStore.patchTaskLocal(taskId, updated)
  if (updated.chapters?.length) {
    stopChapterPolling()
  }
}, 3000)

onUnmounted(() => {
  document.removeEventListener('click', onDocClickCloseSearch)
  stopOnboardingAnim()
  const area = transcriptAreaEl.value
  if (area) {
    area.removeEventListener('wheel', onUserScrollIntent)
    area.removeEventListener('touchmove', onUserScrollIntent)
  }
})
</script>

<style scoped>
/* "我说的" 右对齐气泡对话框（2行布局：头部右对齐 + 文本气泡右对齐） */
.ts-line.is-me {
  align-items: flex-end;
  padding: var(--s-2);
  margin: 0;
}
.ts-line.is-me .ts-line-head {
  flex-direction: row-reverse;
  justify-content: flex-start;
  align-self: flex-end;
}
.ts-line.is-me .spk {
  color: var(--mine) !important;
}
.ts-line.is-me .ts-line-body {
  display: flex;
  justify-content: flex-end;
  width: 100%;
}
.ts-line.is-me .txt {
  display: inline-block;
  background: var(--mine-soft);
  border: 1px solid var(--mine);
  padding: var(--s-2) var(--s-3);
  border-radius: var(--radius-lg);
  text-align: left;
  max-width: 70%;
  color: var(--fg);
}

/* Speaker locate/highlight styles are in legacy-views.css */

/* 播放联动：当前播放行高亮 */
.ts-line.is-playing {
  background: var(--accent-soft);
  border-radius: var(--radius-sm);
}
.ts-line.is-playing .ts {
  color: var(--accent);
  font-weight: 600;
}

/* 播放联动：用户手动滚动后出现的"回到播放位置"浮动按钮
   置于左下角，避开右侧说话人面板（.spk-panel 占 230px） */
.ts-follow-btn {
  position: absolute;
  left: 20px;
  bottom: 20px;
  z-index: 5;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 999px;
  background: var(--surface);
  color: var(--fg);
  border: 1px solid var(--border-strong);
  box-shadow: 0 4px 16px oklch(0% 0 0 / 0.14);
  font-size: var(--fs-12);
  font-weight: 500;
  opacity: 0;
  transform: translateY(8px);
  pointer-events: none;
  transition: opacity 0.18s ease, transform 0.18s ease, background 0.12s, border-color 0.12s;
  cursor: pointer;
}
.ts-follow-btn.is-visible {
  opacity: 1;
  transform: none;
  pointer-events: auto;
}
.ts-follow-btn:hover {
  background: var(--surface-3);
  border-color: var(--subtle);
}
.ts-follow-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.ts-follow-btn svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.spk-wrapper {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
}

.spk {
  cursor: pointer;
  user-select: none;
}

.spk:hover {
  text-decoration: underline;
}

.spk-locate-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  opacity: 0.35;
  transition: opacity 0.2s, color 0.2s, background 0.2s;
  border-radius: var(--radius-sm);
}

.spk-locate-btn:hover {
  opacity: 0.8;
  background: var(--surface-2);
}

.spk-locate-btn.is-active {
  opacity: 1;
  color: var(--accent);
  background: var(--accent-soft);
}

.spk-locate-btn.is-active:hover {
  opacity: 1;
  background: oklch(from var(--accent-soft) calc(l - 0.04) c h);
}

.spk-locate-btn svg {
  width: 14px;
  height: 14px;
}

/* Timestamp clickable */
.ts {
  cursor: pointer;
  user-select: none;
}

.ts:hover {
  text-decoration: underline;
}

/* Feature 4: Archive dialog styles */
.archive-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.archive-dialog {
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--dropdown-shadow);
  min-width: 400px;
  max-width: 500px;
}

.archive-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-4) var(--s-5);
  border-bottom: 1px solid var(--border);
}

.archive-dialog-header h3 {
  margin: 0;
  font-size: var(--fs-15);
  font-weight: 600;
}

.archive-dialog-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.archive-dialog-close:hover {
  opacity: 1;
}

.archive-dialog-close svg {
  width: 12px;
  height: 12px;
}

.archive-dialog-body {
  padding: var(--s-5);
}

.archive-dialog-body p {
  margin: 0;
  color: var(--muted);
}

.archive-dialog-footer {
  display: flex;
  gap: var(--s-2);
  justify-content: flex-end;
  padding: var(--s-3) var(--s-4);
  border-top: 1px solid var(--border);
}

.btn-cancel,
.btn-submit {
  padding: var(--s-2) var(--s-4);
  border-radius: var(--radius-sm);
  font-size: var(--fs-14);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-cancel {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--fg);
}

.btn-cancel:hover {
  background: var(--surface-2);
}

.btn-submit {
  background: var(--accent);
  border: 1px solid var(--accent);
  color: var(--accent-fg);
}

.btn-submit:hover {
  background: oklch(from var(--accent) calc(l - 0.06) c h);
}
</style>
