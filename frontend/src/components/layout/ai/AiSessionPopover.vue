<template>
  <!-- 会话入口：头部右侧时钟图标触发（历史任务语义），弹出式会话列表内置检索 -->
  <IconButton
    ref="triggerComp"
    class="ai-session-trigger"
    :class="{ 'is-open': visible }"
    :label="t('ai-panel.sessions_trigger_label')"
    v-bind="triggerAttrs"
    @click="toggle"
  >
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
      <path d="M3 3v5h5"/>
      <path d="M12 7v5l4 2"/>
    </svg>
  </IconButton>
  <div
    ref="menuEl"
    v-show="visible"
    v-bind="menuAttrs"
    class="ai-session-popover"
    :aria-label="t('ai-panel.sessions')"
  >
    <!-- 顶行：标题 + 计数 + 清空（新建入口已在面板头部） -->
    <div class="asp-head">
      <span class="asp-head-title">{{ t('ai-panel.sessions_title') }}</span>
      <span class="asp-head-count">{{ sessions.length }}</span>
      <span class="asp-head-actions">
        <IconButton
          class="asp-clear" :class="{ 'is-armed': confirmClear }" :label="t('ai-panel.clear_current')"
          tip-position="bottom" :disabled="activeEmpty" @click="confirmClear = !confirmClear"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </IconButton>
      </span>
    </div>
    <!-- 搜索行：打开弹层即聚焦；↓ 进入列表，空搜索时 Esc 关闭并归还焦点 -->
    <div class="asp-search">
      <svg class="asp-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
      <input
        ref="searchRef"
        v-model="query"
        class="asp-search-input"
        type="text"
        autocomplete="off"
        :placeholder="t('ai-panel.sessions_search_placeholder')"
        :aria-label="t('ai-panel.sessions_search_placeholder')"
        @keydown.stop="onSearchKey"
      />
    </div>
    <!-- 会话列表 -->
    <div class="asp-list">
      <div
        v-for="s in filtered" :key="s.id"
        class="asp-item" :class="{ 'is-active': s.id === activeSessionId }"
        role="menuitem"
        :aria-haspopup="renamingId === s.id ? 'dialog' : undefined"
        @click="onSwitch(s.id)"
      >
        <input
          v-if="renamingId === s.id"
          class="asp-item-input"
          :value="renameInput"
          @input="$emit('update:renameInput', ($event.target as HTMLInputElement).value)"
          @keydown.enter.prevent="$emit('confirmRename')"
          @keydown.escape.stop.prevent="$emit('cancelRename')"
          @blur="$emit('confirmRename')"
          @click.stop
          :aria-label="t('ai-panel.rename_session')"
        />
        <span v-else class="asp-item-name">{{ s.name || t('ai-panel.session_default') }}</span>
        <!-- 元信息与行内操作共用同一右槽（grid 叠放）：hover 时换入图标，不产生布局跳动 -->
        <span class="asp-item-slot">
          <span class="asp-item-meta">{{ s.messages.length }} {{ t('ai-panel.sessions_msg_count') }} · {{ relTime(s.createdAt) }}</span>
          <!-- hover 或焦点进入都显示：键盘用户不经 mouseenter 也要能触达重命名/删除 -->
          <span class="asp-item-actions">
            <IconButton class="asp-item-action" :label="t('ai-panel.rename')" @click.stop="$emit('startRename', s.id)">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 1.5l3 3-9 9H2.5v-3z"/></svg>
            </IconButton>
            <IconButton class="asp-item-action is-close" :label="t('ai-panel.delete')" @click.stop="$emit('delete', s.id)">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8"/><path d="M12 4l-8 8"/></svg>
            </IconButton>
          </span>
        </span>
      </div>
      <div v-if="filtered.length === 0" class="asp-empty">{{ t(query.trim() ? 'ai-panel.sessions_empty_match' : 'ai-panel.sessions_empty') }}</div>
    </div>
    <!-- 确认条：只能作为最后一个子节点追加——若插在中间，Vue 按下标 patch 会在本次点击冒泡
         途中摘除已接手的按钮节点，使 click-outside 误判为“点在弹层外”而提前关闭 -->
    <div v-if="confirmClear" class="asp-confirm">
      <span class="asp-confirm-text">{{ t('ai-panel.clear_current_question') }}</span>
      <span class="asp-confirm-actions">
        <button class="asp-mini" @click="confirmClear = false">{{ t('common.action.cancel') }}</button>
        <button class="asp-mini is-danger" @click="onClear">{{ t('ai-panel.clear_current_confirm') }}</button>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AiSession } from '@/stores/aiSessions'
import { usePopMenu } from '@/composables/usePopMenu'
import IconButton from '@/components/common/IconButton.vue'

const { t } = useI18n()

const props = defineProps<{
  sessions: AiSession[]
  activeSessionId: string
  renamingId: string | null
  renameInput: string
}>()

const emit = defineEmits<{
  (e: 'switch', id: string): void
  (e: 'newSession'): void
  (e: 'startRename', id: string): void
  (e: 'delete', id: string): void
  (e: 'confirmRename'): void
  (e: 'cancelRename'): void
  (e: 'clear'): void
  (e: 'update:renameInput', val: string): void
}>()

// IconButton 是组件，模板 ref 拿到的是实例；挂载后取其根 button 元素交给 usePopMenu 定位
const triggerComp = ref<InstanceType<typeof IconButton> | null>(null)
const triggerEl = ref<HTMLElement | null>(null)
const menuEl = ref<HTMLElement | null>(null)
onMounted(() => { triggerEl.value = (triggerComp.value?.$el as HTMLElement) ?? null })
// 触发按钮在 47px 头部行内居中（30px 高，上下各余约 8px），gap 8 使弹层落在行下方
const { visible, toggle, close, triggerAttrs, menuAttrs } = usePopMenu(menuEl, triggerEl, { gap: 8 })

const query = ref('')
const searchRef = ref<HTMLInputElement | null>(null)
const confirmClear = ref(false)
/** 当前会话无消息时「清空」无意义，置灰避免空操作 */
const activeEmpty = computed(() => {
  const s = props.sessions.find(x => x.id === props.activeSessionId)
  return (s?.messages.length ?? 0) === 0
})
const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? props.sessions.filter(s => (s.name || '').toLowerCase().includes(q)) : props.sessions
})

// 打开时重置搜索与确认态，并把光标送进搜索框（找会话是弹层的首要动作）；
// 多包一层 rAF 是为了跑在 usePopMenu 键盘聚焦（将首个 menuitem）之后，不被抢回焦点
watch(visible, (v) => {
  if (!v) return
  query.value = ''
  confirmClear.value = false
  requestAnimationFrame(() => searchRef.value?.focus())
})

/** 搜索框键盘：↓ 下入列表，有内容时 Esc 清空，已空时 Esc 关闭并归还焦点给触发按钮 */
function onSearchKey(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    focusFirstItem()
  } else if (e.key === 'Escape') {
    e.preventDefault()
    if (query.value) { query.value = ''; return }
    close()
    triggerEl.value?.focus()
  }
}

/** menuitem 是 div，没有 tabindex 时 .focus() 无效（与 usePopMenu.focusItem 同一补法） */
function focusFirstItem() {
  const it = menuEl.value?.querySelector<HTMLElement>('[role="menuitem"]')
  if (!it) return
  if (it.tabIndex < 0) it.tabIndex = -1
  it.focus()
}

function onClear() {
  emit('clear')
  confirmClear.value = false
  close()
}

// 重命名行出现后聚焦并全选，与旧标签栏行为一致
watch(() => props.renamingId, (id) => {
  if (!id) return
  nextTick(() => {
    const el = menuEl.value?.querySelector<HTMLInputElement>('.asp-item-input')
    el?.focus()
    el?.select()
  })
})

/** 切换后收起面板；删除保持展开以便连续清理。
    新建由面板头部的圈加号承担，本弹层不再触发 newSession（emit 保留给父层契约） */
function onSwitch(id: string) {
  if (id === props.activeSessionId) { close(); return }
  emit('switch', id)
  close()
}

/** 基于创建时间的相对时间：刚刚 / N分 / N时 / N天 */
function relTime(ts: number): string {
  const sec = Math.max(0, Math.floor((Date.now() - ts) / 1000))
  if (sec < 60) return t('ai-panel.sessions_time_just_now')
  const min = Math.floor(sec / 60)
  if (min < 60) return t('ai-panel.sessions_time_minutes', { n: min })
  const hr = Math.floor(min / 60)
  if (hr < 24) return t('ai-panel.sessions_time_hours', { n: hr })
  return t('ai-panel.sessions_time_days', { n: Math.floor(hr / 24) })
}
</script>
