---
title: MVP 建设方案
description: Mac 端 v1 云方案施工蓝图
author: Yongliang Wang
created_at: 2026-09-03
updated_at: 2026-09-17
version: "1.2.0"
status: published
---

# Open Meeting Scribe — Mac 端 MVP 建设方案（云方案 v1）

> 目标：本机（Apple M3 Pro / 18GB / macOS 26.6.2）跑通「音频 → 云端转写+说话人分离 → 结构化纪要」链路，提供本地 Web UI，并支持实时系统内录。
>
> **已定决策（2026-09-03 更新）**：MVP v1 = **纯云方案，不做本地语音解析**。
> - ASR + 说话人分离 = 通义 / 阿里云百炼 **录音文件识别 paraformer-v2**（一个 API 出带 `speaker_id` 的转写）
> - 纪要生成 = **通义千问 LLM API**（与 ASR 共用同一个 `DASHSCOPE_API_KEY`）
> - 音频采集 = 文件输入 + 实时系统内录（BlackHole，用 ffmpeg 采集）
> - 声纹姓名化 = 后续增强（P3）
>
> **与 MISSION 的关系**：MISSION 的「本地数据·云端智能」是长期方向；v1 为快速跑通先走云。原本地链路（FunASR + pyannote + Ollama）作为 v2 备选保留，不在本版实施。
>
> **文档定位**：本文件是 v1 的**施工蓝图**（分阶段步骤/验收/风险）。稳态设计以 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 为准，API 硬约束以 [docs/API_CONTRACTS.md](docs/API_CONTRACTS.md) 为准，决策来由见 [docs/adr/](docs/adr/)。冲突时以 docs 为准。

---

## 一、为什么改云方案（决策记录）

| 触发点 | 事实 |
|--------|------|
| pyannote 是 HF 受限模型 | 需网页手动同意协议；本机 **HF token 不存在** |
| 本机直连 huggingface.co | **超时（被墙）**，本地下载 pyannote 不可行 |
| 本机直连 dashscope.aliyuncs.com | **可达**（0.1s 响应），云链路网络无障碍 |
| 通义录音文件识别 | **一个 API 同时做 ASR + 说话人分离**，返回 `speaker_id` |
| 成本 | 约 **0.288 元/小时**量级，只对语音内容时长计费（以百炼控制台实价为准） |

**净收益**：砍掉 pyannote、FunASR、torch/MPS、Ollama、6–8GB 模型下载、HF 授权、micromamba 强依赖。代价=需联网、异步任务有排队延迟；音频经云端 API 处理属架构特性（用户自行接入服务商，数据隐私由服务商条款约束）。

---

## 二、本机环境体检结论（更新）

| 项 | 现状 | 结论 |
|----|------|------|
| 直连 dashscope.aliyuncs.com | ✅ 可达（401=需鉴权，0.1s） | 云链路网络通 |
| 直连 huggingface.co | ❌ 超时 | 本地 pyannote 方案 v1 放弃 |
| ffmpeg | 8.1 ✓ | 归一化单声道（分离必需）+ 内录采集（avfoundation） |
| Python | 仅 3.14 | 云链路依赖轻（requests/fastapi）；建独立 venv，若 3.14 有轮子问题退 3.11 |
| BlackHole 2ch | 已装 | 仅需「音频 MIDI 设置」路由（复用录屏配置） |
| HF token | 不存在 | v1 不需要 |

---

## 三、总体架构（云）

```
  实时内录(BlackHole, ffmpeg采集) ┐
                                 ├─▶ ffmpeg 归一化(16k/单声道/wav)
  音频文件拖入 ───────────────────┘            │
                                              ▼
                          上传 DashScope 免费临时存储(≤1GB/48h) → oss:// 临时URL
                          （已是公网URL的音频可跳过此步）
                                              │
                                              ▼
        ┌──────────────────────────────────────────────────────────┐
        │ 提交 paraformer-v2 转写任务（RESTful, 异步）                │
        │  diarization_enabled=true, language_hints=[zh,en]          │
        │  vocabulary_id=热词(可选)                                   │
        │  header: X-DashScope-Async + X-DashScope-OssResourceResolve │
        └───────────────┬──────────────────────────────────────────┘
                        ▼ 轮询 task_id → SUCCEEDED → transcription_url → 结果JSON(句子带 speaker_id)
        ┌──────────────────────────────────────────────────────────┐
        │ 组装发言人对话稿（按 speaker_id 归并句子）                  │
        └───────────────┬──────────────────────────────────────────┘
                        ▼
        ┌──────────────────────────────────────────────────────────┐
        │ 通义千问 LLM(qwen-plus/max) 生成纪要：结论 + 待办           │
        └───────────────┬──────────────────────────────────────────┘
                        ▼  Markdown 纪要输出
```

**必须遵守的 API 硬约束**：
1. **只认公网 URL**：不支持本地文件 / Base64 / 二进制流。本地与内录音频先上传 DashScope 临时存储换 `oss://` URL。
2. **`oss://` URL 只能走 RESTful API**，且请求头加 `X-DashScope-OssResourceResolve: enable`；DashScope SDK 不支持 `oss://` 前缀，也不能配该 header → **转写调用用 `requests` 实现**。
3. **分离仅支持单声道**：多声道不做说话人分离 → ffmpeg 强制下混单声道。
4. **异步流程**：提交任务 → `task_id` → 轮询查询 → `SUCCEEDED` → `transcription_url`（24h 有效）→ 下载结果 JSON。
5. **上传限制**：临时存储单文件 ≤1GB、有效期 48h、文件与模型/主账号绑定；URL 含空格或中文必须先 URL 编码（否则 `InvalidFile.DownloadFailed`）。
6. **单次请求仅 1 个 URL**；开启分离时建议音频 ≤2 小时。

---

## 四、目录结构（当前 v7.3.0）

```
open-meeting-scribe/
├── MISSION.md
├── MVP_PLAN.md          # 本文件（v1 施工蓝图，历史参考）
├── CHANGELOG.md         # 迭代日志
├── cli.py               # 命令行入口（server/build/transcribe）
├── desktop.py           # 桌面客户端入口（pywebview 原生窗口，Mac/Windows 共用）
├── .env                 # 环境变量（不入库，.env.example 为模板）
├── core/                # 业务能力层（详见 ARCHITECTURE.md）
│   ├── audio.py         # ffmpeg 归一化 + BlackHole 采集 + 流式录音
│   ├── audio_recording.py # 录音会话管理
│   ├── transcribe.py    # ASR 代理提交转写 + 碎片合并/说话人修正
│   ├── realtime_asr.py  # 实时 ASR WebSocket 流式客户端
│   ├── realtime_summary.py # 实时增量摘要
│   ├── realtime_chapters.py # 实时章节生成
│   ├── diarization.py   # 实时说话人分离（CAM++ 192维 + VAD + 聚类）
│   ├── llm.py           # 通义千问 provider（含事件循环防护三层架构）
│   ├── summarize.py     # 纪要提示词与解析（结论/决策）+ 标题生成
│   ├── pipeline.py      # 串联全流程
│   ├── pipeline_runner.py # 后台管线执行器（重试 + 错误分类）
│   ├── agent_workspace.py # Agent 角色工作区管理
│   ├── agent_loop.py    # Agent 对话循环
│   ├── voiceprint.py    # CAM++ 声纹匹配 + 注册表
│   ├── embedding_provider.py # 声纹嵌入抽象层（云端 + MFCC 降级）
│   ├── cloud_client.py  # 云端 API 客户端（HMAC-SHA256 签名）
│   ├── ...              # 其他 20+ 模块（详见 ARCHITECTURE.md 分层表）
│   └── models/          # 声纹模型（CAM++ 权重 + 编码器实现）
├── app/
│   ├── server.py        # FastAPI app + 中间件 + 全局异常处理
│   ├── settings_store.py # 三层配置加载 + 原子持久化
│   ├── store.py         # 共享状态层
│   └── routers/         # 21 个功能域路由模块
├── frontend/            # Vue 3 + TypeScript + Vite + Pinia SPA
│   ├── src/
│   │   ├── api/         # 18 个 API 模块
│   │   ├── stores/      # 9 个 Pinia store
│   │   ├── composables/ # 35 个可复用逻辑
│   │   ├── views/       # 9 个页面视图 + 子视图
│   │   ├── components/  # 通用组件 + 子域组件
│   │   ├── styles/      # 10 主题 + 19 个模块化 CSS
│   │   └── i18n/        # vue-i18n 国际化（中英双语）
│   └── package.json
├── asr-proxy/           # ASR 代理服务（独立进程，HMAC 签名中继）
├── sms-proxy/           # 短信代理服务（独立进程）
├── voiceprint-service/  # 声纹推理服务（CAM++ 192维，CPU-only torch）
├── data/
│   ├── agent/_roles/    # Agent 角色工作区（预定义 + 用户自定义）
│   ├── recordings/      # 归一化后的录音文件
│   ├── tasks/           # 任务元数据 JSON + 作业日志 JSONL
│   ├── output/          # 生成的纪要 Markdown
│   ├── settings.json    # 用户配置
│   ├── remote_config.json # 远程配置/公告/版本信息
│   └── ...              # 其他数据文件
├── build/               # Windows 打包（PyInstaller spec + Inno Setup）
├── tests/               # 冒烟测试
├── scripts/             # 工具脚本
├── docs/                # 权威文档
│   ├── ARCHITECTURE.md  # 系统架构（唯一事实源）
│   ├── API_CONTRACTS.md # DashScope API 契约
│   ├── PRD.md           # 产品需求
│   ├── ROADMAP.md       # 版本路线
│   ├── BACKLOG.md       # 零散需求与缺陷修复
│   ├── GLOSSARY.md      # 术语表
│   ├── adr/             # 架构决策记录（17 篇）
│   └── design/          # UI 规范 + 设计文档
├── samples/             # 测试音频
└── requirements.txt     # 运行依赖
```

> 完整模块清单与分层职责见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)。

---

## 五、分阶段实施

### P0 · 环境与凭据（很轻）
1. 建独立 Python 环境（`venv`；若 3.14 装 fastapi/sounddevice 有轮子问题则退 3.11）
2. 装依赖：`requests`、`fastapi`、`uvicorn`、`python-dotenv`（可选 `dashscope`/`openai`）
3. `.env` 写入 `DASHSCOPE_API_KEY`（一个 key 同时用于 ASR 与千问纪要）
4. BlackHole 路由：「音频 MIDI 设置」建多输出设备（复用录屏配置）
5. **冒烟测试**：拿一段公网音频 URL 跑通 `paraformer-v2 + diarization_enabled=true`，确认返回 `speaker_id`；千问能出一句纪要

**验收**：脚本提交一个音频 URL → 轮询拿到带 `speaker_id` 的转写 JSON → 千问生成一句纪要。

### P1 · CLI 核心链路
- `python cli.py transcribe samples/会议.wav`
- 流程：ffmpeg 归一化(单声道) → 上传临时 URL → 提交转写(分离) → 轮询 → 组装对话稿 → 千问纪要 → `data/output/会议_纪要.md`（发言人对话稿 + 结论 + 待办）
- 热词：`data/hotwords.txt` → 建 DashScope 热词表 → 转写带 `vocabulary_id`

**验收**：真实中文多人会议音频 → 产出含发言人的可读纪要。

### P2 · 本地 Web UI + 实时内录（MVP 交付面）
- FastAPI 起本地服务（`http://localhost:8000`）
- 页面能力：拖拽音频 / 点「开始录制」（ffmpeg 从 BlackHole 采集）/ 实时进度（含云端排队状态）/ 展示纪要 / 一键复制下载
- 录制结束 → 自动进 P1 管线

**验收**：① 浏览器上传音频拿到纪要；② 开一场线上会议点录制，结束后自动出纪要。

### P3 · 说话人姓名化（已完成 ✅）
- **状态**：✅ 已完成（v3 初版 resemblyzer → v4 升级 CAM++）
- **方案**：CAM++ 192维神经声纹嵌入 + per-meeting 中心化 + 匈牙利算法一对一分配
- 云端只给 `speaker_id`（0/1/2…）。要变「张三」：
  - **声纹自动匹配**：转写后自动提取声纹并与注册表比对（匹配成功自动绑定）
  - **手动绑定**：无匹配时降级为手动绑定，绑定确认后自动注册声纹
- 数据持久化：`data/speakers.json` 存储说话人档案，`data/voiceprint_registry.json` 存储声纹注册表
- 管线集成：转写后自动执行声纹匹配，匹配成功自动进入纪要生成

**MVP 交付 = P0 + P1 + P2（含实时内录）。** P3 后续叠加。

---

## 六、模型与成本

| 环节 | 方案 | 本地占用 / 成本 | 说明 |
|------|------|------|------|
| ASR + 分离 | DashScope `paraformer-v2` | 0 本地占用；约 0.288 元/小时量级 | 一个 API 出转写 + `speaker_id`；只对语音时长计费 |
| 纪要 | 通义千问 `qwen-plus`（默认）/ `qwen-max` | 按 token 计费 | 与 ASR 共用 `DASHSCOPE_API_KEY` |
| 音频采集 | ffmpeg + BlackHole 2ch | 0 | 复用录屏配置，无需 sounddevice |
| 声纹(P3) | CAM++（FunASR CAMPPlus，192维嵌入） | 0 本地占用（模型权重 28MB 已内置） | ✅ 已完成，注册后自动匹配 |

---

## 七、你需要提供 / 操作的事项

**A. 必须你手动操作**
1. **DashScope API Key**：阿里云百炼控制台开通「录音文件识别 / Paraformer」+「通义千问」→ 创建 API Key → 给我写进 `.env`（或你自填）。**这一个 key 同时管转写和纪要。**
2. **BlackHole 音频路由**（实时内录用，复用你录屏配置）：
   - 「音频 MIDI 设置」→ 建**多输出设备** = BlackHole 2ch + 扬声器（取消勾选漂移校正）
   - 系统输出切到「多输出设备」；ffmpeg 从 BlackHole 2ch 采集
   - 若会议软件可单独选输出，直接让其输出到 BlackHole 更干净

**B. 建议你提供（显著提升效果）**
3. **1–2 段真实会议音频**（中文、多人、5–15 分钟，wav/mp3/m4a 均可）→ 放 `samples/`
4. **热词表**：常出错的企业人名、部门、项目名、术语（一行一个）→ 我写进 `data/hotwords.txt`

**C. 确认资源**
5. **网络**：仅需访问 `dashscope.aliyuncs.com`（已验证可达）；**无需 HF、无需下 6–8GB 模型**
6. **授权安装**：同意我建独立 Python 环境、装轻量依赖（不动你现有环境）

> 原「HuggingFace 授权 pyannote」一项——v1 云方案**不再需要，已删除**。

---

## 八、关键风险

| 风险 | 影响 | 对策 |
|------|------|------|
| 音频经云端 API | 架构特性 | 软件本身不存储用户音频到外部；用户自行接入 API 服务商，数据隐私由服务商条款约束，与软件方无关 |
| 分离仅支持单声道 | 多声道不分离 | ffmpeg 强制下混单声道 |
| API 只认公网 URL | 本地/内录文件不能直传 | 走 DashScope 免费临时存储换 `oss://` URL（≤1GB/48h） |
| `oss://` URL 需 RESTful + 特定 header | SDK 不支持 | 转写调用用 `requests`，加 `X-DashScope-OssResourceResolve: enable` |
| 异步任务排队延迟 | 出纪要慢（数分钟） | UI 显示排队/进度；短音频(≤5min)可选 Flash 同步模型 |
| 上传文件 ≤1GB | 超长会议 | 16k 单声道 wav 约 115MB/小时，常规会议远小于 1GB；超长则分段或自建 OSS |
| `speaker_id` ≠ 姓名 | 纪要只有「说话人1」 | P3 声纹 / 人工映射 |
| URL 含空格/中文 | `InvalidFile.DownloadFailed` | 提交前 URL 编码 |

---

## 附：待你拍板

1. **纪要模型**：`qwen-plus`（便宜够用，默认）还是 `qwen-max`（质量高）？
2. **短音频提速**：≤5 分钟的音频是否改用 Flash 同步模型，省掉轮询等待？
3. **MISSION.md** 的 MVP 清单仍写着 pyannote/FunASR，与本版冲突——是否要我一并同步更新？

---

*创建于 2026-09-03；云方案 v1 更新于 2026-09-03*
