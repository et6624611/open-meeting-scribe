<template>
  <div class="agents-page">
    <!-- 页头 / Page header -->
    <div class="main-head">
      <div class="title-row">
        <h1>{{ t('agents.title') }}</h1>
        <span class="page-count">{{ t('agents.count', { count: allRoles.length }) }}</span>
      </div>
      <p class="agents-desc">{{ t('agents.desc') }}</p>
    </div>

    <div class="agents-layout">
      <!-- 左栏：角色列表 / Left: role list -->
      <div class="agents-sidebar">
        <!-- 预定义角色 / Built-in roles -->
        <div class="as-group">
          <div class="as-group-title">{{ t('agents.builtin') }}</div>
          <div
            v-for="r in builtinRoles"
            :key="r.name"
            class="as-item"
            :class="{ 'is-active': selectedRole === r.name, 'is-current': agentStore.activeAgent === r.name }"
            @click="selectRole(r.name)"
          >
            <span class="as-item-icon" v-html="roleIcon(r.name)"></span>
            <div class="as-item-info">
              <span class="as-item-name">{{ roleTitle(r.name, r.title) }}</span>
              <span class="as-item-desc">{{ roleDesc(r.name, r.description) }}</span>
            </div>
            <svg v-if="agentStore.activeAgent === r.name" class="as-item-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
        </div>

        <!-- 自定义角色 / Custom roles -->
        <div class="as-group">
          <div class="as-group-title">
            {{ t('agents.custom') }}
            <button class="as-add-btn" @click="showForkDialog = true" :title="t('agents.fork')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
          </div>
          <div v-if="customRoles.length" class="as-item-list">
            <div
              v-for="r in customRoles"
              :key="r.name"
              class="as-item"
              :class="{ 'is-active': selectedRole === r.name, 'is-current': agentStore.activeAgent === r.name }"
              @click="selectRole(r.name)"
            >
              <span class="as-item-icon" v-html="roleIcon(r.name)"></span>
              <div class="as-item-info">
                <span class="as-item-name">{{ roleTitle(r.name, r.title) }}</span>
                <span v-if="r.forked_from" class="as-item-source">{{ t('agents.fork_from') }}: {{ r.forked_from }}</span>
              </div>
              <svg v-if="agentStore.activeAgent === r.name" class="as-item-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
          </div>
          <div v-else class="as-empty">
            <span>{{ t('agents.no_custom') }}</span>
            <small>{{ t('agents.no_custom_hint') }}</small>
          </div>
        </div>
      </div>

      <!-- 右栏：文件目录 + 编辑器 / Right: file tree + editor -->
      <div class="agents-content">
        <template v-if="selectedRole">
          <!-- 角色头部 / Role header -->
          <div class="ac-header">
            <div class="ac-header-info">
              <span class="ac-header-icon" v-html="roleIcon(selectedRole)"></span>
              <h2 class="ac-header-title">{{ roleTitle(selectedRole, selectedRoleData?.title) }}</h2>
              <span class="ac-header-badge">{{ selectedRoleData?.category }}</span>
              <span v-if="selectedRoleData?.source === 'builtin'" class="ac-header-readonly">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="width:12px;height:12px;vertical-align:-1px;margin-right:3px"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                {{ t('agents.readonly_hint') }}
              </span>
            </div>
            <div v-if="selectedRoleData?.source === 'custom'" class="ac-header-actions">
              <button v-if="!isEditing" class="btn btn-sm btn-secondary" @click="onEditRole(selectedRole)">
                {{ t('agents.edit') }}
              </button>
              <template v-else>
                <button class="btn btn-sm btn-primary" @click="onSaveRole" :disabled="roleSaving">
                  {{ roleSaving ? t('agents.saving') : t('agents.save') }}
                </button>
                <button class="btn btn-sm btn-secondary" @click="cancelEdit">{{ t('agents.cancel') }}</button>
              </template>
              <button class="btn btn-sm btn-danger" @click="onDeleteRole(selectedRole)">{{ t('agents.delete') }}</button>
            </div>
            <div v-else class="ac-header-actions">
              <button class="btn btn-sm btn-secondary" @click="onForkRole(selectedRole)">{{ t('agents.fork') }}</button>
            </div>
          </div>

          <!-- 文件目录 / File tree -->
          <div class="ac-files">
            <div class="ac-files-label">{{ t('agents.files') }}</div>
            <div class="ac-files-list">
              <button
                v-for="(_content, fname) in roleFiles"
                :key="fname"
                class="ac-file-tab"
                :class="{ 'is-active': activeFile === fname }"
                @click="switchFile(fname as string)"
              >{{ fname }}</button>
            </div>
          </div>

          <!-- 编辑器 / Editor -->
          <div class="ac-editor-wrap">
            <textarea
              v-if="activeFile"
              class="ac-editor"
              :class="{ 'is-readonly': !isEditing }"
              v-model="editorContent"
              :readonly="!isEditing"
              spellcheck="false"
            ></textarea>
          </div>
        </template>

        <!-- 未选择角色 / No role selected -->
        <div v-else class="ac-placeholder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" style="width:40px;height:40px;opacity:0.3"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <p>{{ t('agents.desc') }}</p>
        </div>
      </div>
    </div>

    <!-- Fork 对话框 / Fork dialog -->
    <div v-if="showForkDialog" class="agents-overlay" @click.self="showForkDialog = false">
      <div class="agents-dialog">
        <h3>{{ t('agents.fork_title') }}</h3>
        <div class="agents-dialog-field">
          <label>{{ t('agents.fork_name') }}</label>
          <input v-model="forkName" class="agents-dialog-input" placeholder="my-expert" />
        </div>
        <div class="agents-dialog-field">
          <label>{{ t('agents.fork_source') }}</label>
          <select v-model="forkSource" class="agents-dialog-input">
            <option v-for="r in builtinRoles" :key="r.name" :value="r.name">{{ roleTitle(r.name, r.title) }}</option>
          </select>
        </div>
        <div class="agents-dialog-actions">
          <button class="btn btn-secondary" @click="showForkDialog = false">{{ t('agents.cancel') }}</button>
          <button class="btn btn-primary" @click="onDoFork" :disabled="!forkName.trim()">{{ t('agents.fork_btn') }}</button>
        </div>
      </div>
    </div>

    <!-- 删除角色确认弹窗 / Delete role confirm dialog -->
    <ConfirmDialog
      v-model="showDeleteRoleConfirm"
      :title="t('agents.delete_confirm_title')"
      :message="t('agents.delete_confirm', { name: pendingDeleteRoleName })"
      @confirm="onConfirmDeleteRole"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchRoles, fetchRoleFiles, forkRole, saveRoleFile, deleteRole } from '@/api/agent'
import type { AgentRole } from '@/api/agent'
import { useAgentStore } from '@/stores/agent'
import { useEscClose } from '@/composables/useEscClose'
import { usePageBack } from '@/composables/usePageBack'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const { t } = useI18n()
const agentStore = useAgentStore()

// ESC 返回上一页（弹窗打开时会先消费事件，不会触发返回） / ESC goes back (dialogs consume the event first, so back won't fire)
usePageBack()

// ─── 角色图标 / Role icons (Lucide-style inline SVG) ───
const SVG_ATTRS = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
const ROLE_ICONS: Record<string, string> = {
  'meeting-minutes': `<svg ${SVG_ATTRS}><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/></svg>`,
  'learning-tutor':  `<svg ${SVG_ATTRS}><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>`,
}
const DEFAULT_ICON = `<svg ${SVG_ATTRS}><path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3z"/></svg>`
const allRoles = ref<AgentRole[]>([])
const roleFilesMap = reactive<Record<string, { forked_from: string | null }>>({})
const selectedRole = ref<string | null>(null)
const roleFiles = ref<Record<string, string>>({})
const activeFile = ref('')
const editorContent = ref('')
const isEditing = ref(false)
const roleSaving = ref(false)

// Fork dialog
const showForkDialog = ref(false)
const forkName = ref('')
const forkSource = ref('')
// ESC 关闭 fork 弹窗（自定义浮层，需显式接管 ESC 并消费事件） / ESC closes fork dialog (custom overlay; must explicitly handle ESC and consume the event)
useEscClose(showForkDialog, () => { showForkDialog.value = false })

// Delete role confirm
const showDeleteRoleConfirm = ref(false)
const pendingDeleteRoleName = ref('')

function roleIcon(name: string) { return ROLE_ICONS[name] || DEFAULT_ICON }

/** 优先使用 i18n 翻译，回退到后端返回的原始值 / Prefer i18n translation, fallback to backend value */
function roleTitle(name: string, fallback?: string) {
  const key = `agents.role.${name}.title`
  const translated = t(key)
  return translated === key ? (fallback || name) : translated
}
function roleDesc(name: string, fallback?: string) {
  const key = `agents.role.${name}.description`
  const translated = t(key)
  return translated === key ? (fallback || '') : translated
}

const builtinRoles = computed(() => allRoles.value.filter(r => r.source === 'builtin'))
const customRoles = computed(() => allRoles.value.filter(r => r.source === 'custom').map(r => ({
  ...r,
  forked_from: roleFilesMap[r.name]?.forked_from ?? null,
})))
const selectedRoleData = computed(() => allRoles.value.find(r => r.name === selectedRole.value) ?? null)

async function loadRoles() {
  try {
    const res = await fetchRoles()
    allRoles.value = res.roles
    for (const r of res.roles.filter(r => r.source === 'custom')) {
      try {
        const files = await fetchRoleFiles(r.name)
        roleFilesMap[r.name] = { forked_from: files.forked_from }
      } catch { /* ignore */ }
    }
    // Auto-select first builtin role if none selected
    if (!selectedRole.value && res.roles.length) {
      selectRole(res.roles[0].name)
    }
  } catch (e) { console.error('load roles failed:', e) }
}

async function selectRole(name: string) {
  selectedRole.value = name
  isEditing.value = false
  // 同时激活该助手 / Also activate this agent globally
  await agentStore.setActive(name)
  try {
    const res = await fetchRoleFiles(name)
    roleFiles.value = res.files
    const firstFile = Object.keys(res.files)[0]
    activeFile.value = firstFile
    editorContent.value = res.files[firstFile] || ''
  } catch (e) { console.error('load role files failed:', e) }
}

function switchFile(fname: string) {
  activeFile.value = fname
  editorContent.value = roleFiles.value[fname] || ''
}

function onEditRole(_name: string) {
  isEditing.value = true
}

function cancelEdit() {
  isEditing.value = false
  // Restore original content
  editorContent.value = roleFiles.value[activeFile.value] || ''
}

async function onSaveRole() {
  if (!selectedRole.value || !activeFile.value) return
  roleSaving.value = true
  try {
    await saveRoleFile(selectedRole.value, activeFile.value, editorContent.value)
    roleFiles.value[activeFile.value] = editorContent.value
    isEditing.value = false
  } catch (e: any) { alert(e.response?.data?.detail || e.message) }
  finally { roleSaving.value = false }
}

function onDeleteRole(name: string) {
  pendingDeleteRoleName.value = name
  showDeleteRoleConfirm.value = true
}

function onConfirmDeleteRole() {
  const name = pendingDeleteRoleName.value
  if (!name) return
  deleteRole(name).then(() => {
    selectedRole.value = null
    loadRoles()
  }).catch((e: any) => alert(e.response?.data?.detail || e.message))
}

function onForkRole(sourceName: string) {
  forkSource.value = sourceName
  forkName.value = ''
  showForkDialog.value = true
}

async function onDoFork() {
  if (!forkName.value.trim() || !forkSource.value) return
  try {
    await forkRole(forkSource.value, forkName.value.trim())
    showForkDialog.value = false
    forkName.value = ''
    await loadRoles()
    // Select the newly created role
    const newName = forkName.value.trim() || forkSource.value
    if (allRoles.value.find(r => r.name === newName)) {
      selectRole(newName)
    }
  } catch (e: any) { alert(e.response?.data?.detail || e.message) }
}

onMounted(async () => {
  await agentStore.load()
  loadRoles()
})
</script>

<style scoped>
/* ─── 页面整体 / Page layout ─── */
.agents-page { height: 100%; display: flex; flex-direction: column; overflow: hidden; }
.main-head { padding: var(--s-4) var(--s-6) 0; flex-shrink: 0; }
.title-row { display: flex; align-items: baseline; gap: var(--s-3); }
.title-row h1 { font-size: 18px; font-weight: 700; margin: 0; }
.page-count { font-size: 12px; color: var(--muted); font-family: var(--font-mono); }
.agents-desc { font-size: 12px; color: var(--muted); margin: var(--s-1) 0 0; }

/* ─── 双栏布局 / Two-column layout ─── */
.agents-layout { display: flex; flex: 1; min-height: 0; overflow: hidden; }

/* ─── 左栏：角色列表 / Left: role list ─── */
.agents-sidebar { flex: 0 0 240px; border-right: 1px solid var(--border); overflow-y: auto; padding: var(--s-3) 0; display: flex; flex-direction: column; gap: var(--s-2); }
.as-group { display: flex; flex-direction: column; }
.as-group-title { font-size: 11px; font-weight: 500; color: var(--subtle); text-transform: uppercase; letter-spacing: 0.06em; padding: var(--s-2) var(--s-4); display: flex; align-items: center; gap: var(--s-2); }
.as-add-btn { width: 20px; height: 20px; display: grid; place-items: center; border: none; background: none; color: var(--muted); cursor: pointer; border-radius: var(--radius-sm); padding: 0; }
.as-add-btn:hover { background: var(--surface-2); color: var(--fg); }
.as-add-btn svg { width: 14px; height: 14px; }
.as-item-list { display: flex; flex-direction: column; }
.as-item { display: flex; align-items: center; gap: var(--s-3); padding: var(--s-2) var(--s-4); cursor: pointer; border: 1px solid transparent; margin: 0 var(--s-2); border-radius: var(--radius-sm); transition: background 0.12s, border-color 0.12s; }
.as-item:hover { background: var(--surface); border-color: var(--border); }
.as-item.is-active { background: var(--surface-2); border-color: var(--border-strong); }
.as-item.is-current { border-left-color: var(--accent); }
.as-item-icon { width: 18px; height: 18px; flex-shrink: 0; color: var(--muted); display: grid; place-items: center; }
.as-item-icon svg { width: 18px; height: 18px; }
.as-item-info { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.as-item-name { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.as-item-desc { font-size: 11px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.as-item-source { font-size: 10px; color: var(--subtle); font-family: var(--font-mono); }
.as-item-check { width: 16px; height: 16px; flex-shrink: 0; color: var(--accent); }
.as-empty { padding: var(--s-4); text-align: center; color: var(--muted); font-size: 12px; display: flex; flex-direction: column; gap: 4px; }
.as-empty small { font-size: 11px; color: var(--subtle); }

/* ─── 右栏：内容 / Right: content ─── */
.agents-content { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }
.ac-placeholder { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--s-3); color: var(--muted); }
.ac-placeholder p { font-size: 13px; margin: 0; max-width: 300px; text-align: center; }

/* ─── 角色头部 / Role header ─── */
.ac-header { display: flex; align-items: center; justify-content: space-between; padding: var(--s-3) var(--s-5); border-bottom: 1px solid var(--border); flex-shrink: 0; gap: var(--s-3); flex-wrap: wrap; }
.ac-header-info { display: flex; align-items: center; gap: var(--s-2); flex: 1; min-width: 0; }
.ac-header-icon { width: 20px; height: 20px; flex-shrink: 0; color: var(--muted); display: grid; place-items: center; }
.ac-header-icon svg { width: 20px; height: 20px; }
.ac-header-title { font-size: 15px; font-weight: 600; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ac-header-badge { font-size: 11px; color: var(--muted); background: var(--surface-2); padding: 1px 8px; border-radius: 10px; flex-shrink: 0; }
.ac-header-readonly { font-size: 11px; color: var(--subtle); margin-left: auto; white-space: nowrap; }
.ac-header-actions { display: flex; gap: var(--s-2); flex-shrink: 0; }

/* ─── 文件目录 / File tree ─── */
.ac-files { display: flex; align-items: center; gap: var(--s-3); padding: var(--s-2) var(--s-5); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.ac-files-label { font-size: 11px; font-weight: 500; color: var(--subtle); text-transform: uppercase; letter-spacing: 0.04em; flex-shrink: 0; }
.ac-files-list { display: flex; gap: 4px; flex-wrap: wrap; }
.ac-file-tab { padding: 3px 12px; font-size: 12px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface); cursor: pointer; color: var(--fg); font-family: var(--font-mono); transition: all 0.12s; }
.ac-file-tab:hover { border-color: var(--border-strong); }
.ac-file-tab.is-active { background: var(--accent); color: #fff; border-color: var(--accent); }

/* ─── 编辑器 / Editor ─── */
.ac-editor-wrap { flex: 1; min-height: 0; overflow: hidden; display: flex; }
.ac-editor { width: 100%; height: 100%; font-family: 'SF Mono', 'Menlo', 'Consolas', monospace; font-size: 13px; line-height: 1.7; padding: var(--s-4) var(--s-5); border: none; background: var(--bg); color: var(--fg); resize: none; outline: none; tab-size: 2; }
.ac-editor.is-readonly { background: var(--bg); color: var(--muted); cursor: default; }

/* ─── Fork 对话框 / Fork dialog ─── */
.agents-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.35); display: grid; place-items: center; z-index: 100; }
.agents-dialog { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--s-5); width: 360px; display: flex; flex-direction: column; gap: var(--s-4); box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.agents-dialog h3 { font-size: 15px; font-weight: 600; margin: 0; }
.agents-dialog-field { display: flex; flex-direction: column; gap: 4px; }
.agents-dialog-field label { font-size: 12px; color: var(--muted); }
.agents-dialog-input { padding: var(--s-2) var(--s-3); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); color: var(--fg); font-size: 13px; outline: none; }
.agents-dialog-input:focus { border-color: var(--accent); }
.agents-dialog-actions { display: flex; justify-content: flex-end; gap: var(--s-2); margin-top: var(--s-2); }
</style>
