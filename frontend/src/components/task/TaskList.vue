<template>
  <div class="sb-history-inner">
    <DynamicScroller
      v-if="virtualItems.length > 0 || taskStore.loading"
      ref="scrollerRef"
      class="sb-virtual-scroller"
      :items="virtualItems"
      :min-item-size="48"
      key-field="key"
    >
      <template #default="{ item, index, active }">
        <DynamicScrollerItem
          :item="item"
          :active="active"
          :size-dependencies="[item.type === 'task' && taskStore.currentTaskId]"
          :data-index="index"
        >
          <div
            class="sb-vs-item"
            :class="{
              'is-header': item.type === 'header',
              'is-task': item.type === 'task',
              'is-first': index === 0,
              'is-today': item.type === 'header' && item.isToday,
              'is-collapsed': item.type === 'header' && isCollapsed(item.groupLabel),
            }"
          >
            <!-- 空状态 -->
            <div v-if="item.type === 'empty'" style="padding: 20px 0; text-align: center; color: var(--subtle); font-size: 12px;">
              {{ taskStore.sidebarSearchQuery ? t('task.empty_search') : t('task.empty') }}
            </div>
            <!-- 加载中 -->
            <div v-else-if="item.type === 'loading'" style="padding: 20px 0; text-align: center; color: var(--subtle); font-size: 12px;">
              {{ t('task.loading') }}
            </div>
            <!-- 日期组头 -->
            <div
              v-else-if="item.type === 'header'"
              class="sb-date-group"
              :class="{ 'is-collapsed': isCollapsed(item.groupLabel) }"
            >
              <div
                class="sb-date-marker"
                :class="{ 'is-today': item.isToday }"
                @click="toggleGroup(item.groupLabel)"
              >
                <span class="sb-date-node"></span>
                <span class="sb-date-label">{{ item.label }}</span>
                <span class="sb-date-sub">{{ t('task.group_count', { count: item.count }) }}</span>
                <svg class="sb-date-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </div>
            </div>
            <!-- 会议卡片 -->
            <TaskCard
              v-else
              :key="item.task.task_id"
              :task="item.task"
              :data-task-id="item.task.task_id"
              :is-active="item.task.task_id === taskStore.currentTaskId"
              :is-latest="item.isLatest"
              @select="onSelect"
              @menu="onMenu"
              @retry="onRetry"
              @check-settings="onCheckSettings"
              @reupload="onReupload"
              @rerecord="onRerecord"
              @view-details="onViewDetails"
            />
          </div>
        </DynamicScrollerItem>
      </template>
    </DynamicScroller>

    <!-- 空状态（无数据且非加载中） -->
    <div v-if="virtualItems.length === 0 && !taskStore.loading" style="padding: 20px 0; text-align: center; color: var(--subtle); font-size: 12px;">
      {{ taskStore.sidebarSearchQuery ? t('task.empty_search') : t('task.empty') }}
    </div>

    <!-- 加载中（无数据时） -->
    <div v-if="virtualItems.length === 0 && taskStore.loading" style="padding: 20px 0; text-align: center; color: var(--subtle); font-size: 12px;">
      {{ t('task.loading') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import { useTaskStore } from '@/stores/task'
import { useLayoutStore } from '@/stores/layout'
import { usePlayerStore } from '@/stores/player'
import TaskCard from './TaskCard.vue'
import { retranscribe } from '@/api/tasks'
import type { Task } from '@/api/types'

const { t } = useI18n()
const taskStore = useTaskStore()
const layout = useLayoutStore()
const player = usePlayerStore()
const router = useRouter()

const scrollerRef = ref<InstanceType<typeof DynamicScroller> | null>(null)

/** 虚拟滚动一维数据源：日期组头 + 任务卡片混合 */
type SidebarItem =
  | { type: 'header'; key: string; size: number; label: string; isToday: boolean; count: number; groupLabel: string }
  | { type: 'task'; key: string; size: number; task: Task; isLatest: boolean; groupLabel: string }
  | { type: 'empty'; key: string; size: number }
  | { type: 'loading'; key: string; size: number }

const virtualItems = computed((): SidebarItem[] => {
  const items: SidebarItem[] = []
  const groups = taskStore.groupedTasks
  const firstGroup = groups.length > 0 ? groups[0] : null

  for (const group of groups) {
    items.push({
      type: 'header',
      key: `h-${group.label}`,
      size: 40,
      label: group.label,
      isToday: group.isToday,
      count: group.tasks.length,
      groupLabel: group.label,
    })
    if (!isCollapsed(group.label)) {
      group.tasks.forEach((task, idx) => {
        items.push({
          type: 'task',
          key: `t-${task.task_id}`,
          size: 64,
          task,
          isLatest: group === firstGroup && idx === 0,
          groupLabel: group.label,
        })
      })
    }
  }
  return items
})

/** 播放开始时侧边栏默认定位：滚动到对应任务 */
watch(() => player.taskId, (id) => {
  if (!id) return
  const group = taskStore.groupedTasks.find(g => g.tasks.some(t => t.task_id === id))
  if (!group) return
  if (isCollapsed(group.label)) toggleGroup(group.label)
  nextTick(() => {
    const idx = virtualItems.value.findIndex(
      item => item.type === 'task' && (item as any).task.task_id === id,
    )
    if (idx >= 0) {
      scrollerRef.value?.scrollToItem(idx)
    }
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

  // 录音中（含暂停）任务进入录音页，其余进入纪要页（中间状态由 GeneratingView 内联处理）
  if (task.status === 'recording' || task.status === 'paused') {
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
      const updated = await updateTask(taskId, { title: newName })
      // 增量更新：直接用返回值 patch 本地，避免全量 reload
      taskStore.patchTaskLocal(taskId, { title: updated.title })
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
    // 增量更新：乐观将状态置为识别中，避免全量 reload
    taskStore.patchTaskLocal(taskId, { status: 'transcribing', error: undefined, error_category: undefined })
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
