/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

// ─── pywebview 桌面端桥接类型 / pywebview desktop bridge types ───
// pywebview 通过 window.expose() 将 Python 函数挂载到 window.pywebview.api，
// 前端据此判断是否运行在桌面客户端并调用原生能力（如原生文件夹选择器）。
// pywebview mounts Python functions onto window.pywebview.api via window.expose(),
// frontend uses this to detect desktop mode and invoke native capabilities.
interface PywebviewApi {
  /** 弹出 OS 原生文件夹选择对话框，返回选中路径（空串表示取消）
   * Open OS native folder picker, returns selected path (empty string if cancelled) */
  select_native_folder: () => Promise<string>
}

interface Window {
  pywebview?: {
    api?: PywebviewApi
  }
}

declare module 'vue-virtual-scroller' {
  import type { DefineComponent } from 'vue'
  export const DynamicScroller: DefineComponent<{
    items: any[]
    minItemSize: number | string
    keyField: string
    buffer?: number
  } & Record<string, any>, {}, {
    scrollToItem: (index: number) => void
    scrollToItemAtIndex: (index: number) => void
    $el: HTMLElement
  }>
  export const DynamicScrollerItem: DefineComponent<{
    item: any
    activeSizeDependencies?: any[]
    watchData?: boolean
    tag?: string
  }>
  export const RecycleScroller: DefineComponent<any>
}
