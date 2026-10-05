<template>
  <div class="cc-panel asp-panel">
    <div class="cc-page-head">
      <h1 class="cc-page-title">{{ t('settings.compute.asr_title') }}</h1>
      <p class="cc-page-lead">{{ t('settings.compute.asr_lead') }}</p>
    </div>

    <!-- ═══ 当前生效来源（只读状态条 + 自动改用开关） ═══ -->
    <div class="cc-card asp-status" data-od-id="asr-current-status">
      <div class="asp-ss-row">
        <span class="asp-ss-label">{{ t('settings.compute.current_source') }}</span>
        <span class="asp-ss-value">{{ liveName }}</span>
        <span class="cc-pill" :class="statusPillClass"><span class="cc-dot"></span>{{ statusPillText }}</span>
      </div>
      <p class="asp-ss-sub" :class="{ 'is-warn': statusMode !== 'live' }">{{ statusSub }}</p>
      <p v-if="hint" class="asp-ss-hint">{{ hint }}</p>
      <div class="asp-toggle-row">
        <label class="cc-switch">
          <input type="checkbox" :checked="fallbackOn" :disabled="fbBusy" data-od-id="asr-auto-fallback" @change="onToggleFallback">
          <span class="cc-switch-track"></span>
          <span class="asp-sw-label">{{ t('settings.compute.auto_fb_label') }}</span>
        </label>
        <span class="cc-note asp-fb-note">{{ fbNote }}</span>
      </div>
    </div>

    <!-- ═══ 来源卡（tab 仅导航；切换来源在卡片内） ═══ -->
    <p class="cc-note asp-tab-hint" data-od-id="asr-tab-hint">{{ t('settings.compute.asr_tab_hint') }}</p>
    <div class="asp-tablist" role="tablist" :aria-label="t('settings.compute.asr_title')" data-od-id="asr-tablist" @keydown="onTabKeydown">
      <button
        v-for="s in sources"
        :key="s.key"
        :ref="el => setTabRef(el, s.key)"
        class="asp-tab"
        :class="{ 'is-active': s.key === viewKey }"
        role="tab"
        :aria-selected="s.key === viewKey"
        :tabindex="s.key === viewKey ? 0 : -1"
        :data-tab="s.key"
        @click="viewKey = s.key"
      >
        <span class="asp-tab-name">{{ s.name }}</span>
        <span v-if="tabFlag(s.key)" class="asp-tab-flag" :class="tabFlag(s.key)!.cls">{{ tabFlag(s.key)!.text }}</span>
      </button>
    </div>

    <!-- 体验配额 -->
    <div v-show="viewKey === 'trial'" class="asp-tabpanel" data-od-id="asr-panel-trial">
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
          <p v-if="!readyMap.trial" class="cc-note" style="margin-top:var(--s-2)">{{ t('settings.compute.asr_trial_down_note') }}</p>
          <div class="cc-divider"></div>
          <dl class="cc-kv">
            <dt>{{ t('settings.compute.trial_remaining') }}</dt><dd>{{ quotaText }}</dd>
            <dt>{{ t('settings.asr_model') }}</dt><dd>{{ settings.asr?.model || 'paraformer-v2' }}</dd>
          </dl>
          <div class="cc-ladder-foot">
            <div class="cc-lf-enable">
              <button class="asp-radio" type="button" :aria-pressed="liveKey === 'trial'" :disabled="!readyMap.trial || busy" data-od-id="use-trial" @click="activate('trial')">
                <span class="asp-radio-mark"></span><span>{{ enableText('trial') }}</span>
              </button>
            </div>
            <p v-if="showCardFbNote('trial')" class="asp-card-fb-note">{{ t('settings.compute.card_fb_note') }}</p>
          </div>
        </template>
        <div v-else class="cc-need-login">
          <p class="cc-note">{{ t('settings.compute.need_login_hint') }}</p>
          <button class="cc-btn cc-btn-primary cc-btn-sm" @click="showLogin">{{ t('settings.login') }}</button>
        </div>
      </div>
    </div>

    <!-- API 提供商 -->
    <div v-show="viewKey === 'provider'" class="asp-tabpanel" data-od-id="asr-panel-provider">
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
              <input v-model="asrForm.api_key" :type="keyVisible ? 'text' : 'password'" class="cc-input cc-input-mono" :placeholder="t('settings.compute.asr_api_key_placeholder')" />
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
            <button class="asp-radio" type="button" :aria-pressed="liveKey === 'provider'" :disabled="!readyMap.provider || busy" data-od-id="use-provider" @click="activate('provider')">
              <span class="asp-radio-mark"></span><span>{{ enableText('provider') }}</span>
            </button>
          </div>
          <p v-if="showCardFbNote('provider')" class="asp-card-fb-note">{{ t('settings.compute.card_fb_note') }}</p>
        </div>
      </div>
    </div>

    <!-- 本地引擎 -->
    <div v-show="viewKey === 'local'" class="asp-tabpanel" data-od-id="asr-panel-local">
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
            <button class="asp-radio" type="button" :aria-pressed="liveKey === 'local'" :disabled="!readyMap.local || busy" data-od-id="use-local" @click="activate('local')">
              <span class="asp-radio-mark"></span><span>{{ enableText('local') }}</span>
            </button>
          </div>
          <p v-if="showCardFbNote('local')" class="asp-card-fb-note">{{ t('settings.compute.card_fb_note') }}</p>
        </div>
      </div>
    </div>

    <p class="cc-note asp-foot-note" data-od-id="asr-foot-note">{{ t('settings.compute.asr_foot_note') }}</p>
  </div>
</template>

<script setup lang="ts">
/**
 * ASR 配置面板（来源选择方案）：
 * - 用户选择一个来源，配置好后启用；启用为当前来源是全页唯一切换入口（卡片内单选控件）。
 * - 自动改用默认关闭：当前来源不可用时保持并明示，由用户手动切换或显式开启开关。
 * - 开关开启且发生自动改用时，顶部状态条留痕；原来源恢复后 routing 无状态自动切回。
 * 写路径复用既有端点：
 * - 体验配额 → capability_source.asr = trial
 * - API 提供商 → capability_source.asr = byok（direct）+ asr 表单独立「保存配置」
 * - 本地引擎 → capability_source.asr = local（事务内启停引擎）
 */
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { saveSettings, testApiConnection, type Settings } from '@/api/settings'
import { useUserStore } from '@/stores/user'
import { useEngineStore } from '@/stores/engine'
import type { CapSource } from '@/api/access'

type SrcKey = 'trial' | 'provider' | 'local'

const props = defineProps<{ settings: Settings }>()
const emit = defineEmits<{ (e: 'goto', category: 'engine'): void; (e: 'refresh'): void }>()

const { t } = useI18n()
const userStore = useUserStore()
const engineStore = useEngineStore()

const SOURCES: SrcKey[] = ['trial', 'provider', 'local']
const NAME_KEY: Record<SrcKey, string> = {
  trial: 'settings.compute.src_trial',
  provider: 'settings.compute.src_provider',
  local: 'settings.compute.src_local_engine',
}
function srcName(k: SrcKey): string { return t(NAME_KEY[k]) }

/** 工程来源值（routing/capability）↔ 面板来源键 */
function fromCap(s: string | undefined | null): SrcKey | '' {
  if (s === 'trial') return 'trial'
  if (s === 'byok') return 'provider'
  if (s === 'local') return 'local'
  return ''
}

const busy = ref(false)
const fbBusy = ref(false)
const testing = ref(false)
const testMsg = ref('')
const testErr = ref(false)
const keyVisible = ref(false)
const hint = ref('')

const asrForm = reactive({ base_url: '', model: '', api_key: '' })
watch(() => props.settings.asr, (a) => {
  asrForm.base_url = a?.base_url || ''
  asrForm.model = a?.model || 'paraformer-v2'
  asrForm.api_key = ''
}, { immediate: true, deep: true })

const byokReady = computed(() => !!props.settings.asr?.api_key_set)

function asrEngineReady(): boolean {
  // 就绪单源 = /api/engine/status → local_ready（与导航引擎绿点、LocalEnginePanel 同源）
  return engineStore.status?.local_ready === true
}
const engineRunning = computed(() => engineStore.status?.process_running === true)

/** 各来源就绪判定（启用控件 / 自动改用备选 / 状态条共用） */
const readyMap = computed<Record<SrcKey, boolean>>(() => ({
  trial: userStore.isLoggedIn && (engineStore.quotaRemaining == null || engineStore.quotaRemaining > 0),
  provider: byokReady.value,
  local: asrEngineReady(),
}))

const sources = computed(() => SOURCES.map(k => ({ key: k, name: srcName(k) })))

/** 用户显式选择（capability 真相源）；实际服务来源（routing，自动改用时可能不同） */
const chosenKey = computed<SrcKey | ''>(() => fromCap(engineStore.capability?.asr?.explicit))
const liveKey = computed<SrcKey | ''>(() => fromCap(engineStore.routing?.asr?.source as CapSource | undefined))
const switched = computed(() => engineStore.routing?.asr?.auto_switched === true && !!chosenKey.value && liveKey.value !== chosenKey.value)
const fallbackOn = computed(() => engineStore.autoFallback.asr)

const viewKey = ref<SrcKey>('trial')
watch(liveKey, (k, old) => {
  if (k && old === undefined) viewKey.value = k
}, { immediate: true })

/** tab 键盘导航：←/→ 循环、Home/End 跳转（roving tabindex） */
const tabRefs: Partial<Record<SrcKey, HTMLButtonElement | null>> = {}
function setTabRef(el: Element | { $el?: Element } | null, key: SrcKey) {
  tabRefs[key] = (el as HTMLButtonElement | null) ?? ((el as any)?.$el as HTMLButtonElement | null) ?? null
}
function onTabKeydown(e: KeyboardEvent) {
  const idx = SOURCES.indexOf(viewKey.value)
  let next = -1
  if (e.key === 'ArrowRight') next = (idx + 1) % SOURCES.length
  else if (e.key === 'ArrowLeft') next = (idx - 1 + SOURCES.length) % SOURCES.length
  else if (e.key === 'Home') next = 0
  else if (e.key === 'End') next = SOURCES.length - 1
  if (next >= 0) {
    e.preventDefault()
    viewKey.value = SOURCES[next]
    tabRefs[SOURCES[next]]?.focus()
  }
}

const quotaText = computed(() => engineStore.quotaRemaining == null ? '∞' : `${Math.round(engineStore.quotaRemaining)} ${t('settings.compute.minutes_unit')}`)

/** 额度计量快照（大数字 + 进度条）；不受计量（∞ / 未登录）时为 null */
const quotaInfo = computed(() => {
  const q = engineStore.routing?.quota
  if (!q || q.remaining == null || q.remaining < 0 || q.quota == null || q.quota <= 0) return null
  const used = q.used ?? Math.max(q.quota - q.remaining, 0)
  const pct = Math.min(100, Math.max(0, (used / q.quota) * 100))
  return { remaining: Math.round(q.remaining), total: Math.round(q.quota), used: Math.round(used), pct }
})

const engineStatusText = computed(() => {
  if (liveKey.value === 'local') return t('settings.compute.engine_running')
  return asrEngineReady() ? t('settings.compute.engine_ready_short') : t('settings.compute.engine_unready')
})

/** 不可用原因文案：优先用 routing reason，兜底用就绪判定 */
function downReasonText(key: SrcKey | ''): string {
  const reason = String(engineStore.routing?.asr?.reason || '')
  if (reason.includes('login')) return t('settings.compute.reason_trial_requires_login')
  if (reason.includes('quota_exhausted')) return t('settings.compute.reason_trial_quota_exhausted')
  if (reason.includes('byok_key_missing')) return t('settings.compute.reason_byok_key_missing')
  if (key === 'trial') return userStore.isLoggedIn ? t('settings.compute.reason_trial_quota_exhausted') : t('settings.compute.reason_trial_requires_login')
  if (key === 'provider') return t('settings.compute.reason_byok_key_missing')
  if (key === 'local') return t('settings.compute.reason_local_not_ready')
  return t('settings.compute.state_down')
}

function otherReady(except: SrcKey | ''): boolean {
  return SOURCES.some(k => k !== except && readyMap.value[k])
}

/* ── 顶部状态条三态：自动改用留痕 / 不可用引导 / 未选择 / 正常 ── */
type StatusMode = 'switched' | 'down' | 'unset' | 'live'
const statusMode = computed<StatusMode>(() => {
  if (switched.value) return 'switched'
  if (!chosenKey.value) return 'unset'
  if (!readyMap.value[chosenKey.value as SrcKey]) return 'down'
  return 'live'
})

const liveName = computed(() => (liveKey.value ? srcName(liveKey.value) : '—'))

const statusPillClass = computed(() => statusMode.value === 'live' ? 'cc-pill-accent' : 'cc-pill-warn')
const statusPillText = computed(() => {
  switch (statusMode.value) {
    case 'switched': return t('settings.compute.auto_switched_pill')
    case 'down': return t('settings.compute.unavailable_pill')
    case 'unset': return t('settings.compute.unset_pill')
    default: return t('settings.compute.effective')
  }
})

const statusSub = computed(() => {
  if (statusMode.value === 'switched' && chosenKey.value && liveKey.value) {
    return `${downReasonText(chosenKey.value)} · ${t('settings.compute.trace_to', { name: srcName(liveKey.value) })} · ${t('settings.compute.trace_return', { name: srcName(chosenKey.value) })}`
  }
  if (statusMode.value === 'down') {
    const tail = otherReady(chosenKey.value) ? t('settings.compute.unavailable_sub_switch') : t('settings.compute.unavailable_sub_config')
    return `${downReasonText(chosenKey.value)} · ${tail}`
  }
  if (statusMode.value === 'unset') return t('settings.compute.unset_sub')
  return t('settings.compute.status_live_sub')
})

const fbNote = computed(() => {
  if (!fallbackOn.value) return t('settings.compute.auto_fb_off')
  return otherReady(chosenKey.value) ? t('settings.compute.auto_fb_on') : t('settings.compute.auto_fb_on_none')
})

async function onToggleFallback(e: Event) {
  const v = (e.target as HTMLInputElement).checked
  fbBusy.value = true
  hint.value = ''
  try {
    await engineStore.applyAutoFallback('asr', v)
  } catch (err) {
    console.error('[asr] toggle auto fallback failed:', err)
    hint.value = t('settings.compute.auto_fb_failed')
  } finally {
    fbBusy.value = false
  }
}

/* ── Tab / 卡片状态 ── */
function tabFlag(key: SrcKey): { text: string; cls: 'asp-flag-live' | 'asp-flag-warn' } | null {
  if (key === liveKey.value && readyMap.value[key]) return { text: t('settings.compute.effective'), cls: 'asp-flag-live' }
  if (!readyMap.value[key]) {
    return { text: downFlagText(key), cls: 'asp-flag-warn' }
  }
  return null
}
function downFlagText(key: SrcKey): string {
  if (key === 'trial') return userStore.isLoggedIn ? t('settings.compute.state_exhausted') : t('settings.compute.need_login')
  if (key === 'provider') return t('settings.compute.state_unset')
  return t('settings.compute.state_not_ready')
}

function srcPillClass(key: SrcKey): string {
  if (key === liveKey.value && readyMap.value[key]) return 'cc-pill-accent'
  if (!readyMap.value[key]) return 'cc-pill-warn'
  return 'cc-pill-idle'
}
function srcStateText(key: SrcKey): string {
  if (key === liveKey.value && readyMap.value[key]) return t('settings.compute.effective')
  if (!readyMap.value[key]) return downFlagText(key)
  return t('settings.compute.state_ready')
}

function enableText(key: SrcKey): string {
  if (key === liveKey.value) return t('settings.compute.current_source_live')
  if (!readyMap.value[key]) {
    if (key === 'trial') return userStore.isLoggedIn ? t('settings.compute.disabled_quota') : t('settings.compute.disabled_login')
    if (key === 'provider') return t('settings.compute.disabled_key')
    return t('settings.compute.disabled_engine')
  }
  return t('settings.compute.enable_as_source')
}

/** 卡内自动改用提示：仅开关开启、本卡为生效来源且有备选时出现 */
function showCardFbNote(key: SrcKey): boolean {
  return fallbackOn.value && key === liveKey.value && otherReady(key)
}

function showLogin() { window.dispatchEvent(new CustomEvent('oms:show-login')) }

async function activate(key: SrcKey) {
  if (key === liveKey.value || !readyMap.value[key] || busy.value) return
  viewKey.value = key
  busy.value = true
  hint.value = ''
  try {
    if (key === 'trial') await engineStore.applyCapabilitySource({ asr: 'trial' })
    else if (key === 'provider') await engineStore.applyCapabilitySource({ asr: 'byok' })
    else await engineStore.applyCapabilitySource({ asr: 'local' })
  } catch (e) {
    console.error('[asr] activate failed:', e)
    hint.value = t('settings.compute.switch_failed')
  } finally {
    busy.value = false
  }
}

/** 保存表单配置（与启用解耦：保存不顺带切换来源） */
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
.asp-tabpanel { animation: cc-fade .18s ease; }
.cc-need-login { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-3); padding: var(--s-2) 0; }

/* ── 当前生效来源状态条 ── */
.asp-status { margin-bottom: var(--s-4); }
.asp-ss-row { display: flex; align-items: center; gap: var(--s-3); flex-wrap: wrap; }
.asp-ss-label { font-size: 13px; font-weight: 600; }
.asp-ss-value { font-size: 14px; font-weight: 600; }
.asp-ss-sub { font-family: var(--font-mono); font-size: 11px; color: var(--muted); margin-top: 6px; }
.asp-ss-sub.is-warn { color: var(--warn); }
.asp-ss-hint { font-size: 12px; color: var(--warn); margin-top: 6px; }

/* ── 自动改用开关行 ── */
.asp-toggle-row { display: flex; align-items: center; gap: var(--s-3); flex-wrap: wrap; margin-top: var(--s-4); padding-top: var(--s-3); border-top: 1px solid var(--border); }
.asp-sw-label { font-size: 13px; }
.asp-fb-note { font-size: 12px; }

/* ── Tab（仅导航，无编号） ── */
.asp-tab-hint { margin-bottom: var(--s-3); }
.asp-tablist { display: flex; gap: var(--s-1); border-bottom: 1px solid var(--border); margin-bottom: var(--s-3); }
.asp-tab { position: relative; flex: 0 0 auto; display: inline-flex; align-items: center; gap: 8px; height: 38px; padding: 0 14px; border: 0; background: transparent; border-radius: var(--radius-sm) var(--radius-sm) 0 0; cursor: pointer; }
.asp-tab:hover { background: var(--surface-2); }
.asp-tab.is-active::after { content: ""; position: absolute; left: var(--s-3); right: var(--s-3); bottom: -1px; height: 2px; background: var(--accent); border-radius: 2px; }
.asp-tab-name { font-size: 13px; color: var(--muted); white-space: nowrap; }
.asp-tab.is-active .asp-tab-name { color: var(--fg); font-weight: 600; }
.asp-tab-flag { font-family: var(--font-mono); font-size: 10px; border-radius: 4px; padding: 1px 6px; }
.asp-flag-live { color: var(--accent); background: var(--accent-soft); }
.asp-flag-warn { color: var(--warn); background: var(--warn-soft); }

/* ── 唯一切换入口：单选式启用控件 ── */
.asp-radio { display: inline-flex; align-items: center; gap: var(--s-2); min-height: 36px; padding: 0 var(--s-4); border: 1px solid var(--border-strong); border-radius: var(--radius); background: var(--surface); font-size: 13px; color: var(--fg); white-space: nowrap; cursor: pointer; }
.asp-radio:hover:not(:disabled) { background: var(--surface-2); border-color: var(--fg); }
.asp-radio[aria-pressed="true"] { border-color: var(--fg); font-weight: 600; }
.asp-radio[disabled] { opacity: .55; cursor: not-allowed; border-style: dashed; }
.asp-radio[disabled]:hover { background: var(--surface); border-color: var(--border-strong); }
.asp-radio-mark { width: 14px; height: 14px; border-radius: 50%; border: 1.5px solid var(--border-strong); display: inline-grid; place-items: center; flex: 0 0 auto; }
.asp-radio-mark::after { content: ""; width: 6px; height: 6px; border-radius: 50%; background: transparent; }
.asp-radio[aria-pressed="true"] .asp-radio-mark { border-color: var(--fg); }
.asp-radio[aria-pressed="true"] .asp-radio-mark::after { background: var(--fg); }

/* ── 卡内条件化提示 ── */
.asp-card-fb-note { font-family: var(--font-mono); font-size: 11px; color: var(--muted); text-align: right; line-height: 1.7; margin: 0; }

.asp-foot-note { margin-top: var(--s-5); }

/* ── 窄屏：tab 横滚不挤压，卡底提示左对齐不悬空 ── */
@media (max-width: 720px) {
  .asp-tablist { overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
  .asp-tablist::-webkit-scrollbar { display: none; }
  .asp-tab { flex: 0 0 auto; }
  .asp-card-fb-note { text-align: left; }
}
</style>
