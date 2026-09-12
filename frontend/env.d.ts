/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
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
