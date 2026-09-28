/**
 * 决策中心 API 封装 / Decision-center API wrapper
 *
 * 契约事实源：docs/API_CONTRACTS.md §12（DC-UNIFY-01 修订，2026-09-27）。
 *
 * DC-UNIFY-01：决策只有一个对象——决策流节点（`task["todos"]`）。本模块只负责
 * 跨会议聚合读取（决策中心数据源）；节点级写操作统一复用 `api/notes.ts` 的
 * `/api/tasks/{id}/todos*` 端点，纪要页与决策中心共用同一套写入路径。
 * 原 decision 对象的任务级 CRUD（§12.1/§12.2）与内存 mock 通道已随之后下线。
 */
import client from './client'
import type { TodoItem } from './types'

/** 决策执行人选人值：null = 未指派（DC-R2-b D4，合法态） */
export type OwnerValue = { id: string; name: string } | null

/** 聚合视图条目：决策流节点 + 状态字典元信息 + 来源会议元信息（§12.3 平铺元素） */
export interface FlowNode extends TodoItem {
  task_id: string
  /** 来源会议标题（`title` 已让位给决策自身标题） */
  meeting_title: string
  meeting_date: string | null
  /** 所属知识库（= project_id），未关联为 null */
  kb_id: string | null
  kb_name: string | null
}

/** 聚合查询参数：status 为状态字典 id（单值精确过滤，非法值 422） */
export interface FlowQuery {
  since?: string
  until?: string
  kb_id?: string
  status?: string
  q?: string
  /** 限定单会议（纪要页只读快照用；缺省为全量） */
  task_id?: string
}

export interface FlowGroup {
  key: string
  label: string | null
  task_id: string | null
  meeting_date: string | null
  decisions: FlowNode[]
}

function toParams(q: FlowQuery): Record<string, string> {
  const params: Record<string, string> = {}
  if (q.since) params.since = q.since
  if (q.until) params.until = q.until
  if (q.kb_id) params.kb_id = q.kb_id
  if (q.status) params.status = q.status
  if (q.q) params.q = q.q
  if (q.task_id) params.task_id = q.task_id
  return params
}

/** 跨会议决策流平铺列表 / Flat cross-meeting decision-flow rows */
export async function fetchFlowNodes(q: FlowQuery = {}): Promise<FlowNode[]> {
  const { data } = await client.get<{ decisions: FlowNode[]; total: number }>('/api/decisions', { params: toParams(q) })
  return data.decisions || []
}

/** 跨会议决策流分组结果（group_by=meeting|date） */
export async function fetchFlowGroups(by: 'meeting' | 'date', q: FlowQuery = {}): Promise<FlowGroup[]> {
  const { data } = await client.get<{ groups: FlowGroup[]; total: number }>('/api/decisions', {
    params: { ...toParams(q), group_by: by },
  })
  return data.groups || []
}
