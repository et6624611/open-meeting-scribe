<template>
  <div class="cli-panel">
    <div class="settings-section">
      <h2 class="settings-title">{{ t('settings.cliengine_title') }}</h2>
      <p class="settings-section-desc">{{ t('settings.cliengine_desc') }}</p>

      <!-- 探针三段状态常驻回显（REQ-EXPERT-MODE §2.2：不再「撞错才知道」） -->
      <div class="cli-probe-card">
        <div class="cli-probe-head">
          <span class="cli-probe-name">{{ probe?.display_name || status?.config?.engine_id || '—' }}</span>
          <span v-if="probe?.available" class="cli-probe-state is-ok">✓ {{ t('settings.cliengine_all_ok') }}</span>
          <span v-else-if="probe" class="cli-probe-state is-fail">✗ {{ t('settings.cliengine_failed', { stage: stageLabel(probe.failed_stage) }) }}</span>
        </div>
        <div class="cli-probe-stages" role="list">
          <div class="cp-stage" :class="stageClass('path')" role="listitem">
            <span class="cp-no">①</span>{{ t('settings.cliengine_stage_path') }}
            <span class="cp-detail">{{ probe?.path || '—' }}</span>
          </div>
          <div class="cp-arrow" aria-hidden="true">→</div>
          <div class="cp-stage" :class="stageClass('version')" role="listitem">
            <span class="cp-no">②</span>{{ t('settings.cliengine_stage_version') }}
            <span class="cp-detail">{{ probe?.version || '—' }}</span>
          </div>
          <div class="cp-arrow" aria-hidden="true">→</div>
          <div class="cp-stage" :class="stageClass('login')" role="listitem">
            <span class="cp-no">③</span>{{ t('settings.cliengine_stage_login') }}
            <span class="cp-detail">{{ probe?.logged_in ? t('settings.cliengine_logged_in') : t('settings.cliengine_not_logged_in') }}</span>
          </div>
        </div>
        <p v-if="probe && !probe.available && probe.hint" class="cli-probe-hint">▸ {{ t('ai-panel.' + probeHintKey) }}</p>
      </div>

      <!-- 配置面（显式保存；engine.mode 唯一写入口仍在接入方式决策卡） -->
      <div class="settings-field">
        <label class="settings-label">{{ t('settings.cliengine_enabled') }}</label>
        <div
          class="wm-toggle"
          :class="{ 'is-on': form.enabled }"
          role="switch"
          :aria-checked="form.enabled"
          tabindex="0"
          @click="form.enabled = !form.enabled"
          @keydown.enter.prevent="form.enabled = !form.enabled"
          @keydown.space.prevent="form.enabled = !form.enabled"
        ></div>
      </div>
      <div class="settings-field">
        <label class="settings-label">{{ t('settings.cliengine_engine') }}</label>
        <select v-model="form.engine_id" class="settings-input">
          <option v-for="e in ENGINES" :key="e.id" :value="e.id">{{ e.label }}</option>
        </select>
      </div>
      <div class="settings-field">
        <label class="settings-label">{{ t('settings.cliengine_tier') }}</label>
        <select v-model="form.auth_tier" class="settings-input">
          <option value="readonly">{{ t('settings.cliengine_tier_readonly') }}</option>
          <option value="workspace_write">{{ t('settings.cliengine_tier_workspace_write') }}</option>
          <option value="full_task">{{ t('settings.cliengine_tier_full_task') }}</option>
        </select>
      </div>
      <div class="settings-field">
        <label class="settings-label">{{ t('settings.cliengine_cli_path') }}</label>
        <input v-model="form.cli_path_override" class="settings-input" placeholder="qoder" />
      </div>
      <div class="settings-actions">
        <button class="btn btn-primary" :disabled="saving" @click="onSave">{{ saving ? t('settings.engine_saving') : t('settings.save') }}</button>
        <span v-if="saveMessage" class="cli-save-msg" :class="{ 'is-error': saveError }">{{ saveMessage }}</span>
      </div>
      <p class="settings-section-desc" style="margin-top:var(--s-4)">{{ t('settings.cliengine_orthogonal_note') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * CLI 引擎设置页（REQ-EXPERT-MODE §2.2 · L4 层前置回显）
 *
 * 智能体模式的算力提供者是本机 CLI 引擎（chat_engine 命名空间），与 access_mode 正交。
 * 探针三段：① 可执行路径解析 → ② --version 版本下限 → ③ status 登录态。
 * 状态常驻回显：失败段位直接可见（AC-4），不再「撞错才知道」。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchChatEngineStatus, saveSettings, type ChatEngineProbe } from '@/api/settings'

const { t } = useI18n()

const ENGINES = [
  { id: 'qoder-cli', label: 'Qoder CLI' },
  { id: 'qoder-cli-cn', label: 'Qoder CLI（国内版）' },
]

const probe = ref<ChatEngineProbe | null>(null)
const status = ref<Awaited<ReturnType<typeof fetchChatEngineStatus>> | null>(null)
const saving = ref(false)
const saveMessage = ref('')
const saveError = ref(false)

const form = reactive({
  enabled: false,
  engine_id: 'qoder-cli',
  auth_tier: 'readonly',
  cli_path_override: '',
})

async function load() {
  try {
    status.value = await fetchChatEngineStatus()
    probe.value = status.value.probe ?? null
    const c = status.value.config
    if (c) {
      form.enabled = !!c.enabled
      form.engine_id = c.engine_id || 'qoder-cli'
      form.auth_tier = c.auth_tier || 'readonly'
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
        auth_tier: form.auth_tier,
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

<style scoped>
.cli-panel { max-width: 720px; }
.cli-probe-card { border: 1px solid var(--border); border-radius: var(--radius); padding: var(--s-3) var(--s-4); margin-bottom: var(--s-4); background: var(--surface); }
.cli-probe-head { display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; }
.cli-probe-name { font-size: 13px; font-weight: 600; }
.cli-probe-state { font-size: 12px; border-radius: 999px; padding: 1px 8px; }
.cli-probe-state.is-ok { color: var(--ok); background: var(--ok-soft); }
.cli-probe-state.is-fail { color: var(--warn); background: var(--warn-soft); }
.cli-probe-stages { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: var(--s-2); }
.cp-stage { display: flex; flex-direction: column; font-size: 12px; border: 1px solid var(--border); border-radius: 7px; padding: 4px 10px; color: var(--muted); }
.cp-stage .cp-detail { font-family: var(--font-mono); font-size: 12px; color: var(--subtle); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cp-stage.is-ok { border-color: oklch(from var(--ok) l c h / .4); color: var(--ok); }
.cp-stage.is-fail { border-color: oklch(from var(--warn) l c h / .5); color: var(--warn); font-weight: 600; }
.cp-stage.is-unknown { opacity: .55; }
.cp-arrow { color: var(--subtle); font-size: 12px; }
.cli-probe-hint { font-size: 12px; color: var(--warn); margin: 6px 0 0; }
.cli-save-msg { font-size: 12px; color: var(--ok); align-self: center; }
.cli-save-msg.is-error { color: var(--error); }
.wm-toggle { width: 38px; height: 22px; border-radius: 999px; background: var(--border-strong); position: relative; cursor: pointer; transition: background .15s; display: inline-block; }
.wm-toggle::after { content: ""; position: absolute; width: 18px; height: 18px; border-radius: 50%; background: #fff; top: 2px; left: 2px; transition: left .15s; }
.wm-toggle.is-on { background: var(--accent); }
.wm-toggle.is-on::after { left: 18px; }
</style>
