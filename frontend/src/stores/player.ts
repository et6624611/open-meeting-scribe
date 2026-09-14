/**
 * 全局音频播放状态 / Global audio playback state
 *
 * 职责 / Responsibilities:
 *  - 托管音频元素（不随页面组件卸载而销毁），路由切换后播放不中断 / Host audio element (not destroyed on component unmount); playback survives route changes
 *  - 向会议纪要页音频条、会议列表、侧边栏、顶栏播放 pill 共享播放状态 / Share playback state with meeting audio bar, meeting list, sidebar, topbar pill
 *  - 跨路由 / 页面刷新保留播放进度（sessionStorage 持久化） / Preserve playback progress across routes / page refresh (sessionStorage persistence)
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

const SS_PREFIX = 'oms_player_progress:'  // sessionStorage key 前缀，按 taskId 隔离 / sessionStorage key prefix, isolated by taskId

/** 读取指定任务的上次播放进度（秒），无记录返回 0 / Read last playback progress (seconds) for task; returns 0 if none */
function readSavedProgress(taskId: string): number {
  try {
    const raw = sessionStorage.getItem(SS_PREFIX + taskId)
    if (!raw) return 0
    const v = Number(raw)
    return Number.isFinite(v) && v > 0 ? v : 0
  } catch { return 0 }
}

/** 将指定任务的播放进度写入 sessionStorage / Write playback progress for task to sessionStorage */
function writeSavedProgress(taskId: string, time: number) {
  try { sessionStorage.setItem(SS_PREFIX + taskId, String(time)) } catch { /* */ }
}

/** 清除指定任务的保存进度 / Clear saved progress for task */
function clearSavedProgress(taskId: string) {
  try { sessionStorage.removeItem(SS_PREFIX + taskId) } catch { /* */ }
}

export const usePlayerStore = defineStore('player', () => {
  const taskId = ref<string | null>(null)
  const playing = ref(false)
  const currentTime = ref(0)
  const duration = ref(0)
  const speed = ref(1.0)
  let audioEl: HTMLAudioElement | null = null

  /** 持久化节流：最多每秒写一次 sessionStorage / Persist throttle: write sessionStorage at most once per second */
  let lastPersistTs = 0

  const progress = computed(() =>
    duration.value > 0 ? (currentTime.value / duration.value) * 100 : 0,
  )
  const timeStr = computed(() => `${fmt(currentTime.value)} / ${fmt(duration.value)}`)
  const currentTimeStr = computed(() => fmt(currentTime.value))
  const remainingTimeStr = computed(() => {
    const rem = duration.value - currentTime.value
    return rem > 0 ? `-${fmt(rem)}` : fmt(0)
  })

  /** 将当前进度持久化到 sessionStorage（按 taskId 隔离） / Persist current progress to sessionStorage (isolated by taskId) */
  function persistProgress() {
    if (!taskId.value) return
    writeSavedProgress(taskId.value, currentTime.value)
  }

  function release() {
    if (audioEl) {
      // 释放前将当前进度持久化到对应任务的 key，防止切换后污染 / Persist current progress to the task's key before release to prevent cross-task pollution
      if (taskId.value) {
        writeSavedProgress(taskId.value, audioEl.currentTime || 0)
      }
      audioEl.pause()
      audioEl.removeAttribute('src')
      audioEl = null
    }
    playing.value = false
    currentTime.value = 0
    duration.value = 0
  }

  /** 停止并解除与任务的绑定 / Stop and unbind from task */
  function stop() {
    if (audioEl) {
      audioEl.pause()
      audioEl.removeAttribute('src')
      audioEl = null
    }
    playing.value = false
    currentTime.value = 0
    duration.value = 0
    taskId.value = null
  }

  /** 加载指定任务的音频；已加载同一任务时保持当前播放状态 / Load audio for task; keep current playback state if same task already loaded */
  function load(id: string, url: string) {
    if (taskId.value === id && audioEl) return

    // 从该任务专属的 sessionStorage key 读取上次进度（首次播放则为 0） / Read last progress from task's sessionStorage key (0 for first play)
    const saved = readSavedProgress(id)

    release()
    taskId.value = id
    audioEl = new Audio(url)
    audioEl.playbackRate = speed.value
    audioEl.addEventListener('timeupdate', () => {
      currentTime.value = audioEl?.currentTime ?? 0
    })
    audioEl.addEventListener('loadedmetadata', () => {
      duration.value = audioEl?.duration || 0
      // 恢复上次播放进度（需要在 duration 已知后设置） / Resume last playback progress (must set after duration is known)
      if (saved > 0 && audioEl) {
        audioEl.currentTime = Math.min(saved, audioEl.duration || Infinity)
      }
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

  /** 跳转到指定毫秒并自动播放（点击原文时间戳） / Seek to ms and auto-play (click on transcript timestamp) */
  function seekToMs(ms: number) {
    if (!audioEl) return
    audioEl.currentTime = ms / 1000
    if (!playing.value) audioEl.play()
  }

  /** 按百分比（0-100）跳转 / Seek by percentage (0-100) */
  function seekPercent(pct: number) {
    if (!audioEl || !duration.value) return
    audioEl.currentTime = (pct / 100) * duration.value
  }

  /** 快进/快退指定秒数（负值回退，正值前进） / Skip forward/backward by seconds (negative = rewind, positive = forward) */
  function skip(seconds: number) {
    if (!audioEl) return
    audioEl.currentTime = Math.max(0, Math.min(audioEl.currentTime + seconds, duration.value || Infinity))
  }

  function cycleSpeed() {
    const speeds = [1.0, 1.25, 1.5, 2.0, 0.75]
    speed.value = speeds[(speeds.indexOf(speed.value) + 1) % speeds.length]
    if (audioEl) audioEl.playbackRate = speed.value
  }

  /** 任务被删除时自动停止播放 / Auto-stop playback when task is deleted */
  function stopForTask(id: string) {
    if (taskId.value === id) stop()
  }

  // 监听 timeupdate 驱动的 currentTime 变化，节流持久化到 sessionStorage（≈1次/秒） / Watch currentTime driven by timeupdate; throttle persist to sessionStorage (~1/sec)
  watch(currentTime, () => {
    if (taskId.value && playing.value) {
      const now = Date.now()
      if (now - lastPersistTs >= 1000) {
        lastPersistTs = now
        persistProgress()
      }
    }
  })

  // 任务被删除时自动停止播放并清除其保存进度 / Auto-stop and clear saved progress when task is deleted
  watch(() => useTaskStore().tasks, (tasks) => {
    if (taskId.value && !tasks.some(t => t.task_id === taskId.value)) {
      clearSavedProgress(taskId.value)
      stop()
    }
  })

  // 页面卸载前最后一次持久化 / Last persist before page unload
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', () => {
      if (taskId.value) persistProgress()
    })
  }

  return {
    taskId, playing, currentTime, duration, speed, progress, timeStr, currentTimeStr, remainingTimeStr,
    load, toggle, seekToMs, seekPercent, skip, cycleSpeed, stop, stopForTask,
  }
})
