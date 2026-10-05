/**
 * 决策演变链的路由锚点构造（纯函数，便于单测）
 *
 * 契约事实源：docs/API_CONTRACTS.md §12.6「前端路由锚点契约」。
 * - 决策中心演变链 → 纪要页节点：tab=todos + todo 定位 + from=evolution 来源横幅
 * - 纪要页演变角标 → 决策中心议题：view=topic + topic 定位
 */
import type { LocationQuery, RouteLocationRaw } from 'vue-router'

/** 演变链节点「查看来源会议 / 已被替代 →」跳转的纪要页节点锚点 */
export function meetingNodeLink(taskId: string, todoId: string): RouteLocationRaw {
  return {
    name: 'generating',
    params: { taskId },
    query: { tab: 'todos', todo: todoId, from: 'evolution' },
  }
}

/** 回决策中心并定位到议题（切议题视图、展开簇与演变链） */
export function topicCenterLink(topicKey: string): RouteLocationRaw {
  return { name: 'decisions', query: { view: 'topic', topic: topicKey } }
}

/** 从路由 query 取节点锚点 id（非字符串一律忽略） */
export function parseAnchorTodoId(query: LocationQuery): string {
  return typeof query.todo === 'string' ? query.todo : ''
}

/** 从路由 query 取议题 key（非字符串一律忽略） */
export function parseTopicKey(query: LocationQuery): string {
  return typeof query.topic === 'string' ? query.topic : ''
}
