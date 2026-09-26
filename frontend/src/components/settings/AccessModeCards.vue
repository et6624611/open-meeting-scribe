<template>
  <div class="access-ia" :class="{ 'is-expert': expert }">
    <!-- ═══ 专家详情开关（页面级；移出决策卡容器，不参与三选一）/ Page-level expert switch ═══ -->
    <div class="ai-expert-row">
      <div class="ai-expert-labels">
        <span class="ai-expert-label">{{ t('settings.access.expert_toggle') }}</span>
        <span class="ai-expert-desc">{{ t('settings.access.expert_toggle_desc') }}</span>
      </div>
      <div
        class="ai-sw"
        :class="{ 'is-on': expert }"
        role="switch"
        :aria-checked="expert"
        tabindex="0"
        @click="onToggleExpert"
        @keydown.enter.prevent="onToggleExpert"
        @keydown.space.prevent="onToggleExpert"
      ></div>
    </div>

    <!-- ═══ L2 页面级横幅（amber，不用红；可折叠为历史行）/ Page-level quota banner ═══ -->
    <div v-if="bannerVisible" class="ai-banner" :class="{ 'is-collapsed': !bannerOpen }">
      <div class="ai-banner-main">
        <span class="ai-banner-icon" aria-hidden="true">⚠</span>
        <span v-if="autoSwitch.count > 0" class="ai-banner-text">{{ t('settings.access.quota_banner', { n: autoSwitch.count }) }}</span>
        <span v-else class="ai-banner-text">{{ t('settings.access.quota_low_banner', { n: fmtMinutes(quotaRemaining) }) }}</span>
        <button class="ai-banner-toggle" @click="bannerOpen = !bannerOpen">
          {{ bannerOpen ? t('settings.access.quota_banner_collapse') : t('settings.access.quota_banner_expand') }}
        </button>
      </div>
      <div v-if="bannerOpen && recentEvents.length" class="ai-banner-history">
        {{ t('settings.access.quota_banner_history', { n: recentEvents.length }) }}
      </div>
    </div>

    <!-- ═══ 未选态强引导条 / Mandatory-choice guide banner ═══ -->
    <div v-if="unselected" class="ai-guide">
      <h2 class="ai-guide-title">{{ t('settings.access.guide_title') }}</h2>
      <p class="ai-guide-desc">{{ t('settings.access.guide_desc', { hint: userStore.isLoggedIn ? t('settings.access.guide_hint_ready') : t('settings.access.guide_hint_login') }) }}</p>
    </div>

    <!-- ═══ 决策层两卡（离线 / 联网）：access_mode 唯一写入口 / Decision cards ═══ -->
    <div class="ai-cards" role="radiogroup" :aria-label="t('settings.cat_access')">
      <div
        ref="localCardEl"
        class="ai-card"
        :class="{ 'is-selected': accessMode === 'local', 'is-busy': busy }"
        role="radio"
        :aria-checked="accessMode === 'local'"
        :tabindex="roving('local')"
        @click="onSelect('local')"
        @keydown.enter.prevent="onSelect('local')"
        @keydown.space.prevent="onSelect('local')"
        @keydown="onArrowKey($event, 'local')"
      >
        <div class="ai-card-head">
          <span class="ai-card-icon" v-html="localIcon"></span>
          <span class="ai-card-title">{{ t('settings.access.local_title') }}</span>
          <span v-if="accessMode === 'local'" class="ai-badge ai-badge-current">{{ t('settings.access.current') }}</span>
        </div>
        <p class="ai-card-tagline">{{ t('settings.access.local_tagline') }}</p>
        <p v-if="expert" class="ai-tech">engine.mode ▸ local · asr.mode ▸ local</p>
        <!-- 离线就绪前置回显（EXPERT-MODE §2.2 的 L3 判定基础，本单先行落位） -->
        <div v-if="accessMode === 'local' && !localReady" class="ai-card-ctx is-warn">
          {{ t('topbar.engine_badge_unready') }}
          <button class="ai-btn-sm" @click.stop="emit('goto', 'engine')">{{ t('settings.access.engine_goto') }}</button>
        </div>
      </div>
      <div
        ref="cloudCardEl"
        class="ai-card"
        :class="{ 'is-selected': accessMode === 'cloud', 'is-busy': busy }"
        role="radio"
        :aria-checked="accessMode === 'cloud'"
        :tabindex="roving('cloud')"
        @click="onSelect('cloud')"
        @keydown.enter.prevent="onSelect('cloud')"
        @keydown.space.prevent="onSelect('cloud')"
        @keydown="onArrowKey($event, 'cloud')"
      >
        <div class="ai-card-head">
          <span class="ai-card-icon" v-html="cloudIcon"></span>
          <span class="ai-card-title">{{ t('settings.access.cloud_title') }}</span>
          <span v-if="!userStore.isLoggedIn" class="ai-badge ai-badge-login">{{ t('settings.access.cloud_login_hint') }}</span>
          <span v-if="accessMode === 'cloud'" class="ai-badge ai-badge-current">{{ t('settings.access.current') }}</span>
          <!-- L3 顶层卡角标：N 项能力已自动改用 -->
          <span v-if="accessMode === 'cloud' && autoSwitch.count > 0" class="ai-badge ai-badge-switch">{{ t('settings.access.auto_switch_badge', { n: autoSwitch.count }) }}</span>
        </div>
        <p class="ai-card-tagline">{{ t('settings.access.cloud_tagline') }}</p>
        <p v-if="expert" class="ai-tech">llm/asr 各自 ▸ proxy | direct | local-ep</p>
      </div>
    </div>

    <p v-if="switchMessage" class="ai-msg" :class="msgKind === 'error' ? 'is-error' : msgKind === 'ok' ? 'is-ok' : ''">{{ switchMessage }}</p>

    <!-- ═══ 从属详情层（六卡，缩进 + 引用轨与决策层两层分离）/ Detail layer ═══ -->
    <h3 class="ai-detail-title">{{ t('settings.access.detail_title') }}</h3>
    <div class="ai-detail-layer">
      <div class="ai-detail-grid">
        <!-- ① 账户 · 套餐 -->
        <div ref="acctCardEl" class="ai-subcard">
          <h4 class="ai-subcard-title">{{ t('settings.access.acct_title') }}</h4>
          <p v-if="expert" class="ai-tech">account.tier ▸ {{ tierLabel }} · prefer_subscription ▸ {{ psub ? 'true' : 'false' }}</p>
          <div class="ai-acct-row">
            <span class="ai-tier-badge">{{ tierLabel }}</span>
            <span v-if="userStore.isLoggedIn" class="ai-muted">{{ t('settings.access.acct_logged_in') }}</span>
            <button v-else class="ai-btn-sm ai-btn-primary" @click="showLogin">{{ t('settings.login') }}</button>
          </div>
          <p v-if="quotaRemaining != null" class="ai-quota">{{ t('settings.access.acct_quota_left', { n: Math.round(quotaRemaining) }) }}</p>
          <div class="ai-psub-row" :class="{ 'is-idle': offline }">
            <div
              class="ai-sw ai-sw-sm"
              :class="{ 'is-on': psub, 'is-disabled': offline }"
              role="switch"
              :aria-checked="psub"
              :tabindex="offline ? -1 : 0"
              @click="onTogglePsub"
              @keydown.enter.prevent="onTogglePsub"
              @keydown.space.prevent="onTogglePsub"
            ></div>
            <span class="ai-psub-label">{{ offline ? t('settings.access.acct_psub_idle') : t('settings.access.acct_psub') }}</span>
          </div>
          <p class="ai-note">{{ psub ? t('settings.access.acct_psub_note_on') : t('settings.access.acct_psub_note_off') }}</p>
        </div>

        <!-- ② LLM · 算力来源 -->
        <div ref="llmCardEl" class="ai-subcard" :class="{ 'is-inherited': offline }">
          <h4 class="ai-subcard-title">
            {{ t('settings.access.llm_title') }}
            <span
              v-if="badgeFor('llm')"
              class="ai-badge-src"
              :class="`is-${badgeFor('llm')}`"
              :title="badgeFor('llm') === 'override' ? t('settings.access.badge_override_tip') : t('settings.access.badge_default_tip')"
              @click="jumpToAcct"
            >{{ t(`settings.access.badge_${badgeFor('llm')}`) }}</span>
          </h4>
          <p v-if="expert" class="ai-tech">llm.provider ▸ preset · chat_engine.auth_tier ▸ {{ chatEngineStatus?.config?.auth_tier || 'readonly' }}</p>
          <select class="ai-select" :disabled="offline" :value="capability?.llm?.effective || ''" @change="onSourceChange('llm', ($event.target as HTMLSelectElement).value)">
            <option value="trial">{{ t('settings.access.src_trial') }}</option>
            <option value="byok">{{ t('settings.access.src_byok') }}</option>
            <option value="local_endpoint">{{ t('settings.access.src_local_ep') }}</option>
          </select>
          <p class="ai-ready" :class="readyClass('llm')" v-html="readyHtml('llm')"></p>
          <p class="ai-note">{{ billingText('llm') }}</p>
          <p class="ai-edit-track">
            <template v-if="settings.llm?.api_key">{{ t('settings.access.edit_track_key', { key: settings.llm.api_key }) }}</template>
            <button class="ai-btn-sm" @click="emit('goto', 'services')">{{ t('settings.access.edit_in_services') }}</button>
          </p>
        </div>

        <!-- ③ ASR · 算力来源 -->
        <div ref="asrCardEl" class="ai-subcard" :class="{ 'is-inherited': offline }">
          <h4 class="ai-subcard-title">
            {{ t('settings.access.asr_title') }}
            <span
              v-if="badgeFor('asr')"
              class="ai-badge-src"
              :class="`is-${badgeFor('asr')}`"
              :title="badgeFor('asr') === 'override' ? t('settings.access.badge_override_tip') : t('settings.access.badge_default_tip')"
              @click="jumpToAcct"
            >{{ t(`settings.access.badge_${badgeFor('asr')}`) }}</span>
          </h4>
          <p v-if="expert" class="ai-tech">asr.mode ▸ proxy | direct · model ▸ {{ settings.asr?.model || 'paraformer-v2' }}</p>
          <select class="ai-select" :disabled="offline" :value="capability?.asr?.effective || ''" @change="onSourceChange('asr', ($event.target as HTMLSelectElement).value)">
            <option value="trial">{{ t('settings.access.src_trial') }}</option>
            <option value="byok">{{ t('settings.access.src_byok') }}</option>
          </select>
          <p class="ai-ready" :class="readyClass('asr')" v-html="readyHtml('asr')"></p>
          <p class="ai-note">{{ billingText('asr') }}</p>
          <p class="ai-edit-track">
            <button class="ai-btn-sm" @click="emit('goto', 'services')">{{ t('settings.access.edit_in_services') }}</button>
          </p>
          <p class="ai-vp-note">▸ {{ t('settings.access.vp_note') }}</p>
        </div>

        <!-- ④ 引擎 · 本地组件 -->
        <div class="ai-subcard">
          <h4 class="ai-subcard-title">{{ t('settings.access.engine_title') }}</h4>
          <p v-if="expert" class="ai-tech">engine.local_ready ▸ {{ localReady ? 'true' : 'false' }}</p>
          <p><span class="ai-ro-badge">local_ready: <b :class="localReady ? 'is-ok' : 'is-warn'">{{ localReady ? t('settings.access.engine_ready') : t('settings.access.engine_missing') }}</b></span></p>
          <p class="ai-note">{{ t('settings.access.engine_note') }} <button class="ai-btn-sm" @click="emit('goto', 'engine')">{{ t('settings.access.engine_goto') }}</button></p>
        </div>

        <!-- ⑤ CLI 引擎（正交栈，探针三段状态常驻回显：①路径→②版本→③登录）-->
        <div class="ai-subcard">
          <h4 class="ai-subcard-title">{{ t('settings.access.cli_title') }}</h4>
          <p v-if="expert" class="ai-tech">chat_engine ▸ {{ chatEngineStatus?.config?.engine_id || '—' }} · auth_tier={{ chatEngineStatus?.config?.auth_tier || 'readonly' }}</p>
          <p>
            <span class="ai-ro-badge">{{ chatEngineStatus?.probe?.display_name || chatEngineStatus?.config?.engine_id || '—' }}</span>
            <span class="ai-probe-stage" :class="probeStageClass('path')">①</span>
            <span class="ai-probe-stage" :class="probeStageClass('version')">②</span>
            <span class="ai-probe-stage" :class="probeStageClass('login')">③</span>
            <span v-if="chatEngineStatus?.probe?.available" class="ai-ok-txt" style="font-size:12px">{{ t('settings.access.cli_installed') }} {{ t('settings.access.cli_logged_in') }}</span>
            <span v-else-if="chatEngineStatus?.probe" class="ai-warn-txt" style="font-size:12px">{{ probeFailedText }}</span>
          </p>
          <p><span class="ai-ro-badge">{{ t('settings.access.cli_tier', { tier: tierNameToUser(chatEngineStatus?.config?.auth_tier) }) }}</span></p>
          <p class="ai-note">{{ t('settings.access.cli_note') }}</p>
        </div>

        <!-- ⑥ 使用面回显 · 对话模型（随对话面板选择器联动，REQ-EXPERT-MODE §2.3） -->
        <div class="ai-subcard">
          <h4 class="ai-subcard-title">{{ t('settings.access.usage_title') }}</h4>
          <p v-if="expert" class="ai-tech">chat.model ▸ per-message override</p>
          <p>
            <span class="ai-ro-badge">{{ engineStore.sessionModel ? `${t('settings.access.usage_title')}: ${engineStore.sessionModel}` : t('settings.access.usage_follow') }}</span>
            <span class="ai-ro-badge">{{ unselected ? t('settings.access.usage_src_none') : t('settings.access.usage_src', { src: usageSrcText }) }}</span>
          </p>
          <p class="ai-note">{{ t('settings.access.usage_note') }}</p>
        </div>
      </div>
    </div>

    <!-- ═══ 数据流向矩阵（已搬到接入方式页；专家详情开启时显示）/ Flow matrix ═══ -->
    <section v-if="expert" class="ai-matrix-section">
      <h3 class="ai-detail-title">{{ t('settings.access.matrix_title') }}</h3>
      <p class="ai-note">{{ t('settings.access.matrix_desc') }}</p>
      <table class="ai-matrix">
        <thead>
          <tr>
            <th>{{ t('settings.access.matrix_corner') }}</th>
            <th
              v-for="col in MATRIX_COLS"
              :key="col.key"
              :class="{ 'is-cur': matrixColIsCurrent(col.key) }"
            >
              {{ t(`settings.access.matrix_col_${col.key}`) }}
              <span v-if="expert" class="ai-matrix-tech">{{ col.tech }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in MATRIX_ROWS" :key="row">
            <th>{{ t(`settings.access.matrix_row_${row}`) }}</th>
            <td
              v-for="col in MATRIX_COLS"
              :key="col.key"
              :class="{ 'is-cur': matrixRowColIs(row, col.key) }"
            >
              <template v-if="matrixCellText(row, col.key) === 'na'">{{ t('settings.access.mx_na') }}</template>
              <template v-else>
                {{ matrixCellText(row, col.key) }}
                <span v-if="matrixCellOutbound(row, col.key) === 'out'" class="ai-mx-badge is-out">{{ t('settings.access.mx_out') }}</span>
                <span v-else-if="matrixCellOutbound(row, col.key) === 'zero'" class="ai-mx-badge is-zero">{{ t('settings.access.mx_zero') }}</span>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="ai-note">{{ t('settings.access.matrix_note') }}</p>
    </section>

    <!-- ═══ 切换后果预览弹窗 / Consequence preview modal ═══ -->
    <Teleport to="body">
      <div v-if="pending" class="ai-modal-mask" @click.self="closePreview">
        <div class="ai-modal" role="dialog" aria-modal="true" :aria-label="t('settings.access.preview_title', { mode: modeLabel(pending) })">
          <h3 class="ai-modal-title">{{ t('settings.access.preview_title', { mode: modeLabel(pending) }) }}</h3>
          <details class="ai-modal-fields" :open="expert">
            <summary>{{ t('settings.access.preview_fields', { detail: expert ? t('settings.access.preview_fields_detail_on') : t('settings.access.preview_fields_detail_off') }) }}</summary>
            <table class="ai-modal-table">
              <thead><tr><th>{{ t('settings.access.preview_col_field') }}</th><th>{{ t('settings.access.preview_col_now') }}</th><th>{{ t('settings.access.preview_col_next') }}</th></tr></thead>
              <tbody>
                <tr v-for="row in previewRows" :key="row.field">
                  <td><code class="ai-k">{{ row.field }}</code></td>
                  <td>{{ row.now }}</td>
                  <td><b>{{ row.next }}</b></td>
                </tr>
              </tbody>
            </table>
          </details>
          <ul class="ai-modal-list">
            <li v-html="previewProcess"></li>
            <li v-if="previewRisk" class="is-risk" v-html="previewRisk"></li>
            <li v-html="previewBilling"></li>
            <li v-html="previewDefaultNote"></li>
          </ul>
          <label v-if="previewRisk" class="ai-modal-ack">
            <input type="checkbox" v-model="ackChecked" />
            {{ t('settings.access.preview_ack_local') }}
          </label>
          <div class="ai-modal-acts">
            <button ref="cancelBtnEl" class="ai-btn" @click="closePreview">{{ t('settings.access.preview_cancel') }}</button>
            <button class="ai-btn ai-btn-primary" :disabled="!!(pending && previewRisk) && !ackChecked" @click="confirmPick">
              {{ pending === 'local' ? t('settings.access.preview_confirm_local') : t('settings.access.preview_confirm_cloud') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
/**
 * 接入方式：决策层两卡 + 从属详情层 + 后果预览（REQ-SETTINGS-IA v0.2.0）
 *
 * - access_mode 唯一写入口 = 本组件决策卡（切换必经后果预览 + POST /api/settings/access-mode 事务，
 *   任一环节失败全量回滚「未生效，已保持原模式」——裁决-1）。
 * - 逐能力算力来源（体验配额/自带 Key/本机端点）在详情层选择，任何手动改选持久化覆盖不被勾选改回；
 *   账户「优先使用体验」勾选只决定未覆盖能力的默认值（第 5 刀，静默 route_override 语义消灭）。
 * - 旧「卡片内联自动保存面板」与声纹 provider 选择器已废除（第 2/4 刀）；参数编辑面唯一收敛到「服务」页。
 * - 专家详情为页面级 switch（移出 radiogroup），开启后卡片/详情卡/矩阵显示工程值注释行与流向矩阵。
 * - 词汇 = 裁决-4 五词：离线 / 联网 / 体验配额 / 自带 Key / 本机端点（proxy/direct 仅专家注释）。
 * - 无障碍（裁决-5）：状态文字 ≥12px；色 + 文字 + 符号三通道，不单靠颜色。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEngineStore } from '@/stores/engine'
import { useUserStore } from '@/stores/user'
import { saveCapabilitySource, type AccessMode, type CapSource } from '@/api/access'
import { fetchChatEngineStatus, type ChatEngineStatus, type Settings } from '@/api/settings'
import { updateUserPrefs } from '@/api/usage'

const props = defineProps<{ settings: Settings }>()
const emit = defineEmits<{
  (e: 'goto', category: 'services' | 'engine'): void
  (e: 'guide-request', errorCode?: string | null): void
}>()

const { t } = useI18n()
const engineStore = useEngineStore()
const userStore = useUserStore()

// ─── 单源派生态（stores/engine.ts / routing 单一数据源，禁止本组件自判状态） ───
const accessMode = computed<AccessMode | null>(() => engineStore.accessMode)
const expert = computed(() => engineStore.expertMode)
const capability = computed(() => engineStore.capability)
const routing = computed(() => engineStore.routing)
const autoSwitch = computed(() => engineStore.autoSwitch)
const recentEvents = computed(() => routing.value?.recent_events ?? [])
const quotaRemaining = computed(() => engineStore.quotaRemaining)
const quotaWarning = computed(() => routing.value?.quota_warning ?? null)
const offline = computed(() => accessMode.value === 'local')
const unselected = computed(() => accessMode.value === null)
const localReady = computed(() => engineStore.status?.local_ready === true)
const tierLabel = computed(() => props.settings.diarization?.subscription_tier || 'free')

const localIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="12" rx="2"/><path d="M8 20h8"/><path d="M12 16v4"/><path d="M7 10l3 3 5-5"/></svg>'
const cloudIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>'

// ─── 消息条（非阻断 inline；点当前卡不再静默早退） ───
const busy = ref(false)
const switchMessage = ref('')
const msgKind = ref<'info' | 'ok' | 'error'>('info')
let msgTimer: ReturnType<typeof setTimeout> | null = null
function msg(kind: 'info' | 'ok' | 'error', text: string) {
  msgKind.value = kind
  switchMessage.value = text
  if (msgTimer) clearTimeout(msgTimer)
  msgTimer = setTimeout(() => { switchMessage.value = '' }, 8000)
}

// ─── 专家详情开关（页面级） ───
async function onToggleExpert() {
  const next = !expert.value
  try {
    await engineStore.applyExpertMode(next)
  } catch (e) {
    console.error('[access] expert toggle failed:', e)
    void engineStore.loadRouting(true)
  }
}

// ─── 决策卡：radiogroup 键盘（←/→ roving tabindex 两卡循环） ───
const localCardEl = ref<HTMLElement | null>(null)
const cloudCardEl = ref<HTMLElement | null>(null)
function roving(mode: AccessMode): number {
  if (accessMode.value === mode) return 0
  if (accessMode.value === null) return mode === 'local' ? 0 : -1
  return -1
}
function onArrowKey(e: KeyboardEvent, mode: AccessMode) {
  if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
  e.preventDefault()
  const target = mode === 'local' ? cloudCardEl.value : localCardEl.value
  target?.focus()
}

// ─── 切换流程：非当前卡 → 后果预览 → 事务提交（失败全量回滚） ───
const pending = ref<AccessMode | null>(null)
const ackChecked = ref(false)
const cancelBtnEl = ref<HTMLElement | null>(null)

function modeLabel(mode: AccessMode): string {
  return mode === 'local' ? t('settings.access.local_title') : t('settings.access.cloud_title')
}

function onSelect(mode: AccessMode) {
  if (busy.value) return
  if (accessMode.value === mode) {
    msg('info', t('settings.access.already_current'))
    return
  }
  pending.value = mode
  ackChecked.value = false
  nextTick(() => cancelBtnEl.value?.focus())
}
function closePreview() { pending.value = null }

async function confirmPick() {
  const target = pending.value
  if (!target) return
  pending.value = null
  busy.value = true
  try {
    await engineStore.applyAccess({ access_mode: target })
    msg('ok', t('settings.access.switch_succeeded', { mode: modeLabel(target) }))
    if (target === 'local') void engineStore.loadOverview(true)
  } catch (e) {
    const err = e as Error & { failedStage?: string; errorCode?: string | null }
    msg('error', t('settings.access.switch_failed'))
    if (err.errorCode === 'models_missing' || err.errorCode === 'insufficient_disk' || err.errorCode === 'models_tampered') {
      emit('guide-request', err.errorCode)
    }
    console.error('[access] switch failed:', e)
  } finally {
    busy.value = false
  }
}

// ESC 关闭预览
function onKeydownGlobal(e: KeyboardEvent) {
  if (e.key === 'Escape' && pending.value) closePreview()
}
onMounted(() => {
  window.addEventListener('keydown', onKeydownGlobal)
  void engineStore.loadRouting(true)
  void loadCliProbe()
})
onUnmounted(() => window.removeEventListener('keydown', onKeydownGlobal))

// ─── 预览弹窗：字段级 diff + 进程动作 + 计费与出网三段 ───
const previewRows = computed(() => {
  const target = pending.value
  if (!target) return []
  const curMode = accessMode.value === null ? t('settings.access.preview_unselected') : modeLabel(accessMode.value as AccessMode)
  const engineNow = props.settings.engine?.mode || '—'
  const asrNow = props.settings.asr?.mode || '—'
  const llmSrc = capability.value?.llm?.effective || t('settings.access.preview_unselected')
  const asrSrc = capability.value?.asr?.effective || t('settings.access.preview_unselected')
  if (target === 'local') {
    return [
      { field: 'access_mode', now: curMode, next: 'local' },
      { field: 'engine.mode', now: engineNow, next: 'local（启动本机子进程）' },
      { field: 'asr.mode', now: asrNow, next: 'local' },
      { field: 'LLM 来源', now: srcLabel(llmSrc), next: `${srcLabel(llmSrc)}（只读保留）` },
      { field: 'ASR 来源', now: srcLabel(asrSrc), next: `${srcLabel(asrSrc)}（只读保留）` },
    ]
  }
  const effDefault = capability.value?.account_default || 'trial'
  return [
    { field: 'access_mode', now: curMode, next: 'cloud' },
    { field: 'engine.mode', now: engineNow, next: '按 LLM/ASR 来源派生（proxy | direct | local-ep）' },
    { field: 'asr.mode', now: asrNow, next: '按来源派生' },
    { field: 'LLM 来源', now: srcLabel(llmSrc), next: accessMode.value === null ? `${srcLabel(effDefault)}（默认，可覆盖）` : `保持 ${srcLabel(llmSrc)}` },
    { field: 'ASR 来源', now: srcLabel(asrSrc), next: accessMode.value === null ? `${srcLabel(effDefault)}（默认，可覆盖）` : `保持 ${srcLabel(asrSrc)}` },
  ]
})
const previewProcess = computed(() => {
  const target = pending.value
  if (target === 'local') return t('settings.access.preview_proc_local')
  return t('settings.access.preview_proc_cloud')
})
/** 裁决-2：联网→离线方向追加红色风险条目 + 显式勾选知晓 */
const previewRisk = computed(() => {
  return pending.value === 'local' && accessMode.value === 'cloud' ? t('settings.access.preview_risk_to_local') : ''
})
const previewBilling = computed(() => {
  return pending.value === 'local' ? t('settings.access.preview_bill_local') : t('settings.access.preview_bill_cloud')
})
const previewDefaultNote = computed(() => {
  const effDefault = capability.value?.account_default || 'trial'
  return t('settings.access.preview_default_note', {
    state: psub.value ? t('settings.toggle_on') : t('settings.toggle_off'),
    source: srcLabel(effDefault),
    suffix: accessMode.value === null ? t('settings.access.preview_suffix_first') : t('settings.access.preview_suffix_keep'),
  })
})
function srcLabel(src: string): string {
  if (!src) return '—'
  const key = src === 'local_endpoint' ? 'src_local_ep' : src === 'local' ? 'src_local' : src === 'trial' ? 'src_trial' : 'src_byok'
  return t(`settings.access.${key}`)
}

// ─── 账户卡：登录态 / 配额 / 优先使用体验勾选（详情默认值来源，离线态置灰暂不生效） ───
const psub = ref(false)
watch(() => props.settings.prefer_subscription, (v) => { psub.value = !!v }, { immediate: true })
async function onTogglePsub() {
  if (offline.value) {
    msg('info', t('settings.access.acct_psub_idle_toast'))
    return
  }
  if (!userStore.isLoggedIn) { showLogin(); return }
  const next = !psub.value
  try {
    await updateUserPrefs({ prefer_subscription: next })
    psub.value = next
    await engineStore.loadRouting(true)
    if (next) msg('ok', t('settings.access.acct_psub_note_on'))
  } catch (e) {
    console.error('[access] toggle prefer_subscription failed:', e)
  }
}

// ─── 详情卡：逐能力来源 + 三态徽章 + L1 就绪行内常驻 ───
function badgeFor(cap: 'llm' | 'asr'): 'default' | 'override' | 'none' | 'takeover' | '' {
  if (offline.value) return 'takeover'
  if (unselected.value) return 'none'
  const c = capability.value?.[cap]
  if (!c) return ''
  return c.override ? 'override' : 'default'
}
const acctCardEl = ref<HTMLElement | null>(null)
const llmCardEl = ref<HTMLElement | null>(null)
const asrCardEl = ref<HTMLElement | null>(null)
function jumpToAcct() {
  const el = acctCardEl.value
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.classList.add('is-flash')
  setTimeout(() => el.classList.remove('is-flash'), 1200)
}

async function onSourceChange(cap: 'llm' | 'asr', value: string) {
  if (offline.value) return
  try {
    await saveCapabilitySource({ [cap]: value })
    await engineStore.loadRouting(true)
    await engineStore.loadAccessSettings()
  } catch (e) {
    console.error('[access] save capability source failed:', e)
    await engineStore.loadRouting(true)
  }
}

/** L1 能力行内常驻状态行（≥4.5:1 amber + 行内 CTA；界面禁用「降级/兜底」） */
function readyText(cap: 'llm' | 'asr'): string {
  if (offline.value) return t('settings.access.ready_takeover')
  const c = capability.value?.[cap]
  const decision = routing.value?.[cap]
  const model = cap === 'llm' ? (props.settings.llm?.model || 'qwen-plus') : (props.settings.asr?.model || 'paraformer-v2')
  const src: CapSource = (c?.effective || '') as CapSource
  if (unselected.value || !src) return '—'
  if (src === 'trial') {
    if (!userStore.isLoggedIn || decision?.reason === 'trial_requires_login') {
      return `${t('settings.access.ready_need_login')} <button class="ai-btn-sm" data-act="login">${t('settings.access.cta_login')}</button>`
    }
    if (decision?.reason === 'trial_quota_exhausted') {
      return `${t('settings.access.ready_trial_exhausted')} <button class="ai-btn-sm" data-act="usage">${t('settings.access.cta_usage')}</button> <button class="ai-btn-sm" data-act="back-trial">${t('settings.access.cta_back_trial')}</button>`
    }
    if (decision?.reason === 'trial_quota_exhausted_no_fallback') return t('settings.access.ready_trial_no_fallback')
    const left = quotaRemaining.value
    if (left != null && left <= 10) {
      return `${t('settings.access.ready_trial_low', { n: Math.round(left), model })} <button class="ai-btn-sm" data-act="services">${t('settings.access.cta_preselect')}</button>`
    }
    return t('settings.access.ready_trial', { n: left == null ? '∞' : Math.round(left), model })
  }
  if (src === 'byok') {
    const hasKey = cap === 'llm' ? !!props.settings.llm?.api_key_set : !!props.settings.asr?.api_key_set
    return hasKey
      ? t('settings.access.ready_byok_ok')
      : `${t('settings.access.ready_need_key')} <button class="ai-btn-sm" data-act="services">${t('settings.access.cta_key')}</button>`
  }
  // local_endpoint（仅 LLM）
  return t('settings.access.ready_local_ep', { model: props.settings.llm?.model || '本机模型' })
}
function readyHtml(cap: 'llm' | 'asr'): string { return readyText(cap) }
function readyClass(cap: 'llm' | 'asr'): string {
  const txt = readyText(cap)
  if (txt.startsWith('✗') || txt.startsWith('⚠') || txt.includes('已用尽')) return 'is-warn'
  if (txt.startsWith('✓')) return 'is-ok'
  return ''
}

function billingText(cap: 'llm' | 'asr'): string {
  if (offline.value) return t('settings.access.bill_none')
  const src = capability.value?.[cap]?.effective
  let text = ''
  if (src === 'trial') text = t('settings.access.bill_trial')
  else if (src === 'byok') text = t('settings.access.bill_byok')
  else if (src === 'local_endpoint') text = t('settings.access.bill_local_ep')
  else text = t('settings.access.bill_none')
  // Q4 计量口径未终裁：两条能力卡账单行标注「共用同一额度池」兜底
  if (src === 'trial') text += t('settings.access.bill_shared_pool')
  return text
}

// ─── CLI 引擎探针回显 ───
const chatEngineStatus = ref<ChatEngineStatus | null>(null)
async function loadCliProbe() {
  try { chatEngineStatus.value = await fetchChatEngineStatus() } catch { /* 静默：卡片显示占位 */ }
}
function tierNameToUser(tier?: string): string {
  if (tier === 'workspace_write') return t('common.usage.tier_workspace_write', '工作区可写')
  if (tier === 'full_task') return t('common.usage.tier_full_task', '全任务')
  return t('common.usage.tier_readonly', '只读')
}

// ─── L2 横幅 ───
const bannerOpen = ref(true)
const bannerVisible = computed(() =>
  !unselected.value && !offline.value && (autoSwitch.value.count > 0 || quotaWarning.value === 'low'))

// ─── 流向矩阵（四列 · 按能力逐行高亮 · 出网双通道徽章） ───
const MATRIX_COLS = [
  { key: 'local', tech: 'local' },
  { key: 'trial', tech: 'proxy · cloud' },
  { key: 'byok', tech: 'direct' },
  { key: 'local_ep', tech: 'local-ep' },
] as const
const MATRIX_ROWS = ['audio', 'transcript', 'voiceprint', 'llm'] as const
type MatrixCell = 'out' | 'zero' | 'na'
const MATRIX_OUTBOUND: Record<string, Record<string, MatrixCell>> = {
  audio:      { local: 'zero', trial: 'out', byok: 'out', local_ep: 'na' },
  transcript: { local: 'zero', trial: 'out', byok: 'out', local_ep: 'zero' },
  voiceprint: { local: 'zero', trial: 'zero', byok: 'zero', local_ep: 'zero' },
  llm:        { local: 'zero', trial: 'out', byok: 'out', local_ep: 'zero' },
}
function effectiveCol(cap: 'llm' | 'asr'): string {
  if (offline.value) return 'local'
  const src = capability.value?.[cap]?.effective
  if (src === 'trial') return 'trial'
  if (src === 'byok') return 'byok'
  if (src === 'local_endpoint') return 'local_ep'
  return 'local'
}
function matrixRowColIs(row: string, colKey: string): boolean {
  if (row === 'voiceprint') return colKey === 'local'  // 声纹恒亮「离线/本机」列（结构性零出网）
  if (row === 'audio') return colKey === effectiveCol('asr')
  if (row === 'llm') return colKey === effectiveCol('llm')
  if (row === 'transcript') return offline.value && colKey === 'local'
  return false
}
function matrixColIsCurrent(colKey: string): boolean {
  if (unselected.value) return false
  return matrixRowColIs('audio', colKey) || matrixRowColIs('llm', colKey) || matrixRowColIs('transcript', colKey)
}
function matrixCellText(row: string, colKey: string): string {
  const raw = t(`settings.access.matrix_cell_${row}_${colKey}`)
  return raw === 'na' ? 'na' : raw
}
function matrixCellOutbound(row: string, colKey: string): MatrixCell {
  return MATRIX_OUTBOUND[row]?.[colKey] ?? 'na'
}

/** 其它工具 */
const usageSrcText = computed(() => {
  const src = capability.value?.llm?.effective
  if (!src) return '—'
  const model = engineStore.sessionModel || props.settings.llm?.model || ''
  if (src === 'trial') return `${t('settings.access.src_trial')} · ${model}`
  if (src === 'byok') return `${t('settings.access.src_byok')} · ${model}`
  if (src === 'local_endpoint') return `${t('settings.access.src_local_ep')} · ${model}`
  return t('settings.access.src_local')
})

/** CLI 探针三段状态（①路径→②版本→③登录；前段失败后段无从探测置为未知） */
function probeStageClass(stage: 'path' | 'version' | 'login'): string {
  const p = chatEngineStatus.value?.probe
  if (!p) return 'is-unknown'
  if (p.available) return 'is-ok'
  const failed = (p as { failed_stage?: string | null }).failed_stage
  if (!failed) return stage === 'path' && p.reason === 'not_installed' ? 'is-fail' : 'is-unknown'
  const order = ['path', 'version', 'login'] as const
  const fi = order.indexOf(failed as typeof order[number])
  const si = order.indexOf(stage)
  if (si < fi) return 'is-ok'
  return si === fi ? 'is-fail' : 'is-unknown'
}
const probeFailedText = computed(() => {
  const p = chatEngineStatus.value?.probe
  if (!p) return ''
  const failed = (p as { failed_stage?: string | null }).failed_stage
  if (failed === 'version') return t('settings.access.cli_version_low')
  if (failed === 'login') return t('settings.access.cli_not_logged_in')
  return t('settings.access.cli_missing')
})
function fmtMinutes(min: number | null): string {
  if (min == null) return '—'
  return min >= 60 ? `${Math.floor(min / 60)}h${Math.round(min % 60)}m` : `${Math.round(min)}m`
}
function showLogin() {
  window.dispatchEvent(new CustomEvent('oms:show-login'))
}

// L1 行内 CTA 事件委托（v-html 内的按钮）
function onReadyClick(e: MouseEvent) {
  const btn = (e.target as HTMLElement | null)?.closest?.('[data-act]') as HTMLElement | null
  if (!btn) return
  const act = btn.dataset.act
  if (act === 'login') showLogin()
  else if (act === 'services') emit('goto', 'services')
  else if (act === 'usage') msg('info', t('settings.access.quota_banner', { n: autoSwitch.value.count }))
  else if (act === 'back-trial') void onSourceChange('llm', 'trial')
}
onMounted(() => document.addEventListener('click', onReadyClick))
onUnmounted(() => document.removeEventListener('click', onReadyClick))
</script>

<style scoped>
.access-ia { display: flex; flex-direction: column; gap: var(--s-4); }

/* ─── 专家详情开关（页面级，决策卡容器之外） ─── */
.ai-expert-row { display: flex; align-items: center; justify-content: flex-end; gap: var(--s-3); }
.ai-expert-labels { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }
.ai-expert-label { font-size: 12px; color: var(--muted); }
.ai-expert-desc { font-size: 12px; color: var(--subtle); max-width: 520px; }
.ai-sw { flex: none; width: 38px; height: 22px; border-radius: 999px; background: var(--border-strong); position: relative; cursor: pointer; transition: background .15s; }
.ai-sw::after { content: ""; position: absolute; width: 18px; height: 18px; border-radius: 50%; background: #fff; top: 2px; left: 2px; transition: left .15s; }
.ai-sw.is-on { background: var(--accent); }
.ai-sw.is-on::after { left: 18px; }
.ai-sw.is-disabled { opacity: .45; cursor: not-allowed; }
.ai-sw:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.ai-sw-sm { width: 32px; height: 18px; }
.ai-sw-sm::after { width: 14px; height: 14px; }
.ai-sw-sm.is-on::after { left: 16px; }

/* ─── L2 页面横幅（amber 不用红） ─── */
.ai-banner { border: 1px solid oklch(from var(--warn) l c h / .35); background: var(--warn-soft); color: var(--warn); border-radius: var(--radius); padding: var(--s-2) var(--s-4); font-size: 12px; }
.ai-banner-main { display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; }
.ai-banner-icon { font-size: 13px; }
.ai-banner-text { flex: 1; min-width: 200px; }
.ai-banner-toggle { border: none; background: none; color: var(--warn); font-size: 12px; cursor: pointer; text-decoration: underline; }
.ai-banner-history { margin-top: 4px; color: var(--muted); font-size: 12px; }

/* ─── 未选态强引导 ─── */
.ai-guide { border: 1px solid var(--accent-mid); background: var(--accent-soft); border-radius: var(--radius); padding: var(--s-4) var(--s-5); }
.ai-guide-title { font-size: 15px; font-weight: 600; margin: 0 0 4px; color: var(--accent); }
.ai-guide-desc { font-size: 12px; color: var(--muted); margin: 0; }

/* ─── 决策卡 ─── */
.ai-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: var(--s-3); }
.ai-card { position: relative; border: 1.5px solid var(--border); border-radius: var(--radius); padding: var(--s-4); cursor: pointer; background: var(--surface); transition: border-color .15s, background .15s; }
.ai-card:hover { border-color: var(--border-strong); }
.ai-card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.ai-card.is-selected { border-color: var(--accent); background: var(--accent-soft); }
.ai-card.is-busy { opacity: .6; pointer-events: none; }
.ai-card-head { display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; }
.ai-card-icon :deep(svg) { width: 18px; height: 18px; color: var(--accent); display: block; }
.ai-card-title { font-size: 14px; font-weight: 600; }
.ai-card-tagline { font-size: 12px; color: var(--muted); margin: var(--s-2) 0 0; line-height: 1.5; }
.ai-card-ctx { margin-top: var(--s-2); padding-top: var(--s-2); border-top: 1px dashed var(--border); font-size: 12px; display: flex; align-items: center; gap: var(--s-2); }
.ai-card-ctx.is-warn { color: var(--warn); }
.ai-badge { font-size: 12px; border-radius: 999px; padding: 1px 8px; border: 1px solid transparent; white-space: nowrap; }
.ai-badge-current { color: var(--accent); background: var(--surface); border-color: var(--accent-mid); }
.ai-badge-login { color: var(--warn); background: var(--warn-soft); border-color: oklch(from var(--warn) l c h / .3); }
.ai-badge-switch { color: var(--warn); background: var(--warn-soft); border-color: oklch(from var(--warn) l c h / .3); }

/* 工程值注释行（专家详情；等宽 + ▸ 键值对齐语法，与 .ai-note 说明文区分） */
.ai-tech { display: none; font-family: var(--font-mono); font-size: 12px; color: var(--subtle); margin: var(--s-2) 0 0; background: oklch(96% 0.005 250); border-radius: 5px; padding: 2px 8px; }
.access-ia.is-expert .ai-tech { display: block; }

.ai-msg { font-size: 12px; color: var(--accent); margin: 0; font-weight: 500; }
.ai-msg.is-error { color: var(--error); }
.ai-msg.is-ok { color: var(--ok); }

/* ─── 详情层（缩进 + 引用轨，与决策层视觉两层分离） ─── */
.ai-detail-title { font-size: 14px; font-weight: 600; margin: var(--s-2) 0 0; }
.ai-detail-layer { margin-left: var(--s-2); padding: var(--s-4); border-left: 2px solid var(--accent); background: oklch(97.5% 0.004 250); border-radius: 0 var(--radius) var(--radius) 0; }
.ai-detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: var(--s-3); }
.ai-subcard { border: 1px solid var(--border); border-radius: var(--radius); padding: var(--s-3) var(--s-4); background: var(--surface); }
.ai-subcard.is-inherited { opacity: .62; }
.ai-subcard.is-flash { animation: ai-fadeflash 1s ease-out; }
@keyframes ai-fadeflash { 0% { background: var(--warn-soft); } 100% { background: var(--surface); } }
.ai-subcard-title { margin: 0 0 6px; font-size: 13px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.ai-select { width: 100%; font-size: 12px; padding: 5px 8px; border: 1px solid var(--border-strong); border-radius: 6px; background: #fff; color: var(--text); }
.ai-select:disabled { background: oklch(95% 0.005 250); }

/* 三态徽章（默认生效/已覆盖/未设置/本机接管；色+文字双通道不单靠颜色） */
.ai-badge-src { font-size: 12px; border-radius: 999px; padding: 1px 8px; border: 1px solid transparent; cursor: pointer; }
.ai-badge-src.is-default { color: var(--accent); background: var(--accent-soft); border-color: var(--accent-mid); }
.ai-badge-src.is-override { color: oklch(40% 0.12 250); background: oklch(93% 0.03 250); border-color: oklch(75% 0.08 250); }
.ai-badge-src.is-none, .ai-badge-src.is-takeover { color: var(--muted); background: oklch(94% 0.005 250); border-color: var(--border-strong); }

/* L1 行内常驻状态行（≥12px，amber 对比度 ≥4.5:1） */
.ai-ready { font-size: 12px; margin: 6px 0 0; line-height: 1.5; min-height: 18px; }
.ai-ready.is-ok { color: var(--ok); }
.ai-ready.is-warn { color: var(--warn); font-weight: 500; }
.ai-note { font-size: 12px; color: var(--subtle); margin: 6px 0 0; line-height: 1.5; }
.ai-edit-track { font-size: 12px; color: var(--muted); border-top: 1px dashed var(--border); margin: 8px 0 0; padding-top: 8px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.ai-vp-note { font-size: 12px; color: var(--subtle); border-top: 1px dashed var(--border); margin: 8px 0 0; padding-top: 8px; }
.ai-k { font-family: var(--font-mono); font-size: 12px; background: oklch(94% 0.005 250); border-radius: 4px; padding: 0 5px; }
.ai-ro-badge { display: inline-block; font-size: 12px; font-family: var(--font-mono); background: oklch(94% 0.005 250); border-radius: 5px; padding: 1px 7px; margin: 2px 4px 2px 0; }
.ai-ok-txt { color: var(--ok); font-weight: 600; }
.ai-warn-txt { color: var(--warn); font-weight: 600; }
.ai-probe-stage { display: inline-block; font-size: 12px; border: 1px solid var(--border); border-radius: 4px; padding: 0 5px; margin-right: 3px; color: var(--muted); }
.ai-probe-stage.is-ok { border-color: oklch(from var(--ok) l c h / .45); color: var(--ok); }
.ai-probe-stage.is-fail { border-color: oklch(from var(--warn) l c h / .55); color: var(--warn); font-weight: 700; }
.ai-probe-stage.is-unknown { opacity: .5; }
.ai-muted { font-size: 12px; color: var(--muted); }
.ai-acct-row { display: flex; align-items: center; gap: 8px; font-size: 12px; margin-bottom: 6px; }
.ai-tier-badge { background: var(--accent-soft); color: var(--accent); border-radius: 999px; padding: 1px 10px; font-size: 12px; }
.ai-quota { font-size: 12px; color: var(--muted); margin: 0 0 6px; }
.ai-psub-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.ai-psub-row.is-idle .ai-psub-label { color: var(--subtle); }
.ai-psub-label { font-size: 12px; }
.ai-btn-sm { padding: 2px 10px; font-size: 12px; border-radius: 6px; border: 1px solid var(--border-strong); background: var(--surface); color: var(--text); cursor: pointer; }
.ai-btn-sm:hover { border-color: var(--accent); color: var(--accent); }
.ai-btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }

/* ─── 流向矩阵 ─── */
.ai-matrix-section { margin-top: var(--s-2); }
.ai-matrix { border-collapse: collapse; width: 100%; font-size: 12px; margin-top: 8px; }
.ai-matrix th, .ai-matrix td { border: 1px solid var(--border); padding: 6px 9px; text-align: left; vertical-align: top; }
.ai-matrix th { background: oklch(95% 0.005 250); font-size: 12px; }
.ai-matrix th.is-cur { background: var(--accent); color: #fff; }
.ai-matrix td.is-cur { background: var(--accent-soft); }
.ai-matrix-tech { display: block; font-weight: 400; font-size: 12px; font-family: var(--font-mono); opacity: .85; }
.ai-mx-badge { font-size: 12px; border-radius: 3px; padding: 0 4px; margin-left: 4px; white-space: nowrap; }
.ai-mx-badge.is-out { color: var(--warn); border: 1px solid var(--warn); }
.ai-mx-badge.is-zero { color: var(--ok); border: 1px solid var(--ok); }

/* ─── 后果预览弹窗 ─── */
.ai-modal-mask { position: fixed; inset: 0; background: rgba(20, 26, 36, .45); display: flex; align-items: center; justify-content: center; z-index: 50; }
.ai-modal { background: var(--surface); border-radius: 12px; max-width: 520px; width: 92%; padding: var(--s-5); max-height: 86vh; overflow: auto; }
.ai-modal-title { margin: 0 0 10px; font-size: 15px; }
.ai-modal-fields { font-size: 12px; color: var(--muted); }
.ai-modal-fields summary { cursor: pointer; }
.ai-modal-table { border-collapse: collapse; width: 100%; font-size: 12px; margin-top: 8px; }
.ai-modal-table th, .ai-modal-table td { border: 1px solid var(--border); padding: 4px 8px; text-align: left; }
.ai-modal-table th { background: oklch(95% 0.005 250); }
.ai-modal-list { margin: 10px 0 0; padding-left: 20px; font-size: 12px; line-height: 1.7; }
.ai-modal-list li.is-risk { color: var(--error); font-weight: 600; }
.ai-modal-ack { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--error); margin-top: 10px; cursor: pointer; }
.ai-modal-acts { display: flex; gap: 10px; justify-content: flex-end; margin-top: var(--s-4); }
.ai-btn { padding: 6px 16px; border-radius: 7px; border: 1px solid var(--border-strong); background: var(--surface); cursor: pointer; font-size: 13px; color: var(--text); }
.ai-btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.ai-btn-primary:disabled { opacity: .5; cursor: not-allowed; }
</style>
