# OUTPUT-STRUCT-ENGINEERING-PLAN — REQ-OUT-STRUCT-1 存储链路技术方案

- **对应需求**: [REQUIREMENT-AI-NATIVE-OUTPUT-STRUCTURE.md](../REQUIREMENT-AI-NATIVE-OUTPUT-STRUCTURE.md)（REQ-OUT-STRUCT-1，2026-09-24 可排期）
- **文档性质**: 工程技术方案（**仅设计，不动代码、不迁移存量**）。通过后由产品下实施单。
- **Author**: 后端工程师 `a4cdbd0ca795`
- **Date**: 2026-09-24
- **结论速览**:
  1. 三层 schema（L0/L1/L2）字段级定义完成，见 §3；含稳定 ID 目录、说话人映射、版本链、内容层相对路径。
  2. 写入链路改造点收敛为 **1 个新模块 + 6 个既有文件 9 个函数级挂点**，见 §4。
  3. 迁移归并锚点可靠：文件名前 8 位十六进制 = `task_id[:8]`（证据 §2.1），178 个存量文件可 100% 按此归并或进 `_legacy/`，见 §5。
  4. AC-2 可测化定义为「禁目录枚举的 Agent 模拟器 pytest 用例」，见 §6。
  5. 与 WP-G/WP-I 交叠点共 7 处已盘点，实施分支以两者合入 main 为基线前置，见 §7。
  6. 需求书 §3 骨架存在 4 处工程上需产品裁决的松动点，**未自行改设计**，列于 §8。

---

## 1. 设计原则（与需求书约束对齐）

| 需求书约束 | 工程落地含义 |
|---|---|
| 渐进式披露：每层自足 | 上层 JSON 必须携带「是否要加载下层」的全部判据（日期、内容层清单、版本数），且**字段值不依赖读下层才能获得** |
| R2：目录名=稳定 ID | `kb-id` = project.id（uuid4）、`meeting-id` = task_id（uuid4），改名只动 JSON |
| 定稿唯一、旧版下沉 | 引入 `archive/v<N>/`；版本链在 manifest 内闭环 |
| 非目标：不改生成链路与内容格式 | 内容层文件只做**确定性拆分渲染**（从既有 task 字段派生），不新增 LLM 调用（由此产生的 4 个判据缺口 → §8 待裁决） |
| 文件系统即真相源 | 索引与 manifest 是派生物：任何时刻可由 `data/tasks/*.json` 全量重建（rebuild 是迁移与容灾的兜底能力） |

**关键决策 D-1：task JSON 仍是事实源，output 结构是「消费视图」。**
不反向把 JSON/manifest 变成唯一存储。`data/tasks/<task_id>.json`、`<task_id>.insights.json`、`<task_id>.joblog.jsonl` 原位不动；新结构写入时同步刷新索引，损坏可重建。这保证 AC-5（UI 回归）风险最小。

**关键决策 D-2：新增唯一写入口 `core/output_repository.py`（暂名）。**
所有对新结构的写（落盘、归档、索引刷新、manifest 更新）收敛到这一个模块；现有 5 个散点调用方只改「调用谁」。目的：(a) 与 WP-G/WP-I 的交叠面从「行为冲突」降为「挂点合并冲突」；(b) 索引一致性只有一处实现。

---

## 2. 现状证据（file:line 级）

### 2.1 纪要写入与命名（迁移锚点的来源）

| 事实 | 证据 |
|---|---|
| 纪要落盘目录默认 `data/output`（相对路径，随 CWD） | `core/pipeline.py:50`（DEFAULT_CONFIG）→ `core/pipeline.py:263-277`（stage2 第 7 步保存） |
| 文件名 = `<audio_path.stem>_<生成时间戳 YYYYmmdd_HHMMSS>_纪要.md` | `core/pipeline.py:270` |
| 录音音频 stem = `<task_id[:8]>_<录音时间戳>` | `core/audio_recording.py:399`、`:580` |
| 上传音频文件名 = `<task_id[:8]>_<原始文件名>` | `app/routers/tasks.py:98-99` |
| ⇒ **前 8 位十六进制恒为 task_id 前缀**（个别文件含中文标题即上传原件文件名，如 `086b1b62_预算系统调研…_纪要.md`） | 实测 `data/output/` 179 项 |
| 写文件函数 `save_summary(summary, output_path, dialogue)`，对话稿附在纪要尾部 | `core/summarize.py:293-326` |
| `task["output_path"]` 在 stage2 成功后回写 | `core/pipeline_runner.py:518` |

### 2.2 重新生成与「多副本平铺」成因

| 事实 | 证据 |
|---|---|
| 说话人绑定确认后重跑纪要：`POST /api/tasks/{id}/regenerate-summary` → `run_stage2_task` → 新文件名再次落盘 | `app/routers/speakers.py:406-413`；`core/pipeline_runner.py:571-573` |
| 手动「仅重新生成纪要」：先将 `output_path` 置 None 再后台重跑 | `app/routers/tasks.py:350-384`（`:375`） |
| **旧文件不删不归档，成为孤儿** —— 178 平铺文件的直接成因 | 上述两条链路均无旧文件处理；仅任务删除时 unlink（`app/routers/tasks.py:291-293`） |
| 说话人改名走「原地替换」路径，重写既有 `output_path` 文件（不产生新文件） | `app/routers/speakers.py:360-368` |
| 用户编辑纪要存 `task["user_summary"]`，定稿优先取它 | `app/routers/notes.py:64`；`app/routers/speakers.py:365` |

### 2.3 洞察台产物与转写原文

| 事实 | 证据 |
|---|---|
| 洞察消息持久化在 `data/tasks/<task_id>.insights.json`，**不在 data/output**；读取 API 按此路径 | `app/routers/insights.py:73-75`（`_insights_file`），`:78-111` |
| 洞察分析端点（图表/mermaid）返回即止，**不落盘** | `app/routers/insights.py:45-66` |
| 转写原文（dialogue，含句级时间戳）存 `data/tasks/<task_id>.json` 的 `dialogue` 字段（`transcription` 字段被排除） | `app/task_store.py:72-83` |

### 2.4 知识库（project）与会议关联模型

| 事实 | 证据 |
|---|---|
| 项目存储 `data/projects.json`：`{id: uuid4, name, folders[], created_at, updated_at}` | `core/projects.py:25, 76-92` |
| 会议→知识库关联字段 `task["project_id"]`，可后绑/改绑 | `app/routers/import_tasks.py:187` 等；`app/routers/tasks.py:408` |
| 会议显示名 `task["title"]`（改名接口），另有 `audio_name`、`meeting_date` | `app/routers/tasks.py:395-396, 129` |
| 说话人映射两套字段：`speaker_mapping`（id→名）、`speaker_uuid_mapping`（id→声纹 uuid） | `app/routers/speakers.py:348-349` |
| 章节 `task["chapters"]`（结构化 JSON），待办 `task["todos"]`（从纪要解析） | `core/pipeline.py:256-261`；`core/summarize.py:329` |
| 既有「同步到用户文件夹」链路已生成含 front-matter 的会议 md（可复用其渲染逻辑） | `core/projects.py:215-317`（`_build_sync_markdown`、`sync_meeting_to_folders`） |

### 2.5 读取方（AC-5 回归面）

| 消费方 | 依赖 | 证据 |
|---|---|---|
| 纪要下载/导出 | `/api/download/{task_id}` → FileResponse(`task["output_path"]`) | `app/routers/tasks.py:200-219`；前端 `frontend/src/composables/useGeneratingData.ts:259` |
| 任务删除 | unlink `output_path` + 3 个 tasks sidecar | `app/routers/tasks.py:291-296` |
| 存储用量扫描 | 扫 `data/output` 目录 | `app/routers/settings.py:940` |
| 知识库文件夹同步 | 读 task 字段渲染（不读 data/output） | `core/projects.py:324-375` |
| 设置项 `output_dir` | **现状为摆设**：settings 读写它（`app/routers/settings.py:183, 324`），但管线用 DEFAULT_CONFIG，无人把 settings 值传入 `run_pipeline_stage2` 的 config | `core/pipeline.py:88`（cfg 合并）、全仓无调用方传 `output_dir` |

> ⚠️ §2.5 最后一行是实施时必须一并处置的隐性分叉：新结构落地后 `output_dir` 设置要么真正生效（作为新结构根目录），要么从设置页移除，二选一，见 §8-Q5。

---

## 3. 目标结构与 Schema 定义

### 3.0 目录树（根 = `<output_root>`，默认 `data/output/`）

```
data/output/
  index.json                          # L0 全局索引
  <kb-id>/                            # L1 目录名 = project.id（uuid4）；未关联 = "_unassigned"
    index.json                        # L1 会议清单索引
    <meeting-id>/                     # L2 目录名 = task_id（uuid4）
      manifest.json                   # 会议元数据 + 版本链 + 内容层路径
      summary.md                      # L3 定稿纪要（user_summary 优先，否则 summary）
      chapters.md                     # L3 章节/要点（由 task["chapters"] 确定性渲染）
      decisions.md                    # L3 决策与待办（渲染源见 §8-Q1）
      transcript.md                   # L4 转写原文（由 task["dialogue"] 渲染，含句级时间戳）
      insights/
        messages.json                 # 洞察台对话记录（迁移复制，见 §8-Q3）
      archive/
        v1/                           # 历史版本整组快照（内容与定稿同名）
          summary.md
          manifest.snapshot.json      # 归档当时的 manifest 快照
        v2/ …
  _legacy/                            # 迁移期：无法归类的存量文件（仅迁移写入）
  _migration_report.json              # 迁移执行报告（非结构本体，可重生成）
```

命名硬约束：
- `<kb-id>` / `<meeting-id>` 只用 uuid4 小写带连字符（文件系统安全）；`_unassigned`、`_legacy` 为保留名，project/task 的 uuid 不会碰撞。
- 版本目录 `v<N>` 的 N 与 manifest `version_chain` 数组下标+1 一致，从 1 起。
- 所有 JSON 一律 UTF-8、`\n`、经 `core/fs_atomic.atomic_write_json` 原子写。

### 3.1 L0 `index.json`

```json
{
  "schema_version": 1,
  "generated_at": "2026-09-24T15:02:11+08:00",
  "root_schema": "oms.output.index.v1",
  "stats": { "kb_count": 2, "meeting_count": 5 },
  "knowledge_bases": [
    {
      "kb_id": "8f4c…uuid",
      "display_name": "预算项目",
      "path": "8f4c…uuid/index.json",
      "meeting_count": 2,
      "latest_meeting_date": "2026-09-22"
    },
    {
      "kb_id": "_unassigned",
      "display_name": "未关联知识库",
      "path": "_unassigned/index.json",
      "meeting_count": 3,
      "latest_meeting_date": "2026-09-21"
    }
  ]
}
```

字段准则（渐进式披露判据）：Agent 读本文件即可回答「哪个库、有没有近期会议」，无需进 L1。`display_name` 与 `data/projects.json` 的 `name` 最终一致（改名链路见 §4.3）；project 已删除但目录残留时，`display_name` 以最后一次索引值为准并置 `"stale_name": true`。

### 3.2 L1 `<kb-id>/index.json`

```json
{
  "schema_version": 1,
  "kb_id": "8f4c…uuid",
  "display_name": "预算项目",
  "updated_at": "2026-09-24T15:02:11+08:00",
  "meetings": [
    {
      "meeting_id": "d2b4…uuid",
      "title": "预算系统调研与编制逻辑讨论",
      "meeting_date": "2026-09-05",
      "created_at": "2026-09-05T09:17:08+08:00",
      "duration_seconds": 1435.2,
      "attendee_count": 4,
      "one_line_summary": "确认预算编制以项目为主线，Q4 前完成模板统一。",
      "content_layers": ["summary.md", "chapters.md", "decisions.md", "transcript.md"],
      "has_insights": true,
      "version": 2,
      "manifest": "d2b4…uuid/manifest.json"
    }
  ]
}
```

字段准则：
- `attendee_count` = manifest.speakers 中具名人数（无 LLM 依赖；口径待 §8-Q2 确认）。
- `one_line_summary`：**现状无此数据源**，见 §8-Q2（候选：title 别名 / 纪要首段截断 / 新增 LLM 调用——与需求书非目标冲突故须裁决）。schema 保留字段并允许 `null`，`null` 时 Agent 判据降级为 title+date。
- `content_layers` 只列**实际存在**的文件（如 decisions 判据未过可能缺省），Agent 以此实现「按需加载」。
- `version` = 当前定稿版本号（≥1；重新生成后递增），使「只要最新版」的读者完全无需打开 manifest。

### 3.3 L2 `<kb-id>/<meeting-id>/manifest.json`

```json
{
  "schema_version": 1,
  "meeting_id": "d2b4…uuid",
  "kb_id": "8f4c…uuid",
  "title": "预算系统调研与编制逻辑讨论",
  "title_history": [
    { "value": "086b1b62_预算系统调研与编制逻辑讨论.wav", "set_at": "2026-09-05T09:17:08+08:00" }
  ],
  "meeting_date": "2026-09-05",
  "created_at": "2026-09-05T09:17:08+08:00",
  "duration_seconds": 1435.2,
  "speakers": [
    {
      "speaker_id": 0,
      "display_name": "王强",
      "speaker_uuid": "9e1f…uuid|null",
      "bound": true
    },
    { "speaker_id": 1, "display_name": "Speaker 2", "speaker_uuid": null, "bound": false }
  ],
  "content_layers": {
    "summary":    { "path": "summary.md",    "role": "纪要定稿（L3）" },
    "chapters":   { "path": "chapters.md",   "role": "章节与要点（L3）" },
    "decisions":  { "path": "decisions.md",  "role": "决策与待办（L3）" },
    "transcript": { "path": "transcript.md", "role": "转写原文·句级时间戳（L4）" },
    "insights":   { "path": "insights/messages.json", "role": "洞察台记录（L4）" }
  },
  "current_version": 2,
  "version_chain": [
    {
      "version": 1,
      "generated_at": "2026-09-05T09:41:22+08:00",
      "trigger": "pipeline_auto",
      "archived_to": "archive/v1/",
      "files": ["summary.md", "manifest.snapshot.json"]
    },
    {
      "version": 2,
      "generated_at": "2026-09-05T10:02:47+08:00",
      "trigger": "regenerate_speaker_bind",
      "archived_to": null,
      "files": null
    }
  ],
  "audio_ref": "../../recordings/d2b4d2b4_20260905_091708.wav",
  "task_ref": "../../tasks/d2b4…uuid.json",
  "source": "record|upload|import"
}
```

字段准则：
- `speakers[]` 即说话人映射的落盘形态（合并现状 `speaker_mapping` + `speaker_uuid_mapping` 两字段），Agent 解析 transcript/summary 中 `【姓名】` 前缀时以它为字典。
- `audio_ref` / `task_ref` 为**相对 manifest 所在目录**的相对路径（POSIX 分隔符），录音与 task JSON 均不动（需求书 §4 非目标 4）。
- `trigger` 枚举：`pipeline_auto | regenerate_speaker_bind | regenerate_manual | migration`。
- 版本链语义：`current_version` 指向在位文件；每个被顶替的版本恰有一条 `archived_to` 非空记录。**`archive/v<N>/manifest.snapshot.json` 存归档当时的完整 manifest**，使历史版本自足（AC-3 校验和的根据）。

### 3.4 完整性与演进规则

- 每层 JSON 必含 `schema_version`（整数，从 1 起）。消费端规则：**读到大版本号未知的文件 → 尽力用已知字段，未知字段忽略**；小版本升级只加字段不改语义；破坏性变更才升大版本，且迁移脚本负责重写全部索引。
- 一致性不变量（迁移与运行期共同校验，编码为 §6 的 `validate_structure()`）：
  1. L0 的 `knowledge_bases[].kb_id` 集合 = 根下实际目录集合（排除 `_legacy`、下划线前缀）；
  2. L1 `meetings[].meeting_id` 集合 = L1 目录下实际子目录集合；
  3. manifest.current_version 的内容层文件全部存在，archive 记录与实际目录一一对应；
  4. 每个 `_unassigned` 之外的 kb_id 能在 `data/projects.json` 找到，或带 `stale_name` 标记。

### 3.5 关键样例：一个知识库 · 两会议 · 其中 M1 经历过一次重新生成（验收对照物）

```
data/output/
├── index.json                                  # L0：kb_count=2（本库 + _unassigned）
├── 8f4c1a2e-…-projuuid/                        # L1 目录名 = project.id（uuid4，改名不搬目录）
│   ├── index.json                              # L1：meetings=[M1(version=2), M2(version=1)]
│   ├── d2b4f0c3-…-taskuuid-M1/                 # L2 会议 M1「预算系统调研…」，2026-09-05，已重新生成 1 次
│   │   ├── manifest.json                       # current_version=2；version_chain 含 v1→archive/v1/ 记录（§3.3 样例即此文件）
│   │   ├── summary.md                          # 定稿 = 第 2 版（说话人绑定后重生成）
│   │   ├── chapters.md
│   │   ├── decisions.md
│   │   ├── transcript.md                       # 【王强】[00:01:12-00:01:37] …（句级时间戳）
│   │   ├── insights/
│   │   │   └── messages.json                   # 洞察台记录（§4.3 双写副本）
│   │   └── archive/
│   │       └── v1/                             # 第 1 版（pipeline_auto）整组下沉
│   │           ├── summary.md                  # 旧版纪要原文，字节不改（§5.4-S1 同源约束）
│   │           └── manifest.snapshot.json      # 归档当时 manifest（v1 在位时的完整快照）
│   └── a9e7d1b4-…-taskuuid-M2/                 # L2 会议 M2「ES 系统合同讨论」，2026-09-21，从未重生成
│       ├── manifest.json                       # current_version=1；version_chain 仅一条且 archived_to=null
│       ├── summary.md
│       ├── chapters.md
│       ├── decisions.md
│       └── transcript.md                       # 无 insights/、无 archive/ —— 目录按需存在，Agent 以 manifest 为准
├── _unassigned/
│   └── index.json                              # 未关联知识库的会议（含 M3…）
└── _legacy/                                    # 仅迁移期存在（§5.1-R4）
```

该样例即 §6.1 夹具的完整版；三处判据对照：(a) 读 L1 即可知 M1 有 2 个版本且只需在位文件；(b) M1/M2 的 `meeting_date` 使「近 7 天」过滤不下钻即可完成；(c) 任何重新生成都不在 `<meeting-id>/` 顶层留下第二个 `summary.md`。

---

## 4. 写入链路改造点盘点（文件 + 函数级）

> 图例：🆕 新建 · ✏️ 修改 · ✔️ 只读确认无需改。本表即实施单的拆分工单依据。

### 4.1 新建：`core/output_repository.py`（唯一写入口，D-2）

| 接口 | 职责 |
|---|---|
| `OutputRepository.output_root() -> Path` | 解析根目录（收编 `store.OUTPUT_DIR` / settings `output_dir`，见 §8-Q5） |
| `finalize_meeting_output(task_id) -> Path` | 定稿落盘：渲染 4 个内容层 → 写/替换定稿 → **旧定稿整组下沉 archive/v\<N\>** → 回写 manifest → 刷新 L1/L0 |
| `rename_meeting(task_id, title)` / `rename_kb(kb_id, name)` | 只改 manifest/L1/L0 的显示名，不搬目录（R2 裁决） |
| `bind_project(task_id, kb_id)` | 会议跨库移动：整目录 `<old_kb>/<id>/` → `<new_kb>/<id>/`，两侧 L1 + 全局 L0 刷新 |
| `delete_meeting_output(task_id)` | 删除会议目录 + 索引刷新（替代现状裸 unlink） |
| `rebuild_all_indexes()` | 从 `data/tasks/*.json` + 磁盘实况全量重建 L0/L1/manifest（真相源兜底，D-1） |
| `validate_structure() -> list[Issue]` | §3.4 不变量 1-4 机器校验 |

### 4.2 纪要定稿落盘（主链路）

| # | 文件:行 | 函数 | 现状 | 改造 |
|---|---|---|---|---|
| 1 | `core/pipeline.py:263-277` | `run_pipeline_stage2` 第 7 步「保存」 | 拼平铺文件名 + `save_summary` | ✔️ **保留函数不动**（管线纯函数性），但落盘调用改为可选：新增 config 开关或直接保留（见 #2 收敛策略） |
| 2 | `core/pipeline_runner.py:424-549` | `_run_stage2_for_task` | `:518` 回写 `output_path`；无归档 | ✏️ 在 `save_task_to_disk` 后追加 `OutputRepository.finalize_meeting_output(task_id)`（try/except 尽力而为，失败只记 joblog 不阻塞——对齐 `speakers.py:360-373` 既有容错风格）；`output_path` 语义改为指向新结构内定稿文件 |
| 3 | `core/summarize.py:293` | `save_summary` | 纪要+对话稿合并写 | ✔️ 保留给 pipeline 内部与知识库同步复用；渲染分层的函数放 `core/output_repository.py`（复用 `core/projects.py:_build_sync_markdown` 的 front-matter 渲染经验） |

**收敛策略**（避免大范围动管线）：#1 的平铺写与 #2 的分层写**先共存一个迭代**——finalize 以 task JSON 字段（`summary/user_summary/dialogue/chapters/todos/title/project_id/speaker_*_mapping/meeting_date/audio_duration`）为输入，输入齐备，与 pipeline 内部写互不依赖。实施单第二小步再移除 #1 平铺写。

### 4.3 重新生成 / 改名 / 绑定 / 洞察（事件→索引动作映射表）

| 事件 | 现状挂点（file:line · 函数） | 索引/归档动作 |
|---|---|---|
| 说话人确认后重跑纪要 | `app/routers/speakers.py:406` · `regenerate_summary()` | 走 #2 同一 finalize → 版本链 +1，旧版下沉 archive |
| 手动仅重新生成 | `app/routers/tasks.py:350-384` · `retry_summary_only()`（`:375` 置 output_path=None） | 同上；**删除孤儿文件**的隐式行为改为 finalize 显式归档 |
| 说话人改名原地替换 | `app/routers/speakers.py:360-368`（含 `:296` 注释所述链路） | **不升版本**（内容微调非重生成）：重写定稿 4 层 + manifest.speakers[]；`save_summary` 直写替换为 repo 的 `rewrite_current_version()` |
| 用户编辑纪要 | `app/routers/notes.py:64`（写 `user_summary`） | 不升版本：重写 summary.md（定稿= user_summary 优先，与 `speakers.py:365` 口径一致） |
| 会议改名 | `app/routers/tasks.py:395-396` | `repo.rename_meeting()`：manifest.title + title_history + L1 |
| 会议换绑/首绑知识库 | `app/routers/tasks.py:408`；`import_tasks.py:187` 等 | `repo.bind_project()`：目录移动 + L0/L1 刷新（**迁移前置于 `_unassigned/` 的会议换绑即触发此路径**） |
| 洞察消息保存 | `app/routers/insights.py:94` · `save_insight_messages()` | 双写：源文件 `data/tasks/*.insights.json` 不动（读取 API 零改动，AC-5 低风险），复制一份到 `insights/messages.json` + manifest 置 `has_insights`（若 §8-Q3 裁决为「实移」则改此行为单写） |
| 任务删除 | `app/routers/tasks.py:291-296` · `delete_task()` | 裸 unlink → `repo.delete_meeting_output()`（保留 sidecar 清理逻辑） |
| 知识库删除 | `core/projects.py:108` · `delete_project()` | repo 新增 `retire_kb(kb_id)`——语义待 §8-Q4 裁决 |
| 知识库改名 | `core/projects.py:95` · `update_project()`（`app/routers/projects.py:194`） | `repo.rename_kb()`：L0 display_name |
| 存储用量扫描 | `app/routers/settings.py:940` | ✔️ 递归统计自动兼容新结构，仅需确认排除 `_migration_report.json` |

### 4.4 读取方（AC-5 回归面，预期零改动或极小改动）

- 前端只消费 `/api/tasks*` JSON 字段与 `/api/download/{task_id}`（`useGeneratingData.ts:259`），不感知磁盘路径 → ✔️ 零改动，前提是 `output_path` 字段继续回写真实路径（§4.2 #2）。
- `/api/download`（`tasks.py:200-219`）→ ✔️ FileResponse 按路径工作，零改动。
- `core/projects.py` 知识库同步链路 → ✔️ 与 output 结构正交，零改动。

---

## 5. 存量迁移脚本设计（本单只设计，不执行）

**载体**：`scripts/migrate_output_structure.py` + 回归测试 `tests/test_migrate_output_structure.py`。
**入口**：`python -m scripts.migrate_output_structure --dry-run [--root data/output] [--report <path>]`；去掉 `--dry-run` 才是执行模式。幂等：重复执行自动跳过已迁移项。

### 5.1 归并映射规则（R6 规则链，按序短路）

```
输入：data/output/*.md 全部文件
预载：data/tasks/*.json → { task_id[:8] → task } 内存字典（哈希8位全局唯一性预检见 §5.3-S2）

R1  文件名匹配 ^([0-9a-f]{8})_.*_\d{8}_\d{6}_纪要\.md$ 且前缀命中 task 字典
    → meeting_id = task.task_id；kb_id = task.project_id 或 "_unassigned"
R2  前缀命中 task 但时间戳段解析失败（上传原件名异形）→ 同上归并，
    generated_at 以文件 mtime 代替，报告标 "ts_inferred": true
R3  前缀未命中，但 task 字典中存在 audio_name/stem 全等反查命中 → 归并，标 "by_filename_reverse": true
R4  以上皆失败 → data/output/_legacy/<原文件名>（原件不改名，保证可逆）
```

### 5.2 版本归并与 archive 下沉

同一 meeting 命中多文件时：
1. 按文件名生成时间戳（缺则 mtime）升序排 `f1 … fn`；
2. **`task["output_path"]` 指向的文件 = 定稿**（权威判据；现状每次重生成必回写，§2.1）；
3. 若 `task["output_path"]` 文件不存在或为空（重生成失败态），取时序最新者为定稿，报告标 `"fallback_head": true`；
4. 其余每个文件 → `archive/v<N>/<原角色文件名>`，N 按时序自 1 编号；定稿即 `current_version = n`；
5. 为每个会议生成 manifest（trigger 全标 `"migration"`；archive 记录 `files` 列实际归档文件名），说话人映射/章节等字段从 task JSON 现值渲染（历史版本不重建历史内容层，仅存当时的纪要 md 原文——旧文件本身可能内嵌对话稿附录，原样保留不改字节）。
6. 迁移完成后调用 `repo.rebuild_all_indexes()` 生成 L0/L1，再跑 `validate_structure()`。

> **不解析旧文件内容拆分章节/决策层**：内容层多文件化只对新版生效；存量会议 `content_layers` 按实际可渲染源填写（summary.md 必有；chapters/decisions/transcript 可由 task JSON 补齐则补）。

### 5.3 dry-run 报告格式（`_migration_report.dryrun.json`）

```json
{
  "schema_version": 1,
  "mode": "dry-run",
  "generated_at": "…",
  "summary": {
    "total_files": 178,
    "by_rule": { "R1": 150, "R2": 12, "R3": 5, "R4": 11 },
    "meetings_resolved": 96,
    "meetings_with_archives": 34,
    "unassigned_meetings": 40,
    "collisions": 0,
    "orphan_task_refs": 2
  },
  "actions": [
    {
      "file": "086b1b62_预算系统调研与编制逻辑讨论_20260905_091708_20260905_100247_纪要.md",
      "rule": "R1",
      "meeting_id": "d2b4…", "kb_id": "8f4c…",
      "target": "8f4c…/d2b4…/summary.md",
      "version_role": "current", "version": 2,
      "sha256": "…", "ts_inferred": false
    },
    {
      "file": "086b1b62_…_20260905_094122_纪要.md",
      "rule": "R1", "target": "8f4c…/d2b4…/archive/v1/summary.md",
      "version_role": "archive", "version": 1, "sha256": "…"
    }
  ],
  "issues": [
    { "type": "hash8_collision", "prefix": "0a1b", "tasks": ["…uuid1", "…uuid2"] },
    { "type": "legacy_unresolved", "file": "weird_name.md", "reason": "no R1-R3 match" },
    { "type": "orphan_task_ref", "task_id": "…", "missing": "output file already deleted" }
  ]
}
```

执行模式同结构（`"mode": "apply"`），且每个 action 附移动后 sha256 复核结果；任一复核失败 → 整批回滚（见 §5.4）。

### 5.4 安全与回滚设计

- **S1 内容不变式**：迁移仅移动/复制文件，永不改写 md 字节（manifest/索引为新增）；每个文件的 sha256 移动前后必须相等。
- **S2 前缀唯一性预检**：uuid4 前 8 位碰撞概率约 4.3e-6/万级样本，仍必须预检——`hash8_collision` 非空时 dry-run 拒绝放行执行模式（碰撞组进 `_legacy/collision/<hash8>/`，人工裁决）。
- **S3 两段式落地**：先复制到新结构（校验通过、`validate_structure()` 绿）后，才将原件移入 `data/output/_pre_migration_backup/`（不直接删）；再提供 `--gc-backup` 独立子命令在验收数日后清备份。
- **S4 回写 task JSON**：`task["output_path"]` 批量改为新定稿路径（经 `atomic_write_json`，改前整文件备份到 `data/tasks.bak-migration/`）——否则 `/api/download` 与重新生成链路断。
- **S5 停机窗口**：迁移要求应用停止（`tasks/` 有内存态镜像，运行中迁移会被回写覆盖）；写入 README 迁移章节与实施单验收步骤。

---

## 6. AC-2「Agent 逐层下钻」可测化定义（供产品补验收脚本）

**落点**：`tests/test_output_structure_drilldown.py`（pytest），可直接作为实施单 AC-2 验收证据。

### 6.1 夹具（FIX）

构造脚本 `tests/fixtures/build_output_struct_fixture.py`（或测试内 tmp_path 直构）：一个 kb（2 会议：M1 今日、M2 今日-8 天），M1 经历一次重新生成（`current_version=2`，`archive/v1/` 在位）。即 §3.4 样例树的最小机器版。

### 6.2 Agent 读接口沙箱（SANDBOX）

```python
class DrilldownAgent:
    ALLOWED = ("open_json", "open_text")          # 仅允许按显式路径读取
    FORBIDDEN = ("iterdir", "glob", "rglob", "walk", "listdir", "scandir")
    # 实现：monkeypatch pathlib.Path.iterdir / glob / os.walk / os.listdir →
    #       抛 AssertionError("AC-2 violation: directory enumeration")
    #       同时记录 read_log: list[str]（相对 output_root 的路径序列）
```

### 6.3 走查场景与断言

| # | 场景 | 预期读取序列（唯一合法路径） | 断言 |
|---|---|---|---|
| A（核心 AC-2 场景） | 「知识库 X 近 7 天会议的决策汇总」 | `index.json` → `<kb>/index.json` →（过滤 `meeting_date` ≥ today-7d 的会议）→ 仅命中 M1 → `M1/manifest.json` → `M1/decisions.md` | ① read_log 无任何 FORBIDDEN 调用；② read_log 文件数 ≤ `2 + 2×命中会议数`；③ M2（8 天前）未被读取；④ `archive/` 未被读取；⑤ L0/L1/manifest 三次读取均为纯 `json.load` 成功且 §3 必填字段全在（schema 完整性与场景共用同一断言函数） |
| B | 「M1 的历史版本对比」 | L0 → L1 → `M1/manifest.json` →（依 version_chain[].archived_to）→ `archive/v1/summary.md` | ① 归档定位仅凭 manifest 版本链字段；② read_log 不含 transcript.md |
| C | 未关联会议 | L0（发现 `_unassigned` 条目）→ 同 A 下钻 | `_unassigned` 可被同等下钻 |
| D（负例） | 任何实现若依赖「目录名=显示名」检索 | 同上序列，但按 `display_name` 拼目录路径读取 | 必须失败——目录名只允许来自 L0 的 `path` 字段（R2 裁决的可执行化） |

### 6.4 机器判据（产品补验收脚本时直接引用）

1. `DrilldownAgent` 沙箱下场景 A/B/C 全绿、D 按预期失败；
2. read_log 证明：**目录枚举次数 = 0**；
3. `validate_structure()`（§4.1）对夹具返回空 issue 列表；
4. schema 完整性函数（`tests/helpers/output_schema_check.py`，按 §3.1-3.3 逐字段断言 + `json.load` 成功）对全部三个 JSON 通过 → 同时覆盖 AC-1 的结构可判定部分。

> 真实端到端验收（产品侧）：以任一 Agent（含会议助手对话）对迁移后 `data/output/` 跑场景 A，人工核对 read 轨迹；机器部分以上述 pytest 为准。

---

## 7. 与 WP-G / WP-I 的路径交叠清单与分支基线（R1 落实）

### 7.1 交叠清单（本方案视角，逐条给协调动作）

| # | 在途包 | 交叠面 | 证据/预期变更点 | 协调动作 |
|---|---|---|---|---|
| X1 | WP-G（打包首启，DevOps `78087de278c8`） | 冻结态数据根目录：`store.py:34-45` `OUTPUT_DIR = Path("data/output")` 为**相对 CWD 路径**，冻结包切 CWD 即错位 | `app/store.py:34-45`、`build/build_macos.py:170`（打包白名单含 `data/output` 等） | `output_root()` 作为唯一路径解析函数，内部处理 frozen/BASE_DIR（对齐 WP-G 的 D-R3 外置数据目录裁决）；WP-G 若已改 store.py 常量，实施分支 rebase 后仅改 `output_root()` 一处 |
| X2 | WP-G | 首次启动空目录：新结构要求 L0 index.json 在零会议时即存在 | 新 app 首启 | `finalize`/`rebuild` 之外，启动钩子调 `ensure_root_index()`（写空 L0）；列入实施单，与 WP-G AC-8 首启日志验收对齐 |
| X3 | WP-G | `output_dir` 设置在冻结包中是否生效的裁决连带影响（§2.5 ⚠️） | `app/routers/settings.py:183/324` | 归入 §8-Q5 待产品裁决，裁决前不动 |
| X4 | WP-I（分段增量上屏，本员工 `a4cdbd0ca795`，分支 `task/local-engine-r9-*`；强前置=WP-G G-2/G-3） | 定稿写入点：D-I2「增量段拼接即定稿」意味着 stage2/finalize 的**触发时机与调用方变化** | `core/pipeline_runner.py:424-549`（本方案 §4.2 #2 的挂点同在此函数区域）、`:518` | finalize 挂点必须打在「定稿事件」上而非「stage2 返回」上——WP-I 合入后定稿路径即其拼接完成处；§4.1 `finalize_meeting_output(task_id)` 接口形态**已按两包兼容设计**（输入仅 task_id，读 task JSON 现值），实施时先与 WP-I 定稿点核对一次 |
| X5 | WP-I | transcript.md 的句级时间戳口径：分段增量后 dialogue 段序/时间基准可能有微调 | `core/pipeline_runner.py:76`（`_build_dialogue_from_realtime`）、`core/realtime_store.py` | 渲染函数只依赖 `dialogue[].start_time/end_time` 契约；WP-I 若改契约，只改 output_repository 渲染器一处 |
| X6 | WP-H/WP-I 派工纪律 | 同 CWD 多 Session 并行风险 | ROADMAP.md:208（处置=独立 worktree `../oms-wt-wph` 等） | 本单交付即遵守此纪律（独立 worktree）；实施单同样执行 |
| X7 | CI | `ci-local-engine.yml` 冒烟（[STUB] PASS 契约） | `.github/workflows/`（a7aac5d 起） | 新结构相关测试标记 `@pytest.mark.local_only` 或进独立冒烟，避免阻塞 WP-G CI 绿灯 |

### 7.2 分支基线建议

1. **前置门（硬）**：实施分支 `task/output-struct-impl-<date>` 自 **main** 切出，且切出时点要求 **WP-G（G-2/G-3/G-5 合入）与 WP-I（含 D-I2 定稿链路）均已合入 main**。ROADMAP 已明示 WP-I 强前置 = WP-G 的 G-2/G-3，故两包串行时点即本需求可开工时点；预估本设计评审与两者实施并行，不互相消耗。
2. **可提前部分（软并行，仅当排期需要）**：与设计零冲突、不依赖写入链路的三件可先行合入 main——① schema/渲染的**纯函数模块**（manifest 渲染、内容层渲染 + 单测）；② `scripts/migrate_output_structure.py` 的 **dry-run 模式**（只读扫描出报告，不写盘，可先行拿真实 178 文件数据修正 §5.1 规则命中率）；③ §6 测试夹具与沙箱。执行模式（apply）仍等前置门。
3. **冲突预期**：`core/pipeline_runner.py` 是唯一可能三方共触文件（本方案 §4.2 #2 与 WP-H/WP-I 均在 `_run_stage2_for_task` 尾部区域）。协调规则：**实施分支后合入者负责 rebase**；本方案把改动压缩为「尾部追加 3 行调用 + 1 处赋值语义」，冲突面最小。
4. **迁移执行窗口**：安排在前两包验收完成、发版冻结期外（§5.4-S5 停机要求），且执行前跑 dry-run 并向产品提交报告。

---

## 8. 待产品裁决清单（工程侧不自行改设计）

| # | 问题 | 冲突/缺口陈述 | 工程建议（供裁决参考） |
|---|---|---|---|
| Q1 | `decisions.md`（决策与待办）内容源 | 需求书 §3 要求独立 decisions.md，但现状纪要为单一 md，「决策」无独立段落标记；非目标 §4.1 禁改生成链路。`parse_todos_from_summary`（`core/summarize.py:329`）只能提取**待办**，决策项无结构化源 | A. `decisions.md` = 待办清单（todos 字段渲染），改名「待办与决策（待办部分）」，接受语义缩水；B. 纪要 prompt 输出格式增加决策节（**属改生成链路，需产品显式豁免非目标**）；C. 定稿时一次额外 LLM 抽取（同上）。工程倾向 A 先行、B 随下个内容需求。**2026-09-25 产品裁决（R5 收尾）**：REQ-DECISION-CENTER 已合入（B1@586d141 / F1@714f6cf），`task["decisions"]` 成为结构化决策事实源（source=auto|backfill|manual|injection，含 status/superseded_by）。`decisions.md` 渲染源裁决为 `task["decisions"]`（决策节）+ `task["todos"]`（行动项节），A/B/C 三选项均作废，无需改生成链路。契约见 docs/API_CONTRACTS.md §12 |
| Q2 | `one_line_summary` 与 `attendee_count` 数据源 | 两字段现状均不存在。one_line_summary 任何取法都撞非目标 §4.1；attendee_count 可用 speakers 具名数近似（声纹未绑定时偏小） | one_line_summary 允许 `null`（schema 已如此设计），UI/Agent 判据降级为 title+date；attendee_count 用具名说话人数并在 manifest 注明口径。若产品坚持真摘要 → 豁免生成链路另立单 |
| Q3 | 洞察产物**是否实移**入 `insights/` | 需求书 §3 把洞察画进 output 树，但现状落 `data/tasks/*.insights.json` 且读 API 依赖该路径（`insights.py:73-75`）；实移=AC-5 回归面扩大（洞察台读写 API 迁移） | 双写副本方案（§4.3）：Agent 拿到树内文件，UI API 零改动；真相源仍在 tasks/。若产品要求单一位置 → 升级为 API 迁移子需求 |
| Q4 | 知识库删除/改名后目录处置 | project 删除（`core/projects.py:108`）时其 L1 目录去向：删（丢产出）/ 移 `_unassigned/` / 原样保留成孤儿 | 建议移 `_unassigned/`（与会议未关联语义一致、可逆、Agent 树不腐坏）；需产品确认「删除知识库不应静默删会议产出」 |
| Q5 | `output_dir` 设置项去留 | 现状为摆设（§2.5 ⚠️）。新结构落地后：A. 真正生效为 output_root；B. 从设置页移除 | 若 WP-G 的打包数据目录方案（D-R3）已定为跟随应用数据目录 → 建议 B 移除，避免第二个未兑现承诺；否则 A（一处 `output_root()` 实现） |
| Q6 | 存量会议 `content_layers` 完整度 | 迁移不解析旧 md 内容（§5.2 注），存量会议的 chapters/decisions/transcript 层可由 task JSON 补齐者补，JSON 也缺者（如 `transcription` 从未持久化）只能缺省 | 验收时 AC-4 判定标准请产品认可「存量会议内容层允许不完整、缺失记入迁移报告 stats」即可，无需额外工程 |

**结论**：需求书 §3 骨架整体工程成立（目录分层、稳定 ID、版本链、归档语义均可实现）；松动点集中在「字段数据源 vs 不改生成链路」的交叉处（Q1/Q2），以及洞察产物位置与既有 API 的张力（Q3）。以上不影响 schema 冻结——§3 设计对 Q1/Q2 已留 `null`/缺省路径，可先实施后裁决。

---

## 9. 建议实施排期切分（供实施单拆分，非本单范围）

1. **S-1** `core/output_repository.py`（渲染+finalize+rebuild+validate）+ 单测 —— 先行合入（软并行项 ①）
2. **S-2** 迁移脚本 dry-run + 真实库跑一轮报告 → 修规则 → apply 演练（tmp 副本）——（软并行项 ②）
3. **S-3** 写入链路 9 挂点接线（§4.3 表）+ 洞察双写 + 事件回归 —— 前置门后
4. **S-4** AC-2 下钻测试（§6，沙箱部分为软并行项 ③）+ AC-3 版本链回归 + 真实迁移窗口执行 + AC-4 报告归档
