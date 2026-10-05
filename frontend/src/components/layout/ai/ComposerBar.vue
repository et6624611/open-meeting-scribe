<template>
  <!-- Composer 控制行：模式 + 模型/引擎模型 + 发送/停止（底部输入区与消息编辑态共用） -->
  <div class="composer-bar" ref="barRef" :class="{ 'is-compact': compact }">
    <!-- 对话模式触发器（会话级，与“角色”正交） -->
    <div class="cb-trigger-wrap">
      <button ref="modeTriggerEl" class="ac-trigger is-icon" :class="{ 'is-open': modeMenuVisible }" v-bind="modeTriggerAttrs" :aria-label="t('ai-panel.mode_label')" :data-tip="t('ai-panel.mode_' + chatMode)" @click="toggleModeMenu">
        <svg class="ac-tr-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" v-html="modeIconBody"></svg>
      </button>
      <div ref="modeMenuEl" v-show="modeMenuVisible" class="ac-menu" style="width: 288px;" v-bind="modeMenuAttrs">
        <div class="ac-group">
          <div class="ac-label"><span>{{ t('ai-panel.mode_label') }}</span><span>{{ MODE_LIST.length }}</span></div>
          <button v-for="m in MODE_LIST" :key="m" class="ac-row" role="menuitem" :class="{ 'is-sel': chatMode === m }" :aria-label="t('ai-panel.mode_' + m)" @click="onPickMode(m)">
            <span class="ac-badge"><svg class="ac-badge-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="MODE_ICONS[m].body"></svg></span>
            <span class="ac-it"><span class="ac-it-name">{{ t('ai-panel.mode_' + m) }}</span><span class="ac-it-sub">{{ t('ai-panel.mode_' + m + '_hint') }}</span></span>
            <span class="ac-right">
              <svg v-if="chatMode === m" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
            </span>
          </button>
        </div>
      </div>
    </div>

    <!-- 授权档位触发器（会话级；与模式正交）：模式管“能不能动手”，档位管“动手的上限”。
         问答模式下模型不调用工具，档位钮置灰但仍可查看/预选。 -->
    <div class="cb-trigger-wrap">
      <button
        ref="tierTriggerEl"
        class="ac-trigger is-icon tier-trigger"
        :class="['t-' + pendingTier, { 'is-open': tierMenuVisible, 'is-qa': chatMode === 'qa', 'is-pending': pendingTier !== sessionTier }]"
        v-bind="tierTriggerAttrs"
        :aria-label="t('ai-panel.tier_label')"
        :title="chatMode === 'qa' ? t('ai-panel.tier_qa_title') : t('ai-panel.tier_trigger_title', { tier: tierName(pendingTier) })"
        @click="toggleTierMenu"
      >
        <svg class="ac-tr-icon tier-icon" viewBox="0 0 24 24" v-html="TIER_ICONS[pendingTier].body"></svg>
        <span class="tier-dot" aria-hidden="true"></span>
      </button>
      <div ref="tierMenuEl" v-show="tierMenuVisible" class="ac-menu" style="width: 288px;" v-bind="tierMenuAttrs">
        <div class="ac-group">
          <div class="ac-label"><span>{{ t('ai-panel.tier_label') }}</span><span>{{ t('ai-panel.tier_scope') }}</span></div>
          <div v-if="chatMode === 'qa'" class="ac-hint">{{ t('ai-panel.tier_qa_hint') }}</div>
          <button
            v-for="tr in TIER_LIST" :key="tr"
            class="ac-row" role="menuitem"
            :class="{ 'is-sel': pendingTier === tr }"
            :aria-label="tierName(tr)"
            @click="onPickTier(tr)"
          >
            <span class="ac-badge" :class="'t-badge-' + tr"><svg class="ac-badge-icon" viewBox="0 0 24 24" v-html="TIER_ICONS[tr].body"></svg></span>
            <span class="ac-it">
              <span class="ac-it-name">
                {{ tierName(tr) }}<span v-if="tr === 'workspace_write'" class="tier-rec">{{ t('ai-panel.tier_recommended') }}</span>
              </span>
              <span class="ac-it-sub">{{ t('ai-panel.tier_' + tr + '_hint') }}</span>
            </span>
            <span class="ac-right">
              <svg v-if="pendingTier === tr" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
            </span>
          </button>
          <div class="tier-lock">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="TIER_LOCK_ICON.body"></svg>
            <span v-if="pendingTier !== sessionTier">{{ t('ai-panel.tier_lock_pending', { session: tierName(sessionTier), pending: tierName(pendingTier) }) }}</span>
            <span v-else>{{ t('ai-panel.tier_lock', { tier: tierName(sessionTier) }) }}</span>
          </div>
          <button
            class="ac-foot" role="menuitem"
            :class="{ 'is-ready': pendingTier !== sessionTier, 'is-disabled': pendingTier === sessionTier }"
            :aria-label="pendingTier !== sessionTier ? t('ai-panel.tier_apply', { tier: tierName(pendingTier) }) : t('ai-panel.tier_already')"
            @click="onApplyTier"
          >
            <span>{{ pendingTier !== sessionTier ? t('ai-panel.tier_apply', { tier: tierName(pendingTier) }) : t('ai-panel.tier_already') }}</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" v-html="TIER_ARROW_ICON.body"></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 模型/引擎模型触发器：智能体模式选 CLI 引擎模型，其余选 LLM 模型（ai-model-select 为契约测试锚点） -->
    <div class="cb-trigger-wrap">
      <button ref="modelTriggerEl" class="ac-trigger ai-model-select" :class="{ 'is-open': modelMenuVisible }" v-bind="modelTriggerAttrs" :aria-label="isAgentMode ? t('ai-panel.model_cli_engine_label') : t('ai-panel.model_label')" :title="isAgentMode ? (agentEngineModel || t('ai-panel.model_cli_engine_default')) : (sessionModel || detailModelLabel)" @click="toggleModelMenu">
        <svg class="ac-tr-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 3v3M14 3v3M10 18v3M14 18v3M3 10h3M3 14h3M18 10h3M18 14h3"/></svg>
        <span class="ac-tr-txt">
          <span class="ac-tr-name">{{ isAgentMode ? (agentEngineModel || t('ai-panel.model_cli_engine_default')) : (sessionModel || `${t('ai-panel.model_builtin_default')} · ${detailModelLabel}`) }}</span>
          <span class="ac-tr-sub">{{ isAgentMode ? (agentEngineName || 'CLI') : (sessionModel ? srcLabel(menuModelSource) : t('ai-panel.model_builtin_default')) }}</span>
        </span>
        <svg class="ac-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
      </button>
      <div ref="modelMenuEl" v-show="modelMenuVisible" class="ac-menu" style="width: 322px;" v-bind="modelMenuAttrs">
        <!-- ══ 统一资源清单：全集恒定呈现，模式只切换可选性 ══ -->
        <!-- ── 内置 LLM 组：智能体模式下整组置灰 ── -->
        <div class="ac-group" :class="{ 'is-group-disabled': isAgentMode }">
          <div class="ac-label"><span>{{ t('ai-panel.model_group_builtin') }}</span><span>{{ modelOptions.length + 1 }}</span></div>
          <div v-if="isAgentMode" class="ac-hint">{{ t('ai-panel.model_hint_unavailable_builtin') }}</div>
          <button class="ac-row" role="menuitem" :class="{ 'is-disabled': isAgentMode, 'is-sel': !isAgentMode && !sessionModel }" :aria-label="t('ai-panel.model_builtin_default')" @click="onPickModel('', '')">
            <span class="ac-badge">⇄</span>
            <span class="ac-it"><span class="ac-it-name">{{ t('ai-panel.model_builtin_default') }}</span><span class="ac-it-sub">{{ t('ai-panel.model_builtin_default_hint', { model: detailModelLabel }) }}</span></span>
            <span class="ac-right">
              <svg v-if="!isAgentMode && !sessionModel" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
              <span v-else-if="isAgentMode && !sessionModel" class="ac-pill">{{ t('ai-panel.badge_current') }}</span>
            </span>
          </button>
          <div class="ac-note">{{ t('ai-panel.model_scope_note') }}</div>
        </div>
        <!-- 会话级 LLM 候选（按来源分组） -->
        <div v-for="g in modelGroups" :key="g.source" class="ac-group" :class="{ 'is-group-disabled': isAgentMode }">
          <div class="ac-label"><span>{{ srcLabel(g.source) }}</span><span>{{ g.opts.length }}</span></div>
          <button v-for="opt in g.opts" :key="opt.value" class="ac-row" role="menuitem" :class="{ 'is-disabled': isAgentMode, 'is-sel': !isAgentMode && sessionModel === opt.value && menuModelSource === g.source }" :aria-label="opt.value + ' · ' + srcLabel(g.source)" @click="onPickModel(opt.value, g.source)">
            <span class="ac-badge">{{ srcLabel(g.source).slice(0, 1) }}</span>
            <span class="ac-it">
              <span class="ac-it-name">{{ opt.value }}</span>
              <span class="ac-it-sub">{{ g.source === 'local' ? t('ai-panel.model_local_endpoint') : t('ai-panel.model_configured') }}</span>
            </span>
            <span class="ac-right">
              <svg v-if="!isAgentMode && sessionModel === opt.value && menuModelSource === g.source" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
              <span v-else-if="isAgentMode && sessionModel === opt.value" class="ac-pill">{{ t('ai-panel.badge_current') }}</span>
            </span>
          </button>
        </div>
        <!-- ── CLI 引擎组：问答模式下整组置灰 ── -->
        <div class="ac-group" :class="{ 'is-group-disabled': !isAgentMode }">
          <div class="ac-label"><span>{{ agentEngineName || 'CLI' }}</span><span>{{ agentModels.length }}</span></div>
          <div v-if="!isAgentMode" class="ac-hint">{{ t('ai-panel.model_hint_cli_disabled') }}</div>
          <button class="ac-row" role="menuitem" :class="{ 'is-disabled': !isAgentMode, 'is-sel': isAgentMode && !agentEngineModel }" :aria-label="t('ai-panel.model_cli_engine_default')" @click="onPickAgentModel('')">
            <span class="ac-badge">⇄</span>
            <span class="ac-it"><span class="ac-it-name">{{ t('ai-panel.model_cli_engine_default') }}</span><span class="ac-it-sub">{{ t('ai-panel.model_cli_engine_default_hint') }}</span></span>
            <span class="ac-right">
              <svg v-if="isAgentMode && !agentEngineModel" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
              <span v-else-if="!isAgentMode && !agentEngineModel" class="ac-pill">{{ t('ai-panel.badge_default') }}</span>
            </span>
          </button>
        </div>
        <div v-if="agentModels.length" class="ac-group" :class="{ 'is-group-disabled': !isAgentMode }">
          <button v-for="m in agentModels" :key="m" class="ac-row" role="menuitem" :class="{ 'is-disabled': !isAgentMode, 'is-sel': isAgentMode && agentEngineModel === m }" :aria-label="m" @click="onPickAgentModel(m)">
            <span class="ac-badge">M</span>
            <span class="ac-it"><span class="ac-it-name">{{ m }}</span><span class="ac-it-sub">{{ t('ai-panel.model_cli_available') }}</span></span>
            <span class="ac-right">
              <svg v-if="isAgentMode && agentEngineModel === m" class="ac-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4 10-10"/></svg>
              <span v-else-if="!isAgentMode && agentEngineModel === m" class="ac-pill">{{ t('ai-panel.badge_current') }}</span>
            </span>
          </button>
        </div>
        <div v-else class="ac-empty">{{ cliGroupEmptyText }}</div>
        <button class="ac-foot" role="menuitem" :aria-label="t('ai-panel.model_cli_goto')" @click="onGotoCliSettings">
          <span>{{ t('ai-panel.model_cli_goto') }}</span>
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg>
        </button>
        <button class="ac-foot" role="menuitem" :aria-label="t('ai-panel.model_manage_all')" @click="onGotoComputeSettings">
          <span>{{ t('ai-panel.model_manage_all') }}</span>
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg>
        </button>
      </div>
    </div>

    <div class="cb-right">
      <button class="composer-send is-icon" :class="{ 'is-stop': isLoading }" :disabled="!isLoading && sendDisabled" :aria-label="isLoading ? t('ai-panel.stop_generating') : t('ai-panel.send')" :title="isLoading ? t('ai-panel.stop_generating') : t('ai-panel.send')" @click="onSendOrStop">
        <svg v-if="isLoading" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { ChatEngineProbe } from '@/api/settings'
import { lucideIcon, type IconDef } from '@/utils/lucideIcons'
import { usePopMenu } from '@/composables/usePopMenu'
import type { AuthTier } from '@/composables/useAiChat'

type ChatMode = 'qa' | 'agent'
type ModelSource = 'local' | 'trial' | 'byok'

const props = defineProps<{
  chatMode: ChatMode
  /** 本会话锁定档（快照） */
  sessionTier: AuthTier
  /** 待生效档（会中预选，新会话应用） */
  pendingTier: AuthTier
  /** 403 拒绝卡等外部唤起档位菜单的信号（自增） */
  tierMenuSignal: number
  sessionModel: string
  modelOptions: Array<{ value: string; source: ModelSource }>
  detailModelLabel: string
  isLoading: boolean
  sendDisabled: boolean
  cliProbe: ChatEngineProbe | null
  agentEngineName: string
  agentEngineModel: string
  agentModels: string[]
  agentModelsReason: string
  agentModelsLoading: boolean
}>()

const emit = defineEmits<{
  (e: 'update:chatMode', v: ChatMode): void
  (e: 'update:pendingTier', v: AuthTier): void
  (e: 'apply-new-session'): void
  (e: 'update:sessionModel', v: string): void
  (e: 'update:agentModel', v: string): void
  (e: 'send'): void
  (e: 'stop'): void
}>()

const { t } = useI18n()
const router = useRouter()

/** 智能体模式：模型位切换为 CLI 引擎模型语义 */
const isAgentMode = computed(() => props.chatMode === 'agent')

/** 对话模式清单（两态）与图标（内外同一套 lucide） */
const MODE_LIST = ['qa', 'agent'] as const
const MODE_ICONS: Record<ChatMode, IconDef> = {
  qa: lucideIcon('help-circle')!,
  agent: lucideIcon('terminal')!,
}
const modeIconBody = computed(() => MODE_ICONS[props.chatMode].body)

// ── 弹出菜单：usePopMenu 统一开合/定位/隐式收起 ──
const barRef = ref<HTMLElement | null>(null)
const modeTriggerEl = ref<HTMLElement | null>(null)
const modeMenuEl = ref<HTMLElement | null>(null)
const modelTriggerEl = ref<HTMLElement | null>(null)
const modelMenuEl = ref<HTMLElement | null>(null)
const { visible: modeMenuVisible, toggle: toggleModeMenu, close: closeModeMenu, triggerAttrs: modeTriggerAttrs, menuAttrs: modeMenuAttrs } = usePopMenu(modeMenuEl, modeTriggerEl, { align: 'start' })
const { visible: modelMenuVisible, toggle: toggleModelMenu, close: closeModelMenu, triggerAttrs: modelTriggerAttrs, menuAttrs: modelMenuAttrs } = usePopMenu(modelMenuEl, modelTriggerEl, { align: 'start' })

// ── 授权档位菜单（同款 usePopMenu；会话级快照，会中改档仅待生效） ──
const tierTriggerEl = ref<HTMLElement | null>(null)
const tierMenuEl = ref<HTMLElement | null>(null)
const { visible: tierMenuVisible, toggle: toggleTierMenuRaw, close: closeTierMenu, triggerAttrs: tierTriggerAttrs, menuAttrs: tierMenuAttrs } = usePopMenu(tierMenuEl, tierTriggerEl, { align: 'start' })
// 问答模式下钮置灰但仍可点开预选（档位不生效，只更新待生效值）
function toggleTierMenu() { toggleTierMenuRaw() }
const TIER_LIST: AuthTier[] = ['readonly', 'workspace_write', 'full_task']
const TIER_ICONS: Record<AuthTier, IconDef> = {
  readonly: lucideIcon('ban')!,
  workspace_write: lucideIcon('layers')!,
  full_task: lucideIcon('shield')!,
}
const TIER_LOCK_ICON = lucideIcon('lock')!
const TIER_ARROW_ICON = lucideIcon('arrow-right')!
function tierName(tr: AuthTier): string { return t(`ai-panel.tier_name_${tr}`) }
function onPickTier(tr: AuthTier) {
  // 不关闭弹层：改选后让用户看到锁定说明变化，脚钮「开新会话应用」才收口
  if (tr !== props.pendingTier) emit('update:pendingTier', tr)
}
function onApplyTier() {
  if (props.pendingTier === props.sessionTier) { closeTierMenu(); return }
  closeTierMenu()
  emit('apply-new-session')
}
// 403 拒绝卡等外部唤起：信号自增即打开并给触发器一个脉冲提示
watch(() => props.tierMenuSignal, (n, old) => {
  if (n <= old) return
  if (!tierMenuVisible.value) toggleTierMenuRaw()
  const el = tierTriggerEl.value
  if (el) { el.classList.remove('tier-pulse'); void el.offsetWidth; el.classList.add('tier-pulse') }
})

/** 资源候选按来源分组（本机 → 体验配额 → 自带 Key） */
const MODEL_GROUP_ORDER: ModelSource[] = ['local', 'trial', 'byok']
const modelGroups = computed(() => MODEL_GROUP_ORDER
  .map(source => ({ source, opts: props.modelOptions.filter(o => o.source === source) }))
  .filter(g => g.opts.length > 0))
/** 会话级选中项来源（同值跨源时跟随候选表；未命中保留菜单上次选择） */
const menuModelOverride = ref<{ value: string; source: ModelSource } | null>(null)
const menuModelSource = computed<ModelSource | ''>(
  () => (menuModelOverride.value && menuModelOverride.value.value === props.sessionModel
    ? menuModelOverride.value.source
    : props.modelOptions.find(o => o.value === props.sessionModel)?.source) ?? '')

function srcLabel(source: ModelSource | ''): string {
  if (source === 'local') return t('ai-panel.model_src_local')
  if (source === 'trial') return t('ai-panel.model_src_trial')
  if (source === 'byok') return t('ai-panel.model_src_byok')
  return source || '—'
}

function onPickMode(m: ChatMode) {
  closeModeMenu()
  if (m !== props.chatMode) emit('update:chatMode', m)
}
function onPickModel(value: string, source: ModelSource | '') {
  // 智能体模式下内置组整组置灰，点击 no-op（不隐式切模式）
  if (isAgentMode.value) return
  closeModelMenu()
  emit('update:sessionModel', value)
  if (value && source && props.modelOptions.find(o => o.value === value)?.source !== source) {
    menuModelOverride.value = { value, source }
  } else {
    menuModelOverride.value = null
  }
}
function onPickAgentModel(v: string) {
  // 问答模式下 CLI 组整组置灰
  if (!isAgentMode.value) return
  closeModelMenu()
  if (v !== props.agentEngineModel) emit('update:agentModel', v)
}

/** CLI 组空态文案：问答模式明示懒加载；智能体模式区分加载/未登录/不可用 */
const cliGroupEmptyText = computed(() => {
  if (props.agentModelsLoading) return t('ai-panel.model_cli_loading')
  if (!isAgentMode.value) return t('ai-panel.model_cli_not_probed')
  return props.agentModelsReason === 'not_logged_in' ? t('ai-panel.model_cli_need_login') : t('ai-panel.model_cli_unavailable')
})

function onGotoComputeSettings() {
  closeModelMenu()
  void router.push({ name: 'settings', query: { cat: 'ai' } })
}
function onGotoCliSettings() {
  closeModelMenu()
  void router.push({ name: 'settings', query: { cat: 'ai' } })
}

/** 发送/停止合一（加载态下同一按钮切换为停止） */
function onSendOrStop() {
  if (props.isLoading) emit('stop')
  else emit('send')
}

// ── 窄档密度：控制行可用宽度不足时模型触发器降级纯图标 ──
const compact = ref(false)
function composerVar(name: string, fallback: number): number {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name))
  return Number.isFinite(v) && v > 0 ? v : fallback
}
function syncDensity() {
  const bar = barRef.value
  if (!bar) return
  compact.value = bar.clientWidth > 0 && bar.clientWidth < composerVar('--composer-compact-below', 288)
}
watch(
  () => [props.chatMode, props.sessionModel, props.agentEngineModel, props.agentEngineName],
  () => { void nextTick(syncDensity) },
)

let composerRo: ResizeObserver | null = null
onMounted(() => {
  syncDensity()
  if (typeof ResizeObserver !== 'undefined' && barRef.value) {
    composerRo = new ResizeObserver(() => syncDensity())
    composerRo.observe(barRef.value)
  }
})
onBeforeUnmount(() => { composerRo?.disconnect(); composerRo = null })
</script>

<style scoped>
.composer-bar {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  flex: 0 0 auto;
  flex-wrap: nowrap;
  height: var(--composer-bar-h);
  min-height: var(--composer-bar-h);
  margin-top: var(--composer-gap);
  position: relative;
}
/* 分区 hairline：文本区与控制行语义分隔，线宽取栏内容宽 */
.composer-bar::before {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  top: -9px;
  height: 1px;
  background: var(--border);
}
.cb-trigger-wrap { position: relative; display: flex; min-width: 0; flex: 0 1 auto; }
.cb-trigger-wrap:has(.ac-trigger.is-icon) { flex: 0 0 auto; }
.cb-trigger-wrap:has(.ai-model-select) { flex-shrink: 1; }
.ac-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: min(190px, 100%);
  height: var(--composer-bar-h);
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 6px);
  background: var(--surface-2);
  color: var(--fg);
  cursor: pointer;
  transition: background 0.14s ease, border-color 0.14s ease;
}
.ac-trigger:hover { background: var(--surface-3); border-color: var(--border-strong); }
.ac-trigger.is-open { background: var(--surface-3); border-color: var(--fg); }
.ac-tr-icon {
  width: 14px; height: 14px; flex: 0 0 auto;
  color: var(--muted); fill: none; stroke: currentColor;
  stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round;
}
.ac-trigger.is-open .ac-tr-icon { color: var(--fg); }
.ac-tr-txt { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.25; min-width: 0; overflow: hidden; }
.ac-tr-name { font-size: var(--fs-12, 12px); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 124px; }
.ac-tr-sub { font-family: var(--font-mono); font-size: var(--fs-11, 11px); color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 124px; }
.ac-chev {
  width: 12px; height: 12px; flex: 0 0 auto;
  color: var(--subtle); fill: none; stroke: currentColor;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
  transition: transform 0.14s ease;
}
.ac-trigger.is-open .ac-chev { transform: rotate(180deg); }
.ac-trigger.is-icon { flex: 0 0 auto; width: var(--composer-bar-h); max-width: var(--composer-bar-h); justify-content: center; padding: 0; }
.ac-trigger.is-icon .ac-tr-txt,
.ac-trigger.is-icon .ac-chev { display: none; }
.ac-trigger.is-icon .ac-tr-icon { width: 16px; height: 16px; }

/* 弹出菜单：usePopMenu fixed 定位 */
.ac-menu {
  position: fixed;
  top: 0; left: 0;
  z-index: var(--z-popover, 500);
  max-height: 420px;
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg, 12px);
  box-shadow: 0 10px 28px oklch(18% 0.012 250 / 0.14), 0 2px 6px oklch(18% 0.012 250 / 0.06);
  padding: 6px;
}
.ac-group + .ac-group { border-top: 1px solid var(--border); margin-top: 6px; padding-top: 6px; }
.ac-label {
  display: flex; align-items: center; justify-content: space-between; gap: var(--s-2);
  padding: 6px 8px 4px;
  font-family: var(--font-mono); font-size: var(--fs-11, 11px);
  letter-spacing: 0.06em; color: var(--subtle);
}
.ac-row {
  display: grid;
  grid-template-columns: 26px 1fr auto;
  align-items: center;
  gap: var(--s-2);
  width: 100%;
  text-align: left;
  min-height: 40px;
  padding: 6px 8px;
  border: none;
  border-radius: var(--radius-sm, 6px);
  background: transparent;
  color: var(--fg);
  font: inherit;
  cursor: pointer;
  transition: background 0.12s ease;
}
.ac-row:hover { background: var(--surface-3); }
.ac-row.is-sel { background: var(--accent-soft); }
.ac-row.is-sel:hover { background: var(--accent-soft); filter: brightness(0.97); }
.ac-badge {
  width: 26px; height: 26px;
  display: grid; place-items:center;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 6px);
  background: var(--surface-2);
  font-family: var(--font-mono); font-size: var(--fs-11, 11px); font-weight: 600;
  color: var(--muted);
}
.ac-row.is-sel .ac-badge { background: var(--surface); border-color: var(--border-strong); color: var(--fg); }
.ac-badge-icon { width: 14px; height: 14px; flex-shrink: 0; }
.ac-it { min-width: 0; }
.ac-it-name { display: block; font-size: var(--fs-13, 13px); font-weight: 600; line-height: 1.35; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ac-it-sub { display: block; font-family: var(--font-mono); font-size: var(--fs-11, 11px); color: var(--muted); margin-top: 1px; line-height: 1.4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ac-right { display: flex; align-items: center; gap: 6px; justify-self: end; }
.ac-check { width: 14px; height: 14px; color: var(--accent); flex: 0 0 auto; }
.ac-pill {
  display: inline-flex; align-items: center;
  font-family: var(--font-mono); font-size: var(--fs-11, 11px);
  border-radius: 5px; padding: 2px 6px;
  border: 1px solid var(--border-strong);
  color: var(--muted); background: var(--surface-2); white-space: nowrap;
}
.ac-foot {
  display: flex; align-items: center; justify-content: space-between; gap: var(--s-2);
  width: calc(100% - 12px); margin: 0 6px;
  padding: 9px 8px;
  border: none; border-top: 1px solid var(--border); border-radius: 0;
  background: transparent; color: var(--muted);
  font: inherit; font-size: var(--fs-12, 12px);
  cursor: pointer; transition: all 0.12s;
}
.ac-foot:hover { color: var(--fg); }
.ac-empty {
  padding: 10px 8px;
  font-size: var(--fs-11, 11px);
  color: var(--muted, #888);
  line-height: 1.5;
}
.ac-row.is-disabled { opacity: 0.45; cursor: not-allowed; }
.ac-row.is-disabled:hover { background: transparent; }
.ac-row.is-disabled.is-sel { background: transparent; }
.ac-hint {
  padding: 2px 8px 4px;
  font-size: var(--fs-11, 11px);
  color: var(--muted, #888);
  font-style: italic;
}
.ac-note {
  padding: 4px 8px 2px;
  font-size: var(--fs-11, 11px);
  color: var(--subtle, #aaa);
  line-height: 1.5;
}

.cb-right { margin-left: auto; display: flex; align-items: center; gap: var(--s-2); flex: 0 0 auto; flex-wrap: nowrap; }

.composer-send {
  display:inline-flex;
  align-items: center;
  gap: 6px;
  height: var(--composer-bar-h);
  padding: 0 12px;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid transparent;
  background: var(--fg);
  color: var(--surface);
  font-size: var(--fs-12, 12px);
  font-weight: 600;
  cursor: pointer;
  transition: background 0.14s ease, opacity 0.12s ease, transform 0.05s ease;
}
.composer-send:hover { opacity: 0.85; }
.composer-send:active { transform: translateY(1px); }
.composer-send:disabled { background: var(--surface-3); color: var(--subtle); cursor: not-allowed; transform: none; opacity: 1; }
.composer-send.is-stop { background: var(--surface); color: var(--fg); border-color: var(--border-strong); }
.composer-send.is-stop:hover { background: var(--surface-2); }
.composer-send svg { width: 13px; height: 13px; flex: 0 0 auto; }
.composer-send.is-icon { flex: 0 0 auto; width: var(--composer-bar-h); padding: 0; justify-content: center; }
.composer-send.is-icon svg { width: 15px; height: 15px; }

/* 窄档：模型触发器降级纯图标，发送键不变 */
.composer-bar.is-compact .ai-model-select .ac-tr-txt,
.composer-bar.is-compact .ai-model-select .ac-chev { display: none; }
.composer-bar.is-compact .ai-model-select { flex: 0 0 auto; width: var(--composer-bar-h); max-width: var(--composer-bar-h); padding: 0; justify-content: center; }
.composer-bar.is-compact .cb-trigger-wrap:has(.ai-model-select) { flex: 0 0 auto; }

/* ── 授权档位：盾钮色随档（灰=只读 / 绿=提案 / 琥珀=全任务），蓝点=待生效未应用 ── */
.tier-trigger { position: relative; }
.tier-trigger .tier-icon { transition: color 0.12s ease, opacity 0.12s ease; }
.tier-trigger.t-readonly .tier-icon { color: var(--subtle, #9aa1ad); }
.tier-trigger.t-workspace_write .tier-icon { color: var(--ok, #1a8a4f); }
.tier-trigger.t-full_task .tier-icon { color: var(--warn, #8a5800); }
.tier-trigger.is-open .tier-icon { filter: brightness(0.88); }
/* 问答模式：档位不生效——置灰但可点开预选，不封死入口 */
.tier-trigger.is-qa { opacity: 0.42; }
.tier-trigger.is-qa .tier-icon { color: var(--subtle, #9aa1ad); }
.tier-dot {
  position: absolute; top: 5px; right: 5px;
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent, #2f6fed);
  border: 1.5px solid var(--surface, #fff);
  display: none; pointer-events: none;
}
.tier-trigger.is-pending .tier-dot { display: block; }

/* 弹层内档位行 */
.t-badge-readonly { color: var(--subtle, #9aa1ad); }
.t-badge-workspace_write { color: var(--ok, #1a8a4f); }
.t-badge-full_task { color: var(--warn, #8a5800); }
.tier-rec {
  display: inline-block; margin-left: 6px;
  font-family: var(--font-mono); font-size: 10px; font-weight: 600; line-height: 1.6;
  padding: 0 5px; border-radius: 4px;
  color: var(--ok, #1a8a4f); border: 1px solid color-mix(in srgb, currentColor 35%, transparent);
  white-space: nowrap; vertical-align: 1px;
}
.tier-lock {
  display: flex; align-items: flex-start; gap: 6px;
  margin: 4px 6px 0; padding: 7px 8px 3px;
  border-top: 1px dashed var(--border);
  font-size: var(--fs-11, 11px); color: var(--muted); line-height: 1.5;
}
.tier-lock svg { width: 12px; height: 12px; flex: 0 0 auto; margin-top: 2px; }
.ac-foot.is-ready { color: var(--accent, #2f6fed); font-weight: 600; }
.ac-foot.is-ready:hover { color: var(--accent, #2f6fed); }
.ac-foot.is-disabled { opacity: 0.5; cursor: default; }
.ac-foot.is-disabled:hover { color: var(--muted); }

/* 403 拒绝卡唤起：盾钮脉冲两圈 */
@keyframes tier-pulse-ring {
  0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent, #2f6fed) 45%, transparent); }
  100% { box-shadow: 0 0 0 9px transparent; }
}
.tier-trigger.tier-pulse { animation: tier-pulse-ring 0.7s ease-out 2; }

@media (prefers-reduced-motion: reduce) {
  .tier-trigger.tier-pulse { animation: none; }
}
</style>
