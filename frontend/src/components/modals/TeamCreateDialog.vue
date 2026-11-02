<script setup lang="ts">
/**
 * 建团队弹窗（P1-WP-4，UI 规格 §2.1）：一次输入团队名 → 搜索多选成员 → 创建即入空间。
 * 自己默认在内且角色=管理员由服务端保证（BE create_team 创建者自动 admin，FE 不传自己进 member_ids）。
 * 用户搜索=§8.5 隐私面（只回 user_id/display_name，仅 active），选中项本地缓存显示名。
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { createTeam, searchUsers, type UserSearchHit } from '@/api/teams'
import { useSpaceStore } from '@/stores/space'
import { useEscClose } from '@/composables/useEscClose'
import { showToast } from '@/composables/useToast'

const emit = defineEmits<{ close: []; created: [teamId: string] }>()
const { t } = useI18n()
const space = useSpaceStore()

const name = ref('')
const query = ref('')
const hits = ref<UserSearchHit[]>([])
const picked = ref<UserSearchHit[]>([])
const searching = ref(false)
const creating = ref(false)
const searchBox = ref<HTMLElement | null>(null)
const error = ref('')

const escRef = ref(true)
useEscClose(escRef, () => { if (!creating.value) emit('close') })

let searchTimer: ReturnType<typeof setTimeout> | null = null
function onQuery() {
  if (searchTimer) clearTimeout(searchTimer)
  const q = query.value.trim()
  if (!q) { hits.value = []; return }
  searching.value = true
  searchTimer = setTimeout(async () => {
    try {
      hits.value = await searchUsers(q)
    } catch {
      hits.value = []
    } finally { searching.value = false }
  }, 250)
}

function togglePick(hit: UserSearchHit) {
  const i = picked.value.findIndex((p) => p.user_id === hit.user_id)
  if (i >= 0) picked.value.splice(i, 1)
  else picked.value.push(hit)
}

const canCreate = computed(() => !creating.value && name.value.trim().length > 0)

async function onCreate() {
  if (!canCreate.value) return
  creating.value = true
  error.value = ''
  try {
    const team = await createTeam({ name: name.value.trim(), member_user_ids: picked.value.map((p) => p.user_id) })
    // D017 修复：force 重拉新团队列表→切换校验→**同一帧事实**才报成功——
    // "引导语落地和切换器新团队在列"必须一致，拒绝 toast 闪过分寸即断链的错觉形态
    await space.loadTeams(true)
    space.justCreatedTeamId = team.team_id
    if (space.switchSpace(team.team_id)) {
      showToast(t('enterprise.create.toast_done'), 'success')
      emit('created', team.team_id)
      emit('close')
    } else {
      error.value = t('enterprise.create.err_switch')
    }
  } catch (err) {
    const status = (err as { response?: { status?: number } })?.response?.status
    error.value = status === 403
      ? t('enterprise.create.err_forbidden')
      : t('enterprise.create.err_failed')
  } finally { creating.value = false }
}

onMounted(() => { nextTick(() => searchBox.value?.focus()) })
</script>

<template>
  <Teleport to="body">
    <div class="tc-mask" @click.self="emit('close')">
      <div class="tc-card" role="dialog" aria-modal="true" :aria-label="t('enterprise.create.title')">
        <h3>{{ t('enterprise.create.title') }}</h3>
        <label class="tc-field">
          <span>{{ t('enterprise.create.name_label') }}</span>
          <input v-model="name" type="text" :placeholder="t('enterprise.create.name_placeholder')" maxlength="40" autocomplete="off">
        </label>
        <label class="tc-field">
          <span>{{ t('enterprise.create.members_label') }}</span>
          <input
            ref="searchBox"
            v-model="query"
            type="search"
            :placeholder="t('enterprise.create.search_placeholder')"
            :aria-label="t('enterprise.create.search_placeholder')"
            @input="onQuery"
          >
        </label>
        <p v-if="picked.length" class="tc-picked">
          <span v-for="p in picked" :key="p.user_id" class="tc-chip">
            {{ p.display_name }}
            <button type="button" class="tc-chip-x" :aria-label="t('enterprise.create.remove_member_aria')" @click="togglePick(p)">✕</button>
          </span>
        </p>
        <ul v-if="hits.length" class="tc-hits" role="listbox" :aria-label="t('enterprise.create.search_placeholder')">
          <li v-for="h in hits" :key="h.user_id">
            <button
              type="button"
              role="option"
              class="tc-hit"
              :class="{ 'is-on': picked.some((p) => p.user_id === h.user_id) }"
              :aria-selected="picked.some((p) => p.user_id === h.user_id)"
              @click="togglePick(h)"
            >{{ h.display_name }}</button>
          </li>
        </ul>
        <p v-else-if="searching" class="tc-muted">{{ t('enterprise.library.loading') }}</p>
        <p v-else-if="query.trim() && !hits.length" class="tc-muted">{{ t('enterprise.create.no_users') }}</p>
        <p class="tc-note">{{ t('enterprise.create.note') }}</p>
        <p v-if="error" class="tc-error" role="alert">{{ error }}</p>
        <div class="tc-actions">
          <button type="button" class="tc-btn is-ghost" :disabled="creating" @click="emit('close')">{{ t('common.action.cancel') }}</button>
          <button type="button" class="tc-btn" :disabled="!canCreate" @click="onCreate">{{ creating ? t('enterprise.create.creating') : t('enterprise.create.btn') }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.tc-mask { position: fixed; inset: 0; background: rgb(0 0 0 / 0.35); display: grid; place-items: center; z-index: var(--z-toast, 1200); padding: var(--s-3, 16px); }
.tc-card { width: min(460px, 100%); max-height: calc(100vh - 48px); overflow: auto; background: var(--surface, #fff); border-radius: calc(var(--radius-sm, 8px) * 1.5); padding: calc(var(--s-3, 16px) * 1.25); display: flex; flex-direction: column; gap: var(--s-2, 10px); box-shadow: 0 16px 48px rgb(0 0 0 / 0.2); }
.tc-card h3 { margin: 0; font-size: 15px; }
.tc-field { display: flex; flex-direction: column; gap: 4px; font-size: var(--fs-12, 12px); color: var(--muted, #666); }
.tc-field input { padding: 8px 10px; border: 1px solid var(--border, #d8d8d4); border-radius: var(--radius-sm, 8px); background: var(--surface-2, #fafaf8); font-size: var(--fs-13, 13px); color: var(--fg, #222); }
.tc-field input:focus { outline: 2px solid var(--accent-mid, #4a7); outline-offset: 1px; }
.tc-picked { margin: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.tc-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px; background: var(--accent-soft, #eaf4ec); border: 1px solid var(--accent, #2a6); font-size: var(--fs-11, 11px); color: var(--fg, #222); }
.tc-chip-x { border: none; background: none; cursor: pointer; color: var(--muted, #666); font-size: var(--fs-11, 11px); padding: 0; }
.tc-hits { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; max-height: 200px; overflow: auto; }
.tc-hit { display: block; width: 100%; text-align: left; padding: 7px 10px; border: 1px solid var(--border, #e2e2de); border-radius: var(--radius-sm, 8px); background: var(--surface-2, #fafaf8); font-size: var(--fs-12, 12px); color: var(--fg, #222); cursor: pointer; }
.tc-hit.is-on { border-color: var(--accent, #2a6); background: var(--accent-soft, #eaf4ec); }
.tc-hit:hover { border-color: var(--accent-mid, #4a7); }
.tc-note, .tc-muted { margin: 0; font-size: var(--fs-11, 11px); color: var(--subtle, #999); }
.tc-error { margin: 0; font-size: var(--fs-12, 12px); color: var(--warn, #c33); }
.tc-actions { display: flex; gap: var(--s-2, 10px); justify-content: flex-end; margin-top: var(--s-2, 6px); }
.tc-btn { padding: 8px 16px; border: none; border-radius: var(--radius-sm, 8px); background: var(--accent, #2a6); color: var(--accent-fg, #fff); cursor: pointer; font-size: var(--fs-12, 12px); font-weight: 600; }
.tc-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.tc-btn.is-ghost { background: none; border: 1px solid var(--border, #d8d8d4); color: var(--fg, #222); font-weight: 400; }
</style>
