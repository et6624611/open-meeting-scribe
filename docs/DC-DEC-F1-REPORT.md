# DC-DEC-F1 完工回报（兜档）

> 主通道（`qoderwake messages send` 群回报）报错：`This Waker Session has no complete Conversation Run sending identity; no message was sent.`
> 已按派工补充条款改走兜底通道：`qoderwake session send --session-id eaf4b142-5230-4284-9f08-d749f5608689`（成功，event_id `console-submit:controller-user:c1d3e28d-2b18-48e8-a16d-f7eff1aaad7c`，2026-09-25）。
> 本文件为该次回报的等义存档，随分支入库供验收对照。

## 状态

**已完成并推送分支，等待产品验收合入（未合 main）**

- 分支：`feat/req-decision-center-f1`（基于 main@bf875ff，已推送 origin）
- Commit：`86c33fd` — feat(decision-center): REQ-DECISION-CENTER R3 前端（19 files，+1463/−15）

## 范围落地对照（PRD §4 R3）

| 项 | 实现 |
|---|---|
| 新路由 + 主导航入口 | `/decisions` + ActivityRail「决策中心」 |
| 列表 | 会议日期倒序；按会议分组折叠 / 平铺切换 |
| 筛选 | 时间（近7天/30天/全部）、知识库、状态（默认仅生效中+待确认，待确认默认可见带角标）、关键词（300ms 防抖） |
| 决策卡片 | 文本 + 来源会议跳转（纪要页锚点高亮）+ 日期 + 状态徽标 |
| superseded 沉底 | 折叠区显示「已被〈新决策〉取代」链接；悬空引用降级文案（AC-6 前端部分） |
| 行内操作 | 标记已被取代（检索弹层）/ 已撤销；手动补录入口 |
| 单会议 Tab | 「决策」→「行动项」（AC-9），面板顶部只读决策区 + 去决策中心链接 |
| 视觉 | 复用 DecisionNode.vue 样式基元（.db-node/.db-dot/.db-flow 等） |
| 三态 | 骨架加载 / 空态分流（全局空 vs 筛选无结果）/ 错误重试 |
| i18n | vue-i18n 双语全量键（zh-CN / en） |
| Mock | DEV + `VITE_DECISIONS_MOCK=1` 门控，生产零 mock；联调切换零代码改动 |

## 自测证据（qa-evidence/，未入库）

- dc-f1-01~04：默认分组视图、时间/知识库/状态筛选组合、未关联知识库、平铺
- dc-f1-05~08：卡片菜单、取代检索弹层、检索命中、取代后沉底 + 悬空降级
- dc-f1-09~10：列表状态核对、取代链接
- dc-f1-11/12：补录弹层（296 会议选项）+ 提交成功
- dc-f1-13：来源会议锚点跳转，textarea 选区 329–348 精确命中决策原文
- dc-f1-14：「行动项」Tab + 只读决策区 + 去决策中心链接
- dc-f1-15/16/17/18：筛选空态、加载骨架、英文语言包、撤销 toast

## 验证

- `vue-tsc -b && vite build` 全绿
- 新增/修改文件 eslint 0 error
- 浏览器实测全链路（headless Chrome + Vite dev 5174，mock 通道）

## 修复的缺陷（自测中发现）

真实数据 184/298 条已完成任务缺 `meeting_date`/`created_at`，导致补录下拉 computed 内 `created_at.slice` 抛 TypeError、选项列表静默为空——改可选链防御并包裹 mock 注册链路。

## 残留风险

1. GeneratingView 存在 2 个 main 既有 `require-button-label` lint error，未纳入本单范围。
2. 与 DC-DEC-B1 联调窗口未开，真实 `GET /api/decisions` 响应形状待联调复核。
3. mock 数据为会话内存态，页面刷新即重置（仅影响演示链路）。

## 追加：B1 §12 契约对齐（2026-09-25，commit `d181ed2`）

B1 契约交付后（`docs/API_CONTRACTS.md` §12 @ origin/feat/req-decision-center-b1@7e1a328）完成对接：

1. `status` 为单值精确过滤（逗号多值 422）→ 新增 `fetchDecisionsMulti`：按值并行拆分请求、`task_id:id` 去重、维持 `meeting_date` 倒序（无日期沉底）。
2. 聚合行字段对齐契约：`task_title→title`、`project_id→kb_id`、`project_name→kb_name`；`task_deleted` 降为 mock 专属可选扩展（真实契约不返回已删任务决策）。
3. `__none__`（未关联知识库）为前端伪值：不下发 `kb_id`（契约该过滤会排除未关联任务），改客户端过滤 `!kb_id`。
4. 补录 `text` 1..2000 前置校验（对齐 422），新增双语键 `add_text_too_long`。
5. `group_by` 不下发，分组维持前端实现；CRUD/`supersede` 端点与响应包络与 §12.1 一致，无改动。

验证：`vue-tsc -b && vite build` 全绿；mock 浏览器回归通过（默认 6 卡 / 多状态 8 卡+沉底折叠 / 未关联知识库筛选正确），证据 `qa-evidence/dc-f1-19-contract-align-regression.png`。

回报通道：主通道 `messages send` 仍报 `no complete Conversation Run sending identity`，走 `session send` 兜底成功（event_id `856cf43d-a0c7-48bb-bb67-facb97bfdafd`）。RF-1 追加 commit 仅影响数据产生侧，§12 契约不变，前端无需再改；真实 `/api/decisions` 端到端联调待 B1 合入 main 后进行。

## 追加：B1 合入 main 后转真实接口 + RF-F1 加粗剥除（2026-09-25）

前置：merge origin/main（含 B1 squash `586d141` 与 tracker `07d83f7`）至本分支，merge commit `d22dd9b`，无冲突。

### RF-F1 展示层剥除（按修复单口径：纯展示 helper / dq 保留原文 / 后端数据不回改）

- 新增 `frontend/src/utils/decisionText.ts` → `stripDecisionEmphasis`：仅剥除**成对** `**…**` / `__…__`（单星号/下划线不动，避免误伤 snake_case 与乘号）。
- 三个渲染面接入：`DecisionCard`（卡片正文 + title + 截断，取代链接文本经 pool 同源剥除）、`SupersedeDialog`（候选展示剥除；检索同时命中原始与剥除文本，所见即可搜）、`DecisionFlowPanel`（行动项 Tab 只读决策区）。
- dq 跳转参数保留原始 text：摘要 markdown 本身含 `**`，原文匹配才命中锚点。

### mock → 真实 API

- 前端 dev（5174）去掉 `VITE_DECISIONS_MOCK`，全链路走真实 `GET /api/decisions` + 任务级 CRUD；后端 :8000 重启为 main@07d83f7 代码。契约 §12 无字段改动，前端零修改切换。
- 前端不做去重（后端 RF-1 已按首次出现保序去重），实测 359 条无重复卡。

### 真实后端冒烟（交付标准 · 2026-09-25，qa-evidence/ 未入库）

- dc-f1-20：真实数据总览（359 decisions、分组、Pending 徽标、知识库沉底正常）
- dc-f1-21：**含 `**中间表作为统一数据中转层**` 的 backfill 决策卡片按纯文本渲染**（243/359 条原文含强调符号，DOM 全文 `**` 计数=0）
- dc-f1-22：UI 补录两条含 `**`/`__` 的测试决策，创建成功且展示剥除（POST 200）
- dc-f1-23：取代链路（PATCH …/supersede 200，回读 status=superseded + superseded_by 指向正确；卡片沉底折叠区显示 Superseded 徽标 + 取代链接）
- dc-f1-24：撤销链路（PATCH status=revoked 200 回读确认）
- dc-f1-25：真实 `q` 检索（「中间表」命中 6 卡，无星号泄漏）
- dc-f1-26：来源会议锚点跳转，dq 携带原始含 `**` 文本，textarea 选区 325–431 精确命中摘要原文行
- dc-f1-27：行动项 Tab 只读决策区 12 条全部剥除展示
- 冒烟产生的两条临时决策已 DELETE 清理（回读 remaining=0），真实数据无残留。

### 验证与残留

- `vue-tsc -b && vite build` 全绿；改动文件 eslint 0 error。
- 观察项（非本单缺陷）：真实后端 `GET /api/decisions` 全量首拉 ~5s（慢请求告警 5011ms/6080ms），前端骨架屏已覆盖等待态；如后续量级增长建议后端加缓存或分页，属 B 侧议题。

## 追加：首轮验收修复轮（2026-09-25，验收单要求含反引号剥除）

- 合入 origin/main 最新 `07d83f7`（仅差 1 个 tracker 文档提交；采用 merge 而非 rebase——分支已推送且处于验收流，rebase 需 force-push 重写远端历史，风险大于收益，内容等价）。
- `stripDecisionEmphasis` 按验收口径扩展：新增成对反引号 `` `x` `` 剥除，置于 `**`/`__` 之后以支持 `**\`x\`**` 嵌套；单星/单下划线/无配对反引号不动（snake_case、乘法记号安全）。用例：`**粗体**文本→粗体文本`、``含 `code` 反引号→含 code 反引号``、`**嵌套 \`内联码\` 剥除**→嵌套 内联码 剥除`、`snake_case 不动`、`a*b 不动`。
- 真实后端复拍（非 mock）：dc-f1-28 总览 359 卡、dc-f1-29 含 `**` 原文卡片纯文本渲染、dc-f1-30 dq 跳转 textarea 选区 325–431 仍精确命中纪要原文行（dq 保留原始含符号文本，符合验收要求）。DOM 全文 `**`=0、反引号=0。
- 真实数据 359 条中反引号 0 命中，属防御性剥除；`vue-tsc -b && vite build` 全绿。
