---
title: "洞察板回归原始 HTML 改造方案"
description: "把洞察板（Insight Board）的版式所有权从应用侧交还 CLI：以 iframe 容器承载原始 HTML、把板文件纳入 CLI 上下文、支持一场会议多份板，并补齐原始出口。含契约变更、分期实施、风险与验收。已定：解禁 <script>（安全边界迁至 sandbox + Origin 守卫）、多板仅在用户显式新建时出现。"
tags: ["insight-board", "refactor-plan", "html", "context-export", "open-meeting-scribe"]
created_at: "2026-10-29"
updated_at: "2026-10-29"
version: "1.1.0"
author: "wangyongliang"
status: "implemented"
category: "technical"
related_docs: ["docs/API_CONTRACTS.md", "data/agent/_roles/_builtin/meeting-minutes/insights.md"]
---

## 实施状态（2026-10-29 落地）

本方案 R1–R4 四期已全部实施完毕。以下记录**与方案的三处修正**（评审时代码核对发现，实施按修正后的口径执行）：

1. **Origin 守卫改为白名单口径（非「等于宿主 origin」）**：本机 dev 用浏览器 `localhost:5173` 访问 `:8000` 时，写请求 `Origin` 是 `5173` 而非宿主自地址，按方案 4.7 原文「等于宿主 origin 否则 403」会误杀。实现改为：`Origin` 缺失（无头客户端）放行、命中 `_cors_origins` 白名单放行、其余（含 `null`）403 + `audit.log`。见 `app/server.py` 的 `cross_origin_write_guard`。
2. **存量板数为 0**：方案 §1 称 `data/tasks/*.board.html` 有 17 份，当前工作区扫描为 0。R3 惰性迁移仍实现（服务器/其他副本可能有存量），但 legacy `.ib-*` 组件样式的保留期缩短为「本次保留一个版本周期、下个版本随旧提示词删除」。
3. **`docs/API_CONTRACTS.md` 板 API 段落已严重漂移并一并修正**：原文仍写 `POST /board/analyze/task`、zone ops、`.board.json` 契约（该模式已退役，实际返回 `{html, revision, updated_at, board_id, title}`），本次按多板真实契约整段重写，而非只更新多板口径。

**主视觉判据（§10.2 唯一未拍板项）已按推荐值定案**：`<svg>` / `<canvas>` / mermaid 形态 `<pre>` / data URI 的 `<img>` 计入；`<table>`、相对路径 `<img>`、纯 CSS 条形不计入。

**交付分期（均已完成）**：
- R2：`core/cli_engine/context_export.py` 新增 `_write_board_files`（拷 `context/boards/<board_id>.html` + `index.md`，两出口一致）；`core/insight_board.py` 支持 `expected_revision`（`stale_baseline`）。
- R1：`sanitize_board_html` 拆两级、`_DROP_TAGS` 定为容器级五项、删 `_strip_global_css_and_wrappers`；主视觉判据按形态；前端 `InsightBoard.vue` 改 `sandbox` iframe + `useBoardBridge`/`boardBridge`/`boardThemeTokens`（5 类 postMessage）。
- 4.7：`app/server.py` 写请求 Origin 守卫。
- R3：`core/insight_board.py` manifest 多板模型 + `invoke_create_board` + `unknown_board_id` 硬不变量；`catalog.py`/`impl.py`/`agent_tools.py` 工具面；前端 tab 轨 + `create_insight_board` 提案确认卡（`useBoardProposal`）+ 轮询按 manifest。
- R4：`app/routers/insights.py` `raw`（CSP sandbox）/`open`/`boards` 端点。

**验证**：`pytest` 1057 通过（含 `test_insight_board.py`、`test_origin_guard.py` 新增、`test_agent_tools.py`/`test_text_correction.py`/`test_cli_engine.py` 更新）；`ruff check` 干净；`vue-tsc` 零错误；`vite build` 成功。

**关于 `decision-waiting-sublevel.html`**：它是决策卡「等待方」层级（方案 B）的交互原型，与洞察板改造无关，且 [DecisionNode.vue](../frontend/src/views/generating/DecisionNode.vue) 已实现该方案，本次不动。

---

# 上线后的两轮真实共创（rev1→rev3）：暴露项与修复

同一会议跑了两轮智能体共创（Qoder CLI CN 1.1.80），产物直接暴露了四个只有真板才能发现的问题（手写 fixture 都盖不到）：

1. **主题令牌被逐条打穿**（§4.3 主题下发）：桥原用 `documentElement.style.setProperty` 逐条写，inline 优先级高于板的 `:root{}`。rev1 真板自定义了 8 个变量、其中 4 个与宿主同名（`--bg/--muted/--accent/--warn`），只这 4 个被盖、`--ink` 仍为 #e8edf6 → 宿主切浅色主题时页头白底白字。已改为 `:root{…}` 样式表插到 `head` 最前（后来者胜），**语义从「覆写」降为「兜底」**。
2. **容器不给宽度**（§4.5 容器几何）：`.ib-root` 只写 `max-width:860px; margin:0 auto`，在 flex 列父容器 `.gen-insights-wrap` 里交叉轴 auto margin 使 `align-self:stretch` 失效→ shrink-to-fit。实测 iframe 钉在 **372px**（可用 671px），拖列不跟。补 `width:100%` 后 frameW = 列宽 − padding（515↔437 可逆跟随）。
3. **宽度变、高度不重报**（§4.3 resize 上报）：桥只监听 body 内容尺寸，列宽拖拽不一定触发，板底被裁。补接 `window.resize`，且仅当 `innerWidth` 真变时重测（否则父侧改 iframe 高度会反向触发子文档 resize，板内用了 vh 就是自馈环）。注：本项只验证了修复已入 bundle；前台可见视口才能观察重测（Chrome 对不可见窗口不派发 resize、不跑 ResizeObserver）。
4. **契约太软导致不跟随主题**：§4.4 原写「两种写法都可」，rev1/rev2 的 CLI 合法地选了「整套自定义色板」，于是板永远不跟应用主题。已收紧为：底色/正文/卡片面/边框**四个必须**用带兜底值的宿主令牌，**禁止在 `:root` 重定义同名令牌**，自带色一律走 `--ib-*` 命名空间；raw 出口不注入→ **兜底值必写**。另补上对比度底线 ≥4.5:1（主题所有权转移后可读性不再由宿主保证；实测 rev2 在浅色主题下两处小字 4.24/4.32 贴线不足）。

**图形化主导（§4.4）已在真板上成立**：rev3 为 6 节 / 6 节有有效 mermaid 主视觉，渲染后 6 张全部渲成 SVG（板内文本节点齐全、无 `flowchart` 源文字残留）；宽度在 320→1200px 各档复测均无横向溢出。
**仍待观察项**：`data-seek-ms` 锚点两轮都为 0（契约允许但未被主动使用）；会中/会后两个入口尚未在真板上同场复测。

---

# 洞察板回归原始 HTML 改造方案

> 建议落库路径：`docs/insight-board-raw-html-plan.md`（open-meeting-scribe）。
> 本文所有 `文件:行号` 均已核对当前工作副本（`core/`、`app/`、`frontend/src/`、`data/`）。

## 0. 一句话结论

版式归 CLI，安全与版本归应用。应用只做四件事：安全清洗、版本协议、跨边界能力（跳转写、单节寻址）、内容底线。其余排版意见全部撤除；呈现容器从 `v-html` 改为 `iframe`；板 HTML 原样进入 `context/`；一场会议可以有多份板，但新板只能由用户点出来。

| 编号 | 改造项 | 结论 | 依赖 | 建议顺序 |
|---|---|---|---|---|
| R1 | 原始 HTML 回归（iframe 容器 + 撤除剥壳 + `<script>` 放开 + 4.7 Origin 守卫） | 做 | 无 | 第 2 期 |
| R2 | 板 HTML 进入 CLI 上下文 | 做，收益最大 | 无 | **第 1 期** |
| R3 | 一场会议多份板（manifest + `board_id`，建板权在用户） | 做 | R1、R2 | 第 3 期 |
| R4 | 原始出口（在浏览器中打开） | 做，作次要入口 | R1 | 第 4 期 |

R2 先行的理由：它是纯增量（多写一个文件），不动渲染路径、不动安全边界，却能立刻终止"每轮从零重写"；R1 才是风险集中点，值得在 R2 稳定后再动。

### 0.1 已定决策（本轮拍板）

| # | 议题 | 决策 | 对方案的强制影响 |
|---|---|---|---|
| 1 | `<script>` 是否放开 | **放开** | 安全边界整体迁到浏览器侧：4.2 的 `sandbox` 与 §4.7 的 Origin 守卫成为**唯一**防线，R1 不再具备"切回 `v-html`"的回滚路径（7 期表已改）；4.1 的 `on*` 剥离保留为纵深防御，但必须在回执里如实上报字节被改动 |
| 3 | 多板粒度 | **仅用户显式新建** | 建板权从工具面收回到用户侧：6.3 的 `create_insight_board` 降级为"提案 + UI 按钮"两条通道，且 6.5 的"未知 `board_id` 绝不自动建板"成为 R3 的硬不变量 |

议题 2（主视觉判据放宽到哪一步）尚未拍板，4.4 给了推荐默认值，可按否决代价直接裁定。

---

## 1. 现状（证据）

写入链路唯一：

```
CLI 出 HTML → revise_insight_board(html)              core/agent_tools/catalog.py:207
            → invoke_revise_board                     core/insight_board.py:909
            → sanitize_board_html                     core/insight_board.py:571
            → atomic_write_text(<task_id>.board.html) core/insight_board.py:768,856
前端只读重拉：GET /api/insights/board/{task_id}        app/routers/insights.py:104
             → InsightBoard.vue `v-html`               frontend/src/views/generating/InsightBoard.vue:31
```

应用侧正在行使"排版权"的四处，即本次要撤除的对象：

1. **文档剥壳**：`_strip_global_css_and_wrappers`（`core/insight_board.py:536`）删掉 `DOCTYPE/<html>/<head>/<body>`，并按正则删除 `:root/html/body/*` 选择器的 CSS 规则（`_GLOBAL_CSS_SELECTORS`，:531）。动机写在 docstring 里：`v-html` 注入后 `:root` 会匹配宿主 `<html>`，反向污染全局主题。也就是说，**剥壳是 `v-html` 容器的副产品，不是目标**。换容器即可撤。
2. **工具契约**：`catalog.py:238-247` 要求"只输出片段、不要外壳、不得写全局选择器、颜色一律用应用 CSS 变量（并列出 20 个令牌名）"，:231 还规定"对照用两个 subgraph 分泳道"。
3. **组件类名库**：`notes-editor.css:936-1079` 定义 `.ib-dilemma/.ib-visual/.ib-mermaid/.ib-roadmap/.ib-phase/.ib-tradeoff/.ib-chip/.ib-kicker/.ib-grid/.ib-compare/.ib-col` 等，`.ib-compare` 双泳道样式在 :1015；:973 的注释已把 `ib-flow/ib-tree/ib-compare/ib-grid` 标为 legacy，仅为存量板保留。
4. **主题令牌就近注入**：`.ib-html` 在 :896-914 为 AI 惯用的"非应用真名"令牌提供别名映射（`--success→--ok`、`--danger-bg→--error-soft` 等），本质是在替 CLI 兜排版债。

内容底线与排版无关，属于"内容质量闸"，保留：`detect_recap_floor`（:707，五类复述信号 ≥2 分拒收）、`detect_text_wall`（:754，节式板必须先画后主文）。

上下文的缺口：`export_project_context` 系列写入 `context/` 的清单是 `transcript.md`、`summary.md`、`notes.md`、`decisions.json`、`insights.md`、`history.md`、`attachments/*`（`core/cli_engine/context_export.py:447-545`）——**板 HTML 不在其中**。因此 CLI 每轮只能靠 `revise_insight_board()` 空参回读（:917-923），拿不到基线就没有基线，冷启动必然整份重写；而 `_render_insights`（:302）只把洞察卡渲染成 Markdown，版式信息在上下文里完全不存在。

单文件硬编码：`_board_html_path`（:768）、`_board_meta_path`（:772）均以 `task_id` 为唯一键；旁路消费者也按同一文件名写死——`core/text_correction.py:270` 扫 `TASKS_DIR / f"{task_id}.board.html"`，`scripts/cleanup_test_tasks.py:38` 的 `SIDECAR_SUFFIXES` 含 `.board.html`。

存量数据规模：`data/tasks/*.board.html` 共 17 份，11.5–16.1 KB（最大 16,138 字节）；`BOARD_HTML_CAP = 300_000` 字符（:519）远未触及。

---

## 2. 目标契约：重新划分所有权

| 归属 | 内容 |
|---|---|
| **CLI（全部版式权）** | 是否整份文档、`<style>` 写法与全局选择器、字体、配色（可用自己的十六进制）、栅格与断点、分组/卡片/图文/表格形态、交互脚本 |
| **应用（不可让渡）** | XSS 与资源边界、`revision` 版本协议、落盘原子性、内容底线（复述/文字墙）、跨边界能力桥接、呈现容器 |
| **最小内容契约（三条）** | ① 顶层节包 `<section data-ib-id data-ib-title>`；② 跳转写用 `[data-seek-ms]`；③ 每节存在一个"主视觉"——按能力识别，不按类名 |

三条契约里，①②是**寻址能力**（没有它们，单节共创与转写跳转做不到），③是**内容质量闸的判据**。除此之外不再有版式要求。第 3 期把 ③ 的判据从类名降为形态（见 §4.4）。

---

## 3. R2 — 板 HTML 进入 CLI 上下文（第 1 期）

### 3.1 改动

在 `context_export.py` 的导出流程中，紧随 `_render_insights`（:517 附近）加一步：把**消毒后实际展示的字节**原样拷进工作区，而不是重建。

```
context/boards/<board_id>.html          # 与 data/tasks/<...>.board.html 逐字节一致
context/boards/index.md                 # 清单：board_id / 标题 / revision / 字节数 / 更新时间
```

关键约定：

- 拷 `board_html_load()` 返回的内容（即落盘版本），保证 CLI 看到的基线 = 用户看到的板。不要拷 CLI 提交的原始文本，那与展示版本已经不一致（剥壳与清洗会改字节）。
- `index.md` 里写明 `revision`。CLI 写回时带上 `expected_revision`（见 3.3），用于发现自己读到的基线已过期。
- 走**文件**而非 prompt 注入：工作区文件模式对 token 预算宽松（`context_export.py:516` 的既有注释即为证据），板不进 `brief`，由 CLI 按需 `Read`。所以 R2 的边际 token 成本只在 CLI 真的打开该文件时发生。
- 上限保护：单份拷贝上限沿用 `BOARD_HTML_CAP`；超出（未来大板）只拷 `index.md` + 截断提示，并在 `index.md` 里标注 `truncated: true`，不允许静默截断。

### 3.2 brief 侧同步

`context_export.py:600-608` 的"强制执行三步"文案要把基线来源改为工作区文件：

```
① 读 context/boards/<board_id>.html（冷启动时无此文件 = 首版）
② 需要外部知识时 web_search ≤2 次
③ revise_insight_board(board_id, html, expected_revision) 落盘，回执 revision≥1 才算完成
```

### 3.3 顺带解决：写回不再"最后写者赢"

`invoke_revise_board`（:909）目前无并发保护，`board_html_save` 直接 `revision+1` 覆盖（:853-857）。模块注释（:826）称"写入方唯一，不存在并发合并问题"——这个前提在 R2 之后不再成立：CLI 手里的基线可能是上一轮导出的快照，期间用户可能在另一个窗口共创过。

新增可选参数 `expected_revision`（int）。不匹配则返回 `{"ok": false, "error": "stale_baseline", "current_revision": N, "hint": "重新读取基线后再改"}`，不落盘。老会话不带该参数时保持现有覆盖语义，避免一次性收紧造成大面积拒写。

### 3.4 验收

- 会中/会后各发起一次板共创，工作区 `context/boards/` 出现文件且与 `data/tasks/` 展示版本 `diff` 为空。
- 删除板后重进会议页，`index.md` 不残留已删除的板条目。
- 故意在两个窗口先后写同一板，第二个写入方若带旧 `expected_revision` 收到 `stale_baseline` 而非静默覆盖。

---

## 4. R1 — 原始 HTML 回归（第 2 期）

### 4.1 撤除剥壳：清洗分两级

把 `sanitize_board_html`（:571）拆成两个函数，调用点各取所需：

| 函数 | 内容 | 用于 |
|---|---|---|
| `sanitize_board_html` | 仅安全项：危险 `href/src` scheme（`javascript:`/`data:text/html`，:594）、`on*` 内联事件（:591，见下）、`_DROP_TAGS` 中的内容级嵌套危险标签 | 落盘前（所有板） |
| ~~`_strip_global_css_and_wrappers`~~ | **删除调用**，函数连同 :531-533 三个正则一并移除 | — |

`_DROP_TAGS`（:522）按"内容级 / 容器级"重新解释，本次定案如下：

- **解禁**：`script`（已定，见 0.1）、`link`/`meta`（文档内资源与视口声明；资源为何仍须一律内联，见 4.5-4）、`style` 与 `:root/html/body/*` 全局选择器——在 iframe 文档内部，全局作用器只影响板自己。
- **继续禁**（内容级，防板内再套 iframe 指回站内端点、或 `object/embed/base/form` 逃逸）：`iframe`、`object`、`embed`、`base`、`form`。

`on*` 与 `<script>` 在新边界下**能力等价**（内联事件处理器就是脚本），因此放开 `script` 逻辑上应当同时放开 `on*`。这里仍选择保留剥离，理由是两条而非排版：① `form` 标签仍禁、`sandbox` 仍不给 `allow-forms`/`allow-top-navigation`，`on*` 也仍剥，则"万一要退回 `v-html`"时损害面被压到最小（回滚的真实代价见 §7）；② 剥离会改动 CLI 字节，与 §9-1 的"磁盘与提交 `diff` 为空"直接冲突，所以必须**如实上报**：现有 `removed` 记账（4.6 已引用）继续输出被剥属性名与次数，工具回执原样回传给 CLI，让"字节被改"是可发现事实而不是静默变异。

`_valid_task_id`（:525）与落盘原子性不动。

### 4.2 呈现容器：`iframe srcdoc` + 桥接

`InsightBoard.vue:31` 的 `<div class="ib-html" v-html>` 替换为：

```html
<iframe ref="frameEl" class="ib-frame" sandbox="allow-scripts" :srcdoc="composedDoc" />
```

- `srcdoc` = 落盘字节 + **应用追加**的桥接脚本（在内存里拼接，绝不写回磁盘，磁盘上始终是 CLI 的原始 HTML）。
- `sandbox="allow-scripts"` 且**不给** `allow-same-origin`：板文档落入 opaque origin（`Origin: null`），读不到宿主 DOM、宿主 `localStorage`，也无法读取任何跨源响应。这是把 XSS 防线从"正则剥壳"迁到"浏览器边界"的唯一诚实做法——继续用 `v-html` 又放开 `script` 等于直接开洞。
- 边界到底买到什么，要说准（已核对本机实现）：
  - **响应读取必失败**：`app/server.py:388-394` 的 CORS 是固定 localhost 端口白名单（:154-162，`allow_credentials=True`），`null` origin 不在其中，板内脚本拿不到任何返回值。
  - **反向工具面打不到**：`/api/agent-tools/*` 走进程内短时 bearer（`app/routers/agent_tools.py:46-55`）且在 JWT 豁免白名单里（`server.py:278`），凭据不在 cookie 里，opaque origin 无从获取。
  - **写请求本身仍可能送达**：CORS 只拦响应不拦"简单请求"（`text/plain` POST、表单式 GET）。`enforce_auth_middleware`（:287-308）默认关闭（`REQUIRE_AUTH=false`，:266，本地免登录是产品定位），此时写端点对任何到达的请求都会执行；`REQUIRE_AUTH=true` 时 `SameSite=Lax` 的会话 cookie（`app/routers/auth.py:133-141`）在同一 site 的 sandbox 上下文里仍可能随行。**即 opaque origin 挡住的是"看见"，不是"打进"**。
  - 残余缺口由 4.7 的 Origin 守卫补齐；`form` 标签继续禁，`sandbox` 也不给 `allow-forms`/`allow-top-navigation`，已经掐掉另外两条 CSRF 载体。
- 跨边界只能靠 `postMessage`（opaque origin 下父窗口无法访问 iframe DOM，双向皆然），因此所有原父级委托逻辑必须搬进桥接脚本。

### 4.3 桥接协议（5 类消息）

| 方向 | 消息 | 取代的现状 |
|---|---|---|
| iframe → 父 | `ib:seek {ms}` | `InsightBoard.vue:160-168` 的父级 `[data-seek-ms]` 点击委托 |
| iframe → 父 | `ib:hover {id,title,top,right}` | `InsightBoard.vue:171-188` 的 `getBoundingClientRect` 差值算法（跨文档不可用） |
| iframe → 父 | `ib:resize {height}` | iframe 不自适应高度：父级据此设 `style.height`；桥接内用 `ResizeObserver` 覆盖字体加载与图渲染后的二次变化 |
| 父 → iframe | `ib:theme {vars, dark}` | 主题切换（现状 `InsightBoard.vue:143` 直接重渲 mermaid） |
| 双向 | `ib:mermaid {req,data-ib-id}` / `ib:mermaid:ok {svg}` | `InsightBoard.vue:93-135` 的 mermaid 渲染 |

`v-html` 时代的 `box-sizing`、节间距兜底（`notes-editor.css:914-917`）随容器一起废弃：板内部节奏由 CLI 负责。`.ib-root/.ib-head/.ib-rev/.ib-tool-btn/.ib-sec-cocreate`（:865-931）是应用自己的 chrome，保留。

### 4.4 mermaid 归属：必须现在定，否则 R1 交付即坏

现状落盘的是 mermaid **源码**（`pre.ib-mermaid`，`catalog.py:230`；CSS `display:none` 见 `notes-editor.css:964`），显示时由前端用打包好的 mermaid 渲染（`frontend/src/utils/renderMermaid.ts`，`InsightBoard.vue:101`）。三条路：

| 方案 | 说明 | 判定 |
|---|---|---|
| A. CLI 自带 mermaid.js + CDN | 真"原始 HTML"，但本机应用（`desktop.py` 的 pywebview 单进程形态）常处离线/内网环境，图会整片空白 | 否 |
| B. 应用一律不渲染图 | 违背"图主导"的内容底线，`detect_text_wall` 存在的前提被抽掉 | 否 |
| **C. 桥接代发（推荐）** | 桥接脚本在 iframe 内扫描候选 `<pre>` → 把源码 post 给父 → 父用现有 `renderMermaid.ts` 渲成 SVG（含深浅色分支）→ 回传 SVG 字符串 → 桥接在 iframe 内 `innerHTML` 就地替换 | 是 |

C 的契约要按**形态**识别，不再认类名：`<pre>` 首个非 `%%{ }%%` 指令行的首词命中 `_MERMAID_TYPES` 白名单（`insight_board.py:647-648`，`flowchart/graph/sequenceDiagram/stateDiagram(-v2)/mindmap/timeline`）即视为图。这段判定逻辑已有（`_mermaid_pre_ok`，:663），复用它，把类名要求摘掉。同理 `detect_text_wall` 的"主视觉"判据（`_VISUAL_MARK_RE`，:637）从类名改为形态：`<svg>` / `<canvas>` / mermaid 形态 `<pre>` 三项无争议，`<img>` 与 `<table>` 的归属见 §10.2 的推荐值（这是本轮唯一未拍板的判据，只影响 `detect_text_wall`，不阻塞第 1、2 期的其余改动）。类名 `.ib-flow/.ib-tree/.ib-compare/.ib-grid` 的识别保留一个版本周期，用于存量板。

### 4.5 已知代价（写清，不含糊）

1. **主题跟随失效**：板不再自动吃 `--surface/--fg` 等令牌。缓解：桥接在 `ib:theme` 里下发同一组变量并 `document.documentElement.style.setProperty`，CLI 若用了 `var(--accent)` 就自动跟随，用了硬编码色就保持硬编码——两种都合法，由 CLI 决定。
2. **深色主题对比度**：CLI 硬编码浅色底 + 应用深色 UI 会出现"亮块"。不做拦截（那是排版意见），但在 `index.md` 里回报板声明的主底色，供 UI 侧决定是否给 iframe 外层加 `border` 收边。
3. **响应式责任转移**：`.ib-html` 的 `overflow-x:auto`（:913）没了，板自己不管断点就会横向溢出。撤除 `catalog.py:238-247` 时必须同步补一句"你需要自带响应式"。
4. **资源不靠相对路径（结论确定，理由与实现无关）**：`srcdoc` 文档的地址是 `about:srcdoc`，相对地址会否继承宿主 base URL 属实现细节（Chrome/WebKit 通常继承，`<img src="x.png">` 有可能真能加载）——**不要把版式建在这上面**，R1 前用一次 30 秒实测把它写成事实（宿主 devtools 里执行 `frame.contentDocument.defaultView.eval("document.baseURI")`，结论记进 `docs/`）。三条不受实现影响的原因决定一律内联：① 同一份 HTML 还要经 §5 的 raw 端点在浏览器里打开，那时 base 变成 `/api/insights/board/...`，两处解析结果必然不同；② 板要拷进 `context/` 给 CLI 读，相对路径对 CLI 侧毫无意义；③ opaque origin 下 `fetch()`/XHR 读不到响应（4.2），任何"脚本取资源"的写法都必坏。因此 `<img>`/字体/`<style>` 一律 data URI 内联，确需站内资源时用绝对地址指向 §5 端点。

   > **实测结论（2026-10-29 已测，落成事实）**：在跑起来的宿主 devtools 里取板 iframe 的 `document.baseURI`，得到的是**宿主当前页面 URL**（例 `http://127.0.0.1:8000/meeting/<task_id>?tab=insights`），**不是 `about:srcdoc`**；即本实现的 srcdoc 文档确实继承了宿主 base URL，`<img src="x.png">` 被解析成 `http://127.0.0.1:8000/meeting/x.png`（实测命中 404）。这恰恰印证了“不要把版式建在相对路径上”：相对路径的解析基准是**宿主当前路由**，同一份 HTML 在会议页/详情页/raw 端点三种入口下 base 全不同，图会不会坏看运气；板拷进 `context/` 给 CLI 时相对路径更毫无意义。故硬约束依旧：图片/字体/样式资源一律 data URI 内联（`catalog.py` 与角色 `insights.md` 已写明）。
5. **可访问性**：`iframe` 需 `title`；键盘 Tab 序列会进入子文档，`sandbox` 不给 `allow-top-navigation`，防止板劫持宿主页面。

### 4.6 验收

- 手工构造一份含 `<!DOCTYPE><html><head><style>:root{--accent:#123456}</style></head><body>…<script>document.title='x'</script></body></html>` 的板，落盘后：外壳与 `:root` **完整保留**（`removed` 里不再出现 `doctype/css:*` 项），`:root` 不影响宿主主题（切深浅色对比 `document.documentElement` 计算样式）。
- 恶意样本：`<script>fetch('/api/insights/board/xxx',{method:'POST'})</script>`、`<iframe src="/api/workspace/tree">`、`onclick` 属性、`javascript:href` —— 后两者被清洗，`iframe` 标签被剥；`fetch` 那条**响应读不到但请求可能送达**（4.2），因此必须由 4.7 的守卫拒收，用例断言 HTTP 403 而不是只断言"读不到"。
- `tests/test_insight_board.py:44-76` 中断言剥壳与 `removed` 计数的用例改写；新增"外壳保留"用例。

### 4.7 服务端补刀：写请求的 Origin 守卫（R1 必带）

解禁 `<script>` 之后，板内脚本能做的事只剩一件危险项：**盲打写端点**（拿不到响应，但 `POST/PUT/PATCH/DELETE` 的简单请求会被服务器执行）。这是 4.2 边界分析留下的唯一实际缺口，必须在 R1 同期补上，否则"放开脚本"这个决策是借来的安全。

- 落点：`app/server.py` 新增一个 `@app.middleware("http")`，与 `security_audit_middleware`（:327）同层。规则一句话：写方法（`POST/PUT/PATCH/DELETE`）+ 路径以 `/api/` 开头 + 不在 `_AUTH_EXEMPT_PREFIXES`（:275-284）内 ⇒ `Origin` 要么缺失（无头客户端，现状本就全放行，不构成新缺口），要么等于宿主 origin，否则 403 并落 `audit.log`。板内文档发出的一切写请求都带非空 `Origin: null`，必然落进"否则"那一支。
- 为什么 `Origin: null` 是可靠信号：opaque origin 的 sandbox 文档发跨源请求必然带 `Origin: null`；`_cors_origins`（:154-162）里从来不含 `null`，因此不存在"合法来源被误判"的中间态。
- 宿主 UI 不会被误伤，这一点已核对：`desktop.py:303` 以 `url = f"http://{host}:{port}"` 装载窗口，`:212-214` 传给 `webview.create_window`，即前端与 API **同源**（`http://127.0.0.1:<port>`），写请求带的是真实 origin 而非 `null`。浏览器形态（本机 dev 用 `localhost:5173` 访问 `:8000`）也已在 CORS 白名单内。
- 兜底方案（仅当将来出现"`Origin` 真为 `null` 的合法宿主"，例如改用自定义 scheme 或 `file://` 装载前端时）：宿主启动时生成随机 nonce 注入 `<meta>`，前端写请求带 `X-App-Nonce`；板内文档因 opaque origin 读不到宿主 DOM，拿不到该值。这仍是 R1 之后可独立加的补丁，不改变本方案的其他结论。
- 验收：从板内 `fetch('/api/tasks/x/decisions', {method:'POST', body:'{}', headers:{'content-type':'text/plain'}})` 得到 403 并记入 `audit.log`；UI 的同类操作不受影响。

---

## 5. R4 — 原始出口：在浏览器中打开（第 4 期，与 R1 同期实现亦可）

**需要，但作为次要入口。** 文件本来就是磁盘上的真 HTML，缺的只是出口；主视图若改成"点一下才看得到"，翻页共创的节奏会断。

- 新端点：`GET /api/insights/board/{task_id}/raw?board_id=&rev=` → 直接回磁盘字节，`media_type="text/html"`。
- **必须带 `Content-Security-Policy: sandbox allow-scripts`**。这是关键：经 `srcdoc` 时板是 opaque origin（`Origin: null`，被 4.7 的守卫拒发写请求），经这个端点它是**站内同源文档**，带的是真实宿主 origin——**4.7 那道守卫在这里失效**。所以裸 HTML 出口的唯一防线只剩这条 CSP 响应头：缺了它，`<script>` 放开这个决策就真的有了一条可用的写端点通路。`sandbox` CSP 指令在 WebKit（`desktop.py` 用的 pywebview/WKWebView）与 Chrome 均受支持；`raw` 端点的响应头单测与 4.6/4.7 的用例同批进 CI。
- 打开方式：前端 `window.open` 在 pywebview 里不可靠，走后端 `POST /api/insights/board/{task_id}/open` → `webbrowser.open(raw_url)`（`app/`、`core/`、`desktop.py` 当前无 `webbrowser` 用法，属新增）。入口放板头（`InsightBoard.vue:4-14` 的 `.ib-head`，与「刷新」「共创」并列为 `is-tool-btn` 次级按钮，不抢主 CTA）。
- 与工作区浏览器的关系：`workspace.py:37` 的 `_PREVIEWABLE_EXTS = {".md",".json",".txt"}` 不含 `.html`，且板在 `data/tasks/` 而非工作区。不要为此放开该白名单——用专门的 raw 端点，避免把"任意 HTML 同源渲染"变成工作区浏览器的通用能力。
- `rev=` 参数固定展示某版本（前端从 `revision` 取），避免用户在浏览器里看到的是轮询间隙的新版而共创时引用的是旧版。

---

## 6. R3 — 一场会议多份板（第 3 期）

### 6.1 数据模型

`<task_id>.board.meta.json`（`insight_board.py:772`）升级为 manifest `<task_id>.boards.json`：

```json
{ "boards": [ { "board_id": "main", "title": "供应链阻塞破局", "file": "main",
                "revision": 7, "updated_at": 1730000000000 } ],
  "default_board_id": "main" }
```

文件命名 `data/tasks/<task_id>.board.<board_id>.html`，per-board meta 内联在 manifest 中（少一次读盘；`board_html_meta` 的 64 字节轮询响应改为读 manifest）。

`board_id` 校验复用 `_SECTION_ID_RE` 的思路（:864）：`^[\w-]{1,48}$`，并保留 `main` 为存量迁移目标与 `default_board_id`。走 `_valid_task_id`（:525）同样的穿越拒绝。

### 6.2 存量兼容

首次读取时若无 manifest 且有 `<task_id>.board.html`，就地把该文件重命名为 `<task_id>.board.main.html` 并生成 manifest（一次性、幂等、不复制不丢版本）。不做双读路径——留一条"老文件名也认"的分支会让 R3 的六处消费者各背一份兼容码。

### 6.3 工具面（`catalog.py`）

| 工具 | 变更 |
|---|---|
| `revise_insight_board` | 新增 `board_id`（缺省取 manifest 的 `default_board_id`）、`expected_revision`；空参读时返回 manifest 摘要（`board_id/title/revision` 列表）而不是一份正文，让 CLI 先选目标；**`board_id` 不在 manifest 内直接拒**（见 6.5） |
| `revise_insight_board_section` | 新增 `board_id`（同样严格校验）；`section_id` 在板内寻址（`_section_pattern`，:867 不动） |
| `create_insight_board` | 新增，但**是提案不是写**：`kind: "write"`, `persists: False`（与 `propose_summary`/`propose_notes` 同构，`catalog.py:113,130`），入参 `board_id + title + html`；工具本身不落盘，回执经 `tool_call` 事件回前端确认卡，**用户点「接受」才由 6.5 的 POST 端点建板** |
| `list_insight_boards` | 新增：只读，返回 manifest（`needs_task: True, kind: "read"`） |

`mcp_tool_specs()`（:284）自动带上新工具，无需改 `mcp-bridge`（提案式工具同样按 `kind=write` 预授权，与 `propose_summary` 现状一致）。分发点在 `app/routers/agent_tools.py:_dispatch_write`（:81）里加两支：`create_insight_board` 走"只回提案、不碰磁盘"分支（仿 :114 与 :123 的写法与审计日志措辞），`revise_insight_board` / `revise_insight_board_section` 的现有分支（:233-246）透传 `board_id`；`core/agent_tools/impl.py:48-49,103-108` 的工具名与标签同步（两处消费防定义漂移，注释已声明此约束）。

`frontend/src/composables/useBoardSync.ts:12` 的 `BOARD_WRITE_TOOLS` 只加**真会写盘**的工具名（`create_insight_board` 属提案，不应触发重拉），`isBoardWriteCall`（:28）判定不变，但 `BOARD_WRITTEN_EVENT` 的 detail（:49）要带 `board_id`——否则多板下重拉会拉错板。

### 6.4 前端

- `api/board.ts`：`loadBoard/loadBoardMeta` 增 `boardId` 参数（默认取 manifest 的 `default_board_id`）。
- 新 API `GET /api/insights/board/{task_id}/boards` 返 manifest，供 tab 轨渲染。
- `InsightBoard.vue` 上方加一条板 tab 轨（板数 ≤1 时不显示，保持现有单板观感不变）。
- tab 轨尾部一个「＋ 新建板」次级按钮（与 6.5 通道①对应），点击弹标题输入，确认后 `POST` 建板并把 tab 焦点切到新板；板数 = 0（迁移期理论不出现）时退回现有单板观感。
- 会话侧新增"建板提案卡"：`create_insight_board` 的 tool_result 渲染为确认卡（复用 `propose_summary` 的接受/拒绝交互形状，只是内容是"新建一份板"而非行级 diff），「接受」才调 6.5 的 POST。
- 轮询：`GeneratingView.vue:754` 与 `RecInsightsPanel.vue:281` 的 `BOARD_POLL_MS = 10_000` 各探一次 manifest（一次请求拿全部 revision），变化时只重拉当前可见板。
- 单节共创悬浮按钮的 `board_id` 随 `emit('coCreateSection')` 一起上抛，会话侧填入工具参数。

### 6.5 建板权：只有用户能建板（已定）

决策原文是"用户显式新建才有多板"。落成代码需要两条合法通道加一条硬不变量，否则同一条 UI 里"AI 顺手拆板"仍然会发生。

两条通道，收敛到同一个实现：

| 通道 | 触发者 | 路径 |
|---|---|---|
| ① 直接新建 | 用户点「＋ 新建板」 | `POST /api/insights/board/{task_id}/boards {board_id?, title}` → `invoke_create_board()`（`core/insight_board.py` 新导出）写 manifest 条目 |
| ② 提案后新建 | AI 建议拆板，**用户点「接受」** | `create_insight_board`（`persists: False`）只回提案 → 前端确认卡 → 「接受」调**同一个** POST 端点 |

- 建板只写 manifest 条目（`revision: 0`，`file` 指向尚未存在的 `<task_id>.board.<board_id>.html`），HTML 文件留到首次 `revise_insight_board` 时创建。好处是"空板不产生 0 字节文件"，`cleanup_test_tasks.py` 与 `text_correction.py` 的板遍历都以 manifest 为准，不必特判空文件。
- `board_id` 由服务端生成缺省值（`board-2`、`board-3`…），用户可改标题；`title` 必填。

硬不变量（R3 的验收门槛，写进 `invoke_revise_board` :909 与 `board_html_save_section`）：

```
board_id 不在 manifest 内 → {"ok": false, "error": "unknown_board_id",
                            "boards": [...], "hint": "需要新板请调用 create_insight_board 提案，由用户确认"}
```

**绝不隐式建板**。这条是决策真正生效的地方：只要 `revise_insight_board` 还能"写一个不存在的 board_id 就顺手建出来"，"仅用户显式新建"就只是一句文案。配套把角色提示（`data/agent/_roles/_builtin/*/insights.md`，见 6.6）与 3.2 的 brief 文案都改成"想拆板先向用户提议"。

为什么把建板权留在用户侧（记录理由，便于后人翻案）：多板会同时牵动 `useBoardSync` 重拉、`text_correction` 全板回溯、`context/boards/index.md` 基线清单三条链路，这些成本在 AI 侧不可见；而"这场会议要不要第二份板"是用户单方面就能答对的问题。AI 仍保留**提议**权（通道②），只是执行权在用户手上——与随记/纪要改写走 `propose_*` 的既有产品姿态完全同构。

### 6.6 连带改动清单（容易漏）

| 位置 | 改动 |
|---|---|
| `core/text_correction.py:213-231, 270` | `_correct_board_file` 加 `board_id`，错字回溯遍历 manifest 全部板；残留扫描从单文件改为按 manifest 展开 |
| `scripts/cleanup_test_tasks.py:38` | `SIDECAR_SUFFIXES` 加 `.boards.json` 与 `.board.<id>.html` 形态（改 glob） |
| `app/routers/insights.py:74` 附近 | 新增 `POST .../boards`（建板，通道①②共用）与 `GET .../boards`（manifest）；建板要写 `audit_logger`，与 `agent_tools.py:119` 的"未落盘,待用户确认"审计措辞对齐，方便回溯是谁点的「接受」 |
| §5 的 `raw` / `open` 端点 | 增 `board_id` 查询参数（缺省 `default_board_id`），路径仍按 `task_id` 分节——多板下"在浏览器中打开"必须能指到当前可见的那一份 |
| `docs/API_CONTRACTS.md:560-568` | 板修正管线段落更新为多板口径 |
| `data/agent/_roles/_builtin/*/insights.md` | 角色版式骨架（当前 v2.3.0，第 23-66 行是 `.ib-*` 骨架示例）改写为"内容三契约 + 版式自定"，两个内置角色都要 |
| `tests/test_insight_board.py`、`tests/test_text_correction.py:114-141` | 路径断言与夹具更新 |

---

## 7. 分期与回滚

| 期 | 内容 | 可独立发布 | 回滚方式 |
|---|---|---|---|
| 1 | R2 上下文 + `expected_revision` | 是 | 去掉导出步骤即可，磁盘格式不变 |
| 2 | R1 iframe 容器 + 撤剥壳 + 契约松绑 + 4.5 代价 + **4.7 Origin 守卫** | 是 | **没有回滚到 `v-html` 的路径**（已定：`<script>` 放开，`v-html` 下脚本直接执行）。回滚只能"向前修"：`sandbox` 属性与桥接脚本是渲染必需项，出问题就在 iframe 内修。若必须停用新容器，唯一安全做法是同时恢复 `_strip_global_css_and_wrappers` 并把 `script` 加回 `_DROP_TAGS`，等于回到改造前——这条路要写明是"退回改造前"，不是"切个 flag" |
| 3 | R3 多板 + manifest 迁移 + **6.5 建板权** | 否（依赖 R1/R2 语义） | manifest 保留 `default_board_id`，回滚需先把 `main` 板改回旧文件名；用户新建出来的额外板不会被静默删除，回滚脚本需显式列出它们并交还用户决定 |
| 4 | R4 raw 端点 + 打开 | 是（R1 之后） | 删端点 |

建议 R1 与 R4 同批交付：撤剥壳后板可能自带 `<style>` 与硬编码色，若此时还没有"在浏览器里看真版本"的出口，用户看到任何不满意都只能靠再共创解决，调试成本高一个量级。

---

## 8. 风险

| 风险 | 触发条件 | 处置 |
|---|---|---|
| XSS 面扩大 | 解禁 `<script>` 已成为定案，风险不再是"要不要放"而是"sandbox 配错"：漏写 `allow-scripts` 却给了 `allow-same-origin`、或 raw 端点漏 `sandbox` CSP | 4.6 的恶意样本用例进 CI；两处 sandbox 配置加代码注释锚点，禁止后人在同一处"顺手加个 origin"；`sandbox` 值写成常量而非拼接，避免 `allow-scripts allow-same-origin` 同时出现 |
| 外部内容盲打写端点 | 板 HTML 里可能混入 `web_search`/`web_fetch` 取回的外部文本被 AI 原样排进板；opaque origin 只挡响应读取，不挡简单请求到达服务器（4.2） | 4.7 的 Origin 守卫（写方法 + `Origin: null` → 403 + `audit.log`）；`form` 标签继续禁且不给 `allow-forms`；建议同步把写端点的 `POST` 语义做成幂等或加 `expected_revision`，降低盲打成功后的损害面 |
| 建板限制被绕过 | R3 实施时只在 UI 上藏起「新建板」，`revise_insight_board` 仍对未知 `board_id` 隐式建板 | 6.5 的 `unknown_board_id` 分支进单测（断"不建板 + 不产生文件 + 回执列出候选板"），并把角色提示与 3.2 brief 文案一并改成"先提议" |
| 板内容质量下降 | 撤掉 `.ib-*` 组件库与"对照用两个 subgraph"后，模型退回文字墙/卡片堆砌 | 保留 `detect_recap_floor` 与 `detect_text_wall`，仅把主视觉判据从类名放宽为形态（4.4）；拒收理由回传 AI 的自纠循环（:842-851）不动 |
| 高度塌陷 / 双滚动条 | `ib:resize` 时序（字体加载、mermaid 回传后高度再变） | 桥接用 `ResizeObserver` 持续上报；父级 `min-height` 兜底并保留 `.ib-frame` 的 `overflow-y:auto` 作为失败态 |
| 单节共创定位失效 | 跨 opaque origin 拿不到 rect | `ib:hover` 由 iframe 侧上报自身坐标，父级只做定位（4.3） |
| 存量板显示异常 | 旧板是"片段 + 应用类名"，新容器里缺 `<style>` 会变裸文本 | 迁移期保留 `notes-editor.css` 的 legacy 组件样式至少一个版本周期；或首版共创时由 AI 自行补样式（在 `index.md` 里把这一选项写出来） |
| 上下文膨胀 | 多板 × 大板全量拷进 `context/` | 上限策略见 3.1；板不进 `brief`，只按需 `Read` |

---

## 9. 总体验收

1. CLI 提交含完整外壳与 `<style>` 的 HTML，磁盘文件与提交内容 `diff` 为空（剥壳彻底撤除）。若提交内容里含被剥项（`on*`、危险 scheme、禁用的 `iframe/form/object/embed/base`），则磁盘与"提交内容减去回执 `removed` 列出的项"一致——**不允许出现既没落盘也没上报的改动**。
2. 板内 `:root`、硬编码色、`<script>` 均生效；宿主主题与 `localStorage` 不受影响；板内脚本对写端点的调用**得到 403**（4.7），而非仅"读不到响应"。
3. 第二轮共创时 CLI 从 `context/boards/*.html` 读到上一版真实字节，做增量修改（人工核对 diff 行数显著小于整份重写）。
4. 一场会议的两份板各自独立 `revision`，tab 切换、10s 轮询、单节共创、错字回溯、测试任务清理五条链路都按 `board_id` 正确作用；且第二份板**只能**经「＋ 新建板」或"提案被用户接受"出现——没有任何单独的工具调用能建板（`create_insight_board` 只出提案，`revise_insight_board(board_id="新名")` 收到 `unknown_board_id`）。
5. 「在浏览器中打开」出的同源页面里脚本被 `sandbox` CSP 关进 opaque origin，且所见 `rev` 与前端角标一致。
6. `detect_recap_floor` / `detect_text_wall` 对新契约仍有效：纯文字板被拒，用 `<svg>` 或 mermaid 形态 `<pre>` 的板被收（判据以 10.2 的裁定为准）。

---

## 10. 拍板状态

### 10.1 已定（本轮）

| # | 决策 | 已改写本方案的哪些节 |
|---|---|---|
| 1 | `<script>` **放开** | 4.1（`_DROP_TAGS` 定案 + `on*` 保留剥离并如实上报）、4.2（把边界买到什么写准）、**新增 4.7**（Origin 守卫，补上放开脚本后唯一的实际缺口）、4.6 验收、§7 第 2 期回滚（不再有 `v-html` 退路）、§8 前两行风险、§9-1/§9-2 |
| 3 | 多板**仅在用户显式新建时出现** | 6.3（`create_insight_board` 降为 `persists: False` 提案）、6.4（「＋ 新建板」按钮 + 确认卡）、**新增 6.5**（两条通道 + `unknown_board_id` 硬不变量）、6.6 连带清单、§8 第三行风险、§9-4 |

两项决策合起来换来的一条原则值得单独记下：**放开表达权与收紧创建权是同一件事的两面**——版式（含脚本）交给 CLI，"要不要多一份板"这种会改变用户工作区结构的动作收回到用户。这条线以后遇到类似提案（比如 AI 想删板、改板标题）照此判定即可。

### 10.2 待定：主视觉判据放宽到哪一步（4.4）

议题 1、3 已定，这项是唯一还开着的前置问题，且只影响 `detect_text_wall`（`insight_board.py:754`）的判据集合，不阻塞第 1 期。推荐默认值：

| 形态 | 是否计入"主视觉" | 理由 |
|---|---|---|
| `<svg>` / `<canvas>` / mermaid 形态 `<pre>` | **计入** | 真图形，4.4 的桥接方案本就为其服务 |
| `<img>`（仅 data URI） | **计入** | 相对路径的 `<img>` 在 `srcdoc` 与 raw 端点两处出口下解析结果不一致（4.5-4），只认 data URI 与"一律内联"这条硬约束对齐，不是排版意见 |
| `<table>` | **不计入** | 表格是"结构化文字"，把它当图等于把 `detect_text_wall` 的门槛降到形同虚设——模型可用一张八列大表交付整节文字墙 |
| 纯 CSS 画的条形/环形（`div` + `width:%`） | **不计入** | 无法与装饰性布局可靠区分，判据一旦要靠猜就该删 |

否决代价参考：想让表格算图，就同时给 `detect_text_wall` 加"表内文字密度上限"，否则 §9-6 的验收失去意义；想让相对路径的 `<img>` 也算图，得先决定两处出口（`srcdoc` / raw 端点）用哪一个 base URL 语义，并把它写进 4.5-4 的实测结论。

### 10.3 下一步

第 1 期（R2：板 HTML 进 `context/` + `expected_revision`）不受任何未决项影响，可直接出具体 diff 计划：`core/cli_engine/context_export.py` 的导出步骤、`core/insight_board.py` 的参数与错误分支、`catalog.py:207-257` 的工具描述、`tests/` 的夹具。10.2 定了之后再排第 2 期（R1 + 4.7）。
