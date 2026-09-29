<template>
  <a class="skip-link" href="#mainContent">{{ t('common.skip_to_content') }}</a>
  <div
    class="toast"
    id="globalToast"
    role="status"
    aria-live="polite"
    :class="{ 'is-visible': toastVisible, ['is-' + toastVariant]: toastVariant }"
  >{{ toastMessage }}</div>

  <!-- 遗留的 #selectionToolbar 死模板已移除：无任何脚本控制其可见性，
       且改写/总结/提取决策均已从划词工具栏下架（活跃实现见 SelectionToolbar.vue） -->

  <div class="frame conv-layout" :class="frameClasses">
    <!-- 系统消息横幅；常驻渲染但隐藏时用 display:none 彻底出栈（见 topbar.css
         .reg-guidance-banner.is-hidden）——frame 是 flex 列，仅靠 opacity:0 会让
         隐藏行继续占位，压住左栏最上方的拉手与头部按钮，造成「点了没反应」
         Banner is always rendered but fully out of flow when hidden; an in-flow
         row kept alive by opacity:0 used to swallow clicks on the topmost rail. -->
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
          :class="[statusPipClass, { 'is-open': statusDetailOpen }]"
          role="button"
          tabindex="0"
          :title="t('common.usage.click_detail')"
          :aria-expanded="statusDetailOpen"
          :aria-label="engineStatusLabel"
          @click="toggleStatusDetail"
          @keydown.enter.prevent="toggleStatusDetail"
          @keydown.space.prevent="toggleStatusDetail"
        ><span class="pip"></span> {{ engineStatusLabel }}<span class="status-caret" aria-hidden="true">{{ statusDetailOpen ? '⌄' : '⌃' }}</span></div>
        <div class="usage-indicator" id="usageIndicator" style="display:none" :title="t('common.usage.title')">
          <div class="usage-bar"><div class="usage-bar-fill level-ok" id="usageBarFill" style="width:100%"></div></div>
          <span class="usage-text" id="usageText"></span>
        </div>
      </div>
      <span class="philosophy-text" id="philosophyText"><template v-for="(word, wIdx) in philosophyChars" :key="'w'+wIdx"><span v-for="(ch, cIdx) in word" :key="cIdx" class="philosophy-char" :style="{ animationDelay: `${((wIdx > 0 ? philosophyChars.slice(0, wIdx).reduce((s, w) => s + w.length + 1, 0) : 0) + cIdx) * 0.08}s` }">{{ ch }}</span>{{ wIdx < philosophyChars.length - 1 ? ' ' : '' }}</template></span>
      <div class="right">
        <div class="item" id="statusInfo">{{ t('common.status.ready') }}</div>
      </div>

      <!-- 展开明细：逐能力来源 + 状态 + 配置入口 / Expandable per-capability detail -->
      <div v-show="statusDetailOpen" class="status-detail" role="region" :aria-label="t('common.usage.detail_aria')">
        <div class="sd-row">
          <span class="sd-cap">{{ t('common.usage.status_ai') }}</span>
          <span class="sd-src">{{ llmSourceLabel }}</span>
          <span class="sd-st" :class="llmStatusClass">{{ llmStatusLabel }}</span>
        </div>
        <div class="sd-row">
          <span class="sd-cap">{{ t('common.usage.status_asr') }}</span>
          <span class="sd-src">{{ asrSourceLabel }}</span>
          <span class="sd-st" :class="asrStatusClass">{{ asrStatusLabel }}</span>
        </div>
        <div v-if="quotaLineLabel" class="sd-quota">{{ quotaLineLabel }}</div>
        <button class="sd-config" @click="goToAccessSettings">{{ t('common.usage.go_settings') }}</button>
      </div>
    </footer>
  </div>

  <!-- 登录遮罩层 / Login modal overlay -->
  <LoginModal ref="loginModal" />
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useThemeStore } from '@/stores/theme'
import { useTaskStore } from '@/stores/task'
import { useUserStore } from '@/stores/user'
import { useLayoutStore } from '@/stores/layout'
import { useWatermarkStore } from '@/stores/watermark'
import { useAgentStore } from '@/stores/agent'
import { useEngineStore, type AccessStatusState } from '@/stores/engine'
import { useDivider } from '@/composables/useDivider'
import { useToast, showToast } from '@/composables/useToast'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'
import { useAnnouncements } from '@/composables/useAnnouncements'
import { usePhilosophy } from '@/composables/usePhilosophy'
import { useUpdateCheck } from '@/composables/useUpdateCheck'
import { useCompletionWatch } from '@/composables/useCompletionWatch'
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
const engineStore = useEngineStore()
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

// ─── 底部状态栏：结论 + 原因 + 动作（REQ-SETTINGS-IA §3.1 改版） ───
// 状态推导全部收敛在 stores/engine.ts（单一来源）；模型串与延迟降级到 hover 详情。
const STATUS_LABEL_KEYS: Record<AccessStatusState, string> = {
  local_ready: 'engine_status_local_ready',
  local_pending: 'engine_status_local_pending',
  cloud_ready: 'engine_status_cloud_ready',
  cloud_needs_login: 'engine_status_cloud_login',
  cloud_needs_key: 'engine_status_cloud_key',
  cloud_auto_switched: 'engine_status_cloud_auto_switched',
  unconfigured: 'engine_status_unconfigured',
}

const engineStatusLabel = computed(() => t(`common.usage.${STATUS_LABEL_KEYS[engineStore.statusState]}`))

const statusPipClass = computed(() =>
  engineStore.statusState.endsWith('ready') ? 'is-ok' : 'is-warn')

// ─── 底部状态栏可展开明细（两段式：摘要 + 逐能力来源/状态） ───
const statusDetailOpen = ref(false)
function toggleStatusDetail() { statusDetailOpen.value = !statusDetailOpen.value }

/** 逐能力生效来源：直读 capability.effective（"" = 未设置） */
function capSourceKey(cap: 'llm' | 'asr'): string {
  return engineStore.capability?.[cap]?.effective || ''
}
function srcLabelKey(src: string): string {
  if (src === 'trial') return 'settings.access.src_trial'
  if (src === 'byok') return 'settings.access.src_byok'
  if (src === 'local_endpoint') return 'settings.access.src_local_ep'
  if (src === 'local') return 'settings.access.src_local'
  return ''
}
function sourceLabelOf(cap: 'llm' | 'asr'): string {
  const k = srcLabelKey(capSourceKey(cap))
  return k ? t(k) : '—'
}
const llmSourceLabel = computed(() => sourceLabelOf('llm'))
const asrSourceLabel = computed(() => sourceLabelOf('asr'))

/** 逐能力状态：未设置 / 需登录 / 已改用 / 额度用尽 / 需配 Key / 就绪 */
function capStatus(cap: 'llm' | 'asr'): { text: string; cls: string } {
  const src = capSourceKey(cap)
  const r = engineStore.routing?.[cap]
  if (!src || r?.unconfigured) return { text: t('common.usage.st_not_set'), cls: 'is-muted' }
  if (src === 'trial' && !userStore.isLoggedIn) return { text: t('common.usage.st_need_login'), cls: 'is-warn' }
  if (r?.auto_switched) {
    const to = srcLabelKey(String(r.source || ''))
    return { text: t('common.usage.st_switched', { to: to ? t(to) : '—' }), cls: 'is-warn' }
  }
  if (src === 'trial' && engineStore.quotaRemaining != null && engineStore.quotaRemaining <= 0) return { text: t('common.usage.st_exhausted'), cls: 'is-warn' }
  if (src === 'byok' && String(r?.reason || '').includes('missing')) return { text: t('common.usage.st_need_key'), cls: 'is-warn' }
  return { text: t('common.usage.st_ready'), cls: 'is-ok' }
}
const llmStatus = computed(() => capStatus('llm'))
const asrStatus = computed(() => capStatus('asr'))
const llmStatusLabel = computed(() => llmStatus.value.text)
const llmStatusClass = computed(() => llmStatus.value.cls)
const asrStatusLabel = computed(() => asrStatus.value.text)
const asrStatusClass = computed(() => asrStatus.value.cls)

const quotaLineLabel = computed(() => {
  const q = engineStore.quotaRemaining
  if (!userStore.isLoggedIn || q == null || q < 0) return ''
  return t('common.usage.quota_left', { n: fmtQuotaMinutes(q) })
})

function fmtQuotaMinutes(min: number | null): string {
  if (min == null) return '—'
  if (min >= 60) {
    const h = Math.floor(min / 60)
    const m = Math.round(min % 60)
    return m > 0 ? `${h}h${m}m` : `${h}h`
  }
  return `${Math.round(min)}m`
}

/** A3：底部状态栏为接入状态唯一入口，点击跳接入方式设置（顶栏徽章已下架） */
function goToAccessSettings() {
  router.push({ name: 'settings', query: { cat: 'access' } })
}

// ─── 兜底告知（REQ-SETTINGS-IA §3.5 第 5 刀）：主路径已升为设置页 L1/L2/L3 常驻提示，
// 此处仅在自动改用发生时于任意页面作一次性事后告知（每会话每原因仅一次）；
// 静默 route_override 语义已消灭，文案用「自动改用」，禁用「降级」。事件源 = routing.auto_switched。
watch(() => engineStore.routeOverride, (reason) => {
  if (!reason) return
  const key = `oms.autoSwitchToast.${reason}`
  try {
    if (sessionStorage.getItem(key)) return
    sessionStorage.setItem(key, '1')
  } catch { /* 存储不可用时仍提示，仅失去判重 */ }
  showToast(t(`common.usage.auto_switch_${reason}`, { n: fmtQuotaMinutes(engineStore.quotaRemaining) }), 'warn')
})

// ─── 登录态联动（BUG-LOGOUT-QUOTA）：登录/登出后刷新 routing 快照 ───
// 底部状态栏与 ASR/AI 配置卡的配额信息全部单源自 engineStore.routing；
// 原实现只在启动链拉取一次，登出（或登录）后无人负责重拉，导致配额信息残留旧值。
watch(() => userStore.isLoggedIn, () => {
  void engineStore.loadRouting(true)
  void engineStore.loadAccessSettings()
})

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

// 后台任务完成侦测：站内角标/toast + 系统通知（有则发）——REQ-TRANSCRIBE-PROGRESS R2
useCompletionWatch()

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
  // ─── 状态栏/接入方式单一来源启动链（AM-F1 T5）：引擎态 + 路由推导 + hover 详情 ───
  engineStore.load()
  void engineStore.loadRouting()
  void engineStore.loadAccessSettings().then(() => {
    // 启动时版本检查（受 update_check 开关控制，原 loadStatusModels 职责并入）
    const ff = engineStore.accessSettings?.feature_flags
    updateStartupCheck(ff?.update_check !== false)
  })
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
/* 底部状态栏接入结论态（T5）：就绪=ok / 待办=warn */
.status-engine { cursor: pointer; user-select: none; }
.status-engine:hover { text-decoration: underline; }
.status-engine:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
.status-engine.is-ok .pip { background: var(--ok); }
.status-engine.is-warn .pip { background: var(--warn); }
</style>
