<template>
  <div class="ibv-page">
    <header class="ibv-head">
      <div class="ibv-title-row">
        <span class="ib-eyebrow">{{ t('generating.insights.board.eyebrow') }}</span>
        <h1 class="ibv-title">{{ taskTitle || t('generating.insights.board.viewer_untitled') }}</h1>
      </div>
      <a class="ibv-back" :href="meetingUrl">{{ t('generating.insights.board.viewer_back') }}</a>
    </header>

    <!-- 与会议页共用同一个 InsightBoard 组件：桥接、主题令牌、mermaid 渲染、多板 tab 轨都在这条路径上生效。
         「在浏览器中打开」因此与站内看到同一份观感——raw 端点只回磁盘字节，不跑桥接。 -->
    <div v-if="loadError" class="ibv-error">{{ loadError }}</div>
    <!-- 企业形态（B4）：副本 insights_html 全屏只读窗口——sandbox iframe 铺满内容区，边界与站内 Tab 同款 -->
    <iframe
      v-else-if="isEnterprise && enterpriseHtml"
      class="ibv-ent-frame"
      :srcdoc="enterpriseHtml"
      sandbox="allow-scripts"
      referrerpolicy="no-referrer"
      :title="t('enterprise.detail.insights')"
    ></iframe>
    <InsightBoard
      v-else-if="!isEnterprise"
      :artifact="board"
      :loading="loading"
      :boards="boards"
      :active-board-id="activeBoardId"
      @refresh="load()"
      @switch-board="onSwitchBoard"
      @create-board="onCreateBoard"
      @co-create="backToMeeting"
      @co-create-section="backToMeeting"
      @seek="backToMeeting"
      @open-in-browser="() => {}"
    />
    <!-- UI 走查低项 2：企业慢网装载空窗占位（复用加载文案，不新增键） -->
    <p v-else-if="loading" class="ibv-ent-loading">{{ t('enterprise.library.loading') }}</p>
  </div>
</template>

<script setup lang="ts">
/**
 * 洞察板独立浏览页 / Standalone board viewer
 *
 * 为什么需要这一页：板是一份 AI 直出的原始 HTML，mermaid 图由应用侧的 mermaid 模块渲染，
 * 而渲染能力挂在桥接脚本上（`sandbox` iframe + postMessage）。`/api/insights/board/{id}/raw`
 * 只回磁盘字节、不注入任何东西，因此在浏览器里直接打开 raw 会看到 `<pre>` 源码而不是图。
 * 本路由把同一个 `InsightBoard` 组件搬进独立页面：应用 JS 正常加载 → 图能渲染、
 * 主题令牌能下发（同源共享 localStorage 的主题偏好），同时板仍在 sandbox iframe 内，
 * 安全边界与站内一致（不因为"换个入口"就把原始 HTML 提到顶层文档执行）。
 *
 * 共创、原文跳转等需要会话/音频上下文的能力不在本页提供，一律引导回会议页。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import InsightBoard from '@/views/generating/InsightBoard.vue'
import { createBoard, listBoards, loadBoard, type BoardArtifact, type BoardSummary } from '@/api/board'
import { fetchTask } from '@/api/tasks'
import { isEnterprise } from '@/edition'

const { t } = useI18n()
const route = useRoute()

const taskId = String(route.params.taskId || '')
const emptyArtifact: BoardArtifact = { html: null, revision: 0, updated_at: null }
const board = ref<BoardArtifact>(emptyArtifact)
const boards = ref<BoardSummary[]>([])
const activeBoardId = ref(String(route.query.board_id || ''))
const loading = ref(false)
const loadError = ref('')

// ─── 企业形态（B4 版式找回）：副本 insights_html 服务端读面全屏呈现 ───
// 数据源=contexts.loadDetail（空间路由：团队副本/私有原件自动换向），不触本机 board 端点；
// 渲染仍是 sandbox iframe（allow-scripts，无 same-origin），安全边界与站内 Tab 完全一致——
// "全屏"只是呈现面积变化，不是权限变化。个人形态本分支零消费零变化。
const enterpriseHtml = ref('')
const taskTitle = ref('')

const meetingUrl = computed(() => `/meeting/${encodeURIComponent(taskId)}?tab=insights`)

async function load() {
  if (isEnterprise) {
    if (!taskId) { loadError.value = t('generating.insights.board.viewer_missing_task'); return }
    loading.value = true
    try {
      // 动态 import（space.switchSpace 同款惯例）：企业数据面模块不进个人包
      const { useSpaceStore } = await import('@/stores/space')
      const { useContextsStore } = await import('@/stores/contexts')
      const space = useSpaceStore()
      await space.ensureReady() // D014 同款：深链/重载首帧先等空间就绪，否则团队副本必 404
      const d = await useContextsStore().loadDetail(taskId)
      if (!d?.insights_html) { loadError.value = t('enterprise.detail.insights_empty'); return }
      enterpriseHtml.value = d.insights_html
      taskTitle.value = d.meta?.title || ''
      if (taskTitle.value) document.title = `${taskTitle.value} · ${t('generating.insights.board.eyebrow')}`
      loadError.value = ''
    } catch (e) {
      loadError.value = e instanceof Error ? e.message : String(e)
    } finally { loading.value = false }
    return
  }
  if (!taskId) { loadError.value = t('generating.insights.board.viewer_missing_task'); return }
  loading.value = true
  try {
    const manifest = await listBoards(taskId)
    boards.value = manifest.boards
    if (!activeBoardId.value || !manifest.boards.some(b => b.board_id === activeBoardId.value)) {
      activeBoardId.value = manifest.default_board_id
    }
    board.value = await loadBoard(taskId, activeBoardId.value)
    loadError.value = ''
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

/** 换板：地址栏带上 board_id，刷新/收藏后仍落在同一份板上 */
async function onSwitchBoard(id: string) {
  activeBoardId.value = id
  loading.value = true
  try {
    board.value = await loadBoard(taskId, id)
  } finally {
    loading.value = false
  }
  void window.history.replaceState({}, '', `${window.location.pathname}?board_id=${encodeURIComponent(id)}`)
}

/** 建板权在用户：本页的「＋ 新建板」就是显式动作，与会议页走同一个 POST */
async function onCreateBoard(title: string) {
  const created = await createBoard(taskId, title, undefined, 'ui')
  await load()
  if (created?.board_id) await onSwitchBoard(created.board_id)
}

/** 共创/跳转依赖会话与音频，独立页不提供：带回会议页 */
function backToMeeting() {
  window.location.href = meetingUrl.value
}

onMounted(async () => {
  await load()
  if (isEnterprise) return // 企业标题随 loadDetail 已取；本机 board/task 端点不触达
  try {
    const task = await fetchTask(taskId)
    taskTitle.value = task?.title || ''
    if (taskTitle.value) document.title = `${taskTitle.value} · ${t('generating.insights.board.eyebrow')}`
  } catch { /* 标题取不到不影响看板 */ }
})
</script>

<style scoped>
/* B4 企业形态全屏窗口：宽度铺满内容区（页头保持窄栏阅读节奏），iframe 内部版式由板自身 CSS 决定 */
.ibv-ent-frame { display: block; width: 100%; height: calc(100vh - 120px); min-height: 480px; border: none; border-radius: var(--radius-lg, 12px); background: #fff; box-sizing: border-box; }
.ibv-ent-loading { margin: var(--s-5, 24px) auto; font-size: var(--fs-12, 12px); color: var(--muted, #666); }
</style>
