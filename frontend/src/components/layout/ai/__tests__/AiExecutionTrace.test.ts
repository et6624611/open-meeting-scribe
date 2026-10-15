import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AiExecutionTrace from '../AiExecutionTrace.vue'
import type { AgentStage } from '@/api/chat'
import zh from '@/i18n/locales/zh-CN/ai-panel.json'
import en from '@/i18n/locales/en/ai-panel.json'

const stage: AgentStage = {
  type: 'tool_call', id: 'read-1', label: '读取会议文件', label_en: 'Read meeting file',
  status: 'done', icon: 'file-text', name: 'Read', input: '{"path":"会议.md"}',
  detail: '会议记录摘要', output: '会议原文\n'.repeat(100) + '完整结尾',
}
function render(stages: AgentStage[] = [stage], live = false, locale = 'zh-CN') {
  return mount(AiExecutionTrace, { props: { stages, live, state: live ? 'running' : 'done' }, global: { plugins: [
    createI18n({ legacy: false, locale, messages: { 'zh-CN': { 'ai-panel': zh }, en: { 'ai-panel': en } } }),
  ] } })
}
afterEach(() => vi.restoreAllMocks())

describe('执行过程交互', () => {
  it('执行时展开，完成后折叠但保留入口和全部详情', async () => {
    const wrapper = render([stage], true)
    expect((wrapper.element as HTMLDetailsElement).open).toBe(true)
    await wrapper.setProps({ live: false, state: 'done' })
    expect((wrapper.element as HTMLDetailsElement).open).toBe(false)
    expect(wrapper.find('summary').text()).toContain('执行过程')
    ;(wrapper.element as HTMLDetailsElement).open = true
    await wrapper.trigger('toggle')
    expect(wrapper.findAll('pre')[0]!.text()).toContain('会议.md')
    expect(wrapper.findAll('pre')[1]!.text()).toContain('完整结尾')
    expect(wrapper.findAll('pre')[1]!.attributes('tabindex')).toBe('0')
    wrapper.unmount()
  })

  it('完成后异常摘要与未授权状态可见，不变成成功', () => {
    const wrapper = render([{ ...stage, status: 'denied', output: '未授权，未执行' }, { ...stage, id: 'read-2', status: 'error' }])
    expect(wrapper.find('summary').text()).toContain('2 项异常')
    expect(wrapper.find('.is-denied .trace-status').text()).toBe('未授权')
    expect(wrapper.find('.is-error .trace-status').text()).toBe('失败')
    wrapper.unmount()
  })

  it('折叠入口明确显示补写已落盘，同时保留整轮失败', async () => {
    const wrapper = render([{ type: 'board_retry', label: '正在补写', status: 'done' },
      { ...stage, status: 'error', output: '等待后续输出超时' }])
    await wrapper.setProps({ state: 'error' })
    expect((wrapper.element as HTMLDetailsElement).open).toBe(false)
    expect(wrapper.find('summary').text()).toContain('洞察板补写已落盘')
    expect(wrapper.find('summary').text()).toContain('失败')
    wrapper.unmount()
  })

  it('停止和刷新后的补写不继续显示正在执行', () => {
    const wrapper = render([{ type: 'board_retry', label: '正在补写', status: 'interrupted' }])
    expect(wrapper.find('summary').text()).toContain('洞察板补写结果未确认')
    expect(wrapper.find('summary').text()).not.toContain('正在补写')
    wrapper.unmount()
  })

  it('旧消息兼容，截断与仅摘要情况明确提示', () => {
    const wrapper = render([
      { type: 'tool_call', label: '旧步骤', status: 'done', detail: '旧摘要' },
      { ...stage, inputTruncated: true, outputTruncated: true },
      { ...stage, output: undefined },
    ])
    expect(wrapper.text()).toContain(zh.execution.legacy)
    expect(wrapper.text()).toContain(zh.execution.truncated)
    expect(wrapper.text()).toContain(zh.execution.summary_only)
    wrapper.unmount()
  })

  it('复制时包含输入、输出和真实状态', async () => {
    const writeText = vi.fn(async () => {})
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const wrapper = render()
    await wrapper.find('button').trigger('click')
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('会议.md'))
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('完整结尾'))
    expect(wrapper.find('button').text()).toBe('已复制')
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('工具返回的 HTML 只作为文本显示', () => {
    const wrapper = render([{ ...stage, output: '<img src=x onerror="alert(1)">' }])
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.findAll('pre')[1]!.text()).toContain('<img')
    wrapper.unmount()
  })

  it('英语界面沿用双语标签，历史运行态显示未确认', () => {
    const wrapper = render([{ ...stage, status: 'running' }], false, 'en')
    expect(wrapper.find('summary').text()).toContain('Execution trace')
    expect(wrapper.find('.trace-label').text()).toBe('Read meeting file')
    expect(wrapper.find('.trace-status').text()).toBe('Result unconfirmed')
    wrapper.unmount()
  })
})
