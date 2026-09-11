<template>
  <div class="sb-timeline" :class="{ 'all-collapsed': layout.timelineAllCollapsed }">
    <template v-for="group in taskStore.groupedTasks" :key="group.label">
      <!-- 日期标记 -->
      <div class="sb-date-group" :class="{ 'is-collapsed': isCollapsed(group.label) }">
        <div
          class="sb-date-marker"
          :class="{ 'is-today': group.isToday }"
          @click="toggleGroup(group.label)"
        >
          <span class="sb-date-node"></span>
          <span class="sb-date-label">{{ group.label }}</span>
          <span class="sb-date-sub">{{ t('task.group_count', { count: group.tasks.length }) }}</span>
          <svg class="sb-date-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>

        <!-- 会议条目列表 -->
        <div class="sb-date-content">
          <TaskCard
            v-for="(task, idx) in group.tasks"
            :key="task.task_id"
            :task="task"
            :data-task-id="task.task_id"
            :is-active="task.task_id === taskStore.currentTaskId"
            :is-latest="group === taskStore.groupedTasks[0] && idx === 0"
            @select="onSelect"
            @menu="onMenu"
            @retry="onRetry"
            @check-settings="onCheckSettings"
            @reupload="onReupload"
            @rerecord="onRerecord"
            @view-details="onViewDetails"
          />
        </div>
      </div>
    </template>

    <!-- 空状态 -->
    <div v-if="taskStore.groupedTasks.length === 0 && !taskStore.loading" style="padding: 20px 0; text-align: center; color: var(--subtle); font-size: 12px;">
      {{ taskStore.searchQuery ? t('task.empty_search') : t('task.empty') }}
    </div>

    <!-- 加载中 -->
    <div v-if="taskStore.loading" style="padding: 20px 0; text-align: center; color: var(--subtle); font-size: 12px;">
      {{ t('task.loading') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { useLayoutStore } from '@/stores/layout'
import { usePlayerStore } from '@/stores/player'
import TaskCard from './TaskCard.vue'
import { retranscribe } from '@/api/tasks'

const { t } = useI18n()
const taskStore = useTaskStore()
const layout = useLayoutStore()
const player = usePlayerStore()
const router = useRouter()

/** 播放开始时侧边栏默认定位：展开所在日期组并滚动到该会议条目 */
watch(() => player.taskId, (id) => {
  if (!id) return
  const group = taskStore.groupedTasks.find(g => g.tasks.some(t => t.task_id === id))
  if (group && isCollapsed(group.label)) toggleGroup(group.label)
  nextTick(() => {
    document.querySelector(`.sb-timeline [data-task-id="${id}"]`)
      ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  })
}, { immediate: true })

/** 手动折叠的日期组（与全局 all-collapsed 叠加） */
const collapsedGroups = reactive(new Set<string>())

/** 组是否折叠：全局全部折叠 OR 手动折叠了该组 */
function isCollapsed(label: string): boolean {
  return layout.timelineAllCollapsed || collapsedGroups.has(label)
}

function toggleGroup(label: string) {
  if (layout.timelineAllCollapsed) {
    // 全局折叠态下点击某组 → 退出全局折叠，仅展开该组（其余保持折叠）
    layout.timelineAllCollapsed = false
    collapsedGroups.clear()
    for (const g of taskStore.groupedTasks) {
      if (g.label !== label) collapsedGroups.add(g.label)
    }
    return
  }
  if (collapsedGroups.has(label)) {
    collapsedGroups.delete(label)
  } else {
    collapsedGroups.add(label)
  }
}

function onSelect(taskId: string) {
  taskStore.selectTask(taskId)
  const task = taskStore.currentTask
  if (!task) return

  // 所有非录音任务统一进入纪要页（中间状态由 GeneratingView 内联处理）
  if (task.status === 'recording') {
    router.push({ name: 'recording', params: { taskId } })
  } else {
    router.push({ name: 'generating', params: { taskId } })
  }
}

async function onMenu(taskId: string, event: MouseEvent, newName?: string) {
  if (event.type === 'delete') {
    try {
      await taskStore.removeTask(taskId)
      if (taskStore.currentTaskId === taskId) {
        router.push('/')
      }
    } catch (e) {
      console.error('delete failed:', e)
      alert(t('task.errors.delete_failed'))
    }
  } else if (event.type === 'rename' && newName) {
    try {
      const { updateTask } = await import('@/api/tasks')
      await updateTask(taskId, { title: newName })
      await taskStore.loadTasks()
    } catch (e) {
      console.error('rename failed:', e)
      alert(t('task.errors.rename_failed'))
    }
  } else if (event.type === 'retry') {
    await onRetry(taskId)
  }
}

async function onRetry(taskId: string) {
  try {
    await retranscribe(taskId)
    // 重新加载任务列表以更新状态
    await taskStore.loadTasks()
  } catch (e) {
    console.error('retry failed:', e)
    alert(t('task.errors.retry_failed'))
  }
}

function onCheckSettings() {
  router.push('/settings')
}

function onReupload(taskId: string) {
  // TODO: 实现重新上传逻辑
  console.log('reupload task:', taskId)
  alert(t('task.errors.reupload_wip'))
}

function onRerecord(taskId: string) {
  // TODO: 实现重新录制逻辑
  console.log('rerecord task:', taskId)
  alert(t('task.errors.reupload_wip'))
}

function onViewDetails(taskId: string) {
  taskStore.selectTask(taskId)
  router.push({ name: 'generating', params: { taskId } })
}
</script>
