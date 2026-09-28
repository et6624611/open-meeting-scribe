<template>
  <div class="cc-panel">
    <div class="cc-page-head">
      <h1 class="cc-page-title">{{ t('settings.compute.account_title') }}</h1>
      <p class="cc-page-lead">{{ t('settings.compute.account_lead') }}</p>
    </div>

    <!-- 当前身份 -->
    <div class="cc-card">
      <div class="cc-card-head">
        <div>
          <h2 class="cc-card-title">{{ t('settings.compute.identity') }}</h2>
          <p class="cc-card-desc">{{ t('settings.compute.identity_desc') }}</p>
        </div>
        <span v-if="userStore.isLoggedIn" class="cc-pill cc-pill-ok"><span class="cc-dot"></span>{{ t('settings.compute.logged_in') }}</span>
        <span v-else class="cc-pill cc-pill-idle">{{ t('settings.not_logged_in') }}</span>
      </div>

      <template v-if="userStore.isLoggedIn">
        <div class="cc-row cc-row-first">
          <div>
            <div class="cc-row-main">{{ userStore.displayName }}</div>
            <div class="cc-row-sub">{{ providerLabel }} · {{ t('settings.compute.session_note') }}</div>
          </div>
          <div class="cc-row-side">
            <button class="cc-btn cc-btn-secondary cc-btn-sm" @click="onLogout">{{ t('settings.logout') }}</button>
          </div>
        </div>
        <div class="cc-row">
          <div>
            <div class="cc-row-main">{{ t('settings.compute.quota_eligibility') }}</div>
            <div class="cc-row-sub">{{ t('settings.compute.quota_eligibility_desc') }}</div>
          </div>
          <div class="cc-row-side">
            <span class="cc-num cc-quota-figure" style="font-size:18px">{{ usageSummary.quota != null ? Math.round(usageSummary.quota) : '—' }}</span>
            <span class="cc-note">{{ t('settings.compute.per_month') }}</span>
            <span v-if="metered" class="cc-pill cc-pill-ok"><span class="cc-dot"></span>{{ t('settings.compute.bound') }}</span>
            <span v-else class="cc-pill cc-pill-idle">{{ t('settings.compute.unbound') }}</span>
          </div>
        </div>
      </template>
      <div v-else class="cc-row cc-row-first">
        <div>
          <div class="cc-row-main">{{ t('settings.not_logged_in') }}</div>
          <div class="cc-row-sub">{{ t('settings.compute.login_hint') }}</div>
        </div>
        <div class="cc-row-side">
          <button class="cc-btn cc-btn-primary cc-btn-sm" @click="showLogin">{{ t('settings.login') }}</button>
        </div>
      </div>
    </div>

    <!-- 用量与配额 -->
    <div class="cc-card">
      <div class="cc-card-head">
        <div>
          <h2 class="cc-card-title">{{ t('settings.compute.usage_title') }}</h2>
          <p class="cc-card-desc">{{ t('settings.compute.usage_desc') }}</p>
        </div>
        <span v-if="userStore.isLoggedIn" class="usage-tier-badge" :class="'tier-' + (usageSummary.tier || 'free')">{{ tierName(usageSummary.tier) }}</span>
      </div>

      <div v-if="!userStore.isLoggedIn" class="cc-note">{{ t('settings.usage_login_hint') }}</div>
      <template v-else>
        <div class="cc-quota-row">
          <div class="cc-quota-figure" v-if="metered">{{ Math.round(usageSummary.remaining || 0) }}<span> / {{ Math.round(usageSummary.quota || 0) }} {{ t('settings.compute.minutes_unit') }}</span></div>
          <div class="cc-quota-figure" v-else>∞<span> {{ t('settings.self_key') }}</span></div>
          <div style="text-align:right">
            <div class="cc-note">{{ t('settings.compute.month') }}</div>
            <div class="cc-mono" style="font-size:13px">{{ usageSummary.month || '—' }}</div>
          </div>
        </div>
        <div class="cc-meter"><div class="cc-meter-fill" :style="{ width: usedPct + '%' }"></div></div>
        <div class="cc-meter-legend" v-if="metered"><span>{{ t('settings.used') }} {{ Math.round(usageSummary.used || 0) }}</span><span>{{ usedPct }}%</span></div>
        <div class="cc-divider"></div>
        <!-- 优先使用体验配额 -->
        <div class="cc-row cc-row-first">
          <div>
            <div class="cc-row-main">{{ t('settings.prefer_subscription') }}</div>
            <div class="cc-row-sub" style="font-family:var(--font-body)">{{ t('settings.prefer_subscription_desc') }}</div>
          </div>
          <div class="cc-row-side">
            <label class="cc-switch">
              <input type="checkbox" :checked="preferSubscription" @change="onTogglePreferSubscription" />
              <span class="cc-switch-track"></span>
            </label>
          </div>
        </div>
      </template>
    </div>

    <!-- 数据主权 -->
    <div class="cc-card">
      <div class="cc-card-head">
        <div>
          <h2 class="cc-card-title">{{ t('settings.compute.sovereignty') }}</h2>
          <p class="cc-card-desc">{{ t('settings.compute.sovereignty_desc') }}</p>
        </div>
      </div>
      <dl class="cc-kv">
        <dt>{{ t('settings.compute.sov_primary') }}</dt><dd>127.0.0.1:8000</dd>
        <dt>{{ t('settings.compute.sov_local') }}</dt><dd>{{ t('settings.compute.sov_local_val') }}</dd>
        <dt>{{ t('settings.compute.sov_out') }}</dt><dd>{{ t('settings.compute.sov_out_val') }}</dd>
      </dl>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 账户登录面板（REQ-COMPUTE-CENTER）
 * 复刻原型账户段三卡：当前身份 / 用量与配额 / 数据主权。
 * 登录方式按 userStore.provider 单一如实回显（后端无 GitHub+手机号并存端点）。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/user'
import { fetchUsageSummary, updateUserPrefs, type UsageSummary } from '@/api/usage'

const props = defineProps<{ initialPrefer?: boolean }>()

const { t, te } = useI18n()
const userStore = useUserStore()

const usageSummary = reactive<UsageSummary>({ metered: false })
const preferSubscription = ref(!!props.initialPrefer)

const metered = computed(() => !!usageSummary.metered)
const usedPct = computed(() => {
  const used = usageSummary.used || 0
  const quota = usageSummary.quota || 1
  return Math.min(100, Math.round((used / quota) * 100))
})
const providerLabel = computed(() => {
  const p = userStore.user?.provider || 'local'
  return p === 'github' ? 'GitHub OAuth' : (p === 'phone' || p === 'sms') ? t('settings.compute.provider_phone') : p
})

function tierName(tier?: string): string {
  const key = `settings.tier_names.${tier || 'free'}`
  return te(key) ? t(key) : (tier || t('settings.tier_names.free'))
}

function showLogin() { window.dispatchEvent(new CustomEvent('oms:show-login')) }
async function onLogout() { await userStore.logout() }

async function onTogglePreferSubscription() {
  const next = !preferSubscription.value
  preferSubscription.value = next
  try {
    await updateUserPrefs({ prefer_subscription: next })
  } catch (e) {
    preferSubscription.value = !next
    console.error('update prefer_subscription failed:', e)
  }
}

async function loadUsage() {
  if (!userStore.isLoggedIn) return
  try {
    const summary = await fetchUsageSummary()
    Object.assign(usageSummary, summary)
  } catch (e) {
    console.error('load usage failed:', e)
  }
}

watch(() => props.initialPrefer, (v) => { preferSubscription.value = !!v })
watch(() => userStore.isLoggedIn, (v) => { if (v) loadUsage() })
onMounted(() => { loadUsage() })
</script>

<style src="./compute.css"></style>
<style scoped>
.usage-tier-badge { font-size: 11px; font-family: var(--font-mono); padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border-strong); color: var(--muted); }
.usage-tier-badge.tier-free { color: var(--accent); background: var(--accent-soft); border-color: var(--accent-mid); }
</style>
