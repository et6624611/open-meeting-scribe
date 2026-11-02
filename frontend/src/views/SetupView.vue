<script setup lang="ts">
/**
 * 企业实例初始化向导（D005，产品裁决=首管理员必须产品内完成）
 *
 * 两步流程（对齐后端契约 34ed119，X05 纪律：界面零命令行引导）：
 *  step1 建管理员占位账号（默认绑定手机账号 13373013103=存量数据认领语义，裁决④）
 *        → POST /api/v1/auth/bootstrap（仅本机回环+零 admin 可用）返回一次性邀请码；
 *  step2 凭该邀请码自助设置密码 → POST /api/v1/auth/activate（管理员不经手他人密码纪律不变，
 *        此处本人即管理员，密码自设）→ 建会话进入空间。
 * needs_bootstrap=false 后本路由服务端通道关闭（409 bootstrap_done），前端由守卫+登录页跳转隔离。
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { bootstrapCreateAdmin, enterpriseActivate, authErrorCode, type BootstrapResult } from '@/api/enterpriseAuth'
import { useUserStore } from '@/stores/user'
import LockedPrivacyBlock from '@/components/common/LockedPrivacyBlock.vue'

const { t } = useI18n()
const router = useRouter()
const userStore = useUserStore()

const step = ref<1 | 2>(1)
const displayName = ref('')
const account = ref('13373013103')
const submitting = ref(false)
const errorMsg = ref('')

const boot = ref<BootstrapResult | null>(null)
const password = ref('')
const confirm = ref('')

function clearError() { errorMsg.value = '' }

/** 如实引导文案的落地地址：把当前主机名换成 localhost（保留协议与端口），如 http://localhost:8010 */
function localAdminUrl(): string {
  const { protocol, port } = window.location
  const scheme = protocol === 'https:' ? 'https' : 'http'
  return port ? `${scheme}://localhost:${port}` : `${scheme}://localhost`
}

async function createAdmin() {
  if (submitting.value) return
  errorMsg.value = ''
  if (!account.value.trim()) { errorMsg.value = t('login.enterprise.setup.account_required'); return }
  submitting.value = true
  try {
    // W-D005-B 裁决1（重入不覆盖语义）：显示名留空时省略字段——
    // 首建由后端落默认"管理员"，重入时后端保留用户第一次输入，前端不代传默认值
    boot.value = await bootstrapCreateAdmin(
      displayName.value.trim()
        ? { display_name: displayName.value.trim(), account: account.value.trim() }
        : { account: account.value.trim() },
    )
    step.value = 2
  } catch (err) {
    const code = authErrorCode(err)
    const status = (err as { response?: { status?: number } })?.response?.status
    // PM 裁决 + DevOps 口径更新（T-001 复发派工）：403 两类如实引导，不再落入笼统"服务异常"兜底——
    //  ① 契约信封 bootstrap_loopback_only（来源非回环=设计正确的引导坑）→ 回环如实文案；
    //  ② 网关信封 403（如跨源写守卫 {detail:cross_origin_write_blocked}，非企业错误码）→ 通用拒绝文案。
    // 两者都动态带出服务器本机地址，勿按回环单一根因写死。
    if (code === 'bootstrap_loopback_only') errorMsg.value = t('login.enterprise.setup.loopback', { url: localAdminUrl() })
    else if (status === 403) errorMsg.value = t('login.enterprise.setup.forbidden', { url: localAdminUrl() })
    else if (code === 'bootstrap_done' || status === 409) errorMsg.value = t('login.enterprise.setup.closed')
    else if (code === 'invalid_admin' || status === 422) errorMsg.value = t('login.enterprise.setup.invalid_admin')
    else if (status) errorMsg.value = t('login.enterprise.err_service_error', { status })
    else errorMsg.value = t('login.enterprise.err_network')
  } finally { submitting.value = false }
}

async function setPassword() {
  if (submitting.value) return
  errorMsg.value = ''
  if (password.value.length < 8) { errorMsg.value = t('login.enterprise.err_password_short'); return }
  if (password.value !== confirm.value) { errorMsg.value = t('login.enterprise.err_password_mismatch'); return }
  if (!boot.value) return
  submitting.value = true
  try {
    const me = await enterpriseActivate(boot.value.invite_code, password.value)
    userStore.setUser(me)
    router.replace('/')
  } catch (err) {
    const status = (err as { response?: { status?: number } })?.response?.status
    errorMsg.value = status ? t('login.enterprise.err_service_error', { status }) : t('login.enterprise.err_network')
  } finally { submitting.value = false }
}
</script>

<template>
  <div class="setup-page">
    <div class="setup-card" role="main">
      <div class="setup-brand">
        <div class="brand-mark">
          <svg viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <circle cx="28" cy="28" r="24" fill="var(--fg)"/>
            <path d="M20 20h16v12h-8l-4 4v-4h-4V20z" fill="var(--bg)"/>
            <line x1="24" y1="26" x2="32" y2="26" stroke="var(--fg)" stroke-width="1.5" stroke-linecap="round"/>
            <line x1="26" y1="29" x2="30" y2="29" stroke="var(--fg)" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </div>
        <span>Open Meeting Scribe</span>
      </div>
      <p class="setup-steptag">{{ step === 1 ? t('login.enterprise.setup.step1_tag') : t('login.enterprise.setup.step2_tag') }}</p>
      <h2 class="setup-title">{{ step === 1 ? t('login.enterprise.setup.title1') : t('login.enterprise.setup.title2') }}</h2>

      <!-- step1：建管理员占位账号 -->
      <form v-if="step === 1" class="setup-form" @submit.prevent="createAdmin">
        <p class="setup-hint">{{ t('login.enterprise.setup.hint1') }}</p>
        <input v-model="displayName" type="text" :placeholder="t('login.enterprise.setup.name_placeholder')" autocomplete="name" @input="clearError">
        <input v-model="account" type="text" :placeholder="t('login.enterprise.setup.account_placeholder')" autocomplete="username" required @input="clearError">
        <p class="setup-bind">{{ t('login.enterprise.setup.bind_note') }}</p>
        <div v-if="errorMsg" class="setup-error" role="alert">{{ errorMsg }}</div>
        <button type="submit" :disabled="submitting || !account">
          {{ submitting ? t('login.enterprise.setup.creating') : t('login.enterprise.setup.create_btn') }}
        </button>
      </form>

      <!-- step2：凭一次性邀请码自设管理员密码 -->
      <form v-else class="setup-form" @submit.prevent="setPassword">
        <p class="setup-hint">{{ t('login.enterprise.setup.hint2') }}</p>
        <input v-model="password" type="password" :placeholder="t('login.enterprise.new_password_placeholder')" autocomplete="new-password" required @input="clearError">
        <input v-model="confirm" type="password" :placeholder="t('login.enterprise.confirm_password_placeholder')" autocomplete="new-password" required @input="clearError">
        <div v-if="errorMsg" class="setup-error" role="alert">{{ errorMsg }}</div>
        <button type="submit" :disabled="submitting || !password || !confirm">
          {{ submitting ? t('login.enterprise.activating') : t('login.enterprise.setup.finish_btn') }}
        </button>
      </form>

      <section class="setup-privacy" aria-labelledby="setupPrivacyTitle">
        <h3 id="setupPrivacyTitle">{{ t('login.enterprise.privacy_title') }}</h3>
        <LockedPrivacyBlock />
      </section>
    </div>
  </div>
</template>

<style scoped>
.setup-page {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  background: var(--bg, #f6f6f4);
  padding: var(--s-3, 16px);
  overflow: auto;
}
.setup-card {
  width: min(440px, 100%);
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e2e2de);
  border-radius: calc(var(--radius-sm, 8px) * 2);
  padding: calc(var(--s-3, 16px) * 2);
  box-shadow: 0 12px 40px rgb(0 0 0 / 0.06);
}
.setup-brand {
  display: flex;
  align-items: center;
  gap: var(--s-2, 8px);
  font-weight: 600;
  font-size: var(--fs-13, 13px);
}
.setup-brand .brand-mark { width: 32px; height: 32px; }
.setup-brand svg { width: 100%; height: 100%; }
.setup-steptag {
  margin: var(--s-3, 16px) 0 0;
  font-size: var(--fs-11, 11px);
  color: var(--accent, #2a6);
  font-weight: 600;
}
.setup-title { font-size: 16px; margin: 4px 0 var(--s-2, 8px); }
.setup-hint { margin: 0 0 var(--s-3, 16px); color: var(--muted, #666); font-size: var(--fs-12, 12px); line-height: 1.6; }
.setup-bind { margin: 0 0 var(--s-2, 8px); font-size: var(--fs-11, 11px); color: var(--subtle, #999); }
.setup-form { display: flex; flex-direction: column; gap: var(--s-2, 8px); }
.setup-form input {
  padding: 10px 12px;
  border: 1px solid var(--border, #d8d8d4);
  border-radius: var(--radius-sm, 8px);
  background: var(--surface-2, #fafaf8);
  color: var(--fg, #222);
  font-size: var(--fs-13, 13px);
}
.setup-form input:focus { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.setup-error { color: var(--warn, #c33); font-size: var(--fs-12, 12px); }
.setup-form button {
  margin-top: var(--s-2, 8px);
  padding: 10px 12px;
  border: none;
  border-radius: var(--radius-sm, 8px);
  background: var(--accent, #2a6);
  color: var(--accent-fg, #fff);
  font-size: var(--fs-13, 13px);
  font-weight: 600;
  cursor: pointer;
}
.setup-form button:disabled { opacity: 0.55; cursor: not-allowed; }
.setup-privacy {
  margin-top: var(--s-3, 16px);
  padding: var(--s-3, 16px);
  background: var(--surface-2, #fafaf8);
  border-radius: var(--radius-sm, 8px);
}
.setup-privacy h3 {
  margin: 0 0 var(--s-2, 8px);
  font-size: var(--fs-12, 12px);
  color: var(--subtle, #999);
  font-weight: 600;
}
</style>
