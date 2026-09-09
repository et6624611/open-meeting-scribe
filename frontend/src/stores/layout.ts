/**
 * 布局状态管理 — 侧边栏/AI面板折叠 + 视图模式
 *
 * 单一数据源：TopBar（视图切换器）、Sidebar（折叠按钮）、
 * AIPanel（折叠按钮）、App.vue（body 类名）共享此 store。
 *
 * 4 种视图模式（与旧版 initViewSwitcher 语义一致）：
 *   full   — 侧边栏 + AI 面板均展开
 *   left   — 侧边栏展开，AI 面板折叠（资源视图）
 *   right  — 侧边栏折叠，AI 面板展开（对话视图）
 *   center — 两栏均折叠，仅保留中心（点击已激活按钮触发）
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type ViewMode = 'full' | 'left' | 'right' | 'center'

const STORAGE_KEY = 'oms_view_mode'

export const useLayoutStore = defineStore('layout', () => {
  const sidebarCollapsed = ref(false)
  const aiCollapsed = ref(false)
  /** 时间轴"全部折叠"状态 */
  const timelineAllCollapsed = ref(false)

  /** 由两个折叠状态派生当前视图模式（供按钮高亮） */
  const viewMode = computed<ViewMode>(() => {
    if (!sidebarCollapsed.value && !aiCollapsed.value) return 'full'
    if (sidebarCollapsed.value && !aiCollapsed.value) return 'right'
    if (!sidebarCollapsed.value && aiCollapsed.value) return 'left'
    return 'center'
  })

  function persist() {
    try { localStorage.setItem(STORAGE_KEY, viewMode.value) } catch { /* */ }
  }

  /**
   * 设置视图模式。
   * 关键语义：点击当前已激活的模式 → 切换到 center（两栏折叠）。
   */
  function setViewMode(mode: ViewMode) {
    if (viewMode.value === mode) {
      // 再次点击已激活按钮 → 仅保留中心视图
      sidebarCollapsed.value = true
      aiCollapsed.value = true
    } else if (mode === 'full') {
      sidebarCollapsed.value = false
      aiCollapsed.value = false
    } else if (mode === 'left') {
      sidebarCollapsed.value = false
      aiCollapsed.value = true
    } else if (mode === 'right') {
      sidebarCollapsed.value = true
      aiCollapsed.value = false
    } else if (mode === 'center') {
      sidebarCollapsed.value = true
      aiCollapsed.value = true
    }
    persist()
  }

  /** 切换侧边栏折叠（边缘按钮/头部按钮） */
  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
    persist()
  }

  /** 切换 AI 面板折叠（边缘按钮） */
  function toggleAi() {
    aiCollapsed.value = !aiCollapsed.value
    persist()
  }

  /** 切换时间轴"全部折叠" */
  function toggleTimelineCollapseAll() {
    timelineAllCollapsed.value = !timelineAllCollapsed.value
  }

  /** 从 localStorage 恢复视图模式 */
  function restore() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY) as ViewMode | null
      if (saved === 'full' || saved === 'left' || saved === 'right' || saved === 'center') {
        if (saved === 'full') { sidebarCollapsed.value = false; aiCollapsed.value = false }
        else if (saved === 'left') { sidebarCollapsed.value = false; aiCollapsed.value = true }
        else if (saved === 'right') { sidebarCollapsed.value = true; aiCollapsed.value = false }
        else { sidebarCollapsed.value = true; aiCollapsed.value = true }
      }
    } catch { /* */ }
  }

  return {
    sidebarCollapsed, aiCollapsed, timelineAllCollapsed, viewMode,
    setViewMode, toggleSidebar, toggleAi, toggleTimelineCollapseAll, restore,
  }
})
