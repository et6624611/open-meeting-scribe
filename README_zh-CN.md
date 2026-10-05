---
title: Open Meeting Scribe（中文）
description: 开源会议纪要工具——音频输入即一切，不绑定任何会议平台，数据留在你的设备上。
tags: ["meeting", "transcription", "ASR", "speaker-diarization", "open-source"]
created_at: "2026-09-03"
updated_at: "2026-10-05"
version: "1.0.0"
---

<p align="center">
  <h1 align="center">Open Meeting Scribe</h1>
  <p align="center">
    <strong>开源会议纪要工具——音频输入，纪要输出</strong>
  </p>
  <p align="center">
    音频 → 转写 + 说话人分离 → 结构化纪要（结论 / 待办）
  </p>
  <p align="center">
    <a href="README.md">English</a>
    ·
    <a href="https://github.com/et6624611/open-meeting-scribe/releases">版本发布</a>
    ·
    <a href="SECURITY.md">安全与隐私</a>
  </p>
  <p align="center">
    <img alt="License" src="https://img.shields.io/badge/license-AGPL--3.0-blue">
    <img alt="Version" src="https://img.shields.io/badge/version-1.0.0-green">
    <img alt="Platform" src="https://img.shields.io/badge/platform-macOS%20%7C%20Docker-lightgrey">
  </p>
</p>

---

**不绑定任何会议平台，音频输入即一切。** 无论是线上视频会议、电话会议还是线下会议室，只要能输出音频，就能自动转写并生成结构化纪要。

> **面向非技术用户**：本项目由 AI 辅助开发，也面向「能在 AI 编程助手帮助下使用开源软件」的非 IT 人员。源码与 Docker 两条路径都不需要你是开发者，但需要能接受在终端里粘贴命令。

## ✨ 功能特性

- **多种音频输入**：文件拖拽上传（wav/mp3/m4a）+ BlackHole 系统内录 + 麦克风实时录音
- **高精度转写**：基于 DashScope paraformer-v2，中文识别 SOTA
- **说话人分离**：自动识别不同发言人，标注「说话人 1 / 说话人 2 / ...」
- **声纹姓名化**：注册声纹后，「说话人 1」自动变为「张三」，一次注册全局生效
- **可选全本地引擎** 🚧：FunASR 离线转写 + 本地 CAM++ 声纹 + 自接 Ollama / LM Studio 端点，会议数据永不出设备（开发中，数据边界见 [SECURITY.md §1.3](SECURITY.md) 流向矩阵）
- **热词增强**：自定义企业人名、专业术语，识别时自动加权纠正
- **结构化纪要**：LLM 自动生成结论摘要 + 待办事项（谁 / 做什么 / 截止日）
- **AI 对话驱动**：自然语言对话完成录音、转写、查询、设置等全流程操作
- **实时转写**：会议进行中即可查看实时转写文本与增量摘要
- **项目管理**：按项目组织会议，支持跨会议搜索与资料归档
- **多主题**：7 套内置主题，支持明/暗模式切换

## 🎬 演示

_Demo 视频/GIF 将在 1.0.0 正式发布前补上。当前可直接参考下方「快速开始」。_

## 🖥 系统要求

> **分发方式**：仅提供源码安装与 Docker 两条路径，不提供预编译二进制包。

| 项目 | 要求 |
|------|------|
| 操作系统 | macOS 12+（主要开发平台）；Linux 可走 Docker |
| Python | 3.11+（源码安装） |
| Node.js | 18+（前端构建） |
| ffmpeg | 音频处理必需（Docker 镜像已内置） |
| BlackHole | 系统内录需要（[安装指南](https://github.com/ExistentialAudio/BlackHole)） |

> **支持边界 / Support scope**：本项目桌面优先（macOS），<768px 视口不做适配保证。
> Desktop-first (macOS); viewports under 768px are not guaranteed to be adapted.

## 🚀 快速开始

### 路径 A — Docker（云模式，内置 ffmpeg）

```bash
docker build -t open-meeting-scribe .
docker run --rm -p 8000:8000 \
  -e DASHSCOPE_API_KEY=your-key \
  -v "$(pwd)/data:/app/data" \
  open-meeting-scribe
```

访问 http://localhost:8000。镜像内置 ffmpeg，但**不含**可选的 FunASR 本地引擎权重（约 2 GB）——启用本地引擎时按需下载到挂载卷中。

### 路径 B — 源码安装

#### 1. 克隆仓库

```bash
git clone https://github.com/et6624611/open-meeting-scribe.git
cd open-meeting-scribe
```

#### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 API Key：

| 变量 | 说明 | 获取方式 |
|------|------|----------|
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key（纪要生成） | [百炼控制台](https://bailian.console.aliyun.com/) |
| `ASR_PROXY_URL` | ASR 代理服务地址（转写中转） | 自建或使用订阅服务 |
| `ASR_PROXY_TOKEN` | ASR 代理共享密钥 | 与代理端配置一致 |

> **关于 ASR 代理**：为保护 API Key 安全，转写请求通过代理服务中转，客户端不存储 DashScope Key。你可以自行部署 `asr-proxy/` 服务，或使用第三方提供的代理服务。

#### 3. 安装后端依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 4. 构建前端

```bash
cd frontend
npm install
npm run build
cd ..
```

#### 5. 启动服务

```bash
python cli.py server
```

访问 http://localhost:8000 即可使用。

### CLI 方式

```bash
# 直接转写音频文件
python cli.py transcribe samples/your-meeting.wav
```

## 🏗 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (Vue 3 + TypeScript)              │
│              拖拽上传 / 实时录音 / AI 对话框               │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / WebSocket
┌────────────────────────▼────────────────────────────────┐
│              后端 (Python + FastAPI)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 转写管线  │ │ 声纹匹配  │ │ LLM纪要  │ │ 项目管理  │   │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────────┘   │
└───────┼────────────┼────────────┼───────────────────────┘
        │            │            │
   ┌────▼────┐  ┌────▼────┐  ┌───▼─────┐
   │ASR 代理  │  │CAM++ 服务│  │DashScope │
   │(转写中转)│  │(声纹嵌入)│  │(通义千问) │
   └─────────┘  └─────────┘  └─────────┘
```

**核心技术栈**：
- **后端**：Python 3.11+ / FastAPI / Uvicorn
- **前端**：Vue 3 / TypeScript / Vite / Pinia
- **语音识别**：DashScope paraformer-v2（批处理）+ qwen-audio-asr-flash（实时流式）
- **声纹识别**：CAM++ (FunASR CAMPPlus) 192 维嵌入 + 余弦相似度聚类 + 匈牙利算法匹配
- **纪要生成**：通义千问 qwen-plus
- **音频处理**：ffmpeg + BlackHole（macOS 系统内录）

## 📖 文档

| 文档 | 说明 |
|------|------|
| [MISSION.md](MISSION.md) | 项目使命与设计原则 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构与模块说明 |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | 云服务器部署指南 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 版本路线图 |
| [docs/PRD.md](docs/PRD.md) | 产品需求文档 |
| [SECURITY.md](SECURITY.md) | 安全策略与数据隐私声明 |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | 第三方许可与引导下载模型清单 |
| [CHANGELOG.md](CHANGELOG.md) | 更新日志 |

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 📄 许可证

[GNU AGPLv3](LICENSE) © 2026 et6624611
