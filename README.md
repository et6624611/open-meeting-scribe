---
title: Open Meeting Scribe
description: Open-source meeting minutes tool — audio in, structured minutes out. Platform-agnostic, your data stays on your device.
tags: ["meeting", "transcription", "ASR", "speaker-diarization", "voiceprint", "open-source"]
created_at: "2026-09-03"
updated_at: "2026-10-05"
version: "1.0.0"
---

<p align="center">
  <h1 align="center">Open Meeting Scribe</h1>
  <p align="center">
    <strong>Open-source meeting minutes tool — audio in, minutes out</strong>
  </p>
  <p align="center">
    Audio → Transcription + Speaker Diarization → Structured Minutes (Conclusions / Action Items)
  </p>
  <p align="center">
    <a href="README_zh-CN.md">中文文档</a>
  </p>
</p>

---

**Platform-agnostic — audio is the only input.** Whether it's an online video call, a phone conference, or an in-person meeting room — if it produces audio, Open Meeting Scribe can transcribe it and generate structured minutes automatically.

## ✨ Features

- **Multiple audio inputs**: Drag-and-drop file upload (wav/mp3/m4a) + system loopback recording (BlackHole on macOS) + live microphone capture
- **High-accuracy transcription**: Powered by DashScope paraformer-v2, state-of-the-art for CJK languages
- **Speaker diarization**: Automatically identifies and labels different speakers (Speaker 1, Speaker 2, ...)
- **Voiceprint naming**: Register a voiceprint once, and "Speaker 1" becomes "John Smith" across all future meetings
- **Optional fully local engine** 🚧: Offline FunASR transcription + local CAM++ voiceprint + your self-hosted Ollama / LM Studio endpoint — meeting data never leaves your device (in development, see [SECURITY.md §1.3](SECURITY.md) data-flow matrix)
- **Hotword boosting**: Custom vocabulary (names, jargon) weighted during recognition for higher accuracy
- **Structured minutes**: LLM-generated conclusions + action items (who / what / deadline)
- **AI chat-driven workflow**: Control recording, transcription, queries, and settings through natural language
- **Real-time transcription**: Live transcript view with incremental summaries during the meeting
- **Project management**: Organize meetings by project, cross-meeting search, and archive
- **Themes**: 7 built-in themes with light/dark mode

## 🖥 Requirements

| Item | Requirement |
|------|-------------|
| OS | macOS 12+ (primary development platform) |
| Python | 3.11+ |
| Node.js | 18+ (frontend build) |
| ffmpeg | Required for audio processing |
| BlackHole | Required for system loopback ([Install](https://github.com/ExistentialAudio/BlackHole)) |

> **Support scope**: This project is desktop-first (macOS); viewports under 768px are not guaranteed to be adapted.
> **支持边界**：本项目桌面优先（macOS），<768px 视口不做适配保证。

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/et6624611/open-meeting-scribe.git
cd open-meeting-scribe
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys:

| Variable | Description | How to obtain |
|----------|-------------|---------------|
| `DASHSCOPE_API_KEY` | Alibaba Cloud DashScope API Key (for minutes generation) | [DashScope Console](https://dashscope.console.aliyun.com/) |
| `ASR_PROXY_URL` | ASR proxy service URL (transcription relay) | Self-host or use a subscription service |
| `ASR_PROXY_TOKEN` | ASR proxy shared secret | Must match the proxy server config |

> **About the ASR proxy**: To protect your API key, transcription requests are relayed through a proxy service. The client never stores the DashScope key directly. You can self-host the `asr-proxy/` service or use a third-party proxy.

### 3. Install backend dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Build the frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

### 5. Start the server

```bash
python cli.py server
```

Visit http://localhost:8000 to use the app.

### CLI usage

```bash
# Transcribe an audio file directly
python cli.py transcribe samples/your-meeting.wav
```

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Frontend (Vue 3 + TypeScript)            │
│            Drag & Drop / Live Recording / AI Chat         │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / WebSocket
┌────────────────────────▼────────────────────────────────┐
│                 Backend (Python + FastAPI)                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ Pipeline │  │Voiceprint│  │LLM Mins. │  │ Projects │   │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────────┘   │
└───────┼────────────┼────────────┼───────────────────────┘
        │            │            │
   ┌────▼────┐  ┌────▼────┐  ┌───▼─────┐
   │ASR Proxy│  │ CAM++   │  │DashScope │
   │(relay)  │  │(embed)  │  │  (LLM)  │
   └─────────┘  └─────────┘  └─────────┘
```

**Core tech stack**:
- **Backend**: Python 3.11+ / FastAPI / Uvicorn
- **Frontend**: Vue 3 / TypeScript / Vite / Pinia
- **ASR**: DashScope paraformer-v2 (batch) + qwen-audio-asr-flash (real-time streaming)
- **Voiceprint**: CAM++ (FunASR CAMPPlus) 192-dim embeddings + cosine similarity clustering + Hungarian algorithm matching
- **Minutes generation**: Qwen-plus (OpenAI-compatible API)
- **Audio processing**: ffmpeg + BlackHole (macOS system loopback)

## 🌐 Internationalization

The UI supports multiple languages. The default language is **English**; Chinese (zh-CN) is available as a first-class translation.

| Language | Code | Status |
|----------|------|--------|
| English | `en` | Default |
| 中文 | `zh-CN` | Full translation |

Language detection priority: `localStorage` → browser language → English (default).

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [MISSION.md](MISSION.md) | Project mission & design principles |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture & module details |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Cloud deployment guide |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Version roadmap |
| [docs/PRD.md](docs/PRD.md) | Product requirements document |
| [SECURITY.md](SECURITY.md) | Security policy & data privacy |
| [CHANGELOG.md](CHANGELOG.md) | Changelog |

## 🤝 Contributing

Issues and Pull Requests are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📄 License

[GNU AGPLv3](LICENSE) © 2026 Yongliang Wang
