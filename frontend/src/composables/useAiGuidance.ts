/**
 * AI 引导面板 — 根据会议状态动态生成上下文引导 / AI guidance panel — dynamically generates contextual guidance based on meeting status
 */
import { computed } from 'vue'
import { useTaskStore } from '@/stores/task'

interface GuidanceConfig {
  title: string
  sub: string
  icon: string
  contexts: string[]
  prompts: { text: string; icon: string }[]
}

const ICON_DOC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/></svg>'
const ICON_MIC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/><path d="M19 10v2a7 7 0 01-14 0v-2"/></svg>'
const ICON_CLOCK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>'
const ICON_LIST = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>'
const ICON_SEARCH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>'
const ICON_UPLOAD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>'

const GUIDANCE_MAP: Record<string, GuidanceConfig> = {
  recording: {
    title: '会议进行中',
    sub: '实时记录讨论内容，随时可以提问',
    icon: ICON_MIC,
    contexts: ['实时识别中', '对话不会打断录音'],
    prompts: [
      { text: '目前讨论到哪了？', icon: ICON_SEARCH },
      { text: '帮我记录一条随记', icon: ICON_DOC },
      { text: '目前有哪些待办？', icon: ICON_LIST },
    ],
  },
  processing: {
    title: '正在生成纪要',
    sub: '识别和摘要正在处理中',
    icon: ICON_CLOCK,
    contexts: ['处理中', '完成后可查看详细纪要'],
    prompts: [
      { text: '处理进度如何？', icon: ICON_CLOCK },
      { text: '预计还需要多久？', icon: ICON_SEARCH },
    ],
  },
  pending: {
    title: '等待处理',
    sub: '录音已完成，可以开始识别',
    icon: ICON_UPLOAD,
    contexts: ['待识别', '可配置说话人和热词'],
    prompts: [
      { text: '开始识别并生成纪要', icon: ICON_UPLOAD },
      { text: '如何配置说话人信息？', icon: ICON_SEARCH },
    ],
  },
  completed: {
    title: '会议已结束',
    sub: '可以查看纪要、提取待办、分析发言',
    icon: ICON_DOC,
    contexts: ['纪要已生成', '可编辑和导出'],
    prompts: [
      { text: '生成会议纪要', icon: ICON_DOC },
      { text: '提取所有待办事项', icon: ICON_LIST },
      { text: '分析各发言人核心观点', icon: ICON_SEARCH },
      { text: '总结关键决策', icon: ICON_CLOCK },
    ],
  },
  idle: {
    title: 'AI 会议助手',
    sub: '选择或开始一个会议，我来帮你记录和分析',
    icon: ICON_MIC,
    contexts: ['支持实时录音识别', '支持上传音频文件'],
    prompts: [
      { text: '开始一个新会议', icon: ICON_MIC },
      { text: '上传音频文件', icon: ICON_UPLOAD },
      { text: '查看最近的会议', icon: ICON_LIST },
    ],
  },
}

export function useAiGuidance() {
  const taskStore = useTaskStore()

  const currentStatus = computed(() => taskStore.currentTask?.status ?? null)

  const guidance = computed<GuidanceConfig>(() => {
    const status = currentStatus.value
    if (!taskStore.currentTaskId || !status) return GUIDANCE_MAP.idle
    return GUIDANCE_MAP[status] || GUIDANCE_MAP.idle
  })

  return { guidance }
}
