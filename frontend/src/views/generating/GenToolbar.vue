<template>
  <!-- 紧凑图标工具栏 / Compact icon toolbar -->
  <div class="gen-toolbar">
    <div class="gen-toolbar-left">
      <nav class="gen-breadcrumb" id="genBreadcrumb" :aria-label="t('generating.breadcrumb.nav')">
        <template v-for="(crumb, i) in breadcrumbs" :key="i">
          <button class="gen-breadcrumb-item" :title="crumb.label" @click="$emit('navigate', crumb.to)">
            <svg v-if="crumb.icon === 'folder'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
            <span class="gen-breadcrumb-label">{{ crumb.label }}</span>
          </button>
          <span class="gen-breadcrumb-sep">/</span>
        </template>
        <!-- 页面级标题：点击即原位重命名（编辑器落在顶栏标题，E2E T-021） / Page title: click to rename in place -->
        <span
          class="gen-breadcrumb-current"
          role="button"
          tabindex="0"
          :class="{ 'is-renaming': isTitleRenaming }"
          :title="t('task.rename')"
          @click="$emit('rename-task')"
          @keydown.enter.prevent="$emit('rename-task')"
        >{{ breadcrumbDisplayTitle }}</span>
      </nav>
    </div>
    <div class="gen-toolbar-right">
      <!-- 在 IDE 中继续：上下文联动入口 / Continue in IDE -->
      <div v-if="ides.length" class="gen-ide-wrap">
        <button ref="genIdeBtn" class="gen-toolbar-icon gen-toolbar-ide" :title="t('ai-panel.context.workspace_ide_continue')" @click="$emit('toggle-ide')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          <span class="tb-tip">{{ t('ai-panel.context.workspace_ide_continue') }}</span>
        </button>
        <div v-if="ideMenuOpen" ref="genIdeMenu" class="gen-ide-menu" role="dialog">
          <div class="gen-ide-head">
            <span>{{ t('ai-panel.context.workspace_ide_open_in') }}</span>
            <button class="gen-ide-close" :title="t('ai-panel.context.workspace_ide_close')" @click="$emit('update:ideMenuOpen', false)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
          <div class="gen-ide-scope">
            <span class="gen-ide-scope-label">{{ t('ai-panel.context.workspace_ide_scope_label') }}</span>
            <div class="gen-ide-scope-opts">
              <button
                v-for="s in ideScopes"
                :key="s.id"
                class="gen-ide-scope-btn"
                :class="{ 'is-active': ideScope === s.id }"
                :disabled="s.id === 'project' && !hasProject"
                :title="s.id === 'project' && !hasProject
                  ? t('ai-panel.context.workspace_ide_scope_project_hint')
                  : t('ai-panel.context.workspace_ide_scope_hint')"
                @click="$emit('update:ideScope', s.id)"
              >{{ t(s.label) }}</button>
            </div>
          </div>
          <ul class="gen-ide-list">
            <li v-for="ide in ides" :key="ide.ide_id">
              <button
                class="gen-ide-item"
                :disabled="!ide.available || openingIdeId === ide.ide_id"
                :title="ide.available ? ide.display_name : t('ai-panel.context.workspace_ide_not_found', { name: ide.display_name })"
                @click="$emit('continue-in-ide', ide.ide_id)"
              >
                <span>{{ ide.display_name }}</span>
                <span v-if="!ide.available" class="gen-ide-na">{{ t('ai-panel.context.workspace_ide_unavailable') }}</span>
                <svg v-else-if="openingIdeId === ide.ide_id" class="gen-ide-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/></svg>
              </button>
            </li>
          </ul>
        </div>
      </div>
      <button class="gen-toolbar-icon" @click="$emit('copy')" :title="t('generating.toolbar.copy')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        <span class="tb-tip">{{ t('generating.toolbar.copy') }}</span>
      </button>
      <button class="gen-toolbar-icon" @click="$emit('export')" :title="t('generating.toolbar.export_title')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
        <span class="tb-tip">{{ t('generating.toolbar.export') }}</span>
      </button>
      <button class="gen-toolbar-icon" @click="$emit('fullscreen')" :title="isFullscreen ? t('generating.toolbar.exit_fullscreen') : t('generating.toolbar.fullscreen')">
        <svg v-if="!isFullscreen" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
        <span class="tb-tip">{{ isFullscreen ? t('generating.toolbar.exit_fullscreen') : t('generating.toolbar.fullscreen') }}</span>
      </button>
      <!-- 知识库同步状态指示器 / Knowledge base sync status indicator -->
      <button
        v-if="syncStatus.can_sync"
        class="gen-toolbar-icon gen-toolbar-sync"
        :class="{ 'is-dirty': syncStatus.is_dirty, 'is-syncing': isSyncing, 'is-synced': !syncStatus.is_dirty }"
        :title="isSyncing ? t('generating.toolbar.syncing') : (syncStatus.is_dirty ? t('generating.toolbar.sync_dirty') : t('generating.toolbar.synced'))"
        :disabled="isSyncing"
        @click="$emit('sync-kb')"
      >
        <!-- 同步中：旋转图标 / Syncing: spinning icon -->
        <svg v-if="isSyncing" class="sync-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
        <!-- 已同步：check-circle / Synced: check-circle -->
        <svg v-else-if="!syncStatus.is_dirty" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
        <!-- 有更新：upload-cloud / Dirty: upload-cloud -->
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>
        <span class="tb-tip">{{ t('generating.toolbar.sync_kb') }}</span>
      </button>
      <div class="gen-toolbar-divider"></div>
      <div class="gen-toolbar-more-wrap" @mouseenter="$emit('more-enter')" @mouseleave="$emit('more-leave')">
        <button ref="genMoreBtn" class="gen-toolbar-icon" v-bind="moreTriggerAttrs" @click="$emit('toggle-more')" :aria-label="t('generating.toolbar.more')">
          <svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg>
        </button>
        <div ref="genMoreDropdown" class="gen-toolbar-more-menu" v-bind="moreMenuAttrs" :class="{ 'is-open': showMoreMenu }">
          <!-- 复制组 -->
          <button class="gen-toolbar-more-item" role="menuitem" @click="$emit('copy-title')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            {{ t('task.copy_title') }}
          </button>
          <button v-if="hasSummary" class="gen-toolbar-more-item" role="menuitem" @click="$emit('copy-summary')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            {{ t('task.copy_summary') }}
          </button>
          <!-- 管理组 -->
          <div class="gen-toolbar-more-divider"></div>
          <button class="gen-toolbar-more-item" role="menuitem" @click="$emit('rename-task')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
            {{ t('task.rename') }}
          </button>
          <button class="gen-toolbar-more-item" role="menuitem" @click="$emit('retry-summary')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            {{ t('generating.toolbar.regenerate') }}
          </button>
          <button class="gen-toolbar-more-item" role="menuitem" @click="$emit('retranscribe')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            {{ t('generating.toolbar.retranscribe') }}
          </button>
          <!-- 危险组 -->
          <div class="gen-toolbar-more-divider"></div>
          <button class="gen-toolbar-more-item" role="menuitem" @click="$emit('archive')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><template v-if="!isArchived"><line x1="10" y1="12" x2="14" y2="12"/></template><template v-else><line x1="12" y1="12" x2="12" y2="16"/><line x1="10" y1="14" x2="14" y2="14"/></template></svg>
            {{ isArchived ? t('generating.toolbar.unarchive') : t('generating.toolbar.archive') }}
          </button>
          <button class="gen-toolbar-more-item is-danger" role="menuitem" @click="$emit('delete')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
            {{ t('generating.toolbar.delete') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { WorkspaceScope } from '@/api/workspace'

const { t } = useI18n()

// 模板 ref 声明：字符串 ref 必须在 setup 作用域有同名绑定才会被赋值，且需经 defineExpose 暴露给父组件
// Template refs must be declared as same-name bindings to receive the element, then exposed via defineExpose
const genIdeBtn = ref<HTMLElement | null>(null)
const genIdeMenu = ref<HTMLElement | null>(null)
const genMoreBtn = ref<HTMLElement | null>(null)
const genMoreDropdown = ref<HTMLElement | null>(null)

interface IdeItem {
  ide_id: string
  display_name: string
  available: boolean
}

interface Breadcrumb {
  icon: string | null
  label: string
  to: any
}

interface IdeScopeOpt {
  id: WorkspaceScope
  label: string
}

defineProps<{
  breadcrumbs: Breadcrumb[]
  breadcrumbDisplayTitle: string
  isTitleRenaming: boolean
  ides: IdeItem[]
  ideMenuOpen: boolean
  ideScope: WorkspaceScope
  ideScopes: IdeScopeOpt[]
  openingIdeId: string | null
  hasProject: boolean
  isFullscreen: boolean
  syncStatus: { can_sync: boolean; is_dirty?: boolean }
  isSyncing: boolean
  showMoreMenu: boolean
  moreTriggerAttrs: Record<string, unknown>
  moreMenuAttrs: Record<string, unknown>
  hasSummary: boolean
  isArchived: boolean
}>()

defineEmits<{
  navigate: [to: any]
  'rename-task': []
  'toggle-ide': []
  'update:ideMenuOpen': [value: boolean]
  'update:ideScope': [value: WorkspaceScope]
  'continue-in-ide': [ideId: string]
  copy: []
  export: []
  fullscreen: []
  'sync-kb': []
  'toggle-more': []
  'more-enter': []
  'more-leave': []
  'copy-title': []
  'copy-summary': []
  'retry-summary': []
  retranscribe: []
  archive: []
  delete: []
}>()

defineExpose({
  genIdeBtn,
  genIdeMenu,
  genMoreBtn,
  genMoreDropdown,
})
</script>
