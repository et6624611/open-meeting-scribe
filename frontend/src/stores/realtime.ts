/**
 * 实时转写缓冲区（跨组件共享） / Realtime transcript buffer (cross-component shared)
 *
 * WebSocket 收到句子时推入，AI 对话发送时读取最近 N 条作为上下文。 / Push on WebSocket sentence receive; read latest N entries as context when sending AI chat.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface RealtimeEntry {
  text: string
  speaker_id: number
  begin_time: number
  end_time: number
}

const MAX_ENTRIES = 5000

export const useRealtimeStore = defineStore('realtime', () => {
  const entries = ref<RealtimeEntry[]>([])

  function push(entry: RealtimeEntry) {
    entries.value.push(entry)
    if (entries.value.length > MAX_ENTRIES) {
      entries.value = entries.value.slice(-MAX_ENTRIES)
    }
  }

  function getSnapshot(): RealtimeEntry[] | null {
    return entries.value.length > 0 ? entries.value.slice(-10) : null
  }

  function reset() {
    entries.value = []
  }

  return { entries, push, getSnapshot, reset }
})
