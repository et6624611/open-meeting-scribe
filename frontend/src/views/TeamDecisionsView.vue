<script setup lang="ts">
/**
 * 团队决策聚合视图（/decisions 企业形态；P1-WP-3，规格 §5.2）
 *
 * 本团队全部已公开决策的摊平列表（数据源=副本详情聚合，只链团队副本不链私有原件——防越权穿透）；
 * 卡片沿用 P0 决策样式（左描边+状态 pill），按公开时间倒序、关键词过滤、按来源会议分组筛选。
 * T-002 债偿还面：私有空间不承接（"切换到团队查看公开决策"一句给出口）。
 * 删除（裁决③）在卡片菜单两步确认；恢复入口在变更记录（留痕即回滚依据）。
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSpaceStore } from '@/stores/space'
import { useContextsStore } from '@/stores/contexts'
import { getTeamTask, deleteTeamDecision } from '@/api/teams'
import { aggregateDecisions, type AggregatedDecision } from '@/utils/teamSpacesLogic'
import { showToast } from '@/composables/useToast'
import { useRoute, useRouter } from 'vue-router'
import EmptyHint from '@/components/common/EmptyHint.vue'
import SkeletonList from '@/components/common/SkeletonList.vue'

const { t } = useI18n()
const space = useSpaceStore()
const contexts = useContextsStore()
const route = useRoute()
const router = useRouter()

const rows = ref<AggregatedDecision[]>([])
const loading = ref(false)
const error = ref(false)
const query = ref('')
const sourceFilter = ref('')
const pendingDelete = ref('')

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return rows.value.filter((r) =>
    (!sourceFilter.value || r.teamTaskId === sourceFilter.value)
    && (!q || r.text.toLowerCase().includes(q) || r.taskTitle.toLowerCase().includes(q)),
  )
})
const sources = computed(() => {
  const map = new Map<string, string>()
  for (const r of rows.value) map.set(r.teamTaskId, r.taskTitle)
  return [...map.entries()]
})

async function loadAll() {
  await space.ensureReady() // D014：重载/深链首帧等空间就绪再判定团队上下文取数
  if (!space.isTeamSpace) return
  loading.value = true
  error.value = false
  try {
    if (!contexts.teamTasks.length) await contexts.loadTasks()
    const details = await Promise.all(
      contexts.teamTasks.map(async (summary) => ({ summary, detail: await getTeamTask(space.currentId, summary.task_id).catch(() => null) })),
    )
    rows.value = aggregateDecisions(details)
  } catch {
    error.value = true
  } finally { loading.value = false }
}

async function confirmDelete(r: AggregatedDecision) {
  try {
    await deleteTeamDecision(space.currentId, r.teamTaskId, r.decisionId)
    showToast(t('enterprise.decisions.deleted'), 'success')
    rows.value = rows.value.filter((x) => x.decisionId !== r.decisionId || x.teamTaskId !== r.teamTaskId)
    pendingDelete.value = ''
  } catch {
    showToast(t('enterprise.decisions.delete_failed'), 'error')
  }
}

function openSource(r: AggregatedDecision) {
  router.push(`/meeting/${r.teamTaskId}?tab=decisions`)
}

onMounted(() => { void loadAll() })
void route
</script>

<template>
  <div class="td-root">
    <header class="td-head">
      <h1>{{ space.isTeamSpace ? t('enterprise.decisionsTeam.title') : t('enterprise.decisionsTeam.title') }}</h1>
      <button class="td-refresh" @click="loadAll">{{ t('common.action.retry') }}</button>
    </header>

    <p v-if="!space.isTeamSpace" class="td-empty">{{ t('enterprise.decisionsTeam.private_hint') }}</p>

    <template v-else>
      <p v-if="error" class="td-error" role="alert">{{ t('enterprise.decisionsTeam.load_failed') }}</p>
      <div v-if="rows.length" class="td-filters">
        <input v-model="query" type="search" class="td-search" :placeholder="t('enterprise.decisionsTeam.search_placeholder')" :aria-label="t('enterprise.decisionsTeam.search_placeholder')">
        <select v-model="sourceFilter" class="td-source" :aria-label="t('enterprise.decisionsTeam.filter_source')">
          <option value="">{{ t('enterprise.decisionsTeam.filter_all') }}</option>
          <option v-for="[id, title] in sources" :key="id" :value="id">{{ title }}</option>
        </select>
      </div>

      <SkeletonList v-else-if="loading" :rows="5" />
      <div v-else-if="!rows.length && !error" class="td-empty-wrap">
        <!-- B2 空态插画化：图标+原文案+错峰浮现，不新增能力 -->
        <EmptyHint card>
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
          </template>
          <p class="td-empty">{{ t('enterprise.decisionsTeam.empty') }}</p>
        </EmptyHint>
      </div>

      <ul v-if="filtered.length" class="td-list">
        <li v-for="(r, idx) in filtered" :key="`${r.teamTaskId}-${r.decisionId}`" class="td-card" :style="{ animationDelay: `${Math.min(idx, 8) * 45}ms` }">
          <p class="td-text">{{ r.text }}</p>
          <div class="td-meta">
            <span v-if="r.statusText" class="td-status">{{ r.statusText }}</span>
            <button type="button" class="td-source-link" @click="openSource(r)">{{ t('enterprise.decisionsTeam.from', { title: r.taskTitle }) }}</button>
            <span v-if="space.canEdit" class="td-ops">
              <template v-if="pendingDelete !== `${r.teamTaskId}-${r.decisionId}`">
                <button type="button" class="td-delete" @click="pendingDelete = `${r.teamTaskId}-${r.decisionId}`">{{ t('enterprise.decisions.delete_btn') }}</button>
              </template>
              <template v-else>
                <span class="td-delete-confirm">{{ t('enterprise.decisions.delete_confirm') }}</span>
                <button type="button" class="td-delete-cancel" @click="pendingDelete = ''">{{ t('common.action.cancel') }}</button>
                <button type="button" class="td-delete" @click="confirmDelete(r)">{{ t('enterprise.decisions.delete_btn') }}</button>
              </template>
            </span>
          </div>
        </li>
      </ul>
      <p v-else-if="rows.length && !filtered.length" class="td-empty">{{ t('enterprise.decisionsTeam.no_match') }}</p>
    </template>
  </div>
</template>

<style scoped>
.td-root { max-width: 820px; margin: 0 auto; padding: calc(var(--s-3, 16px) * 1.5); color: var(--fg, #222); }
.td-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: var(--s-3, 16px); }
.td-head h1 { font-size: 17px; margin: 0; }
.td-refresh { border: none; background: none; color: var(--accent, #2a6); cursor: pointer; font-size: var(--fs-12, 12px); }
.td-filters { display: flex; gap: 8px; margin-bottom: var(--s-3, 14px); flex-wrap: wrap; }
.td-search { flex: 1; min-width: 180px; padding: 7px 10px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); background: var(--surface-2, #fafaf8); font-size: var(--fs-12, 12px); color: var(--fg, #222); }
.td-source { padding: 7px 10px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); background: var(--surface, #fff); font-size: var(--fs-12, 12px); color: var(--fg, #222); }
.td-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--s-2, 10px); }
.td-card { background: var(--surface, #fff); border: 1px solid var(--border, #e6e6e2); border-left: 3px solid var(--accent, #2a6); border-radius: var(--radius-sm, 8px); padding: var(--s-3, 14px) var(--s-4, 18px); display: flex; flex-direction: column; gap: 6px; animation: td-rise 0.28s ease both; transition: border-color 0.16s ease, box-shadow 0.16s ease; }
.td-card:hover { border-color: var(--accent, #2a6); box-shadow: 0 3px 12px rgba(0, 0, 0, 0.05); }
@keyframes td-rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .td-card { animation: none; transition: none; } }
.td-empty-wrap { display: flex; justify-content: center; padding: var(--s-5, 24px) 0; }
.td-text { margin: 0; font-size: var(--fs-13, 13px); line-height: 1.7; }
.td-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: var(--fs-11, 11px); color: var(--muted, #666); }
.td-status { background: var(--surface-2, #f2f2f0); padding: 1px 8px; border-radius: 999px; }
.td-source-link { border: none; background: none; color: var(--muted, #666); font-size: var(--fs-11, 11px); cursor: pointer; text-decoration: underline; text-underline-offset: 3px; padding: 0; }
.td-source-link:hover { color: var(--accent, #2a6); }
.td-ops { margin-left: auto; display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.td-delete { border: none; background: none; color: var(--warn, #c33); font-size: var(--fs-11, 11px); cursor: pointer; padding: 0; }
.td-delete-cancel { border: none; background: none; color: var(--muted, #666); font-size: var(--fs-11, 11px); cursor: pointer; padding: 0; }
.td-delete-confirm { color: var(--muted, #666); }
.td-empty { color: var(--muted, #666); font-size: var(--fs-12, 12px); }
.td-error { color: var(--warn, #c33); font-size: var(--fs-12, 12px); }
</style>
