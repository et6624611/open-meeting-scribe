<template>
  <Teleport to="body">
    <div v-if="modelValue" class="fb-overlay" data-vue-overlay @click.self="close">
      <div ref="dialogRef" class="fb-dialog" role="dialog" aria-modal="true" aria-labelledby="fbTitle">
        <!-- 头部 / Header -->
        <div class="fb-header">
          <h3 id="fbTitle">{{ t('projects.browse_title') }}</h3>
          <button class="fb-close-btn" @click="close" :title="t('common.action.close')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <!-- 路径输入 / Path input -->
        <div class="fb-path-row">
          <input
            ref="pathInputRef"
            v-model="pathInput"
            class="fb-path-input"
            :placeholder="t('projects.browse_path_placeholder')"
            @keydown.enter="goToPath"
          />
          <button class="fb-browse-btn" @click="toggleBrowse">
            {{ browsing ? t('projects.browse_hide_list') : t('projects.browse_browse_btn') }}
          </button>
        </div>

        <!-- 双栏目录浏览器 / Two-column directory browser -->
        <div v-if="browsing" class="fb-columns">
          <!-- 左栏：当前目录 / Left column: current directory -->
          <div class="fb-col fb-col-left">
            <div class="fb-col-label">{{ t('projects.browse_current_dir') }}</div>
            <div class="fb-col-list">
              <div v-if="loading" class="fb-loading">
                <div class="fb-spinner"></div>
              </div>
              <div v-else-if="errorMsg" class="fb-error">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <span>{{ errorMsg }}</span>
              </div>
              <template v-else>
                <!-- 上级目录 / Parent directory -->
                <div v-if="parentPath" class="fb-dir-item" @click="navigateTo(parentPath)">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m15 18-6-6 6-6"/></svg>
                  <span class="fb-dir-name">..</span>
                </div>
                <!-- 子目录 / Subdirectories -->
                <div
                  v-for="dir in directories"
                  :key="dir.path"
                  :class="['fb-dir-item', { 'is-selected': selectedPath === dir.path }]"
                  @click="onSelectDir(dir)"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                  </svg>
                  <span class="fb-dir-name">{{ dir.name }}</span>
                  <svg v-if="dir.has_children" class="fb-dir-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
                </div>
              </template>
            </div>
          </div>

          <!-- 右栏：选中文件夹的内容 / Right column: selected folder contents -->
          <div class="fb-col fb-col-right">
            <div class="fb-col-label">{{ selectedDirName || t('projects.browse_selected_dir') }}</div>
            <div class="fb-col-list">
              <div v-if="rightLoading" class="fb-loading">
                <div class="fb-spinner"></div>
              </div>
              <div v-else-if="!selectedPath" class="fb-empty">
                {{ t('projects.browse_select_hint') }}
              </div>
              <div v-else-if="selectedDirContents.length === 0" class="fb-empty">
                {{ t('projects.browse_empty') }}
              </div>
              <div
                v-else
                v-for="dir in selectedDirContents"
                :key="dir.path"
                class="fb-dir-item fb-dir-item-right"
                @click="navigateTo(dir.path)"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                </svg>
                <span class="fb-dir-name">{{ dir.name }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部操作 / Footer actions -->
        <div class="fb-footer">
          <button class="btn btn-secondary btn-sm" @click="close">
            {{ t('common.action.cancel') }} <kbd>ESC</kbd>
          </button>
          <button class="btn btn-primary btn-sm" :disabled="!canSelect" @click="confirmSelect">
            {{ t('projects.browse_select') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { browseFilesystem } from '@/api/projects'
import { useDialog } from '@/composables/useDialog'

const { t } = useI18n()

const props = defineProps<{
  modelValue: boolean
  initialPath?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'select', path: string): void
}>()

const pathInput = ref('')
const browsing = ref(false)
const currentPath = ref('')
const parentPath = ref<string | null>(null)
const directories = ref<Array<{ name: string; path: string; has_children: boolean }>>([])
const selectedPath = ref('')
const selectedDirName = ref('')
const selectedDirContents = ref<Array<{ name: string; path: string; has_children: boolean }>>([])
const loading = ref(false)
const rightLoading = ref(false)
const errorMsg = ref('')
const pathInputRef = ref<HTMLInputElement | null>(null)

/** 是否可以选择当前目录 / Whether current directory can be selected */
const canSelect = computed(() => browsing.value && currentPath.value !== '')

// 使用 computed 保持与 props.modelValue 响应式同步；传入 ref(props.modelValue) 只会快照初始值导致 ESC 失效
// Use computed to stay reactive with props.modelValue; passing ref(props.modelValue) only snapshots the initial value, breaking ESC
const { dialogRef } = useDialog(computed(() => props.modelValue), () => close())

watch(() => props.modelValue, async (visible) => {
  if (!visible) return
  selectedPath.value = ''
  selectedDirName.value = ''
  selectedDirContents.value = []
  pathInput.value = props.initialPath || ''
  browsing.value = false

  // ─── 桌面端优先：调用 OS 原生文件夹选择器 / Desktop first: use OS native folder picker ───
  if (typeof window.pywebview?.api?.select_native_folder === 'function') {
    try {
      const folder = await window.pywebview.api.select_native_folder()
      if (folder) {
        emit('select', folder)
        close()
        return
      }
      close()
      return
    } catch {
      // 原生对话框失败 → 回退路径输入 / Native dialog failed → fallback
    }
  }

  // ─── Web 端回退：聚焦路径输入 / Web fallback: focus path input ───
  await nextTick()
  pathInputRef.value?.focus()
})

/** 切换浏览面板 / Toggle browse panel */
async function toggleBrowse() {
  if (browsing.value) {
    browsing.value = false
    return
  }
  browsing.value = true
  errorMsg.value = ''
  await loadDir()
}

/** 加载目录内容 / Load directory contents */
async function loadDir(path?: string) {
  loading.value = true
  errorMsg.value = ''
  try {
    const result = await browseFilesystem(path)
    currentPath.value = result.current_path
    parentPath.value = result.parent_path
    pathInput.value = result.current_path
    directories.value = result.directories
    // 切换目录后清空右栏 / Clear right column when navigating
    selectedPath.value = ''
    selectedDirName.value = ''
    selectedDirContents.value = []
  } catch (e: any) {
    directories.value = []
    const status = e?.response?.status
    const detail = e?.response?.data?.detail || e?.message || ''
    if (status === 403) errorMsg.value = t('projects.browse_access_denied')
    else if (status === 404) errorMsg.value = t('projects.browse_path_not_found')
    else errorMsg.value = detail || t('projects.browse_load_error')
  } finally {
    loading.value = false
  }
}

/** 左栏单击选中文件夹 / Left column: select folder on click */
async function onSelectDir(dir: { name: string; path: string; has_children: boolean }) {
  selectedPath.value = dir.path
  selectedDirName.value = dir.name
  pathInput.value = dir.path

  // 加载选中文件夹的子目录到右栏 / Load selected folder's contents into right column
  rightLoading.value = true
  try {
    const result = await browseFilesystem(dir.path)
    selectedDirContents.value = result.directories
  } catch {
    selectedDirContents.value = []
  } finally {
    rightLoading.value = false
  }
}

/** 右栏单击进入子目录 / Right column: click to navigate into subdirectory */
function navigateTo(path: string) {
  loadDir(path)
}

/** 路径输入框回车 / Path input Enter key */
function goToPath() {
  const p = pathInput.value.trim()
  if (p) {
    browsing.value = true
    loadDir(p)
  }
}

/** 确认选择 / Confirm selection — 选择当前浏览的目录 / Select current browsing directory */
function confirmSelect() {
  if (currentPath.value) {
    emit('select', currentPath.value)
    close()
  }
}

/** 关闭弹窗 / Close dialog */
function close() {
  emit('update:modelValue', false)
}
</script>

<style scoped>
.fb-overlay { position: fixed; inset: 0; background: var(--overlay-bg); display: flex; align-items: center; justify-content: center; z-index: var(--z-modal); animation: fb-overlay-in 0.2s ease; }
@keyframes fb-overlay-in { from { opacity: 0; } }
.fb-dialog { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); width: 680px; max-width: 92vw; display: flex; flex-direction: column; box-shadow: 0 8px 32px oklch(0% 0 0 / 0.15); animation: fb-card-in 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
@keyframes fb-card-in { from { opacity: 0; transform: translateY(8px); } }

/* 头部 / Header */
.fb-header { display: flex; align-items: center; justify-content: space-between; padding: var(--s-4) var(--s-5); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.fb-header h3 { font-size: 15px; font-weight: 600; margin: 0; color: var(--fg); }
.fb-close-btn { color: var(--subtle); background: none; border: none; cursor: pointer; padding: 4px; border-radius: var(--radius-sm); transition: all 0.12s; display: flex; }
.fb-close-btn:hover { color: var(--fg); background: var(--surface-2); }

/* 路径输入行 / Path input row */
.fb-path-row { display: flex; gap: var(--s-2); padding: var(--s-4) var(--s-5); }
.fb-path-input { flex: 1; min-width: 0; padding: 7px 10px; font-size: 13px; font-family: var(--font-mono); border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-2); color: var(--fg); outline: none; transition: border-color 0.15s; }
.fb-path-input:focus { border-color: var(--accent); }
.fb-path-input::placeholder { color: var(--subtle); font-family: var(--font-body); }
.fb-browse-btn { padding: 7px 14px; font-size: 13px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-2); color: var(--fg); cursor: pointer; white-space: nowrap; transition: all 0.12s; }
.fb-browse-btn:hover { background: var(--border); }

/* 双栏布局 / Two-column layout */
.fb-columns { display: flex; gap: 0; margin: 0 var(--s-5); border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; min-height: 260px; max-height: 380px; }
.fb-col { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.fb-col-left { border-right: 1px solid var(--border); }
.fb-col-label { padding: 6px 12px; font-size: 11px; font-weight: 600; color: var(--subtle); text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border); background: var(--surface-2); flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fb-col-list { flex: 1; overflow-y: auto; padding: var(--s-1) 0; }

/* 加载 / Loading */
.fb-loading { display: flex; justify-content: center; padding: var(--s-6); }
.fb-spinner { width: 20px; height: 20px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: fb-spin 0.8s linear infinite; }
@keyframes fb-spin { to { transform: rotate(360deg); } }

/* 空状态 / Empty state */
.fb-empty { text-align: center; padding: var(--s-6); color: var(--muted); font-size: 13px; }

/* 错误 / Error */
.fb-error { display: flex; align-items: center; justify-content: center; gap: var(--s-2); padding: var(--s-6); color: var(--warn); font-size: 13px; }

/* 目录项 / Directory item */
.fb-dir-item { display: flex; align-items: center; gap: var(--s-2); padding: 6px 12px; cursor: pointer; transition: background 0.1s; color: var(--fg); font-size: 13px; }
.fb-dir-item:hover { background: var(--surface-2); }
.fb-dir-item.is-selected { background: var(--accent-soft); }
.fb-dir-item.is-selected > svg:first-child { color: var(--accent); }
.fb-dir-item-right { padding-left: 12px; }
.fb-dir-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fb-dir-arrow { color: var(--subtle); flex-shrink: 0; opacity: 0; transition: opacity 0.1s; }
.fb-dir-item:hover .fb-dir-arrow { opacity: 1; }

/* 底部 / Footer */
.fb-footer { display: flex; justify-content: flex-end; gap: var(--s-2); padding: var(--s-4) var(--s-5); }
.fb-footer kbd { font-family: var(--font-mono); font-size: 9px; padding: 1px 4px; border-radius: 3px; border: 1px solid var(--border); background: var(--surface-2); color: var(--subtle); line-height: 1.3; margin-left: 4px; }
</style>
