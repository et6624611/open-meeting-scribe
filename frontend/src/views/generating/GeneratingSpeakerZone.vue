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
              <!-- 左组：识别对象 + 说话时长 / Group A: speaker + talk-time bar -->
              <span class="gs-ub-who">
                <span class="gs-compact-label-dot" :style="{ background: sp.color }"></span>
                <span class="gs-compact-label-name" :style="{ color: sp.color }">{{ sp.displayName }}</span>
                <span class="gs-compact-label-bar"><span class="gs-compact-label-fill" :style="{ width: sp.pct + '%', background: sp.color }"></span></span>
              </span>
              <!-- 右组：竖线 + 声纹建议百分比 + 采纳/忽略 / Group B: divider + suggestion + actions -->
              <span v-if="vpItem(sp.sid)" class="gs-ub-vp-group">
                <span class="gs-ub-divider" aria-hidden="true"></span>
                <span class="gs-ub-vp" :class="vpItem(sp.sid)!.status === 'matched' ? 'is-matched' : 'is-weak'">
                  {{ vpItem(sp.sid)!.status === 'matched'
                    ? t('generating.voiceprint.inline_suggest', { name: vpItem(sp.sid)!.matched_name!, pct: vpPct(vpItem(sp.sid)!.similarity) })
                    : t('generating.voiceprint.inline_weak', { pct: vpPct(vpItem(sp.sid)!.similarity) }) }}
                </span>
                <button
                  v-if="canAdoptVp(vpItem(sp.sid)!)"
                  class="gs-vp-adopt"
                  :title="t('generating.voiceprint.adopt_name', { name: vpItem(sp.sid)!.matched_name! })"
                  @click.stop="emit('apply-voiceprint', sp.sid, vpItem(sp.sid)!.matched_uuid!)"
                >
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                </button>
                <button class="gs-vp-x" :title="t('generating.voiceprint.dismiss')" @click.stop="emit('dismiss-voiceprint', sp.sid)">
                  <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 3l6 6M9 3l-6 6"/></svg>
                </button>
              </span>
            </div>
          </div>
        </div>

        <!-- 分隔符 / Separator -->
        <span class="gs-compact-sep"></span>

        <!-- 参会人 chip 列表 + 选择器 + 内联输入 / Roster chips + picker + inline input -->
        <!-- 前后互斥：已绑定说话人已在主显区展示，参会人区不再重复显示 / Bound names live in the primary zone; roster shows the rest only -->
        <div class="gs-compact-roster">
          <span v-for="item in visibleRoster" :key="item.idx" class="gs-roster-chip">
            {{ item.name }}
            <button class="gs-roster-chip-x" :title="t('generating.roster.remove')" @click="emit('roster-remove', item.idx)">
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
          <!-- 声纹识别触发（紧凑态） / Voiceprint trigger in compact bar -->
          <button class="gs-roster-vp-btn" :title="t('generating.voiceprint.run')" @click.stop="emit('run-voiceprint')">
            <span v-if="voiceprintRunning" class="gs-vp-spin" aria-hidden="true"></span>
            <svg v-else width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 0 0 8 11a4 4 0 1 1 8 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 0 0 0 15.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 0 0 8 4.07M3 15.364c.64-1.319 1 2.8 1-4.364 0-1.457.39-2.823 1.07-4"/></svg>
          </button>
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
          <!-- 声纹识别：触发/重跑，运行中转圈 / Voiceprint trigger -->
          <button class="gs-vp-btn" :title="t('generating.voiceprint.run')" @click.stop="emit('run-voiceprint')">
            <span v-if="voiceprintRunning" class="gs-vp-spin" aria-hidden="true"></span>
            <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 0 0 8 11a4 4 0 1 1 8 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0 0 15.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 0 0 8 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4"/></svg>
          </button>
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
              <!-- 声纹相似度标记 / Voiceprint similarity tag -->
              <span
                v-if="vpItem(sp.sid)"
                class="gs-vp-tag"
                :class="vpItem(sp.sid)!.status === 'matched' ? 'is-matched' : 'is-weak'"
                :title="vpItem(sp.sid)!.status === 'matched'
                  ? t('generating.voiceprint.tag_matched', { pct: vpPct(vpItem(sp.sid)!.similarity) })
                  : t('generating.voiceprint.tag_unmatched', { pct: vpPct(vpItem(sp.sid)!.similarity) })"
              >
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 0 0 8 11a4 4 0 1 1 8 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0 0 15.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 0 0 8 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4"/></svg>
                {{ vpPct(vpItem(sp.sid)!.similarity) }}%
                <button class="gs-vp-x" :title="t('generating.voiceprint.dismiss')" @click.stop="emit('dismiss-voiceprint', sp.sid)">
                  <svg width="8" height="8" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 3l6 6M9 3l-6 6"/></svg>
                </button>
              </span>
              <!-- 一键采纳声纹建议 / One-click adopt -->
              <button
                v-if="vpItem(sp.sid) && canAdoptVp(vpItem(sp.sid)!)"
                class="gs-vp-adopt"
                :title="t('generating.voiceprint.adopt_name', { name: vpItem(sp.sid)!.matched_name! })"
                @click.stop="emit('apply-voiceprint', sp.sid, vpItem(sp.sid)!.matched_uuid!)"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              </button>
              <svg v-if="!sp.bound" class="bl-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
              <svg v-else class="bl-check" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              <span class="bl-locate" :title="t('generating.binding.locate')" @click.stop="emit('locate-speaker', sp.sid)">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="7"/><line x1="12" y1="1" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="23"/><line x1="1" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="23" y2="12"/></svg>
              </span>
            </span>
            <span class="gs-bar"><span class="gs-bar-fill" :style="{ width: sp.pct + '%', background: sp.color }"></span></span>
          </span>
        </div>

        <!-- 底部参会人 / Roster at bottom（前后互斥：已绑定名字由上方绑定 chips 主显，不重复） -->
        <div class="gs-roster-section" v-if="visibleRoster.length > 0">
          <span class="gs-roster-label">{{ t('generating.roster.title') }} ({{ visibleRoster.length }})</span>
          <span v-for="item in visibleRoster" :key="item.idx" class="gs-roster-chip">
            {{ item.name }}
            <button class="gs-roster-chip-x" :title="t('generating.roster.remove')" @click="emit('roster-remove', item.idx)">
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
        <!-- 声纹建议置顶项 / Voiceprint suggestion pinned to top -->
        <div
          v-if="vpItem(dropdown.speakerId)?.status === 'matched'"
          class="bt-dropdown-item is-vp-suggest"
          @click="emit('select', dropdown.speakerId, vpItem(dropdown.speakerId)!.matched_uuid!)"
        >
          <span class="bt-di-name">
            {{ vpItem(dropdown.speakerId)!.matched_name }}
            <span class="bt-vp-badge">{{ t('generating.voiceprint.suggest_badge', { pct: vpPct(vpItem(dropdown.speakerId)!.similarity) }) }}</span>
          </span>
        </div>
        <template v-if="filteredSpeakers.length > 0">
          <template v-for="(s, idx) in filteredSpeakers" :key="s.id">
            <div
              v-if="s.id !== vpItem(dropdown.speakerId)?.matched_uuid"
              class="bt-dropdown-item"
              :class="{ 'is-selected': currentMapping[dropdown.speakerId] === s.id, 'is-focused': dropdown.focusIdx === idx }"
              @click="emit('select', dropdown.speakerId, s.id)"
            >
              <span class="bt-di-name" :style="{ color: currentMapping[dropdown.speakerId] === s.id ? getSpeakerColor(String(dropdown.speakerId)) : undefined }">{{ s.name }}<span v-if="s.role" class="bt-di-role">({{ s.role }})</span></span>
            </div>
          </template>
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
import type { VoiceprintMatchItem } from '@/api/types'

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
  /** 声纹识别明细（可空） / Voiceprint match items */
  voiceprintItems: VoiceprintMatchItem[] | null
  /** 识别运行中 / Match in progress */
  voiceprintRunning: boolean
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
  /** 运行/重跑声纹识别 / Run or rerun voiceprint match */
  (e: 'run-voiceprint'): void
  /** 采纳声纹建议（直接绑定） / Adopt voiceprint suggestion */
  (e: 'apply-voiceprint', speakerId: number, uuid: string): void
  /** 忽略声纹建议（本场不再显示） / Dismiss voiceprint suggestion */
  (e: 'dismiss-voiceprint', speakerId: number): void
}>()

const { t } = useI18n()

const interactive = computed(() => props.mode === 'actionable')

// ─── 声纹建议（融入人员栏） / Voiceprint suggestions embedded in personnel bar ───
const vpMap = computed(() => {
  const m = new Map<number, VoiceprintMatchItem>()
  for (const it of props.voiceprintItems || []) m.set(it.speaker_id, it)
  return m
})

/** 该说话人的声纹建议（未绑定且命中）/ Adoptable suggestion for a speaker */
function vpItem(sid: number): VoiceprintMatchItem | undefined {
  return vpMap.value.get(sid)
}

/** 是否可一键采纳：命中、当前未绑定或绑的不是同一人 / Adoptable when matched and not already bound to them */
function canAdoptVp(it: VoiceprintMatchItem): boolean {
  return it.status === 'matched' && !!it.matched_uuid && currentBindingOf(it.speaker_id) !== it.matched_uuid
}

function currentBindingOf(sid: number): string | undefined {
  return props.currentMapping[sid]
}

function vpPct(v: number): number {
  return Math.round(v * 100)
}

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

// ─── 参会人展示口径（前后互斥）/ Visible roster (mutually exclusive with primary bound display) ───
// 已绑定说话人由主显区（紧凑态标签 / 绑定 chips）承载，参会人区只展示其余名字；idx 保留原列表下标供删除
const visibleRoster = computed(() =>
  props.roster
    .map((name, idx) => ({ name, idx }))
    .filter(item => !props.boundNames.includes(item.name))
)

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
