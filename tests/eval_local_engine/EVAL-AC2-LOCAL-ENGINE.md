---
title: EVAL-AC2 — 本地可选计算引擎 AC-2 评测体系报告（WP-C）
description: 本地 FunASR 全管线 vs 云端 paraformer-v2 的转写质量（CER/WER）、多说话人分离（近似 DER）、LLM 最低规格实验、声纹注册表云/本地兼容抽查（AC-6）的量化证据与判定
tags: ["evaluation", "offline", "funasr", "ac-2", "ac-6", "wer", "der", "voiceprint", "ollama", "qa"]
author: QA工程师（WP-C 派工执行）
created_at: "2026-09-23"
updated_at: "2026-09-23"
version: "1.0.0"
status: published
category: qa-evaluation
related_docs:
  - "docs/PRD-LOCAL-ENGINE.md"
  - "docs/SPIKE-R8-LOCAL-ENGINE.md"
  - "docs/REQUIREMENT_LOCAL_ENGINE.md"
  - "docs/adr/0018-本地可选计算引擎与声纹离线化.md"
---

# EVAL-AC2：本地引擎评测体系报告（WP-C）

> 角色边界声明：本报告为 QA 评测产物。全程**只测不改产品代码**、不做单元测试、不提交修复。
> 需要代码变更的缺陷（AC-6 声纹特征管线）以**可复现证据 + 开发移交单**形式交付，不由本角色修补。

## 0. 结论速览

| 验收项 | 判定 | 关键证据 |
|---|---|---|
| **AC-2** 本地 vs 云转写质量（WER 相对差距 ≤15%） | **待定（需人工校准）** | 已交付三层参照体系 + 人工校对工作表；伪参照 CER(local｜cloud) = 7.31% / 19.19% / 24.70%（2P/4P/6P）。正式相对差距须待 `refs/SEG-*_human_ref.txt` 回填后由脚本自动判定，QA 无法替代人工听校 |
| **AC-2 附带** 多说话人分离（DER 近似） | **不达标（趋势明确）** | 近似 DER：fresh 参照 8.6% / 46.9% / 55.8%；说话人计数 2P ✓(2/2)、4P 本地 3 vs 期望 4、6P 本地 4 vs 期望 6。重叠语音/远场是主因 |
| **AC-3 附带** 本地推理时延 | **通过** | RTF 0.069–0.076（27–35s 转写 6–8min 音频），远优于分段批处理体验门槛；峰值内存沿用 Spike §2.2 RSS 3.3GB（本任务未独立复测，见残余风险） |
| **AC-6** 声纹注册表云/本地零迁移互用（误识率相对差异 ≤5%） | **不达标 → 开发移交** | 零迁移 top-1 命中 4/4，但仅 1/4 通过 margin 门槛；跨端 EER 29.2% vs 同端 0–4.2%。根因已定位为 **CMN 特征管线差异**（双向 cos=1.0000 复刻证明） |
| **WP-C-3** LLM 最低规格 | **已产出推荐表** | 推荐默认 **qwen3:8b**、可用下限 **qwen3:4b**；qwen2.5 ≤3B-instruct 不达可用档。已回填 PRD R4 `model_tier` 与需求记录未决问题 2 |

---

## 1. 任务范围与方法

派工任务包 **WP-C：AC-2 评测体系**，5 项交付：

1. AC-2 正式评测脚本：samples/ ≥3 段真实中文会议（覆盖 2/4/6 人）→ 本地 FunASR 全管线转写 → 与参照算 WER/CER；云端 DashScope paraformer-v2 跑同批样本作参照。
2. 多说话人分离补测（2/4/6 人，DER 或可解释近似指标，Spike 遗留第 3 项）。
3. LLM 最低规格实验（Ollama，向下探更小中文模型，测纪要结构正确率与幻觉，产出推荐配置表）。
4. 声纹注册表兼容抽查（AC-6：`cam++-v1-cloud` ↔ 本地 `cam++-v1` 零迁移互用，误识率相对差异 ≤5%）。
5. 产物落 `tests/eval_local_engine/`，报告命名 `EVAL-AC2-LOCAL-ENGINE.md`。

**引擎与环境**

- 本地：FunASR 全管线 = `seaco-paraformer-zh` + `fsmn-vad` + `ct-punc` + `cam++`（ModelScope 完整 ID），spike venv（Python 3.11.15 / funasr 1.4.16 / torch 2.14.0），`MODELSCOPE_CACHE=.spike_local_engine/ms_cache` 复用 Spike 已下载权重（零重复下载）。`generate(batch_size_s=300, merge_vad=True, merge_length_s=15)`。
- 云端：唯一可用通道 = `core.cloud_client.cloud_transcribe → CLOUD_API_URL`（订阅中转，`diarization_enabled=true`）。注：`DASHSCOPE_API_KEY` 与 `ASR_PROXY_URL` 在 `.env` 中均被注释，故未走 DashScope 直连/代理路径。
- LLM：本机 Ollama OpenAI 兼容端点 `http://localhost:11434/v1/chat/completions`；生产提示词 = `core/summarize.SYSTEM_PROMPT`；qwen3 系列传 `"think": false`；幻觉裁判模型 = qwen3:14b（temperature=0）。
- 声纹云：`voiceprint-service`（Bearer 认证，`POST /voiceprint/embedding`，`model:"campplus-v1"`）；本地：funasr `iic/speech_campplus_sv_zh-cn_16k-common` 的 `spk_embedding`。

**指标定义**

- **CER**：字符级 Levenshtein，含 S/D/I 分解。归一化：NFKC → 小写 → 去标点/空白 → 中文数字转阿拉伯数字。（中文以 CER 作 WER 的等价代理，符合 AC-2「字错误率」口径。）
- **三层参照体系**（AC-2 关键设计，见 §3）：云端伪参照 → 自动共识参照 → 人工校对参照。
- **近似 DER**：10ms 帧粒度，穷举标签映射（≤8 人），双参照（fresh 云端片段 diarization / hist 历史全量转写人工绑定姓名时间线）。非人工标注真值，故为「可解释近似指标」。
- **幻觉双探针**：`wordface`（纪要 token 是否出现在转写/提示词中的表层差集，粗粒度）+ `judge`（qwen3:14b 裁判判定「转写中无依据的主张」条数，权威信号）。

---

## 2. 样本与偏差声明

| 段 | 来源 | 窗口 | 期望说话人 | 各说话人云端时长(s) |
|---|---|---|---|---|
| SEG-2P | `samples/sample_meeting_2p4p.mp3`（脱敏化名，任务 95f2e70a） | @1260s, 360s | 2 | S5 217 / 说话人5 140 |
| SEG-4P | 同上 | @2880s, 360s | 4 | S5 194 / 说话人2 39 / S7 22 / 说话人5 20 |
| SEG-6P | **补充样本** `data/uploads/e6cda37b_sample_meeting_6p.mp3`（脱敏化名，任务 e6cda37b，真实 6 人会议） | @620s, 480s | 6 | S1 156 / S2 86 / S3 85 / S4 37 / S5 13 / S6 4 |

> 脱敏说明：S1~S7 为参会人代号（替换真实姓名）；样本文件名为化名。原始语料、转写结果与人工校对稿属私有归档，未随仓库分发。

**偏差披露（必须随结论一并阅读）**

1. **6 人样本非取自 samples/**：`samples/` 库存仅 1 个 5 人会议文件，无法独立覆盖 6 人场景。SEG-6P 取自 `data/uploads/` 真实 6 人会议，与 2P/4P 非同源会议、录音条件不同，横向可比性受限。
2. **SEG-6P 含边缘说话人**：S5(13s)/S6(4s) 在该窗口发言极少，分离难度天然偏高，会放大 6P 的 DER 与计数误差。
3. **SEG-4P 说话人时长高度不均**：3 人发言 <40s，短发言人是计数偏差主要来源。
4. **云端配额报备（派工要求执行前估算并报备）**：本批云端转写量 = 360+360+480 = **1200s（20 分钟）音频**，已在执行前报备并获项目方授权消耗配额；执行前云端账号剩余约 2386.4 分钟。声纹云嵌入提取另消耗少量 embedding 调用（非转写配额）。
5. **人工校对参照未完成**：QA 无法替代人工听校逐句校对，正式 AC-2 相对差距判定因此**挂起**（见 §3.4），已交付工作表使人工校准可一键回填。

---

## 3. AC-2 转写质量

### 3.1 量化结果（CER，中文 WER 代理）

| 段 | CER(local｜cloud 伪参照) | S / D / I | ref_chars | CER(cloud｜consensus) | 共识不确定句 |
|---|---|---|---|---|---|
| SEG-2P | **7.31%** | 79 / 21 / 36 | 1860 | 0.0% | 53 |
| SEG-4P | **19.19%** | 153 / 21 / 69 | 1266 | 0.78% | 59 |
| SEG-6P | **24.70%** | 171 / 18 / 187 | 1522 | 1.36% | 78 |

热词映射（转写后替换）对 CER 影响可忽略（2P 7.31%→7.31%、6P 24.70%→24.77%），说明本批样本的误差主体不是专有名词替换可覆盖的部分，而是重叠语音区的插入/替换。

### 3.2 误差结构解读

- **插入(I)随人数上升主导恶化**：2P I=36 → 4P I=69 → 6P I=187。与 DER 的 false_alarm/confusion 同步上升，指向**重叠语音/串音区本地管线产生额外字符**，而非单纯声学识别弱。
- **2P 干净段表现良好**：单人主讲、几乎无重叠的 2P 段 CER 仅 7.31%，与 Spike §2.3「可读性与云端同档观感」一致，说明本地声学模型基础质量达标；恶化集中在多人重叠场景。

### 3.3 三层参照体系（为何不能直接用云端当真值判 AC-2）

AC-2 要求的是「本地 WER 与云端 WER **各自对人工真值**的相对差距 ≤15%」。直接用云端转写当真值会把**云端自身错误**算到本地头上，产生系统性偏置。故设计三层：

1. **云端伪参照**：CER(local｜cloud)。cloud 非真值，仅作上界代理。
2. **自动共识参照**：以 cloud 为基底、用热词映射裁决 local/cloud 分歧生成 consensus。实测 CER(cloud｜consensus)=0/0.78%/1.36%——**共识高度贴近云端**，故共识参照仍偏向云端，只能作过渡，不能作为 AC-2 终判。
3. **人工校对参照（AC-2 正式判定路径）**：`refs/SEG-*_proofread_worksheet.md` 已标出全部「不确定句」（53/59/78 句），人工听校后写入 `refs/SEG-*_human_ref.txt`，`compute_metrics.py` 检测到该文件即自动输出 `ac2_relative_gap_vs_humanref` 与 `ac2_pass_threshold_15pct` 布尔判定。

### 3.4 AC-2 正式判定：挂起（待人工校准）

**判定材料齐备，正式结论待人工校对参照回填。** 当前可下的**倾向性**结论（非终判）：

- 在干净单人段（2P），本地与云端差距小（CER 7.31%），AC-2 大概率可通过。
- 在多人重叠段（4P/6P），伪参照 CER 升至 19–25%，**若该差距主要由本地引入**，则 AC-2 的「相对差距 ≤15%」在重叠场景存在不通过风险；但伪参照/共识参照均偏向云端，无法排除其中相当比例来自云端自身在重叠区的错误。**须以人工真值裁定，QA 不做无真值的通过/不通过断言。**

> 交付物：人工校对工作表（`refs/SEG-*_proofread_worksheet.md`）+ 自动判定脚本（`compute_metrics.py` 的 human_ref 分支）。人工回填后无需改脚本即得正式 AC-2 判定。

---

## 4. AC-2 附带：多说话人分离（近似 DER）

| 段 | 期望说话人 | 本地检出 | 云端检出 | DER(vs fresh 云片段) | DER(vs hist 姓名时间线) | miss/fa/conf(s, fresh) | 帧一致率(fresh) |
|---|---|---|---|---|---|---|---|
| SEG-2P | 2 | **2** | 2 | **8.6%** | 15.9% | 23.4 / 2.1 / 5.2 | 92.0% |
| SEG-4P | 4 | **3** | 7 | **46.9%** | 44.0% | 32.7 / 11.3 / 82.1 | 57.3% |
| SEG-6P | 6 | **4** | 3 | **55.8%** | 59.6% | 51.9 / 47.0 / 114.7 | 56.5% |

**解读**

- **2P 分离可用**：计数正确、DER 8.6%、帧一致率 92%。
- **4P/6P 计数与 DER 均不达标**：4P 本地少检 1 人（3/4），6P 少检 2 人（4/6）；confusion 时长（82s/115s）是 DER 主体，说明**重叠语音被错误归并到主说话人**。云端在 4P 反而过检（7 vs 期望 4），两端在多人重叠区都不稳，但本地倾向「欠分离」。
- **方法学诚实声明**：DER 为**近似值**（伪参照 + 穷举标签映射），非人工标注真值；fresh 与 hist 双参照差 7–8 个百分点，反映参照自身不确定性。该结果足以判定「多人重叠分离是本地引擎的明确短板」，但不足以给出精确 DER 数值承诺。与 BACKLOG「说话人分离优化」条目一致，手动修正入口是必要体验补偿。

---

## 5. WP-C-3：LLM 最低规格实验

5 档 × 2 段（SEG-2P/SEG-6P），裁判模型 qwen3:14b。原始数据 `results/llm_tiers.json`，纪要全文 `results/llm_outputs/*.md`。

| 模型 | 结构完整度 2P/6P | **裁判判定幻觉 2P/6P** | wordface 2P/6P | 时延(s) 2P/6P | 结论 |
|---|---|---|---|---|---|
| qwen2.5:1.5b-instruct | 0.857 / 1.0 | **2 / 3** | 66 / 62 | 6.3 / 4.9 | ✗ 不达档（丢「议题归类」章节 + 幻觉最多） |
| qwen2.5:3b-instruct | 1.0 / 0.857 | **3 / 3** | 39 / 32 | 9.0 / 8.7 | ✗ 不达档（6P 丢章节 + 幻觉 3/3） |
| qwen3:4b | 1.0 / 1.0 | **0 / 1** | 44 / 67 | 38.9 / 54.7 | △ **可用下限**（结构满分、幻觉 ≤1，时延偏慢） |
| **qwen3:8b** | **1.0 / 1.0** | **0 / 0** | 56 / 67 | 42.7 / 47.0 | ✓ **推荐默认**（结构满分、零裁判幻觉、时延可接受） |
| qwen3:14b | 1.0 / 1.0 | 2 / 0 | 80 / 108 | 86.5 / 92.4 | ✓ 质量达标但时延 ~2×，纪要场景无相对 8b 的净收益 |

**推荐配置表（已回填 PRD R4 `model_tier` 与需求记录未决问题 2）**

| 档位 | 触发条件 | 提示词策略 | UI 行为 |
|---|---|---|---|
| 标准档 | 推理型 qwen3 **≥8B** | 标准 | 正常出纪要（推荐默认 = **qwen3:8b**） |
| 保守档 | 推理型 qwen3 **4–7B** | 防幻觉保守模板 | 正常出纪要，标注「小模型档」 |
| 降级警示 | 非推理型 **≤3B**（如 qwen2.5 instruct） | 保守模板 | **警示**：纪要结构/可靠性不足，建议升级模型或联网提质 |

**指标口径说明**：`wordface` 是表层 token 差集，会**误计合法摘要改写**（14b 因输出更丰富反而 wordface 最高 108），故**不作为幻觉判据**；权威信号是 `judge`（qwen3:14b 裁判「转写中无依据的主张」条数）。结论以 judge + 结构完整度为准。

**结论**：Spike §4「qwen3:8b 达可用档」在受控双段实验中**复现并加强**——8b 是唯一两段均零裁判幻觉且结构满分的档位，定为推荐默认；4b 为可用下限；qwen2.5 ≤3B-instruct 不达可用档。

---

## 6. AC-6：声纹注册表云/本地零迁移兼容

抽查 4 名说话人（S5/S3/S1/S7），每人 enroll+test 纯净单人片段（min_clip 20s，guard 2000ms 防串音）。原始数据 `results/vp_compat.json`、根因 `results/vp_root_cause.json`（私有归档，未随仓库分发）。

### 6.1 四组合相似度与判别力

| 组合 | same_mean | same_min | cross_max | FPR@0.50 | **EER** | d′ |
|---|---|---|---|---|---|---|
| cloud × cloud（同端） | 0.901 | 0.831 | 0.846 | 91.7% | **4.2%** | 3.02 |
| local × local（同端） | 0.910 | 0.866 | 0.770 | 66.7% | **0.0%** | 3.95 |
| cloud(ref) × local(test)（跨端） | 0.625 | 0.495 | 0.617 | 41.7% | **29.2%** | 1.77 |
| local(ref) × cloud(test)（跨端） | 0.616 | 0.523 | 0.577 | 41.7% | **29.2%** | 1.80 |

**同端判别力优秀（EER 0–4.2%），跨端判别力崩塌（EER 29.2%，d′ 从 3+ 掉到 1.8）。** 跨端 same_min 低至 0.495（< 阈值 0.50），意味着同一人云/本地嵌入可能判为不同人。

### 6.2 零迁移模拟（项目匹配器：MATCH_THRESHOLD=0.50, MIN_MATCH_MARGIN=0.05）

`local cam++-v1` 查询 `cloud cam++-v1-cloud` 注册表：

| 查询人 | top-1 命中 | 命中正确 | best_sim | margin | **accepted** |
|---|---|---|---|---|---|
| S5 | S5 | ✓ | 0.709 | 0.159 | ✓ |
| S3 | S3 | ✓ | 0.638 | 0.043 | ✗（margin<0.05） |
| S1 | S1 | ✓ | 0.495 | 0.128 | ✗（sim<0.50） |
| S7 | S7 | ✓ | 0.658 | — | ✗ |

**top-1 排序全对（4/4），但仅 1/4 通过接受门槛。** AC-6「误识率相对差异 ≤5%」**不成立**：跨端 EER 相对同端 cloud 基线差异约 +600%（29.2% vs 4.2%）。

### 6.3 根因定位（已证明，非猜测）

`results/vp_root_cause.json`：用同一份权重 `campplus_cn_common.bin` 分别复刻两种特征管线——

- 裸 fbank(80bin, 25/10ms) **无 CMN** 复刻 vs 云端服务嵌入：**cos = 1.0000**（8/8 片段）
- fbank **+ CMN**（`fbank - fbank.mean(dim=0)`）复刻 vs funasr 本地嵌入：**cos = 1.0000**（8/8 片段）
- 无 CMN 复刻 vs 有 CMN 复刻：**cos = 0.6834（均值）** == 云 vs 本地实测跨端 cos（0.6834）

**结论：跨端相似度崩塌的唯一原因是 CMN（倒谱均值归一化）差异——voiceprint-service 用裸 fbank 无 CMN，funasr AutoModel 用 fbank+CMN，权重完全相同。** 这是确定性管线差异，不是声学/串音噪声。

### 6.4 AC-6 判定与开发移交单

- **判定**：AC-6 ≤5% **不达标**（当前实现）。**QA 不修补产品代码**，移交开发。
- **移交单**：
  - **现象**：云注册声纹在本地模式无法零迁移复用，跨端同人 cos 仅 ~0.62，EER 29.2%，零迁移接受率 1/4。
  - **根因**：本地 `LocalCamPlusProvider`（funasr AutoModel）默认 fbank+CMN，与云端 voiceprint-service 裸 fbank 无 CMN 不一致（cos=1.0 双向复刻证明）。
  - **建议修复方向（供开发，非 QA 实施）**：本地声纹特征管线**复刻云端**——裸 fbank(80bin,25/10ms) 无 CMN，加载同一 `campplus_cn_common.bin`。修复后应重跑 `vp_compat.py` 验证跨端 EER 回落到同端水平、AC-6 相对差异 ≤5%。
  - **复现入口**：`venv/bin/python tests/eval_local_engine/vp_root_cause.py`、`vp_compat.py`。
- **附带发现（独立于 AC-6，移交评估）**：阈值 `MATCH_THRESHOLD=0.50` 在远场会议素材上偏低——即便**纯云端**同端 FPR@0.50 也高达 91.7%（EER 最优阈值约 0.785）。建议按素材域重标定阈值，否则会议场景误识率偏高。此为既有产品参数问题，非本地引擎引入。

---

## 7. 残余风险与未覆盖面

1. **AC-2 正式判定挂起**：依赖人工校对参照回填，当前仅倾向性结论。重叠段（4P/6P）存在不通过风险，须人工真值裁定。
2. **DER 为近似值**：伪参照 + 穷举映射，非人工标注真值；双参照差 7–8pp。可判方向（多人分离是短板），不可作精确数值承诺。
3. **样本偏差**：6P 非同源会议、含边缘说话人；4P 发言时长极不均。横向可比性受限（§2）。
4. **峰值内存未在 WP-C 独立复测**：沿用 Spike §2.2 RSS 3.3GB 结论；本任务只复测了 RTF（0.069–0.076）。
5. **LLM 实验仅 2 段中文样本、单一裁判模型**：裁判 qwen3:14b 自身可能有偏；幻觉判定为相对信号而非绝对真值。wordface 指标已知偏置（§5）。
6. **多说话人分离精度未获纯净多人样本充分验证**：与 Spike 遗留第 3 项一致，4P/6P 结果已部分补齐但参照非真值。
7. **AC-6 修复未验证**：根因已证，但修复后效果须开发实施后由 QA 重跑确认，本任务不声明「已修复」。

---

## 8. 复跑指南与产物索引

**复跑顺序**（详见 `tests/eval_local_engine/README.md`）：

```
# 1. 切片 + 纯净单人片段 + 云端参照时间线
venv/bin/python tests/eval_local_engine/prepare_segments.py
# 2. 本地 FunASR 转写（spike venv）
.spike_local_engine/.venv/bin/python tests/eval_local_engine/run_local_asr.py
# 3. 云端参照转写（项目 venv，消耗配额）
venv/bin/python tests/eval_local_engine/run_cloud_asr.py
# 4. CER/DER/共识/工作表
venv/bin/python tests/eval_local_engine/compute_metrics.py
# 5. LLM 档位实验（可加模型名过滤增量补跑）
venv/bin/python tests/eval_local_engine/run_llm_tiers.py [model...]
# 6. 声纹兼容 + 根因
venv/bin/python tests/eval_local_engine/vp_extract_local.py
venv/bin/python tests/eval_local_engine/vp_compat.py
venv/bin/python tests/eval_local_engine/vp_root_cause.py
```

**入库产物**（`tests/eval_local_engine/`）：评测脚本 + `README.md` + 本报告。原始语料、转写结果、人工校对稿（`refs/`、`results/`、`eval_manifest.json`）含真实会议内容，属私有归档，**不入库、不随仓库分发**；仓库内仅保留方法论与指标结论。

**大文件隔离**：音频切片、模型缓存、中间结果存于工作区内 `.eval_local_engine/`（已加入 `.gitignore`，不入库），与 Spike 的 `.spike_local_engine/` 同级。

---

## 9. 交付契约自检（Delivery Contract）

| # | 项 | 状态 |
|---|---|---|
| 1 | 请求范围（AC-2 CER + 分离 DER + LLM + AC-6）均有可执行证据 | ✓ |
| 2 | 发现可复现、按严重度标注 | ✓（复跑命令 + JSON 证据） |
| 3 | 跳过面/阻塞披露残余风险 | ✓（§7，AC-2 正式判定挂起） |
| 4 | QA 产物不含产品 bug 修复 | ✓（AC-6 仅移交单，未改产品代码） |
| 5 | 协作结论（PRD/需求记录回填）已报告 | ✓（PRD R4 + 未决问题、需求记录未决 2） |
| 6 | 无代码提交动作（commit/push/PR 由 git 纪律约束，仅 QA 产物逐文件 add） | ✓ |
| 7 | 材料→用例可追溯 | ✓（样本清单 + 三层参照 + 工作表） |
| 8–11 | 产物保存于受测仓库内 QA 专用目录、绝对路径、隔离大文件 | ✓ |
