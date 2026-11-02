/**
 * 团队空间契约客户端（P1 契约 §8/§9，server plane，WP-1 基座）
 *
 * 纪律两条（产品批准在案，改造方案 §0/§1）：
 * 1. TB 零暴露证据链：本模块**不实现企业资产层任何读函数**——资产层无读端点（404 by design），
 *    前端连命中它的请求代码都不存在（QA 接口扫基线）。
 * 2. 权限判断不在此层：my_role 仅透传服务端值，渲染门控一律消费 spaceStore.myRole 单点。
 * 发布/撤回端点随 WP-2 扩展（publishToTeam/unpublishFromTeam），本批不含。
 */
import client from './client'
import type { ContextTaskDetail, PublishedCopy, SnapshotResult } from './context'

export type { PublishedCopy }

/** 团队公开面列表行（BE dao.list_team_tasks 实码逐键：无 sync_status，visibility 恒 'team'；
 *  publisher_user_id=发布人，显示名待 GET members 端点补齐（已随批播报 BE 缺项），渲染缺名回退不猜 */
export interface TeamTaskSummary {
  task_id: string
  title: string
  current_rev: number
  content_hash: string
  source_task_id: string | null
  publisher_user_id: string
  updated_at: string
  visibility: 'team'
  /** K4 定版（段五 74cfe95 供给）：首次 publish 留痕时间=公开时刻，决策聚合排序锚。
   *  旧部署态缺键时消费侧回退 updated_at（内容新鲜度序），发布即自动升定版语义 */
  published_at?: string
}

/** 变更记录行（K1 十二值原样透出；未知值前端回退显原文不崩——FE 兜底纪律） */
export interface TeamAuditItem {
  audit_id: string
  action: string
  actor_user_id: string
  actor_name: string
  task_id: string | null
  rev: number | null
  target_ref: string | null
  pre_delete_rev: number | null
  ts: string
}

/** 团队面快照 PUT（§8 复用 §1.4 协议；409 必含项① latest 全文经 snapshotTeamConflict 提取） */
export async function putTeamSnapshot(
  teamId: string, taskId: string, payload: Record<string, unknown>,
  headers: { idempotencyKey: string; baseRev: number },
): Promise<SnapshotResult> {
  const { data } = await client.put<SnapshotResult>(
    `/api/v1/context/teams/${encodeURIComponent(teamId)}/tasks/${encodeURIComponent(taskId)}/snapshot`,
    payload,
    {
      headers: {
        'Idempotency-Key': headers.idempotencyKey,
        'If-Match-Rev': String(headers.baseRev),
      },
    },
  )
  return data
}

/** 团队面 409 提取（必含项①）：current_rev + latest 全文快照（形态=get_team_task DTO） */
export function snapshotTeamConflict(err: unknown): { currentRev: number; latest: ContextTaskDetail | null } | null {
  const data = (err as { response?: { status?: number; data?: { error?: { code?: string; current_rev?: number; latest?: ContextTaskDetail } } } })?.response
  if (data?.status !== 409 || data.data?.error?.code !== 'rev_conflict') return null
  const rev = data.data.error.current_rev
  return { currentRev: typeof rev === 'number' ? rev : -1, latest: data.data.error.latest ?? null }
}

/** 决策条目删除（裁决③；留痕 decision_delete 携 target_ref+pre_delete_rev） */
export async function deleteTeamDecision(teamId: string, taskId: string, decisionId: string): Promise<void> {
  await client.delete(`/api/v1/context/teams/${encodeURIComponent(teamId)}/tasks/${encodeURIComponent(taskId)}/decisions/${encodeURIComponent(decisionId)}`)
}

/** 决策恢复（§6.5 闭环：from_rev=decision_delete 留痕的 pre_delete_rev） */
export async function restoreTeamDecision(teamId: string, taskId: string, decisionId: string, fromRev: number): Promise<void> {
  await client.post(`/api/v1/context/teams/${encodeURIComponent(teamId)}/tasks/${encodeURIComponent(taskId)}/decisions/${encodeURIComponent(decisionId)}/restore`, { from_rev: fromRev })
}

/** 变更记录分页（§8.4 倒序；viewer+ 可读） */
export async function listTeamAudit(teamId: string, cursor?: string | null, limit = 30): Promise<{ items: TeamAuditItem[]; next_cursor: string | null }> {
  const { data } = await client.get<{ items: TeamAuditItem[]; next_cursor: string | null }>(
    `/api/v1/teams/${encodeURIComponent(teamId)}/audit`,
    { params: { limit, ...(cursor ? { cursor } : {}) } },
  )
  return data
}

export type TeamRole = 'admin' | 'editor' | 'viewer'

/** 切换器数据源 DTO（契约 §9.1 直用；BE 段二实核字段=team_id/name/my_role/member_count/joined_at/status）。
 *  D009 收敛（QA 探针，随 WP-1 修复）：归档权威态走 status='archived'（服务端权威优先）；
 *  archived 布尔仅作兼容读入，消费面一律走 teams.ts isTeamArchived() 单源映射。 */
export interface TeamSummary {
  team_id: string
  name: string
  my_role: TeamRole | string
  status?: string
  archived?: boolean
  member_count?: number
  joined_at?: string | null
}

/** 归档判定单源（D009）：status 优先，兼容期回退 archived 布尔——消费方禁止各自散判 */
export function isTeamArchived(t: TeamSummary): boolean {
  if (typeof t.status === 'string') return t.status === 'archived'
  return t.archived === true
}

/** 发布弹窗可选团队（规格 §4.2：归档团队不出现；已公开团队置灰标注、重复选择无效）。
 *  publishedTeamIds 由发布态读面供给——段三契约补注定版前缺省=全可选（服务端幂等兜底）。 */
export function selectablePublishTeams(
  teams: TeamSummary[],
  publishedTeamIds: string[] = [],
): Array<{ team: TeamSummary; alreadyPublished: boolean }> {
  return teams
    .filter((t) => !isTeamArchived(t))
    .map((t) => ({ team: t, alreadyPublished: publishedTeamIds.includes(t.team_id) }))
}

export interface TeamMember {
  user_id: string
  display_name: string
  role: TeamRole | string
  joined_at?: string | null
}

/** 我在的空间清单（含 role）——空间切换器唯一数据源 */
export async function listMyTeams(): Promise<TeamSummary[]> {
  const { data } = await client.get<{ teams: TeamSummary[] }>('/api/v1/context/teams')
  return data.teams
}

/** 团队公开面列表（§8 团队副本读；空团队=空数组，私有原件结构性不在此结果） */
export async function listTeamTasks(teamId: string): Promise<TeamTaskSummary[]> {
  const { data } = await client.get<{ tasks: TeamTaskSummary[] }>(
    `/api/v1/context/teams/${encodeURIComponent(teamId)}/tasks`,
  )
  return data.tasks
}

/** 团队副本详情（服务端按成员权解析；非成员=404 资源隐藏语义） */
export async function getTeamTask(teamId: string, taskId: string): Promise<ContextTaskDetail> {
  const { data } = await client.get<ContextTaskDetail>(
    `/api/v1/context/teams/${encodeURIComponent(teamId)}/tasks/${encodeURIComponent(taskId)}`,
  )
  return data
}

// ─── 发布链（WP-2） ───

/** 发布粒度（契约 §9.2 终形态 + BE ffcb709 实码对齐）：task=整包副本；decision=单条决策独立时间线 */
export type PublishMode = 'task' | 'decision'

/**
 * 发布请求体序列化（单点换向器）。契约终形态 `{team_id, mode, decision_id?}`（§9.2；
 * BE 实码 enterprise_api.py ctx_publish 逐字对齐，D009 纪律=以实测为准不猜键名）。
 * 注：服务端无内容勾选面（task 模式=全量定稿文本包）——规格 §4.2 勾选区的承载缺口
 * 已随 WP-2 播报提请产品/后端裁决，如 §6.5 补注 include 字段只改此函数与弹窗映射。
 */
export function buildPublishBody(teamId: string, mode: PublishMode, decisionId: string | null): Record<string, unknown> {
  return mode === 'decision' && decisionId
    ? { team_id: teamId, mode, decision_id: decisionId }
    : { team_id: teamId, mode: 'task' }
}

/** 发布=创建/刷新团队副本（裁决①原件可多发：每团队一次独立调用；K2 同团队重复发布=刷新不产生第二份） */
export async function publishTaskToTeam(taskId: string, body: Record<string, unknown>): Promise<{ task_id: string; republished?: boolean }> {
  const { data } = await client.post<{ task_id: string; republished?: boolean }>(
    `/api/v1/context/tasks/${encodeURIComponent(taskId)}/publish`, body,
  )
  return data
}

/** 撤回=归档副本（§8 明示端点；按团队独立，原件与已收集资产不受影响） */
export async function unpublishTeamTask(teamId: string, taskId: string): Promise<void> {
  await client.delete(`/api/v1/context/teams/${encodeURIComponent(teamId)}/tasks/${encodeURIComponent(taskId)}`)
}

/** 团队词表 kind 路径段（BE TEAM_ASSET_KIND_MAP 逐字：hotwords / speaker-aliases） */
export type TeamAssetKindSeg = 'hotwords' | 'speaker-aliases'

/** 团队资产信封（BE get_team_asset 实码：kind/visibility='team'/team_id/current_rev/content_hash/payload；
 *  空态 rev=0 payload=null——FE 空态判定单源 current_rev===0，与个人面同构） */
export interface TeamAssetEnvelope<T> {
  kind: string
  visibility: 'team'
  team_id: string
  current_rev: number
  content_hash: string | null
  payload: T | null
}

export async function getTeamAsset<T>(teamId: string, kindSeg: TeamAssetKindSeg): Promise<TeamAssetEnvelope<T>> {
  const { data } = await client.get<TeamAssetEnvelope<T>>(
    `/api/v1/context/teams/${encodeURIComponent(teamId)}/assets/${kindSeg}`,
  )
  return data
}

/** 团队词表 PUT（editor+；§1.4 同协议；归档写 409 team_archived 读放行=裁决④）。
 *  409 形态={error:'rev_conflict'...current_rev}——冲突方界面重拉最新（词表无逐行 diff 需求，
 *  与团队纪要的 WP-5 diff 流刻意不同：整表重读后用户重改，绝不静默覆盖）。 */
export async function putTeamAsset(
  teamId: string, kindSeg: TeamAssetKindSeg, payload: Record<string, unknown>,
  headers: { idempotencyKey: string; baseRev: number },
): Promise<{ current_rev: number; content_hash: string; idempotent_replay: boolean }> {
  const { data } = await client.put(
    `/api/v1/context/teams/${encodeURIComponent(teamId)}/assets/${kindSeg}`,
    { payload },
    { headers: { 'Idempotency-Key': headers.idempotencyKey, 'If-Match-Rev': String(headers.baseRev) } },
  )
  return data
}

// ─── 治理面端点绑定（WP-4 消费；纯契约映射，本批无 UI） ───

export async function createTeam(input: { name: string; member_user_ids: string[] }): Promise<TeamSummary> {
  const { data } = await client.post<TeamSummary>('/api/v1/teams', input)
  return data
}

export async function renameTeam(teamId: string, name: string): Promise<void> {
  await client.put(`/api/v1/teams/${encodeURIComponent(teamId)}`, { name })
}

export async function archiveTeam(teamId: string): Promise<void> {
  await client.put(`/api/v1/teams/${encodeURIComponent(teamId)}/archive`)
}

export async function listTeamMembers(teamId: string): Promise<TeamMember[]> {
  const { data } = await client.get<{ members: TeamMember[] }>(
    `/api/v1/teams/${encodeURIComponent(teamId)}/members`,
  )
  return data.members
}

/** 批量加成员（D010 终态 {user_ids:[...], role?}；added/failed 双载由调用方按 ok 处理，
 *  非成员/权限不足先行 404/403 不被批量结果吞掉——BE 语义） */
export async function addTeamMembers(teamId: string, userIds: string[], role?: TeamRole): Promise<void> {
  await client.post(`/api/v1/teams/${encodeURIComponent(teamId)}/members`, role ? { user_ids: userIds, role } : { user_ids: userIds })
}

export async function removeTeamMember(teamId: string, userId: string): Promise<void> {
  await client.delete(`/api/v1/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userId)}`)
}

export async function setMemberRole(teamId: string, userId: string, role: TeamRole): Promise<void> {
  await client.put(`/api/v1/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userId)}/role`, { role })
}

/** 转让管理员（BE transfer-admin 实码 body={to_user_id}；单事务+role_transfer 留痕） */
export async function transferTeamAdmin(teamId: string, toUserId: string): Promise<void> {
  await client.post(`/api/v1/teams/${encodeURIComponent(teamId)}/transfer-admin`, { to_user_id: toUserId })
}

/** 建团队选成员搜索（§8.5：仅 active，只回 user_id/display_name，形状逐键对实码） */
export interface UserSearchHit { user_id: string; display_name: string }
export async function searchUsers(q: string): Promise<UserSearchHit[]> {
  const { data } = await client.get<{ users: UserSearchHit[] }>('/api/v1/users/search', { params: { q } })
  return data.users
}

/** 首个管理员显示名（首访轻提示"被 X 加入"的 X 取数；无 members 数据时 null 走省略分支） */
export function firstAdminName(members: Array<{ role: string; display_name: string }>): string | null {
  return members.find((m) => m.role === 'admin')?.display_name ?? null
}
