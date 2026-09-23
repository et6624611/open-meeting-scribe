<template>
  <a class="skip-link" href="#mainContent">{{ t('common.skip_to_content') }}</a>
  <div
    class="toast"
    id="globalToast"
    role="status"
    aria-live="polite"
    :class="{ 'is-visible': toastVisible, ['is-' + toastVariant]: toastVariant }"
  >{{ toastMessage }}</div>

  <!-- 浮动选中操作条 / Floating selection toolbar -->
  <div class="selection-toolbar" id="selectionToolbar">
    <button class="sel-tool-btn is-primary" data-action="quote-to-ai" :title="t('common.selection_toolbar.quote_title')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
      {{ t('common.selection_toolbar.quote_to_ai') }}
    </button>
    <span class="sel-tool-sep"></span>
    <button class="sel-tool-btn" data-action="rewrite" :title="t('common.selection_toolbar.rewrite_title')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
      {{ t('common.selection_toolbar.rewrite') }}
    </button>
    <button class="sel-tool-btn" data-action="summarize" :title="t('common.selection_toolbar.summarize_title')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/></svg>
      {{ t('common.selection_toolbar.summarize') }}
    </button>
    <button class="sel-tool-btn" data-action="extract-todo" :title="t('common.selection_toolbar.extract_todo_title')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9,11 12,14 22,4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
      {{ t('common.selection_toolbar.extract_todo') }}
    </button>
  </div>

  <div class="frame conv-layout" :class="frameClasses">
    <!-- 系统消息横幅（参与 grid 布局，不溢出视口）；常驻渲染以保持 frame 网格行数与子元素数一致 / System message banner (participates in grid layout, doesn't overflow viewport); always rendered to keep frame grid row count consistent -->
    <div class="reg-guidance-banner" :class="{ 'is-hidden': !annVisible || !annMessage }">
      <div class="reg-guidance-content" v-if="annMessage">
        <svg class="reg-guidance-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2L2 7l10 5 10-5-10-5z"/>
          <path d="M2 17l10 5 10-5"/>
          <path d="M2 12l10 5 10-5"/>
        </svg>
        <span class="reg-guidance-text" v-html="safeAnnContent"></span>
        <button v-if="annMessage.cta_text && annCtaUrl()" class="reg-guidance-cta" @click="onCtaClick">{{ annMessage.cta_text }}</button>
        <button class="reg-guidance-dismiss" @click="annDismiss" :title="t('common.announcement.dismiss')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- 版本更新提示横幅 / Version update notification banner -->
    <div class="reg-guidance-banner update-banner" :class="{ 'is-hidden': !showUpdateBanner }">
      <div class="reg-guidance-content update-content" v-if="showUpdateBanner">
        <svg class="reg-guidance-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <span class="reg-guidance-text">
          {{ t('common.update_available', { version: updateLatestVersion }) }}
        </span>
        <a v-if="updateDownloadUrl" class="reg-guidance-cta" :href="updateDownloadUrl" target="_blank" rel="noopener">{{ t('common.view_update') }}</a>
        <button class="reg-guidance-dismiss" @click="onDismissUpdate" :title="t('common.announcement.dismiss')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- 水印氛围层 / Watermark atmosphere layer -->
    <div class="wm-layer" id="wmLayer" :class="{ 'is-hidden': !watermark.enabled }" :style="watermark.enabled ? { '--wm-opacity': watermark.opacity } : undefined">
      <div class="wm-glow wm-glow-1"></div>
      <div class="wm-glow wm-glow-2"></div>
      <div class="wm-glow wm-glow-3"></div>
    </div>

    <!-- 顶栏 / Top bar -->
    <TopBar />

    <!-- 三栏主体 / Three-column layout -->
    <div class="body" :class="bodyClasses">
      <!-- 常驻导航轨 / Persistent activity rail -->
      <ActivityRail />

      <!-- 侧边栏 / Sidebar -->
      <Sidebar />

      <!-- 左侧分隔缝（纯视觉） / Left divider gap (visual only) -->
      <div class="layout-divider layout-divider-left">
        <div class="divider-line"></div>
      </div>

      <!-- 主内容区 / Main content area -->
      <main class="main" id="mainContent" tabindex="-1" ref="mainEl" :class="mainWidthClass" :data-tier="mainTier">
        <router-view :key="$route.fullPath" />
      </main>

      <!-- 右侧分隔缝（纯视觉） / Right divider gap (visual only) -->
      <div class="layout-divider layout-divider-right">
        <div class="divider-line"></div>
      </div>

      <!-- AI 面板 / AI panel -->
      <AIPanel />
    </div>

    <!-- 底部状态栏 / Bottom status bar -->
    <footer class="status">
      <div class="left">
        <div
          class="item status-engine"
          :class="`is-${statusEngine}`"
          role="button"
          tabindex="0"
          :title="t('common.usage.engine_hint')"
          @click="goToEngineSettings"
          @keydown.enter="goToEngineSettings"
          @keydown.space.prevent="goToEngineSettings"
        ><span class="pip"></span> {{ engineStatusLabel }}</div>
        <div class="item status-models">{{ statusModels }}</div>
        <div v-if="perfMetrics.apiLatency !== null" class="item perf-indicator">API: {{ perfMetrics.apiLatency }}ms</div>
        <div class="usage-indicator" id="usageIndicator" style="display:none" :title="t('common.usage.title')">
          <div class="usage-bar"><div class="usage-bar-fill level-ok" id="usageBarFill" style="width:100%"></div></div>
          <span class="usage-text" id="usageText"></span>
        </div>
      </div>
      <span class="philosophy-text" id="philosophyText"><span v-for="(ch, i) in philosophyChars" :key="i" class="philosophy-char" :style="{ animationDelay: `${i * 0.08}s` }">{{ ch }}</span></span>
      <div class="right">
        <div class="item" id="statusInfo">{{ t('common.status.ready') }}</div>
      </div>
    </footer>
  </div>

  <!-- 登录遮罩层 / Login modal overlay -->
  <LoginModal ref="loginModal" />
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useThemeStore } from '@/stores/theme'
import { useTaskStore } from '@/stores/task'
import { useUserStore } from '@/stores/user'
import { useLayoutStore } from '@/stores/layout'
import { useWatermarkStore } from '@/stores/watermark'
import { useAgentStore } from '@/stores/agent'
import { useDivider } from '@/composables/useDivider'
import { useToast } from '@/composables/useToast'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'
import { useAnnouncements } from '@/composables/useAnnouncements'
import { usePhilosophy } from '@/composables/usePhilosophy'
import { useUpdateCheck } from '@/composables/useUpdateCheck'
import { escapeHtml } from '@/utils/sanitize'
import { useContainerSize } from '@/composables/useContainerSize'
import { getRecordStatus } from '@/api/record'
import TopBar from '@/components/layout/TopBar.vue'
import Sidebar from '@/components/layout/Sidebar.vue'
import ActivityRail from '@/components/layout/ActivityRail.vue'
import AIPanel from '@/components/layout/AIPanel.vue'
import LoginModal from '@/components/modals/LoginModal.vue'

const router = useRouter()
const { t } = useI18n()
const themeStore = useThemeStore()
const taskStore = useTaskStore()
const userStore = useUserStore()
const layout = useLayoutStore()
const watermark = useWatermarkStore()
const agentStore = useAgentStore()
const { toastMessage, toastVariant, toastVisible } = useToast()
const loginModal = ref<InstanceType<typeof LoginModal> | null>(null)
const mainEl = ref<HTMLElement | null>(null)
const { widthClass: mainWidthClass, tier: mainTier } = useContainerSize(mainEl)
const { philosophyChars, loadPhilosophy, updatePhilosophy } = usePhilosophy()
// 暴露给子视图：Tab 切换时调用 window.__omsUpdatePhilosophy(tab) / Expose to child views: call window.__omsUpdatePhilosophy(tab) on tab switch
if (typeof window !== 'undefined') {
  (window as any).__omsUpdatePhilosophy = (tab?: string) => {
    const route = router.currentRoute.value
    updatePhilosophy(route.name as string | undefined, tab)
  }
}
const perfMetrics = ref<{ apiLatency: number | null }>({ apiLatency: null })
const statusModels = ref('paraformer-v2 + qwen-plus')  // 默认值，加载设置后更新

// ─── 底部状态栏路由三态（BACKLOG v1.6.0 / R4） / Status-bar routing tri-state ───
// local: 本机端点（Ollama/LM Studio）；cloud: 远端服务；unconfigured: 未配置
type EngineRoute = 'local' | 'cloud' | 'unconfigured'
const statusEngine = ref<EngineRoute>('unconfigured')

const engineStatusLabel = computed(() => {
  switch (statusEngine.value) {
    case 'local': return t('common.usage.engine_local')
    case 'cloud': return t('common.usage.engine_cloud')
    default: return t('common.usage.engine_unconfigured')
  }
})

/** 本机地址判定（与后端 is_localhost_base_url 对齐） / Localhost check (mirrors backend) */
function isLocalhostUrl(url?: string): boolean {
  if (!url) return false
  return /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/i.test(url)
}

/** 点击状态栏跳转到 设置 → 计算引擎（服务分类） / Click navigates to Settings → compute engine (services tab) */
function goToEngineSettings() {
  router.push({ name: 'settings', query: { tab: 'services' } })
}

// 加载设置以获取实际模型名与功能开关 / Load settings to get actual model names and feature flags
async function loadStatusModels() {
  try {
    const client = (await import('@/api/client')).default
    const { data } = await client.get('/api/settings')
    const asrModel = data?.asr?.model || 'paraformer-v2'
    const llmModel = data?.llm?.model || 'qwen-plus'
    statusModels.value = `${asrModel} + ${llmModel}`
    // 三态路由判定：数据源为 llm 配置 + 登录态，不新增业务接口 / Tri-state from llm config + login state; no new endpoint
    const llm = data?.llm || {}
    const baseUrl = llm.base_url || ''
    if (isLocalhostUrl(baseUrl)) {
      statusEngine.value = 'local'
    } else if (baseUrl && (llm.api_key_set || userStore.isLoggedIn)) {
      statusEngine.value = 'cloud'
    } else {
      statusEngine.value = 'unconfigured'
    }
    // 启动时版本检查（受 update_check 开关控制） / Startup version check (controlled by update_check flag)
    const updateCheckEnabled = data?.feature_flags?.update_check !== false
    updateStartupCheck(updateCheckEnabled)
  } catch {
    // 静默失败，使用默认值 / Silent failure, use defaults
  }
}

// 公告横幅 / Announcement banner
const { visible: annVisible, currentMessage: annMessage, load: loadAnnouncements, dismiss: annDismiss, getCtaUrl: annCtaUrl } = useAnnouncements()
const safeAnnContent = computed(() => annMessage.value ? escapeHtml(annMessage.value.content) : '')

// 版本更新检查 / Version update check
const { hasUpdate: updateHasUpdate, latestVersion: updateLatestVersion, downloadUrl: updateDownloadUrl, dismissed: updateDismissed, startupCheck: updateStartupCheck, dismiss: updateDismiss } = useUpdateCheck()
const showUpdateBanner = computed(() => updateHasUpdate.value && !updateDismissed.value)

function onDismissUpdate() {
  updateDismiss()
}

function onCtaClick() {
  const url = annCtaUrl()
  if (url) window.location.href = url
}

// 分隔条拖拽 / Divider drag resize
useDivider()

// 全局键盘快捷键 / Global keyboard shortcuts
useKeyboardShortcuts()

const frameClasses = computed(() => ({
  'is-start-mode': themeStore.isStartMode,
}))

// body 类名：驱动侧边栏/AI 面板折叠（与 legacy CSS 类名对齐） / Body classes: drive sidebar/AI panel collapse (aligned with legacy CSS class names)
const bodyClasses = computed(() => ({
  'view-full': layout.viewMode === 'full',
  'view-center-only': layout.viewMode === 'center',
  'sidebar-collapsed': layout.sidebarCollapsed,
  'ai-collapsed': layout.aiCollapsed,
}))

onMounted(async () => {
  layout.restore()
  await userStore.checkAuth()
  // [状态同步] 应用启动时加载任务列表（含活跃录音恢复） / [State Sync] Load task list on app startup (incl. active recording recovery)
  await taskStore.loadTasks()
  // 检查后端是否有进行中的录音，若有则自动导航到录音页（防止刷新后丢失录音上下文） / Check backend for active recording; auto-navigate to recording page (prevent losing recording context after refresh)
  checkActiveRecording()
  loadAnnouncements()
  loadPhilosophy()
  loadStatusModels()  // 加载状态栏模型名
  agentStore.load()  // 加载全局 AI 助手状态

  // ─── 路由变化时刷新理念 / Refresh philosophy on route change ───
  router.afterEach((to) => {
    updatePhilosophy(to.name as string | undefined)
  })

  // ─── 主内容区宽度档位（统一 composable 驱动） ─── / ─── Main content width tier (unified composable-driven) ───
  // 断点与 CSS 类名由 useContainerSize 统一管理，触发 legacy-views.css 等响应式规则 / Breakpoints and CSS classes managed by useContainerSize; triggers legacy-views.css responsive rules

  // ─── 页面刷新保护（桌面端数据保护）─── / ─── Page refresh protection (desktop data protection) ───
  // 录音中刷新/关闭页面时弹出浏览器原生确认对话框，防止误操作丢失录音数据 / Show native browser confirm dialog on refresh/close during recording to prevent accidental data loss
  window.addEventListener('beforeunload', onBeforeUnload)
  // 桌面端 F5 刷新请求（由 pywebview 注入层派发） / Desktop F5 refresh request (dispatched by pywebview injection layer)
  window.addEventListener('oms:reload-requested', onReloadRequested)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('oms:reload-requested', onReloadRequested)
})

/** 检测当前是否有录音中的任务（含暂停） / Check if any recording task is active (incl. paused) */
function isRecordingActive(): boolean {
  const now = Date.now()
  const oneDayAgo = now - 24 * 60 * 60 * 1000
  return taskStore.tasks.some(t => {
    if (t.status !== 'recording' && t.status !== 'paused') return false
    if (t.created_at) {
      const created = new Date(t.created_at).getTime()
      if (created < oneDayAgo) return false
    }
    return true
  })
}

/** beforeunload：录音中阻止意外关闭/刷新 / beforeunload: prevent accidental close/refresh during recording */
function onBeforeUnload(e: BeforeUnloadEvent) {
  if (isRecordingActive()) {
    e.preventDefault()
  }
}

/** 桌面端 F5 刷新请求：录音中弹确认，否则直接刷新 / Desktop F5 refresh: confirm during recording, otherwise reload directly */
function onReloadRequested() {
  if (isRecordingActive()) {
    if (!window.confirm(t('common.reload_recording_confirm'))) return
  }
  window.location.reload()
}

/** 检查后端是否有进行中的录音，自动恢复到录音页 / Check backend for active recording; auto-restore to recording page */
async function checkActiveRecording() {
  try {
    const status = await getRecordStatus()
    if (status.recording && status.task_id) {
      // 当前不在录音页时，自动导航过去 / Auto-navigate to recording page if not already there
      const currentRoute = router.currentRoute.value
      if (currentRoute.name !== 'recording' || currentRoute.params.taskId !== status.task_id) {
        taskStore.selectTask(status.task_id)
        router.push({ name: 'recording', params: { taskId: status.task_id } })
      }
    }
  } catch {
    // 静默失败，不影响正常使用 / Silent failure; doesn't affect normal usage
  }
}



// Performance monitoring
onMounted(() => {
  // Track fetch timing using Performance API
  const observer = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      if (entry.entryType === 'resource' && (entry as PerformanceResourceTiming).initiatorType === 'fetch') {
        const latency = Math.round(entry.duration)
        perfMetrics.value.apiLatency = latency
        // Keep only last value; could be extended to show average
      }
    }
  })
  
  try {
    observer.observe({ entryTypes: ['resource'] })
  } catch {
    // Fallback: Performance API not supported
  }
})


</script>

<style scoped>
/* 底部状态栏「计算引擎」三态 / Status-bar compute-engine tri-state */
.status-engine { cursor: pointer; user-select: none; }
.status-engine:hover { text-decoration: underline; }
.status-engine:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
.status-engine.is-local .pip { background: var(--ok); }
.status-engine.is-cloud .pip { background: var(--accent); }
.status-engine.is-unconfigured .pip { background: var(--warn); }
</style>
