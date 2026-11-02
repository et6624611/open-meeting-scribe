/**
 * 企业版定稿文本数据源（档③基座 + P1-WP-3 团队面分流）
 *
 * 空间=运行时上下文（方案 §0 决策 1）：私有列表=本人 owner 原件（契约 §1.4，D013 后服务端
 * 恒限 scope='personal'——本 store 消费面同样物理分离：tasks 只装私有原件，teamTasks 只装
 * 团队副本，视图各取一侧，串数据面由结构排除）；同步对账/队列权威态在 local plane 不变。
 * 团队副本 PUT 复用 §1.4 协议；409 冲突团队面**不做静默 last-writer-wins**——返回 latest
 * 快照由界面呈现冲突（diff UI=WP-5 交付形态，本批为"保稿不覆盖"下限态）。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { isEnterprise } from '@/edition'
import { listContextTasks, getContextTask, putContextSnapshot, snapshotConflictRev, type ContextTaskSummary, type ContextTaskDetail, type SnapshotPayload } from '@/api/context'
import { listTeamTasks, getTeamTask, putTeamSnapshot, snapshotTeamConflict, type TeamTaskSummary } from '@/api/teams'
import { useSpaceStore } from './space'

/**
 * content_hash 口径（2026-10-29 实测发现）：服务端对入库正文**重算并覆盖**客户端送值。
 * Web 端不自算哈希——提交占位值、以响应/详情的 content_hash 为权威。
 */
const HASH_SERVER_AUTHORITATIVE_PLACEHOLDER = ''

/** Idempotency-Key：每次用户变更一个新 mutation id（全局唯一即可，Web 端一次编辑=一次提交） */
function newMutationId(): string {
  return (globalThis.crypto?.randomUUID?.() ?? `m-${Date.now()}-${Math.random().toString(36).slice(2)}`)
}

export const useContextsStore = defineStore('contexts', () => {
  /** 私有空间=仅本人原件（D013 修复后服务端恒排除 team 行；前端消费面同样只由此数组渲染私有列表） */
  const tasks = ref<ContextTaskSummary[]>([])
  /** 团队空间=该团队公开副本（visibility 恒 'team'；不进 tasks，物理分数组防串=PM 硬核对项载体） */
  const teamTasks = ref<TeamTaskSummary[]>([])
  const loading = ref(false)
  const loadError = ref<string | null>(null)

  /** 空间态清理（spaceStore.switchSpace 的失效单点消费口；两数组同清，防上一空间残留渲染） */
  function forgetSpaceState() {
    tasks.value = []
    teamTasks.value = []
    loadError.value = null
  }

  async function loadTasks() {
    if (!isEnterprise) return
    loading.value = true
    loadError.value = null
    try {
      const space = useSpaceStore()
      if (space.isTeamSpace) {
        teamTasks.value = await listTeamTasks(space.currentId)
      } else {
        tasks.value = await listContextTasks()
      }
    } catch (err) {
      loadError.value = (err as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error?.message ?? 'load_failed'
    } finally { loading.value = false }
  }

  /** 副本行删除后就地剔除（撤回成功即列表消失，不必整表重拉） */
  function dropTeamTask(taskId: string) {
    teamTasks.value = teamTasks.value.filter((t) => t.task_id !== taskId)
  }

  async function loadDetail(taskId: string): Promise<ContextTaskDetail | null> {
    try {
      const space = useSpaceStore()
      return space.isTeamSpace ? await getTeamTask(space.currentId, taskId) : await getContextTask(taskId)
    } catch { return null }
  }

  /**
   * 保存定稿编辑（私有面全量快照 PUT）：meta/formal/decisions 回显自详情，summary/notes 取界面值。
   * 409 冲突 → 拉最新 server_rev、以新 mutation id 重推一次（P0 简化：Web 与助手同机互斥编辑，冲突极罕见）。
   */
  async function saveSnapshot(base: ContextTaskDetail, edits: { summary: string; notes: string }): Promise<{ ok: boolean; conflict?: boolean }> {
    const body: SnapshotPayload = {
      meta: {
        title: base.meta.title,
        meeting_time: base.meta.meeting_time,
        participants_text: base.meta.participants_text,
        source: base.meta.source === 'web_import' ? 'web_import' : 'client',
        legacy_id: base.meta.legacy_id ?? null,
      },
      formal: base.formal,
      summary: edits.summary,
      decisions: base.decisions,
      notes: edits.notes,
      insights_html: base.insights_html ?? null,
      content_hash: HASH_SERVER_AUTHORITATIVE_PLACEHOLDER,
    }

    const r1 = await putContextSnapshotSafe(base.task_id, body, newMutationId(), base.server_rev)
    if (r1.kind === 'ok') return { ok: true }
    if (r1.kind === 'conflict') {
      const latest = await getContextTask(base.task_id)
      if (!latest) return { ok: false, conflict: true }
      const merged: SnapshotPayload = { ...body, formal: latest.formal, decisions: latest.decisions, insights_html: latest.insights_html ?? null }
      const r2 = await putContextSnapshotSafe(base.task_id, merged, newMutationId(), latest.server_rev)
      if (r2.kind === 'ok') return { ok: true }
      return { ok: false, conflict: true }
    }
    return { ok: false }
  }

  async function putContextSnapshotSafe(taskId: string, body: SnapshotPayload, key: string, baseRev: number): Promise<
    { kind: 'ok'; result: Awaited<ReturnType<typeof putContextSnapshot>> } | { kind: 'conflict'; currentRev: number } | { kind: 'error' }
  > {
    try {
      const result = await putContextSnapshot(taskId, body, { idempotencyKey: key, baseRev })
      return { kind: 'ok', result }
    } catch (err) {
      const currentRev = snapshotConflictRev(err)
      if (currentRev !== null) return { kind: 'conflict', currentRev }
      return { kind: 'error' }
    }
  }

  /**
   * 团队副本保存（§8 复用 §1.4 协议）。冲突处理与私有面刻意不同：
   * 返回 conflict + latest 全文（必含项①），界面层保留用户草稿并呈现冲突——
   * 绝不自动重推覆盖他人修改（团队面 last-writer-wins 已被后端裁决禁用；diff 合并 UI=WP-5）。
   */
  async function saveTeamSnapshot(base: ContextTaskDetail, edits: { summary: string; notes: string }): Promise<{ ok: boolean; conflict?: boolean; latest?: ContextTaskDetail | null }> {
    const space = useSpaceStore()
    if (!space.isTeamSpace || !base.team_id) return { ok: false }
    const body = {
      meta: {
        title: base.meta.title,
        meeting_time: base.meta.meeting_time,
        participants_text: base.meta.participants_text,
        source: base.meta.source,
      },
      summary: edits.summary,
      decisions: base.decisions,
      notes: edits.notes,
      insights_html: base.insights_html ?? null,
      content_hash: HASH_SERVER_AUTHORITATIVE_PLACEHOLDER,
    }
    try {
      await putTeamSnapshot(base.team_id, base.task_id, body, { idempotencyKey: newMutationId(), baseRev: base.server_rev })
      return { ok: true }
    } catch (err) {
      const conflict = snapshotTeamConflict(err)
      if (conflict) return { ok: false, conflict: true, latest: conflict.latest }
      return { ok: false }
    }
  }

  async function removeTask(taskId: string): Promise<boolean> {
    const { deleteContextTask } = await import('@/api/context')
    try { await deleteContextTask(taskId); tasks.value = tasks.value.filter(t => t.task_id !== taskId); return true } catch { return false }
  }

  return { tasks, teamTasks, loading, loadError, loadTasks, dropTeamTask, loadDetail, saveSnapshot, saveTeamSnapshot, removeTask, forgetSpaceState }
})
