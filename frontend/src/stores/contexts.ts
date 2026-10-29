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
import { sha256Hex } from '@/utils/sha256'

/** 契约 §1.4 规范化正文：白名单内容字段固定顺序 JSON（客户端与服务端对账同一算法） */
export function computeContentHash(body: Pick<SnapshotPayload, 'formal' | 'summary' | 'decisions' | 'notes' | 'insights_html'>): string {
  return sha256Hex(JSON.stringify([body.formal, body.summary, body.decisions, body.notes, body.insights_html ?? null]))
}

/** Idempotency-Key：每次用户变更一个新 mutation id（UUIDv7 形态不强制，全局唯一即可；重传不变由 outbox 语义约束，Web 端一次编辑=一次提交） */
function newMutationId(): string {
  return (globalThis.crypto?.randomUUID?.() ?? `m-${Date.now()}-${Math.random().toString(36).slice(2)}`)
}

export const useContextsStore = defineStore('contexts', () => {
  const tasks = ref<ContextTaskSummary[]>([])
  const loading = ref(false)
  const loadError = ref<string | null>(null)

  async function loadTasks() {
    if (!isEnterprise) return
    loading.value = true
    loadError.value = null
    try { tasks.value = await listContextTasks() } catch (err) {
      loadError.value = (err as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error?.message ?? 'load_failed'
    } finally { loading.value = false }
  }

  async function loadDetail(taskId: string): Promise<ContextTaskDetail | null> {
    try { return await getContextTask(taskId) } catch { return null }
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
      content_hash: '',
    }
    body.content_hash = computeContentHash(body)

    const r1 = await putContextSnapshotSafe(base.task_id, body, newMutationId(), base.server_rev)
    if (r1.kind === 'ok') return { ok: true }
    if (r1.kind === 'conflict') {
      const latest = await getContextTask(base.task_id)
      if (!latest) return { ok: false, conflict: true }
      const merged: SnapshotPayload = { ...body, formal: latest.formal, decisions: latest.decisions, insights_html: latest.insights_html ?? null }
      merged.content_hash = computeContentHash(merged)
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

  return { tasks, loading, loadError, loadTasks, loadDetail, saveSnapshot, removeTask }
})
