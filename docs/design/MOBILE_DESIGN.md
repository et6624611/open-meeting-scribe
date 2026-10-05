---
title: 移动端消息流设计方案
description: 基于 Webhook 的消息流移动端交互设计，用户通过自选消息应用与本地服务双向通信，实现会议状态监控、随记、超时告警推送与受限的远程动作执行。
tags: ["mobile", "webhook", "notification", "telegram", "design"]
created_at: "2026-09-12"
updated_at: "2026-09-12"
version: "1.1.0"
author: "Yongliang Wang"
status: "published"
related_docs: ["docs/ROADMAP.md", "docs/PRD.md", "docs/adr/0014-移动端走Webhook消息流.md", "docs/adr/0015-本地优先原则重定义与引流授权服务.md", "docs/AUTH_DESIGN.md", "AGENTS.md"]
---

# 移动端消息流设计方案

> **v1.1.0 变更摘要**：
> - 修复 v1.0.0 五处阻塞性问题（ADR 编号错标、多用户鉴权缺失、动作远程执行未做白名单、共享状态归属违反 AGENTS.md、异步边界未定义）
> - 施工顺序由 P1-P5 重排为 M0-M5，工时估算由 4 天修正为 7-9 天
> - 依据 [ADR-0015](../adr/0015-本地优先原则重定义与引流授权服务.md) 澄清「本地数据·云端智能」定义，企业微信通道拆分为「群机器人（单向）」与「智能机器人（双向，需公网）」两行

## 1. 设计背景

### 1.1 问题

Open Meeting Scribe 是本地数据·云端智能的开源项目，不提供官方云服务器。用户在自己的电脑（macOS/Windows）上运行主服务，手机需要能够：

1. **接收会议告警** — 录音超时、静默检测等异常推送到手机
2. **查看会议状态** — 了解当前是否有会议在进行、进度如何
3. **随记** — 在手机上快速记录想法，写入对应会议
4. **与 AI 助手交互** — 查询待办、纪要等会议信息

### 1.2 核心约束

依据 [ADR-0015](../adr/0015-本地优先原则重定义与引流授权服务.md) 澄清后的「本地数据·云端智能」定义：

- **数据主权本地**：录音、纪要、tasks、settings、users.json 等全部业务数据永久存储在用户本地设备，永不落地到项目方服务器
- **计算能力云端**：ASR、LLM、声纹识别通过云端 API 提供（DashScope / 项目方共享 proxy / 用户自配）
- **主服务默认本地**：FastAPI 主服务运行在用户本地（`127.0.0.1:8000`），**默认无公网 IP**；用户如自愿部署到自己的云可解锁公网回调能力，但项目方不提供官方部署服务
- **开源精神**：用户完全掌控数据流向，不强绑特定平台
- **多用户兼容**：项目已上线 GitHub OAuth + JWT 的多用户体系（见 [`core/users.py`](../../core/users.py)、[`core/auth.py`](../../core/auth.py)），移动端方案必须与 ContextVar 鉴权模型兼容，不能假设「进程级单用户」
- **AGENTS.md 架构约束**：跨路由共享状态放 `app/store.py`；异步 I/O 用 `async def`，阻塞操作用 `def`

### 1.3 方案选型

| 方案 | 结论 | 理由 |
|------|------|------|
| 独立移动端面板 | ❌ 放弃 | 开发成本高，需维护独立前端 |
| PWA 响应式 | ⏳ 暂缓 | 主服务本地时需同网络直连，跨网络不可用；若用户自部署到云可解锁 |
| **Webhook 消息流** | ✅ 采用 | 零运营成本，用户自选通知通道，复用现有后端 API |

## 2. 架构概览

```
┌──────────────────────────────────────────────────────┐
│  用户本地电脑（默认部署位置）                          │
│                                                      │
│  ┌─────────────┐    ┌──────────────┐                 │
│  │ 主服务 :8000 │←──→│ core/notify  │                 │
│  │ (FastAPI)    │    │ (通知模块)    │                 │
│  │              │    └──────┬───────┘                 │
│  │  chat.py     │           │                         │
│  │  record.py   │           │ HTTP POST               │
│  │  notes.py    │           ▼                         │
│  │  mobile.py   │  ┌────────────────┐                │
│  └──────────────┘  │ 用户自选通道    │                │
│                     │ ┌────────────┐ │                │
│                     │ │ Telegram   │ │                │
│                     │ │ Bark       │ │                │
│                     │ │ ntfy       │ │                │
│                     │ │ 企微群机器人│ │                │
│                     │ │ Server酱   │ │                │
│                     │ │ 自定义 URL  │ │                │
│                     │ └────────────┘ │                │
│                     └───────┬────────┘                │
└─────────────────────────────┼────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  📱 手机消息应用   │
                    │  (接收通知/回复)   │
                    └──────────────────┘
```

### 2.1 数据流

**下行（服务 → 手机）**：事件触发 → `core/notify.py` 格式化（含 i18n + 分片）→ 按 task 归属解析目标用户 → 查用户 `mobile_bindings` → HTTP POST 到各通道

**上行（手机 → 服务）**：用户回复 → 通道适配层解析 → `mobile.py` 鉴权（`chat_id → user_id`）→ 注入 ContextVar → 动作白名单校验 → 复用 `chat.py` 逻辑 → 分片回发

**鉴权前置**：上行消息在进入 `chat.py` 前必须先解析 `chat_id → user_id` 并调用 `set_request_user_id`，否则计量、注入、任务归属逻辑全部失效。

### 2.2 通道双向性

| 通道 | 下行 | 上行 | 说明 |
|------|------|------|------|
| Telegram Bot | ✅ Bot API | ✅ Long polling / Webhook | **推荐首选**：天然双向，免费，long polling 无需公网 |
| Bark (iOS) | ✅ HTTP POST | ⚠️ 回调 URL / 快捷指令 | 下行优秀，上行需额外配置 |
| ntfy | ✅ HTTP POST | ⚠️ 发布到 topic | 需服务订阅 topic |
| **企业微信群机器人** | ✅ Webhook | ❌ **不支持上行** | 单向告警首选，配置最简；Webhook URL 是唯一凭证 |
| **企业微信智能机器人** | ✅ API（Bot ID + Secret） | ⚠️ **需公网回调 + 加解密** | 主服务本地时不可用；用户自部署到云可解锁，违背默认约束，本项目不推荐 |
| Server酱 | ✅ HTTP GET/POST | ❌ 单向 | 仅通知，不支持交互 |
| 自定义 Webhook | ✅ HTTP POST | ⚠️ 取决于实现 | 通用适配 |

**MVP 首选 Telegram Bot**：零成本、天然双向、支持 Markdown、支持 inline keyboard 快捷按钮、long polling 不需要公网 IP。企业微信群机器人作为**纯下行告警**的补充选项（配置最简）。其他通道延后到 M4 阶段按用户需求驱动。

## 3. 会话锚点模型

### 3.1 问题

桌面端 AI 面板的上下文由视觉空间提供（用户看到选了哪个会议）。移动端通过消息应用交互时，所有信息在一条线性流中，「当前在哪个会议」必须显式管理。

### 3.2 设计

引入**会话锚点（Active Context）**：按用户维度维护 `active_task_id`。

```python
# app/store.py（跨路由共享状态，遵循 AGENTS.md 约束）
# user_id → 当前锚定的 task_id
mobile_active_contexts: dict[str, str | None] = {}
```

**归属说明**：不放 `core/notify.py`。AGENTS.md 明确要求「跨路由共享状态统一放 `app/store.py`」，`mobile.py`、`chat.py`、`record.py` 都会读写锚点。

**持久化策略**：
- 内存字典用于运行时读写
- 变更时异步落盘到 `data/mobile_session.json`，服务重启后恢复
- 与 `realtime_*` 字典的区别：那些是「实时状态」（服务重启即失效），锚点是「用户偏好」（应跨重启保留，避免用户重新 `/switch`）

### 3.3 上下文解析规则

用户消息到达时，按以下优先级确定目标会议：

| 优先级 | 来源 | 示例 |
|--------|------|------|
| 1 | `@会议名` 前缀 | `@方案评审 记一下买机票` |
| 2 | 会话锚点 | 用户已 `/switch 方案评审`，后续消息默认该会议 |
| 3 | 无上下文 | 提示用户选择：`/list` 查看或 `/switch` 切换 |

**告警消息不受锚点限制**：超时告警等推送始终带 `[会议标签]` 前缀，不管当前锚点在哪。

**会议名解析策略**（v1.1.0 新增）：
- 会议名可能含空格（如「Q3 预算评审」），解析时**最长匹配优先** —— 遍历 `tasks` 中所有 `title` / `audio_name`，取与 `@` 后文本前缀匹配的最长项
- 冲突时（多个会议同名）附加 task_id 前 4 位消歧，如 `@周会(a1b2)`
- 会议短标签生成规则：`title[:12]` 或 `audio_name[:12]`，超长追加 `…`
- 录音中的 task 通常无 `title`（stage2 才生成），退化到 `audio_name`

### 3.4 多用户与鉴权绑定（v1.1.0 新增）

#### 3.4.1 用户绑定流程

移动端上行消息不带 JWT cookie，必须通过 `chat_id ↔ user_id` 映射解析用户身份。

**绑定时序**：

```
桌面端浏览器                    服务端                     Telegram
    │                            │                            │
    │ 1. POST /api/mobile/bind   │                            │
    │───────────────────────────>│                            │
    │                            │ 2. 生成 6 位一次性绑定码   │
    │                            │    存 mobile_pending_bindings │
    │ 3. {code: "123456",        │                            │
    │    hint: "10 分钟有效"}    │                            │
    │<───────────────────────────│                            │
    │ 4. 展示："请在 Telegram    │                            │
    │    发送 /bind 123456"      │                            │
    │                            │                            │
    │                            │       5. 用户发送 /bind 123456
    │                            │<───────────────────────────│
    │                            │ 6. 校验绑定码              │
    │                            │ 7. 写入 users.json 的      │
    │                            │    mobile_bindings.telegram │
    │                            │ 8. 销毁绑定码              │
    │                            │       9. 回复"绑定成功"    │
    │                            │───────────────────────────>│
```

#### 3.4.2 上行消息鉴权

```python
# app/routers/mobile.py
from core.users import set_request_user_id, load_users

def resolve_user_from_chat_id(chat_id: str, provider: str) -> str | None:
    """chat_id → user_id 反查，未绑定返回 None（不透露 chat_id 是否存在，防枚举）"""
    users = load_users()
    for user in users["users"]:
        bindings = user.get("mobile_bindings", {})
        if bindings.get(provider) == chat_id:
            return user["id"]
    return None

# 处理消息前必须注入 ContextVar
user_id = resolve_user_from_chat_id(chat_id, "telegram")
if not user_id:
    return _("尚未绑定，请在桌面端设置页获取绑定码")
set_request_user_id(user_id)
try:
    result = await chat_endpoint(request)
finally:
    set_request_user_id(None)  # 必须清理，避免连接池复用时状态泄漏
```

#### 3.4.3 下行消息路由

`send_notification(task_id, event, ...)` 内部：

1. 从 `tasks[task_id]` 读取 `owner_user_id`（若无则视为「公共任务」，推送给所有已绑定用户）
2. 从 `users.json` 查该用户的 `mobile_bindings`
3. 对每个绑定的通道发送

**前置任务**：现有 `tasks[task_id]` 数据结构无 `owner_user_id` 字段。M1 阶段需在录音创建 / 上传时补充：`tasks[task_id]["owner_user_id"] = get_request_user_id()`。这是本方案的隐含依赖，不做则多用户环境下告警会串。

#### 3.4.4 数据结构变更

`data/users.json` 用户对象新增字段：

```json
{
  "id": "uuid",
  "name": "Yongliang Wang",
  "mobile_bindings": {
    "telegram": "123456789",
    "wecom_group": "@wecom_user_id"
  }
}
```

**迁移策略**：读取时若字段缺失自动补 `{}`，写回时保留（参考 [`core/users.py`](../../core/users.py) 已有的 `current_user → users` 迁移模式）。

## 4. 消息协议

### 4.1 下行消息格式（服务 → 手机）

所有下行消息遵循统一结构：

```
[会议标签] 标题
───────────────
正文内容
[操作提示（可选）]
```

**i18n 约束**：所有用户可见字符串必须走 `core/i18n._()`，禁止硬编码中文；否则英文用户收到中文通知。i18n key 命名空间 `mobile.event.*` / `mobile.reply.*`。

#### 4.1.1 告警通知

```
📋 [方案评审] ⚠️ 静默告警
───────────────
会议已静默 5 分钟，请确认是否继续
回复 "继续" 或 "停止"
```

#### 4.1.2 状态推送

```
📋 [方案评审] 转写完成 ✅
───────────────
音频时长: 45:23 | 说话人: 4 | 句子: 312
纪要已生成
```

#### 4.1.3 录音开始

```
📋 [方案评审] 🔴 录音已开始
───────────────
说话人: 3 | 实时转写中
```

#### 4.1.4 长消息分片（v1.1.0 新增）

- Telegram 单条消息上限 **4096 字符**
- `chat.py` 的 LLM 回复上限 `max_tokens=2048`，中文约 3000-4000 字符，易触上限
- `notify.py` 必须实现分片发送：按段落切分（优先 `\n\n`，次选 `\n`，兜底按句号），单片 ≤ 3500 字符（预留 Markdown 转义开销）
- 分片末尾追加 `[i/n]` 标记，便于用户拼接阅读

### 4.2 上行消息格式（手机 → 服务）

#### 4.2.1 全局指令（不需要锚点）

| 指令 | 功能 | 示例 |
|------|------|------|
| `/bind <code>` | 绑定当前 chat_id 到桌面用户（v1.1.0 新增） | `/bind 123456` |
| `/unbind` | 解除当前绑定（v1.1.0 新增） | `/unbind` |
| `/list` | 列出最近会议 | `/list` |
| `/status` | 当前录音状态 | `/status` |
| `/switch <名称>` | 切换会话锚点 | `/switch 方案评审` |
| `/help` | 显示帮助 | `/help` |

#### 4.2.2 会议指令（需要锚点或 @前缀）

| 指令 | 功能 | 示例 |
|------|------|------|
| `@会议名 内容` | 指定会议发送消息 | `@方案评审 记一下买机票` |
| `内容`（无前缀） | 发到当前锚点会议 | `记一下买机票` |

#### 4.2.3 交互流示例

```
[系统] 🔔 会议「方案评审」已开始录音

[用户] /status
[系统] 📋 [方案评审] 🔴 录制中 01:23:45
       说话人: 3 | 句子: 142

[用户] 记一下：下周一前提交预算
[系统] ✅ 已记录笔记到「方案评审」

[用户] /list
[系统] 会议列表：
       1. 🟢 方案评审（录制中）
       2. ✅ 周会（已完成，09/11）
       3. ✅ 客户拜访（已完成，09/10）

[用户] /switch 周会
[系统] 📋 已切换到「周会」
       状态: 已完成 | 待办: 3 条

[用户] 待办有哪些？
[系统] 📋 [周会] 待办事项：
       ⬜ 提交Q3预算（张三）
       ⬜ 更新项目排期（李四）
       ✅ 发送会议纪要（王五）

[系统] ⚠️ [方案评审] 静默告警
       会议已静默 5 分钟
       回复 "继续" 或 "停止"
```

### 4.3 动作白名单（v1.1.0 新增）

`chat.py` 的 [`ACTION_REGISTRY`](../../app/routers/chat.py) 包含破坏性动作（`record_start` / `record_stop` / `retranscribe` / `delete_theme` 等）。**移动端默认只开放只读查询动作**，破坏性动作需用户在桌面端设置页显式启用，或走「二次确认」流程。

#### 4.3.1 动作分级

| 级别 | 动作 | 移动端默认 |
|------|------|-----------|
| **只读** | `list_tasks` / `get_status` / `get_hotwords` / `get_hotword_mappings` / `get_settings` / `extract_todos` / `summarize_conclusions` / `analyze_speakers` | ✅ 开启 |
| **写入** | `record_pause` / `record_resume` / `retry_summary` | ⚠️ 需桌面端启用 |
| **破坏性** | `record_start` / `record_stop` / `retranscribe` / `create_theme` / `delete_theme` | ❌ 需桌面端启用 + 二次确认 |

#### 4.3.2 二次确认（inline keyboard）

破坏性动作触发时，服务端不直接执行，先回复带按钮的消息：

```
📋 [方案评审] 确认操作
───────────────
你即将远程停止当前录音
[✅ 确认] [❌ 取消]
```

用户点按钮 → Telegram callback_query → `mobile.py` 校验 `callback_data`（含 nonce 防重放）→ 执行动作。

#### 4.3.3 配置

复用 `data/settings.json` 已有的 `disabled_commands` 字段（避免配置项发散），新增 per-user 的 `mobile_action_whitelist`：

```json
{
  "mobile_notification": {
    "action_whitelist": {
      "write": ["record_pause", "record_resume"],
      "destructive": []
    }
  }
}
```

## 5. 通知事件定义

以下事件触发下行推送，在 `data/settings.json` 中可按事件独立开关。**消息模板走 i18n**，不硬编码中文：

| 事件 ID | 触发条件 | 默认开关 | i18n Key |
|---------|----------|----------|----------|
| `recording_start` | 录音开始 | ON | `mobile.event.recording_start` |
| `recording_stop` | 录音停止 | ON | `mobile.event.recording_stop` |
| `silence_warning` | 静默检测温和告警 | ON | `mobile.event.silence_warning` |
| `silence_urgent` | 静默检测紧急告警 | ON | `mobile.event.silence_urgent` |
| `auto_stop` | 自动关停录音 | ON | `mobile.event.auto_stop` |
| `transcribe_complete` | 转写完成 | OFF | `mobile.event.transcribe_complete` |
| `summary_complete` | 纪要生成完成 | OFF | `mobile.event.summary_complete` |

## 6. 实现计划

### 6.1 文件结构

```
新增文件：
├── core/
│   └── notify.py              # 通知发送 + 消息格式化 + 通道适配 + 分片 + 限流
├── app/routers/
│   └── mobile.py              # 上行端点 + Telegram long polling 生命周期 + 绑定流程
└── tests/
    └── test_mobile.py         # 冒烟测试

修改文件：
├── app/store.py               # 新增 mobile_active_contexts、mobile_pending_bindings、持久化读写
├── app/server.py              # 注册 mobile router；startup/shutdown 挂载 polling
├── app/routers/record.py      # 静默检测三阶段 + 录音开始/停止中调用 notify；task 补 owner_user_id
├── core/users.py              # users 数据结构增加 mobile_bindings 字段（含迁移）
├── core/i18n/locales/*.po     # 新增消息模板翻译（mobile.event.* / mobile.reply.*）
├── data/settings.json         # 新增 mobile_notification 配置节
└── frontend/src/views/Settings*.vue  # 通知配置区 + 绑定 UI + 动作白名单
```

### 6.2 模块职责

#### core/notify.py

```
职责：
  1. send_notification() — 通用通知发送（异步 httpx.AsyncClient，非阻塞）
  2. format_message() — 消息格式化（含会议标签 + i18n）
  3. split_long_message() — 长消息分片（按段落 / 句号切分，≤3500 字符）
  4. 各通道适配器 — TelegramAdapter / WecomGroupAdapter / BarkAdapter / NtfyAdapter / GenericWebhookAdapter
  5. RateLimiter — 频率限流（key = (task_id, event, level)）

不放这里：
  - MobileSession（属跨路由共享状态，放 app/store.py）
  - 上行消息解析（属端点职责，放 app/routers/mobile.py）
```

#### app/routers/mobile.py

```
职责：
  1. POST /api/mobile/inbound — 通用上行入口（含 chat_id → user_id 鉴权）
  2. POST /api/mobile/telegram/webhook — Telegram webhook 模式（备用，用户自部署到云时可用）
  3. POST /api/mobile/bind — 桌面端生成绑定码（需登录）
  4. POST /api/mobile/test — 发送测试通知（需登录）
  5. POST /api/mobile/reload-polling — 配置变更后重启 polling（需登录）
  6. Telegram Long Polling 后台任务（startup 启动、shutdown 停止）
  7. 上行消息解析 + 动作白名单校验 + 二次确认 + 复用 chat.py
```

#### app/store.py（新增部分）

```
职责：
  1. mobile_active_contexts: dict[user_id → task_id]（会话锚点）
  2. load/save_mobile_session() — 持久化到 data/mobile_session.json
  3. mobile_pending_bindings: dict[code → (user_id, expires_at)]（一次性绑定码，10 分钟过期）
```

### 6.3 配置结构

`data/settings.json` 新增 `mobile_notification` 配置节：

```json
{
  "mobile_notification": {
    "enabled": false,
    "provider": "telegram",
    "telegram": {
      "bot_token": "",
      "polling_timeout_sec": 30,
      "retry_backoff_sec": [1, 5, 30]
    },
    "wecom_group": { "webhook_url": "" },
    "bark": { "server_url": "", "device_key": "" },
    "ntfy": { "server_url": "", "topic": "" },
    "generic_webhook": { "url": "", "method": "POST", "headers": {} },
    "events": {
      "recording_start": true,
      "recording_stop": true,
      "silence_warning": true,
      "silence_urgent": true,
      "auto_stop": true,
      "transcribe_complete": false,
      "summary_complete": false
    },
    "action_whitelist": {
      "write": [],
      "destructive": []
    },
    "rate_limit_sec": 60
  }
}
```

`data/users.json` 用户对象新增 `mobile_bindings` 字段（见 §3.4.4）。

### 6.4 对接现有模块

#### 6.4.1 与 record.py 静默检测对接

在 [`_silence_monitor_loop`](../../app/routers/record.py) 中，现有 `push_realtime_msg` 之后追加：

```python
# 现有代码（保留）
push_realtime_msg(task_id, {
    "type": "presence_warning",
    "level": "gentle",
    "silent_minutes": silent_minutes,
    "countdown_seconds": gentle_countdown,
})

# 新增：推送到手机（异步，不阻塞监测循环）
from core.notify import send_notification
await send_notification(
    task_id=task_id,
    event="silence_warning",
    level="gentle",
    i18n_key="mobile.event.silence_warning",
    context={"silent_minutes": silent_minutes},
)
```

#### 6.4.2 与 chat.py 上行对接

```python
# app/routers/mobile.py
from app.routers.chat import chat as chat_endpoint, ChatRequest, _detect_action
from core.users import set_request_user_id

async def handle_user_message(chat_id: str, provider: str, text: str) -> str:
    # 1. 鉴权：chat_id → user_id
    user_id = resolve_user_from_chat_id(chat_id, provider)
    if not user_id:
        return _("尚未绑定，请在桌面端设置页获取绑定码")

    # 2. 注入 ContextVar（关键：让 chat.py 内的 get_current_user 生效）
    set_request_user_id(user_id)
    try:
        # 3. 解析上行消息
        parsed = parse_inbound_message(text, user_id)

        # 4. 指令 or 对话
        if parsed["type"] == "command":
            return await handle_command(parsed, user_id)

        # 5. 动作白名单校验
        detected = _detect_action(parsed["content"])
        if detected and not is_action_allowed(detected.name, user_id):
            return _("此动作在移动端未启用，请在桌面端设置中开启")

        # 6. 破坏性动作需二次确认
        if detected and is_destructive(detected.name):
            return await request_confirmation(chat_id, detected, parsed)

        # 7. 复用 chat.py
        request = ChatRequest(
            message=parsed["content"],
            task_id=parsed.get("task_id"),
            mode="agent",
        )
        result = await chat_endpoint(request)
        reply = result["reply"]

        # 8. 长消息分片
        return split_long_message(reply, max_chars=3500)
    finally:
        set_request_user_id(None)  # 必须清理，避免 ContextVar 泄漏
```

### 6.5 异步边界与生命周期（v1.1.0 新增）

遵循 AGENTS.md 的 async/sync 约定：

| 函数 | 类型 | 理由 |
|------|------|------|
| `send_notification` | `async def` | 纯异步 HTTP（`httpx.AsyncClient`），不阻塞事件循环 |
| `format_message` | `def` | 纯字符串处理，无 I/O |
| `split_long_message` | `def` | 纯字符串处理 |
| `resolve_user_from_chat_id` | `def` | 读 `users.json` 是同步文件 I/O，量小可接受；若成瓶颈再改 `asyncio.to_thread` |
| `POST /api/mobile/inbound` | `async def` | 纯异步 I/O 端点 |
| `POST /api/mobile/test` | `async def` | 纯异步 I/O 端点 |
| `POST /api/mobile/bind` | `async def` | 纯异步 I/O 端点 |
| `telegram_polling_loop` | `async def` | 长期运行的异步任务 |

**Telegram Long Polling 生命周期**：

```python
# app/server.py
@app.on_event("startup")
async def startup():
    # 现有逻辑...

    # 新增：启动 Telegram polling（若已配置）
    from app.routers.mobile import start_telegram_polling
    await start_telegram_polling()


@app.on_event("shutdown")
async def shutdown():
    # 现有逻辑...

    # 新增：停止 polling
    from app.routers.mobile import stop_telegram_polling
    await stop_telegram_polling()
```

**Polling 任务要求**：
- **单实例约束**：同一 `bot_token` 只能有一个进程 poll，多实例会互相抢消息（本项目定位单机，需在部署文档警示）
- **配置热更新**：用户在设置页改 token 后，通过 `POST /api/mobile/reload-polling` 触发重启 polling 任务
- **异常恢复**：网络断开、Telegram 502 → 指数退避重试（1s / 5s / 30s）
- **失败计数**：连续 10 次失败 → 通过前端设置页红标提示「配置失效」

### 6.6 施工顺序

| 阶段 | 任务 | 预估 | 依赖 |
|------|------|------|------|
| **M0** | 设计补齐（本文档 v1.1.0） | 0.5 天 | 无 |
| M0.1 | 修正 ADR 编号、异步边界、多用户绑定、动作白名单 | — | — |
| **M1** | 端到端最小闭环（Telegram only） | 2 天 | M0 |
| M1.1 | `core/notify.py` + Telegram 适配器（含分片、限流） | — | — |
| M1.2 | `app/store.py` 新增 `mobile_active_contexts` / `mobile_pending_bindings` | — | — |
| M1.3 | `core/users.py` 数据结构补 `mobile_bindings` 字段（含迁移） | — | — |
| M1.4 | `record.py` 补 `owner_user_id` + 静默检测三阶段 + 录音开始/停止对接 notify | — | — |
| M1.5 | Telegram long polling 生命周期（startup/shutdown + 热重载） | — | — |
| M1.6 | 绑定码流程（桌面端生成 → Telegram `/bind` → users.json 写入） | — | — |
| M1.7 | 上行指令 `/list` `/status` `/switch` `/help` `/bind` `/unbind` | — | — |
| **M2** | 上行接入 chat + 动作白名单 | 1.5 天 | M1 |
| M2.1 | `mobile.py` 通用上行入口 + 鉴权 + ContextVar 注入/清理 | — | — |
| M2.2 | 动作白名单校验 + 破坏性动作二次确认（inline keyboard + nonce） | — | — |
| M2.3 | `@会议名` 解析（最长匹配 + 消歧） | — | — |
| M2.4 | 长消息分片发送 | — | — |
| M2.5 | i18n 消息模板（中英双语 `mobile.event.*` / `mobile.reply.*`） | — | — |
| **M3** | 前端配置页 | 2-3 天 | M1, M2 |
| M3.1 | 设置页「移动通知」配置区（遵循 IconButton 约束） | — | — |
| M3.2 | 通道选择 + 字段动态渲染 + Bot Token 脱敏显示（复用 `mask_api_key`） | — | — |
| M3.3 | 7 个事件独立开关 | — | — |
| M3.4 | 测试按钮 + 结果反馈 | — | — |
| M3.5 | Telegram 绑定引导（BotFather 创建 Bot 图文说明 + 绑定码 UI） | — | — |
| M3.6 | 动作白名单勾选界面 | — | — |
| **M4** | 其他通道适配（按需） | 0.5-1 天/通道 | M1 |
| M4.1 | 企业微信群机器人（纯下行，最简） | — | — |
| M4.2 | Bark (iOS) | — | — |
| M4.3 | ntfy | — | — |
| M4.4 | 通用 Webhook | — | — |
| **M5** | 测试 | 1 天 | M1-M3 |
| M5.1 | `test_mobile.py` 冒烟测试 | — | — |
| M5.2 | Telegram 端到端测试（真实 Bot） | — | — |
| M5.3 | 多用户串扰测试（两个 chat_id 分别绑定不同用户） | — | — |
| M5.4 | 动作白名单绕过测试 | — | — |

**总计约 7-9 天**（MVP 只做 Telegram；M4 按用户需求驱动）。

### 6.7 冒烟测试要点

```python
# tests/test_mobile.py

class TestNotify:
    """通知模块基础测试"""
    def test_format_message_includes_meeting_label(self): ...
    def test_format_message_uses_i18n(self): ...
    def test_split_long_message_respects_4096_limit(self): ...
    def test_rate_limiter_per_task_event_level(self): ...

class TestInboundParser:
    """上行解析"""
    def test_parse_at_prefix_longest_match(self): ...
    def test_parse_at_prefix_ambiguity_disambiguation(self): ...
    def test_parse_command_bind(self): ...
    def test_parse_plain_text_uses_anchor(self): ...
    def test_parse_plain_text_no_anchor(self): ...

class TestAuth:
    """鉴权"""
    def test_resolve_user_from_chat_id_success(self): ...
    def test_resolve_user_from_chat_id_unbound(self): ...
    def test_bind_code_expires_after_10min(self): ...
    def test_contextvar_cleanup_after_request(self): ...

class TestActionWhitelist:
    """动作白名单"""
    def test_readonly_action_allowed_by_default(self): ...
    def test_destructive_action_blocked_by_default(self): ...
    def test_destructive_action_requires_confirmation(self): ...

class TestEndpoint:
    """端点"""
    def test_inbound_empty_message_rejected(self): ...
    def test_test_endpoint_requires_login(self): ...
    def test_reload_polling_requires_login(self): ...
```

## 7. 安全考量

1. **凭证存储**：Bot Token / Webhook URL 存 `data/settings.json`，展示时用 [`mask_api_key`](../../app/store.py) 同款脱敏（前 3 位 + 后 4 位）
2. **日志脱敏**：`notify.py` 内所有日志禁止直接输出 `bot_token` / `webhook_url` / `chat_id`，用 `token[:6]+"..."` 形式
3. **绑定码**：一次性、10 分钟过期、用完即销毁；生成时用 `secrets.token_urlsafe` 而非 `random`
4. **上行鉴权**：`chat_id → user_id` 反查失败一律拒绝，不透露「该 chat_id 是否已注册」（防枚举）
5. **动作白名单**：破坏性动作默认关闭；启用后仍需二次确认（inline keyboard `callback_data` 需带 nonce 防重放）
6. **消息长度**：上行 ≤ 5000 字符（防注入）；下行按通道上限自动分片
7. **通知频率**：`(task_id, event, level)` 60 秒内不重复推送
8. **敏感信息过滤**：推送内容不含 API Key、绝对文件路径、`sk-*` 密钥模式
9. **Telegram 单实例**：同 `bot_token` 只能一个进程 poll，多实例部署会互抢消息（本项目定位单机，需在部署文档警示）
10. **ContextVar 清理**：`set_request_user_id` 注入后必须在 `finally` 块清理，避免连接池复用时状态泄漏

## 8. 后续演进

| 阶段 | 能力 | 条件 |
|------|------|------|
| v2 | 引流授权服务集成（License 校验、试用期共享 proxy） | [ADR-0015](../adr/0015-本地优先原则重定义与引流授权服务.md) 施工完成 |
| v2 | 同网络 PWA 直连 | 移动端面板需求明确后 |
| v3 | 语音输入随记 | 浏览器 Speech-to-Text / 录音上传 |
| v3 | 主服务云端部署指南（用户自持） | 用户跨设备访问需求驱动；解锁企业微信智能机器人回调能力 |
| v4 | 更多通道适配 | 用户反馈驱动 |
