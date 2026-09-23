# WP-C — AC-2 本地引擎评测基准（PRD-LOCAL-ENGINE）

对应 PRD §13 任务包 WP-C 与验收标准 AC-2/AC-6，覆盖 Spike 遗留清单第 1/3 项。
报告：[EVAL-AC2-LOCAL-ENGINE.md](EVAL-AC2-LOCAL-ENGINE.md)

## 目录结构

| 文件 | 用途 | 运行环境 |
|---|---|---|
| `eval_manifest.json` | 样本清单（片段窗口、预期说话人、声纹片段配置） | — |
| `prepare_segments.py` | 切分评测片段 + 云端参照时间线导出 + 声纹纯净片段 | 系统 python3 + ffmpeg |
| `run_local_asr.py` | 本地 FunASR 全管线转写（seaco-paraformer + fsmn-vad + ct-punc + cam++） | `.spike_local_engine/venv` |
| `run_cloud_asr.py` | 云端 paraformer-v2 参照转写（项目订阅通道，消耗配额） | `venv`（项目） |
| `compute_metrics.py` | CER（S/D/I 分解）、共识参照、近似 DER、人工校对工作表 | `venv`（项目） |
| `run_llm_tiers.py` | LLM 最低规格实验（Ollama 多档模型 × 结构正确率/幻觉/延迟） | `venv`（项目） |
| `vp_extract_local.py` | 本地 CAM++ 声纹嵌入提取 | `.spike_local_engine/venv` |
| `vp_compat.py` | AC-6 云/本地注册表兼容与误识率对比 + 零迁移模拟 | `venv`（项目） |
| `vp_root_cause.py` | 跨端嵌入差异根因定位（CMN 前处理假设验证） | `.spike_local_engine/venv` |
| `results/` | 评测结果 JSON（入库证据，从 `.eval_local_engine/results/` 归档） | — |
| `refs/` | 共识参照与人工校对工作表（AC-2 正式化路径） | — |

## 复跑顺序

```bash
# 0) 前置：.spike_local_engine/venv（Spike 隔离环境，含 funasr/torch）与 ms_cache 模型权重存在；
#    .env 配置 CLOUD_API_URL/CLOUD_API_TOKEN；Ollama 本机运行且已拉取 MODELS 列表模型
python3 tests/eval_local_engine/prepare_segments.py
.spike_local_engine/venv/bin/python tests/eval_local_engine/run_local_asr.py
venv/bin/python tests/eval_local_engine/run_cloud_asr.py        # 消耗云配额 ≈20 分钟音频
venv/bin/python tests/eval_local_engine/compute_metrics.py
.spike_local_engine/venv/bin/python tests/eval_local_engine/vp_extract_local.py
venv/bin/python tests/eval_local_engine/vp_compat.py
.spike_local_engine/venv/bin/python tests/eval_local_engine/vp_root_cause.py
venv/bin/python tests/eval_local_engine/run_llm_tiers.py        # 全程本机，零云消耗
```

中间产物（切分音频、逐句转写全文、嵌入向量等大文件）统一落 `.eval_local_engine/`（已 gitignore），
入库证据为 `results/` 与 `refs/` 下的小体积 JSON/Markdown。

## AC-2 正式化路径（人工校准）

当前自动指标以云端 paraformer-v2 全新转写为伪参照（cross-CER）。正式 AC-2 判定需人工校对参照：
逐段打开 `refs/SEG-*_proofread_worksheet.md`，对照音频裁决差异句，把最终参照文本存为
`.eval_local_engine/refs/SEG-*_human_ref.txt`，重跑 `compute_metrics.py` 即输出
`ac2_relative_gap_vs_humanref` 与 15% 门槛判定。
