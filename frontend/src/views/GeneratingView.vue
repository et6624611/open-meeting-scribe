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
        <span class="gen-meta-project">
          <span class="gen-meta-project-chip" :class="{ 'is-bound': !!task?.project_id, 'is-unbound': !task?.project_id }" role="button" tabindex="0" :title="task?.project_id ? t('generating.meta.linked_kb_tip') : t('generating.meta.link_kb_tip')" @click.stop="showProjectDropdown = !showProjectDropdown">
            <!-- book-open 图标：知识库语义 -->
            <svg v-if="task?.project_id" width="12" height="12" viewBox="0 0 24 24" fill="currentColor" fill-opacity="0.15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
            <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
            <span>{{ currentProjectName }}</span>
            <!-- 尾部状态图标：未关联 +，已关联 hover ✕ -->
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
          <!-- 知识库关联引导图标（仅未关联时显示） -->
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

    <!-- 说话人绑定条（子组件） -->
    <GeneratingSpeakerBar
      :visible="showBindingBar"
      :legend="bindingLegend"
      :unbound-count="unboundCount"
      :current-mapping="currentBindingMapping"
      :dropdown="bindingDropdown"
      :filtered-speakers="dropdownSpeakers"
      @open-info="openOnboarding"
      @open-dropdown="openBindingDropdown"
      @locate-speaker="toggleLocateSpeaker"
      @skip="skipMapping"
      @confirm="confirmMapping"
      @close="bindingBarHidden = true"
      @select="selectBinding"
      @create-and-bind="createAndBind"
      @dropdown-keydown="onDropdownKeydown"
      @update:dropdown-search="bindingDropdown.search = $event"
    />

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

    <!-- 内容区（子组件） -->
    <div class="gen-content">
      <TranscriptPanel
        ref="transcriptPanelRef"
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
        @toggle-chapter="toggleChapterExpand"
        @toggle-chapter-transcript="toggleChapterTranscript"
        @seek="seekFromTranscriptClick"
        @speaker-label-click="onSpeakerLabelClick"
        @toggle-locate="toggleLocateSpeaker"
        @toggle-speaker="toggleSpeakerFilter"
        @clear-filter="clearSpeakerFilter"
        @nav-focus="navFocusLine"
        @toggle-panel="speakerPanelVisible = !speakerPanelVisible"
        @toggle-search="toggleSearch"
        @search-blur="onSearchBlur"
        @resume-follow="resumeFollowPlayback"
        @show-all-chapters="showAllChapters"
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
        @insert-md="insertMd"
      />

      <TodosPanel
        :visible="activeTab === 'todos'"
        :todos="todos"
        :show-add-form="showAddForm"
        v-model:new-todo-text="newTodoText"
        v-model:new-todo-assignee="newTodoAssignee"
        @toggle="onToggleTodo"
        @delete="onDeleteTodo"
        @locate="locateTodoSource"
        @toggle-form="showAddForm = !showAddForm"
        @add="onAddTodo"
      />
    </div>
    <!-- 浮动选中工具栏 -->
    <SelectionToolbar
      container-selector=".gen-content"
      @action="onSelectionAction"
    />

    <!-- 说话人绑定引导弹窗（子组件） -->
    <OnboardingDialog
      v-model="showOnboarding"
      :demo-lines="demoLines"
      @close="closeOnboarding"
    />

    <!-- 知识库关联引导弹窗（子组件） -->
    <ProjectOnboardingDialog
      v-model="showProjectOnboarding"
      :connected="projConnected"
      @close="closeProjOnboarding"
    />

    <!-- 归档确认对话框（子组件） -->
    <ArchiveDialog
      v-model="showArchiveDialog"
      @confirm="onArchive"
    />

    <!-- 删除确认对话框（子组件） -->
    <DeleteDialog
      v-model="showDeleteDialog"
      @confirm="onDeleteConfirm"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { deleteTask, retranscribe, retrySummary } from '@/api/tasks'
import { usePopMenu } from '@/composables/usePopMenu'
import SelectionToolbar from '@/components/SelectionToolbar.vue'
import TranscriptPanel from './generating/TranscriptPanel.vue'
import SummaryPanel from './generating/SummaryPanel.vue'
import NotesPanel from './generating/NotesPanel.vue'
import TodosPanel from './generating/TodosPanel.vue'
import GeneratingSpeakerBar from './generating/GeneratingSpeakerBar.vue'
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

const { t } = useI18n()
const router = useRouter()
const taskStore = useTaskStore()

// ─── 模板 refs ───
const transcriptPanelRef = ref<InstanceType<typeof TranscriptPanel> | null>(null)
const summaryPanelRef = ref<InstanceType<typeof SummaryPanel> | null>(null)
const notesPanelRef = ref<InstanceType<typeof NotesPanel> | null>(null)

// ─── Composable 编排 ───
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
)

const onboarding = useOnboarding()
const projOnboarding = useProjectOnboarding()

// ─── 解构到模板作用域 ───
const {
  task, activeTab, TABS, switchTab, dotClass,
  chapters, activeChapterIdx, scrollToChapter, allChaptersVisible,
  visibleChapterIndices, expandedChapters, summaryExpandedChapters,
  transcriptItems, flatTranscript, summaryMd, todos, notesContent, notesSaved,
  showArchiveDialog, onArchive, showDeleteDialog, metaDuration, metaDateShort,
  projects, showProjectDropdown, onSelectProject, openDatePicker, breadcrumbTitle,
  player, seekAudio, onCopy, onExport, onFullscreen, speakers, audioUrl,
  toggleChapterExpand, toggleSummaryChapter, toggleChapterTranscript, showAllChapters,
} = data
const {
  showBindingBar, bindingLegend, unboundCount, currentBindingMapping,
  bindingDropdown, dropdownSpeakers, openBindingDropdown,
  skipMapping, confirmMapping, bindingBarHidden, selectBinding, createAndBind, onDropdownKeydown, canBind,
} = binding
const {
  speakerPanelVisible, speakerPanelSearch, searchExpanded, speakerFilterSet,
  focusSpeaker, focusLineIdx, locateSpeakerId,
  panelSpeakerList, panelTotalDuration, panelTotalTurns,
  toggleSearch, onSearchBlur, toggleSpeakerFilter, clearSpeakerFilter, navFocusLine, toggleLocateSpeaker,
} = panel
const { playingLineIdx, followPlayback, playingSpeakerId, toggleAudio, resumeFollowPlayback } = playback
const {
  showAddForm, newTodoText, newTodoAssignee,
  onNotesChange, onSummaryChange, onToggleTodo, onAddTodo, onDeleteTodo, insertMd,
} = notes
const { showOnboarding, demoLines, hasSeenOnboarding, openOnboarding, closeOnboarding } = onboarding
const { showProjectOnboarding, connected: projConnected, openOnboarding: openProjOnboarding, closeOnboarding: closeProjOnboarding } = projOnboarding

// ─── 首次进入时自动弹出说话人关联引导弹窗 ───
watch(showBindingBar, (visible) => {
  if (visible && !hasSeenOnboarding.value) openOnboarding()
}, { immediate: true })

// ─── 更多菜单 ──
const genMoreBtn = ref<HTMLElement | null>(null)
const genMoreDropdown = ref<HTMLElement | null>(null)
const { visible: showMoreMenu, toggle: toggleGenMore, close: closeGenMore } = usePopMenu(genMoreDropdown, genMoreBtn)

// ─── 工具栏操作 ───
function onEditSummary() { closeGenMore(); data.switchTab('summary') }
async function onRetrySummary() { closeGenMore(); await retrySummary(data.taskId); await taskStore.loadTasks() }
async function onRetranscribe() { closeGenMore(); await retranscribe(data.taskId); router.push({ name: 'generating', params: { taskId: data.taskId } }) }
async function onDelete() {
  closeGenMore()
  data.showDeleteDialog.value = true
}
async function onDeleteConfirm() {
  data.showDeleteDialog.value = false
  await deleteTask(data.taskId); await taskStore.loadTasks(); router.push('/')
}
function onArchiveConfirm() { closeGenMore(); data.showArchiveDialog.value = true }

function onSpeakerLabelClick(e: MouseEvent, speakerId: number) {
  if (binding.canBind.value) binding.openBindingDropdown(e, speakerId)
  else panel.toggleLocateSpeaker(speakerId)
}

function onSelectionAction(action: string, text: string, source: string, blockIndex: number) {
  if (action === 'rewrite') {
    data.startRewrite(text, source, blockIndex); data.setQuote(text, source, blockIndex)
    window.dispatchEvent(new CustomEvent('quote-to-ai', { detail: { action: t('generating.ai_actions.rewrite') } }))
  } else if (action === 'summarize') {
    data.setQuote(text, source, blockIndex)
    window.dispatchEvent(new CustomEvent('quote-to-ai', { detail: { action: t('generating.ai_actions.summarize') } }))
  } else if (action === 'extract-todo') {
    data.setQuote(text, source, blockIndex)
    window.dispatchEvent(new CustomEvent('quote-to-ai', { detail: { action: t('generating.ai_actions.extract_todo') } }))
  }
}

function locateTodoSource(_todo: any) { switchTab('transcript') }

/** 切换所有章节原文显隐（导航栏眼睛按钮） */
function toggleAllTranscript() {
  if (allChaptersVisible) visibleChapterIndices.clear()
  else chapters.value.forEach((_: any, idx: number) => visibleChapterIndices.add(idx))
}

/** 点击原文时间戳跳转播放；拖选文本时让位给划词工具栏 */
function seekFromTranscriptClick(ms: number) {
  const sel = window.getSelection()
  if (sel && !sel.isCollapsed && sel.toString().trim()) return
  player.seekToMs(ms)
}

// ─── 计算属性（组合 composable 输出） ───
const speakerStats = computed(() => data.computeSpeakerStats(data.speakers.value, binding.currentBindingMapping))
const breadcrumbs = computed(() => data.computeBreadcrumbs(data.projects.value))
const currentProjectName = computed(() => data.computeCurrentProjectName(data.projects.value))
const speakerNames = computed(() => {
  const m = data.task.value?.speaker_mapping
  return m ? Object.values(m).filter(Boolean) : []
})

// ─── 生命周期 ───
onMounted(async () => {
  // 任务数据可能尚未加载（刷新页面时 store 为空），用 watch 等待任务就绪后初始化绑定映射
  const stopWatch = watch(() => data.task.value, (t) => {
    if (t) { binding.initBindingMapping(); stopWatch() }
  }, { immediate: true })
  document.addEventListener('click', panel.onDocClickCloseSearch)
  document.addEventListener('click', binding.onDocClickForDropdown)

  // 章节滚动追踪 + 用户主动滚动时停止播放跟随
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




