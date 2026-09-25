<template>
  <!-- 决策状态管理（DC-R2-c / D6+D7）：改名、标色、闭档位、排序、删除自定义状态
       Status dictionary manager: rename, recolor, toggle closing, reorder, delete custom -->
  <div v-show="modelValue" class="oms-overlay" data-vue-overlay :class="{ 'is-open': modelValue }" @click.self="close">
    <div ref="dialogRef" class="oms-overlay-card sm-dialog" role="dialog" aria-modal="true" aria-labelledby="smTitle">
      <div class="sm-header">
        <h3 id="smTitle">{{ t('decisions.sm_title') }}</h3>
        <button class="sm-close" :title="t('generating.archive_dialog.close')" @click="close">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3l6 6M9 3l-6 6"/></svg>
        </button>
      </div>

      <div class="sm-body">
        <p class="sm-hint">{{ t('decisions.sm_hint') }}</p>

        <ul class="sm-list">
          <li v-for="(s, i) in list" :key="s.id" class="sm-row" :class="{ 'is-system': s.system }">
            <span class="sm-dot" :style="{ background: s.color }" :aria-label="t('decisions.sm_color')"></span>
            <input
              v-model.trim="s.name"
              class="sm-name"
              type="text"
              maxlength="20"
              :disabled="s.system"
              :readonly="!s.system && !isEditing(s.id)"
              :aria-label="t('decisions.sm_rename')"
              @focus="editingId = s.id"
              @blur="commitRename(s)"
              @keydown.enter.prevent="commitRename(s)"
            />
            <label class="sm-check" :title="s.system ? t('decisions.sm_anchor_locked') : t('decisions.sm_closing_hint')">
              <input type="checkbox" :checked="s.closing" :disabled="s.system" @change="toggleClosing(s, ($event.target as HTMLInputElement).checked)" />
              <span>{{ t('decisions.sm_closing') }}</span>
            </label>
            <div class="sm-palette" :aria-label="t('decisions.sm_color')">
              <button
                v-for="c in STATUS_PALETTE"
                :key="c"
                type="button"
                class="sm-swatch"
                :class="{ 'is-active': s.color === c }"
                :style="{ background: c }"
                :title="t('decisions.sm_color')"
                @click="pickColor(s, c)"
              ></button>
            </div>
            <div class="sm-ops">
              <button type="button" class="sm-op" :disabled="i === 0" :title="t('decisions.sm_move_up')" @click="move(i, -1)">
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><polyline points="18 15 12 9 6 15"/></svg>
              </button>
              <button type="button" class="sm-op" :disabled="i === list.length - 1" :title="t('decisions.sm_move_down')" @click="move(i, 1)">
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
              </button>
              <button
                type="button"
                class="sm-op is-danger"
                :disabled="s.system"
                :title="s.system ? t('decisions.sm_anchor_locked') : t('decisions.sm_delete')"
                @click="askDelete(s)"
              >
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              </button>
            </div>
            <span v-if="s.system" class="sm-badge">{{ t('decisions.sm_system') }}</span>
          </li>
        </ul>

        <!-- 删除确认：说明影响条数（引用决策回落到生效中） -->
        <div v-if="pendingDelete" class="sm-confirm" role="alert">
          <span>{{ t('decisions.sm_delete_confirm', { name: pendingDelete.name }) }}</span>
          <button type="button" class="sm-op" @click="pendingDelete = null">{{ t('decisions.add_cancel') }}</button>
          <button type="button" class="sm-op is-danger-solid" @click="confirmDelete">{{ t('decisions.delete_confirm_btn') }}</button>
        </div>

        <!-- 新增状态 -->
        <div class="sm-add">
          <input v-model.trim="newName" class="sm-name" type="text" maxlength="20" :placeholder="t('decisions.sm_new_placeholder')" @keydown.enter.prevent="addStatus" />
          <label class="sm-check">
            <input type="checkbox" v-model="newClosing" />
            <span>{{ t('decisions.sm_closing') }}</span>
          </label>
          <div class="sm-palette">
            <button
              v-for="c in STATUS_PALETTE"
              :key="c"
              type="button"
              class="sm-swatch"
              :class="{ 'is-active': newColor === c }"
              :style="{ background: c }"
              :title="t('decisions.sm_color')"
              @click="newColor = c"
            ></button>
          </div>
          <button type="button" class="sm-submit" :disabled="!newName || busy" @click="addStatus">+ {{ t('decisions.sm_add') }}</button>
        </div>
        <p v-if="errorMsg" class="sm-error" role="alert">{{ errorMsg }}</p>
      </div>

      <div class="sm-footer">
        <button class="btn-cancel" @click="close">{{ t('decisions.sm_done') }} <kbd>ESC</kbd></button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { extractErrorMessage } from '@/api/client'
import {
  STATUS_PALETTE, createStatus, deleteStatus, fetchStatuses, reorderStatuses, updateStatus,
  type DecisionStatusItem,
} from '@/api/decisionStatuses'
import { useDialog } from '@/composables/useDialog'
import { showToast } from '@/composables/useToast'

const { t, locale } = useI18n()

const props = defineProps<{ modelValue: boolean; statuses: DecisionStatusItem[] }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'changed', list: DecisionStatusItem[]): void
}>()

const { dialogRef } = useDialog(computed(() => props.modelValue), () => close())

const list = ref<DecisionStatusItem[]>([])
/** 已提交名称的本地快照：改名变更判定与失败回滚均以它为准，
 *  不依赖父级 props 是否已同步（新建行首次改名时 props 可能仍缺该 id）。 */
const baseline = ref<Record<string, string>>({})
const editingId = ref('')
const pendingDelete = ref<DecisionStatusItem | null>(null)
const newName = ref('')
const newColor = ref(STATUS_PALETTE[4])
const newClosing = ref(false)
const busy = ref(false)
const errorMsg = ref('')

watch(() => props.modelValue, (open) => {
  if (open) {
    list.value = props.statuses.map(s => ({ ...s }))
    syncBaseline()
    editingId.value = ''
    pendingDelete.value = null
    newName.value = ''
    newClosing.value = false
    errorMsg.value = ''
  }
})

function syncBaseline() {
  baseline.value = Object.fromEntries(list.value.map(s => [s.id, s.name]))
}

function close() {
  emit('update:modelValue', false)
}

function isEditing(id: string): boolean {
  return editingId.value === id
}

/** 名称提交：锚点行只读不会触发；重名/非法由后端 400，失败回滚为上次已提交名。
 *  Enter 与 blur 双通道均可提交，重复调用时名称已一致→自然空转。 */
async function commitRename(s: DecisionStatusItem) {
  const prev = baseline.value[s.id] ?? s.name
  editingId.value = ''
  if (s.system || s.name === prev) {
    if (s.system) s.name = prev
    return
  }
  if (await apply(() => updateStatus(s.id, { name: s.name }), s.id, { name: prev })) {
    baseline.value = { ...baseline.value, [s.id]: s.name }
  }
}

async function toggleClosing(s: DecisionStatusItem, value: boolean) {
  await apply(() => updateStatus(s.id, { closing: value }), s.id, { closing: s.closing })
}

async function pickColor(s: DecisionStatusItem, color: string) {
  if (s.color === color) return
  await apply(() => updateStatus(s.id, { color }), s.id, { color: s.color })
}

/** 统一写操作：成功后向上同步列表；失败回滚 patch 前字段并提示 */
async function apply(req: () => Promise<unknown>, id: string, rollback: Partial<DecisionStatusItem>) {
  busy.value = true
  errorMsg.value = ''
  try {
    await req()
    const next = await fetchFresh()
    emit('changed', next)
    return true
  } catch (e) {
    const row = list.value.find(x => x.id === id)
    if (row) Object.assign(row, rollback)
    errorMsg.value = extractErrorMessage(e, t('decisions.sm_save_failed'))
    return false
  } finally {
    busy.value = false
  }
}

async function fetchFresh(): Promise<DecisionStatusItem[]> {
  const next = await fetchStatuses()
  list.value = next.map(s => ({ ...s }))
  syncBaseline()
  return list.value
}

async function addStatus() {
  const name = newName.value.trim()
  if (!name) return
  busy.value = true
  errorMsg.value = ''
  try {
    await createStatus({ name, color: newColor.value, closing: newClosing.value })
    newName.value = ''
    newClosing.value = false
    const next = await fetchFresh()
    emit('changed', next)
    showToast(t('decisions.sm_added', { name }), 'success')
  } catch (e) {
    errorMsg.value = extractErrorMessage(e, t('decisions.sm_save_failed'))
  } finally {
    busy.value = false
  }
}

function askDelete(s: DecisionStatusItem) {
  if (s.system) return
  pendingDelete.value = s
}

async function confirmDelete() {
  const s = pendingDelete.value
  if (!s) return
  pendingDelete.value = null
  busy.value = true
  try {
    const res = await deleteStatus(s.id)
    const next = await fetchFresh()
    emit('changed', next)
    showToast(res.reassigned > 0 ? t('decisions.sm_deleted_reassigned', { name: s.name, count: res.reassigned }) : t('decisions.sm_deleted', { name: s.name }), 'success')
  } catch (e) {
    errorMsg.value = extractErrorMessage(e, t('decisions.sm_save_failed'))
  } finally {
    busy.value = false
  }
}

/** 上移/下移：本地交换后整体提交顺序（顺序是唯一事实源） */
async function move(index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= list.value.length) return
  const next = [...list.value]
  const [row] = next.splice(index, 1)
  next.splice(target, 0, row)
  list.value = next
  busy.value = true
  try {
    await reorderStatuses(next.map(s => s.id))
    emit('changed', next.map(s => ({ ...s })))
  } catch (e) {
    errorMsg.value = extractErrorMessage(e, t('decisions.sm_save_failed'))
    list.value = props.statuses.map(s => ({ ...s }))
  } finally {
    busy.value = false
  }
}

// locale 切换时列表名回退到服务端值（自定义状态不参与双语，锚点名由后端 name_en 提供）
watch(locale, () => { list.value = props.statuses.map(s => ({ ...s })) })
</script>

<style scoped>
.sm-dialog { width: 620px; max-width: 94vw; max-height: 86vh; overflow: auto; border-radius: var(--radius-lg); border: none; box-shadow: var(--dropdown-shadow); }
.sm-header { display: flex; align-items: center; justify-content: space-between; padding: var(--s-4) var(--s-5); border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface-1, var(--bg)); }
.sm-header h3 { font-size: var(--fs-15, 15px); font-weight: 600; margin: 0; }
.sm-close { border: none; background: transparent; color: var(--muted); cursor: pointer; padding: 4px; border-radius: var(--radius-sm); }
.sm-close:hover { background: var(--surface-2); color: var(--fg); }
.sm-body { padding: var(--s-4) var(--s-5); display: flex; flex-direction: column; gap: var(--s-3); }
.sm-hint { margin: 0; font-size: var(--fs-12, 12px); color: var(--muted); line-height: 1.6; }
.sm-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.sm-row { display: flex; align-items: center; gap: var(--s-2); padding: 6px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm); }
.sm-row.is-system { background: var(--surface-2); }
.sm-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.sm-name { flex: 1; min-width: 90px; padding: 4px 6px; font-size: var(--fs-13, 13px); border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; color: var(--fg); }
.sm-name:not([readonly]):not([disabled]) { border-color: var(--accent); }
.sm-name[disabled] { color: var(--muted); cursor: not-allowed; }
.sm-check { display: inline-flex; align-items: center; gap: 4px; font-size: var(--fs-12, 12px); color: var(--muted); white-space: nowrap; }
.sm-check input { accent-color: var(--accent); }
.sm-palette { display: flex; gap: 3px; }
.sm-swatch { width: 14px; height: 14px; border-radius: 50%; border: 1px solid var(--border); cursor: pointer; padding: 0; }
.sm-swatch.is-active { outline: 2px solid var(--accent); outline-offset: 1px; }
.sm-ops { display: inline-flex; gap: 2px; }
.sm-op { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--muted); cursor: pointer; font-size: var(--fs-12, 12px); padding: 0; }
.sm-op:hover:not(:disabled) { color: var(--fg); border-color: var(--border-strong); }
.sm-op:disabled { opacity: 0.35; cursor: not-allowed; }
.sm-op.is-danger:hover:not(:disabled) { color: var(--error); border-color: var(--error); }
.sm-op.is-danger-solid { width: auto; padding: 2px 8px; border: none; background: var(--error); color: #fff; }
.sm-badge { font-size: var(--fs-11, 11px); color: var(--subtle); white-space: nowrap; }
.sm-confirm { display: flex; align-items: center; gap: var(--s-2); font-size: var(--fs-12, 12px); color: var(--error); padding: 6px 8px; border: 1px solid var(--error); border-radius: var(--radius-sm); }
.sm-add { display: flex; align-items: center; gap: var(--s-2); padding-top: var(--s-2); border-top: 1px dashed var(--border); }
.sm-submit { padding: 4px 10px; font-size: var(--fs-13, 13px); border: none; border-radius: var(--radius-sm); background: var(--accent); color: var(--accent-fg); cursor: pointer; white-space: nowrap; }
.sm-submit:disabled { opacity: 0.45; cursor: not-allowed; }
.sm-error { margin: 0; font-size: var(--fs-12, 12px); color: var(--error); }
.sm-footer { display: flex; justify-content: flex-end; padding: var(--s-3) var(--s-5) var(--s-4); border-top: 1px solid var(--border); }
.btn-cancel { padding: 6px 14px; font-size: var(--fs-13, 13px); border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--muted); cursor: pointer; }
.btn-cancel:hover { color: var(--fg); border-color: var(--border-strong); }
</style>
