import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
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

export default router
