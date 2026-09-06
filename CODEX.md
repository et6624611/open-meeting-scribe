# CODEX — AI 渐进式上下文索引

> 本文件是 AI 代理的**第一入口**。控制在 200 行内，提供最小必要上下文。
> 按需深入：只读任务相关章节，不必全量加载。

## 一句话定位

Mac 端会议纪要工具：音频 → ASR 转写 + 说话人分离 + 声纹姓名化 → LLM 结构化纪要。

## 当前状态

- **版本**：v1.x（v1 云方案 + v4 CAM++ 声纹姓名化 + OAuth 认证已实现）
- **技术栈**：Python 3.11+ / FastAPI / DashScope(paraformer-v2 + qwen-plus) / ffmpeg / torch+torchaudio(CAM++ 声纹)
- **前端**：单页 HTML（`app/static/index.html`，~14700 行巨型文件）
- **入口**：`cli.py`（CLI）/ `app/server.py`（Web 服务）

---

## 模块速查表

### core/ — 管线逻辑（纯业务，无 HTTP）

| 文件 | 职责 | 关键函数 |
|------|------|----------|
| `audio.py` | ffmpeg 归一化 + BlackHole 内录采集 | `normalize_audio()`, `start_recording_with_stream()`, `stop_recording_with_stream()` |
| `upload.py` | 本地文件 → DashScope 临时存储 → `oss://` URL | `upload_file()`, `encode_oss_url()` |
| `transcribe.py` | 提交 paraformer-v2 任务 + 轮询 + 组装对话稿 | `transcribe_audio()`, `assemble_dialogue()`, `merge_fragments()` |
| `hotwords.py` | 热词管理 + 热词映射 | `get_or_create_vocabulary()`, `apply_hotword_mappings()` |
| `llm.py` | 通义千问调用封装（同步/异步/流式） | `chat_completion()`, `async_chat_completion()`, `chat_completion_stream()` |
| `summarize.py` | 纪要生成 + 标题生成 | `generate_summary()`, `generate_title()`, `save_summary()` |
| `pipeline.py` | 串联全流程（stage1: 转写, stage2: 纪要） | `run_pipeline()`, `run_pipeline_stage1()`, `run_pipeline_stage2()` |
| `diarization.py` | 实时说话人分离（CAM++ 192维声纹嵌入 + VAD + 余弦相似度贪心聚类） | `SpeakerDiarizer` 类, `extract_speaker_feature()` |
| `realtime_asr.py` | 实时 ASR WebSocket 客户端 | `RealtimeTranscriber` 类 |
| `realtime_summary.py` | 实时增量摘要 | `RealtimeSummarizer` 类 |
| `speakers.py` | 说话人档案 CRUD + 持久化 | `add_speaker()`, `update_speaker()`, `apply_speaker_names()` |
| `voiceprint.py` | CAM++ 声纹嵌入(192维) + 注册表 + per-meeting 中心化 + 匈牙利算法匹配 | `register_voiceprint()`, `auto_identify_speakers()`, `extract_embedding()` |
| `projects.py` | 项目（文件夹分组）管理 + 索引 + 纪要归档 | `create_project()`, `scan_project()`, `sync_meeting_to_folders()`, `search_project()` |
| `users.py` | 当前用户 + OAuth + 说话人绑定 | `get_current_user()`, `find_or_create_oauth_user()`, `bind_speaker()` |
| `errors.py` | 错误分类与瞬时错误判断 | `is_transient_error()`, `classify_error()` |
| `joblog.py` | per-task 作业日志 + 会议助手渐进式上下文 | `append_event()`, `build_context()`, `read_events()` |
| `auth.py` | OAuth 2.0 提供者 + JWT 签发/验证 | `create_jwt()`, `verify_jwt()`, `exchange_github_code()` |

### app/ — Web 服务与前端

| 文件 | 职责 |
|------|------|
| `server.py` | FastAPI app 创建 + router 注册 + 安全审计中间件（~210 行） |
| `store.py` | 共享状态（tasks 字典、实时状态）集中管理 |
| `static/index.html` | 单页前端（~14700 行，含 CSS + JS + HTML） |

### app/routers/ — API 端点

| 文件 | 端点前缀 | 职责 |
|------|----------|------|
| `tasks.py` | `/api/transcribe`, `/api/tasks` | 转写任务 CRUD + 下载 |
| `record.py` | `/api/record`, `/ws/transcript` | 录音控制 + 实时转写 WebSocket |
| `chat.py` | `/api/chat` | AI 对话 |
| `speakers.py` | `/api/speakers` | 说话人管理 + 映射 |
| `voiceprint.py` | `/api/voiceprint` | 声纹注册/匹配/查询 |
| `hotwords.py` | `/api/hotwords` | 热词管理 |
| `notes.py` | `/api/tasks/{id}/notes` | 笔记/注入/待办 |
| `projects.py` | `/api/projects` | 项目管理 + 文件浏览 |
| `settings.py` | `/api/settings` | 系统设置 |
| `user.py` | `/api/user` | 用户信息 + 绑定 |
| `philosophy.py` | `/api/philosophy` | 理念传播（随机展示设计者理念） |
| `auth.py` | `/auth` | GitHub OAuth 登录 + JWT 会话 + 登出 |

### docs/ — 权威文档（单一事实源）

| 文件 | 何时读 |
|------|--------|
| `ARCHITECTURE.md` | 改架构/模块/数据流时 |
| `API_CONTRACTS.md` | 涉及 DashScope API 字段/约束时 |
| `PRD.md` / `ROADMAP.md` | 产品需求/路线决策时 |
| `design/ui-spec.md` | 改前端界面时 |
| `adr/` | 了解/新增重大技术决策时 |
| `GLOSSARY.md` | 术语口径确认时 |

---

## 按任务类型加载

| 我要做什么 | 必读 | 参考 |
|-----------|------|------|
| 改转写管线 | `core/transcribe.py` + `core/pipeline.py` | `docs/API_CONTRACTS.md` |
| 改实时功能 | `core/realtime_asr.py` + `app/routers/record.py` | `docs/adr/0004`, `docs/adr/0006` |
| 改纪要生成 | `core/summarize.py` + `core/llm.py` | `docs/adr/0003` |
| 改说话人/声纹 | `core/speakers.py` + `core/voiceprint.py` | `docs/adr/0005` |
| 改前端界面 | `app/static/index.html` | `docs/design/ui-spec.md` |
| 加新 API 端点 | `app/routers/` 对应文件 + `app/store.py` | `docs/ARCHITECTURE.md` |
| 改热词系统 | `core/hotwords.py` | `docs/API_CONTRACTS.md` |
| 改项目管理 | `core/projects.py` + `app/routers/projects.py` | — |

---

## 硬约束速记（详情见 API_CONTRACTS.md）

1. 转写 API **只认公网 URL**；本地文件先 `upload.py` 换 `oss://` URL
2. `oss://` URL 必须走 **RESTful** + 请求头 `X-DashScope-OssResourceResolve: enable`
3. 说话人分离**仅支持单声道** → ffmpeg 强制下混
4. 临时存储 ≤1GB / 48h；URL 含空格或中文**必须 URL 编码**
5. 密钥只从 `.env` 读，禁止硬编码

## 架构原则速记（详情见 AGENTS.md）

- `server.py` 轻量化（~210 行），业务逻辑在 `core/` 和 `app/routers/`
- 共享状态集中到 `app/store.py`
- 含阻塞操作的端点用 `def`，纯异步 I/O 用 `async def`
- 一个事实只写一处，改架构先改 docs 再改代码

## 数据目录

| 路径 | 内容 |
|------|------|
| `data/recordings/` | 归一化后的录音文件 |
| `data/tasks/` | 任务元数据 JSON + 作业日志 JSONL |
| `data/output/` | 生成的纪要 Markdown |
| `data/uploads/` | 用户上传的原始音频文件 |
| `data/hotwords.txt` | 热词表 |
| `data/hotword_mappings.txt` | 热词映射（ASR 识别纠正） |
| `data/speakers.json` | 说话人档案 |
| `data/voiceprint_registry.json` | 声纹注册表 |
| `data/users.json` | 用户数据（本地 + OAuth） |
| `data/projects.json` | 项目索引 |
| `data/settings.json` | 系统设置 |

## 深入加载（按需）

- 完整协作规范 → `AGENTS.md`
- 完整架构设计 → `docs/ARCHITECTURE.md`
- 完整 API 契约 → `docs/API_CONTRACTS.md`
- 迭代历史 → `CHANGELOG.md`
- 施工蓝图 → `MVP_PLAN.md`
- 自动生成的知识库 → `.qoder/repowiki/`（只读参考，手写文档为权威源）
