<template>
  <Teleport to="body">
    <div v-if="modelValue" class="fb-overlay" @click.self="close" @keydown.esc="close">
      <div class="fb-dialog" role="dialog" aria-modal="true" aria-labelledby="fbTitle">
        <!-- 头部 / Header -->
        <div class="fb-header">
          <h3 id="fbTitle">{{ t('projects.browse_title') }}</h3>
          <button class="fb-close-btn" @click="close" :title="t('common.action.close')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <!-- 面包屑导航 / Breadcrumb navigation -->
        <div class="fb-breadcrumb">
          <button class="fb-crumb-btn" @click="navigateTo(homePath)" :title="t('projects.browse_home')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
          </button>
          <button v-if="parentPath" class="fb-crumb-btn fb-crumb-up" @click="navigateTo(parentPath)" :title="t('projects.browse_up')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg>
            <span>{{ t('projects.browse_up') }}</span>
          </button>
          <span class="fb-crumb-path">{{ currentPath }}</span>
        </div>

        <!-- 目录列表 / Directory list -->
        <div class="fb-list" ref="listRef">
          <div v-if="loading" class="fb-loading">
            <div class="fb-spinner"></div>
          </div>
          <div v-else-if="directories.length === 0" class="fb-empty">
            {{ t('projects.browse_empty') }}
          </div>
          <div
            v-else
            v-for="dir in directories"
            :key="dir.path"
            :class="['fb-dir-item', { 'is-selected': selectedPath === dir.path }]"
            @click="selectDir(dir.path)"
            @dblclick="navigateTo(dir.path)"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <span class="fb-dir-name">{{ dir.name }}</span>
            <svg v-if="dir.has_children" class="fb-dir-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
          </div>
        </div>

        <!-- 底部操作 / Footer actions -->
        <div class="fb-footer">
          <button class="btn btn-secondary btn-sm" @click="close">
            {{ t('common.action.cancel') }} <kbd>ESC</kbd>
          </button>
          <button class="btn btn-primary btn-sm" :disabled="!selectedPath" @click="confirmSelect">
            {{ t('projects.browse_select') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { browseFilesystem } from '@/api/projects'
import { useEscClose } from '@/composables/useEscClose'

const { t } = useI18n()

const props = defineProps<{
  modelValue: boolean
  initialPath?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'select', path: string): void
}>()

const currentPath = ref('')
const parentPath = ref<string | null>(null)
const homePath = ref('')
const directories = ref<Array<{ name: string; path: string; has_children: boolean }>>([])
const selectedPath = ref('')
const loading = ref(false)
const listRef = ref<HTMLElement | null>(null)

useEscClose(ref(props.modelValue), () => close())

watch(() => props.modelValue, async (visible) => {
  if (!visible) return
  selectedPath.value = ''

  // ─── 桌面端优先：调用 OS 原生文件夹选择器 / Desktop first: use OS native folder picker ───
  // pywebview expose 机制会在 window.pywebview.api 上挂载 Python 函数，
  // 检测到即说明运行在桌面客户端，直接弹原生对话框（macOS NSOpenPanel / Windows 资源管理器）。
  // pywebview expose mounts Python functions on window.pywebview.api,
  // its presence indicates desktop mode — open native dialog directly.
  if (typeof window.pywebview?.api?.select_native_folder === 'function') {
    try {
      const folder = await window.pywebview.api.select_native_folder()
      if (folder) {
        emit('select', folder)
        close()
        return
      }
      // 用户取消了原生对话框 → 同时关闭自定义浏览器 / User cancelled native dialog → close custom browser too
      close()
      return
    } catch {
      // 原生对话框调用失败 → 回退到自定义浏览器 / Native dialog failed → fallback to custom browser
    }
  }

  // ─── Web 端回退：使用自定义目录浏览器 / Web fallback: use custom directory browser ───
  loadDir(props.initialPath || undefined)
})

async function loadDir(path?: string) {
  loading.value = true
  try {
    const result = await browseFilesystem(path)
    currentPath.value = result.current_path
    parentPath.value = result.parent_path
    homePath.value = result.home_path
    directories.value = result.directories
  } catch {
    directories.value = []
  } finally {
    loading.value = false
  }
}

function navigateTo(path: string) {
  selectedPath.value = ''
  loadDir(path)
}

function selectDir(path: string) {
  selectedPath.value = path
}

function confirmSelect() {
  if (selectedPath.value) {
    emit('select', selectedPath.value)
    close()
  }
}

function close() {
  emit('update:modelValue', false)
}
</script>

<style scoped>
.fb-overlay { position: fixed; inset: 0; background: var(--overlay-bg); display: flex; align-items: center; justify-content: center; z-index: var(--z-modal); animation: fb-overlay-in 0.2s ease; }
@keyframes fb-overlay-in { from { opacity: 0; } }
.fb-dialog { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); width: 520px; max-width: 90vw; max-height: 70vh; display: flex; flex-direction: column; box-shadow: 0 8px 32px oklch(0% 0 0 / 0.15); animation: fb-card-in 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
@keyframes fb-card-in { from { opacity: 0; transform: translateY(8px); } }

/* 头部 / Header */
.fb-header { display: flex; align-items: center; justify-content: space-between; padding: var(--s-4) var(--s-5); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.fb-header h3 { font-size: 15px; font-weight: 600; margin: 0; color: var(--fg); }
.fb-close-btn { color: var(--subtle); background: none; border: none; cursor: pointer; padding: 4px; border-radius: var(--radius-sm); transition: all 0.12s; display: flex; }
.fb-close-btn:hover { color: var(--fg); background: var(--surface-2); }

/* 面包屑 / Breadcrumb */
.fb-breadcrumb { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-3) var(--s-5); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.fb-crumb-btn { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; font-size: 12px; color: var(--muted); background: var(--surface-2); border: none; border-radius: var(--radius-sm); cursor: pointer; transition: all 0.12s; }
.fb-crumb-btn:hover { color: var(--fg); background: var(--border); }
.fb-crumb-up { }
.fb-crumb-path { font-size: 12px; color: var(--subtle); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; font-family: var(--font-mono); }

/* 目录列表 / Directory list */
.fb-list { flex: 1; overflow-y: auto; min-height: 200px; max-height: 400px; padding: var(--s-2) 0; }
.fb-loading { display: flex; justify-content: center; padding: var(--s-6); }
.fb-spinner { width: 20px; height: 20px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: fb-spin 0.8s linear infinite; }
@keyframes fb-spin { to { transform: rotate(360deg); } }
.fb-empty { text-align: center; padding: var(--s-6); color: var(--muted); font-size: 13px; }
.fb-dir-item { display: flex; align-items: center; gap: var(--s-2); padding: 8px var(--s-5); cursor: pointer; transition: background 0.1s; color: var(--fg); font-size: 13px; }
.fb-dir-item:hover { background: var(--surface-2); }
.fb-dir-item.is-selected { background: var(--accent-soft); }
.fb-dir-item.is-selected svg:first-child { color: var(--accent); }
.fb-dir-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fb-dir-arrow { color: var(--subtle); flex-shrink: 0; opacity: 0; transition: opacity 0.1s; }
.fb-dir-item:hover .fb-dir-arrow { opacity: 1; }

/* 底部 / Footer */
.fb-footer { display: flex; justify-content: flex-end; gap: var(--s-2); padding: var(--s-4) var(--s-5); border-top: 1px solid var(--border); flex-shrink: 0; }
.fb-footer kbd { font-family: var(--font-mono); font-size: 9px; padding: 1px 4px; border-radius: 3px; border: 1px solid var(--border); background: var(--surface-2); color: var(--subtle); line-height: 1.3; margin-left: 4px; }
</style>
