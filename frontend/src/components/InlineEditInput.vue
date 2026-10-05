<template>
  <div
    v-if="visible"
    class="inline-edit-input"
    :style="positionStyle"
    ref="containerEl"
    @mousedown.stop
  >
    <!-- 快捷指令 chips / Quick action chips -->
    <div v-if="!diffVisible" class="inline-edit-chips">
      <button
        v-for="chip in quickChips"
        :key="chip.key"
        class="inline-edit-chip"
        @click="onChipClick(chip.value)"
      >
        <span class="inline-edit-chip-icon">{{ chip.icon }}</span>
        {{ chip.label }}
      </button>
    </div>
    <!-- 自定义指令输入 / Custom instruction input -->
    <div v-if="!diffVisible" class="inline-edit-input-row">
      <input
        ref="inputEl"
        class="inline-edit-field"
        v-model="inputText"
        :placeholder="t('common.selection_toolbar.inline_edit_placeholder')"
        @keydown.enter.prevent="onSubmit"
        @keydown.escape="onCancel"
        :disabled="loading"
      />
      <button
        class="inline-edit-send"
        :class="{ 'is-loading': loading }"
        :disabled="!inputText.trim() || loading"
        @click="onSubmit"
      >
        <svg v-if="!loading" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="22" y1="2" x2="11" y2="13"/>
          <polygon points="22 2 15 22 11 13 2 9 22 2"/>
        </svg>
        <svg v-else class="inline-edit-spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
        </svg>
      </button>
    </div>
    <!-- 改写结果确认卡（AI 算力入口治理 §3）：预览 + 执行方回显 + 采纳/拒绝 -->
    <div v-else class="inline-edit-result">
      <div class="inline-edit-result-head">{{ t('common.inline_edit_diff_title') }}</div>
      <div class="inline-edit-result-body">{{ editedText }}</div>
      <div class="inline-edit-result-foot">
        <!-- 执行方回显标签：点击起跳设置页更换默认模型 -->
        <button v-if="modelUsage" class="inline-edit-exec-tag" :data-tip="t('common.inline_edit_goto_settings')" @click="$emit('gotoSettings')">
          {{ modelUsage.model }} · {{ srcLabel(modelUsage.source) }}
        </button>
        <span class="inline-edit-result-spacer"></span>
        <button class="inline-edit-accept" @click="$emit('accept')">{{ t('common.inline_edit_accept') }}</button>
        <button class="inline-edit-reject" @click="$emit('reject')">{{ t('common.inline_edit_reject') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ModelUsage } from '@/api/chat'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  loading?: boolean
  anchorRect?: { top: number; left: number } | null
  /** 结果确认态：改写完成待采纳/拒绝 / Result confirmation phase */
  diffVisible?: boolean
  /** 改写结果文本 / Edited text preview */
  editedText?: string
  /** 执行方回显（模型·来源·计费） / Executor echo from inline-edit response */
  modelUsage?: ModelUsage | null
}>()

const emit = defineEmits<{
  (e: 'submit', instruction: string): void
  (e: 'cancel'): void
  (e: 'accept'): void
  (e: 'reject'): void
  (e: 'gotoSettings'): void
}>()

/** 算力来源短标签（与 AiChatPanel 回复尾回显同一套 i18n 键） */
function srcLabel(source: string): string {
  if (source === 'local' || source === 'local_endpoint') return t('ai-panel.model_src_local')
  if (source === 'trial') return t('ai-panel.model_src_trial')
  if (source === 'byok') return t('ai-panel.model_src_byok')
  return source || '—'
}

const containerEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLInputElement | null>(null)
const inputText = ref('')
const positionStyle = ref<Record<string, string>>({})

// 快捷指令 / Quick chips
const quickChips = computed(() => [
  { key: 'polish', icon: '✨', label: t('common.selection_toolbar.inline_edit_polish'), value: '润色这段文字，使语言更流畅、表达更专业' },
  { key: 'simplify', icon: '📝', label: t('common.selection_toolbar.inline_edit_simplify'), value: '精简这段文字，删除冗余内容，保留核心信息' },
  { key: 'expand', icon: '📖', label: t('common.selection_toolbar.inline_edit_expand'), value: '扩写这段文字，补充细节和说明' },
  { key: 'translate', icon: '🌐', label: t('common.selection_toolbar.inline_edit_translate'), value: 'Translate this text to English' },
])

// 定位计算 / Position calculation（input 与 result 两态切换时重新开卡都需定位）
watch(() => props.visible, async (v) => {
  if (v) {
    inputText.value = ''
    await nextTick()
    inputEl.value?.focus()
    updatePosition()
  }
})

function updatePosition() {
  const rect = props.anchorRect
  if (!rect) {
    positionStyle.value = { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }
    return
  }
  const el = containerEl.value
  const w = el?.offsetWidth || 360
  const h = el?.offsetHeight || 100
  let top = rect.top - h - 12
  let left = rect.left - w / 2
  // 边界检测 / Boundary detection
  if (top < 8) top = rect.top + 32
  if (left < 8) left = 8
  if (left + w > window.innerWidth - 8) left = window.innerWidth - w - 8
  positionStyle.value = { top: `${top}px`, left: `${left}px` }
}

function onChipClick(value: string) {
  if (props.loading) return
  emit('submit', value)
}

function onSubmit() {
  if (!inputText.value.trim() || props.loading) return
  emit('submit', inputText.value.trim())
  inputText.value = ''
}

function onCancel() {
  emit('cancel')
}

// 点击外部关闭 / Click outside to dismiss
function onDocClick(e: MouseEvent) {
  if (!props.visible) return
  if (containerEl.value?.contains(e.target as Node)) return
  emit('cancel')
}

onMounted(() => {
  document.addEventListener('mousedown', onDocClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocClick)
})
</script>
