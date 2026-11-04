---
title: "代码库健康检查报告与整改任务清单（2026-11）"
description: "面向未来功能开发与迭代的只读健康检查结论，含按优先级分组的可勾选整改任务清单、每项的位置/影响/验收标准，以及迭代健康门禁。"
tags: ["health-check", "tech-debt", "checklist", "ci", "testing", "architecture"]
created_at: "2026-11-04"
updated_at: "2026-11-04"
version: "1.1.1"
author: "Yongliang Wang"
status: "published"
category: "technical"
---

# 代码库健康检查报告与整改任务清单

> 检查日期：2026-11-04 ｜ 检查方式：只读分析（未修改代码）｜ 检查框架：8 维度 × tech-debt 优先级评分
> 复核日期：2026-11-04 ｜ 复核方式：逐项实测（eslint / vitest / pytest / ruff / 代码统计），初版 4 处结论已修正，详见「一·复核修正」
> 使用方法：按「P0 → P1 → P2」顺序逐项执行，完成后将 `[ ]` 改为 `[x]` 并在「完成记录」列填写日期与 commit。

---

## 一、总体健康结论

**综合评分：6.5/10 — 基础扎实，可迭代，但存在结构性风险，不适合快速扩张新功能。**

| 维度 | 评分 | 一句话结论 |
|---|---|---|
| 项目结构与模块边界 | ⚠️ 6/10 | core→app 反向依赖是主要扣分项 |
| 架构可扩展性 | ✅ 7/10 | 分层清晰，但 core 层耦合限制独立演进 |
| 质量守护能力 | 🔴 4/10 | CI 覆盖严重不足，大量核心模块无测试 |
| 依赖与构建健康度 | ⚠️ 6/10 | 双清单不一致（T-01 已修复），无 lockfile（版本源已统一，非问题） |
| 可观测性与排障能力 | ✅ 8/10 | 日志体系完善，审计中间件 + joblog 事件流 |
| 安全与合规风险 | ✅ 8/10 | 凭据已清理，.env.example 规范，AGPL 合规 |
| 文档与知识沉淀 | ✅ 8/10 | ROADMAP/ARCHITECTURE/BACKLOG 体系完整 |
| 技术债与高风险区域 | ⚠️ 5/10 | 后端 6 + 前端 4 个 >1000 行大文件，31 个 BACKLOG 未解决项 |

**三大主要风险**：
1. **架构层级破坏**：6 个 `core/` 模块直接 `import app.*`，core 无法独立测试与复用
2. **CI 防护盲区**：CI 仅跑 `tests/test_smoke.py`；前端 60 个 vitest 测试不在 CI；ESLint 35 个 error 无门禁
3. **依赖管理分歧**：`pyproject.toml` 与 `requirements.txt` 实质性不一致（pyproject 多 scipy、缺 Babel/pywebview）——已由 T-01 修复；无 Python lockfile，依赖仅 `>=` 下限（仍待 T-14）

---

## 一·复核修正（2026-11-04 实测）

初版报告 4 处结论与代码库现状不符，已按实测更正：

| 初版结论 | 复核结果 | 处置 |
|---|---|---|
| VERSION=7.4.5 vs pyproject=1.0.0，版本源分裂 | `VERSION` 实为 `1.0.0`，与 pyproject 一致；初始提交即如此，7.4.5 仅见于 `.qoder/repowiki/` 旧知识文档 | T-02 撤销 |
| Ruff 全项目 0 报错 | 实测 60 errors（I001×30、F401×18、F841×6、E402×4、E741×3、F541×2、N818×1）；仅 CI 限定 `--select F821,F811,F402` 通过 | 证据附录更正 + 新增 T-20 |
| 全量 pytest 338 passed / 4 failed，`test_llm_selfhost`×2 + `test_chat`×2 确定性回归 | 实测约 1065 用例 / 5 分 31 秒；两次运行一次全绿、一次 1 failed（`test_misc.py::TestAuthMeNotLoggedIn::test_me_unauthorized`，200≠401，偶发）；原 4 个用例现均通过 | T-11 阻塞项重写 |
| 后端「6 个 >1000 行大文件」，仅点名 chat.py | 业务代码确为 6 个，但漏列 `core/cli_engine/context_export.py`（1716 行）、`core/insight_board.py`（1127）、`core/audio_recording.py`（1039） | 新增 T-19 |

另：`requirements.txt` 第 31 行注明「scipy 已移除」，第 35 行仍写「numpy + scipy」，注释自相矛盾（已并入 T-01 修正项）。

---

## 二、P0 立即处理（本周内，均为小改动）

### ☑ T-01 修复 pyproject.toml 与 requirements.txt 依赖不一致

- [x] 从 `pyproject.toml` 的 `dependencies` 移除 `scipy>=1.14.0`（代码已用 numpy 替代，requirements.txt 已注明移除）
- [x] 向 `pyproject.toml` 补充 `Babel>=2.14.0`、`pywebview>=5.0.0`（requirements.txt 有而 pyproject 缺失）
- [x] 逐项 diff 两个清单，确认其余依赖完全一致
- [x] 修正 `requirements.txt` 第 35 行「实时说话人分离使用纯本地 MFCC 聚类（numpy + scipy）」注释，与第 31 行「scipy 已移除」统一

**位置**：`pyproject.toml` `[project].dependencies`、`requirements.txt`
**影响**：`pip install -e .` 与 `pip install -r requirements.txt` 当前会安装不同依赖集；scipy 被错误引入增加包体积
**工作量**：0.5h
**验收标准**：两清单依赖集合一致（除注释项）；`pip install -e .` 后 `python -c "import babel, webview"` 成功
**完成记录**：2026-11-04 完成。双清单经 `tomllib` 逐项 diff，各 16 项、差集为空；`pip install -e .` 元数据构建通过，`import babel, webview` 成功。遗留：`scripts/eval_voiceprint*.py`、`scripts/sweep_threshold.py` 三个离线评测脚本仍 `import scipy`，现改为靠传递依赖（librosa / scikit-learn）间接提供，未按本项范围声明为独立 extra，待单独分诊。

### ❎ T-02 ~~统一版本源（VERSION vs pyproject.toml）~~ — 已撤销

> 复核结论：`VERSION` 实为 `1.0.0`，与 `pyproject.toml` 的 `version = "1.0.0"` 一致，且自初始提交起即如此。初版所称 `VERSION=7.4.5` 仅存在于 `.qoder/repowiki/` 的过期知识文档，非当前代码事实。**该项无问题，不执行。**
>
> 遗留可选动作：`CONTRIBUTING.md` 可补一句「版本号唯一事实源为 `VERSION`」，属文档完善，非整改项。

### ☑ T-03 将前端 vitest 加入 CI

- [x] 在 `.github/workflows/ci.yml` 的 `frontend-build` job 中，于「类型检查」步骤后新增：
  ```yaml
  - name: 单元测试
    working-directory: frontend
    run: npm run test:unit
  ```
- [x] 本地先验证 `cd frontend && npm run test:unit` 全绿（当前 10 文件 60 用例，2.39s）
- [x] 推送后确认 CI 该步骤真实执行且通过（警惕 if 保护导致静默跳过的历史陷阱）

**位置**：`.github/workflows/ci.yml`
**影响**：已有 60 个前端测试完全不在 CI 中，前端回归无防护
**工作量**：0.5h
**验收标准**：CI 运行记录中可见「单元测试」步骤且为绿灯；故意改坏一个断言能被 CI 拦截（验证后还原）
**完成记录**：2026-11-04 完成。`ci.yml` 的 `frontend-build` job 已在「类型检查」后插入「单元测试」步骤，YAML 解析通过、步骤顺序为 检出代码→安装 Node.js→安装依赖→类型检查→单元测试→构建，且该 job 与步骤均无 `if` 保护。本地 `npm run test:unit` 10 文件 60 用例全绿（2.13s）；另以临时失败用例验证退出码为 1（可拦截）后已删除还原。推送后 CI #136（commit f053e9a）全绿，耗时 2m47s。

### ☑ T-04 修复 3 个 vue/no-use-v-if-with-v-for 错误

- [x] 运行 `cd frontend && npx eslint src/ 2>&1 | grep "no-use-v-if-with-v-for"` 定位 3 处
- [x] 将 v-if 条件移入 computed（`sectionTitleChars` 在 `!panelMounted` 时返回空数组），三处 `<template>` 标签仅保留 `v-for`
- [x] vitest 10 文件 60 用例全绿；vue-tsc --noEmit 无报错；无需补测试（渲染逻辑未变，仅守卫从模板移到数据层）

**位置**：`frontend/src/components/layout/ai/AiContextPanel.vue`（3 处，行号 74/108/126，均为 section 标题逐字显现动画的 `<template>` 标签）
**影响**：Vue 官方明确禁止的写法，v-for 优先级高于 v-if 导致每次渲染都执行过滤，且易产生逻辑 bug
**工作量**：0.3h
**验收标准**：`npx eslint src/` 中该规则 error 数为 0；相关页面手动验证渲染正常
**完成记录**：2026-11-04 完成。三处同属 `AiContextPanel.vue` 的 section 标题逐字显现模板，均为 `<template v-if="panelMounted" v-for="...">`。修复方式：守卫条件上移到 `sectionTitleChars` computed——未 mounted 时返回空数组，已 mounted 时返回真实词列表，模板三处仅保留 v-for 指令。实测 `npx eslint src/` 的 error 总数从 35 降至 32（其余为 32 个 `require-button-label`，属 T-06 范围），该规则命中为 0。`npm run test:unit` 60 用例全绿；`npx vue-tsc --noEmit` 无报错。

### ☑ T-05 自动修复前端 1743 个缩进 warning

- [x] 在干净工作区执行 `cd frontend && npx eslint src/ --fix`
- [x] 运行 `npm run test:unit` 与 `npm run build` 确认无破坏
- [x] 单独提交（commit message 注明「纯格式修复，无逻辑变更」），避免与功能改动混合

**位置**：`frontend/src/`（主要是 `vue/html-indent`）
**影响**：diff 噪音大，代码风格不统一
**工作量**：0.5h
**验收标准**：`npx eslint src/` warning 数显著下降（目标 <100）；构建与测试全绿
**完成记录**：2026-11-04 完成。先将遗留改动单独提交（依赖文档清理、T-04 修复各一笔）腾出干净工作区，再执行 `npx eslint src/ --fix`，1743 个 warning 全部清零（剩 32 个 `require-button-label` error 属 T-06 范围）；diff 仅格式变化（+1642/-1640，增删行数对称，无逻辑改动）。`npm run test:unit` 10 文件 60 用例全绿（2.17s）；`npm run build` 成功（11.03s，仅既有 chunk 体积提示）。格式修复单独提交。

---

## 三、P1 近期改进（1-4 周，与功能开发并行）

### ☐ T-06 修复 32 个 require-button-label 无障碍错误

- [ ] 运行 `cd frontend && npx eslint src/ 2>&1 | grep "require-button-label"` 获取完整清单
- [ ] 逐个为图标按钮补充 `title` / `aria-label` / `data-tip` 之一，或迁移到 `IconButton` 组件（label 为必填 prop）
- [ ] 文案走 i18n（遵循翻译 key 模块前缀命名规范）

**位置**：`frontend/src/` 多个组件
**影响**：屏幕阅读器用户无法使用；自定义 ESLint 规则形同虚设
**工作量**：2-3h
**验收标准**：`npx eslint src/` error 数为 0
**完成记录**：＿＿＿＿

### ☐ T-07 在 CI 中启用 ESLint 门禁

- [ ] 前置：T-04、T-05、T-06 全部完成（error=0，warning 收敛）
- [ ] 在 `ci.yml` 的 `frontend-build` job 中新增：
  ```yaml
  - name: ESLint 检查
    working-directory: frontend
    run: npx eslint src/ --max-warnings=0
  ```
- [ ] 若 warning 无法一次清零，先 `--max-warnings=<当前基线数>` 棘轮式收紧

**位置**：`.github/workflows/ci.yml`
**影响**：防止新 lint error 再次进入
**工作量**：0.5h
**验收标准**：CI 出现 ESLint 步骤且绿灯；提交一个含 lint error 的测试分支能被拦截
**完成记录**：＿＿＿＿

### ☐ T-08 修复 BACKLOG 中两个数据安全级 bug

- [ ] **笔记丢失**：`GeneratingView` 切 Tab / 重建编辑器前强制 flush 未落盘内容；`loadTaskNotes()` 增加「本地有未保存修改则不覆盖」保护（现状仅 `artifactsStale` 覆盖「生成完成」一种场景，切 Tab 重建路径无保护）
- [ ] **全屏退出态不可见**：`onFullscreen()` 已能 enter/exit 切换，但按钮 title/图标固定为 `generating.toolbar.fullscreen`，不随 `fullscreenchange` 变化，用户看不到「退出全屏」入口；需补状态联动 + Esc 提示
- [ ] 修复后在 `docs/BACKLOG.md` 对应条目标 ✅ 并注明版本

**位置**：`docs/BACKLOG.md`「纪要页全屏按钮无退出入口，且放大后笔记内容丢失」条目；`frontend/src/views/GeneratingView.vue`、`frontend/src/composables/useGeneratingData.ts#L290-L293`
**影响**：用户数据丢失风险，优先级高于任何新功能
**工作量**：1 天
**验收标准**：手动复现原路径不再丢失笔记；全屏有可见退出入口；BACKLOG 已更新
**完成记录**：＿＿＿＿

### ☐ T-09 为最高风险 core 模块补充单元测试

- [ ] `tests/test_pipeline_runner.py`：覆盖 Stage1/Stage2 正常路径 + 瞬时错误重试 + 永久错误不重试（mock `classify_error`/`is_transient_error` 的输入异常）
- [ ] `tests/test_llm_core.py`：覆盖 `core/llm.py` 的超时包装、HTTP 错误包装、未配置 API Key 报错路径（全部 mock，不打真实 API）
- [ ] `tests/test_transcribe.py`：覆盖 `core/transcribe.py` 碎片合并与说话人归并逻辑（用固定 JSON fixture）
- [ ] 遵循既有约束：全部使用 mock，离线可运行，单文件 <20s

**位置**：`core/pipeline_runner.py`（737 行）、`core/llm.py`（693 行）、`core/transcribe.py`（729 行）——三者均无专属测试
**影响**：转写与纪要生成是产品核心链路，当前任何改动无自动化回归防护
**工作量**：1-2 天
**验收标准**：三个测试文件通过 `DASHSCOPE_API_KEY=test-key JWT_SECRET=test-secret pytest tests/test_pipeline_runner.py tests/test_llm_core.py tests/test_transcribe.py -q` 全绿
**完成记录**：＿＿＿＿

### ☐ T-10 打破 core/pipeline_runner.py 对 app 层的直接依赖（H-1 最小切入点）

- [ ] 将 `from app.settings_store import get_feature_flags` 与 `from app.task_store import save_task_to_disk, tasks` 改为**函数参数注入**或**延迟到函数体内 import**
- [ ] 同步处理 `app/task_store.py:318` 对 `core.pipeline_runner` 的反向 lazy import，明确单向依赖方向
- [ ] 验证：`python -c "import core.pipeline_runner"` 可在不加载 FastAPI app 的情况下成功（用 `sys.modules` 断言无 `app.*`）

**位置**：`core/pipeline_runner.py:22-23`、`app/task_store.py:318`、`app/store.py:147`
**影响**：这是 core↔app 循环依赖最严重的一处；解除后 core 管线可被 CLI/桌面端/测试独立复用
**工作量**：1 天
**验收标准**：`core/pipeline_runner.py` 模块级 import 中不再出现 `app.*`；既有冒烟测试全绿
**完成记录**：＿＿＿＿

### ☐ T-11 CI pytest 从仅冒烟扩展为全量（排除 eval 脚本）

> ⚠️ **已知阻塞（已复核重写）**：2026-11-04 实测全量 `pytest tests/ --ignore=tests/eval_local_engine -q` 为 **约 1065 用例 / 5 分 31 秒**；两次连续运行结果不一致——一次 1065 passed 全绿，一次 1064 passed / 1 failed（`tests/test_misc.py::TestAuthMeNotLoggedIn::test_me_unauthorized`，断言 200 == 401）。属**偶发 flaky**，非确定性回归。初版所称「338 passed / 4 failed，`test_llm_selfhost`×2 + `test_chat`×2」已不成立，这两个文件当前均通过。入 CI 前只需处置 `test_misc` 的 flaky 用例。

- [ ] 前置：T-09 完成，且本地确认全量测试可通过
- [ ] 本地基线：`DASHSCOPE_API_KEY=test-key JWT_SECRET=test-secret pytest tests/ --ignore=tests/eval_local_engine -q`，实测基线约 1065 用例 / 5.5 分钟，记录通过/失败/跳过数量
- [ ] **处置 flaky 用例**：
  - `tests/test_misc.py::TestAuthMeNotLoggedIn::test_me_unauthorized` — 偶发返回 200（期望 401），疑似测试间全局状态/登录态污染或鉴权中间件缓存，需定位根因后修复或加固 fixture 隔离
- [ ] 修复或显式 skip 其余不稳定项，标注 `@pytest.mark.skip(reason=...)` 并登记 BACKLOG
- [ ] 修改 `ci.yml` 的 backend-test 步骤为全量命令，设置 timeout（实测超过 5 分钟，建议 ≥15 分钟）

**位置**：`.github/workflows/ci.yml`、`tests/`（重点 `test_misc.py`）
**影响**：现有 43 个测试文件只有 1 个在 CI 中运行，其余全部是"本地自愿执行"；全量套件存在偶发 flaky，直接入 CI 会间歇性阻塞 PR
**工作量**：1 天（含处置 flaky 用例）
**验收标准**：本地全量 pytest 连续 3 次运行 0 failed；CI backend-test 步骤运行全量测试且绿灯；无静默 skip 未登记的用例
**完成记录**：＿＿＿＿

### ☐ T-12 清理 scripts/ 中的 SSH expect 脚本残留

- [ ] 确认 `scripts/_ssh_helper.exp`、`scripts/_ssh_long.exp` 未被 git 跟踪（`git ls-files scripts/ | grep exp`）
- [ ] 若仍被跟踪则 `git rm --cached`；本地文件移到仓库外或删除
- [ ] 在 `.gitignore` 中增加 `*.exp` 或 `scripts/_ssh_*` 防止再次误提交

**位置**：`scripts/_ssh_helper.exp`、`scripts/_ssh_long.exp`
**影响**：运维脚本含服务器连接方式，开源仓库中属敏感残留
**工作量**：0.5h
**验收标准**：`git ls-files | grep -E "\.exp$"` 输出为空
**完成记录**：＿＿＿＿

---

## 四、P2 中长期演进（1-3 个月，需专项排期）

### ☐ T-13 完成 core → app 反向依赖全面解除

- [ ] 将 `app/task_store.py` 的纯数据层（`tasks` 字典、`save_task_to_disk`、`TASKS_DIR`）下沉为 `core/task_store.py`
- [ ] 将 `app/settings_store.py` 的纯配置读取（`get_feature_flags`、`get_llm_config` 等）下沉为 `core/settings_store.py`
- [ ] `app/store.py`、`app/settings_store.py` 改为 re-export 兼容层，既有 import 路径不破坏
- [ ] 逐个改造剩余 5 个反向依赖模块：`core/agent_tools/impl.py`、`core/silence_detection.py`、`core/chat_actions.py`、`core/chat_context.py`、`core/chat_edits.py`
- [ ] 增加守护测试：扫描 `core/**/*.py` 模块级 import，断言无 `app.*`（可加入 CI）

**位置**：`core/` 6 个模块 + `app/store.py`、`app/task_store.py`、`app/settings_store.py`
**影响**：完成后 core 层可独立测试、可被桌面端/CLI/未来本地引擎安全复用
**工作量**：3-5 天
**验收标准**：`grep -rn "^from app\|^import app" core/ --include="*.py"` 输出为空；全量测试绿灯；守护测试进入 CI
**完成记录**：＿＿＿＿

### ☐ T-14 引入 Python lockfile

- [ ] 选型：`uv`（推荐，速度快、与 pip 兼容）或 `pip-tools`
- [ ] 生成 `requirements.lock`（或 `uv.lock`），提交入库
- [ ] `ci.yml` 与 `scripts/deploy.sh` 改为按 lockfile 安装（`uv pip install -r requirements.lock` / `pip install -r requirements.lock`）
- [ ] 在 `CONTRIBUTING.md` 注明依赖变更流程：改 requirements.txt → 重新生成 lock → 一并提交

**位置**：`requirements.txt`、`.github/workflows/ci.yml`、`scripts/deploy.sh`
**影响**：当前所有依赖仅 `>=` 下限约束，不同时间/环境安装版本可能不同，生产故障难复现，且有供应链漂移风险
**工作量**：1 天
**验收标准**：CI 与部署脚本均从 lockfile 安装；两次独立安装产生完全相同的依赖版本集
**完成记录**：＿＿＿＿

### ☐ T-15 拆分 app/routers/chat.py（1722 行）

- [ ] 前置：T-09/T-11 提供的测试防护就位
- [ ] 按职责拆为 3 个子模块：`chat_actions_routes.py`（动作检测与执行）、`chat_history_routes.py`（会话历史查询）、`chat_stream_routes.py`（SSE 流式响应）
- [ ] 原 `chat.py` 保留为 router 聚合入口（`include_router`），URL 前缀与行为不变
- [ ] 拆分前后运行全量测试 + 手动验证 AI 对话核心流程

**位置**：`app/routers/chat.py`
**影响**：最大 router，AI 对话所有逻辑集中，改动风险与理解成本最高
**工作量**：2 天
**验收标准**：单文件均 <600 行；API 路径与响应结构零变化；测试全绿
**完成记录**：＿＿＿＿

### ☐ T-16 拆分前端超大视图组件

- [ ] `LibraryView.vue`（1609 行）：各 Tab 内容提取为 `views/library/` 下独立子组件
- [ ] `GeneratingView.vue`（1426 行）：工具栏、同步状态指示器、各面板提取为 `views/generating/` 子组件（部分已有先例：`TranscriptPanel.vue`、`DecisionFlowPanel.vue`）
- [ ] `AiChatPanel.vue`（1246 行）+ `useAiChat.ts`（1001 行）：消息渲染、输入区、执行留痕分离
- [ ] 每拆一个组件跑一次 `npm run test:unit && npm run build`

**位置**：`frontend/src/views/LibraryView.vue`、`GeneratingView.vue`、`components/layout/ai/AiChatPanel.vue`、`composables/useAiChat.ts`
**影响**：前端四大高风险区域，LLM 辅助开发单次读取成本高，改动影响面广
**工作量**：2-3 天
**验收标准**：无 >1000 行的 .vue/.ts 业务文件（App.vue 除外可豁免至 ~600）；构建与测试全绿；页面行为零变化
**完成记录**：＿＿＿＿

### ☐ T-17 引入 mypy 基础类型检查

- [ ] `pyproject.toml` 增加 `[tool.optional-dependencies].dev` 中的 `mypy`，配置宽松基线（`ignore_missing_imports = true`，先不启用 strict）
- [ ] 第一阶段仅覆盖 `core/errors.py`、`core/fs_atomic.py`、`core/remote_config.py` 等纯逻辑模块
- [ ] CI 增加非阻断 step（`continue-on-error: true`）观察一周，再转为阻断
- [ ] 新代码要求带类型注解（写入 CONTRIBUTING.md）

**位置**：`pyproject.toml`、`.github/workflows/ci.yml`、`core/`
**影响**：类型错误当前只能运行时发现，大重构缺乏静态防护
**工作量**：1 周（渐进）
**验收标准**：mypy 在 CI 中运行；已覆盖模块 0 error
**完成记录**：＿＿＿＿

### ☐ T-18 BACKLOG 31 个未解决项分诊

- [ ] 对 `docs/BACKLOG.md` 中 31 个未标 ✅ 条目做一次分诊：`修复`（排入迭代）/ `合并`（重复项归并）/ `降级`（转为待定池）/ `关闭`（已失效）
- [ ] 其中「说话人分离实测极不准确」「AI 对话框快捷指令点击后不生成内容」「底部状态栏静态文案与真实路由不符」三项建议优先排期（涉及核心价值与用户信任）
- [ ] 分诊结论回写 BACKLOG，每条注明处置与目标版本

**位置**：`docs/BACKLOG.md`
**影响**：31 个悬置条目中含用户可见 bug，与新功能开发混淆问题根因
**工作量**：0.5 天（分诊）+ 按项排期
**验收标准**：BACKLOG 中每条未完成任务都有明确处置标签与目标版本，无"三无"条目
**完成记录**：＿＿＿＿

### ☐ T-19 拆分 core/cli_engine/context_export.py 等其余超大文件

> 复核补充：初版仅点名 `app/routers/chat.py`，漏列同期超标的 3 个业务文件。

- [ ] `core/cli_engine/context_export.py`（1716 行）：按上下文装配职责拆为模板拼装 / 数据裁剪 / 序列化三层
- [ ] `core/insight_board.py`（1127 行）：看板聚合与渲染分离
- [ ] `core/audio_recording.py`（1039 行）：采集、编码、落盘拆分
- [ ] 每拆一个跑一次相关专项测试，保持行为零变化

**位置**：`core/cli_engine/context_export.py`、`core/insight_board.py`、`core/audio_recording.py`
**影响**：后端第二、四、六大文件，LLM 辅助开发单次读取成本高，与 `chat.py` 同等风险
**工作量**：2 天
**验收标准**：后端业务代码无 >1000 行文件；测试全绿
**完成记录**：＿＿＿＿

### ☐ T-20 清理 Ruff 全项目 60 errors 并恢复全项目 lint 门禁

> 复核新增：初版记「Ruff 0 报错」，实测全项目 60 errors。

- [ ] `I001`×30：`ruff check . --fix` 自动整理 import 排序
- [ ] `F401`×18：删除未使用 import；确属 re-export 兼容层的补 `# noqa: F401`
- [ ] `F841`×6：清理未使用局部变量
- [ ] `E402`×4：已在 `pyproject.toml` 忽略却仍报出，确认是否因文件位于非项目根或 ruff 版本差异，补全 `extend-exclude` 或调整配置
- [ ] `E741`×3、`F541`×2、`N818`×1：逐项人工修正
- [ ] CI 后端 lint 由 `--select F821,F811,F402` 扩为全项目 `ruff check .`

**位置**：全仓库（重灾区 `app/routers/cloud_api.py`、`app/routers/import_tasks.py`、`core/import_parser.py`、`core/model_downloader.py`、多个 tests）
**影响**：未使用的 import/变量掩盖真实缺陷；CI 只查 3 条规则，其余规范无防护
**工作量**：1 天
**验收标准**：`ruff check .` 0 error；CI lint step 为全项目检查且绿灯
**完成记录**：＿＿＿＿

---

## 五、迭代健康门禁（每次 PR 合入 main 前执行）

### 后端

- [ ] `ruff check . --select F821,F811,F402` — 逻辑错误检查（CI 已有；T-20 完成后改为全项目 `ruff check .`）
- [ ] `pytest tests/test_smoke.py -q`（环境变量：`DASHSCOPE_API_KEY=test-key JWT_SECRET=test-secret`）— 冒烟测试（CI 已有）
- [ ] `pytest tests/test_<改动模块>.py -q` — 改动模块专项测试（本地执行）
- [ ] `python -c "import core.<改动模块>"` — 确认无 import 崩溃
- [ ] 新增 core 模块时确认模块级 import 无 `app.*`（T-13 完成前的人工检查，之后由守护测试接管）

### 前端

- [ ] `npx vue-tsc --noEmit` — 类型检查（CI 已有）
- [ ] `npm run test:unit` — 单元测试（T-03 后 CI 覆盖）
- [ ] `npx eslint src/ --max-warnings=0` — lint 检查（T-07 后 CI 覆盖）
- [ ] `npm run build` — 构建验证（CI 已有）

### 依赖与配置

- [ ] 改动 `requirements.txt` 时同步更新 `pyproject.toml`（T-14 完成后改为重新生成 lockfile）
- [ ] 新增依赖确认不含 `torch/torchaudio/funasr/modelscope`（AC-7 云精简包约束，`ci-local-engine-v2.yml` 强制）
- [ ] 改动 API 时同步更新 `docs/API_CONTRACTS.md`

### 文档与安全

- [ ] 新增 core 模块时更新 `docs/ARCHITECTURE.md` 模块表
- [ ] 修复 BACKLOG 条目后立即标 ✅ 并注明版本
- [ ] `git diff --cached | grep -iE "password|secret|token|api_key"` 复查无真实凭据入暂存区
- [ ] 确认 `.env`、`desktop-secrets.env`、`*.exp` 未被跟踪

---

## 六、任务总览表

| ID | 任务 | 优先级 | 工作量 | 前置依赖 | 状态 |
|---|---|---|---|---|---|
| T-01 | 依赖双清单统一 | P0 | 0.5h | — | ☑ 完成（2026-11-04） |
| T-02 | 版本源统一 | P0 | — | — | ❎ 撤销（无问题） |
| T-03 | vitest 入 CI | P0 | 0.5h | — | ☑ 完成（2026-11-04） |
| T-04 | 修复 v-if/v-for 错误 | P0 | 0.3h | — | ☑ 完成（2026-11-04） |
| T-05 | eslint --fix 缩进 | P0 | 0.5h | — | ☐ |
| T-06 | 修复 32 个无障碍 error | P1 | 2-3h | — | ☐ |
| T-07 | ESLint 入 CI 门禁 | P1 | 0.5h | T-04/05/06 | ☐ |
| T-08 | 修复笔记丢失+全屏 bug | P1 | 1d | — | ☐ |
| T-09 | 核心 core 模块补测试 | P1 | 1-2d | — | ☐ |
| T-10 | pipeline_runner 解耦 | P1 | 1d | — | ☐ |
| T-11 | CI 全量 pytest | P1 | 1d | T-09 | ☐ |
| T-12 | 清理 SSH expect 残留 | P1 | 0.5h | — | ☐ |
| T-13 | core→app 依赖全面解除 | P2 | 3-5d | T-10 | ☐ |
| T-14 | Python lockfile | P2 | 1d | T-01 | ☐ |
| T-15 | 拆分 chat.py | P2 | 2d | T-09/T-11 | ☐ |
| T-16 | 拆分前端超大组件 | P2 | 2-3d | T-03 | ☐ |
| T-17 | mypy 类型检查 | P2 | 1w | — | ☐ |
| T-18 | BACKLOG 分诊 | P2 | 0.5d | T-08 | ☐ |
| T-19 | 拆分其余后端超大文件 | P2 | 2d | T-09 | ☐ |
| T-20 | 清理 Ruff 60 errors | P2 | 1d | — | ☐ |

---

## 七、证据附录（2026-11-04 复核实测数据）

- 代码规模：Python 212 文件 / 65,075 行（排除 venv）；前端 TS+Vue 194 文件 / 40,787 行
- Ruff 全项目（配置 E/F/I/N/W，忽略 E501/E402/N806/N801/N812/N999）：**60 errors**（I001×30、F401×18、F841×6、E402×4、E741×3、F541×2、N818×1）；CI 限定 `--select F821,F811,F402` 为 **0 报错**
- 前端 ESLint：**32 errors**（`require-button-label`×32 — T-04 的 3 个 `no-use-v-if-with-v-for` 已于 2026-11-04 修复）+ **1743 warnings**，1743 条可 `--fix`
- 前端 vitest：10 文件 / 60 用例，全部通过（2.39s）
- 后端 pytest：`tests/ --ignore=tests/eval_local_engine` 约 **1065 用例 / 5 分 31 秒**；两次运行一绿一 flaky（`test_misc.py::test_me_unauthorized`）
- CI 现状：Ruff 仅 F821/F811/F402；pytest 仅 test_smoke.py；前端仅 vue-tsc + build，**无 vitest、无 eslint**
- core 模块无专属测试：76 个模块中仅 11 个有同名测试，即 **65 个无**（含 llm/transcribe/summarize/pipeline_runner/audio_recording 等核心链路）
- router 无专属测试：28 个 router 中约 25 个无（chat/settings/record/cloud_api 等）
- core→app 反向依赖：6 个模块（pipeline_runner / agent_tools.impl / silence_detection / chat_actions / chat_context / chat_edits）
- 依赖分歧：pyproject 多 scipy；缺 Babel、pywebview；`VERSION` 与 pyproject 均为 1.0.0（一致）→ **T-01 已修复（2026-11-04），双清单 16 项一致**
- 无 Python lockfile（无 uv.lock / requirements.lock / poetry.lock）
- 无 mypy 配置
- BACKLOG 未解决项：31 条（38 个标题 - 7 个 ✅）
- >1000 行大文件：后端业务代码 6 个（chat.py 1722、context_export.py 1716、settings.py 1349、insight_board.py 1127、record.py 1091、audio_recording.py 1039），前端 4 个（LibraryView 1609、GeneratingView 1426、AiChatPanel 1246、useAiChat 1001）
- SSH 残留：`git ls-files` 无 `.exp` 文件
- 敏感文件：`data/settings.json`（含真实 API Key）已被 `.gitignore` 覆盖，无泄漏
