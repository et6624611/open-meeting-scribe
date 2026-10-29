<script setup lang="ts">
/**
 * 企业版管理台（档⑥，UI 规格 §4，契约 §1.3/§1.6/§1.7）
 *
 * 三页签：概览（服务开关+加密状态+AI 区）/ 用户管理 / 数据与备份（只读承诺卡）。
 * 不提供任何查看员工会议内容的入口（裁决 QA Q2）；员工端除头像菜单管理员项外无管理入口。
 */
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useInstanceStore } from '@/stores/instance'
import {
  adminListUsers, adminCreateUser, adminSetUserStatus, adminResetUser, adminDeleteUserData,
  adminServiceOpen, adminGetAi, adminPutAi, type AdminUser, type AiSettings,
} from '@/api/admin'
import { showToast } from '@/composables/useToast'

const { t } = useI18n()
const instance = useInstanceStore()

const tab = ref<'overview' | 'users' | 'data'>('overview')
const users = ref<AdminUser[]>([])
const usersLoading = ref(false)
// W2-04：「最近更新」保留为排序列（数据新鲜度判断），默认降序
const sortUpdatedDesc = ref(true)
function toggleSortUpdated() { sortUpdatedDesc.value = !sortUpdatedDesc.value }

const activeCount = computed(() => users.value.filter(u => u.status === 'active').length)
const pendingCount = computed(() => users.value.filter(u => u.status === 'pending').length)

async function loadUsers() {
  usersLoading.value = true
  try {
    const list = await adminListUsers()
    list.sort((a, b) => (sortUpdatedDesc.value ? b.updated_at.localeCompare(a.updated_at) : a.updated_at.localeCompare(b.updated_at)))
    users.value = list
  } catch { showToast(t('login.enterprise.err_service_error', { status: '-' }), 'error') }
  finally { usersLoading.value = false }
}

onMounted(() => { void instance.refreshInfo(); void loadUsers() })

/* ── 服务开关 ── */
const switching = ref(false)
async function toggleService() {
  const target = !instance.serviceOpen
  switching.value = true
  try {
    await adminServiceOpen(target)
    await instance.refreshInfo()
  } catch {
    showToast(t('login.enterprise.err_service_error', { status: '-' }), 'error')
  } finally { switching.value = false }
}

/* ── 新建用户 + 邀请码一次性展示 ── */
const showNewForm = ref(false)
const newName = ref('')
const newAccount = ref('')
const creating = ref(false)
const revealedCode = ref<string | null>(null)
const revealedFor = ref('')
const copied = ref(false)

async function createUser() {
  if (!newName.value.trim() || !newAccount.value.trim() || creating.value) return
  creating.value = true
  try {
    const r = await adminCreateUser(newName.value.trim(), newAccount.value.trim())
    revealedCode.value = r.invite_code
    revealedFor.value = newName.value.trim()
    showNewForm.value = false
    newName.value = ''
    newAccount.value = ''
    await loadUsers()
  } catch {
    showToast(t('login.enterprise.err_service_error', { status: '-' }), 'error')
  } finally { creating.value = false }
}

async function copyCode() {
  if (!revealedCode.value) return
  try { await navigator.clipboard.writeText(revealedCode.value); copied.value = true } catch { /* 剪贴板不可用时用户可手抄一次展示 */ }
}

async function resetUser(u: AdminUser) {
  try {
    const r = await adminResetUser(u.user_id)
    revealedCode.value = r.invite_code
    revealedFor.value = u.display_name
    await loadUsers()
    showToast(t('enterprise.admin.users.reset_sent'), 'success')
  } catch { showToast(t('login.enterprise.err_service_error', { status: '-' }), 'error') }
}

async function toggleStatus(u: AdminUser) {
  const target = u.status === 'disabled' ? 'active' : 'disabled'
  try {
    await adminSetUserStatus(u.user_id, target)
    await loadUsers()
  } catch { showToast(t('login.enterprise.err_service_error', { status: '-' }), 'error') }
}

/* ── 整包删除：二次确认 + 输入账号名 ── */
const deleteTarget = ref<AdminUser | null>(null)
const deleteConfirmText = ref('')
async function confirmDelete() {
  if (!deleteTarget.value || deleteConfirmText.value.trim() !== deleteTarget.value.login_account) return
  try {
    await adminDeleteUserData(deleteTarget.value.user_id)
    deleteTarget.value = null
    deleteConfirmText.value = ''
    await loadUsers()
  } catch { showToast(t('login.enterprise.err_service_error', { status: '-' }), 'error') }
}

/* ── 加密状态（W2-01：常驻状态卡=状态+收益+可复制指引；执行走 DevOps 重配流程） ── */
const httpsMode = location.protocol === 'https:'
const guideCopied = ref(false)
async function copyGuide() {
  try { await navigator.clipboard.writeText(t('enterprise.admin.encryption.guide_cmd')); guideCopied.value = true } catch { /* 剪贴板不可用时文本可选中手抄 */ }
}

/* ── AI 出网开关（§1.7，实测扁平 DTO；api_key 只写不回显） ── */
const ai = ref<AiSettings>({ enabled: false, base_url: null, model: null })
const aiBaseUrl = ref('')
const aiModel = ref('')
const aiKey = ref('')
const aiSaving = ref(false)
onMounted(async () => { try { ai.value = await adminGetAi(); aiBaseUrl.value = ai.value.base_url || ''; aiModel.value = ai.value.model || '' } catch { /* 默认关态呈现 */ } })

async function saveAi(enabled: boolean) {
  aiSaving.value = true
  try {
    await adminPutAi({ enabled, base_url: aiBaseUrl.value, model: aiModel.value, ...(aiKey.value ? { api_key: aiKey.value } : {}) })
    ai.value = { enabled, base_url: aiBaseUrl.value, model: aiModel.value }
    aiKey.value = ''
    await instance.refreshInfo()
  } catch { showToast(t('login.enterprise.err_service_error', { status: '-' }), 'error') }
  finally { aiSaving.value = false }
}

function statusLabel(s: string): string {
  if (s === 'active') return t('enterprise.admin.users.status_active')
  if (s === 'disabled') return t('enterprise.admin.users.status_disabled')
  return t('enterprise.admin.users.status_pending')
}
</script>

<template>
  <div class="adm-root">
    <header class="adm-head">
      <h1>{{ t('enterprise.admin.title') }}</h1>
      <RouterLink to="/" class="adm-back">{{ t('enterprise.admin.back_to_workspace') }}</RouterLink>
    </header>

    <nav class="adm-tabs" role="tablist">
      <button role="tab" :aria-selected="tab === 'overview'" :class="{ active: tab === 'overview' }" @click="tab = 'overview'">{{ t('enterprise.admin.tab_overview') }}</button>
      <button role="tab" :aria-selected="tab === 'users'" :class="{ active: tab === 'users' }" @click="tab = 'users'">{{ t('enterprise.admin.tab_users') }}</button>
      <button role="tab" :aria-selected="tab === 'data'" :class="{ active: tab === 'data' }" @click="tab = 'data'">{{ t('enterprise.admin.tab_data') }}</button>
    </nav>

    <!-- 概览 -->
    <section v-if="tab === 'overview'" class="adm-panel">
      <div class="adm-card adm-service-card">
        <div>
          <div class="adm-card-title">{{ t('enterprise.admin.service_switch.label') }}</div>
          <div class="adm-service-state" :class="instance.serviceOpen ? 'is-on' : 'is-off'">
            {{ instance.serviceOpen ? t('enterprise.admin.service_switch.on') : t('enterprise.admin.service_switch.off') }}
          </div>
          <p v-if="!instance.serviceOpen" class="adm-hint">{{ t('enterprise.admin.service_switch.paused_hint') }}</p>
        </div>
        <button class="adm-switch" :class="{ 'is-on': instance.serviceOpen }" :disabled="switching" role="switch"
                :aria-checked="instance.serviceOpen" @click="toggleService">
          <span class="adm-switch-knob"></span>
        </button>
      </div>
      <div class="adm-stats">
        <div class="adm-stat"><b>{{ activeCount }}</b>{{ t('enterprise.admin.overview_users') }}</div>
        <div class="adm-stat"><b>{{ pendingCount }}</b>{{ t('enterprise.admin.overview_pending') }}</div>
      </div>
      <div class="adm-card">
        <div class="adm-card-title">{{ t('enterprise.admin.encryption.title') }}</div>
        <p class="adm-hint">{{ httpsMode ? t('enterprise.admin.encryption.current_https') : t('enterprise.admin.encryption.current_http') }}</p>
        <p class="adm-sub">{{ t('enterprise.admin.encryption.benefit') }}</p>
        <code v-if="!httpsMode" class="adm-code adm-guide-cmd">{{ t('enterprise.admin.encryption.guide_cmd') }}</code>
        <button v-if="!httpsMode" class="adm-btn is-ghost adm-guide-copy" @click="copyGuide">{{ guideCopied ? t('enterprise.admin.users.invite_copied') : t('enterprise.admin.encryption.copy_guide') }}</button>
      </div>
      <div class="adm-card">
        <div class="adm-card-title">{{ t('enterprise.admin.ai.title') }}</div>
        <p class="adm-hint">{{ ai.enabled ? t('enterprise.admin.ai.current_on') : t('enterprise.admin.ai.current_off') }}</p>
        <div class="adm-ai-form">
          <input v-model="aiBaseUrl" :placeholder="t('enterprise.admin.ai.base_url')" autocomplete="off">
          <input v-model="aiModel" :placeholder="t('enterprise.admin.ai.model')" autocomplete="off">
          <input v-model="aiKey" type="password" :placeholder="t('enterprise.admin.ai.cloud_credential')" autocomplete="new-password">
        </div>
        <p class="adm-sub">{{ t('enterprise.admin.ai.credential_note') }}</p>
        <p class="adm-sub">{{ t('enterprise.admin.ai.egress_notice') }}</p>
        <div class="adm-ai-actions">
          <button class="adm-btn" :disabled="aiSaving" @click="saveAi(true)">{{ t('enterprise.admin.ai.enable') }}</button>
          <button class="adm-btn is-ghost" :disabled="aiSaving" @click="saveAi(false)">{{ t('enterprise.admin.ai.disable') }}</button>
        </div>
      </div>
    </section>

    <!-- 用户管理 -->
    <section v-else-if="tab === 'users'" class="adm-panel">
      <div class="adm-toolbar">
        <button class="adm-btn" @click="showNewForm = !showNewForm">{{ t('enterprise.admin.users.new_user') }}</button>
      </div>
      <form v-if="showNewForm" class="adm-newform" @submit.prevent="createUser">
        <input v-model="newName" :placeholder="t('enterprise.admin.users.form_name')" required>
        <input v-model="newAccount" :placeholder="t('enterprise.admin.users.form_account')" required>
        <button type="submit" class="adm-btn" :disabled="creating">{{ t('enterprise.admin.users.form_submit') }}</button>
      </form>

      <table class="adm-table" :aria-busy="usersLoading">
        <thead>
          <tr>
            <th>{{ t('enterprise.admin.users.col_name') }}</th>
            <th>{{ t('enterprise.admin.users.col_account') }}</th>
            <th>{{ t('enterprise.admin.users.col_status') }}</th>
            <th>{{ t('enterprise.admin.users.col_created') }}</th>
            <th>{{ t('enterprise.admin.users.col_last_used') }}</th>
            <th><button class="adm-th-sort" @click="toggleSortUpdated">{{ t('enterprise.admin.users.col_updated') }}{{ sortUpdatedDesc ? ' ↓' : ' ↑' }}</button></th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.user_id">
            <td>{{ u.display_name }}</td>
            <td>{{ u.login_account }}</td>
            <td><span class="adm-status" :class="'is-' + u.status">{{ statusLabel(u.status) }}</span></td>
            <td>{{ u.created_at.slice(0, 10) }}</td>
            <td>{{ u.last_used_at ? u.last_used_at.slice(0, 10) : '—' }}</td>
            <td>{{ u.updated_at.slice(0, 10) }}</td>
            <td class="adm-row-actions">
              <button v-if="u.status !== 'pending'" class="adm-link" @click="resetUser(u)">{{ t('enterprise.admin.users.act_reset') }}</button>
              <button v-if="u.role !== 'admin'" class="adm-link" @click="toggleStatus(u)">{{ u.status === 'disabled' ? t('enterprise.admin.users.act_enable') : t('enterprise.admin.users.act_disable') }}</button>
              <button v-if="u.role !== 'admin'" class="adm-link is-danger" @click="deleteTarget = u; deleteConfirmText = ''">{{ t('enterprise.admin.users.act_delete_data') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 数据与备份（只读承诺卡） -->
    <section v-else class="adm-panel">
      <div class="adm-card">
        <div class="adm-card-title">{{ t('enterprise.admin.data.title') }}</div>
        <p class="adm-hint">{{ t('enterprise.admin.data.server_text_overview') }}</p>
        <ul class="adm-promise">
          <li>{{ t('enterprise.admin.data.promise_line1') }}</li>
          <li>{{ t('enterprise.admin.data.promise_line2') }}</li>
          <li>{{ t('enterprise.admin.data.promise_line3') }}</li>
        </ul>
        <p class="adm-sub">{{ t('enterprise.admin.data.backup_guide') }}</p>
      </div>
    </section>

    <!-- 邀请码一次性展示（创建/重置共用；关闭即销毁，服务端只存 hash） -->
    <div v-if="revealedCode" class="adm-modal-mask">
      <div class="adm-modal" role="dialog" aria-modal="true">
        <div class="adm-card-title">{{ t('enterprise.admin.users.invite_shown_title') }}</div>
        <code class="adm-code">{{ revealedCode }}</code>
        <p class="adm-hint">{{ t('enterprise.admin.users.invite_shown_hint') }}</p>
        <div class="adm-ai-actions">
          <button class="adm-btn" @click="copyCode">{{ copied ? t('enterprise.admin.users.invite_copied') : t('enterprise.admin.users.invite_copy') }}</button>
          <button class="adm-btn is-ghost" @click="revealedCode = null; copied = false">{{ t('common.action.close') }}</button>
        </div>
      </div>
    </div>

    <!-- 整包删除二次确认（输入账号名） -->
    <div v-if="deleteTarget" class="adm-modal-mask">
      <div class="adm-modal" role="alertdialog" aria-modal="true">
        <div class="adm-card-title is-danger">{{ t('enterprise.admin.users.delete_confirm_title') }}</div>
        <p class="adm-hint">{{ t('enterprise.admin.users.delete_confirm_hint', { account: deleteTarget.login_account }) }}</p>
        <input v-model="deleteConfirmText" :placeholder="t('enterprise.admin.users.delete_confirm_placeholder')" class="adm-confirm-input">
        <div class="adm-ai-actions">
          <button class="adm-btn is-danger" :disabled="deleteConfirmText.trim() !== deleteTarget.login_account" @click="confirmDelete">{{ t('enterprise.admin.users.delete_confirm_btn') }}</button>
          <button class="adm-btn is-ghost" @click="deleteTarget = null">{{ t('topbar.abandon_cancel') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.adm-root { max-width: 980px; margin: 0 auto; padding: var(--s-3, 24px); color: var(--fg, #222); }
.adm-head { display: flex; align-items: baseline; justify-content: space-between; }
.adm-head h1 { font-size: 18px; margin: var(--s-3, 16px) 0; }
.adm-back { font-size: var(--fs-12, 12px); color: var(--muted, #666); }
.adm-tabs { display: flex; gap: var(--s-2, 8px); border-bottom: 1px solid var(--border, #e2e2de); margin-bottom: var(--s-3, 16px); }
.adm-tabs button { padding: 8px 14px; border: none; background: none; cursor: pointer; font-size: var(--fs-13, 13px); color: var(--muted, #666); border-bottom: 2px solid transparent; }
.adm-tabs button.active { color: var(--fg, #222); border-bottom-color: var(--accent, #2a6); font-weight: 600; }
.adm-panel { display: flex; flex-direction: column; gap: var(--s-3, 16px); }
.adm-card { background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); padding: var(--s-3, 16px); }
.adm-card-title { font-weight: 600; font-size: var(--fs-13, 13px); margin-bottom: var(--s-2, 8px); }
.adm-card-title.is-danger { color: var(--warn, #c33); }
.adm-service-card { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3, 16px); }
.adm-service-state { font-size: var(--fs-12, 12px); }
.adm-service-state.is-on { color: var(--accent, #2a6); }
.adm-service-state.is-off { color: var(--warn, #b60); }
.adm-switch { position: relative; width: 52px; height: 28px; border-radius: 999px; border: none; cursor: pointer; background: var(--surface-3, #ccc); transition: background 0.15s; flex: none; }
.adm-switch.is-on { background: var(--accent, #2a6); }
.adm-switch-knob { position: absolute; top: 3px; left: 3px; width: 22px; height: 22px; border-radius: 50%; background: #fff; transition: left 0.15s; }
.adm-switch.is-on .adm-switch-knob { left: 27px; }
.adm-hint { font-size: var(--fs-12, 12px); color: var(--muted, #666); margin: 0; }
.adm-sub { font-size: var(--fs-11, 11px); color: var(--subtle, #999); margin: var(--s-2, 8px) 0 0; }
.adm-stats { display: flex; gap: var(--s-3, 16px); }
.adm-stat { flex: 1; background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); padding: var(--s-3, 16px); font-size: var(--fs-12, 12px); color: var(--muted, #666); }
.adm-stat b { display: block; font-size: 22px; color: var(--fg, #222); }
.adm-ai-form { display: flex; flex-direction: column; gap: var(--s-2, 8px); margin-top: var(--s-2, 8px); }
.adm-ai-form input { padding: 8px 10px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); background: var(--surface-2, #fafaf8); font-size: var(--fs-12, 12px); }
.adm-ai-actions { display: flex; gap: var(--s-2, 8px); margin-top: var(--s-3, 16px); }
.adm-btn { padding: 8px 14px; border: none; border-radius: var(--radius-sm, 8px); background: var(--accent, #2a6); color: var(--accent-fg, #fff); cursor: pointer; font-size: var(--fs-12, 12px); font-weight: 600; }
.adm-btn.is-ghost { background: none; border: 1px solid var(--border, #d8d8d4); color: var(--fg, #222); font-weight: 400; }
.adm-btn.is-danger { background: var(--warn, #c33); }
.adm-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.adm-toolbar { display: flex; justify-content: flex-end; }
.adm-newform { display: flex; gap: var(--s-2, 8px); }
.adm-newform input { flex: 1; padding: 8px 10px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); }
.adm-table { width: 100%; border-collapse: collapse; background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); font-size: var(--fs-12, 12px); }
.adm-table th, .adm-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border, #eee); }
.adm-table th { color: var(--muted, #666); font-weight: 500; }
.adm-status.is-active { color: var(--accent, #2a6); }
.adm-status.is-disabled { color: var(--muted, #999); }
.adm-status.is-pending { color: var(--warn, #b60); }
.adm-row-actions { white-space: nowrap; }
.adm-link { border: none; background: none; cursor: pointer; color: var(--accent, #2a6); font-size: var(--fs-12, 12px); padding: 2px 6px; }
.adm-link.is-danger { color: var(--warn, #c33); }
.adm-modal-mask { position: fixed; inset: 0; background: rgb(0 0 0 / 0.35); display: grid; place-items: center; z-index: var(--z-toast, 1200); }
.adm-modal { width: min(420px, calc(100vw - 32px)); background: var(--surface, #fff); border-radius: var(--radius-sm, 8px); padding: var(--s-3, 24px); box-shadow: 0 16px 48px rgb(0 0 0 / 0.2); }
.adm-code { display: block; margin: var(--s-2, 8px) 0; padding: 10px 12px; background: var(--surface-2, #f4f4f2); border-radius: var(--radius-sm, 8px); font-family: var(--font-mono, monospace); font-size: 15px; letter-spacing: 1px; user-select: all; }
.adm-confirm-input { width: 100%; margin-top: var(--s-2, 8px); padding: 8px 10px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); box-sizing: border-box; }
.adm-th-sort { border: none; background: none; cursor: pointer; font: inherit; color: inherit; padding: 0; }
.adm-guide-cmd { white-space: pre-wrap; user-select: all; }
.adm-guide-copy { margin-top: var(--s-2, 8px); align-self: flex-start; }
.adm-promise { margin: var(--s-2, 8px) 0 0; padding-left: 18px; font-size: var(--fs-12, 12px); display: flex; flex-direction: column; gap: 4px; }
</style>
