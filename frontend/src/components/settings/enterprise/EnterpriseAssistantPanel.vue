<script setup lang="ts">
/**
 * Settings 分区 A「本机录音助手」（UI 规格 §2，档⑦）
 *
 * 三态：已连接已绑定（绿）/ 助手在线未绑定（配对引导）/ 不在场（下载引导，不报错）。
 * W4-03 规则：一切设备面动作前先 ensureLocalPlane 判可达，不发注定失败的请求。
 * 助手地址覆盖（W4-02 实连）：写入 scopedKey 用户命名空间 + 失效重探测。
 */
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ensureLocalPlane, localPlaneError, pairedUserId, setLocalOriginOverride, invalidateLocalPlane } from '@/api/origins'
import { useUserStore } from '@/stores/user'
import { createPairing, listDevices, deleteDevice, type DeviceInfo, type PairingResult } from '@/api/pairings'
import { getLocalState, getLocalStorage, migrateLocalStorage, type AssistantState, type LocalStorageInfo } from '@/api/assistant'

const { t } = useI18n()
const userStore = useUserStore()

const probing = ref(true)
const reachable = ref(false)
const paired = ref(false)
const state = ref<AssistantState | null>(null)
const devices = ref<DeviceInfo[]>([])
const pairing = ref<PairingResult | null>(null)
const overrideInput = ref('')
const notice = ref('')
const storage = ref<LocalStorageInfo | null>(null)
const showAdvanced = ref(false)
const migrating = ref(false)
const migrateTarget = ref('')
const migrateConfirm = ref(false)
const migrateDone = ref(false)

async function probe() {
  probing.value = true
  notice.value = ''
  await ensureLocalPlane(userStore.user?.id ?? null)
  reachable.value = !localPlaneError()
  if (reachable.value) {
    state.value = await getLocalState()
    paired.value = !!state.value?.paired || !!pairedUserId()
    if (state.value) {
      try { devices.value = await listDevices() } catch { devices.value = [] }
      storage.value = await getLocalStorage()
    } else {
      reachable.value = false
    }
  }
  probing.value = false
}
onMounted(probe)

function fmtSize(n: number | null | undefined): string {
  if (n == null) return '—'
  const gb = n / 1024 ** 3
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${Math.max(1, Math.round(n / 1024 ** 2))} MB`
}

async function revoke(d: DeviceInfo) {
  try {
    await deleteDevice(d.device_id)
    devices.value = devices.value.filter(x => x.device_id !== d.device_id)
  } catch { notice.value = t('login.enterprise.err_service_error', { status: '-' }) }
}

async function runMigrate() {
  if (migrating.value || !migrateTarget.value.trim()) return
  migrating.value = true
  migrateDone.value = false
  try {
    const r = await migrateLocalStorage(migrateTarget.value.trim())
    migrateDone.value = true
    migrateConfirm.value = false
    storage.value = await getLocalStorage()
    void r
  } catch (err) {
    const status = (err as { response?: { status?: number } })?.response?.status
    notice.value = status === 422 ? t('enterprise.settings.assistant.migrate_rejected') : t('login.enterprise.err_service_error', { status: status ?? '-' })
  } finally { migrating.value = false }
}

async function generatePairing() {
  pairing.value = null
  try { pairing.value = await createPairing() } catch { notice.value = t('login.enterprise.err_service_error', { status: '-' }) }
}

async function saveOverride() {
  const uid = userStore.user?.id ?? null
  if (!uid) return
  const url = overrideInput.value.trim()
  setLocalOriginOverride(uid, url || null)
  invalidateLocalPlane()
  notice.value = t('enterprise.settings.assistant.override_saved')
  await probe()
}

</script>

<template>
  <div class="ap-root">
    <h2>{{ t('enterprise.settings.assistant.title') }}</h2>

    <div v-if="probing" class="ap-state">{{ t('enterprise.settings.assistant.probing') }}</div>

    <!-- 已连接 -->
    <div v-else-if="reachable" class="ap-card is-on">
      <div class="ap-dot is-on" aria-hidden="true"></div>
      <div class="ap-card-body">
        <div class="ap-state">
          {{ state?.paired || paired
            ? t('enterprise.settings.assistant.connected_paired', { name: userStore.displayName })
            : t('enterprise.settings.assistant.connected_unpaired') }}
        </div>
        <div class="ap-sub">{{ t('enterprise.settings.assistant.paired_as', { name: state?.paired_user_id || '' }) }}</div>
        <template v-if="!(state?.paired || paired)">
          <p class="ap-hint">{{ t('enterprise.settings.assistant.unpaired_desc') }}</p>
          <button class="ap-btn" @click="generatePairing">{{ t('enterprise.settings.assistant.pairing_generate') }}</button>
        </template>
        <div v-if="pairing" class="ap-pairing" role="status">
          <code class="ap-code">{{ pairing.pairing_code }}</code>
          <p class="ap-sub">{{ t('enterprise.settings.assistant.pairing_hint', { minutes: pairing.expires_in_minutes }) }}</p>
        </div>
        <div v-if="storage" class="ap-storage">
          <div class="ap-sub">{{ t('enterprise.settings.assistant.storage_dir', { dir: storage.data_dir }) }}</div>
          <div class="ap-sub">{{ t('enterprise.settings.assistant.storage_used', { used: fmtSize(storage.total_bytes), free: fmtSize(storage.disk_free_bytes) }) }} · {{ t('enterprise.settings.assistant.storage_tasks', { n: storage.tasks_files }) }}</div>
          <button class="ap-btn is-ghost" @click="migrateConfirm = true; migrateDone = false">{{ t('enterprise.settings.assistant.migrate_btn') }}</button>
          <p class="ap-sub">{{ t('enterprise.settings.assistant.migrate_note') }}</p>
        </div>
        <details class="ap-advanced" :open="showAdvanced" @toggle="showAdvanced = ($event.target as HTMLDetailsElement).open">
          <summary>{{ t('enterprise.settings.assistant.advanced') }}</summary>
          <div class="ap-override">
            <input v-model="overrideInput" :placeholder="t('enterprise.settings.assistant.override_label')" autocomplete="off">
            <button class="ap-btn is-ghost" @click="saveOverride">{{ t('enterprise.settings.assistant.override_save') }}</button>
          </div>
        </details>
        <div v-if="(state?.paired || paired) && devices.length > 1" class="ap-devices">
          <div class="ap-devices-title">{{ t('enterprise.settings.assistant.devices_title') }}</div>
          <div v-for="d in devices" :key="d.device_id" class="ap-device-row">
            <span>{{ d.device_name }}</span>
            <span class="ap-sub">{{ d.last_used_at ? d.last_used_at.slice(0, 10) : '—' }}</span>
            <button class="ap-link is-danger" @click="revoke(d)">{{ t('enterprise.settings.assistant.device_revoke') }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 不在场：引导（不报错、不丢字；无助手设备"可看可编辑不可录音"即默认形态） -->
    <div v-else class="ap-card is-off">
      <div class="ap-dot is-off" aria-hidden="true"></div>
      <div class="ap-card-body">
        <div class="ap-state">{{ t('enterprise.settings.assistant.disconnected') }}</div>
        <p class="ap-hint">{{ t('enterprise.settings.assistant.disconnected_hint') }}</p>
        <div class="ap-download">
          <div class="ap-download-title">{{ t('enterprise.settings.assistant.download_title') }}</div>
          <p class="ap-sub">{{ t('enterprise.settings.assistant.download_hint') }}</p>
        </div>
        <div class="ap-override">
          <input v-model="overrideInput" :placeholder="t('enterprise.settings.assistant.override_label')" autocomplete="off">
          <button class="ap-btn is-ghost" @click="saveOverride">{{ t('enterprise.settings.assistant.override_save') }}</button>
          <button class="ap-btn is-ghost" @click="probe">{{ t('enterprise.settings.assistant.reprobe') }}</button>
        </div>
        <p v-if="notice" class="ap-sub" role="status">{{ notice }}</p>
      </div>
    </div>
    <!-- 迁移确认/完成弹窗（产品 cmsg_01m63k7hhh7pgjxsg39cq3ka8t 措辞 1-2 逐字） -->
    <div v-if="migrateConfirm" class="ap-mask">
      <div class="ap-modal" role="alertdialog" aria-modal="true">
        <p class="ap-hint">{{ t('enterprise.settings.assistant.migrate_confirm') }}</p>
        <input v-model="migrateTarget" :placeholder="t('enterprise.settings.assistant.migrate_target')" class="ap-modal-input">
        <div class="ap-modal-actions">
          <button class="ap-btn" :disabled="migrating || !migrateTarget.trim()" @click="runMigrate">{{ t('enterprise.settings.assistant.migrate_btn') }}</button>
          <button class="ap-btn is-ghost" @click="migrateConfirm = false">{{ t('topbar.abandon_cancel') }}</button>
        </div>
      </div>
    </div>
    <div v-if="migrateDone" class="ap-mask">
      <div class="ap-modal" role="status">
        <p class="ap-hint">{{ t('enterprise.settings.assistant.migrate_done') }}</p>
        <div class="ap-modal-actions"><button class="ap-btn" @click="migrateDone = false">{{ t('common.action.close') }}</button></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ap-root { display: flex; flex-direction: column; gap: var(--s-3, 16px); max-width: 640px; }
.ap-root h2 { font-size: 15px; margin: 0; }
.ap-card { display: flex; gap: var(--s-3, 16px); padding: var(--s-3, 16px); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); background: var(--surface, #fff); }
.ap-dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 5px; flex: none; }
.ap-dot.is-on { background: var(--accent, #2a6); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent, #2a6) 20%, transparent); }
.ap-dot.is-off { background: var(--surface-3, #ccc); }
.ap-card-body { display: flex; flex-direction: column; gap: var(--s-2, 8px); }
.ap-state { font-weight: 600; font-size: var(--fs-13, 13px); }
.ap-hint, .ap-sub { font-size: var(--fs-12, 12px); color: var(--muted, #666); margin: 0; }
.ap-btn { align-self: flex-start; padding: 7px 14px; border: none; border-radius: var(--radius-sm, 8px); background: var(--accent, #2a6); color: var(--accent-fg, #fff); cursor: pointer; font-size: var(--fs-12, 12px); font-weight: 600; }
.ap-btn.is-ghost { background: none; border: 1px solid var(--border, #d8d8d4); color: var(--fg, #222); font-weight: 400; }
.ap-pairing { margin-top: var(--s-2, 8px); }
.ap-code { display: block; padding: 10px 12px; background: var(--surface-2, #f4f4f2); border-radius: var(--radius-sm, 8px); font-family: var(--font-mono, monospace); font-size: 16px; letter-spacing: 2px; user-select: all; }
.ap-devices { margin-top: var(--s-2, 8px); border-top: 1px dashed var(--border, #eee); padding-top: var(--s-2, 8px); }
.ap-devices-title { font-size: var(--fs-12, 12px); font-weight: 600; margin-bottom: 4px; }
.ap-device-row { display: flex; gap: var(--s-2, 8px); align-items: center; font-size: var(--fs-12, 12px); }
.ap-download { border: 1px dashed var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); padding: var(--s-2, 12px); }
.ap-download-title { font-size: var(--fs-12, 12px); font-weight: 600; margin-bottom: 4px; }
.ap-override { display: flex; gap: var(--s-2, 8px); align-items: center; flex-wrap: wrap; }
.ap-override input { flex: 1; min-width: 200px; padding: 7px 10px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); font-size: var(--fs-12, 12px); }
.ap-link { border: none; background: none; padding: 0; cursor: pointer; color: var(--accent, #2a6); font-size: var(--fs-12, 12px); text-align: left; }
.ap-link.is-danger { color: var(--warn, #c33); }
.ap-storage { display: flex; flex-direction: column; gap: 4px; border-top: 1px dashed var(--border, #eee); padding-top: var(--s-2, 8px); }
.ap-advanced { font-size: var(--fs-12, 12px); color: var(--muted, #666); }
.ap-advanced summary { cursor: pointer; }
.ap-mask { position: fixed; inset: 0; background: rgb(0 0 0 / 0.35); display: grid; place-items: center; z-index: var(--z-toast, 1200); }
.ap-modal { width: min(420px, calc(100vw - 32px)); background: var(--surface, #fff); border-radius: var(--radius-sm, 8px); padding: var(--s-3, 24px); box-shadow: 0 16px 48px rgb(0 0 0 / 0.2); }
.ap-modal-input { width: 100%; margin-top: var(--s-2, 8px); padding: 8px 10px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); box-sizing: border-box; font-size: var(--fs-12, 12px); }
.ap-modal-actions { display: flex; gap: var(--s-2, 8px); margin-top: var(--s-3, 16px); }
</style>
