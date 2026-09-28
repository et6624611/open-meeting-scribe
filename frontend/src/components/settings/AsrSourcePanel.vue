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
      @activate="onActivate"
      @view="viewKey = $event"
    />

    <!-- 01 体验配额 -->
    <div v-show="viewKey === 'trial'" class="cc-tabpanel">
      <div class="cc-source-line">
        <span v-if="activeKey === 'trial'" class="cc-src-pill cc-pill cc-pill-accent"><span class="cc-dot"></span>{{ t('settings.compute.effective') }}</span>
        <span class="cc-src-meta">{{ t('settings.compute.asr_trial_meta') }}</span>
      </div>
      <div class="cc-card">
        <div class="cc-card-head">
          <div>
            <h2 class="cc-card-title">{{ t('settings.compute.asr_trial_shared') }}</h2>
            <p class="cc-card-desc">{{ t('settings.compute.asr_trial_shared_desc') }}</p>
          </div>
        </div>
        <dl class="cc-kv">
          <dt>{{ t('settings.compute.trial_remaining') }}</dt><dd>{{ quotaText }}</dd>
          <dt>{{ t('settings.asr_model') }}</dt><dd>{{ settings.asr?.model || 'paraformer-v2' }}</dd>
        </dl>
        <div class="cc-divider"></div>
        <div class="cc-btn-row">
          <button class="cc-btn cc-btn-secondary cc-btn-sm" @click="activate('trial')">{{ t('settings.compute.use_this') }}</button>
          <button class="cc-btn cc-btn-ghost cc-btn-sm" @click="viewKey = 'provider'">{{ t('settings.compute.quota_to_provider') }}</button>
        </div>
      </div>
    </div>

    <!-- 02 API 提供商 -->
    <div v-show="viewKey === 'provider'" class="cc-tabpanel">
      <div class="cc-source-line">
        <span v-if="activeKey === 'provider'" class="cc-src-pill cc-pill cc-pill-accent"><span class="cc-dot"></span>{{ t('settings.compute.effective') }}</span>
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
            <input v-model="asrForm.api_key" type="password" class="cc-input cc-input-mono" :placeholder="t('settings.asr_api_key_placeholder')" />
          </div>
        </div>
        <div class="cc-btn-row">
          <button class="cc-btn cc-btn-primary cc-btn-sm" @click="saveProvider">{{ t('settings.compute.save_and_enable') }}</button>
          <button class="cc-btn cc-btn-secondary cc-btn-sm" :disabled="testing" @click="testProvider">{{ testing ? t('settings.testing') : t('settings.test_connection') }}</button>
          <span v-if="testMsg" class="cc-result-line" :class="{ 'is-error': testErr, 'is-ok': !testErr }">{{ testMsg }}</span>
        </div>
      </div>
    </div>

    <!-- 03 本地引擎 -->
    <div v-show="viewKey === 'local'" class="cc-tabpanel">
      <div class="cc-source-line">
        <span v-if="activeKey === 'local'" class="cc-src-pill cc-pill cc-pill-accent"><span class="cc-dot"></span>{{ t('settings.compute.effective') }}</span>
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
            <button class="cc-btn cc-btn-secondary cc-btn-sm" @click="emit('goto', 'engine')">{{ t('settings.compute.manage_models') }}</button>
            <template v-if="confirmLocal">
              <button class="cc-btn cc-btn-primary cc-btn-sm" @click="doLocalSwitch(true)">{{ t('settings.compute.confirm_switch') }}</button>
              <button class="cc-btn cc-btn-ghost cc-btn-sm" @click="confirmLocal = false">{{ t('settings.compute.cancel') }}</button>
            </template>
            <button v-else class="cc-btn cc-btn-primary cc-btn-sm" :disabled="busy" @click="onLocalClick">{{ t('settings.compute.use_as_asr') }}</button>
          </div>
        </div>
        <p v-if="confirmLocal" class="cc-note" style="color:var(--warn);margin-top:var(--s-2)">{{ t('settings.compute.local_risk') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ASR 配置面板（REQ-COMPUTE-CENTER）：来源选择器 + 三 Tab。
 * - 01 体验配额 → capability_source.asr = trial
 * - 02 API 提供商 → capability_source.asr = byok（direct）+ 编辑 asr 表单
 * - 03 本地引擎 → access_mode = local（整机离线，含打断确认）
 * 仅前端重排，写路径复用既有端点。
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
const { accessMode, currentSource, quotaRemaining, pickCloudSource, pickLocalEngine } = useComputeSource()

const viewKey = ref<string>('trial')
const hint = ref('')
const busy = ref(false)
const confirmLocal = ref(false)
const testing = ref(false)
const testMsg = ref('')
const testErr = ref(false)

const asrForm = reactive({ base_url: '', model: '', api_key: '' })
watch(() => props.settings.asr, (a) => {
  asrForm.base_url = a?.base_url || ''
  asrForm.model = a?.model || 'paraformer-v2'
  asrForm.api_key = ''
}, { immediate: true, deep: true })

const byokReady = computed(() => !!props.settings.asr?.api_key_set)

function asrEngineReady(): boolean {
  // 就绪单源 = /api/engine/status → models_ready（与导航引擎绿点、LocalEnginePanel 同源）；
  // settings.engine.local.ready 是后端从未返回的占位字段，曾致本卡恒判「不可用」。
  // Single source: engine status models_ready; settings.engine.local.ready was a never-populated placeholder.
  return engineStore.status?.local_ready === true
}

const sources = computed<SourceItem[]>(() => {
  const q = quotaRemaining.value
  return [
    { key: 'trial', idx: '01', name: t('settings.compute.src_trial'), ready: userStore.isLoggedIn, meta: q == null ? t('settings.compute.trial_meta_inf') : t('settings.compute.trial_meta', { n: Math.round(q) }) },
    { key: 'provider', idx: '02', name: t('settings.compute.src_provider'), ready: byokReady.value, meta: t('settings.compute.asr_provider_meta') },
    { key: 'local', idx: '03', name: t('settings.compute.src_local_engine'), ready: asrEngineReady(), meta: t('settings.compute.asr_local_meta') },
  ]
})

const activeKey = computed(() => {
  if (accessMode.value === 'local') return 'local'
  const src = currentSource('asr')
  if (src === 'trial') return 'trial'
  if (src === 'byok') return 'provider'
  return 'trial'
})

const quotaText = computed(() => quotaRemaining.value == null ? '∞' : `${Math.round(quotaRemaining.value)} ${t('settings.compute.minutes_unit')}`)
const engineStatusText = computed(() => {
  if (accessMode.value === 'local') return t('settings.compute.engine_running')
  return asrEngineReady() ? t('settings.compute.engine_ready_short') : t('settings.compute.engine_unready')
})

async function activate(key: string) {
  if (key === activeKey.value) { viewKey.value = key; return }
  const item = sources.value.find(s => s.key === key)
  if (!item?.ready) {
    hint.value = key === 'provider'
      ? t('settings.compute.need_provider_hint')
      : (key === 'local' ? t('settings.compute.need_local_hint') : t('settings.compute.need_login_hint'))
    viewKey.value = key
    return
  }
  hint.value = ''
  viewKey.value = key
  busy.value = true
  try {
    if (key === 'trial') await pickCloudSource('asr', 'trial')
    else if (key === 'provider') await pickCloudSource('asr', 'byok')
  } catch (e) {
    console.error('[asr] pick source failed:', e)
    hint.value = t('settings.compute.switch_failed')
  } finally {
    busy.value = false
  }
}
function onActivate(key: string) { activate(key) }

function onLocalClick() {
  if (asrEngineReady()) { confirmLocal.value = true; viewKey.value = 'local' }
  else { hint.value = t('settings.compute.need_local_hint'); viewKey.value = 'local' }
}
async function doLocalSwitch(confirmed: boolean) {
  confirmLocal.value = false
  if (!confirmed) return
  busy.value = true
  try {
    await pickLocalEngine()
    hint.value = ''
  } catch (e) {
    console.error('[asr] local switch failed:', e)
    hint.value = t('settings.compute.switch_failed')
  } finally {
    busy.value = false
  }
}

async function saveProvider() {
  busy.value = true
  try {
    await saveSettings({ asr: { ...props.settings.asr, mode: 'direct', base_url: asrForm.base_url, model: asrForm.model, ...(asrForm.api_key ? { api_key: asrForm.api_key } : {}) } } as any)
    if (asrForm.api_key) await pickCloudSource('asr', 'byok')
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
</style>
