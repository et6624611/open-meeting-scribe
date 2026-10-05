/**
 * 决策状态字典的共享读取 / Shared accessor for the decision status dictionary
 *
 * DC-UNIFY-01：状态字典同时驱动纪要页决策流面板与决策中心（筛选 chips、色点、
 * 徽标、闭档沉底），因此需要一处加载、多处复用；字典在状态管理弹层变更后调用
 * `refreshDecisionStatuses()` 失效缓存，各视图随之自动更新。
 */
import { computed, ref } from 'vue'
import { fetchStatuses, statusLabel, type DecisionStatusItem } from '@/api/decisionStatuses'

const statuses = ref<DecisionStatusItem[]>([])
const loaded = ref(false)
let inflight: Promise<DecisionStatusItem[]> | null = null

async function load(force = false): Promise<DecisionStatusItem[]> {
  if (loaded.value && !force) return statuses.value
  if (!inflight) {
    inflight = fetchStatuses()
      .then(list => {
        statuses.value = list
        loaded.value = true
        return list
      })
      .catch(() => [] as DecisionStatusItem[])
      .finally(() => { inflight = null })
  }
  return inflight
}

/** 字典变更（新增/改名/标色/删除/排序）后由调用方触发，令所有视图同步 */
export function refreshDecisionStatuses(): Promise<DecisionStatusItem[]> {
  return load(true)
}

export function useDecisionStatuses() {
  const byId = computed<Record<string, DecisionStatusItem>>(() =>
    Object.fromEntries(statuses.value.map(s => [s.id, s])),
  )

  /** 状态展示名：字典缺失（后端降级/字典加载失败）时回退到 id 本身 */
  function labelOf(id: string | undefined, locale: string): string {
    if (!id) return ''
    const meta = byId.value[id]
    return meta ? statusLabel(meta, locale) : id
  }

  /** 状态色：字典驱动，未知 id 落到中性色 */
  function colorOf(id: string | undefined): string {
    return (id && byId.value[id]?.color) || 'var(--muted)'
  }

  /** 是否闭档（完成类）：未知 id 视为未闭档，宁可露出不隐藏 */
  function isClosing(id: string | undefined): boolean {
    return Boolean(id && byId.value[id]?.closing)
  }

  return { statuses, loaded, load, labelOf, colorOf, isClosing }
}
