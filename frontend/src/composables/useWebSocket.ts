/**
 * 实时转写 WebSocket composable
 *
 * 连接 /ws/transcript/{task_id}，接收实时转写消息。
 */
import { ref, onUnmounted } from 'vue'
import { useRealtimeStore } from '@/stores/realtime'

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
  title: string
  start_time: number
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

  let ws: WebSocket | null = null

  /** 连接 WebSocket */
  function connect(taskId: string) {
    disconnect()
    error.value = ''

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${location.host}/ws/transcript/${taskId}`

    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        handleMessage(msg)
      } catch (e) {
        console.error('[WS] 消息解析失败:', e)
      }
    }

    ws.onerror = () => {
      error.value = '连接异常'
      connected.value = false
    }

    ws.onclose = () => {
      connected.value = false
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
          isFinal: true,
        })
        break

      case 'speaker_bound':
        // 说话人绑定更新 — 更新已有行的 speaker_name
        const sid = msg.speaker_id as number
        const name = msg.speaker_name as string
        for (const line of lines.value) {
          if (line.speaker_id === sid) {
            line.speaker_name = name
          }
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

      case 'error':
        error.value = msg.message as string
        break

      case 'ended':
        connected.value = false
        break
    }
  }

  /** 断开连接 */
  function disconnect() {
    if (ws) {
      ws.close()
      ws = null
    }
    connected.value = false
    partialText.value = ''
    speakerCount.value = 0
    speakerNames.value = []
    summaryCountdownSec.value = -1
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
  }

  onUnmounted(disconnect)

  return {
    lines, partialText, summary, chapters, connected, error,
    speakerCount, speakerNames, summaryCountdownSec,
    connect, disconnect, reset,
  }
}
