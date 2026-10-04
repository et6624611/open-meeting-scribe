<template>
  <!-- 决策面板：唯一的决策对象——决策流（DC-UNIFY-01，2026-09-27 项目方裁决）
       Decisions panel: the decision flow is the one and only decision object -->
  <div class="gen-panel" :class="{ hidden: !visible }">
    <!-- 来源横幅：从决策中心演变链跳入时标识上下文（可关闭） / Context banner from the center -->
    <div v-if="fromEvolution && anchorTodoId && !bannerDismissed" class="db-evo-banner">
      <svg class="db-evo-banner-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
      <span class="db-evo-banner-text">{{ t('decisions.meeting_evo_from_banner', { title: anchorTitle }) }}</span>
      <RouterLink class="db-evo-banner-link" :to="anchorTopicKey ? topicCenterLink(anchorTopicKey) : { name: 'decisions' }">
        {{ t('decisions.meeting_evo_banner_goto_center') }}
      </RouterLink>
      <button type="button" class="db-evo-banner-x" :title="t('decisions.meeting_evo_banner_dismiss')" :aria-label="t('decisions.meeting_evo_banner_dismiss')" @click="bannerDismissed = true">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>

    <!-- 顶部：进度摘要 + 决策中心入口 + 添加 / Top: progress summary + center link + add -->
    <div class="db-toolbar" v-if="todos.length">
      <div class="db-toolbar-left">
        <span class="db-summary" v-html="summaryText"></span>
      </div>
      <RouterLink class="db-center-link" :to="{ name: 'decisions' }">
        {{ t('generating.decisions_panel_link') }}
        <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
      </RouterLink>
      <button class="db-add-btn" @click="emit('add')">+ {{ t('generating.todos.add_decision') }}</button>
    </div>

    <!-- 决策卡片列表 / Decision card list -->
    <div class="db-flow" v-if="mainNodes.length">
      <div
        v-for="todo in mainNodes"
        :key="todo.id"
        class="db-node-cell"
        :class="{ 'is-anchor': anchorTodoId === todo.id }"
      >
        <EvolutionBadge v-if="evolution[todo.id]" :info="evolution[todo.id]" />
        <DecisionNode
          :todo="todo"
          @select-status="(s) => emit('status-change', todo, s)"
          @select-owner="(o) => emit('update', todo, { owner_type: o })"
          @commit-content="(c) => emit('update', todo, { why: c })"
          @patch="(p) => emit('update', todo, p)"
          @delete="emit('delete', todo)"
        />
      </div>
    </div>

    <!-- 已完成分组（默认折叠） / Completed group (collapsed by default) -->
    <div class="db-completed" v-if="completedNodes.length">
      <button class="flow-completed-toggle" @click="showCompleted = !showCompleted">
        <svg class="chev" :class="{ open: showCompleted }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
        {{ t('generating.todos.completed_group', { count: completedNodes.length }) }}
      </button>
      <div class="db-flow" v-if="showCompleted">
        <div
          v-for="todo in completedNodes"
          :key="todo.id"
          class="db-node-cell"
          :class="{ 'is-anchor': anchorTodoId === todo.id }"
        >
          <EvolutionBadge v-if="evolution[todo.id]" :info="evolution[todo.id]" />
          <DecisionNode
            :todo="todo"
            @select-status="(s) => emit('status-change', todo, s)"
            @select-owner="(o) => emit('update', todo, { owner_type: o })"
            @commit-content="(c) => emit('update', todo, { why: c })"
            @patch="(p) => emit('update', todo, p)"
            @delete="emit('delete', todo)"
          />
        </div>
      </div>
    </div>

    <!-- 空状态 / Empty state -->
    <div class="flow-empty" v-if="!todos.length">
      <div class="flow-empty-title">{{ t('generating.todos.flow_empty') }}</div>
      <div class="flow-empty-hint">{{ t('generating.todos.flow_empty_hint') }}</div>
    </div>
    <div class="flow-empty" v-else-if="!mainNodes.length && !completedNodes.length">
      {{ t('generating.todos.empty') }}
    </div>

    <!-- 添加决策：与决策中心手动补录共用同一弹层表单（DC-UNIFY-01） / Add decision: same dialog as the center's manual entry -->
    <div class="todos-add-bar">
      <button class="todos-add-btn" @click="emit('add')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        {{ t('generating.todos.add_decision') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, h, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import type { TodoItem } from '@/api/types'
import type { TodoPatch } from '@/api/notes'
import { fetchTaskEvolution, type NodeEvolution } from '@/api/decisions'
import { useDecisionStatuses } from '@/composables/useDecisionStatuses'
import { meetingNodeLink, topicCenterLink } from '@/views/decisionEvolutionNav'
import { partitionNodes, statusOf } from './decisionFlowLogic'
import DecisionNode from './DecisionNode.vue'

const { t, locale } = useI18n()

const props = defineProps<{
  visible: boolean
  taskId: string
  todos: TodoItem[]
  /** 路由锚点：?todo=<id> 跳入时定位高亮的节点 */
  anchorTodoId?: string
  /** 来源标识：?from=evolution（控制顶部横幅） */
  fromEvolution?: boolean
}>()

const emit = defineEmits<{
  (e: 'delete', todo: TodoItem): void
  (e: 'update', todo: TodoItem, patch: TodoPatch): void
  (e: 'status-change', todo: TodoItem, status: string): void
  (e: 'add'): void
}>()

// ── 状态字典：分组与摘要都由它驱动（闭档 = 完成类，沉底折叠） ──
const { statuses, load, labelOf, isClosing } = useDecisionStatuses()
onMounted(() => { void load() })

// ── 节点分组 / Node grouping（逻辑见 decisionFlowLogic.ts） ──
const grouped = computed(() => partitionNodes(props.todos, isClosing))
const mainNodes = computed(() => grouped.value.active)
const completedNodes = computed(() => grouped.value.completed)

const showCompleted = ref(false)

// ── 跨会议演变归属（角标数据源；失败静默降级，不阻塞面板） ──
const evolution = ref<Record<string, NodeEvolution>>({})
async function loadEvolution() {
  try { evolution.value = await fetchTaskEvolution(props.taskId) } catch { /* 无角标降级 */ }
}
onMounted(loadEvolution)

// 内联角标组件（仅本面板使用）：main=本节点即最新推进；history=新讨论在别处
const EvolutionBadge = (nodeProps: { info: NodeEvolution }) => h(
  'div',
  { class: `db-evo-badge${nodeProps.info.role === 'main' ? ' is-main' : ' is-history'}` },
  [
    h('svg', { class: 'db-evo-badge-ico', viewBox: '0 0 24 24', width: 11, height: 11, fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, [
      h('circle', { cx: '5', cy: '12', r: '2' }),
      h('circle', { cx: '19', cy: '5', r: '2' }),
      h('circle', { cx: '19', cy: '19', r: '2' }),
      h('path', { d: 'M6.8 11l10.4-4.8M6.8 13l10.4 4.8' }),
    ]),
    nodeProps.info.role === 'main'
      ? h(RouterLink, { class: 'db-evo-badge-link', to: topicCenterLink(nodeProps.info.topic_key) },
          () => t('decisions.meeting_evo_badge_main', { count: nodeProps.info.meeting_count }))
      : h('span', { class: 'db-evo-badge-grp' }, [
          t('decisions.meeting_evo_badge_history') + ' ',
          h(RouterLink, { class: 'db-evo-badge-link', to: meetingNodeLink(nodeProps.info.latest.task_id, nodeProps.info.latest.todo_id) },
            () => t('decisions.meeting_evo_latest_in', { meeting: nodeProps.info.latest.meeting_title || '' })),
          ' · ',
          h(RouterLink, { class: 'db-evo-badge-link', to: topicCenterLink(nodeProps.info.topic_key) },
            () => t('decisions.meeting_evo_view_topic')),
        ]),
  ],
)

// ── 来源横幅 / Anchor banner ──
const bannerDismissed = ref(false)
const anchorNode = computed(() => props.todos.find(x => x.id === props.anchorTodoId))
const anchorTitle = computed(() => {
  const n = anchorNode.value
  return n ? (n.title || n.text || '') : ''
})
const anchorTopicKey = computed(() =>
  props.anchorTodoId ? evolution.value[props.anchorTodoId]?.topic_key : undefined)

// ── 节点锚点定位：闭档组随字典加载/锚点变化响应式展开 → 滚动 → 高亮闪烁 ──
// 不能只在锚点 watcher 里判定：挂载瞬间字典可能尚未返回，闭档节点会被误分到开放组
const anchorInCompleted = computed(() =>
  Boolean(props.anchorTodoId && completedNodes.value.some(x => x.id === props.anchorTodoId)))
watch(anchorInCompleted, (inCompleted) => {
  // 仅 false→true 时展开，不与用户随后的手动折叠对抗
  if (inCompleted) showCompleted.value = true
}, { immediate: true })

watch(() => props.anchorTodoId, (id) => {
  if (!id) return
  bannerDismissed.value = false
  const tryLocate = (attempts: number) => {
    const el = document.querySelector(`.db-node[data-todo-id="${CSS.escape(id)}"]`) as HTMLElement | null
    if (!el) {
      if (attempts < 20) window.setTimeout(() => tryLocate(attempts + 1), 250)
      return
    }
    void nextTick(() => {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el.classList.remove('evo-anchor-flash')
      void el.offsetWidth
      el.classList.add('evo-anchor-flash')
      window.setTimeout(() => el.classList.remove('evo-anchor-flash'), 2400)
    })
  }
  // 数据/演变归属可能尚未返回，首轮延迟起轮询（同时等闭档组展开渲染）
  window.setTimeout(() => tryLocate(0), 120)
}, { immediate: true })

// ── 进度摘要：按字典顺序列出有量的非闭档态 + 总数 / Progress summary ──
const summaryText = computed(() => {
  const counts = new Map<string, number>()
  for (const todo of props.todos) {
    const sid = statusOf(todo)
    counts.set(sid, (counts.get(sid) || 0) + 1)
  }
  const parts = statuses.value
    .filter(s => !s.closing && counts.get(s.id))
    .map(s => `<strong>${counts.get(s.id)}</strong> ${labelOf(s.id, String(locale.value || 'zh-CN'))}`)
  // 字典外的历史状态（用户删过项）也要被数进去，避免总数与分项对不上
  const covered = new Set(statuses.value.map(s => s.id))
  let stray = 0
  for (const [sid, n] of counts) if (!covered.has(sid) && !isClosing(sid)) stray += n
  if (stray) parts.push(`<strong>${stray}</strong> ${t('generating.todos.status_other')}`)
  const total = t('generating.todos.total_count', { count: props.todos.length })
  return parts.length ? `${parts.join(' · ')} · ${total}` : total
})
</script>

<style scoped>
/* 决策中心入口：与添加按钮同处工具栏右侧，弱化为文字链接 */
.db-center-link {
  display: inline-flex; align-items: center; gap: 3px; flex-shrink: 0;
  font-size: var(--fs-12); color: var(--muted); text-decoration: none; white-space: nowrap;
}
.db-center-link:hover { color: var(--accent); text-decoration: underline; }

/* 演变归属角标：节点上方一条细信息行 */
.db-evo-badge {
  display: flex; align-items: center; gap: 6px; margin: 0 0 4px 2px;
  font-size: var(--fs-11, 11px); color: var(--muted); line-height: 1.4;
}
.db-evo-badge-ico { flex-shrink: 0; color: var(--accent); opacity: 0.8; }
.db-evo-badge-grp { min-width: 0; display: inline-flex; flex-wrap: wrap; align-items: center; gap: 2px; }
.db-evo-badge-link { color: var(--accent); text-decoration: none; }
.db-evo-badge-link:hover { text-decoration: underline; }

/* 锚点高亮：outline 闪烁（不动布局） */
.db-node-cell :deep(.db-node.evo-anchor-flash) {
  animation: evo-anchor-flash 0.8s ease-in-out 3;
}
@keyframes evo-anchor-flash {
  0%, 100% { box-shadow: 0 0 0 0 transparent; }
  50% { box-shadow: 0 0 0 3px var(--accent-soft); border-color: var(--accent); }
}

/* 来源横幅 */
.db-evo-banner {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: var(--s-3); padding: 7px 12px;
  border: 1px solid var(--accent); border-radius: var(--radius-sm);
  background: var(--accent-soft); font-size: var(--fs-12, 12px); color: var(--fg);
}
.db-evo-banner-icon { flex-shrink: 0; color: var(--accent); }
.db-evo-banner-text { min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.db-evo-banner-link { flex-shrink: 0; color: var(--accent); text-decoration: none; font-weight: 500; white-space: nowrap; }
.db-evo-banner-link:hover { text-decoration: underline; }
.db-evo-banner-x {
  flex-shrink: 0; display: inline-flex; padding: 2px; border: none; background: transparent;
  color: var(--muted); border-radius: var(--radius-sm); cursor: pointer;
}
.db-evo-banner-x:hover { color: var(--fg); background: var(--surface-2); }
</style>
