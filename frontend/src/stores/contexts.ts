/**
 * 企业版"我的空间"定稿文本数据源（档③，契约 §1.4，server plane）
 *
 * 列表=本人 owner 的 context tasks（服务端强制 actor 过滤，前端不复制权限逻辑）；
 * visibility 恒 personal（徽标单源）；sync_status 服务端对账态 synced|stale 只做
 * "最后同步于…"展示，队列权威态在 local plane（instance store 负责）。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { isEnterprise } from '@/edition'
import { listContextTasks, getContextTask, putContextSnapshot, snapshotConflictRev, type ContextTaskSummary, type ContextTaskDetail, type SnapshotPayload } from '@/api/context'
import { listTeamTasks, getTeamTask } from '@/api/teams'
import { useSpaceStore } from './space'

/**
 * content_hash 口径（2026-10-29 实测发现，待后端契约确认）：服务端对入库正文**重算并覆盖**
 * 客户端送值（sentinel 用例：送 h2-sentinel → 记录为服务端规范化 hash）。因此 Web 端
 * 不自算哈希、不做客户端对账——提交占位值、以响应/详情的 content_hash 为权威。
 * 助手侧 outbox 对账同样应以服务端回执为准（3b 接线时对齐）。
 */
const HASH_SERVER_AUTHORITATIVE_PLACEHOLDER = ''

/** Idempotency-Key：每次用户变更一个新 mutation id（UUIDv7 形态不强制，全局唯一即可；重传不变由 outbox 语义约束，Web 端一次编辑=一次提交） */
function newMutationId(): string {
  return (globalThis.crypto?.randomUUID?.() ?? `m-${Date.now()}-${Math.random().toString(36).slice(2)}`)
}

export const useContextsStore = defineStore('contexts', () => {
  const tasks = ref<ContextTaskSummary[]>([])
  const loading = ref(false)
  const loadError = ref<string | null>(null)

  /** 空间态清理（spaceStore.switchSpace 的失效单点消费口；列表缓存键=当前空间，防串数据） */
  function forgetSpaceState() {
    tasks.value = []
    loadError.value = null
  }

  async function loadTasks() {
    if (!isEnterprise) return
    loading.value = true
    loadError.value = null
    try {
      const space = useSpaceStore()
      // 空间=运行时上下文（方案 §0 决策 1）：私有=本人 owner 列表；团队=该团队公开副本列表
      tasks.value = space.isTeamSpace ? await listTeamTasks(space.currentId) : await listContextTasks()
    } catch (err) {
      loadError.value = (err as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error?.message ?? 'load_failed'
    } finally { loading.value = false }
  }

  async function loadDetail(taskId: string): Promise<ContextTaskDetail | null> {
    try {
      const space = useSpaceStore()
      return space.isTeamSpace ? await getTeamTask(space.currentId, taskId) : await getContextTask(taskId)
    } catch { return null }
  }

  /**
   * 保存定稿编辑（全量快照 PUT）：meta/formal/decisions 回显自详情，summary/notes 取界面值。
   * 409 冲突 → 拉最新 server_rev、以新 mutation id 重推一次（last-merge-wins 简化：
   * 保留本地编辑字段值，其余字段采纳服务端最新——P0 Web 与助手同机互斥编辑，冲突极罕见）。
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

  async function removeTask(taskId: string): Promise<boolean> {
    const { deleteContextTask } = await import('@/api/context')
    try { await deleteContextTask(taskId); tasks.value = tasks.value.filter(t => t.task_id !== taskId); return true } catch { return false }
  }

  return { tasks, loading, loadError, loadTasks, loadDetail, saveSnapshot, removeTask, forgetSpaceState }
})
