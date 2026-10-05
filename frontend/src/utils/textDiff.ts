/**
 * frontend/src/utils/textDiff.ts — 零依赖行级文本 diff（纪要提案预览用）
 * Line-level text diff via LCS, no external dependency (keeps the bundle lean).
 *
 * 用途：AI 会话改写纪要产出"待确认提案"时，把基线正文与新正文按行做最小差异，
 * 供前端 diff 卡渲染 del/add。仅覆盖文本行，不做词内 diff（纪要整篇改写以行为粒度足够）。
 */

export interface DiffLine {
  type: 'same' | 'add' | 'del'
  text: string
}

/** 行上限：超过则退化为"整段替换"（先删旧后加新），避免 O(n*m) 失控。 */
const MAX_LINES = 3000

function splitLines(input: string): string[] {
  // 保留空行；去掉末尾换行造成的多余空串
  const arr = (input || '').split('\n')
  if (arr.length > 1 && arr[arr.length - 1] === '') arr.pop()
  return arr
}

/**
 * 计算 a → b 的行级 diff。返回顺序排列的 DiffLine 序列。
 * 标准 LCS 动态规划 + 反向回溯；超大输入走粗粒度替换兜底。
 */
export function diffLines(a: string, b: string): DiffLine[] {
  const old = splitLines(a)
  const next = splitLines(b)
  const n = old.length
  const m = next.length

  if (n === 0 && m === 0) return []
  if (n === 0) return next.map(text => ({ type: 'add' as const, text }))
  if (m === 0) return old.map(text => ({ type: 'del' as const, text }))

  // 超大输入兜底：整段替换（全部旧行 del + 全部新行 add）
  if (n > MAX_LINES || m > MAX_LINES) {
    return [
      ...old.map(text => ({ type: 'del' as const, text })),
      ...next.map(text => ({ type: 'add' as const, text })),
    ]
  }

  // dp[i][j] = old[i..] 与 next[j..] 的 LCS 长度
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = old[i] === next[j]
        ? dp[i + 1][j + 1] + 1
        : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }

  const out: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (old[i] === next[j]) {
      out.push({ type: 'same', text: old[i] })
      i++; j++
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ type: 'del', text: old[i] })
      i++
    } else {
      out.push({ type: 'add', text: next[j] })
      j++
    }
  }
  while (i < n) { out.push({ type: 'del', text: old[i] }); i++ }
  while (j < m) { out.push({ type: 'add', text: next[j] }); j++ }
  return out
}

/** diff 摘要：新增/删除行数（供横幅"改了哪几行规模"类文案，可选消费）。 */
export function diffStats(lines: DiffLine[]): { added: number; removed: number } {
  let added = 0
  let removed = 0
  for (const l of lines) {
    if (l.type === 'add') added++
    else if (l.type === 'del') removed++
  }
  return { added, removed }
}
