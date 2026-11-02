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
      // D005 初始化向导（产品裁决：首管理员必须产品内完成）：needs_bootstrap 时登录页自动跳转至此
      path: '/setup',
      name: 'setup',
      component: () => import('@/views/SetupView.vue'),
      meta: { public: true },
    },
    {
      // 档⑥管理台（UI 规格 §4）：仅企业形态 + admin 角色；员工端无入口
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/admin/AdminView.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/',
      name: 'start',
      component: () => import('@/views/StartView.vue'),
      meta: { enterpriseRedirect: '/library' },
    },
    {
      path: '/recording/:taskId?',
      name: 'recording',
      component: () => import('@/views/RecordingView.vue'),
      meta: { enterpriseRedirect: '/library' },
    },
    {
      path: '/meeting/:taskId',
      name: 'generating',
      // 企业形态 Web 定稿查看/编辑面（无音频回放，契约 §1.4）；个人版不变
      component: () => import(isEnterprise ? '@/views/ContextDetailView.vue' : '@/views/GeneratingView.vue'),
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
      meta: { enterpriseRedirect: '/library' },
    },
    {
      path: '/speakers',
      name: 'speakers',
      component: () => import(isEnterprise ? '@/views/EnterpriseAssetsView.vue' : '@/views/SpeakersView.vue'),
      props: isEnterprise ? { kind: 'speakers' } : undefined,
    },
    {
      path: '/hotwords',
      name: 'hotwords',
      component: () => import(isEnterprise ? '@/views/EnterpriseAssetsView.vue' : '@/views/HotwordsView.vue'),
      props: isEnterprise ? { kind: 'hotwords' } : undefined,
    },
    {
      path: '/agents',
      name: 'agents',
      component: () => import('@/views/AgentsView.vue'),
      meta: { enterpriseRedirect: '/library' },
    },
    {
      path: '/settings',
      name: 'settings',
      // 企业形态独立设置视图（UI 规格 §2 两分区；账户/算力四段依赖的个人云端点企业实例不挂载）
      component: () => import(isEnterprise ? '@/views/EnterpriseSettingsView.vue' : '@/views/SettingsView.vue'),
    },
    {
      path: '/library',
      name: 'library',
      // 企业形态库=服务端 context tasks 列表（本人 owner）；个人版不变
      component: () => import(isEnterprise ? '@/views/ContextsView.vue' : '@/views/LibraryView.vue'),
    },
    {
      path: '/decisions',
      name: 'decisions',
      component: () => import('@/views/DecisionCenterView.vue'),
      meta: { enterpriseRedirect: '/library' },
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
    if (userStore.isLoggedIn && (to.name === 'login' || to.name === 'activate' || to.name === 'setup')) return { path: '/' }
    return true
  }
  if (!userStore.isLoggedIn) {
    return { name: 'login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : {} }
  }
  // 管理台仅 admin（越权回员工空间；服务端 §1.3 仍有 403 兜底，前端只管界面边界）
  if (to.meta.requiresAdmin && !userStore.isAdmin) return { path: '/' }
  // 企业形态无服务端承接的本地面路由：直达 URL 也重定向（不产生注定 404 请求，3b 裁决）
  if (to.meta.enterpriseRedirect) return { path: to.meta.enterpriseRedirect as string }
  return true
})

export default router
