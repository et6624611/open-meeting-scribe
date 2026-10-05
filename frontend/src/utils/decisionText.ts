/**
 * 决策文本展示工具 / Decision text display helpers
 *
 * RF-F1：source=auto 的决策文本可能携带纪要里的成对 markdown 强调符号（**粗体** / __下划线__ / `代码`）。
 * 后端数据不回改，仅展示层剥除成对符号；dq 跳转参数与检索原文保留原样（纪要正文含符号才能命中）。
 */

/** 剥除成对的 ** / __ / ` 强调符号（不碰单星/单下划线，避免误伤 snake_case 与乘法记号；反引号最后剥，支持 **`x`** 嵌套） */
export function stripDecisionEmphasis(text: string): string {
  if (!text) return text
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
}
