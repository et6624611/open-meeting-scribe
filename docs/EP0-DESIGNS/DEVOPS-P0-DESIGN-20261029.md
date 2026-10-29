# 企业版 P0 设计方案 —— DevOps 侧（内网私有化交付）

- 作者：DevOps工程师｜日期：2026-10-29｜状态：P0 设计稿，待产品经理汇总入 PRD
- 对应派工单：cmsg_01m63fh4xpe75d04t20w12sge2
- 设计前提（项目方 2026-10-29 裁决，cmsg_01m63fehgb3ewqjd24rgkb14fx）：
  - 双产品线 = 同一套代码、两种打包/交付形态；内网私有化为 P0 主形态，云托管不做
  - 上云边界：仅定稿文本上服务端；音频、API Key、声纹 embedding 不出本地设备
  - 存量单机数据默认归入手机账号 13373013103（初始管理员账号）
  - 账号体系：管理员建号/邀请码，不依赖 SMS/OAuth

## 一、交付物结构：内网私有化 Docker Compose 一键包

现状底座（已核实）：`Dockerfile`（source-only 服务端镜像，CMD 绑 0.0.0.0:8000）、`scripts/deploy.sh`（Ubuntu systemd 一键，含 admin 服务仅绑 127.0.0.1:8001 的边界设计）、`scripts/watchdog.sh`（/健康探活自愈）。P0 将 deploy.sh 的裸机路径收敛为 compose 路径，systemd 裸装降级为备选文档，不再双线维护。

一键包目录结构（新增 `deploy/private/`，随发布产物出包）：

```
deploy/private/
├── docker-compose.yml        # oms-app + oms-proxy(可选) + oms-backup(sidecar)
├── .env.example              # OMS_DATA_ROOT / JWT_SECRET / PORT / TLS_MODE 等
├── oms-offline-install.sh    # 引导脚本：加载镜像 tar → 生成 .env → 起服务 → 打印访问地址
├── images/                   # 仅离线包出现：oms-app_<version>.tar（docker save 产物，含 digest）
├── ca/                       # 仅 HTTPS 模式出现：内置 CA 证书 + 引导脚本（见 §三）
└── README-管理员.md          # 用户向：装在哪、怎么开、怎么给同事访问地址、怎么升级
```

compose 服务划分：
1. **oms-app**：现有 Dockerfile 镜像，`restart: unless-stopped`，数据以 bind mount 挂 `./data`（SQLite + 定稿文本 + 用户命名空间目录，与后端 `DATA_ROOT/users/<user_id>` 方案同层）。admin 后台沿用仅回环监听 + SSH 隧道的既有边界，默认不对局域网暴露 8001。
2. **oms-proxy**：Caddy 单服务，`TLS_MODE=off|internal-ca|custom-cert` 三态开关控制是否启用。选 Caddy 不选 nginx：内置自动 HTTPS/CA 能力（`caddy ca` 本地根证书），配置面最小。
3. **oms-backup**：轻量 sidecar（cron + sqlite3/tar），每日对数据卷做快照并保留轮转，见 §四。

关键工程决策：
- **镜像必须可离线交付**。企业内网常见无出口网络（甚至物理隔离），在线 `docker pull` 不可假设。发布产物 = GitHub Release 附 `oms-private_<version>_linux_amd64.tar.gz`（含 images tar），`load` 而非 `pull`；升级同径。
- **平台承诺范围**：P0 官方支持 = Linux（Ubuntu 22.04/24.04 + Docker Engine）。Windows Server 走 WSL2/Docker Desktop 属可行但不承诺（给出文档、不在验收矩阵），与 deploy.sh 现有 Ubuntu 口径一致。
- 数据根目录与配置全部收敛到 `deploy/private` 同层的命名卷风格路径，升级包不携带 data，天然保护存量。

## 二、管理员初始化向导流程（P0）

配置态与运行态分离：`oms-offline-install.sh` 只做"装起来"，首次"配起来"走应用内向导（前端/UI 的 AdminSetup 流，DevOps 提供状态机后端支持）。

流程（用户向主线："管理员看到什么"）：
1. 管理员在服务器上执行一条安装脚本 → 脚本结束打印 `请在本机浏览器打开 http://localhost:8000 完成初始化`（首启无账号时服务端返回"未初始化"态，仅回环可进配置，避免裸奔期被局域网抢占管理员位）。
2. 向导第 1 步：设置管理员账号（默认建议绑定手机账号 13373013103 作为存量数据归属账号——与裁决④一致，迁移脚本在首个定稿文本写入前提供一次性"认领本机 data/ 存量"选项）。
3. 向导第 2 步：访问方式确认——打印局域网访问地址（自动探测网卡 IP），并复述本条数据治理承诺（只存定稿文本等，供 QA 的"上传知情同意"文案对齐）。
4. 向导第 3 步：建号/邀请码生成，把访问地址发给同事。完成后初始化态锁定，`INITIALIZED=true` 写入环境，对外服务正式开门。

运维兜底：`cli.py` 增加 `admin reset-password`（本机回环执行）作为忘记密码唯一恢复路径，不需要外部短信。

## 三、HTTPS / CA 选型：可降级判断（本派工指定命题）

**结论：在新裁决的边界下，CA 从"P0 功能硬前提"降级为"P0 安全加固项 + P1 前建议完成"。** 理由链：

1. 评审期我判定 HTTPS 是功能性前提，唯一依据是浏览器 getUserMedia 需要 secure context。**裁决③确认录音留本地、本地引擎采集，Web 端不采集麦克风**——该触发条件消失。浏览器在 http + 内网 IP 下可正常完成登录、浏览、编辑文本、下载。
2. 本地引擎 ↔ 服务端的服务间通信不受浏览器 secure context 约束，局域网 http + token 鉴权可工作。
3. 残余风险要说清（不可假装为零）：HTTP 明文下，登录密码、会话 Cookie、定稿文本在内网链路可被同网段抓包窃取/篡改。**内网 ≠ 可信网**（访客 Wi-Fi、IoT 设备、 ARP 欺骗面）。
4. 两个可能推翻降级的核查项（实施期验证，验证前按可降级推进）：
   - 若前端 P0 用到其他 secure-context-only API（crypto.subtle 做本地加密、Service Worker、剪贴板写），HTTP 下会静默失效，需前端确认清单；
   - 若 P1 规划"Web 端快捷录音"等麦克风交互，CA 需求立即回升为硬前提。

三方案矩阵（默认推荐 B，保留 A 为出厂态）：

| 方案 | 内容 | 优点 | 代价 |
| --- | --- | --- | --- |
| A. HTTP 出厂 | 默认 `TLS_MODE=off`，文档明示局域网明文风险 | 零证书运维，P0 最快落地 | 密码/文本可被内网抓包 |
| B. 内置 CA 一键开 | `TLS_MODE=internal-ca`：Caddy 本地根 CA 签发 IP SAN 证书 + `ca/` 目录放根证书与双平台导入脚本（mac 钥匙串 / Win 受信任根） | 一条命令升级加密态，根证书只需每台终端导入一次 | 员工终端需一次性信任操作（可 IT 批量下发） |
| C. 企业自有 CA | `TLS_MODE=custom-cert`：管理员提供企业证书挂入 | 零员工侧操作，合规最优 | 依赖企业已有 PKI，不可普适 |

出厂 A、向导第 2 步内提供"是否现在开启加密访问（推荐）"开关一键进 B，C 留文档位。QA 的验收口径相应拆两条：P0 必须验"HTTP 模式功能完整可用" + "TLS_MODE=B 后全功能回归"，不再把 CA 列为出场 gate。

## 四、数据卷备份与升级回滚

备份（oms-backup sidecar）：
- 每日 `sqlite3 .backup`（在线一致性快照）+ 定稿文本目录 tar，落 `./backups/oms_<date>.tar.gz`，保留 14 天轮转；
- 升级前由升级脚本强制即时备份一次（坏升级=企业数据事故，评审期风险项在此闭环）；
- 备份文件含企业会议文本，文档要求备份目录随数据卷同等保密边界，不外发到云（个人版承诺不反转同款逻辑）。

升级（`oms-upgrade.sh`，管理员一条命令）：
1. 校验当前版本 → 强制备份（§四.1）→ 载入新镜像 tar；
2. 新容器启动前先跑 DB migration（后端提供 `cli.py db migrate`，要求 migration 前向兼容 + 事务化，失败即中止不切流）；
3. `docker compose up -d` 滚动替换，探活 `/healthz` 连续 3 次通过判成功；
4. 升级窗口前后各打印版本号，供项目方/管理员留痕。

回滚（同脚本 `--rollback`）：
- 应用层：切回上一镜像 tag（发布包保留最近 2 个版本 tar）；
- 数据层：恢复升级前强制备份快照。**迁移兼容纪律**：DB schema 变更必须双版本可读（新旧镜像均可读同一库），否则回滚会读不了新 schema——此条写入后端协作契约，是回滚可行性的硬前提；
- 目标值：RPO ≤ 24h（日常）/ 0（升级前强制备份点），RTO ≤ 30min。

运行时健康：/healthz 复用现有 watchdog 探活逻辑移植进 compose healthcheck；日志走容器 stdout + json-file 轮转上限（默认 50MB×5），P0 不引入集中日志栈（P2 审计留存期再评估）。

## 五、对现有单机/个人版的影响（复述边界）

- 个人版 PyInstaller 双平台管线（WP-D/WP-G）**零改动**：新增的 `deploy/private/` 不进入个人版打包产物；
- 双产品线共享源码、分离构建目标：CI 新增企业包 job（compose 文件 + 镜像 build + save tar + 文档，随 Release 产物发布），不动现有冻结冒烟与 R8 打包 job；
- G-7（mac 签名/公证）阻塞状态不受影响：企业版服务端跑 Linux，不依赖 Apple 公证链路；员工侧本地引擎安装包仍受 G-7 凭据前提约束。

## 六、工作量与排期（DevOps 侧）

- compose 包 + 离线安装/升级/回滚脚本：M（1 周级）
- 内置 CA 方案 B（Caddy 配置 + 双平台导入脚本）：S（2-3 天，可在 B 确认后并行）
- 备份 sidecar + 迁移纪律联调：S-M，依赖后端 SQLite 迁移设计定稿
- 总档：M，与评审期结论一致；不与后端 3-4 周关键路径冲突（脚本面可与后端存储迁移并行开发，联调点仅 migration 命令与 /healthz）

## 七、待产品经理裁决的产品问题（用户向语言）

1. **默认加密开关**：装好后同事访问用普通 http（零设置但有内网窃听风险），还是管理员多花 10 分钟给员工电脑装一次"企业信任证书"换全程加密？我的建议：出厂 http、向导里显著推荐一键开加密（方案 B）。这需要产品决定"向导问不问、怎么问"。
2. **断网/隔离内网是否必须支持**：若目标客户存在完全无外网的内网，我按本文档离线 tar 交付执行（略增包体与发布流水线工作）；若都可联网，可在线拉镜像简化发布。请确认目标客户画像。
3. **Windows Server 装企业版是否承诺**：P0 建议只承诺 Linux（现有部署脚本同源），Windows Server 出文档不出口径。若项目方有明确 Windows 企业客户，请裁决是否升为验收项。
4. **备份保留与外带策略**：默认本机保留 14 天、禁止外发云备份——是否作为企业版数据治理承诺写入 PRD（与 QA 验收矩阵对齐）。

## 八、与其他角色的契约点

- 后端：`cli.py db migrate` 事务化 + 双版本 schema 兼容（回滚硬前提）；DATA_ROOT 环境变量注入替代相对路径；/healthz 端点。
- 前端：确认 P0 页面是否使用 secure-context-only API 清单（影响 §三降级结论稳固性）。
- QA：§三验收拆条口径 + §四升级回滚用例（坏升级注入演练）纳入 P0 验收标准初稿。
- UI：初始化向导 4 步信息流（§二）需与管理台 MVP 信息架构合并设计，避免两套"管理员第一次看到的页面"。
