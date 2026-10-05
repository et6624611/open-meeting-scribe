# EVAL-AC2-PREVIEW-2P — AC-2 预览计算报告（SEG-2P 人工参照）

> **性质标注：预览（preview），不构成 AC-2 正式判级。**
> 正式判定须待 SEG-4P / SEG-6P 人工参照回填后，三档合并产出。
> 任务来源：产品经理 2026-09-24 下发追加任务，项目方已裁决参照定稿。
> 报告人：QA工程师（waker 365d21fa11a0）· 生成时间 2026-09-24 17:07 (+08:00)
>
> 数据归档说明：本报告引用的 `refs/`、`results/` 原始语料与逐句文本含真实会议内容，属私有归档，未随仓库分发；下文路径仅作方法论追溯。

---

## 1. 输入与证据链

| 项 | 值 |
|---|---|
| 人工参照（终审定稿） | `tests/eval_local_engine/refs/SEG-2P_human_ref.txt` |
| 参照 SHA-256 | `f283fbcdd3ea8440bf3829753bc155472f160e11d2ecb11b1e129b1e914a35af` |
| 参照规模 | 57 个非空行（每句一行）；归一化后 1877 字符 |
| 过程追溯件 | 同目录 `SEG-2P_human_ref_draft.txt`、`SEG-2P_3col_workbench.md`、`SEG-2P_listen_list.md`（本报告未使用，仅登记） |
| 本地引擎输出 | `.eval_local_engine/results/local_SEG-2P.json`（FunASR，归一化后 1875 字符） |
| 云端引擎输出 | `.eval_local_engine/results/cloud_SEG-2P.json`（paraformer-v2，归一化后 1860 字符） |
| QA-R1 基线 | `.eval_local_engine/results/metrics.json`（2026-09-24 15:02，只读引用，未改动） |
| 计算脚本（QA 件） | `tests/eval_local_engine/ac2_preview_2p.py` |
| 结果产物（新文件） | `.eval_local_engine/results/metrics_ac2_preview_seg2p.json` |

## 2. 方法学

1. **口径来源**：完全复用 `compute_metrics.py` 的 human-ref 分支（L339–347）判定逻辑与 `cer()` / `normalize()` 函数，通过独立 QA 驱动脚本 `ac2_preview_2p.py` **只读 import**，未修改任何产品/评测代码。
2. **归一化规则**（即 `normalize()` 内置规则，本次**未附加任何额外预处理**）：
   - NFKC 全角转半角；统一小写；
   - 去除所有标点与符号（Unicode P/S 类）及空白（含换行，故"每句一行"不影响拼接比较）；
   - 中文数字串转阿拉伯数字；
   - **语气词（呃/啊/嗯）不剔除，保留参与计分**——与项目方"全文统一保留语气词"的裁决一致。
3. **参照中的「—」占位行**（第 11、19 行）：属标点符号类，归一化后自动为空，不贡献参照字符，无需预处理，特此登记。
4. **第三方参考票背景**（项目方裁决口径，QA 不重复裁决）：本项目人工参照以 whisper.cpp large-v3-turbo 离线转写为第三方参考票、项目方逐行终审产出；争议句 176.8s / 233.3s 已由听校人裁决维持原样。
5. **相对差距公式**（与分支代码一致）：`ac2_relative_gap = (CER_local − CER_cloud) / CER_cloud`，达成线 `≤ 15%`。
6. **CER = 编辑距离(替换+插入+删除) / 参照归一化字符数**，字符级 Levenshtein。

## 3. 结果（SEG-2P 单档，预览）

| 指标 | 值 | 明细 |
|---|---|---|
| cer_local_vs_humanref | **13.00%** | 244 edits / 1877 字（sub 154 / ins 44 / del 46） |
| cer_cloud_vs_humanref | **10.87%** | 204 edits / 1877 字（sub 125 / ins 31 / del 48） |
| ac2_relative_gap_vs_humanref | **+19.60%** | (0.1300 − 0.1087) / 0.1087 |
| ≤15% 达成情况（预览口径） | **未达成** | 超阈值 4.60 个百分点（相对差距口径） |

> 再次强调：以上为**单档预览**。AC-2 正式判级以三档（2P/4P/6P）合并为准，本报告不作为通过/否决依据。

## 4. 与 QA-R1 伪参照值（7.31%）的偏差说明

QA-R1 记录 `cer_local_vs_cloudref = 7.31%`（以云端全新转写为伪参照）。本次对人工终审参照测得 13.00%，**偏差 +5.69 个百分点**。归因分析：

1. **伪参照本身有偏**：云端转写相对人工终审参照自身即有 10.87% 的错误。local-vs-cloud 的 7.31% 度量的是"本地与云端的分歧"，而非"本地与真值的差距"，天然低估真实错误率。
2. **共性错误抵消失效**：本地与云端在两版都错（且错过同一处）的位置上，伪参照口径互相抵消、不计入；换成人对照后这些位置全部按各自与真值的差重新开账（local 244 edits vs cloud 204 edits）。
3. **语气词保留不是偏差主因**（QA 实测反驳直觉归因）：归一化后 呃/啊/嗯 计数 参照 60 (15/34/11)、本地 65 (21/32/12)、云端 59 (17/32/10)，三方量级接近，对 5.69pp 偏差贡献有限。
4. **终审裁决已生效**：争议句（176.8s/233.3s）维持原样、whisper 参考票结论已并入定稿，本计算基于定稿全文，不存在"参照未终审导致的额外噪声"。
5. **方向一致性**：无论伪参照还是人参照，均为 local > cloud，QA-R1 的排序性结论未被推翻；被推翻的是**绝对水位**——QA-R1 用 7.31% 估计的本地绝对错误率明显偏乐观。

## 5. 边界纪律遵守声明

- 预览性质已在标题、结果节双重标注，不构成 AC-2 正式判级。
- 未修改任何产品代码及 `compute_metrics.py`；`ac2_preview_2p.py` 为 QA 追加件。
- 未覆盖既有证据：`metrics.json` 与 `.eval_local_engine/qa_r1/` 均保持只读，结果写入新文件 `metrics_ac2_preview_seg2p.json`。
- 未执行任何 git 操作（add/commit/push 均无）；文件入库由产品安排。

## 6. 正式合并前须知（风险提示，非本次任务范围）

1. `compute_metrics.py` 的 human-ref 分支读取路径为 `.eval_local_engine/refs/<SEG>_human_ref.txt`，而定稿现存放于 `tests/eval_local_engine/refs/`。正式三档合并重跑前，须将定稿参照**复制**至前者（该目录为脚本工作镜像，含 consensus/worksheet 同源文件）。
2. 直接运行 `compute_metrics.py SEG-2P`（带参数）会以单档结果**覆盖** `metrics.json`，丢失 4P/6P 既有指标——正式合并务必不带参数全量重跑，或先备份。
3. SEG-4P / SEG-6P 目前仅有 `human_ref_draft.txt`（草稿），终审回填是正式判级的入口条件。

## 7. 证据索引

| 证据 | 路径 |
|---|---|
| 预览指标 JSON（含 meta/哈希/归一化规则全文） | `.eval_local_engine/results/metrics_ac2_preview_seg2p.json` |
| 预览驱动脚本 | `tests/eval_local_engine/ac2_preview_2p.py` |
| 复跑命令 | `venv/bin/python tests/eval_local_engine/ac2_preview_2p.py` |
| 本报告 | `tests/eval_local_engine/EVAL-AC2-PREVIEW-2P.md` |
