<template>
  <section class="mop">
    <div class="mop-head">
      <h2 class="mop-title">{{ t('settings.memory.title') }}</h2>
      <p class="mop-desc">{{ t('settings.memory.desc') }}</p>
    </div>

    <div class="mop-rows">
      <div class="mop-row">
        <span class="mop-label">{{ t('settings.memory.status') }}</span>
        <span class="mop-value">
          {{ t('memory.status.open') }} {{ stats.open }} ·
          {{ t('memory.status.closed') }} {{ stats.closed }} ·
          {{ t('memory.status.proposed') }} {{ stats.proposed }}
        </span>
      </div>
      <div class="mop-row">
        <span class="mop-label">{{ t('settings.memory.storage') }}</span>
        <span class="mop-value mop-mono">data/memory/</span>
      </div>
      <div class="mop-row">
        <span class="mop-label">
          {{ t('settings.memory.enable') }}
          <em class="mop-hint">{{ t('settings.memory.enable_desc') }}</em>
        </span>
        <button
          type="button"
          role="switch"
          class="mop-switch"
          :aria-checked="enabled"
          :class="{ 'is-on': enabled }"
          :disabled="busy"
          @click="toggle('agent_memory')"
        ><span class="mop-knob" /></button>
      </div>
      <div class="mop-row">
        <span class="mop-label">
          {{ t('settings.memory.consolidate') }}
          <em class="mop-hint">{{ t('settings.memory.consolidate_desc') }}</em>
        </span>
        <button
          type="button"
          role="switch"
          class="mop-switch"
          :aria-checked="consolidate"
          :class="{ 'is-on': consolidate }"
          :disabled="busy"
          @click="toggle('agent_memory_consolidate')"
        ><span class="mop-knob" /></button>
      </div>
    </div>

    <div class="mop-actions">
      <button class="mop-manage" @click="goManage">{{ t('settings.memory.manage') }}</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { fetchMemoryStats, type MemoryStats } from '@/api/memory'
import { saveSettings, type Settings } from '@/api/settings'
import { showToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/api/client'

const props = defineProps<{ settings: Settings }>()
const emit = defineEmits<{ (e: 'refresh'): void }>()

const { t } = useI18n()
const router = useRouter()

const stats = ref<MemoryStats>({ open: 0, closed: 0, proposed: 0, archived: 0, deleted: 0, total: 0 })
const busy = ref(false)

const flags = computed<Record<string, unknown>>(
  () => (props.settings.feature_flags || {}) as Record<string, unknown>,
)
const enabled = computed(() => flags.value.agent_memory !== false)
const consolidate = computed(() => flags.value.agent_memory_consolidate === true)

async function toggle(key: 'agent_memory' | 'agent_memory_consolidate') {
  if (busy.value) return
  const current = key === 'agent_memory' ? enabled.value : consolidate.value
  busy.value = true
  try {
    await saveSettings({ feature_flags: { ...flags.value, [key]: !current } })
    emit('refresh')
  } catch (err) {
    showToast(extractErrorMessage(err), 'error')
  } finally {
    busy.value = false
  }
}

function goManage() {
  router.push('/memory')
}

onMounted(async () => {
  try {
    stats.value = await fetchMemoryStats()
  } catch {
    /* 概览计数失败不阻断设置页 */
  }
})
</script>

<style scoped>
.mop {
  margin-top: var(--s-5);
  padding: var(--s-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.mop-head { margin-bottom: var(--s-3); }
.mop-title { margin: 0; font-size: var(--fs-15); font-weight: 600; }
.mop-desc { margin: 4px 0 0; font-size: var(--fs-12); color: var(--muted); }
.mop-rows { display: flex; flex-direction: column; }
.mop-row {
  display: flex; align-items: center; justify-content: space-between; gap: var(--s-4);
  padding: var(--s-2) 0; border-top: 1px solid var(--border);
  font-size: var(--fs-13);
}
.mop-row:first-child { border-top: 0; }
.mop-label { display: flex; flex-direction: column; gap: 2px; color: var(--fg); }
.mop-hint { font-style: normal; font-size: var(--fs-11); color: var(--muted); }
.mop-value { color: var(--muted); font-size: var(--fs-12); text-align: right; }
.mop-mono { font-family: var(--font-mono); }
.mop-switch {
  flex-shrink: 0; position: relative; width: 34px; height: 20px; padding: 0;
  border-radius: 999px; background: var(--surface-3); border: 1px solid var(--border);
  transition: background 0.15s, border-color 0.15s;
}
.mop-switch.is-on { background: var(--accent); border-color: var(--accent); }
.mop-switch:disabled { opacity: 0.6; cursor: default; }
.mop-knob {
  position: absolute; top: 2px; left: 2px; width: 14px; height: 14px;
  border-radius: 50%; background: var(--surface); transition: transform 0.15s;
}
.mop-switch.is-on .mop-knob { transform: translateX(14px); }
.mop-actions { display: flex; justify-content: flex-end; padding-top: var(--s-3); }
.mop-manage {
  padding: 6px 14px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface); color: var(--fg); font-size: var(--fs-12);
}
.mop-manage:hover { border-color: var(--border-strong); background: var(--surface-2); }
</style>
