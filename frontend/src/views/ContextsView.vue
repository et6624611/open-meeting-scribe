<script setup lang="ts">
/**
 * 企业版"我的空间"首页/会议库（档③ 增量 3a）
 * 数据源 GET /api/v1/context/tasks（本人 owner）；卡片挂 VisibilityBadge（W3-01 销项）；
 * stale 呈现"最后同步于…"（服务端对账态）；无音频回放（契约 §1.4 Web 端无媒体）。
 */
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useContextsStore } from '@/stores/contexts'
import VisibilityBadge from '@/components/common/VisibilityBadge.vue'
import PublishedCopiesMenu from '@/components/common/PublishedCopiesMenu.vue'
import EnterpriseConsentGate from '@/components/modals/EnterpriseConsentGate.vue'

const { t } = useI18n()
const contexts = useContextsStore()
onMounted(() => { void contexts.loadTasks() })

function fmtDate(s: string | null): string {
  return s ? s.slice(0, 10) : '—'
}
</script>

<template>
  <div class="cx-root">
    <header class="cx-head">
      <h1>{{ t('enterprise.library.title') }}</h1>
      <button class="cx-refresh" @click="contexts.loadTasks()">{{ t('common.action.retry') }}</button>
    </header>

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

    <!-- 首次知情同意卡：库内看到纪要即触发一次（与详情页同一 ack 源） -->
    <EnterpriseConsentGate :active="contexts.tasks.length > 0" />
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
.cx-empty { color: var(--muted, #666); font-size: var(--fs-12, 12px); }
.cx-error { color: var(--warn, #c33); font-size: var(--fs-12, 12px); }
</style>
