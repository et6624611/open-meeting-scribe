import { createRouter, createWebHistory } from 'vue-router'
import { isEnterprise } from '@/edition'
import { useUserStore } from '@/stores/user'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      // 企业版登录页（档位①）：仅账号密码入口；个人版形态不渲染此路由（守卫不拦截，正常直达首页）
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      // 接受邀请：邀请码自助设置密码（裁决插单③，无初始密码环节）
      path: '/activate',
      name: 'activate',
      component: () => import('@/views/ActivateView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      name: 'start',
      component: () => import('@/views/StartView.vue'),
    },
    {
      path: '/recording/:taskId?',
      name: 'recording',
      component: () => import('@/views/RecordingView.vue'),
    },
    {
      path: '/meeting/:taskId',
      name: 'generating',
      component: () => import('@/views/GeneratingView.vue'),
    },
    // 别名：/meetings/:taskId 重定向到 /meeting/:taskId（用户习惯用复数形式的 URL）
    {
      path: '/meetings/:taskId',
      redirect: (to) => ({ name: 'generating', params: { taskId: to.params.taskId } }),
    },
    {
      path: '/projects',
      name: 'projects',
      component: () => import('@/views/ProjectsView.vue'),
    },
    {
      path: '/speakers',
      name: 'speakers',
      component: () => import('@/views/SpeakersView.vue'),
    },
    {
      path: '/hotwords',
      name: 'hotwords',
      component: () => import('@/views/HotwordsView.vue'),
    },
    {
      path: '/agents',
      name: 'agents',
      component: () => import('@/views/AgentsView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
    },
    {
      path: '/library',
      name: 'library',
      component: () => import('@/views/LibraryView.vue'),
    },
    {
      path: '/decisions',
      name: 'decisions',
      component: () => import('@/views/DecisionCenterView.vue'),
    },
    // 洞察板独立浏览页：“在浏览器中打开”落在这里，而不是直接打开 raw 字节
    // （raw 不跑桥接，mermaid 图不渲染、主题令牌不下发）
    {
      path: '/board/:taskId',
      name: 'board-viewer',
      component: () => import('@/views/BoardViewerView.vue'),
    },
  ],
})

// ─── 档位①路由守卫（仅企业版形态生效，个人版行为零变化） ───
// 未登录访问任何功能 URL → 统一重定向登录页（UI 规格 §1：不弹空白页或报错）
router.beforeEach(async (to) => {
  if (!isEnterprise) return true
  const userStore = useUserStore()
  if (!userStore.checked) await userStore.checkAuth()
  if (to.meta.public) {
    // 已登录用户不再进登录/邀请页
    if (userStore.isLoggedIn && (to.name === 'login' || to.name === 'activate')) return { path: '/' }
    return true
  }
  if (!userStore.isLoggedIn) {
    return { name: 'login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : {} }
  }
  return true
})

export default router
