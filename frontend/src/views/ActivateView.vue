<script setup lang="ts">
/**
 * 接受邀请页（档位①，UI 规格 §1「接受邀请流程」）/ Invite activation page
 *
 * 员工凭邀请码自助设置密码 → 激活账号 + 建立会话（契约 §1.2 activate）。
 * 全程管理员不经手密码（裁决插单③）：本页不存在任何"初始密码"概念。
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { enterpriseActivate, authErrorCode } from '@/api/enterpriseAuth'
import LockedPrivacyBlock from '@/components/common/LockedPrivacyBlock.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const inviteCode = ref(typeof route.query.code === 'string' ? route.query.code.trim() : '')
const password = ref('')
const confirm = ref('')
const submitting = ref(false)
const errorMsg = ref('')

async function onSubmit() {
  if (submitting.value) return
  errorMsg.value = ''
  if (password.value.length < 8) { errorMsg.value = t('login.enterprise.err_password_short'); return }
  if (password.value !== confirm.value) { errorMsg.value = t('login.enterprise.err_password_mismatch'); return }
  submitting.value = true
  try {
    const me = await enterpriseActivate(inviteCode.value.trim(), password.value)
    userStore.setUser(me)
    router.replace('/')
  } catch (err) {
    const code = authErrorCode(err)
    const status = (err as { response?: { status?: number } })?.response?.status
    if (code === 'activation_failed' || code === 'invite_invalid' || status === 401 || status === 403 || status === 404) {
      // activation_failed 涵盖弱密码/邀请码失效（后端实测 422 归并同一用户向提示，避免泄露原因细节）
      errorMsg.value = password.value.length < 8 ? t('login.enterprise.err_password_short') : t('login.enterprise.err_invite_invalid')
    } else if (status) {
      errorMsg.value = t('login.enterprise.err_service_error', { status })
    } else {
      errorMsg.value = t('login.enterprise.err_network')
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="ent-auth-page">
    <div class="ent-auth-card" role="main">
      <h2>{{ t('login.enterprise.accept_invite') }}</h2>
      <form class="ent-auth-form" @submit.prevent="onSubmit">
        <input
          v-model="inviteCode" type="text" :placeholder="t('login.enterprise.invite_placeholder')"
          autocomplete="one-time-code" required
        >
        <input
          v-model="password" type="password" :placeholder="t('login.enterprise.new_password_placeholder')"
          autocomplete="new-password" required
        >
        <input
          v-model="confirm" type="password" :placeholder="t('login.enterprise.confirm_password_placeholder')"
          autocomplete="new-password" required
        >
        <div v-if="errorMsg" class="ent-auth-error" role="alert">{{ errorMsg }}</div>
        <button type="submit" :disabled="submitting || !inviteCode || !password || !confirm">
          {{ submitting ? t('login.enterprise.activating') : t('login.enterprise.activate_submit') }}
        </button>
      </form>
      <section class="ent-auth-privacy" aria-labelledby="activatePrivacyTitle">
        <h3 id="activatePrivacyTitle">{{ t('login.enterprise.privacy_title') }}</h3>
        <LockedPrivacyBlock />
      </section>
      <RouterLink to="/login" class="ent-auth-back">{{ t('login.enterprise.back_to_login') }}</RouterLink>
    </div>
  </div>
</template>

<style scoped>
.ent-auth-page {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  background: var(--bg, #f6f6f4);
  padding: var(--s-3, 16px);
  overflow: auto;
}
.ent-auth-card {
  width: min(420px, 100%);
  background: var(--surface, #fff);
  border: 1px solid var(--border, #e2e2de);
  border-radius: calc(var(--radius-sm, 8px) * 2);
  padding: calc(var(--s-3, 16px) * 2);
  box-shadow: 0 12px 40px rgb(0 0 0 / 0.06);
}
.ent-auth-card h2 { margin: 0 0 var(--s-3, 16px); font-size: var(--fs-13, 16px); }
.ent-auth-form { display: flex; flex-direction: column; gap: var(--s-2, 8px); }
.ent-auth-form input {
  padding: 10px 12px;
  border: 1px solid var(--border, #d8d8d4);
  border-radius: var(--radius-sm, 8px);
  background: var(--surface-2, #fafaf8);
  color: var(--fg, #222);
  font-size: var(--fs-13, 13px);
}
.ent-auth-form input:focus { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.ent-auth-error { color: var(--warn, #c33); font-size: var(--fs-12, 12px); }
.ent-auth-form button {
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
.ent-auth-form button:disabled { opacity: 0.55; cursor: not-allowed; }
.ent-auth-back {
  display: inline-block;
  margin-top: var(--s-3, 16px);
  font-size: var(--fs-12, 12px);
  color: var(--muted, #666);
}
.ent-auth-privacy {
  margin-top: var(--s-3, 16px);
  padding: var(--s-3, 16px);
  background: var(--surface-2, #fafaf8);
  border-radius: var(--radius-sm, 8px);
}
.ent-auth-privacy h3 {
  margin: 0 0 var(--s-2, 8px);
  font-size: var(--fs-12, 12px);
  color: var(--subtle, #999);
  font-weight: 600;
}
</style>
