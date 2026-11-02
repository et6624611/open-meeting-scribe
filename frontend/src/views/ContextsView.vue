<script setup lang="ts">
/**
 * 企业版会议库（档③ 3a + P1-WP-3 空间双模式）
 * 私有空间=本人原件（D013 后服务端恒排除 team 行，本视图数据源=contexts.tasks 单侧数组，
 * 结构上不可能混入副本卡）；团队空间=该团队公开副本（contexts.teamTasks，卡片=副本 DTO 实码字段）。
 * 发布人显示名待 GET members 端点（BE 缺项已播报）：自有行显"您"，他人行缺名回退不渲染该行、不猜。
 */
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useContextsStore } from '@/stores/contexts'
import { useSpaceStore } from '@/stores/space'
import { useUserStore } from '@/stores/user'
import VisibilityBadge from '@/components/common/VisibilityBadge.vue'
import PublishedCopiesMenu from '@/components/common/PublishedCopiesMenu.vue'
import EnterpriseConsentGate from '@/components/modals/EnterpriseConsentGate.vue'

const { t } = useI18n()
const contexts = useContextsStore()
const space = useSpaceStore()
const userStore = useUserStore()

onMounted(() => {
  void contexts.loadTasks()
  void space.loadTeams()
})

function fmtDate(s: string | null): string {
  return s ? s.slice(0, 10) : '—'
}

function publisherLabel(uid: string): string | null {
  if (uid === userStore.user?.id) return t('enterprise.team.self')
  const name = space.memberName(uid)
  return name ?? null
}
</script>

<template>
  <div class="cx-root">
    <header class="cx-head">
      <h1>{{ space.isTeamSpace ? (space.currentSpaceName || t('enterprise.library.title')) : t('enterprise.library.title') }}</h1>
      <button class="cx-refresh" @click="contexts.loadTasks()">{{ t('common.action.retry') }}</button>
    </header>

    <!-- 团队空间=公开副本面（规格 §5.1；卡点开=详情团队形态；数据源 teamTasks 与私有 tasks 物理分离） -->
    <template v-if="space.isTeamSpace">
      <p v-if="contexts.loading && !contexts.teamTasks.length" class="cx-empty">{{ t('enterprise.library.loading') }}</p>
      <p v-else-if="contexts.loadError" class="cx-error" role="alert">{{ contexts.loadError }}</p>
      <p v-else-if="!contexts.teamTasks.length" class="cx-empty">{{ t('enterprise.team.empty') }}</p>
      <ul v-else class="cx-list">
        <li v-for="task in contexts.teamTasks" :key="task.task_id">
          <RouterLink class="cx-card" :to="`/meeting/${task.task_id}`">
            <div class="cx-card-top">
              <span class="cx-title">{{ task.title || task.task_id }}</span>
              <VisibilityBadge visibility="team" />
            </div>
            <div class="cx-meta">
              <span>{{ fmtDate(task.updated_at) }}</span>
              <span v-if="publisherLabel(task.publisher_user_id)" class="cx-publisher"> · {{ t('enterprise.team.published_by', { name: publisherLabel(task.publisher_user_id) }) }}</span>
            </div>
          </RouterLink>
        </li>
      </ul>
    </template>

    <!-- 私有空间=本人原件（D013 后服务端恒排除 team 行；本分支数据源=tasks 单侧数组） -->
    <template v-else>
      <p v-if="contexts.loading && !contexts.tasks.length" class="cx-empty">{{ t('enterprise.library.loading') }}</p>
      <p v-else-if="contexts.loadError" class="cx-error" role="alert">{{ contexts.loadError }}</p>
      <p v-else-if="!contexts.tasks.length" class="cx-empty">{{ t('enterprise.library.empty') }}</p>

      <ul v-else class="cx-list">
        <li v-for="task in contexts.tasks" :key="task.task_id">
          <RouterLink class="cx-card" :to="`/meeting/${task.task_id}`">
            <div class="cx-card-top">
              <span class="cx-title">{{ task.title || task.task_id }}</span>
              <PublishedCopiesMenu :copies="task.published_copies ?? []" @withdrawn="contexts.loadTasks()" />
              <VisibilityBadge :visibility="task.visibility" />
            </div>
            <div class="cx-meta">
              <span>{{ fmtDate(task.updated_at) }}</span>
              <span v-if="task.sync_status === 'stale'" class="cx-stale"> · {{ t('enterprise.library.last_synced', { time: fmtDate(task.updated_at) }) }}</span>
            </div>
          </RouterLink>
        </li>
      </ul>
    </template>

    <!-- 首次知情同意卡：库内看到纪要即触发一次（与详情页同一 ack 源；仅私有面原件语义） -->
    <EnterpriseConsentGate v-if="!space.isTeamSpace" :active="contexts.tasks.length > 0" />
  </div>
</template>

<style scoped>
.cx-root { max-width: 860px; margin: 0 auto; padding: calc(var(--s-3, 16px) * 1.5); color: var(--fg, #222); }
.cx-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: var(--s-3, 16px); }
.cx-head h1 { font-size: 17px; margin: 0; }
.cx-refresh { border: none; background: none; color: var(--accent, #2a6); cursor: pointer; font-size: var(--fs-12, 12px); }
.cx-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--s-2, 10px); }
.cx-card { display: block; padding: var(--s-3, 16px); background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); text-decoration: none; color: inherit; }
.cx-card:hover { border-color: var(--accent, #2a6); }
.cx-card:focus-visible { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 2px; }
.cx-card-top { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2, 8px); }
.cx-title { font-weight: 600; font-size: var(--fs-13, 13px); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cx-meta { margin-top: 4px; font-size: var(--fs-11, 11px); color: var(--muted, #666); }
.cx-stale { color: var(--muted, #666); }
.cx-publisher { color: var(--muted, #666); }
.cx-empty { color: var(--muted, #666); font-size: var(--fs-12, 12px); }
.cx-error { color: var(--warn, #c33); font-size: var(--fs-12, 12px); }
</style>
