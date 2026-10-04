<template>
  <!--
    声纹识别结果条 / Voiceprint match result bar
    - 无数据：手动触发识别 / No data: trigger match manually
    - 有数据：摘要 + 展开每人明细（姓名/相似度/margin/状态） / Results: summary + per-speaker detail
    - 未正式绑定且有命中建议：可一键采纳 / Unbound with a hit: one-click adopt
  -->
  <div class="vp-bar" :class="{ 'is-open': expanded && hasResult }">
    <div class="vp-head">
      <span class="vp-icon">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 0 0 8 11a4 4 0 1 1 8 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0 0 15.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 0 0 8 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4"/></svg>
      </span>

      <!-- 运行中 / Running -->
      <span v-if="running" class="vp-summary">
        <span class="vp-spin" aria-hidden="true"></span>{{ t('generating.voiceprint.running') }}
      </span>

      <!-- 无数据：触发钮 / Idle: trigger -->
      <button v-else-if="!hasResult" class="vp-run" :disabled="!canRun" @click="onRun">
        {{ t('generating.voiceprint.run') }}
      </button>

      <!-- 有数据：摘要 / Result summary -->
      <button v-else class="vp-summary-btn" @click="expanded = !expanded" :aria-expanded="expanded">
        <span class="vp-summary-text">
          {{ t('generating.voiceprint.done', { matched: matchedCount, total: match!.length }) }}
        </span>
        <svg class="vp-chev" :class="{ 'is-up': expanded }" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
      </button>

      <!-- 重跑 / Rerun -->
      <button v-if="hasResult && !running" class="vp-rerun" :title="t('generating.voiceprint.rerun')" @click="onRun">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
      </button>
    </div>

    <!-- 明细 / Detail -->
    <div v-if="hasResult && expanded" class="vp-detail">
      <div v-for="r in match!" :key="r.speaker_id" class="vp-row">
        <span class="vp-dot" :style="{ background: speakerColor(r.speaker_id) }"></span>
        <span class="vp-sid">{{ t('generating.voiceprint.speaker_n', { n: r.speaker_id + 1 }) }}</span>

        <!-- 命中 / Matched -->
        <template v-if="r.status === 'matched'">
          <span class="vp-name">{{ r.matched_name }}</span>
          <span class="vp-meta">{{ pct(r.similarity) }}%</span>
          <span v-if="r.margin > 0" class="vp-meta vp-meta-sub">Δ {{ pct(r.margin) }}%</span>
          <span class="vp-spacer"></span>
          <span v-if="currentMapping[r.speaker_id] === r.matched_uuid" class="vp-adopted">
            {{ t('generating.voiceprint.adopted') }}
          </span>
          <button v-else-if="!currentMapping[r.speaker_id]" class="vp-adopt" @click="emit('apply', r.speaker_id, r.matched_uuid!)">
            {{ t('generating.voiceprint.adopt') }}
          </button>
        </template>

        <!-- 未命中 / Unmatched -->
        <template v-else-if="r.status === 'unmatched'">
          <span class="vp-state">{{ t('generating.voiceprint.unmatched') }}</span>
          <span v-if="r.best_candidate" class="vp-meta vp-meta-sub">
            {{ t('generating.voiceprint.best', { name: r.best_candidate, pct: pct(r.similarity) }) }}
          </span>
        </template>

        <!-- 音频不足 / Insufficient -->
        <template v-else>
          <span class="vp-state vp-state-sub">{{ t('generating.voiceprint.insufficient') }}</span>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { runVoiceprintMatch } from '@/api/voiceprint'
import type { VoiceprintMatchItem } from '@/api/types'
import { getSpeakerColor } from '@/utils/speakerColors'
import { showToast } from '@/composables/useToast'

const { t } = useI18n()

const props = defineProps<{
  taskId: string
  match: VoiceprintMatchItem[] | null
  canRun: boolean
  /** 当前正式绑定（判断建议是否已采纳） / Current confirmed bindings */
  currentMapping: Record<number, string>
}>()

const emit = defineEmits<{
  (e: 'matched', payload: { results: VoiceprintMatchItem[]; autoMapping: Record<string, string> }): void
  (e: 'apply', speakerId: number, uuid: string): void
}>()

const running = ref(false)
const expanded = ref(false)

const hasResult = computed(() => !!props.match && props.match.length > 0)
const matchedCount = computed(() => (props.match || []).filter(r => r.status === 'matched').length)

function pct(v: number): number {
  return Math.round(v * 100)
}

function speakerColor(sid: number): string {
  return getSpeakerColor(String(sid))
}

async function onRun() {
  if (running.value || !props.canRun) return
  running.value = true
  try {
    const res = await runVoiceprintMatch(props.taskId)
    emit('matched', { results: res.results, autoMapping: res.auto_mapping })
    expanded.value = true
  } catch {
    showToast(t('generating.voiceprint.failed'), 'error')
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.vp-bar {
  margin: 8px 0 0;
  padding: 7px 12px;
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}
.vp-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 20px;
}
.vp-icon {
  display: inline-flex;
  color: var(--muted);
  flex-shrink: 0;
}
.vp-summary {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: var(--fs-13);
  color: var(--muted);
}
.vp-run {
  border: none;
  background: none;
  padding: 0;
  font-size: var(--fs-13);
  font-family: var(--font-body);
  color: var(--accent);
  cursor: pointer;
}
.vp-run:disabled {
  color: var(--muted);
  cursor: default;
}
.vp-summary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: none;
  padding: 0;
  font-size: var(--fs-13);
  font-family: var(--font-body);
  color: var(--fg);
  cursor: pointer;
}
.vp-chev {
  color: var(--muted);
  transition: transform 0.15s;
}
.vp-chev.is-up {
  transform: rotate(180deg);
}
.vp-rerun {
  margin-left: auto;
  border: none;
  background: none;
  padding: 2px;
  color: var(--muted);
  cursor: pointer;
  display: inline-flex;
}
.vp-rerun:hover {
  color: var(--fg);
}
.vp-spin {
  width: 11px;
  height: 11px;
  border: 2px solid var(--border-strong);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: vp-rot 0.7s linear infinite;
}
@keyframes vp-rot {
  to { transform: rotate(360deg); }
}
.vp-detail {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.vp-row {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: var(--fs-12);
}
.vp-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.vp-sid {
  color: var(--muted);
  flex-shrink: 0;
}
.vp-name {
  font-weight: 500;
  color: var(--fg);
}
.vp-state {
  color: var(--warn);
}
.vp-state-sub {
  color: var(--muted);
}
.vp-meta {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.vp-meta-sub {
  font-weight: 400;
}
.vp-spacer {
  flex: 1;
}
.vp-adopt {
  border: 1px solid var(--accent);
  background: none;
  color: var(--accent);
  font-size: var(--fs-12);
  font-family: var(--font-body);
  padding: 1px 10px;
  border-radius: var(--radius-pill);
  cursor: pointer;
}
.vp-adopt:hover {
  background: var(--accent);
  color: var(--bg);
}
.vp-adopted {
  color: var(--ok);
  font-size: var(--fs-12);
}
</style>
