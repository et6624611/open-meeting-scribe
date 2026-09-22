<template>
  <!--
    参会人名单（独立于说话人绑定） / Meeting roster (independent of speaker binding)
    仅记录「谁参加了这次会议」，不涉及 ASR 说话人检测或声纹注册。 / Only records "who attended";
    no ASR speaker detection or voiceprint registration involved.
  -->
  <div class="roster-zone">
    <div class="roster-head">
      <span class="roster-label">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        {{ t('generating.roster.title') }}
      </span>
      <span v-if="roster.length" class="roster-count">{{ roster.length }}</span>
    </div>

    <!-- 名单 chips / Roster chips -->
    <div class="roster-chips" v-if="roster.length > 0">
      <span v-for="(name, idx) in roster" :key="idx" class="roster-chip">
        <span class="roster-chip-name">{{ name }}</span>
        <button class="roster-chip-x" :title="t('generating.roster.remove')" @click="emit('remove', idx)">
          <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 3l6 6M9 3l-6 6"/></svg>
        </button>
      </span>
    </div>

    <!-- 添加输入 / Add input -->
    <div class="roster-add">
      <input
        v-model="localInput"
        :placeholder="t('generating.roster.add_placeholder')"
        @keydown.enter="onAdd"
        @keydown.escape="localInput = ''"
      />
      <button class="roster-add-btn" :disabled="!localInput.trim()" @click="onAdd" :title="t('generating.roster.add')">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{
  roster: string[]
}>()

const emit = defineEmits<{
  (e: 'add', name: string): void
  (e: 'remove', index: number): void
}>()

const localInput = ref('')

function onAdd() {
  const name = localInput.value.trim()
  if (!name) return
  emit('add', name)
  localInput.value = ''
}
</script>
