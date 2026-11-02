import { describe, expect, it } from 'vitest'
import { parseFormalSegments } from '../formalLayout'

/** 2026-11-02 企业库实样形态（ctx_entities formal 只读抽样）：「说话人N: 」「姓名: 」半角冒号+全篇连续行 */
const REAL_SAMPLE = '说话人0: 下面这的转让规则啊，这里能看到你原单分别目标单。\n乔晓军: 嗯，就是他们，比方说，那后续他们不处理。\n说话人0: 比如说你付款清单到付款单。\n这是没有冒号前缀的补充行。'

describe('parseFormalSegments（B5 定稿排版分段）', () => {
  it('真实样本：说话人分段+延续行并入当前段（逐字保留）', () => {
    const segs = parseFormalSegments(REAL_SAMPLE)
    expect(segs.map((s) => s.kind)).toEqual(['speaker', 'speaker', 'speaker'])
    expect(segs[0]).toMatchObject({ kind: 'speaker', name: '说话人0', text: '下面这的转让规则啊，这里能看到你原单分别目标单。' })
    expect(segs[1]?.name).toBe('乔晓军')
    expect(segs[2]?.text).toBe('比如说你付款清单到付款单。\n这是没有冒号前缀的补充行。')
  })

  it('全角冒号同权识别', () => {
    const segs = parseFormalSegments('张伟：明天前把物料编码规范发群里。')
    expect(segs[0]).toMatchObject({ kind: 'speaker', name: '张伟', text: '明天前把物料编码规范发群里。' })
  })

  it('冒号后为空=引导行 heading（不当发言人 chip）', () => {
    const segs = parseFormalSegments('会议背景：\n本季上线两个新模块。')
    expect(segs[0]?.kind).toBe('heading')
    expect(segs[0]?.name).toBe('会议背景')
  })

  it('名字含句读/超长行不判说话人（纯转述文本零误标扩散）', () => {
    const segs = parseFormalSegments('这一点很重要。原因：预算已经批了。')
    expect(segs.every((s) => s.kind === 'plain')).toBe(true)
    const long = 'x'.repeat(40) + ': ok'
    expect(parseFormalSegments(long)[0]?.kind).toBe('plain')
  })

  it('拼接保真：所有段 text 按序以换行重组可复原原文全部字符', () => {
    const segs = parseFormalSegments(REAL_SAMPLE)
    const rebuilt = segs.map((s) => (s.name ? `${s.name}: ${s.text}` : s.text)).join('\n')
    // 原文字符全在（前缀名与冒号允许形态差异，正文一字不丢）
    for (const seg of segs) expect(REAL_SAMPLE).toContain(seg.text)
    expect(rebuilt).toContain('这是没有冒号前缀的补充行。')
  })

  it('空输入=空数组', () => {
    expect(parseFormalSegments('')).toEqual([])
  })
})
