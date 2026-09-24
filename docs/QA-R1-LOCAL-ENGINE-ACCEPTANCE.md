---
title: QA-R1 — v10 本地引擎真机断网验收报告（第一轮 · 现状形态）
description: AC-1~AC-6 真机（macOS）断网验收判定，venv 形态，未经 PyInstaller 冻结包验证；Windows 侧 blocked-on-hardware
tags: ["qa", "acceptance", "offline", "local-engine", "ac-1", "ac-2", "ac-3", "ac-4", "ac-5", "ac-6", "QA-R1"]
author: QA工程师（waker 365d21fa11a0，QA-R1 派工执行）
created_at: "2026-09-24"
version: "1.0.0"
status: delivered
category: qa-acceptance
base_commit: "fc5c72f3ed44a00ec1fe93b8647582868b1997ce"
base_branch: "qa/local-engine-r1-20260924"
related_docs:
  - "docs/PRD-LOCAL-ENGINE.md"
  - "docs/ROADMAP.md"
  - "docs/SPIKE-R8-LOCAL-ENGINE.md"
  - "tests/eval_local_engine/EVAL-AC2-LOCAL-ENGINE.md"
---

# QA-R1：v10 本地引擎真机断网验收报告（第一轮 · 现状形态）

> **角色边界声明**：本报告为 QA 验收产物，全程**只测不改产品代码**、不做单元测试、不提交修复、不执行 git 提交动作。
> 需代码变更的缺陷以**可复现证据 + 开发移交单**交付。QA 脚本/报告为唯一新增文件。

## 本轮基线与形态（必读）

| 项 | 值 |
|---|---|
| **基线 commit** | `fc5c72f3ed44a00ec1fe93b8647582868b1997ce`（分支 `qa/local-engine-r1-20260924`，独立 worktree `../oms-wt-qa`） |
| **形态** | **venv 形态（spike funasr 1.4.16 / torch 2.14.0 / Python 3.11.15），未经 PyInstaller 冻结包验证** |
| **平台** | macOS（MacBook Pro M3 / Apple Silicon / arm64 / Darwin 25.6.0），CPU 推理基线 |
| **Windows 侧** | **`blocked-on-hardware`** — 本轮无可用 Windows 真机/虚拟机，**未执行**，不以 macOS 结论顶替 |
| **范围口径** | 依 `docs/ROADMAP.md:197`：本轮判 **AC-1（venv 形态）/ AC-2 / AC-3 / AC-4 / AC-5 / AC-6**；**AC-7 / AC-9 / AC-10 本轮不判**（依赖 WP-G/WP-I，留第二轮） |
| **样本** | `samples/智达方通全面预算系统方案交流.mp3`（118 分钟真实多人会议）截取 **30 分钟段**（@1200s，16kHz 单声道）——满足「≥30 分钟段」硬性要求 |

> ⚠️ **两轮不得混写**：本报告所有结论仅代表 **venv 形态 + 当前主干（fc5c72f）真机行为**，**不代表 WP-G 冻结包交付后的结论**。冻结包形态、Windows 平台、AC-7/9/10 留待第二轮。

---

## 0. 结论速览

| 验收项 | 判定 | 一句话依据 | 证据 |
|---|---|---|---|
| **AC-1** 断网闭环 | **不达标（FAIL）** | 出厂代码路径**真断网下模型加载失败**（`modelscope.cn` 元数据强依赖，DEF-QA-R1-01）；**docx 导出未实现**（DEF-QA-R1-02）。纪要+md 导出、ASR（经修复方向）离线可跑通 | §2.1 / probe T1·T2·T3 / downstream log |
| **AC-2** 质量 | **阻塞（blocked-on-human）** | 量化基线可复现（CER 7.31%/19.19%/24.70%），但**正式相对差距判定须人工听校回填 `refs/SEG-*_human_ref.txt`，QA 不能替代** | §2.2 / 移交一页 `QA-R1-AC2-HUMAN-PROOFREAD-HANDOFF.md` |
| **AC-3** 资源 | **通过（PASS）** | **30 分钟会议峰值 RSS 3.236GB ≤ 8GB（独立复测，补齐 WP-C 未复测项）**；模型总下载 **2.1GB ≤ 3GB** | §2.3 / `qa_r1_asr_mem.json` |
| **AC-4** 可回退 | **不达标（FAIL / 实现缺口）** | 任务状态落盘保留✓，但**无「一键切云端重跑」通路**（`can_fallback_cloud` 前端零引用、无 `engine_override=cloud` 端点）、**无纯内网云端选项置灰 UI** | §2.4 |
| **AC-5** 合规 | **不达标（1 处不一致）** | 流向矩阵三处（UI+README+SECURITY）齐备且互相一致；**业务数据边界与实测一致**；但「除 localhost 外零网络请求 / zero egress」的**绝对化表述被 `modelscope.cn` 加载期出网证伪** | §2.5 |
| **AC-6** 声纹 | **通过（PASS，代码/特征空间层）** | 真实权重独立复跑：跨端 cos=1.0、EER 0%、零迁移 4/4 命中且全过 margin、误识率相对差 ≤5% | §2.6 / `vp_cmn_fix.json` |

**本轮总判定：FAIL（不通过）** — AC-1 存在 P0 断网阻塞缺陷（DEF-QA-R1-01），「数据永不出设备 / 断网闭环」主张在**出厂代码路径 + 真断网**下于第一步（模型加载）即断裂。AC-3/AC-6 通过，AC-2 阻塞于人工，AC-4/AC-5 存在实现缺口。**建议：修复 DEF-QA-R1-01/02 后，随 WP-G 冻结包进行第二轮真机断网验收（含 Windows）。**

---

## 1. 环境与方法学

### 1.1 环境与资产

- 本地引擎权重：`data/models/hub/iic/`（seaco-paraformer-zh 953MB + ct-punc 1.1GB + cam++ 28MB + fsmn-vad 3.9MB = **2.1GB**），由项目下载器落位，含 `.integrity.json`。
- LLM：本机 Ollama `http://localhost:11434/v1`，实测可用模型含 `qwen3:8b`（推荐默认档）。
- 隔离：验收在独立 git worktree `../oms-wt-qa`（分支 `qa/local-engine-r1-20260924`，基线 `fc5c72f`）内执行；重资产（spike venv / ms_cache / data/models / data/uploads / voiceprint-service/models）以**符号链接**复用主副本，未复制、未污染他人 WIP。
- 抓包工具：mitmproxy 12.2.3（独立 venv `/tmp/qa-mitm-venv`）。

### 1.2 断网模拟方法（关键，决定证据可信度）

本轮以**死端口代理**（`HTTP(S)_PROXY=http://127.0.0.1:9`，连接必被 refused）模拟「真断网」，较 mitmproxy MITM 更贴近物理断网且不引入 TLS 证书伪影：

- **若流程在死端口代理下仍成功完成 ⇒ 证明其未依赖任何成功的非 localhost 出网**（任何外呼都会被 refused 而中断）。
- 纪要/导出环节叠加 `NO_PROXY=localhost,127.0.0.1`，使本地 Ollama 可用而其余外呼全部被拒 —— 即「纯内网 + 本地 LLM」真实形态。
- mitmproxy（:8080）作为辅助白名单抓包并行挂载；本轮功能性证据以死端口代理法为准。

> **方法学诚实声明**：死端口代理法捕获**遵循标准 proxy 环境变量的 HTTP(S) 客户端**（requests/httpx/urllib/modelscope 均遵循）的出网；不捕获绕过 proxy 的裸 socket 出网。结论已与代码审查（local 分支拒云端、`disable_update=True`）交叉印证。

### 1.3 复现入口（QA 脚本，均为本轮新增 QA 产物）

```
# AC-1 断网模型加载探针（T1 生产缓存 / T2 spike 缓存 / T3 本地路径修复方向）
.spike_local_engine/venv/bin/python tests/eval_local_engine/qa_r1_offline_probe.py <cache_dir> <wav>
# AC-3 30 分钟峰值内存 + AC-1 ASR 离线（本地路径法）
.spike_local_engine/venv/bin/python tests/eval_local_engine/qa_r1_asr_mem.py <30min.wav> <out.json> 1800
# AC-1 下游（纪要 + md 导出）纯内网模拟
venv/bin/python tests/eval_local_engine/qa_r1_downstream.py <dialogue.json> <out.md>
# AC-6 真实权重回归复跑
venv/bin/python tests/eval_local_engine/vp_cmn_fix_regression.py
# AC-2 量化复跑
venv/bin/python tests/eval_local_engine/compute_metrics.py
```

---

## 2. 逐项判定与证据

### 2.1 AC-1 断网闭环 — **不达标（FAIL）**

**要求**：录音→转写→分离→声纹姓名化→纪要（自接端点）→导出 docx/md 全流程断网走通；除 localhost 外零出网。

**实测分解（macOS / venv 形态）**：

| 环节 | 出厂代码路径（真断网） | 证据 |
|---|---|---|
| 转写 + 说话人分离 | **失败** — `engine_worker._get_asr_model` 以 ModelScope **ID** 调 `AutoModel`，加载期强制访问 `modelscope.cn /repo/files`；断网下 5 次重试全 refused → `RuntimeError: model not registered` | `ac1_offline_probe_T1.log`（生产 `data/models` 缓存）、`T2.log`（spike 缓存，**同样失败**，排除缓存布局因素） |
| 声纹姓名化 | **失败（同源）** — `LocalCamPlusProvider` 经 `engine_host.infer("embedding")` → `_get_spk_model` 同样以 ID 调 `AutoModel`，断网加载失败 | 代码路径 `core/engine_worker.py:93-106`；同 DEF-QA-R1-01 |
| 纪要（Ollama localhost） | **通过** — `base_url=localhost`、`_should_use_cloud()=False`，纯内网模拟下生成 616 字纪要 | `ac1_downstream_summary_export.log` |
| 导出 **md** | **通过** — `save_summary` 落盘 7607 bytes | `qa_r1_summary_SEG-2P.md` |
| 导出 **docx** | **未实现** — 全仓无 docx 导出；`/api/download/{task_id}` 仅回 `.md`（`media_type=text/markdown`）；`python-docx` 仅用于知识库**读取**；前端 `batchExport()` 为 `alert` 占位 | `ac1_downstream_summary_export.log`（`DOCX_EXPORTER_PRESENT=False`）；`app/routers/tasks.py:200-220`；`frontend/src/views/LibraryView.vue:461` |
| 除 localhost 外零出网 | **业务数据零出网✓**；但**加载期存在 `modelscope.cn` 非 localhost 出网**（见 AC-5） | probe T1/T2 日志 |

**结论**：断网闭环在**出厂代码路径**下于**第一步（模型加载）即断裂**，且 docx 导出缺失 → **AC-1 不达标**。
**Windows AC-1：`blocked-on-hardware`（未执行）。**

> **补充（修复方向已验证可行，供开发参考，非 QA 实施）**：probe **T3** 将 `AutoModel` 入参改为**本地文件系统路径**（`data/models/hub/iic/<model>`），在同一死端口断网模拟下 **LOAD_OK 13.8s + GENERATE_OK**（真实出文本）。即：以本地路径替代 ModelScope ID 解析，可使离线加载成立。证据 `ac1_offline_probe_T3.log`。

### 2.2 AC-2 质量 — **阻塞（blocked-on-human）**

**要求**：本地 WER 与 paraformer-v2 对人工真值的相对差距 ≤15%。

- 量化基线**可复现**（本轮重跑 `compute_metrics.py`，与 WP-C 完全一致）：CER(local｜cloud 伪参照) = **7.31% / 19.19% / 24.70%**（2P/4P/6P）；近似 DER(fresh) = 8.6% / 46.9% / 55.8%；说话人计数 2P✓、4P 本地 3/期望 4、6P 本地 4/期望 6。
- **正式相对差距判定挂起**：`refs/SEG-*_human_ref.txt` **尚不存在**（已确认），`compute_metrics.py:339-347` 的人工参照分支（`ac2_relative_gap_vs_humanref` / `ac2_pass_threshold_15pct`）待回填后自动出判定。**人工听校 QA 不能替代。**
- **QA 本轮动作**：将 53/59/78 句不确定项整理为**可交人工的一页移交单** → `tests/eval_local_engine/QA-R1-AC2-HUMAN-PROOFREAD-HANDOFF.md`，并标注**句边界漂移**注意事项（工作表 ⚠️ 行含 cloud/local 断句错位，须按音频内容而非行对齐裁决）。

**结论**：**blocked-on-human**（判定材料齐备，待项目方指定人回填）。

### 2.3 AC-3 资源 — **通过（PASS）**

**要求**：16GB 机型转写 30 分钟会议峰值内存 ≤8GB；模型总下载 ≤3GB。

| 指标 | 实测 | 门槛 | 判定 |
|---|---|---|---|
| **30 分钟会议峰值 RSS** | **3.236GB**（`ru_maxrss`=3,474,866,176 B，权威峰值） | ≤8GB | **✓** |
| 模型总下载体积 | **2.1GB**（含可选 ct-punc 1.1GB） | ≤3GB | **✓** |
| 推理墙钟 / RTF | 174.3s / **0.0968**（30 分钟） | — | 参考 |
| 模型加载 | 15.7s（本地路径，离线） | — | 参考 |

- **独立复测意义**：WP-C 沿用 Spike 10 分钟的 3.3GB 未独立复测；本轮以**真 30 分钟段**独立复测得 **3.236GB**，证实峰值内存**随时长非线性增长**（与 Spike「长度增长主要累加 VAD 段列表」一致），AC-3 内存门槛在 30 分钟尺度有充分裕量。
- **形态标注**：经**本地路径法**（DEF-QA-R1-01 修复方向）测得 —— 因出厂 ID 路径断网无法加载。**同一套权重与管线，内存表征对修复后出厂路径有效**；**venv 形态，未经冻结包验证**（冻结包内存留第二轮）。

证据：`qa_r1_asr_mem.json`、`ac3_asr_mem_run.log`。

### 2.4 AC-4 可回退 — **不达标（FAIL / 实现缺口）**

**要求**：本地失败可切云端重跑，任务与笔记状态不丢失；纯内网正确置灰。

| 子项 | 现状 | 证据 |
|---|---|---|
| 任务状态不丢失 | **✓（数据层）** — `pipeline_runner.on_failure` 置 `status=failed` 并 `save_task_to_disk`，音频与已存笔记不动 | `core/pipeline_runner.py:167-184` |
| 失败错误分类 + 回退标志 | **✓（后端）** — `LocalEngineError.can_fallback_cloud` 由 `is_cloud_enabled()` 驱动；纯内网（无 `CLOUD_API_URL/TOKEN`）⇒ `False` | `core/errors.py:16-38`、`core/engine_host.py:273-279` |
| **「一键切云端重跑」通路** | **✗ 缺失** — 无 `engine_override=cloud` 的重试端点；`/api/tasks/{id}/retranscribe` 只按**当前设置**重跑，用户须先手动切引擎模式；`can_fallback_cloud` 标志**落盘但无任何 router/前端消费** | `grep can_fallback_cloud frontend/src` = **0 命中**；`grep engine_override app/routers` = **0 命中** |
| **纯内网云端选项置灰（UI）** | **✗ 缺失** — 引擎模式下拉仅 `proxy/direct/local`（无 cloud 项可置灰）；唯一置灰逻辑是「本地 LLM 预设不可达置灰」，**非** AC-4 要求的内网云端置灰 | `frontend/src/views/SettingsView.vue:325-336`、`:1266-1270` |

**结论**：状态保留与后端标志到位，但 **PRD R7「切云端重试引导（显式确认）」与 AC-4「纯内网云端选项正确置灰」在 UI/端点层未实现** → **AC-4 不达标**。
**残余**：本轮**未跑浏览器端 E2E**（browser-harness 未执行）；且出厂离线 ASR 路径被 DEF-QA-R1-01 阻塞，无法在真断网下产生「本地失败→云端重跑」的活体链路。判定以代码证据为准。

### 2.5 AC-5 合规 — **不达标（1 处不一致）**

**要求**：数据流向矩阵上线（UI + README + SECURITY.md），与实测抓包一致。

**矩阵齐备性 + 三处一致性：✓**

| 载体 | 位置 | 内容 |
|---|---|---|
| SECURITY.md | `SECURITY.md:84-96`（§1.3） | 4 类数据 × 3 引擎流向表 + 「除 localhost 外零网络请求」承诺 |
| README | `README.md:33` / `README_zh-CN.md:30` | 链接至 SECURITY.md §1.3，主张「会议数据永不出设备」（标 🚧 开发中） |
| UI | `SettingsView.vue:421-443` + i18n `engine_cell_*_local` | 矩阵表；音频/转写/声纹「zero egress」、LLM「zero egress when using local Ollama」 |

**与实测一致性：**

- **业务数据边界：一致 ✓** — 音频/转写文本/声纹嵌入/纪要提示词在本地模式下**实测零非 localhost 出网**（downstream 纯内网模拟成功；ASR 离线运行无业务数据外呼）。矩阵各行（audio/transcript/voiceprint/llm_context）准确。
- **不一致 ✗（1 处）**：SECURITY.md:96「本地引擎模式下**除 localhost 外零网络请求**」与 UI「zero egress」为**绝对化表述**，被**模型加载期 `modelscope.cn /api/v1/models/.../repo/files` 出网**证伪（probe T1/T2 实证 5 次重试）。该出网**不含业务数据**（仅模型版本/文件清单元数据），但**违反「零非 localhost 请求」的字面承诺**，且正是 DEF-QA-R1-01 断网失败的根因。

**结论**：矩阵已上线且三处互相一致、业务数据边界与实测吻合；但「零非 localhost 请求」绝对化表述与实测**存在 1 处不一致** → **AC-5 不达标**（须待 DEF-QA-R1-01 修复消除加载期出网后，或将承诺口径收敛为「业务数据零出网；模型首次获取需联网，缓存后离线」）。

### 2.6 AC-6 声纹 — **通过（PASS，代码/特征空间层）**

**要求**：`0788390`（云端 `_extract_fbank` 加 CMN）修复后真机复测：真实权重下云/本地注册表零迁移互用、误识率相对差 ≤5%。

**本轮以真实权重独立复跑 `vp_cmn_fix_regression.py`（不联网，本地起共享权重 `campplus_cn_common.bin` 调修复后 `server.extract_embedding`，对比 QA 缓存的本地 FunASR 嵌入）：**

| 指标 | 实测 | 判据 | 判定 |
|---|---|---|---|
| 同片段 云(CMN) vs 本地(CMN) cos | **1.0**（8/8 片段；修复前 0.6834） | — | ✓ |
| 跨端 EER | **0.0%**（修复前 29.2%） | — | ✓ |
| 误识率相对差 | **≤5%**（`fpr_within=True`） | ≤5% | ✓ |
| 零迁移模拟 | **4/4 命中且全过 margin**（sim 0.866–0.954，margin 0.179–0.304；修复前仅 1/4） | top-1 命中 + 过门槛 | ✓ |

脚本自检输出 `[AC-6] eer_within=True fpr_within=True zm_correct=True zm_accepted=True → PASS`。

**结论**：CMN 修复在**真实权重、特征空间层**复测**通过**，云/本地注册表零迁移互用成立。

> **关键残余风险（必须随结论阅读）**：本复测验证的是**修复后 `server.py` 代码 + 共享权重**的特征空间一致性，**不等于**已验证：① **线上云端 voiceprint-service 已重新部署**使 CMN 生效；② **既有注册表 2 条 192 维 no-CMN 旧记录已回填**（`0788390` 部署须知明确：旧记录落在旧空间，与新 CMN 查询 cos~0.68，须经 `scripts/backfill_voiceprints.py` 从源音频重提取，源音频缺失则不可恢复）。本环境无可达的线上云端 voiceprint-service，**真实「云注册表 ↔ 本地查询」跨网络复测未执行** → 标 `blocked-on-deployment`。
> **附带发现（独立于本修复）**：`MATCH_THRESHOLD=0.50` 对远场会议素材偏低 —— 纯云同端 FPR@0.50 仍达 66.7%，建议按素材域重标定（既有产品参数问题，非本地引擎引入）。

---

## 3. 缺陷清单与开发移交单

> 依角色边界：以下均为**可复现证据 + 移交单**，**QA 不改业务代码**。严重度 P0=阻断发布 / P1=须修 / P2=建议。

### DEF-QA-R1-01（P0，阻断 AC-1/AC-5）：本地引擎断网下模型加载失败 —— ModelScope ID 解析强制出网

- **现象**：真断网（死端口代理）下，本地引擎加载 ASR/CAM++ 模型失败，`RuntimeError: model '...' is not registered`，断网闭环第一步即断裂。
- **根因**：`core/engine_worker.py:88`（`_get_asr_model`）与 `:105`（`_get_spk_model`）以 **ModelScope 模型 ID**（`iic/...`）调 `funasr.AutoModel(..., disable_update=True)`。`disable_update=True` **不阻止** modelscope 的 `GET https://modelscope.cn/api/v1/models/<id>/repo/files?Revision=master&Recursive=True` 元数据解析；权重虽已完整缓存（日志「Found legacy cache ... reusing」），仍须该请求成功才注册模型。断网 ⇒ 5 次重试全失败 ⇒ 模型未注册。
- **复现**：`qa_r1_offline_probe.py`，T1（`data/models`）与 T2（spike `ms_cache`）**均 FAIL**（排除缓存布局因素）。证据 `ac1_offline_probe_T1.log` / `T2.log`。
- **影响**：AC-1「断网闭环 / 数据永不出设备」在出厂代码路径不成立；AC-5「除 localhost 外零网络请求」被证伪；涉密/内网核心场景不可用。
- **修复方向（已验证可行，供开发）**：probe **T3** 证明——将 `AutoModel` 入参改为**本地文件系统路径**（用 `core.model_registry.get_model_root(key)` 解析到 `data/models/hub/iic/<model>`）替代 ModelScope ID，断网下 **LOAD_OK + GENERATE_OK**（`ac1_offline_probe_T3.log`）。请开发据此改造 `_get_asr_model`/`_get_spk_model`，并补一条「断网（无 modelscope.cn 可达）下引擎可加载并推理」的回归。
- **归属建议**：后端工程师（引擎/引擎子进程，WP-H/WP-I owner `a4cdbd0ca795`）。

### DEF-QA-R1-02（P1，阻断 AC-1）：docx 导出未实现

- **现象**：AC-1 要求「导出 docx/md」，实测**仅 md**，无 docx 导出。
- **证据**：全仓无 docx 导出实现；`app/routers/tasks.py:200-220` `/api/download/{task_id}` 仅回 `.md`（`text/markdown`）；`python-docx`（requirements.txt:38）仅用于 `core/project_index.py` **读取**；前端 `LibraryView.vue:461` `batchExport()` 为 `alert('功能待实现')` 占位。
- **影响**：AC-1 导出子项不达标。
- **建议**：补 docx 导出（可复用已依赖的 `python-docx` 生成），或经产品裁决将 AC-1 导出口径收敛为「md」（须同步 PRD/REQUIREMENT 与发布材料）。
- **归属建议**：后端 + 前端。

### DEF-QA-R1-03（P1，高风险，关联 WP-H）：30 分钟首次转写疑似超 `ENGINE_REQUEST_TIMEOUT=180s` 天花板

- **依据（实测分量 + 常量推导）**：`core/engine_host.py:31` `ENGINE_REQUEST_TIMEOUT=180`（模块常量，单次 `infer` 请求超时）。模型为**惰性加载**（`_get_asr_model` 首次 `_infer_asr` 触发），故**首个** ASR 请求含「加载 15.7s + 30 分钟推理 174.3s ≈ **190s** > 180s」⇒ 预计 `engine_timeout` 整场失败。
- **诚实标注**：本轮**未在出厂 app 路径活体观测到该超时**（因 DEF-QA-R1-01 先阻断离线 app 路径）；结论为**实测分量 + 常量算术推导**，置信中高。30 分钟 RTF 0.0968 已高于 Spike 10 分钟的 0.081，更长/更密集会议或更慢机器裕量更差。
- **建议**：与 WP-H「超时天花板」合并处置——引擎启动时**预热模型**（使加载不计入首个推理请求），或分段送推理，或上调/可配置 `ENGINE_REQUEST_TIMEOUT`；并补 30/60 分钟真机不整场失败的回归（对齐 AC-9 第二轮）。
- **归属建议**：后端工程师（WP-H owner）。

### DEF-QA-R1-04（P1，阻断 AC-4）：回退「切云端重跑」通路与内网置灰 UI 缺失

- **现象**：`can_fallback_cloud` 标志落盘但**前端零引用、无 router 消费**；无 `engine_override=cloud` 重试端点；引擎下拉无 cloud 项、无内网置灰逻辑。详见 §2.4。
- **影响**：AC-4「本地失败切云端重跑（显式引导）」与「纯内网云端选项正确置灰」未实现。
- **建议**：前端消费 `can_fallback_cloud` 渲染「切云端重试」按钮（显式确认）并在 `can_fallback_cloud=False` 时置灰 + 说明原因；或后端补带 `engine_override=cloud` 的重试端点。
- **归属建议**：前端 + 后端。

### OBS-QA-R1-01（P2，AC-6 部署残余）：CMN 修复的线上部署与注册表回填未验证

- 见 §2.6 残余风险：需重新部署云端 voiceprint-service 使 CMN 生效，并回填既有 2 条 no-CMN 旧记录（`scripts/backfill_voiceprints.py`），否则线上跨端零迁移仍会 cos~0.68。标 `blocked-on-deployment`，非本轮 venv/macOS 可判。
- **归属建议**：项目方/后端（部署）+ QA 第二轮（线上跨网络复测）。

---

## 4. 残余风险与未覆盖面

1. **Windows 全平台**：`blocked-on-hardware`，本轮**未执行**任何 Windows 项（AC-1/3/4/5/6 的 Windows 侧、AC-10 Win L1）。**严禁以 macOS 结论顶替。**
2. **冻结包形态**：本轮全为 **venv 形态**；PyInstaller 冻结包（WP-G）下的加载/内存/出网/超时行为**未验证**，留第二轮。冻结态 funasr 冷 import 可达 86s（Spike §3.2），可能进一步挤压 DEF-QA-R1-03 的超时裕量。
3. **AC-2 正式判定**：blocked-on-human，待 `refs/SEG-*_human_ref.txt` 回填。
4. **AC-4 活体 UI E2E**：本轮未跑 browser-harness；判定以代码证据为准。
5. **AC-6 线上跨网络复测**：blocked-on-deployment（云端服务重部署 + 注册表回填）。
6. **AC-1 声纹姓名化端到端**：因 DEF-QA-R1-01 阻断离线 embedding，未在断网下跑通「分离→姓名化」活体链路；AC-6 仅证明嵌入数学正确。
7. **DEF-QA-R1-03**：为推导性高风险，未活体观测。
8. **抓包方法学**：死端口代理法不捕获绕过 proxy 的裸 socket 出网（已与代码审查交叉印证）。

---

## 5. 产物索引（绝对路径）

**证据目录**：`/Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/.eval_local_engine/qa_r1/`

| 文件 | 内容 |
|---|---|
| `ac1_offline_probe_T1.log` | AC-1 断网加载失败（生产 `data/models` 缓存）— DEF-01 |
| `ac1_offline_probe_T2.log` | AC-1 断网加载失败（spike `ms_cache`）— 排除缓存布局因素 |
| `ac1_offline_probe_T3.log` | AC-1 本地路径法断网 **PASS** — DEF-01 修复方向验证 |
| `ac1_downstream_summary_export.log` | AC-1 纪要+md 导出纯内网 **PASS**；docx 缺失 |
| `qa_r1_summary_SEG-2P.md` | AC-1 md 导出实物（7607 bytes） |
| `ac3_asr_mem_run.log` / `qa_r1_asr_mem.json` | AC-3 30 分钟峰值 RSS 3.236GB + RTF/时长 |
| `ac6_rerun_stdout.log` | AC-6 真实权重回归复跑 PASS |
| `qa_r1_30min.wav` / `qa_r1_6s.wav` | 30 分钟 / 6 秒测试切片 |

**其余证据**：
- AC-6 结果 JSON：`/Users/wangyongliang/Documents/我的微云文件/409 Qoder/open-meeting-scribe/.eval_local_engine/results/vp_cmn_fix.json`
- AC-2 量化：`.../.eval_local_engine/results/metrics.json`；工作表 `.../tests/eval_local_engine/refs/SEG-{2P,4P,6P}_proofread_worksheet.md`
- AC-2 人工移交一页：`.../oms-wt-qa/tests/eval_local_engine/QA-R1-AC2-HUMAN-PROOFREAD-HANDOFF.md`
- QA 脚本（本轮新增，worktree）：`.../oms-wt-qa/tests/eval_local_engine/qa_r1_{offline_probe,asr_mem,downstream}.py`

> **产物存放说明（交付契约偏差披露）**：依 Bible 默认 QA 产物应置于受测仓库外独立目录；本轮**遵派工单显式指令**将报告落于仓库内 `docs/` 与 `tests/eval_local_engine/`（与 WP-C `EVAL-AC2` 同址，便于追溯），大文件/日志隔离于 gitignored `.eval_local_engine/qa_r1/`。此为派工单指定的偏差，特此披露。

---

## 6. 交付契约自检（Delivery Contract）

| # | 项 | 状态 |
|---|---|---|
| 1 | 请求范围（AC-1~AC-6）均有可执行证据或明确阻塞标注 | ✓ |
| 2 | 发现可复现、按严重度标注（P0/P1/P2 + 复现命令 + 日志路径） | ✓ |
| 3 | 跳过面/阻塞披露残余风险（Windows/冻结包/人工/部署/UI-E2E） | ✓（§4） |
| 4 | QA 产物不含产品 bug 修复（仅移交单 + QA 脚本） | ✓ |
| 5 | 协作结论报告（回消息产品经理） | ✓（见交付消息） |
| 6 | **无代码提交动作**（未 `git add`/`commit`/`push`/PR）——遵 Bible 角色边界，报告以文件形式置于 worktree，提交由 PM/开发执行 | ✓ |
| 7 | 材料→判定可追溯（PRD §10 / ROADMAP:197 / EVAL / Spike 逐项映射） | ✓ |
| 8-11 | 产物保存 + 绝对路径 + 大文件隔离 + 偏差披露 | ✓（§5） |

---

## 7. 最终结论

**本轮（QA-R1 · venv 形态 · macOS · 基线 fc5c72f）总判定：FAIL（不通过）。**

- **通过**：AC-3（30 分钟峰值 3.236GB≤8GB、模型 2.1GB≤3GB）、AC-6（真实权重特征空间层，附部署残余）。
- **不达标**：AC-1（DEF-01 断网加载 P0 + DEF-02 docx 缺失）、AC-4（DEF-04 回退通路/置灰缺失）、AC-5（零出网绝对化表述与实测 1 处不一致）。
- **阻塞**：AC-2（blocked-on-human）。
- **未执行**：Windows 全平台（blocked-on-hardware）、冻结包形态、AC-7/9/10（本轮不判）。

**建议**：优先修复 **DEF-QA-R1-01（P0）**，并处置 DEF-02/03/04；随后随 **WP-G 冻结包**开展**第二轮**真机断网验收（含 Windows 真机、冻结包形态、AC-6 线上跨网络复测、AC-2 人工回填后正式判定）。两轮结论严格分形态标注，不得混写。
