<template>
  <div class="mf">
    <button ref="btnEl" class="mf-trigger" v-bind="triggerAttrs" @click="toggle">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
        <path d="M3 5h18M7 12h10M10 19h4" />
      </svg>
      <span>{{ t('memory.filter') }}</span>
      <span v-if="activeCount" class="mf-badge">{{ activeCount }}</span>
    </button>

    <div ref="menuEl" v-show="visible" v-bind="menuAttrs" class="mf-menu">
      <div class="mf-section">
        <div class="mf-label">{{ t('memory.filter_panel.namespace') }}</div>
        <button role="menuitem" class="mf-opt" :class="{ 'is-active': !store.namespace }" @click="pickNamespace('')">
          {{ t('memory.filter_panel.all') }}
        </button>
        <button
          v-for="ns in namespaces"
          :key="ns"
          role="menuitem"
          class="mf-opt"
          :class="{ 'is-active': store.namespace === ns }"
          @click="pickNamespace(ns)"
        >{{ nsLabel(ns) }}</button>
      </div>

      <div class="mf-sep" />

      <div class="mf-section">
        <div class="mf-label">{{ t('memory.filter_panel.kind') }}</div>
        <button role="menuitem" class="mf-opt" :class="{ 'is-active': !store.kind }" @click="pickKind('')">
          {{ t('memory.filter_panel.all') }}
        </button>
        <button
          v-for="k in KINDS"
          :key="k"
          role="menuitem"
          class="mf-opt"
          :class="{ 'is-active': store.kind === k }"
          @click="pickKind(k)"
        >{{ t(`memory.kind.${k}`) }}</button>
      </div>

      <button class="mf-reset" role="menuitem" @click="reset">
        {{ t('memory.filter_panel.reset') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePopMenu } from '@/composables/usePopMenu'
import { useMemoryStore } from '@/stores/memoryStore'
import type { MemoryKind } from '@/api/memory'

defineProps<{ namespaces: string[] }>()

const { t } = useI18n()
const store = useMemoryStore()

const KINDS: MemoryKind[] = ['preference', 'fact', 'decision', 'correction', 'habit', 'glossary']

const btnEl = ref<HTMLElement | null>(null)
const menuEl = ref<HTMLElement | null>(null)
const { visible, toggle, close, triggerAttrs, menuAttrs } = usePopMenu(menuEl, btnEl, { align: 'start' })

const activeCount = computed(() => (store.namespace ? 1 : 0) + (store.kind ? 1 : 0))

function nsLabel(ns: string): string {
  return ns === 'global' ? t('memory.scope_global') : ns
}

function pickNamespace(ns: string) {
  store.namespace = ns
  close()
  void store.load()
}

function pickKind(kind: MemoryKind | '') {
  store.kind = kind
  close()
  void store.load()
}

function reset() {
  store.namespace = ''
  store.kind = ''
  close()
  void store.load()
}
</script>

<style scoped>
.mf { position: relative; }
.mf-trigger {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface); color: var(--muted); font-size: var(--fs-12);
  transition: border-color 0.15s, color 0.15s;
}
.mf-trigger:hover { border-color: var(--border-strong); color: var(--fg); }
.mf-badge {
  min-width: 16px; height: 16px; padding: 0 4px; border-radius: 999px;
  background: var(--accent-soft); color: var(--accent);
  font-size: var(--fs-11); line-height: 16px; text-align: center;
}
.mf-menu {
  position: fixed; top: 0; left: 0; z-index: var(--z-popover);
  width: 200px; max-height: 60vh; overflow-y: auto;
  padding: var(--s-2); background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: var(--shadow-float);
}
.mf-section { display: flex; flex-direction: column; gap: 2px; }
.mf-label { padding: 4px 8px; font-size: var(--fs-11); color: var(--subtle); }
.mf-opt {
  padding: 6px 8px; border-radius: var(--radius-xs); text-align: left;
  font-size: var(--fs-13); color: var(--fg); transition: background 0.12s;
}
.mf-opt:hover { background: var(--surface-2); }
.mf-opt.is-active { background: var(--accent-soft); color: var(--accent); }
.mf-sep { height: 1px; margin: var(--s-2) 0; background: var(--border); }
.mf-reset {
  width: 100%; margin-top: var(--s-2); padding: 6px 8px;
  border-top: 1px solid var(--border); border-radius: var(--radius-xs);
  text-align: left; font-size: var(--fs-12); color: var(--muted);
}
.mf-reset:hover { color: var(--fg); }
</style>
