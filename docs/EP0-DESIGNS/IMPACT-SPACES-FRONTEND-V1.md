# P1 团队空间 · 前端视图层影响面清单 v1（2026-11-02）

产出人：前端开发工程师｜依据：R-001 裁决 v0.2 定稿（两层空间/自由组合团队/三档角色/决策→企业资产只收集不消费/录音逐字稿永不进团队空间）+ main @ 82f4890 实读盘点。
状态：影响面清单（派工①）；改造方案待 UI 交互规格 + 后端权限契约定稿后出（派工②）。

## A. 空间上下文基础设施（全新增）

| 面 | 现状 | P1 影响 |
|---|---|---|
| `src/api/context.ts:11` | `Visibility = 'personal'` 单值联合，注释已留"P1 扩展时此处加枚举" | 扩展为多值（team 档 + 决策企业档）；**对外文案不得出现"企业空间"字样（QA 红线，即 FAIL）**，枚举命名以后端契约为准、展示文案以 UI 规格为准 |
| 服务端资产查询 | `GET /api/v1/context/tasks` 恒"本人 owner"单源 | 需空间维度参数（team_id/scope 形态等后端契约）；新增团队 CRUD/成员/ACL 客户端（仿 `enterpriseAuth.ts` 建 `teams.ts`，错误码走 `authErrorCode` 同构信封） |
| 空间状态单点 | 无空间概念；用户切换单点=origins.ts `setActiveUser` | 新增 Pinia space store（当前空间、团队列表、我的角色）；**空间切换=全部服务端请求上下文的失效边界**，复用 setActiveUser 单点切换模式；`stores/contexts.ts` 列表缓存键必须含空间 id，防切换串数据 |

## B. 需要加空间上下文的视图

1. **ContextsView.vue**（/library 企业形态）——空间切换主落点：私有=现内容，团队=该团队公开内容；卡片 VisibilityBadge 已挂，随三态自动生效。
2. **ContextDetailView.vue**——双权限态（团队档"只读/可编辑"ACL 驱动编辑面启用与否）+ "公开到团队/撤回"动作按钮 + 改动留痕展示；原文 Tab 只读纪律不变。
3. **EnterpriseAssetsView.vue**（热词/发言人只读窗口）——`visibility` 本地类型硬编码 `'personal'`（33-35 行 4 处 as 断言），Visibility 扩枚举后 vue-tsc 必拦，**同批必改**；数据源从个人资产键改团队资产键（热词/发言人=全团队共享一份，v0.1 定稿）。
4. **DecisionCenterView.vue + decisions/ 目录**——裁决承接点：团队决策视图；解除 P0 `enterpriseRedirect` 门控重建；"团队决策→企业资产"仅收集不消费 ⇒ **此期不做任何企业资产消费界面（汇总/检索/看板均不做）**。
5. **ProjectsView.vue**——解除门控，"项目=团队空间内归集会议纪要/决策"重建；P0 收起的项目/决策面板由此带回（体验线 P-049 方向收口）。
6. **admin/ 管理台**——新增团队管理页（建团队、选人、三档角色设置）；与既有用户管理页的职责分界等 UI 规格。
7. **SettingsView.vue**——若团队空间有空间级设置入口，归属等 UI 规格；档位⑦助手设备配置面不动。
8. **不动面**：Login/Activate/Setup、StartView/RecordingView（企业形态已路由级门控，录音永在助手设备）、GeneratingView、BoardViewerView（归属等规格，默认随 owner 内容走）。

## C. 全局 chrome

- **Sidebar.vue / ActivityRail.vue / TopBar.vue / EnterpriseUserMenu.vue**——空间切换器（私有+多团队）信息架构挂载点；弹出层一律复用 `usePopMenu.ts`（既有纪律）；切换交互与用户菜单的关系等 UI 规格。
- **LockedPrivacyBlock（§7 锁定三行）**——文本不动；若团队空间需要"数据位置"口径增量表述（如"公开到团队的纪要团队可见"），须产品定稿新文案另立区块，禁止改锁定三行。
- **EnterpriseBanner**——现三态不含空间信息，是否承接空间指示等 UI 规格。

## D. 徽标三态改造（单源链路已就位）

改造面就 4 处，链路短：
1. `VisibilityBadge.vue` label 单分支 → visibility→i18n 键映射（is-personal/is-team/is-enterprise 样式钩子 P0 已预置，零新增样式）。
2. `api/context.ts` Visibility 类型扩枚举（编译期强制暴露全部消费分支）。
3. zh/en 双包 `enterprise.json > settings.badge` 增键（**教训条款：动态 i18n 键必须双包核对存在**）。
4. 消费方 ContextsView/ContextDetailView/EnterpriseAssetsView 随类型跟随，其中 3 有硬编码必改（见 B-3）。
徽标"企业档"对用户显示什么字样（如"公司可见"？）=待 UI 规格裁决项①。

## E. 明确不受影响面（红线声明）

- **local plane 全部零变化**：origins.ts 握手/录音链/引擎配置/声纹/sync 队列——音频与逐字稿永不进团队空间，本机助手不感知空间概念。
- **个人版零变化**：P1 全部表面属企业形态，edition.ts 编译期分流，个人版红线不变。
- **W1-04 存储纪律**：空间本地偏好（如"上次所在空间"）一律 `oms.u.<uid>.*` scopedKey 扩展键，登出 purgeUserScopedData 单点不变。

## F. 等两个定稿的依赖项（出改造方案前必需）

| 待输入 | 阻塞的具体决策 |
|---|---|
| UI 交互规格（档①派工） | 空间切换器挂载形态（侧栏分组 vs 顶部下拉）、徽标企业档字样、项目/决策导航归属、管理台团队页信息架构 |
| 后端契约草案（档②派工） | 查询参数键名（team_id/scope）、P0 预留 scope/tenant_id 承接复核结论、决策→企业资产的存储字段（前端只展示留痕，不消费）、改动留痕的响应形态 |

两份定稿到手后 24h 内出改造方案（change 面拆分 + 分批派工建议 + 验收断言对应到 QA 团队维度越权矩阵 A 系扩展）。
