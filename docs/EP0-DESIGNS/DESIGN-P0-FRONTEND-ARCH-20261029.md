# 企业版 P0 前端架构设计（单实例多用户）

- 作者：前端开发工程师
- 日期：2026-10-29
- 对应派工：cmsg_01m63fh4xpe75d04t20w12sge2
- 设计前提（项目方已裁决）：双产品线、内网私有化、仅定稿文本上服务端、存量数据归手机账号 13373013103、管理员建号/邀请码

---

## 一、现状盘点（代码实况，非推测）

| 事实 | 位置 | 对 P0 的含义 |
|---|---|---|
| 技术栈 Vue 3 + Pinia + vue-router + axios + i18n，无 headless UI | frontend/ | 改造沿用现有栈，无新增依赖 |
| axios 单实例、相对 baseURL、JWT httpOnly cookie 会话 | src/api/client.ts | 双 origin 改造的唯一收口点 |
| 已有 auth 封装：/auth/me、SMS、GitHub OAuth、probeSession、role=admin 判定 | src/api/auth.ts、src/stores/user.ts:21 | 登录态基础设施可复用；缺账号密码登录端点与登录页 |
| 12 条路由，**无任何路由守卫**，无独立登录页 | src/router/index.ts | requiresAuth 体系需新建 |
| WebSocket URL 由 `location.host` 拼接，同源假设；每 taskId 一连接但 composable 内单实例闭包 | src/composables/useWebSocket.ts:121-125 | 跨 origin 连本地引擎需重构地址注入与鉴权方式 |
| 录音控制 `/api/record/start|stop|pause|status` 无 user/task 维度，status 返回全局单例状态 | src/api/record.ts | 多用户并发录音的结构性阻塞，等后端契约 |
| Pinia 11 个 store，其中 task/realtime/engine/player/aiSessions 为全局单任务/单用户假设 | src/stores/ | 去单例化改造主战场 |
| 24 个文件使用 localStorage（主题、i18n、未读、缓存…），key 无用户命名空间 | 全仓 grep | 多用户切换状态泄漏风险点 |
| api 模块 26 个文件，全部走同一 client | src/api/ | 需要一张"数据面归属表"逐模块划分 local/server |

## 二、双 origin client 层封装方案

**概念**：P0 前端第一次面对两个后端——
- **本地控制面（local origin）**：员工电脑上的本地引擎服务（录音采集、实时转写流、引擎状态、本地数据目录），地址形如 `http://127.0.0.1:<port>`；
- **服务端数据面（server origin）**：内网服务器（账号、定稿文本业务数据：任务/纪要/决策流/笔记/热词、管理台）。

**方案**：
1. 新增 `src/api/origins.ts`（OriginRegistry）：持有 `{ local: URL, server: URL }`。server origin = 页面 origin（用户浏览器访问的 Web 地址）；local origin = 默认探测 `127.0.0.1` 常用端口 + 用户在设置页手动配置，配置按 user_id 命名空间存 localStorage。
2. `client.ts` 改为工厂 `createClient(origin)`：请求拦截保留现有 Accept-Language/401 逻辑，按 origin 分别处理（server 走 cookie 会话；local 走设备配对短期 token——鉴权模型为后端契约阻塞项，见 §五）。过渡期保留默认导出，api 模块逐个改标注归属，降低一次性风险。
3. `useWebSocket.ts`：URL 构造从 `location.host` 改为 OriginRegistry 取值；task 维度连接保留现状（已按 taskId 建连，是好消息）；鉴权方式（cookie vs query token）随契约定稿。
4. CORS/CSP：本地控制面仅允许 `http://127.0.0.1` 与部署页 origin 两个来源；服务端需 `SameSite` cookie 策略配合内网 HTTPS（DevOps 的 CA 方案影响此项：若内网走 http，WS 为 `ws:` 可用但 cookie 会话安全性下降，需 QA 验收口径覆盖）。

## 三、登录与用户空间（管理员建号模式交互流）

**用户视角主线**：
- 员工：打开内网地址 → 看到登录页（账号+密码，无短信/第三方登录）→ 首次登录强制改初始密码 → 进入现有工作台（界面不变，只多了右上角身份菜单）。
- 管理员：登录后额外看到"管理台"入口 → 建号（姓名/账号/初始密码或邀请码）、重置密码、启停服务开关。

**前端实现**：
1. 新增 `LoginPage (/login)` + 路由守卫 `meta.requiresAuth` + `beforeEach`（现无守卫体系，全部路由纳入）；企业形态 `REQUIRE_AUTH` 常开，`probeSession` 的匿名分支在 enterprise build 下禁用。
2. `api/auth.ts` 增加账号密码登录/首改密码端点封装（契约待后端）。
3. 用户空间 = 现有 layout 顶部菜单（displayName/avatarLetter 已有），加登出；登出时必须清空当前 user 命名空间下全部 localStorage 与 Pinia 态（防泄漏门禁，QA 用例对齐）。
4. 管理台 MVP：`/admin`（仅 isAdmin），信息架构与 UI 设计师的规格对齐；前端按"用户列表 + 建号表单 + 服务开关"三区块预留。
5. 双产品线打包：企业形态用 build flag（VITE_EDITION=enterprise）隐藏 SMS/GitHub 登录入口与"云引擎"相关引导文案，个人版行为零变化。

## 四、API/WS 去单例化改造清单与排序

排序原则：先安全边界 → 再数据维度 → 再并发形态 → 最后新增页面。每档可独立交付验证。

| # | 改造项 | 涉及面 | 档位 | 依赖 |
|---|---|---|---|---|
| 1 | 路由守卫 + 登录页 + 登出清态（含 localStorage 用户命名空间化，24 文件统一走 helper） | router、user store、storage util | S | 后端登录端点 |
| 2 | OriginRegistry + axios 工厂双 client；26 个 api 模块按归属表打标 | src/api/* | M | 后端/DevOps 定 local/server 归属 |
| 3 | task store 去单例：列表/未读/当前任务按服务端 user 维度过滤（后端过滤，前端不复制权限逻辑） | stores/task.ts、DecisionCenter 等消费方 | M | 后端数据层 user_id |
| 4 | 录音状态 per-task 化：`/api/record/status` 全局单例 → per-task；RecordingView/StartView"正在录音"指示改多任务形态 | api/record.ts、useWebSocket、录音相关视图 | M | **后端多用户录音契约（硬阻塞）** |
| 5 | engine store 归位本地控制面：引擎状态=device 属性而非 user 属性，接设备配对 token | stores/engine.ts | S+M | 后端设备绑定契约 |
| 6 | 管理台 /admin 页面组 | 新视图 + api/admin.ts | M | 后端用户管理 CRUD 契约 |
| 7 | 数据目录设置页 + 数据位置指示 + 上传知情同意交互（Settings 分区，与 UI 规格同步） | SettingsView 区 | M | UI 规格 + 后端契约 |

估算：契约齐备后前端 ≈ 2–3 周单人；契约等待期可用 mock 驱动先行（沿用团队"契约先行 + mock"工作规范）。

## 五、待产品经理裁决的产品问题

1. **登录方式收敛**：企业版是否彻底隐藏 SMS/GitHub OAuth 入口？（建议：彻底隐藏，避免两套账号体系混淆与合规复杂度。）
2. **首次登录强制改密**：管理员建号下发的初始密码，是否强制首登修改？（建议：是。）
3. **本地引擎分发形态**：员工电脑需要一个"本地录音服务"在跑。是随浏览器引导页提供下载、还是 IT 预装？这决定设置页"设备绑定"流程怎么设计——需与 DevOps 交付物设计合并拍板。
4. **管理入口分工**：DevOps 的初始化向导与产品内管理台的边界（建议：向导只产首个管理员账号，日常用户管理全部在产品内 /admin）。
5. **上传知情同意粒度**：每次会议单独确认，还是全局开关 + 例外覆盖？影响 §四-7 交互设计，需与 UI 规格、后端"定稿文本上传"契约三方对齐。

## 六、对后端的契约请求（优先级从高到低）

1. 录音控制面多用户契约：start/stop/status per-task、WS 连接鉴权与归属校验（对应后端派工中"录音控制面留本地的服务端接口边界"）；
2. 账号密码登录 + 首改密码 + 登出端点；
3. 用户管理 CRUD（管理台用）；
4. 数据面归属表：26 个 api 模块逐项 server/local 标注（后端派工中的 API 契约草案建议附带）;
5. 设备配对 token 模型（浏览器页面 ↔ 本机引擎的互信建立）。
