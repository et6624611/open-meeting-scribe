<template>
  <div class="cli-panel">
    <!-- 顶部：你的 CLI（已安装分组） -->
    <div class="cli-section">
      <div class="cli-section-head">
        <h3 class="cli-section-title">{{ t('settings.cliengine_your_cli', { n: installedEngines.length }) }}</h3>
        <button class="cc-btn cc-btn-ghost cc-btn-sm" @click="onRescan" :disabled="rescanning">
          <svg class="cc-btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
          {{ rescanning ? t('settings.cliengine_rescanning') : t('settings.cliengine_rescan') }}
        </button>
      </div>

      <div v-if="installedEngines.length" class="cli-card-list">
        <div
          v-for="e in installedEngines"
          :key="e.engine_id"
          class="cli-engine-card"
          :class="{ 'is-selected': form.engine_id === e.engine_id }"
          @click="selectEngine(e.engine_id)"
          role="button"
          tabindex="0"
          @keydown.enter="selectEngine(e.engine_id)"
        >
          <div class="cli-avatar" :style="{ '--cli-color': e.icon_color || '#6B7280' }">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="iconPaths(e.icon || 'bot')"></svg>
          </div>
          <div class="cli-card-body">
            <div class="cli-card-title-row">
              <span class="cli-card-name">{{ engineLabel(e) }}</span>
              <span v-if="e.recommended" class="cc-pill cc-pill-accent cli-badge">{{ t('settings.cliengine_recommended') }}</span>
            </div>
            <div class="cli-card-meta">
              <span class="cli-meta-item">{{ e.version || '—' }}</span>
              <span class="cli-meta-sep">·</span>
              <span class="cli-meta-item" :class="probeStateClass(e)">{{ probeStateLabel(e) }}</span>
            </div>
          </div>
          <div class="cli-card-actions" @click.stop>
            <button class="cc-btn cc-btn-secondary cc-btn-sm" @click="selectEngine(e.engine_id)">
              {{ t('settings.cliengine_test') }}
            </button>
          </div>
        </div>
      </div>
      <p v-else class="cc-note cli-empty-hint">{{ t('settings.cliengine_none_installed') }}</p>
    </div>

    <!-- 可安装分组（折叠） -->
    <div v-if="installableEngines.length" class="cli-section cli-section-installable">
      <button class="cli-collapsible" @click="installableOpen = !installableOpen" :aria-expanded="installableOpen">
        <h3 class="cli-section-title">{{ t('settings.cliengine_installable', { m: installableEngines.length }) }}</h3>
        <svg class="cli-caret" :class="{ 'is-open': installableOpen }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
      </button>
      <div v-if="installableOpen" class="cli-card-list">
        <div
          v-for="e in installableEngines"
          :key="e.engine_id"
          class="cli-engine-card cli-engine-card-missing"
        >
          <div class="cli-avatar cli-avatar-muted" :style="{ '--cli-color': e.icon_color || '#6B7280' }">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="iconPaths(e.icon || 'bot')"></svg>
          </div>
          <div class="cli-card-body">
            <div class="cli-card-title-row">
              <span class="cli-card-name">{{ engineLabel(e) }}</span>
              <span v-if="e.recommended" class="cc-pill cc-pill-accent cli-badge">{{ t('settings.cliengine_recommended') }}</span>
            </div>
            <div class="cli-card-meta cli-meta-missing">
              {{ t('settings.cliengine_not_found_on_path', { binary: e.binary }) }}
            </div>
          </div>
          <div class="cli-card-actions">
            <button
              v-if="e.install_url"
              class="cc-btn cc-btn-primary cc-btn-sm"
              @click="openInstallUrl(e)"
            >
              {{ t('settings.cliengine_install') }}
            </button>
            <span v-else class="cc-pill cli-badge">{{ t('settings.cliengine_no_install_url') }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 选中引擎的三段探针回显 -->
    <div v-if="probe && form.engine_id" class="cli-probe-card">
      <div class="cli-probe-head">
        <span class="cli-probe-name">{{ probeName }}</span>
        <span v-if="probe.available" class="cc-pill cc-pill-ok cli-probe-state">
          <svg class="cli-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
          {{ t('settings.cliengine_all_ok') }}
        </span>
        <span v-else class="cc-pill cc-pill-warn cli-probe-state">
          <svg class="cli-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
          {{ t('settings.cliengine_failed', { stage: stageLabel(probe.failed_stage) }) }}
        </span>
      </div>
      <div class="cli-probe-stages" role="list">
        <div class="cp-stage" :class="stageClass('path')" role="listitem">
          <span class="cp-stage-label">{{ t('settings.cliengine_stage_path') }}</span>
          <span class="cp-detail" :title="probe.path || ''">{{ probe.path || '—' }}</span>
        </div>
        <span class="cp-arrow" aria-hidden="true">→</span>
        <div class="cp-stage" :class="stageClass('version')" role="listitem">
          <span class="cp-stage-label">{{ t('settings.cliengine_stage_version') }}</span>
          <span class="cp-detail" :title="probe.version || ''">{{ probe.version || '—' }}</span>
        </div>
        <span class="cp-arrow" aria-hidden="true">→</span>
        <div class="cp-stage" :class="stageClass('login')" role="listitem">
          <span class="cp-stage-label">{{ t('settings.cliengine_stage_login') }}</span>
          <span class="cp-detail">{{ probe.logged_in ? t('settings.cliengine_logged_in') : (probe.login_skipped ? t('settings.cliengine_login_skipped') : t('settings.cliengine_not_logged_in')) }}</span>
        </div>
      </div>
      <p v-if="probe && !probe.available && probe.hint" class="cli-probe-hint">{{ t('ai-panel.' + probeHintKey) }}</p>
    </div>

    <!-- 启用开关 + CLI 路径覆盖 -->
    <div class="cc-field">
      <label class="cc-switch cli-switch-row">
        <input type="checkbox" v-model="form.enabled" />
        <span class="cc-switch-track" aria-hidden="true"></span>
        <span class="cli-switch-label">{{ t('settings.cliengine_enabled') }}</span>
      </label>
    </div>

    <div class="cc-field">
      <label class="cc-field-label" for="cli-path-input">{{ t('settings.cliengine_cli_path') }}</label>
      <input id="cli-path-input" v-model="form.cli_path_override" class="cc-input cc-input-mono" :placeholder="selectedBinary || 'qoder'" />
    </div>

    <!-- 联网搜索 -->
    <div class="cc-subcard">
      <div class="cc-subcard-head">
        <h3 class="cc-subcard-title">{{ t('settings.web_search_title') }}</h3>
        <span class="cc-pill" :class="webSearchConfigured ? 'cc-pill-ok' : ''">
          {{ webSearchConfigured ? t('settings.web_search_configured') : t('settings.web_search_not_configured') }}
        </span>
      </div>
      <p class="cc-note cli-note-block">{{ t('settings.web_search_desc') }}</p>
      <div class="cc-field">
        <label class="cc-field-label" for="ws-api-key">{{ t('settings.web_search_api_key') }}</label>
        <input
          id="ws-api-key" v-model="webSearchForm.api_key" class="cc-input cc-input-mono" type="password"
          :placeholder="existingWebSearchKey ? maskKey(existingWebSearchKey) : t('settings.web_search_api_key_placeholder')"
          autocomplete="off"
        />
      </div>
      <div class="ws-actions">
        <span class="cc-note cli-note-block ws-free-hint">{{ t('settings.web_search_brave_free') }}</span>
        <a href="https://brave.com/search/api/" target="_blank" rel="noopener" class="cc-link">{{ t('settings.web_search_get_key') }} →</a>
      </div>
    </div>

    <div class="cc-btn-row">
      <button class="cc-btn cc-btn-primary cc-btn-sm" :disabled="saving" @click="onSave">{{ saving ? t('settings.engine_saving') : t('settings.save') }}</button>
      <span v-if="saveMessage" class="cc-result-line" :class="{ 'is-error': saveError, 'is-ok': !saveError }">{{ saveMessage }}</span>
    </div>
    <p class="cc-note cli-orthogonal-note">{{ t('settings.cliengine_orthogonal_note') }}</p>
  </div>
</template>

<script setup lang="ts">
/**
 * CLI 引擎设置面板 —— 可选 + 可安装分组模式
 *
 * 借鉴图参考：已安装卡片列表（图标 + 名称 + 标签 + 版本 + 状态 + 测试按钮）
 * + 可安装折叠区（图标 + 名称 + 未找到提示 + 安装跳转按钮）
 * + 右上角重新扫描按钮。
 * 点击卡片即选中该引擎（更新 form.engine_id + 跑预览探针），
 * 选中引擎的三段探针回显常驻下方（REQ-EXPERT-MODE §2.2）。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchChatEngineStatus, fetchSettings, saveSettings, type ChatEngineEngineInfo, type ChatEngineProbe } from '@/api/settings'

const { t, te } = useI18n()

const probe = ref<ChatEngineProbe | null>(null)
const status = ref<Awaited<ReturnType<typeof fetchChatEngineStatus>> | null>(null)
const engines = ref<ChatEngineEngineInfo[]>([])
const saving = ref(false)
const saveMessage = ref('')
const saveError = ref(false)
const rescanning = ref(false)
const installableOpen = ref(false)

const form = reactive({
  enabled: false,
  engine_id: 'qoder-cli',
  cli_path_override: '',
})

const webSearchForm = reactive({ api_key: '' })
const existingWebSearchKey = ref('')
const wsIsSet = ref(false)
const webSearchConfigured = computed(() => wsIsSet.value)

function maskKey(key: string): string {
  if (!key || key.length < 8) return '****'
  return `${key.slice(0, 3)}****${key.slice(-4)}`
}

/** 已安装引擎（按 recommended 优先 + 名称排序） */
const installedEngines = computed(() => engines.value
  .filter(e => e.installed)
  .sort((a, b) => {
    if (!!b.recommended !== !!a.recommended) return (b.recommended ? 1 : 0) - (a.recommended ? 1 : 0)
    return (a.display_name || '').localeCompare(b.display_name || '')
  }))

/** 可安装引擎（未在 PATH 中找到） */
const installableEngines = computed(() => engines.value
  .filter(e => !e.installed)
  .sort((a, b) => {
    if (!!b.recommended !== !!a.recommended) return (b.recommended ? 1 : 0) - (a.recommended ? 1 : 0)
    return (a.display_name || '').localeCompare(b.display_name || '')
  }))

/** 引擎展示名：name_key 命中翻译优先，否则品牌原文 */
function engineLabel(e: ChatEngineEngineInfo): string {
  const key = e.name_key
  if (key && te(`settings.${key}`)) return t(`settings.${key}`)
  return e.display_name
}

const selectedBinary = computed(() => engines.value.find(e => e.engine_id === form.engine_id)?.binary || '')

const probeName = computed(() => {
  const key = probe.value?.name_key
  if (key && te(`settings.${key}`)) return t(`settings.${key}`)
  const current = engines.value.find(e => e.engine_id === form.engine_id)
  if (current) return engineLabel(current)
  return probe.value?.display_name || status.value?.config?.engine_id || '—'
})

/** 点击已安装卡片 = 选中引擎 */
function selectEngine(eid: string) {
  if (form.engine_id === eid) return
  form.engine_id = eid
}

/** 测试按钮 = 选中 + 立即保存 */
async function openInstallUrl(e: ChatEngineEngineInfo) {
  if (e.install_url) {
    window.open(e.install_url, '_blank', 'noopener')
  }
}

function probeStateClass(e: ChatEngineEngineInfo): string {
  if (e.available) return 'is-ok'
  if (!e.installed) return 'is-missing'
  return 'is-warn'
}

function probeStateLabel(e: ChatEngineEngineInfo): string {
  if (!e.installed) return t('settings.cliengine_not_installed')
  if (e.available) return t('settings.cliengine_all_ok')
  if (e.failed_stage === 'version') return t('settings.cliengine_stage_version') + ' ' + t('settings.cliengine_failed_short')
  if (e.failed_stage === 'login') return t('settings.cliengine_not_logged_in')
  return t('settings.cliengine_failed')
}

// 引擎切换 → 预览探针（只读，不落盘）
let previewSeq = 0
watch(() => form.engine_id, async (eid) => {
  const saved = status.value?.config?.engine_id
  if (!saved) return
  const seq = ++previewSeq
  try {
    const st = await fetchChatEngineStatus(eid === saved ? '' : eid)
    if (seq !== previewSeq) return
    probe.value = st.probe ?? null
  } catch { /* 静默 */ }
})

async function load() {
  try {
    status.value = await fetchChatEngineStatus()
    probe.value = status.value.probe ?? null
    engines.value = status.value.engines || []
    const c = status.value.config
    if (c) {
      form.enabled = !!c.enabled
      form.engine_id = c.engine_id || 'qoder-cli'
      form.cli_path_override = c.cli_path_override || ''
    }
  } catch { /* 静默 */ }
  try {
    const s = await fetchSettings()
    const ws = s.web_search
    existingWebSearchKey.value = ws?.api_key || ''
    wsIsSet.value = !!ws?.api_key_set
    webSearchForm.api_key = ''
  } catch { /* 静默 */ }
}

async function onRescan() {
  rescanning.value = true
  await load()
  rescanning.value = false
}

function stageClass(stage: 'path' | 'version' | 'login'): string {
  const failed = probe.value?.failed_stage
  if (!probe.value) return 'is-unknown'
  if (probe.value.available) return 'is-ok'
  if (!failed) return 'is-unknown'
  const order: Array<'path' | 'version' | 'login'> = ['path', 'version', 'login']
  const fi = order.indexOf(failed)
  const si = order.indexOf(stage)
  if (si < fi) return 'is-ok'
  if (si === fi) return 'is-fail'
  return 'is-unknown'
}

function stageLabel(stage?: string | null): string {
  if (stage === 'path') return t('settings.cliengine_stage_path')
  if (stage === 'version') return t('settings.cliengine_stage_version')
  if (stage === 'login') return t('settings.cliengine_stage_login')
  return '—'
}

const probeHintKey = computed(() => {
  const s = probe.value?.failed_stage
  if (s === 'version') return 'cli_probe_version_low'
  if (s === 'login') return 'cli_probe_not_logged_in'
  return 'cli_probe_not_installed'
})

async function onSave() {
  saving.value = true
  saveMessage.value = ''
  try {
    await saveSettings({
      chat_engine: {
        enabled: form.enabled,
        engine_id: form.engine_id,
        cli_path_override: form.cli_path_override || null,
      },
      web_search: {
        provider: 'brave',
        api_key: webSearchForm.api_key || '',
      },
    } as any)
    await load()
    saveMessage.value = t('settings.saved')
    saveError.value = false
  } catch {
    saveMessage.value = t('settings.engine_save_failed')
    saveError.value = true
  } finally {
    saving.value = false
  }
}

// ── SVG 图标路径映射（与 lucide 子集对齐；内联 SVG 避免新增依赖） ──
const ICON_PATHS: Record<string, string> = {
  bot: '<rect width="18" height="10" x="3" y="11" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" x2="8" y1="16" y2="16"/><line x1="16" x2="16" y1="16" y2="16"/>',
  cat: '<path d="M12 5c.67 0 1.35.09 2 .26 1.78-2 5.03-2.84 6.42-2.26 1.4.58-.42 7-.42 7 .57 1.07 1 2.24 1 3.44C21 17.9 16.97 21 12 21s-9-3-9-7.5c0-1.25.5-2.4 1-3.44 0 0-1.89-6.42-.5-7 1.39-.58 4.72.23 6.5 2.23A9.04 9.04 0 0 1 12 5"/><path d="M8 14v.5"/><path d="M16 14v.5"/><path d="M11.25 16.25h1.5L12 17z"/>',
  'terminal-square': '<path d="m7 11 2-2-2-2"/><path d="M11 13h4"/><rect width="18" height="18" x="3" y="3" rx="2"/>',
  code: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
  brain: '<path d="M12 2a4 4 0 0 0-4 4v1a4 4 0 0 0-3 3.87v1.75a4 4 0 0 0 3 3.88 4 4 0 0 0 6.52 2.26 4 4 0 0 0 5.48-2.26 4 4 0 0 0 3-3.88v-1.75a4 4 0 0 0-3-3.87V6a4 4 0 0 0-4-4"/><path d="M12 8v13"/><path d="M8 14h1"/><path d="M16 14h1"/><path d="M15 9h1"/><path d="M9 9h1"/>',
  sparkles: '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/>',
  wrench: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
  terminal: '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>',
}

function iconPaths(name: string): string {
  return ICON_PATHS[name] || ICON_PATHS.wrench
}

onMounted(load)
defineExpose({ load })
</script>

<style src="./compute.css"></style>
<style scoped>
.cli-panel { display: flex; flex-direction: column; gap: var(--s-4); }

/* 分组头 */
.cli-section { display: flex; flex-direction: column; }
.cli-section-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); margin-bottom: var(--s-3); }
.cli-section-title { font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; margin: 0; font-family: var(--font-mono); }
.cli-collapsible { display: flex; align-items: center; justify-content: space-between; width: 100%; background: transparent; border: none; cursor: pointer; padding: 0; }
.cli-caret { width: 16px; height: 16px; color: var(--muted); transition: transform .2s ease; }
.cli-caret.is-open { transform: rotate(180deg); }

/* 卡片列表 */
.cli-card-list { display: flex; flex-direction: column; gap: var(--s-2); }
.cli-empty-hint { padding: var(--s-3) var(--s-4); background: var(--surface-2); border-radius: var(--radius); }

/* 单张引擎卡片 */
.cli-engine-card {
  display: flex; align-items: center; gap: var(--s-3);
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: var(--s-3) var(--s-4); cursor: pointer;
  transition: border-color .15s ease, background .15s ease;
}
.cli-engine-card:hover { border-color: var(--border-strong); background: var(--surface-2); }
.cli-engine-card.is-selected { border-color: var(--accent); background: var(--accent-soft, var(--surface-2)); }
.cli-engine-card.is-selected .cli-card-name { color: var(--accent); }
.cli-engine-card-missing { cursor: default; opacity: .85; }
.cli-engine-card-missing:hover { border-color: var(--border); background: var(--surface); }

/* 头像 */
.cli-avatar {
  flex: none; width: 36px; height: 36px; border-radius: 10px;
  background: color-mix(in srgb, var(--cli-color, #6B7280) 15%, transparent);
  color: var(--cli-color, #6B7280);
  display: flex; align-items: center; justify-content: center;
}
.cli-avatar svg { width: 20px; height: 20px; }
.cli-avatar-muted { background: var(--surface-2); color: var(--muted); }

/* 卡片体 */
.cli-card-body { flex: 1; min-width: 0; }
.cli-card-title-row { display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; }
.cli-card-name { font-size: 13px; font-weight: 600; color: var(--fg); }
.cli-card-meta { display: flex; align-items: center; gap: 6px; margin-top: 4px; font-size: 11px; color: var(--muted); font-family: var(--font-mono); }
.cli-meta-item { display: inline-block; }
.cli-meta-sep { color: var(--border-strong); }
.cli-meta-missing { font-family: var(--font-mono); color: var(--warn); font-size: 11px; }

.cli-badge { font-size: 10px; }

.cli-meta-item.is-ok { color: var(--ok); }
.cli-meta-item.is-warn { color: var(--warn); }
.cli-meta-item.is-missing { color: var(--subtle); }

.cli-card-actions { flex: none; display: flex; align-items: center; gap: var(--s-2); }

/* 探针卡 */
.cli-probe-card { background: var(--surface-2); border-radius: var(--radius); padding: var(--s-3) var(--s-4); }
.cli-probe-head { display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; }
.cli-probe-name { font-size: 13px; font-weight: 600; color: var(--fg); }
.cli-probe-state { font-size: 11px; }
.cli-state-icon { width: 12px; height: 12px; flex: none; }

.cli-probe-stages { display: flex; align-items: stretch; gap: 6px; flex-wrap: wrap; margin-top: var(--s-3); }
.cp-stage { display: flex; flex-direction: column; gap: 2px; font-size: 12px; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 5px 10px; color: var(--muted); background: var(--surface); min-width: 0; }
.cp-stage-label { font-weight: 500; white-space: nowrap; }
.cp-stage .cp-detail { font-family: var(--font-mono); font-size: 12px; color: var(--subtle); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cp-stage.is-ok { border-color: color-mix(in srgb, var(--ok) 40%, transparent); color: var(--ok); }
.cp-stage.is-fail { border-color: color-mix(in srgb, var(--warn) 50%, transparent); color: var(--warn); font-weight: 600; }
.cp-stage.is-unknown { opacity: .55; }
.cp-arrow { color: var(--subtle); font-size: 12px; align-self: center; }
.cli-probe-hint { font-size: 12px; color: var(--warn); margin: var(--s-2) 0 0; }

.cli-switch-row { display: flex; align-items: center; gap: var(--s-3); }
.cli-switch-label { font-size: 13px; color: var(--fg); }

.cc-subcard { border-top: 1px solid var(--border); padding-top: var(--s-4); }
.cc-subcard-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--s-2); }
.cc-subcard-title { font-size: 13px; font-weight: 600; color: var(--fg); margin: 0; }
.cli-note-block { margin: var(--s-2) 0; line-height: 1.55; }
.ws-actions { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); margin-top: var(--s-2); flex-wrap: wrap; }
.ws-free-hint { flex: 1; min-width: 0; }
.cc-link { color: var(--accent); text-decoration: none; font-size: 12px; white-space: nowrap; }
.cc-link:hover { text-decoration: underline; }
.cc-btn-icon { width: 14px; height: 14px; }

.cli-orthogonal-note { margin-top: var(--s-2); line-height: 1.55; }
</style>
