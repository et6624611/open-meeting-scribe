<template>
  <!--
    人员栏（渐进式压缩） / Personnel bar (progressive compression)
    - compact（readonly / complete）：响应式说话人展示 + 参会人 chip + 选择器
    - binding（actionable）：展开绑定交互 + 底部参会人管理
  -->
  <div class="gs-zone" :class="{ 'is-binding': interactive, 'is-compact': !interactive, hidden: !visible }">

    <!-- ═══ 紧凑态（readonly / complete） ═══ -->
    <template v-if="!interactive">
      <div class="gs-compact-bar">
        <!-- 宽屏仅逐个展示已关联说话人，未关联折叠成一条（见下方 gs-unbound-wrap） -->
        <div class="gs-compact-full">
          <span
            v-for="sp in boundSpeakers" :key="'f'+sp.sid"
            class="gs-compact-label"
            :title="sp.displayName"
            @click="emit('locate-speaker', sp.sid)"
          >
            <span class="gs-compact-label-row">
              <span class="gs-compact-label-dot" :style="{ background: sp.color }"></span>
              <span class="gs-compact-label-name" :style="{ color: sp.color }">{{ sp.displayName }}</span>
            </span>
            <span class="gs-compact-label-bar"><span class="gs-compact-label-fill" :style="{ width: sp.pct + '%', background: sp.color }"></span></span>
          </span>
          <button v-if="canEditBindings" class="gs-compact-edit" :title="t('generating.binding.edit_bindings')" @click="emit('reenter-binding')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          </button>
        </div>

        <!-- 说话人紧凑圆点（窄屏折叠） / Compact dots (narrow fallback) -->
        <div class="gs-compact-dots">
          <span
            v-for="sp in boundSpeakers" :key="'d'+sp.sid"
            class="gs-compact-dot"
            :style="{ background: sp.color }"
            :title="sp.displayName"
            @click="emit('locate-speaker', sp.sid)"
          >{{ dotInitial(sp.displayName) }}</span>
          <button v-if="canEditBindings" class="gs-compact-edit" :title="t('generating.binding.edit_bindings')" @click="emit('reenter-binding')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          </button>
        </div>

        <!-- 未关联说话人折叠条：逐枚展示信息趋同，收拢为一条，点击展开逐个定位 -->
        <!-- Collapsed unbound speakers chip: expand on click to locate each -->
        <div class="gs-unbound-wrap" :class="{ 'is-open': unboundOpen }" v-if="unboundSpeakers.length">
          <button class="gs-unbound-chip" :title="t('generating.binding.unbound_collapsed_tip')" @click.stop="toggleUnbound">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            {{ t('generating.binding.unbound_collapsed', { count: unboundSpeakers.length }) }}
            <svg class="gs-unbound-chev" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <div v-if="unboundOpen" class="gs-unbound-dropdown" @click.stop>
            <div
              v-for="sp in unboundSpeakers" :key="'u'+sp.sid"
              class="gs-unbound-item"
              @click="locateUnbound(sp.sid)"
            >
              <span class="gs-compact-label-dot" :style="{ background: sp.color }"></span>
              <span class="gs-compact-label-name" :style="{ color: sp.color }">{{ sp.displayName }}</span>
              <span class="gs-compact-label-bar"><span class="gs-compact-label-fill" :style="{ width: sp.pct + '%', background: sp.color }"></span></span>
            </div>
          </div>
        </div>

        <!-- 分隔符 / Separator -->
        <span class="gs-compact-sep"></span>

        <!-- 参会人 chip 列表 + 选择器 + 内联输入 / Roster chips + picker + inline input -->
        <div class="gs-compact-roster">
          <span v-for="(name, idx) in roster" :key="idx" class="gs-roster-chip" :class="{ 'is-auto': isAutoMember(name) }">
            {{ name }}
            <span v-if="isAutoMember(name)" class="gs-roster-auto-tag">{{ t('generating.roster.auto_tag') }}</span>
            <button v-else class="gs-roster-chip-x" :title="t('generating.roster.remove')" @click="emit('roster-remove', idx)">
              <svg width="8" height="8" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3l6 6M9 3l-6 6"/></svg>
            </button>
          </span>
          <!-- 说话人选择器 / Speaker picker -->
          <span class="gs-roster-picker-wrap">
            <button class="gs-roster-picker-btn" :title="t('generating.roster.pick_speaker')" @click.stop="toggleRosterPicker">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
            <div v-if="rosterPickerOpen" class="gs-roster-dropdown" @click.stop>
              <div class="gs-roster-dd-search">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                <input
                  ref="rosterSearchRef"
                  v-model="rosterSearch"
                  :placeholder="t('generating.roster.search_placeholder')"
                  autocomplete="off"
                  @keydown="onRosterPickerKeydown"
                />
              </div>
              <div class="gs-roster-dd-list">
                <div
                  v-for="(s, idx) in filteredRosterSpeakers" :key="s.id"
                  class="gs-roster-dd-item"
                  :class="{ 'is-focused': rosterPickerFocusIdx === idx }"
                  @click="selectRosterSpeaker(s)"
                >
                  <span class="gs-roster-dd-dot" :style="{ background: getSpeakerColor(s.id) }"></span>
                  <span>{{ s.name }}</span>
                </div>
                <div v-if="filteredRosterSpeakers.length === 0 && rosterSearch.trim()" class="gs-roster-dd-create" @click="createAndAddToRoster">
                  {{ t('generating.roster.create_hint', { name: rosterSearch.trim() }) }}
                </div>
                <div v-if="filteredRosterSpeakers.length === 0 && !rosterSearch.trim()" class="gs-roster-dd-empty">
                  {{ t('generating.binding.no_match') }}
                </div>
              </div>
            </div>
          </span>
        </div>
      </div>
    </template>

    <!-- ═══ 绑定态（actionable） ═══ -->
    <template v-else>
      <div class="gbb-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      </div>

      <div class="gs-body">
        <div class="gbb-title-row">
          <span class="gbb-title">{{ mode === 'complete' ? t('generating.binding.title_all_bound') : t('generating.binding.title') }}</span>
        </div>

        <div class="gs-chips">
          <span
            v-for="sp in speakers" :key="sp.sid"
            class="gs-chip is-interactive"
            :class="{ 'is-unbound': !sp.bound }"
            :style="{ background: chipBg(sp.sid) }"
            :title="chipTitle(sp)"
            @click="emit('open-dropdown', $event, sp.sid)"
          >
            <span class="gs-chip-head">
              <span class="gs-name" :class="{ 'gs-unbound': !sp.bound }" :style="{ color: sp.color }">{{ sp.displayName }}</span>
              <svg v-if="!sp.bound" class="bl-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
              <svg v-else class="bl-check" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              <span class="bl-locate" :title="t('generating.binding.locate')" @click.stop="emit('locate-speaker', sp.sid)">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="7"/><line x1="12" y1="1" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="23"/><line x1="1" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="23" y2="12"/></svg>
              </span>
            </span>
            <span class="gs-bar"><span class="gs-bar-fill" :style="{ width: sp.pct + '%', background: sp.color }"></span></span>
          </span>
        </div>

        <!-- 底部参会人 / Roster at bottom -->
        <div class="gs-roster-section" v-if="roster.length > 0">
          <span class="gs-roster-label">{{ t('generating.roster.title') }} ({{ roster.length }})</span>
          <span v-for="(name, idx) in roster" :key="idx" class="gs-roster-chip" :class="{ 'is-auto': isAutoMember(name) }">
            {{ name }}
            <span v-if="isAutoMember(name)" class="gs-roster-auto-tag">{{ t('generating.roster.auto_tag') }}</span>
            <button v-else class="gs-roster-chip-x" :title="t('generating.roster.remove')" @click="emit('roster-remove', idx)">
              <svg width="8" height="8" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3l6 6M9 3l-6 6"/></svg>
            </button>
          </span>
        </div>
      </div>

      <div class="gbb-actions">
        <template v-if="unboundCount > 0">
          <a class="gbb-skip" href="javascript:void(0)" @click="emit('skip')">{{ t('generating.binding.skip') }}</a>
          <button class="btn btn-primary btn-sm" @click="emit('confirm')">{{ t('generating.binding.confirm') }}</button>
        </template>
        <button class="gbb-close" @click="emit('close')" :title="t('generating.binding.close')">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
        </button>
      </div>
    </template>
  </div>

  <!-- 绑定下拉框（Teleport） / Binding dropdown (Teleport) -->
  <Teleport to="body">
    <div v-if="dropdown.visible" class="bt-dropdown" :style="{ left: dropdown.x + 'px', top: dropdown.y + 'px' }" @click.stop>
      <div class="bt-dd-search">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="text" :placeholder="t('generating.binding.search_placeholder')" autocomplete="off" :value="dropdown.search" @input="emit('update:dropdown-search', ($event.target as HTMLInputElement).value)" @keydown="emit('dropdown-keydown', $event)">
      </div>
      <div class="bt-dd-list">
        <template v-if="!dropdown.search">
          <div class="bt-dropdown-item" :class="{ 'is-selected': !currentMapping[dropdown.speakerId] }" @click="emit('select', dropdown.speakerId, '')">
            <span class="bt-di-name">{{ t('generating.binding.no_bind') }}</span>
          </div>
          <div class="bt-dd-sep"></div>
        </template>
        <template v-if="filteredSpeakers.length > 0">
          <div
            v-for="(s, idx) in filteredSpeakers" :key="s.id"
            class="bt-dropdown-item"
            :class="{ 'is-selected': currentMapping[dropdown.speakerId] === s.id, 'is-focused': dropdown.focusIdx === idx }"
            @click="emit('select', dropdown.speakerId, s.id)"
          >
            <span class="bt-di-name" :style="{ color: currentMapping[dropdown.speakerId] === s.id ? getSpeakerColor(String(dropdown.speakerId)) : undefined }">{{ s.name }}<span v-if="s.role" class="bt-di-role">({{ s.role }})</span></span>
          </div>
        </template>
        <div v-else class="bt-dd-empty">{{ t('generating.binding.no_match') }}</div>
      </div>
      <div class="bt-dd-footer" v-if="dropdown.search && filteredSpeakers.length === 0">
        <div class="bt-dropdown-item" :class="{ 'is-focused': dropdown.focusIdx === 0 }" @click="emit('create-and-bind', dropdown.speakerId, dropdown.search)" style="color: var(--accent)">
          <span style="font-weight: 500">{{ t('generating.binding.create_named') }}</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getSpeakerColor } from '@/utils/speakerColors'
import { useEscClose } from '@/composables/useEscClose'
import { createSpeaker, type Speaker } from '@/api/speakers'

interface ZoneSpeaker {
  sid: number
  pct: number
  color: string
  name: string
  displayName: string
  bound: boolean
}

const props = defineProps<{
  mode: 'readonly' | 'actionable' | 'complete'
  visible: boolean
  speakers: ZoneSpeaker[]
  unboundCount: number
  canEditBindings: boolean
  currentMapping: Record<number, string>
  dropdown: {
    visible: boolean
    speakerId: number
    x: number
    y: number
    search: string
    focusIdx: number
  }
  filteredSpeakers: Speaker[]
  roster: string[]
  boundNames: string[]
  allSpeakers: Speaker[]
}>()

const emit = defineEmits<{
  (e: 'open-dropdown', event: MouseEvent, speakerId: number): void
  (e: 'locate-speaker', speakerId: number): void
  (e: 'skip'): void
  (e: 'confirm'): void
  (e: 'close'): void
  (e: 'reenter-binding'): void
  (e: 'select', speakerId: number, uuid: string): void
  (e: 'create-and-bind', speakerId: number, name: string): void
  (e: 'dropdown-keydown', event: KeyboardEvent): void
  (e: 'update:dropdown-search', value: string): void
  (e: 'roster-add', name: string): void
  (e: 'roster-remove', index: number): void
}>()

const { t } = useI18n()

const interactive = computed(() => props.mode === 'actionable')

// ─── 未关联说话人折叠 / Unbound speakers collapse ───
// 紧凑态下未关联说话人显示名趋同，逐枚展示信息冗余，收拢为一条可展开的折叠条
const boundSpeakers = computed(() => props.speakers.filter(s => s.bound))
const unboundSpeakers = computed(() => props.speakers.filter(s => !s.bound))
const unboundOpen = ref(false)
useEscClose(unboundOpen, () => { unboundOpen.value = false })

function toggleUnbound() {
  unboundOpen.value = !unboundOpen.value
}

function locateUnbound(speakerId: number) {
  unboundOpen.value = false
  emit('locate-speaker', speakerId)
}

// ─── 参会人 auto/manual 判断 / Roster auto/manual detection ───
function isAutoMember(name: string): boolean {
  return props.boundNames.includes(name)
}

// ─── 说话人选择器（紧凑态参会人添加） / Speaker picker (compact roster add) ───
const rosterPickerOpen = ref(false)
const rosterSearch = ref('')
const rosterPickerFocusIdx = ref(-1)
const rosterSearchRef = ref<HTMLInputElement | null>(null)

/** 可选说话人（过滤掉已在 roster 中的） / Available speakers (not yet in roster) */
const filteredRosterSpeakers = computed(() => {
  const q = rosterSearch.value.toLowerCase().trim()
  let list = props.allSpeakers.filter(s => !props.roster.includes(s.name))
  if (q) list = list.filter(s => s.name.toLowerCase().includes(q) || (s.role || '').toLowerCase().includes(q))
  return list
})

function toggleRosterPicker() {
  rosterPickerOpen.value = !rosterPickerOpen.value
  if (rosterPickerOpen.value) {
    rosterSearch.value = ''
    rosterPickerFocusIdx.value = -1
    nextTick(() => rosterSearchRef.value?.focus())
  }
}

function selectRosterSpeaker(s: Speaker) {
  emit('roster-add', s.name)
  rosterSearch.value = ''
  rosterPickerFocusIdx.value = -1
  // 保持选择器打开以便继续添加 / Keep picker open for more additions
  nextTick(() => rosterSearchRef.value?.focus())
}

async function createAndAddToRoster() {
  const name = rosterSearch.value.trim()
  if (!name) return
  try {
    await createSpeaker(name)
    emit('roster-add', name)
    rosterSearch.value = ''
    rosterPickerFocusIdx.value = -1
    nextTick(() => rosterSearchRef.value?.focus())
  } catch (e) {
    console.error('create speaker failed:', e)
  }
}

function onRosterPickerKeydown(e: KeyboardEvent) {
  const items = filteredRosterSpeakers.value
  const hasCreate = rosterSearch.value.trim() && items.length === 0
  const total = hasCreate ? 1 : items.length
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    rosterPickerFocusIdx.value = total > 0 ? (rosterPickerFocusIdx.value + 1) % total : 0
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    rosterPickerFocusIdx.value = total > 0 ? (rosterPickerFocusIdx.value <= 0 ? total - 1 : rosterPickerFocusIdx.value - 1) : 0
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (hasCreate && rosterPickerFocusIdx.value === 0) createAndAddToRoster()
    else if (rosterPickerFocusIdx.value >= 0 && rosterPickerFocusIdx.value < items.length) selectRosterSpeaker(items[rosterPickerFocusIdx.value])
  } else if (e.key === 'Escape') {
    e.preventDefault()
    rosterPickerOpen.value = false
  }
}

/** 点击外部关闭选择器 / Close picker on outside click */
function onDocClickPicker(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (rosterPickerOpen.value && !target.closest('.gs-roster-picker-wrap')) {
    rosterPickerOpen.value = false
  }
  if (unboundOpen.value && !target.closest('.gs-unbound-wrap')) {
    unboundOpen.value = false
  }
}

onMounted(() => document.addEventListener('click', onDocClickPicker))
onUnmounted(() => document.removeEventListener('click', onDocClickPicker))

// ─── 辅助函数 / Helpers ───
function dotInitial(name: string): string {
  return name.charAt(0).toUpperCase()
}

function chipBg(speakerId: number): string {
  return `${getSpeakerColor(String(speakerId))}18`
}

function chipTitle(sp: ZoneSpeaker): string {
  if (!interactive.value) return sp.displayName
  return sp.bound ? t('generating.binding.click_to_rebind') : t('generating.binding.click_to_bind')
}
</script>
