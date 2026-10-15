<template>
  <details class="ai-execution" :open="expanded" @toggle="expanded = ($event.target as HTMLDetailsElement).open">
    <summary class="ai-execution-head">
      <span>{{ t('ai-panel.execution.title') }}</span>
      <span class="trace-count">{{ t('ai-panel.execution.steps', { count: stages.length }) }}</span>
      <span v-if="issues" class="trace-issue">{{ t('ai-panel.execution.issues', { count: issues }) }}</span>
      <span v-if="retryStage" class="trace-state">{{ stageLabel(retryStage) }}</span>
      <span v-if="live" class="trace-state">{{ t('ai-panel.execution.running') }}</span>
      <span v-else-if="state && state !== 'done'" class="trace-state">{{ t(`ai-panel.execution.${state}`) }}</span>
    </summary>
    <div class="ai-execution-list">
      <details v-for="(stage, i) in stages" :key="`${stage.id || stage.type}-${i}`" class="ai-execution-step" :class="`is-${statusOf(stage)}`">
        <summary class="trace-step-head">
          <svg v-if="lucideIcon(stage.icon)" class="trace-icon" :viewBox="lucideIcon(stage.icon)!.viewBox" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" v-html="lucideIcon(stage.icon)!.body"></svg>
          <span class="trace-label">{{ stageLabel(stage) }}</span>
          <span class="trace-status">{{ t(`ai-panel.execution.${statusOf(stage) === 'done' ? 'step_done' : statusOf(stage)}`) }}</span>
          <span v-if="stage.detail" class="trace-preview">{{ stage.detail }}</span>
        </summary>
        <div class="trace-body">
          <div class="trace-toolbar">
            <span class="trace-full-label">{{ stageLabel(stage) }}</span>
            <button type="button" class="trace-copy" @click="copyStage(stage, i)">{{ copied === i ? t('ai-panel.execution.copied') : t('ai-panel.execution.copy') }}</button>
          </div>
          <p v-if="copyFailed === i" class="trace-note" role="status">{{ t('ai-panel.execution.copy_failed') }}</p>
          <p v-if="stage.name" class="trace-tool">{{ t('ai-panel.execution.tool') }}：{{ stage.name }}</p>
          <template v-if="stage.input !== undefined">
            <h4>{{ t('ai-panel.execution.input') }}</h4>
            <pre tabindex="0">{{ stage.input }}</pre>
            <p v-if="stage.inputTruncated" class="trace-note">{{ t('ai-panel.execution.truncated') }}</p>
          </template>
          <template v-if="stage.output !== undefined">
            <h4>{{ t('ai-panel.execution.output') }}</h4>
            <pre tabindex="0">{{ formatOutput(stage.output) || t('ai-panel.execution.empty') }}</pre>
            <p v-if="stage.outputTruncated" class="trace-note">{{ t('ai-panel.execution.truncated') }}</p>
          </template>
          <template v-else-if="stage.detail && stage.status !== 'running' && (stage.input === undefined || ['done', 'error', 'denied'].includes(stage.status))">
            <h4>{{ t('ai-panel.execution.detail') }}</h4>
            <pre tabindex="0">{{ stage.detail }}</pre>
            <p v-if="stage.input !== undefined" class="trace-note">{{ t('ai-panel.execution.summary_only') }}</p>
          </template>
          <p v-if="isLegacy(stage)" class="trace-note">{{ t('ai-panel.execution.legacy') }}</p>
        </div>
      </details>
    </div>
  </details>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AgentStage, ChatMessage } from '@/api/chat'
import { lucideIcon } from '@/utils/lucideIcons'

const props = defineProps<{ stages: AgentStage[]; live?: boolean; state?: ChatMessage['executionState'] }>()
const { t, locale } = useI18n()
const expanded = ref(!!props.live)
const copied = ref<number | null>(null)
const retryStage = computed(() => props.stages.find(stage => stage.type === 'board_retry'))
const copyFailed = ref<number | null>(null)
watch(() => props.live, live => { expanded.value = !!live })
watch(() => props.stages, () => { expanded.value = !!props.live; copied.value = null; copyFailed.value = null })

function statusOf(stage: AgentStage) {
  return !props.live && stage.status === 'running' ? 'interrupted' : stage.status
}
const issues = computed(() => props.stages.filter(s => ['error', 'denied', 'stopped', 'interrupted'].includes(statusOf(s))).length)
function stageLabel(stage: AgentStage) {
  if (stage.type === 'board_retry') {
    const status = statusOf(stage)
    const suffix = status === 'done' ? 'written' : status === 'running' ? 'running'
      : status === 'stopped' ? 'stopped' : status === 'interrupted' ? 'unconfirmed' : 'failed'
    return t(`ai-panel.cli_board_retry_${suffix}`)
  }
  return locale.value.startsWith('en') && stage.label_en ? stage.label_en : stage.label
}
function isLegacy(stage: AgentStage) {
  return stage.type === 'tool_call' && stage.input === undefined && stage.output === undefined
}

/** 只格式化完整 JSON，不把工具返回的 HTML 当作页面执行。 */
function formatOutput(value: string): string {
  try {
    const parsed: unknown = JSON.parse(value)
    return typeof parsed === 'object' && parsed !== null ? JSON.stringify(parsed, null, 2) : value
  } catch { return value }
}

async function copyStage(stage: AgentStage, index: number) {
  const parts = [stageLabel(stage), t(`ai-panel.execution.${statusOf(stage) === 'done' ? 'step_done' : statusOf(stage)}`)]
  if (stage.name) parts.push(`${t('ai-panel.execution.tool')}：${stage.name}`)
  if (stage.input !== undefined) parts.push(t('ai-panel.execution.input'), stage.input)
  if (stage.inputTruncated) parts.push(t('ai-panel.execution.truncated'))
  if (stage.output !== undefined) parts.push(t('ai-panel.execution.output'), stage.output)
  else if (stage.detail) parts.push(t('ai-panel.execution.detail'), stage.detail)
  if (stage.outputTruncated) parts.push(t('ai-panel.execution.truncated'))
  if (isLegacy(stage)) parts.push(t('ai-panel.execution.legacy'))
  try {
    await navigator.clipboard.writeText(parts.join('\n\n'))
    copied.value = index
    copyFailed.value = null
  } catch { copyFailed.value = index }
}
</script>

<style scoped>
.ai-execution {
  min-width: 0;
  margin: 6px 0;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 12px;
  color: var(--muted);
}
summary { cursor: pointer; }
summary:focus-visible, .trace-copy:focus-visible, pre:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.ai-execution-head { padding: 8px 10px; line-height: 1.8; overflow-wrap: anywhere; }
.trace-count, .trace-state, .trace-issue { margin-left: 8px; font-size: 11px; }
.trace-issue, .is-error .trace-status { color: var(--error); }
.ai-execution-list { padding: 0 8px 8px; }
.ai-execution-step { min-width: 0; border-top: 1px solid var(--border); }
.trace-step-head { padding: 6px 2px; line-height: 1.6; }
.trace-icon { width: 14px; height: 14px; vertical-align: middle; margin-right: 5px; }
.trace-label { overflow-wrap: anywhere; color: var(--fg); }
.trace-status { font-size: 11px; margin-left: 8px; }
.is-denied .trace-status, .is-interrupted .trace-status, .is-stopped .trace-status { color: var(--warn); }
.is-running .trace-status { color: var(--accent); }
.trace-preview { display: block; padding-left: 18px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }
.trace-body { min-width: 0; padding: 4px 8px 10px; }
.trace-toolbar { display: flex; gap: 8px; align-items: start; justify-content: space-between; }
.trace-full-label, .trace-tool { overflow-wrap: anywhere; white-space: pre-wrap; }
.trace-copy { flex-shrink: 0; cursor: pointer; font: inherit; color: var(--accent); background: none; border: 0; padding: 2px; }
h4 { margin: 10px 0 4px; font-size: 11px; font-weight: 600; }
pre { margin: 0; padding: 8px; max-height: 280px; overflow: auto; overscroll-behavior: contain; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; color: var(--fg); background: var(--surface); border: 1px solid var(--border); border-radius: 4px; font-size: 11px; line-height: 1.6; user-select: text; }
.trace-note { margin: 6px 0 0; font-size: 11px; color: var(--muted); }
</style>
