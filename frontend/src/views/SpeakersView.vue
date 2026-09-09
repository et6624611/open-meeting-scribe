<template>
  <div>
    <!-- 列表视图 -->
    <div v-if="!selectedSpeaker">
      <div class="main-head">
        <h1>说话人管理</h1>
        <p class="sub">管理说话人身份档案，追溯会议参与与发言记录</p>
      </div>
      <div class="spk-create">
        <input v-model="newName" class="spk-create-input" placeholder="输入说话人名称…" @keyup.enter="onCreate" />
        <button class="btn btn-primary" @click="onCreate" :disabled="!newName.trim()">添加</button>
      </div>
      <div v-if="speakers.length > 0" class="spk-list">
        <div v-for="spk in speakers" :key="spk.id" class="spk-item" @click="openDetail(spk)">
          <div class="spk-info">
            <div class="spk-text">
              <span class="spk-name" :style="{ color: getColor(spk.id) }">{{ spk.name }}</span>
              <span v-if="isMe(spk)" class="spk-badge-me">我</span>
            </div>
          </div>
          <div class="spk-meta-row">
            <span v-if="spk.meeting_count" class="spk-meta">{{ spk.meeting_count }} 次会议</span>
            <div class="spk-actions" @click.stop>
              <button v-if="!isMe(spk)" class="spk-action-btn" @click="onSetMe(spk.id)">设为我</button>
              <button class="spk-action-btn danger" @click="onDelete(spk.id)">删除</button>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">暂无说话人</div>
    </div>

    <!-- 详情视图 -->
    <div v-else class="spk-detail">
      <button class="spk-back-btn" @click="backToList">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m15 18-6-6 6-6"/></svg>
        返回列表
      </button>

      <div class="spk-detail-head">
        <div class="spk-detail-left">
          <div class="spk-detail-info">
            <div class="spk-detail-name">
              <span :style="{ color: getColor(selectedSpeaker.id) }">{{ selectedSpeaker.name }}</span>
              <span v-if="isMe(selectedSpeaker)" class="spk-me-badge">当前用户</span>
            </div>
            <div class="spk-detail-role">{{ selectedSpeaker.alias || '' }}</div>
          </div>
        </div>
        <div class="spk-detail-actions">
          <button v-if="!isMe(selectedSpeaker)" class="btn btn-secondary btn-sm" @click="onToggleMe">设为我</button>
          <button class="btn btn-secondary btn-sm" @click="onEdit">编辑</button>
          <button class="btn btn-secondary btn-sm" style="color:var(--rec)" @click="onDelete(selectedSpeaker.id)">删除</button>
        </div>
      </div>

      <!-- 统计卡片 -->
      <div class="spk-stat-cards">
        <div class="spk-stat-card">
          <div class="label">参与会议</div>
          <div class="value">{{ stat.meetings.length }}</div>
          <div class="sub">次会议</div>
        </div>
        <div class="spk-stat-card">
          <div class="label">总发言时长</div>
          <div class="value">{{ Math.round(stat.totalDuration / 60) }}</div>
          <div class="sub">分钟</div>
        </div>
        <div class="spk-stat-card">
          <div class="label">待办事项</div>
          <div class="value">{{ stat.todos.length }}</div>
          <div class="sub">项待办</div>
        </div>
      </div>

      <!-- 声纹管理 -->
      <div v-if="voiceprintStatus" class="spk-voiceprint-section">
        <div class="vp-header">
          <h3 class="vp-title">声纹信息</h3>
          <span :class="['vp-badge', voiceprintStatus.has_voiceprint ? 'vp-registered' : 'vp-not-registered']">
            {{ voiceprintStatus.has_voiceprint ? '已注册' : '未注册' }}
          </span>
        </div>
        <div class="vp-stats">
          <div class="vp-stat-item">
            <span class="vp-stat-label">样本数量：</span>
            <span class="vp-stat-value">{{ voiceprintStatus.sample_count }}</span>
          </div>
          <div class="vp-stat-item">
            <span class="vp-stat-label">总时长：</span>
            <span class="vp-stat-value">{{ formatTime(voiceprintStatus.total_sample_duration) }}</span>
          </div>
          <div v-if="voiceprintStatus.updated_at" class="vp-stat-item">
            <span class="vp-stat-label">更新时间：</span>
            <span class="vp-stat-value">{{ formatDate(voiceprintStatus.updated_at) }}</span>
          </div>
        </div>
        <div class="vp-actions">
          <button class="btn btn-secondary btn-sm" @click="onRebuildVoiceprint" :disabled="voiceprintLoading">
            {{ voiceprintLoading ? '重建中…' : '重建声纹' }}
          </button>
          <button 
            v-if="voiceprintStatus.has_voiceprint" 
            class="btn btn-secondary btn-sm" 
            style="color:var(--rec)" 
            @click="onDeleteVoiceprint"
            :disabled="voiceprintLoading"
          >
            删除声纹
          </button>
        </div>
      </div>

      <!-- Tab 切换 -->
      <div class="spk-tabs">
        <button class="spk-tab" :class="{ 'is-active': activeTab === 'meetings' }" @click="activeTab = 'meetings'">参与的会议</button>
        <button class="spk-tab" :class="{ 'is-active': activeTab === 'utterances' }" @click="activeTab = 'utterances'">发言摘要</button>
        <button class="spk-tab" :class="{ 'is-active': activeTab === 'todos' }" @click="activeTab = 'todos'">待办事项</button>
      </div>

      <!-- 会议列表 -->
      <div v-show="activeTab === 'meetings'" class="spk-tab-panel is-active">
        <div v-if="stat.meetings.length === 0" class="spk-empty">暂无参与的会议</div>
        <div v-for="m in sortedMeetings" :key="m.task_id" class="spk-meeting-card" @click="openTask(m.task_id)">
          <div class="mc-head">
            <span class="mc-title">{{ m.title }}</span>
            <span class="mc-date">{{ formatDate(m.date) }}</span>
          </div>
          <div class="mc-excerpt">{{ m.excerpt }}</div>
          <div class="mc-stats">
            <span>{{ Math.round(m.duration / 60) }} 分钟</span>
            <span>{{ m.utteranceCount }} 条发言</span>
          </div>
        </div>
      </div>

      <!-- 发言摘要 -->
      <div v-show="activeTab === 'utterances'" class="spk-tab-panel is-active">
        <div v-if="allUtterances.length === 0" class="spk-empty">暂无发言记录</div>
        <div v-for="(u, i) in allUtterances.slice(0, 20)" :key="i" class="spk-utterance" :style="{ borderLeftColor: getColor(selectedSpeaker.id) }">
          <div class="ut-meta">
            <span class="ut-meeting" @click="openTask(u.meetingTaskId)">{{ u.meetingTitle }}</span>
            <span class="ut-time">{{ formatTime(u.start) }}</span>
          </div>
          <div class="ut-text">{{ u.text }}</div>
        </div>
        <div v-if="allUtterances.length > 20" class="spk-empty">仅显示最近 20 条发言</div>
      </div>

      <!-- 待办事项 -->
      <div v-show="activeTab === 'todos'" class="spk-tab-panel is-active">
        <div v-if="stat.todos.length === 0" class="spk-empty">暂无待办事项</div>
        <div v-for="todo in stat.todos" :key="todo.id" class="spk-todo-item">
          <input type="checkbox" class="todo-check" :checked="todo.done" @change="onToggleTodo(todo)" />
          <div class="todo-body">
            <div class="todo-text" :class="{ 'is-done': todo.done }">{{ todo.text }}</div>
            <div class="todo-from">来自：{{ todo.fromTaskTitle }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { fetchSpeakers, createSpeaker, deleteSpeaker, setSpeakerAsMe, updateSpeaker } from '@/api/speakers'
import type { Speaker } from '@/api/speakers'
import { loadSpeakerStats, useSpeakerStat } from '@/composables/useSpeakerStats'
import { getSpeakerColor } from '@/utils/speakerColors'
import { useRouter } from 'vue-router'
import { showToast } from '@/composables/useToast'
import { getVoiceprintStatus, rebuildVoiceprint, deleteVoiceprint, type VoiceprintStatus } from '@/api/voiceprint'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const speakers = ref<Speaker[]>([])
const newName = ref('')
const selectedSpeaker = ref<Speaker | null>(null)
const activeTab = ref<'meetings' | 'utterances' | 'todos'>('meetings')
const voiceprintStatus = ref<VoiceprintStatus | null>(null)
const voiceprintLoading = ref(false)

/** 判断说话人是否为当前用户（通过 linked_user_id 比较） */
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

async function load() {
  speakers.value = await fetchSpeakers()
  if (speakers.value.length > 0) {
    await loadSpeakerStats(speakers.value.map(s => s.id))
  }
}

function getColor(id: string) {
  return getSpeakerColor(id)
}

function openDetail(spk: Speaker) {
  selectedSpeaker.value = spk
  activeTab.value = 'meetings'
}

function backToList() {
  selectedSpeaker.value = null
}

async function onCreate() {
  const name = newName.value.trim()
  if (!name) return
  await createSpeaker(name)
  newName.value = ''
  await load()
}

async function onDelete(id: string) {
  if (!confirm('确定删除该说话人？')) return
  await deleteSpeaker(id)
  if (selectedSpeaker.value?.id === id) {
    selectedSpeaker.value = null
  }
  await load()
}

async function onSetMe(id: string) {
  try {
    await setSpeakerAsMe(id)
    await load()
    if (selectedSpeaker.value?.id === id) {
      selectedSpeaker.value = speakers.value.find(s => s.id === id) || null
    }
    const spk = speakers.value.find(s => s.id === id)
    showToast(`已将「${spk?.name}」设为当前用户`, 'success')
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '设置失败'
    showToast(msg, 'error')
  }
}

async function onToggleMe() {
  if (!selectedSpeaker.value) return
  await onSetMe(selectedSpeaker.value.id)
}

function onEdit() {
  if (!selectedSpeaker.value) return
  const newName = prompt('输入新名称：', selectedSpeaker.value.name)
  if (newName && newName.trim()) {
    updateSpeaker(selectedSpeaker.value.id, { name: newName.trim() })
    load()
  }
}

function openTask(taskId: string) {
  router.push({ name: 'generating', params: { taskId } })
}

function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

function formatTime(seconds: number) {
  if (!seconds) return ''
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// 计算属性
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

async function onToggleTodo(todo: any) {
  // TODO: 调用后端 API 更新待办状态
  todo.done = !todo.done
}

async function onRebuildVoiceprint() {
  if (!selectedSpeaker.value) return
  voiceprintLoading.value = true
  try {
    const result = await rebuildVoiceprint(selectedSpeaker.value.id)
    showToast(`声纹重建成功：${result.meeting_count} 次会议，${Math.round(result.duration_sec / 60)} 分钟`, 'success')
    await loadVoiceprint()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '声纹重建失败'
    showToast(msg, 'error')
  } finally {
    voiceprintLoading.value = false
  }
}

async function onDeleteVoiceprint() {
  if (!selectedSpeaker.value) return
  if (!confirm('确定删除该说话人的声纹数据？')) return
  try {
    await deleteVoiceprint(selectedSpeaker.value.id)
    showToast('声纹已删除', 'success')
    await loadVoiceprint()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '删除声纹失败'
    showToast(msg, 'error')
  }
}

onMounted(load)
</script>

<style scoped>
.spk-create { display: flex; gap: var(--s-2); margin-bottom: var(--s-6); }
.spk-create-input { flex: 1; max-width: 300px; padding: var(--s-2) var(--s-3); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); color: var(--fg); font-size: 14px; outline: none; }
.spk-create-input:focus { border-color: var(--accent); }
.spk-list { display: flex; flex-direction: column; gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.spk-item { display: flex; align-items: center; justify-content: space-between; padding: var(--s-3) var(--s-4); background: var(--surface); cursor: pointer; transition: background 0.12s; }
.spk-item:hover { background: var(--surface-2); }
.spk-info { display: flex; align-items: center; gap: var(--s-3); min-width: 0; }
.spk-text { display: flex; align-items: center; gap: var(--s-2); min-width: 0; }
.spk-name { font-size: 14px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.spk-badge-me { font-size: 10px; padding: 1px 6px; border-radius: 4px; background: var(--accent-soft); color: var(--accent); font-weight: 500; flex-shrink: 0; }
.spk-meta-row { display: flex; align-items: center; gap: var(--s-3); flex-shrink: 0; }
.spk-meta { font-size: 12px; color: var(--muted); }
.spk-actions { display: flex; gap: var(--s-1); }
.spk-action-btn { padding: 4px 10px; font-size: 12px; color: var(--muted); background: transparent; border: 1px solid var(--border); border-radius: var(--radius); cursor: pointer; transition: all 0.12s; }
.spk-action-btn:hover { color: var(--fg); border-color: var(--fg); }
.spk-action-btn.danger:hover { color: var(--rec); border-color: var(--rec); }
.empty-state { text-align: center; padding: var(--s-9) var(--s-7); color: var(--muted); font-size: 13px; }

.spk-me-badge { font-size: 11px; margin-left: var(--s-2); padding: 2px 8px; border-radius: 4px; background: var(--accent-soft); color: var(--accent); font-weight: 500; vertical-align: middle; }

/* 详情视图 */
.spk-back-btn { display: inline-flex; align-items: center; gap: var(--s-1); padding: var(--s-2) 0; margin-bottom: var(--s-4); color: var(--muted); font-size: 13px; background: none; border: none; cursor: pointer; transition: color 0.12s; }
.spk-back-btn:hover { color: var(--fg); }
.spk-detail-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--s-6); padding-bottom: var(--s-4); border-bottom: 1px solid var(--border); }
.spk-detail-left { display: flex; align-items: center; gap: var(--s-3); min-width: 0; }
.spk-detail-info { min-width: 0; }
.spk-detail-name { font-size: 18px; font-weight: 600; display: flex; align-items: center; gap: var(--s-2); }
.spk-detail-role { font-size: 13px; color: var(--muted); margin-top: 2px; }
.spk-detail-actions { display: flex; gap: var(--s-2); flex-shrink: 0; }

/* 统计卡片 */
.spk-stat-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--s-3); margin-bottom: var(--s-6); }
.spk-stat-card { padding: var(--s-4); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); text-align: center; }
.spk-stat-card .label { font-size: 12px; color: var(--muted); margin-bottom: var(--s-1); }
.spk-stat-card .value { font-size: 24px; font-weight: 600; font-family: var(--font-mono); }
.spk-stat-card .sub { font-size: 11px; color: var(--muted); margin-top: 2px; }

/* 声纹管理样式 */
.spk-voiceprint-section { 
  margin-bottom: var(--s-6); 
  padding: var(--s-4); 
  border: 1px solid var(--border); 
  border-radius: var(--radius); 
  background: var(--surface); 
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

@media (max-width: 920px) {
  .empty-state { padding: var(--s-7) var(--s-4); }
  .spk-create-input { max-width: 100%; }
  .spk-detail-head { flex-direction: column; align-items: flex-start; gap: var(--s-3); }
  .spk-detail-actions { width: 100%; }
  .spk-stat-cards { grid-template-columns: 1fr; }
  .spk-meta { display: none; }
}
</style>
