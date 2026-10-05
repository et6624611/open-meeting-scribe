<template>
  <div class="cli-panel">
    <!-- 探针三段状态常驻回显（REQ-EXPERT-MODE §2.2：不再「撞错才知道」） -->
    <div class="cli-probe-card">
      <div class="cli-probe-head">
        <span class="cli-probe-name">{{ probeName }}</span>
        <span v-if="probe?.available" class="cc-pill cc-pill-ok cli-probe-state">
          <svg class="cli-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
          {{ t('settings.cliengine_all_ok') }}
        </span>
        <span v-else-if="probe" class="cc-pill cc-pill-warn cli-probe-state">
          <svg class="cli-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
          {{ t('settings.cliengine_failed', { stage: stageLabel(probe.failed_stage) }) }}
        </span>
      </div>
      <div class="cli-probe-stages" role="list">
        <div class="cp-stage" :class="stageClass('path')" role="listitem">
          <span class="cp-stage-label">{{ t('settings.cliengine_stage_path') }}</span>
          <span class="cp-detail" :title="probe?.path || ''">{{ probe?.path || '—' }}</span>
        </div>
        <span class="cp-arrow" aria-hidden="true">→</span>
        <div class="cp-stage" :class="stageClass('version')" role="listitem">
          <span class="cp-stage-label">{{ t('settings.cliengine_stage_version') }}</span>
          <span class="cp-detail" :title="probe?.version || ''">{{ probe?.version || '—' }}</span>
        </div>
        <span class="cp-arrow" aria-hidden="true">→</span>
        <div class="cp-stage" :class="stageClass('login')" role="listitem">
          <span class="cp-stage-label">{{ t('settings.cliengine_stage_login') }}</span>
          <span class="cp-detail">{{ probe?.logged_in ? t('settings.cliengine_logged_in') : t('settings.cliengine_not_logged_in') }}</span>
        </div>
      </div>
      <p v-if="probe && !probe.available && probe.hint" class="cli-probe-hint">{{ t('ai-panel.' + probeHintKey) }}</p>
    </div>

    <!-- 配置面（显式保存；engine.mode 唯一写入口仍在接入方式决策卡） -->
    <div class="cc-field">
      <label class="cc-switch cli-switch-row">
        <input type="checkbox" v-model="form.enabled" />
        <span class="cc-switch-track" aria-hidden="true"></span>
        <span class="cli-switch-label">{{ t('settings.cliengine_enabled') }}</span>
      </label>
    </div>

    <!-- 授权档位已下沉到 AI 对话 ComposerBar（会话级选择），设置页不再提供全局档位入口 -->
    <div class="cc-field">
      <label class="cc-field-label" for="cli-engine-select">{{ t('settings.cliengine_engine') }}</label>
      <select id="cli-engine-select" v-model="form.engine_id" class="cc-select">
        <option v-for="e in engines" :key="e.engine_id" :value="e.engine_id">{{ engineLabel(e) }}</option>
      </select>
    </div>

    <div class="cc-field">
      <label class="cc-field-label" for="cli-path-input">{{ t('settings.cliengine_cli_path') }}</label>
      <input id="cli-path-input" v-model="form.cli_path_override" class="cc-input cc-input-mono" :placeholder="selectedBinary || 'qoder'" />
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
 * CLI 引擎设置面板（REQ-EXPERT-MODE §2.2 · 多 CLI 国际化改版）
 *
 * 智能体模式的算力提供者是本机 CLI 引擎（chat_engine 命名空间），与 access_mode 正交。
 * 探针三段：① 可执行路径解析 → ② --version 版本下限 → ③ status 登录态。
 * 状态常驻回显：失败段位直接可见（AC-4），不再「撞错才知道」。
 * 引擎下拉数据驱动：清单来自后端 /api/settings/chat-engine 的 engines 数组
 * （manifests/ 目录即引擎注册面，新增清单无需改前端）；展示名经 name_key i18n 化。
 * 视觉语言对齐 compute.css（cc-*）：本组件仅承载内容区，标题由父卡 cc-card-head 承担。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchChatEngineStatus, saveSettings, type ChatEngineEngineInfo, type ChatEngineProbe } from '@/api/settings'

const { t, te } = useI18n()

const probe = ref<ChatEngineProbe | null>(null)
const status = ref<Awaited<ReturnType<typeof fetchChatEngineStatus>> | null>(null)
const engines = ref<ChatEngineEngineInfo[]>([])
const saving = ref(false)
const saveMessage = ref('')
const saveError = ref(false)

const form = reactive({
  enabled: false,
  engine_id: 'qoder-cli',
  cli_path_override: '',
})

/** 引擎展示名：name_key 命中翻译优先，否则品牌原文（display_name 不翻译） */
function engineLabel(e: ChatEngineEngineInfo): string {
  const base = e.name_key && te(`settings.${e.name_key}`) ? t(`settings.${e.name_key}`) : e.display_name
  return e.installed ? base : `${base} · ${t('settings.cliengine_engine_not_installed')}`
}

const selectedBinary = computed(() => engines.value.find(e => e.engine_id === form.engine_id)?.binary || '')

const probeName = computed(() => {
  // 探针自身携带 name_key（预览切换时与已保存引擎可能不同），优先按它翻译
  const key = probe.value?.name_key
  if (key && te(`settings.${key}`)) return t(`settings.${key}`)
  // 预览探针（未保存引擎）：用引擎清单的本地化名，避免回退到已保存引擎的展示名
  const current = engines.value.find(e => e.engine_id === form.engine_id)
  if (current) return engineLabel(current).replace(` · ${t('settings.cliengine_engine_not_installed')}`, '')
  return probe.value?.display_name || status.value?.config?.engine_id || '—'
})

// 引擎下拉切换 → 预览探针（只读，不落盘）：失败段即时可见；切回已保存引擎时同样重探恢复，
// 避免预览失败态卡在离开后无法复原（seq 序号丢弃快速连续切换的过期响应）
let previewSeq = 0
watch(() => form.engine_id, async (eid) => {
  const saved = status.value?.config?.engine_id
  if (!saved) return
  const seq = ++previewSeq
  try {
    const st = await fetchChatEngineStatus(eid === saved ? '' : eid)
    if (seq !== previewSeq) return
    probe.value = st.probe ?? null
  } catch { /* 静默：保留上一次探针回显 */ }
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
      // auth_tier 不再由此页读写：档位是会话级口径，入口在 AI ComposerBar
      form.cli_path_override = c.cli_path_override || ''
    }
  } catch { /* 静默：面板显示占位 */ }
}

function stageClass(stage: 'path' | 'version' | 'login'): string {
  const failed = probe.value?.failed_stage
  if (!probe.value) return 'is-unknown'
  if (probe.value.available) return 'is-ok'
  if (!failed) return 'is-unknown'
  // 三段是顺序链：前段失败后段无从探测
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
        // 不传 auth_tier：避免保存引擎设置时误置 _auth_tier_explicit（档位由会话级管理）
        cli_path_override: form.cli_path_override || null,
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

onMounted(load)
defineExpose({ load })
</script>

<style src="./compute.css"></style>
<style scoped>
.cli-panel { display: flex; flex-direction: column; }

/* 探针卡：父级已是 cc-card（surface），此处用 surface-2 背景分区 + 单向分割线语义 */
.cli-probe-card { background: var(--surface-2); border-radius: var(--radius); padding: var(--s-3) var(--s-4); margin-bottom: var(--s-4); }
.cli-probe-head { display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; }
.cli-probe-name { font-size: 13px; font-weight: 600; color: var(--fg); }
.cli-probe-state { font-size: 11px; }
.cli-state-icon { width: 12px; height: 12px; flex: none; }

.cli-probe-stages { display: flex; align-items: stretch; gap: 6px; flex-wrap: wrap; margin-top: var(--s-3); }
.cp-stage { display: flex; flex-direction: column; gap: 2px; font-size: 12px; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 5px 10px; color: var(--muted); background: var(--surface); min-width: 0; }
.cp-stage-label { font-weight: 500; white-space: nowrap; }
.cp-stage .cp-detail { font-family: var(--font-mono); font-size: 12px; color: var(--subtle); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cp-stage.is-ok { border-color: oklch(from var(--ok) l c h / .4); color: var(--ok); }
.cp-stage.is-fail { border-color: oklch(from var(--warn) l c h / .5); color: var(--warn); font-weight: 600; }
.cp-stage.is-unknown { opacity: .55; }
.cp-arrow { color: var(--subtle); font-size: 12px; align-self: center; }
.cli-probe-hint { font-size: 12px; color: var(--warn); margin: var(--s-2) 0 0; }

/* 开关行：与 02/04 Tab 字段节奏一致 */
.cli-switch-row { display: flex; align-items: center; gap: var(--s-3); }
.cli-switch-label { font-size: 13px; color: var(--fg); }

.cli-orthogonal-note { margin-top: var(--s-2); line-height: 1.55; }
</style>
