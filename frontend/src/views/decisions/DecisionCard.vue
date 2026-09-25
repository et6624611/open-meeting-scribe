<template>
  <!-- 决策卡片：复用 DecisionNode 的样式基元（db-node/db-dot/db-title），不含行动项状态机逻辑
       Decision card: reuses DecisionNode style primitives without the action-item state machine -->
  <div class="db-node dc-card" :class="{ 'is-ineffective': decision.status !== 'active' }">
    <div class="db-row1">
      <span class="db-dot dc-dot" :class="'st-' + decision.status" :title="t('decisions.badge_' + decision.status)"></span>
      <!-- 行内编辑态（F3 + DC-R2-b）：标题 / 内容 / 执行人 三字段就地编辑 -->
      <div v-if="editing" class="dc-edit">
        <input
          ref="editTitleRef"
          v-model.trim="editTitle"
          class="dc-edit-area dc-edit-input"
          type="text"
          maxlength="200"
          :aria-label="t('decisions.add_title_label')"
          :placeholder="t('decisions.add_title_placeholder')"
        />
        <textarea
          ref="editAreaRef"
          v-model="editText"
          class="dc-edit-area"
          rows="3"
          maxlength="2000"
          :aria-label="t('decisions.action_edit')"
        ></textarea>
        <OwnerSelectCombobox v-model="editOwner" :label="t('decisions.add_owner_label')" />
        <div class="dc-edit-actions">
          <button type="button" class="dc-edit-btn" @click="cancelEdit">{{ t('decisions.add_cancel') }}</button>
          <button type="button" class="dc-edit-btn is-primary" :disabled="!editText.trim()" @click="saveEdit">{{ t('decisions.add_submit') }}</button>
        </div>
      </div>
      <template v-else>
        <!-- 行首：有三要素标题时现标题，否则降级为内容首行（存量/auto 形态） -->
        <span class="db-title dc-text" :class="{ 'is-title': hasTitle }" :title="rowHead">{{ rowHead }}</span>
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
            <template v-if="!confirmDelete">
              <button class="db-dd-item" @click.stop="startEdit">
                <svg class="db-dd-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                {{ t('decisions.action_edit') }}
              </button>
              <button class="db-dd-item is-danger" @click.stop="confirmDelete = true">
                <svg class="db-dd-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                {{ t('decisions.action_delete') }}
              </button>
              <div class="dc-menu-sep"></div>
              <button class="db-dd-item" :disabled="decision.status === 'superseded'" @click.stop="emit('supersede')">
                <span class="db-dd-dot dc-dot st-superseded"></span>{{ t('decisions.action_supersede') }}
              </button>
              <button class="db-dd-item" :disabled="decision.status === 'revoked'" @click.stop="emit('revoke')">
                <span class="db-dd-dot dc-dot st-revoked"></span>{{ t('decisions.action_revoke') }}
              </button>
            </template>
            <!-- 删除二次确认（不可恢复操作不做静默删除） / Delete needs an in-menu confirm -->
            <div v-else class="dc-del-confirm" @click.stop>
              <p>{{ t('decisions.delete_confirm_desc') }}</p>
              <div class="dc-del-actions">
                <button type="button" class="dc-edit-btn" @click.stop="confirmDelete = false">{{ t('decisions.add_cancel') }}</button>
                <button type="button" class="dc-edit-btn is-danger-solid" @click.stop="remove">{{ t('decisions.delete_confirm_btn') }}</button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 内容行：仅当存在独立标题时补现正文，无标题条目仍保持单行式（不出现空标题堆叠） -->
    <div v-if="!editing && hasTitle" class="dc-content">{{ displayText }}</div>

    <!-- 第二行（F1 去冗余）：组头已含会议标题与日期，卡片只留跳转纪要图标 + 知识库徽标 + 执行人 -->
    <!-- Row 2 (F1 de-dup): group head already carries title+date; keep jump icon + KB badge + owner -->
    <div v-if="!editing" class="dc-meta">
      <template v-if="decision.task_deleted">
        <span class="dc-meta-deleted">{{ t('decisions.meeting_deleted') }}</span>
      </template>
      <template v-else>
        <button class="dc-meta-jump" @click="gotoMeeting" :title="t('decisions.goto_meeting')" :aria-label="t('decisions.goto_meeting')">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        </button>
        <span v-if="decision.kb_name" class="dc-meta-kb">{{ decision.kb_name }}</span>
      </template>
      <!-- 执行人（D4）：未指派不占位，避免卡片出现「执行人：空」噪声 -->
      <span v-if="decision.owner_name" class="dc-meta-owner" :title="t('decisions.owner_tip', { name: decision.owner_name })">
        <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        {{ decision.owner_name }}
      </span>
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
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import type { AggregatedDecision, DecisionPatchPayload, OwnerValue } from '@/api/decisions'
import { stripDecisionEmphasis } from '@/utils/decisionText'
import OwnerSelectCombobox from './OwnerSelectCombobox.vue'

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
  (e: 'edit-save', patch: DecisionPatchPayload): void
  (e: 'remove'): void
}>()

const superseder = computed(() => {
  const ref = props.decision.superseded_by
  if (!ref) return null
  return props.pool.find(d => d.id === ref.decision_id && d.task_id === ref.task_id) ?? null
})

/** 展示文本（内容）：剥除成对强调符号（RF-F1）；dq 跳转仍用原始 text 保证纪要正文命中 */
const displayText = computed(() => stripDecisionEmphasis(props.decision.text))
/** 三要素标题（D5）：有则行首现标题，无则行首降级为内容（存量/auto 不堆空行） */
const hasTitle = computed(() => !!stripDecisionEmphasis(props.decision.title || '').trim())
const rowHead = computed(() => (hasTitle.value ? stripDecisionEmphasis(props.decision.title).trim() : displayText.value))

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

// ── F3 行内编辑与删除（DC-R2-a）/ Inline edit & delete ──
// DC-R2-b：编辑面从单文本升级为标题 + 内容 + 执行人三字段
const editing = ref(false)
const editTitle = ref('')
const editText = ref('')
const editOwner = ref<OwnerValue>(null)
const editTitleRef = ref<HTMLInputElement | null>(null)
const editAreaRef = ref<HTMLTextAreaElement | null>(null)
const confirmDelete = ref(false)

function startEdit() {
  menuOpen.value = false
  editTitle.value = props.decision.title || ''
  editText.value = props.decision.text
  editOwner.value = props.decision.owner_id
    ? { id: props.decision.owner_id, name: props.decision.owner_name || '' }
    : (props.decision.owner_name ? { id: '', name: props.decision.owner_name } : null)
  editing.value = true
  nextTick(() => editTitleRef.value?.focus())
}
function cancelEdit() {
  editing.value = false
}
function saveEdit() {
  const text = editText.value.trim()
  if (!text) return
  editing.value = false
  // 执行人清空：下发空串（后端语义 = 撤销指派），与「未传不改变」区分
  emit('edit-save', {
    title: editTitle.value.trim(),
    text,
    owner_id: editOwner.value?.id ?? '',
    owner_name: editOwner.value?.name ?? '',
  })
}
function remove() {
  menuOpen.value = false
  confirmDelete.value = false
  emit('remove')
}
// 菜单收起即复位删除确认，避免下次打开停在危险态
watch(menuOpen, (open) => { if (!open) confirmDelete.value = false })

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
/* 三要素标题行：加粗一级信息（与内容行拉开层次） */
.db-title.dc-text.is-title { font-weight: 600; -webkit-line-clamp: 1; }
.dc-content {
  margin-top: 3px; font-size: var(--fs-13, 13px); line-height: 1.55; color: var(--fg);
  white-space: normal; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; text-overflow: ellipsis;
}
.dc-card.is-ineffective { opacity: 0.55; }
.dc-card.is-ineffective .dc-text, .dc-card.is-ineffective .dc-content { text-decoration: line-through; color: var(--subtle); }

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
.dc-menu .db-dd-item.is-danger { color: var(--error); }
.dc-menu .db-dd-item.is-danger:hover { background: oklch(0.94 0.03 25); }
.db-dd-icon { flex-shrink: 0; color: var(--muted); }
.db-dd-item.is-danger .db-dd-icon { color: var(--error); }
.dc-menu-sep { height: 1px; margin: 4px 0; background: var(--border); }
.dc-del-confirm { padding: var(--s-2) var(--s-3); }
.dc-del-confirm p { margin: 0 0 var(--s-2); font-size: var(--fs-12, 12px); color: var(--error); line-height: 1.5; }
.dc-del-actions { display: flex; justify-content: flex-end; gap: 6px; }

/* F3 行内编辑 / Inline editor */
.dc-edit { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.dc-edit-input { font-family: inherit; }
.dc-edit-area {
  width: 100%; box-sizing: border-box; padding: 6px 8px; font-size: var(--fs-13, 13px); line-height: 1.5;
  font-family: inherit; border: 1px solid var(--accent); border-radius: var(--radius-sm);
  background: var(--surface-1, transparent); color: var(--fg); resize: vertical;
}
.dc-edit-area:focus { outline: none; }
.dc-edit-actions { display: flex; justify-content: flex-end; gap: 6px; }
.dc-edit-btn { padding: 3px 10px; font-size: var(--fs-12, 12px); border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--muted); cursor: pointer; }
.dc-edit-btn:hover { color: var(--fg); border-color: var(--border-strong); }
.dc-edit-btn.is-primary { border: none; background: var(--accent); color: var(--accent-fg); font-weight: 500; }
.dc-edit-btn.is-primary:disabled { opacity: 0.45; cursor: not-allowed; }
.dc-edit-btn.is-danger-solid { border: none; background: var(--error); color: #fff; font-weight: 500; }

.dc-meta { display: flex; align-items: center; gap: var(--s-2); margin-top: 6px; font-size: var(--fs-12, 12px); color: var(--muted); flex-wrap: wrap; }
.dc-meta-jump {
  display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px;
  border: none; background: transparent; color: var(--muted); border-radius: var(--radius-sm); cursor: pointer;
  opacity: 0.7; transition: opacity 0.12s, background 0.12s, color 0.12s;
}
.dc-card:hover .dc-meta-jump, .dc-meta-jump:focus-visible { opacity: 1; }
.dc-meta-jump:hover { background: var(--surface-2); color: var(--accent); }
.dc-meta-link {
  display: inline-flex; align-items: center; gap: 4px; border: none; background: transparent; padding: 0;
  color: var(--accent); font-size: inherit; cursor: pointer; min-width: 0;
}
.dc-meta-link:hover { text-decoration: underline; }
.dc-meta-kb { padding: 1px 6px; border: 1px solid var(--border); border-radius: var(--radius-sm); }
.dc-meta-owner {
  display: inline-flex; align-items: center; gap: 4px; padding: 1px 6px;
  border-radius: 999px; background: var(--surface-2); color: var(--muted); white-space: nowrap;
}
.dc-meta-deleted { color: var(--subtle); font-style: italic; }
.dc-superseded-by { margin-top: var(--s-1); font-size: var(--fs-12, 12px); }
</style>
