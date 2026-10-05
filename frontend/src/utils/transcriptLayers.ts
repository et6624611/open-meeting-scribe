/**
 * 转写分层展示辅助（PLAN-TRANSCRIPT-LAYERING）/ Transcript-layering display helpers
 *
 * 会中/会后面板共用的清理明细聚合；视图判定（clean_text 回落原文）由各面板内联。
 */
import type { Ref } from 'vue'
import type { CleanOp } from '@/composables/useWebSocket'

type TranslationFn = (key: string, named?: Record<string, unknown>) => string

/** 转写三层视图取值（书面版/清理版/原文）/ Transcript layer view values */
export type LayerView = 'formal' | 'clean' | 'raw'

/**
 * 把 clean_ops 流水聚合为一句可读明细，例如：
 * 「移除语气词 3（嗯、呃、啊）；合并重复 1（得）」
 * Aggregate cleanup ops into one human-readable line under the given i18n namespace
 * ('recording.layer.*' or 'generating.layer.*').
 */
export function cleanupRuleText(
  t: TranslationFn,
  ops: CleanOp[] | undefined,
  namespace: 'recording' | 'generating',
): string {
  if (!ops || !ops.length) return ''
  const parts: string[] = []
  const groups: Array<{ r: CleanOp['r']; suffix: string }> = [
    { r: 'filler', suffix: 'op_filler' },
    { r: 'dup', suffix: 'op_dup' },
    { r: 'punct', suffix: 'op_punct' },
  ]
  for (const g of groups) {
    const matched = ops.filter((o) => o.r === g.r)
    if (!matched.length) continue
    const n = matched.reduce((sum, o) => sum + o.n, 0)
    let text = t(`${namespace}.layer.${g.suffix}`, { n })
    const items = matched.flatMap((o) => o.items ?? [])
    if (items.length) {
      text += t(`${namespace}.layer.op_items`, { items: items.join(t(`${namespace}.layer.op_join`)) })
    }
    parts.push(text)
  }
  return parts.join(t(`${namespace}.layer.op_sep`))
}

/**
 * 三层分段控件键盘导航：←/→ 循环（跳过 disabled）、Home/End 跳首尾，自动激活。
 * Segmented tablist keyboard nav: arrows cycle past disabled items, Home/End jump (automatic activation).
 * 返回挂在 tablist 容器上的 keydown 处理器 / Returns the handler for the tablist container.
 */
export function segKeydownHandler(btns: Array<Ref<HTMLButtonElement | null>>): (e: KeyboardEvent) => void {
  return (e: KeyboardEvent) => {
    const current = btns.findIndex((r) => r.value === e.target)
    if (current < 0) return
    let target = -1
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      const step = e.key === 'ArrowRight' ? 1 : -1
      let i = current
      for (let k = 0; k < btns.length; k++) {
        i = (i + step + btns.length) % btns.length
        if (!btns[i].value?.disabled) { target = i; break }
      }
    } else if (e.key === 'Home') {
      target = btns.findIndex((r) => !r.value?.disabled)
    } else if (e.key === 'End') {
      for (let i = btns.length - 1; i >= 0; i--) {
        if (!btns[i].value?.disabled) { target = i; break }
      }
    }
    if (target >= 0) {
      e.preventDefault()
      btns[target].value?.focus()
      btns[target].value?.click()
    }
  }
}
