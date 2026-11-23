/**
 * AI 聊天流式处理核心 / AI chat streaming core
 *
 * sendRaw 及其内部所有 stream handler 实现。
 * 依赖通过 deps 对象注入，与 Vue 组件解耦（便于单测、减少 facade 体积）。
 */
import { sendMessageStream, cancelStream } from '@/api/chat'
import type { AttachmentMeta, ChatExtractedItem, ChatMessage, AgentStage, ChatScope } from '@/api/chat'
import type { AiSession } from '@/stores/aiSessions'

/** 授权档位（与后端 _VALID_TIERS 对齐）：只读 / 提案写入 / 完全任务 */
export type AuthTier = 'readonly' | 'workspace_write' | 'full_task'

/** 轮级发送覆盖（已发消息编辑再发送）：仅作用本轮，不写全局设置 */
export interface SendOverride {
  mode?: 'qa' | 'agent'
  model?: string
  agentModel?: string
  scope?: ChatScope
}

const AI_MAX_CONTEXT = 20

/** 工具回执可能是 JSON 字符串也可能已是对象；解析失败返回空对象（不抛错不阻断事件流） */
export function safeJsonParse(value: string | unknown): Record<string, unknown> {
  if (value && typeof value === 'object') return value as Record<string, unknown>
  if (typeof value !== 'string' || !value.trim()) return {}
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : {}
  } catch {
    return {}
  }
}

/** 智能体引擎文案解析：后端事件携 hint_key（ai-panel 命名空间）时按当前 locale 翻译，
 *  键缺失/无键时回退后端下发的中文兜底文案（历史兼容）。 */
export function resolveEngineText(
  hintKey: string | undefined, fallback: string,
  params?: Record<string, unknown>, ttFn: (key: string, params?: Record<string, unknown>) => string = (k) => k,
): string {
  if (!hintKey) return fallback
  const translated = ttFn(`ai-panel.${hintKey}`, params || {})
  return translated && translated !== `ai-panel.${hintKey}` ? translated : fallback
}

/** 剥 MCP 工具全名前缀：mcp__<server>__<tool> → tool（内置引擎直接给裸名） */
function bareToolName(name: string): string {
  if (!name) return ''
  const i = name.lastIndexOf('__')
  return i >= 0 ? name.slice(i + 2) : name
}

interface Deps {
  // refs
  isLoading: { value: boolean }
  isStreaming: { value: boolean }
  thinkingStartTime: { value: number }
  currentStreamId: { value: string }
  rewriteIntentPending: { value: boolean }
  rewriteNotPersisted: { value: { text: string } | null }
  summaryProposal: { value: { baseline: string; proposed: string } | null }
  notesProposal: { value: { baseline: string; proposed: string } | null }
  boardProposal: { value: { board_id: string; title: string; reason: string } | null }
  activeEngine: { value: { display_name: string; auth_tier: string; auto_selected: boolean } | null }
  tierDenial: { value: { tool: string; summary: string } | null }
  injectPrompt: { value: { items: ChatExtractedItem[]; desc: string } | null }
  abortController: { value: AbortController | null }
  stages: { value: AgentStage[] }
  followUps: { value: { text: string; icon: string }[] }
  // computed-like refs
  chatMode: { value: 'qa' | 'agent' }
  chatScope: { value: ChatScope }
  sessionModel: { value: string }
  agentEngineModel: { value: string }
  sessionAuthTier: { value: AuthTier }
  hasAgentSession: { value: boolean }
  // stores
  taskStore: {
    currentTaskId: string | null
    currentTask?: { user_summary?: string | null; summary?: string | null } | null
  }
  realtimeStore: { getSnapshot: () => unknown }
  aiSessions: {
    activeMessages: ChatMessage[]
    activeSession: AiSession | null
    persist: () => void
    currentBucket: { activeSessionId?: unknown }
  }
  agentStore: { activeAgent?: unknown }
  insights: {
    lastViewedDiagram: { value?: unknown }
    setChatDiagram: (d: string) => void
  }
  // helpers
  tt: (key: string, params?: Record<string, unknown>) => string
  getLocale: () => string
  ensureSessionTier: () => void
  maybeAutoTitle: (session: AiSession | undefined) => void
  showInjectPrompt: (items: ChatExtractedItem[]) => void
  generateFollowUps: (text: string) => { text: string; icon: string }[]
  notifyBoardWritten: (args: { tool?: string; board_id?: string }) => void
  boardIdOf: (obj: unknown) => string
  isBoardWriteCall: (name: string, args?: Record<string, unknown> | null) => boolean
  isBoardWriteResult: (result: { name?: string; tool_use_id?: string }, writeIds: Set<string>) => boolean
  notifyTaskWritten: (args: { tool: string }) => void
  writeDomainsOf: (name?: string | null) => unknown[] | null
  fetchNotes: (taskId: string) => Promise<string>
}

export interface StreamCore {
  sendRaw: (text: string, override?: SendOverride, attachments?: AttachmentMeta[]) => Promise<void>
  sendWithQuote: (text: string, quoteText: string, quoteSource: string) => Promise<void>
  stopGeneration: () => void
}

export function createStreamCore(deps: Deps): StreamCore {
  const {
    isLoading, isStreaming, thinkingStartTime, currentStreamId,
    rewriteIntentPending, rewriteNotPersisted,
    summaryProposal, notesProposal, boardProposal,
    activeEngine, tierDenial, injectPrompt, abortController,
    stages, followUps,
    chatMode, chatScope, sessionModel, agentEngineModel, sessionAuthTier, hasAgentSession,
    taskStore, realtimeStore, aiSessions, agentStore, insights,
    tt, getLocale, ensureSessionTier, maybeAutoTitle,
    showInjectPrompt, generateFollowUps,
    notifyBoardWritten, boardIdOf, isBoardWriteCall, isBoardWriteResult,
    notifyTaskWritten, writeDomainsOf, fetchNotes,
  } = deps

  /** 发送原始文本消息（流式输出） / Send raw text message (streaming output)
   *  override：编辑再发送时的轮级覆盖，缺省取全局模式与模型，且不回写全局 */
  async function sendRaw(text: string, override?: SendOverride, attachments?: AttachmentMeta[]) {
    if ((!text && (!attachments || attachments.length === 0)) || isLoading.value) return

    // 本轮实际生效口径：override 优先于全局（轮级覆盖，退出后全局不变）
    const effectiveMode: 'qa' | 'agent' = override?.mode ?? chatMode.value
    const effectiveQaModel = override?.model ?? sessionModel.value
    const effectiveAgentModel = override?.agentModel ?? agentEngineModel.value
    const effectiveScope: ChatScope = override?.scope ?? chatScope.value
    // 会话级授权快照：发送前确保本会话已锁定档位（同一场纪要不允许前后口径不一）
    if (effectiveMode === 'agent') ensureSessionTier()
    const effectiveTier = sessionAuthTier.value

    const msgs = aiSessions.activeMessages
    msgs.push({
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
      // @附件 随消息落库：气泡渲染与编辑再发送都能复用
      attachments: attachments && attachments.length ? attachments : undefined,
      // 发送快照落消息：下次编辑直接回填，旧消息无快照走推断
      sendOptions: {
        mode: effectiveMode,
        model: effectiveMode === 'qa' ? effectiveQaModel : '',
        agentModel: effectiveMode === 'agent' ? effectiveAgentModel : '',
        scope: effectiveScope,
      },
    })
    if (msgs.length > AI_MAX_CONTEXT * 2) {
      aiSessions.activeMessages = msgs.slice(-AI_MAX_CONTEXT * 2)
    }
    // 捕获发送时的会话对象：命名请求在途期间用户可能切桶，落名仍须落在正确的会话上
    const sessionAtSend = aiSessions.activeSession

    isLoading.value = true
    isStreaming.value = false
    thinkingStartTime.value = Date.now()
    injectPrompt.value = null
    activeEngine.value = null
    // 新一轮清上轮拒绝卡（卡片只属于最近一个智能体轮）
    tierDenial.value = null

    const ctrl = new AbortController()
    abortController.value = ctrl
    // 本轮流标识（智能体模式真取消用）/ per-turn stream id for hard cancel
    const streamId = (globalThis.crypto?.randomUUID?.() ?? `s-${Date.now()}-${Math.random().toString(36).slice(2)}`)
    currentStreamId.value = streamId
    // 轮级意图捕获：发出即消费（不常驻），避免后续闲聊轮被误标"改写意图"而横幅误报
    const turnIntent = rewriteIntentPending.value
    rewriteIntentPending.value = false
    rewriteNotPersisted.value = null
    // 新一轮开始：清上一轮遗留的纪要提案（提案卡只渲染在末条 assistant 气泡下，新轮后自然失效）
    summaryProposal.value = null
    notesProposal.value = null
    boardProposal.value = null
    let turnHasProposal = false
    let toolWriteOk = false

    const turnMessages = aiSessions.activeMessages
    // stages.value 与 assistantMsg.stages 共享同一数组引用（修改一处即同步到 UI 与持久化）
    stages.value = []
    turnMessages.push({
      role: 'assistant', content: '', timestamp: new Date().toISOString(),
      stages: stages.value, executionId: streamId, executionState: 'running',
    })
    // 捕获本轮响应式消息，切换会话后仍写原消息，不按当前会话的数组下标寻址。
    const assistantMsg = turnMessages[turnMessages.length - 1]!
    const liveMsg = (): ChatMessage => assistantMsg
    const turnStages = assistantMsg.stages!
    const TRACE_LIMIT = 16000

    function finishExecution(state: NonNullable<ChatMessage['executionState']>) {
      // 兼容旧后端 error → done：协议收尾不得把消息级失败改成成功。
      if (state === 'done' && assistantMsg.executionState !== 'running') return
      assistantMsg.executionState = state
      for (const stage of turnStages) {
        if (stage.status !== 'running') continue
        // 未收到工具结果，不等同于成功；并行工具也只能由各自结果确认。
        stage.status = state === 'stopped' ? 'stopped'
          : state === 'done' && stage.type !== 'tool_call' && stage.type !== 'board_retry' ? 'done' : 'interrupted'
      }
      aiSessions.persist()
    }

    function recordError(detail: string, state: 'error' | 'interrupted' = 'error') {
      if (!assistantMsg.content) assistantMsg.content = `${tt('ai-panel.chat_error_prefix')}${detail}`
      turnStages.push({
        type: 'generating', label: tt('ai-panel.execution.error_label'), status: state,
        output: detail.slice(0, TRACE_LIMIT), outputTruncated: detail.length > TRACE_LIMIT,
      })
      finishExecution(state)
    }

    // 本轮内「写板」工具调用的 id 集（读语义不带 html，不计入）：
    // 两引擎的 tool_result 都只带 tool_use_id（CLI 侧不带 name），故先按 call 的 args 定性、再按 id 配对结果
    const boardWriteIds = new Set<string>()

    try {
      const histSlice = aiSessions.activeMessages.slice(-AI_MAX_CONTEXT)

      await sendMessageStream(text, {
        task_id: taskStore.currentTaskId || undefined,
        history: histSlice,
        realtime_transcripts: realtimeStore.getSnapshot() as import('@/api/chat').ChatOptions['realtime_transcripts'],
        role: (agentStore.activeAgent as string | undefined) || undefined,
        current_diagram: (insights.lastViewedDiagram.value as string | undefined) || undefined,
        engine: effectiveMode === 'qa' ? undefined : effectiveMode,
        // 授权档位（会话快照）：仅智能体轮透传，后端请求级优先级最高；问答轮无工具，档位不参与
        auth_tier: effectiveMode === 'agent' ? effectiveTier : undefined,
        // 会话级模型透传（REQ-EXPERT-MODE §2.3）：'' = 跟随详情不传
        model: effectiveMode === 'qa' ? (effectiveQaModel || undefined) : undefined,
        // 智能体轮级 CLI 模型覆盖：正常发送恒为 undefined（后端读全局），编辑再发送才带值
        agentModel: effectiveMode === 'agent' ? (effectiveAgentModel || undefined) : undefined,
        stream_id: streamId,
        chat_session_id: (aiSessions.currentBucket.activeSessionId as string | undefined) || undefined,
        resume_session: effectiveMode !== 'qa' && hasAgentSession.value,
        attachments,
        scope: effectiveScope,
        signal: ctrl.signal,
      }, {
        onToken(token: string) {
          liveMsg().content += token
          isStreaming.value = true
          // 不在首个 token 时清空 stages，保留到完成后折叠 / Keep stages visible during streaming, collapse after done
        },
        onStage(stageData) {
          // 更新或添加思考阶段 / Update or add thinking stage
          // 智能体引擎文案 i18n 化：携 hint_key 时按当前 locale 翻译，否则用 label 兜底
          const stageLabel = resolveEngineText(stageData.hint_key, stageData.label, stageData.hint_params, tt)
          if (stageData.stage === 'board_retry') {
            const retry = turnStages.find(s => s.type === 'board_retry')
            if (retry) {
              retry.label = stageLabel
              retry.status = stageData.status || 'running'
            } else {
              turnStages.push({ type: 'board_retry', label: stageLabel, status: stageData.status || 'running' })
            }
            aiSessions.persist()
            return
          }
          const existing = stages.value.find(s => s.type === stageData.stage && s.status === 'running')
          if (existing) {
            existing.label = stageLabel
          } else if (stageData.stage === 'thinking' || stageData.stage === 'generating') {
            // 将之前的 running 阶段标记为 done / Mark previous running stages as done
            stages.value.forEach(s => {
              if (s.status === 'running' && s.type !== 'tool_call' && s.type !== 'board_retry') s.status = 'done'
            })
            stages.value.push({
              type: stageData.stage as 'thinking' | 'generating',
              label: stageLabel,
              status: 'running',
            })
          }
          aiSessions.persist()
        },
        onToolCall(tool) {
          // 洞察板自动同步：记住本轮哪些调用是「写板」，待其结果成功回传时广播板已更新
          if (isBoardWriteCall(tool.name, tool.args)) boardWriteIds.add(tool.id || `name:${tool.name}`)
          // 纪要提案式改写：propose_summary 不落盘，只把 proposed 全文（携在 tool_call.args）+ 当前基线挂成待确认提案
          if (bareToolName(tool.name) === 'propose_summary') {
            const proposed = String(tool.args?.summary ?? '')
            const ct = taskStore.currentTask as unknown as { user_summary?: string; summary?: string } | null
            const baseline = ct ? (ct.user_summary != null ? ct.user_summary : (ct.summary || '')) : ''
            if (proposed.trim()) {
              summaryProposal.value = { baseline, proposed }
              turnHasProposal = true
            }
          }
          // 随记提案式改写（propose_notes）：后端不落盘，只把建议全文挂成待确认提案。
          // 基线取服务端 user_notes（task 快照不含随记），因此需一次异步回拉；回拉失败按空基线降级，
          // 宁可 diff 多显示几行也不能不给出建议
          if (bareToolName(tool.name) === 'propose_notes') {
            const proposed = String(tool.args?.notes ?? '')
            const taskId = taskStore.currentTaskId
            if (proposed.trim() && taskId) {
              turnHasProposal = true
              void fetchNotes(taskId)
                .then((b) => { notesProposal.value = { baseline: b || '', proposed } })
                .catch(() => { notesProposal.value = { baseline: '', proposed } })
            }
          }
          // 建板提案（create_insight_board）：后端不落盘，只把标题/理由挂成确认卡。
          // 真正建板发生在用户点「接受」后（useBoardProposal → POST .../boards）。
          if (bareToolName(tool.name) === 'create_insight_board') {
            const title = String(tool.args?.title ?? '').trim()
            if (title) {
              boardProposal.value = {
                board_id: String(tool.args?.board_id ?? '').trim(),
                title,
                reason: String(tool.args?.reason ?? '').trim(),
              }
              turnHasProposal = true
            }
          }
          // 将之前的 running 阶段标记为 done / Mark previous running stages as done
          stages.value.forEach(s => {
            if (s.status === 'running' && s.type !== 'tool_call' && s.type !== 'board_retry') s.status = 'done'
          })
          const input = JSON.stringify(tool.args || {}, null, 2)
          stages.value.push({
            type: 'tool_call',
            // 双语标签：manifest 同时下发 label(zh)+label_en，按当前 locale 选取（多 CLI 国际化）
            label: getLocale() === 'en' && tool.label_en ? tool.label_en : tool.label,
            label_en: tool.label_en,
            icon: tool.icon,
            status: 'running',
            id: tool.id,
            name: tool.name,
            detail: input.slice(0, 200),
            input: input.slice(0, TRACE_LIMIT),
            inputTruncated: input.length > TRACE_LIMIT,
          })
          aiSessions.persist()
        },
        onToolResult(result) {
          // 按 id 精确配对（并行工具结果乱序回传，不可靠数组下标/label）
          const candidates = turnStages.filter(s => s.type === 'tool_call' && s.status === 'running'
            && (!result.name || s.name === result.name))
          let toolStage = result.tool_use_id
            ? turnStages.find(s => s.type === 'tool_call' && s.id === result.tool_use_id)
            : candidates.length === 1 ? candidates[0] : undefined
          // 无法唯一配对时保留独立结果，不能错挂到另一个并行工具。
          if (!toolStage) {
            toolStage = { type: 'tool_result', label: result.name || tt('ai-panel.execution.output'), status: 'running', id: result.tool_use_id }
            turnStages.push(toolStage)
            toolStage = turnStages[turnStages.length - 1]!
          }
          const output = result.output ?? result.summary
          const denied = !result.success && /read[_-]only|forbidden|not.authori[sz]ed|permission.denied|needs approval|allow searching the web\?|未授权|需要授权|权限不足/i.test(output)
          toolStage.status = result.success ? 'done' : denied ? 'denied' : 'error'
          toolStage.detail = result.summary.slice(0, 200)
          // 旧后端只有 summary 时不冒充完整结果，组件明确提示。
          if (result.output !== undefined) toolStage.output = output.slice(0, TRACE_LIMIT)
          toolStage.outputTruncated = !!result.output_truncated || output.length > TRACE_LIMIT
          aiSessions.persist()
          // 档位拦截（403 read_only）：MCP 桥把 HTTP 403 正文放进 tool_result，拒绝不静默——
          // 挂拒绝卡，给出就地升档/新会话入口（见 AiChatPanel 末条气泡下的 ai-tier-deny）
          if (!result.success && /read_only|read-only|forbidden/i.test(result.summary)) {
            const deniedName = (result.name || toolStage?.name || 'tool')
              .split('__').pop() || 'tool'
            tierDenial.value = { tool: deniedName, summary: result.summary }
          }
          // 落板成功→广播：板的写入点在后端，呈现侧（同页的洞察 Tab）此前只能人工刷新
          // 多板下带 board_id（回执里那份被写的板），订阅侧才不会重拉错板
          if (result.success && isBoardWriteResult(result, boardWriteIds)) {
            notifyBoardWritten({
              tool: result.name,
              board_id: boardIdOf(safeJsonParse(result.output ?? '')) || boardIdOf(safeJsonParse(result.summary ?? '')),
            })
          }
          // 完成护栏（§5.4）：前端侧写工具成功事实（与后端 done.rewritten 双保险，任一命中即视为落盘）
          // tool_result 可能不带 name（CLI 侧），按 tool_use_id 回溯 tool_call 阶段的工具名后再剥 MCP 前缀
          if (result.success) {
            const calledStage = result.tool_use_id
              ? [...stages.value].reverse().find(s => s.type === 'tool_call' && s.id === result.tool_use_id)
              : undefined
            const bare = ((result.name || calledStage?.name || '') as string).split('__').pop() || ''
            if (bare === 'revise_insight_board') {
              // 读写双语义：只有写板调用（boardWriteIds 在 call 阶段按 args 定性）才算落盘
              if (isBoardWriteResult(result, boardWriteIds)) toolWriteOk = true
            } else if (writeDomainsOf(bare) != null) {
              // 任务数据写回（决策节点/纪要/注入）：除完成护栏事实外，还广播呈现侧重拉，
              // 不让用户看着 AI 说"已更新"却对着旧数据（§5.4）
              toolWriteOk = true
              notifyTaskWritten({ tool: bare })
            } else if (['revise_insight_board_section'].includes(bare)) {
              toolWriteOk = true
            }
          }
        },
        onEngineRoute(info) {
          // §3.9-1 路由回显：本次由智能体引擎执行（含 auto 自动选中），静默分流摧毁信任
          // 引擎名本地化：name_key 命中翻译优先（如国内版后缀），否则品牌原文
          const name = info.name_key ? tt(info.name_key) : ''
          activeEngine.value = {
            display_name: name && name !== info.name_key ? name : (info.display_name || info.engine),
            auth_tier: info.auth_tier, auto_selected: !!info.auto_selected,
          }
        },
        onDone(data) {
          const msg = liveMsg()
          msg.timestamp = new Date().toISOString()
          if (data.metadata) msg.metadata = data.metadata
          if (data.sources) msg.sources = data.sources
          // 提问范围回显：范围与检索统计随消息落库，刷新/切会话仍可见
          if (data.scope) msg.scope = data.scope
          if (data.retrieval) msg.retrieval = data.retrieval
          // 回复尾部消费方/计费回显（与后端 routing 实际判定同源）
          if (data.model_usage) msg.modelUsage = data.model_usage
          if (data.latency_ms != null) {
            msg.performance = {
              latency_ms: data.latency_ms,
              char_count: msg.content.length,
              context_block_count: data.context_block_count ?? 0,
              message_count: data.message_count ?? 0,
            }
          }
          // 有些引擎只在终帧报告拒绝；按调用 id（缺失时唯一未完成的同名工具）归档。
          for (const denial of data.permission_denials || []) {
            const candidates = turnStages.filter(s => s.type === 'tool_call' && s.name === denial.tool_name
              && ['running', 'error', 'denied'].includes(s.status))
            const target = denial.tool_use_id ? turnStages.find(s => s.id === denial.tool_use_id)
              : candidates.length === 1 ? candidates[0] : undefined
            const detail = denial.decision_reason || tt('ai-panel.execution.denied')
            if (target) {
              target.status = 'denied'
              if (!target.output) target.output = detail.slice(0, TRACE_LIMIT)
            } else {
              turnStages.push({ type: 'tool_result', label: denial.tool_name || tt('ai-panel.execution.tool'),
                status: 'denied', output: detail.slice(0, TRACE_LIMIT), outputTruncated: detail.length > TRACE_LIMIT })
            }
          }
          // 异常终态不走成功护栏、自动命名或后续建议；旧 error → done 也不覆盖。
          if (msg.executionState !== 'running') { aiSessions.persist(); return }
          if (data.cancelled || data.status === 'cancelled' || ctrl.signal.aborted) {
            if (!msg.content) msg.content = tt('ai-panel.execution.stopped_reply')
            finishExecution('stopped')
            return
          }
          if (data.error || data.status === 'error' || data.status === 'incomplete') {
            recordError(data.error || tt('ai-panel.execution.interrupted_reply'), data.status === 'incomplete' ? 'interrupted' : 'error')
            return
          }
          // 只结算仍在运行的阶段；失败、未授权及中断记录原样保留。
          finishExecution('done')

          // 完成护栏（§5.4）：改写意图轮零写回 → 显式横幅，不让用户对着旧版本猜
          // 例外：纪要本轮产出了 propose_summary 提案（turnHasProposal）= 已正确响应改写意图（待用户接受），不亮横幅
          if (effectiveMode === 'agent' && turnIntent && !turnHasProposal
              && data.metadata?.rewritten !== true && !toolWriteOk) {
            rewriteNotPersisted.value = { text }
          }

          if (data.extracted_items?.length) {
            showInjectPrompt(data.extracted_items)
          }
          // 图形化内容转发到洞察面板 / Forward diagram to insights panel
          if (data.diagram) {
            insights.setChatDiagram(data.diagram)
          }
          // 首轮完成后尝试 AI 自动命名（失败静默降级，用户手动改名后永不触发）
          maybeAutoTitle(sessionAtSend ?? undefined)
          followUps.value = generateFollowUps(msg.content)
        },
        onError(error, extra) {
          // 已写入事实与整轮失败并不冲突；错误终帧同样保留写回版本元数据。
          if (extra?.metadata) assistantMsg.metadata = extra.metadata
          const errText = resolveEngineText(extra?.hint_key, error, extra?.hint_params, tt)
          recordError(errText, extra?.status === 'incomplete' ? 'interrupted' : 'error')
        },
      })
    } catch (e: unknown) {
      if (ctrl.signal.aborted || (e instanceof Error && e.name === 'AbortError')) {
        if (!assistantMsg.content) assistantMsg.content = tt('ai-panel.execution.stopped_reply')
        finishExecution('stopped')
      } else {
        const err = e as { response?: { data?: unknown }; message?: string }
        const data = err.response?.data
        let detail = '请求失败'
        if (data && typeof data === 'object') {
          const d = data as Record<string, unknown>
          if (typeof d.detail === 'string') {
            detail = d.detail
          } else if (d.detail && typeof d.detail === 'object') {
            const dd = d.detail as Record<string, unknown>
            if (typeof dd.message === 'string') detail = dd.message
            else if (typeof dd.error === 'string') detail = dd.error
            else if (typeof dd.hint === 'string') detail = dd.hint
          } else if (typeof d.message === 'string') {
            detail = d.message
          } else if (typeof d.error === 'string') {
            detail = d.error
          }
        } else if (err.message) {
          detail = err.message
        }
        recordError(detail)
      }
    } finally {
      if (assistantMsg.executionState === 'running') {
        const state = ctrl.signal.aborted ? 'stopped' : 'interrupted'
        if (!assistantMsg.content) assistantMsg.content = tt(`ai-panel.execution.${state}_reply`)
        finishExecution(state)
      }
      isLoading.value = false
      isStreaming.value = false
      thinkingStartTime.value = 0
      abortController.value = null
      currentStreamId.value = ''
      // 消息保留原数组；立即解绑临时引用，避免延迟清空误伤下一轮。
      stages.value = []
    }
  }

  /** 发送用户输入（含引用内容） / Send user input (with quoted content) */
  async function sendWithQuote(text: string, quoteText: string, quoteSource: string) {
    if ((!text.trim() && !quoteText) || isLoading.value) return

    let fullText = text
    if (quoteText) {
      const ctx = `[用户引用了一段内容${quoteSource ? '（' + quoteSource + '）' : ''}]:\n"""${quoteText}"""\n`
      fullText = text ? ctx + '\n用户指令: ' + text : ctx + '\n请帮我处理这段引用内容'
    }

    await sendRaw(fullText)
  }

  /** 停止生成 / Stop generation */
  function stopGeneration() {
    // 智能体模式：fetch abort 不足以杀本机 CLI 子进程，必须真取消（§3.9-5）
    if (chatMode.value === 'agent' && currentStreamId.value) {
      void cancelStream(currentStreamId.value)
    }
    abortController.value?.abort()
  }

  return { sendRaw, sendWithQuote, stopGeneration }
}
