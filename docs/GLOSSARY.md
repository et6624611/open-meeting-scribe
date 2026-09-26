---
title: 术语表
description: Open Meeting Scribe 统一术语定义，避免文档/代码/AI 对话各说各话
tags: ["glossary", "terminology"]
author: Yongliang Wang
created_at: 2026-09-03
updated_at: 2026-09-26
version: "1.4.0"
status: published
---

# GLOSSARY — 术语表

> 统一口径，避免文档/代码/AI 对话各说各话。

| 术语 | 含义 |
|------|------|
| ASR | 自动语音识别，声音 → 文字 |
| ASR 代理 | ASR Proxy 服务（`asr-proxy/`），通过 HMAC-SHA256 签名中继转写请求，保护 API Key 不落地 |
| 说话人分离 / diarization | 区分「哪句是谁说的」，输出匿名 `speaker_id`（0/1/2…） |
| 声纹 / voiceprint | 从声音提取的身份向量（CAM++ 192维嵌入），用于把 `speaker_id` 映射成真实姓名（v4 ✅） |
| 热词 / hotword | 企业人名、术语等专有名词，转写时加权纠偏（`vocabulary_id`） |
| 逐字稿 / 口水稿 | ASR 原始输出，含语气词、重复、口语化 |
| 纪要 | LLM 加工后的结构化产物：结论 + 决策 + 议题 |
| 决策 / decision | 会议中明确下来的定论，独立结构化对象（`task["decisions"]`：text/status/pending_confirmation/source=auto|backfill|manual|injection，支持 supersede/revoked），跨会议全量在「决策中心」查看（REQ-DECISION-CENTER ✅ 2026-09）。注意：本词旧义曾指「行动项」，2026-09-25 术语拆分后严格区分 |
| 行动项 / action item | 「谁 / 做什么 / 截止」的任务项（`task["todos"]`，原称「待办」），由行动项面板（原「决策流面板」，组件名 `DecisionFlowPanel`）展示；纪要页 Tab 已由「决策」更名「行动项」 |
| 决策中心 / Decision Center | 跨会议全量决策页（`/decisions`）：日期/知识库/状态/关键词筛选、补录、取代（supersede）、撤销，数据源 `GET /api/decisions`（契约 API_CONTRACTS §12） |
| Agent 角色 | 基于 `.md` 文件定义的 AI 行为配置，支持预定义角色 + 用户 fork 自定义（v9 ✅） |
| Agent 工作区 | `data/agent/_roles/` 目录结构，存放角色定义文件（AGENT.md + 附带 .md） |
| DashScope | 阿里云百炼模型服务平台，本项目 ASR 与纪要的统一入口 |
| paraformer-v2 | DashScope 录音文件识别模型，支持分离与热词 |
| 通义千问 / qwen | DashScope 的 LLM，本项目用于纪要生成 |
| 临时 URL / `oss://` | DashScope 免费临时存储换取的音频地址，≤1GB / 48h |
| BlackHole | macOS 虚拟音频设备，用于内录系统声音 |
| 内录 | 采集系统播放的声音（线上会议），区别于麦克风采集 |
| MPS | Apple Silicon 的 PyTorch 加速后端（v2 本地方案才涉及） |

## 接入方式五词表（REQ-SETTINGS-IA 裁决-4，2026-09-26 定稿）

用户可见词仅五词，卡片命名须写不会被下层配置证伪的判据：

| 用户词 | 含义 | 工程值（仅专家注释层） |
|--------|------|------|
| 离线（模式） | 算力全在本机，结构性零出网（声纹仅本机 CAM++） | `access_mode=local` · `engine.mode=local` |
| 联网（模式） | 至少一项能力使用云端算力，计费来源逐能力在详情选择 | `access_mode=cloud` |
| 体验配额 | 平台代付（消耗体验分钟数），随账户登录可用 | `trial` / `proxy` · `cloud` |
| 自带 Key | 用户自有 API Key，由用户供应商计费 | `byok` / `direct` |
| 本机端点 | 仅 LLM 详情层：本机 Ollama/LM Studio 端点，零出网 | `local_endpoint` |

历史映射注记（全量清退，仅供存量配置/文档对照）：「**托管**」→ 现拆为联网模式 + 体验配额来源（旧 `access_mode=hosted`）；「体验代理」→ 体验配额；「自持 Key」→ 自带 Key；「自接端点」→ 本机端点；「平台代理」→ 已禁用（改用「平台共享通道」描述链路事实）。旧 `access_mode=byok` 迁移为联网 + 逐能力自带 Key。
