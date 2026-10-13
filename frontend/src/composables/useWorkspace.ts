/**
 * useWorkspace.ts — 工作区浏览 / IDE 联动 / 跨会议索引的状态管理
 *
 * 工作区是「会议上下文物化成的本地文件夹」，AI 会话面板在「上下文 Tab」内
 * 暴露给用户：浏览文件树、预览 .md、一键打开 IDE/Finder、把 IDE 改动回导纪要。
 * 跨会议浏览区复用同一套预览根，按 project 路由聚合。
 */
import { ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/api/client'
import { useSummaryProposal } from '@/composables/useSummaryProposal'
import { useNotesProposal } from '@/composables/useNotesProposal'
import {
  fetchWorkspaceTree,
  fetchWorkspaceFile,
  generatePreview,
  refreshWorkspace,
  importFromWorkspace,
  openInFinder,
  openInIde,
  listIdes,
  listWorkspaceProjects,
  listProjectMeetings,
} from '@/api/workspace'
import type {
  WorkspaceNode,
  WorkspaceFile,
  IdeInfo,
  WorkspaceProject,
  ProjectMeeting,
} from '@/api/workspace'

export function useWorkspace() {
  const { t } = useI18n()
  // ── 当前会议工作区 / Current meeting workspace ──
  const workspacePath = ref<string>('')
  const treeNodes = ref<WorkspaceNode[]>([])
  const workspaceExists = ref(false)
  const loadingTree = ref(false)
  const refreshing = ref(false)
  const importing = ref(false)
  const openingIdeId = ref<string | null>(null)

  // ── 文件预览 / File preview ──
  const previewFile = shallowRef<WorkspaceFile | null>(null)
  const previewRelPath = ref<string>('')
  const previewLoading = ref(false)

  // ── IDE 探测 / IDE detection ──
  const ides = ref<IdeInfo[]>([])
  const idesLoaded = ref(false)
  const idesOpen = ref(false)

  // ── 跨会议浏览 / Cross-meeting browser ──
  const projects = ref<WorkspaceProject[]>([])
  const standaloneCount = ref(0)
  const projectsLoaded = ref(false)
  const projectMeetings = ref<ProjectMeeting[]>([])
  const browsingProjectId = ref<string>('')
  const loadingProjects = ref(false)
  const loadingMeetings = ref(false)

  // ── 当前会议工作区方法 / Current workspace methods ──

  /** 进会议页时预生成工作区；后端幂等，重复调用安全 */
  async function ensurePreview(taskId: string, opts?: { silent?: boolean }): Promise<void> {
    if (!taskId) return
    try {
      const r = await generatePreview(taskId)
      workspacePath.value = r.workspace
      // 预览生成后直接拉文件树，省一次手动刷新
      await loadTree(taskId, { silent: true })
    } catch (err) {
      if (!opts?.silent) showToast(extractErrorMessage(err, '工作区预生成失败'), 'error')
    }
  }

  /** 拉取文件树（不预生成；若工作区不存在 exists=false） */
  async function loadTree(taskId: string, opts?: { silent?: boolean }): Promise<void> {
    if (!taskId) return
    loadingTree.value = true
    try {
      const t = await fetchWorkspaceTree(taskId)
      workspacePath.value = t.path
      treeNodes.value = t.nodes || []
      workspaceExists.value = !!t.exists
    } catch (err) {
      if (!opts?.silent) showToast(extractErrorMessage(err, '加载工作区失败'), 'error')
      treeNodes.value = []
      workspaceExists.value = false
    } finally {
      loadingTree.value = false
    }
  }

  /** 加载文件预览（只读文本；非文本类型后端 400 拦截） */
  async function loadFile(taskId: string, relPath: string): Promise<void> {
    if (!taskId || !relPath) return
    previewLoading.value = true
    previewRelPath.value = relPath
    try {
      previewFile.value = await fetchWorkspaceFile(taskId, relPath)
    } catch (err) {
      showToast(extractErrorMessage(err, '预览失败'), 'error')
      previewFile.value = null
    } finally {
      previewLoading.value = false
    }
  }

  function clearPreview() {
    previewFile.value = null
    previewRelPath.value = ''
  }

  /** 刷新工作区（从软件数据重新生成 + 重拉文件树） */
  async function refresh(taskId: string): Promise<boolean> {
    if (!taskId) return false
    refreshing.value = true
    try {
      await refreshWorkspace(taskId)
      await loadTree(taskId, { silent: true })
      showToast('工作区已刷新', 'success')
      return true
    } catch (err) {
      showToast(extractErrorMessage(err, '刷新失败'), 'error')
      return false
    } finally {
      refreshing.value = false
    }
  }

  /** 从工作区导入 IDE 在 .md 里的改动（走 propose 通道，回到纪要/随记确认） */
  async function importChanges(taskId: string): Promise<boolean> {
    if (!taskId) return false
    importing.value = true
    try {
      const r = await importFromWorkspace(taskId)
      if (!r.has_changes) {
        showToast(t('ai-panel.context.workspace_no_changes'), 'info')
        return false
      }
      // summary 变更 → setSummaryProposal（模块级单例，自动起跳纪要 Tab diff 预览）
      if (r.summary) {
        const { setSummaryProposal } = useSummaryProposal()
        setSummaryProposal({ baseline: r.summary.baseline, proposed: r.summary.proposed })
      }
      // notes 变更 → setNotesProposal（模块级单例，自动起跳随记 Tab diff 预览）
      if (r.notes) {
        const { notesProposal } = useNotesProposal()
        notesProposal.value = { baseline: r.notes.baseline, proposed: r.notes.proposed }
      }
      const parts: string[] = []
      if (r.summary) parts.push(t('ai-panel.context.workspace_summary_changes'))
      if (r.notes) parts.push(t('ai-panel.context.workspace_notes_changes'))
      showToast(t('ai-panel.context.workspace_imported', { parts: parts.join('、') }), 'success')
      return true
    } catch (err) {
      showToast(extractErrorMessage(err, '导入失败'), 'error')
      return false
    } finally {
      importing.value = false
    }
  }

  /** 在系统文件管理器中打开工作区 */
  async function openFinder(taskId: string): Promise<void> {
    if (!taskId) return
    try {
      await openInFinder(taskId)
    } catch (err) {
      showToast(extractErrorMessage(err, '打开文件夹失败'), 'error')
    }
  }

  /** 启动 IDE 打开工作区（已安装的 IDE 才会成功） */
  async function openIde(taskId: string, ideId: string): Promise<void> {
    if (!taskId || !ideId) return
    openingIdeId.value = ideId
    try {
      const r = await openInIde(taskId, ideId)
      if (!r.launched) {
        showToast(r.error || '启动 IDE 失败', 'error')
      }
    } catch (err) {
      showToast(extractErrorMessage(err, '启动 IDE 失败'), 'error')
    } finally {
      openingIdeId.value = null
      idesOpen.value = false
    }
  }

  /** 探测已安装的 IDE（一次拉取，UI 缓存） */
  async function loadIdes(force = false): Promise<void> {
    if (idesLoaded.value && !force) return
    try {
      const r = await listIdes()
      ides.value = r.ides || []
      idesLoaded.value = true
    } catch (err) {
      showToast(extractErrorMessage(err, 'IDE 探测失败'), 'error')
    }
  }

  function toggleIdesMenu() {
    if (!idesOpen.value && !idesLoaded.value) loadIdes()
    idesOpen.value = !idesOpen.value
  }

  function closeIdesMenu() {
    idesOpen.value = false
  }

  // ── 跨会议浏览 / Cross-meeting browser ──

  /** 加载全局工作区索引（按 project 聚合） */
  async function loadProjects(force = false): Promise<void> {
    if (projectsLoaded.value && !force) return
    loadingProjects.value = true
    try {
      const r = await listWorkspaceProjects()
      projects.value = r.projects || []
      standaloneCount.value = r.standalone_count || 0
      projectsLoaded.value = true
    } catch (err) {
      showToast(extractErrorMessage(err, '加载会议索引失败'), 'error')
    } finally {
      loadingProjects.value = false
    }
  }

  /** 加载某项目下的会议索引 */
  async function loadMeetings(projectId: string): Promise<void> {
    if (!projectId) return
    loadingMeetings.value = true
    browsingProjectId.value = projectId
    try {
      const r = await listProjectMeetings(projectId)
      projectMeetings.value = r.meetings || []
    } catch (err) {
      showToast(extractErrorMessage(err, '加载会议列表失败'), 'error')
      projectMeetings.value = []
    } finally {
      loadingMeetings.value = false
    }
  }

  function resetBrowser() {
    projectMeetings.value = []
    browsingProjectId.value = ''
  }

  /** 复制工作区绝对路径到剪贴板（兜底：用户手动粘贴到外部 IDE） */
  async function copyPath(): Promise<void> {
    if (!workspacePath.value) return
    try {
      await navigator.clipboard.writeText(workspacePath.value)
      showToast('路径已复制', 'success')
    } catch {
      showToast('复制失败，请手动选择路径', 'error')
    }
  }

  return {
    // 状态 / State
    workspacePath,
    treeNodes,
    workspaceExists,
    loadingTree,
    refreshing,
    importing,
    openingIdeId,
    previewFile,
    previewRelPath,
    previewLoading,
    ides,
    idesLoaded,
    idesOpen,
    projects,
    standaloneCount,
    projectsLoaded,
    projectMeetings,
    browsingProjectId,
    loadingProjects,
    loadingMeetings,
    // 方法 / Methods
    ensurePreview,
    loadTree,
    loadFile,
    clearPreview,
    refresh,
    importChanges,
    openFinder,
    openIde,
    loadIdes,
    toggleIdesMenu,
    closeIdesMenu,
    loadProjects,
    loadMeetings,
    resetBrowser,
    copyPath,
  }
}
