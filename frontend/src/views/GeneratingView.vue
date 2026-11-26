<template>
  <div class="gen-view">
    <FailurePage
      v-if="isFailed"
      :failure-info="failureInfo"
      :task="task"
      :can-fallback-cloud="canFallbackCloud"
      :cloud-fallback-blocked="cloudFallbackBlocked"
      v-model:show-cloud-fallback-confirm="showCloudFallbackConfirm"
      @retry="onRetryFromFailure"
      @back-to-library="router.push('/library')"
    />

    <!-- 正常态：原有工具栏 + 元信息 + 说话人区 + Tab + 内容区 / Normal state: original toolbar + meta + speaker zone + tabs + content -->
    <template v-else>
      <GenToolbar
        ref="genToolbarRef"
        :breadcrumbs="breadcrumbs"
        :breadcrumb-display-title="breadcrumbDisplayTitle"
        :is-title-renaming="isTitleRenaming"
        :ides="ws.ides.value"
        v-model:ide-menu-open="ideMenuOpen"
        v-model:ide-scope="ideScope"
        :ide-scopes="ideScopes"
        :opening-ide-id="ws.openingIdeId.value"
        :has-project="!!task?.project_id"
        :is-fullscreen="isFullscreen"
        :sync-status="syncStatus"
        :is-syncing="isSyncing"
        :show-more-menu="showMoreMenu"
        :more-trigger-attrs="genMoreTriggerAttrs"
        :more-menu-attrs="genMoreMenuAttrs"
        :has-summary="!!task?.summary"
        :is-archived="data.isArchived.value"
        @navigate="router.push($event)"
        @rename-task="onRenameTask"
        @toggle-ide="toggleIdeMenu"
        @continue-in-ide="onContinueInIde"
        @copy="onCopy"
        @export="onExport"
        @fullscreen="onFullscreen"
        @sync-kb="onSyncToKb"
        @toggle-more="toggleGenMore"
        @more-enter="onGenMoreEnter"
        @more-leave="onGenMoreLeave"
        @copy-title="onCopyTitle"
        @copy-summary="onCopySummary"
        @retry-summary="onRetrySummary"
        @retranscribe="onRetranscribe"
        @archive="onArchiveConfirm"
        @delete="onDelete"
      />

      <GenMetaBar
        ref="genMetaBarRef"
        :meta-duration="metaDuration"
        :speaker-count="speakerCount"
        :meta-date-short="metaDateShort"
        :has-project="!!task?.project_id"
        :current-project-name="currentProjectName"
        :show-project-dropdown="showProjectDropdown"
        :projects="projects"
        :filtered-projects="filteredProjects"
        :selected-project-id="task?.project_id || ''"
        v-model:kb-search-query="kbSearchQuery"
        :show-kb-create-input="showKbCreateInput"
        v-model:kb-create-name="kbCreateName"
        @open-date-picker="openDatePicker"
        @toggle-project-dropdown="showProjectDropdown = !showProjectDropdown"
        @select-project="onSelectProject"
        @create-and-link-kb="createAndLinkKb"
        @cancel-kb-create="showKbCreateInput = false; kbCreateName = ''"
        @open-kb-create="showKbCreateInput = true; $nextTick(() => genMetaBarRef?.kbCreateInputRef?.focus())"
        @open-kb-create-from-search="kbCreateName = kbSearchQuery.trim(); showKbCreateInput = true; $nextTick(() => genMetaBarRef?.kbCreateInputRef?.focus())"
      />

      <!-- 人员栏（渐进式压缩：说话人 + 参会人合并） / Personnel bar (progressive compression: speakers + roster merged) -->
      <GeneratingSpeakerZone
        :mode="speakerZoneMode"
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
        @run-voiceprint="handleRunVoiceprint"
        @apply-voiceprint="onVoiceprintApply"
        @dismiss-voiceprint="handleVoiceprintDismiss"
      />

      <GenTabs
        ref="genTabsRef"
        :tabs="TABS"
        :active-tab="activeTab"
        :tab-dot-class="tabDotClass"
        :layer-view="layerView"
        :cleanup-available="cleanupAvailable"
        :show-layer-picker="showLayerPicker"
        :layer-picker-trigger-attrs="layerPickerTriggerAttrs"
        :layer-picker-menu-attrs="layerPickerMenuAttrs"
        @switch-tab="switchTab"
        @tab-hover="onTabHover"
        @toggle-layer-picker="toggleLayerPicker"
        @select-layer="selectLayer"
      />

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
          :decisions-count="decisions.length"
          :decisions-done-count="decisions.filter(x => x.done).length"
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
          :visible="activeTab === 'decisions'"
          :task-id="data.taskId"
          :decisions="decisions"
          :anchor-decision-id="anchorDecisionId"
          :from-evolution="route.query.from === 'evolution'"
          @delete="onDeleteDecision"
          @update="onEditDecision"
          @status-change="onStatusChange"
          @add="showAddDecisionDialog = true"
        />

        <!-- 洞察台（会后） / Insight Deck：不再区分板/卡视图，统一为 AI 共创的 HTML 产物呈现 -->
        <div v-show="activeTab === 'insights'" class="gen-insights-wrap">
          <InsightBoard
            :artifact="board"
            :loading="boardLoading"
            :boards="boards"
            :active-board-id="activeBoardId"
            @seek="onInsightSeek"
            @refresh="loadBoardData"
            @co-create="onBoardCoCreate"
            @co-create-section="onBoardCoCreateSection"
            @switch-board="onBoardSwitch"
            @create-board="onBoardCreate"
            @open-in-browser="onBoardOpenInBrowser"
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
import { fetchSyncStatus, syncTaskToProject, fetchTask } from '@/api/tasks'
import type { SyncStatus } from '@/api/tasks'
import { usePopMenu } from '@/composables/usePopMenu'
import { useDropdownPopup } from '@/composables/useDropdownPopup'
import type { LayerView } from '@/utils/transcriptLayers'
import SelectionToolbar from '@/components/SelectionToolbar.vue'
import InlineEditInput from '@/components/InlineEditInput.vue'
import TranscriptPanel from './generating/TranscriptPanel.vue'
import SummaryPanel from './generating/SummaryPanel.vue'
import NotesPanel from './generating/NotesPanel.vue'
import DecisionFlowPanel from './generating/DecisionFlowPanel.vue'
import FailurePage from './generating/FailurePage.vue'
import GenToolbar from './generating/GenToolbar.vue'
import GenMetaBar from './generating/GenMetaBar.vue'
import GenTabs from './generating/GenTabs.vue'
import { parseAnchorDecisionId } from './decisionEvolutionNav'
import InsightBoard from './generating/InsightBoard.vue'
import { onTaskWritten } from '@/composables/useTaskWrites'
import GeneratingSpeakerZone from './generating/GeneratingSpeakerZone.vue'
import ArchiveDialog from './generating/ArchiveDialog.vue'
import DeleteDialog from './generating/DeleteDialog.vue'
import AddDecisionDialog from './decisions/AddDecisionDialog.vue'
import type { DecisionCreatePayload } from '@/api/notes'
import { extractErrorMessage } from '@/api/client'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { showToast } from '@/composables/useToast'
import { useGeneratingData } from '@/composables/useGeneratingData'
import { useSpeakerBinding } from '@/composables/useSpeakerBinding'
import { useSpeakerPanel } from '@/composables/useSpeakerPanel'
import { usePlaybackFollow } from '@/composables/usePlaybackFollow'
import { useNotesAndDecisions } from '@/composables/useNotesAndDecisions'
import { useInlineEdit } from '@/composables/useInlineEdit'
import { useSummaryProposal } from '@/composables/useSummaryProposal'
import { useNotesProposal } from '@/composables/useNotesProposal'
import { useAiInsights } from '@/composables/useAiInsights'
import { useMeetingRoster } from '@/composables/useMeetingRoster'
import { useTitleRename } from '@/composables/useTitleRename'
import { useInsightBoardPolling } from '@/composables/useInsightBoardPolling'
import { useIdeLauncher } from '@/composables/useIdeLauncher'
import { useVoiceprintMatch } from '@/composables/useVoiceprintMatch'
import { useTextCorrection } from '@/composables/useTextCorrection'
import { useGenActions } from '@/composables/useGenActions'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const taskStore = useTaskStore()

// ─── 模板 refs / Template refs ───
const transcriptPanelRef = ref<InstanceType<typeof TranscriptPanel> | null>(null)
const summaryPanelRef = ref<InstanceType<typeof SummaryPanel> | null>(null)
const notesPanelRef = ref<InstanceType<typeof NotesPanel> | null>(null)
const genToolbarRef = ref<InstanceType<typeof GenToolbar> | null>(null)
const genMetaBarRef = ref<InstanceType<typeof GenMetaBar> | null>(null)
const genTabsRef = ref<InstanceType<typeof GenTabs> | null>(null)
const kbDropdownRef = computed(() => genMetaBarRef.value?.kbDropdownRef ?? null)
const kbSearchInputRef = computed(() => genMetaBarRef.value?.kbSearchInputRef ?? null)

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
  data.activeTab, data.switchTab,
)

const notes = useNotesAndDecisions(
  data.taskId, data.notesContent, data.notesSaved, data.summaryMd,
  data.decisions, data.activeTab, data.task,
  loadSyncStatus, // 内容修改后自动刷新同步状态 / Refresh sync status after content modification
)

const inlineEdit = useInlineEdit()
/** 纪要改写提案（原位 diff 预览 Layer 1）：共享单例状态，接受/拒绝由 SummaryPanel 操作条发起 */
const sp = useSummaryProposal()
// 随记改写提案（propose_notes）：与纪要同一机制，在随记 Tab 原位预览，用户接受才落盘
const np = useNotesProposal()
/** 洞察消息的跨组件共享状态（仅用于修正后强制重拉，不让陈内存写回覆盖新落盘的文本） */
const insights = useAiInsights()
const rosterComposable = useMeetingRoster(data.taskId, data.task)

// ─── 新提取的 Composables ───
const ide = useIdeLauncher(
  data.taskId,
  () => genToolbarRef.value?.genIdeBtn ?? null,
  () => genToolbarRef.value?.genIdeMenu ?? null,
)
const { ws, ideMenuOpen, ideScope, ideScopes, toggleIdeMenu, onContinueInIde, onIdeDocMouseDown, onIdeResize } = ide

const boardPolling = useInsightBoardPolling({
  taskId: data.taskId,
  activeTab: data.activeTab,
  dotClass: (tab) => data.dotClass(tab),
})
const {
  board, boards, activeBoardId, boardLoading, loadBoardData,
  onTabHover, tabDotClass, onBoardSwitch, onBoardCreate, onBoardOpenInBrowser,
} = boardPolling

const voiceprint = useVoiceprintMatch(
  data.taskId,
  data.task,
  () => canBind.value && flatTranscript.value.length > 0,
  async (speakerId: number, uuid: string) => { await selectBinding(speakerId, uuid) },
)
const { voiceprintRunning, visibleVoiceprintItems, onVoiceprintApply } = voiceprint

async function handleRunVoiceprint() {
  const res = await voiceprint.runVoiceprint()
  if (res) {
    taskStore.patchTaskLocal(data.taskId, {
      voiceprint_match: res.results,
      voiceprint_auto_mapping: res.auto_mapping,
      voiceprint_dismissed: [],
    })
  }
}

async function handleVoiceprintDismiss(speakerId: number) {
  const { dismissedIds, undoBind } = await voiceprint.onVoiceprintDismiss(speakerId)
  if (undoBind) await selectBinding(speakerId, '')
  taskStore.patchTaskLocal(data.taskId, { voiceprint_dismissed: dismissedIds })
}

const textCorrection = useTextCorrection(data.taskId)
const { onSelectionAction } = textCorrection

const genActions = useGenActions({
  taskId: data.taskId,
  showDeleteDialog: data.showDeleteDialog,
  showArchiveDialog: data.showArchiveDialog,
  onArchive: data.onArchive,
  isArchived: data.isArchived,
  startPolling: data.startPolling,
  summaryMd: data.summaryMd,
})
const {
  showCloudFallbackConfirm,
  onRetrySummary, onRetryFromFailure, onCloudFallbackConfirm,
  onDelete, onDeleteConfirm, onArchiveConfirm, onArchiveDone, onRetranscribe,
} = genActions

// ─── 解构到模板作用域 / Destructure to template scope ───
const {
  task, activeTab, TABS, switchTab,
  chapters, activeChapterIdx, scrollToChapter, allChaptersVisible,
  visibleChapterIndices, expandedChapters, summaryExpandedChapters,
  transcriptItems, flatTranscript, summaryMd, decisions, notesContent, notesSaved,
  showArchiveDialog, showDeleteDialog, metaDuration, metaDateShort,
  projects, showProjectDropdown, onSelectProject, openDatePicker, breadcrumbTitle,
  kbSearchQuery, filteredProjects, showKbCreateInput, kbCreateName, createAndLinkKb,
  player, seekAudio, onCopy, onExport, onFullscreen, isFullscreen, speakers, audioUrl,
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
  onNotesChange, onSummaryChange, onAddDecision, onDeleteDecision, onEditDecision, onStatusChange, loadDecisions, loadNotes,
} = notes

// ─── textCorrection 重载器（依赖 notes 的 loadDecisions/loadNotes，故延迟到解构后接线） ───
textCorrection.configure({
  reloadDecision: loadDecisions,
  reloadNotes: loadNotes,
  reloadInsights: insights.reloadTaskMessages,
  reloadBoard: () => { boardPolling.boardDirty.value = false; if (boardPolling.boardFetched.value) boardPolling.loadBoardData() },
})

// ─── 添加决策：复用决策中心「手动补录决策」弹层（DC-UNIFY-01 样式/数据统一） ───
const showAddDecisionDialog = ref(false)
const addDecisionDialogRef = ref<InstanceType<typeof AddDecisionDialog> | null>(null)
async function onAddDecisionSubmit(taskId: string, payload: DecisionCreatePayload) {
  try {
    await onAddDecision(payload, taskId)
    showToast(t('decisions.toast_add_ok'), 'success')
    showAddDecisionDialog.value = false
    // 重拉保证与后端权威数据一致（owner 解析、归属其它会议的节点不干扰本地列表）
    void loadDecisions()
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

// ─── 落板信号 + 生命周期监听（复用 composable 之外的 offTaskWritten） ───
let offTaskWritten: (() => void) | null = null

/** 共创起跳：展开 AI 面板并预填修订请求到输入框（不自动发送）；coCreate 标记使智能体轮自动升可写档以落盘 */
function onBoardCoCreate() {
  window.dispatchEvent(new CustomEvent('quote-to-ai', {
    detail: { prefill: t('generating.insights.board.co_create_msg', { board_id: activeBoardId.value }), coCreate: true },
  }))
}

/** 单节共创起跳：预填节锈点 id与标题的定向修订请求，引导 AI 用 revise_insight_board_section 只改这一节 */
function onBoardCoCreateSection(sec: { id: string; title: string }) {
  const label = sec.title || sec.id
  const prefill = t('generating.insights.board.co_create_section_msg', {
    title: label, id: sec.id, board_id: activeBoardId.value,
  })
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
const genMoreBtn = computed(() => genToolbarRef.value?.genMoreBtn ?? null)
const genMoreDropdown = computed(() => genToolbarRef.value?.genMoreDropdown ?? null)
const { visible: showMoreMenu, toggle: toggleGenMore, close: closeGenMore, triggerAttrs: genMoreTriggerAttrs, menuAttrs: genMoreMenuAttrs } = usePopMenu(genMoreDropdown, genMoreBtn)
let genMoreHoverTimer: ReturnType<typeof setTimeout> | null = null
function onGenMoreEnter() { if (genMoreHoverTimer) { clearTimeout(genMoreHoverTimer); genMoreHoverTimer = null } }
function onGenMoreLeave() { genMoreHoverTimer = setTimeout(() => closeGenMore(), 150) }

// ─── 原文三层视图下拉（tab 栏右侧；真源在此，TranscriptPanel prop 消费）/ Transcript layer dropdown (tab-bar right; source of truth here) ──
const layerView = ref<LayerView>('clean')
const cleanupAvailable = computed(() => task.value?.transcript_layers?.cleanup === true)
const layerPickerBtn = computed(() => genTabsRef.value?.layerPickerBtn ?? null)
const layerPickerMenu = computed(() => genTabsRef.value?.layerPickerMenu ?? null)
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

/** 重命名 / Rename（内联编辑：顶栏标题原位变输入框，不再用浏览器原生 prompt） */
const titleRename = useTitleRename()
/** 面包屑标题实时跟随未保存的草稿 / Breadcrumb echoes the unsaved draft */
const breadcrumbDisplayTitle = computed(() => titleRename.displayTitle(data.taskId, breadcrumbTitle.value))
const isTitleRenaming = computed(() => titleRename.isRenaming(data.taskId))

function onRenameTask() {
  closeGenMore()
  if (isTitleRenaming.value && titleRename.owns('topbar', data.taskId)) return
  const cur = task.value
  titleRename.start(data.taskId, cur?.title || cur?.audio_name || '', 'topbar')
}

/**
 * 决策中心演变链跳转锚点：?tab=decisions&decision=<id>&from=evolution
 * 切到决策面板后由 DecisionFlowPanel 自行展开闭档组、滚动高亮并显示来源横幅。
 */
const anchorDecisionId = computed(() => parseAnchorDecisionId(route.query))

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

// ─── 行间编辑 / Inline edit ───
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

  // 洞察板轮询：绑定信号 + 可见性事件（dispose 时自动清理）
  boardPolling.bindSignals()
  boardPolling.bindVisibilityChange()

  // IDE 联动：探测已安装 IDE，并接管下拉的外部点击/缩放重定位
  void ide.loadIdes()
  document.addEventListener('mousedown', onIdeDocMouseDown, true)
  window.addEventListener('resize', onIdeResize)

  // AI 会话写回任务数据（决策节点/纪要/注入）→ 呈现侧即时对齐（§5.4）
  offTaskWritten = onTaskWritten(async ({ domains }) => {
    const all = !domains || domains.length === 0
    try {
      const updated = await fetchTask(data.taskId)
      taskStore.patchTaskLocal(data.taskId, updated)
    } catch { /* 保留旧视图，下次轮询仍会重拉 */ }
    if (all || domains?.includes('decisions')) void data.loadDecisions()
    if (all || domains?.includes('notes')) void loadNotes()
    void loadSyncStatus()
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
  boardPolling.dispose()
  document.removeEventListener('mousedown', onIdeDocMouseDown, true)
  window.removeEventListener('resize', onIdeResize)
  offTaskWritten?.()
  offTaskWritten = null
  document.removeEventListener('click', panel.onDocClickCloseSearch)
  document.removeEventListener('click', binding.onDocClickForDropdown)
})
</script>




