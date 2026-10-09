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
        <!-- R4-简（REQ-TRANSCRIBE-PROGRESS）：失败阶段标红 + 已处理百分比；重试入口沿用卡片按钮 -->
        <!-- Failed stage highlighted red with processed percent; retry actions stay on the card buttons -->
        <ProgressDialog :task="task" compact hide-retry class="gen-failure-progress" />
        <details v-if="failureInfo.rawError" class="gen-failure-raw">
          <summary>{{ t('generating.failure.show_raw') }}</summary>
          <code>{{ failureInfo.rawError }}</code>
        </details>
        <div class="gen-failure-actions">
          <button class="btn btn-primary" @click="onRetryFromFailure">{{ t('task.failure.transient_action') }}</button>
          <!-- AC-4（QA-R1 DEF-04）：本地引擎失败时按 can_fallback_cloud 渲染云端回退。
               True ⇒ 「切云端重试」+ 显式确认（数据上云告知）；False ⇒ 置灰 + 纯内网原因。
               AC-4: cloud fallback gated on can_fallback_cloud; explicit confirm dialog before uploading data. -->
          <button
            v-if="canFallbackCloud"
            class="btn btn-secondary gen-fallback-cloud-btn"
            @click="showCloudFallbackConfirm = true"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>
            {{ t('generating.failure.cloud_retry') }}
          </button>
          <template v-else-if="cloudFallbackBlocked">
            <button
              class="btn btn-secondary gen-fallback-cloud-btn"
              disabled
              :aria-disabled="true"
              :title="t('generating.failure.cloud_retry_blocked_reason')"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/><line x1="2" y1="2" x2="22" y2="22"/></svg>
              {{ t('generating.failure.cloud_retry') }}
            </button>
            <p class="gen-fallback-blocked-reason">{{ t('generating.failure.cloud_retry_blocked_reason') }}</p>
          </template>
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
        <div class="gen-toolbar-more-wrap" @mouseenter="onGenMoreEnter" @mouseleave="onGenMoreLeave">
          <button ref="genMoreBtn" class="gen-toolbar-icon" v-bind="genMoreTriggerAttrs" @click="toggleGenMore" :aria-label="t('generating.toolbar.more')">
            <svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg>
          </button>
          <div ref="genMoreDropdown" class="gen-toolbar-more-menu" v-bind="genMoreMenuAttrs" :class="{ 'is-open': showMoreMenu }">
            <!-- 复制组 -->
            <button class="gen-toolbar-more-item" role="menuitem" @click="onCopyTitle">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              {{ t('task.copy_title') }}
            </button>
            <button v-if="task?.summary" class="gen-toolbar-more-item" role="menuitem" @click="onCopySummary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
              {{ t('task.copy_summary') }}
            </button>
            <!-- 管理组 -->
            <div class="gen-toolbar-more-divider"></div>
            <button class="gen-toolbar-more-item" role="menuitem" @click="onRenameTask">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              {{ t('task.rename') }}
            </button>
            <button class="gen-toolbar-more-item" role="menuitem" @click="onRetrySummary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
              {{ t('generating.toolbar.regenerate') }}
            </button>
            <button class="gen-toolbar-more-item" role="menuitem" @click="onRetranscribe">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
              {{ t('generating.toolbar.retranscribe') }}
            </button>
            <!-- 危险组 -->
            <div class="gen-toolbar-more-divider"></div>
            <button class="gen-toolbar-more-item" role="menuitem" @click="onArchiveConfirm">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><template v-if="!data.isArchived.value"><line x1="10" y1="12" x2="14" y2="12"/></template><template v-else><line x1="12" y1="12" x2="12" y2="16"/><line x1="10" y1="14" x2="14" y2="14"/></template></svg>
              {{ data.isArchived.value ? t('generating.toolbar.unarchive') : t('generating.toolbar.archive') }}
            </button>
            <button class="gen-toolbar-more-item is-danger" role="menuitem" @click="onDelete">
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
            <span class="gen-meta-val">{{ speakerCount }}</span> {{ t('generating.meta.person') }}
          </span>
          <span class="gen-meta-sep"></span>
          <span class="gen-meta-item">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
            <span class="gen-meta-val gen-meta-date-btn" :title="t('generating.meta.edit_date')" @click.stop="openDatePicker">{{ metaDateShort }}</span>
          </span>
        </div>
        <span class="gen-meta-project">
          <span class="gen-meta-project-chip" :class="{ 'is-bound': !!task?.project_id, 'is-unbound': !task?.project_id }" role="button" tabindex="0" :aria-expanded="showProjectDropdown" :title="task?.project_id ? t('generating.meta.linked_kb_tip') : t('generating.meta.link_kb_tip')" @click.stop="showProjectDropdown = !showProjectDropdown" @keydown.enter.prevent="showProjectDropdown = !showProjectDropdown" @keydown.space.prevent="showProjectDropdown = !showProjectDropdown">
            <!-- book-open 图标：知识库语义 / book-open icon: knowledge base semantics -->
            <svg v-if="task?.project_id" width="12" height="12" viewBox="0 0 24 24" fill="currentColor" fill-opacity="0.15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
            <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
            <span>{{ currentProjectName }}</span>
            <!-- 尾部状态图标：未关联 +，已关联 hover ✕ / Tail status icon: unlinked +, linked hover ✕ -->
            <svg v-if="!task?.project_id" class="chip-tail-icon chip-tail-add" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            <svg v-else class="chip-tail-icon chip-tail-remove" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </span>
          <div ref="kbDropdownRef" class="gen-meta-proj-dropdown" :class="{ hidden: !showProjectDropdown }">
            <!-- 检索输入框（焦点保持在输入框；Esc 由 useDropdownPopup 统一处理） / Search input (keeps focus; Esc handled by useDropdownPopup) -->
            <div class="gen-meta-proj-search">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input
                ref="kbSearchInputRef"
                v-model="kbSearchQuery"
                class="gen-meta-proj-search-input"
                :placeholder="t('generating.meta.kb_search_placeholder')"
              />
            </div>
            <!-- 过滤后的知识库列表 / Filtered project list -->
            <template v-if="filteredProjects.length > 0">
              <button v-for="p in filteredProjects" :key="p.id" data-dd-item class="gen-meta-proj-item" :class="{ 'is-selected': task?.project_id === p.id }" @click="onSelectProject(p.id)">
                {{ p.name }}
              </button>
            </template>
            <!-- 不关联知识库 / No knowledge base linked -->
            <div class="gen-meta-proj-divider"></div>
            <button data-dd-item class="gen-meta-proj-item" :class="{ 'is-selected': !task?.project_id }" @click="onSelectProject('')">
              {{ t('generating.meta.no_project') }}
            </button>
            <!-- 新建知识库区域 / Create KB area -->
            <template v-if="showKbCreateInput">
              <div class="gen-meta-proj-divider"></div>
              <div class="gen-meta-proj-create-inline">
                <input
                  ref="kbCreateInputRef"
                  v-model="kbCreateName"
                  class="gen-meta-proj-create-input"
                  :placeholder="t('generating.meta.create_kb')"
                  data-dd-enter="native"
                  @keydown.enter="createAndLinkKb"
                  @keydown.escape.stop="showKbCreateInput = false; kbCreateName = ''"
                />
              </div>
            </template>
            <template v-else-if="filteredProjects.length === 0 && projects.length > 0">
              <!-- 检索无匹配但总列表非空 / Search no match but total list non-empty -->
              <div class="gen-meta-proj-divider"></div>
              <button data-dd-item class="gen-meta-proj-item gen-meta-proj-cta" @click="kbCreateName = kbSearchQuery.trim(); showKbCreateInput = true; $nextTick(() => kbCreateInputRef?.focus())">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                <span v-if="kbSearchQuery.trim()">{{ t('generating.meta.create_named', { name: kbSearchQuery.trim() }) }}</span>
                <span v-else>{{ t('generating.meta.create_kb') }}</span>
              </button>
            </template>
            <template v-else-if="projects.length === 0">
              <!-- 知识库总数为 0 / Total projects is 0 -->
              <div class="gen-meta-proj-divider"></div>
              <button data-dd-item class="gen-meta-proj-item gen-meta-proj-cta" @click="showKbCreateInput = true; $nextTick(() => kbCreateInputRef?.focus())">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                <span v-if="kbSearchQuery.trim()">{{ t('generating.meta.create_named', { name: kbSearchQuery.trim() }) }}</span>
                <span v-else>{{ t('generating.meta.create_kb') }}</span>
              </button>
            </template>
          </div>
        </span>
      </div>
    </div>

    <!-- 人员栏（渐进式压缩：说话人 + 参会人合并） / Personnel bar (progressive compression: speakers + roster merged) -->
    <GeneratingSpeakerZone
      :mode="speakerZoneMode"
      :visible="bindingLegend.length > 0"
      :speakers="bindingLegend"
      :unbound-count="unboundCount"
      :can-edit-bindings="canBind"
      :current-mapping="currentBindingMapping"
      :dropdown="bindingDropdown"
      :filtered-speakers="dropdownSpeakers"
      :roster="rosterComposable.roster.value"
      :bound-names="boundNames"
      :all-speakers="speakers"
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
      @roster-add="rosterComposable.addMember($event)"
      @roster-remove="rosterComposable.removeMember($event)"
      :voiceprint-items="visibleVoiceprintItems"
      :voiceprint-running="voiceprintRunning"
      @run-voiceprint="runVoiceprint"
      @apply-voiceprint="onVoiceprintApply"
      @dismiss-voiceprint="onVoiceprintDismiss"
    />

    <!-- 控制区：Tab / Control zone: Tabs -->
    <div class="gen-control-zone">
      <div class="gen-tabs-group">
        <div class="gen-tabs" id="genTabsContainer">
          <button v-for="tab in TABS" :key="tab.id" class="gen-tab" :class="{ 'is-active': activeTab === tab.id }" :title="tab.label" @click="switchTab(tab.id)" @mouseenter="onTabHover(tab.id)">
            <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" v-html="tab.icon"></svg>
            <span class="tab-label">{{ tab.label }}</span>
            <span class="tab-dot" :class="tabDotClass(tab.id)"></span>
          </button>
        </div>
      </div>
      <!-- 原文三层视图下拉（仅原文 tab 显示；替代原面板内固定分段控件）/ Transcript layer dropdown (transcript tab only; replaces the in-panel segmented control) -->
      <div class="gen-layer-picker" v-if="activeTab === 'transcript'">
        <button
          ref="layerPickerBtn" class="gen-layer-trigger" v-bind="layerPickerTriggerAttrs"
          :aria-label="t('generating.layer.picker_label')" :title="t('generating.layer.picker_label')"
          @click="toggleLayerPicker"
        >
          <span>{{ t(`generating.layer.${layerView}`) }}</span>
          <span v-if="layerView === 'formal'" class="rec-layer-ai">AI</span>
          <svg class="gen-layer-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <div ref="layerPickerMenu" class="gen-toolbar-more-menu gen-layer-menu" v-bind="layerPickerMenuAttrs" :class="{ 'is-open': showLayerPicker }" :aria-label="t('generating.layer.picker_label')">
          <button class="gen-toolbar-more-item" :class="{ 'is-selected': layerView === 'formal' }" role="menuitem" @click="selectLayer('formal')">
            {{ t('generating.layer.formal') }}
            <span class="rec-layer-ai">AI</span>
          </button>
          <button class="gen-toolbar-more-item" :class="{ 'is-selected': layerView === 'clean' }" role="menuitem" :disabled="!cleanupAvailable" @click="selectLayer('clean')">
            {{ t('generating.layer.clean') }}
          </button>
          <button class="gen-toolbar-more-item" :class="{ 'is-selected': layerView === 'raw' }" role="menuitem" @click="selectLayer('raw')">
            {{ t('generating.layer.raw') }}
          </button>
        </div>
      </div>
    </div>

    <!-- 内容区（子组件） / Content area (sub-components) -->
    <div class="gen-content">
      <TranscriptPanel
        ref="transcriptPanelRef"
        v-model:layer-view="layerView"
        :visible="activeTab === 'transcript'"
        :transcript-items="transcriptItems"
        :chapters="chapters"
        :expanded-chapters="expandedChapters"
        :visible-chapter-indices="visibleChapterIndices"
        :active-chapter-idx="activeChapterIdx"
        :flat-transcript="flatTranscript"
        :task-status="task?.status"
        :task="task"
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
        :task="task"
        :processing="!!task?.status && ['recording', 'processing', 'transcribing', 'summarizing', 'awaiting_mapping'].includes(task.status)"
        :pending="task?.status === 'pending'"
        :has-summary="!!task?.summary"
        :todos-count="todos.length"
        :todos-done-count="todos.filter(x => x.done).length"
        :proposal="sp.summaryProposal.value"
        :preview-mode="sp.summaryPreviewMode.value"
        @change="onSummaryChange"
        @toggle-chapter="toggleSummaryChapter"
        @switch-tab="switchTab"
        @open-preview="sp.openSummaryPreview()"
        @accept="sp.acceptSummaryProposal()"
        @reject="sp.rejectSummaryProposal()"
        @toggle-gap="sp.toggleGapExpanded"
      />

      <NotesPanel
        ref="notesPanelRef"
        :visible="activeTab === 'notes'"
        :markdown="notesContent"
        :notes-saved="notesSaved"
        :proposal="np.notesProposal.value"
        :preview-mode="np.notesPreviewMode.value"
        :segments="np.notesProposalSegments.value"
        :stats="np.notesProposalStats.value"
        @change="onNotesChange"
        @open-preview="np.openNotesPreview()"
        @accept="np.acceptNotesProposal()"
        @reject="np.rejectNotesProposal()"
        @toggle-gap="np.toggleNotesGapExpanded"
      />

      <DecisionFlowPanel
        :visible="activeTab === 'todos'"
        :task-id="data.taskId"
        :todos="todos"
        :anchor-todo-id="anchorTodoId"
        :from-evolution="route.query.from === 'evolution'"
        @delete="onDeleteTodo"
        @update="onEditTodo"
        @status-change="onStatusChange"
        @add="showAddDecisionDialog = true"
      />

      <!-- 洞察台（会后） / Insight Deck：不再区分板/卡视图，统一为 AI 共创的 HTML 产物呈现 -->
      <div v-show="activeTab === 'insights'" class="gen-insights-wrap">
        <InsightBoard
          :artifact="board"
          :loading="boardLoading"
          @seek="onInsightSeek"
          @refresh="loadBoardData"
          @co-create="onBoardCoCreate"
          @co-create-section="onBoardCoCreateSection"
        />
      </div>
    </div>
    <!-- 浮动选中工具栏 / Floating selection toolbar -->
    <SelectionToolbar
      container-selector=".gen-content"
      :textarea-selectors="['textarea.gen-textarea-editor', 'textarea.db-card-textarea', 'textarea.db-edit-area']"
      :formalize-enabled="task?.status === 'completed'"
      @action="onSelectionAction"
      @formalize-selection="(ids) => transcriptPanelRef?.formalizeSelection(ids)"
    />
    <!-- 行间编辑浮动输入框（input 态 + result 确认态共用，确认卡带执行方回显） -->
    <InlineEditInput
      :visible="inlineEdit.showInput.value || inlineEdit.showDiff.value"
      :loading="inlineEdit.isLoading.value"
      :anchor-rect="inlineEdit.anchorRect.value"
      :diff-visible="inlineEdit.showDiff.value"
      :edited-text="inlineEdit.editedText.value"
      :model-usage="inlineEdit.lastModelUsage.value"
      @submit="onInlineEditSubmit"
      @cancel="inlineEdit.cancelEdit"
      @accept="inlineEdit.acceptEdit"
      @reject="inlineEdit.rejectEdit"
      @goto-settings="onInlineEditGotoSettings"
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

    <!-- 添加决策：与决策中心「手动补录决策」共用同一弹层（样式与数据口径统一） / Add decision dialog (shared with Decision Center) -->
    <AddDecisionDialog
      ref="addDecisionDialogRef"
      v-model="showAddDecisionDialog"
      :default-task-id="data.taskId"
      @submit="onAddDecisionSubmit"
    />
    </template>

    <!-- AC-4 显式确认（QA-R1 DEF-04）：切云端重试前告知数据上云，绝不静默上云（PRD R7）。
         置于根层级（v-if/v-else 之外），失败态下同样可用；ConfirmDialog 内部 Teleport 到 body。
         AC-4 explicit confirmation before cloud retry; placed at root so it mounts in the failed branch too. -->
    <ConfirmDialog
      v-model="showCloudFallbackConfirm"
      :title="t('generating.failure.cloud_retry_confirm_title')"
      :message="t('generating.failure.cloud_retry_confirm_message')"
      :confirm-text="t('generating.failure.cloud_retry_confirm_action')"
      :cancel-text="t('generating.failure.cloud_retry_confirm_cancel')"
      :danger="false"
      @confirm="onCloudFallbackConfirm"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { isPlaceholderName } from '@/utils/speakerDisplay'
import { deleteTask, retranscribe, retrySummary, fetchSyncStatus, syncTaskToProject, fetchTask, correctTaskText } from '@/api/tasks'
import type { SyncStatus } from '@/api/tasks'
import type { VoiceprintMatchItem } from '@/api/types'
import { usePopMenu } from '@/composables/usePopMenu'
import { useDropdownPopup } from '@/composables/useDropdownPopup'
import type { LayerView } from '@/utils/transcriptLayers'
import SelectionToolbar from '@/components/SelectionToolbar.vue'
import InlineEditInput from '@/components/InlineEditInput.vue'
import TranscriptPanel from './generating/TranscriptPanel.vue'
import SummaryPanel from './generating/SummaryPanel.vue'
import ProgressDialog from './generating/ProgressDialog.vue'
import NotesPanel from './generating/NotesPanel.vue'
import DecisionFlowPanel from './generating/DecisionFlowPanel.vue'
import { parseAnchorTodoId } from './decisionEvolutionNav'
import InsightBoard from './generating/InsightBoard.vue'
import { loadBoard, loadBoardMeta, type BoardArtifact } from '@/api/board'
import { onBoardWritten } from '@/composables/useBoardSync'
import { onTaskWritten } from '@/composables/useTaskWrites'
import GeneratingSpeakerZone from './generating/GeneratingSpeakerZone.vue'
import { dismissVoiceprintSuggestion, runVoiceprintMatch } from '@/api/voiceprint'
import ArchiveDialog from './generating/ArchiveDialog.vue'
import DeleteDialog from './generating/DeleteDialog.vue'
import AddDecisionDialog from './decisions/AddDecisionDialog.vue'
import type { TodoCreatePayload } from '@/api/notes'
import { extractErrorMessage } from '@/api/client'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { showToast } from '@/composables/useToast'
import { useGeneratingData } from '@/composables/useGeneratingData'
import { useSpeakerBinding } from '@/composables/useSpeakerBinding'
import { useSpeakerPanel } from '@/composables/useSpeakerPanel'
import { usePlaybackFollow } from '@/composables/usePlaybackFollow'
import { useNotesAndTodos } from '@/composables/useNotesAndTodos'
import { useInlineEdit } from '@/composables/useInlineEdit'
import { useSummaryProposal } from '@/composables/useSummaryProposal'
import { useNotesProposal } from '@/composables/useNotesProposal'
import { useAiInsights } from '@/composables/useAiInsights'
import { useMeetingRoster } from '@/composables/useMeetingRoster'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const taskStore = useTaskStore()

// ─── 模板 refs / Template refs ───
const transcriptPanelRef = ref<InstanceType<typeof TranscriptPanel> | null>(null)
const summaryPanelRef = ref<InstanceType<typeof SummaryPanel> | null>(null)
const notesPanelRef = ref<InstanceType<typeof NotesPanel> | null>(null)
const kbSearchInputRef = ref<HTMLInputElement | null>(null)
const kbCreateInputRef = ref<HTMLInputElement | null>(null)
const kbDropdownRef = ref<HTMLElement | null>(null)

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

const inlineEdit = useInlineEdit()
/** 纪要改写提案（原位 diff 预览 Layer 1）：共享单例状态，接受/拒绝由 SummaryPanel 操作条发起 */
const sp = useSummaryProposal()
// 随记改写提案（propose_notes）：与纪要同一机制，在随记 Tab 原位预览，用户接受才落盘
const np = useNotesProposal()
/** 洞察消息的跨组件共享状态（仅用于修正后强制重拉，不让陈内存写回覆盖新落盘的文本） */
const insights = useAiInsights()
/** 回溯修正进行中：一次请求会同时改写任务/洞察/洞察板/导出件四份产物，不允并发提交 */
const correcting = ref(false)
const rosterComposable = useMeetingRoster(data.taskId, data.task)

// ─── 解构到模板作用域 / Destructure to template scope ───
const {
  task, activeTab, TABS, switchTab,
  chapters, activeChapterIdx, scrollToChapter, allChaptersVisible,
  visibleChapterIndices, expandedChapters, summaryExpandedChapters,
  transcriptItems, flatTranscript, summaryMd, todos, notesContent, notesSaved,
  showArchiveDialog, showDeleteDialog, metaDuration, metaDateShort,
  projects, showProjectDropdown, onSelectProject, openDatePicker, breadcrumbTitle,
  kbSearchQuery, filteredProjects, showKbCreateInput, kbCreateName, createAndLinkKb,
  player, seekAudio, onCopy, onExport, onFullscreen, speakers, audioUrl,
  toggleChapterExpand, toggleSummaryChapter, toggleChapterTranscript, showAllChapters,
  isFailed, failureInfo,
  canFallbackCloud, cloudFallbackBlocked,
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
  onNotesChange, onSummaryChange, onAddTodo, onDeleteTodo, onEditTodo, onStatusChange, loadTodos, loadNotes,
} = notes

// ─── 添加决策：复用决策中心「手动补录决策」弹层（DC-UNIFY-01 样式/数据统一） ───
const showAddDecisionDialog = ref(false)
const addDecisionDialogRef = ref<InstanceType<typeof AddDecisionDialog> | null>(null)
async function onAddDecisionSubmit(taskId: string, payload: TodoCreatePayload) {
  try {
    await onAddTodo(payload, taskId)
    showToast(t('decisions.toast_add_ok'), 'success')
    showAddDecisionDialog.value = false
    // 重拉保证与后端权威数据一致（owner 解析、归属其它会议的节点不干扰本地列表）
    void loadTodos()
  } catch (e) {
    addDecisionDialogRef.value?.setSubmitting(false)
    showToast(t('decisions.toast_op_failed', { reason: extractErrorMessage(e) }), 'error')
  }
}

// ─── 知识库同步状态 / Knowledge base sync status ───
const syncStatus = ref<SyncStatus>({ can_sync: false })
const isSyncing = ref(false)

// ─── 洞察台（会后 HTML 产物共创） / Insight Deck (post-meeting HTML co-create) ───

/** 洞察图/节点点击→跳回原文并定位时间轴 / Seek from insight: switch to transcript + seek */
function onInsightSeek(ms: number) {
  switchTab('transcript')
  player.seekToMs(ms)
}

// 【已退役】会后补分析触发入口：随「洞察共创 · 会话驱动」下线，历史洞察消息仍只读呈现

// ─── 洞察板（HTML 产物共创版） / Insight Board (HTML artifact) ───
// 单一写入源在后端：AI 经会话工具 revise_insight_board 整份落盘，前端只读重拉；
// 旧 Board Spec 的失败归因横幅/生成端点已随共创模式退役。
//
// 自动同步双通道（不再依赖人工刷新）：
//   ① 信号通道——对话流里识别到一次成功落板（useBoardSync 广播 board-written）→ 即时重拉；
//   ② 版本通道——洞察 Tab 可见时每 10s 探测 ?meta=1 的 revision，
//      盖住「写板发生在另一个窗口/设备、本标签页收不到对话流信号」的缝隙。
// 换新呈现：静默替换 + rev 徽标脉冲（共创场景用户本已预期内容会变，不打断阅读）。
const board = ref<BoardArtifact>({ html: null, revision: 0, updated_at: null })
const boardFetched = ref(false)
const boardLoading = ref(false)
/** 离开洞察 Tab 期间收到过落板信号 / Board written while the tab was hidden */
const boardDirty = ref(false)

const BOARD_POLL_MS = 10_000
let boardPollTimer: ReturnType<typeof setInterval> | null = null

// 圆点跟随实际内容源：洞察 Tab 是否有点取决于洞察板产物是否存在，
// 而板是懒加载的——悬停时补一次首拉，保证圆点在切 Tab 前就能正确点亮
function onTabHover(tabId: string) {
  if (tabId === 'insights' && !boardFetched.value && !boardLoading.value) loadBoardData()
}

function tabDotClass(tabId: string): string {
  const base = data.dotClass(tabId)
  if (tabId === 'insights') return board.value.html ? 'is-done' : base
  return base
}

async function loadBoardData() {
  boardFetched.value = true
  boardLoading.value = true
  try {
    board.value = await loadBoard(data.taskId)
  } catch {
    // 读板失败不阻断卡片视图 / Load failure never blocks the cards view
  } finally {
    boardLoading.value = false
  }
}

/** 轻量版本探测：只在版本号前进（或无板→有板）时才拉整份正文 */
async function probeBoardRevision() {
  if (boardLoading.value || document.hidden) return
  try {
    const meta = await loadBoardMeta(data.taskId)
    if (meta.revision !== board.value.revision || (meta.exists && !board.value.html)) {
      await loadBoardData()
    }
  } catch {
    // 探测失败静默跳过，下一轮再试 / Probe failure is silent; next tick retries
  }
}

function startBoardPolling() {
  stopBoardPolling()
  boardPollTimer = setInterval(probeBoardRevision, BOARD_POLL_MS)
}

function stopBoardPolling() {
  if (boardPollTimer) { clearInterval(boardPollTimer); boardPollTimer = null }
}

// Tab 切换：进入→首拉（脏则重拉）+ 开轮询；离开→停轮询（不可见不产生流量）
watch(activeTab, (tab) => {
  if (tab === 'insights') {
    if (!boardFetched.value || boardDirty.value) loadBoardData()
    boardDirty.value = false
    startBoardPolling()
  } else {
    stopBoardPolling()
  }
}, { immediate: true })

// 落板信号：正在看洞察 Tab 就即时换新；在其它 Tab 则记脏，回去时补拉
let offBoardWritten: (() => void) | null = null
let offTaskWritten: (() => void) | null = null
/** 窗口回到前台立即对齐：隐藏时轮询主动跳过且后台定时器会被浏览器节流，回到前台不等 10s 就补一次探测 */
function onVisibilityChange() {
  if (!document.hidden && activeTab.value === 'insights') probeBoardRevision()
}
onMounted(() => {
  offBoardWritten = onBoardWritten(() => {
    if (activeTab.value === 'insights') loadBoardData()
    else boardDirty.value = true
  })
  // AI 会话写回任务数据（决策节点/纪要/注入）→ 呈现侧即时对齐（§5.4）：
  // 写点在后端工具落盘，本页不在实时通道上，不重拉就是"AI 说改了、页面还是旧的"
  offTaskWritten = onTaskWritten(async ({ domains }) => {
    const all = !domains || domains.length === 0
    try {
      const updated = await fetchTask(data.taskId)
      taskStore.patchTaskLocal(data.taskId, updated)
    } catch { /* 保留旧视图，切 Tab 时 loadTodos 仍会重拉 */ }
    if (all || domains?.includes('todos')) void data.loadTodos()
    // 随记：接受 AI 提案或 AI 写回后以服务端为准刷新（用 notes 版 loadNotes，它会取消挂起的自动保存）
    if (all || domains?.includes('notes')) void loadNotes()
    void loadSyncStatus()
  })
  document.addEventListener('visibilitychange', onVisibilityChange)
})
onUnmounted(() => {
  stopBoardPolling()
  document.removeEventListener('visibilitychange', onVisibilityChange)
  offBoardWritten?.()
  offBoardWritten = null
  offTaskWritten?.()
  offTaskWritten = null
})

/** 共创起跳：展开 AI 面板并预填修订请求到输入框（不自动发送）；coCreate 标记使智能体轮自动升可写档以落盘 */
function onBoardCoCreate() {
  window.dispatchEvent(new CustomEvent('quote-to-ai', {
    detail: { prefill: t('generating.insights.board.co_create_msg'), coCreate: true },
  }))
}

/** 单节共创起跳：预填带节锈点 id/标题的定向修订请求，引导 AI 用 revise_insight_board_section 只改这一节 */
function onBoardCoCreateSection(sec: { id: string; title: string }) {
  const label = sec.title || sec.id
  const prefill = t('generating.insights.board.co_create_section_msg', { title: label, id: sec.id })
  window.dispatchEvent(new CustomEvent('quote-to-ai', {
    detail: { prefill, coCreate: true },
  }))
}

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

// [状态同步] 说话人绑定采用极简内联交互：进入绑定态后直接通过 chip 关联身份，不再提供引导弹窗

// [状态同步] 任务状态变化时刷新知识库同步状态（完成/关联项目时显示同步按钮）
watch(() => data.task.value, (t) => {
  if (t?.status === 'completed' && t?.project_id) {
    loadSyncStatus()
  } else {
    syncStatus.value = { can_sync: false }
  }
}, { immediate: true })

// ─── 说话人绑定 → 参会人自动同步 / Speaker binding → roster auto-sync ───
// L3：占位名不入 roster（判定器命中即跳过同步，设计稿 §3.2）
const boundNames = computed(() =>
  bindingLegend.value.filter(b => b.bound && !isPlaceholderName(b.displayName)).map(b => b.displayName)
)

watch(boundNames, (names) => {
  const currentRoster = [...rosterComposable.roster.value]
  const manualNames = rosterComposable.manualNames
  let changed = false
  // 新增：绑定的人自动加入 roster / Auto-add bound speakers to roster
  for (const name of names) {
    if (!currentRoster.includes(name)) {
      currentRoster.push(name)
      changed = true
    }
  }
  // 移除：仅移除不再绑定的「自动同步」名字，保留手动添加的 / Only remove auto-synced names no longer bound; preserve manual adds
  const nameSet = new Set(names)
  const before = currentRoster.length
  rosterComposable.roster.value = currentRoster.filter(n => nameSet.has(n) || manualNames.has(n))
  if (rosterComposable.roster.value.length !== before) changed = true
  if (changed) rosterComposable.persist()
})

// ─── 知识库下拉：统一弹出交互规范（点击外部关闭 + ↑↓/Enter 键盘导航 + 焦点保持在检索框）
//     KB dropdown: unified popup spec (click-outside close + ↑↓/Enter nav + focus stays in search input) ───
const { resetNav: resetKbNav } = useDropdownPopup({
  isOpen: () => data.showProjectDropdown.value,
  close: () => { data.showProjectDropdown.value = false },
  root: kbDropdownRef,
  autoFocus: kbSearchInputRef,
})

// ─── 知识库下拉打开时聚焦检索框；关闭时清理状态 / Focus search on open; clean up state on close ───
watch(() => data.showProjectDropdown.value, (open) => {
  if (!open) {
    // 关闭时清理检索与新建状态 / Clean up search & create state on close
    data.kbSearchQuery.value = ''
    data.showKbCreateInput.value = false
    data.kbCreateName.value = ''
  }
})

// 检索词或就地新建状态变化 → 候选项集合已变，重置键盘高亮 / Filter or create-state change → reset nav highlight
watch([data.kbSearchQuery, data.showKbCreateInput], () => resetKbNav())

// ─── 更多菜单 / More menu ──
const genMoreBtn = ref<HTMLElement | null>(null)
const genMoreDropdown = ref<HTMLElement | null>(null)
const { visible: showMoreMenu, toggle: toggleGenMore, close: closeGenMore, triggerAttrs: genMoreTriggerAttrs, menuAttrs: genMoreMenuAttrs } = usePopMenu(genMoreDropdown, genMoreBtn)
let genMoreHoverTimer: ReturnType<typeof setTimeout> | null = null
function onGenMoreEnter() { if (genMoreHoverTimer) { clearTimeout(genMoreHoverTimer); genMoreHoverTimer = null } }
function onGenMoreLeave() { genMoreHoverTimer = setTimeout(() => closeGenMore(), 150) }

// ─── 原文三层视图下拉（tab 栏右侧；真源在此，TranscriptPanel prop 消费）/ Transcript layer dropdown (tab-bar right; source of truth here) ──
const layerView = ref<LayerView>('clean')
const cleanupAvailable = computed(() => task.value?.transcript_layers?.cleanup === true)
const layerPickerBtn = ref<HTMLElement | null>(null)
const layerPickerMenu = ref<HTMLElement | null>(null)
const { visible: showLayerPicker, toggle: toggleLayerPicker, close: closeLayerPicker, triggerAttrs: layerPickerTriggerAttrs, menuAttrs: layerPickerMenuAttrs } = usePopMenu(layerPickerMenu, layerPickerBtn)
function selectLayer(v: LayerView) {
  layerView.value = v
  closeLayerPicker()
}

// ─── 工具栏操作 / Toolbar actions ───

/** 复制会议标题 / Copy meeting title */
async function onCopyTitle() {
  closeGenMore()
  const t = task.value
  const title = t?.title || t?.audio_name || ''
  if (!title) return
  try { await navigator.clipboard.writeText(title) } catch { /* 剪贴板不可用静默降级 */ }
}

/** 复制纪要摘要 / Copy summary */
async function onCopySummary() {
  closeGenMore()
  const summary = task.value?.summary || ''
  if (!summary) return
  try { await navigator.clipboard.writeText(summary) } catch { /* 剪贴板不可用静默降级 */ }
}

/** 重命名 / Rename */
async function onRenameTask() {
  closeGenMore()
  const cur = task.value
  const current = cur?.title || cur?.audio_name || ''
  const newName = prompt(t('task.rename_prompt'), current)
  if (!newName || !newName.trim() || newName.trim() === current) return
  try {
    const { updateTask } = await import('@/api/tasks')
    const updated = await updateTask(data.taskId, { title: newName.trim() })
    taskStore.patchTaskLocal(data.taskId, { title: updated.title })
  } catch (e) {
    console.error('rename failed:', e)
    alert(t('task.errors.rename_failed'))
  }
}

/**
 * 决策中心演变链跳转锚点：?tab=todos&todo=<id>&from=evolution
 * 切到决策面板后由 DecisionFlowPanel 自行展开闭档组、滚动高亮并显示来源横幅。
 */
const anchorTodoId = computed(() => parseAnchorTodoId(route.query))

/**
 * 决策中心跳转锚点：?tab=summary&dq=<决策文本> → 切到纪要页并在正文中定位选区高亮。
 * 文本可能因纪要编辑而对不上：匹配失败后静默停留在纪要页，不报错、不白屏。
 * Anchor flow from the Decision Center: switch to the minutes tab and select the
 * quoted decision text; a failed match degrades silently to the plain minutes view.
 */
function anchorFromDecisionCenter() {
  const tab = typeof route.query.tab === 'string' ? route.query.tab : ''
  if (tab && data.TABS.value.some(x => x.id === tab)) data.switchTab(tab)
  const dq = typeof route.query.dq === 'string' ? route.query.dq.trim() : ''
  if (!dq) return
  let attempts = 0
  const tick = () => {
    attempts += 1
    const md = data.summaryMd.value
    const el = summaryPanelRef.value?.textareaEl as HTMLTextAreaElement | undefined | null
    if (md && el) {
      let idx = md.indexOf(dq)
      if (idx < 0) idx = md.indexOf(dq.slice(0, 10))
      if (idx >= 0) {
        el.focus({ preventScroll: false })
        el.setSelectionRange(idx, Math.min(idx + dq.length, md.length))
        return
      }
    }
    if (attempts < 15) window.setTimeout(tick, 250)
  }
  window.setTimeout(tick, 100)
}
async function onRetrySummary() {
  closeGenMore()
  // 乐观切进行态：点击即有反馈，不等待慢列表（全量列表 35MB，曾稳定 2.8s 白屏）。
  // 详情轮询立即启动接管真实状态；列表刷新只服务会议库，后台进行不阻塞 UI。
  taskStore.patchTaskLocal(data.taskId, {
    status: 'processing',
    progress: 75,
    error: undefined,
    error_category: undefined,
    error_suggestion: undefined,
    failed_stage: undefined,
  })
  data.startPolling()
  try {
    await retrySummary(data.taskId)
    void taskStore.loadTasks()
  } catch (e) {
    // 提交失败：回拉详情恢复真实状态，防乐观态卡死在处理中
    console.error('retry summary failed:', e)
    try {
      taskStore.patchTaskLocal(data.taskId, await fetchTask(data.taskId))
    } catch { /* 保留乐观态，等下次轮询纠偏 */ }
  }
}
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

// ─── AC-4 切云端重试（QA-R1 DEF-04）：仅在用户显式确认「数据上云」后调用 engine_override=cloud
//     AC-4 cloud fallback: only invoked with engine_override=cloud after explicit user confirmation ───
const showCloudFallbackConfirm = ref(false)

async function onCloudFallbackConfirm() {
  try {
    await retranscribe(data.taskId, { engineOverride: 'cloud' })
    taskStore.patchTaskLocal(data.taskId, {
      status: 'transcribing',
      error: undefined, error_category: undefined, error_suggestion: undefined,
      error_code: undefined, can_fallback_cloud: undefined,
    })
    showToast(t('generating.failure.cloud_retry_started'), 'success')
    data.startPolling()
  } catch (e) {
    console.error('cloud fallback retry failed:', e)
    showToast(t('generating.failure.cloud_retry_failed'), 'error')
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

// ─── 声纹识别：人员栏内触发，结果落本地 / Voiceprint match triggered within personnel bar ───
const voiceprintRunning = ref(false)

/** 过滤已忽略建议后的可见项 / Visible items after dismissed filtering */
const visibleVoiceprintItems = computed<VoiceprintMatchItem[] | null>(() => {
  const items = task.value?.voiceprint_match ?? null
  if (!items) return null
  const dismissed = new Set(task.value?.voiceprint_dismissed ?? [])
  return dismissed.size ? items.filter(it => !dismissed.has(it.speaker_id)) : items
})

async function runVoiceprint() {
  if (voiceprintRunning.value || !canBind.value || flatTranscript.value.length === 0) return
  voiceprintRunning.value = true
  try {
    const res = await runVoiceprintMatch(data.taskId)
    taskStore.patchTaskLocal(data.taskId, {
      voiceprint_match: res.results,
      voiceprint_auto_mapping: res.auto_mapping,
      voiceprint_dismissed: [],
    })
  } catch {
    showToast(t('generating.voiceprint.failed'), 'error')
  } finally {
    voiceprintRunning.value = false
  }
}

async function onVoiceprintApply(speakerId: number, uuid: string) {
  await selectBinding(speakerId, uuid)
}

async function onVoiceprintDismiss(speakerId: number) {
  // 若当前绑定正来自这条声纹建议，忽略即一并撤销；手工改绑他人则保留
  const item = (task.value?.voiceprint_match ?? []).find(it => it.speaker_id === speakerId)
  if (
    item?.status === 'matched' && item.matched_uuid
    && binding.currentBindingMapping[speakerId] === item.matched_uuid
  ) {
    await selectBinding(speakerId, '')
  }
  const dismissed = new Set(task.value?.voiceprint_dismissed ?? [])
  dismissed.add(speakerId)
  taskStore.patchTaskLocal(data.taskId, {
    voiceprint_dismissed: [...dismissed].sort((a, b) => a - b),
  })
  try {
    await dismissVoiceprintSuggestion(data.taskId, speakerId)
  } catch {
    showToast(t('generating.voiceprint.failed'), 'error')
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

/** 文本回溯修正：把一条误识别→正确文本映射落到本场会议的全部产物
 *  Retroactive correction: apply one wrong→correct mapping to every artifact of this meeting.
 *
 * 取代旧 replaceInTranscriptDom：那个实现只在「原文 Tab 的 .txt DOM」里改第一处命中就 return，
 * 不回写数据也不落盘，因此纪要 Tab 完全无效、一次重渲染就复原，却仍无条件报「已修正」。
 * 现在写入权威在后端（core.text_correction），前端拿到真实命中数后从数据源重拉呈现。
 */
async function applyTextCorrection(oldText: string, newText: string, createdMapping = false) {
  if (correcting.value) return
  correcting.value = true
  try {
    const result = await correctTaskText(data.taskId, oldText, newText)
    await refreshAfterCorrection()
    const scope = createdMapping ? t('generating.correction.mapping_saved') : ''
    if (result.replaced > 0) {
      showToast(t('generating.correction.applied', { scope, text: newText, n: result.replaced }), 'success')
    } else {
      // 映射存住了，但本场会议确实没这个词：说清事实，不给假反馈
      showToast(t('generating.correction.no_match', { scope, text: oldText }), 'warn')
    }
  } catch (e) {
    showToast(t('generating.correction.failed', { reason: extractErrorMessage(e) }), 'error')
  } finally {
    correcting.value = false
  }
}

/** 修正后从数据源重拉各面板 / Re-pull every panel from its source of truth after a correction. */
async function refreshAfterCorrection() {
  // 1. 任务主体（原文/纪要/标题/章节）走 store，计算属性链自动重渲染
  try {
    const updated = await fetchTask(data.taskId)
    taskStore.patchTaskLocal(data.taskId, updated)
  } catch { /* 保留旧视图；下一轮轮询仍会拉到新值 */ }
  // 2. 决策项独立端点，不在 task 快照里
  data.loadTodos().catch(() => { /* */ })
  // 3. 随记：用户正在随记 Tab 时不覆盖其编辑中的内容（与管线完成时的既有规则一致）
  if (data.activeTab.value !== 'notes') data.loadNotes().catch(() => { /* */ })
  // 4. 洞察卡片：内存缓存不重拉会与新落盘的 insights.json 不一致，且切会议时会被写回覆盖
  insights.reloadTaskMessages(data.taskId).catch(() => { /* */ })
  // 5. 洞察板：仅在已拉取过时重拉，避免为未打开过的 Tab 白跑一次请求（脏标记属于上一个会议，先清）
  boardDirty.value = false
  if (boardFetched.value) loadBoardData()
}

function onSelectionAction(action: string, text: string, _source: string, _blockIndex: number, replacement?: string, createdMapping?: boolean) {
  // 划词工具栏已下架改写/总结/提取待办，仅保留热词修正；
  // 其余 AI 意图由用户通过「引用到 AI」自行表达
  // Toolbar rewrite/summarize/extract retired; only hotword correction remains.
  if (action === 'correct' && replacement) {
    // 全量回溯修正本场会议（后端写盘 + 前端从数据源重拉） / Retroactive, persisted, then re-pulled
    void applyTextCorrection(text, replacement, createdMapping)
  }
}

// ─── 行间编辑 / Inline edit ───
// 工具栏「改写」入口已下架：划词不再 emit inline-edit，onInlineEditRequest 随之移除；
// InlineEditInput 基础设施暂保留（可见性恒为 false），待其它入口评估后统一清理
// The toolbar rewrite entry is retired; inline-edit requests no longer fire.
// The InlineEditInput scaffolding stays dormant (visible is always false).
async function onInlineEditSubmit(instruction: string) {
  await inlineEdit.submitInstruction(instruction)
}

/** 回显标签起跳：更换面板外操作的默认模型（AI 算力入口治理 §5） */
function onInlineEditGotoSettings() {
  void router.push({ name: 'settings', query: { cat: 'ai' } })
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
// 口径：speaker_mapping 的键数（未命名空串也计数），与人员栏「未关联 N」同源——
// 顶部显示实际说话人数，而非已命名人数 / Count mapping keys (unnamed included),
// aligned with the personnel bar's unbound count.
const speakerCount = computed(() => {
  const m = data.task.value?.speaker_mapping
  return m ? Object.keys(m).length : 0
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
  // 原写法是 const stopWatch = watch(..., { immediate: true })，而 immediate 回调在
  // const 完成赋值之前就会同步执行 → stopWatch() 触发 TDZ ReferenceError，
  // 连带 initBindingMapping() 被跳过：从侧栏点进会议（任务已在 store 里）必命中此路径。
  // The previous form ran the immediate callback before `const stopWatch` was
  // assigned, so stopWatch() threw a TDZ ReferenceError and initBindingMapping()
  // was skipped — guaranteed on the common path where the task is already loaded.
  if (data.task.value) {
    binding.initBindingMapping()
  } else {
    const stopUntilTaskReady = watch(() => data.task.value, (t) => {
      if (t) { binding.initBindingMapping(); stopUntilTaskReady() }
    })
    onUnmounted(stopUntilTaskReady)
  }
  document.addEventListener('click', panel.onDocClickCloseSearch)
  document.addEventListener('click', binding.onDocClickForDropdown)

  // 决策中心跳转锚点 / Anchor positioning when coming from the Decision Center
  anchorFromDecisionCenter()

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
})
</script>




