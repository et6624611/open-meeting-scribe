/**
 * AI 助手全局状态 / AI assistant global state
 *
 * 管理当前激活的 AI 助手（角色），持久化到 settings.json。
 * Manage the currently active AI assistant (role), persisted to settings.json.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchRoles, fetchActiveAgent, setActiveAgent as apiSetActive } from '@/api/agent'
import type { AgentRole } from '@/api/agent'

const DEFAULT_AGENT = 'meeting-minutes'

export const useAgentStore = defineStore('agent', () => {
  const roles = ref<AgentRole[]>([])
  const activeAgent = ref(DEFAULT_AGENT)
  const loaded = ref(false)

  const activeRole = computed(() =>
    roles.value.find(r => r.name === activeAgent.value) ?? null,
  )

  /** 从后端加载角色列表和当前激活助手 / Load roles and active agent from backend */
  async function load() {
    try {
      const [rolesRes, activeRes] = await Promise.all([
        fetchRoles(),
        fetchActiveAgent(),
      ])
      roles.value = rolesRes.roles
      activeAgent.value = activeRes.active_agent || rolesRes.active_agent || DEFAULT_AGENT
      loaded.value = true
    } catch (e) {
      console.error('load agent state failed:', e)
    }
  }

  /** 切换当前激活的助手 / Switch the currently active agent */
  async function setActive(name: string) {
    if (name === activeAgent.value) return
    try {
      await apiSetActive(name)
      activeAgent.value = name
    } catch (e) {
      console.error('set active agent failed:', e)
    }
  }

  return {
    roles,
    activeAgent,
    activeRole,
    loaded,
    load,
    setActive,
  }
})
