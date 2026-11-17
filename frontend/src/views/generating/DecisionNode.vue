<template>
  <!-- 决策流卡片（唯一决策对象的交互载体）/ Decision-flow card: the one and only decision object -->
  <div class="db-node" :data-decision-id="decision.id" :class="{ 'is-done': closing }" :style="statusVarStyle">
    <!-- 第一行：状态点 + 标题（状态在下方平铺；等待方收进「等待中」父芯片的 caret 弹层） -->
    <div class="db-row1">
      <span class="db-dot"></span>
      <button
        type="button"
        class="db-title"
        v-if="!editing"
        :title="fullText"
        @click="startEdit"
      >{{ displayTitle }}</button>
      <span class="db-title-spacer" v-else></span>
      <!-- 待确认提案徽标：与已定结论共用 to_decide 态，靠 pending_confirmation 区分 -->
      <span v-if="!editing && decision.pending_confirmation" class="db-pending-badge">{{ t('generating.decisions.pending_badge') }}</span>
    </div>
    <!-- 平铺状态行；「等待中」为父芯片（方案 B）：主体=选中状态，caret=等待方子级入口 -->
    <div class="db-tiles-row" v-if="!editing">
      <div class="db-tile-group" role="radiogroup" :aria-label="t('decisions.add_status_label')">
        <template v-for="s in statusOptions" :key="s.id">
          <!-- 等待中父芯片：回显「等待中 · {等待方}」，caret 弹层选等待方；非等待中态即普通芯片 -->
          <span
            v-if="s.id === WAITING_STATUS_ID"
            class="db-parent"
            :class="{ 'is-active': isWaiting, 'has-child': isWaiting }"
          >
            <button
              type="button"
              class="db-parent-main"
              role="radio"
              :aria-checked="isWaiting"
              @click.stop="onSelectStatus(s.id)"
            >
              <span class="db-tile-dot" :style="{ background: s.color }"></span>
              {{ labelOf(s.id, locale) }}
            </button>
            <span class="db-parent-echo"><span class="sep">·</span><span>{{ ownerEchoLabel }}</span></span>
            <button
              :ref="setOwnerCaretRef"
              type="button"
              class="db-caret"
              v-bind="ownerTriggerAttrs"
              :title="t('generating.decisions.owner_caret_label')"
              :aria-label="t('generating.decisions.owner_caret_label')"
              @click.stop="toggleOwnerMenu"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <div
              :ref="setOwnerMenuRef"
              class="db-menu db-owner-menu"
              v-bind="ownerMenuAttrs"
              :class="{ 'is-open': ownerMenuVisible }"
            >
              <div class="db-owner-menu-head">{{ t('generating.decisions.owner_menu_head') }}</div>
              <button
                v-for="o in ownerOptions"
                :key="o"
                type="button"
                class="db-menu-item db-owner-item"
                role="menuitem"
                :aria-checked="o === ownerType"
                @click.stop="onPickOwner(o)"
              >{{ t('generating.decisions.owner_waiting_' + o) }}<span v-if="o === ownerType" class="db-owner-check">✓</span></button>
            </div>
          </span>
          <button
            v-else
            type="button"
            class="db-tile"
            :class="{ 'is-active': s.id === status }"
            role="radio"
            :aria-checked="s.id === status"
            @click.stop="onSelectStatus(s.id)"
          >
            <span class="db-tile-dot" :style="{ background: s.color }"></span>
            {{ labelOf(s.id, locale) }}
          </button>
        </template>
      </div>
    </div>

    <!-- ⋯ 菜单进入的行内编辑态：编辑「标题 + 主文本」；正文(why)仍由下方常驻 textarea 维护 -->
    <div class="db-edit" v-if="editing" @focusout="onEditFocusOut">
      <label class="db-edit-field">
        <span class="db-edit-label">{{ t('generating.decisions.edit_title_label') }}</span>
        <textarea
          ref="editTitleRef"
          class="db-edit-input"
          rows="1"
          maxlength="200"
          v-model="editTitle"
          :placeholder="t('generating.decisions.edit_title_placeholder')"
          @input="autoGrowTitle"
          @keydown.meta.enter.prevent="saveEdit"
          @keydown.ctrl.enter.prevent="saveEdit"
        ></textarea>
      </label>
      <label class="db-edit-field">
        <span class="db-edit-label">{{ t('generating.decisions.edit_content_label') }}</span>
        <textarea
          ref="editAreaRef"
          class="db-edit-area"
          v-model="editText"
          rows="3"
          :placeholder="t('generating.decisions.edit_content_placeholder')"
          @input="onDateShortcut"
          @keydown="onEditKeydown"
          @blur="editMenu.onBlur"
        ></textarea>
        <SlashDateMenu
          :open="editMenuOpen" :items="editMenuItems" :active-index="editMenuActive" :pos="editMenuPos"
          @select="editMenu.select" @hover="editMenu.setActive"
        />
      </label>
    </div>

    <!-- 第二行：Markdown textarea / Row 2: Markdown textarea -->
    <div class="db-content" v-if="!editing">
      <textarea
        ref="contentRef"
        class="db-card-textarea"
        :value="content"
        :placeholder="t('generating.decisions.content_placeholder')"
        rows="2"
        spellcheck="false"
        @input="onContentInput"
        @keydown="contentOnKeydown"
        @blur="onContentBlur"
      ></textarea>
      <SlashDateMenu
        :open="contentMenuOpen" :items="contentMenuItems" :active-index="contentMenuActive" :pos="contentMenuPos"
        @select="contentMenu.select" @hover="contentMenu.setActive"
      />
    </div>

    <!-- 备查层证据注行：内联注已从正文剥离为 evidence，展示层在此还原（只读） -->
    <div class="db-evidence" v-if="!editing && decision.evidence?.text">
      {{ t('generating.decisions.evidence_prefix') }}{{ decision.evidence.text }}
    </div>

    <!-- 底部：时间足迹 + 操作（时间与删除钮同为 hover 显隐） / Footer: timestamps + actions -->
    <div class="db-footer">
      <span class="db-meta" v-if="!editing && timeMeta">{{ timeMeta }}</span>
      <span class="db-footer-spacer"></span>
      <button class="db-delete-btn" :title="t('generating.decisions.delete')" @click="emit('delete')" :aria-label="t('generating.decisions.delete')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, onMounted, onBeforeUnmount, type ComponentPublicInstance } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DecisionItem, OwnerType } from '@/api/types'
import type { DecisionPatch } from '@/api/notes'
import { useDecisionStatuses } from '@/composables/useDecisionStatuses'
import { useEscClose } from '@/composables/useEscClose'
import { usePopMenu } from '@/composables/usePopMenu'
import { useSlashDateMenu } from '@/composables/useSlashDateMenu'
import { stripDecisionEmphasis } from '@/utils/decisionText'
import { handleDateShortcut } from '@/utils/dateShortcuts'
import SlashDateMenu from '@/components/SlashDateMenu.vue'

const { t, locale } = useI18n()

const props = defineProps<{
  decision: DecisionItem
}>()

const emit = defineEmits<{
  (e: 'select-status', status: string): void
  (e: 'select-owner', owner: OwnerType): void
  (e: 'commit-content', content: string): void
  (e: 'patch', patch: DecisionPatch): void
  (e: 'delete'): void
}>()

// ── 状态字典（选项 / 名称 / 颜色 / 闭档位全部配置驱动） ──
const { statuses, load, labelOf, colorOf, isClosing } = useDecisionStatuses()
void load()

const ownerOptions: OwnerType[] = ['self', 'agent', 'colleague', 'enterprise']
const statusOptions = computed(() => statuses.value)

// 状态：显式 status 优先，缺省由旧 done 布尔推导（历史 task JSON 兼容）
const status = computed(() => props.decision.status || (props.decision.done ? 'done' : 'in_progress'))
const closing = computed(() => isClosing(status.value) || status.value === 'done')
const ownerType = computed<OwnerType>(() => props.decision.owner_type || 'self')

// 状态色以 CSS 变量注入卡片，色点/徽标共用一个来源（不再写死 st-* 类名）
const statusVarStyle = computed(() => ({
  '--db-status-color': colorOf(status.value),
  '--db-status-soft': `color-mix(in oklch, ${colorOf(status.value)} 14%, transparent)`,
}))

// 标题 + 正文双要素：有 title 时标题占第一行
// DC-UI-02：标题下方的灰色摘要行已移除——它与下方正文重复冲突
// 但 why 为空时 text 是唯一内容，改为落到正文位置展示，不丢信息
// RF-F1：auto 节点文本携带纪要里的成对 markdown 强调符号，仅展示层剥除，数据不回改
const strip = stripDecisionEmphasis
const hasTitle = computed(() => Boolean(props.decision.title && props.decision.text && props.decision.text !== props.decision.why))

// 决策内容（why 字段存 Markdown）；有独立标题且 why 为空时回退展示 text
// / Decision content (Markdown in why); falls back to text when the body is empty
const bodyContent = computed(() => props.decision.why || (hasTitle.value ? props.decision.text : ''))

const displayTitle = computed(() => strip(props.decision.title || props.decision.text))
// tooltip 与正文取同一来源，避免悬停时重现已被收起的旧 text 摘要
// 无独立标题的卡（多数存量）首行即 text，tooltip 仍展示完整 text
const fullText = computed(() => {
  if (!hasTitle.value) return strip(props.decision.text)
  const body = strip(bodyContent.value || props.decision.text)
  const title = strip(props.decision.title || '')
  return body ? `${title}：${body}` : title
})

// ── 时间足迹：创建/更新时间，格式 月-日 时:分；无独立改动时只显示创建 ──
function fmtMetaTime(raw?: string): string {
  if (!raw) return ''
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(raw)
  return m ? `${m[2]}-${m[3]} ${m[4]}:${m[5]}` : ''
}
const timeMeta = computed(() => {
  const created = fmtMetaTime(props.decision.created_at)
  const updated = fmtMetaTime(props.decision.updated_at)
  if (!created) return updated ? t('generating.decisions.meta_updated', { time: updated }) : ''
  if (!updated || updated === created) return t('generating.decisions.meta_created', { time: created })
  return `${t('generating.decisions.meta_created', { time: created })} · ${t('generating.decisions.meta_updated', { time: updated })}`
})

const content = ref(bodyContent.value)

// 同步外部变化 / Sync external changes
watch(bodyContent, (val: string) => {
  content.value = val
})

// ── 正文框高度随内容自适应：rows 只统计硬换行，长段落软折行时框高不会增长 ──
function autoGrowContent() {
  const el = contentRef.value
  // 分组折叠（display:none）下测量为 0，跳过；展开时 ResizeObserver 会补算
  if (!el || el.offsetWidth === 0) return
  el.style.height = 'auto'
  // border-box 下 scrollHeight 不含上下 border，直接赋值会稳定差出 2px
  const cs = getComputedStyle(el)
  const borderY = parseFloat(cs.borderTopWidth) + parseFloat(cs.borderBottomWidth)
  el.style.height = el.scrollHeight + borderY + 'px'
}
// 输入、斜杠日期展开、外部数据回流都经 content，统一在这里重算
watch(content, () => { void nextTick(autoGrowContent) })

let contentResizeObs: ResizeObserver | undefined

function onContentInput(e: Event) {
  // 先就地展开日期触发词（/today 后接空格），展开后的 input 事件会再回到这里同步 content
  handleDateShortcut(e)
  content.value = (e.target as HTMLTextAreaElement).value
  // 未即时展开时，刷新斜杠日期候选菜单
  contentMenuOnInput()
}

function onContentBlur() {
  contentMenuOnBlur()
  emit('commit-content', content.value)
}

// 编辑态 textarea 用 v-model，只需插入展开逻辑，模型同步由 v-model 接住
function onDateShortcut(e: Event) {
  handleDateShortcut(e)
  editMenuOnInput()
}

// ── 斜杠日期候选菜单（常驻正文 + 编辑态各一套）──
const contentRef = ref<HTMLTextAreaElement | null>(null)
const editAreaRef = ref<HTMLTextAreaElement | null>(null)
const contentMenu = useSlashDateMenu(() => contentRef.value)
const editMenu = useSlashDateMenu(() => editAreaRef.value)
// 解构为顶层 const，供模板自动解包 Ref（嵌套 Ref 不会自动解包）
const {
  open: contentMenuOpen, items: contentMenuItems, activeIndex: contentMenuActive,
  pos: contentMenuPos, onInput: contentMenuOnInput, onKeydown: contentOnKeydown,
  onBlur: contentMenuOnBlur,
} = contentMenu
const {
  open: editMenuOpen, items: editMenuItems, activeIndex: editMenuActive,
  pos: editMenuPos, onInput: editMenuOnInput, onKeydown: editOnKeydown,
} = editMenu

// 编辑区统一 keydown：先给菜单（纯 Enter 选中项会 preventDefault），未消费且 Cmd/Ctrl+Enter 则保存
function onEditKeydown(e: KeyboardEvent) {
  editOnKeydown(e)
  if (e.defaultPrevented) return
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault()
    saveEdit()
  }
}

function onSelectStatus(s: string) {
  if (s !== status.value) emit('select-status', s)
}

function onSelectOwner(o: OwnerType) {
  if (o !== ownerType.value) emit('select-owner', o)
}

// ── 等待中父芯片（方案 B）：等待方是「等待中」的子级，caret 弹层选择 ──
// 字典里承载「等待中」语义的锚点 id 是 in_progress（用户可改名，id 不可改）；
// owner_type 切状态不重置，仅回显随 status === in_progress 显隐
const WAITING_STATUS_ID = 'in_progress'
const isWaiting = computed(() => status.value === WAITING_STATUS_ID)
const ownerEchoLabel = computed(() => t('generating.decisions.owner_short_' + ownerType.value))

// ref 位于 v-for 作用域内，字符串 ref 会收集成数组，改用函数 ref 绑定单例
const ownerCaretRef = ref<HTMLElement | null>(null)
const ownerMenuRef = ref<HTMLElement | null>(null)
type RefEl = Element | ComponentPublicInstance | null
function setOwnerCaretRef(el: RefEl) { ownerCaretRef.value = el instanceof HTMLElement ? el : null }
function setOwnerMenuRef(el: RefEl) { ownerMenuRef.value = el instanceof HTMLElement ? el : null }

const {
  visible: ownerMenuVisible,
  toggle: toggleOwnerMenu,
  close: closeOwnerMenu,
  triggerAttrs: ownerTriggerAttrs,
  menuAttrs: ownerMenuAttrs,
} = usePopMenu(ownerMenuRef, ownerCaretRef, { align: 'start' })

function onPickOwner(o: OwnerType) {
  closeOwnerMenu()
  onSelectOwner(o)
}

// 切离等待中即收起弹层（外部数据回流也可能改 status，watch 兜底）
watch(isWaiting, (v) => { if (!v) closeOwnerMenu() })

// ── ⋯ 动作菜单 + 行内编辑态 ──
// DC-UNIFY-01 重构后标题/主文本曾无编辑入口，这里恢复旧「⋯ → 编辑决策文本」的行内编辑能力
// 预填与写回按节点形态区分，保证「所见即所编辑」且保存后不重复展示：
//   有独立 title（少数）：标题框=title、内容框=text，保存 {title, text}
//   无独立 title（多数）：卡片首行即 text，标题框=text、内容框=正文 why，保存 {text, why}
const editing = ref(false)
const editingHasTitle = ref(false)
const editTitle = ref('')
const editText = ref('')
const editTitleRef = ref<HTMLTextAreaElement | null>(null)
// 进入编辑时的快照：退出时据此判断是否真改动，避免仅聚焦后点走也发一次 patch
const originalTitle = ref('')
const originalText = ref('')

// 编辑态 ESC 取消：退回只读、不发请求（各自仅在自身可见时挂载，与下拉 ESC 不冲突）
useEscClose(editing, () => cancelEdit())

// 改写即存：焦点离开编辑区（点卡片其他位置或页面任意处）即自动保存并退出，无需按钮
function onEditFocusOut(e: FocusEvent) {
  if (!editing.value) return
  const next = e.relatedTarget as Node | null
  if (next && (e.currentTarget as HTMLElement)?.contains(next)) return
  saveEdit()
}

// 标题编辑框高度随内容自适应：单行起步，长标题软换行后框体跟着长，不出现内部滚动
function autoGrowTitle() {
  const el = editTitleRef.value
  if (!el) return
  el.style.height = 'auto'
  const cs = getComputedStyle(el)
  const borderY = parseFloat(cs.borderTopWidth) + parseFloat(cs.borderBottomWidth)
  el.style.height = el.scrollHeight + borderY + 'px'
}
watch(editTitle, () => { if (editing.value) void nextTick(autoGrowTitle) })

function startEdit() {
  const t = props.decision
  editingHasTitle.value = Boolean(t.title && t.title.trim())
  if (editingHasTitle.value) {
    // 有独立标题：标题行=title，内容框预填正文权威源 why（why 空回退 text）
    // 与 AddDecisionDialog 新建时同时写 text+why 的口径对齐，保证所见即所编辑
    editTitle.value = t.title || ''
    editText.value = t.why || t.text || ''
  } else {
    // 无独立标题：卡片首行展示的是 text，正文是 why
    editTitle.value = t.text || ''
    editText.value = t.why || ''
  }
  originalTitle.value = editTitle.value.trim()
  originalText.value = editText.value.trim()
  editing.value = true
  void nextTick(() => {
    autoGrowTitle()
    editTitleRef.value?.focus()
  })
}

function saveEdit() {
  if (!editing.value) return
  // 与 AddDecisionDialog 新建口径对齐：有 title 时内容同时写 text（主文本/检索）和 why（正文权威源），
  // 保证 bodyContent 优先读 why 时能拿到用户最新编辑内容，不被残留 why 老值覆盖
  const title = editTitle.value.trim()
  const body = editText.value.trim()
  const dirty = title !== originalTitle.value || body !== originalText.value
  editing.value = false
  if (!dirty) return
  emit('patch', editingHasTitle.value
    ? { title, text: body, why: body }
    : { text: title, why: body })
}

function cancelEdit() {
  editing.value = false
}

onMounted(() => {
  void nextTick(autoGrowContent)
  // 宽度变化（窗口缩放）与分组 v-show 折叠/展开都会触发，按新尺寸重算折行高度
  contentResizeObs = new ResizeObserver(() => autoGrowContent())
  if (contentRef.value) contentResizeObs.observe(contentRef.value)
})
onBeforeUnmount(() => {
  contentResizeObs?.disconnect()
})

// 编辑态（v-if）结束后正文 textarea 是重新挂载的节点，需补测并重新挂观察
watch(editing, (v) => {
  if (!v) void nextTick(() => {
    autoGrowContent()
    if (contentResizeObs && contentRef.value) contentResizeObs.observe(contentRef.value)
  })
})
</script>
