<script setup lang="ts">
/**
 * 企业版定稿文本查看/编辑面（档③ 增量 3a，"Web 登录查看编辑定稿文字"用户场景承接）
 *
 * 读：GET /api/v1/context/tasks/{id}（定稿全文快照）；Web 端无音频回放（契约 §1.4）。
 * 写：PUT snapshot——Idempotency-Key 每次编辑新 mutation、If-Match-Rev=server_rev，
 *     409 拉新合并重推一次（store 内实现）。编辑对象=纪要/笔记文本；转写定稿只读
 *     （改写转写正文=助手侧职责，Web 端 P0 不破坏 verbatim 锚点）。
 * 徽标挂详情头（W3-01 销项）。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useContextsStore } from '@/stores/contexts'
import type { ContextTaskDetail } from '@/api/context'
import VisibilityBadge from '@/components/common/VisibilityBadge.vue'
import EnterpriseConsentGate from '@/components/modals/EnterpriseConsentGate.vue'
import { showToast } from '@/composables/useToast'

const { t } = useI18n()
const route = useRoute()
const contexts = useContextsStore()

const detail = ref<ContextTaskDetail | null>(null)
const notFound = ref(false)
const summary = ref('')
const notes = ref('')
const saving = ref(false)
const dirty = computed(() => detail.value != null && (summary.value !== detail.value.summary || notes.value !== detail.value.notes))

async function load() {
  const taskId = typeof route.params.taskId === 'string' ? route.params.taskId : ''
  notFound.value = false
  detail.value = null
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
      // 保存成功：回读服务端最新态（server_rev/对账态以服务端为准），再刷新库列表
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
    <header class="cd-head">
      <div class="cd-titleline">
        <RouterLink to="/library" class="cd-back">← {{ t('enterprise.library.title') }}</RouterLink>
        <h1>{{ detail?.meta.title || t('common.loading') }}</h1>
        <VisibilityBadge v-if="detail" :visibility="detail.visibility" />
      </div>
      <div class="cd-actions">
        <span v-if="detail && dirty" class="cd-dirty">{{ t('enterprise.detail.unsaved') }}</span>
        <button class="cd-save" :disabled="!dirty || saving" @click="onSave">{{ saving ? t('enterprise.detail.saving') : t('enterprise.detail.save') }}</button>
      </div>
    </header>

    <div v-if="detail" class="cd-meta">
      <span>{{ fmtDT(detail.meta.meeting_time) }}</span>
      <span v-if="detail.meta.participants_text"> · {{ detail.meta.participants_text }}</span>
      <span> · {{ t('enterprise.detail.audio_local') }}</span>
    </div>

    <p v-if="notFound" class="cd-missing" role="alert">{{ t('enterprise.detail.not_found') }}</p>

    <div v-else-if="detail" class="cd-body">
      <section class="cd-sec">
        <h2>{{ t('enterprise.detail.formal') }}</h2>
        <p class="cd-formal">{{ detail.formal }}</p>
      </section>
      <section class="cd-sec">
        <h2>{{ t('enterprise.detail.summary') }}</h2>
        <textarea v-model="summary" rows="8" :aria-label="t('enterprise.detail.summary')"></textarea>
      </section>
      <section v-if="(detail.decisions as unknown[]).length" class="cd-sec">
        <h2>{{ t('enterprise.detail.decisions') }}</h2>
        <ul class="cd-decisions">
          <li v-for="(d, i) in detail.decisions as Array<{ text?: string; status_text?: string }>" :key="i">{{ d.text ?? '' }}<span v-if="d.status_text" class="cd-dstat">{{ d.status_text }}</span></li>
        </ul>
      </section>
      <section class="cd-sec">
        <h2>{{ t('enterprise.detail.notes') }}</h2>
        <textarea v-model="notes" rows="5" :aria-label="t('enterprise.detail.notes')"></textarea>
      </section>
    </div>

    <EnterpriseConsentGate :active="!!detail?.summary" />
  </div>
</template>

<style scoped>
.cd-root { max-width: 860px; margin: 0 auto; padding: calc(var(--s-3, 16px) * 1.5); color: var(--fg, #222); }
.cd-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2, 8px); flex-wrap: wrap; margin-bottom: var(--s-2, 8px); }
.cd-titleline { display: flex; align-items: center; gap: var(--s-2, 10px); flex-wrap: wrap; }
.cd-titleline h1 { font-size: 17px; margin: 0; }
.cd-back { font-size: var(--fs-12, 12px); color: var(--muted, #666); text-decoration: none; }
.cd-actions { display: flex; align-items: center; gap: var(--s-2, 8px); }
.cd-dirty { font-size: var(--fs-11, 11px); color: var(--warn, #b60); }
.cd-save { padding: 7px 16px; border: none; border-radius: var(--radius-sm, 8px); background: var(--accent, #2a6); color: var(--accent-fg, #fff); font-weight: 600; font-size: var(--fs-12, 12px); cursor: pointer; }
.cd-save:disabled { opacity: 0.5; cursor: not-allowed; }
.cd-meta { font-size: var(--fs-11, 11px); color: var(--muted, #666); margin-bottom: var(--s-3, 16px); }
.cd-missing { color: var(--warn, #c33); font-size: var(--fs-12, 12px); }
.cd-body { display: flex; flex-direction: column; gap: var(--s-3, 16px); }
.cd-sec { background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); padding: var(--s-3, 16px); }
.cd-sec h2 { font-size: 13px; margin: 0 0 var(--s-2, 8px); }
.cd-formal { white-space: pre-wrap; font-size: var(--fs-12, 12px); line-height: 1.7; margin: 0; }
.cd-sec textarea { width: 100%; box-sizing: border-box; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); padding: 10px; font: inherit; font-size: var(--fs-12, 12px); background: var(--surface-2, #fafaf8); resize: vertical; }
.cd-sec textarea:focus { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.cd-decisions { margin: 0; padding-left: 18px; font-size: var(--fs-12, 12px); display: flex; flex-direction: column; gap: 4px; }
.cd-dstat { color: var(--muted, #666); font-size: var(--fs-11, 11px); margin-left: 6px; }
</style>
