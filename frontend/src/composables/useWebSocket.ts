/**
 * 实时转写 WebSocket composable / Realtime transcript WebSocket composable
 *
 * 连接 /ws/transcript/{task_id}，接收实时转写消息。 / Connects to /ws/transcript/{task_id}; receives realtime transcript messages.
 */
import { ref, onUnmounted } from 'vue'
import { useRealtimeStore } from '@/stores/realtime'
import { getLocale } from '@/i18n'

/** 口语清理单条规则流水（与后端 core.transcript_cleanup 的 ops 契约一致） / One cleanup op record */
export interface CleanOp {
  /** filler=填充词删除 dup=口吃合并 punct=标点整理 */
  r: 'filler' | 'dup' | 'punct'
  n: number
  items?: string[]
}

export interface TranscriptLine {
  speaker_id: number
  speaker_name: string
  /** 逐字稿原文，永不改写（引用/追责锚点） / Verbatim text, never rewritten */
  text: string
  /** 本地规则清理版（仅发生变化的句子/段落才挂键） / Local-rule cleaned text (only present when changed) */
  clean_text?: string
  clean_ops?: CleanOp[]
  begin_time?: number
  end_time?: number
  isFinal: boolean
}

export interface SummaryUpdate {
  content: string
}

export interface ChapterItem {
  id: number
  title: string
  start_ms: number
  end_ms: number
  summary?: string
  key_points?: string[]
}

export interface PresenceWarning {
  level: 'gentle' | 'urgent'
  silent_minutes: number
  countdown_seconds: number
}

export interface AutoStopped {
  reason: string
  duration: number
  message: string
}

export interface TranslationEntry {
  index: number
  original_text: string
  translated_text: string
  speaker_id: number
  speaker_name: string
  begin_time: number
  end_time: number
}

/** 段落合并时间阈值（同一说话人连续句子间隔 < 此值则合并为段落） / Paragraph merge gap threshold (merge consecutive sentences from same speaker if gap < this) */
const PARAGRAPH_MERGE_GAP_MS = 3000

/** 段落合并长度上限（超过此字数不再合并，强制另起段落，防单人长发言撑出文字墙） / Paragraph merge length cap (force new paragraph beyond this, avoid wall-of-text on long monologues) */
const PARAGRAPH_MAX_CHARS = 150

export function useWebSocketTranscript() {
  const lines = ref<TranscriptLine[]>([])
  const partialText = ref('')
  const listening = ref(false)
  const summary = ref('')
  const chapters = ref<ChapterItem[]>([])
  const connected = ref(false)
  const error = ref('')
  const speakerCount = ref(0)
  const speakerNames = ref<string[]>([])
  const summaryCountdownSec = ref(-1)
  const summaryPaused = ref(false)  // 由后端 summary_status 消息驱动 / Driven by backend summary_status messages
  const volumeWarning = ref('')  // '' | 'low'
  const presenceWarning = ref<PresenceWarning | null>(null)
  const autoStopped = ref<AutoStopped | null>(null)

  // 说话人绑定更新回调（供外部组件注册，同步本地绑定映射表） / Speaker bound callback (registered by external components to sync local binding map)
  let onSpeakerBoundCb: ((speakerId: number, speakerUuid: string, speakerName: string) => void) | null = null
  // 翻译回调（供 useTranslation composable 注册） / Translation callback (registered by useTranslation composable)
  let onTranslationUpdateCb: ((translations: TranslationEntry[]) => void) | null = null
  let onTranslationStatusCb: ((msg: { status: string; target_lang: string }) => void) | null = null

  /** 注册 speaker_bound 事件回调 / Register speaker_bound event callback */
  function onSpeakerBound(cb: (speakerId: number, speakerUuid: string, speakerName: string) => void) {
    onSpeakerBoundCb = cb
  }

  /** 注册翻译更新回调 / Register translation update callback */
  function onTranslationUpdate(cb: (translations: TranslationEntry[]) => void) {
    onTranslationUpdateCb = cb
  }

  /** 注册翻译状态回调 / Register translation status callback */
  function onTranslationStatus(cb: (msg: { status: string; target_lang: string }) => void) {
    onTranslationStatusCb = cb
  }

  let ws: WebSocket | null = null
  let wsRetryTimer: ReturnType<typeof setTimeout> | null = null
  const wsRetryCount = ref(0)
  const MAX_WS_RETRIES = 8

  /** 连接 WebSocket（支持自动重连） / Connect WebSocket (supports auto-reconnect) */
  function connect(taskId: string) {
    // 清除旧的重连定时器 / Clear old reconnect timer
    if (wsRetryTimer) { clearTimeout(wsRetryTimer); wsRetryTimer = null }
    disconnect()
    error.value = ''

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const locale = getLocale().replace('-', '_')
    const url = `${protocol}//${location.host}/ws/transcript/${taskId}?locale=${locale}`

    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
      // 连接成功，重置重连计数 / Connected; reset reconnect counter
      wsRetryCount.value = 0
      if (wsRetryTimer) { clearTimeout(wsRetryTimer); wsRetryTimer = null }
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        handleMessage(msg)
      } catch (e) {
        console.error('[WS] message parse failed:', e)
      }
    }

    ws.onerror = () => {
      error.value = 'Connection error'
      connected.value = false
    }

    ws.onclose = () => {
      connected.value = false
      // 区分主动断开（disconnect() 已将 ws 置 null）和意外断开 / Distinguish intentional disconnect (disconnect() set ws to null) from unexpected
      if (!ws || wsRetryCount.value >= MAX_WS_RETRIES) return
      // 指数退避重连：2s → 4s → 8s → 16s → 30s（上限） / Exponential backoff reconnect: 2s → 4s → 8s → 16s → 30s (cap)
      wsRetryCount.value++
      const delay = Math.min(2000 * Math.pow(2, wsRetryCount.value - 1), 30000)
      console.warn(`[WS] 意外断开，${delay}ms 后第 ${wsRetryCount.value} 次重连...`)
      wsRetryTimer = setTimeout(() => {
        connect(taskId)
      }, delay)
    }
  }

  function handleMessage(msg: Record<string, unknown>) {
    const type = msg.type as string
    const rtStore = useRealtimeStore()

    // 取清理层字段（仅后端实际挂键时透传） / Pick cleanup-layer fields only when backend sends them
    const pickClean = (): Pick<TranscriptLine, 'clean_text' | 'clean_ops'> => {
      if (typeof msg.clean_text === 'string') {
        return {
          clean_text: msg.clean_text,
          ...(Array.isArray(msg.clean_ops) ? { clean_ops: msg.clean_ops as CleanOp[] } : {}),
        }
      }
      return {}
    }

    switch (type) {
      case 'history':
        rtStore.push({
          text: msg.text as string,
          speaker_id: msg.speaker_id as number,
          begin_time: msg.begin_time as number || 0,
          end_time: msg.end_time as number || 0,
        })
        // 历史句子回放（同样执行段落合并） / History sentence playback (also apply paragraph merging)
        mergeOrAppendLine({
          speaker_id: msg.speaker_id as number,
          speaker_name: msg.speaker_name as string || '',
          text: msg.text as string,
          begin_time: msg.begin_time as number,
          end_time: msg.end_time as number,
          isFinal: true,
          ...pickClean(),
        })
        break

      case 'partial':
        // 临时识别结果 → 仅标记「正在聆听」，不显示逐字流式文本 / Partial result → only mark "listening", no streaming text display
        listening.value = true
        // 转写已有文字 → 麦克风正常，自动关闭音量警告 / Transcript has text → mic is working; auto-dismiss volume warning
        if (volumeWarning.value) volumeWarning.value = ''
        break

      case 'sentence':
        rtStore.push({
          text: msg.text as string,
          speaker_id: msg.speaker_id as number,
          begin_time: msg.begin_time as number || 0,
          end_time: msg.end_time as number || 0,
        })
        // 定稿句子 — 清除 listening，执行段落合并 / Finalized sentence — clear listening, apply paragraph merging
        listening.value = false
        partialText.value = ''
        // 转写已有文字 → 麦克风正常，自动关闭音量警告 / Transcript has text → mic is working; auto-dismiss volume warning
        if (volumeWarning.value) volumeWarning.value = ''
        mergeOrAppendLine({
          speaker_id: msg.speaker_id as number,
          speaker_name: msg.speaker_name as string || '',
          text: msg.text as string,
          begin_time: msg.begin_time as number,
          end_time: msg.end_time as number,
          isFinal: true,
          ...pickClean(),
        })
        break

      case 'speaker_bound':
        // 说话人绑定更新 — 更新已有行的 speaker_name，并通知外部同步绑定映射表 / Speaker bound update — update speaker_name in existing lines; notify external to sync binding map
        const sid = msg.speaker_id as number
        const name = msg.speaker_name as string
        const uuid = msg.speaker_uuid as string || ''
        for (const line of lines.value) {
          if (line.speaker_id === sid) {
            line.speaker_name = name
          }
        }
        // 通知外部组件同步绑定映射（realtimeSpeakerBindings） / Notify external components to sync binding map (realtimeSpeakerBindings)
        if (onSpeakerBoundCb && uuid) {
          onSpeakerBoundCb(sid, uuid, name)
        }
        break

      case 'summary_update':
        summary.value = msg.content as string
        break

      case 'chapters_update':
        chapters.value = msg.chapters as ChapterItem[]
        break

      case 'speaker_count_update':
        speakerCount.value = msg.count as number
        speakerNames.value = (msg.speakers as string[]) || []
        break

      case 'summary_countdown':
        summaryCountdownSec.value = msg.remaining as number
        break

      case 'summary_status': {
        const status = msg.status as string
        // 后端推送的 paused/idle/stopped 状态同步到前端 / Backend-pushed paused/idle/stopped status synced to frontend
        summaryPaused.value = (status === 'paused' || status === 'stopped')
        // 同步倒计时剩余秒数（暂停/停止时为 0，恢复时为剩余秒数） / Sync countdown remaining seconds (0 when paused/stopped; remaining when resumed)
        if (typeof msg.remaining === 'number') {
          summaryCountdownSec.value = msg.remaining as number
        }
        break
      }

      case 'volume_warning':
        volumeWarning.value = (msg.level as string) || 'low'
        break

      case 'presence_warning':
        presenceWarning.value = {
          level: (msg.level as 'gentle' | 'urgent') || 'gentle',
          silent_minutes: (msg.silent_minutes as number) || 0,
          countdown_seconds: (msg.countdown_seconds as number) || 120,
        }
        break

      case 'auto_stopped':
        autoStopped.value = {
          reason: (msg.reason as string) || 'unknown',
          duration: (msg.duration as number) || 0,
          message: (msg.message as string) || '',
        }
        break

      case 'translation_update':
        onTranslationUpdateCb?.(msg.translations as TranslationEntry[])
        break

      case 'translation_status':
        onTranslationStatusCb?.({
          status: (msg.status as string) || '',
          target_lang: (msg.target_lang as string) || '',
        })
        break

      case 'error':
        error.value = msg.message as string
        break

      case 'ended':
        connected.value = false
        break
    }
  }

  /** 段落合并：同一说话人连续句子间隔 < 阈值且未超长则合并文本，否则新建段落 / Paragraph merge: merge text if same speaker within gap and under length cap, otherwise create new paragraph */
  function mergeOrAppendLine(newLine: TranscriptLine) {
    const last = lines.value[lines.value.length - 1]
    if (
      last &&
      last.speaker_id === newLine.speaker_id &&
      last.isFinal &&
      last.text.length < PARAGRAPH_MAX_CHARS &&
      newLine.begin_time &&
      (last.end_time || 0) > 0 &&
      (newLine.begin_time - (last.end_time || 0)) < PARAGRAPH_MERGE_GAP_MS
    ) {
      // 合并到上一段落（追加文本 + 更新时间戳） / Merge into previous paragraph (append text + update timestamps)
      const prevRaw = last.text
      last.text += newLine.text
      last.end_time = newLine.end_time
      // 清理层按句拼接：只要任一句有清理结果，段落即挂 clean_text；
      // 未变化的句子用其原文参与拼接 / Clean layer is joined per-sentence;
      // an unchanged sentence contributes its verbatim text.
      if (last.clean_text !== undefined || newLine.clean_text !== undefined) {
        last.clean_text = (last.clean_text ?? prevRaw) + (newLine.clean_text ?? newLine.text)
        const mergedOps: CleanOp[] = [...(last.clean_ops ?? []), ...(newLine.clean_ops ?? [])]
        if (mergedOps.length) last.clean_ops = mergedOps
        else delete last.clean_ops
      }
    } else {
      lines.value.push(newLine)
    }
  }

  /** 发送心跳消息（含存在性评分） / Send heartbeat message (with presence score) */
  function sendHeartbeat(score: number, userAck = false) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'heartbeat',
        presence_score: score,
        user_ack: userAck,
      }))
    }
  }

  /** 发送翻译控制命令 / Send translation control command */
  function sendTranslationControl(action: string, targetLang?: string) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'translation_control',
        action,
        target_lang: targetLang,
      }))
    }
  }

  /** 清除存在性警告（用户确认后调用） / Clear presence warning (called after user confirmation) */
  function clearPresenceWarning() {
    presenceWarning.value = null
  }

  /** 断开连接（主动断开，不触发重连） / Disconnect (intentional; doesn't trigger reconnect) */
  function disconnect() {
    // 清除重连定时器 / Clear reconnect timer
    if (wsRetryTimer) { clearTimeout(wsRetryTimer); wsRetryTimer = null }
    wsRetryCount.value = 0
    if (ws) {
      ws.close()
      ws = null
    }
    connected.value = false
    partialText.value = ''
    listening.value = false
    speakerCount.value = 0
    speakerNames.value = []
    summaryCountdownSec.value = -1
    // 注意：不重置 summaryPaused，因为录音暂停时 WebSocket 会断开， / Note: don't reset summaryPaused; WebSocket disconnects on recording pause,
    // 但后端总结可能已联动暂停，该状态在重连后通过回放更新 / but backend summary may have been paused; state updated via history playback on reconnect
    volumeWarning.value = ''
    presenceWarning.value = null
    autoStopped.value = null
  }

  /** 重置所有数据 / Reset all data */
  function reset() {
    disconnect()
    lines.value = []
    partialText.value = ''
    listening.value = false
    summary.value = ''
    chapters.value = []
    error.value = ''
    speakerCount.value = 0
    speakerNames.value = []
    summaryCountdownSec.value = -1
    summaryPaused.value = false
    volumeWarning.value = ''
    presenceWarning.value = null
    autoStopped.value = null
  }

  onUnmounted(disconnect)

  return {
    lines, partialText, listening, summary, chapters, connected, error,
    speakerCount, speakerNames, summaryCountdownSec, summaryPaused, volumeWarning,
    presenceWarning, autoStopped, wsRetryCount,
    connect, disconnect, reset, sendHeartbeat, sendTranslationControl,
    clearPresenceWarning, onSpeakerBound, onTranslationUpdate, onTranslationStatus,
  }
}
