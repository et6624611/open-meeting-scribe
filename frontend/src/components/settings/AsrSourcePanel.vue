<template>
  <div class="cc-panel">
    <div class="cc-page-head">
      <h1 class="cc-page-title">{{ t('settings.compute.asr_title') }}</h1>
      <p class="cc-page-lead">{{ t('settings.compute.asr_lead') }}</p>
    </div>

    <SourcePicker
      :label="t('settings.compute.asr_picker_label')"
      :sources="sources"
      :active-key="activeKey"
      :view-key="viewKey"
      :hint="hint"
      :active-state-tone="headerState.tone"
      :active-state-text="headerState.text"
      @activate="onActivate"
      @view="viewKey = $event"
    />

    <!-- 01 体验配额 -->
    <div v-show="viewKey === 'trial'" class="cc-tabpanel">
      <div class="cc-source-line">
        <span class="cc-src-pill cc-pill" :class="srcPillClass('trial')"><span class="cc-dot"></span>{{ srcStateText('trial') }}</span>
        <span class="cc-src-meta">{{ t('settings.compute.asr_trial_meta') }}</span>
      </div>
      <div class="cc-card">
        <template v-if="userStore.isLoggedIn">
          <div class="cc-card-head">
            <div>
              <h2 class="cc-card-title">{{ t('settings.compute.asr_trial_shared') }}</h2>
              <p class="cc-card-desc">{{ t('settings.compute.asr_trial_shared_desc') }}</p>
            </div>
          </div>
          <div class="cc-quota-row">
            <div class="cc-quota-figure" v-if="quotaInfo">{{ quotaInfo.remaining }}<span> / {{ quotaInfo.total }} {{ t('settings.compute.minutes_left') }}</span></div>
            <div class="cc-quota-figure" v-else>∞<span> · {{ t('settings.compute.trial_meta_inf') }}</span></div>
          </div>
          <template v-if="quotaInfo">
            <div class="cc-meter"><div class="cc-meter-fill" :style="{ width: quotaInfo.pct + '%' }"></div></div>
            <div class="cc-meter-legend">
              <span>{{ t('settings.compute.quota_meter_legend', { used: quotaInfo.used, total: quotaInfo.total }) }}</span>
              <span>{{ quotaInfo.pct.toFixed(1) }}%</span>
            </div>
          </template>
          <div class="cc-divider"></div>
          <dl class="cc-kv">
            <dt>{{ t('settings.compute.trial_remaining') }}</dt><dd>{{ quotaText }}</dd>
            <dt>{{ t('settings.asr_model') }}</dt><dd>{{ settings.asr?.model || 'paraformer-v2' }}</dd>
          </dl>
          <div class="cc-ladder-foot">
            <div class="cc-lf-enable">
              <button class="cc-btn cc-btn-primary cc-btn-sm" :disabled="activeKey === 'trial' || busy" @click="activate('trial')">{{ t('settings.compute.use_this') }}</button>
              <span class="cc-lf-label">{{ t('settings.compute.instant_tag') }}</span>
            </div>
            <p class="cc-lf-fallback">{{ t('settings.compute.ladder_fb_trial') }}</p>
          </div>
        </template>
        <div v-else class="cc-need-login">
          <p class="cc-note">{{ t('settings.compute.need_login_hint') }}</p>
          <button class="cc-btn cc-btn-primary cc-btn-sm" @click="showLogin">{{ t('settings.login') }}</button>
        </div>
      </div>
    </div>

    <!-- 02 API 提供商 -->
    <div v-show="viewKey === 'provider'" class="cc-tabpanel">
      <div class="cc-source-line">
        <span class="cc-src-pill cc-pill" :class="srcPillClass('provider')"><span class="cc-dot"></span>{{ srcStateText('provider') }}</span>
        <span class="cc-src-meta">{{ t('settings.compute.asr_provider_meta') }}</span>
      </div>
      <div class="cc-card">
        <div class="cc-card-head">
          <div>
            <h2 class="cc-card-title">{{ t('settings.compute.asr_provider_title') }}</h2>
            <p class="cc-card-desc">{{ t('settings.compute.asr_provider_desc') }}</p>
          </div>
          <span class="cc-pill">{{ t('settings.compute.asr_hotword_tag') }}</span>
        </div>
        <p v-if="!byokReady" class="cc-note" style="margin-bottom:var(--s-4)">
          <span class="cc-pill cc-pill-warn"><span class="cc-dot"></span>{{ t('settings.compute.state_unset') }}</span>
          {{ t('settings.compute.activated_notready_key') }}
        </p>
        <div class="cc-field">
          <label class="cc-field-label">{{ t('settings.asr_base_url') }}</label>
          <input v-model="asrForm.base_url" class="cc-input cc-input-mono" placeholder="https://dashscope.aliyuncs.com" />
        </div>
        <div class="cc-grid-2">
          <div class="cc-field">
            <label class="cc-field-label">{{ t('settings.asr_model') }}</label>
            <input v-model="asrForm.model" class="cc-input cc-input-mono" placeholder="paraformer-v2" />
          </div>
          <div class="cc-field">
            <label class="cc-field-label">{{ t('settings.api_key') }}</label>
            <div class="cc-field-inline">
              <input v-model="asrForm.api_key" :type="keyVisible ? 'text' : 'password'" class="cc-input cc-input-mono" :placeholder="t('settings.asr_api_key_placeholder')" />
              <button class="cc-btn cc-btn-secondary cc-btn-sm" @click="keyVisible = !keyVisible">{{ keyVisible ? t('settings.compute.hide') : t('settings.compute.show') }}</button>
            </div>
          </div>
        </div>
        <div class="cc-btn-row">
          <button class="cc-btn cc-btn-secondary cc-btn-sm" :disabled="busy" @click="saveProvider">{{ t('settings.compute.save_config') }}</button>
          <button class="cc-btn cc-btn-secondary cc-btn-sm" :disabled="testing" @click="testProvider">{{ testing ? t('settings.testing') : t('settings.test_connection') }}</button>
          <span v-if="testMsg" class="cc-result-line" :class="{ 'is-error': testErr, 'is-ok': !testErr }">{{ testMsg }}</span>
        </div>
        <div class="cc-ladder-foot">
          <div class="cc-lf-enable">
            <button class="cc-btn cc-btn-primary cc-btn-sm" :disabled="activeKey === 'provider' || busy" @click="activate('provider')">{{ t('settings.compute.use_this') }}</button>
            <span class="cc-lf-label">{{ t('settings.compute.instant_tag') }}</span>
          </div>
          <p class="cc-lf-fallback">{{ t('settings.compute.ladder_fb_provider') }}</p>
        </div>
      </div>
    </div>

    <!-- 03 本地引擎 -->
    <div v-show="viewKey === 'local'" class="cc-tabpanel">
      <div class="cc-source-line">
        <span class="cc-src-pill cc-pill" :class="srcPillClass('local')"><span class="cc-dot"></span>{{ srcStateText('local') }}</span>
        <span class="cc-src-meta">{{ t('settings.compute.asr_local_meta') }}</span>
      </div>
      <div class="cc-card">
        <div class="cc-card-head">
          <div>
            <h2 class="cc-card-title">{{ t('settings.compute.asr_local_title') }}</h2>
            <p class="cc-card-desc">{{ t('settings.compute.asr_local_desc') }}</p>
          </div>
          <span class="cc-pill">{{ t('settings.compute.data_local_tag') }}</span>
        </div>
        <div class="cc-row cc-row-first">
          <div>
            <div class="cc-row-main">{{ t('settings.compute.engine_status') }}</div>
            <div class="cc-row-sub">{{ engineStatusText }}</div>
          </div>
          <div class="cc-row-side">
            <span v-if="engineRunning" class="cc-pill cc-pill-ok"><span class="cc-dot"></span>{{ t('settings.compute.engine_running_yes') }}</span>
            <button class="cc-btn cc-btn-secondary cc-btn-sm" @click="emit('goto', 'engine')">{{ t('settings.compute.manage_models') }}</button>
          </div>
        </div>
        <p class="cc-note" style="color:var(--warn);margin-top:var(--s-2)">{{ t('settings.compute.asr_local_risk_note') }}</p>
        <div class="cc-ladder-foot">
          <div class="cc-lf-enable">
            <button class="cc-btn cc-btn-primary cc-btn-sm" :disabled="activeKey === 'local' || busy" @click="activate('local')">{{ t('settings.compute.use_this') }}</button>
            <span class="cc-lf-label">{{ t('settings.compute.instant_tag') }}</span>
          </div>
          <p class="cc-lf-fallback">{{ t('settings.compute.ladder_fb_local') }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ASR 配置面板（启用与顺延统一方案）：
 * - 规则一 · 三档统一「即选即用」：任意档位点「选为当前来源」即生效，
 *   不再前置开关 / 二次确认 / 先配置后启用；未就绪档选中后行内提示补配置。
 * - 规则二 · 顺延说明随各档卡底 ladder-foot 行内呈现（顺延判定与自动动作
 *   由后端 core/routing 明示自动改用承担）。
 * 写路径复用既有端点：
 * - 01 体验配额 → capability_source.asr = trial
 * - 02 API 提供商 → capability_source.asr = byok（direct）+ asr 表单独立「保存配置」
 * - 03 本地引擎 → access_mode = local（整机离线，无二次确认）
 */
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import SourcePicker, { type SourceItem } from './SourcePicker.vue'
import { useComputeSource } from '@/composables/useComputeSource'
import { saveSettings, testApiConnection, type Settings } from '@/api/settings'
import { useUserStore } from '@/stores/user'
import { useEngineStore } from '@/stores/engine'

const props = defineProps<{ settings: Settings }>()
const emit = defineEmits<{ (e: 'goto', category: 'engine'): void; (e: 'refresh'): void }>()

const { t } = useI18n()
const userStore = useUserStore()
const engineStore = useEngineStore()
const { currentSource, quotaRemaining, pickCloudSource, pickLocalEngine } = useComputeSource()

const viewKey = ref<string>('trial')
const hint = ref('')
const busy = ref(false)
const testing = ref(false)
const testMsg = ref('')
const testErr = ref(false)
const keyVisible = ref(false)

const asrForm = reactive({ base_url: '', model: '', api_key: '' })
watch(() => props.settings.asr, (a) => {
  asrForm.base_url = a?.base_url || ''
  asrForm.model = a?.model || 'paraformer-v2'
  asrForm.api_key = ''
}, { immediate: true, deep: true })

const byokReady = computed(() => !!props.settings.asr?.api_key_set)

function asrEngineReady(): boolean {
  // 就绪单源 = /api/engine/status → local_ready（与导航引擎绿点、LocalEnginePanel 同源）；
  // settings.engine.local.ready 是后端从未返回的占位字段，曾致本卡恒判「不可用」。
  return engineStore.status?.local_ready === true
}
const engineRunning = computed(() => engineStore.status?.process_running === true)

/** 各档就绪判定（统一供选择器 / 顺延链 / 行内状态消费） */
const readyMap = computed<Record<string, boolean>>(() => ({
  trial: userStore.isLoggedIn && (quotaRemaining.value == null || quotaRemaining.value > 0),
  provider: byokReady.value,
  local: asrEngineReady(),
}))

const sources = computed<SourceItem[]>(() => {
  const q = quotaRemaining.value
  return [
    { key: 'trial', idx: '01', name: t('settings.compute.src_trial'), ready: readyMap.value.trial, meta: q == null ? t('settings.compute.trial_meta_inf') : t('settings.compute.trial_meta', { n: Math.round(q) }) },
    { key: 'provider', idx: '02', name: t('settings.compute.src_provider'), ready: readyMap.value.provider, meta: t('settings.compute.asr_provider_meta') },
    { key: 'local', idx: '03', name: t('settings.compute.src_local_engine'), ready: readyMap.value.local, meta: t('settings.compute.asr_local_meta') },
  ]
})

const activeKey = computed(() => {
  const src = currentSource('asr')
  if (src === 'trial') return 'trial'
  if (src === 'byok') return 'provider'
  if (src === 'local') return 'local'
  return 'trial'
})

const quotaText = computed(() => quotaRemaining.value == null ? '∞' : `${Math.round(quotaRemaining.value)} ${t('settings.compute.minutes_unit')}`)

/** 额度计量快照（大数字 + 进度条）；不受计量（∞ / 未登录）时为 null */
const quotaInfo = computed(() => {
  const q = engineStore.routing?.quota
  if (!q || q.remaining == null || q.remaining < 0 || q.quota == null || q.quota <= 0) return null
  const used = q.used ?? Math.max(q.quota - q.remaining, 0)
  const pct = Math.min(100, Math.max(0, (used / q.quota) * 100))
  return { remaining: Math.round(q.remaining), total: Math.round(q.quota), used: Math.round(used), pct }
})

const engineStatusText = computed(() => {
  if (currentSource('asr') === 'local') return t('settings.compute.engine_running')
  return asrEngineReady() ? t('settings.compute.engine_ready_short') : t('settings.compute.engine_unready')
})

function srcPillClass(key: string): string {
  if (key === 'trial' && !userStore.isLoggedIn) return 'cc-pill-warn'
  if (key === activeKey.value) return 'cc-pill-accent'
  if (!readyMap.value[key]) return 'cc-pill-warn'
  return 'cc-pill-idle'
}
function srcStateText(key: string): string {
  if (key === 'trial' && !userStore.isLoggedIn) return t('settings.compute.need_login')
  if (key === activeKey.value) return t('settings.compute.effective')
  if (!readyMap.value[key]) return t('settings.compute.state_down')
  return t('settings.compute.state_ready')
}
/** 未登录的体验配额：顶部选择器头部同步显示「需登录」 */
const headerState = computed(() => (activeKey.value === 'trial' && !userStore.isLoggedIn)
  ? { tone: 'warn' as const, text: t('settings.compute.need_login') }
  : { tone: 'live' as const, text: '' })
function showLogin() { window.dispatchEvent(new CustomEvent('oms:show-login')) }

/**
 * 即选即用：三档一律执行切换（不再就绪拦截、不再二次确认）；
 * 切到未就绪档后行内提示补配置方向，切换失败保持原来源并提示。
 */
async function activate(key: string) {
  if (key === activeKey.value) { viewKey.value = key; return }
  viewKey.value = key
  busy.value = true
  hint.value = ''
  try {
    if (key === 'trial') await pickCloudSource('asr', 'trial')
    else if (key === 'provider') await pickCloudSource('asr', 'byok')
    else if (key === 'local') await pickLocalEngine()
    if (!readyMap.value[key]) {
      hint.value = key === 'trial'
        ? t('settings.compute.activated_notready_login')
        : (key === 'provider' ? t('settings.compute.activated_notready_key') : t('settings.compute.activated_notready_engine'))
    }
  } catch (e) {
    console.error('[asr] activate failed:', e)
    hint.value = t('settings.compute.switch_failed')
  } finally {
    busy.value = false
  }
}
function onActivate(key: string) { activate(key) }

/** 保存表单配置（与启用解耦：先启用后补配置，保存不再顺带切换来源） */
async function saveProvider() {
  busy.value = true
  try {
    await saveSettings({ asr: { ...props.settings.asr, mode: 'direct', base_url: asrForm.base_url, model: asrForm.model, ...(asrForm.api_key ? { api_key: asrForm.api_key } : {}) } } as any)
    hint.value = ''
  } catch (e) {
    console.error('[asr] save provider failed:', e)
  } finally {
    busy.value = false
    emit('refresh')
  }
}

async function testProvider() {
  testing.value = true
  testMsg.value = ''
  try {
    const res = await testApiConnection({ service_type: 'asr', asr: { mode: 'direct', base_url: asrForm.base_url, api_key: asrForm.api_key } })
    const ok = res.ok ?? res.success
    testErr.value = !ok
    testMsg.value = res.message || res.error || (ok ? t('settings.connection_success') : t('settings.connection_failed'))
  } catch {
    testErr.value = true
    testMsg.value = t('settings.connection_failed')
  } finally {
    testing.value = false
  }
}
</script>

<style src="./compute.css"></style>
<style scoped>
.cc-tabpanel { animation: cc-fade .18s ease; }
@keyframes cc-fade { from { opacity: 0; } to { opacity: 1; } }
.cc-need-login { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-3); padding: var(--s-2) 0; }
</style>
