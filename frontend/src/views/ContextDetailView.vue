<script setup lang="ts">
/**
 * 企业版定稿文本查看/编辑面（档③ 3a + A项版式对齐升级）
 *
 * 读：GET /api/v1/context/tasks/{id}；写：PUT snapshot（Idempotency-Key 新 mutation +
 * If-Match-Rev，409 拉新合并重推一次——逻辑与 3a 一致，本次只升版式）。
 * 版式对齐个人版详情面：下划线 Tab 栏（原文/纪要/决策/笔记）、标题行徽标、决策卡片；
 * 数据边界不变（§1.4）：无音频回放、无洞察板、转写只读锚点。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useContextsStore } from '@/stores/contexts'
import type { ContextTaskDetail } from '@/api/context'
import VisibilityBadge from '@/components/common/VisibilityBadge.vue'
import EnterpriseConsentGate from '@/components/modals/EnterpriseConsentGate.vue'
import { showToast } from '@/composables/useToast'

type TabId = 'formal' | 'summary' | 'decisions' | 'notes'

const { t } = useI18n()
const route = useRoute()
const contexts = useContextsStore()

const detail = ref<ContextTaskDetail | null>(null)
const notFound = ref(false)
const summary = ref('')
const notes = ref('')
const saving = ref(false)
const activeTab = ref<TabId>('formal')
const dirty = computed(() => detail.value != null && (summary.value !== detail.value.summary || notes.value !== detail.value.notes))
const decisionCount = computed(() => (detail.value?.decisions as unknown[] | undefined)?.length ?? 0)

async function load() {
  const taskId = typeof route.params.taskId === 'string' ? route.params.taskId : ''
  notFound.value = false
  detail.value = null
  activeTab.value = 'formal'
  if (!taskId) { notFound.value = true; return }
  const d = await contexts.loadDetail(taskId)
  if (!d) { notFound.value = true; return }
  detail.value = d
  summary.value = d.summary ?? ''
  notes.value = d.notes ?? ''
}
onMounted(load)
watch(() => route.params.taskId, load)

async function onSave() {
  if (!detail.value || !dirty.value || saving.value) return
  saving.value = true
  try {
    const r = await contexts.saveSnapshot(detail.value, { summary: summary.value, notes: notes.value })
    if (r.ok) {
      await load()
      showToast(t('enterprise.detail.saved'), 'success')
      void contexts.loadTasks()
    } else if (r.conflict) {
      showToast(t('enterprise.detail.conflict_reload'), 'error')
      await load()
    } else {
      showToast(t('enterprise.detail.save_failed'), 'error')
    }
  } finally { saving.value = false }
}

function fmtDT(s: string | null): string { return s ? s.replace('T', ' ').slice(0, 16) : '—' }
</script>

<template>
  <div class="cd-root">
    <div v-if="notFound" class="cd-missing" role="alert">
      {{ t('enterprise.detail.not_found') }}
      <RouterLink to="/library" class="cd-back">← {{ t('enterprise.library.title') }}</RouterLink>
    </div>

    <template v-else-if="detail">
      <!-- 标题行：返回 + 标题 + 徽标 + 保存 -->
      <header class="cd-head">
        <RouterLink to="/library" class="cd-back">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
          {{ t('enterprise.library.title') }}
        </RouterLink>
        <div class="cd-titleline">
          <h1>{{ detail.meta.title || detail.task_id }}</h1>
          <VisibilityBadge :visibility="detail.visibility" />
        </div>
        <div class="cd-actions">
          <span v-if="dirty" class="cd-dirty">{{ t('enterprise.detail.unsaved') }}</span>
          <button class="cd-save" :disabled="!dirty || saving" @click="onSave">{{ saving ? t('enterprise.detail.saving') : t('enterprise.detail.save') }}</button>
        </div>
      </header>

      <!-- 元信息行（对齐个人版 toolbar meta） -->
      <div class="cd-meta">
        <span class="cd-meta-item">{{ fmtDT(detail.meta.meeting_time) }}</span>
        <span v-if="detail.meta.participants_text" class="cd-meta-item">· {{ detail.meta.participants_text }}</span>
        <span class="cd-meta-audio" title="">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
          {{ t('enterprise.detail.audio_local') }}
        </span>
      </div>

      <!-- Tab 栏：个人版同款下划线视觉语言 -->
      <nav class="cd-tabs" role="tablist">
        <button role="tab" :aria-selected="activeTab === 'formal'" :class="{ 'is-active': activeTab === 'formal' }" @click="activeTab = 'formal'">{{ t('enterprise.detail.formal') }}</button>
        <button role="tab" :aria-selected="activeTab === 'summary'" :class="{ 'is-active': activeTab === 'summary' }" @click="activeTab = 'summary'">
          {{ t('enterprise.detail.summary') }}<span v-if="!detail.summary" class="cd-tab-dot is-empty"></span>
        </button>
        <button v-if="decisionCount" role="tab" :aria-selected="activeTab === 'decisions'" :class="{ 'is-active': activeTab === 'decisions' }" @click="activeTab = 'decisions'">
          {{ t('enterprise.detail.decisions') }}<span class="cd-tab-count">{{ decisionCount }}</span>
        </button>
        <button role="tab" :aria-selected="activeTab === 'notes'" :class="{ 'is-active': activeTab === 'notes' }" @click="activeTab = 'notes'">{{ t('enterprise.detail.notes') }}</button>
      </nav>

      <!-- 内容面板（对齐个人版 gen-panel 宽度节奏） -->
      <section class="cd-panel">
        <div v-show="activeTab === 'formal'" class="cd-pane">
          <p class="cd-readonly-hint">{{ t('enterprise.detail.formal_hint') }}</p>
          <div class="cd-formal">{{ detail.formal }}</div>
        </div>

        <div v-show="activeTab === 'summary'" class="cd-pane">
          <textarea v-model="summary" rows="14" class="cd-area" :aria-label="t('enterprise.detail.summary')" :placeholder="t('enterprise.detail.summary_placeholder')"></textarea>
        </div>

        <div v-show="activeTab === 'decisions'" class="cd-pane">
          <article v-for="(d, i) in detail.decisions as Array<{ text?: string; status_text?: string; status_id?: string }>" :key="i" class="cd-decision">
            <p class="cd-decision-text">{{ d.text ?? '' }}</p>
            <span v-if="d.status_text" class="cd-decision-status" :class="'rev-' + (d.status_id ?? '')">{{ d.status_text }}</span>
          </article>
        </div>

        <div v-show="activeTab === 'notes'" class="cd-pane">
          <textarea v-model="notes" rows="10" class="cd-area" :aria-label="t('enterprise.detail.notes')" :placeholder="t('enterprise.detail.notes_placeholder')"></textarea>
        </div>
      </section>
    </template>

    <EnterpriseConsentGate :active="!!detail?.summary" />
  </div>
</template>

<style scoped>
.cd-root { height: 100%; overflow: auto; color: var(--fg, #222); display: flex; flex-direction: column; }
.cd-head { display: flex; align-items: center; gap: var(--s-3, 16px); padding: var(--s-3, 16px) var(--s-6, 28px) 0; flex-wrap: wrap; }
.cd-back { display: inline-flex; align-items: center; gap: 4px; font-size: var(--fs-12, 12px); color: var(--muted, #666); text-decoration: none; flex: none; }
.cd-back:hover { color: var(--fg, #222); }
.cd-titleline { display: flex; align-items: center; gap: var(--s-2, 10px); flex: 1; min-width: 0; }
.cd-titleline h1 { font-size: 16px; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cd-actions { display: flex; align-items: center; gap: var(--s-2, 8px); flex: none; }
.cd-dirty { font-size: var(--fs-11, 11px); color: var(--warn, #b60); }
.cd-save { padding: 6px 16px; border: none; border-radius: var(--radius-sm, 8px); background: var(--accent, #2a6); color: var(--accent-fg, #fff); font-weight: 600; font-size: var(--fs-12, 12px); cursor: pointer; }
.cd-save:disabled { opacity: 0.45; cursor: not-allowed; }
.cd-meta { display: flex; gap: 8px; align-items: center; padding: 6px var(--s-6, 28px) 0; font-size: var(--fs-11, 11px); color: var(--muted, #666); flex-wrap: wrap; }
.cd-meta-audio { display: inline-flex; align-items: center; gap: 4px; margin-left: auto; padding: 2px 8px; border-radius: 999px; background: var(--surface-2, #f2f2f0); color: var(--subtle, #999); }
.cd-tabs { display: flex; gap: 2px; padding: var(--s-3, 14px) var(--s-6, 28px) 0; border-bottom: 1px solid var(--border, #e6e6e2); }
.cd-tabs button { position: relative; padding: 8px var(--s-3, 16px); font-size: var(--fs-13, 13px); color: var(--muted, #666); background: none; border: none; border-bottom: 2px solid transparent; margin-bottom: -1px; cursor: pointer; display: flex; align-items: center; gap: 5px; }
.cd-tabs button:hover { color: var(--fg, #222); }
.cd-tabs button.is-active { color: var(--accent, #2a6); border-bottom-color: var(--accent, #2a6); font-weight: 600; }
.cd-tab-count { font-size: var(--fs-11, 11px); background: var(--surface-2, #f0f0ee); border-radius: 999px; padding: 0 6px; color: var(--muted, #666); }
.cd-tab-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--subtle, #bbb); display: inline-block; }
.cd-panel { width: 80%; min-width: min(600px, 100%); max-width: 960px; margin: 0 auto; padding: var(--s-6, 28px) 0 var(--s-7, 48px); box-sizing: border-box; }
.cd-pane { display: flex; flex-direction: column; gap: var(--s-2, 10px); }
.cd-readonly-hint { margin: 0; font-size: var(--fs-11, 11px); color: var(--subtle, #999); }
.cd-formal { white-space: pre-wrap; font-size: var(--fs-13, 14px); line-height: 2; }
.cd-area { width: 100%; box-sizing: border-box; border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 10px); padding: var(--s-4, 20px); font: inherit; font-size: var(--fs-13, 14px); line-height: 1.9; background: var(--surface, #fff); color: var(--fg, #222); resize: vertical; }
.cd-area:focus { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.cd-decision { background: var(--surface, #fff); border: 1px solid var(--border, #e6e6e2); border-left: 3px solid var(--accent, #2a6); border-radius: var(--radius-sm, 8px); padding: var(--s-3, 14px) var(--s-4, 18px); display: flex; flex-direction: column; gap: 6px; }
.cd-decision-text { margin: 0; font-size: var(--fs-13, 13px); line-height: 1.7; }
.cd-decision-status { align-self: flex-start; font-size: var(--fs-11, 11px); color: var(--muted, #666); background: var(--surface-2, #f2f2f0); padding: 1px 8px; border-radius: 999px; }
.cd-missing { padding: var(--s-7, 48px); color: var(--warn, #c33); font-size: var(--fs-12, 12px); display: flex; gap: var(--s-3, 16px); align-items: center; }
.cd-back { color: var(--muted, #666); }
</style>
