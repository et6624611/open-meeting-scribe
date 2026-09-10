<template>
  <a class="skip-link" href="#mainContent">跳到主要内容</a>
  <div
    class="toast"
    id="globalToast"
    role="status"
    aria-live="polite"
    :class="{ 'is-visible': toastVisible, ['is-' + toastVariant]: toastVariant }"
  >{{ toastMessage }}</div>

  <!-- 浮动选中操作条 -->
  <div class="selection-toolbar" id="selectionToolbar">
    <button class="sel-tool-btn is-primary" data-action="quote-to-ai" title="引用到会议助手">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
      引用到 AI
    </button>
    <span class="sel-tool-sep"></span>
    <button class="sel-tool-btn" data-action="rewrite" title="AI 改写">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
      改写
    </button>
    <button class="sel-tool-btn" data-action="summarize" title="AI 总结">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/></svg>
      总结
    </button>
    <button class="sel-tool-btn" data-action="extract-todo" title="提取待办">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9,11 12,14 22,4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
      提取待办
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
        <span class="reg-guidance-text" v-html="annMessage.content"></span>
        <button v-if="annMessage.cta_text && annCtaUrl()" class="reg-guidance-cta" @click="onCtaClick">{{ annMessage.cta_text }}</button>
        <button class="reg-guidance-dismiss" @click="annDismiss" title="关闭提示">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- 水印氛围层 -->
    <div class="wm-layer" id="wmLayer">
      <div class="wm-glow wm-glow-1"></div>
      <div class="wm-glow wm-glow-2"></div>
      <div class="wm-glow wm-glow-3"></div>
    </div>

    <!-- 顶栏 -->
    <TopBar />

    <!-- 三栏主体 -->
    <div class="body" :class="bodyClasses">
      <!-- 侧边栏 -->
      <Sidebar />

      <!-- 左侧分隔缝（纯视觉） -->
      <div class="layout-divider layout-divider-left">
        <div class="divider-line"></div>
      </div>

      <!-- 主内容区 -->
      <main class="main" id="mainContent" tabindex="-1">
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
        <div class="item"><span class="pip"></span> DashScope 已连接</div>
        <div class="item status-models">paraformer-v2 + qwen-plus</div>
        <div v-if="perfMetrics.apiLatency !== null" class="item perf-indicator">API: {{ perfMetrics.apiLatency }}ms</div>
        <div class="usage-indicator" id="usageIndicator" style="display:none" title="本月识别额度">
          <div class="usage-bar"><div class="usage-bar-fill level-ok" id="usageBarFill" style="width:100%"></div></div>
          <span class="usage-text" id="usageText"></span>
        </div>
      </div>
      <span class="philosophy-text" id="philosophyText">{{ philosophyText }}</span>
      <div class="right">
        <div class="item" id="statusInfo">就绪</div>
      </div>
    </footer>
  </div>

  <!-- 登录遮罩层 -->
  <LoginModal ref="loginModal" />
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { useTaskStore } from '@/stores/task'
import { useUserStore } from '@/stores/user'
import { useLayoutStore } from '@/stores/layout'
import { useDivider } from '@/composables/useDivider'
import { useToast } from '@/composables/useToast'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'
import { useAnnouncements } from '@/composables/useAnnouncements'
import TopBar from '@/components/layout/TopBar.vue'
import Sidebar from '@/components/layout/Sidebar.vue'
import AIPanel from '@/components/layout/AIPanel.vue'
import LoginModal from '@/components/modals/LoginModal.vue'

const themeStore = useThemeStore()
const taskStore = useTaskStore()
const userStore = useUserStore()
const layout = useLayoutStore()
const { toastMessage, toastVariant, toastVisible } = useToast()
const loginModal = ref<InstanceType<typeof LoginModal> | null>(null)
const philosophyText = ref('')
const perfMetrics = ref<{ apiLatency: number | null }>({ apiLatency: null })

// 公告横幅
const { visible: annVisible, currentMessage: annMessage, load: loadAnnouncements, dismiss: annDismiss, getCtaUrl: annCtaUrl } = useAnnouncements()

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
  taskStore.loadTasks()
  loadAnnouncements()
  loadPhilosophy()
})

async function loadPhilosophy() {
  const CACHE_KEY = 'philosophy_cache'
  const WEEK_MS = 7 * 24 * 60 * 60 * 1000
  try {
    const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || '{}')
    const now = Date.now()
    let text = cached.text
    if (!text || !cached.ts || now - cached.ts > WEEK_MS) {
      const res = await fetch('/api/philosophy/random')
      if (!res.ok) return
      const data = await res.json()
      if (!data.text) return
      text = data.text
      localStorage.setItem(CACHE_KEY, JSON.stringify({ text, ts: now }))
    }
    philosophyText.value = text || ''
    setTimeout(() => {
      const el = document.getElementById('philosophyText')
      if (el) el.classList.add('is-visible')
    }, 800)
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
