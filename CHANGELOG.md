# CHANGELOG — 迭代日志

> 每版一条，配合 git tag。分类：新增 / 变更 / 决策 / 修复。最新的在最上面。

## [v1.x-remote-config] - 2026-09-06

### 新增
- **远程配置系统**：管理后台可动态管理客户端横幅/公告消息，文案、展示条件、关闭策略均通过后台实时下发，无需发版。
  - `core/remote_config.py` — 消息 CRUD + 过滤逻辑，存储在 `data/remote_config.json`
  - `GET /api/config/announcements` — 客户端拉取当前有效消息（按 target 过滤、priority 排序）
  - `GET /api/config/version` — 配置版本号（增量刷新判断）
  - 管理后台 5 个 API：列表、创建、更新、删除、启用/禁用切换
- **消息管理后台 Tab**：管理后台前端新增「消息管理」标签页，支持消息列表、创建/编辑表单、启用/禁用开关、删除操作。
- **三种关闭策略**：`session`（会话级）、`delayed`（延迟 N 天重现）、`permanent`（永久关闭），替代原有的"关闭即永久消失"逻辑。

### 变更
- **`index.html` 横幅**：从硬编码文案改为远程拉取渲染，横幅内容（文案、按钮、链接）由管理后台动态配置。
- **`app/server.py`**：注册 config 路由模块。
- **`app/routers/admin.py`**：新增消息管理 CRUD 端点。

## [v1.x-cloud-deploy] - 2026-09-06

### 新增
- **云服务器部署**：阿里云轻量应用服务器（2核4G，Ubuntu 24.04，IP: 47.116.10.194），systemd 托管 Web 服务（8000）+ 管理后台（8001），开机自启 + 崩溃自动重启。
- **部署文档**：`docs/DEPLOYMENT.md` 记录服务器信息、端口、SSH、服务管理、代码更新流程、API 调用路径、systemd 配置。
- **部署脚本**：`scripts/deploy.sh` 一键部署脚本（系统依赖 + venv + pip install + systemd + 防火墙）。

### 架构
- 本地开发与云服务器各自独立调用 DashScope API，互不影响
- 代码在哪台机器运行，API 就从哪台机器发出

## [v1.x-voiceprint-cloud-split] - 2026-09-06

### 新增
- **声纹嵌入提取抽象层**（`core/embedding_provider.py`）：定义 `EmbeddingProvider` 接口，三个实现——`LocalCamPlusProvider`（本地 torch）、`CloudEmbeddingProvider`（HTTP 云端，暂不部署）、`MfccFallbackProvider`（14 维 MFCC 零依赖降级）。`get_embedding_provider()` 按 settings.json 配置自动选择，支持环境变量覆盖。
- **声纹配置管理**：`settings.json` 新增 `voiceprint` 配置节（`provider`/`cloud.base_url`/`cloud.api_key`），`GET/POST /api/settings` 已支持读写，API Key 脱敏处理。
- **兼容版本集合**：`COMPATIBLE_VERSIONS` 使本地 `cam++-v1` 与云端 `cam++-v1-cloud` 提取的 embedding 可互相匹配，注册表无需区分来源。

### 变更
- **`core/voiceprint.py`**：`extract_embedding()` 和 `extract_embedding_from_pcm()` 改为通过 provider 抽象层调用；新增 `extract_embedding_local()` 和 `extract_embedding_from_pcm_local()` 封装原始 CAM++ 推理代码，供实时链路直接调用。匹配侧（`match_voiceprint_detail`、`auto_identify_speakers`、`register_voiceprint`、`get_voiceprint_status`）统一改用 `_is_compatible_version()` 做版本兼容检查。
- **`core/diarization.py`**：`_extract_camplus_embedding()` 改为调用 `extract_embedding_from_pcm_local()`，实时链路始终走本地 CAM++，不受 provider 切换影响。
- **`app/routers/settings.py`**：GET/POST 端点新增 voiceprint 配置字段，保存后自动重置 provider 缓存。
- **ADR-0009** 状态从 Proposed → Accepted。

### 架构
- 批处理链路（voiceprint.py）→ provider 抽象层 → 本地/云端/MFCC 三选一
- 实时链路（diarization.py）→ 始终本地 CAM++（延迟敏感，不走 provider）
- 云端服务暂不部署，接口契约已在 ADR-0009 中定义

## [v1.x-admin-panel] - 2026-09-06

### 新增
- **独立管理后台（方案 B）**：同代码库、独立运行入口，与用户端服务完全隔离。管理后台默认监听 `127.0.0.1:8001`，不暴露到公网。
- **启动命令**：`python cli.py admin [--host 127.0.0.1] [--port 8001] [--reload]`，打包后为 `open-meeting-scribe.exe admin`。
- **管理员认证**：独立密码认证（`ADMIN_PASSWORD` 环境变量），独立 JWT cookie（`oms_admin_session`），与用户端 `oms_session` 完全隔离，互不干扰。
- **管理后台 API**（`app/routers/admin.py`）：
  - `POST /api/admin/login` — 管理员登录
  - `GET /api/admin/overview` — 系统概览（用户总数、档位分布、本月用量、最近注册）
  - `GET /api/admin/users` — 用户列表（支持搜索、档位筛选）
  - `GET /api/admin/users/{id}` — 用户详情（含 7 天用量历史）
  - `PUT /api/admin/users/{id}/subscription` — 修改订阅档位
  - `PUT /api/admin/users/{id}/status` — 禁用/启用账号
- **管理后台前端**（`app/admin_static/admin.html`）：单页应用，包含概览仪表盘、用户管理列表、用户详情面板、订阅修改、账号状态控制。
- **新增环境变量** `ADMIN_PASSWORD`（`.env.example` 已同步更新）。

### 架构
- `app/admin_server.py` — 独立 FastAPI 实例，与 `app/server.py` 共享 `core/` 层数据访问，但运行时完全独立。
- `cli.py` 新增 `admin` 子命令，与 `server` 子命令平级。

## [v1.x-sms-send-fix] - 2026-09-06

### 修复
- **短信验证码发送 500 崩溃**：`core/sms.py` 给 `SendSmsVerifyCodeRequest` 传了不存在的参数 `expire_time`（PNVS SDK 正确字段为 `valid_time`，映射到 API 的 `ValidTime`），导致 `TypeError` 在 try 块外抛出、端点返回 HTTP 500 纯文本，前端 `resp.json()` 解析失败误报「网络异常，请检查连接」。修正参数名，并将请求构造移入 try 块，使任何 SDK 异常统一转为 400 JSON。
- **前端错误提示区分**：`app/static/index.html` 新增 `_readSmsJson` 稳健解析响应，服务端返回非 JSON（如 500 纯文本）时降级为带 HTTP 状态码的提示，不再一律误报「网络异常」；发送与核验两处调用点均已切换。
- **回归测试**：`tests/test_smoke.py` 新增 `TestSmsSendHappyPath`，覆盖此前缺失的「有效号码 → 构造请求」关键路径，断言请求携带 `TemplateParam`/`CodeType`/`ValidTime`（秒）且 PNVS 错误返回 400 而非 500。
- **PNVS 发送缺失 TemplateParam 报 400（MissingTemplateParam）**：`SendSmsVerifyCode` 的 `TemplateParam` 为必填，验证码位须用占位符 `##code##`（由 PNVS 动态生成并托管，`CheckSmsVerifyCode` 方可核验），且传占位符时 `CodeType` 必填。新增 `SMS_TEMPLATE_PARAM`/`SMS_CODE_TYPE`/`SMS_CODE_LENGTH` 三个可配置项（同步 `.env.example`）。
- **ValidTime 单位修正**：PNVS 的 `ValidTime` 单位是「秒」（默认 300）而非分钟，上一轮误传 `5`（=5 秒），改为 `SMS_EXPIRE_MINUTES * 60`。
- **模板参数变量不匹配（请检查模板内容与模板参数是否匹配）**：赠送模板 `100001` 含 `${code}` 与 `${min}` 两个变量，上一轮默认只传 `{"code":"##code##"}` 漏了 `min`。默认 `SMS_TEMPLATE_PARAM` 改为 `{"code":"##code##","min":"<有效期分钟>"}`（min 动态同步 `SMS_EXPIRE_MINUTES`）；并在模板类错误时于返回信息附上当前 TemplateParam 与核对指引，便于自助排查。
- **核验恒判失败（验证码错误或已过期）**：`CheckSmsVerifyCode` 的核验结果只在 `Model.VerifyResult`（`PASS`=通过 / `UNKNOWN`=失败），且官方明确 `Code=OK`/`Success=true` 仅代表请求成功。旧代码误读不存在的 `body.pass_`/`body.Pass`，导致发送成功、验证码正确也恒判失败。改为读取 `body.model.verify_result == "PASS"`；新增 `TestSmsCheckVerifyCode` 三个用例覆盖 PASS/UNKNOWN/接口错误。

## [v1.x-sms-login] - 2026-09-06

### 新增
- **手机号短信验证码登录**：接入阿里云短信认证服务 (PNVS)，支持个人账号无需企业资质。新增 `core/sms.py` 封装 `SendSmsVerifyCode` / `CheckSmsVerifyCode` 两个 API，内置 60 秒冷却 + 每天 10 次频率限制。
- **新增端点** `POST /auth/sms/send`（发送验证码）和 `POST /auth/sms/verify`（核验并登录），核验通过后签发 JWT 并设置 httpOnly cookie，与 GitHub OAuth 登录机制完全一致。
- **登录卡片 Tab 化**：前端登录页新增「GitHub / 手机号」双 Tab 切换，手机号 Tab 包含号码输入框、验证码输入框、60 秒倒计时发送按钮、错误提示区域。
- **SMS 用户模型**：`core/users.py` 新增 `find_or_create_sms_user`，用户 `provider="sms"`，`provider_id` 为手机号，默认名称为掩码手机号（如 `133****3103`）。
- **冒烟测试**：`tests/test_smoke.py` 新增 `TestSmsSendValidation` / `TestSmsVerifyValidation` 覆盖手机号格式校验和必填字段验证。

### 变更
- **requirements.txt**：新增 `alibabacloud-dypnsapi20170525` 和 `alibabacloud-tea-openapi` 两个 SDK 包。
- **.env.example**：新增 `ALIBABA_CLOUD_ACCESS_KEY_ID`、`ALIBABA_CLOUD_ACCESS_KEY_SECRET`、`SMS_SIGN_NAME`、`SMS_TEMPLATE_CODE` 四个环境变量说明，同时补全 GitHub OAuth 和 JWT 配置模板。

## [v1.x-metering-ui] - 2026-09-06

### 新增
- **底部状态栏用量指示器**：进度条 + 剩余时长文本，颜色三级编码（绿 >50%、黄 20-50%、红 <20%）。非计量用户自动隐藏。
- **设置页「用量与订阅」面板**：档位徽章、月额度/已用/剩余三栏统计、进度条、最近 30 天用量柱状图（hover 显示详情）。三种状态：计量模式 / 自带 Key 模式 / 未登录。
- **自动刷新**：页面加载（checkAuth 后）、转写完成、录制结束、保存设置后均自动刷新状态栏额度。

### 变更
- **app/static/index.html**：状态栏新增 `#usageIndicator` 区域；设置页账户卡片下方新增用量卡片；JS 新增 `loadUsageSummary` / `loadUsagePanel` / `_renderUsageChart` / `_formatMinutes` 四个函数。

## [v1.x-metering-impl] - 2026-09-06

### 新增
- **用量计量引擎** `core/metering.py`：record_usage（JSONL 追加写入）、get_monthly_usage（按月汇总）、get_daily_history（逐日明细）、check_quota（配额预检）、is_metered（双轨判定）。数据存储在 `data/usage/usage-YYYY-MM.jsonl`。
- **用量查询 API** `app/routers/usage.py`：GET `/api/usage/summary`（状态栏）、GET `/api/usage/history`（图表）、GET `/api/usage/check`（预检）。
- **批量转写计量钩子** `app/store.py`：run_pipeline_task 转写完成后自动记录 audio_duration。
- **实时录制计量钩子** `app/routers/record.py`：stop_record 按录制时长记录用量。
- **配额预检**：录制开始（`/api/record/start`）和文件上传（`/api/transcribe`）前检查配额，额度用尽返回 402。
- **Key 来源标记** `app/store.py`：get_asr_config() 返回 `source` 字段（"platform" | "user"），用于计量判定。
- **订阅管理** `core/users.py`：get_user_subscription / set_user_subscription，新用户默认 tier="free"。

### 变更
- **app/server.py**：注册 usage router（第 13 个路由模块）。
- **app/routers/settings.py**：GET /api/settings 返回 asr.source 字段。

## [v1.x-metering-decision] - 2026-09-06

### 决策
- **USAGE_METERING_DESIGN.md 开放问题已决策**：①实时转写先按录制时长计量；②体验版额度用尽后允许配置自有 Key；③团队版**先扣团队共享池，超出后扣个人额度**（与原建议相反）；④按月度额度处理、跨月清零；⑤v1 不做风控，先观察数据分布。

## [v1.x-doc-sync] - 2026-09-06

### 文档
- **全面复盘代码与文档一致性**：遍历 `core/`、`app/routers/`、`app/server.py`、`app/store.py` 等核心代码，对比所有说明性文档，修正 28 处不同步问题。
- **CODEX.md**：版本号 v0.25 → v1.x；技术栈 resemblyzer → torch/torchaudio(CAM++)；前端行数 6500 → ~14700；diarization.py 描述更新（CAM++ 192维 + VAD）；RealtimeASRClient → RealtimeTranscriber；voiceprint.py/projects.py/users.py 关键函数更新；server.py 行数 <100 → ~210；路由表补充 philosophy.py/auth.py；数据目录补充 uploads/hotword_mappings/voiceprint_registry/users/settings；新增 errors.py/joblog.py/auth.py 模块条目。
- **docs/ARCHITECTURE.md**：分层表新增 10 个模块（实时转写/实时分离/实时总结/说话人/项目/用户/认证/错误处理/路由/共享状态）；依赖列表补充 httpx/python-docx/PyPDF2/PyJWT；明确标注 resemblyzer 已移除。
- **docs/PRD.md**：功能清单从未实现改为已完成（[x]）；声纹姓名化从非目标移除并标记 ✅。
- **MISSION.md**：技术路线从 FunASR/pyannote/WeSpeaker 更新为 DashScope paraformer-v2/CAM++；核心组件选型表全面更新；MVP 清单标记已完成项；当前状态从「原型设计」更新为「v1.x 迭代开发」。
- **MVP_PLAN.md**：目录结构全面更新（新增 15+ 文件/目录）；P3 声纹姓名化从「开发中」改为 ✅ 已完成；WeSpeaker → CAM++。
- **docs/ROADMAP.md**：M1 实时聚类升级标记 ✅；多个迭代计划项去掉「规划中」标签。
- **docs/GLOSSARY.md**：声纹条目从 v3 更新为 v4（CAM++ 192维嵌入）。
- **app/server.py**：头部注释补充安全审计中间件职责；voiceprint 版本 V3 → V4 CAM++。

## [v1.x-sel-toolbar-position-fix] - 2026-09-06

### 修复
- **选中操作条定位异常**：浮动选中操作条（引用到 AI / 改写 / 总结 / 提取待办）在某些场景下 `range.getBoundingClientRect()` 返回零值 rect，导致工具栏被定位到页面左上角 `(8, 8)`。新增 `rangeCount` 安全检查，并在 rect 无效时回退使用 anchor 元素的位置进行定位。

## [v1.x-auth-phase1] - 2026-09-06

### 新增
- **GitHub OAuth 登录**：新增 `core/auth.py`（OAuth 流程 + JWT 管理）和 `app/routers/auth.py`（`/auth/github`、`/auth/callback`、`/auth/me`、`/auth/logout`），支持通过 GitHub 账号登录。
- **JWT 会话管理**：登录后签发 httpOnly cookie（`oms_session`），7 天有效期，前端不直接操作 token。
- **登录界面**：未登录时显示登录遮罩层，登录后在 topbar 显示用户头像和下拉菜单（含退出登录）。
- **用户数据模型升级**：`users.json` 从单用户结构迁移为多用户数组结构（`users[]` + `current_user_id`），支持 OAuth 用户（provider、provider_id、avatar_url 等），旧数据自动迁移。
- **新增依赖**：`PyJWT>=2.8.0`。

### 决策
- 认证架构详见 `docs/adr/0006-认证与订阅架构.md` 和 `docs/AUTH_DESIGN.md`。
- 第一期仅实现 GitHub OAuth，后续扩展 Google 和微信。
- 当前不强制登录（前端检查但后端 API 未加认证中间件），后续逐步添加。

## [v1.x-ai-panel-collapse-fix] - 2026-09-05

### 修复
- **AI 面板折叠/展开布局问题**：折叠时 `conv-canvas-center`（聊天画布）未隐藏，导致内容被挤压到 44px 宽度内造成布局错乱；已将其加入折叠隐藏列表。
- **折叠宽度不稳固**：`.ai.is-collapsed` 缺少 `max-width` 约束，内容可能撑开面板；新增 `max-width: 44px !important` 确保折叠宽度稳定。
- **折叠动画不完整**：过渡效果仅覆盖 `flex-basis`，`min-width` 变化无动画；现已同步添加 `min-width` 过渡。
- **折叠按钮层级不足**：`.ai-toggle` 的 `z-index` 从 10 提升至 20，确保按钮始终可点击。

## [v1.x-speaker-count-fix] - 2026-09-05

### 修复
- **说话人计数修正**：`speaker_count` 原本误用 `len(dialogue)`（对话条目总数），改为从 dialogue 中提取 `speaker_id` 去重集合长度，正确反映实际说话人数。
- **历史数据自动迁移**：`load_tasks_from_disk()` 启动时扫描所有已有任务文件，若 `speaker_count` 与去重说话人数不一致则自动修正并回写磁盘，日志输出修正数量。

## [v1.x-divider-visual-removed] - 2026-09-05

### 变更
- **分隔条移除悬停视觉反馈**：去掉鼠标悬停时分隔线的 accent 色加粗发光、握柄圆点（.divider-grip）、追踪涟漪点（.tracking-dot）、模式标签（.mode-badge）、滚动指示条（.scroll-indicator）、宽度提示（.width-tooltip）等全部装饰效果；分隔条仅保留 1px 静态边框线作为面板分隔，拖拽调整宽度功能不受影响。

## [v1.x-sidebar-filter-collapse] - 2026-09-05

### 新增
- **侧边栏头部增加筛选与折叠按钮**：头部最左侧新增面板折叠按钮（点击收起整个侧边栏，左边缘出现浮动展开按钮可恢复）；「全部折叠」右侧新增「筛选」按钮，点击展开搜索行，支持输入关键词实时过滤时间轴会议列表，并提供「重置」一键清空筛选并关闭搜索行。

## [v1.x-divider-no-collapse] - 2026-09-05

### 变更
- **分隔条取消单击折叠/展开**：左右分隔条从「拖动调宽 / 单击折叠 / 拖动或滚轮滚动」三合一收敛为两合一，单击不再触发任何面板折叠，避免误触。面板显隐统一由顶栏视图切换（全视图 / 资源视图 / 对话视图）承担。
- **移除右侧 AI 面板折叠态**：删除 `ai-collapsed` 窄轨模式（48px 竖排「AI 助手」标签）及配套 CSS、`toggleAiPanel()`、视图切换中的 `expandAiPanel()` 强制展开逻辑；`setView` 去掉已无意义的 `opts.enforce` 参数。≤1200px 断点改为直接隐藏 AI 面板与其分隔条。
- **清理分隔条死代码**：删除 `mode-click` 徽标样式与 `collapse-flash` 闪烁动画、`_toggleCollapse` / `_isCollapsed` / `isAiCollapsed` 及点击判定常量（`CLICK_MAX_MOVEMENT` / `CLICK_MAX_DURATION`）与 `startTime` / `currentX` / `currentY` 状态；`initTripleDivider` 更名为 `initLayoutDividers`。

### 文档
- `docs/design/ui-spec.md`：顶栏「面板切换」改为「视图切换」；§6.1 新增分隔条交互说明并修正 ≤1200px 断点描述。

### 验证
- `node --check` 校验内联脚本语法通过；全文已无 `toggleAiPanel` / `ai-collapsed` / `ai-rail` / `collapse-flash` 残留引用；拖动调宽与滚动联动逻辑保持不变。

## [v1.x-sidebar-header-textbtns] - 2026-09-05

### 变更
- **侧边栏头部改文字式操作按钮**：去掉「全部会议」标题；两个纯图标按钮改为「图标 + 文字」文字式按钮并右对齐。「全部折叠/全部展开」按钮文字与图标随全局折叠态联动切换（展开态显示「全部折叠」+ 内向箭头，全折叠态显示「全部展开」+ 外向箭头）；筛选按钮图标改为三横线式。头部底部加分割线与列表区隔开；筛选浮层下移至分割线下方，不被遮挡。
- **折叠态联动与保持**：手动折叠/展开单个日期组后自动同步全局状态（全组折叠才记为全折叠态并刷新按钮）；历史列表刷新重建日期组后继承全折叠态，折叠状态不再丢失。

### 验证
- 浏览器实测：按钮触发全部折叠/全部展开、手动逐组折叠后按钮自动切换，均正常；console 零报错。

## [v1.x-notes-tab-reload] - 2026-09-05

### 修复
- **录音笔记在会议完成后「笔记」Tab 看不到**：实时录音期间录入的笔记，停止后后端已正确写入 `tasks[].user_notes` 并落盘（`GET /api/tasks/{id}/notes` 实测正常返回），但完成页「笔记」Tab 空白。根因是笔记加载为一次性、无兜底——`loadTaskNotes()` 仅在 `showCompleted()` 中以 fire-and-forget（`async` 未 `await`）方式调用一次，而 `switchGenTab('notes')` 不像待办 Tab 那样重载；该次异步回填一旦遇到 `currentTaskId` 竞态或多会议来回切换未落到输入框，笔记便永久空白。修复：`switchGenTab` 增加 `if (tab === 'notes') loadTaskNotes();`，与待办 Tab（`loadTaskTodos`）对称，每次切入笔记 Tab 都从后端拉取最新 `user_notes`，同时因切换时 `currentTaskId` 已稳定而消除竞态（`app/static/index.html`）。

## [v1.x-breadcrumb-nav] - 2026-09-05

### 新增
- **会议纪要面包屑导航**：工具栏左侧新增进入链路展示，显示用户从何处进入当前会议（全部会议 / 项目 / 说话人），点击上游节点可返回对应视图。支持三种进入方式：侧边栏/库视图（默认"全部会议"）、说话人详情页（显示"说话人 / 姓名"）、项目详情页（显示"项目 / 项目名"）。
- **工具栏按钮布局调整**：复制按钮移至右侧，与导出、全屏并列；左侧仅保留面包屑导航。

### 变更
- 新增 `navCrumbs` 状态变量和 `setNavContext` / `renderBreadcrumb` 函数，在各入口点（`loadTask`、`openTaskFromSpeaker`、侧边栏点击、库视图点击、悬停卡片打开）设置导航上下文。
- 在 `showCompleted`、`showMeetingProcessing`、`showGenError`、`showSpeakerBinding` 中调用 `renderBreadcrumb()` 渲染面包屑。

## [v1.x-toolbar-more-menu] - 2026-09-05

### 变更
- **纪要工具栏按钮精简**：外部可见操作只保留"看"类与"分享"类（复制、导出、全屏），"编辑"类操作（编辑、重新识别）收入"更多"下拉菜单。删除冗余的 `genBtnRetranscribe2` 按钮及其全部 JS 引用。

## [v1.x-tab-memory-fix] - 2026-09-05

### 修复
- **会议 Tab 记忆覆盖生成完成落点（回归）**：按会议记忆 Tab（`meetingTabState`）上线后，任务从「处理中」轮询到 `completed` 时也走记忆恢复，用户在等待期间点过「转写」，纪要生成完毕便停在转写页看不到结果（改造前总是跳「纪要」）。修复：`pollTask` 的 completed 分支先 `delete meetingTabState[currentTaskId]` 再 `showCompleted`，即 Tab 记忆只服务「侧边栏来回切换会议」，不覆盖状态跃迁的自然落点（`app/static/index.html`）。
- **`updateSpkBatchBar` 抛 `TypeError: visibleRows.every is not a function`**：`$$` 是 `document.querySelectorAll` 别名，返回 NodeList，只有 `forEach` 没有 `every`。异常沿 `renderSpeakersManageList` 冒泡到 `loadSpeakers` 的 catch，导致初始化在 `backToSpeakerList()` 前中断（控制台报「加载说话人失败」），且全选框与行勾选状态永不同步、`toggleSpkSelectAll` / `toggleSpkRowSelect` / `clearSpkSelection` 全部抛错。修复：`Array.from($$(...))` 后再 `every`，与文件内既有 `Array.from(palette.querySelectorAll(...))` 写法统一。

### 变更
- `deleteTask` 删除会议时清理 `meetingTabState[taskId]`，避免已删任务的 Tab 记忆残留。

### 验证
- 浏览器实测 13 项全通过：页面加载 console 零报错；说话人页全选→行取消勾选后全选框自动回退 false；会议 A 切「转写」→ 会议 B → 切回 A 仍停在「转写」；模拟轮询 completed 分支后 Tab 由 `transcript` 强制回落 `summary`。
- `node --check` 校验整段内联脚本无语法错误；全文件复查无其他 NodeList 误用数组方法。

## [v1.x-chat-verified-actions] - 2026-09-05

### 修复
- **AI 回复幻觉操作声称**：此前数据修改类请求（如「待办中张玉苗应该是张宇」）没有执行通道，LLM 凭空声称「已修正、纪要已同步更新」，后端从未写入、界面也不刷新。现按 ADR-0008 重构：执行权与叙述权分离，操作结果以系统校验为唯一事实源。

### 新增
- **待办编辑意图解析与执行校验**（`app/routers/chat.py`）：编辑类消息经门槛关键词预过滤后，由低温度 LLM 解析为结构化操作（白名单：待办责任人/内容/完成状态/删除），`_sanitize_edit_ops` 过滤越权操作；`_execute_and_verify_edits` 执行后**回读磁盘逐条校验**，产出带 `verified` 标记的变更清单并写入 joblog。
- **回复事后审计** `_audit_reply_claims`：扫描回复中的操作声称词。有变更 → 回复尾部追加「✅ 系统校验（本轮执行结果，磁盘回读确认）」清单；无变更却含声称 → 追加「⚠️ 系统校验：本轮未执行任何写操作」提示。审计结论由系统生成，不依赖 LLM 自觉。
- **系统提示词「操作权限边界」**：最高优先级规范——AI 无执行权，操作结果只能引用「系统动作执行结果」块，禁止复述待办/纪要全文。
- **界面同步**：`/api/chat` 响应新增 `verified_changes` 字段；前端收到非空变更清单后自动刷新待办 Tab 与本地任务缓存，界面与真实状态一致。

### 变更
- 编辑轮跳过关键词动作检测（避免「待办」关键词误触发 extract_todos 叠加动作）；编辑轮回复不再产出注入候选（避免改写后的待办被当作新待办注入）。

### 验证
- 49 个冒烟测试全部通过（新增 6 个：执行校验、删除校验、无变更、操作白名单、回复审计、端点端到端）

## [v1.x-speaker-locate] - 2026-09-05

### 新增
- **说话人绑定栏「定位」功能**：在"识别说话人"界面（等待绑定态），绑定栏每个已识别说话人新增定位图标（`app/static/index.html`）。点击后自动切到「转写」Tab、滚动到该说话人的第一条发言，并进入聚焦模式——高亮本人全部发言、淡化其他人，便于在多人会议中快速定位指定说话人；再次点击同一说话人取消定位。原有"点击说话人绑定姓名"的交互完全保留（定位图标 `stopPropagation`，不触发绑定下拉）。
- 转写行 `.bt-line` 增加 `data-speaker-id` 属性作为定位检索依据；`renderBindingTranscript` 重渲染时重置定位状态，避免残留高亮。

## [v1.x-diarization-merge] - 2026-09-05

### 修复
- **`SpeakerProfile.avg_feature` 缺失 L2 归一化（过度分裂根因）**：单个 CAM++ 嵌入是 L2 归一化的单位向量，但 `avg_feature` 取均值后不再是。`_match_speaker` 用 `np.dot(feature, avg)` 当余弦相似度，要求双方都是单位向量。未归一化导致点积系统性偏低 → 有效阈值被抬高 → 同一说话人被拆成多个簇。修复：均值后重新 L2 归一化，与 `voiceprint.py::merge_embeddings` 做法统一。
- **方案 C 将 `speaker_count=None` 误判为 <2**：`pipeline.py` 的兜底条件 `speaker_count is None or speaker_count < 2` 将"未知，交给 API 自动估计"的 None 等同于"< 2"并强制替换为 2，对多人会议造成回归（4 人被钉死成 2 人）。修复：仅在 `speaker_count` 明确给出且 < 2 时干预，None 保持透传。
- **CAM++ 嵌入时间漂移导致过度分裂**：实测同说话人相邻窗口余弦 0.79，但跨时段（前 14s vs 后 28s）仅 0.174。贪心聚类用初始帧建立档案后，同说话人后来的嵌入 drifted away 被当成新说话人。新增 `SpeakerDiarizer.finalize()` 后处理合并：录音结束后比较所有簇质心，将余弦相似度 > 0.40 的簇迭代合并。实测 853fa856（46s，真值 2 人）从贪心 6 人降到合并后 2 人，命中真值。

### 新增
- **`SpeakerDiarizer.finalize()` 方法**：执行后处理合并并返回最终说话人数量。录音停止时（`record.py`）和离线估算时（`store.py::estimate_speaker_count`）显式调用，录音期间不触发（避免过早合并正在形成的簇）。
- **谱聚类辅助离线估算**：`estimate_speaker_count()` 新增谱聚类（eigengap 启发式）路径：提取采样片段特征 → 构建余弦相似度矩阵 → 归一化图拉普拉斯 → 特征值 eigengap 自动确定最优 k。与贪心聚类交叉验证，谱聚类信号强时优先采信。轻量实现仅依赖 scipy（不引入 sklearn）。

### 验证
- 43 个冒烟测试全部通过
- 853fa856（46s，真值 2 人）：贪心 6 → 合并 2 ✅
- 03c74e81（700s，多人会议）：贪心 4 → 合并 2

## [v1.x-diarization-upgrade] - 2026-09-05

### 变更
- **实时声纹聚类升级：MFCC 14维 → CAM++ 192维神经声纹**（方案 A）。`core/diarization.py` 的 `extract_speaker_feature()` 优先调用 `voiceprint.extract_embedding_from_pcm()` 提取 CAM++ 嵌入，区分度提升一个量级。CAM++ 不可用时自动降级为 MFCC（向后兼容）。相似度阈值从 0.65 调整为 0.55（适配 192 维空间），特征窗口从 1.5s 增至 2.5s（CAM++ 需要更长的音频段）。
- **VAD 前置过滤**（方案 B）。新增 `_is_speech()` 能量阈值 VAD，RMS < 0.01 或时长 < 0.8s 的音频段跳过特征提取，避免静音段产生噪声聚类。新增 `get_vad_stats()` 调试接口。
- **批处理说话人分离兜底**（方案 C）。`core/pipeline.py` 的 `run_pipeline_stage1()` 中，当音频时长 > 30 秒但估算说话人数量 < 2 时，强制传 `speaker_count=2` 给 DashScope，确保长音频至少尝试 2 人分离。

### 修复
- **说话人未被识别**：根因为 MFCC 14维特征区分度不足 + speaker_count=1 时 DashScope 不做分离。三方案联合修复：CAM++ 提升实时聚类精度 → VAD 减少噪声 → 兜底确保批处理不遗漏。

## [v1.x-camplus-encoder] - 2026-09-04

### 变更
- **声纹编码器升级：resemblyzer GE2E → CAM++**（v3 → v4）。CAM++ 基于 FunASR CAMPPlus 实现（MIT License），权重来自 ModelScope `iic/speech_campplus_sv_zh-cn_16k-common`（28MB，中文语料训练）。嵌入维度 256 → 192（L2 归一化），对中文说话人判别力显著优于英文训练的 GE2E。实现放在 `core/models/cam_plus.py`，自包含、仅依赖 torch + torchaudio，剥离 funasr 重依赖链。
- **注册表加 `model_version` 字段**（当前 `cam++-v1`）。匹配侧自动忽略版本不一致的记录，避免跨 encoder 的不可比向量污染结果；注册侧遇到旧版本记录时强制覆盖（不累积），保证语义一致。
- **匹配算法升级：逐人独立匹配 → per-meeting 统筹分配**。同一会议所有说话人共享录音信道（同一麦克风/线路），embedding 含公共信道分量导致人间相似度偏高。新算法：① 提取所有说话人嵌入后减均值（per-meeting 中心化），消除信道公共分量；② 用匈牙利算法（`scipy.optimize.linear_sum_assignment`）做最优一对一分配，保证不会把两个 ASR 说话人分给同一个注册人。中心化空间中绝对相似度不可比，接受准则改为仅看 margin（最佳与次优的差距）。
- **移除 GE2E 时代的补丁代码**：旧版 cohort centering（减注册表均值）、`RAW_*` / 中心化双阈值、`CENTERING_MIN_SPEAKERS` 等。
- **依赖调整**：`requirements.txt` 移除 `resemblyzer`，新增 `torch` + `torchaudio`；卸载 `funasr`（仅用于参考架构，未实际使用）。

### 修复
- **`register_from_binding` 空路径保护**：`audio_path` 为 None 时返回 `audio_unavailable` 而非崩溃。
- **`extract_embedding` 防御性类型转换**：int16 输入自动转 float32，避免 torchaudio fbank 报错。

### 迁移
- 用 `scripts/backfill_voiceprints.py` 全量重建注册表：10/11 条记录升级到 `cam++-v1`（1 条因源会议音频缺失保留 legacy，下次参与会议时自动覆盖）。

### 文档
- `docs/ARCHITECTURE.md`：声纹层描述更新为 CAM++，依赖列表更新。
- `docs/ROADMAP.md`：新增 v4 · CAM++ 声纹编码器升级 ✅；M1 实时聚类升级改用 CAM++。

## [v1.x-auto-todo-extract] - 2026-09-04

### 修复
- **待办自动提取**：纪要生成后自动从 Markdown 中解析 `- [ ] **负责人**：任务描述（截止日期）` 格式的待办事项，写入 `task["todos"]`。此前纪要虽包含待办章节，但无代码将其解析为结构化数据，导致前端待办 Tab 始终为空。新增 `core/summarize.py::parse_todos_from_summary()`，在 `app/store.py::_run_stage2_for_task()` 纪要完成后调用。支持负责人提取、截止日期提取、去重、跳过已完成项。
- **历史数据回填**：新增 `scripts/backfill_todos.py` 一次性脚本，为修复前已完成的会议纪要回填待办。已为 2 个会议回填 9 条待办（税务研讨会 5 条、预付款讨论 4 条）；1 个会议纪要内容过短无待办可提取。

### 测试
- 新增 `TestParseTodosFromSummary` 6 个冒烟测试（含负责人/截止日期/无负责人/去重/空输入/跳过已完成）。

## [v1.x-joblog-context] - 2026-09-04

### 新增
- **per-task 作业日志层 `core/joblog.py`**：以 task_id 为键的 append-only JSONL（`data/tasks/{id}.joblog.jsonl`），记录录音/转写/声纹匹配/绑定/纪要生成/助手动作的关键操作与运行事件（`ts/stage/level/message/detail`）。作业日志从属于会议纪要，使会议助手能对应到该会议此前发生过的操作与运行痕迹。写入失败静默降级，不打断主链路。
- **会议助手作业日志渐进式上下文（chat 维度 2.5）**：仅当问题涉及操作/运行/流程/故障（`JOBLOG_INTENT_KEYWORDS` 门控，即"某些情况"）才注入；注入分两层——先轻量概要（阶段计数 + 最近事件），再按问题检索相关明细（stage 触发词 + 子串命中，限条数），避免全量日志塞入提示词。

### 变更
- **关键节点埋点**：`app/store.py` 管线 stage1/stage2（开始/完成/重试/失败）、声纹匹配（命中/0 命中降级/异常）、等待手动绑定；`app/routers/speakers.py` 确认绑定（含姓名）；`app/routers/chat.py` 助手动作执行结果（成功/失败）。不记 HTTP 与逐句转写噪声。
- **文档**：`docs/ARCHITECTURE.md` 分层表新增作业日志层并补充从属/渐进式说明；新增 `docs/adr/0007` 记录 per-task 作业日志与渐进式上下文决策。

### 测试
- 新增作业日志写入/读取、概要/检索、渐进式上下文、意图门控 4 个冒烟测试（合计 39 个）。

## [v1.x-voiceprint-cross-meeting-rebuild] - 2026-09-04

### 新增
- **跨会议声纹重建端点 `POST /api/voiceprint/rebuild/{speaker_uuid}`**：人员独立于会议记录——扫描该说话人参与的所有已完成会议（按 `speaker_uuid_mapping` 反查），从每场会议的归一化音频中按其发言时间段提取声纹嵌入，均值融合后整体覆盖注册表（`sample_count` = 参与会议数）。此前说话人详情页「注册/更新声纹」只取发言最长的**单场**会议音频，声纹被绑死在一个录音文件上；现改为聚合全部已绑定会议，抑制单场录音的信道偏置。实测王永亮声纹基于 2 场会议、共 222.6s 发言重建。

### 变更
- **前端「注册/更新声纹」改调重建端点**：删除前端单会议挑选与时间段计算逻辑（约 80 行），聚合逻辑收敛到后端；按钮反馈显示「已基于 N 场会议更新 ✓」。
- **`core/voiceprint.py` 提取复用函数**：新增 `extract_speaker_embedding`（单会议单人嵌入提取）与 `merge_embeddings`（多嵌入均值融合）；`register_from_binding` 改为复用前者，消除重复的截断/拼接逻辑；`register_voiceprint` 新增 `sample_count` 显式入参（重建时一次写入多场样本数）。
- **归一化音频路径推导收敛**：`app/routers/voiceprint.py` 新增 `_resolve_normalized_path`，重建端点与任务级匹配端点共用。
- **测试**：新增跨会议重建聚合、无足够音频 400、说话人不存在 404 三个冒烟测试（合计 35 个）。

## [v1.x-mapping-count-guard] - 2026-09-04

### 修复
- **彻底移除历史会议映射自动绑定说话人**：此前声纹匹配失败后，`loadLatestMappingSuggestion` 会从 `meeting_mappings.json` 取最近一次会议的 speaker_id→姓名映射，按 speaker_id 数值自动补填到当前会议。但 DashScope paraformer-v2 的 speaker_id 按发言顺序/音量分配，跨会议完全不稳定（speaker_id=0 在不同会议中可能是完全不同的人），导致错误绑定（如将"苗文娟"误绑到当前说话人）。现已完全移除 `loadLatestMappingSuggestion` 函数及其调用，说话人绑定仅依赖声纹自动匹配——匹配成功则自动填入，匹配失败则由用户手动绑定，不再使用任何历史数据。

## [v1.x-chat-reparse-actions] - 2026-09-04

### 新增
- **AI 对话支持「重新解析音频」与「重新生成纪要」动作**：在 `ACTION_REGISTRY` 新增 `retranscribe`（关键词：重新解析/重新识别/重新转写/重新处理音频）和 `retry_summary`（关键词：重新生成纪要/重新总结/重新写纪要）两个动作。用户通过右侧 AI 对话框说"那就重新解析音频"即可触发后台重新跑管线，无需手动操作。执行逻辑复用 `run_pipeline_task` / `run_stage2_task`，以 daemon 线程后台运行。

## [v1.x-voiceprint-centering] - 2026-09-04

### 修复
- **声纹通道空转（自动绑定退化为历史映射）**：注册表已有 8 人、resemblyzer 正常工作，但每场会议均 0 命中——被上一版引入的次优优势门槛全部拦下（实测 best=0.915/margin=0.002、best=0.923/margin=0.018 < 0.02）。根因是原始 d-vector 在同一路内录音频上判别力极差：不同人余弦高达 0.970，与同人得分完全重叠，绝对阈值 0.75 形同虚设，放宽门槛即误判、收紧即空转。
- **注册与匹配样本长度不一致**：注册侧截断单人前 180s，匹配侧却拼接全量发言（长会议十余分钟）。d-vector 是全段平均，长度差异让嵌入不可比，同人相似度被显著压低。现两侧共用 `_cap_segments` 与 `MAX_SEC_PER_SPEAKER`，回测 margin 从 0.405~0.836 提升至 0.468~0.819 且自匹配全为 1.000。
- **未命中时相似度被归零**：`voiceprint_match` 中 unmatched 一律记 `similarity: 0.0`，掩盖真实分数，无法判断是"分数不够"还是"提取失败"。现保留真实 best 分数、`margin` 与 `best_candidate`（低置信候选，仅供人工参考）。
- **旧任务声纹匹配接口 400**：`POST /api/voiceprint/tasks/{id}/match` 对重启前创建的任务因缺 `normalized_path` 直接 400。现按命名约定推导归一化音频并回填任务。

### 变更
- **中心化比对（cohort centering）**：匹配前减去注册表均值向量再 L2 归一化。注册表人间最大相似度由 0.970 降至 0.595，本人自匹配 1.000。阈值随空间重标为 `MATCH_THRESHOLD=0.55` / `MIN_MATCH_MARGIN=0.08`；注册人数 < `CENTERING_MIN_SPEAKERS=3` 时均值不可靠，退化为原始余弦并沿用旧阈值（`RAW_MATCH_THRESHOLD=0.75` / `RAW_MIN_MATCH_MARGIN=0.02`）。
- **多样本累积注册**：`register_voiceprint(accumulate=True)` 按样本数加权平均而非整体覆盖，多场会议样本可逐步抵消单场录音的信道偏置，提升跨会议判别力。
- **测试**：新增中心化命中/模糊拒绝、人数不足退化、多样本累积 3 个冒烟测试（合计 32 个）。

### 回测结论
9 人注册表下，三场会议全部已确认绑定的说话人 **100% 命中本人**（e6cda37b 6/6、703ff5db 2/2、ef3f6b76 1/1）；未注册的说话人被正确拒绝（0.316~0.410），无跨人误判。

## [v1.x-ffmpeg-stdin-guard] - 2026-09-04

### 修复
- **SIGTTIN 进程组挂起**：`core/audio.py` 中 5 处 ffmpeg/ffprobe subprocess 调用未重定向 stdin。服务以后台进程组运行时，音频归一化阶段 ffmpeg 读取控制终端触发 SIGTTIN，整个进程组被挂起，表现为页面卡在"正在上传"、API 无响应、进程 STAT=T。现全部显式 `stdin=subprocess.DEVNULL`。
- **watchdog 崩溃循环**：watchdog 启动终端被回收后其 fd 0 失效（revoked），此后每次拉起服务均在解释器 `init_sys_streams` 阶段 EBADF 即死，自愈能力失效且 2 秒一轮空转。启动命令改为 `nohup bash scripts/watchdog.sh >> logs/watchdog.log 2>&1 < /dev/null &`，服务 fd 0 落 `/dev/null`。

### 变更
- **watchdog 自愈增强**（`scripts/watchdog.sh`）：脚本内 `exec </dev/null` 自保险，不再依赖启动命令写法；新增健康检查循环，curl `/` 连续 3 次失败（约 15s）即判定服务"活着但不响应"（挂起等），强杀重启——补齐旧 watchdog 只在进程退出时自愈、无法感知挂起的缺口。

## [v1.x-voiceprint-auto-register] - 2026-09-04

### 修复
- **声纹自动注册闭环**：此前声纹注册表（`data/voiceprint_registry.json`）无自动写入路径（仅说话人详情页手动注册），导致自动匹配永远空命中，绑定页的"自动绑定"实际按 speaker_id 位置复用上次会议映射（跨会议不稳定），产生跨会议身份混淆。现用户点击「确认并生成纪要」后，后台按确认绑定逐人提取声纹注册/更新（`core/voiceprint.py::register_from_binding`），后续会议可真正按声纹特征自动匹配并写入任务上下文（`voiceprint_match` / `voiceprint_auto_mapping`）。

### 变更
- **绑定页建议机制**：改为先声纹自动匹配、上次会议映射仅为未命中且未绑定的说话人补填建议，并明确提示"非声纹确认、需人工核对"；`auto_identify_speakers` 在注册表为空时直接返回，避免对长音频做无意义的嵌入提取。
- **测试**：新增声纹自动注册闭环、空注册表跳过 2 个冒烟测试（注册表临时目录隔离 + mock 嵌入提取，不加载重模型）。

## [v1.x-voiceprint-backfill] - 2026-09-04

### 新增
- **声纹回溯采集脚本**（`scripts/backfill_voiceprints.py`）：扫描已完成且带确认绑定的任务，按绑定从归一化音频补录声纹。首次回溯两场会议共 8 人（郑思、张天雷、任亚单、王永亮、廖书豪、赵沂波、赵里海、沈天雅），注册表自此可用，回测绑定命中 8/8。
- **匹配次优优势门槛**（`MIN_MATCH_MARGIN = 0.02`）：同通道内录音频下不同人余弦相似度实测可达 0.97，仅靠绝对阈值 0.75 会误判；现要求最佳匹配显著优于次优候选才接受，回测中 3 条 0.94~0.96 的跨人误判被拦截。

### 修复
- **normalized_path 持久化**：stage1 完成后写入任务字典（此前仅局部变量），绑定后声纹补录闭环与回溯脚本依赖该字段；旧任务缺失时按命名约定（原文件名 + `_normalized.wav`）推导兜底。
- **注册音频截断**（`max_sec_per_speaker` 默认 180s）：d-vector 在数分钟音频上已稳定，截断避免长会议注册/提取的分钟级 CPU 消耗。

### 测试
- 新增次优优势门槛冒烟测试（两人注册表余弦 ≈0.96，中间查询被拒绝）。

---

## [v1.x-security-audit] - 2026-09-04

### 新增
- **开发阶段安全审计体系**：双层监控，实时中间件 + 离线扫描脚本。
  - **审计中间件**（`app/server.py`）：所有 HTTP 请求记录到 `logs/audit.log`（IP、方法、路径、状态码、耗时）；自动检测可疑行为（路径遍历 `../`、敏感文件探测 `.env/.git/.ssh/.aws`、URL 中泄露的 API Key）并标记告警；4xx/5xx 错误单独记录 WARNING 级别。
  - **离线扫描器**（`scripts/security_audit.py`）：支持扫描 `server.log` 或 `audit.log`，检测 API Key 明文泄露、堆栈暴露、路径遍历、异常访问频率、错误激增等 6 类安全隐患。支持 `--watch` 持续监控模式、`--since 1h` 时间范围过滤、`--file` 指定日志文件。

---

## [v1.x-gen-toolbar-simplify] - 2026-09-04

### 变更
- **会议纪要顶部菜单精简**：移除 gen-toolbar 左侧重复标题（"录音纪要"），工具栏去掉背景色和底边框，视觉降级退至内容之后。操作按钮从 7 个平铺精简为 2 个常驻（编辑、导出与分享）+ 1 个"更多"下拉菜单（复制、全屏、重新生成纪要、重新识别）。下拉菜单支持点击外部关闭。移除冗余的 `genToolbarTitle` 元素，所有标题显示统一由顶部导航栏 `currentTaskTitle` 承担

---

## [v1.x-meeting-date-editable] - 2026-09-04

### 新增
- **支持修改会议纪要日期**：录音文件上传场景下，会议日期默认为上传日期，用户可在详情页点击日期弹出日期选择器修改为实际开会日期。新增 `meeting_date` 字段（`YYYY-MM-DD`），后端 PATCH `/api/tasks/{task_id}` 支持更新；前端所有日期显示位置（左侧列表、悬停卡片、分组逻辑、会议库表格、详情元信息行）统一从 `meeting_date` 读取，兜底 `created_at`。已有任务自动迁移（启动时从 `created_at` 提取日期填充 `meeting_date`）。纪要生成也优先使用 `meeting_date` 作为会议时间

---

## [v1.x-table-squeeze-guard] - 2026-09-04

### 新增
- **全局表格防挤压机制**：表头与数值/时间/状态/操作类单元格永不换行，空间不足时优先压缩弹性文本列（姓名、标题、最近参与，带省略号），极限宽度下容器横向滚动兜底。解决「总发言时长」等长表头在窄窗口下换行、以及 lib-table `overflow: hidden` 裁切内容的问题。统一覆盖说话人、项目、热词、会议库四个数据表格；后续新增表格将其类名加入机制选择器组、并用 `.table-scroll` 包裹即可

---

## [v1.x-fix-event-loop-blocking] - 2026-09-04

### 修复
- **服务卡死根因修复：async def 端点阻塞事件循环**：大量 `async def` 端点内执行同步阻塞 I/O（文件读写、目录遍历、subprocess 状态检查），冻结 asyncio 事件循环导致 WebSocket 断连、HTTP 请求排队、服务表现为「卡死」。按 AGENTS.md 规范将所有含阻塞操作的端点改为 `def`（FastAPI 自动线程池化）：
  - `tasks.py`: `serve_audio`、`download_summary`、`get_task`、`delete_task`、`retranscribe_task`、`retry_summary`、`update_task`
  - `speakers.py`: 全部 9 个端点（CRUD + 映射）
  - `settings.py`: `get_settings`、`save_settings`
  - `hotwords.py`: 全部 4 个端点
  - `notes.py`: 全部 9 个端点（笔记/注入/待办）
  - `user.py`: 全部 3 个端点
  - `projects.py`: 全部 11 个端点（含最严重的 `browse_filesystem` 目录遍历）
  - `chat.py`: `_execute_action` 函数（含录音启动等阻塞操作）

### 预防
- 新增端点时必须遵循 async/sync 边界：含阻塞操作（文件 I/O、subprocess、同步 HTTP）用 `def`；纯异步 I/O 用 `async def`

---

## [v1.x-meeting-menu-restraint] - 2026-09-04

### 决策
- **会议纪要顶部菜单精简**：顶部菜单要克制，更多信息留给内容而不是功能。菜单栏只保留高频、不可缺少的操作，低频功能下沉到右键菜单或设置页。内容区域优先于功能区域——用户打开会议纪要是为了阅读，不是为了点按钮。这是软件的设计范式

### 文档
- `docs/ROADMAP.md` 新增「v1.x 会议纪要顶部菜单精简」迭代计划
- `docs/design/ui-spec.md` 补充「菜单克制、内容优先」设计规范

---

## [v0.41-cleanup-ai-task-control] - 2026-09-04

### 变更
- **清理 AI 任务控制条冗余状态**：移除 `updateAiInputState()` 中"纪要生成中…"的显示逻辑——该状态在 `pending`/`processing`/`awaiting_mapping` 下不一致展示，已失去实际意义；状态统一由 `aiSessionBar` 准确呈现。控制条现仅服务于录音态（录音中/录音已暂停）
- **清理关联死代码**：移除 `stopCurrentTask()` 中处理中分支（实际只输出提示消息，无中断能力）、`.ai-task-control.is-proc` / `.ai-task-stop.is-proc` CSS 规则

## [v0.40-task-failure-handling] - 2026-09-04

### 新增
- **识别任务失败处理机制**：构建三层失败处理体系——① 后端自动重试瞬时错误（网络超时、API 限流等，最多 2 次，用户无感）；② 阶段感知重试：转写成功但纪要失败时，可仅重跑纪要阶段（`POST /api/tasks/{task_id}/retry-summary`），无需重跑耗时的 ASR；③ 前端错误分类展示：按错误类型（瞬时/音频/API配置/未知）给出不同提示和操作按钮，失败态内容区直接嵌入「重新生成纪要」+「重新识别」按钮
- **错误分类模块**（`core/errors.py`）：提供 `is_transient_error()` 判断是否可重试、`classify_error()` 返回错误分类与用户建议
- **任务数据模型扩展**：新增 `failed_stage`（失败阶段）、`error_category`（错误分类）、`error_suggestion`（建议）、`retry_count`（重试次数）字段

### 变更
- **管线自动重试**：`run_pipeline_task` 和 `_run_stage2_for_task` 均加入重试循环，瞬时错误等待 2s/5s 后自动重试，永久错误立即失败
- **前端失败态改造**：`showGenError()` 从接收错误字符串改为接收 task 对象，按 `error_category` 渲染不同图标和文案，按 `failed_stage` 决定显示哪些操作按钮
- **工具栏新增「重新生成纪要」按钮**：仅当纪要阶段失败且转写结果存在时可见

## [v0.39-retranscribe-button] - 2026-09-04

### 新增
- **重新识别按钮**：会议完成页工具栏新增「重新识别」按钮，可对当前录音文件重新执行 ASR 转写管线（归一化 → 上传 → 说话人分离 → 纪要生成），清除旧结果并重新处理。适用于转写质量不佳或热词配置更新后需要重新识别的场景。后端 `POST /api/tasks/{task_id}/retranscribe`，前端按钮在完成态和失败态可见，处理中自动隐藏

## [v0.38-sidebar-user-menu-polish] - 2026-09-04

### 修复
- **管理菜单定位错误（P0）**：`.sb-mgmt-dropdown` 此前以整条侧边栏为定位容器（`bottom: 100%`），展开后菜单底边贴在侧边栏顶部、大部分伸出视口被裁剪。现以 `.sb-user-wrap` 包裹触发器与菜单，菜单锚定在用户行上方 6px 处，展开位置正确

### 变更
- **用户信息入口显性化**：设置用户名的模态框原先只能通过点击小头像进入（隐形功能），现作为「用户信息」菜单项置于管理菜单顶部，头像不再承载点击
- **菜单项语义化**：`mgd-item` 由 `div onclick` 改为 `<button role="menuitem">`，触发器由 `div role=button` 改为真实 `<button>` 并补 `aria-haspopup` / `aria-controls` / `aria-expanded`
- **键盘支持**：Escape 关闭菜单并归还焦点；ArrowDown 从触发器进入菜单，菜单内 ArrowUp/ArrowDown 循环移动焦点（原生 Enter/Space 触发按钮）
- **视觉**：菜单项改为圆角 pill hover（对齐千问参考风格）；当前页菜单项加 2px 品牌色 inset 左条与 hover 区分；chevron 默认向上（提示向上展开）、展开后旋转向下；菜单加 0.12s 上滑入场动效（`prefers-reduced-motion` 全局兜底）
- **清理死代码**：删除顶栏用户区遗留的 `.user-area` / `.user-avatar` / `.user-name` 样式（HTML 已无引用）

## [v0.37-sidebar-event-decoupling] - 2026-09-04

### 变更
- **侧边栏刷新改为事件驱动，解耦任务变更与 UI 刷新**：引入轻量事件总线（`EventTarget` + `CustomEvent`），任务创建/删除/完成/加载处只发 `task-changed` 事件，侧边栏监听事件自动刷新。消除 6 处直接调用 `refreshHistory()` 的耦合点，后续新增任务操作无需关心侧边栏刷新逻辑

### 修复
- **新建会议时左侧列表未及时更新**：录音启动和文件上传成功后未刷新左侧历史列表。通过事件机制自动触发刷新，用户可立即看到新会议条目

---

## [v0.36-fix-stop-record-blocking] - 2026-09-04

### 修复
- **停止录音端点阻塞事件循环导致服务卡死**：`/api/record/stop` 原为 `async def`，内部调用 `stop_recording_with_stream()` 包含 `subprocess.wait(timeout=10)` + `thread.join(timeout=5)` 等阻塞操作，直接卡死 asyncio 事件循环导致整个服务无法响应。改为 `def`（同步端点），FastAPI 自动在线程池中运行，不阻塞事件循环

---

## [v0.35-speaker-count-estimation] - 2026-09-04

### 新增
- **文件上传路径说话人数量自动估算（采样法）**：`estimate_speaker_count()` 重构为均匀采样策略——读取 WAV 文件头计算时长，在 10-30 个均匀分布的时间点各提取 3 秒片段，馈入声纹聚类器估算说话人数。101 分钟音频从数分钟降至 1-3 秒
- **前端上传说话人数手动指定**：拖拽上传区下方新增说话人数下拉选择器（2-10 人或自动估算），用户已知人数时指定可显著提升分离精度

### 变更
- `run_pipeline_task()` 复用估算阶段生成的归一化文件，避免重复 ffmpeg 归一化

---

## [v0.34-sidebar-sync-on-create] - 2026-09-04

### 修复
- **新建会议时左侧列表未及时更新**：录音启动和文件上传成功后未调用 `refreshHistory()`，导致左侧历史列表不显示新创建的会议条目，用户感觉不同步。修复：在 `switchToRecordingView()` 末尾和 `uploadFile()` 上传成功后立即刷新历史列表

---

## [v0.33-fix-history-switch] - 2026-09-04

### 修复
- **切换历史记录时误报「录音文件加载失败」**：`initAudioPlayer` 销毁旧 Audio 实例时设置 `src=''` 会触发 error 事件，导致误弹 Toast。修复方案：移除旧实例的 error 监听器，并在新监听器中校验 src 是否为目标 URL
- **已完成会议显示「纪要生成中…」状态不一致**：`updateAiInputState()` 仅检查 `viewGenerating` 是否可见，未校验任务实际状态。已完成任务也使用 `viewGenerating` 视图，导致误显示生成中状态。修复方案：增加任务状态校验，仅 `pending/processing/awaiting_mapping` 状态才显示生成中

---

## [v0.32-sidebar-asset-p2] - 2026-09-04

### 新增
- **左侧栏资产化 P2**：搜索 + 悬停知识卡片，快速定位与预览会议内容
  - **搜索框**：历史列表顶部新增搜索输入，按标题 / 摘要 / 音频名实时过滤，150ms 防抖；支持一键清除
  - **悬停知识卡片**：鼠标悬停 400ms 弹出浮动卡片，显示完整标题、日期、时长、说话人标签、纪要摘要（最多 4 行）；底部快捷操作支持下载纪要 / 直接打开
  - 卡片智能定位：优先显示在历史项右侧，空间不足时自动切换到左侧或向上偏移

### 变更
- `refreshHistory()` 拆分为数据获取 + `_renderHistoryList()` 渲染两个函数，支持搜索过滤复用
- 缓存 `_allTasks` 全量任务数据，供搜索过滤和悬停卡片共享
- 移除旧的 `.sb-title-tooltip` 简单文本提示，替换为 `.sb-hover-card` 富信息卡片
- **恢复 P0/P1 功能**：时间分组（今天/昨天/本周/更早）、状态视觉权重（左边框色彩）、双行卡片（标题+摘要首句）、元数据条（时长·说话人数·状态·日期）

### 文档
- `docs/ROADMAP.md` 标记 P2 已完成
- `docs/design/ui-spec.md` 补充搜索框与悬停知识卡片规范

---

## [v0.31-sidebar-asset-p1] - 2026-09-04

### 新增
- **左侧栏资产化 P1**：历史卡片从单行升级为双行信息架构
  - **双行卡片**：标题下方显示纪要摘要首句（去除 Markdown 标题前缀），不打开即可获取核心信息；未完成态显示对应状态提示（处理中 / 录音中 / 待绑定 / 失败）
  - **元数据条**：卡片底部展示 `时长 · 说话人数 · 状态 · 日期`，以 `·` 分隔，辅助快速判断

### 变更
- `.sb-history-item` 布局从 `flex row` 改为 `flex column`，新增 `.sb-card-top` / `.sb-card-summary` / `.sb-card-meta` 三个子结构
- `refreshHistory()` 渲染逻辑重构：从 `task.summary` 提取首句、从 `task.audio_duration` / `task.speaker_count` 组装元数据

---

## [v0.30-sidebar-asset] - 2026-09-04

### 新增
- **左侧栏资产化 P0**：历史会议列表从「待办清单」升级为「知识资产」
  - **时间分组**：列表按「今天 / 昨天 / 本周 / 更早」分组，空分组自动隐藏，消灭无尽滚动
  - **状态视觉权重**：非完成态任务通过左边框色彩引导注意力——失败红色、待绑定琥珀色、进行中蓝色脉冲；完成态无边框
  - 纯前端改造，无需后端变更；`refreshHistory()` 按 `created_at` 分组渲染

### 文档
- `docs/ROADMAP.md` 新增「v1.x 左侧栏资产化」迭代计划（P0/P1/P2 分级）
- `docs/design/ui-spec.md` 补充历史列表时间分组与状态视觉权重规范

---

## [v0.29-diarization-accuracy] - 2026-09-04

### 修复
- **说话人分离精度增强（短期四项）**：
  - **S1** `speaker_count` 全链路传递：文件上传端点新增可选 `speaker_count` 表单参数；未传时自动归一化→快速声纹扫描估算（钳制到 1-10），解决上传路径不传 speaker_count 导致 paraformer-v2 盲猜说话人数的问题
  - **S2** 录音路径 speaker_count 钳制保护：实时聚类估算值钳制到 [1, 10]，避免噪声产生过多伪说话人
  - **S3** 放松后处理修正条件：夹心修正间隔 2000ms→800ms，碎片跟前句间隔 2000ms→500ms（新增 `FRAGMENT_SPEAKER_FIX_GAP_MS`），减少真正的说话人切换被误合并
  - **S4** 聚类参数调优：相似度阈值 0.70→0.65（更严格区分音色相近者），特征窗口 2s→1.5s / 步长 1s→0.75s（提升时间分辨率）

### 变更
- `docs/ROADMAP.md` 新增「v3+ 说话人分离精度增强」迭代计划（短期 S1-S4 / 中期 M1-M3 / 长期 L1-L3）

## [v0.28-self-highlight] - 2026-09-04

### 新增
- **转写栏「自己」右对齐对话框样式**：当说话人姓名与当前用户姓名一致时，转写条目以右对齐气泡样式显示
  - 实时转写（`rec-entry`）：`flex-direction: row-reverse` + 淡蓝气泡背景
  - 对话稿（`bt-line`）：`flex-direction: row-reverse` + 淡蓝气泡背景 + 70% 最大宽度
  - 判断逻辑：`_currentUser && label === _currentUser.name`
  - 自动刷新：保存用户姓名、绑定说话人、实时说话人绑定更新时自动刷新高亮

## [v0.27-cli-in-settings] - 2026-09-04

### 新增
- **设置页 CLI 命令参考**：设置页新增「CLI 命令行工具」卡片，展示所有可用 CLI 命令
  - 前端动态加载：`loadCliReference()` 从 `/api/cli-reference` 获取命令列表并渲染
  - 后端新增 `GET /api/cli-reference` 端点，返回结构化 CLI 命令参考（JSON 格式）
  - 便于用户理解 CLI 功能，也便于其他 AI Agent 工具程序化调用

---
## [v0.26-codex-workspace-health] - 2026-09-04

### 新增
- **CODEX.md 渐进式上下文索引**：AI 代理第一入口（124 行），模块速查 + 按任务类型加载路径
  - 替代原「全量加载 README→MISSION→ARCHITECTURE」模式
  - 包含：模块速查表、API 端点概览、硬约束速记、数据目录说明
- **截图归档**：根目录 50 张调试截图移入 `docs/screenshots/{verify,test,debug}/`

### 变更
- `AGENTS.md`：开工先读改为渐进式加载（CODEX.md 优先）
- `README.md`：文档地图新增 AI 入口层
- `.gitignore`：补充运行时数据文件排除（speakers.json、users.json、voiceprint_registry.json 等）

---

## [v0.25-fix-audio-player-binding] - 2026-09-04

### 修复
- **说话人绑定页音频无法播放**：`awaiting_mapping` 状态下点击播放按钮无反应
  - 根因：`showSpeakerBinding()` 未调用 `initAudioPlayer()`，音频元素未初始化
  - 修复：在 `showSpeakerBinding()` 中添加 `initAudioPlayer(currentTaskId)` 调用

---

## [v0.25-voiceprint] - 2026-09-04

### 新增
- **V3 声纹姓名化**：把「说话人1」自动变「张三」
  - `core/voiceprint.py`：声纹提取与匹配引擎
    - 基于 resemblyzer（GE2E 编码器）提取 256 维声纹嵌入向量
    - 声纹注册表持久化（`data/voiceprint_registry.json`），与 `speakers.json` 解耦
    - 余弦相似度匹配（阈值 0.75），支持注册/更新/删除/查询
    - `auto_identify_speakers()`：从归一化音频中按 speaker_id 提取各段声纹，批量匹配注册表
    - 延迟加载编码器，保持服务启动轻量
  - `app/routers/voiceprint.py`：声纹管理 API
    - `GET /api/voiceprint/registry` — 获取声纹注册表（含说话人姓名）
    - `GET /api/voiceprint/status/{uuid}` — 查询指定说话人声纹状态
    - `POST /api/voiceprint/register` — 从音频片段注册声纹
    - `DELETE /api/voiceprint/{uuid}` — 删除声纹
    - `POST /api/voiceprint/tasks/{task_id}/match` — 对任务执行自动声纹匹配
  - **管线集成**（`app/store.py`）：转写完成后自动执行声纹匹配
    - 有匹配结果 → 自动绑定说话人 → 直接进入纪要生成
    - 无匹配 → 降级为手动绑定（向后兼容）
    - 匹配失败不阻塞管线
  - **前端集成**（`app/static/index.html`）：
    - 说话人绑定视图：声纹自动识别状态栏，显示匹配结果与置信度
    - 说话人管理页：列表显示声纹注册状态图标（麦克风）
    - 说话人详情页：新增「注册声纹」/「更新声纹」按钮
    - 自动加载声纹注册表，实时反映注册状态
  - **依赖**：`resemblyzer>=0.1.3`（含 torch、librosa、webrtcvad）

### 决策
- 声纹引擎选 resemblyzer 而非 WeSpeaker：resemblyzer 更轻量，模型加载快（<1s），256 维嵌入足够区分 4-8 人会议
- 声纹注册表独立于 speakers.json：解耦声纹数据与人员档案，支持声纹单独更新不影响人员信息
- 匹配阈值 0.75：平衡误识别与漏识别，可通过 API 参数调整

---

## [v0.25-unified-meeting-page] - 2026-09-04

### 变更
- **说话人绑定页 / 纪要生成页 / 结果页融合为统一会议页**：录音结束 → 上传/转写 → 说话人绑定 → 纪要生成 → 结果查看，全程不再切换页面
  - `viewSpeakerBinding` 独立绑定页删除：绑定交互内联到统一会议页「转写」Tab（点击说话人 chip 下拉绑定 / 新建说话人）
  - `viewCompleted` 独立结果页删除：纪要 / 待办 / 笔记全部并入统一页
  - 顶部新增「说话人绑定条」：识别到 N 位说话人（M 位未绑定）+ 说话人概览 chips + 跳过 / 新建说话人 / 确认并生成纪要
  - Tab 统一为：转写 / 纪要 / 章节 / 笔记 / 待办；纪要面板三态（待绑定提示 → 骨架屏 → 内容）
- **上传流程并入统一会议页**：`uploadFile` 不再切 processing 视图，上传/转写进度实时显示在纪要 Tab 骨架屏提示语
- **声纹自动匹配自动触发**：`triggerVoiceprintMatch` 重构为无 UI 依赖的 `autoMatchVoiceprint`，进入绑定阶段且无已有绑定时自动执行并应用结果
- **活跃任务互斥判断统一**：`isTaskActive` / `getActiveTaskView` / 上传与录音互斥 / AI 面板任务控制条全部收敛到 `viewGenerating`

### 修复
- 清理死代码：旧完成页 Tab 处理器（TAB_IDS）、AI 注入 Tab 函数群、`renderTranscriptTab`、`showSpeakerBindingForEdit`、声纹绑定页死 UI

---

## [v0.24-server-refactor] - 2026-09-04

### 变更
- **server.py 轻量化重构**：2152 行 → 95 行，按功能域拆分为 9 个 router 模块
  - 新增 `app/store.py`：共享状态层（任务字典、实时状态、持久化辅助、配置常量）
  - 新增 `app/routers/`：tasks / record / speakers / projects / chat / user / hotwords / settings / notes
  - server.py 仅保留 app 创建、路由注册、生命周期管理、前端页面托管
- **新增冒烟测试**：`tests/test_smoke.py` 覆盖 15 个关键路径，含录音启动防阻塞回归测试

### 规范
- **server.py 轻量化原则**：server.py 仅做 app 创建与 router 注册，不含业务逻辑
- **async/sync 边界规则**：含阻塞操作的端点用 `def`；纯异步 I/O 端点用 `async def`
- **冒烟测试兜底原则**：每个功能域至少一个冒烟测试覆盖关键路径

---
## [v0.23-fix-record-start-blocking] - 2026-09-04

### 修复
- **麦克风录音无响应**：点击"麦克风录音"按钮无任何反应
  - 根因：`/api/record/start` 端点定义为 `async def`，但内部执行阻塞操作（`subprocess.Popen` 启动 ffmpeg + `time.sleep(0.5)`），卡死 asyncio 事件循环，整个服务无法响应任何请求
  - 修复：将端点改为同步 `def`，FastAPI 自动在线程池执行，不再阻塞事件循环

---
## [v0.22-fix-binding-confirm] - 2026-09-04

### 修复
- **说话人绑定确认失败**：点击"确认并生成纪要"后页面无响应，任务永远停留在处理中
  - 根因：代码引用了不存在的 DOM 元素 `progressFill`、`processLog`、`pipelineSteps`，导致 `TypeError: Cannot read properties of null` 中断函数执行，API 请求从未发送
  - 修复：为所有引用添加空值检查（`if ($('#progressFill')) ...`），确保元素不存在时不抛错
  - 影响函数：`confirmSpeakerMapping()`、`generateSummaryWithoutMapping()`、`pollTask()`、`updatePipelineSteps()`、`addLog()`、`resetToIdle()`、`loadTask()`

---
## [v0.21-audio-playback] - 2026-09-04

### 新增
- **会议录音回放功能**：已完成会议支持原始录音回放
  - 后端新增 `GET /api/audio/{task_id}` 端点，按 MIME 类型流式返回音频文件
  - 前端用真实 HTML5 `<audio>` 替换原模拟播放器，支持播放/暂停/拖动进度/快进快退/倍速
  - 完成态视图（`viewCompleted`）新增音频播放器栏，与生成态视图共用同一播放器逻辑
  - 音频播放器自动适配当前可见视图（通过 `_audioIds()` 路由到正确 DOM 元素）
  - 原始录音文件保留在 `data/recordings/` 或 `data/uploads/`，删除任务时一并清理

---
## [v0.20-hotword-mappings] - 2026-09-04

### 新增
- **热词映射（后处理纠正）**：ASR 识别结果自动纠正，如 `ES` → `EAS系统`
  - 映射文件 `data/hotword_mappings.txt`，格式 `错误识别→正确文本`
  - 英文词使用 `\b` 词边界匹配（大小写不敏感），避免误替换子串
  - 中文/中英混合直接子串替换
  - 长匹配优先（按左串长度降序排列）
  - 批处理管线（`assemble_dialogue()`）和实时转写（`on_event()`）均已集成
  - REST API：`GET/POST /api/hotword-mappings` 管理映射
  - AI 动作：支持「热词映射」「映射列表」查询

---
## [v0.19-rec-tab-mode] - 2026-09-04

### 新增
- **录音视图响应式 Tab 切换**：视口宽度 < 800px 时，实时转写与实时总结自动切换为 Tab 模式
  - 顶部 Tab 栏含图标 + 文字，激活项有下划线高亮
  - 默认展示「实时转写」，点击切换到「实时总结」
  - 切换时保留数据和滚动位置（仅 CSS 显隐控制）
  - Tab 区域最小高度 44px，触摸友好
  - 从窄屏恢复宽屏时自动清除 Tab 状态，恢复并行布局
  - Tab 模式下总结面板折叠按钮隐藏（Tab 切换替代折叠功能）

---
## [v0.18-ai-panel-enhanced] - 2026-09-03

### 新增
- **AI 面板任务控制条**：录音或处理中时，AI 输入区上方显示任务状态条，含停止按钮可快速终止录音
- **AI 面板「更多」菜单**：输入框左侧新增更多按钮（⋮），点击展开向上弹出的快捷操作菜单
  - 配置化架构（`AI_QUICK_ACTIONS` 数组），新增功能只需追加一项即可
  - 预置 4 项：麦克风录音（录音中自动切换为「停止录音」并高亮）、上传音频文件、查看历史会议、热词管理
  - 点击外部自动关闭菜单
- **状态联动**：任务控制条与更多菜单文案随录音/暂停/处理状态实时更新

---
## [v0.17-ai-action-cli] - 2026-09-03

### 新增
- **AI 对话框动作执行**：右侧 AI 对话框的操作按钮现在真正执行系统功能
  - 后端 `/api/chat` 新增动作检测层，识别用户意图并执行对应操作
  - 支持 11 种动作：录音控制（开始/停止/暂停/恢复）、内容分析（提取待办/关键结论/发言分析）、任务查询、热词/设置查看
  - 动作结果注入 LLM 上下文，生成自然回复
  - 前端根据动作结果自动更新 UI（如录音启动后切换到录音视图）
- **完整 CLI 会议助手**：`cli.py` 扩展为完整的命令行工具
  - `record start/stop/pause/resume/status` — 录音控制
  - `tasks list/show/delete` — 任务管理
  - `speakers list/add` — 说话人管理
  - `hotwords list/add` — 热词管理
  - `settings show/set` — 设置管理
  - `chat <消息>` — AI 对话

---
## [v0.16-sidebar-nav-refactor] - 2026-09-03

### 变更
- **顶栏清理**：移除说话人按钮和用户设置入口，顶栏仅保留应用标题、任务标题、状态指示器和面板切换按钮
- **左栏底部导航**：新增说话人管理、热词管理、设置三个导航入口，位于项目列表下方
- **中栏视图扩展**：新增说话人管理页、热词管理页、设置页三个中栏视图，点击左栏底部入口切换
- **侧栏宽度**：从 232px 调整为 200px，符合 UI 规范
- **API 新增**：
  - `GET/POST /api/hotwords` — 热词读取与保存
  - `GET/POST /api/settings` — 设置读取与保存

### 文档
- 更新 `docs/design/ui-spec.md` 顶栏与左栏说明

---
## [v0.15-realtime-summary-restore] - 2026-09-03

### 修复
- **实时总结页面刷新丢失**：录音中刷新页面后，实时总结面板内容完全消失
  - 后端 WebSocket 连接建立时，回放当前实时总结内容和状态（`summary_update` + `summary_status`）
  - 前端 `checkRecording()` 恢复录音时初始化总结面板 UI 状态
  - 暂停状态也能正确恢复

---

## [v0.14-realtime-speaker-binding] - 2026-09-03

### 新增
- **实时说话人绑定**：录音期间可直接在实时转写区域绑定发言人身份
  - 点击转写条目中的发言人姓名，弹出说话人选择下拉框
  - 选择已有说话人或新建说话人后立即绑定
  - 绑定后所有该说话人的转写条目自动刷新姓名显示
  - 已绑定的说话人名称加粗高亮，便于区分
- **实时总结发言人标注**：实时总结内容自动包含发言人姓名
  - 后端 `_resolve_realtime_speaker_name()` 从绑定映射解析姓名
  - 总结器 `_do_summary()` 构造对话文本时标注「发言人：内容」格式
  - 系统提示词新增发言人标注原则
- **实时绑定 API**：
  - `POST /api/record/bind-speaker` — 录音期间绑定说话人
  - `GET /api/record/speaker-bindings` — 查询当前绑定状态
  - WebSocket 下行新增 `speaker_bound` 消息类型，广播绑定更新
- **页面刷新恢复**：恢复录音时自动拉取已有说话人绑定

### 变更
- **实时转写消息增强**：`partial`/`sentence`/`history` 消息均携带 `speaker_name` 字段
- **实时总结输入增强**：`feed_sentence()` 支持 `speaker_name` 字段，总结 prompt 包含发言人归属信息
- **录音停止时保存绑定**：实时说话人绑定映射写入任务数据，供批管线复用

---

## [v0.13-tab-refactor] - 2026-09-03

### 新增
- **笔记 Tab**：完成态新增可编辑笔记 tab，支持自动保存（防抖 1 秒），录音时的临时笔记自动迁移到持久化笔记
- **AI 注入 Tab**：AI 对话回复中自动识别待办/结论/决策，弹出注入提示条，用户可一键注入到会议记录
  - 后端 `_extract_injectable_items()` 规则引擎，从 AI 回复中匹配 Markdown checkbox、关键词列表项和结论段落
  - `/api/chat` 返回新增 `extracted_items` 字段
  - 注入内容支持「写入纪要」标记和删除操作
- **待办 Tab**：汇总展示会议相关待办事项，支持勾选完成/删除，来源标注（AI 注入 / 纪要提取）
- **用户信息登记**：顶栏右侧新增用户区域，点击弹出模态框输入姓名，支持一键绑定当前会议的说话人身份
  - `core/users.py` 用户数据管理模块，持久化到 `data/users.json`
  - `GET/POST /api/user`、`POST /api/user/bind-speaker` 端点
- **笔记/注入/待办 API**：
  - `GET/PUT /api/tasks/{id}/notes` — 笔记读写
  - `GET/POST /api/tasks/{id}/injections` — 注入内容列表/新增
  - `POST /api/tasks/{id}/injections/{id}/apply` — 标记已写入纪要
  - `DELETE /api/tasks/{id}/injections/{id}` — 删除注入
  - `GET /api/tasks/{id}/todos` — 待办列表
  - `POST /api/tasks/{id}/todos/{id}/toggle` — 切换待办完成状态
  - `DELETE /api/tasks/{id}/todos/{id}` — 删除待办

### 变更
- **移除「原始转写」Tab**：完成态不再展示 DashScope 原始返回 JSON，减少无意义数据暴露
- **任务 JSON 瘦身**：`_save_task_to_disk()` 持久化时排除 `transcription` 字段，单任务文件从 ~124KB 降至 ~10KB
- **启动迁移**：`_load_tasks_from_disk()` 自动检测并剔除旧文件中的 `transcription` 字段

---

## [v0.12-delete-task] - 2026-09-03

### 新增
- **录音列表删除功能**：左侧历史记录支持删除会议录音
  - 鼠标悬停在历史项时显示删除按钮（垃圾桶图标）
  - 删除前弹出确认对话框，防止误操作
  - 删除后自动刷新列表，若删除的是当前查看的任务则切回空闲态
  - 后端复用已有 `DELETE /api/tasks/{task_id}` 接口，清理任务文件与持久化数据

## [v0.11-folder-picker] - 2026-09-03

### 新增
- **文件夹选择器**：项目关联文件夹时支持可视化浏览本地文件系统，不再需要手动输入路径
  - 后端 `GET /api/filesystem/browse?path=...` 端点，返回目录列表（默认返回用户主目录）
  - 前端弹窗式文件夹浏览器：面包屑导航、主目录/上级快捷按钮、子目录列表（点击进入）
  - 选择后路径自动回填到输入框，用户仍可手动编辑

## [v0.10-realtime-summary] - 2026-09-03

### 新增
- **实时总结功能**：录音期间每分钟自动生成增量会议纪要摘要
  - **后端增量引擎**（`core/realtime_summary.py`）：收集定稿句子，每 60 秒触发 LLM 增量总结，使用 qwen-turbo 低延迟模型
  - **增量策略**：首次总结仅用当前缓冲句子；后续传入「上次摘要 + 新增句子」，模型输出更新后的完整摘要
  - **前端左右分栏布局**：录音界面笔记栏上方分为左栏（实时转写）和右栏（实时总结），55%/45% 比例
  - **控制面板**：右栏支持暂停/恢复总结、折叠/展开面板
  - **WebSocket 消息扩展**：复用现有 `/ws/transcript/{task_id}`，新增 `summary_update` 和 `summary_status` 消息类型
- **新增 API 端点**：
  - `POST /api/record/summary/pause` — 暂停实时总结
  - `POST /api/record/summary/resume` — 恢复实时总结

### 变更
- 录音界面布局从单栏转写升级为双栏（转写 + 总结），转写区域宽度从 `flex:1` 调整为 `flex:55`
- 定稿句子回调同时送入实时转写 WebSocket 和实时总结引擎

---

## [v0.9-ai-context] - 2026-09-03

### 新增
- **AI 面板深度上下文集成**：右侧会议助手对话框基于四维上下文生成回复
  - **维度 1 — 实时转写流**：录音期间将最近 10 条定稿句子作为动态上下文注入，AI 可基于最新对话内容回答
  - **维度 2 — 已完成会议纪要**：已生成纪要的摘要、结论、待办事项作为上下文
  - **维度 3 — 关联项目资料**：通过项目关键词检索注入相关文档片段
  - **维度 4 — 对话历史**：维护最近 5 轮（10 条）对话历史，确保多轮连贯性
- **后端实时转写缓冲区**：`_realtime_transcript_buffers` 自动收集 WebSocket 流中的定稿句子（`app/server.py`）
- **`POST /api/chat` 增强**：
  - 新增 `realtime_transcripts` 请求字段，接收前端传来的实时转写条目
  - 上下文按优先级注入：实时转写 > 完成纪要 > 项目资料 > 对话历史
  - 新增 `_build_speaker_name_map()` 辅助函数，解析说话人姓名
- **前端实时转写追踪**：
  - 新增 `realtimeTranscriptEntries` 数组，在 `handleTranscriptMessage` 的 `sentence` 分支自动收集
  - `sendAiMessage()` 请求体携带最近 10 条实时转写条目
  - 录音启动/恢复时自动清空缓冲区

### 变更
- AI 对话上下文注入从单一维度升级为四维分层，优先级清晰
- 系统提示词结构保持不变，动态上下文块以 `---` 分隔追加在末尾

---

## [v0.8.1-ui-fix] - 2026-09-03

### 修复
- **会议时间显示"未提供"**：LLM 有时忽略提示词中的会议时间，增加后处理兜底替换；同时增加从音频文件名提取时间的兜底逻辑（`app/server.py`、`core/summarize.py`）
- **"关联项目"按钮点击无响应**：按钮 onclick 与 document click 监听器存在事件冒泡冲突，添加 `event.stopPropagation()` 修复（`index.html`）
- **记录要点输入框高度过小**：CSS `min-height` 从 4em 增至 6em，JS 自动扩展上限从 80px 增至 150px，`rows` 从 1 改为 3（`index.html`）
- **"添加文件夹"按钮点击无效**：将 `prompt()` 弹窗改为页面内联输入框，避免浏览器阻止原生对话框（`index.html`）

## [v0.8-notes] - 2026-09-03

### 新增
- **录音笔记栏**：录音界面底部控制栏上方新增笔记输入区域
  - 用户可在录音期间随时记录要点、待办或关键信息
  - 笔记自动扩展高度（最大 80px），支持多行输入
  - 笔记内容作为上下文传递给纪要生成 LLM，辅助理解会议背景
- **后端支持**：
  - `POST /api/record/stop` 新增 `notes` 参数，接收用户笔记
  - 笔记存储在任务记录中（`user_notes` 字段）
  - 管线第二阶段将笔记注入 `generate_summary` 提示词
- **纪要提示词增强**：系统提示词新增「用户笔记为辅助参考」原则，明确笔记仅作背景参考，纪要仍以对话原文为依据

## [v0.7-projects] - 2026-09-03

### 新增
- **项目关联功能**：会议纪要与本地项目资料深度联动
- **`core/projects.py`**：项目管理与文件索引模块
  - 项目 CRUD：创建/删除项目，关联多个本地文件夹
  - 文件扫描：自动扫描 md/txt/docx/pdf 文件，提取文本内容
  - 轻量索引：文件名 + 摘要 + 关键词（Markdown 标题/英文术语/中文书名号）
  - 关键词检索：基于文件名/标题/关键词/摘要的匹配搜索
  - 上下文注入：`get_project_context_for_chat()` 为 AI 对话提供项目资料片段
- **项目 API 端点**：
  - `GET/POST/PUT/DELETE /api/projects`：项目 CRUD
  - `POST/DELETE /api/projects/{id}/folders`：文件夹管理
  - `POST /api/projects/{id}/scan`：异步触发索引构建
  - `GET /api/projects/{id}/files`：获取索引文件列表
  - `POST /api/projects/{id}/search`：项目文件搜索
- **`POST /api/chat`**：AI 对话端点（接入通义千问，替代原有模拟回复）
  - 自动注入当前会议纪要上下文 + 项目资料检索增强
  - 返回回复文本 + 引用来源文件列表
- **前端 UI**：
  - 左侧导航新增「项目」区域
  - 中栏新增项目管理视图（创建/添加文件夹/重建索引/查看文件）
  - AI 对话框新增「📎 关联项目」按钮
  - AI 回复引用项目资料时标注来源
  - AI 对话接入真实 LLM（qwen-plus），支持多轮上下文
- **依赖**：`python-docx>=1.1.0`、`PyPDF2>=3.0.0`

### 变更
- AI 对话从模拟回复升级为接入通义千问 LLM
- `requirements.txt`：新增 python-docx、PyPDF2

### 决策
- 项目配置独立存储于 `data/projects.json`
- 索引采用轻量关键词匹配，适合 MVP 规模
- AI 对话注入上下文上限 3000 字符

---

## [v0.6.4-realtime-diarization] - 2026-09-03

### 新增
- **实时说话人分离**：录音过程中实时区分不同说话人，前端显示「发言人1」「发言人2」等标签
  - 原理：本地声纹聚类（MFCC 特征提取 + 余弦相似度），无需云端 API
  - `core/diarization.py`：新增声纹聚类模块，每 2 秒提取一次特征，基于相似度阈值自动创建/匹配说话人
  - `app/server.py`：PCM 回调同时送 ASR 和声纹聚类器，ASR 句子标注 speaker_id 后推送前端
  - `requirements.txt`：新增 numpy、scipy 依赖
  - 前端已支持 speaker_id 显示（`msg.speaker_id ?? 1`），无需改动

### 限制
- 基于声学特征的启发式方法，准确率低于神经声纹模型（如 WeSpeaker）
- 适合 2-4 人会议场景；人数过多或音色相近时可能误判
- 需要每人至少说 2 秒才能建立可靠档案

---

## [v0.6.3-fix-pause-recording] - 2026-09-03

### 修复
- **录音暂停无效**：点击暂停按钮后录音仍在继续，实时转写也未停止
  - 根因：前端 `togglePause()` 仅暂停了计时器 UI，未通知后端
  - `core/audio.py`：新增 `_stream_paused` 标志，reader loop 暂停时仍读取 pipe（防 ffmpeg 阻塞）但丢弃数据，不写文件、不送 ASR
  - `core/audio.py`：新增 `pause_recording_with_stream()` / `resume_recording_with_stream()` 函数，累计暂停时长从最终 duration 中扣除
  - `app/server.py`：新增 `POST /api/record/pause` 和 `POST /api/record/resume` 端点
  - `app/static/index.html`：`togglePause()` 改为 async，暂停/恢复时调用后端 API

---

## [v0.6.2-task-persist] - 2026-09-03

### 修复
- **任务数据持久化**：任务数据（对话稿、说话人绑定、纪要等）从纯内存存储改为 JSON 文件持久化（`data/tasks/`），页面刷新或服务重启后数据不丢失
- **说话人绑定刷新丢失**：绑定说话人后页面刷新，已关联的人员绑定不再丢失
  - 后端：`set_speaker_mapping` 端点在触发纪要生成前，即将 `speaker_uuid_mapping` 写入任务并持久化
  - 前端：`showSpeakerBinding` 加载任务时从 `speaker_uuid_mapping` 恢复已有绑定状态
  - 前端：`confirmSpeakerMapping` 提交成功后立即同步映射到本地 task 对象
- **loadTask 缺少 failed 状态处理**：加载失败状态任务时页面不再空白，正确显示错误信息

### 变更
- `app/server.py`：新增 `_save_task_to_disk()` / `_load_tasks_from_disk()` 函数，启动时自动恢复任务
- `app/static/index.html`：`selectBtOption` 同步更新本地 task 缓存；`showSpeakerBinding` 支持恢复已有绑定
- `.gitignore`：新增 `data/tasks/` 排除规则

---

## [v0.6.1-retry] - 2026-09-03

### 修复
- **实时转写限流重试**：DashScope ASR 返回 `Too many requests` 时自动指数退避重试（2s/5s/10s，最多 3 次）
- `core/realtime_asr.py`：
  - `_TranscriptCallback` 新增 `wait_for_connect()` 同步等待连接结果（`on_open`/`on_error` 信号）
  - `RealtimeTranscriber.start()` 增加重试循环，重试期间显示用户友好提示（"服务繁忙，自动重试中"）
  - 仅最后一次重试才转发原始 SDK 错误，避免中间错误刷屏
- `app/server.py`：转写器启动移至后台线程，避免阻塞 FastAPI 事件循环（重试等待可能持续数秒）
- **管线热词参数名修复**：`pipeline.py` 调用 `get_or_create_vocabulary()` 的参数从 `model=` 修正为 `target_model=`（v0.4 升级 API 时遗留）

### 变更
- **说话人绑定界面重构**：从抽象卡片列表（"说话人0 · 5句"）改为对话稿内联绑定模式
  - 对话稿按时间线排列，每行显示时间戳 + 说话人标签（彩色 chip）+ 文本内容
  - 点击说话人标签弹出下拉菜单，可选择绑定身份或新建说话人
  - 顶部增加说话人概览条，显示各说话人绑定状态
  - 用户可看着实际发言内容来判断说话人身份，不再依赖抽象序号

---

## [v0.6-speakers] - 2026-09-03

### 新增
- **说话人姓名化**（P3）：将 `speaker_id` 映射为真实姓名，纪要中使用真实姓名
- **`core/speakers.py`**：说话人档案管理模块
  - `Speaker` 类：说话人档案（姓名、角色、备注）
  - `MeetingMapping` 类：会议级 speaker_id → 说话人 映射
  - 全局说话人 CRUD：`load_speakers()` / `add_speaker()` / `update_speaker()` / `delete_speaker()`
  - 会议映射管理：`save_meeting_mapping()` / `get_latest_mapping()`
  - 姓名应用：`apply_speaker_names()` 将 speaker_id 映射为真实姓名
- **数据文件**：
  - `data/speakers.json`：全局说话人档案
  - `data/meeting_mappings.json`：会议映射历史（用于复用建议）
- **API 端点**：
  - `GET /api/speakers`：获取说话人列表
  - `POST /api/speakers`：添加说话人
  - `PUT /api/speakers/{id}`：更新说话人
  - `DELETE /api/speakers/{id}`：删除说话人
  - `GET /api/speakers/mapping/latest`：获取最近一次会议映射（用于复用）
  - `POST /api/speakers/mapping`：保存会议映射
- **管线集成**：`run_pipeline()` 新增 `speaker_mapping` 参数，转写后自动应用姓名映射
- **纪要提示词**：`generate_summary()` 使用真实姓名，对话稿显示 `**张三**：...` 而非 `**说话人0**：...`

### 决策
- 采用「人工映射 + 历史复用」方案（详见 ADR-0005），不引入声纹识别（WeSpeaker），保持 v1 纯云方案定位
- 说话人档案全局共享，会议映射独立存储，支持历史复用

---

## [v0.5-postprocess] - 2026-09-03

### 新增
- **批转写后处理管线**（`core/transcribe.py`）：
  - `merge_fragments()`：碎片句子合并——基于时间间隔（<2s）、短句检测（<12字）、跨句拆词检测（如"智"+"能"="智能"）
  - `correct_speaker_ids()`：说话人修正——夹心修正（A-B-A→全A）+ 碎片短句跟随前句说话人
  - `assemble_dialogue()` 接入后处理管线：原始句子 → 碎片合并 → 说话人修正 → 按 speaker 归并

---

## [v0.4-asr-upgrade] - 2026-09-03

### 变更
- **实时转写模型升级**：`paraformer-realtime-v2` → `qwen-audio-3.0-asr-flash-streaming`（官方首推实时模型，详见 ADR-0004）
- `core/realtime_asr.py`：新增 `vocabulary`（即时热词）和 `context`（上下文增强）参数支持
- `core/hotwords.py`：热词 API 适配新版——`model` → `target_model`，热词格式 `{"word": ..., "weight": 2}` → `{"text": ..., "weight": 4}`，上限 500 → 2000

### 决策
- 实时转写升级为 `qwen-audio-3.0-asr-flash-streaming`：支持上下文增强（传入领域术语提升识别率）和即时热词（随请求内联传入，免创建热词表）
- 批处理转写（paraformer-v2）保持不变，因其支持说话人分离且异步处理长音频稳定
- WebSocket 连接逻辑无需改动（新模型使用相同 SDK 和回调机制）

---

## [v0.3-realtime] - 2026-09-03

### 新增
- **实时转写**：录音期间通过 DashScope `paraformer-realtime-v2` 流式识别，前端实时显示转写文字（延迟约 1-2 秒）
- **`core/realtime_asr.py`**：封装实时转写引擎（WebSocket + SDK 回调 → asyncio Queue → 前端推送）
- **流式录音**：`core/audio.py` 新增 `start_recording_with_stream()`，ffmpeg 输出 raw PCM 到 stdout pipe，后台线程同时写文件 + 回调送入 ASR
- **WebSocket 端点**：`app/server.py` 新增 `WS /ws/transcript/{task_id}`，实时推送 partial/sentence/error/ended 消息
- **前端实时视图**：录音中页面下方新增「实时转写预览」区域，临时结果斜体显示，定稿句子正常追加
- 实时转写失败时优雅降级：仅录音，不影响后续批管线

### 变更
- 录音端点改用流式录音（`start_recording_with_stream` / `stop_recording_with_stream`）替代原有文件直写方式
- `requirements.txt` 新增 `dashscope>=1.23.0`、`websockets>=12.0`

### 决策
- 实时转写（paraformer-realtime-v2）**不支持说话人分离**，定位为「预览」；最终纪要仍走批管线（paraformer-v2 + diarization）
- 使用语义断句（`semantic_punctuation_enabled=True`）更适合会议场景
- 单 ffmpeg 进程输出 PCM pipe，Python 线程分叉写文件 + 送 ASR（避免 avfoundation 并发采集冲突）

---

## [v0.2-recording] - 2026-09-03

### 新增
- **实时录音**：`core/audio.py` 增加麦克风/BlackHole 采集（ffmpeg avfoundation），支持开始/停止录音、设备列表查询
- **录音 API**：`app/server.py` 新增 `POST /api/record/start`、`POST /api/record/stop`、`GET /api/record/status` 三个端点
- **录音 UI**：前端增加录音按钮、录音中视图（红点脉冲 + 计时器 + 停止按钮）、页面刷新恢复录音状态
- 录音文件存放 `data/recordings/`，停止录音后自动进入管线处理（归一化 → 转写 → 纪要）
- 录音设备名可通过环境变量 `RECORD_DEVICE` 覆盖（默认 `MacBook Pro麦克风`；线上会议戴耳机场景可改为 `BlackHole 2ch`）

---

## [v0.1-mvp] - 2026-09-03

### 新增
- **core/ 管线模块**：`audio.py`（ffmpeg 归一化）、`upload.py`（DashScope 临时存储上传）、`transcribe.py`（paraformer-v2 转写+轮询+说话人分离）、`hotwords.py`（热词表）、`llm.py`（通义千问 provider）、`summarize.py`（纪要提示词与解析）、`pipeline.py`（全流程编排）
- **cli.py**：命令行入口，支持 `transcribe` / `normalize` / `upload` / `server` 四个子命令
- **app/server.py**：FastAPI 本地服务，RESTful API（上传/查询/下载）+ 后台管线执行
- **app/static/index.html**：前端页面，左中右三栏布局，支持拖拽上传、实时进度、纪要展示、AI 对话框
- **requirements.txt**：运行依赖清单
- **端到端验证通过**：samples/ 下 ~2h 真实会议音频（4 说话人 / 983 句）全流程跑通，纪要质量合格

### 决策
- 转写调用使用 `requests` 直调 RESTful API（SDK 不支持 `oss://` 前缀），详见 API_CONTRACTS.md

---

## [v0-prototype] - 2026-09-03

### 新增
- MVP 原型图（HTML 可视化线框）：`docs/design/wireframes/mvp-prototype.html`
- 细化 `docs/design/ui-spec.md`：完整页面结构、交互流程、热词管理页、设置页、快捷键

### 变更
- `MISSION.md` MVP 清单同步为 v1 云方案（DashScope），当前状态更新为「原型设计」
- `docs/PRD.md` 加入 AI 对话功能到核心场景与功能清单，明确「AI 对话是标配」产品定位

### 重构
- 界面布局从「上下结构」改为「左中右三栏布局」
- 右栏 AI 对话框作为产品标配功能，支持对话驱动操作（录音、转写、查询、设置、热词管理）

---

## [v0-skeleton] - 2026-09-03

### 新增
- 工作区骨架：`README` 入口、`AGENTS` 约定、`CHANGELOG`、`.env.example`、`.gitignore`
- `docs/` 分层：`ARCHITECTURE`、`API_CONTRACTS`、`GLOSSARY`、`adr/`、产品层占位（PRD/ROADMAP/design）
- 代码目录占位：`core/` `app/` `tests/` `scripts/` `data/`
- 初始化 git 仓库（main 分支）

### 决策
- **ADR-0001** MVP v1 走云方案（DashScope），不做本地语音解析
- **ADR-0002** ASR + 说话人分离 选 `paraformer-v2`
- **ADR-0003** 纪要生成 选 通义千问 `qwen-plus`

### 说明
- 云方案 v1 设计定稿，见 `MVP_PLAN.md`。
- 待办：P0 环境与冒烟测试尚未开始。
