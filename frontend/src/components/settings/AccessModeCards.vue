<template>
  <div class="access-cards">
    <!-- R4 引导头：未登录且未配置时首屏出现 / Onboarding header (not logged in & unconfigured) -->
    <div v-if="onboarding" class="access-guide">
      <h2 class="access-guide-title">{{ t('settings.access.guide_title') }}</h2>
      <p class="access-guide-desc">{{ t('settings.access.guide_desc') }}</p>
    </div>

    <!-- ═══ R1 三张接入方式卡片 / Three access-mode cards ═══ -->
    <div class="amc-grid" role="radiogroup" :aria-label="t('settings.cat_access')">
      <div
        v-for="card in CARDS"
        :key="card.mode"
        class="amc-card"
        :class="{ 'is-selected': current === card.mode, 'is-busy': busy }"
        role="radio"
        :aria-checked="current === card.mode"
        :tabindex="current === card.mode ? 0 : (current === null && card === CARDS[0] ? 0 : -1)"
        @click="onSelect(card.mode)"
        @keydown.enter.prevent="onSelect(card.mode)"
        @keydown.space.prevent="onSelect(card.mode)"
        @keydown="onArrowKey($event, card.mode)"
      >
        <div class="amc-head">
          <span class="amc-icon" v-html="cardIcons[card.mode]"></span>
          <span class="amc-title">{{ t(`settings.access.${card.mode}_title`) }}</span>
          <span v-if="card.mode === 'local'" class="amc-badge-reco">{{ t('settings.access.recommended') }}</span>
          <span v-if="current === card.mode" class="amc-badge-current">{{ t('settings.access.current') }}</span>
        </div>
        <p class="amc-tagline">{{ t(`settings.access.${card.mode}_tagline`) }}</p>
        <!-- 一行说清：谁出算力 · 花谁的钱 · 数据去哪 -->
        <div class="amc-dims">
          <span class="amc-dim"><em>{{ t('settings.access.dim_power') }}</em>{{ t(`settings.access.${card.mode}_power`) }}</span>
          <span class="amc-dim-sep">·</span>
          <span class="amc-dim"><em>{{ t('settings.access.dim_cost') }}</em>{{ t(`settings.access.${card.mode}_cost`) }}</span>
          <span class="amc-dim-sep">·</span>
          <span class="amc-dim"><em>{{ t('settings.access.dim_data') }}</em>{{ t(`settings.access.${card.mode}_data`) }}</span>
        </div>

        <!-- 卡片上下文态 / Card contextual state -->
        <div v-if="current === card.mode" class="amc-context">
          <template v-if="card.mode === 'hosted'">
            <span v-if="!userStore.isLoggedIn" class="amc-ctx-warn">
              {{ t('settings.access.login_required') }}
              <button class="btn btn-sm btn-primary amc-login-btn" @click.stop="showLogin">{{ t('settings.login') }}</button>
            </span>
            <span v-else class="amc-ctx-ok">{{ t('settings.access.quota_remaining', { n: fmtMinutes(quotaRemaining) }) }}</span>
          </template>
          <template v-else-if="card.mode === 'byok'">
            <span v-if="routing?.llm.reason === 'byok_key_missing'" class="amc-ctx-warn">{{ t('settings.access.selfkey_missing') }}</span>
            <span v-else class="amc-ctx-ok">{{ t('settings.access.selfkey_ready') }}</span>
          </template>
          <template v-else-if="card.mode === 'local'">
            <span v-if="!engineStore.status?.local_ready" class="amc-ctx-warn">{{ t('settings.access.local_pending') }}</span>
            <span v-else class="amc-ctx-ok">{{ t('settings.access.local_ready') }}</span>
          </template>
        </div>

        <!-- D3 声纹并入所属卡片折叠区（仅选中卡片展开） / Voiceprint folded into its card -->
        <details v-if="current === card.mode" class="amc-vp" @click.stop>
          <summary>{{ t('settings.access.voiceprint_collapse') }}</summary>
          <template v-if="card.mode === 'local'">
            <p class="amc-vp-note">{{ t('settings.access.voiceprint_local_note') }}</p>
          </template>
          <template v-else-if="card.mode === 'hosted'">
            <p class="amc-vp-note">{{ t('settings.access.voiceprint_hosted_note') }}</p>
          </template>
          <template v-else>
            <div class="settings-field amc-field">
              <label class="settings-label">{{ t('settings.voiceprint_provider') }}</label>
              <select v-model="settings.voiceprint!.provider" class="settings-input" @change="saveVoiceprint">
                <option value="auto">{{ t('settings.voiceprint_provider_auto') }}</option>
                <option value="local">{{ t('settings.voiceprint_provider_local') }}</option>
                <option value="cloud">{{ t('settings.voiceprint_provider_cloud') }}</option>
              </select>
            </div>
            <div v-if="settings.voiceprint?.provider === 'cloud'" class="settings-field amc-field">
              <label class="settings-label">{{ t('settings.voiceprint_cloud_base_url') }}</label>
              <input v-model="settings.voiceprint!.cloud_base_url" class="settings-input" placeholder="https://" @change="saveVoiceprint" />
            </div>
            <div v-if="settings.voiceprint?.provider === 'cloud'" class="settings-field amc-field">
              <label class="settings-label">{{ t('settings.voiceprint_cloud_api_key') }}</label>
              <input v-model="settings.voiceprint!.cloud_api_key" type="password" class="settings-input" :placeholder="t('settings.voiceprint_cloud_api_key_placeholder')" @change="saveVoiceprint" />
            </div>
          </template>
        </details>
      </div>
    </div>

    <p v-if="switchMessage" class="amc-switch-msg" :class="{ 'is-error': switchError }">{{ switchMessage }}</p>

    <!-- ═══ R1/D4 高级设置折叠区 / Advanced settings collapse ═══ -->
    <details class="amc-advanced" :open="expert">
      <summary class="amc-advanced-summary">{{ t('settings.access.advanced') }}</summary>

      <div class="wm-setting-row amc-expert-row">
        <label>
          {{ t('settings.access.expert_label') }}
          <span class="toggle-desc">{{ t('settings.access.expert_desc') }}</span>
        </label>
        <div class="wm-toggle-wrap">
          <div
            class="wm-toggle"
            :class="{ 'is-on': expert }"
            role="switch"
            :aria-checked="expert"
            tabindex="0"
            @click="onToggleExpert"
            @keydown.enter.prevent="onToggleExpert"
            @keydown.space.prevent="onToggleExpert"
          ></div>
          <span class="wm-setting-val">{{ expert ? t('settings.toggle_on') : t('settings.toggle_off') }}</span>
        </div>
      </div>

      <!-- 服务区块：离线选中时整体灰化 + 「由离线模式接管」（消除静默覆盖） -->
      <div class="amc-services" :class="{ 'is-takeover': current === 'local' }">
        <div class="amc-services-head">
          <h3 class="amc-services-title">{{ t('settings.access.services_title') }}</h3>
          <span v-if="current === 'local'" class="amc-takeover-badge">{{ t('settings.access.services_takeover') }}</span>
        </div>
        <fieldset :disabled="current === 'local' || !expert">
          <p v-if="current === 'local'" class="amc-services-note">{{ t('settings.access.services_takeover_desc') }}</p>
          <p v-else-if="!expert" class="amc-services-note">{{ t('settings.access.services_expert_hint') }}</p>
          <template v-else>
            <!-- LLM 底层参数（与「服务」分类共享同一 settings 引用，改动互为可见） -->
            <div class="settings-field amc-field">
              <label class="settings-label">{{ t('settings.llm_service') }} · {{ t('settings.llm_base_url') }}</label>
              <input v-model="settings.llm!.base_url" class="settings-input" @change="saveServices" />
            </div>
            <div class="settings-field amc-field">
              <label class="settings-label">{{ t('settings.llm_model') }}</label>
              <input v-model="settings.llm!.model" class="settings-input" placeholder="qwen-plus" @change="saveServices" />
            </div>
            <div class="settings-field amc-field">
              <label class="settings-label">{{ t('settings.llm_api_key_placeholder') }}</label>
              <input v-model="settings.llm!.api_key" type="password" class="settings-input" :placeholder="t('settings.api_key_placeholder')" @change="saveServices" />
            </div>
            <div class="settings-field amc-field">
              <label class="settings-label">{{ t('settings.asr_service') }} · {{ t('settings.asr_model') }}</label>
              <input v-model="settings.asr!.model" class="settings-input" placeholder="paraformer-v2" @change="saveServices" />
            </div>
            <div class="settings-field amc-field">
              <label class="settings-label">{{ t('settings.asr_api_key_placeholder') }}</label>
              <input v-model="settings.asr!.api_key" type="password" class="settings-input" :placeholder="t('settings.api_key_placeholder')" @change="saveServices" />
            </div>
          </template>
        </fieldset>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * 接入方式三卡片（REQ-ACCESS-MODE-CARDS T3/T4 · AM-F1）
 * R1 三选一卡片 + R4 引导头 + D3 声纹折叠区 + D4 专家模式开关 + 服务区块离线灰化。
 * access_mode/expert_mode 读写走 api/access.ts（AM-B1 契约 §13，mock 先行）。
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEngineStore } from '@/stores/engine'
import { useUserStore } from '@/stores/user'
import { saveSettings, type Settings } from '@/api/settings'
import type { AccessMode } from '@/api/access'

const props = defineProps<{ settings: Settings }>()
const emit = defineEmits<{ (e: 'local-selected'): void; (e: 'expert-changed', on: boolean): void }>()

const { t } = useI18n()
const engineStore = useEngineStore()
const userStore = useUserStore()

const CARDS: { mode: AccessMode }[] = [{ mode: 'local' }, { mode: 'hosted' }, { mode: 'byok' }]

const cardIcons = computed<Record<AccessMode, string>>(() => ({
  local: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="12" rx="2"/><path d="M8 20h8"/><path d="M12 16v4"/><path d="M7 10l3 3 5-5"/></svg>',
  hosted: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>',
  byok: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>',
}))

const current = computed(() => engineStore.accessMode)
const expert = computed(() => engineStore.expertMode)
const onboarding = computed(() => engineStore.onboardingRequired && !userStore.isLoggedIn)
const routing = computed(() => engineStore.routing)
const quotaRemaining = computed(() => engineStore.quotaRemaining)

const busy = ref(false)
const switchMessage = ref('')
const switchError = ref(false)

function fmtMinutes(min: number | null): string {
  if (min == null) return '—'
  if (min >= 60) {
    const h = Math.floor(min / 60)
    const m = Math.round(min % 60)
    return m > 0 ? `${h}h${m}m` : `${h}h`
  }
  return `${Math.round(min)}m`
}

async function onSelect(mode: AccessMode) {
  if (busy.value || current.value === mode) return
  busy.value = true
  switchMessage.value = ''
  try {
    await engineStore.applyAccess({ access_mode: mode })
    switchMessage.value = t(`settings.access.saved_${mode}`)
    switchError.value = false
    if (mode === 'local') emit('local-selected')
  } catch (e) {
    switchMessage.value = t('settings.access.save_failed')
    switchError.value = true
    console.error('[access] switch failed:', e)
  } finally {
    busy.value = false
  }
}

/** 卡片 ←→ 方向键导航（radiogroup 键盘语义） / Arrow-key navigation within the radiogroup */
function onArrowKey(e: KeyboardEvent, mode: AccessMode) {
  if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
  e.preventDefault()
  const idx = CARDS.findIndex(c => c.mode === mode)
  const next = CARDS[(idx + (e.key === 'ArrowRight' ? 1 : CARDS.length - 1)) % CARDS.length]
  void onSelect(next.mode)
  ;(e.currentTarget as HTMLElement | null)?.focus?.()
}

async function onToggleExpert() {
  if (busy.value) return
  busy.value = true
  const next = !expert.value
  try {
    await engineStore.applyAccess({ expert_mode: next })
    emit('expert-changed', next)
  } catch (e) {
    console.error('[access] expert toggle failed:', e)
  } finally {
    busy.value = false
  }
}

async function saveVoiceprint() {
  try {
    await saveSettings({ voiceprint: { ...props.settings.voiceprint } })
  } catch (e) {
    console.error('[access] save voiceprint failed:', e)
  }
}

async function saveServices() {
  try {
    await saveSettings({ llm: { ...props.settings.llm }, asr: { ...props.settings.asr } })
  } catch (e) {
    console.error('[access] save services failed:', e)
  }
}

function showLogin() {
  window.dispatchEvent(new CustomEvent('oms:show-login'))
}
</script>

<style scoped>
.access-cards { display: flex; flex-direction: column; gap: var(--s-4); }

/* ─── 引导头 / Guide header ─── */
.access-guide { border: 1px solid var(--accent-mid); background: var(--accent-soft); border-radius: var(--radius); padding: var(--s-4) var(--s-5); }
.access-guide-title { font-size: 15px; font-weight: 600; margin: 0 0 4px; color: var(--accent); }
.access-guide-desc { font-size: 12px; color: var(--muted); margin: 0; }

/* ─── 三卡片 / Cards ─── */
.amc-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--s-3); }
.amc-card { position: relative; border: 1.5px solid var(--border); border-radius: var(--radius); padding: var(--s-4); cursor: pointer; background: var(--surface); transition: border-color 0.15s, background 0.15s, box-shadow 0.15s; }
.amc-card:hover { border-color: var(--border-strong); }
.amc-card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.amc-card.is-selected { border-color: var(--accent); background: var(--accent-soft); box-shadow: 0 0 0 1px var(--accent-mid); }
.amc-card.is-busy { opacity: 0.6; pointer-events: none; }
.amc-head { display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; }
.amc-icon :deep(svg) { width: 18px; height: 18px; color: var(--accent); display: block; }
.amc-title { font-size: 14px; font-weight: 600; }
.amc-badge-reco { font-size: 10px; color: var(--ok); background: var(--ok-soft); border: 1px solid oklch(from var(--ok) l c h / 0.25); padding: 1px 7px; border-radius: 999px; }
.amc-badge-current { font-size: 10px; color: var(--accent); background: var(--surface); border: 1px solid var(--accent-mid); padding: 1px 7px; border-radius: 999px; }
.amc-tagline { font-size: 12px; color: var(--muted); margin: var(--s-2) 0 0; line-height: 1.5; }
.amc-dims { display: flex; align-items: baseline; gap: 4px; flex-wrap: wrap; margin-top: var(--s-3); font-size: 11px; color: var(--subtle); }
.amc-dim em { font-style: normal; font-weight: 600; color: var(--muted); margin-right: 3px; }
.amc-dim-sep { color: var(--border-strong); }
.amc-context { margin-top: var(--s-3); padding-top: var(--s-2); border-top: 1px dashed var(--border); font-size: 12px; }
.amc-ctx-ok { color: var(--ok); font-weight: 500; }
.amc-ctx-warn { color: var(--warn); display: inline-flex; align-items: center; gap: var(--s-2); }
.amc-login-btn { padding: 0 12px; height: 26px; font-size: 12px; }

/* 声纹折叠区 / Voiceprint collapse (D3) */
.amc-vp { margin-top: var(--s-2); font-size: 12px; }
.amc-vp summary { cursor: pointer; color: var(--muted); font-size: 11px; padding: 2px 0; user-select: none; }
.amc-vp-note { color: var(--subtle); margin: 6px 0 0; line-height: 1.5; }
.amc-field { margin: var(--s-2) 0 0; }
.amc-field .settings-input { max-width: 100%; font-size: 12px; }

.amc-switch-msg { font-size: 12px; color: var(--accent); margin: 0; font-weight: 500; }
.amc-switch-msg.is-error { color: var(--error); }

/* ─── 高级设置 / Advanced ─── */
.amc-advanced { border: 1px solid var(--border); border-radius: var(--radius); padding: 0 var(--s-4) var(--s-2); }
.amc-advanced > summary { cursor: pointer; font-size: 13px; font-weight: 600; color: var(--muted); padding: var(--s-3) 0; user-select: none; list-style: none; }
.amc-advanced > summary::-webkit-details-marker { display: none; }
.amc-advanced > summary::before { content: '▸'; display: inline-block; margin-right: 6px; transition: transform 0.15s; }
.amc-advanced[open] > summary::before { transform: rotate(90deg); }
.amc-expert-row { padding: var(--s-2) 0 var(--s-4); border-bottom: 1px solid var(--border); }

.amc-services { margin-top: var(--s-4); transition: opacity 0.2s; }
.amc-services fieldset { border: none; padding: 0; margin: 0; min-width: 0; }
.amc-services-head { display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; margin-bottom: var(--s-2); }
.amc-services-title { font-size: 13px; font-weight: 600; margin: 0; }
.amc-services-note { font-size: 12px; color: var(--muted); margin: 0 0 var(--s-2); }
/* 离线接管：整块灰化 + 标注（R1 消除静默覆盖） */
.amc-services.is-takeover { opacity: 0.45; }
.amc-takeover-badge { font-size: 11px; font-weight: 600; color: var(--warn); background: var(--warn-soft); border: 1px solid oklch(from var(--warn) l c h / 0.3); padding: 1px 8px; border-radius: 999px; }
</style>
