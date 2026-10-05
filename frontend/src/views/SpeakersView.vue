<template>
  <div class="spk-page">
    <!-- 列表视图 / List view -->
    <Transition name="fade" mode="out-in">
    <div v-if="!selectedSpeaker" key="list">
      <div class="main-head">
        <div class="title-row">
          <h1>{{ t('speakers.title') }}</h1>
          <span class="page-count">{{ t('speakers.count', { count: speakers.length }) }}</span>
        </div>
      </div>
      <!-- 统一输入框：搜索 + 新建 / Unified input: search + create -->
      <div class="spk-unified">
        <div class="spk-unified-field">
          <svg class="spk-unified-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <template v-if="showCreateHint">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </template>
            <template v-else>
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </template>
          </svg>
          <input
            ref="unifiedInputRef"
            v-model="inputText"
            class="spk-unified-input"
            type="text"
            :placeholder="t('speakers.unified_placeholder')"
            @keyup.enter="onUnifiedEnter"
          />
        </div>
      </div>
      <!-- 加载态 / Loading state -->
      <div v-if="loading" class="spk-loading">
        <div class="spk-spinner"></div>
        <span>{{ t('speakers.voiceprint_loading') }}</span>
      </div>
      <!-- 说话人列表 / Speaker list -->
      <div v-else-if="filteredSpeakers.length > 0 || showCreateHint" class="spk-list">
        <div v-for="spk in filteredSpeakers" :key="spk.id" :class="['spk-item', { 'is-new': createdSpeakerId === spk.id }]" @click="openDetail(spk)">
          <div class="spk-info">
            <span :class="['spk-vp-dot', voiceprintIds.has(spk.id) ? 'vp-yes' : 'vp-no']" :title="voiceprintIds.has(spk.id) ? t('speakers.voiceprint_registered') : t('speakers.voiceprint_not_registered')"></span>
            <div class="spk-text">
              <span class="spk-name" :class="{ 'is-unid': isPlaceholderName(spk.name) }" :style="{ color: getTextColor(spk.id) }">{{ spkDisplayName(spk.name) }}</span>
              <span v-if="isMe(spk)" class="spk-badge-me">{{ t('speakers.badge_me') }}</span>
            </div>
          </div>
          <div class="spk-meta-row">
            <span v-if="spk.meeting_count" class="spk-meta">{{ t('speakers.meetings_count', { count: spk.meeting_count }) }}</span>
            <div class="spk-actions" @click.stop>
              <button class="spk-action-btn" @click="onSetMe(spk.id)">{{ isMe(spk) ? t('speakers.unset_me') : t('speakers.set_me') }}</button>
              <button class="spk-action-btn danger" @click="confirmDelete(spk)">{{ t('common.action.delete') }}</button>
            </div>
          </div>
        </div>
        <!-- 新建提示 / Create new hint -->
        <div v-if="showCreateHint" class="spk-create-hint" @click="onCreate">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>{{ t('speakers.create_hint', { name: inputText.trim() }) }}</span>
        </div>
      </div>
      <!-- 空状态 / Empty state -->
      <div v-else class="empty-state">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        <p>{{ speakers.length === 0 ? t('speakers.empty') : t('speakers.search_placeholder') }}</p>
        <p v-if="speakers.length === 0" class="empty-hint">{{ t('speakers.empty_hint') }}</p>
      </div>
      <!-- 设为我功能提示 / Set-as-me hint -->
      <p v-if="speakers.length > 0" class="spk-set-me-hint">{{ t('speakers.set_me_hint') }}</p>
    </div>

    <!-- 详情视图 / Detail view -->
    <div v-else key="detail" class="spk-detail">
      <button class="spk-back-btn" @click="backToList">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m15 18-6-6 6-6"/></svg>
        {{ t('speakers.back_list') }}
      </button>

      <div class="spk-detail-head">
        <div class="spk-detail-left">
          <div class="spk-detail-info">
            <div class="spk-detail-name" @click="startRename">
              <span v-if="!isRenaming" class="spk-name-clickable" :class="{ 'is-unid': isPlaceholderName(selectedSpeaker.name) }" :style="{ color: getTextColor(selectedSpeaker.id) }">{{ spkDisplayName(selectedSpeaker.name) }}</span>
              <input v-else ref="renameInputRef" v-model="renameValue" class="spk-inline-edit" @keyup.enter="saveRename" @keydown.escape.prevent="cancelRename" @blur="saveRename" />
              <span v-if="isMe(selectedSpeaker)" class="spk-me-badge">{{ t('speakers.current_user') }}</span>
            </div>
            <div v-if="selectedSpeaker.alias" class="spk-detail-role">{{ selectedSpeaker.alias }}</div>
          </div>
        </div>
        <div class="spk-detail-actions">
          <button v-if="!isMe(selectedSpeaker)" class="btn btn-secondary btn-sm" @click="onToggleMe">{{ t('speakers.set_me') }}</button>
          <button class="btn btn-secondary btn-sm" style="color:var(--error)" @click="confirmDelete(selectedSpeaker)">{{ t('common.action.delete') }}</button>
        </div>
      </div>

      <!-- 统计卡片 / Stat cards -->
      <div class="spk-stat-cards">
        <div class="spk-stat-card">
          <div class="label">{{ t('speakers.stat_meetings') }}</div>
          <div class="value">{{ stat.meetings.length }}</div>
          <div class="sub">{{ t('speakers.stat_meetings_unit') }}</div>
        </div>
        <div class="spk-stat-card">
          <div class="label">{{ t('speakers.stat_duration') }}</div>
          <div class="value">{{ Math.round(stat.totalDuration / 60) }}</div>
          <div class="sub">{{ t('speakers.stat_duration_unit') }}</div>
        </div>
        <div class="spk-stat-card">
          <div class="label">{{ t('speakers.stat_todos') }}</div>
          <div class="value">{{ stat.todos.length }}</div>
          <div class="sub">{{ t('speakers.stat_todos_unit') }}</div>
        </div>
      </div>

      <!-- 声纹管理 / Voiceprint management -->
      <div class="spk-voiceprint-section">
        <div v-if="voiceprintLoading && !voiceprintStatus" class="vp-skeleton">
          <div class="vp-skeleton-line"></div>
          <div class="vp-skeleton-line short"></div>
        </div>
        <template v-else-if="voiceprintStatus">
        <div class="vp-header">
          <h3 class="vp-title">{{ t('speakers.voiceprint_title') }}</h3>
          <span :class="['vp-badge', voiceprintStatus.has_voiceprint ? 'vp-registered' : 'vp-not-registered']">
            {{ voiceprintStatus.has_voiceprint ? t('speakers.voiceprint_registered') : t('speakers.voiceprint_not_registered') }}
          </span>
        </div>
        <div class="vp-stats">
          <div class="vp-stat-item">
            <span class="vp-stat-label">{{ t('speakers.voiceprint_samples') }}</span>
            <span class="vp-stat-value">{{ voiceprintStatus.sample_count }}</span>
          </div>
          <div class="vp-stat-item">
            <span class="vp-stat-label">{{ t('speakers.voiceprint_total_duration') }}</span>
            <span class="vp-stat-value">{{ formatTime(voiceprintStatus.total_sample_duration) }}</span>
          </div>
          <div v-if="voiceprintStatus.updated_at" class="vp-stat-item">
            <span class="vp-stat-label">{{ t('speakers.voiceprint_updated') }}</span>
            <span class="vp-stat-value">{{ formatDate(voiceprintStatus.updated_at) }}</span>
          </div>
        </div>
        <div class="vp-actions">
          <button class="btn btn-secondary btn-sm" @click="onRebuildVoiceprint" :disabled="voiceprintLoading">
            {{ voiceprintLoading ? t('speakers.voiceprint_rebuilding') : t('speakers.voiceprint_rebuild') }}
          </button>
          <button 
            v-if="voiceprintStatus.has_voiceprint" 
            class="btn btn-secondary btn-sm" 
            style="color:var(--rec)" 
            @click="onDeleteVoiceprint"
            :disabled="voiceprintLoading"
          >
            {{ t('speakers.voiceprint_delete') }}
          </button>
        </div>
        </template>
      </div>

      <!-- Tab 切换 / Tab switcher -->
      <div class="spk-tabs">
        <button class="spk-tab" :class="{ 'is-active': activeTab === 'meetings' }" @click="activeTab = 'meetings'">
          {{ t('speakers.tab_meetings') }} <span class="spk-tab-count">{{ stat.meetings.length }}</span>
        </button>
        <button class="spk-tab" :class="{ 'is-active': activeTab === 'utterances' }" @click="activeTab = 'utterances'">
          {{ t('speakers.tab_utterances') }} <span class="spk-tab-count">{{ allUtterances.length }}</span>
        </button>
        <button class="spk-tab" :class="{ 'is-active': activeTab === 'todos' }" @click="activeTab = 'todos'">
          {{ t('speakers.tab_todos') }} <span class="spk-tab-count">{{ stat.todos.length }}</span>
        </button>
      </div>

      <!-- 会议列表 / Meeting list -->
      <div v-show="activeTab === 'meetings'" class="spk-tab-panel is-active">
        <div v-if="stat.meetings.length === 0" class="spk-empty">{{ t('speakers.empty_meetings') }}</div>
        <div v-for="m in sortedMeetings" :key="m.task_id" class="spk-meeting-card" @click="openTask(m.task_id)">
          <div class="mc-head">
            <span class="mc-title">{{ m.title }}</span>
            <span class="mc-date">{{ formatDate(m.date) }}</span>
          </div>
          <div class="mc-excerpt">{{ m.excerpt }}</div>
          <div class="mc-stats">
            <span>{{ t('speakers.minutes', { count: Math.round(m.duration / 60) }) }}</span>
            <span>{{ t('speakers.utterances_count', { count: m.utteranceCount }) }}</span>
          </div>
        </div>
      </div>

      <!-- 发言摘要 / Utterance summary -->
      <div v-show="activeTab === 'utterances'" class="spk-tab-panel is-active">
        <div v-if="allUtterances.length === 0" class="spk-empty">{{ t('speakers.empty_utterances') }}</div>
        <div v-for="(u, i) in allUtterances.slice(0, 20)" :key="i" class="spk-utterance" :style="{ borderLeftColor: getColor(selectedSpeaker.id) }">
          <div class="ut-meta">
            <span class="ut-meeting" @click="openTask(u.meetingTaskId)">{{ u.meetingTitle }}</span>
            <span class="ut-time">{{ formatTime(u.start) }}</span>
          </div>
          <div class="ut-text">{{ u.text }}</div>
        </div>
        <div v-if="allUtterances.length > 20" class="spk-empty">{{ t('speakers.utterances_limit') }}</div>
      </div>

      <!-- 待办事项 / Todo items -->
      <div v-show="activeTab === 'todos'" class="spk-tab-panel is-active">
        <div v-if="stat.todos.length === 0" class="spk-empty">{{ t('speakers.empty_todos') }}</div>
        <div v-for="todo in stat.todos" :key="todo.id" class="spk-todo-item">
          <div class="todo-body">
            <div class="todo-text" :class="{ 'is-done': todo.done }">{{ todo.text }}</div>
            <div class="todo-from">{{ t('speakers.todo_from', { title: todo.fromTaskTitle }) }}</div>
          </div>
        </div>
      </div>
    </div>
    </Transition>

    <!-- 确认对话框 / Confirmation dialog -->
    <Teleport to="body">
    <div v-if="showConfirmDialog" class="spk-dialog-overlay" @click.self="showConfirmDialog = false">
      <div class="spk-dialog">
        <h3>{{ confirmDialogTitle }}</h3>
        <p>{{ confirmDialogMsg }}</p>
        <div class="spk-dialog-actions">
          <button class="btn btn-secondary btn-sm" @click="showConfirmDialog = false">{{ t('speakers.cancel') }} <kbd>ESC</kbd></button>
          <button class="btn btn-secondary btn-sm danger-confirm" @click="onConfirmDelete">{{ t('common.action.delete') }}</button>
        </div>
      </div>
    </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchSpeakers, createSpeaker, deleteSpeaker, setSpeakerAsMe, updateSpeaker } from '@/api/speakers'
import type { Speaker } from '@/api/speakers'
import { loadSpeakerStats, useSpeakerStat } from '@/composables/useSpeakerStats'
import { getSpeakerColor, getSpeakerTextColor } from '@/utils/speakerColors'
import { isPlaceholderName } from '@/utils/speakerDisplay'
import { useRouter } from 'vue-router'
import { showToast } from '@/composables/useToast'
import { getVoiceprintStatus, rebuildVoiceprint, deleteVoiceprint, fetchVoiceprintRegistry, type VoiceprintStatus } from '@/api/voiceprint'
import { useUserStore } from '@/stores/user'
import { useEscClose } from '@/composables/useEscClose'
import { usePageBack } from '@/composables/usePageBack'

const { t } = useI18n()
const router = useRouter()
const userStore = useUserStore()

/** REQ-SPK-RN L5：占位档案名展示位收敛为中性「未识别」（数据本体不动 H4，改名走既有编辑） */
function spkDisplayName(name: string): string {
  return isPlaceholderName(name) ? t('speakers.unidentified') : name
}
const speakers = ref<Speaker[]>([])
const inputText = ref('')
const unifiedInputRef = ref<HTMLInputElement | null>(null)
const createdSpeakerId = ref<string | null>(null)
const selectedSpeaker = ref<Speaker | null>(null)
const activeTab = ref<'meetings' | 'utterances' | 'todos'>('meetings')
const voiceprintStatus = ref<VoiceprintStatus | null>(null)
const voiceprintLoading = ref(false)
const loading = ref(false)
const voiceprintIds = ref<Set<string>>(new Set())
// 内联重命名 / Inline rename
const isRenaming = ref(false)
const renameValue = ref('')
const renameInputRef = ref<HTMLInputElement | null>(null)
// 确认对话框 / Confirmation dialog
const showConfirmDialog = ref(false)
const confirmDialogTitle = ref('')
const confirmDialogMsg = ref('')

useEscClose(showConfirmDialog, () => { showConfirmDialog.value = false })
// ESC 返回：详情页先回到列表，列表页再路由返回 / ESC back: detail view returns to list first, list view then navigates back
usePageBack({ intercept: () => { if (selectedSpeaker.value) { backToList(); return true } return false } })
let confirmCallback: (() => void) | null = null

/** 判断说话人是否为当前用户（通过 linked_user_id 比较） / Check if speaker is current user (via linked_user_id) */
function isMe(spk: Speaker): boolean {
  if (!spk.linked_user_id || !userStore.user?.id) return false
  return spk.linked_user_id === userStore.user.id
}

async function loadVoiceprint() {
  if (!selectedSpeaker.value) return
  try {
    voiceprintStatus.value = await getVoiceprintStatus(selectedSpeaker.value.id)
  } catch (e) {
    console.error('Failed to load voiceprint status:', e)
    voiceprintStatus.value = null
  }
}

watch(
  () => selectedSpeaker.value?.id,
  () => {
    if (selectedSpeaker.value) {
      loadVoiceprint()
    } else {
      voiceprintStatus.value = null
    }
  },
)

// Tab 切换时刷新底部理念 / Refresh footer philosophy on tab switch
watch(activeTab, (tab) => {
  ;(window as any).__omsUpdatePhilosophy?.(tab)
})

async function load() {
  loading.value = true
  try {
    speakers.value = await fetchSpeakers()
  } finally {
    loading.value = false
  }
  // 列表已显示，后台并行加载统计数据与声纹注册表
  if (speakers.value.length > 0) {
    Promise.all([
      loadSpeakerStats(speakers.value.map(s => s.id)),
      fetchVoiceprintRegistry().then(ids => { voiceprintIds.value = ids }),
    ]).catch(() => { /* 静默处理，不影响列表展示 */ })
  }
}

/** 按输入文本过滤说话人 / Filter speakers by input text */
const filteredSpeakers = computed(() => {
  const q = inputText.value.trim().toLowerCase()
  if (!q) return speakers.value
  return speakers.value.filter(s => s.name.toLowerCase().includes(q))
})

/** 是否存在精确名称匹配 / Whether an exact name match exists */
const hasExactMatch = computed(() => {
  const q = inputText.value.trim().toLowerCase()
  if (!q) return true
  return speakers.value.some(s => s.name.toLowerCase() === q)
})

/** 是否显示「新建」提示 / Whether to show the create-new hint */
const showCreateHint = computed(() => inputText.value.trim().length > 0 && !hasExactMatch.value)

function getColor(id: string) {
  return getSpeakerColor(id)
}

function getTextColor(id: string) {
  return getSpeakerTextColor(id)
}

function openDetail(spk: Speaker) {
  selectedSpeaker.value = spk
  activeTab.value = 'meetings'
}

function backToList() {
  selectedSpeaker.value = null
}

async function onCreate() {
  const name = inputText.value.trim()
  if (!name) return
  // 重名检测 / Duplicate name check
  if (speakers.value.some(s => s.name === name)) {
    showToast(t('speakers.duplicate_name', { name }), 'warn')
    return
  }
  try {
    await createSpeaker(name)
    inputText.value = ''
    showToast(t('speakers.create_success', { name }), 'success')
    await load()
    // 找到新创建的说话人并滚动+高亮 / Find newly created speaker and scroll+highlight
    const newSpk = speakers.value.find(s => s.name === name)
    if (newSpk) {
      createdSpeakerId.value = newSpk.id
      await nextTick()
      const el = document.querySelector('.spk-item.is-new')
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }
      setTimeout(() => { createdSpeakerId.value = null }, 1500)
    }
    unifiedInputRef.value?.focus()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || t('speakers.create_failed')
    showToast(msg, 'error')
  }
}

/** 统一输入框 Enter 处理 / Unified input Enter handler */
function onUnifiedEnter() {
  if (showCreateHint.value) {
    onCreate()
  } else if (filteredSpeakers.value.length === 1) {
    openDetail(filteredSpeakers.value[0])
  }
}

async function onDelete(id: string) {
  const spk = speakers.value.find(s => s.id === id)
  try {
    await deleteSpeaker(id)
    if (selectedSpeaker.value?.id === id) {
      selectedSpeaker.value = null
    }
    await load()
    if (spk) showToast(t('speakers.delete_success', { name: spk.name }), 'success')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || e?.message || t('speakers.delete_failed'), 'error')
  }
}

/** 打开确认对话框 / Open confirmation dialog */
function confirmDelete(spk: Speaker) {
  confirmDialogTitle.value = t('speakers.confirm_delete_title')
  confirmDialogMsg.value = t('speakers.confirm_delete_msg', { name: spk.name })
  confirmCallback = () => onDelete(spk.id)
  showConfirmDialog.value = true
}

/** 确认删除回调 / Confirm delete callback */
function onConfirmDelete() {
  showConfirmDialog.value = false
  confirmCallback?.()
  confirmCallback = null
}

async function onSetMe(id: string) {
  try {
    await setSpeakerAsMe(id)
    await load()
    if (selectedSpeaker.value?.id === id) {
      selectedSpeaker.value = speakers.value.find(s => s.id === id) || null
    }
    const spk = speakers.value.find(s => s.id === id)
    showToast(t('speakers.set_me_success', { name: spk?.name }), 'success')
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || t('speakers.set_me_failed')
    showToast(msg, 'error')
  }
}

async function onToggleMe() {
  if (!selectedSpeaker.value) return
  await onSetMe(selectedSpeaker.value.id)
}

/** 开始内联重命名 / Start inline rename */
function startRename() {
  if (!selectedSpeaker.value) return
  renameValue.value = selectedSpeaker.value.name
  isRenaming.value = true
  nextTick(() => renameInputRef.value?.focus())
}

/** 保存重命名 / Save rename */
async function saveRename() {
  if (!isRenaming.value || !selectedSpeaker.value) return
  const name = renameValue.value.trim()
  if (!name || name === selectedSpeaker.value.name) {
    cancelRename()
    return
  }
  await updateSpeaker(selectedSpeaker.value.id, { name })
  selectedSpeaker.value.name = name
  isRenaming.value = false
  await load()
}

/** 取消重命名 / Cancel rename */
function cancelRename() {
  isRenaming.value = false
}

function openTask(taskId: string) {
  router.push({ name: 'generating', params: { taskId } })
}

function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return t('speakers.date_format', { month: d.getMonth() + 1, day: d.getDate() })
}

function formatTime(seconds: number) {
  if (!seconds) return ''
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// 计算属性 / Computed
const { stat } = useSpeakerStat(computed(() => selectedSpeaker.value?.id || ''))

const sortedMeetings = computed(() => {
  return [...stat.value.meetings].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
})

const allUtterances = computed(() => {
  const result: Array<{ meetingTitle: string; meetingTaskId: string; start: number; text: string }> = []
  stat.value.meetings.forEach(m => {
    m.utterances.forEach(u => {
      result.push({
        meetingTitle: m.title,
        meetingTaskId: m.task_id,
        start: u.begin_time,
        text: u.text,
      })
    })
  })
  return result
})

async function onRebuildVoiceprint() {
  if (!selectedSpeaker.value) return
  voiceprintLoading.value = true
  try {
    const result = await rebuildVoiceprint(selectedSpeaker.value.id)
    showToast(t('speakers.voiceprint_rebuild_success', { count: result.meeting_count, minutes: Math.round(result.duration_sec / 60) }), 'success')
    await loadVoiceprint()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || t('speakers.voiceprint_rebuild_failed')
    showToast(msg, 'error')
  } finally {
    voiceprintLoading.value = false
  }
}

async function onDeleteVoiceprint() {
  if (!selectedSpeaker.value) return
  confirmDialogTitle.value = t('speakers.confirm_delete_title')
  confirmDialogMsg.value = t('speakers.confirm_delete_voiceprint_msg')
  confirmCallback = async () => {
    try {
      if (!selectedSpeaker.value) return
      await deleteVoiceprint(selectedSpeaker.value.id)
      showToast(t('speakers.voiceprint_deleted'), 'success')
      await loadVoiceprint()
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || t('speakers.voiceprint_delete_failed')
      showToast(msg, 'error')
    }
  }
  showConfirmDialog.value = true
}

onMounted(load)
</script>

<style scoped>
.spk-page { padding: var(--s-5) var(--s-5) var(--s-6); }
/* 统一输入框 / Unified input */
.spk-unified { margin-bottom: var(--s-4); }
.spk-unified-field { display: flex; align-items: center; gap: var(--s-2); position: relative; }
.spk-unified-icon { position: absolute; left: 10px; color: var(--subtle); pointer-events: none; transition: color 0.15s; }
.spk-unified-input { width: 100%; max-width: 400px; padding: 8px 10px 8px 32px; border: none; border-bottom: 1px solid var(--border); border-radius: 0; font-size: 14px; outline: none; background: transparent; color: var(--fg); transition: border-color 0.15s; }
.spk-unified-input:focus { border-bottom-color: var(--accent); box-shadow: 0 1px 0 0 var(--accent); }
.spk-unified-input:focus ~ .spk-unified-icon,
.spk-unified-field:focus-within .spk-unified-icon { color: var(--accent); }
.spk-unified-input::placeholder { color: var(--subtle); }
/* 新建提示行 / Create-new hint row */
.spk-create-hint { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-3) var(--s-4); cursor: pointer; transition: background 0.12s; color: var(--accent); font-size: 13px; border-top: 1px dashed var(--border); }
.spk-create-hint:hover { background: var(--accent-soft); }
.spk-create-hint svg { flex-shrink: 0; }
.spk-list { display: flex; flex-direction: column; }
.spk-item { display: flex; align-items: center; justify-content: space-between; padding: var(--s-3) var(--s-4); background: transparent; cursor: pointer; transition: background 0.12s; border-bottom: 1px solid var(--border); }
.spk-item:last-child { border-bottom: none; }
.spk-item:hover { background: var(--surface); }
.spk-item:hover .spk-actions { opacity: 1; }
.spk-item.is-new { animation: spk-highlight 1.5s ease-out; }
@keyframes spk-highlight {
  0% { background: var(--accent-soft); box-shadow: inset 3px 0 0 var(--accent); }
  100% { background: var(--surface); box-shadow: none; }
}
.spk-info { display: flex; align-items: center; gap: var(--s-2); min-width: 0; }
.spk-vp-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.spk-vp-dot.vp-yes { background: var(--ok); }
.spk-vp-dot.vp-no { background: var(--border); }
.spk-text { display: flex; align-items: center; gap: var(--s-2); min-width: 0; }
.spk-name { font-size: 14px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* REQ-SPK-RN L5：存量占位档案仍列出（H4 数据本体不动），名字位灰标中性文案，改名走既有编辑 */
.spk-name.is-unid, .spk-name-clickable.is-unid { color: var(--subtle) !important; font-style: italic; font-weight: 400; }
.spk-badge-me { font-size: 10px; padding: 1px 6px; border-radius: 4px; background: var(--accent-soft); color: var(--accent); font-weight: 500; flex-shrink: 0; }
.spk-meta-row { display: flex; align-items: center; gap: var(--s-3); flex-shrink: 0; }
.spk-meta { font-size: 12px; color: var(--muted); }
.spk-actions { display: flex; gap: var(--s-1); opacity: 0; transition: opacity 0.12s; }
.spk-action-btn { padding: 4px 10px; font-size: 12px; color: var(--muted); background: transparent; border: none; border-radius: 4px; cursor: pointer; transition: all 0.12s; }
.spk-action-btn:hover { color: var(--fg); background: var(--surface-2); }
.spk-action-btn.danger:hover { color: var(--error); background: oklch(95% 0.04 25); }
.empty-state { text-align: center; padding: var(--s-9) var(--s-7); color: var(--muted); font-size: 13px; display: flex; flex-direction: column; align-items: center; gap: var(--s-2); }
.empty-hint { font-size: 12px; color: var(--subtle); }
.spk-set-me-hint { font-size: 12px; color: var(--subtle); margin-top: var(--s-3); text-align: center; }

.spk-loading { display: flex; align-items: center; gap: var(--s-3); padding: var(--s-6); color: var(--muted); font-size: 13px; justify-content: center; }
.spk-spinner { width: 18px; height: 18px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spk-spin 0.8s linear infinite; }
@keyframes spk-spin { to { transform: rotate(360deg); } }

.spk-me-badge { font-size: 11px; margin-left: var(--s-2); padding: 2px 8px; border-radius: 4px; background: var(--accent-soft); color: var(--accent); font-weight: 500; vertical-align: middle; }

/* 详情视图 / Detail view */
.spk-back-btn { display: inline-flex; align-items: center; gap: var(--s-1); padding: var(--s-2) 0; margin-bottom: var(--s-4); color: var(--muted); font-size: 13px; background: none; border: none; cursor: pointer; transition: color 0.12s; }
.spk-back-btn:hover { color: var(--fg); }
.spk-detail-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--s-6); padding-bottom: var(--s-4); border-bottom: 1px solid var(--border); }
.spk-detail-left { display: flex; align-items: center; gap: var(--s-3); min-width: 0; }
.spk-detail-info { min-width: 0; }
.spk-detail-name { font-size: 18px; font-weight: 600; display: flex; align-items: center; gap: var(--s-2); cursor: pointer; }
.spk-name-clickable { cursor: pointer; border-radius: var(--radius-sm); padding: 1px 4px; margin: -1px -4px; transition: background 0.12s; }
.spk-name-clickable:hover { background: var(--surface-2); }
.spk-inline-edit { font-size: 18px; font-weight: 600; border: 1px solid var(--accent); border-radius: var(--radius); padding: 1px 6px; background: var(--surface); color: var(--fg); outline: none; font-family: inherit; }
.spk-detail-role { font-size: 13px; color: var(--muted); margin-top: 2px; }
.spk-detail-actions { display: flex; gap: var(--s-2); flex-shrink: 0; }

/* 统计卡片 / Stat cards */
.spk-stat-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--s-3); margin-bottom: var(--s-6); }
.spk-stat-card { padding: var(--s-4); background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius); backdrop-filter: var(--glass-blur-lg); -webkit-backdrop-filter: var(--glass-blur-lg); text-align: center; }
.spk-stat-card .label { font-size: 12px; color: var(--muted); margin-bottom: var(--s-1); }
.spk-stat-card .value { font-size: 24px; font-weight: 600; font-family: var(--font-mono); }
.spk-stat-card .sub { font-size: 11px; color: var(--muted); margin-top: 2px; }

/* 声纹管理样式 / Voiceprint management styles */
.spk-voiceprint-section {
  margin-bottom: var(--s-6);
  padding: var(--s-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.vp-header { 
  display: flex; 
  align-items: center; 
  justify-content: space-between; 
  margin-bottom: var(--s-3); 
}
.vp-title { 
  font-size: 14px; 
  font-weight: 600; 
  margin: 0; 
  color: var(--fg); 
}
.vp-badge { 
  font-size: 11px; 
  padding: 3px 10px; 
  border-radius: var(--radius-lg); 
  font-weight: 500; 
}
.vp-registered { 
  background: var(--ok-soft); 
  color: var(--ok); 
}
.vp-not-registered { 
  background: var(--rec-soft); 
  color: var(--rec); 
}
.vp-stats { 
  display: flex; 
  gap: var(--s-4); 
  margin-bottom: var(--s-3); 
  flex-wrap: wrap; 
}
.vp-stat-item { 
  font-size: 13px; 
  color: var(--subtle); 
}
.vp-stat-label { 
  color: var(--muted); 
}
.vp-stat-value { 
  font-weight: 500; 
  color: var(--fg); 
}
.vp-actions { 
  display: flex; 
  gap: var(--s-2); 
}

/* Tab 计数徽章 / Tab count badge */
.spk-tab { display: inline-flex; align-items: center; gap: var(--s-1); }
.spk-tab-count { font-size: 11px; color: var(--muted); background: var(--surface-2); padding: 0 5px; border-radius: 999px; min-width: 18px; text-align: center; }
.spk-tab.is-active .spk-tab-count { background: var(--accent-soft); color: var(--accent); }

/* 过渡动画 / Transition animation */
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* 确认对话框 / Confirmation dialog */
.spk-dialog-overlay { position: fixed; inset: 0; background: var(--overlay-bg); display: flex; align-items: center; justify-content: center; z-index: var(--z-modal); animation: oms-overlay-in 0.2s ease; }
.spk-dialog { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: var(--s-6); max-width: 400px; width: 90%; box-shadow: 0 8px 32px oklch(0% 0 0 / 0.15); animation: oms-card-in 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
@keyframes oms-overlay-in { from { opacity: 0; } }
@keyframes oms-card-in { from { opacity: 0; transform: translateY(8px); } }
.spk-dialog h3 { font-size: 16px; font-weight: 600; margin: 0 0 var(--s-3); color: var(--fg); }
.spk-dialog p { font-size: 14px; color: var(--muted); margin: 0 0 var(--s-5); line-height: 1.5; }
.spk-dialog-actions { display: flex; justify-content: flex-end; gap: var(--s-2); }
.danger-confirm { color: var(--error) !important; border-color: var(--error) !important; }
.danger-confirm:hover { background: var(--error-soft) !important; }

/* 声纹骨架屏 / Voiceprint skeleton */
.vp-skeleton { display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-2) 0; }
.vp-skeleton-line { height: 14px; background: linear-gradient(90deg, var(--surface-2) 25%, var(--border) 50%, var(--surface-2) 75%); background-size: 200% 100%; border-radius: var(--radius-sm); animation: vp-shimmer 1.5s infinite; }
.vp-skeleton-line.short { width: 60%; }
@keyframes vp-shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* 待办事项 / Todo items */
.todo-body { flex: 1; min-width: 0; }

/* ESC 快捷键标识 / ESC shortcut indicator */
.spk-dialog-actions kbd {
  font-family: var(--font-mono);
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 3px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--subtle);
  line-height: 1.3;
  margin-left: 4px;
}

@media (max-width: 920px) {
  .empty-state { padding: var(--s-7) var(--s-4); }
  .spk-unified-input { max-width: 100%; }
  .spk-detail-head { flex-direction: column; align-items: flex-start; gap: var(--s-3); }
  .spk-detail-actions { width: 100%; }
  .spk-stat-cards { grid-template-columns: 1fr; }
  .spk-meta { display: none; }
}
</style>
