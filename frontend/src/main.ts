import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

// 样式引入顺序：
// 1. 主题变量（CSS 自定义属性，必须最先加载）
import './styles/themes/default.css'
import './styles/themes/dark.css'
import './styles/themes/warm.css'
import './styles/themes/forest.css'
import './styles/themes/ocean.css'
import './styles/themes/lavender.css'
import './styles/themes/rose.css'
// 2. 旧版全量 CSS（过渡文件，确保所有视图视觉完整）
import './styles/legacy-views.css'
// 3. 新版模块化 CSS（覆盖 legacy 中的重复规则）
import './styles/base.css'
import './styles/layout.css'
import './styles/topbar.css'
import './styles/sidebar.css'
import './styles/ai-panel.css'
import './styles/components.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')

// ═══ 全局 tooltip（L2 防护层） ═══
// 单一 DOM 元素挂载在 document.body，position: fixed 定位，
// 不受 .body { overflow: hidden } 等父容器裁剪。
// 读取 data-tip 或 title 属性作为文本，同时抑制浏览器原生 title tooltip。
const TOOLTIP_EXCLUDE = '.usage-chart-bar'

const tooltipEl = document.createElement('div')
tooltipEl.id = 'global-tooltip'
document.body.appendChild(tooltipEl)

// 检测元素是否为"..."更多按钮（三个圆点图标已是通用符号，无需 tooltip 提示）
function isMoreButton(el: HTMLElement): boolean {
  // 检查元素自身或其子元素是否包含"..."图标 SVG（三个 circle）
  const svg = el.querySelector?.('svg') || el
  const circles = svg.querySelectorAll?.('circle')
  if (circles && circles.length === 3) {
    // 水平排列：cx 分别为 5, 12, 19
    const cxValues = Array.from(circles).map(c => c.getAttribute('cx'))
    if (cxValues.includes('5') && cxValues.includes('12') && cxValues.includes('19')) {
      return true
    }
    // 垂直排列：cy 分别为 5, 12, 19（如 TaskCard 的"更多"按钮）
    const cyValues = Array.from(circles).map(c => c.getAttribute('cy'))
    if (cyValues.includes('5') && cyValues.includes('12') && cyValues.includes('19')) {
      return true
    }
  }
  return false
}

function showTooltip(e: Event) {
  const target = e.target as HTMLElement
  const el = target.closest?.('[data-tip], [title]') as HTMLElement | null
  if (!el || el.matches(TOOLTIP_EXCLUDE)) return
  // "..."更多按钮是通用符号，不需要 tooltip 提示
  if (isMoreButton(el)) return

  const text = el.dataset.tip || el.title || ''
  if (!text) {
    // data-tip/title 已变为空字符串（如菜单打开时），隐藏已显示的 tooltip
    tooltipEl.classList.remove('is-visible')
    return
  }

  // 抑制浏览器原生 title tooltip（将 title 暂存到 data-original-title）
  if (el.title && !el.dataset.originalTitle) {
    el.dataset.originalTitle = el.title
    el.removeAttribute('title')
  }

  tooltipEl.textContent = text
  tooltipEl.classList.add('is-visible')

  // 定位：鼠标事件用光标坐标，键盘聚焦用元素位置
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

  // 鼠标仍在同一触发元素内部移动，不隐藏
  const related = me.relatedTarget as Node | null
  if (el && related && el.contains(related)) return

  tooltipEl.classList.remove('is-visible')

  // 恢复浏览器原生 title 属性
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
