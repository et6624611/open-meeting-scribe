# AGENTS.md — AI 协作约定

给在此工作区干活的 AI / 新人。目标：低成本对齐全局、不制造矛盾信息、决策可追溯。

## 开工前先读（渐进式加载）

1. `CODEX.md` —— **第一入口**，模块速查 + 按任务类型加载路径（124 行）
2. 按任务类型读对应文件（见 CODEX「按任务类型加载」表）
3. 如需完整规范 → `MISSION.md` + 本文件 + 对应层文档

## 单一事实源（改哪、不改哪）
| 内容 | 唯一文档 | 规则 |
|------|----------|------|
| 架构 / 模块 / 数据流 | `docs/ARCHITECTURE.md` | 改架构先改这里 |
| 云服务器部署 / 运维 | `docs/DEPLOYMENT.md` | 服务器信息、端口、更新流程、API 路径 |
| DashScope API 约束 / 字段 | `docs/API_CONTRACTS.md` | 代码注释只引用，不复述 |
| 重大决策 | `docs/adr/` | 新增一篇；旧决策作废标 `Superseded`，不删不改 |
| 版本施工步骤 | `MVP_PLAN.md` | 当前版本怎么做 |
| 迭代痕迹 | `CHANGELOG.md` | 每次功能迭代追加一条 |
| 需求 / 路线 / 界面 | `docs/PRD.md` `ROADMAP.md` `design/ui-spec.md` | 产品视角 |

## 硬约束（不可违背，细节见 API_CONTRACTS.md）
- 转写 API **只认公网 URL**；本地 / 内录文件先上传 DashScope 临时存储换 `oss://` URL。
- `oss://` URL 必须走 **RESTful API** + 请求头 `X-DashScope-OssResourceResolve: enable`（SDK 不支持）。
- 说话人分离**仅支持单声道** → ffmpeg 强制下混单声道。
- 临时存储单文件 **≤1GB / 48h**；URL 含空格或中文**必须 URL 编码**。

## 代码规范
- 语言：Python 3.11+（独立 venv，不用系统 3.14）
- 密钥：只从 `.env` 读，**禁止硬编码 / 入库**
- 注释 / 文档 / 提交信息：中文
- 目录：`core/` 放管线逻辑，`app/` 放服务与前端，`tests/` 放测试

## 架构原则
- **server.py 轻量化**：`app/server.py` 仅做 app 创建与 router 注册（<100 行），不含业务逻辑；新功能一律加在 `app/routers/` 下对应文件
- **共享状态集中**：跨路由共享状态（tasks 字典、实时状态等）统一放 `app/store.py`，各 router 通过 import 引用
- **async/sync 边界**：含阻塞操作（subprocess、time.sleep、同步 HTTP）的端点用 `def`（FastAPI 自动线程池化）；纯异步 I/O 端点用 `async def`
- **冒烟测试兜底**：每个功能域至少一个冒烟测试覆盖关键路径（`tests/test_smoke.py`）；新增端点必须补充对应测试

## 禁区
- **不 `git commit` / `push`，除非用户明确要求**
- v1 不下载 / 引入本地大模型（纯云）
- 不改 MISSION「本地优先」的长期定位（云只是 v1 捷径）

## 收尾清单
- [ ] 更新 `CHANGELOG.md`
- [ ] 若涉架构 / 契约 / 决策 → 同步对应 docs（必要时新增 ADR）
- [ ] 若涉界面 → 更新 `docs/design/ui-spec.md`
