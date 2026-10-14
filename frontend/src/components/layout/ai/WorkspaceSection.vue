<template>
  <div class="ctx-section section-workspace" :class="{ 'is-collapsed': !expanded }">
    <!-- 分区头：图标 + 标题 + 折叠箭头 -->
    <div class="ctx-section-header" @click="expanded = !expanded">
      <div class="ctx-section-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2Z"/></svg>
        <h4>{{ t('ai-panel.context.workspace_title') }}</h4>
      </div>
      <div class="ctx-section-header-right">
        <span v-if="workspaceExists" class="ctx-section-count">{{ fileCountLabel }}</span>
        <svg class="ctx-chevron" :class="{ 'is-collapsed': !expanded }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
    </div>

    <div v-if="!expanded" class="ctx-section-collapsed-hint" @click.stop="expanded = true">
      <span v-if="workspaceExists" class="ws-collapsed-path" :title="workspacePath">{{ shortPath }}</span>
      <span v-else class="ws-collapsed-empty">{{ t('ai-panel.context.workspace_empty') }}</span>
    </div>

    <div v-else class="ctx-section-body ws-body">
      <!-- 操作行 / Action row -->
      <div class="ws-actions">
        <button class="ws-act" :disabled="refreshing" :title="t('ai-panel.context.workspace_refresh')" @click="onRefresh">
          <svg :class="{ 'is-spin': refreshing }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></svg>
        </button>
        <button class="ws-act" :disabled="!workspacePath" :title="t('ai-panel.context.workspace_copy_path')" @click="ws.copyPath()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        </button>
        <button class="ws-act" :disabled="!workspaceExists" :title="t('ai-panel.context.workspace_open_finder')" @click="ws.openFinder(taskId!)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2Z"/></svg>
        </button>
        <button class="ws-act" :disabled="!workspaceExists" :title="t('ai-panel.context.workspace_open_ide')" @click="ws.toggleIdesMenu()" ref="ideTriggerRef">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 18 6-6-6-6"/><path d="M8 6 2 12l6 6"/></svg>
        </button>
        <button class="ws-act ws-act-import" :disabled="!workspaceExists || importing" :title="t('ai-panel.context.workspace_import')" @click="onImport">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></svg>
        </button>
      </div>

      <!-- 路径 / Path -->
      <div v-if="workspacePath" class="ws-path" :title="workspacePath">
        <span class="ws-path-label">{{ t('ai-panel.context.workspace_path_label') }}</span>
        <code>{{ workspacePath }}</code>
      </div>

      <!-- 文件树 / File tree -->
      <div class="ws-tree" :class="{ 'is-loading': loadingTree }">
        <div v-if="loadingTree" class="ws-tree-loading">{{ t('ai-panel.context.workspace_loading') }}</div>
        <div v-else-if="!workspaceExists" class="ws-tree-empty">
          <p>{{ t('ai-panel.context.workspace_not_exist') }}</p>
          <button class="ws-empty-btn" @click="ws.ensurePreview(taskId!)">{{ t('ai-panel.context.workspace_generate') }}</button>
        </div>
        <div v-else-if="treeNodes.length === 0" class="ws-tree-empty">
          <p>{{ t('ai-panel.context.workspace_empty_files') }}</p>
        </div>
        <div v-else class="ws-tree-list">
          <FileTreeNode
            v-for="node in treeNodes"
            :key="node.rel_path"
            :node="node"
            :depth="0"
            :active-path="previewRelPath"
            @select="onFileSelect"
          />
        </div>
      </div>

      <!-- 文件预览 / File preview -->
      <div v-if="previewRelPath || previewLoading" class="ws-preview" :class="{ 'is-loading': previewLoading }">
        <div class="ws-preview-head">
          <span class="ws-preview-path" :title="previewRelPath">{{ previewRelPath }}</span>
          <button class="ws-preview-close" :title="t('ai-panel.context.workspace_preview_close')" @click="ws.clearPreview()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
          </button>
        </div>
        <div v-if="previewLoading" class="ws-preview-loading">{{ t('ai-panel.context.workspace_preview_loading') }}</div>
        <pre v-else-if="previewFile" class="ws-preview-content">{{ previewFile.content }}<span v-if="previewFile.truncated" class="ws-preview-trunc">{{ t('ai-panel.context.workspace_preview_truncated') }}</span></pre>
      </div>

      <!-- IDE 下拉浮层 / IDE dropdown -->
      <div v-if="ws.idesOpen.value" class="ws-ide-menu" ref="ideMenuRef" role="dialog">
        <div class="ws-ide-head">
          <span>{{ t('ai-panel.context.workspace_ide_open_in') }}</span>
          <button class="ws-ide-close" :title="t('ai-panel.context.workspace_ide_close')" @click="ws.closeIdesMenu()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
          </button>
        </div>
        <ul class="ws-ide-list">
          <li v-for="ide in ws.ides.value" :key="ide.ide_id">
            <button
              class="ws-ide-item"
              :class="{ 'is-disabled': !ide.available, 'is-busy': ws.openingIdeId.value === ide.ide_id }"
              :disabled="!ide.available || ws.openingIdeId.value === ide.ide_id"
              :title="ide.available ? ide.display_name : t('ai-panel.context.workspace_ide_not_found', { name: ide.display_name })"
              @click="ws.openIde(taskId!, ide.ide_id)"
            >
              <span class="ws-ide-name">{{ ide.display_name }}</span>
              <span v-if="!ide.available" class="ws-ide-na">{{ t('ai-panel.context.workspace_ide_unavailable') }}</span>
              <svg v-else-if="ws.openingIdeId.value === ide.ide_id" class="ws-ide-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/></svg>
            </button>
          </li>
        </ul>
      </div>

      <!-- 跨会议浏览 / Cross-meeting browser -->
      <div class="ws-browser">
        <div class="ws-browser-head">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7h18"/><path d="M3 12h18"/><path d="M3 17h18"/></svg>
          <span>{{ t('ai-panel.context.workspace_browser_title') }}</span>
          <button v-if="browsingProjectId" class="ws-browser-back" @click="ws.resetBrowser()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
          </button>
        </div>
        <div class="ws-browser-body">
          <div v-if="loadingProjects" class="ws-browser-loading">{{ t('ai-panel.context.workspace_loading') }}</div>
          <div v-else-if="!browsingProjectId">
            <div v-if="projects.length === 0 && standaloneCount === 0" class="ws-browser-empty">{{ t('ai-panel.context.workspace_browser_empty') }}</div>
            <ul v-else class="ws-browser-list">
              <li v-for="proj in projects" :key="proj.project_id">
                <button class="ws-browser-item" @click="ws.loadMeetings(proj.project_id)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                  <span class="ws-browser-name" :title="proj.project_name">{{ proj.project_name }}</span>
                  <span class="ws-browser-count">{{ proj.meeting_count }}</span>
                </button>
              </li>
              <li v-if="standaloneCount > 0">
                <button class="ws-browser-item" @click="ws.loadMeetings('_standalone')">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7V4a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v3"/><path d="M9 22V12"/><path d="M15 22V12"/><path d="M3 22h18"/><path d="M3 12h18"/></svg>
                  <span class="ws-browser-name">{{ t('ai-panel.context.workspace_browser_standalone') }}</span>
                  <span class="ws-browser-count">{{ standaloneCount }}</span>
                </button>
              </li>
            </ul>
          </div>
          <div v-else>
            <div v-if="loadingMeetings" class="ws-browser-loading">{{ t('ai-panel.context.workspace_loading') }}</div>
            <ul v-else class="ws-browser-list">
              <li v-for="m in projectMeetings" :key="m.task_id">
                <button class="ws-browser-item ws-browser-meeting" @click="$emit('goMeeting', m.task_id)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m7 13 3 3 6-6"/></svg>
                  <span class="ws-browser-name" :title="m.title">{{ m.title || t('ai-panel.context.source_untitled') }}</span>
                  <span v-if="m.meeting_date" class="ws-browser-date">{{ m.meeting_date }}</span>
                </button>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { useWorkspace } from '@/composables/useWorkspace'
import { getDockBounds, positionDropdown } from '@/utils/popoverPosition'
import FileTreeNode from './FileTreeNode.vue'

const { t } = useI18n()
const ws = useWorkspace()

const props = defineProps<{
  taskId: string | null
}>()

defineEmits<{
  (e: 'goMeeting', meetingId: string): void
}>()

const expanded = ref(true)
const ideMenuRef = ref<HTMLElement | null>(null)
const ideTriggerRef = ref<HTMLElement | null>(null)

// 解构访问常用状态（保持模板简洁）
const {
  workspacePath,
  treeNodes,
  workspaceExists,
  loadingTree,
  refreshing,
  importing,
  previewFile,
  previewRelPath,
  previewLoading,
  projects,
  standaloneCount,
  projectMeetings,
  browsingProjectId,
  loadingProjects,
  loadingMeetings,
} = ws

const fileCountLabel = computed(() => {
  const n = countFiles(treeNodes.value)
  return n === 0 ? t('ai-panel.context.workspace_no_files_short') : `${n}`
})

function countFiles(nodes: typeof treeNodes.value): number {
  let c = 0
  for (const n of nodes) {
    if (n.type === 'file') c++
    else if (n.children) c += countFiles(n.children)
  }
  return c
}

const shortPath = computed(() => {
  const p = workspacePath.value
  if (!p) return ''
  if (p.length <= 40) return p
  // 截尾显示文件名层级 / show trailing tail
  const tail = p.split(/[\\/]/).slice(-3).join('/')
  return '…/' + tail
})

async function onRefresh() {
  if (props.taskId) await ws.refresh(props.taskId)
}

async function onImport() {
  if (props.taskId) await ws.importChanges(props.taskId)
}

async function onFileSelect(relPath: string) {
  if (props.taskId) await ws.loadFile(props.taskId, relPath)
}

// IDE 下拉定位（每次打开重新计算，遵循停靠栏避让硬约束）
async function repositionIdeMenu() {
  await nextTick()
  if (!ideMenuRef.value || !ideTriggerRef.value) return
  const tr = ideTriggerRef.value.getBoundingClientRect()
  const bounds = getDockBounds()
  const menuW = ideMenuRef.value.offsetWidth
  const menuH = ideMenuRef.value.offsetHeight
  const { x, y } = positionDropdown(
    { top: tr.top, left: tr.left, width: tr.width, height: tr.height },
    menuW, menuH, bounds,
    { align: 'end' },
  )
  ideMenuRef.value.style.left = `${x}px`
  ideMenuRef.value.style.top = `${y}px`
}

watch(() => ws.idesOpen.value, (open) => {
  if (open) repositionIdeMenu()
})

// 外部点击关闭下拉
function onDocMouseDown(e: MouseEvent) {
  if (!ws.idesOpen.value) return
  const t = e.target as Node
  if (ideMenuRef.value?.contains(t)) return
  if (ideTriggerRef.value?.contains(t)) return
  ws.closeIdesMenu()
}

// 窗口缩放重定位
function onResize() {
  if (ws.idesOpen.value) repositionIdeMenu()
}

onMounted(() => {
  document.addEventListener('mousedown', onDocMouseDown, true)
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  document.removeEventListener('mousedown', onDocMouseDown, true)
  window.removeEventListener('resize', onResize)
})

// taskId 变化时预生成工作区（进会议页触发）
watch(
  () => props.taskId,
  (id) => {
    if (id) ws.ensurePreview(id, { silent: true })
  },
  { immediate: true },
)

// 会议产出变化时 debounce 800ms 刷新工作区（会后修改纪要/随记/决策时同步）。
// 会议中（recording/paused）不触发，避免高频写盘；
// 工作区不存在时不刷新（ensurePreview 会先生成）。
const taskStore = useTaskStore()
let refreshTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => [
    taskStore.currentTask?.summary,
    (taskStore.currentTask as unknown as { user_notes?: string } | null)?.user_notes,
    taskStore.currentTask?.todos,
  ],
  () => {
    if (refreshTimer) clearTimeout(refreshTimer)
    refreshTimer = setTimeout(() => {
      const status = taskStore.currentTask?.status
      if (status === 'recording' || status === 'paused') return
      if (!props.taskId || !ws.workspaceExists.value) return
      // 静默刷新：不弹 toast，不打扰用户阅读
      // Silent refresh: no toast, no disturbance
      refreshWorkspaceSilent(props.taskId)
    }, 800)
  },
)

async function refreshWorkspaceSilent(taskId: string) {
  try {
    const { refreshWorkspace } = await import('@/api/workspace')
    await refreshWorkspace(taskId)
    await ws.loadTree(taskId, { silent: true })
  } catch {
    /* 静默失败，不打扰 */
  }
}

onUnmounted(() => {
  if (refreshTimer) clearTimeout(refreshTimer)
})
</script>

<style scoped>
.ctx-section {
  border-top: 1px solid var(--border-subtle, rgba(0,0,0,0.06));
  padding: 12px 16px 4px;
}
.ctx-section-header {
  display: flex; align-items: center; justify-content: space-between;
  cursor: pointer; user-select: none;
  padding-bottom: 6px;
}
.ctx-section-title { display: flex; align-items: center; gap: 8px; color: var(--text-secondary, #6b7280); }
.ctx-section-title svg { width: 16px; height: 16px; }
.ctx-section-title h4 { margin: 0; font-size: 13px; font-weight: 600; color: var(--text-primary, #111827); }
.ctx-section-header-right { display: flex; align-items: center; gap: 8px; }
.ctx-section-count { font-size: 11px; color: var(--text-tertiary, #9ca3af); }
.ctx-chevron { width: 14px; height: 14px; color: var(--text-tertiary, #9ca3af); transition: transform 0.15s; }
.ctx-chevron.is-collapsed { transform: rotate(-90deg); }

.ctx-section-collapsed-hint { cursor: pointer; padding: 4px 0 8px; }
.ws-collapsed-path { display: block; font-size: 11px; color: var(--text-tertiary, #9ca3af); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: ui-monospace, monospace; }
.ws-collapsed-empty { font-size: 11px; color: var(--text-tertiary, #9ca3af); }

.ws-body { display: flex; flex-direction: column; gap: 8px; padding-bottom: 8px; }

.ws-actions { display: flex; gap: 4px; flex-wrap: wrap; }
.ws-act {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 6px;
  border: 1px solid var(--border-subtle, rgba(0,0,0,0.08));
  background: var(--surface-1, transparent);
  color: var(--text-secondary, #6b7280);
  cursor: pointer; transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.ws-act:hover:not(:disabled) { background: var(--hover-bg, rgba(0,0,0,0.04)); color: var(--text-primary, #111827); border-color: var(--accent, #3b82f6); }
.ws-act:disabled { opacity: 0.4; cursor: not-allowed; }
.ws-act svg { width: 14px; height: 14px; }
.ws-act svg.is-spin { animation: ws-spin 0.8s linear infinite; }
.ws-act-import { margin-left: auto; }
@keyframes ws-spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }

.ws-path {
  display: flex; align-items: center; gap: 6px;
  font-size: 10px; color: var(--text-tertiary, #9ca3af);
  overflow: hidden;
}
.ws-path-label { flex-shrink: 0; }
.ws-path code {
  flex: 1; min-width: 0;
  font-family: ui-monospace, monospace; font-size: 10px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--text-secondary, #6b7280);
}

.ws-tree {
  max-height: 260px; overflow-y: auto;
  border: 1px solid var(--border-subtle, rgba(0,0,0,0.06));
  border-radius: 6px; padding: 4px;
  background: var(--surface-1, rgba(0,0,0,0.015));
}
.ws-tree.is-loading { opacity: 0.6; }
.ws-tree-loading, .ws-tree-empty { padding: 16px 8px; text-align: center; font-size: 11px; color: var(--text-tertiary, #9ca3af); }
.ws-tree-empty p { margin: 0 0 8px; }
.ws-empty-btn { font-size: 11px; padding: 4px 10px; border-radius: 4px; border: 1px solid var(--accent, #3b82f6); background: transparent; color: var(--accent, #3b82f6); cursor: pointer; }
.ws-empty-btn:hover { background: var(--accent-soft, rgba(59,130,246,0.08)); }
.ws-tree-list { display: flex; flex-direction: column; }

.ws-preview {
  border: 1px solid var(--border-subtle, rgba(0,0,0,0.06));
  border-radius: 6px; background: var(--surface-1, rgba(0,0,0,0.02));
  max-height: 240px; overflow: hidden; display: flex; flex-direction: column;
}
.ws-preview-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 8px; border-bottom: 1px solid var(--border-subtle, rgba(0,0,0,0.06));
}
.ws-preview-path { font-family: ui-monospace, monospace; font-size: 10px; color: var(--text-tertiary, #9ca3af); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ws-preview-close { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border: none; background: transparent; cursor: pointer; color: var(--text-tertiary, #9ca3af); border-radius: 3px; }
.ws-preview-close:hover { background: var(--hover-bg, rgba(0,0,0,0.06)); color: var(--text-primary, #111827); }
.ws-preview-close svg { width: 12px; height: 12px; }
.ws-preview-loading { padding: 16px; text-align: center; font-size: 11px; color: var(--text-tertiary, #9ca3af); }
.ws-preview-content {
  margin: 0; padding: 8px; overflow: auto;
  font-family: ui-monospace, monospace; font-size: 11px; line-height: 1.5;
  color: var(--text-secondary, #6b7280);
  white-space: pre-wrap; word-break: break-word;
}
.ws-preview-trunc { display: block; margin-top: 8px; padding-top: 6px; border-top: 1px dashed var(--border-subtle, rgba(0,0,0,0.1)); color: var(--warn, #d97706); font-size: 10px; }

.ws-ide-menu {
  position: fixed; z-index: 600;
  min-width: 200px; max-width: 280px;
  background: var(--glass-bg, rgba(255,255,255,0.96));
  backdrop-filter: blur(12px);
  border: 1px solid var(--border-subtle, rgba(0,0,0,0.08));
  border-radius: 8px; padding: 6px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
}
.ws-ide-head { display: flex; align-items: center; justify-content: space-between; padding: 4px 6px 6px; border-bottom: 1px solid var(--border-subtle, rgba(0,0,0,0.06)); }
.ws-ide-head span { font-size: 11px; color: var(--text-tertiary, #9ca3af); }
.ws-ide-close { display: inline-flex; width: 16px; height: 16px; align-items: center; justify-content: center; border: none; background: transparent; cursor: pointer; color: var(--text-tertiary, #9ca3af); border-radius: 3px; }
.ws-ide-close:hover { background: var(--hover-bg, rgba(0,0,0,0.06)); }
.ws-ide-close svg { width: 11px; height: 11px; }
.ws-ide-list { list-style: none; margin: 0; padding: 2px 0 0; }
.ws-ide-item { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; padding: 6px 8px; border: none; background: transparent; cursor: pointer; border-radius: 4px; text-align: left; font-size: 12px; color: var(--text-primary, #111827); }
.ws-ide-item:hover:not(.is-disabled) { background: var(--hover-bg, rgba(0,0,0,0.04)); }
.ws-ide-item.is-disabled { opacity: 0.4; cursor: not-allowed; }
.ws-ide-name { flex: 1; }
.ws-ide-na { font-size: 10px; color: var(--text-tertiary, #9ca3af); }
.ws-ide-spin { width: 12px; height: 12px; animation: ws-spin 0.8s linear infinite; }

.ws-browser { border-top: 1px solid var(--border-subtle, rgba(0,0,0,0.06)); padding-top: 6px; }
.ws-browser-head { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-tertiary, #9ca3af); margin-bottom: 4px; }
.ws-browser-head svg { width: 12px; height: 12px; }
.ws-browser-back { margin-left: auto; display: inline-flex; width: 16px; height: 16px; align-items: center; justify-content: center; border: none; background: transparent; cursor: pointer; color: var(--text-secondary, #6b7280); border-radius: 3px; }
.ws-browser-back:hover { background: var(--hover-bg, rgba(0,0,0,0.06)); }
.ws-browser-back svg { width: 12px; height: 12px; }
.ws-browser-loading, .ws-browser-empty { padding: 8px; text-align: center; font-size: 11px; color: var(--text-tertiary, #9ca3af); }
.ws-browser-list { list-style: none; margin: 0; padding: 0; }
.ws-browser-item { display: flex; align-items: center; gap: 6px; width: 100%; padding: 5px 6px; border: none; background: transparent; cursor: pointer; border-radius: 4px; text-align: left; font-size: 12px; color: var(--text-secondary, #6b7280); }
.ws-browser-item:hover { background: var(--hover-bg, rgba(0,0,0,0.04)); color: var(--text-primary, #111827); }
.ws-browser-item svg { width: 13px; height: 13px; flex-shrink: 0; opacity: 0.7; }
.ws-browser-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ws-browser-count { font-size: 10px; color: var(--text-tertiary, #9ca3af); flex-shrink: 0; padding: 1px 6px; border-radius: 8px; background: var(--badge-bg, rgba(0,0,0,0.05)); }
.ws-browser-date { font-size: 10px; color: var(--text-tertiary, #9ca3af); flex-shrink: 0; }
</style>
