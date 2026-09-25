<template>
  <!-- 决策中心：跨会议决策的检索、筛选与管理（REQ-DECISION-CENTER R3 / 派工单 DC-DEC-F1）
       Decision Center: cross-meeting decision browsing, filtering and lifecycle ops -->
  <div class="dc-page">
    <!-- 头部：标题 + 计数 + 视图切换 + 补录 / Header -->
    <div class="dc-header-bar">
      <div class="dc-title-group">
        <h1>{{ t('decisions.title') }}</h1>
        <span class="dc-count" v-if="!loading && !error">{{ t('decisions.count', { count: effectiveRows.length + ineffectiveRows.length }) }}</span>
      </div>
      <div class="dc-header-actions">
        <button class="dc-add-btn" @click="showAdd = true">+ {{ t('decisions.add_manual') }}</button>
      </div>
    </div>

    <!-- 筛选区：时间 × 知识库 × 状态 × 关键词 / Filter bar -->
    <div class="dc-filter-bar" role="search">
      <div class="dc-filter-group">
        <span class="dc-filter-label">{{ t('decisions.filter_time') }}</span>
        <div class="dc-seg" role="group" :aria-label="t('decisions.filter_time')">
          <button v-for="opt in TIME_OPTIONS" :key="opt" class="dc-seg-btn" :class="{ active: timeRange === opt }" @click="timeRange = opt">
            {{ t('decisions.time_' + opt) }}
          </button>
        </div>
      </div>
      <div class="dc-filter-group">
        <span class="dc-filter-label">{{ t('decisions.filter_kb') }}</span>
        <KbFilterCombobox v-model="kbId" :projects="projects" :label="t('decisions.filter_kb')" />
      </div>
      <div class="dc-filter-group" role="group" :aria-label="t('decisions.filter_status')">
        <span class="dc-filter-label">{{ t('decisions.filter_status') }}</span>
        <!-- 状态 chips 由状态字典驱动（含用户新增项）；「待确认」仍为标志位维度（D7） -->
        <button
          v-for="s in statuses"
          :key="s.id"
          class="dc-chip"
          :class="{ on: visibleStatusIds.has(s.id) }"
          :aria-pressed="visibleStatusIds.has(s.id)"
          @click="toggleStatus(s.id)"
        >
          <span class="dc-chip-dot" :style="{ background: s.color }"></span>{{ labelOf(s) }}
        </button>
        <button
          class="dc-chip"
          :class="{ on: selected.has(PENDING_KEY) }"
          :aria-pressed="selected.has(PENDING_KEY)"
          @click="toggleStatus(PENDING_KEY)"
        >{{ t('decisions.st_pending') }}</button>
        <!-- D7：默认只看非闭档（未完成）类，可一键查看全部 -->
        <button
          class="dc-chip dc-chip-all"
          :class="{ on: showAll }"
          :aria-pressed="showAll"
          @click="toggleShowAll"
        >{{ t('decisions.filter_view_all') }}</button>
        <button type="button" class="dc-manage-btn" @click="showStatusMgr = true">{{ t('decisions.sm_open') }}</button>
      </div>
      <div class="dc-filter-group dc-grow">
        <label class="sr-only" for="dcKeyword">{{ t('decisions.search_placeholder') }}</label>
        <div class="dc-kw-wrap">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" class="dc-kw-icon"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input id="dcKeyword" v-model.trim="keyword" type="search" class="dc-kw-input" :placeholder="t('decisions.search_placeholder')" />
        </div>
      </div>
    </div>

    <!-- 错误态（优先于空态：失败 ≠ 没有数据） / Error state ahead of empty -->
    <div v-if="error && !loading" class="dc-error" role="alert">
      <span>{{ t('decisions.error_load') }} · {{ error }}</span>
      <button type="button" class="dc-error-retry" @click="load()">{{ t('common.error.retry') }}</button>
    </div>

    <!-- 加载态 / Loading state -->
    <div v-else-if="loading" class="dc-loading" aria-busy="true">
      <div class="gen-skeleton"><div class="gen-skeleton-bar"></div><div class="gen-skeleton-bar"></div><div class="gen-skeleton-bar"></div><div class="gen-skeleton-bar"></div></div>
    </div>

    <!-- 空态：无数据 vs 筛选无结果 / Two empty flavors -->
    <div v-else-if="!visibleGroups.length && !ineffectiveRows.length" class="dc-empty">
      <svg viewBox="0 0 24 24" width="34" height="34" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><path d="M8 21h8"/><path d="M5 7h14"/><path d="M5 7 2.5 13a3 3 0 0 0 5 0L5 7z"/><path d="M19 7l-2.5 6a3 3 0 0 0 5 0L19 7z"/></svg>
      <p>{{ showFilteredEmpty ? t('decisions.empty_filtered') : t('decisions.empty_all') }}</p>
    </div>

    <!-- 列表主体：固定按会议分组（F2 移除平铺切换，DC-R2-a） / Body: always grouped by meeting -->
    <section v-else class="dc-groups">
      <div v-for="g in visibleGroups" :key="g.taskId" class="dc-group">
        <button class="dc-group-head" :title="g.title" :aria-expanded="!collapsed.has(g.taskId)" @click="toggleGroup(g.taskId)">
          <svg class="dc-chev" :class="{ open: !collapsed.has(g.taskId) }" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
          <span class="dc-group-title">{{ g.title }}</span>
          <span class="dc-group-date">{{ g.date }}</span>
          <span class="dc-group-count">{{ t('decisions.group_meeting_count', { count: g.rows.length }) }}</span>
        </button>
        <div v-show="!collapsed.has(g.taskId)" class="db-flow dc-flow">
          <DecisionCard
            v-for="d in g.rows"
            :key="d.id"
            :decision="d"
            :pool="pool"
            @edit-save="saveDecision(d, $event)"
            @remove="removeDecision(d)"
          />
          <!-- 组内失效沉底折叠 / Ineffective items sink to the group footer -->
          <div v-if="g.ineffective.length" class="dc-ineffective">
            <button class="flow-completed-toggle dc-ineff-toggle" :aria-expanded="openIneff.has('g:' + g.taskId)" @click="toggleIneff('g:' + g.taskId)">
              <svg class="chev" :class="{ open: openIneff.has('g:' + g.taskId) }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
              {{ t('decisions.collapsed_title', { count: g.ineffective.length }) }}
            </button>
            <div v-show="openIneff.has('g:' + g.taskId)" class="db-flow dc-flow">
              <DecisionCard v-for="d in g.ineffective" :key="d.id" :decision="d" :pool="pool" @edit-save="saveDecision(d, $event)" @remove="removeDecision(d)" />
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 弹层 / Dialogs -->
    <StatusManagerDialog v-model="showStatusMgr" :statuses="statuses" @changed="onStatusesChanged" />
    <AddDecisionDialog ref="addDialogRef" v-model="showAdd" @submit="onAddSubmit" />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { extractErrorMessage } from '@/api/client'
import { fetchDecisions, updateTaskDecision, createTaskDecision, deleteTaskDecision } from '@/api/decisions'
import { isMockEnabled } from '@/api/decisionsMock'
import type { AggregatedDecision, DecisionCreatePayload, DecisionPatchPayload } from '@/api/decisions'
import { fetchStatuses, statusLabel, type DecisionStatusItem } from '@/api/decisionStatuses'
import { fetchProjects, type Project } from '@/api/projects'
import { useTaskStore } from '@/stores/task'
import { showToast } from '@/composables/useToast'
import DecisionCard from './decisions/DecisionCard.vue'
import KbFilterCombobox from './decisions/KbFilterCombobox.vue'
import StatusManagerDialog from './decisions/StatusManagerDialog.vue'
import AddDecisionDialog from './decisions/AddDecisionDialog.vue'

const { t, locale } = useI18n()
const taskStore = useTaskStore()

// ─── 数据 / Data ───
const rows = ref<AggregatedDecision[]>([])
/** 全量引用池（不带筛选）：解析 superseded_by 展示文本、supersede 候选 */
const pool = ref<AggregatedDecision[]>([])
const projects = ref<Project[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

// ─── 筛选器：状态字典驱动（DC-R2-c D6/D7） ───
// 默认选中 = 全部非闭档（未完成）状态 + 待确认位；「查看全部」一键放宽。
const TIME_OPTIONS = ['7d', '30d', 'all'] as const
type TimeRange = typeof TIME_OPTIONS[number]
/** 「待确认」伪筛选项：它是标志位而非状态（D7），与状态 chips 并列 */
const PENDING_KEY = 'pending'

const statuses = ref<DecisionStatusItem[]>([])
const timeRange = ref<TimeRange>('all')
const kbId = ref('')
const selected = ref<Set<string>>(new Set())
const keyword = ref('')
const showStatusMgr = ref(false)

function labelOf(s: DecisionStatusItem): string {
  return statusLabel(s, String(locale.value || 'zh-CN'))
}

/** 默认选中集 = 非闭档状态全集 + 待确认位 */
function defaultSelection(): Set<string> {
  const next = new Set(statuses.value.filter(s => !s.closing).map(s => s.id))
  next.add(PENDING_KEY)
  return next
}

/** 当前可见的状态 id（selected 去掉伪筛选项） */
const visibleStatusIds = computed(() => {
  const ids = new Set<string>()
  for (const k of selected.value) if (k !== PENDING_KEY) ids.add(k)
  return ids
})

/** 「查看全部」呈现为按下态：选中集已覆盖所有状态 */
const showAll = computed(() =>
  statuses.value.length > 0 && statuses.value.every(s => selected.value.has(s.id)),
)

/** 默认筛选下「待确认」只影响是否露出带标志位的条目 */
const hasPendingOnlyFilter = computed(() => !selected.value.has(PENDING_KEY))

function toggleStatus(key: string) {
  const next = new Set(selected.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selected.value = next
}

function toggleShowAll() {
  selected.value = showAll.value
    ? defaultSelection()
    : new Set([...statuses.value.map(s => s.id), PENDING_KEY])
}

/** 上一次状态字典的 id 集，用于区分「新新增」与「用户手动取消勾选」 */
const selectedBefore = ref<Set<string>>(new Set())

/** 状态字典变更后的选中集修正：删掉已不存在的项、新增的非闭档项自动露出（D7 默认可见） */
function syncSelection(nextList: DecisionStatusItem[]) {
  const ids = new Set(nextList.map(s => s.id))
  const next = new Set<string>()
  for (const k of selected.value) if (k === PENDING_KEY || ids.has(k)) next.add(k)
  const before = selectedBefore.value
  for (const s of nextList) if (!s.closing && !before.has(s.id)) next.add(s.id)
  selected.value = next
  selectedBefore.value = ids
}

function sinceDate(): string | undefined {
  if (timeRange.value === 'all') return undefined
  const days = timeRange.value === '7d' ? 7 : 30
  return new Date(Date.now() - days * 24 * 3600 * 1000).toISOString().slice(0, 10)
}

/** 空态文案分流：存在非默认筛选且全量池有数据 → 「筛选无结果」，否则 → 「暂无决策」 */
const isDefaultFilter = computed(() => {
  if (!statuses.value.length) return true
  const def = defaultSelection()
  if (def.size !== selected.value.size) return false
  return [...def].every(k => selected.value.has(k))
})
const showFilteredEmpty = computed(() =>
  (timeRange.value !== 'all' || kbId.value !== '' || keyword.value !== '' || !isDefaultFilter.value) &&
  pool.value.length > 0
)

// ─── 加载（关键词防抖） / Load with debounced keyword ───
let debounceTimer: number | undefined
async function load() {
  loading.value = true
  error.value = null
  try {
    // 状态字典可自定义后不再按状态多次往返：一次拉全量，状态筛选在客户端完成
    rows.value = await fetchDecisions({ since: sinceDate(), kb_id: kbId.value || undefined, q: keyword.value || undefined })
    if (!pool.value.length) pool.value = await fetchDecisions()
  } catch (e) {
    error.value = extractErrorMessage(e, t('decisions.error_load'))
    rows.value = []
  } finally {
    loading.value = false
  }
}
async function loadPool() {
  try { pool.value = await fetchDecisions() } catch { /* 池加载失败不阻断主列表 / pool failure never blocks the list */ }
}

watch([timeRange, kbId], () => { void load() })
watch(keyword, () => {
  window.clearTimeout(debounceTimer)
  debounceTimer = window.setTimeout(() => { void load() }, 300)
})
onBeforeUnmount(() => window.clearTimeout(debounceTimer))

onMounted(async () => {
  void load()
  try {
    statuses.value = await fetchStatuses()
    selected.value = defaultSelection()
    selectedBefore.value = new Set(statuses.value.map(s => s.id))
  } catch { /* 状态字典加载失败时降级为不过滤（列表仍可读） */ selected.value = new Set([PENDING_KEY]) }
  try { projects.value = await fetchProjects() } catch { /* 知识库筛选降级为“全部” / KB filter degrades to all */ }
  if (!taskStore.tasks.length) { try { await taskStore.loadTasks() } catch { /* 补录弹层会议列表降级 / add-dialog options degrade */ } }
  // mock 通道下把真实任务注册为会议，供补录/跳转/取代链路演示（生产构建永不触发）
  if (isMockEnabled()) {
    try {
      const { registerMockMeetings } = await import('@/api/decisionsMock')
      const nameOf = (pid: string | null) => projects.value.find(p => p.id === pid)?.name ?? null
      registerMockMeetings(taskStore.tasks.filter(x => x.status === 'completed').map(x => ({
        task_id: x.task_id,
        title: x.title || x.audio_name || x.task_id,
        meeting_date: x.meeting_date || x.created_at?.slice(0, 10) || '',
        kb_id: x.project_id,
        kb_name: nameOf(x.project_id),
      })))
    } catch { /* mock 注册失败仅影响演示链路 / mock registration is dev-only */ }
  }
})

// ─── 派生列表：状态可见集 + pending 客户端过滤 → 有/闭档分层 → 分组 ───
const filtered = computed(() => {
  const visible = visibleStatusIds.value
  let list = rows.value.filter(d => visible.has(d.status))
  if (hasPendingOnlyFilter.value) list = list.filter(d => !d.pending_confirmation)
  return list
})
const effectiveRows = computed(() => filtered.value.filter(d => !d.status_closing))
const ineffectiveRows = computed(() => filtered.value.filter(d => d.status_closing))

/** 组头标题取会议标题（DC-R2-b 契约修正：`title` 已为决策自身标题） */
interface MeetingGroup { taskId: string; title: string; date: string; rows: AggregatedDecision[]; ineffective: AggregatedDecision[] }
const visibleGroups = computed<MeetingGroup[]>(() => {
  const map = new Map<string, MeetingGroup>()
  for (const d of effectiveRows.value) {
    let g = map.get(d.task_id)
    if (!g) {
      g = { taskId: d.task_id, title: d.meeting_title || d.task_id, date: d.meeting_date || '', rows: [], ineffective: [] }
      map.set(d.task_id, g)
    }
    g.rows.push(d)
  }
  for (const d of ineffectiveRows.value) {
    const g = map.get(d.task_id)
    if (g) g.ineffective.push(d)
    else {
      // 该会议只剩失效条目时也要成组，保证筛选 superseded 时可见
      const ng: MeetingGroup = { taskId: d.task_id, title: d.meeting_title || d.task_id, date: d.meeting_date || '', rows: [], ineffective: [d] }
      map.set(d.task_id, ng)
    }
  }
  // rows 为空、仅失效的组不展开常规区，直接并入组内沉底
  return [...map.values()]
})

// ─── 折叠状态 / Collapse state ───
const collapsed = ref(new Set<string>())
function toggleGroup(id: string) {
  const next = new Set(collapsed.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  collapsed.value = next
}
const openIneff = ref(new Set<string>())
function toggleIneff(key: string) {
  const next = new Set(openIneff.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  openIneff.value = next
}

// ─── 行内操作：补录 / 状态字典管理 / Inline ops ───
// DC-R2-c（D6）：取代与撤销不再是系统行为，相关弹层与处理函数已下线。
async function onStatusesChanged(next: DecisionStatusItem[]) {
  statuses.value = next
  syncSelection(next)
  await Promise.all([load(), loadPool()])
}

// ─── F3 行内编辑/删除（DC-R2-a）：走既有 PUT/DELETE 任务级 CRUD，不回写纪要正文 ───
// DC-R2-b：入参升级为三字段 patch（title / text / owner）
async function saveDecision(d: AggregatedDecision, patch: DecisionPatchPayload) {
  try {
    await updateTaskDecision(d.task_id, d.id, patch)
    showToast(t('decisions.toast_edit_ok'), 'success')
    await Promise.all([load(), loadPool()])
  } catch (e) {
    showToast(t('decisions.toast_op_failed', { reason: extractErrorMessage(e) }), 'error')
  }
}

async function removeDecision(d: AggregatedDecision) {
  try {
    await deleteTaskDecision(d.task_id, d.id)
    showToast(t('decisions.toast_delete_ok'), 'success')
    await Promise.all([load(), loadPool()])
  } catch (e) {
    showToast(t('decisions.toast_op_failed', { reason: extractErrorMessage(e) }), 'error')
  }
}

const showAdd = ref(false)
const addDialogRef = ref<InstanceType<typeof AddDecisionDialog> | null>(null)
async function onAddSubmit(taskId: string, payload: DecisionCreatePayload) {
  try {
    await createTaskDecision(taskId, payload)
    showToast(t('decisions.toast_add_ok'), 'success')
    showAdd.value = false
    await Promise.all([load(), loadPool()])
  } catch (e) {
    addDialogRef.value?.setSubmitting(false)
    showToast(t('decisions.toast_op_failed', { reason: extractErrorMessage(e) }), 'error')
  }
}
</script>

<style scoped>
.dc-page { padding: var(--s-6) var(--s-8) var(--s-9); max-width: 880px; margin: 0 auto; }

.dc-header-bar { display: flex; align-items: center; justify-content: space-between; gap: var(--s-4); margin-bottom: var(--s-5); flex-wrap: wrap; }
.dc-title-group { display: flex; align-items: baseline; gap: var(--s-3); }
.dc-title-group h1 { font-size: var(--fs-20); font-weight: 600; margin: 0; }
.dc-count { font-size: var(--fs-12, 12px); color: var(--muted); }
.dc-header-actions { display: flex; align-items: center; gap: var(--s-3); }

/* 分段切换 / Segmented control */
.dc-seg { display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; }
.dc-seg-btn { padding: 5px 12px; font-size: var(--fs-12, 12px); border: none; background: transparent; color: var(--muted); cursor: pointer; transition: all 0.12s; }
.dc-seg-btn + .dc-seg-btn { border-left: 1px solid var(--border); }
.dc-seg-btn.active { background: var(--surface-2); color: var(--fg); font-weight: 500; }
.dc-seg-btn:hover:not(.active) { color: var(--fg); }

.dc-add-btn { padding: 5px 12px; border: 1px solid var(--border); background: transparent; color: var(--muted); font-size: var(--fs-12, 12px); cursor: pointer; border-radius: var(--radius-sm); white-space: nowrap; transition: all 0.12s; }
.dc-add-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }

/* 筛选栏 / Filter bar */
.dc-filter-bar { display: flex; align-items: center; gap: var(--s-5); flex-wrap: wrap; padding: var(--s-3) var(--s-4); border: 1px solid var(--border); border-radius: var(--radius-md, 8px); background: var(--surface-1, transparent); margin-bottom: var(--s-5); }
.dc-filter-group { display: flex; align-items: center; gap: var(--s-2); }
.dc-grow { flex: 1; min-width: 180px; }
.dc-filter-label { font-size: var(--fs-12, 12px); color: var(--muted); white-space: nowrap; }
.dc-chip { padding: 3px 10px; font-size: var(--fs-12, 12px); border: 1px solid var(--border); border-radius: 999px; background: transparent; color: var(--muted); cursor: pointer; transition: all 0.12s; }
.dc-chip.on { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); font-weight: 500; }
/* DC-R2-c：状态 chips 由字典驱动，带色点；「查看全部」为放宽筛选的虚线项；管理入口靠右 */
.dc-chip { display: inline-flex; align-items: center; gap: 5px; }
.dc-chip-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dc-chip-all { border-style: dashed; }
.dc-chip-all.on { border-style: solid; }
.dc-manage-btn { margin-left: auto; padding: 3px 10px; font-size: var(--fs-12, 12px); border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--muted); cursor: pointer; white-space: nowrap; }
.dc-manage-btn:hover { color: var(--accent); border-color: var(--accent); }
.dc-kw-wrap { position: relative; display: flex; align-items: center; flex: 1; }
.dc-kw-icon { position: absolute; left: 9px; color: var(--muted); pointer-events: none; }
.dc-kw-input { width: 100%; box-sizing: border-box; padding: 5px 10px 5px 28px; font-size: var(--fs-12, 12px); border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--fg); }
.dc-kw-input:focus { outline: none; border-color: var(--accent); }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }

/* 三态 / States */
.dc-loading { padding: var(--s-6) 0; }
.dc-error { display: flex; align-items: center; justify-content: center; gap: var(--s-3); padding: var(--s-6); color: var(--error); font-size: var(--fs-13, 13px); }
.dc-error-retry { padding: 3px 12px; color: var(--error); background: transparent; border: 1px solid var(--error); border-radius: var(--radius-sm); cursor: pointer; font-size: var(--fs-12, 12px); }
.dc-error-retry:hover { background: var(--error); color: var(--surface); }
.dc-empty { text-align: center; padding: var(--s-9) var(--s-7); color: var(--muted); }
.dc-empty svg { opacity: 0.4; margin-bottom: var(--s-2); }
.dc-empty p { font-size: var(--fs-13, 13px); margin: 0 auto; max-width: 360px; line-height: 1.6; }

/* 分组 / Groups */
.dc-groups { display: flex; flex-direction: column; gap: var(--s-5); }
.dc-group-head { display: flex; align-items: center; gap: var(--s-2); width: 100%; padding: var(--s-2) 0; border: none; background: transparent; cursor: pointer; color: var(--fg); text-align: left; }
.dc-chev { transition: transform 0.15s; color: var(--muted); flex-shrink: 0; transform: rotate(90deg); }
.dc-group-head[aria-expanded="false"] .dc-chev { transform: rotate(0deg); }
.dc-group-title { font-size: var(--fs-14); font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dc-group-date { font-size: var(--fs-12, 12px); color: var(--subtle); flex-shrink: 0; }
.dc-group-count { margin-left: auto; font-size: var(--fs-12, 12px); color: var(--muted); flex-shrink: 0; }
.dc-flow { margin-top: var(--s-2); }

/* 失效沉底折叠区：复用 flow-completed-toggle 基元 / Sink section reuses the toggle primitive */
.dc-ineffective { margin-top: var(--s-3); padding-top: var(--s-3); border-top: 1px dashed var(--border); }
.dc-ineff-toggle { margin-bottom: var(--s-2); }
</style>
