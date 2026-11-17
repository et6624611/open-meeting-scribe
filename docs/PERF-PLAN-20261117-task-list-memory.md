# 任务列表性能与内存优化方案（2026-11-17）

> 执行说明：本文档可独立实施，无需回看原始对话。按 P0 → P1 顺序做，P2/P3 需用户签字后再动。
> 所有"现状"数字均为本机实测（macOS / Python 3.14 / 140 场会议 / `asr.mode=direct`）。

## 1. 问题与实测基线

### 1.1 现场数据

| 指标 | 实测值 | 度量方式 |
|---|---|---|
| 后端进程空闲 RSS（刚启动、未请求列表） | 677 MB | `ps -o rss= -p <pid>` |
| 调用一次 `GET /api/tasks` 后 RSS | 808 MB（不回落） | 同上 |
| `GET /api/tasks`（full） | **71.3 MB / 1.86 s** | `curl -w "%{size_download} %{time_total}"` |
| `GET /api/tasks?view=lite` | 45 KB / 3.7 ms | 同上 |
| 空闲 CPU | 0.0%（12–13 线程） | `top -l 2 -pid` |
| 启动：import 应用 | 90 MB | `resource.getrusage(...).ru_maxrss` |
| 启动：恢复 140 场任务 | +383 MB（→ 473 MB） | 同上 |
| `data/tasks` 磁盘 | 145 MB / 382 个 json | `du -sh` |

### 1.2 根因（关键结论）

对 140 场任务按字段拆解，`dialogue` 占列表响应 **95.3%**。继续下钻 `dialogue` 内部结构：

```
dialogue 总 73.4 MB
  └─ sentences[].words（词级时间戳）  64.6 MB  ← 87.9%
```

**词级时间戳 `words` 是唯一的大头**，而前端没有任何代码读取它（全仓 `frontend/src` 无 `sentence.words` 引用）；后端只在转写合并阶段用过（[transcribe.py](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/core/transcribe.py#L611-L649)），落盘后的读取链路全部不用。

实测对照（同一批 140 场，进程内保留全部任务）：

| 口径 | 常驻 RSS | dialogue JSON |
|---|---|---|
| 现状（含 words） | 394 MB | 73.4 MB |
| 剔除 words | **130 MB** | **8.3 MB** |

结论：**优化主力是 `words`，不是索引/缓存**。列表是否携带 dialogue 是第二层问题（8.3 MB vs 0）。

## 2. 目标

| 指标 | 现状 | P0 后（预期） | P0+P1 后（预期） |
|---|---|---|---|
| 列表响应体 | 71.3 MB | ≈ 12 MB | ≈ 3.7 MB |
| 列表耗时 | 1.86 s | ≈ 1.2–1.4 s | ≈ 0.15–0.25 s |
| 单次列表服务端峰值增量 | +200 MB | +60 MB 量级 | +10 MB 量级 |
| 空闲 RSS | 677 MB | 677 MB（P0 不动内存） | 677 MB |
| 空闲 RSS（P2 批准后） | 677 MB | — | ≈ 300–350 MB |

P0/P1 **只改读路径**，不写盘、不改数据格式、可整体回滚。

## 3. P0：响应剔除词级时间戳（必做）

### 3.1 改动点

1. 新增 `core/transcript_slim.py`：

```python
"""转写瘦身：响应层剔除句级词时间戳（约占 dialogue 体积 88%）。"""

def drop_word_timings(dialogue: list) -> None:
    """原地剔除 sentences[].words；非 dict 结构跳过，绝不改 text/时间码。"""
    for block in dialogue:
        if not isinstance(block, dict):
            continue
        for sentence in block.get("sentences") or []:
            if isinstance(sentence, dict):
                sentence.pop("words", None)
```

2. 改 [tasks.py](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/app/routers/tasks.py#L241-L258) `_with_transcript_layers`：
   - 清理版开启分支：`deepcopy` 之后、`enrich_sentence` 之前调用一次 `drop_word_timings`
   - 清理版关闭分支：当前直接 `{**task}` 原样返回，会漏出 words —— 必须改为 `deepcopy(task["dialogue"])` + `drop_word_timings` 后返回
   - 该函数被列表（L297）和详情（L353）共用，改一处两边生效，不要分别改

3. `words` 键的处理口径：**直接 pop（响应中不存在该键）**，不返回空数组，避免旧前端误判。

### 3.2 明确不动

- 不写回内存 task、不写盘（PLAN-TRANSCRIPT-LAYERING 既有约定）
- 不动 `core/transcribe.py` 生成期逻辑
- 不动 `view=lite` 字段集
- 不动 `transcript_layers` 信封与 `clean_text` 富化语义

### 3.3 测试

新增 `tests/test_transcript_response_shape.py`（参照 [test_task_list_lite.py](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/tests/test_task_list_lite.py) 的 fixture 写法）：

1. 详情接口：构造带 `words` 的 dialogue → 响应句子里不含 `words` 键
2. 列表 full：同样不含 `words`
3. 清理版开启/关闭两种配置下都不含
4. 原文 `text`、`begin_time`、`end_time`、`sentence_id`、`speaker_id` 与写入值逐项相等（证据层不可变）
5. 内存 task 中 `words` 仍存在（证明未回写）

## 4. P1：列表轻量视图 + 服务端转写检索 + speaker_share（必做）

### 4.1 后端：`GET /api/tasks?view=list`

在 [list_tasks](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/app/routers/tasks.py#L277-L303) 增加第三档 `view`：

- 字段口径：任务全部字段 **减去** `dialogue`、`realtime_full_transcript`
- 新增派生字段：
  - `has_dialogue: bool`
  - `speaker_share: {"<speaker_id>": <累计秒 float>, ...}`（含占位/未识别 speaker）
  - `dialogue_duration: float`（`speaker_share` 求和）
- `view` 取值：`lite` / `list` / `full`；未知值继续回退 `full`（有测试锁定）
- 保持 sync `def`、保持 `json.dumps` 预序列化直出、保持排序口径不变

新增 `core/speaker_share.py`：

```python
def compute_speaker_share(dialogue: list) -> dict[str, float]:
    """按 speaker_id 累计发言秒数。"""
```

缓存：模块级 `_CACHE: dict[str, tuple[tuple, dict]]`，键 `task_id`，指纹 `(len(dialogue), 末块末句 end_time)`；指纹变化则重算。**只放内存，不落盘**。计算成本实测 140 场 0.01 s，缓存只为省重复遍历。

> 之所以不让前端自己算：TaskCard 与会议库现在都遍历 dialogue 求时长占比，列表剔除 dialogue 后必须由后端给数。

### 4.2 后端：`GET /api/tasks/search?q=`

只补"转写维度"检索（标题/纪要/说话人/章节/决策 前端本地已有）。契约：

```json
{ "query": "税费", "task_ids": ["<id>", "..."], "truncated": false }
```

- `q` trim 后为空 → `{"query": "", "task_ids": [], "truncated": false}`
- 大小写不敏感子串匹配，扫 `block.text` 与 `sentences[].text`，命中即跳过该任务
- 上限 200 条，超出置 `truncated: true`
- 不返回正文、不做清理版富化；`def` 同步端点

实测全量不命中（最坏情况）扫描 140 场约 0.01–0.02 s，无需索引。

### 4.3 前端改动清单

| 文件 | 改动 |
|---|---|
| [api/tasks.ts](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/frontend/src/api/tasks.ts#L11-L16) | `fetchTasks(view: 'lite'\|'list'\|'full' = 'list')`；新增 `searchTranscript(q)` |
| [api/types.ts](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/frontend/src/api/types.ts) | Task 增加 `has_dialogue?` / `speaker_share?` / `dialogue_duration?` |
| [stores/task.ts](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/frontend/src/stores/task.ts#L174-L188) | `loadTasks(view)`；`debouncedSidebarQuery` 变化时调 `searchTranscript`，结果入 `transcriptMatchIds`（递增序号丢弃过期响应）；`filteredTasks` = `matchTask(t,q) \|\| transcriptMatchIds.has(id)`，q 清空时重置集合 |
| [TaskCard.vue](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/frontend/src/components/task/TaskCard.vue#L249-L276) | `topSpeakers` 改用 `speaker_share`；抽 `utils/speakerShare.ts` 纯函数便于单测；`speaker_share` 缺失时回退旧 dialogue 逻辑 |
| [useLibrarySelection.ts](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/frontend/src/composables/useLibrarySelection.ts#L250-L286) | `getSpeakerList` 同上（未识别聚合按 sid 求和 duration；pct 用总量） |
| [AIPanel.vue](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/frontend/src/components/layout/AIPanel.vue#L357) | `@原文` 可用性 → `has_dialogue \|\| dialogue?.length \|\| recording` |
| [useAiContext.ts](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/frontend/src/composables/useAiContext.ts#L37-L68) | 无 dialogue 时 `speakerCount` 回退 `task.speaker_count`，`chapterCount` 回退 `task.chapters?.length ?? 0` |
| [useSpeakerStats.ts](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/frontend/src/composables/useSpeakerStats.ts#L39) | 显式传 `'full'`（说话人页需要逐字稿流水） |

### 4.4 必须守住的既有行为

- **不要把非 lite 列表当成"替换全部字段"**：[mergeTaskLists](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/frontend/src/utils/taskListMerge.ts#L66-L70) 是 `{...local, ...snap}` 展开合并，详情页拉到的 dialogue 不会被列表刷掉——不要改成整体替换
- lite 轮询语义不变（只并状态字段、不新增、不删除）
- `patchTaskLocal`（详情/轮询回填）保持不变
- 会议详情页仍走 `GET /api/tasks/{id}`（含 dialogue + 清理版），不做懒加载改造

### 4.5 测试

后端新增 `tests/test_task_list_views.py`：
1. `view=list` 不含 `dialogue` / `realtime_full_transcript`
2. 含 `has_dialogue`、`speaker_share`、`dialogue_duration`，且时长与 dialogue 实际累加一致（含占位 speaker）
3. `view=lite` 字段集不变、`view=full` 仍含 dialogue、未知 view 回退 full
4. `search?q=`：命中/不命中/空 q/大小写；只回 id 不回正文
5. `speaker_share` 缓存：dialogue 替换后重新计算

前端：`utils/speakerShare` 单测（时长占比、占位聚合、缺字段回退）；`npm run test:unit` 全绿；`npm run build` 通过。

## 5. P2（可选，需用户签字）：词级时间戳彻底下线

P0 只清响应，内存与磁盘仍保留 words（383 MB 常驻 / 145 MB 磁盘）。若确认再无用途：

- `core/transcribe.py` 合并完成后不再保留 `words` 字段
- 一次性迁移脚本剥离存量任务文件中的 `words`（**先做全量备份**，参照 2026-10-04 快照分支教训）
- 预期：常驻 394 MB → **130 MB**；`data/tasks` 145 MB → ≈ 25 MB

风险：不可逆；未来词级字幕/精确定位需重新转写。**未签字不执行**。

## 6. P3（已评估关闭，2026-11-17）

原计划：启动时不驻留 dialogue，详情/管线按需从 `data/tasks/{id}.json` 读取，预期常驻 383 MB → 116 MB。

**P2 落地后前提消失**：磁盘剥离词时间戳后，`data/tasks` 仅 14.4 MB，全部任务读入内存后 dialogue 只占约 19 MB（实测：载入全部任务 45 MB，剔除 dialogue/realtime_full_transcript 后 26 MB）。服务实际启动 RSS 114 MB，P3 最多再省约 19 MB，却要把摘要重跑、AI 上下文、导出、声纹、书面版五条直接读 `task["dialogue"]` 的路径统一收口，风险与收益不匹配。

结论：**不实施**。若将来单场会议体积显著变大（如数小时录音），再按原思路单独立项。

## 7. 实施与验收

### 7.1 环境

```bash
# 后端（本机 .env 为 asr.mode=direct，无需 ENGINE_PYTHON）
venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port 8000
# 后端测试
venv/bin/pytest tests/test_transcript_response_shape.py tests/test_task_list_views.py tests/test_task_list_lite.py
# 前端
cd frontend && npm run test:unit && npm run build
```

注意：后端读 `frontend/dist`，前端改完必须重新 build 再起服务，否则页面仍是旧包。

### 7.2 度量脚本（改动前后各跑一次，记录到 PR 描述）

```bash
P=$(pgrep -f "uvicorn app.server" | head -1)
echo "RSS 启动后: $(( $(ps -o rss= -p $P) / 1024 )) MB"
curl -s -o /dev/null -w "full : %{http_code} %{time_total}s %{size_download} bytes\n" "http://127.0.0.1:8000/api/tasks"
echo "RSS 列表后: $(( $(ps -o rss= -p $P) / 1024 )) MB"
curl -s -o /dev/null -w "list : %{http_code} %{time_total}s %{size_download} bytes\n" "http://127.0.0.1:8000/api/tasks?view=list"
curl -s -o /dev/null -w "lite : %{http_code} %{time_total}s %{size_download} bytes\n" "http://127.0.0.1:8000/api/tasks?view=lite"
curl -s -o /dev/null -w "detail: %{http_code} %{time_total}s %{size_download} bytes\n" "http://127.0.0.1:8000/api/tasks/<任一task_id>"
curl -s "http://127.0.0.1:8000/api/tasks/search?q=税" | head -c 200
```

### 7.3 功能回归清单（必须逐项点过）

1. 启动应用：侧边栏会议列表、时间分组、未读角标正常
2. 会议库：卡片说话人占比、未识别聚合、排序、筛选、批量导出/归档正常
3. 侧边栏搜索：标题命中、纪要命中、**转写内容命中**均能搜到；删词后结果收回
4. 进入会议详情：逐字稿全文、时间码、清理版切换、章节、决策、导出 md/docx 正常
5. AI 面板：`@原文` 有/无转写时可用性正确；`/` 指令正常
6. 说话人页：发言统计（依赖 full 列表）数值与改动前一致
7. 录音中任务：状态轮询、完成角标、跳转正常
8. 控制台无新增报错；`view=lite` 轮询请求体仍在 100 KB 以内

### 7.4 回滚

P0/P1 均为纯读路径。回滚只需把 `fetchTasks()` 默认值改回 `'full'` 并还原 `_with_transcript_layers`，无需数据修复。

## 8. 不做的事

- 不动 ffmpeg/录音链路、CPU 相关（已四层防护，本次无优化空间）
- 不动 `view=lite` 字段集（高频轮询契约）
- 不改任务落盘格式（除非 P2 签字）
- 不动洞察板、决策中心、AI 提示词
- 不引入 gzip 中间件（本地回环收益有限，优先级低于上述）
- `data/models` 2.1 GB 属磁盘占用（direct 模式不加载），单独走磁盘治理，不进本方案

## 9. 实施结果（2026-11-17，P0 + P1 已落地）

改动文件：

- 新增 `core/transcript_slim.py`（`drop_word_timings`）、`core/speaker_share.py`（`compute_speaker_share` / `get_speaker_share` 内存缓存）
- [tasks.py](file:///Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/app/routers/tasks.py)：`_with_transcript_layers` 统一剔除 words；新增 `view=list`、`_list_item`、`_dialogue_contains`、`GET /api/tasks/search`
- 前端：`api/tasks.ts`（`TaskListView` + `searchTranscript`）、`api/types.ts`（派生字段）、`stores/task.ts`（默认 list + 转写检索合并）、`utils/speakerShare.ts`（新增，纯函数）、`TaskCard.vue`、`useLibrarySelection.ts`、`AIPanel.vue`、`useAiContext.ts`、`useSpeakerStats.ts`、`useCompletionWatch.ts`
- 测试：`tests/test_transcript_response_shape.py`（5 条）、`tests/test_task_list_views.py`（14 条）、`frontend/src/utils/__tests__/speakerShare.test.ts`（4 条）

实测（同一份 140 场数据）：

| 指标 | 改动前 | 改动后 |
|---|---|---|
| `GET /api/tasks`（full） | 71.3 MB / 1.86 s | **13.2 MB / 1.53 s** |
| `GET /api/tasks?view=list` | —（新增） | **1.58 MB / 14 ms** |
| `GET /api/tasks?view=lite` | 45 KB / 3.7 ms | 45 KB / 1.9 ms |
| 详情 `GET /api/tasks/{id}` | 397 KB 量级（含 words，实测最高 3.1 MB） | 397 KB / 57 ms（709 句，含 words 0 句） |
| 进程 RSS 启动后 | 677 MB | **451 MB**（P0+P1）→ **114 MB**（P2 后） |
| 跑过 full + list 后的 RSS | 808 MB | **470 MB**（P0+P1）→ **155 MB**（P2 后） |
| `data/tasks` 磁盘 | 146.5 MB | **14.4 MB**（P2 迁移后） |

说明：

- 句级时间码是毫秒，`speaker_share` 统一换算成秒下发，顺带修正了会议库说话人 tooltip 时长（此前直接把毫秒当秒，显示偏大 1000 倍）。
- P2 已执行（2026-11-17，用户签字）：`core/transcribe.py` 的 `assemble_dialogue` 在合并完成后剔除 words（合并期仍可用），存量数据由 `scripts/strip_word_timings.py` 一次性迁移（预演 → `--apply`，原子写、幂等，旁挂 sidecar 不动）。迁移前全量备份：`~/oms-tasks-backup-20261117.tar.gz`。抽样校验：447 句文本与时间码逐句一致，summary/decisions 一致，words 归零。
- P3（dialogue 懒加载）已评估关闭：P2 后 dialogue 常驻仅约 19 MB，收益与改造风险不匹配（详见第 6 节）。


