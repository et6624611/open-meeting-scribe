/**
 * 全局键盘快捷键
 *
 * 旧版快捷键映射：
 *   ESC        → 关闭弹窗/对话框/下拉菜单/退出聚焦模式
 *   /          → 打开 AI 指令面板（非输入框聚焦时）
 *   Cmd/Ctrl+B → 切换侧边栏
 *   Cmd/Ctrl+J → 切换 AI 面板
 *   Cmd/Ctrl+K → 聚焦侧边栏搜索
 *   Cmd/Ctrl+N → 新建会议（跳转录音页）
 */
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useLayoutStore } from '@/stores/layout'

/** 判断当前焦点是否在可编辑元素内 */
function isEditableTarget(el: Element | null): boolean {
  if (!el) return false
  const tag = el.tagName.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true
  if ((el as HTMLElement).isContentEditable) return true
  return false
}

export function useKeyboardShortcuts() {
  const router = useRouter()
  const layout = useLayoutStore()

  function handleKeydown(e: KeyboardEvent) {
    const isMeta = e.metaKey || e.ctrlKey
    const isEscape = e.key === 'Escape'
    const isSlash = e.key === '/' && !isMeta && !e.altKey

    // ─── ESC ───
    if (isEscape) {
      // 1. 关闭登录弹窗
      const loginOverlay = document.getElementById('loginOverlay')
      if (loginOverlay && !loginOverlay.classList.contains('is-hidden')) {
        e.preventDefault()
        loginOverlay.classList.add('is-hidden')
        return
      }

      // 2. 关闭所有可见的下拉菜单
      const openDropdowns = document.querySelectorAll('.is-open, [data-dropdown].is-visible')
      if (openDropdowns.length > 0) {
        openDropdowns.forEach(el => {
          el.classList.remove('is-open', 'is-visible')
        })
        e.preventDefault()
        return
      }

      // 3. 关闭浮动选中工具栏
      const toolbar = document.getElementById('selectionToolbar')
      if (toolbar && toolbar.classList.contains('is-visible')) {
        toolbar.classList.remove('is-visible')
        e.preventDefault()
        return
      }

      // 4. 派发全局 esc 事件（供各组件按需监听）
      window.dispatchEvent(new CustomEvent('global-esc'))
      return
    }

    // ─── / 打开 AI 指令面板 ───
    if (isSlash && !isEditableTarget(document.activeElement)) {
      e.preventDefault()
      if (layout.aiCollapsed) layout.toggleAi()
      // 聚焦 AI 输入框并触发 "/"
      window.dispatchEvent(new CustomEvent('global-ai-focus'))
      return
    }

    // ─── Cmd/Ctrl 组合键 ───
    if (isMeta) {
      switch (e.key.toLowerCase()) {
        // Cmd+B → 切换侧边栏
        case 'b':
          e.preventDefault()
          layout.toggleSidebar()
          return

        // Cmd+J → 切换 AI 面板
        case 'j':
          e.preventDefault()
          layout.toggleAi()
          return

        // Cmd+K → 聚焦侧边栏搜索
        case 'k':
          e.preventDefault()
          if (layout.sidebarCollapsed) layout.toggleSidebar()
          window.dispatchEvent(new CustomEvent('global-sidebar-search'))
          return

        // Cmd+N → 新建会议
        case 'n':
          e.preventDefault()
          router.push('/recording')
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
