/**
 * 实时转写 WebSocket composable
 *
 * 连接 /ws/transcript/{task_id}，接收实时转写消息。
 */
import { ref, onUnmounted } from 'vue'
import { useRealtimeStore } from '@/stores/realtime'
import { getLocale } from '@/i18n'

export interface TranscriptLine {
  speaker_id: number
  speaker_name: string
  text: string
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

export function useWebSocketTranscript() {
  const lines = ref<TranscriptLine[]>([])
  const partialText = ref('')
  const summary = ref('')
  const chapters = ref<ChapterItem[]>([])
  const connected = ref(false)
  const error = ref('')
  const speakerCount = ref(0)
  const speakerNames = ref<string[]>([])
  const summaryCountdownSec = ref(-1)
  const summaryPaused = ref(false)  // 由后端 summary_status 消息驱动
  const volumeWarning = ref('')  // '' | 'low'
  const presenceWarning = ref<PresenceWarning | null>(null)
  const autoStopped = ref<AutoStopped | null>(null)

  // 说话人绑定更新回调（供外部组件注册，同步本地绑定映射表）
  let onSpeakerBoundCb: ((speakerId: number, speakerUuid: string, speakerName: string) => void) | null = null

  /** 注册 speaker_bound 事件回调 */
  function onSpeakerBound(cb: (speakerId: number, speakerUuid: string, speakerName: string) => void) {
    onSpeakerBoundCb = cb
  }

  let ws: WebSocket | null = null
  let wsRetryTimer: ReturnType<typeof setTimeout> | null = null
  const wsRetryCount = ref(0)
  const MAX_WS_RETRIES = 8

  /** 连接 WebSocket（支持自动重连） */
  function connect(taskId: string) {
    // 清除旧的重连定时器
    if (wsRetryTimer) { clearTimeout(wsRetryTimer); wsRetryTimer = null }
    disconnect()
    error.value = ''

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const locale = getLocale().replace('-', '_')
    const url = `${protocol}//${location.host}/ws/transcript/${taskId}?locale=${locale}`

    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
      // 连接成功，重置重连计数
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
      // 区分主动断开（disconnect() 已将 ws 置 null）和意外断开
      if (!ws || wsRetryCount.value >= MAX_WS_RETRIES) return
      // 指数退避重连：2s → 4s → 8s → 16s → 30s（上限）
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

    switch (type) {
      case 'history':
        rtStore.push({
          text: msg.text as string,
          speaker_id: msg.speaker_id as number,
          begin_time: msg.begin_time as number || 0,
          end_time: msg.end_time as number || 0,
        })
        // 历史句子回放
        lines.value.push({
          speaker_id: msg.speaker_id as number,
          speaker_name: msg.speaker_name as string || '',
          text: msg.text as string,
          begin_time: msg.begin_time as number,
          end_time: msg.end_time as number,
          isFinal: true,
        })
        break

      case 'partial':
        // 临时识别结果
        partialText.value = msg.text as string
        break

      case 'sentence':
        rtStore.push({
          text: msg.text as string,
          speaker_id: msg.speaker_id as number,
          begin_time: msg.begin_time as number || 0,
          end_time: msg.end_time as number || 0,
        })
        // 定稿句子 — 清除 partial，追加到 lines
        partialText.value = ''
        lines.value.push({
          speaker_id: msg.speaker_id as number,
          speaker_name: msg.speaker_name as string || '',
          text: msg.text as string,
          begin_time: msg.begin_time as number,
          end_time: msg.end_time as number,
          isFinal: true,
        })
        break

      case 'speaker_bound':
        // 说话人绑定更新 — 更新已有行的 speaker_name，并通知外部同步绑定映射表
        const sid = msg.speaker_id as number
        const name = msg.speaker_name as string
        const uuid = msg.speaker_uuid as string || ''
        for (const line of lines.value) {
          if (line.speaker_id === sid) {
            line.speaker_name = name
          }
        }
        // 通知外部组件同步绑定映射（realtimeSpeakerBindings）
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
        // 后端推送的 paused/idle/stopped 状态同步到前端
        summaryPaused.value = (status === 'paused' || status === 'stopped')
        // 同步倒计时剩余秒数（暂停/停止时为 0，恢复时为剩余秒数）
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

      case 'error':
        error.value = msg.message as string
        break

      case 'ended':
        connected.value = false
        break
    }
  }

  /** 发送心跳消息（含存在性评分） */
  function sendHeartbeat(score: number, userAck = false) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'heartbeat',
        presence_score: score,
        user_ack: userAck,
      }))
    }
  }

  /** 清除存在性警告（用户确认后调用） */
  function clearPresenceWarning() {
    presenceWarning.value = null
  }

  /** 断开连接（主动断开，不触发重连） */
  function disconnect() {
    // 清除重连定时器
    if (wsRetryTimer) { clearTimeout(wsRetryTimer); wsRetryTimer = null }
    wsRetryCount.value = 0
    if (ws) {
      ws.close()
      ws = null
    }
    connected.value = false
    partialText.value = ''
    speakerCount.value = 0
    speakerNames.value = []
    summaryCountdownSec.value = -1
    // 注意：不重置 summaryPaused，因为录音暂停时 WebSocket 会断开，
    // 但后端总结可能已联动暂停，该状态在重连后通过回放更新
    volumeWarning.value = ''
    presenceWarning.value = null
    autoStopped.value = null
  }

  /** 重置所有数据 */
  function reset() {
    disconnect()
    lines.value = []
    partialText.value = ''
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
    lines, partialText, summary, chapters, connected, error,
    speakerCount, speakerNames, summaryCountdownSec, summaryPaused, volumeWarning,
    presenceWarning, autoStopped, wsRetryCount,
    connect, disconnect, reset, sendHeartbeat, clearPresenceWarning, onSpeakerBound,
  }
}
