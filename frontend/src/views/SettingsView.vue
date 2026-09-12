<template>
  <div>
    <div class="main-head">
      <h1>{{ t('settings.title') }}</h1>
      <p class="sub">{{ t('settings.subtitle') }}</p>
    </div>

    <!-- 隐私提示条 -->
    <div class="settings-privacy-bar" v-if="showPrivacyNotice">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
      <span>{{ t('settings.privacy_notice.text') }}</span>
      <a class="settings-privacy-link" href="https://github.com/et6624611/open-meeting-scribe/blob/main/SECURITY.md" target="_blank" rel="noopener">{{ t('settings.privacy_notice.learn_more') }}</a>
      <button class="rec-volume-dismiss" @click="showPrivacyNotice = false">&times;</button>
    </div>

    <!-- 账户信息 -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.account') }}</h2>
      <div v-if="userStore.isLoggedIn" class="settings-account">
        <span class="settings-avatar">{{ userStore.avatarLetter }}</span>
        <div>
          <div class="settings-name">{{ userStore.displayName }}</div>
          <div class="settings-role">{{ userStore.user?.provider || 'local' }}</div>
        </div>
      </div>
      <div v-else class="settings-login-prompt">
        <p>{{ t('settings.not_logged_in') }}</p>
        <button class="btn btn-primary" @click="showLogin">{{ t('settings.login') }}</button>
      </div>
    </div>

    <!-- API 配置 -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.api_config') }}</h2>

      <!-- LLM 纪要生成服务 -->
      <div class="api-subsection">
        <h3 class="api-subsection-title">{{ t('settings.llm_service') }}</h3>
        <div class="settings-field">
          <label class="settings-label">{{ t('settings.llm_provider') }}</label>
          <select v-model="settings.llm!.provider" class="settings-input" @change="onLlmProviderChange">
            <option v-for="p in llmPresets" :key="p.name" :value="p.name">{{ p.name }}</option>
          </select>
        </div>
        <div class="settings-field">
          <label class="settings-label">{{ t('settings.llm_base_url') }}</label>
          <input v-model="settings.llm!.base_url" class="settings-input" :placeholder="t('settings.llm_base_url_placeholder')" />
        </div>
        <div class="settings-field">
          <label class="settings-label">{{ t('settings.api_key') }}</label>
          <input v-model="settings.llm!.api_key" type="password" class="settings-input" :placeholder="t('settings.llm_api_key_placeholder')" />
        </div>
        <div class="settings-field">
          <label class="settings-label">{{ t('settings.llm_model') }}</label>
          <input v-model="settings.llm!.model" class="settings-input" placeholder="qwen-plus" />
        </div>
      </div>

      <!-- ASR 语音转写服务 -->
      <div class="api-subsection">
        <h3 class="api-subsection-title">{{ t('settings.asr_service') }}</h3>
        <div class="settings-field">
          <label class="settings-label">{{ t('settings.asr_provider') }}</label>
          <span class="api-readonly">{{ settings.asr?.provider || 'Cloud AI' }}<span class="api-proxy-hint">{{ t('settings.asr_proxy_managed') }}</span></span>
        </div>
        <div class="settings-field">
          <label class="settings-label">{{ t('settings.asr_model') }}</label>
          <input v-model="settings.asr!.model" class="settings-input" placeholder="paraformer-v2" />
        </div>
      </div>

      <div class="settings-actions">
        <button class="btn btn-secondary" @click="onTest" :disabled="testing">{{ testing ? t('settings.testing') : t('settings.test_connection') }}</button>
        <button class="btn btn-primary" @click="onSave">{{ t('settings.save') }}</button>
      </div>
      <p v-if="testResult" class="settings-test-result" :class="{ 'is-error': testIsError }">{{ testResult }}</p>
    </div>

    <!-- 声纹服务 -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.voiceprint') }}</h2>
      <p class="settings-section-desc">{{ t('settings.voiceprint_desc') }}</p>
      <div class="settings-field">
        <label class="settings-label">{{ t('settings.voiceprint_provider') }}</label>
        <select v-model="settings.voiceprint!.provider" class="settings-input">
          <option value="auto">{{ t('settings.voiceprint_provider_auto') }}</option>
          <option value="local">{{ t('settings.voiceprint_provider_local') }}</option>
          <option value="cloud">{{ t('settings.voiceprint_provider_cloud') }}</option>
        </select>
      </div>
      <div class="settings-field">
        <label class="settings-label">{{ t('settings.voiceprint_cloud_base_url') }}</label>
        <input v-model="settings.voiceprint!.cloud_base_url" class="settings-input" placeholder="https://" />
      </div>
      <div class="settings-field">
        <label class="settings-label">{{ t('settings.voiceprint_cloud_api_key') }}</label>
        <input v-model="settings.voiceprint!.cloud_api_key" type="password" class="settings-input" :placeholder="t('settings.voiceprint_cloud_api_key_placeholder')" />
      </div>
    </div>

    <!-- 说话人分离 -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.diarization') }}</h2>
      <p class="settings-section-desc">{{ t('settings.diarization_desc') }}</p>
      <div class="wm-setting-row">
        <label>
          {{ t('settings.diarization_effective') }}
          <span class="toggle-desc">
            {{ diarizationInfo.effective === 'local' ? t('settings.diarization_effective_local') : t('settings.diarization_effective_cloud') }}
          </span>
        </label>
      </div>
      <div class="wm-setting-row">
        <label>
          {{ t('settings.diarization_local_toggle') }}
          <span class="toggle-desc">{{ t('settings.diarization_local_toggle_desc') }}</span>
        </label>
        <div class="wm-toggle-wrap">
          <div
            class="wm-toggle"
            :class="{ 'is-on': diarizationInfo.local_diarization, 'is-disabled': !diarizationInfo.can_toggle }"
            role="switch"
            :aria-checked="diarizationInfo.local_diarization"
            :tabindex="diarizationInfo.can_toggle ? 0 : -1"
            @click="onToggleDiarization"
            @keydown.enter.prevent="onToggleDiarization"
            @keydown.space.prevent="onToggleDiarization"
          ></div>
          <span class="wm-setting-val">{{ diarizationInfo.local_diarization ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
        </div>
        <span v-if="!diarizationInfo.can_toggle" class="toggle-experimental">{{ t('settings.diarization_requires_subscription') }}</span>
      </div>
    </div>

    <!-- 输出目录 -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.output_dir') }}</h2>
      <p class="settings-section-desc">{{ t('settings.output_dir_desc') }}</p>
      <div class="settings-field">
        <input v-model="settings.output_dir" class="settings-input" :placeholder="t('settings.output_dir_placeholder')" />
      </div>
    </div>

    <!-- 主题 -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.appearance') }}</h2>
      <div class="theme-grid">
        <button
          v-for="theme in THEMES"
          :key="theme.id"
          class="theme-chip"
          :class="{ 'is-active': themeStore.current === theme.id }"
          @click="themeStore.setTheme(theme.id)"
        >{{ t(`common.theme.${theme.id}`) }}</button>
      </div>
    </div>

    <!-- 水印氛围 -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.watermark') }}</h2>
      <p class="settings-section-desc">{{ t('settings.watermark_desc') }}</p>
      <div class="wm-setting-row">
        <label>{{ t('settings.watermark_enabled') }}</label>
        <div class="wm-toggle-wrap">
          <div
            class="wm-toggle"
            :class="{ 'is-on': wmEnabled }"
            role="switch"
            :aria-checked="wmEnabled"
            tabindex="0"
            @click="wmToggle"
            @keydown.enter.prevent="wmToggle"
            @keydown.space.prevent="wmToggle"
          ></div>
          <span class="wm-setting-val">{{ wmEnabled ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
        </div>
      </div>
      <div class="wm-setting-row">
        <label>{{ t('settings.watermark_opacity') }}</label>
        <input type="range" min="10" max="100" step="5" :value="Math.round(wmOpacity * 100)" @input="onWmOpacityInput" />
        <span class="wm-setting-val">{{ Math.round(wmOpacity * 100) }}%</span>
      </div>
    </div>

    <!-- 语言 -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.language') }}</h2>
      <p class="settings-section-desc">{{ t('settings.language_subtitle') }}</p>
      <div class="theme-grid">
        <button
          v-for="lang in LANG_OPTIONS"
          :key="lang.id"
          class="theme-chip"
          :class="{ 'is-active': currentLocale === lang.id }"
          @click="onSwitchLang(lang.id)"
        >{{ lang.label }}</button>
      </div>
    </div>

    <!-- 功能开关 -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.features') }}</h2>
      <p class="settings-section-desc">{{ t('settings.features_desc') }}</p>
      
      <div class="feature-toggles">
        <div class="wm-setting-row">
          <label>
            {{ t('settings.realtime_chapters') }}
            <span class="toggle-desc">{{ t('settings.realtime_chapters_desc') }}</span>
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
            <span class="wm-setting-val">{{ featureFlags.realtime_chapters ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
          </div>
        </div>

        <div class="wm-setting-row">
          <label>
            {{ t('settings.realtime_summary') }}
            <span class="toggle-desc">{{ t('settings.realtime_summary_desc') }}</span>
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
            <span class="wm-setting-val">{{ featureFlags.realtime_summary ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
          </div>

        </div>

        <div class="wm-setting-row">
          <label>
            {{ t('settings.update_check') }}
            <span class="toggle-desc">{{ t('settings.update_check_desc') }}</span>
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
            <span class="wm-setting-val">{{ featureFlags.update_check ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
          </div>
        </div>

        <div class="wm-setting-row">
          <label>
            {{ t('settings.voiceprint_auto_match') }}
            <span class="toggle-desc">{{ t('settings.voiceprint_auto_match_desc') }}</span>
            <span class="toggle-experimental">{{ t('settings.experimental') }}</span>
          </label>
          <div class="wm-toggle-wrap">
            <div 
              class="wm-toggle" 
              :class="{ 'is-on': featureFlags.voiceprint_auto_match }" 
              role="switch" 
              :aria-checked="featureFlags.voiceprint_auto_match"
              tabindex="0"
              @click="toggleFlag('voiceprint_auto_match')"
              @keydown.enter.prevent="toggleFlag('voiceprint_auto_match')"
              @keydown.space.prevent="toggleFlag('voiceprint_auto_match')"
            ></div>
            <span class="wm-setting-val">{{ featureFlags.voiceprint_auto_match ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
          </div>
        </div>
      </div>
    </div>
    <!-- 系统提示词 -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.system_prompts') }}</h2>
      <p class="settings-section-desc">{{ t('settings.system_prompts_desc') }}</p>
      <div class="prompt-list">
        <div v-for="(item, name) in systemPrompts" :key="name" class="prompt-item">
          <div class="prompt-item-header">
            <span class="prompt-item-name">{{ name }}</span>
            <span class="prompt-item-source">{{ t('settings.system_prompts_source') }}: {{ item.module }}</span>
            <button class="btn btn-sm btn-secondary" @click="togglePromptExpand(name)">
              {{ expandedPrompts.has(name) ? '▲' : t('settings.system_prompts_view') }}
            </button>
          </div>
          <p class="prompt-item-desc">{{ item.description }}</p>
          <pre v-if="expandedPrompts.has(name)" class="prompt-item-content">{{ item.prompt }}</pre>
        </div>
        <p v-if="!Object.keys(systemPrompts).length" class="settings-empty">—</p>
      </div>
    </div>

    <!-- CLI 命令参考 -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.cli_reference') }}</h2>
      <p class="settings-section-desc">{{ t('settings.cli_reference_desc') }}</p>
      <div class="cli-ref-list">
        <template v-for="(val, key) in cliReference" :key="key">
          <div v-if="typeof val === 'string'" class="cli-ref-item">
            <span class="cli-ref-cmd">{{ key }}</span>
            <code>{{ val }}</code>
          </div>
          <div v-else-if="typeof val === 'object'" class="cli-ref-group">
            <div class="cli-ref-group-title">{{ key }}</div>
            <div v-for="(subVal, subKey) in (val as Record<string, string>)" :key="subKey" class="cli-ref-item">
              <span class="cli-ref-cmd">{{ subKey }}</span>
              <code>{{ subVal }}</code>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 禁用快捷指令 -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.disabled_commands') }}</h2>
      <p class="settings-section-desc">{{ t('settings.disabled_commands_desc') }}</p>
      <div v-if="!settings.disabled_commands?.length" class="settings-empty">{{ t('settings.no_disabled_commands') }}</div>
      <div v-else class="disabled-cmd-list">
        <div v-for="cmd in settings.disabled_commands" :key="cmd" class="disabled-cmd-item">
          <code>{{ cmd }}</code>
          <button class="btn btn-sm btn-secondary" @click="onEnableCommand(cmd)">{{ t('settings.command_enable') }}</button>
        </div>
      </div>
    </div>

    <!-- 用量与配额 -->
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.usage') }}</h2>
      <p class="settings-section-desc">{{ t('settings.usage') }}</p>

      <!-- 未登录 -->
      <div v-if="!userStore.isLoggedIn" class="usage-not-metered">
        <p>{{ t('settings.usage_login_hint') }}</p>
        <button class="btn btn-primary" style="margin-top:12px;padding:0 16px;height:32px;font-size:12px" @click="showLogin">{{ t('settings.login') }}</button>
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
            <div class="stat-label">{{ t('settings.monthly_quota') }}</div>
          </div>
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.used || 0) }}</div>
            <div class="stat-label">{{ t('settings.used') }}</div>
          </div>
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.remaining || 0) }}</div>
            <div class="stat-label">{{ t('settings.remaining') }}</div>
          </div>
        </div>
        <div class="usage-progress">
          <div class="usage-progress-fill" :style="progressStyle"></div>
        </div>
        <div style="font-size:12px;color:var(--muted);margin-bottom:8px">{{ t('settings.recent_30_days') }}</div>
        <div class="usage-chart">
          <div
            v-for="d in usageHistory"
            :key="d.date"
            class="usage-chart-bar"
            :style="{ height: barHeight(d.minutes) + 'px' }"
            :data-tip="t('settings.usage_tooltip', { date: d.date.slice(5), minutes: formatMinutes(d.minutes), tasks: d.tasks })"
          ></div>
          <div v-if="!usageHistory.length" style="font-size:12px;color:var(--muted);padding:8px">{{ t('settings.no_usage') }}</div>
        </div>
      </div>

      <!-- 非计量模式 -->
      <div v-else class="usage-panel">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <span class="usage-tier-badge" :class="'tier-' + (usageSummary.tier || 'free')">{{ tierName(usageSummary.tier) }}</span>
          <span style="font-size:12px;color:var(--muted);font-family:var(--font-mono)">{{ t('settings.self_key') }}</span>
        </div>
        <div class="usage-summary-row">
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.quota || 0) }}</div>
            <div class="stat-label">{{ t('settings.monthly_quota') }}</div>
          </div>
          <div class="usage-stat">
            <div class="stat-value" style="color:var(--muted)">∞</div>
            <div class="stat-label">{{ t('settings.used_self') }}</div>
          </div>
          <div class="usage-stat">
            <div class="stat-value">{{ formatMinutes(usageSummary.quota || 0) }}</div>
            <div class="stat-label">{{ t('settings.platform_remaining') }}</div>
          </div>
        </div>
        <p style="margin:12px 0 0;font-size:12px;color:var(--muted)">{{ t('settings.cloud_mode_hint') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/user'
import { useThemeStore, THEMES } from '@/stores/theme'
import { useWatermarkStore } from '@/stores/watermark'
import { fetchSettings, saveSettings, testApiConnection, fetchSystemPrompts, fetchCliReference } from '@/api/settings'
import type { Settings, FeatureFlags, ProviderPreset, SystemPromptItem } from '@/api/settings'
import { fetchUsageSummary, fetchUsageHistory } from '@/api/usage'
import type { UsageSummary, UsageHistoryItem } from '@/api/usage'
import { setI18nLocale, getLocale, type SupportedLocale } from '@/i18n'

const { t } = useI18n()
const userStore = useUserStore()
const themeStore = useThemeStore()
const watermarkStore = useWatermarkStore()

const showPrivacyNotice = ref(true)

// ─── 水印氛围 ───
const wmEnabled = computed(() => watermarkStore.enabled)
const wmOpacity = computed(() => watermarkStore.opacity)

function wmToggle() {
  watermarkStore.toggle()
}

function onWmOpacityInput(e: Event) {
  const val = Number((e.target as HTMLInputElement).value)
  watermarkStore.setOpacity(val / 100)
}
const settings = reactive<Settings>({})
const testing = ref(false)
const testResult = ref('')
const testIsError = ref(false)

/** LLM Provider 预设列表（从后端加载） */
const llmPresets = computed<ProviderPreset[]>(() => settings.llm_provider_presets || [
  { name: 'DashScope（通义千问）', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen-plus', 'qwen-max', 'qwen-turbo'] },
  { name: 'OpenAI', base_url: 'https://api.openai.com/v1', models: ['gpt-4o', 'gpt-4o-mini'] },
  { name: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', models: ['deepseek-chat', 'deepseek-reasoner'] },
  { name: '自定义', base_url: '', models: [] },
])

/** Provider 切换时自动填充 Base URL */
function onLlmProviderChange() {
  const preset = llmPresets.value.find(p => p.name === settings.llm?.provider)
  if (preset && preset.base_url) {
    settings.llm!.base_url = preset.base_url
  }
}

const featureFlags = reactive<FeatureFlags>({
  realtime_chapters: true,
  realtime_summary: true,
  realtime_summary_interval: 60,
  update_check: true,
  voiceprint_auto_match: false,
})

const usageSummary = reactive<UsageSummary>({ metered: false })
const usageHistory = ref<UsageHistoryItem[]>([])

// ─── 声纹 / 分离 / 输出目录 ───
const diarizationInfo = reactive({
  subscription_tier: 'free',
  local_diarization: true,
  effective: 'local',
  can_toggle: false,
})

function onToggleDiarization() {
  if (!diarizationInfo.can_toggle) return
  diarizationInfo.local_diarization = !diarizationInfo.local_diarization
  saveSettings({ diarization: { local_diarization: diarizationInfo.local_diarization } } as any)
}

// ─── 系统提示词 ───
const systemPrompts = reactive<Record<string, SystemPromptItem>>({})
const expandedPrompts = reactive(new Set<string>())

function togglePromptExpand(name: string) {
  if (expandedPrompts.has(name)) expandedPrompts.delete(name)
  else expandedPrompts.add(name)
}

// ─── CLI 参考 ───
const cliReference = reactive<Record<string, unknown>>({})

// ─── 禁用指令 ───
function onEnableCommand(cmd: string) {
  if (!settings.disabled_commands) return
  settings.disabled_commands = settings.disabled_commands.filter(c => c !== cmd)
  saveSettings({ disabled_commands: settings.disabled_commands })
}

function tierName(_tier?: string) {
  return t('settings.tier_names.free')
}

// ─── 语言切换 ───
const LANG_OPTIONS: { id: SupportedLocale; label: string }[] = [
  { id: 'zh-CN', label: '简体中文' },
  { id: 'en', label: 'English' },
]
const currentLocale = computed(() => getLocale())

async function onSwitchLang(locale: SupportedLocale) {
  await setI18nLocale(locale)
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
    asr: { ...settings.asr },
    llm: { ...settings.llm },
    voiceprint: { ...settings.voiceprint },
    output_dir: settings.output_dir,
    feature_flags: { ...featureFlags },
  })
  alert(t('settings.saved'))
}

async function onTest() {
  testing.value = true
  testResult.value = ''
  try {
    const res = await testApiConnection()
    testResult.value = res.message || (res.success ? t('settings.connection_success') : t('settings.connection_failed'))
    testIsError.value = !res.success
  } catch {
    testResult.value = t('settings.connection_failed')
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



async function saveFeatureFlags() {
  await saveSettings({ feature_flags: { ...featureFlags } })
}

onMounted(async () => {
  const s = await fetchSettings()
  // 确保嵌套对象存在，避免模板中 settings.llm!.xxx 报错
  if (!s.llm) s.llm = {}
  if (!s.asr) s.asr = {}
  Object.assign(settings, s)
  if (s.feature_flags) {
    Object.assign(featureFlags, {
      realtime_chapters: s.feature_flags.realtime_chapters !== false,
      realtime_summary: s.feature_flags.realtime_summary !== false,
      realtime_summary_interval: s.feature_flags.realtime_summary_interval || 60,
      update_check: s.feature_flags.update_check !== false,
      voiceprint_auto_match: s.feature_flags.voiceprint_auto_match === true,
    })
  }
  // 声纹配置
  if (s.voiceprint) {
    if (!settings.voiceprint) settings.voiceprint = {}
    Object.assign(settings.voiceprint, s.voiceprint)
  }
  // 分离配置
  if (s.diarization) {
    Object.assign(diarizationInfo, s.diarization)
  }
  // 输出目录
  if (s.output_dir) {
    settings.output_dir = s.output_dir
  }
  loadUsage()
  loadSystemPrompts()
  loadCliReference()
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
    console.error('load usage failed:', e)
  }
}

async function loadSystemPrompts() {
  try {
    const data = await fetchSystemPrompts()
    Object.assign(systemPrompts, data)
  } catch (e) {
    console.error('load system prompts failed:', e)
  }
}

async function loadCliReference() {
  try {
    const data = await fetchCliReference()
    Object.assign(cliReference, data)
  } catch (e) {
    console.error('load cli reference failed:', e)
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
.api-subsection { margin-bottom: var(--s-5); padding-left: var(--s-3); border-left: 2px solid var(--border); }
.api-subsection-title { font-size: 13px; font-weight: 600; margin-bottom: var(--s-3); color: var(--fg); }
.api-readonly { font-size: 13px; color: var(--muted); display: flex; align-items: center; gap: var(--s-2); }
.api-proxy-hint { font-size: 11px; color: var(--subtle); }
.settings-test-result { font-size: 12px; margin-top: var(--s-2); }
.settings-test-result.is-error { color: var(--rec); }
.theme-grid { display: flex; flex-wrap: wrap; gap: var(--s-2); }
.theme-chip { padding: 6px var(--s-4); border-radius: 20px; border: 1px solid var(--border); background: var(--surface); color: var(--fg); font-size: 13px; cursor: pointer; transition: all 0.15s; }
.theme-chip:hover { border-color: var(--border-strong); }
.theme-chip.is-active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); font-weight: 500; }
.settings-section-desc { font-size: 12px; color: var(--muted); margin: calc(-1 * var(--s-2)) 0 var(--s-4); }
.feature-toggles { display: flex; flex-direction: column; gap: var(--s-5); }
.toggle-desc { display: block; font-size: 11px; color: var(--muted); font-weight: 400; margin-top: 2px; }
.toggle-experimental { display: inline-block; font-size: 10px; color: var(--muted); background: var(--border); padding: 1px 6px; border-radius: 8px; margin-left: 6px; vertical-align: middle; }
.interval-selector { display: flex; align-items: center; gap: var(--s-2); margin-top: var(--s-2); }
.interval-label { font-size: 12px; color: var(--muted); }
.freq-btns { display: flex; gap: 2px; }
.interval-hint { font-size: 11px; color: var(--subtle); }
.settings-empty { font-size: 13px; color: var(--muted); padding: var(--s-3) 0; }
.wm-toggle.is-disabled { opacity: 0.4; cursor: not-allowed; }
/* 声纹 / 分离 / 输出目录 */
/* 系统提示词 */
.prompt-list { display: flex; flex-direction: column; gap: var(--s-3); }
.prompt-item { border: 1px solid var(--border); border-radius: var(--radius); padding: var(--s-3); }
.prompt-item-header { display: flex; align-items: center; gap: var(--s-3); flex-wrap: wrap; }
.prompt-item-name { font-weight: 600; font-size: 13px; }
.prompt-item-source { font-size: 11px; color: var(--muted); font-family: var(--font-mono); }
.prompt-item-desc { font-size: 12px; color: var(--subtle); margin: 4px 0 0; }
.prompt-item-content { font-size: 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: var(--s-3); margin: var(--s-2) 0 0; white-space: pre-wrap; word-break: break-word; max-height: 300px; overflow-y: auto; font-family: var(--font-mono); line-height: 1.5; }
/* CLI 参考 */
.cli-ref-list { display: flex; flex-direction: column; gap: var(--s-2); }
.cli-ref-group { margin-bottom: var(--s-3); }
.cli-ref-group-title { font-size: 13px; font-weight: 600; margin-bottom: var(--s-2); color: var(--fg); }
.cli-ref-item { display: flex; align-items: baseline; gap: var(--s-3); padding: 4px 0; font-size: 13px; }
.cli-ref-cmd { font-weight: 500; min-width: 80px; color: var(--fg); }
.cli-ref-item code { font-family: var(--font-mono); font-size: 12px; color: var(--muted); background: var(--surface-2); padding: 2px 6px; border-radius: var(--radius-sm); word-break: break-all; }
/* 禁用指令 */
.disabled-cmd-list { display: flex; flex-direction: column; gap: var(--s-2); }
.disabled-cmd-item { display: flex; align-items: center; justify-content: space-between; padding: var(--s-2) var(--s-3); border: 1px solid var(--border); border-radius: var(--radius); }
.disabled-cmd-item code { font-family: var(--font-mono); font-size: 12px; color: var(--fg); }
</style>
