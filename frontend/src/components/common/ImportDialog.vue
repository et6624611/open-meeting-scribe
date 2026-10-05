<template>
  <Teleport to="body">
    <div v-if="visible" class="import-overlay" data-vue-overlay @click.self="onCancel">
      <div ref="dialogRef" class="import-dialog" role="dialog" aria-modal="true" aria-labelledby="importDialogTitle">
        <!-- 标题 / Title -->
        <div class="import-dialog-title" id="importDialogTitle">{{ t('start.import.title') }}</div>

        <!-- 重复检测提示 / Duplicate detection notice -->
        <div v-if="duplicateInfo" class="import-duplicate">
          <div class="import-duplicate-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          </div>
          <div class="import-duplicate-body">
            <div class="import-duplicate-text">
              {{ t('start.import.duplicate_found') }}
            </div>
            <div class="import-duplicate-detail">
              📄 {{ duplicateInfo.existing_task_title }}
              <span v-if="duplicateInfo.existing_task_date"> · {{ duplicateInfo.existing_task_date }}</span>
            </div>
          </div>
          <div class="import-duplicate-actions">
            <button class="import-dup-btn import-dup-btn-secondary" @click="onOpenExisting">{{ t('start.import.duplicate_open') }}</button>
            <button class="import-dup-btn import-dup-btn-primary" @click="onContinueImport">{{ t('start.import.duplicate_continue') }}</button>
          </div>
        </div>

        <!-- 主内容区（非重复检测状态） / Main content (non-duplicate state) -->
        <template v-else>
          <!-- 拖拽上传区 / Drag & drop zone -->
          <div
            class="import-dropzone"
            :class="{ 'is-dragging': isDragging }"
            @dragenter.prevent="isDragging = true"
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="onDrop"
            @click="openFilePicker"
          >
            <div class="import-dropzone-icon">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            </div>
            <div class="import-dropzone-text">{{ t('start.import.dropzone_text') }}</div>
            <div class="import-dropzone-hint">{{ t('start.import.dropzone_hint') }}</div>
          </div>

          <!-- 已选文件预览 / Selected file preview -->
          <div v-if="selectedFile" class="import-file-preview">
            <div class="import-file-info">
              <span class="import-file-icon">📄</span>
              <span class="import-file-name">{{ selectedFile.name }}</span>
              <span class="import-file-size">{{ formatSize(selectedFile.size) }}</span>
            </div>
            <button class="import-file-remove" @click="clearFile" :title="t('common.action.delete')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>

          <!-- 分隔线 / Divider -->
          <div class="import-divider">
            <span>{{ t('start.import.or_paste') }}</span>
          </div>

          <!-- 粘贴文字区 / Paste text area -->
          <textarea
            v-model="pasteText"
            class="import-paste-area"
            :placeholder="t('start.import.paste_placeholder')"
            rows="4"
          />

          <!-- 处理中状态 / Processing state -->
          <div v-if="processing" class="import-processing">
            <div class="import-spinner"></div>
            <span>{{ t('start.import.processing') }}</span>
          </div>
        </template>

        <!-- 底部操作 / Footer actions -->
        <div class="import-dialog-actions">
          <button class="import-action-cancel" @click="onCancel">{{ t('common.action.cancel') }}</button>
          <button
            v-if="!duplicateInfo"
            class="import-action-submit"
            :disabled="!canSubmit || processing"
            @click="onSubmit"
          >
            {{ t('start.import.btn_submit') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- 隐藏的文件输入 / Hidden file input -->
  <input
    type="file"
    ref="fileInputRef"
    :accept="ACCEPT_EXTENSIONS"
    style="display:none"
    @change="onFileSelected"
  >
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { checkDuplicate, importFile, importText } from '@/api/import'
import { extractErrorMessage } from '@/api/client'
import { useDialog } from '@/composables/useDialog'
import type { DuplicateCheckResult } from '@/api/import'

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'imported', taskId: string): void
  (e: 'openExisting', taskId: string): void
}>()

const { t } = useI18n()
const { dialogRef } = useDialog(computed(() => props.visible), () => emit('close'))

const fileInputRef = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)
const selectedFile = ref<File | null>(null)
const pasteText = ref('')
const processing = ref(false)
const duplicateInfo = ref<DuplicateCheckResult | null>(null)

// 支持的文件扩展名 / Supported file extensions
const ACCEPT_EXTENSIONS = [
  'audio/*', 'video/*',
  '.md', '.txt', '.srt', '.vtt',
  '.png', '.jpg', '.jpeg',
].join(',')

// 提交按钮可用性 / Submit button availability
const canSubmit = computed(() => {
  if (processing.value) return false
  return !!selectedFile.value || (pasteText.value.trim().length >= 10)
})

// 弹窗关闭时重置状态 / Reset state when dialog closes
watch(() => props.visible, (v) => {
  if (!v) {
    selectedFile.value = null
    pasteText.value = ''
    processing.value = false
    duplicateInfo.value = null
    isDragging.value = false
  }
})

function openFilePicker() {
  fileInputRef.value?.click()
}

function clearFile() {
  selectedFile.value = null
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// ── 文件选择处理 / File selection handling ──

function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) handleFileSelected(file)
}

function onDrop(e: DragEvent) {
  isDragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) handleFileSelected(file)
}

async function handleFileSelected(file: File) {
  selectedFile.value = file
  pasteText.value = '' // 清空粘贴区 / Clear paste area

  // 重复检测 / Duplicate detection
  try {
    const result = await checkDuplicate(file.name, file.size)
    if (result.is_duplicate) {
      duplicateInfo.value = result
      return
    }
  } catch {
    // 检测失败不阻断导入 / Don't block import if check fails
  }

  // 无重复，直接提交 / No duplicate, submit directly
  doSubmit()
}

// ── 重复检测处理 / Duplicate handling ──

function onOpenExisting() {
  if (duplicateInfo.value?.existing_task_id) {
    emit('openExisting', duplicateInfo.value.existing_task_id)
    emit('close')
  }
}

function onContinueImport() {
  duplicateInfo.value = null
  doSubmit()
}

// ── 提交导入 / Submit import ──

function onSubmit() {
  if (selectedFile.value) {
    // 文件已选，直接提交（可能已做过重复检测） / File selected, submit directly
    doSubmit()
  } else if (pasteText.value.trim().length >= 10) {
    doSubmit()
  }
}

async function doSubmit() {
  if (processing.value) return
  processing.value = true

  try {
    if (selectedFile.value) {
      // 文件导入 / File import
      const result = await importFile(selectedFile.value)
      emit('imported', result.task_id)
      emit('close')
    } else if (pasteText.value.trim().length >= 10) {
      // 文字粘贴导入 / Paste text import
      const result = await importText(pasteText.value.trim())
      emit('imported', result.task_id)
      emit('close')
    }
  } catch (e: unknown) {
    alert(extractErrorMessage(e, t('start.import.errors.import_failed')))
  } finally {
    processing.value = false
  }
}

function onCancel() {
  emit('close')
}
</script>
