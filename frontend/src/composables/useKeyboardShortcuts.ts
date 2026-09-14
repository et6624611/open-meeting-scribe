/**
 * 全局键盘快捷键 / Global keyboard shortcuts
 *
 * 旧版快捷键映射 / Legacy shortcut mapping:
 *   ESC        → 关闭弹窗/对话框/下拉菜单/退出聚焦模式 / Close modal/dialog/dropdown/exit focus mode
 *   Cmd/Ctrl+B → 切换侧边栏 / Toggle sidebar
 *   Cmd/Ctrl+J → 切换 AI 面板 / Toggle AI panel
 *   Cmd/Ctrl+K → 聚焦侧边栏搜索 / Focus sidebar search
 *   Cmd/Ctrl+N → 新建会议（跳转录音页） / New meeting (navigate to recording page)
 *   Cmd/Ctrl+R → 开始页：麦克风录音 / Start page: microphone recording
 *   Cmd/Ctrl+U → 开始页：上传音频文件 / Start page: upload audio file
 */
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useLayoutStore } from '@/stores/layout'

export function useKeyboardShortcuts() {
  const router = useRouter()
  const layout = useLayoutStore()

  function handleKeydown(e: KeyboardEvent) {
    const isMeta = e.metaKey || e.ctrlKey
    const isEscape = e.key === 'Escape'

    // ─── ESC ───
    if (isEscape) {
      // 1. 关闭登录弹窗（派事件由 LoginModal 同步状态，避免直接改 DOM 与 Vue 状态脱钩） / 1. Close login overlay (dispatch event; LoginModal syncs state to avoid DOM/Vue desync)
      const loginOverlay = document.getElementById('loginOverlay')
      if (loginOverlay && !loginOverlay.classList.contains('is-hidden')) {
        e.preventDefault()
        window.dispatchEvent(new CustomEvent('oms:hide-login'))
        return
      }

      // 2. 关闭所有可见的下拉菜单（排除 Vue 响应式管理的 overlay，它们由 useEscClose 自行处理） / 2. Close all visible dropdowns (excluding Vue-managed overlays handled by useEscClose)
      const openDropdowns = document.querySelectorAll('.is-open:not([data-vue-overlay]), [data-dropdown].is-visible')
      if (openDropdowns.length > 0) {
        openDropdowns.forEach(el => {
          el.classList.remove('is-open', 'is-visible')
        })
        e.preventDefault()
        return
      }

      // 3. 关闭浮动选中工具栏 / 3. Close floating selection toolbar
      const toolbar = document.getElementById('selectionToolbar')
      if (toolbar && toolbar.classList.contains('is-visible')) {
        toolbar.classList.remove('is-visible')
        e.preventDefault()
        return
      }

      // 4. 派发全局 esc 事件（供各组件按需监听） / 4. Dispatch global esc event (for components to listen as needed)
      window.dispatchEvent(new CustomEvent('global-esc'))
      return
    }

    // ─── Cmd/Ctrl 组合键（排除含 Shift/Alt 的浏览器原生快捷键） / Cmd/Ctrl combos (excluding browser-native shortcuts with Shift/Alt) ───
    // Cmd+Shift+R = 强制刷新, Cmd+Shift+N = 无痕窗口, Cmd+Shift+B = 书签栏,
    // Cmd+Shift+J = 下载面板, Cmd+Shift+K = 开发者控制台, Cmd+Shift+U = 页面源码 等
    if (isMeta && !e.shiftKey && !e.altKey) {
      switch (e.key.toLowerCase()) {
        // Cmd+B → 切换侧边栏 / Cmd+B: toggle sidebar
        case 'b':
          e.preventDefault()
          layout.toggleSidebar()
          return

        // Cmd+J → 切换 AI 面板 / Cmd+J: toggle AI panel
        case 'j':
          e.preventDefault()
          layout.toggleAi()
          return

        // Cmd+K → 聚焦侧边栏搜索 / Cmd+K: focus sidebar search
        case 'k':
          e.preventDefault()
          if (layout.sidebarCollapsed) layout.toggleSidebar()
          window.dispatchEvent(new CustomEvent('global-sidebar-search'))
          return

        // Cmd+N → 新建会议 / Cmd+N: new meeting
        case 'n':
          e.preventDefault()
          router.push('/recording')
          return

        // Cmd+R → 开始页：麦克风录音 / Cmd+R: start page microphone recording
        case 'r':
          if (router.currentRoute.value.name === 'start') {
            e.preventDefault()
            window.dispatchEvent(new CustomEvent('global-start-record'))
          }
          return

        // Cmd+U → 开始页：上传音频文件 / Cmd+U: start page upload audio file
        case 'u':
          if (router.currentRoute.value.name === 'start') {
            e.preventDefault()
            window.dispatchEvent(new CustomEvent('global-start-upload'))
          }
          return
      }
    }
  }

  onMounted(() => {
    document.addEventListener('keydown', handleKeydown)
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeydown)
  })
}
