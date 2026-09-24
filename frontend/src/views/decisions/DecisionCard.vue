<template>
  <!-- 决策卡片：复用 DecisionNode 的样式基元（db-node/db-dot/db-title），不含行动项状态机逻辑
       Decision card: reuses DecisionNode style primitives without the action-item state machine -->
  <div class="db-node dc-card" :class="{ 'is-ineffective': decision.status !== 'active' }">
    <div class="db-row1">
      <span class="db-dot dc-dot" :class="'st-' + decision.status" :title="t('decisions.badge_' + decision.status)"></span>
      <span class="db-title dc-text" :title="displayText">{{ displayText }}</span>
      <!-- 状态徽标：待确认默认可见带徽标（REQ-DECISION-CENTER §11-2 裁决） -->
      <!-- Status badges: pending-confirmation is visible by default with a badge -->
      <span v-if="decision.pending_confirmation && decision.status === 'active'" class="dc-badge dc-badge-pending">{{ t('decisions.badge_pending') }}</span>
      <span v-if="decision.status !== 'active'" class="dc-badge" :class="'dc-badge-' + decision.status">{{ t('decisions.badge_' + decision.status) }}</span>
      <!-- 行内操作菜单 / Inline action menu -->
      <div class="dc-action-wrap" ref="menuWrapRef">
        <button class="dc-action-btn" :aria-expanded="menuOpen" aria-haspopup="menu" :title="t('decisions.action_more')" @click.stop="menuOpen = !menuOpen">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="5" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="12" cy="19" r="1.6"/></svg>
        </button>
        <div class="db-dropdown dc-menu" :class="{ 'is-open': menuOpen }">
          <button class="db-dd-item" :disabled="decision.status === 'superseded'" @click.stop="emit('supersede')">
            <span class="db-dd-dot dc-dot st-superseded"></span>{{ t('decisions.action_supersede') }}
          </button>
          <button class="db-dd-item" :disabled="decision.status === 'revoked'" @click.stop="emit('revoke')">
            <span class="db-dd-dot dc-dot st-revoked"></span>{{ t('decisions.action_revoke') }}
          </button>
        </div>
      </div>
    </div>

    <!-- 第二行：来源会议 + 日期 / Row 2: source meeting + date -->
    <div class="dc-meta">
      <template v-if="decision.task_deleted">
        <span class="dc-meta-deleted">{{ t('decisions.meeting_deleted') }}</span>
      </template>
      <template v-else>
        <button class="dc-meta-link" @click="gotoMeeting" :title="t('decisions.goto_meeting')">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          {{ decision.title || decision.task_id }}
        </button>
        <span v-if="decision.meeting_date" class="dc-meta-date">{{ decision.meeting_date }}</span>
        <span v-if="decision.kb_name" class="dc-meta-kb">{{ decision.kb_name }}</span>
      </template>
    </div>

    <!-- 取代关系：有效 → 可跳转链接；引用悬空（取代方会议被删）→ 降级文本，不白屏 -->
    <!-- Supersede link: jumpable when resolvable, degraded text when the ref is dangling -->
    <div v-if="decision.status === 'superseded' && decision.superseded_by" class="dc-superseded-by">
      <button v-if="superseder" class="dc-meta-link" @click="gotoSuperseder">
        {{ t('decisions.superseded_by', { text: truncate(superseder.text) }) }}
      </button>
      <span v-else class="dc-meta-deleted">{{ t('decisions.superseded_broken') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import type { AggregatedDecision } from '@/api/decisions'
import { stripDecisionEmphasis } from '@/utils/decisionText'

const { t } = useI18n()
const router = useRouter()

const props = defineProps<{
  decision: AggregatedDecision
  /** 全量决策引用池（不含筛选），用于解析 superseded_by 指向的新决策文本 */
  /** Unfiltered decision pool used to resolve superseded_by into display text */
  pool: AggregatedDecision[]
}>()

const emit = defineEmits<{
  (e: 'supersede'): void
  (e: 'revoke'): void
}>()

const superseder = computed(() => {
  const ref = props.decision.superseded_by
  if (!ref) return null
  return props.pool.find(d => d.id === ref.decision_id && d.task_id === ref.task_id) ?? null
})

/** 展示文本：剥除成对强调符号（RF-F1）；dq 跳转仍用原始 text 保证纪要正文命中 */
const displayText = computed(() => stripDecisionEmphasis(props.decision.text))

function truncate(text: string): string {
  const plain = stripDecisionEmphasis(text)
  return plain.length > 24 ? plain.slice(0, 24) + '…' : plain
}

/** 跳转来源会议纪要页，dq 携带决策文本供锚点定位 / Jump to minutes tab with an anchor query */
function gotoMeeting() {
  if (props.decision.task_deleted) return
  router.push({
    name: 'generating',
    params: { taskId: props.decision.task_id },
    query: { tab: 'summary', dq: props.decision.text },
  })
}

function gotoSuperseder() {
  const s = superseder.value
  if (!s || s.task_deleted) return
  router.push({ name: 'generating', params: { taskId: s.task_id }, query: { tab: 'summary', dq: s.text } })
}

// ── 行内菜单：点击外部/ESC 关闭 / Inline menu: close on outside-click / ESC ──
const menuOpen = ref(false)
const menuWrapRef = ref<HTMLElement | null>(null)
function onDocClick(e: MouseEvent) {
  if (menuWrapRef.value && !menuWrapRef.value.contains(e.target as Node)) menuOpen.value = false
}
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') menuOpen.value = false
}
onMounted(() => {
  document.addEventListener('click', onDocClick, true)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick, true)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
/* 决策中心卡片：仅补充基元不具备的徽标/元信息样式 / Card extras: badges + meta rows only */
.dc-card { display: block; }
.dc-text { white-space: normal; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; text-overflow: ellipsis; }
.dc-card.is-ineffective { opacity: 0.55; }
.dc-card.is-ineffective .dc-text { text-decoration: line-through; color: var(--subtle); }

/* 状态点颜色沿用决策流基元色（--st-*）/ Dots reuse the decision-flow token palette */
.dc-dot.st-active { background: var(--st-done); }
.dc-dot.st-superseded { background: var(--st-decide); }
.dc-dot.st-revoked { background: var(--error); }

.dc-badge {
  flex-shrink: 0; font-size: var(--fs-11, 11px); line-height: 1; padding: 4px 7px;
  border-radius: 999px; font-weight: 500; white-space: nowrap;
}
.dc-badge-pending { background: oklch(0.94 0.04 70); color: var(--st-confirm); }
.dc-badge-superseded { background: var(--surface-2); color: var(--muted); border: 1px solid var(--border); }
.dc-badge-revoked { background: oklch(0.94 0.03 25); color: var(--error); }

.dc-action-wrap { position: relative; display: inline-flex; flex-shrink: 0; }
.dc-action-btn {
  display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px;
  border: none; background: transparent; color: var(--muted); border-radius: var(--radius-sm); cursor: pointer;
  opacity: 0; transition: opacity 0.12s, background 0.12s;
}
.dc-card:hover .dc-action-btn, .dc-action-btn:focus-visible, .dc-action-btn[aria-expanded="true"] { opacity: 1; }
.dc-action-btn:hover { background: var(--surface-2); color: var(--fg); }
.dc-menu { right: 0; left: auto; min-width: 168px; }
.dc-menu .db-dd-item:disabled { opacity: 0.4; cursor: not-allowed; }
.dc-menu .db-dd-item:disabled:hover { background: transparent; }

.dc-meta { display: flex; align-items: center; gap: var(--s-2); margin-top: 6px; font-size: var(--fs-12, 12px); color: var(--muted); flex-wrap: wrap; }
.dc-meta-link {
  display: inline-flex; align-items: center; gap: 4px; border: none; background: transparent; padding: 0;
  color: var(--accent); font-size: inherit; cursor: pointer; min-width: 0;
}
.dc-meta-link:hover { text-decoration: underline; }
.dc-meta-date, .dc-meta-kb { color: var(--subtle); }
.dc-meta-kb { padding: 1px 6px; border: 1px solid var(--border); border-radius: var(--radius-sm); }
.dc-meta-deleted { color: var(--subtle); font-style: italic; }
.dc-superseded-by { margin-top: var(--s-1); font-size: var(--fs-12, 12px); }
</style>
