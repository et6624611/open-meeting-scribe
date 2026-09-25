# AM-F1 完工回报（接入方式三卡片 · 前端）

> 派工单：AM-F1（基于 docs/REQUIREMENT-ACCESS-MODE-CARDS.md v0.1.0，§3 R1/R2/R4，§6 AC-T3/T4/T5）
> 会话：1659366c · 岗位：前端开发工程师 · 回报时间：2026-09-25

## 状态

**已完成并推送分支，等待产品验收合入（未合 main）**

- 分支：`feat/req-access-mode-f1`（已 rebase 至 origin/main@bd7db48，已推送 origin）
- Commit：`89ae37e` — feat(access-cards): AM-F1 接入方式三卡片前端落地（10 files，+913/−107）
- ⚠️ rebase 义务说明：截至本回报 **REQ-PROGRESS-P0 尚未合入 main**（tracker 10:00 巡检：P0 转等推送回报）。
  当前已 rebase 至最新 main（bd7db48）且构建全绿；**P0 合入后、验收前将补一次 rebase + 全绿构建**并更新本回报证据。

## 范围落地对照

| 项 | 实现 |
|---|---|
| T3 三卡片 | 新组件 `frontend/src/components/settings/AccessModeCards.vue`：离线/托管/自带 Key，每卡一行「算力·花费·数据去向」三维描述（R1）；离线选中 → 服务区块灰化 + 「由离线模式接管」徽章（R2）；声纹并入卡片折叠区（D3），主视图不再单列「声纹服务」 |
| T3 高级设置 | LLM/ASR/声纹底层参数仅在专家模式开启时于「高级设置」折叠区可编辑；`access_mode`/`expert_mode` 读写按 AM-B1 契约（API_CONTRACTS §13）mock 先行 |
| T4 引导 | 未登录/未配置用户设置首屏 = 引导头（「选择一个接入方式」）+ 三卡片；专家模式开关置于高级设置内（D4），开启恢复账户/服务/计算引擎旧分类，关闭回落新分类并自动跳回接入方式视图 |
| T5 状态栏 | footer.status 主文案只留「结论+原因+动作」：`离线就绪 / 离线未就绪 · 本地模型未安装 / 托管就绪（剩余 4h40m）/ 还需登录 / 自带 Key 就绪`；模型串与 API 延迟移入 hover title；EngineBadge 与 footer 均跳 `/settings?cat=access`（A3） |
| T5 单一源 | 状态推导收敛到 `frontend/src/stores/engine.ts`（statusState/statusDetail/routeOverride 等），App.vue / EngineBadge / AccessModeCards 只消费；`frontend/src/api/access.ts` 镜像 §13 契约：真实端点 200 优先并清影子态、404 回退本地推导 ⇒ **后端合入后零代码切换**；A2 兼容窗口旧字段双写 |
| D2 toast | 托管额度路由切换显性告知，sessionStorage 判重「一次且仅一次」；文案覆盖 prefer_subscription / byok_key_missing / cloud_unavailable / legacy_unconfigured 四类 reason |
| 边界遵守 | 未改任何后端 py 文件；未动 core/pipeline.py；文案中文优先、en 双语同步补齐；主工作区 data/settings.json 未触碰（自测全程 mock 拦截写请求） |

## 自测证据（qa-evidence/req-access-mode-f1/，未入库）

Playwright 有状态 mock（模拟 AM-B1 未合入窗口）全链路断言，`ALL SELF-TEST ASSERTIONS PASSED`（见 selftest-run.log）：

- ① 三卡片选择→持久化链：`e1-01_select_hosted.png` → 刷新后仍选中托管 `e1-02_hosted_persisted_after_reload.png`
- ② 离线选中服务区块灰化+接管徽章：`e2_services_takeover_gray.png`
- ③ 专家模式开/关两态：`e3a_expert_on_old_categories.png`（账户/服务/计算引擎回归）、`e3a2_expert_services_view.png`、`e3b_expert_off.png`
- ④ 两处状态入口同参跳转：`e4a_footer_jump_cat_access.png`、`e4b_badge_jump_cat_access.png`（均落 `/settings?cat=access`）
- ⑤ 构建全绿：`e5_npm_build.log`（`vue-tsc -b && vite build`，exit=0，rebase 后重跑）
- AC 补充：`AC-T4-01_guide_onboarding.png`（引导头+未配置文案）、`AC-T5-01_local_ready_status.png`（离线就绪）、`AC-T5-02_hosted_ready_remaining.png`（托管剩余 n）、`AC-T5-03_d2_route_override_toast.png`（D2 toast，reload 后判重复验通过）

## 浏览器验收包（硬性交付物）

- **页面路径**：设置 → 接入方式（`/settings` 或 `/settings?cat=access`）；底部状态栏；顶栏引擎徽章
- **非技术五步验证**：
  1. 打开设置页：首屏看到「选择一个接入方式」引导 + 三张卡片，每张卡一行写清「算力/花费/数据」；
  2. 点「离线模式」：下方「服务配置」变灰并带「由离线模式接管」徽章；再点「托管模式」恢复；
  3. 展开「高级设置」，拨动「专家模式」开→关：左侧「账户/服务/计算引擎」分类出现→消失；
  4. 点底部状态栏文字、再点右上角引擎徽章：两者都跳到「接入方式」设置页；状态栏主文案只有一句话（结论+原因），鼠标悬停才看到模型与延迟明细；
  5. 选「自带 Key」并开启「优先使用订阅流量」后回首页：弹一次「路由切换…走平台额度」提示，刷新页面不再重复弹。
- **通过标准**：上述 5 步全部符合预期即验收通过。
- **对照截图**：qa-evidence/req-access-mode-f1/（同上清单）
- **环境说明**：AM-B1 后端未合入，以上演示走前端 mock 通道（本机 vite 5199 + 拦截层）；后端合入后同一交互零代码切换。若验收时 AM-B1 已合入，请直接对真实后端复验。

## 残留风险

1. P0 合入后需补 rebase（nav/status 区域有交集，冲突概率低但非零）——已列为验收前置动作。
2. mock 推导（`deriveLegacyAccess/Expert`）与 AM-B1 后端惰性迁移表若出现语义偏差，联调窗口以真实端点 200 响应为准自动覆盖，风险可控。
3. 自测中「离线未就绪」场景点卡片会触发引擎启动尝试（mock 返回成功弹出「本地引擎已启动」toast）；真实后端会按 models_missing 拒绝，属 mock 环境噪音，不影响验收口径。
