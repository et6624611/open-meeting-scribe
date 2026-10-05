<template>
  <div class="proj-page">
    <Transition name="fade" mode="out-in">
    <!-- ═══ 列表视图 / List view ═══ -->
    <div v-if="!selectedProject" key="list">
      <div class="main-head">
        <div class="title-row">
          <h1>{{ t('projects.title') }}</h1>
          <span class="page-count">{{ t('projects.count', { count: projects.length }) }}</span>
        </div>
      </div>
      <!-- 统一输入框 / Unified input -->
      <div class="proj-unified">
        <div class="proj-unified-field">
          <svg class="proj-unified-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <template v-if="showCreateHint">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </template>
            <template v-else>
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </template>
          </svg>
          <input
            v-model="inputText"
            class="proj-unified-input"
            type="text"
            :placeholder="t('projects.unified_placeholder')"
            @keyup.enter="onUnifiedEnter"
          />
        </div>
      </div>
      <!-- 知识库列表 / Project list -->
      <div v-if="filteredProjects.length > 0 || showCreateHint" class="proj-list">
        <div v-for="proj in filteredProjects" :key="proj.id" class="proj-card" @click="openDetail(proj)">
          <div class="proj-card-header">
            <h3 class="proj-card-name">{{ proj.name }}</h3>
            <div class="proj-card-actions" @click.stop>
              <button class="proj-card-action" :title="t('projects.open_folder')" @click="onOpenFolder(proj)" v-if="proj.folders?.length">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
              </button>
              <button class="proj-card-action danger" @click="confirmDelete(proj)" :title="t('common.action.delete')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          </div>
          <div class="proj-card-meta">
            <span>{{ t('projects.folders_count', { count: proj.folders?.length || 0 }) }}</span>
            <span v-if="proj.file_count"> · {{ t('projects.stat_files') }}: {{ proj.file_count }}</span>
          </div>
        </div>
        <!-- 新建提示 / Create new hint -->
        <div v-if="showCreateHint" class="proj-create-hint" @click="onCreate">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>{{ t('projects.create_hint', { name: inputText.trim() }) }}</span>
        </div>
      </div>
      <div v-else-if="!inputText.trim()" class="empty-state">{{ t('projects.empty') }}</div>
    </div>

    <!-- ═══ 详情视图 / Detail view ═══ -->
    <div v-else key="detail" class="proj-detail">
      <button class="proj-back-btn" @click="backToList">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m15 18-6-6 6-6"/></svg>
        {{ t('projects.back_list') }}
      </button>

      <div class="proj-detail-head">
        <div class="proj-detail-left">
          <div class="proj-detail-name" @click="startRename">
            <span v-if="!isRenaming" class="proj-name-clickable">{{ selectedProject.name }}</span>
            <input v-else ref="renameInputRef" v-model="renameValue" class="proj-inline-edit" @keyup.enter="saveRename" @keydown.escape.prevent="cancelRename" @blur="saveRename" />
          </div>
          <div class="proj-index-status" :class="indexStatusClass">
            {{ indexStatusText }}
          </div>
        </div>
        <div class="proj-detail-actions">
          <button class="btn btn-secondary btn-sm" @click="onRebuildIndex" :disabled="scanning">
            {{ scanning ? t('projects.rebuilding') : t('projects.rebuild_index') }}
          </button>
          <button class="btn btn-secondary btn-sm" @click="onTriggerSync" :disabled="syncing">
            {{ syncing ? t('projects.syncing') : t('projects.sync_trigger') }}
          </button>
          <button class="btn btn-secondary btn-sm" style="color:var(--error)" @click="confirmDelete(selectedProject)">
            {{ t('common.action.delete') }}
          </button>
        </div>
      </div>

      <!-- 统计卡片 / Stat cards -->
      <div class="proj-stat-cards">
        <div class="proj-stat-card">
          <div class="label">{{ t('projects.stat_files') }}</div>
          <div class="value">{{ detailData?.file_count || 0 }}</div>
          <div class="sub">{{ t('projects.stat_files_unit') }}</div>
        </div>
        <div class="proj-stat-card">
          <div class="label">{{ t('projects.stat_meetings') }}</div>
          <div class="value">{{ detailData?.meetings?.length || 0 }}</div>
          <div class="sub">{{ t('projects.stat_meetings_unit') }}</div>
        </div>
        <div class="proj-stat-card">
          <div class="label">{{ t('projects.stat_folders') }}</div>
          <div class="value">{{ selectedProject.folders?.length || 0 }}</div>
          <div class="sub">{{ t('projects.stat_folders_unit') }}</div>
        </div>
      </div>

      <!-- 文件夹管理 / Folder management -->
      <div class="proj-folders-section">
        <h3 class="proj-section-title">{{ t('projects.stat_folders') }}</h3>
        <div v-if="selectedProject.folders?.length" class="proj-folders-list">
          <div v-for="folder in selectedProject.folders" :key="folder.path" class="proj-folder-row">
            <div class="proj-folder-info">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
              <span class="proj-folder-path">{{ folder.path }}</span>
            </div>
            <div class="proj-folder-controls">
              <!-- 同步开关 / Sync toggle -->
              <label class="proj-sync-toggle">
                <span class="proj-sync-label">{{ t('projects.sync_enabled') }}</span>
                <div class="wm-toggle-wrap">
                  <div
                    class="wm-toggle"
                    :class="{ 'is-on': folder.sync_enabled }"
                    role="switch"
                    :aria-checked="folder.sync_enabled"
                    tabindex="0"
                    @click="toggleSync(folder)"
                    @keydown.enter.prevent="toggleSync(folder)"
                    @keydown.space.prevent="toggleSync(folder)"
                  ></div>
                </div>
              </label>
              <button class="proj-folder-btn" :title="t('projects.open_folder')" @click="onOpenFolderByPath(folder.path)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              </button>
              <button class="proj-folder-btn danger" :title="t('projects.remove_folder')" @click="onRemoveFolder(selectedProject.id, folder.path)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          </div>
        </div>
        <button class="btn btn-secondary btn-sm" @click="showFolderBrowser = true">
          {{ t('projects.add_folder') }}
        </button>
      </div>

      <!-- Tab 切换 / Tab switcher -->
      <div class="proj-tabs">
        <button class="proj-tab" :class="{ 'is-active': activeTab === 'meetings' }" @click="activeTab = 'meetings'">
          {{ t('projects.meetings_tab') }} <span class="proj-tab-count">{{ detailData?.meetings?.length || 0 }}</span>
        </button>
        <button class="proj-tab" :class="{ 'is-active': activeTab === 'files' }" @click="switchToFiles">
          {{ t('projects.files_tab') }} <span class="proj-tab-count">{{ indexedFiles.length }}</span>
        </button>
        <button class="proj-tab" :class="{ 'is-active': activeTab === 'search' }" @click="activeTab = 'search'">
          {{ t('projects.search_tab') }}
        </button>
      </div>

      <!-- 关联会议 / Meetings tab -->
      <div v-show="activeTab === 'meetings'" class="proj-tab-panel">
        <div v-if="!detailData?.meetings?.length" class="proj-empty">{{ t('projects.meetings_empty') }}</div>
        <div v-for="m in detailData?.meetings" :key="m.task_id" class="proj-meeting-card" @click="openTask(m.task_id)">
          <div class="pmc-head">
            <span class="pmc-title">{{ m.title }}</span>
            <span class="pmc-date">{{ formatDate(m.meeting_date || m.created_at) }}</span>
          </div>
          <div class="pmc-meta">
            <DurationDial v-if="m.audio_duration" :seconds="m.audio_duration" />
            <span v-if="m.speaker_count">{{ m.speaker_count }} {{ t('projects.meeting_speakers_unit') }}</span>
            <span v-if="m.status !== 'completed'" class="pmc-status" :class="'status-' + m.status">{{ formatStatus(m.status) }}</span>
          </div>
        </div>
      </div>

      <!-- 索引文件 / Files tab -->
      <div v-show="activeTab === 'files'" class="proj-tab-panel">
        <div v-if="filesLoading" class="proj-loading"><div class="proj-spinner"></div></div>
        <div v-else-if="indexedFiles.length === 0" class="proj-empty">{{ t('projects.files_empty') }}</div>
        <table v-else class="proj-files-table">
          <thead>
            <tr>
              <th>{{ t('projects.file_name') }}</th>
              <th style="width:60px">{{ t('projects.file_type') }}</th>
              <th style="width:80px">{{ t('projects.file_size') }}</th>
              <th style="width:140px">{{ t('projects.file_modified') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in indexedFiles" :key="f.path">
              <td class="file-name-cell">
                <span class="file-title">{{ f.title || f.name }}</span>
                <span v-if="f.relative_path" class="file-rel-path">{{ f.relative_path }}</span>
              </td>
              <td><span class="file-type-badge">{{ f.type }}</span></td>
              <td class="file-size">{{ formatSize(f.size) }}</td>
              <td class="file-date">{{ formatDate(f.modified_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 搜索 / Search tab -->
      <div v-show="activeTab === 'search'" class="proj-tab-panel">
        <div class="proj-search-bar">
          <input
            v-model="searchQuery"
            class="proj-search-input"
            type="text"
            :placeholder="t('projects.search_placeholder')"
            @keyup.enter="onSearch"
          />
          <button class="btn btn-secondary btn-sm" @click="onSearch" :disabled="!searchQuery.trim()">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          </button>
        </div>
        <div v-if="searchLoading" class="proj-loading"><div class="proj-spinner"></div></div>
        <div v-else-if="searchResults.length > 0" class="proj-search-results">
          <div class="proj-search-summary">{{ t('projects.search_results', { count: searchResults.length }) }}</div>
          <div v-for="f in searchResults" :key="f.path" class="proj-search-item">
            <span class="search-item-title">{{ f.title || f.name }}</span>
            <span class="search-item-path">{{ f.relative_path }}</span>
          </div>
        </div>
        <div v-else-if="searchDone" class="proj-empty">{{ t('projects.search_empty') }}</div>
      </div>
    </div>
    </Transition>

    <!-- 确认对话框 / Confirmation dialog -->
    <Teleport to="body">
    <div v-if="showConfirmDialog" class="proj-dialog-overlay" @click.self="showConfirmDialog = false">
      <div class="proj-dialog">
        <h3>{{ confirmDialogTitle }}</h3>
        <p>{{ confirmDialogMsg }}</p>
        <div class="proj-dialog-actions">
          <button class="btn btn-secondary btn-sm" @click="showConfirmDialog = false">{{ t('common.action.cancel') }} <kbd>ESC</kbd></button>
          <button class="btn btn-secondary btn-sm danger-confirm" @click="onConfirmDelete">{{ t('common.action.delete') }}</button>
        </div>
      </div>
    </div>
    </Teleport>

    <!-- 文件夹选择器 / Folder browser -->
    <FolderBrowserDialog
      v-model="showFolderBrowser"
      @select="onFolderSelected"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  fetchProjects, fetchProjectDetail, createProject, updateProject, deleteProject,
  addFolder, removeFolder, updateFolderSync, triggerSync, triggerScan,
  getProjectFiles, searchProjectFiles, openFolderInFinder,
} from '@/api/projects'
import type { Project, ProjectDetail, ProjectFolder, IndexedFile } from '@/api/projects'
import { showToast } from '@/composables/useToast'
import { useEscClose } from '@/composables/useEscClose'
import { usePageBack } from '@/composables/usePageBack'
import DurationDial from '@/components/common/DurationDial.vue'
import FolderBrowserDialog from './projects/FolderBrowserDialog.vue'

const { t } = useI18n()
const router = useRouter()

// ─── 列表状态 / List state ───
const projects = ref<Project[]>([])
const inputText = ref('')

// ─── 详情状态 / Detail state ───
const selectedProject = ref<Project | null>(null)
const detailData = ref<ProjectDetail | null>(null)
const activeTab = ref<'meetings' | 'files' | 'search'>('meetings')
const indexedFiles = ref<IndexedFile[]>([])
const filesLoading = ref(false)
const searchQuery = ref('')
const searchResults = ref<IndexedFile[]>([])
const searchLoading = ref(false)
const searchDone = ref(false)
const scanning = ref(false)
const syncing = ref(false)

// ─── 重命名 / Rename ───
const isRenaming = ref(false)
const renameValue = ref('')
const renameInputRef = ref<HTMLInputElement | null>(null)

// ─── 确认对话框 / Confirmation dialog ───
const showConfirmDialog = ref(false)
const confirmDialogTitle = ref('')
const confirmDialogMsg = ref('')
let confirmCallback: (() => void) | null = null
// 直接传入响应式 ref；之前传 ref(showConfirmDialog.value) 仅快照初始值（永远 false）导致 ESC 失效
// Pass the reactive ref directly; the previous ref(showConfirmDialog.value) only snapshotted the initial value (always false), breaking ESC
useEscClose(showConfirmDialog, () => { showConfirmDialog.value = false })

// ESC 返回：详情页先回到列表，列表页再路由返回 / ESC back: detail view returns to list first, list view then navigates back
usePageBack({ intercept: () => { if (selectedProject.value) { backToList(); return true } return false } })

// ─── 文件夹选择器 / Folder browser ───
const showFolderBrowser = ref(false)

// ─── 计算属性 / Computed ───
const filteredProjects = computed(() => {
  const q = inputText.value.trim().toLowerCase()
  if (!q) return projects.value
  return projects.value.filter(p => p.name.toLowerCase().includes(q))
})

const hasExactMatch = computed(() => {
  const q = inputText.value.trim().toLowerCase()
  if (!q) return true
  return projects.value.some(p => p.name.toLowerCase() === q)
})

const showCreateHint = computed(() => inputText.value.trim().length > 0 && !hasExactMatch.value)

const indexStatusClass = computed(() => {
  if (!detailData.value?.indexed_at) return 'never'
  return 'ok'
})

const indexStatusText = computed(() => {
  if (!detailData.value?.indexed_at) return t('projects.index_never')
  const time = formatDate(detailData.value.indexed_at)
  return t('projects.index_time', { time })
})

// ─── 数据加载 / Data loading ───
async function load() {
  projects.value = await fetchProjects()
}

async function loadDetail(projectId: string) {
  try {
    detailData.value = await fetchProjectDetail(projectId)
    // 同步更新 selectedProject 的文件夹数据
    if (detailData.value && selectedProject.value) {
      selectedProject.value.folders = detailData.value.folders
      selectedProject.value.file_count = detailData.value.file_count
      selectedProject.value.indexed_at = detailData.value.indexed_at
    }
  } catch {
    detailData.value = null
  }
}

// ─── 列表操作 / List operations ───
function onCreate() {
  const name = inputText.value.trim()
  if (!name) return
  createProject(name).then(() => {
    inputText.value = ''
    showToast(t('projects.rename_success', { name }), 'success')
    load()
  }).catch(e => {
    showToast(e?.response?.data?.detail || e?.message, 'error')
  })
}

function onUnifiedEnter() {
  if (showCreateHint.value) {
    onCreate()
  } else if (filteredProjects.value.length === 1) {
    openDetail(filteredProjects.value[0])
  }
}

function openDetail(proj: Project) {
  selectedProject.value = proj
  activeTab.value = 'meetings'
  indexedFiles.value = []
  searchResults.value = []
  searchDone.value = false
  loadDetail(proj.id)
}

function backToList() {
  selectedProject.value = null
  detailData.value = null
  load() // 刷新列表
}

// ─── 重命名 / Rename ───
function startRename() {
  if (!selectedProject.value) return
  renameValue.value = selectedProject.value.name
  isRenaming.value = true
  nextTick(() => renameInputRef.value?.focus())
}

async function saveRename() {
  if (!isRenaming.value || !selectedProject.value) return
  const name = renameValue.value.trim()
  if (!name || name === selectedProject.value.name) {
    cancelRename()
    return
  }
  try {
    await updateProject(selectedProject.value.id, name)
    selectedProject.value.name = name
    isRenaming.value = false
    showToast(t('projects.rename_success', { name }), 'success')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || e?.message, 'error')
  }
}

function cancelRename() {
  isRenaming.value = false
}

// ─── 删除 / Delete ───
function confirmDelete(proj: Project) {
  confirmDialogTitle.value = t('projects.confirm_delete_title')
  confirmDialogMsg.value = t('projects.confirm_delete_msg', { name: proj.name })
  confirmCallback = () => doDelete(proj.id)
  showConfirmDialog.value = true
}

async function doDelete(id: string) {
  try {
    await deleteProject(id)
    if (selectedProject.value?.id === id) {
      selectedProject.value = null
      detailData.value = null
    }
    await load()
    showToast(t('common.action.success'), 'success')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || e?.message, 'error')
  }
}

function onConfirmDelete() {
  showConfirmDialog.value = false
  confirmCallback?.()
  confirmCallback = null
}

// ─── 文件夹管理 / Folder management ───
function onFolderSelected(path: string) {
  if (!selectedProject.value) return
  const pid = selectedProject.value.id
  addFolder(pid, path).then(() => {
    loadDetail(pid)
  }).catch(e => {
    showToast(e?.response?.data?.detail || e?.message, 'error')
  })
}

async function onRemoveFolder(projectId: string, path: string) {
  try {
    await removeFolder(projectId, path)
    if (selectedProject.value) loadDetail(projectId)
  } catch (e: any) {
    showToast(e?.response?.data?.detail || e?.message, 'error')
  }
}

async function toggleSync(folder: ProjectFolder) {
  if (!selectedProject.value) return
  const newEnabled = !folder.sync_enabled
  try {
    await updateFolderSync(selectedProject.value.id, {
      path: folder.path,
      enabled: newEnabled,
    })
    folder.sync_enabled = newEnabled
  } catch (e: any) {
    showToast(e?.response?.data?.detail || e?.message, 'error')
  }
}

async function onOpenFolder(proj: Project) {
  if (proj.folders?.length) {
    onOpenFolderByPath(proj.folders[0].path)
  }
}

async function onOpenFolderByPath(path: string) {
  try {
    await openFolderInFinder(path)
  } catch (e: any) {
    showToast(e?.response?.data?.detail || e?.message, 'error')
  }
}

// ─── 索引管理 / Index management ───
async function onRebuildIndex() {
  if (!selectedProject.value) return
  scanning.value = true
  try {
    await triggerScan(selectedProject.value.id)
    // 等待几秒后刷新
    setTimeout(() => {
      loadDetail(selectedProject.value!.id)
      scanning.value = false
      showToast(t('projects.rebuild_success', { count: detailData.value?.file_count || 0 }), 'success')
    }, 2000)
  } catch (e: any) {
    scanning.value = false
    showToast(e?.response?.data?.detail || e?.message, 'error')
  }
}

async function onTriggerSync() {
  if (!selectedProject.value) return
  syncing.value = true
  try {
    const result = await triggerSync(selectedProject.value.id)
    showToast(t('projects.sync_success', { count: result.synced, files: result.files.length }), 'success')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || e?.message, 'error')
  } finally {
    syncing.value = false
  }
}

// ─── Tab 切换 / Tab switching ───
async function switchToFiles() {
  activeTab.value = 'files'
  if (indexedFiles.value.length === 0 && selectedProject.value) {
    filesLoading.value = true
    try {
      const result = await getProjectFiles(selectedProject.value.id)
      indexedFiles.value = result.files || []
    } catch {
      indexedFiles.value = []
    } finally {
      filesLoading.value = false
    }
  }
}

async function onSearch() {
  if (!searchQuery.value.trim() || !selectedProject.value) return
  searchLoading.value = true
  searchDone.value = false
  try {
    const result = await searchProjectFiles(selectedProject.value.id, searchQuery.value.trim())
    searchResults.value = result.results || []
    searchDone.value = true
  } catch {
    searchResults.value = []
    searchDone.value = true
  } finally {
    searchLoading.value = false
  }
}

function openTask(taskId: string) {
  router.push({ name: 'generating', params: { taskId } })
}

function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// 状态文案与 StartView / 侧栏 TaskCard 同源（common.status.*），避免裸英文枚举 / Status labels share the common.status.* keys (same source as StartView / sidebar TaskCard)
const statusLabels: Record<string, string> = {
  recording: t('common.status.recording'),
  paused: t('common.status.paused'),
  pending: t('common.status.pending'),
  processing: t('common.status.processing'),
  transcribing: t('common.status.transcribing'),
  summarizing: t('common.status.summarizing'),
  awaiting_mapping: t('common.status.awaiting_mapping'),
  failed: t('common.status.failed'),
}

function formatStatus(status: string): string {
  return statusLabels[status] || status
}

function formatSize(bytes: number) {
  if (!bytes) return '—'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

onMounted(load)
</script>

<style scoped>
.proj-page { padding: var(--s-5) var(--s-5) var(--s-6); }

/* 统一输入框 / Unified input */
.proj-unified { margin-bottom: 24px; }
.proj-unified-field { display: flex; align-items: center; gap: var(--s-2); position: relative; }
.proj-unified-icon { position: absolute; left: 10px; color: var(--subtle); pointer-events: none; transition: color 0.15s; }
.proj-unified-input { width: 100%; max-width: 400px; padding: 8px 10px 8px 32px; border: none; border-bottom: 1px solid var(--border); border-radius: 0; font-size: 14px; outline: none; background: transparent; color: var(--fg); transition: border-color 0.15s; }
.proj-unified-input:focus { border-bottom-color: var(--accent); box-shadow: 0 1px 0 0 var(--accent); }
.proj-unified-input:focus ~ .proj-unified-icon,
.proj-unified-field:focus-within .proj-unified-icon { color: var(--accent); }
.proj-unified-input::placeholder { color: var(--subtle); }

/* 列表 / List */
.proj-list { display: flex; flex-direction: column; }
.proj-card { padding: 16px; border-bottom: 1px solid var(--border); cursor: pointer; transition: background 0.12s; }
.proj-card:hover { background: var(--surface); }
.proj-card:hover .proj-card-actions { opacity: 1; }
.proj-card-header { display: flex; align-items: center; justify-content: space-between; }
.proj-card-name { font-size: 16px; font-weight: 600; margin: 0; }
.proj-card-actions { display: flex; gap: var(--s-1); opacity: 0; transition: opacity 0.12s; }
.proj-card-action { color: var(--subtle); background: none; border: none; cursor: pointer; padding: 4px; border-radius: var(--radius-sm); transition: all 0.12s; display: flex; }
.proj-card-action:hover { color: var(--fg); background: var(--surface-2); }
.proj-card-action.danger:hover { color: var(--error); background: oklch(95% 0.04 25); }
.proj-card-meta { font-size: 12px; color: var(--subtle); margin-top: 4px; }

/* 新建提示 / Create hint */
.proj-create-hint { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-3) var(--s-4); cursor: pointer; transition: background 0.12s; color: var(--accent); font-size: 13px; border-top: 1px dashed var(--border); }
.proj-create-hint:hover { background: var(--accent-soft); }
.empty-state { text-align: center; padding: 60px 0; color: var(--muted); font-size: 13px; }

/* 过渡动画 / Transition */
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* 详情视图 / Detail view */
.proj-back-btn { display: inline-flex; align-items: center; gap: var(--s-1); padding: var(--s-2) 0; margin-bottom: var(--s-4); color: var(--muted); font-size: 13px; background: none; border: none; cursor: pointer; transition: color 0.12s; }
.proj-back-btn:hover { color: var(--fg); }
.proj-detail-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--s-5); padding-bottom: var(--s-4); border-bottom: 1px solid var(--border); }
.proj-detail-left { min-width: 0; }
.proj-detail-name { font-size: 18px; font-weight: 600; display: flex; align-items: center; gap: var(--s-2); cursor: pointer; }
.proj-name-clickable { cursor: pointer; border-radius: var(--radius-sm); padding: 1px 4px; margin: -1px -4px; transition: background 0.12s; }
.proj-name-clickable:hover { background: var(--surface-2); }
.proj-inline-edit { font-size: 18px; font-weight: 600; border: 1px solid var(--accent); border-radius: var(--radius); padding: 1px 6px; background: var(--surface); color: var(--fg); outline: none; font-family: inherit; }
.proj-index-status { font-size: 12px; margin-top: 4px; }
.proj-index-status.never { color: var(--subtle); }
.proj-index-status.ok { color: var(--ok); }
.proj-index-status.stale { color: var(--warn); }
.proj-detail-actions { display: flex; gap: var(--s-2); flex-shrink: 0; }

/* 统计卡片 / Stat cards */
.proj-stat-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--s-3); margin-bottom: var(--s-5); }
.proj-stat-card { padding: var(--s-4); background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius); text-align: center; }
.proj-stat-card .label { font-size: 12px; color: var(--muted); margin-bottom: var(--s-1); }
.proj-stat-card .value { font-size: 24px; font-weight: 600; font-family: var(--font-mono); }
.proj-stat-card .sub { font-size: 11px; color: var(--muted); margin-top: 2px; }

/* 文件夹管理 / Folder management */
.proj-folders-section { margin-bottom: var(--s-5); padding: var(--s-4); background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); }
.proj-section-title { font-size: 14px; font-weight: 600; margin: 0 0 var(--s-3); color: var(--fg); }
.proj-folders-list { display: flex; flex-direction: column; gap: var(--s-2); margin-bottom: var(--s-3); }
.proj-folder-row { display: flex; align-items: center; justify-content: space-between; padding: var(--s-2) var(--s-3); background: var(--surface-2); border-radius: var(--radius-sm); gap: var(--s-2); }
.proj-folder-info { display: flex; align-items: center; gap: var(--s-2); min-width: 0; flex: 1; }
.proj-folder-path { font-size: 12px; color: var(--fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--font-mono); }
.proj-folder-controls { display: flex; align-items: center; gap: var(--s-2); flex-shrink: 0; }
.proj-sync-toggle { display: flex; align-items: center; gap: var(--s-2); }
.proj-sync-label { font-size: 11px; color: var(--muted); }
.proj-folder-btn { color: var(--subtle); background: none; border: none; cursor: pointer; padding: 4px; border-radius: var(--radius-sm); transition: all 0.12s; display: flex; }
.proj-folder-btn:hover { color: var(--fg); background: var(--border); }
.proj-folder-btn.danger:hover { color: var(--error); background: oklch(95% 0.04 25); }

/* Tab 切换 / Tabs */
.proj-tabs { display: flex; gap: var(--s-1); border-bottom: 1px solid var(--border); margin-bottom: var(--s-4); }
.proj-tab { padding: var(--s-2) var(--s-4); font-size: 13px; color: var(--muted); background: none; border: none; border-bottom: 2px solid transparent; cursor: pointer; transition: all 0.12s; display: inline-flex; align-items: center; gap: var(--s-1); }
.proj-tab:hover { color: var(--fg); }
.proj-tab.is-active { color: var(--accent); border-bottom-color: var(--accent); }
.proj-tab-count { font-size: 11px; color: var(--muted); background: var(--surface-2); padding: 0 5px; border-radius: 999px; min-width: 18px; text-align: center; }
.proj-tab.is-active .proj-tab-count { background: var(--accent-soft); color: var(--accent); }

/* Tab 面板 / Tab panels */
.proj-tab-panel { min-height: 120px; }
.proj-empty { text-align: center; padding: var(--s-6); color: var(--muted); font-size: 13px; }
.proj-loading { display: flex; justify-content: center; padding: var(--s-6); }
.proj-spinner { width: 20px; height: 20px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: proj-spin 0.8s linear infinite; }
@keyframes proj-spin { to { transform: rotate(360deg); } }

/* 会议卡片 / Meeting cards */
.proj-meeting-card { padding: var(--s-3) var(--s-4); border-bottom: 1px solid var(--border); cursor: pointer; transition: background 0.12s; }
.proj-meeting-card:hover { background: var(--surface); }
.proj-meeting-card:last-child { border-bottom: none; }
.pmc-head { display: flex; justify-content: space-between; align-items: center; }
.pmc-title { font-size: 14px; font-weight: 500; color: var(--fg); }
.pmc-date { font-size: 12px; color: var(--subtle); }
.pmc-meta { display: flex; gap: var(--s-3); margin-top: 4px; font-size: 12px; color: var(--muted); }
.pmc-status { padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 500; }
.pmc-status.status-completed { background: var(--ok-soft); color: var(--ok); }
.pmc-status.status-processing { background: var(--warn-soft); color: var(--warn); }
.pmc-status.status-pending { background: var(--surface-2); color: var(--subtle); }
.pmc-status.status-failed { background: var(--error-soft); color: var(--error); }

/* 文件表格 / Files table */
.proj-files-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.proj-files-table th { text-align: left; font-size: 11px; font-weight: 500; color: var(--subtle); text-transform: uppercase; letter-spacing: 0.04em; padding: var(--s-2) var(--s-3); border-bottom: 1px solid var(--border); }
.proj-files-table td { padding: 8px var(--s-3); border-bottom: 1px solid var(--border); }
.proj-files-table tr:hover td { background: var(--surface-2); }
.file-name-cell { display: flex; flex-direction: column; gap: 2px; }
.file-title { color: var(--fg); font-weight: 500; }
.file-rel-path { font-size: 11px; color: var(--subtle); font-family: var(--font-mono); }
.file-type-badge { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 500; background: var(--surface-2); color: var(--muted); text-transform: uppercase; }
.file-size, .file-date { font-size: 12px; color: var(--muted); font-family: var(--font-mono); }

/* 搜索 / Search */
.proj-search-bar { display: flex; gap: var(--s-2); margin-bottom: var(--s-4); }
.proj-search-input { flex: 1; max-width: 400px; padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--radius); font-size: 13px; outline: none; background: var(--surface); color: var(--fg); transition: border-color 0.15s; }
.proj-search-input:focus { border-color: var(--accent); box-shadow: var(--shadow-focus); }
.proj-search-summary { font-size: 12px; color: var(--muted); margin-bottom: var(--s-3); }
.proj-search-item { padding: var(--s-2) var(--s-3); border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 2px; }
.proj-search-item:hover { background: var(--surface-2); }
.search-item-title { font-size: 13px; font-weight: 500; color: var(--fg); }
.search-item-path { font-size: 11px; color: var(--subtle); font-family: var(--font-mono); }

/* 确认对话框 / Confirmation dialog */
.proj-dialog-overlay { position: fixed; inset: 0; background: var(--overlay-bg); display: flex; align-items: center; justify-content: center; z-index: var(--z-modal); animation: fb-overlay-in 0.2s ease; }
@keyframes fb-overlay-in { from { opacity: 0; } }
.proj-dialog { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: var(--s-6); max-width: 400px; width: 90%; box-shadow: 0 8px 32px oklch(0% 0 0 / 0.15); animation: fb-card-in 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
@keyframes fb-card-in { from { opacity: 0; transform: translateY(8px); } }
.proj-dialog h3 { font-size: 16px; font-weight: 600; margin: 0 0 var(--s-3); color: var(--fg); }
.proj-dialog p { font-size: 14px; color: var(--muted); margin: 0 0 var(--s-5); line-height: 1.5; }
.proj-dialog-actions { display: flex; justify-content: flex-end; gap: var(--s-2); }
.proj-dialog-actions kbd { font-family: var(--font-mono); font-size: 9px; padding: 1px 4px; border-radius: 3px; border: 1px solid var(--border); background: var(--surface-2); color: var(--subtle); line-height: 1.3; margin-left: 4px; }
.danger-confirm { color: var(--error) !important; border-color: var(--error) !important; }
.danger-confirm:hover { background: var(--error-soft) !important; }

@media (max-width: 920px) {
  .proj-unified-input { max-width: 100%; }
  .proj-detail-head { flex-direction: column; align-items: flex-start; gap: var(--s-3); }
  .proj-detail-actions { width: 100%; flex-wrap: wrap; }
  .proj-stat-cards { grid-template-columns: 1fr; }
  .proj-folder-row { flex-direction: column; align-items: flex-start; }
  .proj-folder-controls { width: 100%; justify-content: flex-end; }
}
</style>
