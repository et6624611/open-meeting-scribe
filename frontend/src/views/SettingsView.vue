<template>
  <div>
    <div class="main-head">
      <h1>设置</h1>
      <p class="sub">账户、API 配置、模型选择</p>
    </div>

    <!-- 账户信息 -->
    <div class="settings-section">
      <h2 class="settings-title">账户</h2>
      <div v-if="userStore.isLoggedIn" class="settings-account">
        <span class="settings-avatar">{{ userStore.avatarLetter }}</span>
        <div>
          <div class="settings-name">{{ userStore.displayName }}</div>
          <div class="settings-role">{{ userStore.user?.provider || 'local' }}</div>
        </div>
      </div>
      <div v-else class="settings-login-prompt">
        <p>未登录</p>
        <button class="btn btn-primary" @click="showLogin">登录</button>
      </div>
    </div>

    <!-- API 配置 -->
    <div class="settings-section">
      <h2 class="settings-title">API 配置</h2>
      <div class="settings-field">
        <label class="settings-label">API Key</label>
        <input v-model="settings.api_key" type="password" class="settings-input" placeholder="留空则使用环境变量中的 Key" />
      </div>
      <div class="settings-field">
        <label class="settings-label">ASR 模型</label>
        <input v-model="settings.asr_model" class="settings-input" placeholder="paraformer-v2" />
      </div>
      <div class="settings-field">
        <label class="settings-label">LLM 模型</label>
        <input v-model="settings.llm_model" class="settings-input" placeholder="qwen-plus" />
      </div>
      <div class="settings-actions">
        <button class="btn btn-secondary" @click="onTest" :disabled="testing">{{ testing ? '测试中…' : '测试连接' }}</button>
        <button class="btn btn-primary" @click="onSave">保存设置</button>
      </div>
      <p v-if="testResult" class="settings-test-result" :class="{ 'is-error': testIsError }">{{ testResult }}</p>
    </div>

    <!-- 主题 -->
    <div class="settings-section">
      <h2 class="settings-title">外观</h2>
      <div class="theme-grid">
        <button
          v-for="theme in THEMES"
          :key="theme.id"
          class="theme-chip"
          :class="{ 'is-active': themeStore.current === theme.id }"
          @click="themeStore.setTheme(theme.id)"
        >{{ theme.label }}</button>
      </div>
    </div>

    <!-- 功能开关 -->
    <div class="settings-section">
      <h2 class="settings-title">功能开关</h2>
      <p class="settings-section-desc">控制录音过程中的实时 AI 功能，默认全部开启</p>
      
      <div class="feature-toggles">
        <div class="wm-setting-row">
          <label>
            实时章节生成
            <span class="toggle-desc">录音过程中自动按话题切分章节</span>
          </label>
          <div class="wm-toggle-wrap">
            <div 
              class="wm-toggle" 
              :class="{ 'is-on': featureFlags.realtime_chapters }" 
              role="switch" 
              :aria-checked="featureFlags.realtime_chapters"
              tabindex="0"
              @click="toggleFlag('realtime_chapters')"
              @keydown.enter.prevent="toggleFlag('realtime_chapters')"
              @keydown.space.prevent="toggleFlag('realtime_chapters')"
            ></div>
            <span class="wm-setting-val">{{ featureFlags.realtime_chapters ? '开启' : '关闭' }}</span>
          </div>
        </div>

        <div class="wm-setting-row">
          <label>
            实时总结生成
            <span class="toggle-desc">录音过程中按设定间隔增量生成摘要</span>
          </label>
          <div class="wm-toggle-wrap">
            <div 
              class="wm-toggle" 
              :class="{ 'is-on': featureFlags.realtime_summary }" 
              role="switch" 
              :aria-checked="featureFlags.realtime_summary"
              tabindex="0"
              @click="toggleFlag('realtime_summary')"
              @keydown.enter.prevent="toggleFlag('realtime_summary')"
              @keydown.space.prevent="toggleFlag('realtime_summary')"
            ></div>
            <span class="wm-setting-val">{{ featureFlags.realtime_summary ? '开启' : '关闭' }}</span>
          </div>
          <div v-if="featureFlags.realtime_summary" class="interval-selector">
            <span class="interval-label">刷新频率：</span>
            <div class="freq-btns">
              <button 
                v-for="sec in [30, 60, 120, 300]" 
                :key="sec"
                type="button" 
                class="wm-freq-btn" 
                :class="{ 'is-active': featureFlags.realtime_summary_interval === sec }"
                @click="setInterval(sec)"
              >{{ sec }}s</button>
            </div>
            <span class="interval-hint">修改后下次录音生效</span>
          </div>
        </div>

        <div class="wm-setting-row">
          <label>
            软件更新提示
            <span class="toggle-desc">启动时检查新版本并提示升级</span>
          </label>
          <div class="wm-toggle-wrap">
            <div 
              class="wm-toggle" 
              :class="{ 'is-on': featureFlags.update_check }" 
              role="switch" 
              :aria-checked="featureFlags.update_check"
              tabindex="0"
              @click="toggleFlag('update_check')"
              @keydown.enter.prevent="toggleFlag('update_check')"
              @keydown.space.prevent="toggleFlag('update_check')"
            ></div>
            <span class="wm-setting-val">{{ featureFlags.update_check ? '开启' : '关闭' }}</span>
          </div>
        </div>
      </div>
    </div>
    <!-- 用量与订阅 -->
    <div class="settings-section">
      <h2 class="settings-title">用量与订阅</h2>
      <p class="settings-section-desc">本月识别额度与使用情况</p>

      <!-- 未登录 -->
      <div v-if="!userStore.isLoggedIn" class="usage-not-metered">
        <p>登录后可查看识别额度与使用情况。未登录时使用本地模式，需自行配置 API Key。</p>
        <button class="btn btn-primary" style="margin-top:12px;padding:0 16px;height:32px;font-size:12px" @click="showLogin">登录</button>
      </div>

      <!-- 计量模式 -->
      <div v-else-if="usageSummary.metered" class="usage-panel">
        <div style="display:flex;align-items:center;justify-content:space-between">
          <span class="usage-tier-badge" :class="'tier-' + (usageSummary.tier || 'free')">{{ tierName(usageSummary.tier) }}</span>
          <span style="font-size:12px;color:var(--muted);font-family:var(--font-mono)">{{ usageSummary.month }}</span>
        </div>
        <div class="usage-summary-row">
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.quota || 0) }}</div>
            <div class="stat-label">月额度</div>
          </div>
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.used || 0) }}</div>
            <div class="stat-label">已使用</div>
          </div>
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.remaining || 0) }}</div>
            <div class="stat-label">剩余</div>
          </div>
        </div>
        <div class="usage-progress">
          <div class="usage-progress-fill" :style="progressStyle"></div>
        </div>
        <div style="font-size:12px;color:var(--muted);margin-bottom:8px">最近 30 天用量</div>
        <div class="usage-chart">
          <div
            v-for="d in usageHistory"
            :key="d.date"
            class="usage-chart-bar"
            :style="{ height: barHeight(d.minutes) + 'px' }"
            :data-tip="d.date.slice(5) + '：' + formatMinutes(d.minutes) + '（' + d.tasks + ' 次）'"
          ></div>
          <div v-if="!usageHistory.length" style="font-size:12px;color:var(--muted);padding:8px">暂无用量记录</div>
        </div>
      </div>

      <!-- 非计量模式 -->
      <div v-else class="usage-panel">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <span class="usage-tier-badge" :class="'tier-' + (usageSummary.tier || 'free')">{{ tierName(usageSummary.tier) }}</span>
          <span style="font-size:12px;color:var(--muted);font-family:var(--font-mono)">自带 Key</span>
        </div>
        <div class="usage-summary-row">
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.quota || 0) }}</div>
            <div class="stat-label">月额度</div>
          </div>
          <div class="usage-stat">
            <div class="stat-value" style="color:var(--muted)">∞</div>
            <div class="stat-label">已使用（自费）</div>
          </div>
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.quota || 0) }}</div>
            <div class="stat-label">平台额度剩余</div>
          </div>
        </div>
        <p style="margin:12px 0 0;font-size:12px;color:var(--muted)">当前使用云端代理模式，识别费用已包含在订阅额度中。</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useUserStore } from '@/stores/user'
import { useThemeStore, THEMES } from '@/stores/theme'
import { fetchSettings, saveSettings, testApiConnection } from '@/api/settings'
import type { Settings, FeatureFlags } from '@/api/settings'
import { fetchUsageSummary, fetchUsageHistory } from '@/api/usage'
import type { UsageSummary, UsageHistoryItem } from '@/api/usage'

const userStore = useUserStore()
const themeStore = useThemeStore()
const settings = reactive<Settings>({})
const testing = ref(false)
const testResult = ref('')
const testIsError = ref(false)

const featureFlags = reactive<FeatureFlags>({
  realtime_chapters: true,
  realtime_summary: true,
  realtime_summary_interval: 60,
  update_check: true
})

const usageSummary = reactive<UsageSummary>({ metered: false })
const usageHistory = ref<UsageHistoryItem[]>([])

const TIER_NAMES: Record<string, string> = { free: '体验版', personal: '个人版', pro: '专业版', team: '团队版' }

function tierName(tier?: string) {
  return tier ? (TIER_NAMES[tier] || tier) : '体验版'
}

function formatMinutes(min: number): string {
  if (min >= 60) {
    const h = Math.floor(min / 60)
    const m = Math.round(min % 60)
    return m > 0 ? `${h}h${m}m` : `${h}h`
  }
  return Math.round(min) + 'm'
}

const progressStyle = computed(() => {
  const used = usageSummary.used || 0
  const quota = usageSummary.quota || 1
  const pct = Math.round(used / quota * 100)
  let color = 'oklch(55% 0.15 155)'
  if (pct > 80) color = 'oklch(55% 0.2 25)'
  else if (pct > 50) color = 'oklch(65% 0.16 80)'
  return { width: Math.min(pct, 100) + '%', background: color }
})

const maxHistoryMinutes = computed(() => {
  if (!usageHistory.value.length) return 1
  return Math.max(...usageHistory.value.map(d => d.minutes), 1)
})

function barHeight(minutes: number): number {
  return Math.max(2, Math.round(minutes / maxHistoryMinutes.value * 56))
}

function showLogin() {
  window.dispatchEvent(new CustomEvent('oms:show-login'))
}

async function onSave() {
  await saveSettings({ 
    ...settings,
    feature_flags: { ...featureFlags }
  })
  alert('设置已保存')
}

async function onTest() {
  testing.value = true
  testResult.value = ''
  try {
    const res = await testApiConnection()
    testResult.value = res.message || (res.success ? '连接成功' : '连接失败')
    testIsError.value = !res.success
  } catch {
    testResult.value = '连接失败'
    testIsError.value = true
  } finally {
    testing.value = false
  }
}

function toggleFlag(key: keyof FeatureFlags) {
  if (key === 'realtime_summary_interval') return
  featureFlags[key] = !featureFlags[key] as boolean
  saveFeatureFlags()
}

function setInterval(sec: number) {
  featureFlags.realtime_summary_interval = sec
  saveFeatureFlags()
}

async function saveFeatureFlags() {
  await saveSettings({ feature_flags: { ...featureFlags } })
}

onMounted(async () => {
  const s = await fetchSettings()
  Object.assign(settings, s)
  if (s.feature_flags) {
    Object.assign(featureFlags, {
      realtime_chapters: s.feature_flags.realtime_chapters !== false,
      realtime_summary: s.feature_flags.realtime_summary !== false,
      realtime_summary_interval: s.feature_flags.realtime_summary_interval || 60,
      update_check: s.feature_flags.update_check !== false
    })
  }
  loadUsage()
})

async function loadUsage() {
  if (!userStore.isLoggedIn) return
  try {
    const [summary, history] = await Promise.all([
      fetchUsageSummary(),
      fetchUsageHistory(30),
    ])
    Object.assign(usageSummary, summary)
    usageHistory.value = history.history || []
  } catch (e) {
    console.error('加载用量失败:', e)
  }
}
</script>

<style scoped>
.settings-section { margin-bottom: var(--s-7); }
.settings-title { font-size: 16px; font-weight: 600; margin-bottom: var(--s-3); padding-bottom: var(--s-2); border-bottom: 1px solid var(--border); }
.settings-account { display: flex; align-items: center; gap: var(--s-3); }
.settings-avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--border); color: var(--muted); display: grid; place-items: center; font-size: 16px; font-weight: 600; }
.settings-name { font-size: 15px; font-weight: 500; }
.settings-role { font-size: 12px; color: var(--subtle); }
.settings-login-prompt { display: flex; align-items: center; gap: var(--s-3); }
.settings-login-prompt p { margin: 0; color: var(--muted); }
.settings-field { margin-bottom: var(--s-4); }
.settings-label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.settings-input { width: 100%; max-width: 400px; padding: var(--s-2) var(--s-3); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); color: var(--fg); font-size: 14px; outline: none; }
.settings-input:focus { border-color: var(--accent); }
.settings-actions { display: flex; gap: var(--s-2); margin-top: var(--s-4); }
.settings-test-result { font-size: 12px; margin-top: var(--s-2); }
.settings-test-result.is-error { color: var(--rec); }
.theme-grid { display: flex; flex-wrap: wrap; gap: var(--s-2); }
.theme-chip { padding: 6px var(--s-4); border-radius: 20px; border: 1px solid var(--border); background: var(--surface); color: var(--fg); font-size: 13px; cursor: pointer; transition: all 0.15s; }
.theme-chip:hover { border-color: var(--border-strong); }
.theme-chip.is-active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); font-weight: 500; }
.settings-section-desc { font-size: 12px; color: var(--muted); margin: calc(-1 * var(--s-2)) 0 var(--s-4); }
.feature-toggles { display: flex; flex-direction: column; gap: var(--s-5); }
.toggle-desc { display: block; font-size: 11px; color: var(--muted); font-weight: 400; margin-top: 2px; }
.interval-selector { display: flex; align-items: center; gap: var(--s-2); margin-top: var(--s-2); }
.interval-label { font-size: 12px; color: var(--muted); }
.freq-btns { display: flex; gap: 2px; }
.interval-hint { font-size: 11px; color: var(--subtle); }
</style>
