<template>
  <div class="gen-view">
    <!-- 失败态：整页替换为居中大卡片 / Failed state: full-page replacement with centered card -->
    <!-- 背景：录音管线失败后 output_path/audio_path 均为空，若仍渲染工具栏，用户点击导出会触发 /api/download 404，
         新标签页展示原始 JSON {"detail":"Not Found"}。此处统一拦截，按 error_category 展示友好失败页。
         Context: after pipeline failure output_path/audio_path are null; rendering the toolbar would let users
         hit /api/download 404 and see raw JSON in a new tab. Intercept here with a category-aware failure page. -->
    <div v-if="isFailed" class="gen-failure-page">
      <div class="gen-failure-card">
        <div class="gen-failure-icon" :class="failureInfo.iconClass">
          <svg v-if="failureInfo.icon === 'refresh'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
          <svg v-else-if="failureInfo.icon === 'settings'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H2a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V2a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H22a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>
          <svg v-else-if="failureInfo.icon === 'audio'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        </div>
        <h2 class="gen-failure-title">{{ t('generating.failure.title') }}</h2>
        <p class="gen-failure-message">{{ failureInfo.message }}</p>
        <p v-if="failureInfo.suggestion" class="gen-failure-suggestion">{{ failureInfo.suggestion }}</p>
        <details v-if="failureInfo.rawError" class="gen-failure-raw">
          <summary>{{ t('generating.failure.show_raw') }}</summary>
          <code>{{ failureInfo.rawError }}</code>
        </details>
        <div class="gen-failure-actions">
          <button class="btn btn-primary" @click="onRetryFromFailure">{{ t('task.failure.transient_action') }}</button>
          <button class="btn btn-secondary" @click="router.push('/library')">{{ t('generating.failure.back_to_library') }}</button>
        </div>
      </div>
    </div>

    <!-- 正常态：原有工具栏 + 元信息 + 说话人区 + Tab + 内容区 / Normal state: original toolbar + meta + speaker zone + tabs + content -->
    <template v-else>
    <!-- 紧凑图标工具栏 / Compact icon toolbar -->
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
        <!-- 知识库同步状态指示器 / Knowledge base sync status indicator -->
        <button
          v-if="syncStatus.can_sync"
          class="gen-toolbar-icon gen-toolbar-sync"
          :class="{ 'is-dirty': syncStatus.is_dirty, 'is-syncing': isSyncing, 'is-synced': !syncStatus.is_dirty }"
          :title="isSyncing ? t('generating.toolbar.syncing') : (syncStatus.is_dirty ? t('generating.toolbar.sync_dirty') : t('generating.toolbar.synced'))"
          :disabled="isSyncing"
          @click="onSyncToKb"
        >
          <!-- 同步中：旋转图标 / Syncing: spinning icon -->
          <svg v-if="isSyncing" class="sync-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
          <!-- 已同步：check-circle / Synced: check-circle -->
          <svg v-else-if="!syncStatus.is_dirty" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          <!-- 有更新：upload-cloud / Dirty: upload-cloud -->
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>
          <span class="tb-tip">{{ t('generating.toolbar.sync_kb') }}</span>
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
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><template v-if="!data.isArchived.value"><line x1="10" y1="12" x2="14" y2="12"/></template><template v-else><line x1="12" y1="12" x2="12" y2="16"/><line x1="10" y1="14" x2="14" y2="14"/></template></svg>
              {{ data.isArchived.value ? t('generating.toolbar.unarchive') : t('generating.toolbar.archive') }}
            </button>
            <button class="gen-toolbar-more-item is-danger" @click="onDelete">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
              {{ t('generating.toolbar.delete') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 元信息行 + 说话人区 / Meta info + speaker zone -->
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
        <span class="gen-meta-project">
          <span class="gen-meta-project-chip" :class="{ 'is-bound': !!task?.project_id, 'is-unbound': !task?.project_id }" role="button" tabindex="0" :title="task?.project_id ? t('generating.meta.linked_kb_tip') : t('generating.meta.link_kb_tip')" @click.stop="showProjectDropdown = !showProjectDropdown">
            <!-- book-open 图标：知识库语义 / book-open icon: knowledge base semantics -->
            <svg v-if="task?.project_id" width="12" height="12" viewBox="0 0 24 24" fill="currentColor" fill-opacity="0.15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
            <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
            <span>{{ currentProjectName }}</span>
            <!-- 尾部状态图标：未关联 +，已关联 hover ✕ / Tail status icon: unlinked +, linked hover ✕ -->
            <svg v-if="!task?.project_id" class="chip-tail-icon chip-tail-add" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            <svg v-else class="chip-tail-icon chip-tail-remove" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </span>
          <div class="gen-meta-proj-dropdown" :class="{ hidden: !showProjectDropdown }">
            <template v-if="projects.length > 0">
              <button v-for="p in projects" :key="p.id" class="gen-meta-proj-item" :class="{ 'is-selected': task?.project_id === p.id }" @click="onSelectProject(p.id)">
                {{ p.name }}
              </button>
              <div class="gen-meta-proj-divider"></div>
              <button class="gen-meta-proj-item" :class="{ 'is-selected': !task?.project_id }" @click="onSelectProject('')">
                {{ t('generating.meta.no_project') }}
              </button>
            </template>
            <button v-else class="gen-meta-proj-item gen-meta-proj-cta" @click="$router.push({ name: 'projects' })">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              {{ t('generating.meta.create_kb') }}
            </button>
          </div>
          <!-- 知识库关联引导图标（仅未关联时显示） / Knowledge base link guide icon (shown only when unlinked) -->
          <span
            v-if="!task?.project_id"
            class="gen-spk-info-icon gen-meta-proj-info-icon"
            :title="t('generating.project_onboarding.info_icon_tip')"
            @click="openProjOnboarding"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
          </span>
        </span>
      </div>
    </div>

    <!-- 说话人区（三态合并：只读名单 / 绑定提示 / 绑定完成） / Speaker zone (three-state: readonly / binding prompt / binding complete) -->
    <GeneratingSpeakerZone
      :mode="speakerZoneMode"
      :visible="bindingLegend.length > 0"
      :speakers="bindingLegend"
      :unbound-count="unboundCount"
      :can-edit-bindings="canBind"
      :current-mapping="currentBindingMapping"
      :dropdown="bindingDropdown"
      :filtered-speakers="dropdownSpeakers"
      @open-info="openOnboarding"
      @open-dropdown="openBindingDropdown"
      @locate-speaker="onLocateSpeaker"
      @skip="skipMapping"
      @confirm="confirmMapping"
      @close="bindingBarHidden = true"
      @reenter-binding="reenterBinding"
      @select="selectBinding"
      @create-and-bind="createAndBind"
      @dropdown-keydown="onDropdownKeydown"
      @update:dropdown-search="bindingDropdown.search = $event"
    />

    <!-- 控制区：Tab / Control zone: Tabs -->
    <div class="gen-control-zone">
      <div class="gen-tabs-group">
        <div class="gen-tabs" id="genTabsContainer">
          <button v-for="tab in TABS" :key="tab.id" class="gen-tab" :class="{ 'is-active': activeTab === tab.id }" :title="tab.label" @click="switchTab(tab.id)">
            <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" v-html="tab.icon"></svg>
            <span class="tab-label">{{ tab.label }}</span>
            <span class="tab-dot" :class="dotClass(tab.id)"></span>
          </button>
        </div>
      </div>
    </div>

    <!-- 内容区（子组件） / Content area (sub-components) -->
    <div class="gen-content">
      <TranscriptPanel
        ref="transcriptPanelRef"
        :visible="activeTab === 'transcript'"
        :transcript-items="transcriptItems"
        :chapters="chapters"
        :expanded-chapters="expandedChapters"
        :visible-chapter-indices="visibleChapterIndices"
        :active-chapter-idx="activeChapterIdx"
        :flat-transcript="flatTranscript"
        :task-status="task?.status"
        :can-bind="canBind"
        :speaker-filter-set="speakerFilterSet"
        :focus-speaker="focusSpeaker"
        :focus-line-idx="focusLineIdx"
        :locate-speaker-id="locateSpeakerId"
        :playing-line-idx="playingLineIdx"
        :playing-speaker-id="playingSpeakerId"
        :player-playing="player.playing"
        :follow-playback="followPlayback"
        :speaker-panel-visible="speakerPanelVisible"
        v-model:speaker-panel-search="speakerPanelSearch"
        :search-expanded="searchExpanded"
        :panel-speaker-list="panelSpeakerList"
        :panel-total-duration="panelTotalDuration"
        :panel-total-turns="panelTotalTurns"
        :current-binding-mapping="currentBindingMapping"
        :speakers="speakers"
        :audio-url="audioUrl"
        :audio-playing="player.playing"
        :audio-progress="player.progress"
        :audio-time-str="player.timeStr"
        :audio-current-time-str="player.currentTimeStr"
        :audio-remaining-time-str="player.remainingTimeStr"
        :audio-speed="player.speed"
        :audio-current-time="player.currentTime"
        :chapter-overview-visible="chapters.length > 0 && activeTab === 'transcript'"
        :all-chapters-visible="allChaptersVisible"
        @toggle-audio="toggleAudio"
        @seek-audio="seekAudio"
        @skip-audio="(s) => player.skip(s)"
        @cycle-speed="player.cycleSpeed()"
        @toggle-chapter="toggleChapterExpand"
        @toggle-chapter-transcript="toggleChapterTranscript"
        @seek="seekFromTranscriptClick"
        @speaker-label-click="onSpeakerLabelClick"
        @toggle-locate="onLocateSpeaker"
        @toggle-speaker="toggleSpeakerFilter"
        @clear-filter="clearSpeakerFilter"
        @nav-focus="navFocusLine"
        @toggle-panel="speakerPanelVisible = !speakerPanelVisible"
        @toggle-search="toggleSearch"
        @search-blur="onSearchBlur"
        @resume-follow="resumeFollowPlayback"
        @show-all-chapters="showAllChapters"
        @scroll-to-chapter="scrollToChapter"
        @toggle-all-transcript="toggleAllTranscript"
      />

      <SummaryPanel
        ref="summaryPanelRef"
        :visible="activeTab === 'summary'"
        :summary-md="summaryMd"
        :chapters="chapters"
        :expanded-chapters="summaryExpandedChapters"
        :processing="!!task?.status && ['recording', 'processing', 'transcribing', 'summarizing', 'awaiting_mapping'].includes(task.status)"
        :pending="task?.status === 'pending'"
        :has-summary="!!task?.summary"
        :todos-count="todos.length"
        :todos-done-count="todos.filter(x => x.done).length"
        @change="onSummaryChange"
        @toggle-chapter="toggleSummaryChapter"
        @switch-tab="switchTab"
      />

      <NotesPanel
        ref="notesPanelRef"
        :visible="activeTab === 'notes'"
        :markdown="notesContent"
        :notes-saved="notesSaved"
        @change="onNotesChange"
      />

      <DecisionFlowPanel
        :visible="activeTab === 'todos'"
        :todos="todos"
        :show-add-form="showAddForm"
        v-model:new-todo-text="newTodoText"
        v-model:new-todo-assignee="newTodoAssignee"
        @delete="onDeleteTodo"
        @update="onEditTodo"
        @status-change="onStatusChange"
        @toggle-form="showAddForm = !showAddForm"
        @add="onAddTodo"
      />
    </div>
    <!-- 浮动选中工具栏 / Floating selection toolbar -->
    <SelectionToolbar
      container-selector=".gen-content"
      @action="onSelectionAction"
      @inline-edit="onInlineEditRequest"
    />
    <!-- 行间编辑浮动输入框 / Inline edit floating input -->
    <InlineEditInput
      :visible="inlineEdit.showInput.value"
      :loading="inlineEdit.isLoading.value"
      :anchor-rect="inlineEdit.anchorRect.value"
      @submit="onInlineEditSubmit"
      @cancel="inlineEdit.cancelEdit"
    />

    <!-- 说话人绑定引导弹窗（子组件） / Speaker binding onboarding dialog (sub-component) -->
    <OnboardingDialog
      v-model="showOnboarding"
      :demo-lines="demoLines"
      @close="closeOnboarding"
    />

    <!-- 知识库关联引导弹窗（子组件） / Knowledge base onboarding dialog (sub-component) -->
    <ProjectOnboardingDialog
      v-model="showProjectOnboarding"
      :connected="projConnected"
      @close="closeProjOnboarding"
    />

    <ArchiveDialog
      v-model="showArchiveDialog"
      :is-unarchive="data.isArchived.value"
      @confirm="onArchiveDone"
    />

    <!-- 删除确认对话框（子组件） / Delete confirmation dialog (sub-component) -->
    <DeleteDialog
      v-model="showDeleteDialog"
      @confirm="onDeleteConfirm"
    />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { deleteTask, retranscribe, retrySummary, fetchSyncStatus, syncTaskToProject } from '@/api/tasks'
import type { SyncStatus } from '@/api/tasks'
import { usePopMenu } from '@/composables/usePopMenu'
import SelectionToolbar from '@/components/SelectionToolbar.vue'
import InlineEditInput from '@/components/InlineEditInput.vue'
import TranscriptPanel from './generating/TranscriptPanel.vue'
import SummaryPanel from './generating/SummaryPanel.vue'
import NotesPanel from './generating/NotesPanel.vue'
import DecisionFlowPanel from './generating/DecisionFlowPanel.vue'
import GeneratingSpeakerZone from './generating/GeneratingSpeakerZone.vue'
import OnboardingDialog from './generating/OnboardingDialog.vue'
import ProjectOnboardingDialog from './generating/ProjectOnboardingDialog.vue'
import ArchiveDialog from './generating/ArchiveDialog.vue'
import DeleteDialog from './generating/DeleteDialog.vue'
import { useGeneratingData } from '@/composables/useGeneratingData'
import { useSpeakerBinding } from '@/composables/useSpeakerBinding'
import { useSpeakerPanel } from '@/composables/useSpeakerPanel'
import { usePlaybackFollow } from '@/composables/usePlaybackFollow'
import { useNotesAndTodos } from '@/composables/useNotesAndTodos'
import { useOnboarding } from '@/composables/useOnboarding'
import { useProjectOnboarding } from '@/composables/useProjectOnboarding'
import { useInlineEdit } from '@/composables/useInlineEdit'

const { t } = useI18n()
const router = useRouter()
const taskStore = useTaskStore()

// ─── 模板 refs / Template refs ───
const transcriptPanelRef = ref<InstanceType<typeof TranscriptPanel> | null>(null)
const summaryPanelRef = ref<InstanceType<typeof SummaryPanel> | null>(null)
const notesPanelRef = ref<InstanceType<typeof NotesPanel> | null>(null)

// ─── Composable 编排 / Composable orchestration ───
const data = useGeneratingData(transcriptPanelRef, summaryPanelRef, notesPanelRef)

const binding = useSpeakerBinding(
  data.taskId, data.task, data.flatTranscript, data.speakers,
  data.switchTab, data.startPolling,
)

const panel = useSpeakerPanel(
  data.task, data.flatTranscript, data.speakers,
  binding.currentBindingMapping, transcriptPanelRef,
)

const playback = usePlaybackFollow(
  data.player, data.taskId, data.flatTranscript, data.chapters,
  data.visibleChapterIndices, transcriptPanelRef,
  data.activeTab, data.switchTab, data.getChapterIdxAtTime,
)

const notes = useNotesAndTodos(
  data.taskId, data.notesContent, data.notesSaved, data.summaryMd,
  data.todos, data.activeTab, data.task,
  loadSyncStatus, // 内容修改后自动刷新同步状态 / Refresh sync status after content modification
)

const onboarding = useOnboarding()
const projOnboarding = useProjectOnboarding()
const inlineEdit = useInlineEdit()

// ─── 解构到模板作用域 / Destructure to template scope ───
const {
  task, activeTab, TABS, switchTab, dotClass,
  chapters, activeChapterIdx, scrollToChapter, allChaptersVisible,
  visibleChapterIndices, expandedChapters, summaryExpandedChapters,
  transcriptItems, flatTranscript, summaryMd, todos, notesContent, notesSaved,
  showArchiveDialog, showDeleteDialog, metaDuration, metaDateShort,
  projects, showProjectDropdown, onSelectProject, openDatePicker, breadcrumbTitle,
  player, seekAudio, onCopy, onExport, onFullscreen, speakers, audioUrl,
  toggleChapterExpand, toggleSummaryChapter, toggleChapterTranscript, showAllChapters,
  isFailed, failureInfo,
} = data
const {
  showBindingBar, bindingLegend, unboundCount, currentBindingMapping,
  bindingDropdown, dropdownSpeakers, openBindingDropdown,
  skipMapping, confirmMapping, bindingBarHidden, selectBinding, createAndBind, onDropdownKeydown, canBind, reenterBinding,
} = binding
const {
  speakerPanelVisible, speakerPanelSearch, searchExpanded, speakerFilterSet,
  focusSpeaker, focusLineIdx, locateSpeakerId,
  panelSpeakerList, panelTotalDuration, panelTotalTurns,
  toggleSearch, onSearchBlur, toggleSpeakerFilter, clearSpeakerFilter, navFocusLine,
} = panel
const { playingLineIdx, followPlayback, playingSpeakerId, toggleAudio, resumeFollowPlayback } = playback
const {
  showAddForm, newTodoText, newTodoAssignee,
  onNotesChange, onSummaryChange, onAddTodo, onDeleteTodo, onEditTodo, onStatusChange,
} = notes
const { showOnboarding, demoLines, hasSeenOnboarding, openOnboarding, closeOnboarding } = onboarding
const { showProjectOnboarding, connected: projConnected, openOnboarding: openProjOnboarding, closeOnboarding: closeProjOnboarding } = projOnboarding

// ─── 知识库同步状态 / Knowledge base sync status ───
const syncStatus = ref<SyncStatus>({ can_sync: false })
const isSyncing = ref(false)

async function loadSyncStatus() {
  if (!data.task.value?.project_id || data.task.value?.status !== 'completed') {
    syncStatus.value = { can_sync: false }
    return
  }
  try {
    syncStatus.value = await fetchSyncStatus(data.taskId)
  } catch {
    syncStatus.value = { can_sync: false }
  }
}

async function onSyncToKb() {
  if (isSyncing.value) return
  isSyncing.value = true
  try {
    await syncTaskToProject(data.taskId)
    // 同步完成后刷新状态 / Refresh status after sync
    await loadSyncStatus()
  } catch (e) {
    console.error('sync to kb failed:', e)
  } finally {
    isSyncing.value = false
  }
}

// ─── 首次进入时自动弹出说话人关联引导弹窗 / Auto-open speaker binding onboarding on first entry ───
watch(showBindingBar, (visible) => {
  if (visible && !hasSeenOnboarding.value) openOnboarding()
}, { immediate: true })

// [状态同步] 任务状态变化时刷新知识库同步状态（完成/关联项目时显示同步按钮）
watch(() => data.task.value, (t) => {
  if (t?.status === 'completed' && t?.project_id) {
    loadSyncStatus()
  } else {
    syncStatus.value = { can_sync: false }
  }
}, { immediate: true })

// ─── 更多菜单 / More menu ──
const genMoreBtn = ref<HTMLElement | null>(null)
const genMoreDropdown = ref<HTMLElement | null>(null)
const { visible: showMoreMenu, toggle: toggleGenMore, close: closeGenMore } = usePopMenu(genMoreDropdown, genMoreBtn)

// ─── 工具栏操作 / Toolbar actions ───
function onEditSummary() { closeGenMore(); data.switchTab('summary') }
async function onRetrySummary() { closeGenMore(); await retrySummary(data.taskId); await taskStore.loadTasks() }
async function onRetranscribe() { closeGenMore(); await retranscribe(data.taskId); router.push({ name: 'generating', params: { taskId: data.taskId } }) }

/** 失败态卡片「重试转写」：复用 retranscribe API，乐观更新状态并恢复轮询，与 TaskList.vue 重试行为一致
 * Failure card "retry transcription": reuse retranscribe API, optimistically update status and resume polling,
 * consistent with TaskList.vue retry behavior. */
async function onRetryFromFailure() {
  try {
    await retranscribe(data.taskId)
    taskStore.patchTaskLocal(data.taskId, { status: 'transcribing', error: undefined, error_category: undefined, error_suggestion: undefined })
    data.startPolling()
  } catch (e) {
    console.error('retry from failure page failed:', e)
  }
}
async function onDelete() {
  closeGenMore()
  data.showDeleteDialog.value = true
}
async function onDeleteConfirm() {
  data.showDeleteDialog.value = false
  await deleteTask(data.taskId); await taskStore.loadTasks(); router.push('/')
}
function onArchiveConfirm() { closeGenMore(); data.showArchiveDialog.value = true }
async function onArchiveDone() {
  await data.onArchive()
  if (data.isArchived.value) {
    // 归档后跳转至会议库 / Redirect to library after archiving
    router.push('/library')
  }
}

function onSpeakerLabelClick(e: MouseEvent, speakerId: number) {
  if (binding.canBind.value) binding.openBindingDropdown(e, speakerId)
  else panel.toggleLocateSpeaker(speakerId)
}

/** 说话人区定位按钮：切换到原文 Tab 并滚动到目标说话人首条发言 / Speaker locate button: switch to transcript tab and scroll to target speaker's first utterance */
function onLocateSpeaker(speakerId: number) {
  // 1. 若当前不在原文 Tab，先切换 / 1. Switch to transcript tab if not already
  if (activeTab.value !== 'transcript') {
    switchTab('transcript')
  }
  // 2. 设置定位状态（高亮目标说话人、淡化其余） / 2. Set locate state (highlight target speaker, dim others)
  panel.toggleLocateSpeaker(speakerId)
  // 3. DOM 更新后滚动到该说话人的第一条发言 / 3. Scroll to speaker's first utterance after DOM update
  nextTick(() => {
    const firstLine = flatTranscript.value.find(l => l.speaker_id === speakerId)
    if (!firstLine) return
    const el = transcriptPanelRef.value?.transcriptListEl?.querySelector(`[data-begin-time="${firstLine.begin_time}"]`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
}

/** 转写原文面板 DOM 文本替换 / DOM text replacement in transcript panel */
function replaceInTranscriptDom(oldText: string, newText: string) {
  const listEl = transcriptPanelRef.value?.transcriptListEl
  if (!listEl) return
  const txtEls = listEl.querySelectorAll('.ts-line-body .txt')
  for (const el of txtEls) {
    const node = el.childNodes[0] as Text | undefined
    if (node && node.nodeType === 3 && node.textContent?.includes(oldText)) {
      node.textContent = node.textContent.replace(oldText, newText)
      return
    }
  }
}

function onSelectionAction(action: string, text: string, source: string, blockIndex: number, replacement?: string) {
  if (action === 'rewrite') {
    // 旧改写流程保留作为 fallback / Old rewrite flow kept as fallback
    data.startRewrite(text, source, blockIndex); data.setQuote(text, source, blockIndex)
    window.dispatchEvent(new CustomEvent('quote-to-ai', { detail: { action: t('generating.ai_actions.rewrite') } }))
  } else if (action === 'summarize') {
    data.setQuote(text, source, blockIndex)
    window.dispatchEvent(new CustomEvent('quote-to-ai', { detail: { action: t('generating.ai_actions.summarize') } }))
  } else if (action === 'extract-todo') {
    data.setQuote(text, source, blockIndex)
    window.dispatchEvent(new CustomEvent('quote-to-ai', { detail: { action: t('generating.ai_actions.extract_todo') } }))
  } else if (action === 'correct' && replacement) {
    // 转写原文面板：直接 DOM 替换 / Transcript panel: direct DOM replacement
    replaceInTranscriptDom(text, replacement)
  }
}

// ─── 行间编辑 / Inline edit ───
function onInlineEditRequest(text: string, source: string, _blockIndex: number, range?: { start: number; end: number }) {
  if (range) {
    // textarea 面板：使用 range 模式 / textarea panels: use range mode
    inlineEdit.startInlineEdit(text, source, range)
  } else {
    // 转写原文面板：使用 DOM 选区 / Transcript panel: use DOM selection
    const sel = window.getSelection()
    let rect: { top: number; left: number } | undefined
    if (sel && sel.rangeCount > 0) {
      const r = sel.getRangeAt(0).getBoundingClientRect()
      rect = { top: r.top, left: r.left + r.width / 2 }
    }
    // 无 range 时用 0,0 占位（转写原文面板不走 replaceRange） / No range: use 0,0 placeholder
    inlineEdit.startInlineEdit(text, source, { start: 0, end: text.length }, rect)
  }
}

async function onInlineEditSubmit(instruction: string) {
  await inlineEdit.submitInstruction(instruction)
}


/** 切换所有章节原文显隐（导航栏眼睛按钮） / Toggle all chapters transcript visibility (navbar eye button) */
function toggleAllTranscript() {
  if (allChaptersVisible) visibleChapterIndices.clear()
  else chapters.value.forEach((_: any, idx: number) => visibleChapterIndices.add(idx))
}

/** 点击原文时间戳跳转播放；拖选文本时让位给划词工具栏 / Click transcript timestamp to play; yield to selection toolbar when dragging */
function seekFromTranscriptClick(ms: number) {
  const sel = window.getSelection()
  if (sel && !sel.isCollapsed && sel.toString().trim()) return
  player.seekToMs(ms)
}

// ─── 计算属性（组合 composable 输出） / Computed properties (combining composable output) ───
// 说话人区三态：非绑定态或用户已关闭绑定条 → readonly；否则按是否存在未关联切换 actionable/complete / Speaker zone tri-state
const speakerZoneMode = computed<'readonly' | 'actionable' | 'complete'>(() => {
  if (!showBindingBar.value) return 'readonly'
  return unboundCount.value > 0 ? 'actionable' : 'complete'
})
const breadcrumbs = computed(() => data.computeBreadcrumbs(data.projects.value))
const currentProjectName = computed(() => data.computeCurrentProjectName(data.projects.value))
const speakerNames = computed(() => {
  const m = data.task.value?.speaker_mapping
  return m ? Object.values(m).filter(Boolean) : []
})

// ─── 生命周期 / Lifecycle ───
onMounted(async () => {
  // 行间编辑范围替换回调 / Inline edit range replacer
  inlineEdit.registerRangeReplacer((start: number, end: number, newText: string) => {
    const src = inlineEdit.source.value || '纪要'
    if (src === '随记' && notesPanelRef.value) {
      notesPanelRef.value.replaceRange(start, end, newText)
    } else if (summaryPanelRef.value) {
      summaryPanelRef.value.replaceRange(start, end, newText)
    }
  })

  // 任务数据可能尚未加载（刷新页面时 store 为空），用 watch 等待任务就绪后初始化绑定映射 / Task data may not be loaded yet (store empty on page refresh), use watch to init binding mapping when ready
  const stopWatch = watch(() => data.task.value, (t) => {
    if (t) { binding.initBindingMapping(); stopWatch() }
  }, { immediate: true })
  document.addEventListener('click', panel.onDocClickCloseSearch)
  document.addEventListener('click', binding.onDocClickForDropdown)

  // 章节滚动追踪 + 用户主动滚动时停止播放跟随 / Chapter scroll tracking + stop playback follow on user scroll
  nextTick(() => {
    const area = transcriptPanelRef.value?.transcriptAreaEl ?? null
    if (!area) return
    area.addEventListener('wheel', playback.onUserScrollIntent, { passive: true })
    area.addEventListener('touchmove', playback.onUserScrollIntent, { passive: true })
  })
})

onUnmounted(() => {
  document.removeEventListener('click', panel.onDocClickCloseSearch)
  document.removeEventListener('click', binding.onDocClickForDropdown)
  onboarding.stopOnboardingAnim()
  projOnboarding.stopAnim()
})
</script>




