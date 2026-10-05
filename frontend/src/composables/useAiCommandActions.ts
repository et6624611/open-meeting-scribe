/**
 * useAiCommandActions.ts — AI 指令操作回调 / AI command action callbacks
 *
 * 从 AIPanel.vue 拆分而来，封装 /指令 系统的所有操作回调。 / Split from AIPanel.vue; wraps all action callbacks for the /command system.
 * 通过参数注入依赖（router、chat、taskStore 等），保持纯逻辑层。 / Dependencies injected via parameters (router, chat, taskStore, etc.) to keep it a pure logic layer.
 */

import { useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/task'
import { useAiSessionsStore } from '@/stores/aiSessions'
import { showToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/api/client'
import type { AiCommand } from '@/composables/useAiCommands'
import type { Ref } from 'vue'
import { ref } from 'vue'

interface ChatLike {
  messages: Ref<Array<{ role: string; content: string }>>
  sendRaw: (text: string) => Promise<void> | void
}

export function useAiCommandActions(
  chat: ChatLike,
  inputRef: Ref<HTMLTextAreaElement | null>,
) {
  const router = useRouter()
  const taskStore = useTaskStore()
  const aiSessions = useAiSessionsStore()

  async function onRecordStart() {
    try {
      const { startRecord } = await import('@/api/record')
      const res = await startRecord()
      showToast('录音已开始', 'success')
      // 乐观更新：立即将新任务加入本地列表，不阻塞导航 / Optimistic update: add task locally, don't block navigation
      taskStore.patchTaskLocal(res.task_id, {
        status: 'recording',
        source: 'record',
        created_at: new Date().toISOString(),
        meeting_date: new Date().toISOString().slice(0, 10),
      } as any)
      // [状态同步] 绑定当前会议，确保右侧 AI 会话面板路由到正在录制的会议 / Bind the new task so the AI chat panel routes to the recording meeting
      taskStore.selectTask(res.task_id)
      router.push(`/recording/${res.task_id}`)
      // [状态同步] 后台静默刷新任务列表 / Silently refresh task list in background
      taskStore.loadTasks()
    } catch (e: any) {
      if (e?.response?.status === 400) {
        try {
          const { getRecordStatus } = await import('@/api/record')
          const status = await getRecordStatus()
          if (status.recording && status.task_id) {
            taskStore.selectTask(status.task_id)
            router.push(`/recording/${status.task_id}`)
            // [状态同步] 后台静默刷新任务列表 / Silently refresh task list in background
            taskStore.loadTasks()
            return
          }
        } catch { /* 静默 / silent */ }
      }
      showToast(extractErrorMessage(e), 'error')
    }
  }

  async function onRecordStop() {
    try {
      const { stopRecord } = await import('@/api/record')
      await stopRecord()
      showToast('录音已停止', 'success')
      taskStore.loadTasks()
    } catch (e: any) { showToast(extractErrorMessage(e), 'error') }
  }

  async function onRecordPause() {
    try {
      const { pauseRecord } = await import('@/api/record')
      await pauseRecord()
      showToast('录音已暂停', 'success')
    } catch (e: any) { showToast(extractErrorMessage(e), 'error') }
  }

  async function onRecordResume() {
    try {
      const { resumeRecord } = await import('@/api/record')
      await resumeRecord()
      showToast('录音已恢复', 'success')
    } catch (e: any) { showToast(extractErrorMessage(e), 'error') }
  }

  async function onRecordStatus() {
    try {
      const { getRecordStatus } = await import('@/api/record')
      const s = await getRecordStatus()
      const text = s.recording
        ? `录制状态：进行中${s.paused ? '（已暂停）' : ''}\n已录时长：${s.elapsed.toFixed(1)} 秒\n任务 ID：${s.task_id ?? '-'}`
        : '录制状态：未录制'
      chat.messages.value.push({ role: 'assistant', content: text })
      aiSessions.persist()
    } catch (e: any) { showToast(extractErrorMessage(e), 'error') }
  }

  function onTasksShow() {
    const id = taskStore.currentTaskId
    if (id) router.push(`/meeting/${id}`)
    else { showToast('未选择任务，已打开会议库', 'warn'); router.push('/library') }
  }

  const showDeleteConfirm = ref(false)
  const pendingDeleteTaskId = ref<string | null>(null)

  function onTasksDelete() {
    const id = taskStore.currentTaskId
    if (!id) { showToast('未选择任务', 'warn'); return }
    pendingDeleteTaskId.value = id
    showDeleteConfirm.value = true
  }

  async function confirmDeleteTask() {
    const id = pendingDeleteTaskId.value
    if (!id) return
    try {
      const { deleteTask } = await import('@/api/tasks')
      await deleteTask(id)
      showToast('任务已删除', 'success')
      taskStore.loadTasks()
    } catch (e: any) { showToast(extractErrorMessage(e), 'error') }
  }

  async function onSpeakersAdd(nameArg?: string) {
    const name = nameArg || prompt('输入人员姓名：')
    if (!name?.trim()) return
    try {
      const { createSpeaker } = await import('@/api/speakers')
      await createSpeaker(name.trim())
      showToast(`已添加人员：${name.trim()}`, 'success')
    } catch (e: any) { showToast(extractErrorMessage(e), 'error') }
  }

  async function onHotwordsAdd(inputArg?: string) {
    const input = inputArg || prompt('输入热词（多个用空格或逗号分隔）：')
    if (!input?.trim()) return
    try {
      const { fetchHotwords, saveHotwords } = await import('@/api/hotwords')
      const current = await fetchHotwords()
      const words = current.split('\n').map(w => w.trim()).filter(Boolean)
      const added: string[] = []
      for (const w of input.split(/[\s,，]+/).filter(Boolean)) {
        if (!words.includes(w)) { words.push(w); added.push(w) }
      }
      if (!added.length) { showToast('这些热词已存在', 'warn'); return }
      await saveHotwords(words.join('\n'))
      showToast(`已添加 ${added.length} 个热词`, 'success')
    } catch (e: any) { showToast(extractErrorMessage(e), 'error') }
  }

  /** 构建指令列表 / Build command list */
  function buildCommands(): AiCommand[] {
    return [
      { key: '/transcribe', desc: '打开首页（新建转写入口）', descKey: 'cmd_transcribe', when: 'all', action: () => router.push('/') },
      { key: '/normalize', desc: '归一化音频（16kHz/单声道）', descKey: 'cmd_normalize', when: 'all', action: () => showToast('CLI 专用命令：python cli.py normalize <音频文件>', 'warn') },
      { key: '/upload', desc: '上传音频到 DashScope（测试用）', descKey: 'cmd_upload', when: 'all', action: () => showToast('CLI 专用命令：python cli.py upload <音频文件>', 'warn') },
      { key: '/server', desc: '启动 Web UI 服务', descKey: 'cmd_server', when: 'all', action: () => showToast('CLI 专用命令：python cli.py server', 'warn') },
      { key: '/build', desc: '构建前端（Vue 3 + Vite）', descKey: 'cmd_build', when: 'all', action: () => showToast('CLI 专用命令：python cli.py build', 'warn') },
      { key: '/admin', desc: '启动管理后台', descKey: 'cmd_admin', when: 'all', action: () => showToast('CLI 专用命令：python cli.py admin', 'warn') },
      { key: '/record start', desc: '开始录音', descKey: 'cmd_record_start', when: 'all', action: onRecordStart },
      { key: '/record stop', desc: '停止录音', descKey: 'cmd_record_stop', when: 'all', action: onRecordStop },
      { key: '/record pause', desc: '暂停录音', descKey: 'cmd_record_pause', when: 'all', action: onRecordPause },
      { key: '/record resume', desc: '恢复录音', descKey: 'cmd_record_resume', when: 'all', action: onRecordResume },
      { key: '/record status', desc: '查看录音状态', descKey: 'cmd_record_status', when: 'all', action: onRecordStatus },
      { key: '/tasks list', desc: '打开会议库', descKey: 'cmd_tasks_list', when: 'all', action: () => router.push('/library') },
      { key: '/tasks show', desc: '查看当前会议详情', descKey: 'cmd_tasks_show', when: 'all', action: onTasksShow },
      { key: '/tasks delete', desc: '删除当前会议', descKey: 'cmd_tasks_delete', when: 'all', action: onTasksDelete },
      { key: '/speakers list', desc: '打开人员列表', descKey: 'cmd_speakers_list', when: 'all', action: () => router.push('/speakers') },
      { key: '/speakers add', desc: '添加人员（可带姓名：/speakers add 张三）', descKey: 'cmd_speakers_add', when: 'all', action: (args?: string) => onSpeakersAdd(args) },
      { key: '/hotwords list', desc: '打开热词列表', descKey: 'cmd_hotwords_list', when: 'all', action: () => router.push('/hotwords') },
      { key: '/hotwords add', desc: '添加热词（可空格分隔多个）', descKey: 'cmd_hotwords_add', when: 'all', action: (args?: string) => onHotwordsAdd(args) },
      { key: '/settings show', desc: '打开设置', descKey: 'cmd_settings', when: 'all', action: () => router.push('/settings') },
      { key: '/settings set', desc: '修改设置', descKey: 'cmd_settings', when: 'all', action: () => router.push('/settings') },
      { key: '/chat', desc: 'AI 对话（直接输入消息发送）', descKey: 'cmd_chat', when: 'all', action: () => inputRef.value?.focus() },
    ]
  }

  return {
    buildCommands,
    // 单独导出操作回调，供子组件按需使用 / Export action callbacks individually for child component use
    onRecordStart,
    onRecordStop,
    onRecordPause,
    onRecordResume,
    onRecordStatus,
    onTasksShow,
    onTasksDelete,
    onSpeakersAdd,
    onHotwordsAdd,
    // 删除确认状态 / Delete confirmation state
    showDeleteConfirm,
    pendingDeleteTaskId,
    confirmDeleteTask,
  }
}
