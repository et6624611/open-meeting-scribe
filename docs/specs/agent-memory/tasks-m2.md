# Agent 长期记忆 · M2 任务书

- 状态：待确认
- 范围：巩固进程 + proposed 确认 + 衰减归档 + 审计（spec §12 M2）
- 出口：自动化闭环——定稿会议自动产出待确认记忆，陈旧记忆自动归档，删除项按时物理清理
- 前提：M0/M1 已完成；M2 不改面板交互（确认流已在 M1），不改向量层

## 1. 巩固进程

### 1.1 新增 `core/agent_memory/consolidate.py`

常量：

```python
MAX_ITEMS = 5
ALLOWED_KINDS = ("fact", "decision", "preference", "glossary")
MAX_SOURCE_CHARS = 6000
```

函数：

| 函数 | 签名 | 行为 |
|---|---|---|
| `consolidate_task` | `(task_id: str, *, force: bool = False, llm=None) -> dict` | 单场巩固，返回 `{task_id, created, skipped, reason}` |
| `consolidate_recent` | `(limit: int = 20) -> dict` | 遍历近 `limit` 场已完成任务，逐场调用；返回 `{tasks, created, skipped}` |

`consolidate_task` 流程：

1. 开关：非 `force` 且 `get_feature_flags().get("agent_memory_consolidate", False)` 为假 → 返回 `reason="disabled"`。
2. 取任务：`from core.task_store import tasks`；不存在 → `reason="task_not_found"`。
3. 状态：非 `force` 且 `status != "completed"` → `reason="not_completed"`。
4. 幂等：`store.load_all()` 中已存在 `source.task_id == task_id` 的条目 → `reason="already_consolidated"`。
5. 取源文：`summary` + `user_notes` + `decisions` 的 `title/decision` 拼接，截断 `MAX_SOURCE_CHARS`；为空 → `reason="no_source_text"`。
6. 组 prompt：system 要求只输出 JSON 数组；user 附源文与规则（最多 5 条、`kind` 限四类、`quote` 必须逐字摘自源文、`text` ≤200 字、可给 `subject/relation/object/importance`）。
7. 调 `llm`（缺省 `core.llm.chat_completion`），`temperature=0.2`、`max_tokens=900`。
8. 解析：剥离 ```json 围栏，取首个 `[` 到末个 `]`；非数组 → `reason="bad_json"`。
9. 逐条校验并写入：
   - `kind` 不在 `ALLOWED_KINDS` → 归为 `fact`
   - `text` 去空白后为空或 >200 → 丢弃
   - `quote` 去空白后 <4 字或不在源文（去空白子串）中 → 丢弃
   - `namespace`：`task["project_id"]` 存在 → `space:<project_id>`，否则 `global`
   - 条目固定 `status="proposed"`、`source={"task_id", "quote", "anchor": {}}`、`recorded_at=now`
   - `store.upsert(item, require_source=True)`；成功计数，达到 `MAX_ITEMS` 即停
10. 审计：`store.audit("consolidate", {"id": task_id}, {"created": n, "skipped": m})`。
11. 返回汇总。

`consolidate_recent`：

- 读取 `tasks` 中 `status == "completed"` 的最近 `limit` 场（按 `created_at` 降序）。
- 逐场调用 `consolidate_task(task_id)`；单场异常只记 warning，不中断。
- 不强制 `force`，遵守开关。

### 1.2 触发点

**自动（会后）** — `core/pipeline_runner.py`：Stage2 成功、`task["summary"]` 等字段写回之后（约 L690–L730 区块末尾），补：

```python
try:
    from core.settings_store import get_feature_flags
    if get_feature_flags().get("agent_memory_consolidate", False):
        import threading
        from core.agent_memory.consolidate import consolidate_task
        threading.Thread(target=consolidate_task, args=(task_id,), daemon=True).start()
except Exception as e:
    logger.warning("记忆巩固启动失败（不影响主流程）: %s", e)
```

**手动** — `app/routers/memory.py` 新增 `POST /api/memory/consolidate/{task_id}`：`consolidate_task(task_id, force=True)`，`not_found` → 404，其余异常 → 422。

**定时** — `app/server.py`：

- 新增 `_MEMORY_LIFECYCLE_INTERVAL = 24 * 3600`
- 新增 `_run_memory_lifecycle()`：`get_feature_flags().get("agent_memory", True)` 为假直接返回；否则 `consolidate_recent()` + `lifecycle.run_lifecycle()`，异常只记 warning。
- 新增 `async def _memory_lifecycle_loop()`，形制同 `_auto_archive_loop`（先 sleep 再跑，捕获 `CancelledError`）。
- lifespan 中：`asyncio.create_task(_auto_archive_loop())` 之后加启动一次 `await asyncio.to_thread(_run_memory_lifecycle)`（包 try/except）与 `asyncio.create_task(_memory_lifecycle_loop())`。

## 2. 生命周期（衰减归档 + 清理）

### 2.1 新增 `core/agent_memory/lifecycle.py`

| 函数 | 阈值 | 行为 |
|---|---|---|
| `archive_stale(*, days=180, importance_floor=0.3, now=None) -> int` | 180 天 / 0.3 | `status=="active"` 且 `valid_to` 为空，`importance < 0.3`，参考时间（`last_used_at` 优先，否则 `recorded_at`）早于 N 天 → `store.set_status(id, "archived")` |
| `enforce_capacity(*, max_open=500) -> int` | 每 namespace 500 | 按 namespace 统计 open（active 且未闭合），超出部分按 `(importance 升序, recorded_at 升序)` 归档 |
| `purge_deleted(*, days=30, now=None) -> int` | 30 天 | `status=="deleted"` 且 `deleted_at` 早于 N 天 → `store.purge(id)` |
| `run_lifecycle() -> dict` | — | 顺序执行三者，返回 `{archived, capacity_archived, purged}` |

时间解析：兼容 `YYYY-MM-DD` 与 ISO datetime；无法解析视为「不过期」，不归档。

### 2.2 `core/agent_memory/store.py` 增补

```python
def audit(action: str, item: dict, extra: dict | None = None) -> None:
    """公开审计写入口（巩固/生命周期用）。"""

def read_audit(limit: int = 100) -> list[dict]:
    """读取 audit.jsonl 末尾 limit 条（倒序返回）。"""
```

不改现有写路径语义。

### 2.3 审计查询

`GET /api/memory/audit?limit=100` → `{"items": store.read_audit(limit)}`。

## 3. 测试 `tests/test_memory_consolidate.py`

fixture 复用 `memory_dir`（monkeypatch `store.MEMORY_DIR`）+ 注入 `tasks[task_id]`，`llm` 用 stub。

用例：

1. 开关关（`get_feature_flags` 返回 `{"agent_memory_consolidate": False}`）→ `created=0`、`reason="disabled"`，store 为空。
2. `force=True` → 产出 2 条 `proposed`，`stats()["proposed"]==2`。
3. `quote` 不在源文 → 该条丢弃；超 200 字 → 丢弃。
4. 幂等：连续调用两次，第二次 `reason="already_consolidated"`，条目数不变。
5. `project_id` 存在 → `namespace=="space:<id>"`；否则 `global`。
6. `archive_stale`：构造 200 天前、importance 0.1 的 active 条目 → 归档；importance 0.5 不动。
7. `enforce_capacity(max_open=2)`：同 namespace 3 条开放 → 归档 1 条（importance 最低）。
8. `purge_deleted(days=30)`：`deleted_at` 40 天前 → 物理删除；近 5 天保留。
9. `POST /api/memory/consolidate/{task_id}`（TestClient）→ 200 且返回 `created`；不存在任务 → 404。
10. `GET /api/memory/audit` 至少能读到 `consolidate` 记录。

## 4. 不变项

- 前端不新增页面/组件；M1 的待确认流与设置页开关原样复用。
- `feature_flags.agent_memory_consolidate` 默认仍为关。
- 不引入向量库；不改逐字稿/纪要/决策落盘链路。

## 5. 验证

```bash
.venv/bin/python -m pytest tests/test_memory_consolidate.py tests/test_memory_api.py tests/test_agent_memory.py tests/test_core_layer_purity.py -q
```

前端无改动，不需要重新构建。

## 6. 执行进度

- [x] 1.1 `consolidate.py`
- [x] 1.2 自动/手动/定时触发
- [x] 2.1 `lifecycle.py`
- [x] 2.2 `store.audit` + `read_audit`
- [x] 2.3 审计查询接口
- [x] 3 测试并跑通（41 passed）
