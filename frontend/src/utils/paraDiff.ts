/**
 * 段落级 diff 对齐（WP-5 冲突合并弹窗核心，规格 §6 下限形态=交付形态）
 *
 * 零依赖：空行切段（Markdown block 级）+ 段落序列 LCS 动态规划（段数量级 <200，O(n·m) 无压力）。
 * 方向约定：theirs=服务器新版（他人已保存的 latest），mine=本地编辑草稿。
 * 输出 ops 保序可渲染；合并=对每个 change 段选择一侧整段，same 透传——合并结果是所选段落的原文拼接，
 * 不做字符级改写（"逐段可验"验收断言的立足点）。
 */

export type ParaOp =
  | { kind: 'same'; text: string }
  | { kind: 'change'; theirs: string[]; mine: string[] }

/** 空行分段：连续空行算一个分隔；行内换行保留在段文本内 */
export function splitParas(text: string): string[] {
  if (!text) return []
  const paras: string[] = []
  let cur: string[] = []
  for (const line of text.split('\n')) {
    if (line.trim() === '') {
      if (cur.length) { paras.push(cur.join('\n')); cur = [] }
    } else {
      cur.push(line)
    }
  }
  if (cur.length) paras.push(cur.join('\n'))
  return paras
}

/** LCS 对齐两侧段落序列 → 保序 ops（标准回溯：same/del-theirs/ins-mine 三 run，相邻两 run 聚合成一个 change 块） */
export function diffParas(theirs: string[], mine: string[]): ParaOp[] {
  const n = theirs.length
  const m = mine.length
  // dp[i][j] = LCS(theirs[i:], mine[j:])
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i]![j] = theirs[i] === mine[j]
        ? dp[i + 1]![j + 1]! + 1
        : Math.max(dp[i + 1]![j]!, dp[i]![j + 1]!)
    }
  }
  type Raw = { kind: 'same'; text: string } | { kind: 'theirs'; text: string } | { kind: 'mine'; text: string }
  const raw: Raw[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (theirs[i] === mine[j]) {
      raw.push({ kind: 'same', text: theirs[i]! })
      i++; j++
    } else if (dp[i + 1]![j]! >= dp[i]![j + 1]!) {
      raw.push({ kind: 'theirs', text: theirs[i]! })
      i++
    } else {
      raw.push({ kind: 'mine', text: mine[j]! })
      j++
    }
  }
  while (i < n) { raw.push({ kind: 'theirs', text: theirs[i]! }); i++ }
  while (j < m) { raw.push({ kind: 'mine', text: mine[j]! }); j++ }

  // run 聚合：连续 theirs-run 紧跟连续 mine-run（或反序）→ 一个 change 块；same 透传
  const ops: ParaOp[] = []
  let k = 0
  while (k < raw.length) {
    const r = raw[k]!
    if (r.kind === 'same') { ops.push({ kind: 'same', text: r.text }); k++; continue }
    const theirsSeg: string[] = []
    const mineSeg: string[] = []
    while (k < raw.length && raw[k]!.kind === 'theirs') { theirsSeg.push((raw[k] as { text: string }).text); k++ }
    while (k < raw.length && raw[k]!.kind === 'mine') { mineSeg.push((raw[k] as { text: string }).text); k++ }
    // 若 mine-run 在前（回溯方向导致），上面第一循环收到 theirsSeg=0、第二循环前 raw[k] 是 mine——补齐：
    if (!theirsSeg.length && !mineSeg.length) {
      // 回溯可产生 mine-run 在前：两循环按 raw[k] 实际种类收取，此分支仅保推进（不可静默丢段）
      const rr = raw[k]!
      if (rr.kind === 'theirs') theirsSeg.push(rr.text)
      else if (rr.kind === 'mine') mineSeg.push(rr.text)
      k++
    }
    ops.push({ kind: 'change', theirs: theirsSeg, mine: mineSeg })
  }
  return ops
}

export type ChangeChoice = 'theirs' | 'mine'

/** 逐 change 块应用选择 → 段落序列（same 透传；块内保序：选谁的段序=那一侧原序） */
export function mergeParas(ops: ParaOp[], choices: Record<number, ChangeChoice>): string[] {
  const out: string[] = []
  ops.forEach((op, idx) => {
    if (op.kind === 'same') { out.push(op.text); return }
    const pick = choices[idx] ?? 'mine'
    out.push(...(pick === 'theirs' ? op.theirs : op.mine))
  })
  return out
}

/** 合并文本输出（段间分隔可参数化：纪要/笔记默认 '\n\n' 段落语义；词表 lineMode 传 '\n' 保"一行一词"原形态——UI 走查低 1） */
export function mergedText(ops: ParaOp[], choices: Record<number, ChangeChoice>, sep = '\n\n'): string {
  return mergeParas(ops, choices).join(sep)
}

/** 快捷全量选择表 */
export function allChoices(ops: ParaOp[], pick: ChangeChoice): Record<number, ChangeChoice> {
  const c: Record<number, ChangeChoice> = {}
  ops.forEach((op, idx) => { if (op.kind === 'change') c[idx] = pick })
  return c
}
