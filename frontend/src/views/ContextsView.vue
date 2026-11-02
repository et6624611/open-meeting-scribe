<script setup lang="ts">
/**
 * 企业版会议库（档③ 3a + P1-WP-3 空间双模式 + B1~B3 版式找回）
 * 私有空间=本人原件（D013 后服务端恒排除 team 行，本视图数据源=contexts.tasks 单侧数组，
 * 结构上不可能混入副本卡）；团队空间=该团队公开副本（contexts.teamTasks，卡片=副本 DTO 实码字段）。
 * 发布人显示名待 GET members 端点（BE 缺项已播报）：自有行显"您"，他人行缺名回退不渲染该行、不猜。
 *
 * 版式找回（UI-RESTORE-INVENTORY B1~B3，个人版同款视觉语言）：
 *  - B1 日期分组（今天/昨天/近7天/更早）+ 丰富卡片 + 悬停摘要预览（懒取详情、逐字缓存，失败不显不猜）；
 *  - B2 空态插画化（EmptyHint 统一语言：图标+文案+已有动线按钮，不新增能力）；
 *  - B3 加载骨架 + 卡片错峰浮现。列表语义与数据源零变化——纯呈现层。
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useContextsStore } from '@/stores/contexts'
import { useSpaceStore } from '@/stores/space'
import { useUserStore } from '@/stores/user'
import { groupByRecency } from '@/utils/recencyGroup'
import VisibilityBadge from '@/components/common/VisibilityBadge.vue'
import PublishedCopiesMenu from '@/components/common/PublishedCopiesMenu.vue'
import EnterpriseConsentGate from '@/components/modals/EnterpriseConsentGate.vue'
import EmptyHint from '@/components/common/EmptyHint.vue'
import SkeletonList from '@/components/common/SkeletonList.vue'

const { t } = useI18n()
const contexts = useContextsStore()
const space = useSpaceStore()
const userStore = useUserStore()

// D014：整页重载首帧先等空间就绪（user 会话+teams+last_space 恢复），再按真实空间取数
onMounted(() => {
  void (async () => {
    await space.ensureReady()
    await contexts.loadTasks()
  })()
})

function fmtDate(s: string | null): string {
  return s ? s.slice(0, 10) : '—'
}

/** B1：日期分组（组序=今天>昨天>近7天>更早，组内保持列表原序=updated_at 倒序） */
const privateGroups = computed(() => groupByRecency(contexts.tasks))
const teamGroups = computed(() => groupByRecency(contexts.teamTasks))

function publisherLabel(uid: string): string | null {
  if (uid === userStore.user?.id) return t('enterprise.team.self')
  const name = space.memberName(uid)
  return name ?? null
}

// ─── B1 悬停摘要预览（个人版 TaskCard hover-card 同款交互语言：600ms 停留触发、离开即收）───
interface HoverPreview { title: string; date: string; summary: string; left: string; top: string }
const hover = ref<HoverPreview | null>(null)
const summaryCache = new Map<string, string | null>()
let hoverTimer: ReturnType<typeof setTimeout> | null = null

function onCardEnter(e: MouseEvent, taskId: string, title: string, date: string) {
  const el = e.currentTarget as HTMLElement
  if (hoverTimer) clearTimeout(hoverTimer)
  hoverTimer = setTimeout(async () => {
    let summary: string | null
    if (summaryCache.has(taskId)) {
      summary = summaryCache.get(taskId) ?? null
    } else {
      const d = await contexts.loadDetail(taskId)
      summary = d?.summary?.trim() ? d.summary : null
      summaryCache.set(taskId, summary)
    }
    if (!summary) return // 无摘要/取失败=不弹（不猜不空弹）
    const rect = el.getBoundingClientRect()
    const cardW = 280
    const left = rect.right + cardW + 16 <= window.innerWidth ? rect.right + 10 : Math.max(8, rect.left - cardW - 10)
    hover.value = {
      title: title || taskId,
      date,
      summary: summary.slice(0, 220) + (summary.length > 220 ? '…' : ''),
      left: `${left}px`,
      top: `${Math.max(8, Math.min(rect.top, window.innerHeight - 220))}px`,
    }
  }, 600)
}
function onCardLeave() {
  if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = null }
  hover.value = null
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
      <SkeletonList v-if="contexts.loading && !contexts.teamTasks.length" :rows="5" />
      <p v-else-if="contexts.loadError" class="cx-error" role="alert">{{ contexts.loadError }}</p>
      <div v-else-if="!contexts.teamTasks.length" class="cx-empty-wrap">
        <EmptyHint card>
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          </template>
          <p class="cx-empty-title">{{ space.justCreatedTeamId === space.currentId ? t('enterprise.team.created_empty') : t('enterprise.team.empty') }}</p>
          <template v-if="space.canEdit" #action>
            <RouterLink to="/members" class="cx-guide-btn">{{ t('sidebar.rail_members') }}</RouterLink>
          </template>
        </EmptyHint>
      </div>
      <template v-else>
        <section v-for="g in teamGroups" :key="g.key" class="cx-group">
          <h2 class="cx-group-head">{{ t(`enterprise.library.group_${g.key}`) }}</h2>
          <ul class="cx-list">
            <li v-for="(task, i) in g.items" :key="task.task_id">
              <RouterLink
                class="cx-card"
                :style="{ animationDelay: `${Math.min(i, 8) * 45}ms` }"
                :to="`/meeting/${task.task_id}`"
                @mouseenter="onCardEnter($event, task.task_id, task.title, fmtDate(task.updated_at))"
                @mouseleave="onCardLeave"
              >
                <span class="cx-eyebrow">{{ t('enterprise.library.eyebrow') }}</span>
                <div class="cx-card-top">
                  <span class="cx-title">{{ task.title || task.task_id }}</span>
                  <VisibilityBadge :visibility="task.visibility" />
                </div>
                <div class="cx-meta">
                  <svg class="cx-meta-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                  <span>{{ fmtDate(task.updated_at) }}</span>
                  <span v-if="publisherLabel(task.publisher_user_id)" class="cx-publisher"> · {{ t('enterprise.team.published_by', { name: publisherLabel(task.publisher_user_id) }) }}</span>
                </div>
              </RouterLink>
            </li>
          </ul>
        </section>
      </template>
    </template>

    <!-- 私有空间=本人原件（D013 后服务端恒排除 team 行；本分支数据源=tasks 单侧数组） -->
    <template v-else>
      <SkeletonList v-if="contexts.loading && !contexts.tasks.length" :rows="5" />
      <p v-else-if="contexts.loadError" class="cx-error" role="alert">{{ contexts.loadError }}</p>
      <div v-else-if="!contexts.tasks.length" class="cx-empty-wrap">
        <EmptyHint card>
          <template #icon>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="12" y2="17"/></svg>
          </template>
          <p class="cx-empty-title">{{ t('enterprise.library.empty') }}</p>
          <template #action>
            <button type="button" class="cx-guide-btn" @click="contexts.loadTasks()">{{ t('common.action.retry') }}</button>
          </template>
        </EmptyHint>
      </div>
      <template v-else>
        <section v-for="g in privateGroups" :key="g.key" class="cx-group">
          <h2 class="cx-group-head">{{ t(`enterprise.library.group_${g.key}`) }}</h2>
          <ul class="cx-list">
            <li v-for="(task, i) in g.items" :key="task.task_id">
              <RouterLink
                class="cx-card"
                :style="{ animationDelay: `${Math.min(i, 8) * 45}ms` }"
                :to="`/meeting/${task.task_id}`"
                @mouseenter="onCardEnter($event, task.task_id, task.title, fmtDate(task.updated_at))"
                @mouseleave="onCardLeave"
              >
                <span class="cx-eyebrow">{{ t('enterprise.library.eyebrow') }}</span>
                <div class="cx-card-top">
                  <span class="cx-title">{{ task.title || task.task_id }}</span>
                  <PublishedCopiesMenu :copies="task.published_copies ?? []" @withdrawn="contexts.loadTasks()" />
                  <VisibilityBadge :visibility="task.visibility" />
                </div>
                <div class="cx-meta">
                  <svg class="cx-meta-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                  <span>{{ fmtDate(task.updated_at) }}</span>
                  <span v-if="task.sync_status === 'stale'" class="cx-stale"> · {{ t('enterprise.library.last_synced', { time: fmtDate(task.updated_at) }) }}</span>
                </div>
              </RouterLink>
            </li>
          </ul>
        </section>
      </template>
    </template>

    <!-- B1 悬停摘要卡（Teleport 挂 body+fixed——弹出层纪律；只补摘要预览，不新增数据面） -->
    <Teleport to="body">
      <div v-if="hover" class="cx-hover" :style="{ left: hover.left, top: hover.top }" aria-hidden="true">
        <div class="cxh-title">{{ hover.title }}</div>
        <div class="cxh-meta">{{ hover.date }}</div>
        <div class="cxh-label">{{ t('task.summary_label') }}</div>
        <div class="cxh-summary">{{ hover.summary }}</div>
      </div>
    </Teleport>

    <!-- 首次知情同意卡：库内看到纪要即触发一次（与详情页同一 ack 源；仅私有面原件语义） -->
    <EnterpriseConsentGate v-if="!space.isTeamSpace" :active="contexts.tasks.length > 0" />
  </div>
</template>

<style scoped>
.cx-root { max-width: 860px; margin: 0 auto; padding: calc(var(--s-3, 16px) * 1.5); color: var(--fg, #222); }
.cx-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: var(--s-3, 16px); }
.cx-head h1 { font-size: 17px; margin: 0; }
.cx-refresh { border: none; background: none; color: var(--accent, #2a6); cursor: pointer; font-size: var(--fs-12, 12px); }
.cx-group { margin-bottom: var(--s-4, 18px); }
.cx-group-head { font-size: var(--fs-11, 11px); font-weight: 600; color: var(--subtle, #999); letter-spacing: 0.04em; margin: 0 0 var(--s-2, 8px); }
.cx-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--s-2, 10px); }
.cx-card {
  display: block; position: relative; padding: var(--s-3, 16px) var(--s-4, 18px);
  background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-md, 12px);
  text-decoration: none; color: inherit;
  animation: cx-rise 0.28s ease both;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}
.cx-card:hover { border-color: var(--accent, #2a6); box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06); transform: translateY(-1px); }
.cx-card:focus-visible { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 2px; }
@keyframes cx-rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .cx-card { animation: none; transition: none; } }
.cx-eyebrow { display: block; font-size: var(--fs-11, 11px); color: var(--accent, #2a6); opacity: 0.85; margin-bottom: 4px; }
.cx-card-top { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2, 8px); }
.cx-title { font-weight: 600; font-size: var(--fs-14, 14.5px); line-height: 1.5; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cx-meta { margin-top: 6px; font-size: var(--fs-11, 11px); color: var(--muted, #666); display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.cx-meta-ico { width: 11px; height: 11px; opacity: 0.7; flex: none; }
.cx-stale { color: var(--muted, #666); }
.cx-publisher { color: var(--muted, #666); }
.cx-empty-wrap { display: flex; justify-content: center; padding: var(--s-5, 24px) 0; }
.cx-empty-title { font-size: var(--fs-13, 13px); color: var(--fg, #222); margin: 0; }
.cx-guide-btn { display: inline-flex; align-items: center; padding: 7px 16px; border: 1px solid var(--accent, #2a6); border-radius: var(--radius-sm, 8px); background: none; color: var(--accent, #2a6); font-size: var(--fs-12, 12px); text-decoration: none; cursor: pointer; }
.cx-guide-btn:hover { background: var(--accent, #2a6); color: var(--accent-fg, #fff); }
.cx-guide-btn:focus-visible { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 2px; }
.cx-error { color: var(--warn, #c33); font-size: var(--fs-12, 12px); }
</style>

<style>
/* 悬停摘要卡走 body 挂载（Teleport 内容不吃 scoped 哈希），类名带 cx- 前缀防撞 */
.cx-hover {
  position: fixed; z-index: 1200; width: 280px; box-sizing: border-box;
  background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-md, 12px);
  box-shadow: 0 10px 32px rgba(0, 0, 0, 0.12); padding: 14px 16px;
  animation: cxh-in 0.18s ease both; pointer-events: none;
}
@keyframes cxh-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
.cxh-title { font-size: var(--fs-13, 13px); font-weight: 600; color: var(--fg, #222); line-height: 1.5; }
.cxh-meta { margin-top: 2px; font-size: var(--fs-11, 11px); color: var(--subtle, #999); }
.cxh-label { margin-top: 10px; font-size: var(--fs-11, 11px); color: var(--subtle, #999); }
.cxh-summary { margin-top: 2px; font-size: var(--fs-12, 12px); color: var(--muted, #666); line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
