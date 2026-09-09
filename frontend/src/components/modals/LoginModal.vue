<template>
  <Teleport to="body">
    <div class="login-overlay" :class="{ 'is-hidden': !visible }" id="loginOverlay">
      <div class="login-card">
        <div class="login-card-brand">
          <div class="brand-mark">O</div>
          <span>Open Meeting Scribe</span>
        </div>
        <p class="login-card-sub">登录后即可使用 AI 会议纪要生成、说话人识别等全部功能</p>

        <!-- 登录方式 Tab -->
        <div class="login-tabs">
          <button class="login-tab" :class="{ active: activeTab === 'github' }" @click="switchTab('github')">GitHub</button>
          <button class="login-tab" :class="{ active: activeTab === 'sms' }" @click="switchTab('sms')">手机号</button>
        </div>

        <!-- GitHub 登录面板 -->
        <div class="login-tab-panel" :class="{ active: activeTab === 'github' }">
          <button class="login-btn" @click="onGithubLogin">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
            使用 GitHub 登录
          </button>
        </div>

        <!-- 手机号登录面板 -->
        <div class="login-tab-panel" :class="{ active: activeTab === 'sms' }">
          <div class="sms-input-group">
            <input class="sms-input" ref="phoneRef" type="tel" maxlength="11"
                   placeholder="请输入手机号" autocomplete="tel"
                   v-model="phone" @input="clearError()">
          </div>
          <div class="sms-row">
            <input class="sms-input" ref="codeRef" type="text" maxlength="6" inputmode="numeric"
                   placeholder="验证码" autocomplete="one-time-code"
                   v-model="code" @input="clearError()"
                   @keydown.enter="onVerify">
            <button class="sms-send-btn" ref="sendBtnRef" :disabled="cooldown > 0" @click="onSendCode">
              {{ cooldown > 0 ? cooldown + 's' : '获取验证码' }}
            </button>
          </div>
          <div class="sms-error" v-show="errorMsg">{{ errorMsg }}</div>
          <button class="sms-submit-btn" :disabled="submitting" @click="onVerify">
            {{ submitting ? '登录中...' : '登录' }}
          </button>
        </div>

        <p class="login-footer">登录即表示同意开源使用条款<br>个人版完全免费，无需订阅</p>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

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

function open() { visible.value = false } // 登录遮罩不再强制弹出，仅按需显示
function show() { visible.value = true }
function hide() { visible.value = false }

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
    errorMsg.value = '请输入正确的 11 位手机号'
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
      errorMsg.value = data.message || '发送失败，请稍后重试'
      return
    }
    startCooldown(60)
    codeRef.value?.focus()
  } catch {
    errorMsg.value = '网络异常，请检查连接'
  }
}

async function onVerify() {
  clearError()
  const p = phone.value.trim()
  const c = code.value.trim()
  if (!p) { errorMsg.value = '请输入手机号'; return }
  if (!c) { errorMsg.value = '请输入验证码'; return }
  submitting.value = true
  try {
    const resp = await fetch('/auth/sms/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: p, code: c }),
    })
    const data = await safeJson(resp)
    if (!data.success) {
      errorMsg.value = data.message || '登录失败'
      return
    }
    // 登录成功，刷新页面（cookie 已设置）
    window.location.href = '/'
  } catch {
    errorMsg.value = '网络异常，请检查连接'
  } finally {
    submitting.value = false
  }
}

async function safeJson(resp: Response): Promise<{ success: boolean; message?: string }> {
  const text = await resp.text()
  try { return JSON.parse(text) } catch { return { success: false, message: `服务异常（HTTP ${resp.status}），请稍后重试` } }
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

// 监听全局事件
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
