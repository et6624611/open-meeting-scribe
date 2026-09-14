/**
 * 录音控制 composable — 封装录音 API 调用 / Recording control composable — wraps recording API calls
 */
import { ref, computed } from 'vue'
import client from '@/api/client'

export type RecordState = 'idle' | 'recording' | 'paused'

export function useRecorder() {
  const state = ref<RecordState>('idle')
  const taskId = ref<string | null>(null)
  const elapsed = ref(0) // 已录制秒数 / Elapsed recording seconds
  let elapsedTimer: ReturnType<typeof setInterval> | null = null

  const isRecording = computed(() => state.value === 'recording')
  const isPaused = computed(() => state.value === 'paused')

  /** 开始录音 / Start recording */
  async function startRecording() {
    try {
      const { data } = await client.post('/api/record/start')
      taskId.value = data.task_id
      state.value = 'recording'
      elapsed.value = 0
      startElapsedTimer()
      return data
    } catch (e) {
      console.error('[Recorder] 开始录音失败:', e)
      throw e
    }
  }

  /** 暂停录音 */
  async function pauseRecording() {
    try {
      const { data } = await client.post('/api/record/pause')
      state.value = 'paused'
      stopElapsedTimer()
      return data
    } catch (e) {
      console.error('[Recorder] 暂停录音失败:', e)
      throw e
    }
  }

  /** 恢复录音 */
  async function resumeRecording() {
    try {
      const { data } = await client.post('/api/record/resume')
      state.value = 'recording'
      startElapsedTimer()
      return data
    } catch (e) {
      console.error('[Recorder] 恢复录音失败:', e)
      throw e
    }
  }

  /** 停止录音（进入管线处理） */
  async function stopRecording(notes?: string) {
    try {
      const { data } = await client.post('/api/record/stop', notes ? { notes } : {})
      state.value = 'idle'
      stopElapsedTimer()
      return data
    } catch (e) {
      console.error('[Recorder] 停止录音失败:', e)
      throw e
    }
  }

  /** 放弃录音 */
  async function abandonRecording() {
    try {
      await client.post('/api/record/abandon')
      state.value = 'idle'
      taskId.value = null
      stopElapsedTimer()
    } catch (e) {
      console.error('[Recorder] 放弃录音失败:', e)
      throw e
    }
  }

  /** 查询录音状态 */
  async function checkStatus() {
    try {
      const { data } = await client.get('/api/record/status')
      if (data.recording) {
        taskId.value = data.task_id
        state.value = data.paused ? 'paused' : 'recording'
        elapsed.value = data.elapsed || 0
        if (state.value === 'recording') startElapsedTimer()
      } else {
        state.value = 'idle'
        taskId.value = null
      }
      return data
    } catch {
      state.value = 'idle'
      return null
    }
  }

  function startElapsedTimer() {
    stopElapsedTimer()
    elapsedTimer = setInterval(() => { elapsed.value++ }, 1000)
  }

  function stopElapsedTimer() {
    if (elapsedTimer) {
      clearInterval(elapsedTimer)
      elapsedTimer = null
    }
  }

  /** 格式化时长 */
  function formatElapsed(seconds?: number): string {
    const s = Math.floor(seconds ?? elapsed.value)
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    const sec = s % 60
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
  }

  return {
    state, taskId, elapsed, isRecording, isPaused,
    startRecording, pauseRecording, resumeRecording,
    stopRecording, abandonRecording, checkStatus, formatElapsed,
  }
}
