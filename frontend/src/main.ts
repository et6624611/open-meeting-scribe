import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import i18n, { loadLocaleMessages, getLocale } from './i18n'

// 样式引入顺序： / Style import order:
// 1. 主题变量（CSS 自定义属性，必须最先加载） / 1. Theme variables (CSS custom properties; must load first)
import './styles/themes/standard-light.css'
import './styles/themes/standard-dark.css'
import './styles/themes/default.css'
import './styles/themes/dark.css'
import './styles/themes/warm.css'
import './styles/themes/forest.css'
import './styles/themes/mist.css'
import './styles/themes/moss.css'
import './styles/themes/wheat.css'
import './styles/themes/moonlight.css'
// 2. 模块化 CSS（按功能域拆分） / 2. Modular CSS (split by functional domain)
import './styles/base.css'
import './styles/layout.css'
import './styles/topbar.css'
import './styles/sidebar.css'
import './styles/activity-rail.css'
import './styles/ai-panel.css'
import './styles/components.css'
import './styles/recording.css'
import './styles/recording-view.css'
import './styles/shared-list.css'
import './styles/speakers.css'
import './styles/hotwords.css'
import './styles/start-page.css'
import './styles/import-dialog.css'
import './styles/meeting-view.css'
import './styles/ai-canvas.css'
import './styles/auth.css'
import './styles/update-panel.css'
import './styles/notes-editor.css'
import './styles/summary-panel.css'

// ─── 启动：先确保「初始语言」的语言包已加载，再挂载应用 ─── / ─── Startup: ensure initial locale messages loaded before mounting app ───
// en 已在 i18n 模块静态内置（零延迟）；但 detectLocale() 可能返回 zh-CN / en is statically built-in in i18n module (zero delay); but detectLocale() may return zh-CN
// （上次切换后 localStorage 持久化了 zh-CN）。此时若不先 / (localStorage persisted zh-CN from last switch). Without
// 动态加载 zh-CN 语言包，首屏会因缺少消息而回退到 en，造成「语言选择器 / dynamically loading zh-CN messages first, the first screen falls back to en due to missing messages,
// 高亮 中文、界面却是英文」的不一致（刷新后必现）。故挂载前先 await 加载。 / causing "selector highlights Chinese but UI shows English" inconsistency (always after refresh). So await load before mount.
async function bootstrap() {
  try {
    await loadLocaleMessages(getLocale())
  } catch (err) {
    // 加载失败时静默回退：en 已静态内置，保证应用仍可挂载 / Silent fallback on load failure: en is statically built-in, ensuring app can still mount
    console.error('初始语言包加载失败，回退到默认语言 en', err)
  }

  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.use(i18n)

  // ─── 全局错误捕获（自愈层） ─── / ─── Global error handler (self-healing layer) ───
  // 未捕获的组件异常统一记录到控制台，便于桌面端排查； / Log uncaught component errors to console for desktop debugging;
  // 各业务模块已有局部 try/catch，此处仅作兆底。 / business modules already have local try/catch; this is just a fallback.
  app.config.errorHandler = (err, instance, info) => {
    console.error('[OMS] Unhandled error:', err)
    console.error('[OMS] Component:', (instance as any)?.$options?.name || '<unknown>')
    console.error('[OMS] Info:', info)
  }
  // 捕获 Promise 未处理拒绝（如 API 调用失败后未 catch） / Catch unhandled Promise rejections (e.g. API call failure without catch)
  window.addEventListener('unhandledrejection', (event) => {
    console.error('[OMS] Unhandled promise rejection:', event.reason)
  })

  app.mount('#app')
}
bootstrap()

// ═══ 全局 tooltip（L2 防护层） ═══ / ═══ Global tooltip (L2 guard layer) ═══
// 单一 DOM 元素挂载在 document.body，position: fixed 定位， / Single DOM element mounted on document.body, position: fixed,
// 不受 .body { overflow: hidden } 等父容器裁剪。 / not clipped by parent containers like .body { overflow: hidden }.
// 读取 data-tip 或 title 属性作为文本，同时抑制浏览器原生 title tooltip。 / Reads data-tip or title attribute as text; suppresses native browser title tooltip.
const TOOLTIP_EXCLUDE = '.usage-chart-bar'

const tooltipEl = document.createElement('div')
tooltipEl.id = 'global-tooltip'
document.body.appendChild(tooltipEl)

// 检测元素是否为"..."更多按钮（三个圆点图标已是通用符号，无需 tooltip 提示） / Check if element is "..." more button (three-dot icon is already a universal symbol; no tooltip needed)
function isMoreButton(el: HTMLElement): boolean {
  // 检查元素自身或其子元素是否包含"..."图标 SVG（三个 circle） / Check if element or its children contain "..." icon SVG (three circles)
  const svg = el.querySelector?.('svg') || el
  const circles = svg.querySelectorAll?.('circle')
  if (circles && circles.length === 3) {
    // 水平排列：cx 分别为 5, 12, 19 / Horizontal layout: cx values are 5, 12, 19
    const cxValues = Array.from(circles).map(c => c.getAttribute('cx'))
    if (cxValues.includes('5') && cxValues.includes('12') && cxValues.includes('19')) {
      return true
    }
    // 垂直排列：cy 分别为 5, 12, 19（如 TaskCard 的"更多"按钮） / Vertical layout: cy values are 5, 12, 19 (e.g. TaskCard "more" button)
    const cyValues = Array.from(circles).map(c => c.getAttribute('cy'))
    if (cyValues.includes('5') && cyValues.includes('12') && cyValues.includes('19')) {
      return true
    }
  }
  return false
}

// 检测按钮元素内部是否已包含可见文字标签（自身已有文字则无需 tooltip 重复提示） / Check if button already contains visible text label (no need for redundant tooltip if text exists)
function hasVisibleText(el: HTMLElement): boolean {
  // 克隆节点以移除 SVG 图标，再检查剩余文字内容 / Clone node to remove SVG icons, then check remaining text content
  const clone = el.cloneNode(true) as HTMLElement
  clone.querySelectorAll('svg').forEach(s => s.remove())
  const text = (clone.textContent || '').trim()
  return text.length > 0
}

function showTooltip(e: Event) {
  const target = e.target as HTMLElement
  const el = target.closest?.('[data-tip], [title]') as HTMLElement | null
  if (!el || el.matches(TOOLTIP_EXCLUDE)) return
  // "..."更多按钮是通用符号，不需要 tooltip 提示 / "..." more button is a universal symbol; no tooltip needed
  if (isMoreButton(el)) return
  // 按钮自身已包含可见文字标签，tooltip 会造成文字叠加冗余 / Button already has visible text label; tooltip would cause text overlay redundancy
  if (el.tagName === 'BUTTON' && hasVisibleText(el)) return

  const text = el.dataset.tip || el.title || ''
  if (!text) {
    // data-tip/title 已变为空字符串（如菜单打开时），隐藏已显示的 tooltip / data-tip/title became empty (e.g. when menu opens); hide shown tooltip
    tooltipEl.classList.remove('is-visible')
    return
  }

  // 抑制浏览器原生 title tooltip（将 title 暂存到 data-original-title） / Suppress native browser title tooltip (stash title to data-original-title)
  if (el.title && !el.dataset.originalTitle) {
    el.dataset.originalTitle = el.title
    el.removeAttribute('title')
  }

  tooltipEl.textContent = text
  tooltipEl.classList.add('is-visible')

  // 定位：鼠标事件用光标坐标，键盘聚焦用元素位置 / Position: mouse events use cursor coords; keyboard focus uses element position
  if ('clientX' in e && e.clientX) {
    positionTooltip(e as MouseEvent)
  } else {
    const r = el.getBoundingClientRect()
    tooltipEl.style.left = (r.right + 8) + 'px'
    tooltipEl.style.top = (r.top + r.height / 2 - 14) + 'px'
  }
}

function positionTooltip(e: MouseEvent) {
  const x = e.clientX + 12
  const y = e.clientY - 4
  const rect = tooltipEl.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight

  tooltipEl.style.left = (x + rect.width > vw ? e.clientX - rect.width - 8 : x) + 'px'
  tooltipEl.style.top = (y + rect.height > vh ? e.clientY - rect.height - 8 : y) + 'px'
}

function hideTooltip(e: Event) {
  const me = e as MouseEvent
  const target = e.target as HTMLElement
  const el = target.closest?.('[data-tip], [title], [data-original-title]') as HTMLElement | null

  // 鼠标仍在同一触发元素内部移动，不隐藏 / Mouse still moving within same trigger element; don't hide
  const related = me.relatedTarget as Node | null
  if (el && related && el.contains(related)) return

  tooltipEl.classList.remove('is-visible')

  // 恢复浏览器原生 title 属性 / Restore native browser title attribute
  if (el?.dataset.originalTitle) {
    el.title = el.dataset.originalTitle
    delete el.dataset.originalTitle
  }
}

document.addEventListener('mouseover', showTooltip, true)
document.addEventListener('mousemove', (e: Event) => {
  if (tooltipEl.classList.contains('is-visible')) positionTooltip(e as MouseEvent)
}, true)
document.addEventListener('mouseout', hideTooltip, true)
document.addEventListener('focusin', showTooltip, true)
document.addEventListener('focusout', hideTooltip, true)
