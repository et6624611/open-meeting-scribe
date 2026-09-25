<template>
  <!-- 手动补录决策（DC-R2-b 三要素）：归属会议 + 标题 + 内容 + 执行人 +（可选）待确认标记
       Manual entry: meeting + title + content + owner (speaker archive), optional pending flag -->
  <div v-show="modelValue" class="oms-overlay" data-vue-overlay :class="{ 'is-open': modelValue }" @click.self="close">
    <div ref="dialogRef" class="oms-overlay-card ad-dialog" role="dialog" aria-modal="true" aria-labelledby="adDialogTitle">
      <div class="ad-header">
        <h3 id="adDialogTitle">{{ t('decisions.add_modal_title') }}</h3>
        <button class="ad-close" @click="close" :title="t('generating.archive_dialog.close')">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
        </button>
      </div>
      <div class="ad-body">
        <label class="ad-field">
          <span class="ad-label">{{ t('decisions.add_meeting_label') }}</span>
          <select v-model="taskId" class="ad-select">
            <option value="" disabled>{{ t('decisions.add_meeting_required') }}</option>
            <option v-for="m in meetingOptions" :key="m.task_id" :value="m.task_id">{{ m.label }}</option>
          </select>
        </label>
        <label class="ad-field">
          <span class="ad-label">{{ t('decisions.add_title_label') }}</span>
          <input
            ref="titleInputRef"
            v-model.trim="title"
            type="text"
            class="ad-input"
            maxlength="200"
            :placeholder="t('decisions.add_title_placeholder')"
            @keydown.meta.enter.prevent="submit"
            @keydown.ctrl.enter.prevent="submit"
          />
        </label>
        <label class="ad-field">
          <span class="ad-label">{{ t('decisions.add_content_label') }}</span>
          <textarea
            ref="textAreaRef"
            v-model="text"
            class="ad-textarea"
            rows="3"
            :placeholder="t('decisions.add_text_placeholder')"
            @keydown.meta.enter.prevent="submit"
            @keydown.ctrl.enter.prevent="submit"
          ></textarea>
        </label>
        <div class="ad-field">
          <span class="ad-label">{{ t('decisions.add_owner_label') }}</span>
          <OwnerSelectCombobox v-model="owner" :label="t('decisions.add_owner_label')" />
        </div>
        <label class="ad-check">
          <input type="checkbox" v-model="pending" />
          <span>{{ t('decisions.add_pending_check') }}</span>
        </label>
        <p class="ad-error" v-if="errorMsg" role="alert">{{ errorMsg }}</p>
      </div>
      <div class="ad-footer">
        <button class="btn-cancel" @click="close">{{ t('decisions.add_cancel') }} <kbd>ESC</kbd></button>
        <button class="btn-submit" :disabled="submitting" @click="submit">{{ t('decisions.add_submit') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTaskStore } from '@/stores/task'
import { useDialog } from '@/composables/useDialog'
import type { DecisionCreatePayload, OwnerValue } from '@/api/decisions'
import OwnerSelectCombobox from './OwnerSelectCombobox.vue'

const { t } = useI18n()
const taskStore = useTaskStore()

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'submit', taskId: string, payload: DecisionCreatePayload): void
}>()

const { dialogRef } = useDialog(computed(() => props.modelValue), () => close())

const taskId = ref('')
const title = ref('')
const text = ref('')
const owner = ref<OwnerValue>(null)
const pending = ref(false)
const submitting = ref(false)
const errorMsg = ref('')
const titleInputRef = ref<HTMLInputElement | null>(null)
const textAreaRef = ref<HTMLTextAreaElement | null>(null)

/** 归属会议候选：已完成的任务（含 mock 会议，标题兜底 audio_name） / Completed meetings as options */
const meetingOptions = computed(() =>
  taskStore.tasks
    .filter(x => x.status === 'completed')
    .map(x => ({
      task_id: x.task_id,
      label: `${x.meeting_date?.slice(0, 10) || x.created_at?.slice(0, 10) || '—'} · ${x.title || x.audio_name || x.task_id}`,
    })),
)

watch(() => props.modelValue, (open) => {
  if (open) {
    title.value = ''
    text.value = ''
    owner.value = null
    pending.value = false
    errorMsg.value = ''
    submitting.value = false
    if (!taskId.value && meetingOptions.value.length) taskId.value = meetingOptions.value[0].task_id
    nextTick(() => titleInputRef.value?.focus())
  }
})

function close() {
  emit('update:modelValue', false)
}

function submit() {
  if (!taskId.value) { errorMsg.value = t('decisions.add_meeting_required'); return }
  const trimmed = text.value.trim()
  if (!trimmed) { errorMsg.value = t('decisions.add_text_required'); return }
  // 契约 §12.1：text 1..2000，超长后端 422，前端先行拦截
  if (trimmed.length > 2000) { errorMsg.value = t('decisions.add_text_too_long'); return }
  if (title.value.length > 200) { errorMsg.value = t('decisions.add_title_too_long'); return }
  submitting.value = true
  // 执行人可留空（D4）：指派时同时下传档案 id 与快照名（后端以档案为权威）
  emit('submit', taskId.value, {
    title: title.value,
    text: trimmed,
    owner_id: owner.value?.id ?? '',
    owner_name: owner.value?.name ?? '',
    pending_confirmation: pending.value,
  })
}

/** 父级完成后回填 submitting 状态（成功时父级会关闭弹层） / Parent resets the busy flag; closes on success */
watch(() => props.modelValue, (v) => { if (!v) submitting.value = false })

defineExpose({ setSubmitting: (v: boolean) => { submitting.value = v } })
</script>

<style scoped>
.ad-dialog { width: 460px; max-width: 92vw; border-radius: var(--radius-lg); border: none; box-shadow: var(--dropdown-shadow); }
.ad-header { display: flex; align-items: center; justify-content: space-between; padding: var(--s-4) var(--s-5); border-bottom: 1px solid var(--border); }
.ad-header h3 { font-size: var(--fs-15, 15px); font-weight: 600; margin: 0; }
.ad-close { border: none; background: transparent; color: var(--muted); cursor: pointer; padding: 4px; border-radius: var(--radius-sm); }
.ad-close:hover { background: var(--surface-2); color: var(--fg); }
.ad-body { padding: var(--s-4) var(--s-5); display: flex; flex-direction: column; gap: var(--s-3); }
.ad-field { display: flex; flex-direction: column; gap: 6px; }
.ad-label { font-size: var(--fs-12, 12px); color: var(--muted); }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
.ad-select, .ad-textarea, .ad-input {
  width: 100%; box-sizing: border-box; padding: 8px 10px; font-size: var(--fs-13, 13px);
  border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-1, transparent); color: var(--fg);
  font-family: inherit;
}
.ad-select:focus, .ad-textarea:focus, .ad-input:focus { outline: none; border-color: var(--accent); }
.ad-textarea { resize: vertical; min-height: 64px; }
.ad-check { display: flex; align-items: center; gap: var(--s-2); font-size: var(--fs-13, 13px); color: var(--fg); cursor: pointer; }
.ad-check input { accent-color: var(--accent); width: 14px; height: 14px; }
.ad-error { margin: 0; font-size: var(--fs-12, 12px); color: var(--error); }
.ad-footer { display: flex; justify-content: flex-end; gap: var(--s-2); padding: var(--s-3) var(--s-5) var(--s-4); border-top: 1px solid var(--border); }
.btn-cancel, .btn-submit { padding: 6px 14px; font-size: var(--fs-13, 13px); border-radius: var(--radius-sm); cursor: pointer; }
.btn-cancel { border: 1px solid var(--border); background: transparent; color: var(--muted); }
.btn-cancel:hover { color: var(--fg); border-color: var(--border-strong); }
.btn-submit { border: none; background: var(--accent); color: var(--accent-fg); font-weight: 500; }
.btn-submit:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
