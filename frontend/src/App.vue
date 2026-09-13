<template>
  <a class="skip-link" href="#mainContent">{{ t('common.skip_to_content') }}</a>
  <div
    class="toast"
    id="globalToast"
    role="status"
    aria-live="polite"
    :class="{ 'is-visible': toastVisible, ['is-' + toastVariant]: toastVariant }"
  >{{ toastMessage }}</div>

  <!-- 浮动选中操作条 -->
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
    <!-- 系统消息横幅（参与 grid 布局，不溢出视口）；常驻渲染以保持 frame 网格行数与子元素数一致 -->
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

    <!-- 水印氛围层 -->
    <div class="wm-layer" id="wmLayer" :class="{ 'is-hidden': !watermark.enabled }" :style="watermark.enabled ? { '--wm-opacity': watermark.opacity } : undefined">
      <div class="wm-glow wm-glow-1"></div>
      <div class="wm-glow wm-glow-2"></div>
      <div class="wm-glow wm-glow-3"></div>
    </div>

    <!-- 顶栏 -->
    <TopBar />

    <!-- 三栏主体 -->
    <div class="body" :class="bodyClasses">
      <!-- 常驻导航轨 -->
      <ActivityRail />

      <!-- 侧边栏 -->
      <Sidebar />

      <!-- 左侧分隔缝（纯视觉） -->
      <div class="layout-divider layout-divider-left">
        <div class="divider-line"></div>
      </div>

      <!-- 主内容区 -->
      <main class="main" id="mainContent" tabindex="-1" ref="mainEl" :class="mainWidthClass" :data-tier="mainTier">
        <router-view :key="$route.fullPath" />
      </main>

      <!-- 右侧分隔缝（纯视觉） -->
      <div class="layout-divider layout-divider-right">
        <div class="divider-line"></div>
      </div>

      <!-- AI 面板 -->
      <AIPanel />
    </div>

    <!-- 底部状态栏 -->
    <footer class="status">
      <div class="left">
        <div class="item"><span class="pip"></span> {{ t('common.usage.cloud_connected') }}</div>
        <div class="item status-models">paraformer-v2 + qwen-plus</div>
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

  <!-- 登录遮罩层 -->
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
import { useDivider } from '@/composables/useDivider'
import { useToast } from '@/composables/useToast'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'
import { useAnnouncements } from '@/composables/useAnnouncements'
import { escapeHtml } from '@/utils/sanitize'
import { useContainerSize } from '@/composables/useContainerSize'
import { getRecordStatus } from '@/api/record'
import { getLocale } from '@/i18n'
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
const { toastMessage, toastVariant, toastVisible } = useToast()
const loginModal = ref<InstanceType<typeof LoginModal> | null>(null)
const mainEl = ref<HTMLElement | null>(null)
const { widthClass: mainWidthClass, tier: mainTier } = useContainerSize(mainEl)
const philosophyVariants = ref<Record<string, string>>({})
const philosophyText = computed(() => {
  const lang = getLocale().startsWith('zh') ? 'zh' : 'en'
  return philosophyVariants.value[lang] || philosophyVariants.value.zh || ''
})
const philosophyChars = computed(() => philosophyText.value.split('').map(ch => ch === ' ' ? '\u00A0' : ch))
const perfMetrics = ref<{ apiLatency: number | null }>({ apiLatency: null })

// 公告横幅
const { visible: annVisible, currentMessage: annMessage, load: loadAnnouncements, dismiss: annDismiss, getCtaUrl: annCtaUrl } = useAnnouncements()
const safeAnnContent = computed(() => annMessage.value ? escapeHtml(annMessage.value.content) : '')

function onCtaClick() {
  const url = annCtaUrl()
  if (url) window.location.href = url
}

// 分隔条拖拽
useDivider()

// 全局键盘快捷键
useKeyboardShortcuts()

const frameClasses = computed(() => ({
  'is-start-mode': themeStore.isStartMode,
}))

// body 类名：驱动侧边栏/AI 面板折叠（与 legacy CSS 类名对齐）
const bodyClasses = computed(() => ({
  'view-full': layout.viewMode === 'full',
  'view-center-only': layout.viewMode === 'center',
  'sidebar-collapsed': layout.sidebarCollapsed,
  'ai-collapsed': layout.aiCollapsed,
}))

onMounted(async () => {
  layout.restore()
  await userStore.checkAuth()
  // [状态同步] 应用启动时加载任务列表（含活跃录音恢复）
  await taskStore.loadTasks()
  // 检查后端是否有进行中的录音，若有则自动导航到录音页（防止刷新后丢失录音上下文）
  checkActiveRecording()
  loadAnnouncements()
  loadPhilosophy()

  // ─── 主内容区宽度档位（统一 composable 驱动）───
  // 断点与 CSS 类名由 useContainerSize 统一管理，触发 legacy-views.css 等响应式规则

  // ─── 页面刷新保护（桌面端数据保护）───
  // 录音中刷新/关闭页面时弹出浏览器原生确认对话框，防止误操作丢失录音数据
  window.addEventListener('beforeunload', onBeforeUnload)
  // 桌面端 F5 刷新请求（由 pywebview 注入层派发）
  window.addEventListener('oms:reload-requested', onReloadRequested)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('oms:reload-requested', onReloadRequested)
})

/** 检测当前是否有录音中的任务（含暂停） */
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

/** beforeunload：录音中阻止意外关闭/刷新 */
function onBeforeUnload(e: BeforeUnloadEvent) {
  if (isRecordingActive()) {
    e.preventDefault()
  }
}

/** 桌面端 F5 刷新请求：录音中弹确认，否则直接刷新 */
function onReloadRequested() {
  if (isRecordingActive()) {
    if (!window.confirm(t('common.reload_recording_confirm'))) return
  }
  window.location.reload()
}

/** 检查后端是否有进行中的录音，自动恢复到录音页 */
async function checkActiveRecording() {
  try {
    const status = await getRecordStatus()
    if (status.recording && status.task_id) {
      // 当前不在录音页时，自动导航过去
      const currentRoute = router.currentRoute.value
      if (currentRoute.name !== 'recording' || currentRoute.params.taskId !== status.task_id) {
        taskStore.selectTask(status.task_id)
        router.push({ name: 'recording', params: { taskId: status.task_id } })
      }
    }
  } catch {
    // 静默失败，不影响正常使用
  }
}

async function loadPhilosophy() {
  const CACHE_KEY = 'philosophy_cache'
  const WEEK_MS = 7 * 24 * 60 * 60 * 1000
  try {
    const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || '{}')
    const now = Date.now()
    let variants = cached.variants as Record<string, string> | undefined
    // 校验缓存格式：值必须为字符串（旧版本可能写入嵌套对象）
    if (variants && typeof variants === 'object') {
      const hasStringValue = Object.values(variants).some(v => typeof v === 'string')
      if (!hasStringValue) variants = undefined
    }
    if (!variants || !cached.ts || now - cached.ts > WEEK_MS) {
      const res = await fetch('/api/philosophy/random')
      if (!res.ok) return
      const data = await res.json()
      variants = data.variants
        || (typeof data.text === 'object' && data.text !== null ? data.text : { zh: String(data.text || '') })
      localStorage.setItem(CACHE_KEY, JSON.stringify({ variants, ts: now }))
    }
    philosophyVariants.value = variants || {}
    const text = philosophyText.value
    if (!text) return
    setTimeout(() => {
      const el = document.getElementById('philosophyText')
      if (el) el.classList.add('is-visible')
    }, 500)
    // 逐字显现完成后启动微光扫过效果
    setTimeout(() => {
      const el = document.getElementById('philosophyText')
      if (el) el.classList.add('is-shimmer')
    }, 500 + text.length * 80 + 800)
  } catch { /* 静默 */ }
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
