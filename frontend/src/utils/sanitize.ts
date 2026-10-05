/**
 * HTML 转义工具，防止 XSS。 / HTML escape utility to prevent XSS.
 * 在通过 v-html 渲染用户生成内容（UGC）或 AI 生成内容前必须调用。 / Must call before rendering user-generated content (UGC) or AI-generated content via v-html.
 */
export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}
