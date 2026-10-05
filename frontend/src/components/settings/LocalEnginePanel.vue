<template>
  <div class="cc-panel">
    <div class="cc-page-head">
      <h1 class="cc-page-title">{{ t('settings.compute.engine_title') }}</h1>
      <p class="cc-page-lead">{{ t('settings.compute.engine_lead') }}</p>
    </div>

    <!-- 引擎开关 -->
    <div class="cc-card">
      <div class="cc-card-head">
        <div>
          <h2 class="cc-card-title">{{ t('settings.compute.engine_switch') }}</h2>
          <p class="cc-card-desc">{{ t('settings.compute.engine_switch_desc') }}</p>
        </div>
        <label class="cc-switch">
          <input type="checkbox" :checked="isRunning" :disabled="busy || !(canManage)" @change="onToggleEngine" />
          <span class="cc-switch-track"></span>
        </label>
      </div>
      <div class="cc-row cc-row-first">
        <div>
          <div class="cc-row-main">{{ t('settings.compute.engine_running') }}</div>
          <div class="cc-row-sub">{{ runningSub }}</div>
        </div>
        <div class="cc-row-side">
          <span class="cc-pill" :class="isRunning ? 'cc-pill-ok' : 'cc-pill-idle'"><span v-if="isRunning" class="cc-dot"></span>{{ isRunning ? t('settings.compute.engine_running_yes') : t('settings.compute.engine_running_no') }}</span>
        </div>
      </div>
      <dl class="cc-kv">
        <dt>{{ t('settings.compute.engine_mode_ro') }}</dt><dd>{{ engineModeLabel }} <span class="cc-note">（{{ t('settings.engine_mode_readonly') }}）</span></dd>
        <dt>{{ t('settings.engine_local_ready') }}</dt><dd :class="localReady ? 'cc-pill-ok' : 'cc-pill-warn'" style="text-align:right">{{ localReady ? t('settings.engine_local_ready_yes') : t('settings.engine_local_ready_no') }}</dd>
        <dt>{{ t('settings.compute.engine_coldstart') }}</dt><dd>{{ t('settings.compute.engine_coldstart_val') }}</dd>
      </dl>
    </div>

    <!-- 模型清单 -->
    <div class="cc-card">
      <div class="cc-card-head">
        <div>
          <h2 class="cc-card-title">{{ t('settings.compute.model_manifest') }}</h2>
          <p class="cc-card-desc">{{ t('settings.compute.model_manifest_desc') }}</p>
        </div>
        <span class="cc-demo-tag">{{ t('settings.compute.size_real') }}</span>
      </div>

      <div class="cc-storage-controls">
        <input v-model="storageDraft" class="cc-input cc-input-mono" :disabled="!canManage" />
        <button v-if="canManage" class="cc-btn cc-btn-secondary cc-btn-sm" :disabled="storageSaving || storageDraft === engineStore.overview?.model_dir" @click="onSaveStorage">{{ t('settings.engine_storage_save') }}</button>
      </div>
      <div class="cc-disk-hint" :class="{ 'is-short': diskShort }">
        <span>{{ t('settings.engine_disk_free', { size: fmtBytes(engineStore.overview?.disk_free_bytes || 0) }) }}</span>
        <span v-if="diskShort" class="cc-disk-short">{{ t('settings.engine_disk_short') }}</span>
      </div>

      <div v-if="!engineStore.overview" class="cc-note" style="padding:var(--s-3) 0">{{ t('common.loading') }}</div>
      <table v-else class="cc-table">
        <thead>
          <tr><th>{{ t('settings.compute.col_model') }}</th><th>{{ t('settings.compute.col_size') }}</th><th>{{ t('settings.compute.col_status') }}</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="m in engineStore.overview.models" :key="m.key">
            <td>
              <div class="cc-row-main">{{ m.name }}<span v-if="m.optional" class="cc-opt-tag">{{ t('settings.engine_model_optional') }}</span></div>
              <div class="cc-note-mono">{{ m.modelscope_id }}</div>
              <div v-if="m.status === 'downloading' && m.job" class="cc-model-progress">
                <div class="cc-progress-bar"><div class="cc-progress-fill" :style="{ width: m.job.percent + '%' }"></div></div>
                <span class="cc-progress-pct">{{ m.job.percent }}%</span>
                <span class="cc-progress-meta">{{ fmtSpeed(m.job.speed_bps) }}</span>
                <span v-if="m.job.eta_seconds != null" class="cc-progress-meta">{{ t('settings.engine_progress_eta', { eta: fmtDuration(m.job.eta_seconds) }) }}</span>
                <button v-if="canManage" class="cc-btn cc-btn-secondary cc-btn-sm" :disabled="busyKey === m.job.id" @click="onCancel(m.job.id)">{{ t('settings.engine_action_cancel') }}</button>
              </div>
            </td>
            <td class="cc-num-col">{{ fmtBytes(m.size_bytes) }}</td>
            <td>
              <span class="cc-pill" :class="statusPill(m.status)"><span v-if="m.status === 'ready'" class="cc-dot"></span>{{ t(`settings.engine_model_status_${m.status}`) }}</span>
            </td>
            <td>
              <div v-if="canManage && m.status !== 'downloading'" class="cc-model-actions">
                <button v-if="m.status === 'not_downloaded' || m.status === 'missing'" class="cc-btn cc-btn-secondary cc-btn-sm" :disabled="busyKey === m.key" @click="onDownload(m.key)">{{ t('settings.engine_action_download') }}</button>
                <button v-else-if="m.status === 'partial'" class="cc-btn cc-btn-secondary cc-btn-sm" :disabled="busyKey === m.key" @click="onDownload(m.key)">{{ t('settings.engine_action_resume') }}</button>
                <button v-else-if="m.status === 'ready'" class="cc-btn cc-btn-ghost cc-btn-sm" :disabled="busyKey === m.key" @click="onVerify(m.key)">{{ t('settings.engine_action_verify') }}</button>
                <button v-else-if="m.status === 'tampered'" class="cc-btn cc-btn-secondary cc-btn-sm" :disabled="busyKey === m.key" @click="onDownload(m.key)">{{ t('settings.engine_action_redownload') }}</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-for="j in failedJobs" :key="j.id" class="cc-job-failed">⚠ {{ jobErrorText(j) }}</div>

      <div class="cc-divider"></div>
      <div class="cc-quota-row">
        <div class="cc-quota-figure">{{ fmtBytes(engineStore.overview?.total_size_required_bytes || 0) }}<span> {{ t('settings.compute.required') }}</span></div>
        <div class="cc-btn-row">
          <button v-if="canManage" class="cc-btn cc-btn-primary cc-btn-sm" :disabled="busyKey === 'all' || engineStore.isDownloading" @click="onDownload('all')">{{ t('settings.engine_download_all') }}</button>
          <button class="cc-btn cc-btn-secondary cc-btn-sm" :disabled="engineStore.overviewLoading" @click="onRefreshAll">{{ t('settings.engine_refresh') }}</button>
        </div>
      </div>
    </div>

    <LocalEngineGuideDialog
      :open="guideOpen"
      :disk-free-bytes="engineStore.overview?.disk_free_bytes ?? 0"
      :disk-required-bytes="engineStore.overview?.total_size_required_bytes ?? 0"
      :disk-buffer-bytes="DISK_BUFFER_BYTES"
      :missing="engineStore.requiredNotReady"
      :tampered="engineStore.tamperedModels"
      @close="guideOpen = false"
      @download-all="onGuideDownloadAll"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 本地引擎面板（REQ-COMPUTE-CENTER）：引擎开关 + 模型清单资产面。
 * 从 SettingsView 迁移而来，复用 engineStore 的下载/校验/启停/存储与切换事务；
 * 引擎模式为只读回显（唯一写入口仍是来源选择/离线切换）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEngineStore } from '@/stores/engine'
import { useUserStore } from '@/stores/user'
import type { DownloadJob } from '@/api/engine'
import LocalEngineGuideDialog from '@/components/modals/LocalEngineGuideDialog.vue'
import { showToast } from '@/composables/useToast'

const { t } = useI18n()
const engineStore = useEngineStore()
const userStore = useUserStore()

const DISK_BUFFER_BYTES = 500 * 1024 * 1024
const busyKey = ref('')
const busy = ref(false)
const guideOpen = ref(false)
const storageDraft = ref('')
const storageSaving = ref(false)

const canManage = computed(() => userStore.isAdmin || engineStore.canManage)
const isRunning = computed(() => engineStore.status?.process_running === true)
const localReady = computed(() => engineStore.status?.local_ready === true)
const diskShort = computed(() => {
  const o = engineStore.overview
  if (!o) return false
  return o.disk_free_bytes < o.total_size_required_bytes + DISK_BUFFER_BYTES
})
const failedJobs = computed(() => engineStore.jobs.filter(j => j.state === 'failed'))
const runningSub = computed(() => isRunning.value
  ? t('settings.engine_process_running', { pid: engineStore.status?.pid ?? '-' })
  : t('settings.engine_process_stopped'))

const engineModeLabel = computed(() => {
  const mode = engineStore.status?.mode || ''
  if (mode === 'local') return t('settings.engine_mode_local')
  if (mode === 'proxy' || mode === 'cloud') return t('settings.engine_mode_proxy')
  if (mode === 'direct') return t('settings.engine_mode_direct')
  return mode || '—'
})

watch(() => engineStore.overview?.model_dir, (dir) => {
  if (dir && !storageSaving.value) storageDraft.value = dir
}, { immediate: true })

function statusPill(s: string): string {
  if (s === 'ready') return 'cc-pill-ok'
  if (s === 'downloading') return 'cc-pill-accent'
  if (s === 'partial' || s === 'tampered' || s === 'missing') return 'cc-pill-warn'
  return 'cc-pill-idle'
}
function fmtBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`
}
function fmtSpeed(bps: number): string { return `${fmtBytes(bps)}/s` }
function fmtDuration(sec: number): string {
  if (sec == null || !isFinite(sec)) return '—'
  if (sec < 60) return `${Math.max(1, Math.round(sec))}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}m${Math.round(sec % 60)}s`
  return `${Math.floor(sec / 3600)}h${Math.round((sec % 3600) / 60)}m`
}
function engineErrText(code?: string | null, error?: string | null): string {
  const map: Record<string, string> = {
    insufficient_disk: 'settings.engine_err_insufficient_disk',
    unwritable_dir: 'settings.engine_err_unwritable_dir',
    unknown_model: 'settings.engine_err_unknown_model',
    models_tampered: 'settings.engine_err_models_tampered',
    models_missing: 'settings.engine_err_models_missing',
    download_failed: 'settings.engine_err_download_failed',
  }
  const key = code ? map[code] : undefined
  if (key) return t(key)
  return t('settings.engine_err_generic', { error: error || code || '-' })
}
function jobErrorText(j: DownloadJob): string { return engineErrText(j.error_code, j.error) }

async function onDownload(key: string) {
  busyKey.value = key
  try {
    const r = await engineStore.download(key)
    if (!r.ok) showToast(engineErrText(r.error_code, r.error), 'error')
  } catch (e) {
    showToast(engineErrText(null, String(e)), 'error')
  } finally {
    busyKey.value = ''
  }
}
async function onCancel(jobId: string) {
  busyKey.value = jobId
  try {
    const r = await engineStore.cancel(jobId)
    if (!r.ok) showToast(engineErrText(r.error_code, r.error), 'error')
  } finally {
    busyKey.value = ''
  }
}
async function onVerify(key: string) {
  busyKey.value = key
  try {
    const r = await engineStore.verify(key)
    if (r.ok && r.status !== 'tampered') showToast(t('settings.engine_verify_ok'), 'success')
    else if (r.status === 'tampered') showToast(t('settings.engine_verify_tampered'), 'error')
    else showToast(engineErrText(r.error_code, r.error), 'error')
  } finally {
    busyKey.value = ''
  }
}
async function onSaveStorage() {
  const dir = storageDraft.value.trim()
  if (!dir) return
  storageSaving.value = true
  try {
    const r = await engineStore.saveStorage(dir)
    if (r.ok) showToast(t('settings.engine_storage_saved'), 'success')
    else showToast(engineErrText(r.error_code, r.error), 'error')
  } catch {
    showToast(t('settings.engine_storage_failed'), 'error')
  } finally {
    storageSaving.value = false
  }
}
async function onToggleEngine() {
  busy.value = true
  try {
    if (isRunning.value) {
      const r = await engineStore.stop()
      if (r.ok) showToast(t('settings.engine_stopped'), 'success')
      else showToast(engineErrText(r.error_code, r.error), 'error')
    } else {
      const r = await engineStore.start()
      if (r.ok) showToast(t('settings.engine_started'), 'success')
      else if (r.error_code === 'models_tampered' || r.error_code === 'models_missing') {
        await engineStore.loadOverview(true)
        guideOpen.value = true
      } else showToast(engineErrText(r.error_code, r.error), 'error')
    }
  } catch (e) {
    showToast(t('settings.engine_start_failed'), 'error')
    void e
  } finally {
    busy.value = false
  }
}
function onGuideDownloadAll() { guideOpen.value = false; onDownload('all') }

/** [状态同步] 回读引擎状态：进程存活/PID 只在 status 里，overview 轮询不会刷新它 */
async function refreshEngineStatus() {
  try { await engineStore.load(true) } catch { /* store 内部已静默降级 */ }
}
function onRefreshAll() {
  engineStore.loadOverview(true)
  refreshEngineStatus()
}

onMounted(() => {
  // force：SettingsView 挂载时已 load() 过一次，此处不吃 loaded 守卫的快照，
  // 否则子进程在设置页打开后被重启／退出时，面板会一直停在旧 PID 上。
  refreshEngineStatus()
  engineStore.loadOverview(true)
})
</script>

<style src="./compute.css"></style>
<style scoped>
.cc-storage-controls { display: flex; align-items: center; gap: var(--s-2); margin-bottom: var(--s-2); }
.cc-disk-hint { display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; font-size: 12px; color: var(--muted); margin-bottom: var(--s-3); }
.cc-disk-hint.is-short { color: var(--warn); }
.cc-disk-short { font-weight: 600; }
.cc-opt-tag { font-size: 10px; color: var(--muted); background: var(--surface-2); border: 1px solid var(--border); padding: 1px 6px; border-radius: 999px; margin-left: 6px; }
.cc-model-progress { display: flex; align-items: center; gap: var(--s-2); margin-top: 6px; flex-wrap: wrap; }
.cc-progress-bar { flex: 1; min-width: 120px; height: 6px; background: var(--surface-2); border-radius: 999px; overflow: hidden; }
.cc-progress-fill { height: 100%; background: var(--accent); border-radius: 999px; transition: width 0.3s ease; }
.cc-progress-pct { font-size: 12px; font-weight: 600; font-family: var(--font-mono); color: var(--accent); }
.cc-progress-meta { font-size: 11px; color: var(--muted); font-family: var(--font-mono); }
.cc-model-actions { display: flex; gap: var(--s-2); }
.cc-job-failed { display: flex; gap: 6px; font-size: 12px; color: var(--error); margin-top: var(--s-2); line-height: 1.5; }
</style>
