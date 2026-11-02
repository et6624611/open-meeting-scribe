<script setup lang="ts">
/**
 * 企业版定稿文本查看/编辑面（档③ 3a + A项版式对齐 + P1-WP-3 团队形态）
 *
 * 私有面：契约 §1.4 原语义零变化（D013 守卫后个人端点恒限 scope='personal'）。
 * 团队形态（detail.visibility==='team'，服务端单源判定）：
 *  - Tab=纪要/决策/笔记/洞察（insights_html 有才渲染；**无逐字稿 Tab=结构性缺失不渲染不解释**，
 *    复制器白名单在数据层已排除 formal）；
 *  - 编辑权=detail.my_role 单源（editor/admin 渲染编辑面，viewer 无任何编辑控件+一行说明，不灰态不解释缺失）；
 *  - 保存冲突=对照合并弹窗（WP-5，规格 §6）：409{current_rev, latest} → ConflictDiffDialog 装载两版
 *    逐段取舍 → 以 latest 为 base 新 mutation id 重推；latest 缺形回退"保稿冲突条"下限态（联调首查项注记）；
 *    取消=弃稿装载新版；再 409 重入循环；绝不静默覆盖、冲突不记留痕（P1 裁）。
 *  - 决策条目删除（裁决③，二次确认）；恢复入口在变更记录（WP-3 ChangesView）。
 * 读：GET 团队/个人详情端点；写：PUT snapshot（Idempotency-Key + If-Match-Rev）。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useContextsStore } from '@/stores/contexts'
import { useSpaceStore } from '@/stores/space'
import { deleteTeamDecision } from '@/api/teams'
import type { ContextTaskDetail, PublishedCopy } from '@/api/context'
import { parseFormalSegments } from '@/utils/formalLayout'
import { getSpeakerNameBg, getSpeakerNameTextColor } from '@/utils/speakerColors'
import VisibilityBadge from '@/components/common/VisibilityBadge.vue'
import PublishedCopiesMenu from '@/components/common/PublishedCopiesMenu.vue'
import EnterpriseConsentGate from '@/components/modals/EnterpriseConsentGate.vue'
import PublishToTeamDialog from '@/components/modals/PublishToTeamDialog.vue'
import ConflictDiffDialog, { type DiffField } from '@/components/modals/ConflictDiffDialog.vue'
import { showToast } from '@/composables/useToast'

type TabId = 'formal' | 'summary' | 'decisions' | 'notes' | 'insights'

const { t } = useI18n()
const route = useRoute()
const contexts = useContextsStore()
const space = useSpaceStore()

const detail = ref<ContextTaskDetail | null>(null)
const notFound = ref(false)
const summary = ref('')
const notes = ref('')
const saving = ref(false)
const activeTab = ref<TabId>('formal')
const conflictNote = ref(false)
const dirty = computed(() => detail.value != null && (summary.value !== detail.value.summary || notes.value !== detail.value.notes))
const decisionCount = computed(() => (detail.value?.decisions as unknown[] | undefined)?.length ?? 0)

/** 空间形态单源=服务端 visibility 字段（D013 后私有面 DTO 不可能出现 team 值） */
const isTeamDetail = computed(() => detail.value?.visibility === 'team')
const hasInsights = computed(() => !!detail.value?.insights_html)
/** B5（版式找回）：formal 纯文本呈现层分段——不改变任何字符内容，仅发言人 chip+分段留白 */
const formalSegments = computed(() => parseFormalSegments(detail.value?.formal ?? ''))
/** B4：洞察板"在浏览器中打开"全屏形态（BoardViewerView 企业分支=同源 sandbox iframe 铺满视口）；
 *  备案 4：task_id encodeURIComponent 对齐 meetingUrl 口径 */
const boardHref = computed(() => (detail.value ? `/board/${encodeURIComponent(detail.value.task_id)}` : ''))
function segNameColor(name: string): string { return getSpeakerNameTextColor(name) }
function segNameBg(name: string): string { return getSpeakerNameBg(name) }
/** 编辑权单源：detail.my_role（服务端随行下发）；私有面恒可编辑（本人原件） */
const canEdit = computed(() => {
  if (!detail.value) return false
  if (!isTeamDetail.value) return true
  return detail.value.my_role === 'editor' || detail.value.my_role === 'admin'
})
const isTeamViewer = computed(() => isTeamDetail.value && !canEdit.value)

/** 发布入口=私有空间原件面（团队副本空间不渲染发布动作——副本不二次发布） */
const canPublish = computed(() => !space.isTeamSpace)
const publishedCopies = computed<PublishedCopy[]>(() => (detail.value as { published_copies?: PublishedCopy[] } | null)?.published_copies ?? [])
const publishOpen = ref(false)
const publishDecision = ref<{ id: string; text: string } | null>(null)

function openPublish(decision: { id: string; text: string } | null) {
  publishDecision.value = decision
  publishOpen.value = true
}

function afterPublishChange() {
  void load()
  void contexts.loadTasks()
}

async function load() {
  const taskId = typeof route.params.taskId === 'string' ? route.params.taskId : ''
  notFound.value = false
  conflictNote.value = false
  detail.value = null
  if (!taskId) { notFound.value = true; return }
  // D014：副本详情深链/重载——首帧必须等空间恢复，否则团队副本 id 落个人端点必 404（D013 守卫放大态）
  await space.ensureReady()
  const d = await contexts.loadDetail(taskId)
  if (!d) { notFound.value = true; return }
  detail.value = d
  summary.value = d.summary ?? ''
  notes.value = d.notes ?? ''
  // 团队副本无逐字稿 Tab（结构性缺失）：默认落纪要 Tab；?tab=/?restore= 深链（决策聚合/变更记录）直落决策 Tab
  if (d.visibility === 'team') {
    const qTab = route.query.tab
    activeTab.value = (qTab === 'decisions' || typeof route.query.restore === 'string')
      ? 'decisions'
      // B4：洞察板全屏页"返回会议"回洞察 Tab（仅当副本确有板内容）
      : (qTab === 'insights' && d.insights_html ? 'insights' : 'summary')
  } else {
    activeTab.value = 'formal'
  }
}
onMounted(load)
watch(() => route.params.taskId, load)

async function onSave() {
  if (!detail.value || !dirty.value || saving.value || !canEdit.value) return
  saving.value = true
  try {
    if (isTeamDetail.value) {
      const r = await contexts.saveTeamSnapshot(detail.value, { summary: summary.value, notes: notes.value })
      if (r.ok) {
        await load()
        showToast(t('enterprise.detail.saved'), 'success')
        void contexts.loadTasks()
      } else if (r.conflict && r.latest) {
        // WP-5：latest 在位→对照合并弹窗（409 必含项①）
        openConflictDialog(r.latest)
      } else if (r.conflict) {
        // latest 缺形→保稿冲突条下限态回退（联调首查项注记；绝不静默覆盖）
        conflictNote.value = true
        showToast(t('enterprise.detail.conflict_team'), 'error')
      } else {
        showToast(t('enterprise.detail.save_failed'), 'error')
      }
      return
    }
    const r = await contexts.saveSnapshot(detail.value, { summary: summary.value, notes: notes.value })
    if (r.ok) {
      await load()
      showToast(t('enterprise.detail.saved'), 'success')
      void contexts.loadTasks()
    } else if (r.conflict) {
      showToast(t('enterprise.detail.conflict_reload'), 'error')
      await load()
    } else {
      showToast(t('enterprise.detail.save_failed'), 'error')
    }
  } finally { saving.value = false }
}

// ─── WP-5 冲突对照合并流（规格 §6）：弹窗装载 409 latest 两版 → 逐段取舍 → 以 latest 为 base 重推 ───
const conflictDialog = ref<DiffField[] | null>(null)
const conflictSubmitting = ref(false)
let conflictBase: ContextTaskDetail | null = null

function openConflictDialog(latest: ContextTaskDetail) {
  conflictBase = latest
  conflictDialog.value = [
    { key: 'summary', label: t('enterprise.detail.summary'), serverText: latest.summary ?? '', myText: summary.value },
    { key: 'notes', label: t('enterprise.detail.notes'), serverText: latest.notes ?? '', myText: notes.value },
  ]
}

async function onConflictConfirm(merged: Record<string, string>) {
  if (!conflictBase || conflictSubmitting.value) return
  conflictSubmitting.value = true
  try {
    // 重推三钉：base=latest（If-Match=其 server_rev）+ 新 mutation id + 合并文本——再 409 重入弹窗换新 latest
    const r = await contexts.saveTeamSnapshot(conflictBase, { summary: merged.summary ?? '', notes: merged.notes ?? '' })
    if (r.ok) {
      conflictDialog.value = null
      conflictBase = null
      await load()
      showToast(t('enterprise.detail.saved'), 'success')
      void contexts.loadTasks()
    } else if (r.conflict && r.latest) {
      openConflictDialog(r.latest)
    } else if (r.conflict) {
      conflictDialog.value = null
      conflictNote.value = true
      showToast(t('enterprise.detail.conflict_team'), 'error')
    } else {
      showToast(t('enterprise.detail.save_failed'), 'error')
    }
  } finally { conflictSubmitting.value = false }
}

function onConflictCancel() {
  // 规格逐字语义：取消=弃稿装载新版
  conflictDialog.value = null
  conflictBase = null
  void load()
}

/** 决策条目删除（裁决③）：行内两步确认，删除写 decision_delete 留痕（携 pre_delete_rev=恢复依据） */
const pendingDeleteDecisionId = ref('')
function askDeleteDecision(id: string) { pendingDeleteDecisionId.value = pendingDeleteDecisionId.value === id ? '' : id }

async function confirmDeleteDecision(id: string) {
  const d = detail.value
  if (!d?.team_id || !d) return
  try {
    await deleteTeamDecision(d.team_id, d.task_id, id)
    showToast(t('enterprise.decisions.deleted'), 'success')
    pendingDeleteDecisionId.value = ''
    await load()
    void contexts.loadTasks()
  } catch {
    showToast(t('enterprise.decisions.delete_failed'), 'error')
  }
}

function fmtDT(s: string | null): string { return s ? s.replace('T', ' ').slice(0, 16) : '—' }
</script>

<template>
  <div class="cd-root">
    <div v-if="notFound" class="cd-missing" role="alert">
      {{ t('enterprise.detail.not_found') }}
      <!-- PM 窗口D 收口拍板：错误空间打开副本链接=提示态非空白（不解析不点名团队，给出口） -->
      <p v-if="!space.isTeamSpace" class="cd-missing-hint">{{ t('enterprise.detail.link_team_hint') }}</p>
      <RouterLink to="/library" class="cd-back">← {{ t('enterprise.library.title') }}</RouterLink>
    </div>

    <template v-else-if="detail">
      <!-- 标题行：返回 + 标题 + 徽标 + 保存 -->
      <header class="cd-head">
        <RouterLink to="/library" class="cd-back">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
          {{ t('enterprise.library.title') }}
        </RouterLink>
        <div class="cd-titleline">
          <h1>{{ detail.meta.title || detail.task_id }}</h1>
          <VisibilityBadge :visibility="detail.visibility" />
        </div>
        <div class="cd-actions">
          <span v-if="dirty && canEdit" class="cd-dirty">{{ t('enterprise.detail.unsaved') }}</span>
          <PublishedCopiesMenu :copies="publishedCopies" @withdrawn="afterPublishChange" />
          <button v-if="canPublish" class="cd-publish" @click="openPublish(null)">{{ t('enterprise.publish.entry_task') }}</button>
          <button v-if="canEdit" class="cd-save" :disabled="!dirty || saving" @click="onSave">{{ saving ? t('enterprise.detail.saving') : t('enterprise.detail.save') }}</button>
        </div>
      </header>

      <!-- 元信息行（对齐个人版 toolbar meta） -->
      <div class="cd-meta">
        <span class="cd-meta-item">{{ fmtDT(detail.meta.meeting_time) }}</span>
        <span v-if="detail.meta.participants_text" class="cd-meta-item">· {{ detail.meta.participants_text }}</span>
        <span class="cd-meta-audio" title="">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
          {{ t('enterprise.detail.audio_local') }}
        </span>
      </div>

      <!-- Tab 栏：个人版同款下划线视觉语言；团队形态无"原文"Tab（结构性缺失不渲染不解释），洞察 Tab 仅有内容时出现 -->
      <nav class="cd-tabs" role="tablist">
        <button v-if="!isTeamDetail" role="tab" :aria-selected="activeTab === 'formal'" :class="{ 'is-active': activeTab === 'formal' }" @click="activeTab = 'formal'">{{ t('enterprise.detail.formal') }}</button>
        <button role="tab" :aria-selected="activeTab === 'summary'" :class="{ 'is-active': activeTab === 'summary' }" @click="activeTab = 'summary'">
          {{ t('enterprise.detail.summary') }}<span v-if="!detail.summary" class="cd-tab-dot is-empty"></span>
        </button>
        <button v-if="decisionCount" role="tab" :aria-selected="activeTab === 'decisions'" :class="{ 'is-active': activeTab === 'decisions' }" @click="activeTab = 'decisions'">
          {{ t('enterprise.detail.decisions') }}<span class="cd-tab-count">{{ decisionCount }}</span>
        </button>
        <button role="tab" :aria-selected="activeTab === 'notes'" :class="{ 'is-active': activeTab === 'notes' }" @click="activeTab = 'notes'">{{ t('enterprise.detail.notes') }}</button>
        <button v-if="hasInsights" role="tab" :aria-selected="activeTab === 'insights'" :class="{ 'is-active': activeTab === 'insights' }" @click="activeTab = 'insights'">{{ t('enterprise.detail.insights') }}</button>
      </nav>

      <!-- 只读成员一行中性说明（规格 §3：给出口不制造缺失感）；团队面 viewer 唯一渲染 -->
      <p v-if="isTeamViewer" class="cd-viewer-note">{{ t('enterprise.team.viewer_note') }}</p>
      <!-- 团队面冲突条：保稿不覆盖（diff 合并 UI 随 WP-5 交付形态） -->
      <div v-if="conflictNote" class="cd-conflict" role="alert">
        {{ t('enterprise.detail.conflict_team') }}
        <button type="button" class="cd-conflict-reload" @click="load()">{{ t('common.action.retry') }}</button>
      </div>

      <!-- 内容面板（对齐个人版 gen-panel 宽度节奏；B3：Tab 切换淡入淡出过渡） -->
      <section class="cd-panel">
        <Transition name="cd-fade" mode="out-in">
        <div :key="activeTab">
        <div v-show="activeTab === 'formal'" class="cd-pane">
          <p class="cd-readonly-hint">{{ t('enterprise.detail.formal_hint') }}</p>
          <div class="cd-formal cd-formal-seg">
            <template v-for="(seg, i) in formalSegments" :key="i">
              <p v-if="seg.kind === 'speaker'" class="cd-seg is-speaker">
                <span class="cd-seg-name" :style="{ color: segNameColor(seg.name), background: segNameBg(seg.name) }">{{ seg.name }}</span>
                <span class="cd-seg-text">{{ seg.text }}</span>
              </p>
              <p v-else-if="seg.kind === 'heading'" class="cd-seg is-heading">
                <span class="cd-seg-heading">{{ seg.name }}</span><span v-if="seg.text" class="cd-seg-text">{{ seg.text }}</span>
              </p>
              <p v-else class="cd-seg"><span class="cd-seg-text">{{ seg.text }}</span></p>
            </template>
          </div>
        </div>

        <div v-show="activeTab === 'summary'" class="cd-pane">
          <textarea v-if="canEdit" v-model="summary" rows="14" class="cd-area" :aria-label="t('enterprise.detail.summary')" :placeholder="t('enterprise.detail.summary_placeholder')"></textarea>
          <div v-else class="cd-formal cd-readonly-block">{{ detail.summary || t('enterprise.detail.empty_summary') }}</div>
        </div>

        <div v-show="activeTab === 'decisions'" class="cd-pane">
          <article v-for="(d, i) in detail.decisions as Array<{ id?: string; text?: string; status_text?: string; status_id?: string }>" :key="d.id ?? i" class="cd-decision">
            <p class="cd-decision-text">{{ d.text ?? '' }}</p>
            <span v-if="d.status_text" class="cd-decision-status" :class="'rev-' + (d.status_id ?? '')">{{ d.status_text }}</span>
            <button
              v-if="canPublish && d.id"
              type="button"
              class="cd-decision-publish"
              @click="openPublish({ id: d.id, text: d.text ?? '' })"
            >{{ t('enterprise.publish.entry_decision') }}</button>
            <div v-else-if="isTeamDetail && canEdit && d.id" class="cd-decision-ops">
              <template v-if="pendingDeleteDecisionId !== d.id">
                <button type="button" class="cd-decision-publish is-danger" @click="askDeleteDecision(d.id!)">{{ t('enterprise.decisions.delete_btn') }}</button>
              </template>
              <template v-else>
                <p class="cd-delete-confirm-text">{{ t('enterprise.decisions.delete_confirm') }}</p>
                <div class="cd-delete-confirm-actions">
                  <button type="button" class="cd-decision-publish is-ghost" @click="pendingDeleteDecisionId = ''">{{ t('common.action.cancel') }}</button>
                  <button type="button" class="cd-decision-publish is-danger" @click="confirmDeleteDecision(d.id!)">{{ t('enterprise.decisions.delete_btn') }}</button>
                </div>
              </template>
            </div>
          </article>
        </div>

        <div v-show="activeTab === 'notes'" class="cd-pane">
          <textarea v-if="canEdit" v-model="notes" rows="10" class="cd-area" :aria-label="t('enterprise.detail.notes')" :placeholder="t('enterprise.detail.notes_placeholder')"></textarea>
          <div v-else class="cd-formal cd-readonly-block">{{ detail.notes || t('enterprise.detail.empty_notes') }}</div>
        </div>

        <div v-show="activeTab === 'insights'" class="cd-pane">
          <!-- B4：洞察板全屏入口——同页 iframe 之外给"在浏览器中打开"（/board 企业分支=副本 insights_html 铺满视口，
               仍是 sandbox iframe 承载，安全边界不因换入口而变） -->
          <div class="cd-insights-bar">
            <a v-if="boardHref" class="cd-insights-open" :href="boardHref" target="_blank" rel="noopener">
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              {{ t('enterprise.detail.open_in_browser') }}
            </a>
          </div>
          <!-- 团队洞察板=内容面只读窗口（裁决⑤随副本进团队）：sandbox iframe 承载 HTML 串，
               无 same-origin 授权、无脚本触达宿主；桥接渲染一致性列窗口C 联调观察项 -->
          <iframe
            v-if="hasInsights"
            class="cd-insights-frame"
            :srcdoc="detail.insights_html ?? ''"
            sandbox="allow-scripts"
            :title="t('enterprise.detail.insights')"
            referrerpolicy="no-referrer"
          ></iframe>
        </div>
        </div>
        </Transition>
      </section>
    </template>

    <EnterpriseConsentGate :active="!!detail?.summary" />

    <PublishToTeamDialog
      v-if="publishOpen && detail"
      :task-id="detail.task_id"
      :decision-only="publishDecision"
      :published-copies="publishedCopies"
      @close="publishOpen = false"
      @published="afterPublishChange"
    />

    <!-- WP-5 冲突对照合并弹窗（latest 装载→逐段取舍→重推由本视图执行） -->
    <ConflictDiffDialog
      v-if="conflictDialog"
      :fields="conflictDialog"
      :submitting="conflictSubmitting"
      @cancel="onConflictCancel"
      @confirm="onConflictConfirm"
    />
  </div>
</template>

<style scoped>
.cd-root { height: 100%; overflow: auto; color: var(--fg, #222); display: flex; flex-direction: column; }
.cd-head { display: flex; align-items: center; gap: var(--s-3, 16px); padding: var(--s-3, 16px) var(--s-6, 28px) 0; flex-wrap: wrap; }
.cd-back { display: inline-flex; align-items: center; gap: 4px; font-size: var(--fs-12, 12px); color: var(--muted, #666); text-decoration: none; flex: none; }
.cd-back:hover { color: var(--fg, #222); }
.cd-titleline { display: flex; align-items: center; gap: var(--s-2, 10px); flex: 1; min-width: 0; }
.cd-titleline h1 { font-size: 16px; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cd-actions { display: flex; align-items: center; gap: var(--s-2, 8px); flex: none; }
.cd-dirty { font-size: var(--fs-11, 11px); color: var(--warn, #b60); }
.cd-save { padding: 6px 16px; border: none; border-radius: var(--radius-sm, 8px); background: var(--accent, #2a6); color: var(--accent-fg, #fff); font-weight: 600; font-size: var(--fs-12, 12px); cursor: pointer; }
.cd-save:disabled { opacity: 0.45; cursor: not-allowed; }
.cd-publish { padding: 6px 12px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); background: var(--surface, #fff); color: var(--fg, #222); font-size: var(--fs-12, 12px); cursor: pointer; }
.cd-publish:hover { border-color: var(--accent, #2a6); color: var(--accent, #2a6); }
.cd-publish:focus-visible { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.cd-decision { position: relative; }
.cd-decision-publish { align-self: flex-start; border: none; background: none; color: var(--muted, #666); font-size: var(--fs-11, 11px); cursor: pointer; padding: 2px 0; text-decoration: underline; text-underline-offset: 3px; }
.cd-decision-publish:hover { color: var(--accent, #2a6); }
.cd-decision-publish:focus-visible { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.cd-decision-publish.is-danger { color: var(--warn, #c33); }
.cd-decision-publish.is-ghost { color: var(--muted, #666); }
.cd-decision-ops { display: flex; flex-direction: column; gap: 4px; align-self: flex-start; }
.cd-delete-confirm-text { margin: 0; font-size: var(--fs-11, 11px); color: var(--muted, #666); }
.cd-delete-confirm-actions { display: flex; gap: 10px; }
.cd-viewer-note { margin: var(--s-2, 8px) var(--s-6, 28px) 0; font-size: var(--fs-11, 11px); color: var(--muted, #666); }
.cd-conflict { margin: var(--s-2, 8px) var(--s-6, 28px) 0; display: flex; align-items: center; gap: 10px; font-size: var(--fs-12, 12px); color: var(--warn, #b60); background: var(--warn-soft, #fdf6e3); border: 1px solid var(--border, #f0e0b0); border-radius: var(--radius-sm, 8px); padding: 8px 12px; }
.cd-conflict-reload { border: none; background: none; color: var(--accent, #2a6); cursor: pointer; font-size: var(--fs-12, 12px); }
.cd-readonly-block { background: var(--surface, #fff); border: 1px solid var(--border, #e6e6e2); border-radius: var(--radius-sm, 10px); padding: var(--s-4, 20px); }
.cd-insights-frame { width: 100%; min-height: 480px; border: 1px solid var(--border, #e6e6e2); border-radius: var(--radius-sm, 10px); background: #fff; }
.cd-meta { display: flex; gap: 8px; align-items: center; padding: 6px var(--s-6, 28px) 0; font-size: var(--fs-11, 11px); color: var(--muted, #666); flex-wrap: wrap; }
.cd-meta-audio { display: inline-flex; align-items: center; gap: 4px; margin-left: auto; padding: 2px 8px; border-radius: 999px; background: var(--surface-2, #f2f2f0); color: var(--subtle, #999); }
.cd-tabs { display: flex; gap: 2px; padding: var(--s-3, 14px) var(--s-6, 28px) 0; border-bottom: 1px solid var(--border, #e6e6e2); }
.cd-tabs button { position: relative; padding: 8px var(--s-3, 16px); font-size: var(--fs-13, 13px); color: var(--muted, #666); background: none; border: none; border-bottom: 2px solid transparent; margin-bottom: -1px; cursor: pointer; display: flex; align-items: center; gap: 5px; }
.cd-tabs button:hover { color: var(--fg, #222); }
.cd-tabs button.is-active { color: var(--accent, #2a6); border-bottom-color: var(--accent, #2a6); font-weight: 600; }
.cd-tab-count { font-size: var(--fs-11, 11px); background: var(--surface-2, #f0f0ee); border-radius: 999px; padding: 0 6px; color: var(--muted, #666); }
.cd-tab-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--subtle, #bbb); display: inline-block; }
.cd-panel { width: 80%; min-width: min(600px, 100%); max-width: 960px; margin: 0 auto; padding: var(--s-6, 28px) 0 var(--s-7, 48px); box-sizing: border-box; }
.cd-fade-enter-active, .cd-fade-leave-active { transition: opacity 0.16s ease; }
.cd-fade-enter-from, .cd-fade-leave-to { opacity: 0; }
.cd-pane { display: flex; flex-direction: column; gap: var(--s-2, 10px); }
.cd-readonly-hint { margin: 0; font-size: var(--fs-11, 11px); color: var(--subtle, #999); }
.cd-formal { white-space: pre-wrap; font-size: var(--fs-13, 14px); line-height: 2; }
/* B5 版式找回：发言人分段 chip（色板=个人版 speakerColors 同源 oklch 体系，名字哈希确定性取色） */
.cd-formal-seg { display: flex; flex-direction: column; gap: 6px; }
.cd-seg { margin: 0; white-space: pre-wrap; }
.cd-seg.is-speaker { display: flex; align-items: baseline; gap: 8px; padding: 4px 0; border-radius: var(--radius-sm, 8px); }
.cd-seg-name { flex: none; font-size: var(--fs-11, 11px); font-weight: 600; line-height: 1.6; padding: 1px 9px; border-radius: 999px; white-space: nowrap; }
.cd-seg.is-heading .cd-seg-heading { font-weight: 700; }
.cd-seg-text { min-width: 0; }
.cd-insights-bar { display: flex; justify-content: flex-end; }
.cd-insights-open { display: inline-flex; align-items: center; gap: 5px; font-size: var(--fs-12, 12px); color: var(--muted, #666); text-decoration: none; padding: 4px 10px; border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); background: var(--surface, #fff); }
.cd-insights-open:hover { color: var(--accent, #2a6); border-color: var(--accent, #2a6); }
.cd-insights-open:focus-visible { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.cd-area { width: 100%; box-sizing: border-box; border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 10px); padding: var(--s-4, 20px); font: inherit; font-size: var(--fs-13, 14px); line-height: 1.9; background: var(--surface, #fff); color: var(--fg, #222); resize: vertical; }
.cd-area:focus { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.cd-decision { background: var(--surface, #fff); border: 1px solid var(--border, #e6e6e2); border-left: 3px solid var(--accent, #2a6); border-radius: var(--radius-sm, 8px); padding: var(--s-3, 14px) var(--s-4, 18px); display: flex; flex-direction: column; gap: 6px; }
.cd-decision-text { margin: 0; font-size: var(--fs-13, 13px); line-height: 1.7; }
.cd-decision-status { align-self: flex-start; font-size: var(--fs-11, 11px); color: var(--muted, #666); background: var(--surface-2, #f2f2f0); padding: 1px 8px; border-radius: 999px; }
.cd-missing { padding: var(--s-7, 48px); color: var(--warn, #c33); font-size: var(--fs-12, 12px); display: flex; gap: var(--s-3, 16px); align-items: center; flex-wrap: wrap; }
.cd-missing-hint { margin: 0; width: 100%; color: var(--muted, #666); font-size: var(--fs-12, 12px); }
.cd-back { color: var(--muted, #666); }
</style>
