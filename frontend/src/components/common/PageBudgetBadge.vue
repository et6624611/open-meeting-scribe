<template>
  <!-- 一页纸系数角标 / One-page factor badge：系数从属单个会议，长在最需要它的面板头上 -->
  <div class="page-budget">
    <button
      ref="btnEl"
      class="page-budget-btn"
      :class="{ 'is-open': visible, 'is-nondefault': normalized !== 1 }"
      v-bind="triggerAttrs"
      @click="toggle"
    >{{ t('common.page_budget.level_label', { n: labelFactor }) }}</button>
    <div ref="menuEl" v-bind="menuAttrs" class="page-budget-menu" :class="{ 'is-open': visible }" role="menu">
      <div class="page-budget-menu-head">{{ t('common.page_budget.label') }}</div>
      <button
        v-for="f in PAGE_FACTORS" :key="f"
        class="page-budget-item"
        :class="{ 'is-active': f === normalized }"
        role="menuitem"
        @click="pick(f)"
      >
        <span class="page-budget-item-label">{{ t('common.page_budget.level_label', { n: f }) }}</span>
        <span class="page-budget-item-desc">{{ t('common.page_budget.desc.' + descKey(f)) }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 一页纸系数角标 / One-page factor badge
 *
 * 展示当前会议的系数档位（如「1 页」），点击弹出四档小菜单选择。
 * 组件自行 PATCH task.one_page.[surface] 并乐观更新 task store；洞察面改档会触发
 * 后端卡集重排，宿主需监听 changed 事件重拉消息。纪要面改档仅存值，
 * 下次生成纪要时生效（不自动重算，防误触耗 LLM 配额）。
 * Shows the per-meeting factor; picking a level PATCHes task.one_page[surface].
 * Insights side: the server rebalances the card set in the same request — listen to
 * `changed` to reload messages. Summary side: takes effect on next summary generation.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePopMenu } from '@/composables/usePopMenu'
import { updateTask } from '@/api/tasks'
import { useTaskStore } from '@/stores/task'
import { showToast } from '@/composables/useToast'
import { PAGE_FACTORS, normalizeFactor } from '@/utils/pageBudget'

const { t } = useI18n()

const props = defineProps<{
  taskId: string
  /** 约束面：纪要正文 / 洞察卡集，各自一页、互不相加 / Surface: summary or insights, each with its own page */
  surface: 'summary' | 'insights'
  /** 当前系数（宿主从 task.one_page 解析；缺省按 1） / Current factor resolved from task JSON */
  factor: number | null | undefined
}>()

const emit = defineEmits<{
  (e: 'changed', factor: number): void
}>()

const menuEl = ref<HTMLElement | null>(null)
const btnEl = ref<HTMLElement | null>(null)
const { visible, toggle, close, triggerAttrs, menuAttrs } = usePopMenu(menuEl, btnEl)

const taskStore = useTaskStore()
const saving = ref(false)

const normalized = computed(() => normalizeFactor(props.factor))
const labelFactor = computed(() => (normalized.value % 1 === 0 ? normalized.value.toFixed(0) : String(normalized.value)))

/** 档位 → 说明文案 key（下划线命名，规避 vue-i18n 连字符路径解析陷阱） */
function descKey(f: number): string {
  return f === 0.5 ? 'f0_5' : f === 1 ? 'f1' : f === 1.5 ? 'f1_5' : 'f2'
}

async function pick(f: number) {
  close()
  if (f === normalized.value || saving.value || !props.taskId) return
  saving.value = true
  try {
    const resp = await updateTask(props.taskId, { one_page: { [props.surface]: f } })
    // 乐观同步本地任务对象（后端 PATCH 响应携带合并后的完整 one_page）
    taskStore.patchTaskLocal(props.taskId, { one_page: resp.one_page ?? { [props.surface]: f } })
    showToast(
      props.surface === 'summary' ? t('common.page_budget.toast_summary') : t('common.page_budget.toast_insights'),
      'success'
    )
    emit('changed', f)
  } catch {
    showToast(t('common.page_budget.failed'), 'error')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.page-budget {
  position: relative;
  display: inline-flex;
  align-items: center;
}
.page-budget-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--muted);
  font-size: var(--fs-11);
  font-family: inherit;
  line-height: 1.6;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}
.page-budget-btn:hover,
.page-budget-btn.is-open {
  color: var(--accent);
  border-color: var(--accent);
}
/* 非默认档强调：提醒本会已偏离标准一页预算 */
.page-budget-btn.is-nondefault {
  color: var(--proactive, var(--accent));
  border-color: var(--proactive, var(--accent));
  background: var(--proactive-soft, transparent);
}
.page-budget-menu {
  position: fixed;
  z-index: var(--z-popover);
  min-width: 190px;
  padding: var(--s-1) 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
  box-shadow: var(--shadow-float, 0 8px 24px rgba(0, 0, 0, 0.18));
  display: none;
}
.page-budget-menu.is-open {
  display: block;
}
.page-budget-menu-head {
  padding: var(--s-1) var(--s-3) var(--s-1);
  font-size: var(--fs-11);
  color: var(--subtle);
}
.page-budget-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  width: 100%;
  padding: var(--s-1) var(--s-3);
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
  font-family: inherit;
}
.page-budget-item:hover {
  background: var(--accent-soft, var(--surface-2));
}
.page-budget-item.is-active .page-budget-item-label {
  color: var(--accent);
  font-weight: 600;
}
.page-budget-item-label {
  font-size: var(--fs-12);
  color: var(--fg);
}
.page-budget-item-desc {
  font-size: var(--fs-11);
  color: var(--muted);
}
</style>
