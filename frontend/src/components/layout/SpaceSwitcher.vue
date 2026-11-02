<script setup lang="ts">
/**
 * 空间切换器（P1-WP1；UI 规格 §1.1，侧栏顶部常驻）
 *
 * 挂载在 ActivityRail 顶部（企业形态）：rail 宽度受限，触发按钮显图标+截断空间名，
 * 完整空间名与角色标注在下拉内呈现（挂载形态差异已随批次播报请 UI 复核）。
 * 角色标注是"只读成员理解为什么不能改"的第一入口（规格 §1.1）——必须显性。
 * "+ 新建团队"入口随 WP-4 建团队弹窗落地（本批不建无行为的占位按钮）。
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { PRIVATE_SPACE, useSpaceStore } from '@/stores/space'
import { isTeamArchived } from '@/api/teams'
import { usePopMenu } from '@/composables/usePopMenu'

const { t } = useI18n()
const space = useSpaceStore()

const btnEl = ref<HTMLElement | null>(null)
const menuEl = ref<HTMLElement | null>(null)
const { visible, close, toggle, triggerAttrs, menuAttrs } = usePopMenu(menuEl, btnEl, { align: 'start', gap: 6 })

const query = ref('')
const showSearch = computed(() => space.teams.length > 6)
const filteredTeams = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? space.teams.filter((tm) => tm.name.toLowerCase().includes(q)) : space.teams
})
const displayName = computed(() => (space.isTeamSpace ? space.currentSpaceName : t('enterprise.space.private')))
const triggerTitle = computed(() => t('enterprise.space.current_aria', { name: displayName.value }))

onMounted(() => { void space.ensureReady() })

function pick(id: string) {
  space.switchSpace(id)
  close()
}

function roleLabel(role: string): string {
  if (role === 'admin') return t('enterprise.space.role_admin')
  if (role === 'editor') return t('enterprise.space.role_editor')
  return t('enterprise.space.role_viewer')
}
</script>

<template>
  <div class="ss-root">
    <button
      ref="btnEl"
      class="ss-btn"
      :title="triggerTitle"
      :aria-label="triggerTitle"
      v-bind="triggerAttrs"
      @click="toggle"
    >
      <svg v-if="!space.isTeamSpace" class="ss-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="5" y="11" width="14" height="9" rx="2"/>
        <path d="M8 11V7a4 4 0 0 1 8 0v4"/>
      </svg>
      <svg v-else class="ss-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>
      <span class="ss-name">{{ displayName }}</span>
      <svg class="ss-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
    </button>

    <div v-show="visible" ref="menuEl" class="ss-menu" v-bind="menuAttrs">
      <input
        v-if="showSearch"
        v-model="query"
        class="ss-search"
        type="text"
        :placeholder="t('enterprise.space.search_placeholder')"
        :aria-label="t('enterprise.space.search_placeholder')"
      >
      <button
        role="menuitem"
        class="ss-item"
        :class="{ 'is-active': !space.isTeamSpace }"
        :aria-current="!space.isTeamSpace ? 'true' : undefined"
        @click="pick(PRIVATE_SPACE)"
      >
        <span class="ss-item-name">{{ t('enterprise.space.private') }}</span>
        <span class="ss-hint">{{ t('enterprise.space.private_hint') }}</span>
      </button>

      <p class="ss-section">{{ t('enterprise.space.my_teams') }}</p>
      <template v-if="filteredTeams.length">
        <button
          v-for="tm in filteredTeams"
          :key="tm.team_id"
          role="menuitem"
          class="ss-item"
          :class="{ 'is-active': space.currentId === tm.team_id }"
          :aria-current="space.currentId === tm.team_id ? 'true' : undefined"
          @click="pick(tm.team_id)"
        >
          <span class="ss-item-name">
            {{ tm.name }}
            <span v-if="isTeamArchived(tm)" class="ss-archived">{{ t('enterprise.space.archived_tag') }}</span>
          </span>
          <span class="ss-role">{{ roleLabel(tm.my_role) }}</span>
        </button>
      </template>
      <p v-else-if="space.loaded && !space.loadError" class="ss-empty">{{ t('enterprise.space.no_teams') }}</p>
      <p v-else-if="space.loadError" class="ss-empty" role="alert">{{ t('enterprise.space.load_error') }}</p>
    </div>
  </div>
</template>

<style scoped>
.ss-root { position: relative; width: 100%; }
.ss-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  padding: 6px 4px;
  border: 1px solid var(--border, #e2e2de);
  border-radius: var(--radius-sm, 8px);
  background: var(--surface, #fff);
  color: var(--fg, #222);
  cursor: pointer;
  font-size: var(--fs-11, 11px);
}
.ss-btn:hover { background: var(--surface-2, #fafaf8); }
.ss-btn:focus-visible { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.ss-ico { width: 14px; height: 14px; flex: none; }
.ss-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}
.ss-caret { width: 10px; height: 10px; flex: none; color: var(--muted, #666); }
.ss-menu {
  position: absolute;
  left: 0;
  top: calc(100% + 4px);
  z-index: var(--z-popover, 1000);
  min-width: 232px;
  max-width: 280px;
  padding: var(--s-2, 8px) 0;
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e2e2de);
  border-radius: var(--radius-sm, 8px);
  box-shadow: 0 8px 24px rgb(0 0 0 / 0.1);
}
.ss-search {
  width: calc(100% - 16px);
  margin: 0 8px 6px;
  padding: 6px 8px;
  border: 1px solid var(--border, #d8d8d4);
  border-radius: var(--radius-sm, 8px);
  background: var(--surface-2, #fafaf8);
  font-size: var(--fs-12, 12px);
  color: var(--fg, #222);
}
.ss-section {
  margin: 6px 14px 2px;
  font-size: var(--fs-11, 11px);
  color: var(--subtle, #999);
  font-weight: 600;
}
.ss-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 7px 14px;
  border: none;
  background: none;
  text-align: left;
  font-size: var(--fs-12, 12px);
  color: var(--fg, #222);
  cursor: pointer;
}
.ss-item:hover { background: var(--surface-2, #fafaf8); }
.ss-item.is-active { background: var(--accent-soft, #eaf4ec); }
.ss-item-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ss-hint, .ss-role {
  flex: none;
  font-size: var(--fs-11, 11px);
  color: var(--muted, #666);
}
.ss-role {
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--surface-2, #f2f2f0);
  border: 1px solid var(--border, #e6e6e2);
}
.ss-archived { color: var(--subtle, #999); font-size: var(--fs-11, 11px); }
.ss-empty { margin: 6px 14px; font-size: var(--fs-11, 11px); color: var(--subtle, #999); }
</style>
