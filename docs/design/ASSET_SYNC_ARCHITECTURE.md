---
title: "会议纪要两层存在形式与同步架构方案"
description: "将纪要收敛为机器可读 SSOT（任务 JSON + sidecar）与资产化工作区两种存在形式；data/output 导出降级为按需临时下载产物；定义单向投影 + 提案式回流的同步契约、冲突判定、迁移路径与分阶段落地计划。"
tags: ["architecture", "sync", "workspace", "single-source-of-truth", "migration"]
created_at: "2026-11-11"
updated_at: "2026-11-11"
version: "1.1.0"
author: "wangyongliang"
status: "review"
category: "design"
related_docs: ["docs/ARCHITECTURE.md", "docs/API_CONTRACTS.md"]
---

# 会议纪要两层存在形式与同步架构方案

> 状态：P0-P3 已实施（待验收），P4 收尾中。所有「现状」结论均经代码核验，附文件与行号；
> 无法核验处显式标注「待确认」。
>
> **实施备注（2026-11-11）**：
> - P0-P3 已落地，回归见 `tests/test_asset_sync_p0~p3.py`（38 例）。
> - **docx 临时缓存位置修正**：原设计拟用 `data/downloads/`，核验发现该目录已被
>   自建分发服务占用（`app/server.py` L492-511 按文件名对外服务），改放
>   `data/output/{task_id}_{ts}_纪要.docx`，启动 sweep 与任务删除联动清理。
> - 回流冲突判定采用 manifest 双 hash（`hash`=投影正文 / `base_hash`=投影时 SSOT
>   定稿基线），notes 域 F 用含头部声明的完整 body 与投影同口径，避免误报。
> - Q1-Q6 按推荐项执行：外部改写仍走提案确认；Web 侧取消 md 落盘（CLI `-o` 保留）；
>   投影默认开启（`feature_flags.asset_projection`）；知识库副本不合并、不传播删除。

## 0. 术语对齐与前提修正

- **机器可读版**：`data/tasks/{task_id}.json` 及 `.formal.json` / `.insights.json` /
  `.joblog.jsonl` / `.rewrites.jsonl` / 板旁路等 sidecar。程序侧结构化数据。
- **同步能力**：两侧保持同步的能力——任一侧新增/变更/删除后，另一侧可靠跟上。
- **前提修正（重要）**：现状不是三层，而是**四种并列存在形式**。除任务 JSON、
  `data/output/` 导出 md、知识库同步副本外，**资产化工作区已经存在**：
  `agent-workspace/_preview/`（`core/cli_engine/context_paths.py` L41-49），
  按项目/日期/标题/短 ID 组织，含 `context/summary.md` 等带 frontmatter 的文件、
  `output/` 可写区、`AGENTS.md` 与 `.oms/` 机器索引，且**已有回流入口**
  `import_from_workspace`（`core/cli_engine/context_export.py` L531-583）。
  因此本主张的实质是：**把 `_preview` 升格为唯一资产层并补全同步契约，
  把 `data/output/` 降级为按需临时产物，把知识库副本定位为单向出口投影**。

## 1. 结论与推荐架构（先读这里）

1. **唯一真相源（SSOT）= 任务 JSON + sidecar**，维持不变。
   `summary`（AI 原稿）核心不可变：仅流水线生成与说话人姓名替换可写；
   一切编辑落 `user_summary`；定稿口径统一为 `task_final_summary()`
   （`core/chat_context.py` L67-78：`user_summary is not None` 即优先）。
2. **`data/output/` 的 md 退化为纯按需生成的临时下载产物**（推荐），
   不收敛为资产文件夹内的派生产物。理由：
   - 资产层已有 `context/summary.md`（定稿口径、跟随更新）。再放一份
     「纪要+原始对话稿」md 会制造**两份需互相同步的人可读纪要**，
     与「不应有并列第三种形式」的主张自相矛盾。
   - 下载件的内容口径（附全量逐字稿、交付用途）与资产文件（定稿基线、
     工作用途）本就不同，混放会污染资产目录契约。
   - 按需从 SSOT 渲染可**顺带消灭已核验的过期下载缺陷**（见 §2.3 G1/G2）。
   - API 契约（`/api/download/{task_id}?format=md|docx`）与文件名规则不变，
     前端零改动；产物可清理、不参与同步、不进资产索引。
3. **同步 = 单向投影（JSON → 资产文件夹，自动、幂等、始终新鲜）
   + 受控提案回流（文件 → JSON，用户确认后才落盘）**。
   不做对称双向自动同步。理由：纪要原文不可变是硬约束；提案通道
   （`propose_summary` / `import_from_workspace`）已实现且经受过事故复盘；
   符合洞察板「容错不降级」口径（非法/冲突整批拒绝，不落半截状态）。
4. **知识库副本保留为「面向用户目录的单向出口投影」**：用户拥有该目录，
   内容按 `content_types` 裁剪，只推不拉。它与 `_preview` 共享渲染器但
   不合并——在契约层面只有两种存在形式（SSOT + 资产层），出口投影是
   资产层的派生行为，不是独立存在形式。

```
                 ┌────────────────────────────────────────────┐
                 │  SSOT: data/tasks/{id}.json (+sidecars)    │
                 │  summary(不可变原稿) / user_summary(编辑层) │
                 └──────┬──────────────────────────▲──────────┘
        单向投影(自动、幂等、hash 锚定)│              │提案回流(用户确认才落盘)
                 ┌──────▼──────────────────────────┴──────────┐
                 │  资产层: agent-workspace/_preview/…        │
                 │  context/*.md(只读派生) + output/(可写区)   │
                 └──────┬─────────────────────────────────────┘
        出口投影(单向、裁剪、手动/脏标记)│      按需渲染(临时、可清理)
                 ┌──────▼─────────────┐   ┌────────────────────┐
                 │ 用户知识库文件夹    │   │ /api/download md/docx│
                 │ (用户拥有,不回流)   │   │ (data/downloads 缓存)│
                 └────────────────────┘   └────────────────────┘
```

## 2. 现状盘点（全部经代码核验）

### 2.1 各层写入 / 读取 / 删除链路

**A. 机器可读层（data/tasks/）**

| 环节 | 位置 | 事实 |
|---|---|---|
| 纪要落库 | `core/pipeline_runner.py` L635-637, L676 | stage2 后写 `summary`/`title`/`output_path`，`save_task_to_disk` |
| 原子持久化 | `core/task_store.py` L83-95 | `atomic_write_json` 写 `{id}.json`，剔除 `transcription` |
| 用户编辑 | `core/notes_service.py` L74-80 | `update_summary` 只写 `user_summary` + `mark_modified`（L52-54 设 `last_modified_at`），**不触碰 summary 与 output_path** |
| 定稿读取 | `core/chat_context.py` L67-78 | `task_final_summary`：`user_summary is not None` 即优先（含空串） |
| 说话人替换 | `app/routers/speakers.py` L340-371 | `summary` 与 `user_summary` 分别原地替换姓名（保留用户编辑） |
| AI 写回快照 | `core/rewrite_snapshots.py` L1-44 | `.rewrites.jsonl`；summary target = `user_summary` 字段级；强制快照、每 target 20 版、可按轮恢复 |
| 删除 | `app/routers/tasks.py` L483-540 | `remove_task` + `_purge_task_artifacts`（best-effort，启动孤儿清理兜底） |

**B. 导出层（data/output/）**

| 环节 | 位置 | 事实 |
|---|---|---|
| 生成写入 | `core/pipeline.py` L295-307 → `core/summarize.py` L435-468 | `save_summary`：纪要 + `## 附：原始对话稿`（全量逐字稿）；文件名 `{音频stem}_{时间戳}_纪要.md` |
| 唯一重写点 | `app/routers/speakers.py` L373-381 | 说话人绑定后重写（display = user_summary 优先）；**用户编辑纪要不重写** |
| md 下载 | `app/routers/tasks.py` L402-428 | `FileResponse(output_path)`，直接服务落盘文件 |
| docx 下载 | `app/routers/tasks.py` L430-444 → `core/docx_export.py` L109-122 | **优先读落盘 md**，回退 `task["summary"]`（非定稿口径） |
| 删除 | `app/routers/tasks.py` L526-531 | md + 伴生 docx 一并 unlink |
| 重转写重置 | `app/routers/tasks.py` L589-590 | `output_path=None` 但**不删旧文件** |

**C. 知识库副本（用户文件夹）**

| 环节 | 位置 | 事实 |
|---|---|---|
| 目标解析 | `core/projects.py` L191-212 | 每文件夹 `sync_enabled`/`sync_content_types`（默认 summary+action_items）/子目录默认 `OpenMeetingScribe` |
| 内容渲染 | `core/projects.py` L215-316 | frontmatter（meeting_id/title/date/participants/…）；纪要取 `user_summary or summary`（**空串语义，与定稿口径不一致**） |
| 写入 | `core/projects.py` L326-381 | `{日期}_{标题}_自动纪要.md` 覆盖写；成功后 `last_synced_at` 落库 |
| 触发 | `core/pipeline_runner.py` L686-698；`app/routers/speakers.py` L382-386；`app/routers/tasks.py` L830-854 | 首次完成自动推 / 绑定后推 / 手动按钮 |
| 脏检测 | `app/routers/tasks.py` L757-792 | `is_dirty = last_modified_at > last_synced_at`（字符串比较） |
| 删除/改名 | 无 | 任务删除**不删**知识库副本；标题变更后下次同步写新文件名，**旧文件遗留**（task 只存 last_synced_at，无已同步路径清单） |

**D. 资产工作区（agent-workspace/_preview/）——已存在的第四形式**

| 环节 | 位置 | 事实 |
|---|---|---|
| 根与命名 | `core/cli_engine/context_paths.py` L41-49, L80-86 | `BASE_DIR/agent-workspace/_preview`；会议目录 `YYYY-MM-DD_标题__短ID8`；项目目录 `项目名__短ID`；独立会议 `_standalone/` |
| 目录迁移 | `context_paths.py` L122-144, L218-241 | 标题/日期变化惰性改名；旧 UUID 目录迁移；`_merge_dir_into` 只搬缺失项绝不覆盖 |
| `_migrate_meeting_dirs` 真实模块 | **`core/cli_engine/context_index.py` L266** | `context_export.py` L28 import 再导出；测试 `tests/test_workspace_ide_scope.py` L6 的 `ce` = `core.cli_engine.context_export`（聚合入口，`__getattr__` 延迟转发到 context_paths/context_render/context_index） |
| 投影写入 | `core/cli_engine/context_export.py` L296+；`context_render.py` L50-72 | `context/{transcript,summary,notes,insights,history}.md` + `decisions.json`，frontmatter 锚点 `task_id/meeting_title/generated_at/source/version`；**普通 write_text，非原子** |
| 投影触发 | `app/routers/workspace.py` L259-271, L138-147, L189-224 | 进会议页 `GET /preview`（前端 `generatePreview`）/ 手动 refresh / open-ide（**meeting scope 只补 IDE 规则不重导出**，L210-212） |
| 回流 | `context_export.py` L531-583；`workspace.py` L150-160；`frontend/src/composables/useWorkspace.ts` L137+ | `import_from_workspace`：只解析 summary.md/notes.md；frontmatter `task_id` 不匹配拒收；body ≠ 定稿基线 → 返回 `{baseline, proposed}` 走 propose diff 卡，用户接受才经 `PUT /summary` 落盘 |
| AI 写通道 | `core/agent_tools/catalog.py` L99-142 | `propose_summary`/`propose_notes`（persists=False，提案式唯一通道）；`update_summary` 已弃用；授权档 readonly/workspace_write/full_task（`core/settings_store.py` L283-298） |
| 清理 | `context_paths.py` L178-215；`app/server.py` L659-664 | `cleanup_workspace` 只清引擎会话工作区；启动 sweep（retention_days 默认 7）**只清 `<engine>/<task>` 两层与快照，不触碰 _preview**；任务删除**不清理 _preview 会议目录** |

**E. 基础设施与旁证**

- 原子写：`core/fs_atomic.py` L41-73，同目录 tmp + fsync + os.replace；
  **仅进程内 threading.Lock，无跨进程锁**。
- 文件监听：requirements.txt / pyproject.toml **无 watchdog/inotify 依赖**
  （已核验）；现状变更检测 = 按需 import + mtime 返回。
- 功能开关：`core/settings_store.py` L316-343 `feature_flags`，
  `workspace_explorer` 默认 True 闸门全部工作区端点。
- 重命名/归档：`app/routers/tasks.py` L668-710（title/date/project 变更设
  `last_modified_at`）；L795-827 归档仅设 `archived_at`，无文件动作。
- `_backup_20261028` / `_backup_20261103`：目录存在于 data/，但全库 Python
  代码无 `_backup` 生成路径（已核验）→ **推断为手工备份，待确认**；本方案不触碰。
- 既有同步经验：洞察板「容错不降级」（非法操作整批丢弃、revision+1、409 并发守卫）；
  后端落盘产物「双通道同步」（tool 事件信号 + `?meta=1` revision 轮询、
  document.hidden 节流）——本方案复用后者做外部变更探测。

### 2.2 职责重叠结论

- 纪要正文存在 **4 份人可读副本**（output md、知识库 md、_preview summary.md、
  前端渲染），其中只有 _preview 与知识库跟随用户编辑（且知识库有空串语义偏差），
  output md 完全冻结 → 同一内容三种新鲜度。
- 「定稿口径」已有收口函数 `task_final_summary()`，但 docx 回退、知识库渲染
  两处未收口（G2/G3）。
- 回流与提案基础设施齐备（import_from_workspace + propose_summary + 快照恢复），
  缺的是：**投影侧的自动触发与 hash/revision 锚点、回流侧的冲突判定**。

### 2.3 已核验缺陷清单（收敛的直接动机）

| # | 缺陷 | 证据 |
|---|---|---|
| G1 | 用户编辑纪要后下载 md/docx 仍是旧版（编辑不写回 output md） | notes_service L74-80 无 output_path 写；speakers L373-381 是唯一重写点 |
| G2 | docx 回退读 `task["summary"]` 而非定稿口径 | docx_export.py L118 |
| G3 | 知识库渲染 `user_summary or summary`（空串回退）≠ 定稿 `is not None` | projects.py L292 vs chat_context.py L75-78 |
| G4 | retranscribe 重置 output_path 不删旧 md → 孤儿文件 | tasks.py L589-590 |
| G5 | 任务删除不清理 `.formal.json` / `.rewrites.jsonl` | tasks.py L534 后缀列表 + task_store purge_board_files L218-231 范围 |
| G6 | open-ide meeting scope 不重导出，工作区可能过期 | workspace.py L210-212 |
| G7 | 知识库同步无改名追踪：标题变更后旧文件名文件遗留 | projects.py L342-347；task 无已同步路径记录 |
| G8 | 无跨进程写锁（设计约束） | fs_atomic.py L26-38 仅 threading.Lock |

## 3. 目标模型定义

### 3.1 SSOT 归属与不可变性

- 唯一真相源：`data/tasks/{id}.json` + sidecars。资产文件全部是派生物，
  可随时由 SSOT 重建（refresh 端点已存在）。
- `summary`（AI 原稿）写入方**仅限**：流水线 stage2、说话人姓名原地替换。
  用户编辑 → `user_summary`；外部 AI 改写 → 提案 → 用户接受 → `user_summary`
  （经 rewrite_snapshots 强制快照，可按轮恢复）。原稿永远可回退 = 保底项。
- 定稿口径全局收口 `task_final_summary()`（P0 修复 G2/G3 后无例外）。

### 3.2 资产文件夹目录契约（沿用现有实现，不另起炉灶）

```
agent-workspace/_preview/
├── AGENTS.md / _INDEX.md / _DECISIONS.md / .oms/index.json   # 全局（已有）
├── <项目名>__<短ID8>/                                        # 项目级（已有）
│   ├── .oms/meetings.json                                    # 机器索引（已有）
│   └── <YYYY-MM-DD>_<标题slug>__<短ID8>/                     # 会议级（已有）
│       ├── AGENTS.md / related.md / <IDE规则文件>            # 已有
│       ├── .oms/projection.json                              # ★新增：投影清单
│       ├── context/                                          # 只读派生区
│       │   ├── summary.md / transcript.md / notes.md
│       │   ├── insights.md / history.md / decisions.json
│       └── output/                                           # 外部可写区（已有）
└── _standalone/…                                             # 独立会议（已有）
```

- 命名与迁移规则维持 `context_paths.py` 现状（日期_标题__短ID、惰性改名、
  孤儿归档「未识别会议__短ID」）。**锚点一律走 frontmatter `task_id` 与
  `.oms/` 索引，禁止靠文件名反解**（短 ID 仅用于目录定位，已有 `_find_meeting_dir`）。
- frontmatter 在现有 `_base_meta`（task_id/meeting_title/generated_at/source/version）
  基础上**新增**：`content_hash`（正文 sha256）、`content_rev`（任务内容版本号）、
  `projection: "readonly"`（context 区标记）。

### 3.3 结构化字段 → 文件映射表

| SSOT 字段 | 资产文件 | 权限 | 回流 |
|---|---|---|---|
| `summary` + `user_summary`（定稿口径） | `context/summary.md` | 只读派生 | 提案回流 → `user_summary`（已实现） |
| `dialogue`（清理版渲染，40k 截断标记） | `context/transcript.md` | 只读派生 | 否（逐字稿不可变；书面版走 .formal.json 专用通道） |
| `user_notes` | `context/notes.md` | 只读派生 | 提案回流 → `user_notes`（已实现） |
| `decisions` | `context/decisions.json` + 上级 `_DECISIONS.md` | 只读派生 | 否（决策写走 update_decision_node 工具面，避免双写通道） |
| `.insights.json` | `context/insights.md` | 只读派生 | 否（洞察走板工具面） |
| `.formal.json` | **不投影** | — | —（避免制造第二份可编辑逐字稿基线；书面版仅在应用内消费） |
| `.joblog.jsonl` / `.rewrites.jsonl` | 不投影 | — | —（运行痕迹，非会议内容） |
| 外部 AI 自由产物 | `output/**` | 外部可写 | 不自动回流；用户可显式取用 |

### 3.4 投影清单 `.oms/projection.json`（新增契约）

```json
{
  "task_id": "5cdf8150-…",
  "content_rev": 12,
  "projected_at": "2026-11-11T10:00:00",
  "files": {
    "context/summary.md": {"hash": "sha256:…", "rev": 12},
    "context/transcript.md": {"hash": "sha256:…", "rev": 9}
  },
  "errors": {}
}
```

用途：幂等跳过、回环判定、冲突三方比对的「投影基线」记录。

## 4. 同步机制设计（核心）

### 4.1 方向：单向投影 + 受控提案回流

- **JSON → 文件：自动单向投影**。触发即增量重投影，始终新鲜。
- **文件 → JSON：仅提案回流**。外部改动永远不直接落 SSOT；经
  `import_from_workspace` → propose diff 卡 → 用户接受 → 受控写服务
  （notes_service）→ 快照。这是「纪要原文不可变」与「用户是主人」口径的必然选择。
- **删除语义不对称（明确约定）**：
  - SSOT 删除 → 资产会议目录删除（应用拥有 _preview，P2 补上，现状缺失）。
  - 资产文件被外部删除 → **不传播为数据删除**（派生物可再生）；探测到缺失
    即重投影补回，并在 joblog 留痕。
  - 知识库副本删除 → 不传播（用户拥有）；任务删除也不删知识库文件（维持现状）。
- **用户编辑 vs 外部 AI 改写同时发生的优先级**：应用内用户编辑永远优先。
  外部文件只是提案素材；提案基线取**当前**定稿值，若投影后 SSOT 又变过，
  提案卡标「冲突」，由用户裁决，绝不自动三方合并。

### 4.2 冲突判定（三方 hash 决策表）

记 S = SSOT 定稿正文 hash，P = manifest 记录的投影 hash，F = 文件实际正文 hash：

| 情形 | 判定 | 动作 |
|---|---|---|
| F == P，S == P | 无变化 | 跳过（幂等） |
| F == P，S != P | 仅 SSOT 变了 | 正常投影更新文件与 manifest |
| F != P，S == P | 纯外部改动 | 生成提案（baseline=S，proposed=文件 body） |
| F != P，S != P | 双侧改动冲突 | 生成提案并标 conflict；baseline 取 S 当前值；用户接受/拒绝裁决 |
| frontmatter task_id 不匹配 | 拒收 | 维持现状（import_from_workspace L563-565） |
| manifest 缺失（旧工作区） | 降级为现状行为 | body ≠ 定稿基线即提案；首次投影后补齐 manifest |

防回环：投影写入后 manifest.hash == 文件 hash，import 见 F==P 一律判「无外部
改动」——即使此时 S 已前进（那是待投影，不是外部编辑）。mimeType/换行差异
通过「正文规范化后 hash」（strip 尾部空白、统一 \n）吸收。

### 4.3 触发点

| 事件 | 现状钩子 | 目标动作 |
|---|---|---|
| 纪要生成完成 | pipeline_runner L676-698 | 投影 + 知识库首推（现有） |
| 应用内编辑（纪要/随记/决策/注入） | notes_service.mark_modified L52-54 | **收口为唯一脏标记入口**，挂投影（增量） |
| 说话人绑定替换 | speakers.py L370-386 | 同上（替换 summary/user_summary 后投影） |
| 重命名/改日期/改项目 | update_task L707-710 | 目录惰性改名（现有）+ 重投影 + manifest 更新 |
| 归档/取消归档 | tasks.py L795-827 | manifest 标 archived；**不移动文件**（保护外部引用） |
| 任务删除 | _purge_task_artifacts L500-540 | 追加删除 _preview 会议目录 + 补清 .formal/.rewrites（G5） |
| 提案被接受 | PUT /summary → notes_service | 走 mark_modified 同一钩子，无特殊路径 |
| 外部文件改动 | 无自动探测 | 懒探测（进会议页/打开工作区树/点导入）+ 可选 meta 轮询 |
| CLI 引擎写回 | workspace_write 授权档 | 引擎只读 context/、可写 output/；结构化写回只走 propose 工具面（现状维持） |

### 4.4 变更检测手段取舍

- **权威判据 = 内容 sha256**；mtime 仅作廉价预过滤（mtime 未变跳过读文件）。
  不用 mtime 做权威：外部工具保留 mtime 写入、时钟漂移、同步盘都会破坏它。
- **不引入 watchdog**：依赖不存在（已核验）、PyInstaller 打包与跨平台
  （macOS FSEvents/Windows ReadDirectoryChangesW）成本高、且同步盘场景事件不可靠。
- 采用**事件驱动 + 懒探测 + 可选低频轮询**：投影由写入事件触发；外部改动在
  用户进入会议页/工作区视图时扫一次（每会议 6 个小文件，成本可忽略）；
  如需「开着会即时感知」，复用洞察板已验证的 `?meta=1` revision 轮询模式
  （10s、document.hidden 节流），列为 P3 可选项。
- revision：task 新增单调 `content_rev`（mark_modified 时 +1），随 frontmatter
  与 manifest 传播，供前端/轮询做廉价比对。

### 4.5 工程健壮性

- **幂等**：hash 相等跳过写入；同一 rev 重复投影零副作用。
- **防回环**：§4.2 的 F==P 规则；投影与回流共用 manifest 单一事实。
- **原子写**：`context_render._write_md_with_meta` 从 write_text 升级为
  `fs_atomic.atomic_write_text`（现有设施）；manifest 用 atomic_write_json。
- **并发**：per-task threading.Lock + content_rev CAS（投影前读 rev，写后校验）。
  跨进程遵循**单写者约定**：只有服务进程投影；CLI 引擎与外部 IDE 不写 context/。
  fs_atomic 无跨进程锁（G8）——若未来多实例部署需另加文件锁，本期不做（待确认
  桌面端是否保证单实例）。
- **部分失败（容错不降级口径）**：单文件要么完整写入要么不写（原子保证）；
  某文件失败 → manifest.errors 记录 + joblog 留痕 + 整体标 dirty 待重试，
  **绝不把半截批次标为已同步**；失败不阻断主链路（与现有同步 try/except 口径一致）。
- **增量与性能**：逐文件 hash 比对，仅变更文件重写；transcript 最大 40k 字符
  （现有截断），hash 成本可忽略；全量重建（refresh）仅作兜底。
- **备份与可恢复**：投影物无需备份（SSOT 可重建）；AI 写回有 .rewrites.jsonl
  快照（现有，20 版/按轮恢复）；SSOT 自身维持 atomic_write_json。
  `_backup_*` 目录不触碰。

## 5. 兼容与迁移

### 5.1 下载链路（API 契约不变）

- `GET /api/download/{id}?format=md`：改为从 SSOT 按需渲染
  （新纯函数 `render_minutes_md(task)` = 定稿纪要 + 原始对话稿附录，
  复用 save_summary 的渲染逻辑），`Response` 直接返回，不落盘。
  文件名规则不变（`{音频stem}_{时间戳}_纪要.md` 或沿用 task 记录）。
- `format=docx`：`export_task_docx` 改为基于 `task_final_summary()` 渲染，
  产物写 `data/downloads/`（目录已存在），按 retention 清理。
- 存量 `output_path` 字段：保留可读（旧任务删除清理仍用），新任务不再写。

### 5.2 存量 data/output/ 文件

- 停止新增（Web 管线）；**cli.py transcribe -o 保留文件输出**（CLI 场景文件即交付物）：
  `run_pipeline_stage2` 增加 `emit_file: bool = True` 参数，pipeline_runner 传 False。
- 存量文件：任务删除时照旧清理；可选启动 sweep（文件 mtime 超 retention 且
  对应任务存在 → 删除，因可随时按需再生）。不主动批量删除，避免惊扰用户。
- `_backup_*`：不触碰（推断手工备份，待确认）。

### 5.3 开关、灰度与回滚

- 新增 `feature_flags.asset_projection`（默认 True，投影增强）；
  下载按需渲染属缺陷修复，不设开关。
- 灰度：flag off = 投影行为退回现状（进页面导出 + 手动 refresh/导入），
  下载修复不受影响。回滚 = 关 flag，无数据结构破坏（manifest/frontmatter
  新增字段均为 additive，旧代码忽略）。
- 已安装客户端：目录结构只增不改；settings.json 前向兼容（ff.get 缺省默认）；
  知识库同步行为完全不变（本期不动其触发模型）。

## 6. 落地计划（可独立验收）

### P0 缺陷修复与口径收口（独立可发布）
- 改：`core/docx_export.py`（回退用 task_final_summary，G2）；
  `core/projects.py` L292（改 `is not None` 语义，G3）；
  `app/routers/tasks.py` `_purge_task_artifacts`（补 `.formal.json`/`.rewrites.jsonl`，G5）；
  retranscribe 重置前 unlink 旧 md/docx（G4）。
- 测试：pytest 单测——空串 user_summary 的定稿/知识库/docx 三处口径一致；
  purge 覆盖全部 sidecar；retranscribe 后旧文件不存在。
- 验收：G1-G5 中除 G1（P1 解决）外全部关闭，回归无副作用。

### P1 下载按需化（消灭第三形式）
- 新增：`core/minutes_render.py`（纯函数 render_minutes_md；单测覆盖附录/截断/空稿）。
- 改：`app/routers/tasks.py` download 端点；`core/docx_export.py`（读 SSOT，
  产物落 data/downloads）；`core/pipeline.py` run_pipeline_stage2 增 emit_file；
  `core/pipeline_runner.py` 传 False；`app/routers/speakers.py` L373-381 重写块移除。
- API 契约：URL/参数/文件名不变；响应内容口径变为「定稿 + 附录」（修复 G1，
  需在 CHANGELOG 明示）。
- 测试：编辑纪要后下载 md/docx 含编辑内容；Web 任务完成后 data/output 无新增；
  cli.py transcribe 仍产出文件；旧任务（有 output_path）下载同样新鲜。
- 验收：data/output 不再是任何读路径的依赖。

### P2 投影增强（单向同步自动化）
- 新增：`core/cli_engine/projection.py`（manifest 读写、hash/rev、增量投影、
  per-task 锁）；task 字段 `content_rev`。
- 改：`context_render._write_md_with_meta`（原子写 + frontmatter 新字段）；
  `notes_service.mark_modified`（收口脏标记 + 挂投影；合并 routers 侧
  `_mark_modified` 重复实现）；`pipeline_runner`/`update_task`/archive/删除钩子；
  `_purge_task_artifacts` 追加 _preview 会议目录清理。
- 测试：幂等（重复投影零写入）、增量（只写变更文件）、改名跟随、删除清理、
  部分失败标 dirty 不标 synced、原子写崩溃恢复（tmp 不残留）。
- 验收：应用内任何编辑后，不点刷新，工作区文件即与定稿一致。

### P3 回流冲突判定（双向同步闭环）
- 改：`import_from_workspace`（三方 hash 决策表 + conflict 标记 + 规范化 hash）；
  `app/routers/workspace.py` import 响应增 `conflict` 字段；
  前端 `useWorkspace.importChanges` / propose diff 卡冲突徽标（i18n 双语）。
- 可选：`GET /api/workspace/meta?task_id=`（revision 轮询，复用板模式）。
- 测试：§4.2 决策表四象限 + task_id 拒收 + manifest 缺失降级 + 防回环
  （投影后立即 import 判无变化）。
- 验收：外部 IDE 改 summary.md → 应用提示提案；双侧同改 → 冲突卡用户裁决；
  任何路径下 summary 原稿不被外部改动直接覆盖。

### P4 收敛与清理
- 存量 output sweep（可选开关）；`feature_flags.asset_projection` 默认固化；
  更新 docs/ARCHITECTURE.md、docs/API_CONTRACTS.md、CHANGELOG；
  移除 speakers 残留兼容代码与 output_path 写路径。
- 验收：全库无「读 data/output 作为内容来源」的路径（cli -o 除外）。

## 7. 风险与开放问题（需拍板）

| # | 问题 | 推荐 | 理由 |
|---|---|---|---|
| Q1 | 允许外部 AI 直接改纪要正文并自动回流？ | **否**，维持提案+确认 | 原文不可变保底；propose 通道已实现并经事故复盘；自动回流无法与用户编辑安全合并 |
| Q2 | 彻底取消 md 落盘导出？ | **Web 侧是**；CLI `-o` 保留 | Web 下载按需渲染更新鲜且零维护；CLI 场景文件即交付物 |
| Q3 | 投影同步默认开启？ | **是**（flag 默认 True） | 本地、廉价、可重建、可关；回流仍手动确认，知识库同步仍显式 opt-in |
| Q4 | 知识库副本与 _preview 合并？ | **否**，共享渲染器、目标分离 | 用户目录归用户（裁剪内容、不回流）；合并会引入跨所有权同步难题 |
| Q5 | 删除/改名传播到知识库？ | 删除**不传播**；改名写新文件、旧文件保留 | 用户资产不自动删；如需改名追踪需存已同步路径清单（可作后续增量） |
| Q6 | 空串 user_summary 语义统一为 `is not None`？ | **是**（P0） | 与前端纪要 Tab/AI 基线逐字节同口径，消除 G3 |

**其他风险**：
- 多进程/多实例写冲突：本期单写者约定兜底；桌面端是否保证单实例**待确认**。
- 外部工具破坏 frontmatter：task_id 不匹配已拒收；hash 字段缺失按「外部改动」
  处理（保守方向，宁可多提案不可漏判）。
- 同步盘（iCloud/微云）延迟与冲突副本：hash 判据天然免疫 mtime 漂移；
  冲突副本文件（如 `summary 2.md`）不在契约文件名内，不参与同步。
- 大逐字稿投影性能：40k 截断 + 增量 hash，实测风险低；refresh 全量兜底。