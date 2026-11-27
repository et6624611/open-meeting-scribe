<template>
  <div class="md">
    <div class="md-head">
      <h2 class="md-title">{{ item.text }}</h2>
      <span class="md-status" :class="`is-${visualStatus}`">{{ statusLabel }}</span>
    </div>

    <section class="md-group">
      <h3 class="md-group-title">{{ t('memory.fields.origin') }}</h3>
      <dl class="md-rows">
        <div class="md-row">
          <dt>{{ t('memory.fields.kind') }}</dt>
          <dd>{{ t(`memory.kind.${item.kind}`) }}</dd>
        </div>
        <div class="md-row">
          <dt>{{ t('memory.fields.namespace') }}</dt>
          <dd class="md-mono">{{ item.namespace }}</dd>
        </div>
        <div class="md-row">
          <dt>{{ t('memory.fields.source') }}</dt>
          <dd>
            <router-link v-if="sourceTarget" :to="sourceTarget" class="md-link" :title="t('memory.source_goto')">
              {{ sourceLabel }}
            </router-link>
            <span v-else class="md-muted">{{ t('memory.fields.manual') }}</span>
          </dd>
        </div>
      </dl>
    </section>

    <section class="md-group">
      <h3 class="md-group-title">{{ t('memory.fields.lifecycle') }}</h3>
      <dl class="md-rows">
        <div class="md-row">
          <dt>{{ t('memory.fields.valid') }}</dt>
          <dd>{{ validity }}</dd>
        </div>
        <div class="md-row">
          <dt>{{ t('memory.fields.usage') }}</dt>
          <dd>{{ usage }}</dd>
        </div>
      </dl>
    </section>

    <div class="md-actions">
      <template v-if="item.status === 'proposed'">
        <button class="md-btn md-btn-primary" @click="emit('accept')">{{ t('memory.action.accept') }}</button>
        <button class="md-btn" @click="emit('reject')">{{ t('memory.action.reject') }}</button>
      </template>
      <template v-else-if="item.status === 'deleted'">
        <span class="md-muted">{{ t('memory.status.deleted') }}</span>
      </template>
      <template v-else>
        <button class="md-btn" @click="emit('edit')">{{ t('memory.action.edit') }}</button>
        <button v-if="item.valid_to" class="md-btn" @click="emit('reopen')">{{ t('memory.action.reopen') }}</button>
        <button v-else class="md-btn" @click="emit('close')">{{ t('memory.action.close') }}</button>
        <button class="md-btn md-btn-danger" @click="emit('delete')">{{ t('memory.action.delete') }}</button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MemoryItem } from '@/api/memory'

const props = defineProps<{ item: MemoryItem }>()
const emit = defineEmits<{
  (e: 'edit'): void
  (e: 'close'): void
  (e: 'reopen'): void
  (e: 'delete'): void
  (e: 'accept'): void
  (e: 'reject'): void
}>()

const { t } = useI18n()

const visualStatus = computed(() => {
  if (props.item.status === 'active') return props.item.valid_to ? 'closed' : 'open'
  return props.item.status
})

const statusLabel = computed(() => {
  const key = visualStatus.value === 'open' ? 'active' : visualStatus.value
  return t(`memory.status.${key}`)
})

const validity = computed(() => {
  const from = props.item.valid_from
  const to = props.item.valid_to
  if (!to) return `${from} · ${t('memory.fields.open_ended')}`
  return `${from} → ${to}（${t('memory.fields.closed')}）`
})

const usage = computed(() => {
  if (!props.item.last_used_at) return t('memory.fields.not_used')
  return t('memory.fields.used', { count: props.item.use_count })
})

const sourceTarget = computed(() => {
  const src = props.item.source
  if (!src || src.manual || !src.task_id) return ''
  const anchor = src.anchor?.dialogue_index
  const query = anchor != null ? `?dialogue=${anchor}` : ''
  return `/meeting/${src.task_id}${query}`
})

const sourceLabel = computed(() => {
  const src = props.item.source || {}
  const date = (props.item.recorded_at || '').slice(0, 10)
  const quote = String(src.quote || '').slice(0, 20)
  return quote ? `${date} · ${quote}` : date
})
</script>

<style scoped>
.md { display: flex; flex-direction: column; gap: var(--s-5); padding: var(--s-5); }
.md-head { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--s-3); }
.md-title { margin: 0; font-size: var(--fs-18); font-weight: 600; line-height: 1.45; color: var(--fg); word-break: break-word; }
.md-status {
  flex-shrink: 0; padding: 2px 8px; border-radius: 999px;
  font-size: var(--fs-11); color: var(--muted); background: var(--surface-2);
}
.md-status.is-open { color: var(--ok); background: var(--ok-soft); }
.md-status.is-proposed { color: var(--warn); background: var(--warn-soft); }
.md-status.is-closed { color: var(--muted); background: var(--surface-2); }
.md-status.is-archived { color: var(--muted); background: var(--surface-2); }

.md-group { display: flex; flex-direction: column; gap: var(--s-2); }
.md-group-title { margin: 0; font-size: var(--fs-11); font-weight: 500; letter-spacing: 0.04em; color: var(--subtle); text-transform: uppercase; }
.md-rows { display: flex; flex-direction: column; gap: 6px; margin: 0; }
.md-row { display: flex; gap: var(--s-3); font-size: var(--fs-13); }
.md-row dt { flex: 0 0 72px; color: var(--muted); }
.md-row dd { margin: 0; color: var(--fg); word-break: break-word; }
.md-mono { font-family: var(--font-mono); font-size: var(--fs-12); }
.md-muted { color: var(--muted); }
.md-link { color: var(--accent); text-decoration: none; border-bottom: 1px solid transparent; }
.md-link:hover { border-bottom-color: var(--accent); }

.md-actions { display: flex; gap: var(--s-2); flex-wrap: wrap; padding-top: var(--s-3); border-top: 1px solid var(--border); }
.md-btn {
  padding: 6px 14px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface); color: var(--fg); font-size: var(--fs-12);
  transition: border-color 0.15s, background 0.15s;
}
.md-btn:hover { border-color: var(--border-strong); background: var(--surface-2); }
.md-btn-primary { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
.md-btn-primary:hover { background: var(--accent); border-color: var(--accent); }
.md-btn-danger:hover { border-color: var(--error); color: var(--error); }
</style>
