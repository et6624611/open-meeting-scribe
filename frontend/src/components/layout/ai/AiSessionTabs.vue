<template>
  <div class="ai-session-tabs">
    <div ref="tabsRoot" class="ai-session-tabs-scroll" role="tablist" :aria-label="t('ai-panel.sessions')">
      <!-- 原为 <button>，内部又嵌重命名/删除 <button>：违反 HTML 内容模型（交互元素不可嵌套），
           静态解析时内层会被提出。外层改 div 后 DOM 合法，键盘可达性由 focus-within 兜底。
           The outer element used to be a <button> wrapping two more <button>s, which is
           invalid HTML content model. A div host makes the tree legal. -->
      <div
        v-for="s in visibleSessions" :key="s.id"
        class="ai-session-seg" :class="{ 'is-active': s.id === activeSessionId }"
        :data-session-id="s.id"
        role="tab"
        :aria-selected="s.id === activeSessionId"
        :tabindex="s.id === activeSessionId ? 0 : -1"
        :title="s.name || t('ai-panel.session_default')"
        @click="$emit('switch', s.id)"
        @keydown.enter.prevent="$emit('switch', s.id)"
        @keydown.space.prevent="$emit('switch', s.id)"
        @keydown="onSegKeydown($event, s.id)"
        @mouseenter="segHover = s.id"
        @mouseleave="segHover = null"
        @focusin="segFocus = s.id"
        @focusout="onSegFocusOut"
      >
        <input
          v-if="renamingId === s.id"
          ref="renameInputRef"
          class="ai-session-seg-input"
          :value="renameInput" @input="$emit('update:renameInput', ($event.target as HTMLInputElement).value)"
          @keydown="onRenameKey"
          @blur="$emit('confirmRename')"
          @click.stop
          :aria-label="t('ai-panel.rename_session')"
        />
        <span v-else class="ai-session-seg-label">{{ s.name }}</span>
        <span class="ai-session-seg-dot"></span>
        <!-- hover 或焦点进入都显示：此前只有 @mouseenter，键盘用户永远够不到这两个动作 -->
        <span v-if="(segHover === s.id || segFocus === s.id) && s.id !== activeSessionId && renamingId !== s.id" class="ai-session-seg-actions">
          <IconButton class="ai-session-seg-action" :label="t('ai-panel.rename')" @click.stop="$emit('startRename', s.id)">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 1.5l3 3-9 9H2.5v-3z"/></svg>
          </IconButton>
          <IconButton class="ai-session-seg-action is-close" :label="t('ai-panel.delete')" @click.stop="$emit('delete', s.id)">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8"/><path d="M12 4l-8 8"/></svg>
          </IconButton>
        </span>
      </div>
    </div>
    <div v-if="overflowSessions.length > 0" class="ai-session-overflow">
      <IconButton
        class="ai-session-overflow-btn"
        :class="{ 'is-active': showOverflowMenu }"
        :label="t('ai-panel.more_sessions', { count: overflowSessions.length })"
        @click.stop="showOverflowMenu = !showOverflowMenu"
      >
        <svg viewBox="0 0 16 16" fill="currentColor"><circle cx="3.5" cy="8" r="1.2"/><circle cx="8" cy="8" r="1.2"/><circle cx="12.5" cy="8" r="1.2"/></svg>
      </IconButton>
      <div v-if="showOverflowMenu" class="ai-session-overflow-menu" @click.stop>
        <div
          v-for="s in overflowSessions" :key="s.id"
          class="ai-session-overflow-item"
          :class="{ 'is-active': s.id === activeSessionId }"
          @click="$emit('switch', s.id); showOverflowMenu = false"
        >
          <span class="ai-session-overflow-item-label">{{ s.name }}</span>
          <span class="ai-session-overflow-item-actions">
            <IconButton class="ai-session-seg-action" :label="t('ai-panel.rename')" @click.stop="$emit('startRename', s.id)">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.5 1.5l3 3-9 9H2.5v-3z"/></svg>
            </IconButton>
            <IconButton class="ai-session-seg-action is-close" :label="t('ai-panel.delete')" @click.stop="$emit('delete', s.id); showOverflowMenu = false">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8"/><path d="M12 4l-8 8"/></svg>
            </IconButton>
          </span>
        </div>
      </div>
    </div>
    <IconButton class="ai-session-add" :label="t('ai-panel.new_session')" show-label @click="$emit('newSession')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
    </IconButton>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import IconButton from '@/components/common/IconButton.vue'

const { t } = useI18n()

const props = defineProps<{
  sessions: Array<{ id: string; name: string }>
  activeSessionId: string
  renamingId: string | null
  renameInput: string
}>()

defineEmits<{
  (e: 'switch', id: string): void
  (e: 'newSession'): void
  (e: 'startRename', id: string): void
  (e: 'delete', id: string): void
  (e: 'confirmRename'): void
  (e: 'cancelRename'): void
  (e: 'renameKey', ev: KeyboardEvent): void
  (e: 'update:renameInput', val: string): void
}>()

const MAX_VISIBLE_SESSIONS = 3
const showOverflowMenu = ref(false)
const segHover = ref<string | null>(null)
/** 焦点版 hover：键盘用户没有 mouseenter，重命名/删除此前对其完全不可见 */
const segFocus = ref<string | null>(null)
const renameInputRef = ref<HTMLInputElement | HTMLInputElement[] | null>(null)
const tabsRoot = ref<HTMLElement | null>(null)

/** ←→ 只移动焦点，Enter/Space 才切换会话：浏览不会真的换掉当前上下文
    Arrow keys move focus only; activation stays manual so browsing never switches. */
function onSegKeydown(e: KeyboardEvent, id: string) {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
  const ids = visibleSessions.value.map(s => s.id)
  const i = ids.indexOf(id)
  if (i < 0) return
  e.preventDefault()
  const nextId = ids[(i + (e.key === 'ArrowRight' ? 1 : -1) + ids.length) % ids.length]
  const target = tabsRoot.value?.querySelector<HTMLElement>(`[data-session-id="${CSS.escape(nextId)}"]`)
  if (!target) return
  // roving tabindex：临时放开目标以便聚焦，离开后收回，保持 Tab 只停在工作会话上
  target.setAttribute('tabindex', '0')
  target.addEventListener('blur', () => target.setAttribute('tabindex', '-1'), { once: true })
  target.focus()
}

/** 焦点在 seg 与其内部按钮之间移动时不收起动作区 */
function onSegFocusOut(e: FocusEvent) {
  const seg = e.currentTarget as HTMLElement
  const to = e.relatedTarget as Node | null
  if (to && seg.contains(to)) return
  segFocus.value = null
}

const visibleSessions = computed(() => props.sessions.slice(0, MAX_VISIBLE_SESSIONS))
const overflowSessions = computed(() => props.sessions.slice(MAX_VISIBLE_SESSIONS))

function onRenameKey(e: KeyboardEvent) {
  if (e.key === 'Enter') { e.preventDefault(); /* parent handles confirm */ }
  else if (e.key === 'Escape') { e.preventDefault(); /* parent handles cancel */ }
}

defineExpose({ renameInputRef, showOverflowMenu })
</script>
