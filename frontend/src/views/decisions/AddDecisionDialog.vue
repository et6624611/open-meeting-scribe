<template>
  <!-- 补录/添加决策：归属会议 + 标题 + 内容 + 等待方(owner_type) + 状态
       与纪要页「添加决策」共用同一弹层（样式/数据口径统一）；不再采集执行人 -->
  <div v-show="modelValue" class="oms-overlay" data-vue-overlay :class="{ 'is-open': modelValue }" @click.self="close">
    <div ref="dialogRef" class="oms-overlay-card ad-dialog" role="dialog" aria-modal="true" aria-labelledby="adDialogTitle">
      <div class="ad-header">
        <h3 id="adDialogTitle">{{ t('decisions.add_modal_title') }}</h3>
        <button class="ad-close" @click="close" :title="t('generating.archive_dialog.close')">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
        </button>
      </div>
      <div class="ad-body">
        <!-- 纪要页上下文：归属会议已确定，不展示选择器（meetingLocked） -->
        <label class="ad-field" v-if="!meetingLocked">
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
        <label class="ad-field ad-text-field">
          <span class="ad-label">{{ t('decisions.add_content_label') }}</span>
          <textarea
            ref="textAreaRef"
            v-model="text"
            class="ad-textarea"
            rows="3"
            :placeholder="t('decisions.add_text_placeholder')"
            @input="onTextSlashInput"
            @keydown="onTextKeydown"
            @blur="slashMenuOnBlur"
          ></textarea>
          <SlashDateMenu
            :open="slashOpen" :items="slashItems" :active-index="slashActive" :pos="slashPos"
            @select="slashMenu.select" @hover="slashMenu.setActive"
          />
        </label>
        <!-- 次要信息（等待方 / 状态）默认折叠，展开后可编辑；不编辑即默认“等自己 · 待决策” -->
        <div class="ad-advanced">
          <button type="button" class="ad-adv-toggle" :aria-expanded="showAdvanced" @click="showAdvanced = !showAdvanced">
            <svg class="ad-adv-chev" :class="{ open: showAdvanced }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
            <span>{{ t('decisions.add_advanced_toggle') }}</span>
            <span class="ad-adv-summary" v-if="!showAdvanced">{{ ownerTypeSummary }} · {{ statusSummary }}</span>
          </button>
          <div class="ad-adv-body" v-show="showAdvanced">
            <div class="ad-field">
              <span class="ad-label">{{ t('decisions.add_owner_type_label') }}</span>
              <select v-model="ownerType" class="ad-select">
                <option v-for="o in ownerTypeOptions" :key="o" :value="o">{{ t('decisions.owner_type_' + o) }}</option>
              </select>
            </div>
            <div class="ad-field">
              <span class="ad-label">{{ t('decisions.add_status_label') }}</span>
              <select v-model="statusId" class="ad-select">
                <option v-for="s in statuses" :key="s.id" :value="s.id">{{ labelOf(s.id, locale) }}</option>
              </select>
            </div>
          </div>
        </div>
        <p class="ad-hint" v-if="!meetingLocked">{{ t('decisions.add_flow_hint') }}</p>
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
import { useDecisionStatuses } from '@/composables/useDecisionStatuses'
import { useSlashDateMenu } from '@/composables/useSlashDateMenu'
import { handleDateShortcut } from '@/utils/dateShortcuts'
import SlashDateMenu from '@/components/SlashDateMenu.vue'
import type { TodoCreatePayload } from '@/api/notes'
import type { OwnerType } from '@/api/types'

const { t, locale } = useI18n()
const taskStore = useTaskStore()

const props = defineProps<{
  modelValue: boolean
  /** 默认归属会议（纪要页打开时传当前任务） / Task pre-selected as the owning meeting */
  defaultTaskId?: string
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'submit', taskId: string, payload: TodoCreatePayload): void
}>()

const { dialogRef } = useDialog(computed(() => props.modelValue), () => close())

const taskId = ref('')
const title = ref('')
const text = ref('')
const ownerType = ref<OwnerType>('self')
const statusId = ref('')
const showAdvanced = ref(false)
const submitting = ref(false)
const errorMsg = ref('')
const titleInputRef = ref<HTMLInputElement | null>(null)
const textAreaRef = ref<HTMLTextAreaElement | null>(null)

// 斜杠日期候选菜单（内容 textarea）
const slashMenu = useSlashDateMenu(() => textAreaRef.value)
const {
  open: slashOpen, items: slashItems, activeIndex: slashActive, pos: slashPos,
  onInput: slashMenuOnInput, onKeydown: slashMenuOnKeydown, onBlur: slashMenuOnBlur,
} = slashMenu
function onTextSlashInput(e: Event) {
  handleDateShortcut(e)
  slashMenuOnInput()
}

// 统一 keydown：先给菜单（纯 Enter 选中项会 preventDefault），未消费且 Cmd/Ctrl+Enter 则提交
function onTextKeydown(e: KeyboardEvent) {
  slashMenuOnKeydown(e)
  if (e.defaultPrevented) return
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault()
    submit()
  }
}

// 纪要页上下文（传入 defaultTaskId）时锁定归属会议并隐藏选择器
const meetingLocked = computed(() => Boolean(props.defaultTaskId))

// 等待方四维（与卡片下拉同源）；状态选项由状态字典驱动（三态）
const ownerTypeOptions: OwnerType[] = ['self', 'agent', 'colleague', 'enterprise']
const { statuses, load: loadStatuses, labelOf } = useDecisionStatuses()
void loadStatuses()

// 折叠态下的当前取值摘要（不展开也能看到生效值：默认“等自己 · 待决策”）
const ownerTypeSummary = computed(() => t('decisions.owner_type_' + ownerType.value))
const statusSummary = computed(() => labelOf(statusId.value, String(locale.value || 'zh-CN')))

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
    ownerType.value = 'self'
    // 默认状态 = 字典首个开放态（当前为“待决策”）
    statusId.value = statuses.value.find(s => !s.closing)?.id || statuses.value[0]?.id || ''
    showAdvanced.value = false
    errorMsg.value = ''
    submitting.value = false
    // 归属：纪要页锁定时直接用当前任务；否则优先入参（需在候选内），再回落到首个候选
    const def = props.defaultTaskId
    if (meetingLocked.value && def) {
      taskId.value = def
    } else {
      taskId.value = def && meetingOptions.value.some(m => m.task_id === def)
        ? def
        : (meetingOptions.value[0]?.task_id || '')
    }
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
  // 契约：text 1..500（决策流节点口径），超长前端先行拦截
  if (trimmed.length > 500) { errorMsg.value = t('decisions.add_text_too_long'); return }
  if (title.value.length > 200) { errorMsg.value = t('decisions.add_title_too_long'); return }
  submitting.value = true
  // 统一口径：携带等待方(owner_type)与状态；不再采集执行人(owner_id)
  // 内容同时写入正文栏(why)：有标题时内容落在卡片正文框，text 作为主文本供检索/聚合
  emit('submit', taskId.value, {
    title: title.value,
    text: trimmed,
    why: title.value ? trimmed : undefined,
    owner_type: ownerType.value,
    status: statusId.value || undefined,
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
/* 内容字段作为斜杠菜单的定位祖先 / content field is the positioning ancestor of the slash menu */
.ad-text-field { position: relative; }
.ad-label { font-size: var(--fs-12, 12px); color: var(--muted); }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
.ad-select, .ad-textarea, .ad-input {
  width: 100%; box-sizing: border-box; padding: 8px 10px; font-size: var(--fs-13, 13px);
  border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-1, transparent); color: var(--fg);
  font-family: inherit;
}
.ad-select:focus, .ad-textarea:focus, .ad-input:focus { outline: none; border-color: var(--accent); }
.ad-textarea { resize: vertical; min-height: 64px; }
/* 内容字段作为斜杠菜单的定位祖先 / content field is positioning ancestor of slash menu */
.ad-text-field { position: relative; }
/* 次要信息折叠区：一个弱化的文字开关 + 展开后的缩进字段组 */
.ad-advanced { display: flex; flex-direction: column; gap: var(--s-2); }
.ad-adv-toggle { display: inline-flex; align-items: center; gap: 6px; align-self: flex-start; border: none; background: transparent; padding: 2px 0; font-size: var(--fs-12, 12px); color: var(--muted); cursor: pointer; font-family: inherit; }
.ad-adv-toggle:hover { color: var(--fg); }
.ad-adv-chev { transition: transform 0.15s ease; flex-shrink: 0; }
.ad-adv-chev.open { transform: rotate(90deg); }
.ad-adv-summary { color: var(--subtle); }
.ad-adv-body { display: flex; flex-direction: column; gap: var(--s-3); padding-left: 18px; }
.ad-check { display: flex; align-items: center; gap: var(--s-2); font-size: var(--fs-13, 13px); color: var(--fg); cursor: pointer; }
.ad-check input { accent-color: var(--accent); width: 14px; height: 14px; }
.ad-error { margin: 0; font-size: var(--fs-12, 12px); color: var(--error); }
.ad-hint { margin: 0; font-size: var(--fs-12, 12px); color: var(--subtle); line-height: 1.5; }
.ad-footer { display: flex; justify-content: flex-end; gap: var(--s-2); padding: var(--s-3) var(--s-5) var(--s-4); border-top: 1px solid var(--border); }
.btn-cancel, .btn-submit { padding: 6px 14px; font-size: var(--fs-13, 13px); border-radius: var(--radius-sm); cursor: pointer; }
.btn-cancel { border: 1px solid var(--border); background: transparent; color: var(--muted); }
.btn-cancel:hover { color: var(--fg); border-color: var(--border-strong); }
.btn-submit { border: none; background: var(--accent); color: var(--accent-fg); font-weight: 500; }
.btn-submit:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
