<template>
  <!-- 决策流卡片（唯一决策对象的交互载体）/ Decision-flow card: the one and only decision object -->
  <div class="db-node" :data-todo-id="todo.id" :class="{ 'is-done': closing }" :style="statusVarStyle">
    <!-- 第一行：状态点 + 标题 + 状态下拉 + 负责人下拉 / Row 1: dot + title + status dropdown + owner dropdown -->
    <div class="db-row1">
      <span class="db-dot"></span>
      <span class="db-title" v-if="!editing" :title="fullText">{{ displayTitle }}</span>
      <span class="db-title-spacer" v-else></span>
      <!-- 状态下拉：选项与颜色全部来自状态字典 / Status dropdown: options & colors come from the status dictionary -->
      <div class="db-dropdown-wrap" ref="statusDropRef">
        <button class="db-status-btn" :aria-expanded="statusOpen" aria-haspopup="menu" @click.stop="statusOpen = !statusOpen">
          {{ statusLabel }}
          <svg class="db-dd-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <div class="db-dropdown" :class="{ 'is-open': statusOpen }" role="menu">
          <button
            v-for="s in statusOptions"
            :key="s.id"
            class="db-dd-item"
            :class="{ 'is-active': s.id === status }"
            @click.stop="onSelectStatus(s.id)"
          >
            <span class="db-dd-dot" :style="{ background: s.color }"></span>
            {{ labelOf(s.id, locale) }}
            <svg v-if="s.id === status" class="db-dd-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
          </button>
        </div>
      </div>
      <!-- 负责人下拉 / Owner dropdown -->
      <div class="db-dropdown-wrap" ref="ownerDropRef">
        <button class="db-owner-btn" :aria-expanded="ownerOpen" aria-haspopup="menu" @click.stop="ownerOpen = !ownerOpen">
          {{ ownerLabel }}
          <svg class="db-dd-caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <div class="db-dropdown" :class="{ 'is-open': ownerOpen }" role="menu">
          <button
            v-for="o in ownerOptions"
            :key="o"
            class="db-dd-item"
            :class="{ 'is-active': o === ownerType }"
            @click.stop="onSelectOwner(o)"
          >
            {{ t('generating.todos.owner_waiting_' + o) }}
            <svg v-if="o === ownerType" class="db-dd-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- ⋯ 菜单进入的行内编辑态：编辑「标题 + 主文本」；正文(why)仍由下方常驻 textarea 维护 -->
    <div class="db-edit" v-if="editing">
      <label class="db-edit-field">
        <span class="db-edit-label">{{ t('generating.todos.edit_title_label') }}</span>
        <input
          ref="editTitleRef"
          class="db-edit-input"
          type="text"
          maxlength="200"
          v-model="editTitle"
          :placeholder="t('generating.todos.edit_title_placeholder')"
          @keydown.meta.enter.prevent="saveEdit"
          @keydown.ctrl.enter.prevent="saveEdit"
        />
      </label>
      <label class="db-edit-field">
        <span class="db-edit-label">{{ t('generating.todos.edit_content_label') }}</span>
        <textarea
          ref="editAreaRef"
          class="db-edit-area"
          v-model="editText"
          rows="3"
          :placeholder="t('generating.todos.edit_content_placeholder')"
          @input="onDateShortcut"
          @keydown="onEditKeydown"
          @blur="editMenu.onBlur"
        ></textarea>
        <SlashDateMenu
          :open="editMenuOpen" :items="editMenuItems" :active-index="editMenuActive" :pos="editMenuPos"
          @select="editMenu.select" @hover="editMenu.setActive"
        />
      </label>
      <div class="db-edit-actions">
        <button type="button" class="db-edit-btn" @click="cancelEdit">{{ t('generating.todos.edit_cancel') }}</button>
        <button type="button" class="db-edit-btn is-primary" @click="saveEdit">{{ t('generating.todos.edit_save') }}</button>
      </div>
    </div>

    <!-- 第二行：Markdown textarea / Row 2: Markdown textarea -->
    <div class="db-content" v-if="!editing">
      <textarea
        ref="contentRef"
        class="db-card-textarea"
        :value="content"
        :placeholder="t('generating.todos.content_placeholder')"
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

    <!-- 底部：操作 / Footer: actions -->
    <div class="db-footer">
      <span class="db-footer-spacer"></span>
      <!-- ⋯ 动作菜单：进入「编辑决策文本」态（编辑态下隐藏，避免重复入口） -->
      <div class="db-action-wrap" v-if="!editing">
        <button
          ref="actionBtnRef"
          type="button"
          class="db-action-btn"
          v-bind="actionTriggerAttrs"
          @click="toggleActionMenu"
          :title="t('generating.todos.edit_menu')"
          :aria-label="t('generating.todos.edit_menu')"
        >
          <svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg>
        </button>
        <div
          ref="actionMenuRef"
          class="db-menu"
          v-bind="actionMenuAttrs"
          :class="{ 'is-open': actionMenuVisible }"
        >
          <button type="button" class="db-menu-item" role="menuitem" @click="startEdit">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
            {{ t('generating.todos.edit_text') }}
          </button>
        </div>
      </div>
      <button class="db-delete-btn" :title="t('generating.todos.delete')" @click="emit('delete')" :aria-label="t('generating.todos.delete')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TodoItem, OwnerType } from '@/api/types'
import type { TodoPatch } from '@/api/notes'
import { useDecisionStatuses } from '@/composables/useDecisionStatuses'
import { useEscClose } from '@/composables/useEscClose'
import { usePopMenu } from '@/composables/usePopMenu'
import { useSlashDateMenu } from '@/composables/useSlashDateMenu'
import { stripDecisionEmphasis } from '@/utils/decisionText'
import { handleDateShortcut } from '@/utils/dateShortcuts'
import SlashDateMenu from '@/components/SlashDateMenu.vue'

const { t, locale } = useI18n()

const props = defineProps<{
  todo: TodoItem
}>()

const emit = defineEmits<{
  (e: 'select-status', status: string): void
  (e: 'select-owner', owner: OwnerType): void
  (e: 'commit-content', content: string): void
  (e: 'patch', patch: TodoPatch): void
  (e: 'delete'): void
}>()

// ── 状态字典（选项 / 名称 / 颜色 / 闭档位全部配置驱动） ──
const { statuses, load, labelOf, colorOf, isClosing } = useDecisionStatuses()
void load()

const ownerOptions: OwnerType[] = ['self', 'agent', 'colleague', 'enterprise']
const statusOptions = computed(() => statuses.value)

// ── 下拉状态 / Dropdown open state ──
const statusOpen = ref(false)
const ownerOpen = ref(false)
// ESC 关闭下拉需落到状态上，仅剥 class 会让下次渲染重新打开
// ESC must clear state, not just the class, or the next render reopens the surface.
useEscClose(statusOpen, () => { statusOpen.value = false })
useEscClose(ownerOpen, () => { ownerOpen.value = false })
const statusDropRef = ref<HTMLElement | null>(null)
const ownerDropRef = ref<HTMLElement | null>(null)

// 状态：显式 status 优先，缺省由旧 done 布尔推导（历史 task JSON 兼容）
const status = computed(() => props.todo.status || (props.todo.done ? 'done' : 'in_progress'))
const closing = computed(() => isClosing(status.value) || status.value === 'done')
const statusLabel = computed(() => labelOf(status.value, String(locale.value || 'zh-CN')))
const ownerType = computed<OwnerType>(() => props.todo.owner_type || 'self')

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
const hasTitle = computed(() => Boolean(props.todo.title && props.todo.text && props.todo.text !== props.todo.why))

// 决策内容（why 字段存 Markdown）；有独立标题且 why 为空时回退展示 text
// / Decision content (Markdown in why); falls back to text when the body is empty
const bodyContent = computed(() => props.todo.why || (hasTitle.value ? props.todo.text : ''))

const displayTitle = computed(() => strip(props.todo.title || props.todo.text))
// tooltip 与正文取同一来源，避免悬停时重现已被收起的旧 text 摘要
// 无独立标题的卡（多数存量）首行即 text，tooltip 仍展示完整 text
const fullText = computed(() => {
  if (!hasTitle.value) return strip(props.todo.text)
  const body = strip(bodyContent.value || props.todo.text)
  const title = strip(props.todo.title || '')
  return body ? `${title}：${body}` : title
})

// 负责人文字标签 / Owner text label
const ownerLabel = computed(() => t('generating.todos.owner_waiting_' + ownerType.value))

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
  statusOpen.value = false
  if (s !== status.value) emit('select-status', s)
}

function onSelectOwner(o: OwnerType) {
  ownerOpen.value = false
  if (o !== ownerType.value) emit('select-owner', o)
}

// ── ⋯ 动作菜单 + 行内编辑态 ──
// DC-UNIFY-01 重构后标题/主文本曾无编辑入口，这里恢复旧「⋯ → 编辑决策文本」的行内编辑能力
// 预填与写回按节点形态区分，保证「所见即所编辑」且保存后不重复展示：
//   有独立 title（少数）：标题框=title、内容框=text，保存 {title, text}
//   无独立 title（多数）：卡片首行即 text，标题框=text、内容框=正文 why，保存 {text, why}
const editing = ref(false)
const editingHasTitle = ref(false)
const editTitle = ref('')
const editText = ref('')
const editTitleRef = ref<HTMLInputElement | null>(null)
const actionBtnRef = ref<HTMLElement | null>(null)
const actionMenuRef = ref<HTMLElement | null>(null)
const {
  visible: actionMenuVisible,
  toggle: toggleActionMenu,
  close: closeActionMenu,
  triggerAttrs: actionTriggerAttrs,
  menuAttrs: actionMenuAttrs,
} = usePopMenu(actionMenuRef, actionBtnRef)

// 编辑态 ESC 取消：退回只读、不发请求（各自仅在自身可见时挂载，与下拉 ESC 不冲突）
useEscClose(editing, () => cancelEdit())

function startEdit() {
  closeActionMenu()
  const t = props.todo
  editingHasTitle.value = Boolean(t.title && t.title.trim())
  if (editingHasTitle.value) {
    // 有独立标题：标题行=title，摘要行=text
    editTitle.value = t.title || ''
    editText.value = t.text || ''
  } else {
    // 无独立标题：卡片首行展示的是 text，正文是 why
    editTitle.value = t.text || ''
    editText.value = t.why || ''
  }
  editing.value = true
  void nextTick(() => editTitleRef.value?.focus())
}

function saveEdit() {
  if (!editing.value) return
  // 按进入编辑态时的形态写回对应字段：走既有 patch 链路（决策中心 savePatch / 纪要页 update→onEditTodo）
  const title = editTitle.value.trim()
  const body = editText.value.trim()
  emit('patch', editingHasTitle.value ? { title, text: body } : { text: title, why: body })
  editing.value = false
}

function cancelEdit() {
  editing.value = false
}

// ── 点击外部关闭下拉 / Click-outside to close dropdowns ──
function onDocClick(e: MouseEvent) {
  if (statusDropRef.value && !statusDropRef.value.contains(e.target as Node)) statusOpen.value = false
  if (ownerDropRef.value && !ownerDropRef.value.contains(e.target as Node)) ownerOpen.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocClick, true)
  void nextTick(autoGrowContent)
  // 宽度变化（窗口缩放）与分组 v-show 折叠/展开都会触发，按新尺寸重算折行高度
  contentResizeObs = new ResizeObserver(() => autoGrowContent())
  if (contentRef.value) contentResizeObs.observe(contentRef.value)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick, true)
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
