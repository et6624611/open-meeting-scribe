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
          <span class="sb-date-sub">{{ group.tasks.length }} 个会议</span>
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
            @view-details="onViewDetails"
          />
        </div>
      </div>
    </template>

    <!-- 空状态 -->
    <div v-if="taskStore.groupedTasks.length === 0 && !taskStore.loading" style="padding: 20px 0; text-align: center; color: var(--subtle); font-size: 12px;">
      {{ taskStore.searchQuery ? '没有匹配的会议' : '暂无会议记录' }}
    </div>

    <!-- 加载中 -->
    <div v-if="taskStore.loading" style="padding: 20px 0; text-align: center; color: var(--subtle); font-size: 12px;">
      加载中…
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/task'
import { useLayoutStore } from '@/stores/layout'
import { usePlayerStore } from '@/stores/player'
import TaskCard from './TaskCard.vue'
import { retranscribe } from '@/api/tasks'

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

  // 根据任务状态路由到对应视图
  if (task.status === 'recording') {
    router.push({ name: 'recording', params: { taskId } })
  } else if (task.status === 'pending' || task.status === 'transcribing' || task.status === 'summarizing') {
    router.push({ name: 'processing', params: { taskId } })
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
      console.error('删除失败:', e)
      alert('删除失败，请重试')
    }
  } else if (event.type === 'rename' && newName) {
    try {
      const { updateTask } = await import('@/api/tasks')
      await updateTask(taskId, { title: newName })
      await taskStore.loadTasks()
    } catch (e) {
      console.error('重命名失败:', e)
      alert('重命名失败，请重试')
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
    console.error('重试失败:', e)
    alert('重试失败，请检查网络连接')
  }
}

function onCheckSettings() {
  router.push('/settings')
}

function onReupload(taskId: string) {
  // TODO: 实现重新上传逻辑
  console.log('重新上传任务:', taskId)
  alert('重新上传功能开发中')
}

function onViewDetails(taskId: string) {
  taskStore.selectTask(taskId)
  router.push({ name: 'generating', params: { taskId } })
}
</script>
