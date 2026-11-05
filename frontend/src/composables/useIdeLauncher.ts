import { ref, computed } from 'vue'
import { useWorkspace } from '@/composables/useWorkspace'
import { getDockBounds, positionDropdown } from '@/utils/popoverPosition'
import type { WorkspaceScope } from '@/api/workspace'

export function useIdeLauncher(
  taskId: string,
  getGenIdeBtn: () => HTMLElement | null,
  getGenIdeMenu: () => HTMLElement | null,
) {
  const ws = useWorkspace()

  const genIdeBtn = computed(getGenIdeBtn)
  const genIdeMenu = computed(getGenIdeMenu)
  const ideMenuOpen = ref(false)
  const ideScope = ref<WorkspaceScope>('meeting')
  const ideScopes: Array<{ id: WorkspaceScope; label: string }> = [
    { id: 'meeting', label: 'ai-panel.context.workspace_ide_scope_meeting' },
    { id: 'project', label: 'ai-panel.context.workspace_ide_scope_project' },
    { id: 'all', label: 'ai-panel.context.workspace_ide_scope_all' },
  ]

  async function repositionIdeMenu() {
    if (!genIdeMenu.value || !genIdeBtn.value) return
    const tr = genIdeBtn.value.getBoundingClientRect()
    const { x, y } = positionDropdown(
      { top: tr.top, left: tr.left, width: tr.width, height: tr.height },
      genIdeMenu.value.offsetWidth, genIdeMenu.value.offsetHeight, getDockBounds(),
      { align: 'end' },
    )
    genIdeMenu.value.style.left = `${x}px`
    genIdeMenu.value.style.top = `${y}px`
  }

  async function toggleIdeMenu() {
    ideMenuOpen.value = !ideMenuOpen.value
    if (ideMenuOpen.value) {
      await ws.loadIdes()
      await repositionIdeMenu()
    }
  }

  async function onContinueInIde(ideId: string) {
    const ok = await ws.openIde(taskId, ideId, ideScope.value)
    if (ok) ideMenuOpen.value = false
  }

  function onIdeDocMouseDown(e: MouseEvent) {
    if (!ideMenuOpen.value) return
    const target = e.target as Node
    if (genIdeMenu.value?.contains(target) || genIdeBtn.value?.contains(target)) return
    ideMenuOpen.value = false
  }

  function onIdeResize() {
    if (ideMenuOpen.value) void repositionIdeMenu()
  }

  return {
    ws, genIdeBtn, genIdeMenu, ideMenuOpen, ideScope, ideScopes,
    toggleIdeMenu, onContinueInIde, onIdeDocMouseDown, onIdeResize,
    loadIdes: () => ws.loadIdes(),
  }
}
