/**
 * Lucide 图标 path 数据（16×16 描边风格，与全局内联 SVG 惯例一致）
 * 仅收录 AI 对话阶段/工具调用标签用到的图标；新增图标按需补充，
 * 禁止引入整包图标库（项目零 UI 依赖约定）。
 */

export interface IconDef {
  viewBox: string
  /** SVG 子元素（path/circle/rect 等）拼串，stroke 由外层统一控制 */
  body: string
}

const LUCIDE_ICONS: Record<string, IconDef> = {
  'file-text': { viewBox: '0 0 24 24', body: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>' },
  'pen-line': { viewBox: '0 0 24 24', body: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>' },
  'pencil': { viewBox: '0 0 24 24', body: '<path d="M21.2 8.6c-1.5-1.5-4.1-1.4-5.4-.3L4 19.9 3 22l2.1-1 11.6-11.6c1.1-1.3 1.2-3.9-.3-5.4Z"/><path d="m15 5 4 4"/>' },
  'terminal': { viewBox: '0 0 24 24', body: '<path d="m4 17 6-6-6-6"/><path d="M12 19h8"/>' },
  'search': { viewBox: '0 0 24 24', body: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>' },
  'list-filter': { viewBox: '0 0 24 24', body: '<path d="M3 6h18"/><path d="M7 12h10"/><path d="M10 18h4"/>' },
  'bot': { viewBox: '0 0 24 24', body: '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>' },
  'clipboard-list': { viewBox: '0 0 24 24', body: '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/>' },
  'check-square': { viewBox: '0 0 24 24', body: '<path d="m9 11 3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>' },
  'list': { viewBox: '0 0 24 24', body: '<path d="M3 12h.01"/><path d="M3 18h.01"/><path d="M3 6h.01"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M8 6h13"/>' },
  'globe': { viewBox: '0 0 24 24', body: '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>' },
  'telescope': { viewBox: '0 0 24 24', body: '<path d="m10.065 12.493-6.18 1.318a.934.934 0 0 1-1.108-.702l-.537-2.15a1.07 1.07 0 0 1 .691-1.265l13.504-4.44"/><path d="m13.56 11.747 4.332-.924"/><path d="m16 21-3.105-6.21"/><path d="M16.485 5.94a2 2 0 0 1 1.455-1.94l1.09-.294a1 1 0 0 1 1.212.72l.666 2.663a1 1 0 0 1-.55 1.147l-.822.408a2 2 0 0 1-2.253-.288Z"/><path d="m8 15 1.485-2.97a2 2 0 0 1 2.62-.96l4.45 1.78a2 2 0 0 1 1.14 2.54l-.96 2.4"/>' },
  'plug': { viewBox: '0 0 24 24', body: '<path d="M12 22v-5"/><path d="M9 8V2"/><path d="M15 8V2"/><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z"/>' },
  'wrench': { viewBox: '0 0 24 24', body: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76Z"/>' },
  'check': { viewBox: '0 0 24 24', body: '<path d="M20 6 9 17l-5-5"/>' },
  'x': { viewBox: '0 0 24 24', body: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>' },
  'alert-triangle': { viewBox: '0 0 24 24', body: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/>' },
  'help-circle': { viewBox: '0 0 24 24', body: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>' },
  'sparkles': { viewBox: '0 0 24 24', body: '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/>' },
}

/** 按 lucide 图标名取 SVG 定义；未知名返回 null（调用方降级为文本/emoji） */
export function lucideIcon(name?: string | null): IconDef | null {
  if (!name) return null
  return LUCIDE_ICONS[name] || null
}
