/**
 * useBoardBridge.ts — 洞察板 iframe 桥接（父侧）/ Insight Board iframe bridge (host side)
 *
 * 板是 CLI 直出的原始 HTML，呈现容器从 `v-html` 换成 `sandbox="allow-scripts"` 的 iframe：
 * 板文档落入 opaque origin，父窗口拿不到它的 DOM（双向皆然），所以原先挂在父级的一切
 * 委托逻辑（锚点点击、悬停定位、mermaid 渲染、高度自适应）都改经 postMessage 完成。
 *
 * 磁盘上始终是 CLI 的原始 HTML；桥接脚本只在内存里随 srcdoc 拼接，绝不写回。
 */
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch, type Ref } from 'vue'
import { boardThemeTokens } from '@/utils/boardThemeTokens'
import { composeBoardDoc, BOARD_SANDBOX } from '@/utils/boardBridge'
import { isDarkThemeId, renderMermaidToSvg } from '@/utils/renderMermaid'
import type { ThemeId } from '@/stores/theme'

export interface BoardHoverSec {
  id: string
  title: string
  /** 相对 iframe 文档左上角的偏移（父侧再加 iframe 滚动量换算为 .ib-root 坐标） */
  top: number
  right: number
}

interface BridgeMsg {
  __ib?: string
  ms?: number
  height?: number
  id?: string
  title?: string
  top?: number
  right?: number
  req?: string
  src?: string
}

/**
 * @param frameEl   iframe 元素 ref（模板上 ref="frameEl"）
 * @param htmlRef   当前板的落盘字节（只读，桥不改写它）
 * @param themeRef  当前主题 id（用于变量下发与 mermaid 明暗分支）
 */
export function useBoardBridge(
  frameEl: Ref<HTMLElement | null>,
  htmlRef: Ref<string>,
  themeRef: Ref<ThemeId | string>,
) {
  /** iframe 高度：由 ib:resize 持续上报（字体加载、mermaid 回传后都会二次变化） */
  const frameHeight = ref(360)
  /** 悬停节：供「共创此节」浮动按钮定位 */
  const hoverSec = shallowRef<BoardHoverSec | null>(null)
  /** 主题变量是否已随 srcdoc 变化而过期（新文档需要重新下发） */
  let stale = true

  /** 每次 html 变化重算：sandbox 取值与 srcdoc 都在这里收口，不留第二处拼接 */
  const docHtml = computed(() => (htmlRef.value ? composeBoardDoc(htmlRef.value) : ''))

  function frameWin(): Window | null {
    return (frameEl.value as HTMLIFrameElement | null)?.contentWindow || null
  }

  function postToFrame(payload: Record<string, unknown>) {
    const win = frameWin()
    // opaque origin 下 targetOrigin 只能给 '*'；数据方向是父→自己创建的子文档，无外泄面
    if (win) win.postMessage(payload, '*')
  }

  function pushTheme() {
    const vars = boardThemeTokens()
    stale = false
    postToFrame({ __ib: 'ib:theme', vars, dark: isDarkThemeId(themeRef.value as ThemeId) })
  }

  /** 浮动按钮坐标：iframe 文档坐标 + iframe 自身滚动量（跨文档拿不到 rect，只能这样换算） */
  function toHost(m: BridgeMsg): BoardHoverSec {
    const win = frameWin() as (Window & { scrollY?: number; scrollX?: number }) | null
    return {
      id: String(m.id || ''),
      title: String(m.title || ''),
      top: Number(m.top || 0) + (win?.scrollY || 0),
      right: Number(m.right || 0) + (win?.scrollX || 0),
    }
  }

  async function handleMermaid(m: BridgeMsg) {
    const req = String(m.req || '')
    const src = String(m.src || '')
    if (!req || !src) return
    try {
      const { svg } = await renderMermaidToSvg(src, isDarkThemeId(themeRef.value as ThemeId))
      // 尺寸归一（去 width + max-width:100%）在桥接脚本 applySvg 里做（父侧拿不到跨文档 DOM 元素）；
      // 不 bindFunctions：mermaid click 语句天然失效
      postToFrame({ __ib: 'ib:mermaid:ok', req, svg })
    } catch (e) {
      postToFrame({ __ib: 'ib:mermaid:err', req, message: e instanceof Error ? e.message : String(e) })
    }
  }

  const seekHandlers = new Set<(ms: number) => void>()
  const hoverHandlers = new Set<(sec: BoardHoverSec | null) => void>()

  function onMessage(e: MessageEvent) {
    const win = frameWin()
    // 来源校验：只接受本 iframe 发出的消息（opaque origin 下 event.source 仍是子 window 引用）
    if (!win || e.source !== win) return
    const m = e.data as BridgeMsg
    if (!m || typeof m !== 'object' || !m.__ib) return
    switch (m.__ib) {
      case 'ib:ready':
        pushTheme()
        break
      case 'ib:resize':
        if (typeof m.height === 'number' && m.height > 0) frameHeight.value = m.height
        break
      case 'ib:hover':
        hoverSec.value = m.id ? toHost(m) : null
        hoverHandlers.forEach(h => h(hoverSec.value))
        break
      case 'ib:seek':
        if (typeof m.ms === 'number' && Number.isFinite(m.ms) && m.ms >= 0) {
          seekHandlers.forEach(h => h(m.ms as number))
        }
        break
      case 'ib:mermaid':
        void handleMermaid(m)
        break
      default:
        break
    }
  }

  function onFrameLoad() {
    if (stale) pushTheme()
  }

  onMounted(() => {
    window.addEventListener('message', onMessage)
    if (docHtml.value) pushTheme()
  })
  onBeforeUnmount(() => {
    window.removeEventListener('message', onMessage)
    seekHandlers.clear()
    hoverHandlers.clear()
  })

  watch(htmlRef, () => {
    stale = true
    hoverSec.value = null
  })
  watch(themeRef, () => { pushTheme() })

  return {
    docHtml, frameHeight, hoverSec,
    sandbox: BOARD_SANDBOX,
    onFrameLoad,
    onSeek: (h: (ms: number) => void) => { seekHandlers.add(h); return () => seekHandlers.delete(h) },
    onHover: (h: (sec: BoardHoverSec | null) => void) => { hoverHandlers.add(h); return () => hoverHandlers.delete(h) },
  }
}
