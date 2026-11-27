# Agent 长期记忆 · M1 任务书

- 状态：待确认
- 范围：REST 接口 + 记忆面板（`/memory`）+ 设置页「AI 记忆」概览
- 真源：`docs/specs/agent-memory/spec.md` §11 / §12；UI 基线 `prototype-v3.html`
- 前提：M0 已完成（store/retrieve/inject/工具面/注入 + 12 项测试全绿），本轮不改写 M0 语义

## 1. 后端

### 1.1 `core/agent_memory/store.py` 增补

新增 `set_status(memory_id: str, status: str) -> dict[str, Any]`：

- `status` 必须属于 `schema.STATUSES`，否则抛 `MemoryWriteError("bad_status")`
- 持 `_LOCK`，读 `load_all()`，找不到抛 `MemoryWriteError("not_found")`
- 只改 `status`；`deleted` 时补 `deleted_at = schema.now_iso()`
- `_save_all(items)` + `_audit("status", target, {"status": status})`
- 返回更新后的条目

不改 `list_items` / `stats` / `close` / `reopen` / `update` / `delete` 的现有签名。

### 1.2 新增 `app/routers/memory.py`

`router = APIRouter(tags=["memory"])`。统一错误映射：`MemoryWriteError.code == "not_found"` → 404，其余 → 422，响应体 `{"error": code, "message": str}`。`ValueError` → 422。

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `/api/memory/stats` | 直接返回 `store.stats()` |
| GET | `/api/memory` | 参数 `view=open\|closed\|proposed\|archived`（缺省 open）、`namespace`、`kind`、`q`、`cursor`、`limit`（默认 50，上限 200）。返回 `{"items": [...], "next_cursor": str \| null}` |
| POST | `/api/memory` | 手动新建：`require_source=False`，`source={"manual": True}`，`status="active"` |
| PATCH | `/api/memory/{id}` | 只接受白名单字段 `text/kind/namespace/subject/relation/object/tags/valid_from/valid_to/importance`，其余丢弃；调 `store.update` |
| POST | `/api/memory/{id}/close` | body 可选 `{valid_to?, invalidated_by?, reason?}`；调 `store.close` |
| POST | `/api/memory/{id}/reopen` | 调 `store.reopen` |
| DELETE | `/api/memory/{id}` | 软删，调 `store.delete` |
| POST | `/api/memory/{id}/accept` | `store.set_status(id, "active")` |
| POST | `/api/memory/{id}/reject` | `store.delete(id)`（proposed → deleted，写 `deleted_at`） |
| GET | `/api/memory/export` | `JSONResponse`，`Content-Disposition: attachment; filename="memory-export-<yyyymmdd>.json"`，体 `{"version": 1, "exported_at", "count", "items": store.load_all()}` |

列表实现：

- 取 `store.list_items(namespace=..., kind=..., q=...)` 后按视图过滤：
  - `open` → `status == "active" and not valid_to`
  - `closed` → `status == "active" and valid_to`
  - `proposed` / `archived` → 对应 `status`
- 排序固定 `(recorded_at, id)` 降序；cursor 为 `f"{recorded_at}|{id}"`（不 base64，交给 HTTP 层编码）。返回该键严格小于 cursor 的后续条目。
- 非法 `view` / `cursor` → 422。

### 1.3 `app/server.py`

- 在 `from app.routers import (...)` 中加入 `memory`（按字母序）
- 在 `app.include_router(...)` 组中加 `app.include_router(memory.router)`

### 1.4 `app/routers/settings_core.py`

`POST /api/settings` 的 `feature_flags` 白名单（约 424–433 行）补两项，口径与 `get_feature_flags` 一致：

```python
"agent_memory": data.get("feature_flags", {}).get("agent_memory", existing_ff.get("agent_memory", True)),
"agent_memory_consolidate": data.get("feature_flags", {}).get("agent_memory_consolidate", existing_ff.get("agent_memory_consolidate", False)),
```

（GET 走 `get_feature_flags()` 已含这两项，无需改。）

### 1.5 测试 `tests/test_memory_api.py`

复用 `tests/test_agent_memory.py` 的 `memory_dir` fixture 方式（monkeypatch `store.MEMORY_DIR`），`TestClient(app)`。覆盖：

1. 手动新建 → stats.open +1，`source.manual is True`
2. 带来源写入 + 列表 `view=open` / `view=closed` 过滤正确
3. cursor 分页：写 3 条、`limit=2`，两页拼起来无重复且完整
4. PATCH 改 text 生效、`status` 字段被忽略
5. close → stats.closed +1 → reopen → 回 open
6. accept：proposed → active；reject：proposed → deleted
7. DELETE 软删 → stats.deleted +1
8. export 返回附件头与 `items` 全量
9. 不存在的 id → 404，body 含 `error=not_found`

## 2. 前端

### 2.1 `frontend/src/api/memory.ts`

`client` 风格同 `hotwords.ts`。导出类型：

```ts
MemoryStatus = 'proposed' | 'active' | 'archived' | 'deleted'
MemoryView = 'open' | 'closed' | 'proposed' | 'archived'
MemoryItem { id, namespace, kind, subject, relation, object, text, tags,
  valid_from, valid_to, time_confidence, recorded_at, source, status,
  invalidated_by, importance, confidence, last_used_at, use_count }
MemoryStats { open, closed, proposed, archived, deleted, total }
```

函数：`fetchMemoryStats()`、`listMemory(params)`、`createMemory(payload)`、`updateMemory(id, patch)`、`closeMemory(id, body?)`、`reopenMemory(id)`、`deleteMemory(id)`、`acceptMemory(id)`、`rejectMemory(id)`、`exportMemory()`（`responseType: 'blob'`，前端触发下载）。

### 2.2 `frontend/src/stores/memoryStore.ts`

Pinia setup store（风格参考 `stores/layout.ts`）：

- state：`items`、`stats`、`view`（默认 `open`）、`filters`（`namespace/kind`）、`query`、`cursor`、`hasMore`、`loading`、`loadingMore`、`error`、`selectedId`、`draft`（新增/编辑）
- getters：`selected`
- actions：`loadStats`、`load(reset=true)`（防抖由视图层做）、`loadMore`、`select(id)`、`create(payload)`、`update(id, patch)`、`close(id)`、`reopen(id)`、`remove(id)`、`accept(id)`、`reject(id)`、`exportAll()`
- 乐观更新口径：`close/reopen/remove/accept/reject` 成功后本地改状态并刷新 stats，不重排列表；`create/update` 成功后 `load()` 重拉。

### 2.3 `frontend/src/views/MemoryView.vue`

布局：内容区最大宽 1080 居中；`< 900px` 单栏（列表 / 详情二选一，选中后显示详情+返回）。

- 顶栏：标题 + 统计（开放/已闭合/待确认，数字可点 → 切 `view`）+ 右侧「导出」
- 工具行：搜索框（`/` 聚焦，防抖 300ms）、状态 chips（open/closed/proposed/archived，带计数）、「筛选」popover（namespace/kind；`usePopMenu` 定位，内部走 `popoverPosition`）
- 左列表 250px：正文两行截断 + meta（类型圆点 + 类型名按钮 + namespace + 日期）
- 状态只走左侧 3px 竖条：默认透明、待确认 `--warn`、已闭合 `--muted` 实线、已归档 `--border-strong` 实线；选中背景 `--accent-soft` + 1px 内描边，不占左边框
- 右详情：标题（全文）+ 状态标签 + 「出身」（类型/namespace/来源）+ 「生命周期」（有效期/使用情况）；底部操作按状态变化（开放：编辑/闭合/删除；已闭合：编辑/重新打开/删除；待确认：采纳/忽略）
- 来源可点：`/meeting/<task_id>?dialogue=<anchor.dialogue_index>`；`source.manual` 显示「手动」
- 新增：详情区行内表单，类型 / 作用域 / 正文（≤200 字必填）
- 待确认横幅：`N 条记忆待确认` + [逐条处理] [全部忽略]；采纳后跳下一条，清空提示；全部忽略 5 秒撤销
- 键盘：`/` 聚焦、`↑↓` 移动、`Enter` 编辑、`Delete` 删除确认、`Esc` 逐级关闭
- 危险操作：单条删除确认弹窗显示正文前 40 字；闭合不确认，toast 5 秒撤销；本页不做嵌套滚动
- 空态 / 搜索无结果 / 骨架 / 失败重试按 spec §11.2
- 无障碍：列表 `role="list"`、项 `role="listitem" tabindex="0"`；类型标签独立 `<button aria-pressed>`；开关 `role="switch" aria-checked`
- 样式只用 token，禁止组件内硬编码 `oklch()`

### 2.4 `frontend/src/components/memory/*`

- `MemoryFilterPopover.vue`：namespace（全部/global/各 space/role/task 选项由当前 items 派生）、kind 六类；选中即回写 store；定位用 `usePopMenu`
- `MemoryDetail.vue`：可拆出详情 + 行内表单，供视图组合

### 2.5 设置页概览 `frontend/src/components/settings/MemoryOverviewPanel.vue`

挂载点：`SettingsView.vue` 的 `activeCategory === 'ai'` 区块，`<AiSourcePanel>` 之后。内容：

- 标题「AI 记忆」+ 一句说明
- 状态：开放 / 已闭合 / 待确认（读 `fetchMemoryStats`）
- 存储：`<数据目录>/memory/`（只显示路径，不提供打开目录按钮——避免新增系统调用端点，列为后续项）
- 开关：记忆启用（`feature_flags.agent_memory`）、会后自动巩固（`feature_flags.agent_memory_consolidate`），`role="switch"`；切换调 `saveSettings({ feature_flags: { ...两项 } })`
- 按钮 [管理记忆] → `router.push('/memory')`

### 2.6 路由与导航

- `frontend/src/router/index.ts` 加 `{ path: '/memory', name: 'memory', component: () => import('@/views/MemoryView.vue') }`
- `frontend/src/components/layout/ActivityRail.vue`：在 agents 之后加入口，图标用「记忆/书签」线性 SVG，`route.name === 'memory'` 高亮，`t('sidebar.rail_memory')`；`RAIL_NAV_PAGES` 加入 `/memory`

### 2.7 i18n

- 新建 `frontend/src/i18n/locales/en/memory.json`、`zh-CN/memory.json`，键按 spec §11.2「i18n」清单
- `frontend/src/i18n/index.ts` 四处登记：静态 import、`MessageSchema`、`LOCALE_MODULES`、`defaultMessages`
- `sidebar.json`（en/zh-CN）加 `rail_memory`
- `settings.json`（en/zh-CN）加 `settings.memory.*` 概览键

## 3. 验证

后端：

```bash
.venv/bin/python -m pytest tests/test_memory_api.py tests/test_agent_memory.py tests/test_core_layer_purity.py -q
```

前端：

```bash
cd frontend && npm run build
```

最后用 `build-frontend` skill 重新打包（后端静态目录以 dist 为准）。

## 4. 执行进度

- [x] 1.1 `store.set_status`
- [x] 1.2 `app/routers/memory.py`
- [x] 1.3 `app/server.py` 注册
- [x] 1.4 `settings_core.py` 白名单
- [x] 1.5 `tests/test_memory_api.py`（32 passed）
- [x] 2.1 `api/memory.ts`
- [x] 2.2 `stores/memoryStore.ts`
- [x] 2.3 `MemoryView.vue`
- [x] 2.4 `components/memory/*`
- [x] 2.5 `MemoryOverviewPanel` + 设置页
- [x] 2.6 路由与 ActivityRail
- [x] 2.7 i18n
- [x] 3 前端构建（vue-tsc + vite 通过，dist 已刷新）

## 5. 明确不做（本轮）

- 批量多选（Cmd/Ctrl + 点击）
- 虚拟滚动（>100 条）先按普通列表，超过阈值后续补
- 设置页「打开目录」按钮（需新增系统调用端点）
- 清空全部（保留在后续高级项，要求输入「清空」）
- 会后巩固进程（`consolidate.py`）与 M2 范围
