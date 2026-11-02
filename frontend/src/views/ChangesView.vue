<script setup lang="ts">
/**
 * 团队变更记录视图（/changes；P1-WP-3，规格 §7 + PM Q4 裁决）
 *
 * 轻量倒序操作列表（时间/操作人/操作文本），分页加载，全员可见（viewer 也在=信任透明）；
 * 无审批流、无跳转复杂度。删除类条目对 editor+ 附"恢复"按钮（裁决③回滚面：
 * from_rev=pre_delete_rev 服务端留痕直读，恢复本身=新留痕由服务端写）。
 * 未知 action 枚举回退显原文（兜底不崩）。
 */
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSpaceStore } from '@/stores/space'
import { useContextsStore } from '@/stores/contexts'
import { listTeamAudit, restoreTeamDecision, type TeamAuditItem } from '@/api/teams'
import { auditLabelKey } from '@/utils/teamSpacesLogic'
import { showToast } from '@/composables/useToast'
import type { Router } from 'vue-router'
import { useRouter } from 'vue-router'

const { t } = useI18n()
const space = useSpaceStore()
const contexts = useContextsStore()
const router: Router = useRouter()

const items = ref<TeamAuditItem[]>([])
const cursor = ref<string | null>(null)
const loading = ref(false)
const done = ref(false)
const error = ref(false)
const restoring = ref('')

function taskTitle(taskId: string | null): string {
  if (!taskId) return ''
  return contexts.teamTasks.find((x) => x.task_id === taskId)?.title || taskId.slice(-6)
}

function label(item: TeamAuditItem): string {
  const key = auditLabelKey(item.action)
  const title = taskTitle(item.task_id)
  if (!key) return `${item.action}${title ? `《${title}》` : ''}`
  return t(`enterprise.${key}`, { name: item.actor_name, title })
}

function canRestore(item: TeamAuditItem): boolean {
  return space.canEdit && item.action === 'decision_delete' && !!item.task_id && !!item.target_ref && item.pre_delete_rev != null
}

async function fetchPage(reset = false) {
  if (!space.isTeamSpace || loading.value) return
  loading.value = true
  error.value = false
  try {
    const page = await listTeamAudit(space.currentId, reset ? null : cursor.value)
    items.value = reset ? page.items : [...items.value, ...page.items]
    cursor.value = page.next_cursor
    done.value = page.next_cursor === null
    if (reset) {
      void contexts.loadTasks()
      void space.loadMembers(space.currentId)
    }
  } catch {
    error.value = true
  } finally { loading.value = false }
}

async function onRestore(item: TeamAuditItem) {
  if (!item.task_id || !item.target_ref || item.pre_delete_rev == null) return
  restoring.value = item.audit_id
  try {
    await restoreTeamDecision(space.currentId, item.task_id, item.target_ref, item.pre_delete_rev)
    showToast(t('enterprise.audit.restore_done'), 'success')
    await fetchPage(true)
  } catch {
    showToast(t('enterprise.audit.restore_failed'), 'error')
  } finally { restoring.value = '' }
}

/** 恢复前先落决策所在会议（规格：不做审批流，恢复在变更记录一键完成；跳转详情供核对） */
function openSource(item: TeamAuditItem) {
  if (item.task_id) router.push(`/meeting/${item.task_id}?restore=${encodeURIComponent(item.target_ref ?? '')}`)
}

onMounted(() => { void fetchPage(true) })
</script>

<template>
  <div class="ch-root">
    <header class="ch-head">
      <h1>{{ t('enterprise.changes.title') }}</h1>
      <button class="ch-refresh" @click="fetchPage(true)">{{ t('common.action.retry') }}</button>
    </header>

    <p v-if="!space.isTeamSpace" class="ch-empty">{{ t('enterprise.changes.private_hint') }}</p>
    <p v-else-if="error" class="ch-error" role="alert">{{ t('enterprise.changes.load_failed') }}</p>
    <p v-else-if="!loading && !items.length" class="ch-empty">{{ t('enterprise.changes.empty') }}</p>

    <ul v-if="items.length" class="ch-list">
      <li v-for="item in items" :key="item.audit_id" class="ch-item">
        <div class="ch-line">
          <span class="ch-actor">{{ item.actor_name }}</span>
          <span class="ch-action">{{ label(item) }}</span>
        </div>
        <div class="ch-meta">
          <span class="ch-time">{{ item.ts.replace('T', ' ').slice(0, 16) }}</span>
          <button v-if="item.task_id" type="button" class="ch-link" @click="openSource(item)">{{ t('enterprise.changes.open_source') }}</button>
          <button
            v-if="canRestore(item)"
            type="button"
            class="ch-restore"
            :disabled="restoring === item.audit_id"
            @click="onRestore(item)"
          >{{ restoring === item.audit_id ? t('enterprise.changes.restoring') : t('enterprise.audit.restore_btn') }}</button>
        </div>
      </li>
    </ul>

    <button v-if="!done && !loading && space.isTeamSpace && !error" class="ch-more" @click="fetchPage()">{{ t('enterprise.changes.load_more') }}</button>
    <p v-else-if="loading && items.length" class="ch-empty">{{ t('enterprise.library.loading') }}</p>
  </div>
</template>

<style scoped>
.ch-root { max-width: 720px; margin: 0 auto; padding: calc(var(--s-3, 16px) * 1.5); color: var(--fg, #222); }
.ch-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: var(--s-3, 16px); }
.ch-head h1 { font-size: 17px; margin: 0; }
.ch-refresh, .ch-more { border: none; background: none; color: var(--accent, #2a6); cursor: pointer; font-size: var(--fs-12, 12px); }
.ch-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--s-2, 10px); }
.ch-item { background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); padding: var(--s-2, 10px) var(--s-3, 14px); display: flex; flex-direction: column; gap: 4px; }
.ch-line { display: flex; gap: 8px; font-size: var(--fs-12, 12px); flex-wrap: wrap; }
.ch-actor { font-weight: 600; }
.ch-action { color: var(--fg, #222); }
.ch-meta { display: flex; gap: 12px; align-items: baseline; font-size: var(--fs-11, 11px); color: var(--muted, #666); }
.ch-time { margin-right: auto; }
.ch-link, .ch-restore { border: none; background: none; cursor: pointer; font-size: var(--fs-11, 11px); color: var(--muted, #666); text-decoration: underline; text-underline-offset: 3px; padding: 0; }
.ch-restore { color: var(--accent, #2a6); }
.ch-link:hover, .ch-restore:hover { color: var(--accent, #2a6); }
.ch-restore:disabled { opacity: .5; cursor: not-allowed; }
.ch-empty { color: var(--muted, #666); font-size: var(--fs-12, 12px); }
.ch-error { color: var(--warn, #c33); font-size: var(--fs-12, 12px); }
</style>
