---
title: R8 Spike 报告 — 本地引擎构建可行性与模型选型实测
description: 在 Apple Silicon 真机上实测 FunASR 离线管线（体积/内存/RTF/质量）与 PyInstaller 冻结 torch/funasr 可行性，为 D-R1（模型组合）与 D-R3（分发形态）提供裁决证据
tags: ["spike", "offline", "funasr", "pyinstaller", "ollama", "decision-evidence"]
author: 工程实施（QoderIDE）
created_at: "2026-09-23"
updated_at: "2026-09-23"
version: "1.0.0"
status: published
category: technical
related_docs: ["docs/PRD-LOCAL-ENGINE.md", "docs/REQUIREMENT_LOCAL_ENGINE.md", "docs/adr/0018-本地可选计算引擎与声纹离线化.md"]
---

# R8 Spike 报告：D-R1 / D-R3 裁决证据

## 0. 结论速览

| 决策点 | 建议 | 置信度 |
|---|---|---|
| **D-R1** FunASR 模型组合 | 全家桶四模型（seaco-paraformer-zh + fsmn-vad + ct-punc + cam++），总下载 **≈2.0GB ≤ 3GB 预算**；标点模型为可裁剪项（省 1.0GB） | 高（macOS 实测） |
| **D-R3** 本地组件分发形态 | **应用内引导下载 → 外置引擎目录（onedir 冻结包 + 模型权重分目录）**；Windows 侧用 Inno Setup 组件形态承载同一目录结构；**否决**打包进云精简主包 | 中高（macOS 冻结 PASS，Windows 未实测） |

两项均**未触发 PRD §12 预留的失败出口**（PyInstaller 可行性已验证；"外置引擎目录"本身就是 D-R3 推荐落点而非退路）。

## 1. 实验环境

- 机型：MacBook Pro M3 Pro / 18GB RAM / Apple Silicon，CPU 推理基线（未用 MPS）
- 隔离环境：Python 3.11.15（uv 创建，与项目 3.14 venv 完全隔离）；torch 2.14.0 / funasr 1.4.16 / modelscope 1.40.1 / PyInstaller 最新版
- 测试素材：`samples/智达方通全面预算系统方案交流.mp3`（118 分钟真实多人会议）截取 10 分钟段 + 3 秒冻结测试段
- 产物目录：`.spike_local_engine/`（已加入 .gitignore，含日志/结果 JSON/冻结 dist，不入库）

## 2. D-R1 实测：模型组合与资源预算

### 2.1 模型清单与体积（ModelScope 实际下载量）

| 模型 | ModelScope ID | 体积 | 用途 |
|---|---|---|---|
| seaco-paraformer-zh | `iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch` | 944MB | 转写主模型 |
| ct-punc | `iic/punc_ct-transformer_cn-en-common-vocab471067-large` | **1.0GB** | 标点恢复 |
| fsmn-vad | `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | 3.9MB | 语音活动检测 |
| cam++ | `iic/speech_campplus_sv_zh-cn_16k-common` | 28MB | 说话人分离 + **声纹（R3 复用同一份权重）** |
| **合计** | | **≈2.0GB** | AC-3 预算 ≤3GB ✅ |

关键发现：**标点模型比转写主模型还大**（1.0GB，占总量 50%），是唯一可裁剪大件——去掉后总下载降至 ≈1.0GB，代价是转写文本无标点。建议 D-R1 采用「默认全家桶 + 标点可选项」，而非全局降级到无标点档。

### 2.2 性能与资源（10 分钟真实会议音频，CPU，全管线含说话人分离）

| 指标 | 实测 | AC-3 门槛 | 判定 |
|---|---|---|---|
| 推理墙钟 | 48.8s（RTF ≈ **0.081**） | — | 30 分钟会议 ≈ 2.5 分钟，分段批处理体验可行 |
| 峰值内存 | RSS 3.3GB / footprint 5.2GB | 16GB 机型 ≤8GB | ✅（长度增长主要累加 VAD 段列表，非线性） |
| 首次加载（含 2GB 下载） | 1477s | — | 下载完成后进程内加载为数十秒级 |
| 冻结包峰值内存（无 spk） | RSS 1.7GB | — | ✅ |

### 2.3 转写质量抽查（定性）

- 250 句全部带时间戳 + speaker 字段，输出契约可直接对齐 `docs/API_CONTRACTS.md`；该段为单人主讲（分离结果 spk=0 符合事实），**多说话人分离准确性未获样本验证**。
- 可读性与云端 paraformer-v2 同档观感；专有名词错误突出：「智达方通」→「其他方通/吉达方通」、「交付」→「提付」——**实证 R2 热词映射（转写后替换）是必配项而非可选项**。
- **未做**正式 WER 对比（需 ≥3 段 2/4/6 人样本 + 云参照），按分工留给 AC-2 评测脚本（实施角色任务）。

## 3. D-R3 实测：PyInstaller 冻结可行性

### 3.1 结果：PASS

- 命令：`--onedir --collect-all funasr --collect-all modelscope --collect-all torch`，构建约 25 分钟，产物 **975MB**（纯代码层，不含任何模型权重）。
- 冻结可执行文件完整跑通：torch import 1–9s → funasr import 7–86s → paraformer+vad+punc 加载 → 3 秒音频真实推理出文本（「给定了一定的资源支持，包括领导上对。」），退出码 0。
- **模型权重保持外置**（运行时经 MODELSCOPE_CACHE 定位 `data/models/`）——与 R5「引导下载不内置分发」决策天然一致。

### 3.2 已知代价与风险

| 项 | 实测/风险 | 缓解 |
|---|---|---|
| 首启 import 慢 | 冻结态 funasr import 首次 86s（Windows 杀软场景更差） | 常驻引擎子进程（启动一次复用），勿每任务冷启 |
| 子进程重复引导 | 日志见 torch/funasr import 重复 5–6 次（multiprocessing 重执行冻结包） | 实施时以 `if __name__=="__main__"` + 显式 `freeze_support` 架构约束 |
| Windows 未验证 | 本机无 Windows 环境；torch 冻结有 ADR-0009 时代先例，funasr 新增面未测 | 实施首个 CI 任务跑 Windows 冻结冒烟（替身权重，禁真模型下载，对齐 R8） |
| onefile 未测 | 有意放弃：2GB 级解压体验差且无收益 | 直接 onedir，不投入 |

### 3.3 分发形态推演（证据 → 建议）

- 组件总量 ≈ **975MB 冻结包 + 2.0GB 权重 ≈ 3GB**；打进云精简包（现状 ~200MB）直接违反 AC-7「云包零增长」——**排除内置**。
- 引擎包与权重均为「目录形态、可独立更新」→ 推荐**应用内引导下载**为主路径（两者复用 R5 下载器的进度/校验/断点续传能力）。
- Windows 安装器（Inno Setup，沿用既有升级方案决策）以**组件选项**承载同一目录布局，作为政企离线/内网拷贝路径（对齐 R5 离线模型包需求）。
- 云模式用户零感知：不下载则目录不存在；R6 徽章按「目录存在性 + settings.engine.mode」双因子判定。

## 4. 附带验证：Ollama 自接前提（R4 / 需求记录未决问题 2）

本机 Ollama（qwen3:8b / qwen3:14b 在线）以 Spike 本地转写文本实测：OpenAI 兼容 `/v1/chat/completions` 调用成功，2500 字转写 → 31 秒产出结构正确（主题/要点/行动项）、未见幻觉的纪要。**qwen3:8b 即达「可用」档**，支持 R4 `model_tier` auto 策略（≤14B 保守档）设计；正式最低推荐规格实验仍随 AC-2 评测脚本执行。

## 5. 遗留与移交清单

1. AC-2 正式 WER 评测脚本（含云端 paraformer-v2 参照）——随 R4/R5/R6 拆解给实施角色。
2. Windows PyInstaller + funasr 冻结 CI 冒烟（替身权重）。
3. 多说话人分离准确性样本测试（现样本以单人主讲段为主）。
4. D-R1/D-R3 采纳后：PRD §12 Open Questions 状态更新、R2/R8 条目按本报告口径细化（产品经理执行）。
