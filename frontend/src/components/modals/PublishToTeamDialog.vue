<script setup lang="ts">
/**
 * 公开确认弹窗（P1-WP-2；UI 规格 §4.2 核心承诺面，发布态按 BE ffcb709 实码对齐）
 *
 * 粒度两形态同组件：纪要级=mode task 整包副本；决策条目级=mode decision 单条独立时间线。
 * 锁定行=B5 第五表面第一处消费：LOCKED_TEAM_PROMISE_LINE 单源 import，禁手抄；
 * "不会出现"区恒显示、不可勾选、无开关（规格生命线）。
 * 多团队=独立发布（裁决①）：每团队一次独立调用，失败互不牵连；K2 同团队重复发布=刷新。
 * 已公开团队置灰依据=原件 published_copies 读面（§6.5 补漏注）；decision 粒度不置灰
 * （published_copies 行无 decision id，置灰依据不足则不禁——服务端幂等刷新兜底）。
 */
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSpaceStore } from '@/stores/space'
import { LOCKED_TEAM_PROMISE_LINE } from '@/constants/lockedCopy'
import { buildPublishBody, publishTaskToTeam, selectablePublishTeams } from '@/api/teams'
import { showToast } from '@/composables/useToast'
import { useEscClose } from '@/composables/useEscClose'
import type { PublishedCopy } from '@/api/context'

const props = defineProps<{
  taskId: string
  /** 非 null=决策条目级发布（mode decision），null=纪要级整包发布 */
  decisionOnly: { id: string; text: string } | null
  publishedCopies?: PublishedCopy[]
}>()
const emit = defineEmits<{ close: []; published: [count: number] }>()

const { t } = useI18n()
const space = useSpaceStore()

const teamRows = computed(() => {
  const publishedIds = (props.publishedCopies ?? []).map((c) => c.team_id)
  const rows = selectablePublishTeams(space.teams, publishedIds)
  // 决策粒度：置灰依据不含 decision id → 全部可选（K2 服务端刷新语义兜重复发布）
  if (props.decisionOnly) return rows.map((r) => ({ ...r, alreadyPublished: false }))
  return rows
})
const selectableTeamIds = computed(() => teamRows.value.filter((r) => !r.alreadyPublished).map((r) => r.team.team_id))

const chosenTeams = reactive<Set<string>>(new Set())
const submitting = ref(false)
const firstFocusEl = ref<HTMLElement | null>(null)

const escRef = ref(true)
useEscClose(escRef, () => { if (!submitting.value) emit('close') })

function toggleTeam(id: string) {
  chosenTeams.has(id) ? chosenTeams.delete(id) : chosenTeams.add(id)
}

const canSubmit = computed(() =>
  !submitting.value
  && selectableTeamIds.value.length > 0
  && chosenTeams.size > 0,
)

async function onConfirm() {
  if (!canSubmit.value) return
  submitting.value = true
  const mode = props.decisionOnly ? 'decision' : 'task'
  const calls = [...chosenTeams].map((teamId) =>
    publishTaskToTeam(props.taskId, buildPublishBody(teamId, mode, props.decisionOnly?.id ?? null)),
  )
  const results = await Promise.allSettled(calls)
  const ok = results.filter((r) => r.status === 'fulfilled').length
  const fail = results.length - ok
  submitting.value = false
  if (fail === 0) showToast(t('enterprise.publish.toast_done', { count: ok }), 'success')
  else if (ok > 0) showToast(t('enterprise.publish.toast_partial', { ok, fail }), 'error')
  else showToast(t('enterprise.publish.toast_failed'), 'error')
  if (ok > 0) emit('published', ok)
  emit('close')
}

onMounted(() => {
  void space.loadTeams()
  nextTick(() => firstFocusEl.value?.focus())
})
</script>

<template>
  <Teleport to="body">
    <div class="pt-mask" @click.self="emit('close')">
      <div class="pt-card" role="dialog" aria-modal="true" :aria-label="t(decisionOnly ? 'enterprise.publish.title_decision' : 'enterprise.publish.title')">
        <h3>{{ t(decisionOnly ? 'enterprise.publish.title_decision' : 'enterprise.publish.title') }}</h3>

        <p v-if="decisionOnly" class="pt-decision-quote">{{ decisionOnly.text }}</p>
        <p class="pt-scope">{{ t(decisionOnly ? 'enterprise.publish.scope_decision' : 'enterprise.publish.scope_task') }}</p>

        <p class="pt-label">{{ t('enterprise.publish.teams_label') }}</p>
        <p v-if="!teamRows.length" class="pt-note">{{ t('enterprise.publish.no_teams_hint') }}</p>
        <ul v-else class="pt-teams" role="listbox" :aria-label="t('enterprise.publish.teams_label')">
          <li v-for="row in teamRows" :key="row.team.team_id">
            <button
              type="button"
              class="pt-team"
              :class="{ 'is-on': chosenTeams.has(row.team.team_id), 'is-off': row.alreadyPublished }"
              :disabled="row.alreadyPublished"
              :aria-pressed="chosenTeams.has(row.team.team_id) && !row.alreadyPublished"
              @click="!row.alreadyPublished && toggleTeam(row.team.team_id)"
            >
              <span class="pt-team-name">{{ row.team.name }}</span>
              <span v-if="row.alreadyPublished" class="pt-tag">{{ t('enterprise.publish.already_published_tag') }}</span>
            </button>
          </li>
        </ul>

        <!-- B5 第五锁定表面（规格 §4.2：恒显示、不可勾选、无开关；末行逐字单源） -->
        <div class="pt-excluded" role="note">
          <p class="pt-excluded-title">{{ t('enterprise.publish.excluded_heading') }}</p>
          <p class="pt-excluded-items">{{ t('enterprise.publish.excluded_items') }}</p>
          <p class="pt-locked">{{ LOCKED_TEAM_PROMISE_LINE }}</p>
        </div>

        <p class="pt-after">{{ t('enterprise.publish.after_note') }}</p>

        <div class="pt-actions">
          <button type="button" class="pt-btn is-ghost" :disabled="submitting" @click="emit('close')">{{ t('common.action.cancel') }}</button>
          <button ref="firstFocusEl" type="button" class="pt-btn" :disabled="!canSubmit" @click="onConfirm">{{ submitting ? t('enterprise.publish.submitting') : t('enterprise.publish.btn_confirm') }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.pt-mask { position: fixed; inset: 0; background: rgb(0 0 0 / 0.35); display: grid; place-items: center; z-index: var(--z-toast, 1200); padding: var(--s-3, 16px); }
.pt-card { width: min(480px, 100%); max-height: calc(100vh - 48px); overflow: auto; background: var(--surface, #fff); border-radius: calc(var(--radius-sm, 8px) * 1.5); padding: calc(var(--s-3, 16px) * 1.25); display: flex; flex-direction: column; gap: var(--s-2, 10px); box-shadow: 0 16px 48px rgb(0 0 0 / 0.2); }
.pt-card h3 { margin: 0; font-size: 15px; }
.pt-label { margin: 4px 0 0; font-size: var(--fs-12, 12px); color: var(--muted, #666); font-weight: 600; }
.pt-note, .pt-after, .pt-scope { margin: 0; font-size: var(--fs-12, 12px); color: var(--muted, #666); line-height: 1.7; }
.pt-decision-quote { margin: 0; font-size: var(--fs-13, 13px); color: var(--fg, #222); background: var(--surface-2, #fafaf8); border-left: 3px solid var(--accent, #2a6); border-radius: var(--radius-sm, 8px); padding: var(--s-2, 10px) var(--s-3, 14px); line-height: 1.7; }
.pt-teams { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.pt-team { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; padding: 7px 10px; border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); background: var(--surface-2, #fafaf8); color: var(--fg, #222); font-size: var(--fs-12, 12px); cursor: pointer; text-align: left; }
.pt-team:hover:not(:disabled) { border-color: var(--accent-mid, #4a7); }
.pt-team.is-on { border-color: var(--accent, #2a6); background: var(--accent-soft, #eaf4ec); }
.pt-team.is-off, .pt-team:disabled { opacity: 0.55; cursor: not-allowed; }
.pt-team:focus-visible { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.pt-team-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pt-tag { flex: none; font-size: var(--fs-11, 11px); color: var(--subtle, #999); }
.pt-excluded { background: var(--surface-2, #f4f6f4); border: 1px solid var(--border, #e6e6e2); border-radius: var(--radius-sm, 8px); padding: var(--s-2, 10px) var(--s-3, 14px); display: flex; flex-direction: column; gap: 2px; }
.pt-excluded-title { margin: 0; font-size: var(--fs-11, 11px); color: var(--subtle, #999); font-weight: 600; }
.pt-excluded-items { margin: 0; font-size: var(--fs-12, 12px); color: var(--fg, #222); }
.pt-locked { margin: 0; font-size: var(--fs-12, 12px); color: var(--fg, #222); line-height: 1.7; }
.pt-actions { display: flex; gap: var(--s-2, 10px); justify-content: flex-end; margin-top: var(--s-2, 6px); }
.pt-btn { padding: 8px 16px; border: none; border-radius: var(--radius-sm, 8px); background: var(--accent, #2a6); color: var(--accent-fg, #fff); cursor: pointer; font-size: var(--fs-12, 12px); font-weight: 600; }
.pt-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.pt-btn.is-ghost { background: none; border: 1px solid var(--border, #d8d8d4); color: var(--fg, #222); font-weight: 400; }
</style>
