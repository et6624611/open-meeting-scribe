<template>
  <div class="proj-page">
    <div class="main-head">
      <div class="title-row">
        <h1>{{ t('projects.title') }}</h1>
        <span class="page-count">{{ t('projects.count', { count: projects.length }) }}</span>
      </div>
    </div>

    <!-- 新建项目 / Create project -->
    <div class="proj-create">
      <input v-model="newName" class="proj-create-input" :placeholder="t('projects.input_placeholder')" @keyup.enter="onCreate" />
      <button class="btn btn-primary" @click="onCreate" :disabled="!newName.trim()">{{ t('projects.create') }}</button>
    </div>

    <!-- 项目列表 / Project list -->
    <div v-if="projects.length > 0" class="proj-list">
      <div v-for="proj in projects" :key="proj.id" class="proj-card">
        <div class="proj-card-header">
          <h3 class="proj-card-name">{{ proj.name }}</h3>
          <button class="proj-card-delete" @click="onDelete(proj.id)" :title="t('common.action.delete')">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="proj-card-meta">
          <span>{{ t('projects.folders_count', { count: proj.folders?.length || 0 }) }}</span>
        </div>
        <div v-if="proj.folders?.length" class="proj-folders">
          <div v-for="folder in proj.folders" :key="folder" class="proj-folder">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            <span>{{ folder }}</span>
            <button class="proj-folder-rm" @click="onRemoveFolder(proj.id, folder)" :title="t('projects.remove_folder')">×</button>
          </div>
        </div>
        <button class="btn btn-secondary btn-sm" @click="onAddFolder(proj.id)">{{ t('projects.add_folder') }}</button>
      </div>
    </div>
    <div v-else class="empty-state">{{ t('projects.empty') }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchProjects, createProject, deleteProject, addFolder, removeFolder } from '@/api/projects'
import type { Project } from '@/api/projects'

const { t } = useI18n()

const projects = ref<Project[]>([])
const newName = ref('')

async function load() {
  projects.value = await fetchProjects()
}

async function onCreate() {
  const name = newName.value.trim()
  if (!name) return
  await createProject(name)
  newName.value = ''
  await load()
}

async function onDelete(id: string) {
  if (!confirm(t('projects.confirm_delete'))) return
  await deleteProject(id)
  await load()
}

async function onAddFolder(projectId: string) {
  const path = prompt(t('projects.folder_path_prompt'))
  if (!path) return
  await addFolder(projectId, path.trim())
  await load()
}

async function onRemoveFolder(projectId: string, path: string) {
  await removeFolder(projectId, path)
  await load()
}

onMounted(load)
</script>

<style scoped>
.proj-page { padding: var(--s-5) var(--s-5) var(--s-6); }
.proj-create { display: flex; gap: 8px; margin-bottom: 24px; }
.proj-create-input { flex: 1; max-width: 300px; padding: 8px 12px; border: none; border-bottom: 1px solid var(--border); border-radius: 0; background: transparent; color: var(--fg); font-size: 14px; outline: none; transition: border-color 0.15s; }
.proj-create-input:focus { border-bottom-color: var(--accent); box-shadow: 0 1px 0 0 var(--accent); }
.proj-list { display: flex; flex-direction: column; background: transparent; }
.proj-card { padding: 16px; border-bottom: 1px solid var(--border); }
.proj-card:last-child { border-bottom: none; }
.proj-card-header { display: flex; align-items: center; justify-content: space-between; }
.proj-card-name { font-size: 16px; font-weight: 600; margin: 0; }
.proj-card-delete { color: var(--subtle); cursor: pointer; transition: color 0.15s; }
.proj-card-delete:hover { color: var(--rec); }
.proj-card-meta { font-size: 12px; color: var(--subtle); margin: 4px 0 12px; }
.proj-folders { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.proj-folder { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); padding: 4px 8px; background: var(--surface-2); border-radius: 0; }
.proj-folder span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.proj-folder-rm { color: var(--subtle); cursor: pointer; font-size: 16px; line-height: 1; }
.proj-folder-rm:hover { color: var(--rec); }
.btn-sm { padding: 5px 10px; font-size: 12px; }
.empty-state { text-align: center; padding: 60px 0; color: var(--muted); font-size: 13px; }
</style>
