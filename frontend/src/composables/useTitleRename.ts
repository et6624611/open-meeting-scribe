/**
 * useTitleRename.ts — 会议标题内联重命名 / Meeting title inline rename
 *
 * 背景（E2E T-021）：纪要页「更多 → 重命名」与会议卡片重命名此前调用浏览器原生
 * prompt()，在桌面端 / WKWebView / 受限环境下弹窗被拦截，且与页面 UI 割裂。
 * 现改为原位内联编辑：标题所在表面直接变成 input，Enter/blur 保存、Esc 放弃，
 * 沿用 SpeakersView 说话人改名同一套交互口径（行内编辑以 blur 收尾，不参与
 * click-away 隐式收起）。
 *
 * 状态做成模块级单例：同一条标题有两个渲染面（顶栏 .topbar-title 与侧栏卡片
 * .sb-tl-title），scope 记录本次重命名由哪个表面发起，保证任意时刻只有一个可聚焦
 * 的输入框；另一面只把未保存的草稿作为纯文本实时回显，避免两个输入框互相触发
 * blur 提交。
 */
import { ref } from 'vue'
import { updateTask } from '@/api/tasks'
import { extractErrorMessage } from '@/api/client'
import { tt } from '@/i18n'
import { useTaskStore } from '@/stores/task'
import { showToast } from '@/composables/useToast'

/** 编辑器归属的表面 / Surface owning the inline editor */
export type TitleRenameScope = 'topbar' | 'card'

// ── 模块级单例状态 / Module-level singleton state ──
const taskId = ref<string | null>(null)
const scope = ref<TitleRenameScope | null>(null)
const draft = ref('')
/** 进入编辑态时的原标题：用于「未改动即视为取消」判定 / Title captured on entry, for no-change detection */
let original = ''
/** 提交进行中：Enter 与随后元素卸载触发的 blur 会重复进入，需去重 */
let saving = false

export function useTitleRename() {
  const taskStore = useTaskStore()

  /** 该表面此刻是否应渲染编辑器 / Should this surface render the editor now */
  function owns(at: TitleRenameScope, ofTask?: string | null): boolean {
    return !!ofTask && taskId.value === ofTask && scope.value === at
  }

  /** 是否正处于重命名态（不限表面） / Whether a rename session is open on any surface */
  function isRenaming(ofTask?: string | null): boolean {
    return !!ofTask && taskId.value === ofTask
  }

  /** 进入内联编辑态 / Enter inline editing */
  function start(ofTask: string, currentTitle: string, at: TitleRenameScope) {
    taskId.value = ofTask
    scope.value = at
    draft.value = currentTitle
    original = currentTitle
  }

  /** 放弃编辑 / Discard the edit */
  function cancel() {
    taskId.value = null
    scope.value = null
    draft.value = ''
    original = ''
  }

  /** 保存（Enter / blur 触发）；空标题或无变更按取消处理 / Save; empty or unchanged title cancels */
  async function commit() {
    const id = taskId.value
    if (!id || saving) return
    const title = draft.value.trim()
    if (!title || title === original) {
      cancel()
      return
    }
    saving = true
    try {
      const updated = await updateTask(id, { title })
      // [状态同步] 增量 patch 本地任务：顶栏标题、纪要页面包屑、侧栏卡片共享同一 store，
      // 全量 loadTasks 会让侧栏滚动位置重置。
      taskStore.patchTaskLocal(id, { title: updated.title || title })
      cancel()
    } catch (e) {
      console.error('rename failed:', e)
      showToast(extractErrorMessage(e, tt('task.errors.rename_failed')), 'error')
      // 失败保留编辑态，用户可原地重试，不必重新点一次菜单 / keep editing for in-place retry
    } finally {
      saving = false
    }
  }

  /**
   * 非编辑面的只读回显：重命名进行中时跟随草稿，避免同一标题在两个表面显示不一致。
   * Read-only echo for the surface without the input, so both places show one title.
   */
  function displayTitle(ofTask: string | null | undefined, fallback: string): string {
    if (ofTask && taskId.value === ofTask) return draft.value || fallback
    return fallback
  }

  return { taskId, scope, draft, owns, isRenaming, start, cancel, commit, displayTitle }
}
