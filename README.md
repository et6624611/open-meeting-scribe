---
title: Open Meeting Scribe
description: 开源 Mac 端会议纪要工具
author: 王永亮
created_at: 2026-09-03
updated_at: 2026-09-07
status: published
version: 1.0.0
---

# Open Meeting Scribe

> 开源、Mac 端的会议纪要工具：**音频 → 转写 + 说话人分离 → 结构化纪要（结论 / 待办）**。不绑定任何会议平台，音频输入即一切。

## 当前状态
- **阶段**：v1 云方案，设计已定稿，待搭 P0 环境。
- **版本路线**：v1 云（DashScope）→ v2 本地 → v3 声纹姓名化。
- **下一步**：P0 冒烟测试——跑通 `paraformer-v2` + 说话人分离，确认返回 `speaker_id`。
- **技术栈**：Python + DashScope 录音文件识别 + 通义千问；FastAPI 本地 Web UI；ffmpeg + BlackHole 内录。

## 文档地图（改前先读对应层；一个事实只在该层唯一文档里写）
| 层 | 文档 | 用途 |
|----|------|------|
| **AI 入口** | [CODEX.md](CODEX.md) | 渐进式上下文索引，AI 第一入口 |
| **Why 理念** | [MISSION.md](MISSION.md) | 为什么做、设计原则 |
| **What 产品** | [docs/PRD.md](docs/PRD.md) · [docs/ROADMAP.md](docs/ROADMAP.md) · [docs/design/DESIGN_DECISIONS.md](docs/design/DESIGN_DECISIONS.md) | 需求 / 路线 / 界面设计决策 |
| **How 技术** | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/API_CONTRACTS.md](docs/API_CONTRACTS.md) · [docs/adr/](docs/adr/) | 架构 / API 契约 / 决策记录 |
| **Build 实现** | `core/` · `app/` · `tests/` · [CHANGELOG.md](CHANGELOG.md) | 代码 / 测试 / 迭代日志 |
| **施工蓝图** | [MVP_PLAN.md](MVP_PLAN.md) | v1 分阶段实施（P0–P3） |
| **协作约定** | [AGENTS.md](AGENTS.md) | AI/新人开工规则 |
| **术语** | [docs/GLOSSARY.md](docs/GLOSSARY.md) | 口径统一 |

## 快速上手（开发者）
```bash
cp .env.example .env          # 填 DASHSCOPE_API_KEY
bash scripts/setup_env.sh     # 建 venv + 装依赖（待补）
python cli.py transcribe samples/xxx.wav
```
> 环境搭建细节见 MVP_PLAN「P0」；密钥只需一个 DashScope Key（转写 + 纪要共用）。

## 协作铁律
1. AI / 新人先读本文件 + MISSION.md，再进对应层文档。
2. 重大决策记 `docs/adr/`（新增一篇，不改旧的）。
3. 改架构 / 契约：**先改 docs，再改代码**。
4. 一个事实只写一处，禁止跨文档复述。
5. 详见 [AGENTS.md](AGENTS.md)。

---
*v1 云方案 · 骨架建于 2026-09-03*
