/**
 * 空间上下文单点（P1-WP1 基座，改造方案 §0 决策 2）
 *
 * 切换即失效：switchSpace 清空并重载全部服务端态缓存（当前为 contexts 列表；WP-3 起
 * 词表/变更表面随各自 store 挂同一失效点），杜绝串数据——与 P0 origins.ts setActiveUser 同构。
 * 最近所在空间持久化走 oms.u.<uid>.last_space（W1-04 scopedKey 纪律，登出 purge 覆盖）；
 * 登出/401 时 reset() 回私有态。个人版恒私有：不发 teams 请求、不持久化。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { isEnterprise } from '@/edition'
import { listMyTeams, listTeamMembers, type TeamRole, type TeamSummary } from '@/api/teams'
import { scopedGet, scopedSet } from '@/utils/scopedStorage'
import { useUserStore } from './user'

export const PRIVATE_SPACE = 'private'
const LAST_SPACE_KEY = 'last_space'

export const useSpaceStore = defineStore('space', () => {
  const teams = ref<TeamSummary[]>([])
  const loaded = ref(false)
  const loadError = ref(false)
  const currentId = ref<string>(PRIVATE_SPACE)
  let loading: Promise<void> | null = null

  const isTeamSpace = computed(() => currentId.value !== PRIVATE_SPACE)
  const currentTeam = computed(() => teams.value.find((t) => t.team_id === currentId.value) ?? null)
  /** 角色单点（方案 §0 决策 3）：权限渲染一律消费 myRole/canEdit，视图不得自行判断 */
  const myRole = computed<TeamRole | null>(() => (currentTeam.value ? (currentTeam.value.my_role as TeamRole) : null))
  const canEdit = computed(() => myRole.value === 'admin' || myRole.value === 'editor')
  const isTeamAdmin = computed(() => myRole.value === 'admin')
  const currentSpaceName = computed(() => currentTeam.value?.name ?? '')

  function userId(): string | null {
    return useUserStore().user?.id ?? null
  }

  /**
   * 成员显示名缓存（uid→name，按团队加载；GET /teams/{id}/members 端点 BE 尚在排期——
   * 请求失败静默空缓存，消费侧回退不渲染"公开人"行，不猜名不显裸 id。端点落地零改动生效） */
  const memberNames = ref<Record<string, string>>({})

  function memberName(uid: string): string | null {
    return memberNames.value[uid] ?? null
  }

  async function loadMembers(teamId: string): Promise<void> {
    if (!isEnterprise || teamId === PRIVATE_SPACE) return
    try {
      const members = await listTeamMembers(teamId)
      const next = { ...memberNames.value }
      for (const m of members) next[m.user_id] = m.display_name
      memberNames.value = next
    } catch { /* 端点未就位（404）静默回退：显示名缺省 */ }
  }

  /** 幂等加载（并发共享同一次请求）；完成后校验/恢复最近所在空间，失效（被移出团队等）静默回私有 */
  async function loadTeams(): Promise<void> {
    if (!isEnterprise) return
    if (loaded.value) return
    if (loading) return loading
    loading = (async () => {
      loadError.value = false
      try {
        teams.value = await listMyTeams()
        loaded.value = true
      } catch {
        loadError.value = true
      } finally {
        loading = null
      }
      if (isTeamSpace.value && !currentTeam.value) {
        currentId.value = PRIVATE_SPACE
      } else if (!isTeamSpace.value) {
        const uid = userId()
        const saved = uid ? scopedGet(uid, LAST_SPACE_KEY) : null
        if (saved && teams.value.some((t) => t.team_id === saved)) {
          currentId.value = saved
          void loadMembers(saved)
        }
      } else {
        void loadMembers(currentId.value)
      }
    })()
    return loading
  }

  function switchSpace(id: string): void {
    if (!isEnterprise || id === currentId.value) return
    if (id !== PRIVATE_SPACE && !teams.value.some((t) => t.team_id === id)) return
    currentId.value = id
    const uid = userId()
    if (uid) scopedSet(uid, LAST_SPACE_KEY, id)
    void loadMembers(id)
    // 切换即失效（动态 import 避免与 contexts store 的静态环依赖；同 removeTask 延迟加载惯例）
    void (async () => {
      const { useContextsStore } = await import('./contexts')
      const contexts = useContextsStore()
      contexts.forgetSpaceState()
      await contexts.loadTasks()
    })()
  }

  /**
   * D014 首帧就绪单点（PM 拍板"一次修全部同模式面孔"）：整页重载/深链时视图首帧必须等
   * ①user 会话探测完成（last_space 恢复的 uid 依据）与②teams 恢复完成后才取数——
   * 消费方一律 await ensureReady() 再 fetch，不再各自赌挂载顺序。
   * 可重入：checkAuth/loadTeams 均有并发去重；teams 加载失败后再次调用即重试（loaded 仅成功置真）。
   */
  async function ensureReady(): Promise<void> {
    if (!isEnterprise) return
    const user = useUserStore()
    if (!user.checked) await user.checkAuth()
    await loadTeams()
  }

  /** 登出清态（EnterpriseUserMenu 调用；401 路径走整页跳转天然覆盖） */
  function reset(): void {
    teams.value = []
    memberNames.value = {}
    loaded.value = false
    loadError.value = false
    loading = null
    currentId.value = PRIVATE_SPACE
  }

  return {
    teams, loaded, loadError, currentId,
    isTeamSpace, currentTeam, myRole, canEdit, isTeamAdmin, currentSpaceName,
    loadTeams, switchSpace, reset, memberName, loadMembers, ensureReady,
  }
})
