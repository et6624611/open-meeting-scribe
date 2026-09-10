/**
 * 全局音频播放状态
 *
 * 职责：
 *  - 托管音频元素（不随页面组件卸载而销毁），路由切换后播放不中断
 *  - 向会议纪要页音频条、会议列表、侧边栏、顶栏播放 pill 共享播放状态
 */
import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { useTaskStore } from '@/stores/task'

function fmt(sec: number): string {
  if (!isFinite(sec) || sec < 0) sec = 0
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export const usePlayerStore = defineStore('player', () => {
  const taskId = ref<string | null>(null)
  const playing = ref(false)
  const currentTime = ref(0)
  const duration = ref(0)
  const speed = ref(1.0)
  let audioEl: HTMLAudioElement | null = null

  const progress = computed(() =>
    duration.value > 0 ? (currentTime.value / duration.value) * 100 : 0,
  )
  const timeStr = computed(() => `${fmt(currentTime.value)} / ${fmt(duration.value)}`)

  function release() {
    if (audioEl) {
      audioEl.pause()
      audioEl.removeAttribute('src')
      audioEl = null
    }
    playing.value = false
    currentTime.value = 0
    duration.value = 0
  }

  /** 停止并解除与任务的绑定 */
  function stop() {
    release()
    taskId.value = null
  }

  /** 加载指定任务的音频；已加载同一任务时保持当前播放状态 */
  function load(id: string, url: string) {
    if (taskId.value === id && audioEl) return
    release()
    taskId.value = id
    audioEl = new Audio(url)
    audioEl.playbackRate = speed.value
    audioEl.addEventListener('timeupdate', () => {
      currentTime.value = audioEl?.currentTime ?? 0
    })
    audioEl.addEventListener('loadedmetadata', () => {
      duration.value = audioEl?.duration || 0
    })
    audioEl.addEventListener('play', () => { playing.value = true })
    audioEl.addEventListener('pause', () => { playing.value = false })
    audioEl.addEventListener('ended', () => { playing.value = false })
  }

  function toggle() {
    if (!audioEl) return
    if (playing.value) audioEl.pause()
    else audioEl.play()
  }

  /** 跳转到指定毫秒并自动播放（点击原文时间戳） */
  function seekToMs(ms: number) {
    if (!audioEl) return
    audioEl.currentTime = ms / 1000
    if (!playing.value) audioEl.play()
  }

  /** 按百分比（0-100）跳转 */
  function seekPercent(pct: number) {
    if (!audioEl || !duration.value) return
    audioEl.currentTime = (pct / 100) * duration.value
  }

  function cycleSpeed() {
    const speeds = [1.0, 1.25, 1.5, 2.0, 0.75]
    speed.value = speeds[(speeds.indexOf(speed.value) + 1) % speeds.length]
    if (audioEl) audioEl.playbackRate = speed.value
  }

  /** 任务被删除时自动停止播放 */
  function stopForTask(id: string) {
    if (taskId.value === id) stop()
  }

  watch(() => useTaskStore().tasks, (tasks) => {
    if (taskId.value && !tasks.some(t => t.task_id === taskId.value)) stop()
  })

  return {
    taskId, playing, currentTime, duration, speed, progress, timeStr,
    load, toggle, seekToMs, seekPercent, cycleSpeed, stop, stopForTask,
  }
})
