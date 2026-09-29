<template>
  <div class="cc-panel">
    <div class="cc-page-head">
      <h1 class="cc-page-title">{{ t('settings.compute.ai_title') }}</h1>
      <p class="cc-page-lead">{{ t('settings.compute.ai_lead') }}</p>
    </div>

    <SourcePicker
      :label="t('settings.compute.ai_picker_label')"
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
        <span class="cc-src-meta">{{ t('settings.compute.ai_trial_meta') }}</span>
      </div>
      <div class="cc-card">
        <template v-if="userStore.isLoggedIn">
          <div class="cc-card-head">
            <div>
              <h2 class="cc-card-title">{{ t('settings.compute.month_quota') }}</h2>
              <p class="cc-card-desc">{{ t('settings.compute.month_quota_desc') }}</p>
            </div>
          </div>
          <div class="cc-quota-row">
            <div class="cc-quota-figure">{{ quotaRemaining == null ? '∞' : Math.round(quotaRemaining) }}<span v-if="quotaRemaining != null"> {{ t('settings.compute.minutes_left') }}</span></div>
            <!-- 体验配额在云端执行：本地 tag 模型名不在此生效，展示实际会用的云端模型（与 core/llm._cloud_safe_model 同规则） -->
            <div style="text-align:right" :title="t('settings.compute.model_trial_tip')"><div class="cc-note">{{ t('settings.compute.model') }}</div><div class="cc-mono" style="font-size:13px">{{ trialModel }}</div></div>
          </div>
          <div class="cc-divider"></div>
          <div class="cc-btn-row">
            <button class="cc-btn cc-btn-secondary cc-btn-sm" @click="activate('trial')">{{ t('settings.compute.use_this') }}</button>
            <button class="cc-btn cc-btn-ghost cc-btn-sm" @click="viewKey = 'provider'">{{ t('settings.compute.quota_to_provider') }}</button>
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
        <span v-if="activeKey === 'provider'" class="cc-src-pill cc-pill cc-pill-accent"><span class="cc-dot"></span>{{ t('settings.compute.effective') }}</span>
        <span class="cc-src-meta">{{ t('settings.compute.ai_provider_meta') }}</span>
      </div>
      <div class="cc-card">
        <div class="cc-card-head">
          <div>
            <h2 class="cc-card-title">{{ t('settings.compute.ai_provider_title') }}</h2>
            <p class="cc-card-desc">{{ t('settings.compute.ai_provider_desc') }}</p>
          </div>
        </div>
        <div class="cc-provider-grid">
          <button
            v-for="p in cloudPresets"
            :key="p.name"
            class="cc-provider"
            :class="{ 'is-selected': llmForm.provider === p.name }"
            @click="choosePreset(p)"
          >
            <span class="cc-provider-top">
              <span class="cc-provider-name">{{ p.name }}</span>
              <span v-if="llmForm.provider === p.name" class="cc-pill cc-pill-accent">{{ t('settings.compute.selected') }}</span>
            </span>
            <span class="cc-provider-models">{{ (p.models || []).slice(0, 2).join(' · ') }}</span>
          </button>
        </div>
        <div class="cc-grid-2">
          <div class="cc-field">
            <label class="cc-field-label">{{ t('settings.llm_base_url') }}</label>
            <input v-model="llmForm.base_url" class="cc-input cc-input-mono" :placeholder="t('settings.llm_base_url_placeholder')" />
          </div>
          <div class="cc-field">
            <label class="cc-field-label">{{ t('settings.llm_model') }}</label>
            <input v-model="llmForm.model" class="cc-input cc-input-mono" list="ai-model-options" placeholder="qwen-plus" />
            <datalist id="ai-model-options"><option v-for="m in modelOptions" :key="m" :value="m" /></datalist>
            <!-- 作用域说明（AI 算力入口治理 §4）：与 AI 面板统一资源清单的内置组文案镜像互指 -->
            <div class="cc-note">{{ t('settings.llm_model_scope_note') }}</div>
          </div>
        </div>
        <div class="cc-field">
          <label class="cc-field-label">{{ t('settings.api_key') }}</label>
          <div class="cc-field-inline">
            <input v-model="llmForm.api_key" :type="showKey ? 'text' : 'password'" class="cc-input cc-input-mono" :placeholder="t('settings.llm_api_key_placeholder')" />
            <button class="cc-btn cc-btn-secondary cc-btn-sm" @click="showKey = !showKey">{{ showKey ? t('settings.compute.hide') : t('settings.compute.show') }}</button>
          </div>
        </div>
        <div class="cc-btn-row">
          <button class="cc-btn cc-btn-primary cc-btn-sm" :disabled="busy" @click="saveProvider">{{ t('settings.compute.save_and_enable') }}</button>
          <button class="cc-btn cc-btn-secondary cc-btn-sm" :disabled="testing" @click="testLlm">{{ testing ? t('settings.testing') : t('settings.test_connection') }}</button>
          <span v-if="testMsg" class="cc-result-line" :class="{ 'is-error': testErr, 'is-ok': !testErr }">{{ testMsg }}</span>
        </div>
      </div>
    </div>

    <!-- 03 本机 CLI（正交栈：智能体对话算力） -->
    <div v-show="viewKey === 'cli'" class="cc-tabpanel">
      <div class="cc-source-line"><span class="cc-src-meta">{{ t('settings.compute.ai_cli_meta') }}</span></div>
      <div class="cc-card">
        <div class="cc-card-head">
          <div>
            <h2 class="cc-card-title">{{ t('settings.compute.ai_cli_title') }}</h2>
            <p class="cc-card-desc">{{ t('settings.compute.ai_cli_desc') }}</p>
          </div>
          <span class="cc-pill cc-pill-warn">{{ t('settings.compute.orthogonal_tag') }}</span>
        </div>
        <CliEnginePanel ref="cliPanel" />
      </div>
    </div>

    <!-- 04 本地端点 -->
    <div v-show="viewKey === 'endpoint'" class="cc-tabpanel">
      <div class="cc-source-line">
        <span v-if="activeKey === 'endpoint'" class="cc-src-pill cc-pill cc-pill-accent"><span class="cc-dot"></span>{{ t('settings.compute.effective') }}</span>
        <span class="cc-src-meta">{{ t('settings.compute.ai_endpoint_meta') }}</span>
      </div>
      <div class="cc-card">
        <div class="cc-card-head">
          <div>
            <h2 class="cc-card-title">{{ t('settings.compute.ai_endpoint_title') }}</h2>
            <p class="cc-card-desc">{{ t('settings.compute.ai_endpoint_desc') }}</p>
          </div>
          <span class="cc-pill">{{ t('settings.compute.data_local_tag') }}</span>
        </div>
        <div class="cc-field">
          <label class="cc-field-label">{{ t('settings.llm_base_url') }}</label>
          <input v-model="llmForm.base_url" class="cc-input cc-input-mono" placeholder="http://127.0.0.1:11434/v1" />
          <div class="cc-chips">
            <button v-for="e in localEngines" :key="e.base_url" class="cc-chip" @click="applyLocalEngine(e)">{{ e.name }}<span v-if="e.reachable"> · {{ t('settings.llm_probe_detected') }}</span></button>
          </div>
        </div>
        <div class="cc-grid-2">
          <div class="cc-field">
            <label class="cc-field-label">{{ t('settings.llm_model') }}</label>
            <input v-model="llmForm.model" class="cc-input cc-input-mono" list="ep-model-options" placeholder="qwen2.5:7b-instruct" />
            <datalist id="ep-model-options"><option v-for="m in localModels" :key="m" :value="m" /></datalist>
          </div>
          <div class="cc-field">
            <label class="cc-field-label">{{ t('settings.api_key') }}</label>
            <input v-model="llmForm.api_key" class="cc-input cc-input-mono" :placeholder="t('settings.compute.local_no_key')" />
          </div>
        </div>
        <div class="cc-btn-row">
          <button class="cc-btn cc-btn-primary cc-btn-sm" :disabled="busy" @click="saveEndpoint">{{ t('settings.compute.save_and_enable') }}</button>
          <button class="cc-btn cc-btn-secondary cc-btn-sm" :disabled="testing" @click="testLlm">{{ testing ? t('settings.testing') : t('settings.test_connection') }}</button>
          <span v-if="testMsg" class="cc-result-line" :class="{ 'is-error': testErr, 'is-ok': !testErr }">{{ testMsg }}</span>
        </div>
        <div class="cc-divider"></div>
        <p class="cc-note">{{ t('settings.compute.ai_endpoint_note') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * API 配置面板（REQ-COMPUTE-CENTER）：来源选择器 + 四 Tab。
 * 01 体验配额 → capability_source.llm=trial；02 API 提供商 → byok + LLM 表单；
 * 03 本机 CLI → 复用 CliEnginePanel（正交，仅配置 chat_engine，不改纪要路由）；
 * 04 本地端点 → local_endpoint + localhost 表单/探测。写路径全部复用既有端点。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import SourcePicker, { type SourceItem } from './SourcePicker.vue'
import CliEnginePanel from './CliEnginePanel.vue'
import { useComputeSource } from '@/composables/useComputeSource'
import { saveSettings, testApiConnection, probeLocalEngine, type Settings, type ProviderPreset, type LocalEngineProbe } from '@/api/settings'
import { useUserStore } from '@/stores/user'

const props = defineProps<{ settings: Settings }>()
const emit = defineEmits<{ (e: 'refresh'): void }>()

const { t } = useI18n()
const userStore = useUserStore()
const { currentSource, quotaRemaining, pickCloudSource } = useComputeSource()

const viewKey = ref<string>('trial')
const hint = ref('')
const busy = ref(false)
const testing = ref(false)
const showKey = ref(false)
const testMsg = ref('')
const testErr = ref(false)

const llmForm = reactive({ provider: '', base_url: '', model: '', api_key: '' })
watch(() => props.settings.llm, (l) => {
  llmForm.provider = l?.provider || ''
  llmForm.base_url = l?.base_url || ''
  llmForm.model = l?.model || ''
  llmForm.api_key = ''
}, { immediate: true, deep: true })

/** 体验配额实际生效的模型：llm.model 是跨来源共享字段，残留的本地 tag 名（含 ":"，如 qwen3:8b）
    在云端链路会被守护性回退为默认模型（与 core/llm._cloud_safe_model 同规则），卡片如实展示 */
const trialModel = computed(() => {
  const m = (props.settings.llm?.model || '').trim()
  return !m || m.includes(':') ? 'qwen-plus' : m
})

const presets = computed<ProviderPreset[]>(() => props.settings.llm_provider_presets || [
  { name: 'DashScope（通义千问）', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen-plus', 'qwen-max', 'qwen-turbo'] },
  { name: 'OpenAI', base_url: 'https://api.openai.com/v1', models: ['gpt-4o', 'gpt-4o-mini'] },
  { name: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', models: ['deepseek-chat', 'deepseek-reasoner'] },
  { name: '智谱 GLM', base_url: 'https://open.bigmodel.cn/api/paas/v4', models: ['glm-4-flash', 'glm-4-plus'] },
])
const cloudPresets = computed(() => presets.value.filter(p => !p.localhost))
const localEngines = ref<LocalEngineProbe[]>([])

function isLocalUrl(url?: string): boolean {
  if (!url) return false
  return /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/i.test(url)
}
const currentPreset = computed(() => presets.value.find(p => p.name === llmForm.provider))
const modelOptions = computed(() => currentPreset.value?.models || [])
const localModels = computed(() => {
  const e = localEngines.value.find(x => x.base_url === llmForm.base_url)
  return e?.reachable ? e.models : []
})

const byokReady = computed(() => !!props.settings.llm?.api_key_set)
// 就绪 = 配置的本地端点此刻探测可达（而非仅「填过 localhost 地址」）；未探测到即判不可用，避免 Ollama 未启动仍显示绿色
function originOf(u?: string): string {
  if (!u) return ''
  try { return new URL(u).origin } catch { return '' }
}
const endpointReady = computed(() => {
  const bu = props.settings.llm?.base_url || ''
  if (!isLocalUrl(bu)) return false
  const o = originOf(bu)
  return localEngines.value.some(e => e.reachable && (!o || originOf(e.base_url) === o))
})

const sources = computed<SourceItem[]>(() => {
  const q = quotaRemaining.value
  return [
    { key: 'trial', idx: '01', name: t('settings.compute.src_trial'), ready: userStore.isLoggedIn && (quotaRemaining.value == null || quotaRemaining.value > 0), meta: q == null ? t('settings.compute.trial_meta_inf') : t('settings.compute.trial_meta', { n: Math.round(q) }) },
    { key: 'provider', idx: '02', name: t('settings.compute.src_provider'), ready: byokReady.value, meta: t('settings.compute.ai_provider_meta') },
    { key: 'cli', idx: '03', name: t('settings.compute.src_cli'), ready: true, meta: t('settings.compute.ai_cli_meta') },
    { key: 'endpoint', idx: '04', name: t('settings.compute.src_endpoint'), ready: endpointReady.value, meta: t('settings.compute.ai_endpoint_meta') },
  ]
})

const activeKey = computed(() => {
  const src = currentSource('llm')
  if (src === 'trial') return 'trial'
  if (src === 'byok') return 'provider'
  if (src === 'local_endpoint') return 'endpoint'
  return 'trial'
})

function onActivate(key: string) { viewKey.value = key; if (key !== activeKey.value) activate(key) }

/** 未登录的体验配额：即便被选为当前来源，也应显示「需登录」而非「生效中」 */
const trialNeedsLogin = computed(() => activeKey.value === 'trial' && !userStore.isLoggedIn)
const headerState = computed(() => trialNeedsLogin.value
  ? { tone: 'warn' as const, text: t('settings.compute.need_login') }
  : { tone: 'live' as const, text: '' })

function isReady(key: string): boolean { return !!sources.value.find(s => s.key === key)?.ready }
function srcPillClass(key: string): string {
  if (key === 'trial' && !userStore.isLoggedIn) return 'cc-pill-warn'
  if (key === activeKey.value) return 'cc-pill-accent'
  return isReady(key) ? 'cc-pill-idle' : 'cc-pill-warn'
}
function srcStateText(key: string): string {
  if (key === 'trial' && !userStore.isLoggedIn) return t('settings.compute.need_login')
  if (key === activeKey.value) return t('settings.compute.effective')
  return isReady(key) ? t('settings.compute.state_ready') : t('settings.compute.state_down')
}
function showLogin() { window.dispatchEvent(new CustomEvent('oms:show-login')) }

async function activate(key: string) {
  hint.value = ''
  if (key === 'cli') { hint.value = t('settings.compute.cli_orthogonal_hint'); return }
  if (key === activeKey.value) return
  const item = sources.value.find(s => s.key === key)
  if (!item?.ready) {
    hint.value = key === 'provider' ? t('settings.compute.need_provider_hint')
      : key === 'endpoint' ? t('settings.compute.need_endpoint_hint')
      : t('settings.compute.need_login_hint')
    return
  }
  busy.value = true
  try {
    const cap: 'trial' | 'byok' | 'local_endpoint' = key === 'trial' ? 'trial' : key === 'provider' ? 'byok' : 'local_endpoint'
    await pickCloudSource('llm', cap)
  } catch (e) {
    console.error('[ai] pick source failed:', e)
    hint.value = t('settings.compute.switch_failed')
  } finally {
    busy.value = false
  }
}

function choosePreset(p: ProviderPreset) {
  llmForm.provider = p.name
  if (p.base_url) llmForm.base_url = p.base_url
  if (p.models?.length) llmForm.model = p.models[0]
}
function applyLocalEngine(e: LocalEngineProbe) {
  llmForm.base_url = e.base_url
  if (!llmForm.model && e.models.length) llmForm.model = e.models[0]
  if (!llmForm.api_key) llmForm.api_key = e.name.includes('LM Studio') ? 'lm-studio' : 'ollama'
}

async function persistLlm(): Promise<boolean> {
  try {
    await saveSettings({ llm: { ...props.settings.llm, provider: llmForm.provider, base_url: llmForm.base_url, model: llmForm.model, ...(llmForm.api_key ? { api_key: llmForm.api_key } : {}) } } as any)
    return true
  } catch (e) {
    console.error('[ai] save llm failed:', e)
    return false
  }
}

async function saveProvider() {
  busy.value = true
  if (await persistLlm()) { await pickCloudSource('llm', 'byok'); hint.value = '' }
  busy.value = false
  emit('refresh')
}
async function saveEndpoint() {
  busy.value = true
  if (await persistLlm()) { await pickCloudSource('llm', 'local_endpoint'); hint.value = '' }
  busy.value = false
  emit('refresh')
}

async function testLlm() {
  testing.value = true
  testMsg.value = ''
  try {
    const res = await testApiConnection({ service_type: 'llm', llm: { base_url: llmForm.base_url, api_key: llmForm.api_key, model: llmForm.model } })
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

onMounted(async () => {
  try {
    const r = await probeLocalEngine()
    localEngines.value = r.engines || []
  } catch { /* 静默 */ }
})
</script>

<style src="./compute.css"></style>
<style scoped>
.cc-tabpanel { animation: cc-fade .18s ease; }
@keyframes cc-fade { from { opacity: 0; } to { opacity: 1; } }
.cc-provider { display: block; }
.cc-need-login { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-3); padding: var(--s-2) 0; }
</style>
