---
id: QA-R1-DEFECTS
title: QA-R1 验收缺陷修复派工说明（DEF-QA-R1-01/02/03/04）
version: 1.0.0
status: dispatched（项目方 2026-09-24 批准派工；Windows 项按项目方裁决顺延至下一环节）
date: 2026-09-24
source: docs/QA-R1-LOCAL-ENGINE-ACCEPTANCE.md（commit `854be3a`，分支 `qa/local-engine-r1-20260924`）
prd: docs/PRD-LOCAL-ENGINE.md §10（AC-1 / AC-4 / AC-5）
related:
  - docs/WP-G-R8-PACKAGING-DISPATCH.md
  - docs/ROADMAP.md v10「派工执行记录」
owners:
  - 后端工程师 `a4cdbd0ca795`（DEF-01 / DEF-02 生成侧 / DEF-03 并入 WP-H / DEF-04 端点侧）
  - 前端开发工程师 `d1b77737cde5`（DEF-02 导出入口 / DEF-04 回退 UI 与置灰）
approvers: 项目方（2026-09-24 裁决：可以派工；先跑通 macOS，Windows 放下一环节；修复后再 push）
---

# QA-R1 缺陷修复派工说明

## 0. 总口径（产品裁决，不得静默变通）

1. **基线 FAIL 已确认**：QA-R1 第一轮（venv 形态 · macOS · `fc5c72f`）总判定 FAIL，本报告接受、不复议。
2. **修复顺序**：DEF-01（P0）先行 → DEF-03（与其同引擎域，合并处置）→ DEF-04 / DEF-02。DEF-01 未修复前，**禁止**任何对外材料强化「数据永不出设备 / 断网闭环已成立」表述（README 现有 🚧 开发中标注保留）。
3. **docx 裁决**：DEF-02 选择**实现 docx**，AC-1 口径**不收敛**为 md-only。理由：docx 是企业会议纪要的主流交付格式，属目标用户真实交付物；`python-docx` 已在依赖（requirements.txt:38），边际成本低。
4. **AC-5 承诺口径**：不降级文字，收敛定义为「**运行期**零非 localhost 出网（含模型加载期）；模型首次获取（下载）需联网，属获取期行为」。DEF-01 修复后由 QA 复跑死端口代理抓包正式判 AC-5。
5. **平台范围**：本轮修复与回归验证**以 macOS 为准**（项目方裁决）；Windows 真机项（含 AC-10 Win L1）顺延至下一环节，随 WP-G 冻结包与第二轮验收处理。
6. **入库纪律**：各项目在独立 worktree 内提交（同 WP-G/WP-H 已下发纪律）；**修复完成前不 push origin 合并**——QA 产物 commit `854be3a` 也按项目方指令保持本地待推，随本轮修复一起入库。

## 1. 交付物索引（证据已入库）

- 验收报告：`docs/QA-R1-LOCAL-ENGINE-ACCEPTANCE.md`（worktree 分支 `qa/local-engine-r1-20260924` @ `854be3a`）
- 复现脚本：`tests/eval_local_engine/qa_r1_{offline_probe,asr_mem,downstream}.py`（同 commit）
- 证据目录（gitignored）：`.eval_local_engine/qa_r1/`（T1/T2 失败日志、T3 修复方向验证日志等）

## 2. 逐单任务书

### DEF-QA-R1-01｜P0｜断网下模型加载失败（ModelScope ID 强制出网）

- **归属**：后端工程师 `a4cdbd0ca795`
- **建议分支**：`fix/qa-r1-def01-offline-model-load`
- **现象/根因**：`core/engine_worker.py:88`（`_get_asr_model`）与 `:105`（`_get_spk_model`）以 ModelScope ID 调 `funasr.AutoModel(disable_update=True)`；`disable_update=True` 不阻止 modelscope 的 `GET modelscope.cn/api/v1/models/<id>/repo/files` 元数据请求，断网下 5 次重试全失败 → 模型未注册 → 断网闭环第一步即断裂（`core/engine_worker.py:93-106` 同源影响声纹姓名化）。
- **修复方向（QA probe T3 已验证可行）**：`AutoModel` 入参改为**本地文件系统路径**，经 `core.model_registry.get_model_root(key)` 解析到 `data/models/hub/iic/<model>`；模型缺失时给可行动错误（引导下载），不得隐式回连。
- **Done 判据**：
  1. 死端口代理（`HTTP(S)_PROXY=http://127.0.0.1:9`）+ 完整本地缓存下，ASR 与 CAM++ 均加载成功并出真实结果（复现入口：`qa_r1_offline_probe.py` 的 T1 场景改后须 PASS）。
  2. 新增回归测试：「断网（modelscope.cn 不可达）下引擎可加载并推理」，纳入 `ci-local-engine` 链路。
  3. 全仓 grep 确认 local 运行期无新增非 localhost 出网点；有网首下链路（项目下载器）行为不变。
- **风险提示**：冻结包形态（WP-G）下路径解析另受相对路径缺陷 B-2 影响（见 WP-G 派工单 §2），修复时用绝对路径锚点，勿留 `Path("data/models")` 相对写法。

### DEF-QA-R1-03｜P1｜30 分钟首请求 ≈190s 超 ENGINE_REQUEST_TIMEOUT=180s

- **归属**：后端工程师 `a4cdbd0ca795`，**并入 WP-H 超时口径一并处置**
- **依据**：模型惰性加载 ⇒ 首个 ASR 请求 = 加载 15.7s + 推理 174.3s ≈ 190s > `core/engine_host.py:31` 的 180s ⇒ 预计整场 `engine_timeout`（推导值，置信中高，未活体观测，因被 DEF-01 前置阻断）。
- **修复方向（三选一或组合，回报产品后定）**：① 引擎启动**预热**（加载移出首请求，推荐）；② 分段送推理；③ 上调/可配置 `ENGINE_REQUEST_TIMEOUT`。
- **Done 判据**：macOS 真机 30 分钟会议在 app 路径整场成功、无 `engine_timeout`；补 30/60 分钟不整场失败回归（对齐第二轮 AC-9）。冻结态冷 import 可达 86s，预热须覆盖该形态裕量声明。

### DEF-QA-R1-04｜P1｜AC-4 回退「切云端重跑」通路与内网置灰缺失

- **归属**：后端（端点）+ 前端 `d1b77737cde5`（UI）
- **现状缺口**（报告 §2.4）：`can_fallback_cloud` 落盘但前端零引用、无 router 消费；无 `engine_override=cloud` 重试端点（`/api/tasks/{id}/retranscribe` 只按当前设置重跑）；引擎下拉无云端置灰逻辑（现有置灰是「本地 LLM 预设不可达」，非 AC-4 要求）。
- **修复方向**：后端新增/改造重试端点支持显式 `engine_override=cloud`（保持任务与笔记状态不丢失，复用 `pipeline_runner.on_failure` 落盘语义）；前端在失败态消费 `can_fallback_cloud`：`True` ⇒ 渲染「切云端重试」按钮 + **显式确认**（含数据上云告知）；`False` ⇒ 置灰 + 说明原因（纯内网不可用云端）。
- **Done 判据**：AC-4 两子项（切云端重跑引导 / 纯内网置灰）在 macOS 真机浏览器 E2E 可演示；回归不得破坏「任务状态不丢失」现有通过项。

### DEF-QA-R1-02｜P1｜docx 导出未实现

- **归属**：后端（生成）+ 前端（入口）
- **现状**：`/api/download/{task_id}` 仅回 `.md`（`app/routers/tasks.py:200-220`）；`python-docx` 仅用于知识库读取（`core/project_index.py`）；`LibraryView.vue:461` `batchExport()` 为 alert 占位。
- **修复方向**：新增 md→docx 导出（标题/说话人段落/时间戳映射为 Word 结构，中文不乱码）；下载端点支持格式参数；前端批量导出接真实现。
- **Done 判据**：真实会议纪要导出的 docx 可被 Word/WPS 正常打开、结构完整；批量导出无 alert 占位残留；AC-1 导出子项在第二轮复测 PASS。

## 3. 第二轮验收前置条件（QA-R2 启动门）

1. DEF-01/02/03/04 修复合入并 push；
2. AC-2 人工听校 `refs/SEG-*_human_ref.txt` 回填（**仍待项目方指定听校人**）；
3. WP-G 冻结包产物可用（AC-7/9/10 与冻结包形态依赖）；
4. OBS-QA-R1-01：云端 voiceprint-service 重部署 + `scripts/backfill_voiceprints.py` 注册表回填，第二轮做线上跨网络复测。
5. 流程教训（产品侧已登记）：WP-C 早前「全程离线」结论疑在有网环境得出——**第二轮所有离线判定强制使用死端口代理法**，不接受无抓包佐证的离线声明。

## 4. 回报要求

各 owner 完成后在本文件追加「执行进展」小节（commit 链接 + 回归证据路径）；判定建议值技术不可行的，回报产品，不得静默变通。

---

## 5. 执行进展（后端工程师 a4cdbd0ca795，2026-09-24）

**分支**：`fix/qa-r1-def01-offline-model-load`（worktree `../oms-wt-def01`；按项目方裁决本轮仅本地提交、暂不 push）
**代码 commit**：`23b6da6` fix(qa-r1): 断网模型加载/引擎预热/云端显式回退重试/docx 导出（DEF-01/02/03/04 后端）

### 各缺陷处置与 Done 判据对照

| 缺陷 | 处置 | 判据证据 |
|------|------|----------|
| DEF-01(P0) | `engine_worker` 模型入参改经 `model_registry` 解析的本地绝对路径（相对 `model_dir` 锚定绝对化 `MODELSCOPE_CACHE`，同时承接 WP-G B-2 冻结态形态）；权重缺失→`models_missing` 可行动错误（校验先于 funasr import），运行期零隐式出网 | ① 死端口代理（`HTTP(S)_PROXY=http://127.0.0.1:9`）活体探针全过：`RESULT=QA_R1_FIX_OFFLINE_PASS`，日志 `.eval_local_engine/qa_r1_fix/ac1_offline_probe_after_fix.log`（探针脚本 `tests/eval_local_engine/qa_r1fix_offline_probe.py`，走 EngineHost 项目代码路径，强于裸 AutoModel 探针）；② 断网回归 17 项已入 ci-local-engine-v2 新 job `offline-load-guard`；③ grep 复核本地运行期无新增非 localhost 出网；④ 首次联网下载路径未改动 |
| DEF-03(P1) | 采派工单推荐方案①：协议新增 `warmup` 命令，宿主健康检查通过后后台预热；`ENGINE_WARMUP_TIMEOUT=300`（留量声明覆盖冻结态冷 import ≈86s + 双模型加载 ≈32s + 余量，测试钉死）；WP-H 时长感知超时口径不变 | macOS 实测（离线代理下）：warmup 22.9s done；首个 ASR 仅 1.9s（加载已移出）；30min 整场 infer 157.4s < 预算 960s，零 `engine_timeout`。**口径申报（非静默变通）**：30min 证据为引擎路径（EngineHost 子进程）活体，未含完整 FastAPI 上传链路，全 app 真机演示留待 QA-R2；协议守护双防线（worker `_quiet_stdout` fd 级屏蔽 + 宿主非 JSON 行重同步）系 QA 未列的实证必要修复（funasr 加载 print 污染 stdout 曾致预热响应被打断） |
| DEF-04 后端 | `POST /api/tasks/{id}/retranscribe` 支持可选 body `{"engine_override":"cloud"}`：白名单仅 cloud（其余 400，防误配静默上云）+ `is_cloud_enabled` 预检 400；透传至 `transcribe_audio`；仅重置失败语义字段（新增清 `error_code`/`can_fallback_cloud`），音频/笔记/绑定状态不动；无 body 旧调用完全兼容 | `tests/test_qa_r1_defects.py::TestEngineOverride` 5 项（含笔记保留断言）。**给前端的契约**：失败任务读 `task.error_code` + `task.can_fallback_cloud`；`True`⇒渲染「切云端重试」按钮，显式确认后 `POST …/retranscribe` body `{"engine_override":"cloud"}`；`False`⇒置灰说明。UI 消费与浏览器 E2E 归前端 d1b77737cde5 |
| DEF-02 后端 | 新增 `core/docx_export.py`（md→docx：标题 1–6/有序无序列表/段内粗斜体/说话人段落原文保留；`w:eastAsia` 宋体防乱码）；`GET /api/download/{task_id}?format=md|docx`（默认 md 向后兼容，其余格式 400）；删除任务连带清理 `.docx` 伴生文件。python-docx 为既有依赖无新增 | `TestDocxExport` 3 项 + 真实 QA 样张经 macOS `textutil` 解析通过（中文正常、结构完整）：`.eval_local_engine/qa_r1_fix/real_summary_sample.docx`。已知外观口径：Word List Number 全局连续编号（跨列表接续），批量导出入口归前端 |

### 验证账目

- 新增测试 17 passed；本地引擎既有套件 40 passed 复跑通过；CI ruff（`--select F821,F811,F402`）通过。
- 全量后端套件 3 失败（test_chat×2 缺 `.env` key、TestPhilosophyRandom×1 缺 gitignored 数据）经 `git stash` roundtrip 证明为预存在环境项，与本轮改动无关。
- code-review 门禁：Approve，报告 `docs/code-review-open-meeting-scribe-qa-r1-fix.md`（两处提交前修复：spk import 移出静默块残留、测试落盘泄漏打桩）。

### 未尽事项（移交/后续）

1. **Windows 冻结形态**：按项目方裁决顺延下一环节；`offline-load-guard` job 已在 linux 纯打桩层先行守护。
2. **QA-R2 复判**：DEF-01 Done 判据 1 的正式复判建议 QA 按 §3.5 死端口代理法在本修复分支上重跑（本方活体证据见上，属自证需他验）。
3. **前端依赖项**：DEF-04 失败态 UI（can_fallback_cloud 消费/显式确认/置灰）与 DEF-02 批量导出真实现，契约见上表。
4. **冻结包相对路径锚点（WP-G B-2）**：已由 `MODELSCOPE_CACHE` 绝对化锚点统一承接，WP-G 合入后建议冒烟复认一次。
5. **本轮仅本地提交**：4 项修复齐备后按裁决 push + PR；合入为 QA-R2 启动门 §3.1 前置。

---

## 6. 执行进展（前端工程师 d1b77737cde5，2026-09-24）

### 前端｜DEF-QA-R1-04（AC-4 回退 UI）+ DEF-QA-R1-02（批量导出）

- **分支 / worktree**：`fix/qa-r1-def04-def02-frontend-20260924`（独立 worktree `../oms-wt-def04-fe`，未在主工作区切分支）
- **commit**：`cf480daa4f7c89b817d35068341f19c11ffaf82c`（本地提交，**未 push origin**，待后端对齐后统一合入）
- **改动面**：13 文件 +448/−9。核心：`api/types.ts`（Task 增 `error_code`/`can_fallback_cloud` 可选字段）、`api/tasks.ts`（`retranscribe` 支持 `engineOverride:'cloud'`、新增 `downloadSummaryUrl(format)`）、`composables/useGeneratingData.ts`（`isLocalEngineFailure`/`canFallbackCloud`/`cloudFallbackBlocked` 计算 + `local_engine` 失败态文案）、`views/GeneratingView.vue`（失败卡片：可回退⇒「切云端重试」按钮 + 显式确认弹窗含数据上云告知；不可回退⇒置灰 + 原因说明）、`views/LibraryView.vue`（`batchExport()` alert 占位替换为 docx/md 格式选择弹窗 + 真实下载）、i18n（zh-CN/en）、`styles/meeting-view.css`。
- **契约登记**：`docs/API_CONTRACTS.md` 新增 §11「本地应用内部端点（QA-R1 缺陷修复批次·先行登记）」，登记 `POST /api/tasks/{id}/retranscribe`（可选 body `{"engine_override":"cloud"}`）、`GET /api/download/{id}?format=docx|md`（默认 md）、任务 JSON 失败字段；标注前端已实现、后端 `a4cdbd0ca795` 合入前确认。
- **macOS 真机浏览器 E2E 证据**（`/tmp/qa-r1-def04-fe-e2e/`）：
  - `02_failure_cloud_true.png` — `can_fallback_cloud=True` 失败态渲染可用「Retry via cloud」按钮；
  - `03b_cloud_confirm_dialog.png` — 点击后弹出显式确认弹窗（含数据上云告知文案）；
  - `04_dialog_cancelled.png` — 取消关闭弹窗、不触发重试；
  - `05_intranet_greyed.png` — `can_fallback_cloud=False`（纯内网）按钮 `disabled`/`aria-disabled=true` + 置灰原因说明；
  - `06_library_page.png`/`07_export_dialog.png`/`08_export_confirmed.png` — 批量选择 2 个已完成会议→导出弹窗（docx/md 单选）→确认后触发 2 个 `/api/download/{id}?format=docx` 下载、toast「Export started for 2 meeting(s)」、`window.alert` 调用计数为 0（无 alert 残留）；md 格式路径同样验证通过（`?format=md`）。
- **验证环境**：worktree 后端 8010 + vite dev 5173（临时 `vite.config.e2e.ts`，验证后已删除），种子任务落 `data/tasks`（gitignored）；用户主工作区 8000 后端与浏览器标签未受影响。
- **未尽事项 / 残余风险**：
  1. 后端 `engine_override=cloud` 重试端点与 `download?format=docx` 尚未由 `a4cdbd0ca795` 实现；契约已在 API_CONTRACTS.md §11 登记，**合入前须与后端对齐**。在后端就绪前：`retranscribe` 的 override 会被现有端点忽略、`download` 回退为 md。
  2. E2E 未真实点击「确认切云端重试」以免触发真实 pipeline / 数据上云；确认弹窗→调用 `retranscribe(engineOverride:'cloud')` 的代码路径经静态走查与取消路径验证，真机云端重跑回归待后端端点就绪后补。
  3. Windows 验证按项目方裁决顺延下一环节。
  4. `GeneratingView.vue` 2 处 eslint icon-button label 报错经核对为 main 基线既有（行号位移），非本轮引入，未改动。

---

## 7. 产品复核批注（合并时，2026-09-24，产品经理）

- §6 残余风险 1（后端端点未实现）**已闭环**：后端 `23b6da6` 已实现 `engine_override=cloud` 与 `download?format=docx`，合并前产品侧代码级抽查确认前后端字段名与端点一致（`tasks.py:61/207` ↔ `api/tasks.ts:40/50`），并在修复分支独立复跑 `tests/test_qa_r1_defects.py` **17/17 passed**；后端活体证据（断网探针 PASS、30min infer 157.4s、docx 样张、9 张前端 E2E 截图）已核验归档。
- QA-R2 启动门 §3.1（四缺陷合入并 push）随本次合并满足；正式复判仍须 QA 按死端口代理法在他验路径重跑。

---

## 8. 执行进展（DEF-FE-05，前端工程师 d1b77737cde5，2026-09-24）

**任务**：本地模式下状态栏模型名误导显示修复（产品经理派工单 DEF-FE-05）

- **分支 / worktree**：`fix/def-fe05-statusbar-local-models-20260924`（独立 worktree `../oms-wt-def-fe05`，基于 main `da47a03`；未在主工作区切分支）
- **代码 commit**：`8c4fd82b7faf45dc1e8fe1fd88cd93cdf26a6e66`（本地提交，**未 push**，待产品复核合入）
- **改动面**：3 文件 +39/−6。`App.vue`：`loadStatusModels` 感知 `engine.mode`——`local` 时状态栏 = 「FunASR 本地模型」+ LLM 段（按 `llm.provider`/`base_url` 判定 Ollama / LM Studio，显示实际 `llm.model`；model 为空兜底「本地模型」，跳转设置入口保留于引擎徽标点击）；云端/代理/直连分支维持原逻辑逐字不变；默认占位 `'paraformer-v2 + qwen-plus'` 改为中性 `'…'`（根因项）。i18n `common.usage.local_asr` / `local_model` zh-CN/en 双语同步。
- **契约核对（派工要求 3）**：判定数据源全部为 `/api/settings` 既有字段（`engine.mode`、`llm.provider`、`llm.base_url`、`llm.model`，见 `app/routers/settings.py:161-184` + `get_engine_config`），**无后端补字段需求，API_CONTRACTS.md 无变更**。
- **验证账目**：`vue-tsc -b` 通过；`eslint src/App.vue` 0 错；`vite build` 成功。
- **macOS 真机浏览器证据**（`/tmp/def-fe05-e2e/`；worktree 后端 8010 + vite 5174 临时代理配置，验证后已删除、进程已停）：
  - `02_local_zh_named.png` — zh-CN · local + Ollama（model=qwen3:8b）：状态栏「本地引擎 · FunASR 本地模型 + Ollama + qwen3:8b」；
  - `01_local_ollama_named.png` — 同上 en 态（"FunASR local model + Ollama + qwen3:8b"）；
  - `03_local_zh_empty_model.png` — local + model 为空：「FunASR 本地模型 + Ollama + 本地模型」（兜底 + 引擎徽标跳转入口在位）；
  - `04_cloud_regression_zh.png` / `05_cloud_regression_en.png` — 切回 cloud 模式：仍显示「paraformer-v2 + qwen-plus」，与修复前行为一致（回归不变）。
  - DOM 级断言（local 态）：`footer.status` 文本 `paraformer` 出现=False、`qwen-plus` 出现=False；console 错误探针 0 条、`window.alert` 调用 0 次（Done 判据 ①④）。
- **Done 判据对照**：① local 态无云端模型名（截图+DOM 断言）✔；② 云端显示回归不变（双态截图）✔；③ zh-CN/en 双语齐备 ✔；④ 无新增 alert/console 错误 ✔。
- **残余风险 / 说明**：
  1. 真机证据采自本机 macOS Chrome（QA 实例 :9333，项目内既有验证通道），非用户日常标签页；用户主实例（8000/5173）全程未触碰。
  2. LM Studio 判定（`:1234` / provider 文本）为按同一口径的对称实现，截图证据仅覆盖 Ollama 场景。
  3. local 模式下若 `llm.base_url` 误配为非 localhost 地址，LLM 段仅显示「本地模型」不显示任何模型名（防云端模型名泄漏的保守口径）。
