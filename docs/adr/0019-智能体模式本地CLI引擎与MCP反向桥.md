# ADR-0019 智能体模式：本地 CLI 工程化引擎与 MCP 反向工具桥

- 状态：Implemented（2026-09-25 Phase 0–3 落地并实测）
- 日期：2026-09-25
- 决策人：Yongliang Wang（裁决 D1 正交、D3 写路径、D5 会话持久化默认开）
- 相关：PROPOSAL-QODER-CLI-ENGINE、SPIKE-QODER-CLI-ENGINE（均存内部归档）、[ADR-0001](0001-mvp走云方案.md)、[ADR-0008](0008-ai操作结果系统校验.md)、[ADR-0012](0012-ASR转写走云端代理.md)、[ADR-0015](0015-本地优先原则重定义与引流授权服务.md)、[ADR-0017](0017-agent角色系统从硬编码提示词到md工作区.md)、[ADR-0018](0018-本地可选计算引擎与声纹离线化.md)、[ADR-0020](0020-工程化能力收敛退役自建Agent循环.md)（后继：自建 agent_loop 退役，本文背景中的 `core/agent_loop.py` 已不存在，工具实现迁至 `core/agent_tools/impl.py`）

## 背景

AI 对话面板的工程化能力此前全部软件内自建：`core/agent_loop.py` 的 ReAct 循环工具集仅覆盖 task/项目数据读写，无法做真正的文件级/多步/代码级工作；上下文靠 `_build_chat_context_blocks` 手工拼进巨型 prompt；结构化输出靠文本正则后处理提取（脆弱）；会话记忆靠前端截最近 10 条、无跨轮持久化。在单体应用里继续堆叠"沙箱执行 + 文件编辑 + 多步规划 + 上下文管理"，本质是重造一个 Coding Agent 的轮子，维护重且偏离主业（会议智能）。

同时验证（qodercli 1.1.53）：本机 Qoder CLI 已具备被程序化无头调用的完整接口（`-p --output-format stream-json`、`--append-system-prompt`、`-w/--add-dir`、`--session-id/-r`、`--permission-mode`、`--mcp-config`）。而会议转写/纪要/决策/说话人映射/项目知识库恰是软件独占、CLI 自身拿不到的数据资产。

由此形成"分工组合"设想：**软件=上下文环境提供方，CLI=工程化会话引擎**。

Phase 0 Spike（7 项假设全部实测）产出三条强制修订，直接塑造本决策：
- **M1**：`-p` 模式 text 为整段 block 非逐 token → 打字机效果需软件侧合成。
- **M2**：无头模式 `--permission-mode default` 静默拒绝且 `permission_denials` 为空、`--allowed-tools` 对内置 Write 不生效 → 授权必须前置为 permission-mode 档位映射。
- **M3**：读边界是权限门（软件层）非 chroot（物理层），生产必用免审批档位 → workspace 必须物理迁出含 settings.json 的 `data/` 树。

## 选项

1. **软件内自建完整 Agent 框架**（补文件工具/沙箱/规划器）——优点：单一进程、无外部依赖；缺点：重造轮子、与主业偏离、维护成本最高。**否决**。
2. **把 CLI 塞成第四种 access_mode**（与 local/hosted/byok 并列）——优点：复用路由骨架；缺点：制造"智能体与传输通道互斥"的错误心智，污染 AccessModeCards 三卡，且 access_mode 语义是 LLM/ASR 传输通道，与"面板能力开关"不是一回事。
3. **正交引擎维度 + MCP 双向桥（选定）**——`chat_engine` 独立命名空间（默认关闭），面板三态模式 pill；上下文走工作区文件，结构化回写走软件自建的本地 MCP Server 反向调用软件受控 API。优点：能力正交、概念清晰；写操作复用既有落盘/审计/状态同步入口而非自由写文件；缺点：多 CLI 子进程 + MCP 桥一层间接；分发依赖用户本机已登录 CLI（故只能非默认）。

## 决定

采用**选项 3**，并落地为四个组件：

1. **适配层 `core/cli_engine/`**：声明式 manifest（`manifests/qoder-cli.json`）+ probe 探针 + context_export 上下文序列化 + event_bridge（stream-json→规范 SSE，含打字机合成、按 `tool_use_id` 配对、`result.is_error` 判成败、`error_code=118` 额度专项映射）+ runner（每轮一进程、独立进程组、真取消）。路由输出 `engine_id` 而非布尔位，为未来第二引擎留形。
2. **引擎维度正交（D1）**：`data/settings.json` 新增 `chat_engine` 命名空间，与 `access_mode` 完全独立；`core/routing.py` 不改动。面板模式 pill「⚡问答 / 🧭自动 / 🤖智能体」，`auto` 走 `intent.py` 规则分流且结果**始终经 `engine_route` 事件可见回显**（不静默分流）。
3. **授权前置为档位映射（M2）**：三档编译为 `--permission-mode`——`readonly`→`dont_ask`+disallowed、`workspace_write`→`accept_edits`、`full_task`→`auto`；`default` 档与 `--allowed-tools` 前置授权路线（对内置工具）废弃。`--dangerously-skip-permissions` 一律不用。
4. **MCP 反向工具桥（结构化回写）**：`mcp-bridge/server.py`（零依赖 stdio JSON-RPC）经 HTTP 回连本机 `/api/agent-tools/invoke`（`app/routers/agent_tools.py`）。每轮由服务端签发**进程内短时 bearer 令牌**（`core/agent_tools/tokens.py`，TTL 15min、用后即撤、绝不落盘/入 settings.json），mcp-config 落系统临时目录 0600 用后即删。读工具复用 `core.agent_loop.execute_tool`，写工具复用 `app.routers.notes` 既有函数（继承 `save_task_to_disk`+脏标记），并落 `logs/audit.log` 语义审计。
5. **会话与数据边界**：CLI `session_id` 由 `chat_session_id`（面板标签）优先派生，与面板会话对齐；同标签多轮自动 `-r` 延续（D5 默认开），workspace 按 `retention_days` 启动清扫（M3/R7）。

## 后果

- 正面：AI 面板获得真正的文件级/多步/跨会议工程化能力而不自建 Agent 框架；结构化回写从"文本正则"升级为"工具调用直出"，可靠性质变；模型消耗走用户个人 Qoder 账号（本软件成本减负）；写路径单一、可审计、可回退。
- 负面：① 依赖用户本机安装并登录 CLI（探针失败自动回退内置问答，且功能默认关闭，不破坏"零配置即用"）；② 分钟级任务击穿原"秒级无状态"前端假设，已配套真取消、路由回显、执行轨迹与产物区；③ stream-json 属 CLI 内部协议，版本升级可能漂移——以最低版本探针 + 宽容解析 + 契约样本测试（`tests/test_cli_engine.py` 内联真实样本）缓解。
- 后续需注意：① 会话恢复 UX 已前后端打通，但 CLI session 文件被 retention 清理后 `-r` 为 best-effort，未来可加“恢复失败自动重建上下文”兜底；② ~~Phase 3 未做“删除面板会话标签→联动清理 workspace”~~ ——已实现：工作区改以 `chat_session_id` 为键（与 CLI 会话对齐），新增 `/api/agent-tools/cleanup` 端点，前端删除会话标签即联动清理（仅删本软件 `agent-workspace/` 内目录，防穿越；CLI 自身会话存于 `~/.qoder` 属外部域不触碰）；③ 多 CLI 引擎（Claude Code/Codex/Gemini）适配层为防腐设计非开放平台，新增引擎=一份 manifest+一个 parser，不开放用户自带 adapter（D8）。
