/**
 * 洞察板主题令牌桥 / Insight Board theme tokens
 *
 * 版式归 CLI 后，板不再是宿主 DOM 的一部分（渲染在 sandbox iframe 的独立文档里），
 * 拿不到应用的 CSS 变量。这里把宿主当前主题的变量**值**取出来，经 postMessage 下发，
 * 由桥接脚本以**低优先级样式表**写进板文档（插到 head 最前，板自己的 `:root{}` 后来者胜）。
 *
 * 口径（三条，都不算排版意见）：
 * 1. 全量转发比挑子集更诚实：CLI 想用哪个就用哪个，应用不替它决定；
 * 2. 注入语义是**兜底而非覆写**：板自定义了同名令牌就听板的，没自定义才跟随宿主。
 *    早期版本用 inline style 逐条写，优先级高于板的 `:root{}`，板只重定义部分同名变量时
 *    会出现「背景跟宿主、文字跟板」的混合故障（实测白底白字），故整体改为样式表注入；
 * 3. 别名映射沿用旧 `.ib-html` 容器提供的对照（notes-editor.css 已退役的那份），
 *    让习惯写 `--success/--danger-bg` 这类"非应用真名"的旧提示词仍然解析得开——
 *    这是在替 CLI 兜排版债，迁移期结束后随旧类名一起下线。
 *
 * 取不到值的变量直接跳过（不写空串），让板自己的默认值生效；
 * 板内硬编码色保持硬编码——两种写法都合法，由 CLI 决定。
 * ⚠️ 只有 iframe 路径会下发令牌：`raw` 端点（在浏览器中打开）没有桥接，
 *    板若用 `var(--bg)` 必须自带兜底值，否则在那个出口下没有颜色来源。
 */

/** 应用真名令牌（见 frontend/src/styles/themes/standard-light.css） */
const CORE_TOKENS = [
  '--bg', '--surface', '--surface-2', '--surface-3',
  '--fg', '--fg-inv', '--muted', '--subtle',
  '--border', '--border-strong',
  '--accent', '--accent-soft', '--accent-fg', '--accent-strong',
  '--ok', '--ok-soft', '--warn', '--warn-soft', '--info', '--info-soft',
  '--error', '--error-soft', '--purple', '--purple-soft', '--proactive',
  '--font-body', '--font-mono',
  '--fs-11', '--fs-12', '--fs-13', '--fs-14', '--fs-15', '--fs-16',
  '--fs-18', '--fs-20', '--fs-24',
  '--s-1', '--s-2', '--s-3', '--s-4', '--s-5', '--s-6', '--s-7', '--s-8', '--s-9', '--s-10',
  '--radius-sm', '--radius', '--radius-lg', '--radius-pill',
  '--shadow-focus', '--dropdown-shadow', '--glass-blur-lg',
]

/** 旧 .ib-html 容器为 AI 惯用名提供的别名（迁移期保留，之后随旧类名一起下线） */
const ALIAS_TOKENS: Record<string, string> = {
  '--surface-alt': '--surface-2',
  '--surface-card': '--surface',
  '--fg-secondary': '--muted',
  '--fg-muted': '--subtle',
  '--accent-light': '--accent-soft',
  '--success': '--ok',
  '--success-bg': '--ok-soft',
  '--warning': '--warn',
  '--warning-bg': '--warn-soft',
  '--danger': '--error',
  '--danger-bg': '--error-soft',
  '--info-bg': '--info-soft',
  '--purple-bg': '--purple-soft',
}

/**
 * 读取当前主题的令牌值 / Resolve the live theme token map.
 *
 * 从 body 的计算样式取值（而非 :root）：主题变量定义在 `html[data-theme=…]` 上，
 * 但板文档同样会写到自己的 `:root`，父侧只是取值、不参与渲染，取哪个都行；
 * 用 body 是为了避开 `:root` 上少量仅在特定选择器下才生效的覆盖。
 */
export function boardThemeTokens(): Record<string, string> {
  const out: Record<string, string> = {}
  if (typeof document === 'undefined') return out
  const cs = getComputedStyle(document.body)
  const readOne = (name: string): string => cs.getPropertyValue(name).trim()
  for (const name of CORE_TOKENS) {
    const v = readOne(name)
    if (v) out[name] = v
  }
  for (const [alias, real] of Object.entries(ALIAS_TOKENS)) {
    const v = readOne(real)
    if (v) out[alias] = v
  }
  // 兜底：板文档没有 box-sizing 重置时，绝对定位与百分比宽度容易算错（不是排版意见，是几何下限）
  out['__ib_reset'] = '*,*::before,*::after{box-sizing:border-box}'
  return out
}
