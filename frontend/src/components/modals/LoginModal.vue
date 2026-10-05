<template>
  <Teleport to="body">
    <div class="login-overlay" data-vue-overlay :class="{ 'is-hidden': !visible }" id="loginOverlay">
      <div ref="dialogRef" class="login-card" role="dialog" aria-modal="true" aria-labelledby="loginBrand">
        <div class="login-card-brand">
          <div class="brand-mark">
            <svg viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="28" cy="28" r="24" fill="var(--fg)"/>
              <path d="M20 20h16v12h-8l-4 4v-4h-4V20z" fill="var(--bg)"/>
              <line x1="24" y1="26" x2="32" y2="26" stroke="var(--fg)" stroke-width="1.5" stroke-linecap="round"/>
              <line x1="26" y1="29" x2="30" y2="29" stroke="var(--fg)" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
          </div>
          <span id="loginBrand">Open Meeting Scribe</span>
        </div>
        <p class="login-card-sub">{{ t('login.subtitle') }}</p>

        <!-- 登录方式 Tab / Login method tabs -->
        <div class="login-tabs">
          <button class="login-tab" :class="{ active: activeTab === 'github' }" @click="switchTab('github')">{{ t('login.tab_github') }}</button>
          <button class="login-tab" :class="{ active: activeTab === 'sms' }" @click="switchTab('sms')">{{ t('login.tab_sms') }}</button>
        </div>

        <!-- GitHub 登录面板 / GitHub login panel -->
        <div class="login-tab-panel" :class="{ active: activeTab === 'github' }">
          <button class="login-btn" @click="onGithubLogin">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
            {{ t('login.github_btn') }}
          </button>
        </div>

        <!-- 手机号登录面板 / Phone number login panel -->
        <div class="login-tab-panel" :class="{ active: activeTab === 'sms' }">
          <div class="sms-beta-notice">{{ t('login.sms_beta_notice') }}</div>
          <div class="sms-input-group">
            <input
              class="sms-input" ref="phoneRef" type="tel" maxlength="11"
              :placeholder="t('login.phone_placeholder')" autocomplete="tel"
              v-model="phone" @input="clearError()"
            >
          </div>
          <div class="sms-row">
            <input
              class="sms-input" ref="codeRef" type="text" maxlength="6" inputmode="numeric"
              :placeholder="t('login.code_placeholder')" autocomplete="one-time-code"
              v-model="code" @input="clearError()"
              @keydown.enter="onVerify"
            >
            <button class="sms-send-btn" ref="sendBtnRef" :disabled="cooldown > 0" @click="onSendCode">
              {{ cooldown > 0 ? cooldown + 's' : t('login.send_code') }}
            </button>
          </div>
          <div class="sms-error" v-show="errorMsg">{{ errorMsg }}</div>
          <button class="sms-submit-btn" :disabled="submitting" @click="onVerify">
            {{ submitting ? t('login.submitting') : t('login.submit') }}
          </button>
        </div>

        <p class="login-footer">{{ t('login.footer_line1') }}<br>{{ t('login.footer_line2') }}</p>
        <div class="login-footer-action">
          <IconButton class="login-back-btn" :label="t('login.back')" show-label @click="hide">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
            <template #label>{{ t('login.back_label') }} <kbd>ESC</kbd></template>
          </IconButton>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import IconButton from '@/components/common/IconButton.vue'
import { useDialog } from '@/composables/useDialog'

const { t } = useI18n()

const visible = ref(false)
const activeTab = ref<'github' | 'sms'>('github')
const phone = ref('')
const code = ref('')
const errorMsg = ref('')
const cooldown = ref(0)
const submitting = ref(false)
const phoneRef = ref<HTMLInputElement | null>(null)
const codeRef = ref<HTMLInputElement | null>(null)

let cooldownTimer: ReturnType<typeof setInterval> | null = null

function open() { visible.value = false } // 登录遮罩不再强制弹出，仅按需显示 / Login overlay no longer forced, show on demand only
function show() { visible.value = true }
function hide() { visible.value = false }

// 焦点陷阱与关闭后焦点归还；ESC 仍由 useKeyboardShortcuts 的 #loginOverlay 分支先行处理
// Tab trap + focus restore; ESC still short-circuits in useKeyboardShortcuts' login branch first
const { dialogRef } = useDialog(visible, hide)

function switchTab(tab: 'github' | 'sms') {
  activeTab.value = tab
  clearError()
  if (tab === 'sms') {
    setTimeout(() => phoneRef.value?.focus(), 100)
  }
}

function clearError() { errorMsg.value = '' }

function onGithubLogin() {
  window.location.href = '/auth/github'
}

async function onSendCode() {
  clearError()
  const p = phone.value.trim()
  if (!/^1[3-9]\d{9}$/.test(p)) {
    errorMsg.value = t('login.errors.invalid_phone')
    return
  }
  try {
    const resp = await fetch('/auth/sms/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: p }),
    })
    const data = await safeJson(resp)
    if (!data.success) {
      errorMsg.value = data.message || t('login.errors.send_failed')
      return
    }
    startCooldown(60)
    codeRef.value?.focus()
  } catch {
    errorMsg.value = t('login.errors.network')
  }
}

async function onVerify() {
  clearError()
  const p = phone.value.trim()
  const c = code.value.trim()
  if (!p) { errorMsg.value = t('login.errors.phone_required'); return }
  if (!c) { errorMsg.value = t('login.errors.code_required'); return }
  submitting.value = true
  try {
    const resp = await fetch('/auth/sms/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: p, code: c }),
    })
    const data = await safeJson(resp)
    if (!data.success) {
      errorMsg.value = data.message || t('login.errors.login_failed')
      return
    }
    // 登录成功，刷新页面（cookie 已设置） / Login success, refresh page (cookie set)
    window.location.href = '/'
  } catch {
    errorMsg.value = t('login.errors.network')
  } finally {
    submitting.value = false
  }
}

async function safeJson(resp: Response): Promise<{ success: boolean; message?: string }> {
  const text = await resp.text()
  try { return JSON.parse(text) } catch { return { success: false, message: t('login.errors.service_error', { status: resp.status }) } }
}

function startCooldown(seconds: number) {
  cooldown.value = seconds
  cooldownTimer = setInterval(() => {
    cooldown.value--
    if (cooldown.value <= 0 && cooldownTimer) {
      clearInterval(cooldownTimer)
      cooldownTimer = null
    }
  }, 1000)
}

// 监听全局事件 / Listen for global events
function onShowLogin() { show() }
function onHideLogin() { hide() }
onMounted(() => {
  window.addEventListener('oms:show-login', onShowLogin)
  window.addEventListener('oms:hide-login', onHideLogin)
  window.addEventListener('global-esc', hide)
})
onUnmounted(() => {
  window.removeEventListener('oms:show-login', onShowLogin)
  window.removeEventListener('oms:hide-login', onHideLogin)
  window.removeEventListener('global-esc', hide)
  if (cooldownTimer) clearInterval(cooldownTimer)
})

defineExpose({ show, hide, open })
</script>
