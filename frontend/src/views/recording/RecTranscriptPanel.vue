<template>
  <div class="rec-transcript">
    <div class="rec-transcript-header">
      <div class="rec-header-row">
        <div class="rec-transcript-title">{{ t('recording.tab.transcript') }}</div>
        <!-- 时间轴导航（填充标题与按钮之间的剩余宽度） / Timeline navigation (fills remaining width between title and buttons) -->
        <RecTimeline
          v-if="lines.length > 0"
          ref="timelineRef"
          :lines="lines"
          :chapters="chapters"
          :total-duration-ms="totalDurationMs"
          :current-time-ms="currentTimeMs"
          :marker-mode="markerMode"
          :has-note-at="hasNoteAt"
          @seek-to-time="onSeekToTime"
        />
        <div class="rec-transcript-actions">
        <!-- 三层分段控件：书面版（会中锁定）/ 清理版（默认）/ 原文 / Layer segmented control: formal (locked live) / cleaned (default) / verbatim -->
        <div class="rec-layer-seg" role="tablist" :aria-label="t('recording.layer.list_label')" @keydown="onSegKeydown">
          <button
            type="button"
            role="tab"
            ref="segFormalBtn"
            class="rec-layer-btn"
            :class="{ 'is-active': layerView === 'formal' }"
            :aria-selected="layerView === 'formal'"
            @click="layerView = 'formal'"
          >
            <svg v-if="!formalUnlocked" class="rec-layer-lock" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            {{ t('recording.layer.formal') }}
            <span class="rec-layer-ai">AI</span>
          </button>
          <button
            type="button"
            role="tab"
            ref="segCleanBtn"
            class="rec-layer-btn"
            :class="{ 'is-active': layerView === 'clean' }"
            :aria-selected="layerView === 'clean'"
            :disabled="!cleanupEnabled"
            @click="layerView = 'clean'"
          >{{ t('recording.layer.clean') }}</button>
          <button
            type="button"
            role="tab"
            ref="segRawBtn"
            class="rec-layer-btn"
            :class="{ 'is-active': layerView === 'raw' }"
            :aria-selected="layerView === 'raw'"
            @click="layerView = 'raw'"
          >{{ t('recording.layer.raw') }}</button>
        </div>
        <!-- 显示/隐藏原文 / Show/hide transcript -->
        <button class="action-btn" :class="{ 'is-active': showTranscript }" @click="$emit('update:showTranscript', !showTranscript)" :title="showTranscript ? t('recording.transcript.hide_title') : t('recording.transcript.show_title')">
          <svg class="toggle-icon-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
          <svg class="toggle-icon-on" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          <span>{{ showTranscript ? t('recording.transcript.hide') : t('recording.transcript.show') }}</span>
        </button>
        <!-- 翻译更多菜单 / Translation more menu -->
        <div class="transcript-more-wrap">
          <button ref="moreBtn" class="transcript-more-btn" v-bind="moreTriggerAttrs" @click="toggleMore" :title="t('common.action.more')" :aria-label="t('common.action.more')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
          </button>
          <Teleport to="body">
            <div ref="moreDropdown" class="transcript-more-dropdown" v-bind="moreMenuAttrs" :class="{ 'is-open': showMore }">
              <!-- 翻译开关 / Translation toggle -->
              <div class="transcript-more-item transcript-more-toggle">
                <div
                  class="toggle-switch"
                  role="menuitemcheckbox"
                  tabindex="0"
                  :aria-checked="translateEnabled"
                  :class="{ 'is-on': translateEnabled }"
                  @click="$emit('toggleTranslate')"
                  @keydown.enter.prevent="$emit('toggleTranslate')"
                  @keydown.space.prevent="$emit('toggleTranslate')"
                >
                  <div class="toggle-switch-track">
                    <div class="toggle-switch-knob"></div>
                  </div>
                  <span class="toggle-switch-label">{{ t('recording.translate.title') }}</span>
                </div>
                <span v-if="translateEnabled" class="transcript-more-lang">{{ targetLangLabel }}</span>
              </div>
              <!-- 语言选择 / Language selection -->
              <template v-if="translateEnabled">
                <button v-for="lang in supportedLanguages" :key="lang.code" class="transcript-more-item transcript-more-lang-item" role="menuitem" :aria-selected="lang.code === targetLang" :class="{ 'is-selected': lang.code === targetLang }" @click="$emit('setTranslateLang', lang.code); closeMore()">
                  {{ lang.label }}
                  <svg v-if="lang.code === targetLang" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                </button>
              </template>
              <!-- 文本处理 / Text processing -->
              <div class="transcript-more-sep" role="separator"></div>
              <div class="transcript-more-label">{{ t('recording.layer.more_section') }}</div>
              <!-- 口语清理开关（本地规则，默认开，逃生通道）/ Spoken cleanup toggle (local rules, default on, escape hatch) -->
              <div class="transcript-more-item transcript-more-toggle">
                <div
                  class="toggle-switch"
                  role="menuitemcheckbox"
                  tabindex="0"
                  :aria-checked="cleanupEnabled"
                  :class="{ 'is-on': cleanupEnabled }"
                  @click="toggleCleanup"
                  @keydown.enter.prevent="toggleCleanup"
                  @keydown.space.prevent="toggleCleanup"
                >
                  <div class="toggle-switch-track">
                    <div class="toggle-switch-knob"></div>
                  </div>
                  <span class="toggle-switch-label">
                    {{ t('recording.layer.cleanup_name') }}
                    <span class="transcript-more-side">{{ t('recording.layer.cleanup_side') }}</span>
                  </span>
                </div>
              </div>
              <div class="transcript-more-sub">{{ t('recording.layer.cleanup_sub') }}</div>
              <!-- AI 书面化：会中禁用，仅会后可用 / AI formal rewrite: disabled live, post-meeting only -->
              <button class="transcript-more-item transcript-more-item-disabled" type="button" disabled :aria-disabled="true">
                <span class="transcript-more-item-text">
                  <span class="transcript-more-item-name">
                    {{ t('recording.layer.formal_name') }}
                    <span class="transcript-more-side">{{ t('recording.layer.formal_side') }}</span>
                  </span>
                  <span class="transcript-more-sub">{{ t('recording.layer.formal_sub') }}</span>
                </span>
                <span class="transcript-more-go">{{ t('recording.layer.formal_post_only') }}</span>
              </button>
            </div>
          </Teleport>
        </div>
        </div>
      </div>
    </div>
    <!-- 本地模式声明：按 realtime_segments 开关区分「逐句上屏」与「录音后本机批转写」两种口径 / Local mode notice: copy follows the realtime_segments flag — incremental display vs. post-recording on-device batch -->
    <div v-if="isLocalMode" class="rec-local-batch-banner" role="status">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
      <span>{{ t(localSegmentsEnabled ? 'recording.transcript.local_realtime_notice' : 'recording.transcript.local_batch_notice') }}</span>
    </div>
    <!-- 章节条 / Chapter strip -->
    <div class="rec-chapter-strip" v-if="chapters.length > 0">
      <div class="rec-chapter-dots"><span v-for="(_, i) in chapters" :key="i" class="rec-ch-dot" :class="{ 'is-current': i === chapters.length - 1 }"></span></div>
      <div class="rec-chapter-current">
        <span class="rec-chapter-num">{{ chapters.length }}</span>
        <span class="rec-chapter-title">{{ chapters[chapters.length - 1]?.title || t('recording.chapter.discussing') }}</span>
      </div>
    </div>
    <!-- 书面版视图（WP-1 会中锁定引导；生成能力属 WP-2） / Formal view (locked-live notice in WP-1; generation lands in WP-2) -->
    <div v-if="layerView === 'formal'" class="rec-formal-lock">
      <svg class="rec-formal-lock-ico" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
      <div class="rec-formal-lock-title">{{ t('recording.layer.formal_locked_title') }}</div>
      <div class="rec-formal-lock-desc">{{ t('recording.layer.formal_locked_desc') }}</div>
    </div>
    <!-- 转写列表（含 listening 指示器 / 空状态，统一虚拟滚动） / Transcript list (with listening indicator / empty state, unified virtual scroll) -->
    <div v-else class="rec-scroll-wrap">
      <DynamicScroller
        ref="scrollerRef"
        class="rec-transcript-body"
        :items="mixedItems"
        :min-item-size="48"
        key-field="key"
        @scroll="onScrollerScroll"
        @wheel="onUserWheel"
      >
        <template #default="{ item, index, active }">
          <DynamicScrollerItem
            :item="item"
            :active="active"
            :size-dependencies="[item.type === 'chapter' && expandedChapters.has(item.chapterIdx), showTranscript, markerMode, layerView, cleanupEnabled, item.type === 'line' && peeked.has(item.lineIdx)]"
            :data-index="index"
          >
            <div class="rec-transcript-item">
          <!-- 章节分隔卡片 / Chapter divider card -->
          <div v-if="item.type === 'chapter'" class="chapter-divider" :class="{ 'is-current': item.chapterIdx === chapters.length - 1, 'is-expanded': expandedChapters.has(item.chapterIdx) }" @click="$emit('toggleChapter', item.chapterIdx)">
            <div class="chapter-header">
              <div class="chapter-number">{{ chapters[item.chapterIdx].id || item.chapterIdx + 1 }}</div>
              <div class="chapter-info">
                <div class="chapter-title">{{ chapters[item.chapterIdx].title }}</div>
                <div class="chapter-meta">
                  <span>{{ formatTime(chapters[item.chapterIdx].start_ms) }}</span>
                  <template v-if="chapters[item.chapterIdx].end_ms"><span class="sep">–</span><span>{{ formatTime(chapters[item.chapterIdx].end_ms || 0) }}</span></template>
                  <template v-if="(chapters[item.chapterIdx].key_points || []).length"><span class="sep">·</span><span>{{ t('recording.chapter.key_points_count', { count: (chapters[item.chapterIdx].key_points || []).length }) }}</span></template>
                </div>
                <div v-if="chapters[item.chapterIdx].summary" class="chapter-summary-text">{{ chapters[item.chapterIdx].summary }}</div>
              </div>
              <div class="chapter-chevron"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg></div>
            </div>
            <div v-if="expandedChapters.has(item.chapterIdx)" class="chapter-body"><div class="chapter-body-inner"><div class="chapter-key-points" v-if="chapters[item.chapterIdx].key_points?.length"><div class="chapter-key-points-title">{{ t('recording.chapter.key_points') }}</div><div v-for="(p, pi) in chapters[item.chapterIdx].key_points" :key="pi" class="chapter-key-point">{{ p }}</div></div></div></div>
          </div>
          <!-- 转写行 / Transcript line -->
          <div v-else-if="item.type === 'line'" class="rec-line" :class="{ 'is-me': isMe(lineOf(item).speaker_id), 'is-located': locateId === lineOf(item).speaker_id, 'is-dimmed': locateId !== null && locateId !== lineOf(item).speaker_id }">
            <div class="rec-line-avatar" :style="{ background: speakerColor(lineOf(item).speaker_id) }">{{ avatarInitial(getSpeakerName(lineOf(item)), lineOf(item).speaker_id) }}</div>
            <div class="rec-line-content">
              <div class="rec-line-head">
                <span class="rec-line-speaker" :style="{ '--spk-color': speakerColor(lineOf(item).speaker_id) }" @click.stop="$emit('openBind', lineOf(item).speaker_id)">{{ getSpeakerName(lineOf(item)) }}</span>
                <button v-if="!locateId || locateId === lineOf(item).speaker_id" class="rec-line-locate-btn" @click.stop="$emit('toggleLocate', lineOf(item).speaker_id)" :title="t('recording.speaker.locate')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg></button>
                <!-- 清理视图：已清理行的原文回览入口 / Clean view: peek-verbatim entry on cleaned lines -->
                <button
                  v-if="isCleanedView(lineOf(item))"
                  type="button"
                  class="rec-line-clean-tag"
                  :aria-expanded="peeked.has(item.lineIdx)"
                  :title="t('recording.layer.tag_cleaned_title')"
                  @click.stop="togglePeek(item.lineIdx)"
                >{{ t('recording.layer.tag_cleaned') }}</button>
              </div>
              <div class="rec-line-body">
                <span v-if="translationDisplay !== 'translation'" class="rec-line-text">{{ displayText(lineOf(item)) }}</span>
                <span v-if="translationDisplay !== 'original' && translationMap.get(item.lineIdx)" class="rec-line-translation">{{ translationMap.get(item.lineIdx) }}</span>
              </div>
              <!-- 原文回览块（只读原文 + 清理明细）/ Verbatim peek block (read-only raw + cleanup detail) -->
              <div v-if="isCleanedView(lineOf(item)) && peeked.has(item.lineIdx)" class="rec-peek">
                <div class="rec-peek-label">{{ t('recording.layer.peek_label') }}</div>
                <div class="rec-peek-text">{{ lineOf(item).text }}</div>
                <div v-if="cleanupRuleText(lineOf(item).clean_ops)" class="rec-peek-rule">{{ cleanupRuleText(lineOf(item).clean_ops) }}</div>
              </div>
              <div v-if="notesByLine[item.lineIdx]" class="note-inline-card">
                <span class="note-inline-text">{{ notesByLine[item.lineIdx] }}</span>
                <button class="note-inline-delete" @click.stop="$emit('deleteNote', item.lineIdx)" :title="t('recording.notes.delete')"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
              </div>
            </div>
          </div>
          <!-- 正在聆听指示器 / Listening indicator -->
          <div v-else-if="item.type === 'listening'" class="rec-line rec-line-listening">
            <div class="rec-line-avatar" style="background: var(--subtle)">
              <span class="listening-dots"><span></span><span></span><span></span></span>
            </div>
            <div class="rec-line-content">
              <div class="rec-line-head"><span class="rec-line-speaker">…</span></div>
              <div class="rec-line-body"><span class="rec-line-text rec-line-text--listening">{{ t('recording.transcript.listening') }}</span></div>
            </div>
          </div>
          <!-- 空状态（本地批转写降级时换口径：会中不出字属正常） / Empty state (batch-degraded local mode: no live text by design) -->
          <div v-else-if="item.type === 'empty'" class="rec-empty">
            <p>{{ t(localBatchDegraded ? 'recording.transcript.batch_empty' : 'recording.transcript.empty') }}</p>
            <p class="rec-empty-hint">{{ t(localBatchDegraded ? 'recording.transcript.batch_empty_hint' : 'recording.transcript.empty_hint') }}</p>
          </div>
            </div>
          </DynamicScrollerItem>
        </template>
      </DynamicScroller>
      <button class="rec-jump-latest" :class="{ 'is-visible': showJumpBtn }" @click="jumpToLatest" :title="t('recording.jump_latest')">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></svg>
      </button>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import { getSpeakerColor } from '@/utils/speakerColors'
import RecTimeline from './RecTimeline.vue'
import { usePopMenu } from '@/composables/usePopMenu'
import { useEngineStore } from '@/stores/engine'
import type { TranscriptLine } from '@/composables/useWebSocket'
import type { SupportedLanguage } from '@/composables/useTranslation'
import { fetchSettings, saveSettings } from '@/api/settings'
import { cleanupRuleText as formatCleanupRule, segKeydownHandler } from '@/utils/transcriptLayers'

const { t } = useI18n()

// 本地模式口径判定：mode + realtime_segments.enabled 双因子（WP-I 开启＝逐句上屏；
// 关闭＝WP-H 设计内降级，录音后本机统一批转写，会中不出字）/ Local-mode wording
// driven by mode + realtime_segments.enabled (WP-I on = incremental; off = WP-H batch)
const engineStore = useEngineStore()

// ── 转写三层视图（PLAN-TRANSCRIPT-LAYERING WP-1） ──
// formal=书面版（WP-1 会中恒锁定，WP-2 接入会后生成）；clean=本地清理版（默认）；raw=逐字稿原文
type LayerView = 'formal' | 'clean' | 'raw'
const layerView = ref<LayerView>('clean')
const cleanupEnabled = ref(true)
const cleanupSaving = ref(false)
// WP-1：会中面板书面版永不解锁 / WP-1: formal layer stays locked on the live panel
const formalUnlocked = false
const peeked = ref<Set<number>>(new Set())

// 分段控件按钮 refs（键盘导航用） / Segmented-control button refs (keyboard nav)
const segFormalBtn = ref<HTMLButtonElement | null>(null)
const segCleanBtn = ref<HTMLButtonElement | null>(null)
const segRawBtn = ref<HTMLButtonElement | null>(null)

onMounted(() => {
  engineStore.load()
  // 读入口语清理开关（失败按默认开静默处理）/ Load cleanup escape-hatch state (default-on on failure)
  fetchSettings()
    .then((s) => {
      const enabled = s.transcript?.cleanup?.enabled
      if (typeof enabled === 'boolean') {
        cleanupEnabled.value = enabled
        if (!enabled && layerView.value === 'clean') layerView.value = 'raw'
      }
    })
    .catch(() => {})
})

// 关闭清理：收敛回原文视图并清空原文回览 / When cleanup is off, collapse to verbatim and close peeks
watch(cleanupEnabled, (on) => {
  if (!on) {
    peeked.value = new Set()
    if (layerView.value === 'clean') layerView.value = 'raw'
  }
})

/** 乐观更新口语清理开关，失败回滚（会中只改显示；后端按会话快照继续推送）
 *  Optimistic cleanup toggle with rollback (live: display-only; backend keeps session snapshot) */
async function toggleCleanup() {
  if (cleanupSaving.value) return
  const prev = cleanupEnabled.value
  const next = !prev
  cleanupEnabled.value = next
  cleanupSaving.value = true
  try {
    await saveSettings({ transcript: { cleanup: { enabled: next } } })
  } catch (err) {
    cleanupEnabled.value = prev
    console.error('[transcript] save cleanup preference failed:', err)
  } finally {
    cleanupSaving.value = false
  }
}

function togglePeek(idx: number) {
  const next = new Set(peeked.value)
  if (next.has(idx)) next.delete(idx)
  else next.add(idx)
  peeked.value = next
}

/** 当前行是否处于「已清理」展示态（清理视图 + 开关开 + 该行确有清理版） */
function isCleanedView(line: TranscriptLine): boolean {
  return layerView.value === 'clean' && cleanupEnabled.value && typeof line.clean_text === 'string'
}

/** 行的展示文本：清理视图取 clean_text（无则回落原文），其余恒原文 */
function displayText(line: TranscriptLine): string {
  if (isCleanedView(line)) return line.clean_text as string
  return line.text
}

/** 清理明细：按规则聚合 ops 为一句可读说明 / Aggregate cleanup ops into a human-readable line */
function cleanupRuleText(ops?: TranscriptLine['clean_ops']): string {
  return formatCleanupRule(t, ops, 'recording')
}

/** tablist 键盘导航（←/→ 循环跳过禁用项，Home/End，自动激活）/ Tablist keyboard nav */
const onSegKeydown = segKeydownHandler([segFormalBtn, segCleanBtn, segRawBtn])
const isLocalMode = computed(() => engineStore.status?.mode === 'local')
const localSegmentsEnabled = computed(() => engineStore.status?.realtime_segments_enabled === true)
const localBatchDegraded = computed(() => isLocalMode.value && !localSegmentsEnabled.value)

// ── 更多菜单 / More menu ──
const moreBtn = ref<HTMLElement | null>(null)
const moreDropdown = ref<HTMLElement | null>(null)
const { visible: showMore, toggle: toggleMore, close: closeMore, triggerAttrs: moreTriggerAttrs, menuAttrs: moreMenuAttrs } = usePopMenu(moreDropdown, moreBtn)

const props = defineProps<{
  lines: TranscriptLine[]
  listening: boolean
  chapters: Array<{ id?: number; title: string; start_ms: number; end_ms?: number; key_points?: string[]; summary?: string }>
  showTranscript: boolean
  markerMode: boolean
  notesByLine: Record<number, string>
  compressedCount: number
  expandedChapters: Set<number>
  locateId: number | null
  totalDurationMs: number
  currentTimeMs: number
  getSpeakerName: (line: TranscriptLine) => string
  isMe: (speakerId: number) => boolean
  hasNoteAt: (idx: number) => boolean
  chapterStartMap: Map<number, { title: string; chapterIdx: number }>
  translationMap: Map<number, string>
  translationDisplay: 'original' | 'translation' | 'bilingual'
  translateEnabled: boolean
  targetLang: string
  targetLangLabel: string
  supportedLanguages: SupportedLanguage[]
}>()

defineEmits<{
  (e: 'update:showTranscript', val: boolean): void
  (e: 'update:markerMode', val: boolean): void
  (e: 'toggleChapter', idx: number): void
  (e: 'openBind', asrId: number): void
  (e: 'toggleLocate', id: number): void
  (e: 'deleteNote', idx: number): void
  (e: 'toggleTranslate'): void
  (e: 'setTranslateLang', lang: string): void
}>()

// ── Refs ──
// 组件引用 / Component refs
const scrollerRef = ref<InstanceType<typeof DynamicScroller> | null>(null)
const timelineRef = ref<InstanceType<typeof RecTimeline> | null>(null)

// ── 混合列表：章节分隔 + 转写行 + 聆听指示器 + 空状态 / Mixed list: chapter divider + transcript lines + listening indicator + empty state ──
type MixedItem =
  | { type: 'chapter'; key: string; chapterIdx: number; size: number }
  | { type: 'line'; key: string; lineIdx: number; size: number }
  | { type: 'listening'; key: string; size: number }
  | { type: 'empty'; key: string; size: number }

// ── 行高预估辅助（提升 scrollToEnd 定位精度） / Row height estimation helpers (improve scrollToEnd accuracy) ──
/** 估算文本在气泡内的换行数（气泡内宽 ≈ 360px，fs-13 中文 ≈ 13px / 字符） / Estimate wrapped lines in bubble (bubble inner width ≈ 360px, fs-13 CJK ≈ 13px/char) */
function estTextLines(text: string, charsPerLine = 38): number {
  if (!text) return 0
  let lines = 0
  for (const seg of text.split('\n')) {
    lines += Math.max(1, Math.ceil(seg.length / charsPerLine))
  }
  return lines
}

/** 预估单条转写行的渲染高度（ResizeObserver 实测后会被覆盖） / Estimate rendered height of a transcript line (overridden by ResizeObserver measurements) */
function estimateLineHeight(idx: number): number {
  const line = props.lines[idx]
  if (!line) return 80

  // 头像(32px) 与 content 列间距(10px) + content 列内部： / Avatar(32px) + content column gap(10px) + content column inner:
  // head(18px) + gap(4px) + 气泡：border(2) + padding-v(16) + 文本行高 / head(18px) + gap(4px) + bubble: border(2) + padding-v(16) + text line height
  let h = 32 + 10 + 18 + 4

  // 气泡：border(2) + padding-v(16) + 文本行高（按当前分层视图展示文本估算）/ Bubble height (estimate by the active layer's displayed text)
  const textLineH = 13 * 1.6           // fs-13 × line-height 1.6 ≈ 20.8
  const textLines = estTextLines(displayText(line))
  h += 2 + 16 + textLines * textLineH

  // 原文回览块展开：margin(8) + label(14) + 原文行 + 明细行(≤1) + 内边距(~20) / Expanded verbatim peek block
  if (isCleanedView(line) && peeked.value.has(idx)) {
    h += 8 + 14 + estTextLines(line.text) * textLineH + (line.clean_ops?.length ? 18 : 0) + 20
  }

  // 翻译行（双语或纯译文模式下追加） / Translation line (appended in bilingual or translation-only mode)
  if (props.translationDisplay !== 'original') {
    const tr = props.translationMap.get(idx)
    if (tr) {
      const trLineH = 12 * 1.5         // fs-12 × line-height 1.5 = 18
      h += 4 + estTextLines(tr) * trLineH // 4px margin-top
    }
  }

  // 内联笔记卡片 / Inline note card
  if (props.notesByLine[idx]) {
    h += 4 + 12 + 18                   // margin-top + padding + 内容
  }

  // content 列 padding-bottom(--s-4 = 16px) / Content column padding-bottom(--s-4 = 16px)
  h += 16
  return Math.max(48, Math.ceil(h))
}

const mixedItems = computed<MixedItem[]>(() => {
  const items: MixedItem[] = []
  if (!props.showTranscript && props.chapters.length === 0) return items

  for (let i = 0; i < props.lines.length; i++) {
    const chStart = props.chapterStartMap.get(i)
    if (chStart) {
      const isExpanded = props.expandedChapters.has(chStart.chapterIdx)
      // 预计算章节卡片高度（ResizeObserver 启动后会用实测值覆盖） / Pre-calculate chapter card height (overridden by ResizeObserver once active)
      // 折叠：margin(16) + header padding(24) + content(~56) ≈ 96px / Collapsed: margin(16) + header padding(24) + content(~56) ≈ 96px
      // 展开：折叠高度 + border(1) + key-points-inner(~110) ≈ 208px / Expanded: collapsed height + border(1) + key-points-inner(~110) ≈ 208px
      const chHeight = isExpanded ? 208 : 96
      items.push({ type: 'chapter', key: `ch-${chStart.chapterIdx}`, chapterIdx: chStart.chapterIdx, size: chHeight })
    }
    if (props.showTranscript) {
      if (props.markerMode && !props.hasNoteAt(i)) continue
      items.push({ type: 'line', key: `ln-${i}`, lineIdx: i, size: estimateLineHeight(i) })
    }
  }
  // 尾部：聆听指示器 或 空状态（合并进虚拟滚动，消除独立 tail 区域） / Tail: listening indicator or empty state (merged into virtual scroll, eliminating separate tail area)
  if (props.listening) {
    items.push({ type: 'listening', key: 'listening', size: 60 })
  } else if (items.length === 0) {
    items.push({ type: 'empty', key: 'empty', size: 80 })
  }
  return items
})

// ── 清理 / Cleanup ──
onUnmounted(() => {
  autoFollow.value = false
  cancelAnimationFrame(settleRaf1)
  cancelAnimationFrame(settleRaf2)
  clearTimeout(settleTimer)
})

// 追踪上一次 expandedChapters 的快照，用于检测变化并强制 remeasure / Track previous expandedChapters snapshot to detect changes and force remeasure
let prevExpandedKeys = new Set<number>()
watch(() => [...props.expandedChapters], (newKeys: number[]) => {
  const added = newKeys.filter((k: number) => !prevExpandedKeys.has(k))
  const removed = [...prevExpandedKeys].filter((k: number) => !newKeys.includes(k))
  if (added.length > 0 || removed.length > 0) {
    // 延迟一帧确保 DOM 已更新，然后强制 scroller 重新计算所有 item 高度 / Delay one frame to ensure DOM is updated, then force scroller to recalculate all item heights
    nextTick(() => {
      requestAnimationFrame(() => {
        ;(scrollerRef.value as any)?.updateVisibleItems?.(true)
      })
    })
  }
  prevExpandedKeys = new Set(newKeys)
}, { deep: true })

// ── 自动滚动（会中实时跟随） / Auto-scroll (live in-meeting follow) ──
const autoFollow = ref(true)
const showJumpBtn = ref(false)
const NEAR_BOTTOM_PX = 80

/* 程序性滚动窗口：scrollToBottom 及其高度校正会触发 scroll 事件，
   窗口内不把它们误判为「用户上滑」而中断跟随（A2 缺陷根因之一）。
   Programmatic-scroll window: scroll events fired by scrollToBottom and its
   size-correction passes must not be misread as user scroll-up. */
let programmaticUntil = 0
function markProgrammatic() { programmaticUntil = performance.now() + 300 }

function scrollerEl(): HTMLElement | null {
  return (scrollerRef.value?.$el as HTMLElement) ?? null
}

function isNearBottom(el: HTMLElement): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX
}

let settleRaf1 = 0
let settleRaf2 = 0
let settleTimer = 0

/** 滚到真实底部：虚拟列表行高「先估算后实测」，scrollTop 会被低估的 scrollHeight 截断，
    故用 双帧 + 250ms 三段校正，高度收敛后视口仍钉在底部（替代 scrollToItem(len-1)，
    后者把末项对齐到视口顶部而非底部）。
    Scroll to the true bottom with a 3-pass correction (double rAF + 250ms timeout),
    because virtual-scroller estimated heights truncate the first scrollTop assignment. */
function scrollToBottom() {
  const el = scrollerEl()
  if (!el) return
  markProgrammatic()
  el.scrollTop = el.scrollHeight
  cancelAnimationFrame(settleRaf1)
  cancelAnimationFrame(settleRaf2)
  settleRaf1 = requestAnimationFrame(() => {
    settleRaf2 = requestAnimationFrame(() => {
      const e2 = scrollerEl()
      if (!e2 || !autoFollow.value) return
      markProgrammatic()
      e2.scrollTop = e2.scrollHeight
    })
  })
  clearTimeout(settleTimer)
  settleTimer = window.setTimeout(() => {
    const e3 = scrollerEl()
    if (!e3 || !autoFollow.value || isNearBottom(e3)) return
    markProgrammatic()
    e3.scrollTop = e3.scrollHeight
  }, 250)
}

function onScrollerScroll(e: Event) {
  const el = e.target as HTMLElement
  if (!el) return
  if (isNearBottom(el)) {
    // 回到底部即恢复跟随（含用户手动下滑回底） / Near bottom → resume follow
    autoFollow.value = true
    showJumpBtn.value = false
  } else if (performance.now() >= programmaticUntil) {
    // 仅用户滚动可中断跟随；程序性校正窗口内不中断 / Only user scrolls break follow
    autoFollow.value = false
    showJumpBtn.value = true
  }
}

/** 用户滚轮上滑 → 立即暂停跟随（不等 scroll 事件，避免与自动滚底竞争）
    Wheel-up → pause follow immediately, no race with auto-scroll */
function onUserWheel(e: WheelEvent) {
  if (e.deltaY < 0 && autoFollow.value) {
    autoFollow.value = false
    showJumpBtn.value = mixedItems.value.length > 0
  }
}

function jumpToLatest() {
  autoFollow.value = true
  showJumpBtn.value = false
  scrollToBottom()
}

// 列表增长（新行到达 / 末行原地合并变长 / 聆听指示器出现）→ 自动滚底。
// 只看 props，不触碰 realtime 上屏链路（WP-I 在途区）。
// List growth (new line / tail-line merge growth / listening indicator) → follow bottom.
// Reads props only; does not touch the realtime ingestion chain (WP-I in-flight area).
watch(
  () => [props.lines.length, props.lines[props.lines.length - 1]?.text.length ?? 0, props.listening] as const,
  () => {
    if (!autoFollow.value) return
    nextTick(() => scrollToBottom())
  }
)

// 分层视图/清理开关切换：展示文本与 peek 块改变行高，强制重测并校正贴底
// Layer/cleanup switching changes line heights — force remeasure and re-attach to bottom.
watch([layerView, cleanupEnabled, peeked], () => {
  nextTick(() => {
    requestAnimationFrame(() => {
      ;(scrollerRef.value as any)?.updateVisibleItems?.(true)
      if (autoFollow.value) scrollToBottom()
    })
  })
})

// ── 辅助函数 / Helper functions ──
function lineOf(item: MixedItem): TranscriptLine {
  if (item.type !== 'line') return { speaker_id: 0, speaker_name: '', text: '', isFinal: true }
  return props.lines[item.lineIdx] ?? { speaker_id: 0, speaker_name: '', text: '', isFinal: true }
}

function speakerColor(sid: string | number): string { return getSpeakerColor(sid) }

/** 头像首字：真名取首字符；未识别取中性符（REQ-SPK-RN D5：禁用编号数字） */
function avatarInitial(name: string, _speakerId: number): string {
  if (name && name.trim()) return name.trim()[0]
  return t('recording.speaker.unid_initial')
}

function formatTime(ms: number): string {
  const sec = Math.floor(ms / 1000)
  const m = Math.floor(sec / 60), s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// ── 时间轴跳转 / Timeline jump ──
function onSeekToTime(timeMs: number) {
  const idx = timelineRef.value?.findLineIndexByTime(timeMs) ?? 0
  scrollToLineIndex(idx)
  autoFollow.value = false
}

function scrollToLineIndex(lineIdx: number) {
  const items = mixedItems.value
  const pos = items.findIndex(it => it.type === 'line' && (it as { type: 'line'; key: string; lineIdx: number }).lineIdx >= lineIdx)
  if (pos >= 0) {
    (scrollerRef.value as any)?.scrollToItem(pos)
    autoFollow.value = false
  }
}

// ── 暴露给父组件 / Expose to parent component ──
const bodyRef = computed(() => scrollerRef.value?.$el as HTMLElement | null)

defineExpose({
  bodyRef,
  scrollerRef,
  scrollToLineIndex,
  scrollToItem: (pos: number) => { (scrollerRef.value as any)?.scrollToItem(pos); autoFollow.value = false },
  scrollToEnd: () => { scrollToBottom() },
  jumpToLatest,
})
</script>
