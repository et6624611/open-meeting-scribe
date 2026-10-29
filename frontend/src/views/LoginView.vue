<script setup lang="ts">
/**
 * 企业版登录页（档位①，UI 规格 §1）/ Enterprise login page
 *
 * 只有账号密码一种入口（裁决⑥：不挂载 SMS/GitHub OAuth）；
 * 服务暂停时登录页拦截文案（裁决④）；隐私说明 = §7 锁定三行（经 LockedPrivacyBlock）。
 */
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { enterpriseLogin, fetchInstanceInfo, authErrorCode, type InstanceInfo } from '@/api/enterpriseAuth'
import LockedPrivacyBlock from '@/components/common/LockedPrivacyBlock.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const account = ref('')
const password = ref('')
const submitting = ref(false)
const errorMsg = ref('')
const noticeMsg = ref('')
const instance = ref<InstanceInfo | null>(null)

onMounted(async () => {
  if (route.query.expired) noticeMsg.value = t('login.enterprise.expired_notice')
  try {
    instance.value = await fetchInstanceInfo()
    if (instance.value.service_open === false) noticeMsg.value = t('login.enterprise.paused_notice')
  } catch {
    /* 免登录端点不可达时不阻塞表单，提交时以后端错误为准 */
  }
})

function clearError() { errorMsg.value = '' }

async function onSubmit() {
  if (submitting.value) return
  errorMsg.value = ''
  submitting.value = true
  try {
    const me = await enterpriseLogin(account.value.trim(), password.value)
    userStore.setUser(me)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.replace(redirect)
  } catch (err) {
    const code = authErrorCode(err)
    const status = (err as { response?: { status?: number } })?.response?.status
    if (code === 'password_not_set') errorMsg.value = t('login.enterprise.err_password_not_set')
    else if (code === 'service_closed') { noticeMsg.value = t('login.enterprise.paused_notice'); errorMsg.value = '' }
    else if (code === 'account_disabled') errorMsg.value = t('login.enterprise.err_account_disabled')
    else if (status === 401 || status === 403) errorMsg.value = t('login.enterprise.err_invalid')
    else if (status) errorMsg.value = t('login.enterprise.err_service_error', { status })
    else errorMsg.value = t('login.enterprise.err_network')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="ent-auth-page">
    <div class="ent-auth-card" role="main">
      <div class="ent-auth-brand">
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
      <p class="ent-auth-sub">{{ t('login.enterprise.subtitle') }}</p>

      <div v-if="noticeMsg" class="ent-auth-notice" role="status">{{ noticeMsg }}</div>

      <form class="ent-auth-form" @submit.prevent="onSubmit">
        <input
          v-model="account" type="text" :placeholder="t('login.enterprise.account_placeholder')"
          autocomplete="username" required @input="clearError"
        >
        <input
          v-model="password" type="password" :placeholder="t('login.enterprise.password_placeholder')"
          autocomplete="current-password" required @input="clearError"
        >
        <div v-if="errorMsg" class="ent-auth-error" role="alert">{{ errorMsg }}</div>
        <button type="submit" :disabled="submitting || !account || !password">
          {{ submitting ? t('login.enterprise.submitting') : t('login.enterprise.submit') }}
        </button>
      </form>

      <div class="ent-auth-invite">
        <p>{{ t('login.enterprise.accept_invite_hint') }}</p>
        <RouterLink to="/activate" class="ent-auth-invite-btn">{{ t('login.enterprise.accept_invite') }}</RouterLink>
      </div>

      <section class="ent-auth-privacy" aria-labelledby="privacyTitle">
        <h3 id="privacyTitle">{{ t('login.enterprise.privacy_title') }}</h3>
        <LockedPrivacyBlock />
      </section>
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
.ent-auth-brand {
  display: flex;
  align-items: center;
  gap: var(--s-2, 8px);
  font-weight: 600;
  font-size: var(--fs-13, 13px);
}
.ent-auth-brand .brand-mark { width: 32px; height: 32px; }
.ent-auth-brand svg { width: 100%; height: 100%; }
.ent-auth-sub {
  margin: var(--s-2, 8px) 0 var(--s-3, 16px);
  color: var(--muted, #666);
  font-size: var(--fs-12, 12px);
}
.ent-auth-notice {
  margin-bottom: var(--s-2, 8px);
  padding: var(--s-2, 8px) var(--s-3, 12px);
  border-radius: var(--radius-sm, 8px);
  background: color-mix(in srgb, var(--warn, #b60) 12%, transparent);
  color: var(--warn, #b60);
  font-size: var(--fs-12, 12px);
}
.ent-auth-form { display: flex; flex-direction: column; gap: var(--s-2, 8px); }
.ent-auth-form input {
  padding: 10px 12px;
  border: 1px solid var(--border, #d8d8d4);
  border-radius: var(--radius-sm, 8px);
  background: var(--surface-2, #fafaf8);
  color: var(--fg, #222);
  font-size: var(--fs-13, 13px);
}
.ent-auth-form input:focus {
  outline: 2px solid var(--accent-mid, #4a7);
  outline-offset: 1px;
}
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
.ent-auth-invite {
  margin-top: var(--s-3, 16px);
  padding-top: var(--s-3, 16px);
  border-top: 1px dashed var(--border, #e2e2de);
  font-size: var(--fs-12, 12px);
  color: var(--muted, #666);
}
.ent-auth-invite p { margin: 0 0 var(--s-2, 8px); }
.ent-auth-invite-btn {
  display: inline-block;
  padding: 6px 14px;
  border: 1px solid var(--accent, #2a6);
  border-radius: 999px;
  color: var(--accent, #2a6);
  text-decoration: none;
  font-weight: 600;
}
.ent-auth-invite-btn:focus-visible { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 2px; }
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
