<template>
  <div
    v-if="visible"
    class="inline-edit-input"
    :style="positionStyle"
    ref="containerEl"
    @mousedown.stop
  >
    <!-- 快捷指令 chips / Quick action chips -->
    <div class="inline-edit-chips">
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
    <div class="inline-edit-input-row">
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  loading?: boolean
  anchorRect?: { top: number; left: number } | null
}>()

const emit = defineEmits<{
  (e: 'submit', instruction: string): void
  (e: 'cancel'): void
}>()

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

// 定位计算 / Position calculation
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
