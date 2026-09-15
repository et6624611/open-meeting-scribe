<template>
  <!-- 随记面板 / Quick notes panel -->
  <div class="gen-panel" :class="{ hidden: !visible }">
    <!-- 编辑器工具栏 / Editor toolbar -->
    <div class="gen-ta-toolbar">
      <button v-if="!isEditing" class="gen-ta-edit-btn" @click="startEdit">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
        {{ t('generating.toolbar.edit') }}
      </button>
      <template v-else>
        <button class="gen-ta-save-btn" @click="finishEdit">{{ t('common.save') }}</button>
        <button class="gen-ta-cancel-btn" @click="cancelEdit">{{ t('common.cancel') }}</button>
      </template>
    </div>
    <!-- Markdown textarea 编辑器 / Markdown textarea editor -->
    <div class="gen-textarea-wrap">
      <textarea
        ref="textareaEl"
        class="gen-textarea-editor"
        :class="{ 'is-readonly': !isEditing }"
        :value="displayContent"
        :readonly="!isEditing"
        :placeholder="t('generating.notes.placeholder')"
        spellcheck="false"
        @input="onInput"
        @mouseup="onSelectionChange"
        @keyup="onSelectionChange"
      ></textarea>
    </div>
    <span class="task-notes-saved" :class="{ show: notesSaved }">{{ t('generating.notes.saved') }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  markdown: string
  notesSaved: boolean
}>()

const emit = defineEmits<{
  (e: 'change', md: string): void
}>()

// ── textarea 编辑状态 / textarea editing state ──
const textareaEl = ref<HTMLTextAreaElement | null>(null)
const isEditing = ref(false)
const editBuffer = ref('')
const displayContent = computed(() => isEditing.value ? editBuffer.value : props.markdown)

function startEdit() {
  editBuffer.value = props.markdown
  isEditing.value = true
  nextTick(() => {
    textareaEl.value?.focus()
    autoGrow()
  })
}

function finishEdit() {
  isEditing.value = false
  if (editBuffer.value !== props.markdown) {
    emit('change', editBuffer.value)
  }
}

function cancelEdit() {
  isEditing.value = false
  editBuffer.value = props.markdown
}

function onInput(e: Event) {
  const val = (e.target as HTMLTextAreaElement).value
  editBuffer.value = val
  autoGrow()
}

function autoGrow() {
  const el = textareaEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

// 外部 markdown 变化时同步编辑缓冲 / Sync edit buffer when external markdown changes
watch(() => props.markdown, (val) => {
  if (isEditing.value) editBuffer.value = val
  nextTick(autoGrow)
})

// 面板可见时自适应高度 / Auto-grow when panel becomes visible
watch(() => props.visible, (v) => { if (v) nextTick(autoGrow) })

// ── 选区追踪（行间编辑用） / Selection tracking (for inline edit) ──
function onSelectionChange() {
  const el = textareaEl.value
  if (!el || el.selectionStart === el.selectionEnd) return
}

// ── 行间编辑接口 / Inline edit interface ──
function replaceRange(start: number, end: number, newText: string) {
  const content = isEditing.value ? editBuffer.value : props.markdown
  const updated = content.slice(0, start) + newText + content.slice(end)
  editBuffer.value = updated
  emit('change', updated)
}

defineExpose({
  replaceRange,
  textareaEl,
})
</script>
