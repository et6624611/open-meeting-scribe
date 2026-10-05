<template>
  <!-- 决策中心：跨会议的决策流总览与就地管理（DC-UNIFY-01：决策流是唯一决策对象）
       Decision Center: cross-meeting decision flow, editable in place -->
  <div class="dc-page">
    <!-- 头部：标题 + 计数 + 补录 / Header -->
    <div class="dc-header-bar">
      <div class="dc-title-group">
        <h1>{{ t('decisions.title') }}</h1>
        <span class="dc-count" v-if="!loading && !error">{{ viewMode === 'topic' ? t('decisions.topic_count', { count: visibleTopics.length }) : t('decisions.count', { count: effectiveRows.length + ineffectiveRows.length }) }}</span>
      </div>
      <div class="dc-header-actions">
        <div class="dc-seg" role="group" :aria-label="t('decisions.view_mode_label')">
          <button type="button" class="dc-seg-btn" :class="{ active: viewMode === 'meeting' }" @click="viewMode = 'meeting'">{{ t('decisions.view_by_meeting') }}</button>
          <button type="button" class="dc-seg-btn" :class="{ active: viewMode === 'topic' }" @click="viewMode = 'topic'">{{ t('decisions.view_by_topic') }}</button>
        </div>
        <button class="dc-add-btn" @click="showAdd = true">+ {{ t('decisions.add_manual') }}</button>
      </div>
    </div>

    <!-- 筛选区：时间 + 筛选（知识库/状态收纳进浮层）+ 关键词 / Filter bar -->
    <div class="dc-filter-bar" role="search">
      <div class="dc-seg" role="group" :aria-label="t('decisions.filter_time')">
        <button v-for="opt in TIME_OPTIONS" :key="opt" class="dc-seg-btn" :class="{ active: timeRange === opt }" @click="timeRange = opt">
          {{ t('decisions.time_' + opt) }}
        </button>
      </div>

      <!-- 筛选触发：知识库 + 状态收进浮层；生效条件数以徽章呈现 / Filter trigger with active-count badge -->
      <div class="dc-filter-pop-wrap">
        <button
          ref="filterBtnEl"
          type="button"
          class="dc-filter-trigger"
          :class="{ on: filterOpen || activeFilterCount > 0 }"
          aria-haspopup="dialog"
          :aria-expanded="filterOpen"
          :aria-controls="'dcFilterPop'"
          @click="toggleFilter"
        >
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
          {{ t('decisions.filter_trigger') }}
          <span v-if="activeFilterCount > 0" class="dc-filter-badge">{{ activeFilterCount }}</span>
        </button>
        <div
          v-show="filterOpen"
          ref="filterPopEl"
          id="dcFilterPop"
          class="dc-filter-pop"
          role="dialog"
          :aria-label="t('decisions.filter_trigger')"
        >
          <!-- 知识库：内联单选列表（避免嵌套浮层）/ KB: inline single-select list -->
          <div class="dfp-section">
            <span class="dfp-label">{{ t('decisions.filter_kb') }}</span>
            <div class="dfp-kb-list">
              <button
                type="button"
                class="dfp-kb-opt"
                :class="{ on: kbId === '' }"
                :aria-pressed="kbId === ''"
                @click="kbId = ''"
              >{{ t('decisions.kb_all') }}</button>
              <button
                type="button"
                class="dfp-kb-opt"
                :class="{ on: kbId === '__none__' }"
                :aria-pressed="kbId === '__none__'"
                @click="kbId = '__none__'"
              >{{ t('decisions.kb_none') }}</button>
              <button
                v-for="p in projects"
                :key="p.id"
                type="button"
                class="dfp-kb-opt"
                :class="{ on: kbId === p.id }"
                :aria-pressed="kbId === p.id"
                :title="p.name"
                @click="kbId = p.id"
              >{{ p.name }}</button>
            </div>
          </div>

          <!-- 状态：字典驱动 chips 多选（含用户新增项）；默认只看非闭档 / Status: dict-driven multi-select -->
          <div class="dfp-section">
            <div class="dfp-label-row">
              <span class="dfp-label">{{ t('decisions.filter_status') }}</span>
              <button type="button" class="dfp-link" @click="selectAllStatuses">{{ t('decisions.filter_select_all') }}</button>
            </div>
            <div class="dfp-chips" role="group" :aria-label="t('decisions.filter_status')">
              <button
                v-for="s in statuses"
                :key="s.id"
                class="dc-chip"
                :class="{ on: visibleStatusIds.has(s.id) }"
                :aria-pressed="visibleStatusIds.has(s.id)"
                @click="toggleStatus(s.id)"
              >
                <span class="dc-chip-dot" :style="{ background: s.color }"></span>{{ labelOf(s.id, locale) }}
              </button>
            </div>
          </div>

          <!-- 底部：重置默认口径 + 状态管理（配置操作不外露）/ Footer: reset + status manager -->
          <div class="dfp-footer">
            <button type="button" class="dfp-link" @click="resetFilters">{{ t('decisions.filter_reset') }}</button>
            <button type="button" class="dfp-manage" @click="openStatusMgr">
              {{ t('decisions.sm_open') }}
              <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
        </div>
      </div>

      <div class="dc-kw-wrap dc-grow">
        <label class="sr-only" for="dcKeyword">{{ t('decisions.search_placeholder') }}</label>
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" class="dc-kw-icon"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input id="dcKeyword" v-model.trim="keyword" type="search" class="dc-kw-input" :placeholder="t('decisions.search_placeholder')" />
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

    <!-- 空态：无数据（标题+说明） vs 筛选无结果（仅说明）；统一 EmptyHint，无功能按钮 -->
    <div v-else-if="(viewMode === 'meeting' ? !visibleGroups.length : !visibleTopics.length)" class="dc-empty">
      <EmptyHint
        :title="showFilteredEmpty ? '' : t('decisions.empty_title')"
        :body="showFilteredEmpty ? t('decisions.empty_filtered') : t('decisions.empty_all')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><path d="M8 21h8"/><path d="M5 7h14"/><path d="M5 7 2.5 13a3 3 0 0 0 5 0L5 7z"/><path d="M19 7l-2.5 6a3 3 0 0 0 5 0L19 7z"/></svg>
        </template>
      </EmptyHint>
    </div>

    <!-- 列表主体（按会议）：固定按会议分组，卡片即纪要页同款可交互决策流节点 -->
    <section v-else-if="viewMode === 'meeting'" class="dc-groups">
      <div v-for="g in visibleGroups" :key="g.taskId" class="dc-group">
        <div class="dc-group-head">
          <button class="dc-group-toggle" :aria-expanded="!collapsed.has(g.taskId)" @click="toggleGroup(g.taskId)">
            <svg class="dc-chev" :class="{ open: !collapsed.has(g.taskId) }" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
          <RouterLink class="dc-group-title" :title="g.title" :to="{ name: 'generating', params: { taskId: g.taskId }, query: { tab: 'todos' } }">{{ g.title }}</RouterLink>
          <span class="dc-group-date">{{ g.date }}</span>
          <span class="dc-group-count">{{ t('decisions.group_meeting_count', { count: g.rows.length + g.ineffective.length }) }}</span>
        </div>
        <div v-show="!collapsed.has(g.taskId)" class="db-flow dc-flow">
          <DecisionNode
            v-for="d in g.rows"
            :key="d.id"
            :todo="d"
            @select-status="(s) => saveStatus(d, s)"
            @select-owner="(o) => savePatch(d, { owner_type: o })"
            @commit-content="(c) => savePatch(d, { why: c })"
            @patch="(p) => savePatch(d, p)"
            @delete="removeNode(d)"
          />
          <!-- 闭档（完成类）条目沉底折叠 / Closing items sink to the group footer -->
          <div v-if="g.ineffective.length" class="dc-ineffective">
            <button class="flow-completed-toggle dc-ineff-toggle" :aria-expanded="openIneff.has('g:' + g.taskId)" @click="toggleIneff('g:' + g.taskId)">
              <svg class="chev" :class="{ open: openIneff.has('g:' + g.taskId) }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
              {{ t('decisions.collapsed_title', { count: g.ineffective.length }) }}
            </button>
            <div v-show="openIneff.has('g:' + g.taskId)" class="db-flow dc-flow">
              <DecisionNode
                v-for="d in g.ineffective"
                :key="d.id"
                :todo="d"
                @select-status="(s) => saveStatus(d, s)"
                @select-owner="(o) => savePatch(d, { owner_type: o })"
                @commit-content="(c) => savePatch(d, { why: c })"
                @patch="(p) => savePatch(d, p)"
                @delete="removeNode(d)"
              />
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 列表主体（按议题 · 全局视角）：跨会议同议题归并为主记录，历史折叠为演变链 -->
    <section v-else class="dc-topics">
      <p class="dc-topic-hint">{{ t('decisions.topic_view_hint') }}</p>
      <div v-for="g in visibleTopics" :key="g.topic_key" class="dc-topic" :data-topic-key="g.topic_key">
        <div class="dc-topic-head">
          <button class="dc-group-toggle" :aria-expanded="!collapsedTopics.has(g.topic_key)" @click="toggleTopic(g.topic_key)">
            <svg class="dc-chev" :class="{ open: !collapsedTopics.has(g.topic_key) }" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
          <span class="dc-topic-title">{{ g.title }}</span>
          <span v-if="g.meeting_count > 1" class="dc-topic-badge">{{ t('decisions.topic_meetings_badge', { count: g.meeting_count }) }}</span>
          <span v-if="g.history.length" class="dc-topic-conf" :title="t('decisions.topic_confidence_hint', { pct: Math.round(g.confidence * 100) })">{{ t('decisions.topic_confidence_hint', { pct: Math.round(g.confidence * 100) }) }}</span>
          <span v-if="g.kb_name" class="dc-topic-kb">{{ g.kb_name }}</span>
        </div>
        <div v-show="!collapsedTopics.has(g.topic_key)" class="db-flow dc-flow">
          <!-- 主记录：纪要页同款可交互卡片（写操作仍落回自身节点） -->
          <DecisionNode
            :todo="g.main"
            @select-status="(s) => saveStatus(g.main, s)"
            @select-owner="(o) => savePatch(g.main, { owner_type: o })"
            @commit-content="(c) => savePatch(g.main, { why: c })"
            @patch="(p) => savePatch(g.main, p)"
            @delete="removeNode(g.main)"
          />
          <!-- 演变链：历史同类记录（只读，回跳来源会议） -->
          <div v-if="g.history.length" class="dc-ineffective">
            <button class="flow-completed-toggle dc-ineff-toggle" :aria-expanded="openEvo.has(g.topic_key)" @click="toggleEvo(g.topic_key)">
              <svg class="chev" :class="{ open: openEvo.has(g.topic_key) }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
              {{ t('decisions.topic_evolution_toggle', { count: g.history.length }) }}
            </button>
            <ul v-show="openEvo.has(g.topic_key)" class="dc-evo-list">
              <li
                v-for="h in g.history"
                :key="h.id"
                class="dc-evo-item"
                :class="{ 'is-superseded': !!h.superseded_by }"
              >
                <span class="dc-evo-dot" :style="{ background: h.status_color || 'var(--muted)' }"></span>
                <div class="dc-evo-entry">
                  <div class="dc-evo-row">
                    <span class="dc-evo-title" :title="evoTitle(h)">{{ evoTitle(h) }}</span>
                    <span class="dc-evo-status" :class="{ 'is-superseded': !!h.superseded_by }" :style="evoStatusStyle(h)">{{ evoStatusLabel(h) }}</span>
                    <!-- 未替代：动作出口——标记为已被本议题主记录替代 / Action only when still active -->
                    <button
                      v-if="!h.superseded_by"
                      type="button"
                      class="dc-evo-act"
                      :disabled="evoBusy.has(h.id)"
                      :title="t('decisions.evo_mark_superseded')"
                      :aria-label="t('decisions.evo_mark_superseded')"
                      @click="markSuperseded(h, g.main)"
                    >
                      <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
                    </button>
                    <RouterLink
                      class="dc-evo-go"
                      :to="meetingNodeLink(h.task_id, h.id)"
                      :title="t('decisions.topic_goto_meeting')"
                    >
                      <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                    </RouterLink>
                  </div>
                  <!-- 替代关系：指向新决策（快照标题；点击直达节点锚点）+ 撤销 -->
                  <div v-if="h.superseded_by" class="dc-evo-replaced">
                    <span class="dc-evo-replaced-label">{{ t('decisions.evo_replaced_by') }}</span>
                    <RouterLink class="dc-evo-replaced-link" :to="meetingNodeLink(h.superseded_by.task_id, h.superseded_by.todo_id)">
                      {{ h.superseded_by.meeting_title ? t('decisions.evo_replaced_target', { meeting: h.superseded_by.meeting_title, title: h.superseded_by.title }) : (h.superseded_by.title || t('decisions.evo_replaced_target_gone')) }}
                    </RouterLink>
                    <button
                      type="button"
                      class="dc-evo-undo"
                      :disabled="evoBusy.has(h.id)"
                      @click="undoSupersede(h)"
                    >{{ t('decisions.evo_undo') }}</button>
                  </div>
                  <p v-if="evoBody(h)" class="dc-evo-text">{{ evoBody(h) }}</p>
                  <div class="dc-evo-foot">
                    <span class="dc-evo-meta">{{ h.meeting_title }}<template v-if="h.meeting_date"> · {{ h.meeting_date }}</template></span>
                    <span v-if="!h.superseded_by" class="dc-evo-owner">{{ t('generating.todos.owner_waiting_' + (h.owner_type || 'self')) }}</span>
                  </div>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <StatusManagerDialog v-model="showStatusMgr" :statuses="statuses" @changed="onStatusesChanged" />
    <AddDecisionDialog ref="addDialogRef" v-model="showAdd" @submit="onAddSubmit" />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { extractErrorMessage } from '@/api/client'
import { fetchFlowNodes, fetchFlowTopics, type FlowNode, type TopicGroup } from '@/api/decisions'
import { createTodo, deleteTodo, supersedeTodo, revertSupersede, updateTodo, type TodoCreatePayload, type TodoPatch } from '@/api/notes'
import { meetingNodeLink, parseTopicKey } from '@/views/decisionEvolutionNav'
import { fetchStatuses, statusLabel, type DecisionStatusItem } from '@/api/decisionStatuses'
import { refreshDecisionStatuses } from '@/composables/useDecisionStatuses'
import { fetchProjects, type Project } from '@/api/projects'
import { useTaskStore } from '@/stores/task'
import { showToast } from '@/composables/useToast'
import { usePageBack } from '@/composables/usePageBack'
import { getDockBounds, positionDropdown } from '@/utils/popoverPosition'
import { stripDecisionEmphasis } from '@/utils/decisionText'
import EmptyHint from '@/components/common/EmptyHint.vue'
import DecisionNode from './generating/DecisionNode.vue'
import StatusManagerDialog from './decisions/StatusManagerDialog.vue'
import AddDecisionDialog from './decisions/AddDecisionDialog.vue'

const { t, locale } = useI18n()
const taskStore = useTaskStore()

// ESC 返回上一页：与其他二级管理页一致（浮层由各自处理器消费事件，不受影响）
usePageBack()

// ─── 数据 / Data ───
const rows = ref<FlowNode[]>([])
/** 议题归并簇（全局视角）：与 rows 同步拉取，切换视图无需往返 */
const topics = ref<TopicGroup[]>([])
/** 视图模式：按会议（默认）/ 按议题（跨会议归并） */
const viewMode = ref<'meeting' | 'topic'>('meeting')
/** 全量引用池（不带筛选）：用于判断空态是"没有数据"还是"筛没了" */
const pool = ref<FlowNode[]>([])
const projects = ref<Project[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

// ─── 筛选器：状态字典驱动（DC-R2-c D6/D7 + DC-UNIFY-01） ───
// 默认选中 = 全部非闭档（未完成）状态；「查看全部」一键放宽。
const TIME_OPTIONS = ['7d', '30d', 'all'] as const
type TimeRange = typeof TIME_OPTIONS[number]

const statuses = ref<DecisionStatusItem[]>([])
const timeRange = ref<TimeRange>('all')
const kbId = ref('')
const selected = ref<Set<string>>(new Set())
const keyword = ref('')
const showStatusMgr = ref(false)

function labelOf(id: string, loc: string): string {
  const meta = statuses.value.find(s => s.id === id)
  return meta ? statusLabel(meta, loc) : id
}

// ─── 演变链历史项：就地只读展示（字段口径与 DecisionNode 一致，标题不再承担跳转） ───
const strip = stripDecisionEmphasis

function evoTitle(h: FlowNode): string {
  return strip(h.title || h.text || '')
}

/** 正文：why 优先；有独立标题时 why 为空回退 text，无独立标题时首行已是 text，不重复 */
function evoBody(h: FlowNode): string {
  const hasTitle = Boolean(h.title && h.text && h.text !== h.why)
  return strip(h.why || (hasTitle ? h.text || '' : ''))
}

function evoStatusLabel(h: FlowNode): string {
  const st = h.status || (h.done ? 'done' : 'in_progress')
  return labelOf(st, String(locale.value || 'zh-CN'))
}

function evoStatusStyle(h: FlowNode) {
  const color = h.status_color || 'var(--muted)'
  return { color, background: `color-mix(in oklch, ${color} 14%, transparent)` }
}

// ─── 演变链动作：手动标记/撤销「已被替代」（永不自动闭档） ───
const route = useRoute()
const evoBusy = ref(new Set<string>())

async function markSuperseded(h: FlowNode, main: FlowNode) {
  if (evoBusy.value.has(h.id)) return
  evoBusy.value = new Set(evoBusy.value).add(h.id)
  try {
    await supersedeTodo(h.task_id, h.id, { taskId: main.task_id, todoId: main.id })
    await load()
    showToast(t('decisions.evo_mark_ok'), 'success')
  } catch (e) {
    showToast(t('decisions.toast_op_failed', { reason: extractErrorMessage(e) }), 'error')
  } finally {
    const next = new Set(evoBusy.value); next.delete(h.id); evoBusy.value = next
  }
}

async function undoSupersede(h: FlowNode) {
  if (evoBusy.value.has(h.id)) return
  evoBusy.value = new Set(evoBusy.value).add(h.id)
  try {
    await revertSupersede(h.task_id, h.id)
    await load()
    showToast(t('decisions.evo_undo_ok'), 'success')
  } catch (e) {
    showToast(t('decisions.toast_op_failed', { reason: extractErrorMessage(e) }), 'error')
  } finally {
    const next = new Set(evoBusy.value); next.delete(h.id); evoBusy.value = next
  }
}

/** 纪要页演变角标回跳：?view=topic&topic=<key> → 切议题视图、展开该簇与演变链并滚动定位 */
function applyTopicAnchor() {
  if (route.query.view === 'topic') viewMode.value = 'topic'
  const key = parseTopicKey(route.query)
  if (!key || viewMode.value !== 'topic') return
  collapsedTopics.value = new Set([...collapsedTopics.value].filter(k => k !== key))
  openEvo.value = new Set(openEvo.value).add(key)
  void nextTick(() => {
    const el = document.querySelector(`[data-topic-key="${CSS.escape(key)}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

/** 默认选中集 = 非闭档状态全集 */
function defaultSelection(): Set<string> {
  return new Set(statuses.value.filter(s => !s.closing).map(s => s.id))
}

/** 当前可见的状态 id */
const visibleStatusIds = computed(() => selected.value)

function toggleStatus(key: string) {
  const next = new Set(selected.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selected.value = next
}

/** 全选所有状态（含闭档）；与「重置」构成默认口径的两个出口 */
function selectAllStatuses() {
  selected.value = new Set(statuses.value.map(s => s.id))
}

// ─── 筛选浮层：定位走 popoverPosition 单一真源，禁止手写 left/top 夹视口 ───
const filterBtnEl = ref<HTMLElement | null>(null)
const filterPopEl = ref<HTMLElement | null>(null)
const filterOpen = ref(false)

/** 状态集是否偏离默认口径（非闭档全集） */
const statusDirty = computed(() => {
  const def = defaultSelection()
  if (def.size !== selected.value.size) return true
  return [...def].some(k => !selected.value.has(k))
})

/** 生效条件数：知识库 + 状态各计 1（时间外露，不计） */
const activeFilterCount = computed(() =>
  (kbId.value !== '' ? 1 : 0) + (statusDirty.value ? 1 : 0),
)

/** 计算浮层位置：rAF 后实测尺寸，向下弹出、start 对齐、避让停靠栏 */
function positionFilter() {
  requestAnimationFrame(() => {
    if (!filterBtnEl.value || !filterPopEl.value) return
    const tr = filterBtnEl.value.getBoundingClientRect()
    const { x, y } = positionDropdown(
      { top: tr.top, left: tr.left, width: tr.width, height: tr.height },
      filterPopEl.value.offsetWidth,
      filterPopEl.value.offsetHeight,
      getDockBounds(),
      { gap: 4, align: 'start' },
    )
    filterPopEl.value.style.top = `${y}px`
    filterPopEl.value.style.left = `${x}px`
  })
}

function onFilterDocClick(e: MouseEvent) {
  const tgt = e.target as Node
  if (filterPopEl.value?.contains(tgt) || filterBtnEl.value?.contains(tgt)) return
  closeFilter()
}

function onFilterKeydown(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  // 消费事件：避免页面级 ESC（usePageBack）把「关闭浮层」误判为返回
  e.preventDefault()
  closeFilter()
  filterBtnEl.value?.focus()
}

function onFilterReflow() {
  if (filterOpen.value) positionFilter()
}

function openFilter() {
  filterOpen.value = true
  positionFilter()
  document.addEventListener('click', onFilterDocClick)
  document.addEventListener('keydown', onFilterKeydown)
  window.addEventListener('scroll', onFilterReflow, true)
  window.addEventListener('resize', onFilterReflow)
}

function closeFilter() {
  if (!filterOpen.value) return
  filterOpen.value = false
  document.removeEventListener('click', onFilterDocClick)
  document.removeEventListener('keydown', onFilterKeydown)
  window.removeEventListener('scroll', onFilterReflow, true)
  window.removeEventListener('resize', onFilterReflow)
}

function toggleFilter() {
  filterOpen.value ? closeFilter() : openFilter()
}

/** 重置为默认口径：全部知识库 + 非闭档状态 */
function resetFilters() {
  kbId.value = ''
  selected.value = defaultSelection()
}

/** 状态管理是配置操作：从浮层进入，先关浮层 */
function openStatusMgr() {
  closeFilter()
  showStatusMgr.value = true
}

onBeforeUnmount(closeFilter)

/** 上一次状态字典的 id 集，用于区分「新新增」与「用户手动取消勾选」 */
const selectedBefore = ref<Set<string>>(new Set())

/** 状态字典变更后的选中集修正：删掉已不存在的项、新增的非闭档项自动露出（D7 默认可见） */
function syncSelection(nextList: DecisionStatusItem[]) {
  const ids = new Set(nextList.map(s => s.id))
  const next = new Set<string>()
  for (const k of selected.value) if (ids.has(k)) next.add(k)
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
    const q = { since: sinceDate(), kb_id: kbId.value || undefined, q: keyword.value || undefined }
    rows.value = await fetchFlowNodes(q)
    topics.value = await fetchFlowTopics(q)
    if (!pool.value.length) pool.value = await fetchFlowNodes()
  } catch (e) {
    error.value = extractErrorMessage(e, t('decisions.error_load'))
    rows.value = []
  } finally {
    loading.value = false
  }
}
async function loadPool() {
  try { pool.value = await fetchFlowNodes() } catch { /* 池加载失败不阻断主列表 / pool failure never blocks the list */ }
}

watch([timeRange, kbId], () => { void load() })
watch(keyword, () => {
  window.clearTimeout(debounceTimer)
  debounceTimer = window.setTimeout(() => { void load() }, 300)
})
onBeforeUnmount(() => window.clearTimeout(debounceTimer))

onMounted(async () => {
  // 状态字典先到位：默认「非闭档」过滤依赖它，否则议题锚点定位时簇尚未渲染
  try {
    statuses.value = await fetchStatuses()
    selected.value = defaultSelection()
    selectedBefore.value = new Set(statuses.value.map(s => s.id))
  } catch { /* 状态字典加载失败时降级为不过滤（列表仍可读） */ selected.value = new Set() }
  await load()
  applyTopicAnchor()
  try { projects.value = await fetchProjects() } catch { /* 知识库筛选降级为"全部" / KB filter degrades to all */ }
  if (!taskStore.tasks.length) { try { await taskStore.loadTasks() } catch { /* 补录弹层会议列表降级 / add-dialog options degrade */ } }
})

// ─── 派生列表：状态可见集 → 有/闭档分层 → 分组 ───
const filtered = computed(() => rows.value.filter(d => visibleStatusIds.value.has(d.status || '')))
const effectiveRows = computed(() => filtered.value.filter(d => !d.status_closing))
const ineffectiveRows = computed(() => filtered.value.filter(d => d.status_closing))

interface MeetingGroup { taskId: string; title: string; date: string; rows: FlowNode[]; ineffective: FlowNode[] }
const visibleGroups = computed<MeetingGroup[]>(() => {
  const map = new Map<string, MeetingGroup>()
  const ensure = (d: FlowNode): MeetingGroup => {
    let g = map.get(d.task_id)
    if (!g) {
      g = { taskId: d.task_id, title: d.meeting_title || d.task_id, date: d.meeting_date || '', rows: [], ineffective: [] }
      map.set(d.task_id, g)
    }
    return g
  }
  for (const d of effectiveRows.value) ensure(d).rows.push(d)
  for (const d of ineffectiveRows.value) ensure(d).ineffective.push(d)
  return [...map.values()]
})

// 议题视图可见集：主记录状处于可见状态集才展示（与按会议一致的“只看非闭档”默认口径）
const visibleTopics = computed<TopicGroup[]>(() =>
  topics.value.filter(g => visibleStatusIds.value.has(g.main?.status || '')),
)

// 议题/演变链折叠态 / Topic & evolution collapse state
const collapsedTopics = ref(new Set<string>())
function toggleTopic(key: string) {
  const next = new Set(collapsedTopics.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  collapsedTopics.value = next
}
const openEvo = ref(new Set<string>())
function toggleEvo(key: string) {
  const next = new Set(openEvo.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  openEvo.value = next
}

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

// ─── 行内操作：直接落到决策流节点（与纪要页同一套端点） ───
async function saveStatus(d: FlowNode, status: string) {
  await savePatch(d, { status })
}

async function savePatch(d: FlowNode, patch: TodoPatch) {
  try {
    await updateTodo(d.task_id, d.id, patch)
    await Promise.all([load(), loadPool()])
  } catch (e) {
    showToast(t('decisions.toast_op_failed', { reason: extractErrorMessage(e) }), 'error')
  }
}

async function removeNode(d: FlowNode) {
  try {
    await deleteTodo(d.task_id, d.id)
    showToast(t('decisions.toast_delete_ok'), 'success')
    await Promise.all([load(), loadPool()])
  } catch (e) {
    showToast(t('decisions.toast_op_failed', { reason: extractErrorMessage(e) }), 'error')
  }
}

// ─── 补录：归属某场会议的一条决策流节点 / Manual entry into a meeting's flow ───
const showAdd = ref(false)
const addDialogRef = ref<InstanceType<typeof AddDecisionDialog> | null>(null)
async function onAddSubmit(taskId: string, payload: TodoCreatePayload) {
  try {
    await createTodo(taskId, payload)
    showToast(t('decisions.toast_add_ok'), 'success')
    showAdd.value = false
    await Promise.all([load(), loadPool()])
  } catch (e) {
    addDialogRef.value?.setSubmitting(false)
    showToast(t('decisions.toast_op_failed', { reason: extractErrorMessage(e) }), 'error')
  }
}

// ─── 状态字典变更后同步（管理弹层 / 卡片色点徽标都随之刷新） ───
async function onStatusesChanged(next: DecisionStatusItem[]) {
  statuses.value = next
  syncSelection(next)
  await refreshDecisionStatuses()
  await Promise.all([load(), loadPool()])
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

/* 筛选栏：单行（时间 + 筛选触发 + 搜索）/ Single-row filter bar */
.dc-filter-bar { display: flex; align-items: center; gap: var(--s-3); flex-wrap: wrap; padding: var(--s-3) var(--s-4); border: 1px solid var(--border); border-radius: var(--radius-md, 8px); background: var(--surface-1, transparent); margin-bottom: var(--s-5); }
.dc-filter-pop-wrap { display: inline-flex; }
.dc-grow { flex: 1; min-width: 180px; }

/* 筛选触发钮 / Filter trigger */
.dc-filter-trigger { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; font-size: var(--fs-12, 12px); border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--muted); cursor: pointer; white-space: nowrap; transition: all 0.12s; }
.dc-filter-trigger:hover { border-color: var(--border-strong); color: var(--fg); }
.dc-filter-trigger.on { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
.dc-filter-badge { display: inline-flex; align-items: center; justify-content: center; min-width: 16px; height: 16px; padding: 0 4px; font-size: 10px; font-weight: 600; line-height: 1; border-radius: 999px; background: var(--accent); color: var(--surface, #fff); }

/* 筛选浮层：fixed + 定位真源 popoverPosition / Filter popover */
.dc-filter-pop { position: fixed; z-index: var(--z-popover); width: 280px; box-sizing: border-box; padding: var(--s-3); border: 1px solid var(--border); border-radius: var(--radius-md, 8px); background: var(--surface-1, var(--bg, #fff)); box-shadow: var(--dropdown-shadow); }
.dfp-section + .dfp-section { margin-top: var(--s-3); }
.dfp-label { display: block; font-size: var(--fs-12, 12px); color: var(--muted); margin-bottom: 6px; }
.dfp-label-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.dfp-label-row .dfp-label { margin-bottom: 0; }
.dfp-link { padding: 0; font-size: var(--fs-12, 12px); border: none; background: none; color: var(--muted); cursor: pointer; }
.dfp-link:hover { color: var(--accent); }
.dfp-kb-list { max-height: 168px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.dfp-kb-opt { text-align: left; padding: 5px 8px; font-size: var(--fs-12, 12px); border: none; border-radius: var(--radius-sm); background: transparent; color: var(--fg); cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dfp-kb-opt:hover { background: var(--surface-2); }
.dfp-kb-opt.on { color: var(--accent); background: var(--accent-soft); font-weight: 500; }
.dfp-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.dc-chip { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; font-size: var(--fs-12, 12px); border: 1px solid var(--border); border-radius: 999px; background: transparent; color: var(--muted); cursor: pointer; transition: all 0.12s; }
.dc-chip.on { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); font-weight: 500; }
.dc-chip-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

.dfp-footer { display: flex; align-items: center; justify-content: space-between; margin-top: var(--s-3); padding-top: var(--s-3); border-top: 1px solid var(--border); }
.dfp-manage { display: inline-flex; align-items: center; gap: 4px; padding: 0; font-size: var(--fs-12, 12px); border: none; background: none; color: var(--muted); cursor: pointer; }
.dfp-manage:hover { color: var(--accent); }
.dfp-manage svg { transform: rotate(-90deg); }

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
.dc-empty { display: flex; }
.dc-empty .empty-hint { margin: 0 auto; max-width: 480px; }

/* 分组 / Groups */
.dc-groups { display: flex; flex-direction: column; gap: var(--s-5); }
.dc-group-head { display: flex; align-items: center; gap: var(--s-2); width: 100%; padding: var(--s-2) 0; }
.dc-group-toggle { display: inline-flex; align-items: center; border: none; background: transparent; cursor: pointer; color: var(--muted); padding: 2px; }
.dc-chev { transition: transform 0.15s; color: var(--muted); flex-shrink: 0; transform: rotate(90deg); }
.dc-group-toggle[aria-expanded="false"] .dc-chev { transform: rotate(0deg); }
.dc-group-title { font-size: var(--fs-14); font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--fg); text-decoration: none; }
.dc-group-title:hover { color: var(--accent); text-decoration: underline; }
.dc-group-date { font-size: var(--fs-12, 12px); color: var(--subtle); flex-shrink: 0; }
.dc-group-count { margin-left: auto; font-size: var(--fs-12, 12px); color: var(--muted); flex-shrink: 0; }
.dc-flow { margin-top: var(--s-2); }

/* 闭档沉底折叠区：复用 flow-completed-toggle 基元 */
.dc-ineffective { margin-top: var(--s-3); padding-top: var(--s-3); border-top: 1px dashed var(--border); }
.dc-ineff-toggle { margin-bottom: var(--s-2); }

/* 议题视图（全局视角） / Topic (global) view */
/* 议题 = 容器分组：边框+淡底明确边界，议题间不再靠纯留白 */
.dc-topics { display: flex; flex-direction: column; gap: var(--s-4); }
.dc-topic-hint { font-size: var(--fs-12, 12px); color: var(--muted); margin: 0 0 var(--s-2); line-height: 1.5; }
.dc-topic { padding: var(--s-3) var(--s-4) var(--s-4); border: 1px solid var(--border); border-radius: var(--radius-md, 8px); background: var(--surface-1, transparent); }
.dc-topic-head { display: flex; align-items: center; gap: var(--s-2); width: 100%; padding: 0 0 var(--s-2); }
.dc-topic-title { font-size: var(--fs-14); font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--fg); }
.dc-topic-badge { flex-shrink: 0; font-size: var(--fs-11, 11px); color: var(--accent); background: var(--accent-soft); border-radius: 999px; padding: 1px 8px; white-space: nowrap; }
.dc-topic-conf { flex-shrink: 0; font-size: var(--fs-11, 11px); color: var(--subtle); white-space: nowrap; }
.dc-topic-kb { margin-left: auto; flex-shrink: 0; font-size: var(--fs-11, 11px); color: var(--muted); white-space: nowrap; }

/* 演变链：相对主卡次级的竖向时间线——只读出处，不与主卡平级 */
.dc-evo-list { position: relative; list-style: none; margin: var(--s-1) 0 0; padding: 0; }
.dc-evo-list::before { content: ''; position: absolute; left: 3px; top: 10px; bottom: 8px; width: 2px; border-radius: 1px; background: var(--border-strong); opacity: 0.7; }
.dc-evo-item { position: relative; padding: 0 0 var(--s-3) 20px; }
.dc-evo-item:last-child { padding-bottom: 2px; }
.dc-evo-dot { position: absolute; left: 0; top: 5px; width: 8px; height: 8px; border-radius: 50%; box-shadow: 0 0 0 2px var(--surface-1, var(--bg, #fff)); }
.dc-evo-entry { min-width: 0; }
.dc-evo-row { display: flex; align-items: center; gap: var(--s-2); }
.dc-evo-title { flex: 1; min-width: 0; color: var(--subtle); font-size: var(--fs-12, 12px); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dc-evo-status { flex-shrink: 0; font-size: 10px; line-height: 1; padding: 2px 7px; border-radius: 999px; white-space: nowrap; opacity: 0.85; }
.dc-evo-go { flex-shrink: 0; display: inline-flex; color: var(--muted); border-radius: var(--radius-sm); padding: 2px; opacity: 0.6; }
.dc-evo-go:hover { color: var(--accent); opacity: 1; }
.dc-evo-text { margin: 3px 0 0; font-size: var(--fs-12, 12px); line-height: 1.55; color: var(--muted); white-space: pre-wrap; word-break: break-word; }
.dc-evo-foot { display: flex; align-items: center; gap: var(--s-2); margin-top: 3px; }
.dc-evo-meta { min-width: 0; color: var(--muted); font-size: var(--fs-11, 11px); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dc-evo-owner { margin-left: auto; flex-shrink: 0; color: var(--muted); font-size: var(--fs-11, 11px); white-space: nowrap; }

/* 标记「已被替代」动作钮：默认与外链同级弱显，hover 才强调 */
.dc-evo-act { flex-shrink: 0; display: inline-flex; padding: 2px; border: none; background: transparent; color: var(--muted); border-radius: var(--radius-sm); cursor: pointer; opacity: 0.6; }
.dc-evo-act:hover:not(:disabled) { color: var(--accent); opacity: 1; background: var(--accent-soft); }
.dc-evo-act:disabled { opacity: 0.4; cursor: default; }

/* 已替代项：整体降权，明确「此条已闭档，看新决策」 */
.dc-evo-item.is-superseded .dc-evo-title { text-decoration: line-through; }
.dc-evo-item.is-superseded .dc-evo-text { opacity: 0.7; }
.dc-evo-item.is-superseded .dc-evo-dot { opacity: 0.6; }
.dc-evo-status.is-superseded { text-decoration: none; }
.dc-evo-replaced { display: flex; align-items: baseline; gap: 6px; margin-top: 3px; font-size: var(--fs-12, 12px); line-height: 1.5; }
.dc-evo-replaced-label { flex-shrink: 0; color: var(--muted); }
.dc-evo-replaced-link { min-width: 0; color: var(--accent); text-decoration: none; word-break: break-word; }
.dc-evo-replaced-link:hover { text-decoration: underline; }
.dc-evo-undo { flex-shrink: 0; margin-left: 2px; padding: 0; border: none; background: transparent; color: var(--muted); font-size: var(--fs-11, 11px); cursor: pointer; }
.dc-evo-undo:hover:not(:disabled) { color: var(--accent); text-decoration: underline; }
.dc-evo-undo:disabled { opacity: 0.4; cursor: default; }
</style>
