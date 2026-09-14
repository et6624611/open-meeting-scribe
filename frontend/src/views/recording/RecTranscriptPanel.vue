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
        <!-- 统一按钮组：翻译 + 显示/隐藏 / Unified button group: translation + show/hide -->
        <div class="transcript-action-group">
          <div class="translate-wrap">
            <div
              class="toggle-switch"
              :class="{ 'is-on': translateEnabled }"
              :title="translateEnabled ? t('recording.translate.disable') : t('recording.translate.enable')"
              @click="$emit('toggleTranslate')"
            >
              <div class="toggle-switch-track">
                <div class="toggle-switch-knob"></div>
              </div>
            </div>
            <span class="action-label">{{ t('recording.translate.title') }}</span>
            <button
              v-if="translateEnabled"
              class="action-lang-btn"
              :title="t('recording.translate.target_lang')"
              @click="showTranslateMenu = !showTranslateMenu"
            >
              {{ targetLangLabel }}
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <div v-if="showTranslateMenu" class="translate-dropdown">
              <div class="translate-dropdown-title">{{ t('recording.translate.target_lang') }}</div>
              <button v-for="lang in supportedLanguages" :key="lang.code" class="translate-dropdown-item" :class="{ 'is-selected': lang.code === targetLang }" @click="$emit('setTranslateLang', lang.code); showTranslateMenu = false">
                {{ lang.label }}
                <svg v-if="lang.code === targetLang" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
              </button>
            </div>
          </div>
          <div class="action-divider"></div>
          <button class="action-btn" :class="{ 'is-active': showTranscript }" @click="$emit('update:showTranscript', !showTranscript)" :title="showTranscript ? t('recording.transcript.hide_title') : t('recording.transcript.show_title')">
            <svg class="toggle-icon-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
            <svg class="toggle-icon-on" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            <span>{{ showTranscript ? t('recording.transcript.hide') : t('recording.transcript.show') }}</span>
          </button>
        </div>
        </div>
      </div>
    </div>
    <!-- 章节条 / Chapter strip -->
    <div class="rec-chapter-strip" v-if="chapters.length > 0">
      <div class="rec-chapter-dots"><span v-for="(_, i) in chapters" :key="i" class="rec-ch-dot" :class="{ 'is-current': i === chapters.length - 1 }"></span></div>
      <div class="rec-chapter-current">
        <span class="rec-chapter-num">{{ chapters.length }}</span>
        <span class="rec-chapter-title">{{ chapters[chapters.length - 1]?.title || t('recording.chapter.discussing') }}</span>
      </div>
    </div>
    <!-- 转写列表（含 partial / 空状态，统一虚拟滚动） / Transcript list (with partial / empty state, unified virtual scroll) -->
    <div class="rec-scroll-wrap">
      <DynamicScroller
        ref="scrollerRef"
        class="rec-transcript-body"
        :items="mixedItems"
        :min-item-size="48"
        key-field="key"
        @scroll="onScrollerScroll"
      >
        <template #default="{ item, index, active }">
          <DynamicScrollerItem
            :item="item"
            :active="active"
            :size-dependencies="[item.type === 'chapter' && expandedChapters.has(item.chapterIdx), showTranscript, markerMode]"
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
              </div>
              <div class="rec-line-body">
                <span v-if="translationDisplay !== 'translation'" class="rec-line-text">{{ lineOf(item).text }}</span>
                <span v-if="translationDisplay !== 'original' && translationMap.get(item.lineIdx)" class="rec-line-translation">{{ translationMap.get(item.lineIdx) }}</span>
              </div>
              <div v-if="notesByLine[item.lineIdx]" class="note-inline-card">
                <span class="note-inline-text">{{ notesByLine[item.lineIdx] }}</span>
                <button class="note-inline-delete" @click.stop="$emit('deleteNote', item.lineIdx)" :title="t('recording.notes.delete')"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
              </div>
            </div>
          </div>
          <!-- 实时部分转写 / Real-time partial transcript -->
          <div v-else-if="item.type === 'partial'" class="rec-line rec-line-partial">
            <div class="rec-line-avatar" style="background: var(--subtle)">…</div>
            <div class="rec-line-content">
              <div class="rec-line-head"><span class="rec-line-speaker">…</span></div>
              <div class="rec-line-body"><span class="rec-line-text">{{ partialText }}</span></div>
            </div>
          </div>
          <!-- 空状态 / Empty state -->
          <div v-else-if="item.type === 'empty'" class="rec-empty">
            <p>{{ t('recording.transcript.empty') }}</p>
            <p class="rec-empty-hint">{{ t('recording.transcript.empty_hint') }}</p>
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
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import { getSpeakerColor } from '@/utils/speakerColors'
import RecTimeline from './RecTimeline.vue'
import type { TranscriptLine } from '@/composables/useWebSocket'
import type { SupportedLanguage } from '@/composables/useTranslation'

const { t } = useI18n()

const showTranslateMenu = ref(false)

const props = defineProps<{
  lines: TranscriptLine[]
  partialText: string
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

// ── 混合列表：章节分隔 + 转写行 + 实时部分转写 + 空状态 / Mixed list: chapter divider + transcript lines + real-time partial + empty state ──
type MixedItem =
  | { type: 'chapter'; key: string; chapterIdx: number; size: number }
  | { type: 'line'; key: string; lineIdx: number; size: number }
  | { type: 'partial'; key: string; size: number }
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

  // 气泡：border(2) + padding-v(16) + 文本行高 / Bubble: border(2) + padding-v(16) + text line height
  const textLineH = 13 * 1.6           // fs-13 × line-height 1.6 ≈ 20.8
  const textLines = estTextLines(line.text)
  h += 2 + 16 + textLines * textLineH

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
  // 尾部：实时部分转写 或 空状态（合并进虚拟滚动，消除独立 tail 区域） / Tail: real-time partial transcript or empty state (merged into virtual scroll, eliminating separate tail area)
  if (props.partialText) {
    items.push({ type: 'partial', key: 'partial', size: 60 })
  } else if (items.length === 0) {
    items.push({ type: 'empty', key: 'empty', size: 80 })
  }
  return items
})

// ── 清理 / Cleanup ──
onUnmounted(() => { autoFollow.value = false })

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

// ── 自动滚动 / Auto-scroll ──
const autoFollow = ref(true)
const showJumpBtn = ref(false)
const NEAR_BOTTOM_PX = 80

function onScrollerScroll(e: Event) {
  const el = e.target as HTMLElement
  if (!el) return
  const dist = el.scrollHeight - el.scrollTop - el.clientHeight
  if (dist < NEAR_BOTTOM_PX) {
    autoFollow.value = true
    showJumpBtn.value = false
  } else {
    autoFollow.value = false
    showJumpBtn.value = true
  }
}

function jumpToLatest() {
  const len = mixedItems.value.length
  if (len > 0) (scrollerRef.value as any)?.scrollToItem(len - 1)
  autoFollow.value = true
  showJumpBtn.value = false
}

// 新行到达 → 自动滚动到底部 / New line arrives → auto-scroll to bottom
watch(() => props.lines.length, () => {
  if (!autoFollow.value) return
  nextTick(() => {
    requestAnimationFrame(() => {
      const len = mixedItems.value.length
      if (len > 0) (scrollerRef.value as any)?.scrollToItem(len - 1)
    })
  })
})

// 实时部分转写更新 → 自动滚动到底部（partial 作为列表末尾 item） / Real-time partial transcript update → auto-scroll to bottom (partial as last item)
watch(() => props.partialText, (val) => {
  if (!val || !autoFollow.value) return
  nextTick(() => {
    requestAnimationFrame(() => {
      const len = mixedItems.value.length
      if (len > 0) (scrollerRef.value as any)?.scrollToItem(len - 1)
    })
  })
})

// ── 辅助函数 / Helper functions ──
function lineOf(item: MixedItem): TranscriptLine {
  if (item.type !== 'line') return { speaker_id: 0, speaker_name: '', text: '', isFinal: true }
  return props.lines[item.lineIdx] ?? { speaker_id: 0, speaker_name: '', text: '', isFinal: true }
}

function speakerColor(sid: string | number): string { return getSpeakerColor(sid) }

/** 头像首字：取名称首字符，无名则用编号 / Avatar initial: first char of name, fallback to ID */
function avatarInitial(name: string, speakerId: number): string {
  if (name && name.trim()) return name.trim()[0]
  return String(speakerId + 1)
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
  scrollToEnd: () => {
    const len = mixedItems.value.length
    if (len > 0) (scrollerRef.value as any)?.scrollToItem(len - 1)
  },
  jumpToLatest,
})
</script>
