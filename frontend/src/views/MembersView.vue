<script setup lang="ts">
/**
 * 成员管理页（/members，P1-WP-4，UI 规格 §2 管理员形态）
 *
 * 仅团队管理员渲染操作面；非管理员/私有空间直链=中性提示态非空白（窗口D 收口口径同形态直生）。
 * 操作集：添加成员（§8.5 搜索多选批量）、改角色（只读↔可编辑）、移出（保留其已公开内容——
 * 信任模型"发出去的话不因离场而消失"，文案如实）、转让管理员（二次确认）、归档团队
 * （输入团队名确认；文案规格逐字=裁决④"归档非毁灭"）。
 * 最后一名 admin 守护/转让单事务由服务端权威（409 last_admin 明示文案承接）。
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSpaceStore } from '@/stores/space'
import { useContextsStore } from '@/stores/contexts'
import {
  addTeamMembers, archiveTeam, removeTeamMember, searchUsers, setMemberRole, transferTeamAdmin,
  type TeamMember, type UserSearchHit,
} from '@/api/teams'
import { showToast } from '@/composables/useToast'

const { t } = useI18n()
const space = useSpaceStore()
const contexts = useContextsStore()

const members = ref<TeamMember[]>([])
const loading = ref(true)
const busy = ref(false)
const actionError = ref('')

const isAdmin = computed(() => space.isTeamSpace && space.isTeamAdmin)
const teamName = computed(() => space.currentSpaceName)

async function refresh() {
  loading.value = true
  try {
    members.value = await space.loadMembers(space.currentId)
    await space.loadTeams()
  } finally { loading.value = false }
}
onMounted(async () => {
  await space.ensureReady()
  await refresh()
})

function roleLabel(m: TeamMember): string {
  if (m.role === 'admin') return t('enterprise.space.role_admin')
  if (m.role === 'editor') return t('enterprise.space.role_editor')
  return t('enterprise.space.role_viewer')
}
function joined(m: TeamMember): string {
  return m.joined_at ? m.joined_at.slice(0, 10) : '—'
}

async function changeRole(m: TeamMember, role: 'viewer' | 'editor') {
  if (busy.value) return
  busy.value = true
  actionError.value = ''
  try {
    await setMemberRole(space.currentId, m.user_id, role)
    await refresh()
  } catch {
    actionError.value = t('enterprise.members.err_action')
  } finally { busy.value = false }
}

/* 移出：行内两步确认（保留内容承诺随行显示） */
const pendingRemove = ref('')
async function confirmRemove(m: TeamMember) {
  if (busy.value) return
  busy.value = true
  actionError.value = ''
  try {
    await removeTeamMember(space.currentId, m.user_id)
    pendingRemove.value = ''
    showToast(t('enterprise.members.removed', { name: m.display_name }), 'success')
    await refresh()
  } catch {
    actionError.value = t('enterprise.members.err_action')
  } finally { busy.value = false }
}

/* 转让：选择对象后二次确认（规格 §2） */
const transferTo = ref('')
const pendingTransfer = ref(false)
const transferCandidates = computed(() => members.value.filter((m) => m.role !== 'admin'))
async function confirmTransfer() {
  if (busy.value || !transferTo.value) return
  busy.value = true
  actionError.value = ''
  try {
    await transferTeamAdmin(space.currentId, transferTo.value)
    pendingTransfer.value = false
    showToast(t('enterprise.members.transferred'), 'success')
    await refresh()
  } catch {
    // 最后一名守护等冲突由服务端 409 承载——转让对象至少含一名 admin 的形态由候选保证
    actionError.value = t('enterprise.members.err_action')
  } finally { busy.value = false }
}

/* 添加成员：搜索多选批量（D010 终态 {user_ids:[...]}） */
const addQuery = ref('')
const addHits = ref<UserSearchHit[]>([])
const addPicked = ref<UserSearchHit[]>([])
const addRole = ref<'viewer' | 'editor'>('editor')
let addTimer: ReturnType<typeof setTimeout> | null = null
function onAddQuery() {
  if (addTimer) clearTimeout(addTimer)
  const q = addQuery.value.trim()
  if (!q) { addHits.value = []; return }
  addTimer = setTimeout(async () => {
    try {
      const existing = new Set(members.value.map((m) => m.user_id))
      addHits.value = (await searchUsers(q)).filter((h) => !existing.has(h.user_id))
    } catch { addHits.value = [] }
  }, 250)
}
function toggleAdd(h: UserSearchHit) {
  const i = addPicked.value.findIndex((p) => p.user_id === h.user_id)
  if (i >= 0) addPicked.value.splice(i, 1)
  else addPicked.value.push(h)
}
async function submitAdd() {
  if (busy.value || !addPicked.value.length) return
  busy.value = true
  actionError.value = ''
  try {
    await addTeamMembers(space.currentId, addPicked.value.map((p) => p.user_id), addRole.value)
    addPicked.value = []
    addQuery.value = ''
    addHits.value = []
    showToast(t('enterprise.members.added'), 'success')
    await refresh()
  } catch {
    actionError.value = t('enterprise.members.err_action')
  } finally { busy.value = false }
}

/* 归档：输入团队名确认（裁决④非毁灭语义，文案规格逐字） */
const archiveOpen = ref(false)
const archiveInput = ref('')
const archiveCanConfirm = computed(() => archiveInput.value.trim() === teamName.value)
async function confirmArchive() {
  if (busy.value || !archiveCanConfirm.value) return
  busy.value = true
  try {
    await archiveTeam(space.currentId)
    archiveOpen.value = false
    archiveInput.value = ''
    showToast(t('enterprise.members.archived'), 'success')
    await space.loadTeams()
    void contexts.loadTasks()
  } catch {
    actionError.value = t('enterprise.members.err_action')
  } finally { busy.value = false }
}
</script>

<template>
  <div class="mb-root">
    <template v-if="space.isTeamSpace && isAdmin">
      <header class="mb-head">
        <h1>{{ t('enterprise.members.title', { name: teamName }) }}</h1>
      </header>
      <p v-if="actionError" class="mb-error" role="alert">{{ actionError }}</p>

      <p v-if="loading" class="mb-muted">{{ t('enterprise.library.loading') }}</p>
      <ul v-else class="mb-list">
        <li v-for="m in members" :key="m.user_id" class="mb-row">
          <div class="mb-info">
            <span class="mb-name">{{ m.display_name }}</span>
            <span class="mb-joined">{{ joined(m) }}</span>
          </div>
          <div class="mb-ops">
            <span v-if="m.role === 'admin'" class="mb-tag">{{ roleLabel(m) }}</span>
            <template v-else>
              <select
                class="mb-role"
                :value="m.role"
                :aria-label="t('enterprise.members.change_role_aria')"
                :disabled="busy"
                @change="changeRole(m, ($event.target as HTMLSelectElement).value as 'viewer' | 'editor')"
              >
                <option value="editor">{{ t('enterprise.space.role_editor') }}</option>
                <option value="viewer">{{ t('enterprise.space.role_viewer') }}</option>
              </select>
              <template v-if="pendingRemove !== m.user_id">
                <button type="button" class="mb-danger" :disabled="busy" @click="pendingRemove = m.user_id">{{ t('enterprise.members.remove_btn') }}</button>
              </template>
              <template v-else>
                <span class="mb-confirm">{{ t('enterprise.members.remove_confirm') }}</span>
                <button type="button" class="mb-ghost" :disabled="busy" @click="pendingRemove = ''">{{ t('common.action.cancel') }}</button>
                <button type="button" class="mb-danger" :disabled="busy" @click="confirmRemove(m)">{{ t('enterprise.members.remove_btn') }}</button>
              </template>
            </template>
          </div>
        </li>
      </ul>

      <section class="mb-add" aria-labelledby="mbAddTitle">
        <h2 id="mbAddTitle">{{ t('enterprise.members.add_title') }}</h2>
        <div class="mb-add-row">
          <input v-model="addQuery" type="search" :placeholder="t('enterprise.members.search_placeholder')" :aria-label="t('enterprise.members.search_placeholder')" @input="onAddQuery">
          <select v-model="addRole" :aria-label="t('enterprise.members.add_role_aria')">
            <option value="editor">{{ t('enterprise.space.role_editor') }}</option>
            <option value="viewer">{{ t('enterprise.space.role_viewer') }}</option>
          </select>
        </div>
        <p v-if="addPicked.length" class="mb-chips">
          <span v-for="h in addPicked" :key="h.user_id" class="mb-chip">
            {{ h.display_name }}
            <button type="button" class="mb-chip-x" :aria-label="t('enterprise.create.remove_member_aria')" @click="toggleAdd(h)">✕</button>
          </span>
        </p>
        <ul v-if="addHits.length" class="mb-hits" role="listbox">
          <li v-for="h in addHits" :key="h.user_id">
            <button type="button" role="option" class="mb-hit" :class="{ 'is-on': addPicked.some((p) => p.user_id === h.user_id) }" :aria-selected="addPicked.some((p) => p.user_id === h.user_id)" @click="toggleAdd(h)">{{ h.display_name }}</button>
          </li>
        </ul>
        <button type="button" class="mb-btn" :disabled="busy || !addPicked.length" @click="submitAdd">{{ t('enterprise.members.add_btn') }}</button>
      </section>

      <section class="mb-admin" aria-labelledby="mbAdminTitle">
        <h2 id="mbAdminTitle">{{ t('enterprise.members.admin_title') }}</h2>
        <div class="mb-admin-row">
          <select v-model="transferTo" class="mb-role" :aria-label="t('enterprise.members.transfer_aria')">
            <option value="">{{ t('enterprise.members.transfer_pick') }}</option>
            <option v-for="c in transferCandidates" :key="c.user_id" :value="c.user_id">{{ c.display_name }}</option>
          </select>
          <template v-if="!pendingTransfer">
            <button type="button" class="mb-btn" :disabled="busy || !transferTo" @click="pendingTransfer = true">{{ t('enterprise.members.transfer_btn') }}</button>
          </template>
          <template v-else>
            <span class="mb-confirm">{{ t('enterprise.members.transfer_confirm') }}</span>
            <button type="button" class="mb-ghost" :disabled="busy" @click="pendingTransfer = false">{{ t('common.action.cancel') }}</button>
            <button type="button" class="mb-btn" :disabled="busy" @click="confirmTransfer">{{ t('enterprise.members.transfer_btn') }}</button>
          </template>
        </div>
        <div class="mb-admin-row">
          <button type="button" class="mb-danger" :disabled="busy" @click="archiveOpen = !archiveOpen">{{ t('enterprise.members.archive_btn') }}</button>
        </div>
        <div v-if="archiveOpen" class="mb-archive">
          <p class="mb-archive-note">{{ t('enterprise.members.archive_note') }}</p>
          <input v-model="archiveInput" type="text" :placeholder="t('enterprise.members.archive_input_placeholder')" :aria-label="t('enterprise.members.archive_input_placeholder')">
          <div class="mb-archive-actions">
            <button type="button" class="mb-ghost" :disabled="busy" @click="archiveOpen = false; archiveInput = ''">{{ t('common.action.cancel') }}</button>
            <button type="button" class="mb-danger" :disabled="busy || !archiveCanConfirm" @click="confirmArchive">{{ t('enterprise.members.archive_btn') }}</button>
          </div>
        </div>
      </section>
    </template>

    <p v-else-if="!space.isTeamSpace" class="mb-muted">{{ t('enterprise.members.private_hint') }}</p>
    <p v-else class="mb-muted">{{ t('enterprise.members.not_admin_hint') }}</p>
  </div>
</template>

<style scoped>
.mb-root { max-width: 760px; margin: 0 auto; padding: calc(var(--s-3, 16px) * 1.5); color: var(--fg, #222); }
.mb-head h1 { font-size: 17px; margin: 0 0 var(--s-3, 14px); }
.mb-muted { color: var(--muted, #666); font-size: var(--fs-12, 12px); }
.mb-error { margin: 0 0 var(--s-2, 8px); color: var(--warn, #c33); font-size: var(--fs-12, 12px); }
.mb-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.mb-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; background: var(--surface, #fff); border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); padding: 9px 12px; flex-wrap: wrap; }
.mb-info { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.mb-name { font-size: var(--fs-13, 13px); font-weight: 600; }
.mb-joined { font-size: var(--fs-11, 11px); color: var(--subtle, #999); }
.mb-ops { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.mb-tag { font-size: var(--fs-11, 11px); color: var(--muted, #666); background: var(--surface-2, #f2f2f0); border-radius: 999px; padding: 1px 8px; }
.mb-role { padding: 4px 8px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); background: var(--surface, #fff); font-size: var(--fs-11, 11px); color: var(--fg, #222); }
.mb-confirm { font-size: var(--fs-11, 11px); color: var(--muted, #666); }
.mb-danger { border: none; background: none; color: var(--warn, #c33); font-size: var(--fs-11, 11px); cursor: pointer; padding: 2px 0; }
.mb-danger:hover { text-decoration: underline; }
.mb-danger:disabled { opacity: .5; cursor: not-allowed; }
.mb-ghost { border: none; background: none; color: var(--muted, #666); font-size: var(--fs-11, 11px); cursor: pointer; }
.mb-add, .mb-admin { margin-top: var(--s-4, 22px); padding-top: var(--s-3, 14px); border-top: 1px solid var(--border, #e6e6e2); display: flex; flex-direction: column; gap: 8px; }
.mb-add h2, .mb-admin h2 { margin: 0; font-size: var(--fs-13, 13px); }
.mb-add-row { display: flex; gap: 8px; }
.mb-add-row input { flex: 1; padding: 7px 10px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); background: var(--surface-2, #fafaf8); font-size: var(--fs-12, 12px); color: var(--fg, #222); }
.mb-chips { margin: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.mb-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px; background: var(--accent-soft, #eaf4ec); border: 1px solid var(--accent, #2a6); font-size: var(--fs-11, 11px); }
.mb-chip-x { border: none; background: none; cursor: pointer; color: var(--muted, #666); padding: 0; font-size: var(--fs-11, 11px); }
.mb-hits { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; max-height: 180px; overflow: auto; }
.mb-hit { display: block; width: 100%; text-align: left; padding: 6px 10px; border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); background: var(--surface-2, #fafaf8); font-size: var(--fs-12, 12px); cursor: pointer; color: var(--fg, #222); }
.mb-hit.is-on { border-color: var(--accent, #2a6); background: var(--accent-soft, #eaf4ec); }
.mb-btn { align-self: flex-start; padding: 7px 14px; border: none; border-radius: var(--radius-sm, 8px); background: var(--accent, #2a6); color: var(--accent-fg, #fff); font-size: var(--fs-12, 12px); font-weight: 600; cursor: pointer; }
.mb-btn:disabled { opacity: .5; cursor: not-allowed; }
.mb-admin-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.mb-archive { display: flex; flex-direction: column; gap: 8px; background: var(--surface-2, #fafaf8); border: 1px solid var(--border, #e6e6e2); border-radius: var(--radius-sm, 8px); padding: var(--s-2, 10px) var(--s-3, 14px); }
.mb-archive-note { margin: 0; font-size: var(--fs-12, 12px); color: var(--fg, #222); line-height: 1.7; }
.mb-archive input { padding: 7px 10px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); background: var(--surface, #fff); font-size: var(--fs-12, 12px); color: var(--fg, #222); }
.mb-archive-actions { display: flex; gap: 10px; justify-content: flex-end; }
</style>
