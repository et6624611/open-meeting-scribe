<template>
  <!-- 元信息行 + 说话人区 / Meta info + speaker zone -->
  <div class="gen-meta" id="genMeta">
    <div class="gen-meta-row">
      <div class="gen-meta-group">
        <span class="gen-meta-item">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
          <span class="gen-meta-val">{{ metaDuration }}</span>
        </span>
        <span class="gen-meta-sep"></span>
        <span class="gen-meta-item">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
          <span class="gen-meta-val">{{ speakerCount }}</span> {{ t('generating.meta.person') }}
        </span>
        <span class="gen-meta-sep"></span>
        <span class="gen-meta-item">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
          <span class="gen-meta-val gen-meta-date-btn" :title="t('generating.meta.edit_date')" @click.stop="$emit('open-date-picker')">{{ metaDateShort }}</span>
        </span>
      </div>
      <span class="gen-meta-project">
        <span class="gen-meta-project-chip" :class="{ 'is-bound': hasProject, 'is-unbound': !hasProject }" role="button" tabindex="0" :aria-expanded="showProjectDropdown" :title="hasProject ? t('generating.meta.linked_kb_tip') : t('generating.meta.link_kb_tip')" @click.stop="$emit('toggle-project-dropdown')" @keydown.enter.prevent="$emit('toggle-project-dropdown')" @keydown.space.prevent="$emit('toggle-project-dropdown')">
          <!-- book-open 图标：知识库语义 / book-open icon: knowledge base semantics -->
          <svg v-if="hasProject" width="12" height="12" viewBox="0 0 24 24" fill="currentColor" fill-opacity="0.15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
          <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
          <span>{{ currentProjectName }}</span>
          <!-- 尾部状态图标：未关联 +，已关联 hover ✕ / Tail status icon: unlinked +, linked hover ✕ -->
          <svg v-if="!hasProject" class="chip-tail-icon chip-tail-add" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <svg v-else class="chip-tail-icon chip-tail-remove" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </span>
        <div ref="kbDropdownRef" class="gen-meta-proj-dropdown" :class="{ hidden: !showProjectDropdown }">
          <!-- 检索输入框（焦点保持在输入框；Esc 由 useDropdownPopup 统一处理） / Search input (keeps focus; Esc handled by useDropdownPopup) -->
          <div class="gen-meta-proj-search">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input
              ref="kbSearchInputRef"
              :value="kbSearchQuery"
              class="gen-meta-proj-search-input"
              :placeholder="t('generating.meta.kb_search_placeholder')"
              @input="$emit('update:kbSearchQuery', ($event.target as HTMLInputElement).value)"
            />
          </div>
          <!-- 过滤后的知识库列表 / Filtered project list -->
          <template v-if="filteredProjects.length > 0">
            <button v-for="p in filteredProjects" :key="p.id" data-dd-item class="gen-meta-proj-item" :class="{ 'is-selected': selectedProjectId === p.id }" @click="$emit('select-project', p.id)">
              {{ p.name }}
            </button>
          </template>
          <!-- 不关联知识库 / No knowledge base linked -->
          <div class="gen-meta-proj-divider"></div>
          <button data-dd-item class="gen-meta-proj-item" :class="{ 'is-selected': !selectedProjectId }" @click="$emit('select-project', '')">
            {{ t('generating.meta.no_project') }}
          </button>
          <!-- 新建知识库区域 / Create KB area -->
          <template v-if="showKbCreateInput">
            <div class="gen-meta-proj-divider"></div>
            <div class="gen-meta-proj-create-inline">
              <input
                ref="kbCreateInputRef"
                :value="kbCreateName"
                class="gen-meta-proj-create-input"
                :placeholder="t('generating.meta.create_kb')"
                data-dd-enter="native"
                @input="$emit('update:kbCreateName', ($event.target as HTMLInputElement).value)"
                @keydown.enter="$emit('create-and-link-kb')"
                @keydown.escape.stop="$emit('cancel-kb-create')"
              />
            </div>
          </template>
          <template v-else-if="filteredProjects.length === 0 && projects.length > 0">
            <!-- 检索无匹配但总列表非空 / Search no match but total list non-empty -->
            <div class="gen-meta-proj-divider"></div>
            <button data-dd-item class="gen-meta-proj-item gen-meta-proj-cta" @click="$emit('open-kb-create-from-search')">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              <span v-if="kbSearchQuery.trim()">{{ t('generating.meta.create_named', { name: kbSearchQuery.trim() }) }}</span>
              <span v-else>{{ t('generating.meta.create_kb') }}</span>
            </button>
          </template>
          <template v-else-if="projects.length === 0">
            <!-- 知识库总数为 0 / Total projects is 0 -->
            <div class="gen-meta-proj-divider"></div>
            <button data-dd-item class="gen-meta-proj-item gen-meta-proj-cta" @click="$emit('open-kb-create')">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              <span v-if="kbSearchQuery.trim()">{{ t('generating.meta.create_named', { name: kbSearchQuery.trim() }) }}</span>
              <span v-else>{{ t('generating.meta.create_kb') }}</span>
            </button>
          </template>
        </div>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

interface Project {
  id: string
  name: string
}

defineProps<{
  metaDuration: string
  speakerCount: number
  metaDateShort: string
  hasProject: boolean
  currentProjectName: string
  showProjectDropdown: boolean
  projects: Project[]
  filteredProjects: Project[]
  selectedProjectId: string
  kbSearchQuery: string
  showKbCreateInput: boolean
  kbCreateName: string
}>()

defineEmits<{
  'open-date-picker': []
  'toggle-project-dropdown': []
  'select-project': [id: string]
  'update:kbSearchQuery': [value: string]
  'update:kbCreateName': [value: string]
  'create-and-link-kb': []
  'cancel-kb-create': []
  'open-kb-create': []
  'open-kb-create-from-search': []
}>()

defineExpose<{
  kbDropdownRef: HTMLElement | null
  kbSearchInputRef: HTMLInputElement | null
  kbCreateInputRef: HTMLInputElement | null
}>()
</script>
