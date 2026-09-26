---
title: "SPIKE: Qoder CLI 引擎 Phase 0 七项假设实测结论"
description: "对 PROPOSAL-QODER-CLI-ENGINE §5 Phase 0 的 7 项关键假设逐条实测取证（qodercli 1.1.53 / macOS / 2026-09-25），给出 stream-json 协议形状、权限档位矩阵、MCP 前置授权与读边界可信性结论，并列出对方案的具体修订要求。"
tags: ["spike", "qoder-cli", "agent", "feasibility", "evidence"]
created_at: "2026-09-25"
updated_at: "2026-09-25"
version: "1.0.0"
author: "wangyongliang"
status: "published"
category: "architecture"
related_docs: ["docs/PROPOSAL-QODER-CLI-ENGINE.md", ".spike_qoder/"]
---

# SPIKE-QODER-CLI-ENGINE：Phase 0 实测结论

**结论一句话：7 项假设全部成立，Phase 1 可以开工；但取证发现 3 处必须修订方案的设计（详见 §4）。**

| 项 | 假设 | 结论 |
|---|---|---|
| 1 | stream-json 可映射到现有 SSE 协议 | ✅ 成立 |
| 2 | `--session-id` / `-r` 跨进程会话恢复 | ✅ 成立 |
| 3 | `--mcp-config` 挂载 stdio MCP 并稳定调用工具 | ✅ 成立（需前置授权） |
| 4 | 无头模式权限行为（R8） | ✅ 风险确认，但已有可用解法 |
| 5 | 任意 cwd 拉起 + 相对/绝对路径混合 | ✅ 成立（有路径解析陷阱） |
| 6 | 并行 tool_use / tool_result 可配对 | ✅ 成立 |
| 7 | CLI 读边界可信性 | ⚠️ 是权限门而非物理隔离，成立但有条件 |

- 取证脚本：`scripts/spike_qoder_cli.py`（独立于主程序）
- 原始证据：`.spike_qoder/*.jsonl`（每步 stream-json 原文）+ `.spike_qoder/results.json`
- 环境：qodercli **1.1.53**，macOS，protocol_version **1.4.0**，实测模型 `Qwen3.8-Flash`

---

## 1. stream-json 协议形状（假设 1 ✅）

逐行 NDJSON，每行一个事件，事件类型封闭可枚举：

```
{"type":"system","subtype":"init","apiKeySource":"none","protocol_version":"1.4.0",
 "cwd":"...","tools":[35 个内置工具名],"mcp_servers":[{"name":"spike-ping","status":"connected"}],
 "model":"Efficient","permissionMode":"default","agents":[...],"skills":[...],
 "capabilities":["interrupt_receipt_v1","interrupt_cancel_queued_v1","msg_lifecycle_v1",...],
 "session_id":"39f51d1e-..."}
{"type":"system","subtype":"artifacts_update","artifacts":[]}
{"type":"system","subtype":"hook_started|hook_progress|hook_response", ...}   # SessionStart 钩子噪音
{"type":"assistant","message":{"role":"assistant","content":[
    {"type":"thinking","thinking":"..."} | {"type":"text","text":"..."} |
    {"type":"tool_use","id":"call_xxx","name":"Read","input":{...}}
 ],"usage":{...},"model":"..."},"uuid":"...","session_id":"..."}
{"type":"user","message":{"content":[
    {"type":"tool_result","tool_use_id":"call_xxx","content":"...","is_error":null}
 ]}}
{"type":"result","subtype":"success|error_during_execution","duration_ms":690,
 "is_error":false,"num_turns":3,"total_cost_usd":0,"total_credits":0,
 "usage":{"input_tokens":0,"output_tokens":0,...},"modelUsage":{...},
 "permission_denials":[],"errors":null,"error_code":null,"session_id":"..."}
```

映射到现有 SSE 词汇表的可行性：

| CLI 事件 | 现有 SSE | 说明 |
|---|---|---|
| `assistant.content[].type=="text"` | `token` | ⚠️ **非逐 token**，而是整段 text block（见 §4-M1） |
| `assistant.content[].type=="thinking"` | `stage:thinking` | 可直接映射 |
| `assistant.content[].type=="tool_use"` | `stage:tool_call` + `tool_call` | 携带 `id`/`name`/`input` |
| `user.content[].type=="tool_result"` | `tool_result` | 携带 `tool_use_id`，配对可靠 |
| `result` | `done` | 携带 usage / duration_ms / permission_denials |
| `system:init` | 一次性 `stage` 或 metadata | 可取 tools / mcp_servers / session_id 用于回显 |
| `system:hook_*` / `artifacts_update` | **丢弃** | 噪声事件，宽容解析器需过滤 |

**关键陷阱（实测踩到）**：额度耗尽时 CLI 仍返回 `returncode=0`，失败信号只在事件里：
`result.is_error=true` + `result.subtype="error_during_execution"` + `error_code=118` + `assistant.content[0].text="You've reached your credit usage limit..."`。
→ **判定引擎成败必须读 result 事件，不能读退出码**。

---

## 2. 权限档位实测矩阵（假设 4 ✅，R8 风险确认）

同一个任务：`用 Write 工具把 BETA 写入 <ws>/output/perm.txt`（`-p` 无头模式）

| `--permission-mode` | 结果 | 证据事件 | 证据文件 |
|---|---|---|---|
| `default` | ❌ Write 被拒 | `tool_result.is_error=true`，content=`"Error: Allow writing to ...?"`；**`result.permission_denials=[]`（无结构化信息）** | `step4a_default.jsonl` |
| `dont_ask` | ❌ Write 被拒 | 独立事件 `{"type":"system","subtype":"permission_denied"}` + **`result.permission_denials=[{tool_name, tool_use_id, tool_input, message, decision_reason_type:"mode", tool_denial_kind:"permission-rule"}]`** | `step4b_dontask.jsonl` |
| `accept_edits` | ✅ 写入成功 | `File created successfully at ...` | `step4h_accept_edits.jsonl` |
| `auto` | ✅ 写入成功 | 同上，且 Bash 也放行 | `step4e_auto.jsonl` |
| `bypass_permissions` | ✅ 写入成功 | 同上（全放行，不建议用于生产） | `step4g_bypass_retry.jsonl` |
| `default` + `--allowed-tools Write` | ❌ **仍被拒** | `result.allowedTools` 在 init 事件中为 `None` → 该 flag 在此场景未生效 | `step4d_allowed_tools.jsonl` |

三条结论：
1. **R8 完全成立且比预估更糟**：`default` 档在无人应答时静默拒绝，且 `permission_denials` 为空数组——用户只会看到"它说写不了"，软件拿不到任何可展示的结构化拒绝原因。方案 §3.7-3 原选 `default` **必须废弃**。
2. **`--allowed-tools` 不能作为前置授权手段**（实测 init 事件 `allowedTools:None`）。方案 §3.9-3 的"授权前置卡"需改为 **`permission-mode` 档位映射**而非 allowed-tools 列表（见 §4-M2）。
3. **`dont_ask` 是唯一能拿到结构化拒绝原因的档位**（`permission_denials` 含 tool_name/tool_input/decision_reason）。这为"授权被拒时的可解释提示"提供了技术底座。

另外 `-p` 无头模式下未出现任何挂起/等待输入：CLI 选择"拒绝并继续对话"而非阻塞。**因此不需要担心进程挂死，但必须担心静默失败。**

## 3. 其余假设证据

### 3.1 会话恢复（假设 2 ✅）
| 轮次 | 命令 | 结果 | 耗时 |
|---|---|---|---|
| R1 | `--session-id <uuid>` + "记住这个数字：4287" | 正常应答 | 6.39s |
| R2 | `-r <uuid>` + "我刚才让你记住的数字是多少" | **回答 4287，跨进程恢复成功** | 7.12s |

证据 `step2_round1.jsonl` / `step2_round2.jsonl`。恢复轮无额外冷启动惩罚（两轮耗时相当）。

### 3.2 MCP 挂载与工具调用（假设 3 ✅）
- 零依赖手写 stdio MCP Server（JSON-RPC 2.0：`initialize`/`tools/list`/`tools/call`）即被识别：init 事件 `"mcp_servers":[{"name":"spike-ping","status":"connected"}]`；
- `--strict-mcp-config` 生效：用户账号下 12 个既有 MCP（canva/figma/slack…）被排除，只剩注入的 spike-ping；
- 工具调用成功：`tool_use: mcp__spike-ping__spike_ping` → `tool_result: "SPIKE-MCP-7731"`，11.95s（`step3d_mcp_preauth.jsonl`）；
- **`--permission-mode auto` 可免 MCP 审批**（8.21s，`step3e_mcp_auto.jsonl`）；`default` 档下 MCP 调用同样被静默拒绝（`step3_mcp.jsonl`）。
- 工具全名格式为 `mcp__<serverName>__<toolName>`（Phase 1 中文标签映射表需按此解析）。

### 3.3 路径解析（假设 5 ✅ + 陷阱）
- 从 `cwd=/tmp` 拉起、`-w` 传绝对路径 → 正常（`step5_cwd.jsonl`，31.11s，相对+绝对混读均可达）；
- `--add-dir <绝对路径>` 挂第二目录 → 两目录内容都读到（`step5b_add_dir.jsonl`，40.99s，工作区标记与附加目录标记均命中）；
- **陷阱**：`--mcp-config` 传入相对路径时，CLI 按 **`-w` 目录**而非进程 cwd 解析，导致 `ENOENT`（见 `step3c_mcp_preauth2.jsonl` 的 stderr）。→ Phase 1 所有传入路径必须 `.resolve()` 为绝对路径（与项目已登记的"子进程按 repo 根解析相对路径"已知隐患同源）。

### 3.4 并行工具归属（假设 6 ✅）
要求并行读 3 个文件：一条 assistant 事件内出现 3 个 `tool_use`（各带独立 `id`），随后 3 条 `tool_result` 各带 `tool_use_id`。⚠️ **结果回传顺序与调用顺序不一致**（实测返回顺序为 b→a→c），因此前端/后端配对**必须按 `tool_use_id` 匹配，禁止按数组下标**——正好印证 §3.9-7 对 `useAiChat.ts` 现有写法的怀疑。证据 `step6_retry_dashsep.jsonl`。

### 3.5 读边界（假设 7 ⚠️ 有条件成立）
受控尝试让 CLI 读取 `-w` 之外的两个哨兵文件（兄弟目录 + 无关绝对路径）：
- `Read` 工具**发起了越界调用**，但被权限门拦截，哨兵串未出现在任何输出中（`step7_boundary.jsonl`，两处 grep 命中数均为 0）；
- 模型自述："读取被权限门拦下，需要你在弹窗里点允许…目前没有拿到内容"。

**但这是权限门（软件层），不是 chroot/沙箱（物理层）**：`--permission-mode auto/accept_edits/bypass_permissions` 下同类读取会放行。因此：
- §3.7-1 的"工作区隔离"定性为**缓解措施而非硬边界**（方案原表述过于乐观）；
- §3.10 已预判的"workspace 迁出 `data/`"从"建议整改"升级为**Phase 1 强制要求**——因为生产必然要用免审批档位，届时物理相邻即等于可读。

---

## 4. 对方案的强制修订（Phase 1 实施前生效）

**M1｜打字机效果需自行合成**
`-p` 模式的 `text` 是整段 block 一次性到达（实测一次问答仅 2~6 个 assistant 事件），不是逐 token 流。直映 SSE 会让面板"转圈十几秒后整段砸出"。→ event_bridge 需按字符/词组节流切片推送，或改用 `--input-format stream` 观察是否有增量事件（Phase 1 内二选一验证）。

**M2｜授权前置卡改为"档位映射"而非 allowed-tools 列表**
按 §2 结论，UI 的三个授权档落地为：
| 授权卡选项 | CLI 参数 |
|---|---|
| 只读（默认档） | `--permission-mode dont_ask` + `--disallowed-tools Bash Write Edit` |
| 可写工作区 output/ | `--permission-mode accept_edits` |
| 可执行任务（含 Bash） | `--permission-mode auto` + 显式二次确认 |
`--dangerously-skip-permissions` 一律不使用。`default` 档因无结构化拒绝信息而禁用。

**M3｜workspace 必须物理迁出 `data/`**
按 §3.5，生产档位下 CLI 可读相邻文件。落地路径改为仓库/用户目录下与 settings 树无父子关系的
`agent-workspace/<engine_id>/<task_id>/`（§3.10 已提出，此处确认必须执行），且 `context/` 内只写会话必需内容，禁止复制 settings.json 或其字段。

**其余确认项**
- 传 CLI 的全部路径 `.resolve()`；
- prompt 一律以 `["--", prompt]` 形式置于 argv 末尾（实测中文 prompt 不加 `--` 时偶发未传递，模型报"only system context"）；
- 成败判定读 `result.is_error` / `error_code`，不读退出码；`error_code=118` 需专项映射为"Qoder 额度不足"引导文案；
- 过滤 `system.subtype ∈ {hook_*, artifacts_update}` 噪声事件；
- 工具标签映射按 `mcp__<server>__<tool>` 与内置 35 工具名（含 Write/Bash/Edit/Read/Agent/WebFetch…）建表。

---

## 5. 冷启动与耗时基线（供 D2 决策与超时标定）

| 场景 | 耗时 |
|---|---|
| 纯文本问答（无工具） | 6.4 ~ 7.1s（含冷启动） |
| 单轮工具调用（Read 1 文件） | 13.2 ~ 14.1s |
| 写文件任务（Bash + Write） | 15.0 ~ 19.6s |
| MCP 工具调用 | 8.2 ~ 12.0s |
| 三文件并行 + 双目录（add-dir） | 41.0s |
| SessionStart 钩子固定开销 | ~1.0s（两个钩子，776ms + 168ms） |

→ Phase 1 超时建议：**首事件 60s / 总时长 300s**（远大于现有 60/120s 直连档），并在 stage 事件中持续给出"已执行 N 步"计数（对应 §3.9-6）。
→ D2 裁决：**维持"每轮一进程"**——会话恢复无额外惩罚（6.39s vs 7.12s），常驻进程收益不明确，不作前置投入。

---

## 6. Spike 过程中发现的独立事实（与方案无关，但对项目有用）

1. 本机 Qoder 账号默认模型额度已耗尽（`error_code=118`），`-m Qwen3.8-Flash` 可用；`qoder --list-models` 仅列出 Qwen3.8-Max / Flash 两个模型。任何调用 CLI 的自动化都需要显式 `-m` 或额度兜底分支。
2. CLI 会加载用户全局配置（12 个 MCP、几十个 skills/plugins/agents），init 事件体积约 4KB。集成时应使用 `--strict-mcp-config` + `--setting-sources` 收敛，否则用户环境会污染会议软件的行为（本次 step3 首轮即因全局配置出现额外钩子输出）。

---

*取证时间 2026-09-25。原始样本见 `.spike_qoder/`。下一步：按 §4 修订进入 Phase 1。*
