# SaaS 化长期规划 / SaaS Roadmap

作者：Yongliang Wang
创建：2026-11-20
状态：规划中（P0 待执行）

---

## 0. 执行约定

本项目为 **100% 代码 AI 项目**。所有任务必须满足以下四条，否则不进清单：

1. **有代码产出**：每个任务必须落到明确的文件、函数、字段。
2. **有可观测差异**：执行前后能在接口响应、磁盘文件或 UI 上看到确定变化。
3. **可独立提交**：一个任务 = 一个 commit，可单独回滚。
4. **可逐项验收**：验收步骤写成"点击/命令 → 预期结果"，不写"确认正常"。

禁止出现在本清单的动词：调研、评估、梳理、优化、完善、重构一下。
若某步需要先调研，说明方案未定，先出决策，不入清单。

状态标记：`[ ]` 未开始 / `[~]` 进行中 / `[x]` 已完成 / `[!]` 阻塞

### 0.1 分支与回滚

不开长期分支。主干（main）随时可运行，风险靠短分支 + tag + 备份兜。

| 任务类型 | 策略 |
|---|---|
| T-000 ~ T-003、T-005 | 短分支，一任务一 PR，不超过 2 天 |
| T-004 数据迁移 | **必须**独立分支 `feat/tenant-dirs` + tag + data 备份 |
| T-006 a~d | 每小步一短分支，合并后再开下一步 |
| M1 之后 | 短分支 + feature flag，不开形态分支 |

命名：`feat/tXXX-短描述`，如 `feat/t000-capabilities`。

T-004 开工前固定动作：

```bash
git tag pre-tenant-dirs
git checkout -b feat/tenant-dirs
cp -a data ~/oms-data-backup-$(date +%Y%m%d)
```

不做三件事：

1. 不开 `saas` / `dev` 长期分支——会与 main 持续分叉，合并冲突不可控
2. 不用分支隔离单机版与 SaaS 版——用 D9 的 edition 配置
3. 不打 release 分支——等真有用户在用发行版再说

---

## 1. 现状基线（2026-11-20 实测）

| 项 | 事实 | 依据 |
|---|---|---|
| 路由端点 | 206 个端点，42 个 router 文件 | `grep -c "@router\."` |
| 鉴权覆盖 | 仅 4 个文件、25 个端点有 `Depends` | admin / admin_config / engine_component / models |
| 任务存储 | 全局单份 `data/tasks`，`tasks` 为模块级 dict | `core/task_store.py:33-74` |
| 数据归属 | task 无 owner / tenant 字段 | `app/routers/tasks.py` 创建路径 |
| 录音并发 | **进程级单例，一台实例同时只能录一场** | `core/audio_stream.py:41-65` |
| 实时实例 | 全局 dict 按 task_id 索引，无用户维度 | `core/realtime_store.py:34-36` |
| 协作能力 | 零（share/member/team/collaborator 无命中） | routers 全量 grep |
| 音频存量 | 220 场 / 5.3 GB / 约 46 小时 | `du -sh data/recordings` |
| 计费雏形 | usage jsonl + subscription tier 已有 | `data/usage/`、`app/routers/usage.py` |
| 本地能力 | 设备枚举、workspace、IDE 启动、录音 | `record_devices.py`、`workspace.py`、`desktop.py` |

结论：云端链路已通，缺的是**租户语义**与**会话编排**，不是重写。

---

## 2. 已定架构决策

| # | 决策 | 内容 | 不可逆性 |
|---|---|---|---|
| D1 | 并发单位 | 按**会议**伸缩，一场一个 worker，不做共享进程池 | 高 |
| D2 | 租户模型 | 先 User，Org 后置；owner 字段 P0 就写入 | 极高 |
| D3 | 本地桥协议 | 出站 WebSocket + 任务级临时授权 + 白名单目录 | 高 |
| D4 | 音频策略 | 边录边传，Opus 落对象存储，热存 30 天 | 中 |
| D5 | 共享语义 | 共享会议默认只读；工作区需显式"发布"才可见 | 高 |
| D6 | 商业形态 | 开源核心 + 托管增值（协作/审计/存储/SSO） | 高 |
| D7 | 会议归属 | 任何会议**必须且只能**属于一个空间，禁止同时归属两个 | 极高 |
| D8 | 本地镜像 | 全量只读镜像只含文本，**音频不落本地**，走云端链接 | 中 |
| D9 | 功能边界 | SaaS-only 闭集：空间与成员、共享与链接、审计查询导出、SSO/SCIM、多端同步、组织与计费；单机版单人能力一项不减 | 高 |
| D10 | 空间可见性 | 空间内**全成员可见**全部会议，会议级不再单独设权限；写权限由空间角色决定 | 高 |

D9 细化：

| 只给 SaaS | 单机永久保留 |
|---|---|
| 空间与成员管理 | 录音、上传 |
| 会议共享、共享链接 | 转写、说话人识别、声纹 |
| 审计查询与导出 | 纪要、决策、洞察板 |
| SSO / SCIM | AI 对话、检索 |
| 多端同步 | 本地引擎（可选装） |
| 组织管理、席位计费 | 工作区、IDE 联动 |

判定标准：
1. 需要**多个人**才有意义 → SaaS
2. 需要**跨设备** → SaaS
3. 需要**集中治理** → SaaS
4. 其余单人能力 → 单机永久保留

实现约束：
- 禁止散落 `if edition == "saas"`；统一由前端 `useEdition()` 与后端 edition 配置控制
- 单机版必须保持"完整可用的个人工具"，不得阉割单人能力

D5 细化（避免后续临时补丁）：
- 共享后，会议内文本、纪要、决策对成员可见
- 工作区默认对成员**不可见**，owner 需点「发布工作区」生成只读快照
- 非 owner 的任何写操作（改纪要、绑说话人）一律 403

### 2.1 领域模型：空间（Space）

空间是唯一的资产容器，同时是权限边界、存储边界、审计维度。

| 空间类型 | 产生方式 | 成员 | 语义 |
|---|---|---|---|
| 本地空间 | 未登录单机，唯一 | 仅本机 | 私产 |
| 个人空间 | 登录后自动创建 | 仅本人 | 私产 |
| 团队空间 | 组织下创建 | 受邀成员 | 团队资产 |

落点：

| 维度 | 落点 |
|---|---|
| 逻辑 | `meeting.space_id` |
| 物理 | 对象前缀 `org/{org_id}/space/{space_id}/` |
| 权限 | `SpaceMember(space_id, user_id, role)`，role ∈ owner/editor/viewer |
| 审计 | 按 space 归档，可导出 |

已定规则：
- 私产转团队资产只有「移入空间」一个动作，**不留副本**
- 移入必须写审计：谁、从哪、到哪、何时
- 原地址的链接指向新位置，不返回 404
- 现有 `project` 不升级为空间：它是本地目录同步配置，含绝对路径，不适合做团队容器

可见性规则（D10）：
- 空间内全成员可见全部会议，不做会议级单独授权
- 读：空间成员一律可读
- 写：按空间角色，`owner` / `editor` 可写，`viewer` 只读
- 权限判定只看空间角色，不看会议归属人

命名约束：
- 不叫「会议空间」——空间里还有纪要、决策、洞察板、声纹库、文档
- 不叫「工作空间」——与现有 workspace（本地文件目录）撞车
- 统一用**空间** / Space

---

## 3. 里程碑总览

每个里程碑以一个**可演示的完整动作**作为出口，不达标不进下一阶段。

| 里程碑 | 出口演示 | 预计任务数 |
|---|---|---|
| M0 地基 | 同一份代码：单机可用 + 开启鉴权后未登录访问被拦 + 每场会议有 owner + 关键操作有审计记录 + 本地能力已接口化 | 13 |
| M1 托管版 | 云端起一个实例，浏览器完成注册→上传→转写→纪要，全程免安装 | 9 |
| M2 本地桥 | 新机器装 30 秒，本机录音+工作区+IDE 在云端页面可用；全量镜像可在 IDE 内检索 | 7 |
| M3 协作 | 两人同看一场会，权限各自正确，共享链接可撤销 | 6 |
| M4 组织合规 | 能过一遍企业安全问卷 | 6 |

---

## 4. M0 地基（详细任务）

M0 原则：**不改变任何现有用户可见行为**。所有差异要么在磁盘、要么在接口字段、要么在开关打开后才生效。

执行顺序即编号顺序，前一项验收通过再开下一项。

---

### T-000 本地能力接口化（拆 3 小步）

- [ ] T-000a 定义接口与单机实现
- [ ] T-000b 录音链路迁移
- [ ] T-000c 文件系统与 IDE 迁移

- 目的：把"必须在本机执行的动作"收进接口，业务层只依赖接口。否则 M2 的桥要在已上线的录音与文件代码上返工。
- 依据：现状是散着直连的——
  - 录音：[audio_stream.py:133](core/audio_stream.py) 直接拉 ffmpeg
  - 文件系统：[projects.py:65](app/routers/projects.py) 直接读绝对路径
  - IDE：`workspace.py:176-220` 直接 `subprocess.Popen`

#### T-000a 定义接口与单机实现
- 改动：
  1. 新增 `core/capabilities.py`
     - `AudioCapture` / `LocalFS` / `IdeLauncher` 三个 `Protocol`
     - `LocalAudioCapture` / `LocalFS` / `LocalIdeLauncher`：每个方法直接委托现有函数，**不新写逻辑**
     - `get_audio_capture()` / `get_local_fs()` / `get_ide_launcher()`：当前返回单机实现
  2. **不改任何调用点**
- 验证：
  1. 前端录音/上传/纪要全流程不变
  2. `pytest tests/ -q` 全绿
  3. 新增单测 `tests/test_capabilities.py`：三个 getter 返回单机实现，方法可调用
- 回滚：删文件与测试，单 commit

#### T-000b 录音链路迁移
- 改动：`app/routers/record*.py` 中 `from core.audio import start_recording_with_stream ...` 改为经 `get_audio_capture()`
- 验证：
  1. 前端录 30 秒 → 转写正常，停止后进程清理干净
  2. `pytest tests/test_record_sentinel_contract.py -q` 全绿
  3. AST 守护：新增断言，`app/routers/record*.py` 不得直接 import `core.audio_stream`
- 回滚：单 commit

#### T-000c 文件系统与 IDE 迁移
- 改动：`projects.py` 的目录浏览、`workspace.py` 的 `launch_ide` / 打开目录，改经 `get_local_fs()` / `get_ide_launcher()`
- 验证：
  1. 前端浏览目录正常；点「在 IDE 打开」本机 IDE 启动到正确目录
  2. 打开 Finder 正常
  3. AST 守护：这两个 router 不得直接出现 `subprocess.Popen`
- 回滚：单 commit

- 边界：只做三个接口。不做事件总线、不做插件系统、不预留"未来可能需要"的能力。
- 依赖：无（可在 T-001 之前并行）

---

### T-001 统一身份依赖（行为零变化）

- [ ] 执行
- 目的：让"当前用户"成为每个请求可取的唯一来源，为越权拦截铺路。
- 改动点：
  1. 新增 `app/deps.py`
     - `get_current_user(request) -> dict`：优先解析 `oms_session` cookie 的 JWT；缺失时若 `is_local_single_user()` 为真，返回 `{"id": "local", "role": "admin", "source": "local_mode"}`；否则 401
     - 复用 `core/auth.py` 的 `JWT_SECRET`，不新建密钥体系
  2. 在 4 个核心 router 的 router 级挂依赖：`tasks.py`、`record.py`、`notes.py`、`chat.py`
  3. 不改任何业务逻辑，不删原有 `Depends`
- 验证：
  1. `REQUIRE_AUTH=false` 启动，`curl -s localhost:8000/api/tasks | head -c 100` → 返回任务数组，与改动前一致
  2. 前端打开会议列表、详情、纪要页 → 无报错，数据条数不变
  3. `REQUIRE_AUTH=true` 重启，`curl -i localhost:8000/api/tasks` → `HTTP/1.1 401`
  4. `REQUIRE_AUTH=true` 时前端刷新 → 跳转登录页
- 回滚：删除 `app/deps.py` 与 4 处 `dependencies=[...]`，单 commit 回退。
- 依赖：无

---

### T-002 审计事件写入（纯增量）

- [ ] 执行
- 目的：审计最怕补历史，先积累。
- 改动点：
  1. 新增 `core/audit.py`
     - `append_event(actor_id, action, target_type, target_id, meta: dict | None = None) -> None`
     - 落盘 `data/audit/YYYY-MM.jsonl`，字段：`ts`(ISO8601 UTC)、`actor_id`、`action`、`target_type`、`target_id`、`meta`、`ip`、`ua`
     - 写入失败只记 warning，绝不阻断主流程
  2. 埋 3 个点：
     - `app/routers/tasks.py` 创建任务 → `action="meeting.create"`
     - `app/routers/tasks.py` 删除任务 → `action="meeting.delete"`
     - 导出纪要端点 → `action="meeting.export"`
- 验证：
  1. 前端新建一场会议 → `data/audit/2026-11.jsonl` 新增 1 行，`action` 为 `meeting.create`，`target_id` 为新 task_id
  2. 删除该会议 → 新增 `meeting.delete` 行
  3. 导出纪要 → 新增 `meeting.export` 行
  4. 手动把 `data/audit` 设为只读，再新建会议 → 会议仍创建成功，日志有 warning
- 回滚：删模块与 3 处调用；已写入的 jsonl 可保留。
- 依赖：无

---

### T-003 owner 字段落库

- [ ] 执行
- 目的：数据归属从第一天写进去，后续迁移成本最低。
- 改动点：
  1. `app/routers/tasks.py` 创建任务时写入 `owner_id`（取 `get_current_user`）
  2. `app/routers/import_tasks.py` 导入任务同样写入
  3. `core/tasks_repo.py` 新增 `list_tasks(owner_id: str | None = None)`，`None` 时返回全部（兼容）
  4. `core/task_store.py` 启动加载时，缺失 `owner_id` 的旧任务补 `owner_id="local"` 并回写
- 验证：
  1. 前端新建会议 → `data/tasks/{id}.json` 含 `"owner_id": "local"`
  2. `curl localhost:8000/api/tasks` → 每条记录含 `owner_id`
  3. 重启服务 → 旧 811 条任务全部补上 `owner_id`，会议列表条数不变
  4. `pytest tests/test_tasks_repo.py -q` → 全绿
- 回滚：字段可保留（无害），回退代码即可。
- 依赖：T-001

---

### T-004 数据目录按用户分区 + 迁移

- [ ] 执行（高风险，独立分支 `feat/tenant-dirs`）
- 目的：物理隔离。这一步风险最高，必须独立提交、独立回滚。
- 前置：`git tag pre-tenant-dirs`，并完整备份 `data/` 一次。
- 改动点：
  1. 新增 `core/paths.py`
     - `user_root(uid) -> Path`：`data/users/{uid}`
     - `tasks_dir(uid)` / `recordings_dir(uid)` / `uploads_dir(uid)` / `output_dir(uid)` / `attachments_dir(uid)`
     - `DATA_LAYOUT` 开关：`legacy`（默认，仍走全局） / `tenant`（走分区）
  2. 迁移脚本 `scripts/migrate_to_tenant_dirs.py`
     - 移动 `data/{tasks,recordings,uploads,output,chat_attachments}` → `data/users/local/`
     - 移动 `settings.json`、`speakers.json`、`voiceprint_registry.json`、`projects.json`、`_meetings.json`
     - **同步改写 task json 内的 `audio_path`**（旧值含 `data/recordings/...`，必须指向新路径，否则孤儿恢复失效）
     - 输出迁移报告：文件数、改写路径数、失败数
  3. `core/task_store.py` 的 4 个目录常量改为调用 `core/paths.py`
- 验证：
  1. 迁移前记录：`ls data/tasks | wc -l` → 811；`ls data/recordings | wc -l` → 220
  2. 执行迁移脚本 → 报告 `tasks=811, recordings=220, rewritten_paths=811, failed=0`
  3. 启动服务 → 前端会议列表仍 811 条；随机打开 3 场会议，音频可播放
  4. 上传一个音频转写 → 文件落到 `data/users/local/uploads/`，任务可正常完成
  5. `pytest tests/ -q -k "task or record"` → 全绿
- 回滚：`git checkout pre-tenant-dirs -- .` + 用备份还原 `data/`
- 依赖：T-003

---

### T-005 越权拦截

- [ ] 执行
- 目的：把 owner 变成真权限，而非装饰字段。
- 改动点：
  1. `app/deps.py` 新增 `require_meeting_access(task_id, user, need="read"|"write")`
  2. 挂到：会议详情、更新、删除、录音控制、导出
  3. `REQUIRE_AUTH=false` 时直接放行（本地单机）
- 验证：
  1. `REQUIRE_AUTH=false`：全部会议可读写，前端无变化
  2. `REQUIRE_AUTH=true`，用 A 的 cookie 请求 B 的会议详情 → 403，前端显示"无权访问"
  3. 用 A 的 cookie 删除 B 的会议 → 403，磁盘文件仍在
  4. 新增测试 `tests/test_tenant_access.py`，覆盖 read/write 各 2 条
- 回滚：移除依赖挂载。
- 依赖：T-001、T-003

---

### T-006 录音会话实例化（最大件，拆 4 小步）

- [ ] T-006a 抽类，行为零变化
- [ ] T-006b 会话注册表
- [ ] T-006c 隔离验证
- [ ] T-006d 孤儿清扫适配

- 目的：解除 `core/audio_stream.py` 的进程级单例，这是 SaaS 的第一块地基。
- 为什么必须拆：`_stream_process` 等 12 个模块变量（`audio_stream.py:41-65`）意味着第二个用户开录会直接覆盖第一个用户的进程句柄。

#### T-006a 抽出 `RecordingSession` 类（行为零变化）
- 改动：把 12 个模块变量收进 `RecordingSession` 实例属性；模块级函数保留为薄包装，委托到 `_default_session`
- 验证：
  1. 前端录 30 秒 → 正常出转写
  2. `pytest tests/test_record_sentinel_contract.py -q` → 全绿
  3. 差异对比：录音产物 WAV 时长与改动前同量级（±2%）
- 回滚：单 commit

#### T-006b 会话注册表
- 改动：新增 `sessions: dict[str, RecordingSession]`；`start/stop/pause/resume` 接受 task_id，从注册表取实例；无 task_id 时走默认实例（兼容）
- 验证：
  1. 前端单场录音全流程不变
  2. 停止后 `sessions` 为空，无残留线程（日志无 `stream` 线程）
- 回滚：单 commit

#### T-006c 隔离验证
- 改动：无新增业务代码，补 `tests/test_recording_sessions.py`
- 验证（诚实说明：一台机器只有一个麦克风，物理上无法真实双录）
  1. 单测：用 fake ffmpeg（monkeypatch `subprocess.Popen`）起 2 个 session，断言进程句柄、读线程、回调队列互不共享；停 1 个不影响另 1 个
  2. 真实环境回归：单场录音 30 秒仍正常
  3. 真实多并发留到 M1 的容器编排验证
- 回滚：测试可保留

#### T-006d 孤儿清扫适配
- 改动：`_exit_cleanup_stream` 与启动清扫从"单个进程"改为遍历 `sessions`
- 验证：起 2 个 fake session 后强制退出 → 两个 ffmpeg 都被清理，`ps aux | grep ffmpeg` 无残留
- 回滚：单 commit
- 依赖：T-001（取当前用户）

---

### T-007 M0 出口验收

- [ ] 执行
- 一次性验证清单：
  1. `REQUIRE_AUTH=false` 启动 → 前端所有页面可用，会议 811 条，录音/上传/转写/纪要全流程正常
  2. `REQUIRE_AUTH=true` 启动 → 未登录 401 且前端跳登录；登录后仅见自己会议
  3. 新建会议 → task json 含 `owner_id`，落在 `data/users/{uid}/tasks/`
  4. 新建/删除/导出 → `data/audit/` 各 1 条记录
  5. 跨用户访问 → 403
  6. 本地能力已接口化：`app/routers/record*.py` 无 `core.audio_stream` 直连；`projects.py` / `workspace.py` 无 `subprocess.Popen`；AST 守护测试通过
  7. `pytest tests/ -q` 全绿；`cd frontend && npx vue-tsc --noEmit` 零错误
- 出口标准：以上 7 条全过，打 tag `m0-tenant-base`

---

## 5. M1 托管版（任务简表）

| 编号 | 任务 | 改动点 | 验证 | 状态 |
|---|---|---|---|---|
| T-101 | 存储抽象层 | 新增 `core/storage.py`：`StorageBackend` 接口 + `LocalBackend`；录音读写走接口 | 前端录音/播放不变；切 backend 由配置控制 | [ ] |
| T-102 | 对象存储后端 | 实现 `S3Backend`（MinIO 兼容）；上传/下载/签名 URL | 上传一场会议，文件落 MinIO；前端播放走签名 URL | [ ] |
| T-103 | 音频转 Opus | 录音完成后转码，原 WAV 按策略保留/删除 | 一场 30 分钟会议 WAV 115MB → Opus 约 6MB | [ ] |
| T-104 | worker 编排 | `deploy/worker/`：一场会议一个进程，任务队列派发 | 起 10 场并发上传，全部完成，互不干扰 | [ ] |
| T-105 | 声纹库隔离 | `speakers.json` / `voiceprint_registry.json` 移入用户目录 | 两个账号声纹互不可见 | [ ] |
| T-106 | 注册流程 | 邮箱/手机验证码注册 + 自动建用户目录 | 新用户注册 → 目录自动生成，首场会议可跑 | [ ] |
| T-107 | 计费接入 | usage 写实时用量；超额拦截 | 模拟超额 → 转写接口返回 402，前端提示升级 | [ ] |
| T-108 | edition 门控 | 前端 `useEdition()` + 后端 edition 配置，控制入口显隐与路由注册 | personal 构建下 SaaS 入口不存在，SaaS 路由返回 404；saas 构建下全部可见 | [ ] |
| T-109 | M1 出口 | 浏览器全流程免安装 | 干净浏览器：注册→上传→转写→纪要→导出 | [ ] |

---

## 6. M2 本地桥（任务简表）

| 编号 | 任务 | 改动点 | 验证 | 状态 |
|---|---|---|---|---|
| T-201 | bridge 骨架 | 独立可执行 `bridge/`，出站 WS 连云端，心跳+重连 | 断网 10 秒重连，云端显示在线 | [ ] |
| T-202 | 录音下沉 | 录音从服务端迁到 bridge，按云端指令启停 | 云端点录制 → 本机出声，云端出转写 | [ ] |
| T-203 | 目录代理 | 白名单目录的 list/read/preview，按 task 授权 | 云端访问非白名单路径 → 拒绝 | [ ] |
| T-204 | IDE 代理 | `launch_ide` / 打开 Finder 经 bridge 执行 | 云端点「在 IDE 打开」→ 本机 IDE 启动到正确目录 | [ ] |
| T-205 | 瘦身 | 本地引擎依赖移出默认安装，改可选插件 | 全新机器安装包体积 < 100MB，安装 < 30 秒 | [ ] |
| T-206 | M2 出口 | 新机器端到端 | 新机器装完 → 录音/工作区/IDE 全可用 | [ ] |
| T-207 | 全量只读镜像 | 单机：应用内「打开全量工作区」直接用 `_preview`；SaaS：按空间打包 → bridge 落到 `~/OMS/{space}/` → 只读 → 生成 `_SYNC.md`；按 `updated_at` 增量 | IDE 内搜某决策关键词命中 3 场以上历史会议；镜像内改文件后同步被覆盖并提示；镜像内无音频文件 | [ ] |

T-207 约束（按 D8）：

1. 只同步当前用户有权的空间，路径带 `space_id`，禁止跨空间平铺
2. 目录只读；需要修改走现有「导入 IDE 改动」，不在镜像里直接改
3. 每个空间根生成 `_SYNC.md`：同步时间、会议数、版本号
4. 索引复用 [context_export.py](core/cli_engine/context_export.py)，不另写同步逻辑
5. 音频不进镜像；纪要内的音频引用指向云端签名链接，过期可刷新
6. 增量按 `updated_at`，整包只在首次或索引损坏时触发

---

## 7. M3 协作（任务简表）

| 编号 | 任务 | 改动点 | 验证 | 状态 |
|---|---|---|---|---|
| T-301 | 空间成员模型 | `SpaceMember(space_id, user_id, role)`，role ∈ owner/editor/viewer；空间内会议全成员可见（D10） | 邀请成员后即可见空间内全部会议；viewer 只读，editor 可写 | [ ] |
| T-302 | 权限中间层 | `require_space_access(space_id, user, need)`；只判空间角色，不判会议级 | viewer/editor/owner 对读与 5 个写接口各跑一遍，403/200 全符合 D10 | [ ] |
| T-303 | 共享链接 | 生成/撤销/过期；匿名只读；默认整场会议 | 撤销后旧链接 404；过期后 403 | [ ] |
| T-304 | 实时广播 | 转写流按会议广播给多连接 | 两个浏览器同看，延迟差 < 1 秒 | [ ] |
| T-305 | 工作区语义 | 按 D5：默认不可见 + 显式发布只读快照 | 未发布时成员看不到工作区 tab | [ ] |
| T-306 | 私产移入空间 | 「移入空间」动作 + 审计留痕 + 旧链接重定向；不留副本 | 个人空间会议移入后仅团队可见；审计有 1 条记录；原 URL 跳转新位置 | [ ] |
| T-307 | M3 出口 | 双人协作演示 | 两人同看、编辑冲突提示、链接撤销、移入空间 | [ ] |

---

## 8. M4 组织与合规（任务简表）

| 编号 | 任务 | 改动点 | 验证 | 状态 |
|---|---|---|---|---|
| T-401 | 组织模型 | `Org` / `OrgMember` / 项目归属 | 组织内成员互见项目，跨组织不可见 | [ ] |
| T-402 | SSO | OIDC 接入 + SCIM 预留 | 用测试 IdP 登录成功 | [ ] |
| T-403 | 审计查询 | 审计列表页 + 筛选 + CSV 导出 | 按人/时间/动作筛出正确记录 | [ ] |
| T-404 | 数据生命周期 | 留存策略、删除请求、导出个人数据 | 删除请求执行后 30 天内数据不再可查 | [ ] |
| T-405 | 席位账单 | 按席位计费 + 发票信息 | 模拟 5 席位账单金额正确 | [ ] |
| T-406 | M4 出口 | 安全问卷演练 | 逐项给出证据链接 | [ ] |

---

## 9. 前端逐项验证矩阵

每个阶段都必须能在 UI 上单独点出来，不需要读日志。

| 能力 | 入口 | 预期 |
|---|---|---|
| 登录拦截 | 关 cookie 刷新任意页 | 跳登录页 |
| 会议归属 | 会议卡片 | 仅自己会议 |
| 越权提示 | 直接访问他人会议 URL | 403 提示页 |
| 录音隔离 | 录制页 | 不出现"设备被占用"以外的异常 |
| 共享入口 | 会议详情 → 分享 | 生成链接、角色选择 |
| 成员可见性 | 成员视角打开会议 | 工作区 tab 隐藏（未发布） |
| 审计 | 设置 → 审计日志（M4） | 列表可按时间筛 |
| 配额 | 状态栏 | 剩余时长 + 超额拦截提示 |

M0 阶段前端**不应有任何新入口**。若出现，说明改动了现有行为，需回退。

---

## 10. 风险与回滚

| 风险 | 触发点 | 缓解 |
|---|---|---|
| 数据迁移丢文件 | T-004 | 先备份 + tag；迁移脚本幂等；报告失败数 |
| 录音回归 | T-006a~d | 每小步一个 commit；录 30 秒人工回归 |
| 接口过度抽象 | T-000 | 只做 3 个接口，不预留未使用能力；AST 守护只禁直连，不限制内部实现 |
| 鉴权误伤 | T-001/T-005 | 开关默认 false；灰度到 true 才生效 |
| 审计写盘阻塞 | T-002 | 失败只 warning，不抛 |
| 并发模型选错 | D1 | 已定按会议分 worker，不共享进程 |

---

## 11. 进度看板

| 编号 | 状态 | 验收人 | 提交 | 备注 |
|---|---|---|---|---|
| T-000a | [ ] | | | |
| T-000b | [ ] | | | |
| T-000c | [ ] | | | |
| T-001 | [ ] | | | |
| T-002 | [ ] | | | |
| T-003 | [ ] | | | |
| T-004 | [ ] | | | |
| T-005 | [ ] | | | |
| T-006a | [ ] | | | |
| T-006b | [ ] | | | |
| T-006c | [ ] | | | |
| T-006d | [ ] | | | |
| T-007 | [ ] | | | |

M1 起沿用同一看板格式，进入阶段时再展开。

---

## 12. 待拍板事项

以下不定就无法进入对应阶段，暂不排入任务清单。

| # | 事项 | 影响阶段 | 选项 |
|---|---|---|---|
| Q4 | 数据可移植契约 | M1 | 建议 M1 先定导出格式，导入后置 |
| Q5 | M1 服务器规格与存储后端 | M1 | 现有 47.116.10.194（2C4G）只够演示 |
