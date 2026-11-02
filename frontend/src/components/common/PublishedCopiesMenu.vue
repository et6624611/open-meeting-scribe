<script setup lang="ts">
/**
 * 原件"已公开到 N 个团队"角标 + 逐团队撤回面（P1-WP-2，UI 规格 §4.3）
 *
 * 数据源=原件 published_copies 读面（契约 §6.5 补漏注，仅计 active 副本，撤回即消失）。
 * 撤回=copy_task_id+team_id 调既有 DELETE（撤回面=读面闭环）；二次确认文案规格逐字。
 * 角标按 distinct team_id 归并（纪要粒度与决策粒度副本分行，granularity 标注供辨识）。
 * 分享状态≠可见性：本角标不改变"个人·仅你可见"徽标（原件徽标语义不动）。
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { unpublishTeamTask } from '@/api/teams'
import { usePopMenu } from '@/composables/usePopMenu'
import { showToast } from '@/composables/useToast'
import type { PublishedCopy } from '@/api/context'

const props = defineProps<{ copies: PublishedCopy[] }>()
const emit = defineEmits<{ withdrawn: [] }>()

const { t } = useI18n()
const btnEl = ref<HTMLElement | null>(null)
const menuEl = ref<HTMLElement | null>(null)
const { visible, close, toggle, triggerAttrs, menuAttrs } = usePopMenu(menuEl, btnEl, { align: 'start', gap: 6 })

const teamCount = computed(() => new Set(props.copies.map((c) => c.team_id)).size)
const confirming = ref<PublishedCopy | null>(null)
const busy = ref(false)

function onWithdraw(c: PublishedCopy) {
  if (busy.value) return
  confirming.value = c
}

function cancelConfirm() { confirming.value = null }

async function confirmWithdraw() {
  const c = confirming.value
  if (!c || busy.value) return
  busy.value = true
  try {
    await unpublishTeamTask(c.team_id, c.copy_task_id)
    showToast(t('enterprise.publish.withdraw_done'), 'success')
    emit('withdrawn')
    confirming.value = null
    close()
  } catch {
    showToast(t('enterprise.publish.withdraw_failed'), 'error')
  } finally { busy.value = false }
}
</script>

<template>
  <div v-if="copies.length" class="pc-root">
    <button
      ref="btnEl"
      type="button"
      class="pc-badge"
      :aria-label="t('enterprise.publish.badge_aria')"
      v-bind="triggerAttrs"
      @click.stop.prevent="toggle()"
      @keydown.stop
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
      {{ t('enterprise.publish.badge_count', { n: teamCount }) }}
    </button>
    <!-- D019 修复：Teleport 挂 body + position:fixed——usePopMenu 的视口坐标不再被卡片容器
         原点二次偏移（右列角标菜单出屏=撤回不可达）；祖先 overflow/transform 劫持同解，
         同 ResponsiveButtonGroup 既定模式 -->
    <Teleport to="body">
      <div v-show="visible" ref="menuEl" class="pc-menu" v-bind="menuAttrs" @click.stop>
      <p class="pc-section">{{ t('enterprise.publish.published_to') }}</p>
      <div v-for="(c, i) in copies" :key="`${c.team_id}-${c.copy_task_id}-${i}`" class="pc-row">
        <template v-if="confirming !== c">
          <div class="pc-row-info">
            <span class="pc-team">{{ c.team_name }}</span>
            <span class="pc-gran">{{ t(c.granularity === 'decision' ? 'enterprise.publish.gran_decision' : 'enterprise.publish.gran_task') }}</span>
          </div>
          <button type="button" class="pc-withdraw" role="menuitem" :aria-label="t('enterprise.publish.withdraw_btn')" @click="onWithdraw(c)">{{ t('enterprise.publish.withdraw_btn') }}</button>
        </template>
        <div v-else class="pc-confirm" role="alertdialog" :aria-label="t('enterprise.publish.withdraw_btn')">
          <p class="pc-confirm-text">{{ t('enterprise.publish.withdraw_confirm_text') }}</p>
          <div class="pc-confirm-actions">
            <button type="button" class="pc-btn is-ghost" :disabled="busy" @click="cancelConfirm">{{ t('common.action.cancel') }}</button>
            <button type="button" class="pc-btn is-danger" :disabled="busy" @click="confirmWithdraw">{{ t('enterprise.publish.withdraw_btn') }}</button>
          </div>
        </div>
      </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.pc-root { position: relative; flex: none; }
.pc-badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border: 1px solid var(--border, #e6e6e2); border-radius: 999px; background: var(--surface-2, #f2f2f0); color: var(--muted, #666); font-size: var(--fs-11, 11px); cursor: pointer; }
.pc-badge:hover { border-color: var(--accent-mid, #4a7); color: var(--fg, #222); }
.pc-badge svg { width: 11px; height: 11px; }
.pc-menu { position: fixed; z-index: var(--z-popover, 1000); min-width: 240px; max-width: 300px; padding: var(--s-2, 8px) 0; background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); box-shadow: 0 8px 24px rgb(0 0 0 / 0.1); }
.pc-section { margin: 2px 14px 6px; font-size: var(--fs-11, 11px); color: var(--subtle, #999); font-weight: 600; }
.pc-row { padding: 4px 14px; }
.pc-row-info { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.pc-team { flex: 1; font-size: var(--fs-12, 12px); color: var(--fg, #222); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pc-gran { flex: none; font-size: var(--fs-11, 11px); color: var(--subtle, #999); }
.pc-withdraw { border: none; background: none; color: var(--warn, #c33); font-size: var(--fs-11, 11px); cursor: pointer; padding: 2px 0; text-align: left; }
.pc-withdraw:hover { text-decoration: underline; }
.pc-confirm { display: flex; flex-direction: column; gap: 6px; background: var(--surface-2, #fafaf8); border-radius: var(--radius-sm, 8px); padding: var(--s-2, 10px); }
.pc-confirm-text { margin: 0; font-size: var(--fs-11, 11px); color: var(--fg, #222); line-height: 1.6; }
.pc-confirm-actions { display: flex; gap: 8px; justify-content: flex-end; }
.pc-btn { padding: 4px 12px; border: none; border-radius: var(--radius-sm, 8px); font-size: var(--fs-11, 11px); cursor: pointer; }
.pc-btn.is-danger { background: var(--warn, #c33); color: #fff; }
.pc-btn.is-ghost { background: none; border: 1px solid var(--border, #d8d8d4); color: var(--fg, #222); }
.pc-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
