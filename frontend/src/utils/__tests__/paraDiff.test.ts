import { describe, expect, it } from 'vitest'
import { allChoices, diffParas, mergedText, mergeParas, splitParas, type ParaOp } from '../paraDiff'

describe('splitParas（空行分段）', () => {
  it('连续空行并一个分隔；段内换行保留', () => {
    expect(splitParas('A\nB\n\n\nC\n')).toEqual(['A\nB', 'C'])
    expect(splitParas('')).toEqual([])
  })
})

describe('diffParas（LCS 对齐）', () => {
  it('同文透传 same，零 change', () => {
    const t = splitParas('P1\n\nP2')
    const m = splitParas('P1\n\nP2')
    expect(diffParas(t, m)).toEqual([{ kind: 'same', text: 'P1' }, { kind: 'same', text: 'P2' }])
  })

  it('中段单替换=一 change 块（theirs/mine 各一段）', () => {
    const ops = diffParas(splitParas('A\n\nT\n\nC'), splitParas('A\n\nM\n\nC'))
    expect(ops.map((o) => o.kind)).toEqual(['same', 'change', 'same'])
    const ch = ops[1] as Extract<ParaOp, { kind: 'change' }>
    expect(ch.theirs).toEqual(['T'])
    expect(ch.mine).toEqual(['M'])
  })

  it('纯新增段（mine 独有）与纯删除段（theirs 独有）各自成 change 块且一侧可为空', () => {
    const ops = diffParas(splitParas('A\n\nB'), splitParas('A\n\nX\n\nB'))
    const change = ops.find((o) => o.kind === 'change') as Extract<ParaOp, { kind: 'change' }>
    expect(change.mine).toEqual(['X'])
    const ops2 = diffParas(splitParas('A\n\nY\n\nB'), splitParas('A\n\nB'))
    const change2 = ops2.find((o) => o.kind === 'change') as Extract<ParaOp, { kind: 'change' }>
    expect(change2.theirs).toEqual(['Y'])
  })

  it('保真红线：any op 序列重放——两侧每一段都必出现在某一侧，不可凭空丢段', () => {
    const theirs = splitParas('一\n\n二\n\n三\n\n四')
    const mine = splitParas('一\n\n贰改\n\n四')
    const ops = diffParas(theirs, mine)
    const inOps = ops.flatMap((o) => (o.kind === 'same' ? [o.text] : [...o.theirs, ...o.mine]))
    for (const p of [...theirs, ...mine]) expect(inOps).toContain(p)
  })
})

describe('mergeParas/mergedText（逐段可验合并）', () => {
  const ops = diffParas(splitParas('A\n\n他们的新段\n\nC'), splitParas('A\n\n我的修改段\n\nC'))

  it('默认选择=mine（保用户编辑意图）；全用他们的快捷可翻转', () => {
    expect(mergeParas(ops, {})).toEqual(['A', '我的修改段', 'C'])
    expect(mergedText(ops, allChoices(ops, 'theirs'))).toBe('A\n\n他们的新段\n\nC')
    expect(mergedText(ops, allChoices(ops, 'mine'))).toBe('A\n\n我的修改段\n\nC')
  })

  it('混合选择：按 change 块索引逐块取舍，same 透传不受影响', () => {
    const mixed = diffParas(splitParas('T1\n\nK\n\nT2'), splitParas('M1\n\nK\n\nM2'))
    const chIdx = mixed.map((o, i) => (o.kind === 'change' ? i : -1)).filter((i) => i >= 0)
    const choices: Record<number, 'theirs' | 'mine'> = { [chIdx[0]!]: 'theirs' }
    const out = mergeParas(mixed, { ...allChoices(mixed, 'mine'), ...choices })
    expect(out).toEqual(['T1', 'K', 'M2'])
  })

  it('词表单文本框退化形态=每行一段同样可 diff（行级合并）', () => {
    const t = splitParas('苹果\n香蕉')
    const m = splitParas('苹果\n橘子\n西瓜')
    const merged = mergedText(diffParas(t, m), allChoices(diffParas(t, m), 'mine'))
    expect(merged).toBe('苹果\n橘子\n西瓜')
  })
})
