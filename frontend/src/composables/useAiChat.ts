/**
 * AI 聊天核心逻辑 / AI chat core logic
 *
 * 消息发送、动作执行、停止生成、跟进建议、数据注入。 / Message sending, action execution, stop generation, follow-up suggestions, data injection.
 * 消息持久化由 aiSessions store 管理。 / Message persistence managed by aiSessions store.
 * 流式处理核心已下沉 useAiChatStreamCore.ts。 / Streaming core moved to useAiChatStreamCore.ts.
 */
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { injectItems, generateChatTitle } from '@/api/chat'
import type { ChatAction, ChatExtractedItem, ChatMessage, AgentStage } from '@/api/chat'
import { fetchChatEngineStatus, fetchChatEngineModels, fetchSettings, probeLocalEngine, saveSettings, type ChatEngineProbe } from '@/api/settings'
import { useTaskStore } from '@/stores/task'
import { useRealtimeStore } from '@/stores/realtime'
import { useAiSessionsStore } from '@/stores/aiSessions'
import type { AiSession } from '@/stores/aiSessions'
import { useAgentStore } from '@/stores/agent'
import { useEngineStore } from '@/stores/engine'
import { useAiInsights } from '@/composables/useAiInsights'
import { useSummaryProposal } from '@/composables/useSummaryProposal'
import { useNotesProposal } from '@/composables/useNotesProposal'
import { useBoardProposal } from '@/composables/useBoardProposal'
import { fetchNotes } from '@/api/notes'
import { isBoardWriteCall, isBoardWriteResult, notifyBoardWritten, boardIdOf } from '@/composables/useBoardSync'
import { notifyTaskWritten, writeDomainsOf } from '@/composables/useTaskWrites'
import { showToast } from '@/composables/useToast'
import { tt, getLocale } from '@/i18n'
import { createStreamCore, type SendOverride as CoreSendOverride } from '@/composables/useAiChatStreamCore'

/** 授权档位（与后端 _VALID_TIERS 对齐）：只读 / 提案写入 / 完全任务 */
export type AuthTier = 'readonly' | 'workspace_write' | 'full_task'

interface FollowUpSuggestion {
  text: string
  icon: string
}

interface VerifiedChange {
  op: string
  decision_id: string
  field: string
  old: unknown
  new: unknown
  verified: boolean
}

const ICON_PLUS = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 8h8M8 4v8"/></svg>'
const ICON_LIST = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 4h8M4 8h6M4 12h7"/></svg>'
const ICON_SEARCH = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="7" cy="7" r="4"/><path d="M10 10l3.5 3.5"/></svg>'
const ICON_CLOCK = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><path d="M8 5v3l2 1"/></svg>'

/** 默认建议（原快捷命令），对话有内容但无 AI 推断建议时展示 / Default suggestions (original quick commands); shown when chat has content but no AI-inferred suggestions */
const DEFAULT_SUGGESTIONS: FollowUpSuggestion[] = [
  { text: '生成会议纪要', icon: ICON_LIST },
  { text: '提取决策事项', icon: ICON_PLUS },
  { text: '分析发言要点', icon: ICON_SEARCH },
]

export function useAiChat() {
  const router = useRouter()
  const taskStore = useTaskStore()
  const realtimeStore = useRealtimeStore()
  const aiSessions = useAiSessionsStore()
  const agentStore = useAgentStore()
  const engineStore = useEngineStore()
  const insights = useAiInsights()
  // 纪要改写提案：模块级单例状态（原位 diff 预览 Layer 1），与 GeneratingView/SummaryPanel 共享
  const proposal = useSummaryProposal()
  const notesProposalStore = useNotesProposal()
  // 建板提案（create_insight_board）：同样不落盘，用户点「接受」才 POST 建板
  const boardProposalStore = useBoardProposal()

  const isLoading = ref(false)
  const isStreaming = ref(false)
  const abortController = ref<AbortController | null>(null)
  const followUps = ref<FollowUpSuggestion[]>([])
  const thinkingStartTime = ref(0)
  const stages = ref<AgentStage[]>([])

  // ── 智能体模式（本地 CLI 引擎）/ Agent mode ──
  // 与"角色"正交：角色=人格/提示词，模式=执行引擎（方案 §3.9-8 术语消歧）
  // 两态：qa=内置问答、agent=智能体（AI 算力入口治理：auto 规则分流已退役，用户选择即意图）
  type ChatMode = 'qa' | 'agent'
  const VALID_MODES: ChatMode[] = ['qa', 'agent']
  // 存量 'auto' 用户回落为问答（一次性迁移：非法值与 auto 均落 qa）
  const storedMode = localStorage.getItem('ai_chat_mode') as ChatMode | null
  const chatMode = ref<ChatMode>(storedMode && VALID_MODES.includes(storedMode) ? storedMode : 'qa')
  /** 当前活跃流 id，供真取消 */
  const currentStreamId = ref<string>('')
  /** 本次回复实际使用的引擎回显（§3.9-1 路由可见） */
  const activeEngine = ref<{ display_name: string; auth_tier: string; auto_selected: boolean } | null>(null)
  /** 模式即权限（PROPOSAL-AGENT-REWRITE-CHANNEL §5.1）：写回权是智能体模式固有的权利，
     不再按按钮才升档——后端 agent 轮默认落 workspace_write，前端不再传 auth_tier 特例。
     本 flag 只承担「共创意图打标」单一职责（轮级）：入口按钮置真 → 下一轮发出即清除 →
     done 时无任何写工具成功回传则亮「本轮未落盘」横幅（§5.4 完成护栏输入）。 */
  const rewriteIntentPending = ref(false)
  /** 横幅态：上一个智能体轮有改写意图但零写回 */
  const rewriteNotPersisted = ref<{ text: string } | null>(null)
  /** 纪要改写提案（提案式 diff）状态已下沉 useSummaryProposal 模块级单例（原位预览需跨组件共享），
     本 composable 只负责在 propose_summary 工具调用时置入、新一轮/切任务时清空。 */
  const summaryProposal = proposal.summaryProposal
  /** 随记改写提案（propose_notes）：同一机制的单例下沉（随记 Tab 原位预览），用户接受才落盘 */
  const notesProposal = notesProposalStore.notesProposal
  /** 建板提案（create_insight_board）：建板权属于用户，侧栏确认卡接受后才 POST 建板 */
  const boardProposal = boardProposalStore.boardProposal

  function setRewriteIntent(v: boolean) {
    rewriteIntentPending.value = v
    if (!v) rewriteNotPersisted.value = null
  }
  /** 兼容名：洞察板共创入口沿用（语义已从"升档特权"收敛为"轮级意图打标"） */
  function setBoardCoCreate(v: boolean) {
    setRewriteIntent(v)
  }

  function setChatMode(mode: ChatMode) {
    chatMode.value = mode
    localStorage.setItem('ai_chat_mode', mode)
  }

  /** 取会话的首轮问答对（仅未被命名过的会话才有命名资格） */
  function titlePairOf(session: AiSession) {
    if (session.autoTitled !== undefined) return null
    const firstUser = session.messages.find(m => m.role === 'user' && m.content.trim())
    const firstReply = session.messages.find(m => m.role === 'assistant' && m.content.trim())
    return firstUser && firstReply ? { firstUser, firstReply } : null
  }

  /** AI 命名单个会话：失败/空标题静默保留默认名（autoTitled 仍为 undefined，可被后续重试） */
  async function titleSession(session: AiSession) {
    const pair = titlePairOf(session)
    if (!pair) return
    const title = await generateChatTitle(pair.firstUser.content, pair.firstReply.content.slice(0, 300))
    if (title) aiSessions.applyAutoTitle(session, title)
  }

  /** 首轮完成后的自动命名（AI 命名，仅此一种来源） */
  function maybeAutoTitle(session: AiSession | undefined) {
    if (session) void titleSession(session)
  }

  // 模块级标记：存量命名回填每次启动只跑一轮（composable 可能被多次实例化）
  let titleBackfillStarted = false

  /** 存量会话命名回填：遍历所有任务桶，对未被命名过且已有完整首轮的会话逐个 AI 命名。
   *  串行执行避免突发请求；单条失败静默跳过，下次启动自愈重试。 */
  function backfillSessionTitles() {
    if (titleBackfillStarted) return
    titleBackfillStarted = true
    void (async () => {
      for (const bucket of Object.values(aiSessions.historyMap)) {
        for (const session of bucket.sessions) {
          await titleSession(session)
        }
      }
    })()
  }

  // ── 授权档位（会话级；档位入口下沉到 ComposerBar，不再放设置页） ──
  // 改档即生效：选档同时更新 pendingAuthTier（全局期望+新会话默认）和当前会话锁定档。
  const VALID_TIERS: AuthTier[] = ['readonly', 'workspace_write', 'full_task']
  const TIER_STORAGE_KEY = 'ai_auth_tier'
  function normalizeTier(v: unknown): AuthTier | null {
    return typeof v === 'string' && (VALID_TIERS as string[]).includes(v) ? (v as AuthTier) : null
  }
  /** 待生效授权档；与后端 agent 轮默认一致，首次使用落 workspace_write（提案写入） */
  const pendingAuthTier = ref<AuthTier>(
    normalizeTier(localStorage.getItem(TIER_STORAGE_KEY)) ?? 'workspace_write',
  )
  function setPendingAuthTier(tier: AuthTier) {
    if (!VALID_TIERS.includes(tier) || pendingAuthTier.value === tier) return
    pendingAuthTier.value = tier
    localStorage.setItem(TIER_STORAGE_KEY, tier)
    // 会中改档即时生效：覆盖当前会话锁定档，下一轮即按新档发送
    aiSessions.updateActiveSessionTier(tier)
  }
  /** 本会话锁定档：历史会话无戳时按当前待生效档补盖一次（首次使用即锁定） */
  function ensureSessionTier() {
    const s = aiSessions.activeSession
    if (s && !normalizeTier(s.authTier)) {
      aiSessions.stampActiveSessionTier(pendingAuthTier.value)
    }
  }
  const sessionAuthTier = computed<AuthTier>(() =>
    normalizeTier(aiSessions.activeSession?.authTier) ?? pendingAuthTier.value)
  // 切任务桶 / 切会话：新激活会话若无戳立即补盖，保证发送时口径确定
  watch(() => aiSessions.activeSession?.id, () => { ensureSessionTier() }, { immediate: true })

  /** 拒绝卡：本轮智能体工具被档位拦截（tool_result read_only）时呈现，下轮自动清 */
  const tierDenial = ref<{ tool: string; summary: string } | null>(null)
  /** 档位菜单外部唤起信号（403 拒绝卡「提升档位」）：自增进而 ComposerBar watch 打开 */
  const tierMenuSignal = ref(0)
  function requestTierMenu(preset?: AuthTier) {
    if (preset) setPendingAuthTier(preset)
    tierMenuSignal.value += 1
  }
  /** 开新会话（头部新建与弹层脚钮共用） */
  function startNewSession() {
    aiSessions.createNewSession(pendingAuthTier.value)
    followUps.value = []
    injectPrompt.value = null
    rewriteIntentPending.value = false
    rewriteNotPersisted.value = null
    summaryProposal.value = null
    notesProposal.value = null
    boardProposal.value = null
    tierDenial.value = null
  }

  // ── 会话级模型选择器（REQ-EXPERT-MODE §2.3：默认跟随详情，后端零改造透传 model） ──
  // 态存于 engine store 共享（与接入方式页「使用面回显」卡联动）
  /** '' = 跟随详情（不传 model，后端取 llm.model 设置值，变更即时反映到下一轮） */
  const sessionModel = computed(() => engineStore.sessionModel)
  /** 候选项：预设模型 + 探测到的本机模型，每项标注来源（本机/体验配额/自带 Key） */
  interface ModelOption { value: string; source: 'local' | 'trial' | 'byok' }
  const modelCandidates = ref<ModelOption[]>([])
  /** 详情层 LLM 当前生效模型（「跟随详情」标签插值用） */
  const detailModelLabel = computed(() => (engineStore.accessSettings as any)?.llm?.model || 'qwen-plus')
  /** CLI 引擎探针状态前置回显（§2.2：不再撞错才知道；失败段定位 AC-4） */
  const cliProbe = ref<ChatEngineProbe | null>(null)
  const agentEngineEnabled = ref(false)
  // ── 智能体引擎模型（就地切换：CLI 路径读 chat_engine.model，非 sessionModel） ──
  const agentEngineId = ref('')
  /** 当前 chat_engine.model（'' = 引擎默认，不传 -m） */
  const agentEngineModel = ref('')
  /** 引擎展示名（name_key 命中优先翻译，否则品牌原文） */
  const agentEngineName = ref('')
  /** 该引擎当前用户可用模型清单（--list-models 探测） */
  const agentModels = ref<string[]>([])
  const agentModelsReason = ref('')
  const agentModelsLoading = ref(false)

  /** 归一化 base_url 用于 provider 匹配：去尾部斜杠与 /v1 段 */
  function normBaseUrl(u: string): string {
    return (u || '').trim().replace(/\/+$/, '').replace(/\/v1$/, '')
  }

  async function loadModelCandidates() {
    const opts: ModelOption[] = []
    const seen = new Set<string>()
    const capSource = engineStore.capability?.llm?.effective
    const cloudSource: 'trial' | 'byok' = capSource === 'trial' ? 'trial' : 'byok'
    // 云端组：只取「当前生效 provider」对应的预设模型，而非把全目录都贴上同一来源标签
    // （体验配额经云端代理转发至 DashScope；自带 Key/直连按 base_url / provider 名匹配预设）
    try {
      const s = await fetchSettings()
      const cloudPresets = (s.llm_provider_presets || []).filter(p => !p.localhost)
      let target: (typeof cloudPresets)[number] | undefined
      if (capSource === 'trial') {
        target = cloudPresets.find(p => /dashscope/i.test(p.base_url || '') || /通义|DashScope/i.test(p.name || ''))
      } else {
        const cur = normBaseUrl(s.llm?.base_url || '')
        target = cloudPresets.find(p => normBaseUrl(p.base_url) === cur)
          || cloudPresets.find(p => p.name === s.llm?.provider)
      }
      // 无匹配（如自定义端点）→ 仅列当前配置的模型，不臆造全目录
      const cloudModels = target?.models?.length ? target.models : (s.llm?.model ? [s.llm.model] : [])
      for (const m of cloudModels) {
        if (seen.has(m)) continue
        seen.add(m)
        opts.push({ value: m, source: cloudSource })
      }
    } catch { /* 静默：候选降级为仅探测结果 */ }
    // 本机组：只列探测到已安装/可达的模型，去掉写死预设（避免显示未安装的）
    try {
      const probe = await probeLocalEngine()
      for (const e of probe.engines) {
        if (!e.reachable) continue
        for (const m of e.models) {
          if (seen.has(m)) continue
          seen.add(m)
          opts.push({ value: m, source: 'local' })
        }
      }
    } catch { /* 同上 */ }
    modelCandidates.value = opts
  }

  async function loadCliProbe() {
    try {
      const st = await fetchChatEngineStatus()
      cliProbe.value = st.probe ?? null
      agentEngineEnabled.value = !!st.config?.enabled
      // 捕获引擎配置（id/model）与展示名，供智能体模式模型选择器使用
      const cfg = st.config
      agentEngineId.value = cfg?.engine_id || ''
      agentEngineModel.value = cfg?.model || ''
      const info = (st.engines || []).find(e => e.engine_id === cfg?.engine_id)
      const nameKey = st.probe?.name_key || info?.name_key || ''
      const tn = nameKey ? tt(nameKey) : ''
      agentEngineName.value = (tn && tn !== nameKey) ? tn : (st.probe?.display_name || info?.display_name || cfg?.engine_id || 'CLI')
    } catch {
      cliProbe.value = null
    }
  }

  /** 拉取智能体引擎可用模型（就地切换菜单打开时） */
  async function loadAgentModels() {
    agentModelsLoading.value = true
    try {
      const r = await fetchChatEngineModels(agentEngineId.value || undefined)
      agentModels.value = r.models || []
      agentModelsReason.value = r.reason || ''
    } catch {
      agentModels.value = []
      agentModelsReason.value = 'probe_error'
    } finally {
      agentModelsLoading.value = false
    }
  }

  /** 就地切换 CLI 引擎模型：持久化到 chat_engine.model（CLI 路径唯一读取源）；'' = 引擎默认 */
  async function setAgentModel(v: string) {
    agentEngineModel.value = v
    try {
      await saveSettings({ chat_engine: { model: v || null } } as never)
    } catch { /* 静默：本地已更新，下次面板刷新对齐 */ }
  }

  /** 智能体模式是否可选（未安装/未登录时置灰 + 指引，AC-4） */
  const agentAvailable = computed(() => cliProbe.value?.available === true)

  // 面板挂载即拉一次（探针/候选不阻塞对话）；模型候选随详情源变化重标
  void loadCliProbe()
  void loadModelCandidates()
  // 存量会话一次性批量命名（串行、静默；每次启动一轮）
  backfillSessionTitles()
  // 详情层来源变化 → 重新按当前 provider 派生候选（模型集与来源标签同步刷新）
  watch(() => engineStore.capability?.llm?.effective, () => { void loadModelCandidates() })
  // 切到智能体模式且尚无模型清单 → 懒加载 --list-models（immediate 覆盖初始即 agent 态）
  watch(chatMode, (m) => {
    if (m === 'agent' && agentModels.value.length === 0 && !agentModelsLoading.value) void loadAgentModels()
  }, { immediate: true })

  /** 思考耗时（秒），流式期间实时更新，完成后归零 / Thinking elapsed seconds; live during streaming, resets after done */
  const thinkingElapsed = computed(() => {
    if (!thinkingStartTime.value) return 0
    return Math.floor((Date.now() - thinkingStartTime.value) / 1000)
  })

  /** 统一建议：对话为空或 AI 正在回复时隐藏；有推断建议时用推断，否则用默认 / Unified suggestions: hidden when chat is empty or AI is replying; use inferred suggestions when available, otherwise defaults */
  const displaySuggestions = computed(() => {
    if (messages.value.length === 0) return []
    if (isLoading.value) return []
    return followUps.value.length > 0 ? followUps.value : DEFAULT_SUGGESTIONS
  })
  const injectPrompt = ref<{ items: ChatExtractedItem[]; desc: string } | null>(null)
  const verifiedChanges = ref<VerifiedChange[]>([])

  const messages = computed(() => aiSessions.activeMessages)

  /** 当前面板会话是否已建立过智能体（CLI）会话 → 后续智能体轮次自动延续多轮上下文（方案 §3.6） */
  const hasAgentSession = computed(() =>
    aiSessions.activeMessages.some(
      (m: ChatMessage) => m.role === 'assistant' && m.metadata?.engine,
    ),
  )

  watch(() => taskStore.currentTaskId, (taskId) => {
    aiSessions.setChatKey(taskId)
    followUps.value = []
    injectPrompt.value = null
    rewriteIntentPending.value = false
    rewriteNotPersisted.value = null
    summaryProposal.value = null
    notesProposal.value = null
    boardProposal.value = null
  }, { immediate: true })

  const canSend = computed(() => !isLoading.value)

  // ── 流式核心（handler 实现已下沉 useAiChatStreamCore） ──

  /** 显示数据注入提示 / Show data injection prompt */
  function showInjectPrompt(items: ChatExtractedItem[]) {
    const typeCounts: Record<string, number> = {}
    const typeLabels: Record<string, string> = {
      decision: tt('ai-panel.chat.type_decision'),
      conclusion: tt('ai-panel.chat.type_conclusion'),
    }
    items.forEach(i => { typeCounts[i.type] = (typeCounts[i.type] || 0) + 1 })
    const desc = Object.entries(typeCounts)
      .map(([type, c]) => tt('ai-panel.chat.type_count', { count: c, type: typeLabels[type] || type }))
      .join(tt('ai-panel.chat.type_join'))
    injectPrompt.value = { items, desc }
  }

  /** 生成跟进建议 / Generate follow-up suggestions */
  function generateFollowUps(text: string): FollowUpSuggestion[] {
    const t = (text || '').toLowerCase()
    const suggestions: FollowUpSuggestion[] = []

    if (/决策|任务|行动|跟进|decision|action/.test(t)) {
      suggestions.push({ text: '展开某个决策事项的详情', icon: ICON_PLUS })
      suggestions.push({ text: '按责任人分类这些决策', icon: ICON_LIST })
    }
    if (/结论|决策|决定|达成|consensus|decision/.test(t)) {
      suggestions.push({ text: '展开讨论细节', icon: ICON_SEARCH })
      suggestions.push({ text: '还有哪些未达成共识的议题？', icon: ICON_CLOCK })
    }
    if (/风险|问题|挑战|隐患|risk|issue/.test(t)) {
      suggestions.push({ text: '如何规避这些风险？', icon: ICON_PLUS })
      suggestions.push({ text: '风险优先级排序', icon: ICON_LIST })
    }
    if (/总结|摘要|纪要|summary/.test(t)) {
      suggestions.push({ text: '生成会议纪要文档', icon: ICON_LIST })
      suggestions.push({ text: '还有哪些遗漏的信息？', icon: ICON_SEARCH })
    }
    if (/发言|说话|占比|speaker/.test(t)) {
      suggestions.push({ text: '各发言人的核心观点分别是什么？', icon: ICON_SEARCH })
      suggestions.push({ text: '谁的观点存在分歧？', icon: ICON_PLUS })
    }
    if (suggestions.length === 0) {
      suggestions.push({ text: '展开说说细节', icon: ICON_SEARCH })
      suggestions.push({ text: '帮我生成会议纪要', icon: ICON_LIST })
      suggestions.push({ text: '还有哪些值得深入探讨的？', icon: ICON_PLUS })
    }
    return suggestions.slice(0, 3)
  }

  // 创建流式核心——所有 handler 实现在 useAiChatStreamCore
  const core = createStreamCore({
    // refs
    isLoading, isStreaming, thinkingStartTime, currentStreamId,
    rewriteIntentPending, rewriteNotPersisted,
    summaryProposal, notesProposal, boardProposal,
    activeEngine, tierDenial, injectPrompt, abortController,
    stages, followUps,
    // computed-like
    chatMode, sessionModel, agentEngineModel, sessionAuthTier, hasAgentSession,
    // stores
    taskStore, realtimeStore, aiSessions, agentStore, insights,
    // helpers
    tt, getLocale, ensureSessionTier, maybeAutoTitle,
    showInjectPrompt, generateFollowUps,
    notifyBoardWritten, boardIdOf, isBoardWriteCall, isBoardWriteResult,
    notifyTaskWritten, writeDomainsOf, fetchNotes,
  })
  const sendRaw = core.sendRaw
  const sendWithQuote = core.sendWithQuote
  const stopGeneration = core.stopGeneration

  /** 执行后端返回的动作 / Execute action returned by backend */
  async function executeAction(action: ChatAction) {
    const d = action.data || {}

    switch (action.name) {
      case 'record_start': {
        const tid = d.task_id as string
        if (!tid) break
        if (taskStore.currentTaskId && (taskStore.currentTask?.status === 'recording' || taskStore.currentTask?.status === 'paused') && taskStore.currentTaskId !== tid) {
          showToast(tt('ai-panel.chat.duplicate_record'), 'warn')
        } else {
          // [状态同步] AI 触发录音后刷新任务列表 / [State Sync] Refresh task list after AI triggers recording
          await taskStore.loadTasks()
          taskStore.selectTask(tid)
          router.push(`/recording/${tid}`)
        }
        break
      }
      case 'record_stop':
      case 'record_pause':
      case 'record_resume': {
        // [状态同步] AI 触发录音操作后刷新任务列表 / [State Sync] Refresh task list after AI triggers recording operations
        taskStore.loadTasks()
        break
      }
      case 'retranscribe': {
        const tid = d.task_id as string
        if (tid) {
          taskStore.selectTask(tid)
          // /processing 路由已不存在（i18n 里的 processing 命名空间是残留）。
          // 重新转写的进行中状态由 GeneratingView 的轮询内联处理。
          // The /processing route no longer exists; GeneratingView renders the
          // in-progress state via its own polling.
          router.push(`/meeting/${tid}`)
        }
        break
      }
      case 'retry_summary': {
        const tid = d.task_id as string
        if (tid) {
          taskStore.selectTask(tid)
          router.push(`/meeting/${tid}`)
        }
        break
      }
      case 'create_theme': {
        const name = d.theme_name as string || tt('ai-panel.chat.custom_theme')
        const hue = d.accent_hue as number || 255
        showToast(tt('ai-panel.chat.theme_created', { name, hue }), 'success')
        break
      }
    }
  }

  /** 执行注入 / Execute injection */
  async function doInjectAll() {
    if (!injectPrompt.value || !taskStore.currentTaskId) return
    const items = injectPrompt.value.items
    try {
      await injectItems(taskStore.currentTaskId, items)
      showToast(tt('ai-panel.chat.injected', { count: items.length }), 'success')
      injectPrompt.value = null
    } catch {
      showToast(tt('ai-panel.chat.inject_failed'), 'error')
    }
  }

  /** 生成校验变化的可读描述 / Generate readable description of verified changes */
  function formatChangeDescription(change: VerifiedChange): string {
    const fieldLabels: Record<string, string> = {
      title: '标题',
      content: '内容',
      assignee: '责任人',
      deadline: '截止时间',
      status: '状态',
      priority: '优先级',
    }
    const label = fieldLabels[change.field] || change.field
    const oldVal = change.old ?? '空'
    const newVal = change.new ?? '空'
    return `${label}「${oldVal}」→「${newVal}」`
  }

  /** 清除对话 / Clear conversation */
  function clearConversation() {
    aiSessions.clearCurrentSession()
    followUps.value = []
    injectPrompt.value = null
    verifiedChanges.value = []
  }

  /** 重试最后一条消息 / Retry last message */
  async function retryLast(originalText: string) {
    await sendRaw(originalText)
  }

  /** 编辑已发消息后再发送：截断该消息（含）之后全部内容，以轮级覆盖重发，不改全局设置。
      原消息附件随消息保留重发（截断前捕获）。 */
  async function editAndResend(index: number, text: string, override?: CoreSendOverride) {
    if (isLoading.value) return
    if (index < 0 || index >= aiSessions.activeMessages.length) return
    const originalAttachments = aiSessions.activeMessages[index]?.attachments
    aiSessions.activeMessages.splice(index)
    await sendRaw(text, override, originalAttachments)
  }

  return {
    messages, isLoading, isStreaming, thinkingElapsed, stages, followUps, displaySuggestions, injectPrompt, verifiedChanges, canSend, formatChangeDescription,
    sendRaw, sendWithQuote, stopGeneration, executeAction,
    doInjectAll, clearConversation, retryLast, editAndResend,
    chatMode, setChatMode, activeEngine, hasAgentSession,
    // 授权档位（会话快照；ComposerBar 档位菜单 + 403 拒绝卡）
    pendingAuthTier, sessionAuthTier, tierDenial, tierMenuSignal,
    setPendingAuthTier, startNewSession, requestTierMenu,
    rewriteIntentPending, rewriteNotPersisted, setRewriteIntent, setBoardCoCreate,
    summaryProposal, acceptSummaryProposal: proposal.acceptSummaryProposal, rejectSummaryProposal: proposal.rejectSummaryProposal,
    openSummaryPreview: proposal.openSummaryPreview,
    notesProposal, acceptNotesProposal: notesProposalStore.acceptNotesProposal,
    rejectNotesProposal: notesProposalStore.rejectNotesProposal,
    openNotesPreview: notesProposalStore.openNotesPreview,
    boardProposal, acceptBoardProposal: boardProposalStore.acceptBoardProposal,
    rejectBoardProposal: boardProposalStore.rejectBoardProposal,
    // 使用面闭环（REQ-EXPERT-MODE §2.3） / usage-surface loop
    sessionModel, setSessionModel: engineStore.setSessionModel,
    modelCandidates, detailModelLabel, cliProbe, agentEngineEnabled, agentAvailable,
    refreshCliProbe: loadCliProbe,
    // 智能体模式就地切换引擎模型（写 chat_engine.model）
    agentEngineId, agentEngineModel, agentEngineName, agentModels, agentModelsReason, agentModelsLoading,
    loadAgentModels, setAgentModel,
  }
}
