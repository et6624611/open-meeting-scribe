import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DecisionFlowPanel from '../DecisionFlowPanel.vue'
import type { TodoItem } from '@/api/types'
import type { NodeEvolution } from '@/api/decisions'

// jsdom 不提供 CSS.escape，面板锚点选择器依赖它
if (!globalThis.CSS) {
  (globalThis as unknown as { CSS: { escape: (s: string) => string } }).CSS = {
    escape: (s: string) => s.replace(/["\\]/g, '\\$&'),
  }
}

// ── 打桩：状态字典与演变归属（facade 级 mock，不碰真实 HTTP） ──
const { STATUSES, EVOLUTION, TODOS } = vi.hoisted(() => {
  const statuses = [
    { id: 'to_decide', name: '待决策', name_en: 'To decide', color: 'var(--x)', closing: false, system: true },
    { id: 'in_progress', name: '进行中', name_en: 'In progress', color: 'var(--x)', closing: false, system: false },
    { id: 'superseded', name: '已替代', name_en: 'Superseded', color: 'var(--subtle)', closing: true, system: true },
    { id: 'done', name: '完成', name_en: 'Done', color: 'var(--ok)', closing: true, system: true },
  ]
  const todos: TodoItem[] = [
    { id: 'a1', text: '主节点决策', title: '主节点决策', done: false, status: 'to_decide' },
    { id: 'a2', text: '另一条开放决策', done: false, status: 'in_progress' },
    { id: 'c1', text: '已替代的旧决策', title: '已替代的旧决策', done: true, status: 'superseded' },
  ]
  const evolution: Record<string, NodeEvolution> = {
    a1: {
      topic_key: 'k1', topic_title: '预算调整议题', role: 'main', meeting_count: 2,
      latest: { task_id: 't1', todo_id: 'a1', title: '主节点决策', meeting_title: '本会议' },
    },
    c1: {
      topic_key: 'k1', topic_title: '预算调整议题', role: 'history', meeting_count: 2,
      latest: { task_id: 't2', todo_id: 'b1', title: '新决策', meeting_title: '新会议' },
    },
  }
  return { STATUSES: statuses, EVOLUTION: evolution, TODOS: todos }
})

vi.mock('@/api/decisions', () => ({ fetchTaskEvolution: vi.fn(async () => EVOLUTION) }))
vi.mock('@/api/decisionStatuses', () => ({
  fetchStatuses: vi.fn(async () => STATUSES),
  statusLabel: (item: { name: string; name_en: string }, locale: string) =>
    locale.startsWith('en') ? item.name_en : item.name,
}))

// 仅列面板模板实际消费的文案；断言也引用同一对象，避免中英文件漂移导致脆测
const ZH = {
  decisions: {
    meeting_evo_badge_main: '跨 {count} 场会议持续讨论 · 查看议题全貌',
    meeting_evo_badge_history: '此议题在另一场会议有了新推进',
    meeting_evo_latest_in: '最新推进：《{meeting}》',
    meeting_evo_view_topic: '议题全貌',
    meeting_evo_from_banner: '来自决策中心 · 正在查看「{title}」的演变上下文',
    meeting_evo_banner_goto_center: '回决策中心',
    meeting_evo_banner_dismiss: '关闭横幅',
  },
  generating: {
    decisions_panel_link: '决策中心',
    todos: {
      add_decision: '添加决策',
      completed_group: '已完成（{count}）',
      total_count: '共 {count} 条',
      status_other: '其他',
      flow_empty: '暂无决策',
      flow_empty_hint: 'hint',
      empty: '空',
    },
  },
}

function mountPanel(props: Record<string, unknown> = {}) {
  const i18n = createI18n({ legacy: false, locale: 'zh-CN', messages: { 'zh-CN': ZH } })
  // 面板内以 import 方式直接使用 RouterLink（h 渲染角标），必须提供真实 router 实例
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { name: 'home', path: '/', component: { template: '' } },
      { name: 'generating', path: '/g/:taskId', component: { template: '' } },
      { name: 'decisions', path: '/d', component: { template: '' } },
    ],
  })
  const w = mount(DecisionFlowPanel, {
    attachTo: document.body,
    props: { visible: true, taskId: 't1', todos: TODOS, ...props },
    global: {
      plugins: [i18n, router],
      stubs: {
        // 手动 stub 保留根节点 data-todo-id，使锚点选择器在测试中可命中
        DecisionNode: {
          props: ['todo'],
          template: '<div class="db-node" :data-todo-id="todo.id">{{ todo.title || todo.text }}</div>',
        },
      },
    },
  })
  mounted.push(w)
  return w
}

const tick = (ms = 250) => new Promise(r => window.setTimeout(r, ms))

// jsdom 不实现 scrollIntoView；补一个可断言的桩并在用例间复位
let scrollSpy: ReturnType<typeof vi.fn>
const mounted: ReturnType<typeof mount>[] = []
beforeEach(() => {
  scrollSpy = vi.fn()
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
    configurable: true,
    value: scrollSpy,
  })
})
afterEach(() => {
  mounted.forEach(w => w.unmount())
  mounted.length = 0
  document.body.innerHTML = ''
  delete (HTMLElement.prototype as Partial<typeof HTMLElement.prototype>).scrollIntoView
  vi.restoreAllMocks()
})

describe('DecisionFlowPanel 演变角标', () => {
  it('main 节点显示跨会议角标；history 节点指向另一场会议的最新推进', async () => {
    // 借锚点把闭档组展开（history 节点 c1 在闭档组内），但不给来源横幅
    const w = mountPanel({ anchorTodoId: 'c1' })
    await flushPromises()
    await tick(250)

    const badges = w.findAll('.db-evo-badge')
    expect(badges).toHaveLength(2)

    const text = w.text()
    expect(text).toContain('跨 2 场会议持续讨论')
    expect(text).toContain(ZH.decisions.meeting_evo_badge_history)
    expect(text).toContain('《新会议》')
    expect(text).toContain(ZH.decisions.meeting_evo_view_topic)

    // 无演变归属的开放节点不出角标
    const a2Cell = w.find('[data-todo-id="a2"]').element.parentElement
    expect(a2Cell?.querySelector('.db-evo-badge')).toBeNull()
  })
})

describe('DecisionFlowPanel 节点锚点（?todo=&from=evolution）', () => {
  it('锚到闭档节点：自动展开闭档组、滚动、闪烁高亮，并显示来源横幅', async () => {
    const w = mountPanel({ anchorTodoId: 'c1', fromEvolution: true })
    await flushPromises()
    await tick(250)

    // 闭档组默认折叠；锚点必须先把组展开，节点才在 DOM 中
    const node = w.find('.db-node[data-todo-id="c1"]')
    expect(node.exists()).toBe(true)
    expect(node.classes()).toContain('evo-anchor-flash')
    expect(scrollSpy).toHaveBeenCalledTimes(1)

    const banner = w.find('.db-evo-banner')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('已替代的旧决策')
    expect(banner.text()).toContain(ZH.decisions.meeting_evo_banner_goto_center)
  })

  it('横幅可关闭', async () => {
    const w = mountPanel({ anchorTodoId: 'a1', fromEvolution: true })
    await flushPromises()
    await tick(200)
    expect(w.find('.db-evo-banner').exists()).toBe(true)

    await w.find('.db-evo-banner-x').trigger('click')
    expect(w.find('.db-evo-banner').exists()).toBe(false)
  })

  it('无锚点/无来源标识：不出横幅，闭档组保持折叠（旧决策默认隐藏）', async () => {
    const w = mountPanel()
    await flushPromises()
    await tick(200)

    expect(w.find('.db-evo-banner').exists()).toBe(false)
    expect(w.find('.db-node[data-todo-id="c1"]').exists()).toBe(false)
    expect(scrollSpy).not.toHaveBeenCalled()
  })
})
