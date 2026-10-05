# 认证与授权系统 — 技术设计文档

> 配套 ADR-0006。本文档描述具体实现方案，供开发参考。
>
> **定位说明**：本项目为个人开发者维护的开源软件，不提供商业订阅服务。下文「授权」指开发者对用户的使用权限管理，而非商业订阅关系。

## 目录

1. [API 服务模型](#api-服务模型)
2. [系统总览](#系统总览)
3. [个人认证：OAuth 2.0](#个人认证oauth-20)
4. [会话管理：JWT](#会话管理jwt)
5. [License Key 离线验证](#license-key-离线验证)
6. [功能门控](#功能门控)
7. [数据模型](#数据模型)
8. [API 设计](#api-设计)
9. [前端改造](#前端改造)
10. [环境变量与配置](#环境变量与配置)
11. [安全考量](#安全考量)
12. [你需要准备的资源](#你需要准备的资源)

---

## API 服务模型

### 双服务架构

系统将 AI 能力拆分为两个独立服务，各自拥有独立的 API Key 和配置。默认厂商为 DashScope（可替换为任意兼容 API）：

| 服务 | 职责 | 默认厂商 | 默认模型 |
|------|------|----------|----------|
| **ASR（语音转写）** | 录音转文字 | DashScope | paraformer-v2 |
| **LLM（纪要生成）** | AI 摘要与对话 | DashScope | qwen-plus |

### 三层话语体系

| 受众 | 话语 | 示例 |
|------|------|------|
| **普通用户** | 服务状态 | "语音转写服务已连接"、"纪要生成服务已连接" |
| **开发者** | 模型 | "DashScope Paraformer"、"qwen-plus" |
| **系统** | API | `asr.api_key`、`llm.base_url` |

三个层级不要混。设置页面对使用共享 proxy 的用户展示「开发者共享代理」状态，对自持 Key 用户展示完整的配置表单。

### 共享 proxy 用户 vs 自持 Key 用户

| | 共享 proxy 用户 | 自持 Key 用户 |
|---|---|---|
| **注册方式** | 国内手机号（SMS 验证） | 任意注册方式 |
| **ASR 服务** | 开发者共享代理，体验期内免费 | 用户自行配置 API Key |
| **LLM 服务** | 开发者共享代理，体验期内免费 | 用户自行配置 API Key |
| **功能范围** | 完整功能 | 完整功能（不阉割） |
| **费用承担** | 体验期内由开发者承担 | 用户自行承担 API 费用 |

**核心原则：功能不分级，资源分配策略分级。** 共享 proxy 用户默认走本地 MFCC 以节约开发者成本，自持 Key 用户可使用云端 CAM++（用户自担费用）。

### 体验期服务区域限制

体验期共享 proxy **仅限通过国内手机号（SMS）注册的用户**。GitHub OAuth 和本地账户用户需自行配置 API Key。

**原因**：
- 开发者 API Key 部署在国内云服务器，云端 AI 国内服务通常仅限中国大陆地区使用
- 境外用户通过共享 proxy 访问可能涉及服务区域限制与数据跨境合规问题
- 国内手机号 SMS 验证作为天然的地理屏障，无需额外的 IP 检测基础设施

**代码实现**：`core/metering.py` 的 `is_metered()` 检查 `user.provider == "sms"`，非 SMS 用户返回 `False`（不计量，需自持 Key）。

### 设置文件结构（v3）

```json
{
  "asr": {
    "provider": "DashScope",
    "base_url": "https://dashscope.aliyuncs.com",
    "api_key": "sk-...",
    "model": "paraformer-v2"
  },
  "llm": {
    "provider": "DashScope（通义千问）",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "sk-...",
    "model": "qwen-plus"
  },
  "output_dir": "data/output/"
}
```

---

## 系统总览

```
┌─────────────────────────────────────────────────────────┐
│                      前端 (index.html)                    │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐  │
│  │ 登录页面  │  │ 用户状态  │  │ 团队/License 管理页面  │  │
│  └──────────┘  └──────────┘  └───────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
                     HTTP / WebSocket
                          │
┌─────────────────────────────────────────────────────────┐
│                    FastAPI (app/server.py)                │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ auth router  │  │ license router│  │ 中间件        │  │
│  │ /auth/*      │  │ /license/*    │  │ auth_required │  │
│  └─────────────┘  └──────────────┘  │ license_gate  │  │
│                                      └───────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
              ┌───────────┼───────────┐
              │           │           │
        ┌─────▼─────┐ ┌──▼───┐ ┌────▼────┐
        │ core/auth  │ │core/ │ │core/    │
        │            │ │users │ │license  │
        └────────────┘ └──────┘ └─────────┘
              │           │           │
              └───────────┼───────────┘
                          │
              ┌───────────▼───────────┐
              │   data/*.json          │
              │   users.json           │
              │   licenses.json        │
              └────────────────────────┘
```

---

## 个人认证：OAuth 2.0

### 支持的 Provider

| Provider | OAuth 版本 | 授权端点 | Token 端点 | 用户信息端点 |
|----------|-----------|---------|-----------|-------------|
| GitHub | OAuth 2.0 | `https://github.com/login/oauth/authorize` | `https://github.com/login/oauth/access_token` | `https://api.github.com/user` |
| Google | OAuth 2.0 | `https://accounts.google.com/o/oauth2/v2/auth` | `https://oauth2.googleapis.com/token` | `https://www.googleapis.com/oauth2/v3/userinfo` |
| 微信 | OAuth 2.0 | `https://open.weixin.qq.com/connect/qrconnect` | `https://api.weixin.qq.com/sns/oauth2/access_token` | `https://api.weixin.qq.com/sns/userinfo` |

### 认证流程

```
1. 用户点击「GitHub 登录」
2. 前端跳转: GET /auth/github
3. 后端生成 state (CSRF 防护)，重定向到 GitHub 授权页
4. 用户在 GitHub 授权
5. GitHub 回调: GET /auth/callback?code=xxx&state=yyy
6. 后端验证 state，用 code 换 access_token
7. 用 access_token 拉取用户信息 (id, name, avatar, email)
8. 在 users.json 中查找/创建用户记录
9. 签发 JWT，设置 httpOnly cookie
10. 重定向到首页
```

### 核心代码结构

```python
# core/auth.py

class OAuthProvider:
    """OAuth 提供者基类"""
    def get_authorize_url(self, state: str) -> str: ...
    def exchange_code(self, code: str) -> dict: ...
    def fetch_user_info(self, token: str) -> dict: ...

class GitHubProvider(OAuthProvider): ...
class GoogleProvider(OAuthProvider): ...
class WeChatProvider(OAuthProvider): ...

def create_jwt(user_id: str, role: str) -> str: ...
def verify_jwt(token: str) -> dict | None: ...
```

---

## 会话管理：JWT

### Token 结构

```json
{
  "sub": "user-uuid",
  "name": "Yongliang Wang",
  "role": "personal",
  "team_id": null,
  "iat": 1725580800,
  "exp": 1726185600
}
```

### 配置

- **签名算法**：HS256（对称，足够安全）
- **密钥**：`JWT_SECRET` 环境变量（首次启动自动生成并写入 `.env`）
- **有效期**：7 天（可配置）
- **存储方式**：httpOnly cookie（`oms_session`），前端不直接操作

### 为什么不用 Session

- JWT 无状态，不需要服务端存储 session
- 适合未来扩展（多实例部署）
- 当前单实例 JSON 存储架构下，session 也可以，但 JWT 更灵活

---

## License Key 离线验证

### 密钥对

```bash
# 生成 Ed25519 密钥对（开发者执行一次）
python -c "
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

private_key = Ed25519PrivateKey.generate()
# 私钥 → 开发者保管，不发布
# 公钥 → 编译进软件
print('Private:', private_key.private_bytes_raw().hex())
print('Public:', private_key.public_key().public_bytes_raw().hex())
"
```

### License 生成（开发者工具，不随软件发布）

```python
# scripts/generate_license.py（开发者本地使用）

import json, base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def generate_license(
    private_key_hex: str,
    team_name: str,
    max_members: int,
    features: list[str],
    days_valid: int = 365
) -> str:
    """生成 License Key"""
    payload = {
        "tid": str(uuid.uuid4()),
        "name": team_name,
        "members": max_members,
        "features": features,
        "iat": int(time.time()),
        "exp": int(time.time()) + days_valid * 86400,
    }
    
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    
    # 签名
    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    signature = private_key.sign(payload_bytes)
    
    # 拼接 + 编码
    combined = payload_bytes + b"|" + base64.b64encode(signature)
    encoded = base64.b32encode(combined).decode()
    
    # 分段: OMSK-XXXXX-XXXXX-...
    chunks = [encoded[i:i+5] for i in range(0, len(encoded), 5)]
    return "OMSK-" + "-".join(chunks)
```

### License 验证（内置于软件）

```python
# core/license.py

PUBLIC_KEY_HEX = "..."  # 编译时写入

class LicenseInfo:
    team_name: str
    max_members: int
    features: list[str]
    expires_at: datetime
    
    @property
    def is_valid(self) -> bool: ...
    
    @property
    def is_expired(self) -> bool: ...

def verify_license(key: str) -> LicenseInfo | None:
    """
    验证 License Key。纯本地计算，不联网。
    
    1. 去除 "OMSK-" 前缀，合并分段
    2. Base32 解码
    3. 分离 payload 和 signature
    4. 用内置公钥验签
    5. 解析 payload，检查过期
    """
    ...

def get_current_license() -> LicenseInfo | None:
    """读取本机 License 状态"""
    ...
```

### License Key 格式示例

```
OMSK-JBSWY3DPEHPK3PXP-JBSWY3DPEHPK3PXP-JBSWY3DPEHPK3PXP-JBSWY3DPEHPK3PXP
```

---

## 功能门控

### 中间件设计

```python
# app/middleware/auth.py

async def auth_required(request: Request) -> dict:
    """验证 JWT，返回用户信息。未登录返回 401。"""
    token = request.cookies.get("oms_session")
    if not token:
        raise HTTPException(401, "未登录")
    user = verify_jwt(token)
    if not user:
        raise HTTPException(401, "登录已过期")
    return user

def require_feature(feature: str):
    """依赖注入：检查当前用户是否有某功能权限"""
    def checker(request: Request):
        user = await auth_required(request)
        # 体验期基础功能不需要额外授权
        if feature in PERSONAL_FEATURES:
            return user
        # 协作功能需要有效授权
        license = get_current_license()
        if not license or not license.is_valid:
            raise HTTPException(403, "需要协作授权")
        if feature not in license.features:
            raise HTTPException(403, f"当前授权不包含此功能: {feature}")
        return user
    return checker
```

### 功能分层表

```python
# 体验期免费功能（无需额外授权）
PERSONAL_FEATURES = {
    "transcribe",      # 录音转写
    "summary",         # AI 纪要
    "diarization",     # 说话人识别
    "voiceprint",      # 声纹识别
    "watermark",       # 水印/主题
    "hotwords",        # 热词
    "projects",        # 项目管理（单人）
    "chat",            # AI 对话
}

# 协作功能（需要授权）
TEAM_FEATURES = {
    "sharing",         # 项目共享
    "team_admin",      # 团队管理
    "team_analytics",  # 团队统计
    "member_invite",   # 邀请成员
}
```

---

## 数据模型

### users.json（扩展后）

```json
{
  "users": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "provider": "github",
      "provider_id": "12345678",
      "name": "Yongliang Wang",
      "avatar_url": "https://avatars.githubusercontent.com/u/12345678",
      "email": "user@example.com",
      "role": "personal",
      "team_id": null,
      "prefs": {
        "watermark_enabled": true,
        "watermark_density": 50,
        "theme_opacity": 100,
        "avatar_color": "#4A90D9"
      },
      "created_at": "2026-09-06T00:00:00Z",
      "last_login": "2026-09-06T12:00:00Z"
    }
  ],
  "speaker_bindings": {
    "<task_id>": {"<speaker_id>": "<speaker_uuid>"}
  }
}
```

### licenses.json

```json
{
  "license_key": "OMSK-XXXX-XXXX-XXXX-XXXX-XXXX",
  "team_name": "云端科技",
  "max_members": 10,
  "features": ["sharing", "team_admin", "team_analytics"],
  "issued_at": "2026-09-06T00:00:00Z",
  "expires_at": "2027-09-06T00:00:00Z",
  "verified": true
}
```

---

## API 设计

### 认证相关

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/auth/github` | 发起 GitHub OAuth | 无 |
| GET | `/auth/google` | 发起 Google OAuth | 无 |
| GET | `/auth/wechat` | 发起微信 OAuth | 无 |
| GET | `/auth/callback` | OAuth 回调 | 无 |
| POST | `/auth/logout` | 登出 | 需要 |
| GET | `/auth/me` | 获取当前用户信息 | 需要 |

### License 相关

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/license` | 查询当前 License 状态 | 需要 |
| POST | `/api/license/activate` | 激活 License Key | 需要 |
| DELETE | `/api/license` | 移除 License（降级为个人版） | 需要 |

### 需要改造的现有 API

现有 API 需要增加认证中间件。未登录用户返回 401。

```python
# 示例：tasks.py 增加认证
from app.middleware.auth import auth_required

@router.get("/api/tasks")
def list_tasks(request: Request):
    user = auth_required(request)  # 新增
    # ... 原有逻辑
```

---

## 前端改造

### 新增页面/组件

1. **登录页面**（未登录时显示）
   - 三个 OAuth 按钮：GitHub / Google / 微信
   - 简洁居中布局

2. **用户菜单**（右上角）
   - 显示头像 + 名称
   - 下拉：个人设置、团队管理、登出

3. **团队管理页面**（新功能入口）
   - License 状态卡片
   - 激活 License 输入框
   - 团队成员列表（第三期）

### 登录状态管理

```javascript
// 前端检查登录状态
async function checkAuth() {
  const res = await fetch('/auth/me');
  if (res.ok) {
    window.currentUser = await res.json();
    showMainUI();
  } else {
    showLoginUI();
  }
}
```

---

## 环境变量与配置

### .env 新增项

```bash
# ── OAuth 配置 ──
OAUTH_GITHUB_CLIENT_ID=
OAUTH_GITHUB_CLIENT_SECRET=
OAUTH_GOOGLE_CLIENT_ID=
OAUTH_GOOGLE_CLIENT_SECRET=
OAUTH_WECHAT_APP_ID=
OAUTH_WECHAT_APP_SECRET=

# ── JWT 配置 ──
JWT_SECRET=  # 首次启动自动生成

# ── License 公钥（编译时写入） ──
LICENSE_PUBLIC_KEY=  # Ed25519 公钥 hex

# ── 应用配置 ──
APP_URL=http://127.0.0.1:8000  # OAuth 回调需要
```

### OAuth 回调 URL 配置

在各平台注册应用时，需填写回调 URL：
- GitHub: `http://127.0.0.1:8000/auth/callback`
- Google: `http://127.0.0.1:8000/auth/callback`
- 微信: `http://127.0.0.1:8000/auth/callback`

> 注意：微信 OAuth 要求已备案域名，本地开发可用测试号或 ngrok。

---

## 安全考量

### 已覆盖

| 威胁 | 防护 |
|------|------|
| CSRF | OAuth state 参数 |
| Session 劫持 | httpOnly cookie + Secure flag |
| Token 伪造 | JWT 签名验证 |
| License 伪造 | Ed25519 签名，私钥不发布 |
| 密码泄露 | 不管理密码（纯 OAuth） |

### 需注意

| 风险 | 说明 | 缓解 |
|------|------|------|
| 私钥泄露 | License 私钥泄露可被伪造 | 私钥加密存储，不入库 |
| 无法远程吊销 | License 一旦签发无法撤销 | 可发布新版本更换公钥 |
| OAuth 平台故障 | 第三方不可用 | 支持多个 Provider，互为备份 |
| 本地数据泄露 | JSON 文件无加密 | 未来可引入加密存储 |

---

## 你需要准备的资源

### 必须（第一期）

| 资源 | 用途 | 获取方式 |
|------|------|---------|
| GitHub OAuth App | GitHub 登录 | [GitHub Settings](https://github.com/settings/developers) |
| Google OAuth Client | Google 登录 | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) |
| 微信开放平台应用 | 微信登录 | [微信开放平台](https://open.weixin.qq.com/)（需企业资质） |

### 可选（第二期）

| 资源 | 用途 | 获取方式 |
|------|------|--------|
| ~~微信支付商户号~~ | ~~团队版收款~~ | 已取消：本项目不提供商业订阅服务 |
| ~~支付宝商户号~~ | ~~团队版收款~~ | 已取消：本项目不提供商业订阅服务 |

### 我会帮你生成

| 资源 | 说明 |
|------|------|
| Ed25519 密钥对 | License 签名用 |
| JWT_SECRET | 会话签名用 |
| 代码实现 | 全部 Python + 前端代码 |

---

## 依赖新增

```
# requirements.txt 新增
cryptography>=41.0.0    # Ed25519 签名
PyJWT>=2.8.0            # JWT 处理
httpx>=0.25.0           # OAuth HTTP 请求（已有）
```

---

## 下一步

确认此方案后，按以下顺序实施：

1. **你去注册 OAuth 应用**（GitHub 最快，5 分钟搞定）
2. **我生成密钥对**（Ed25519 + JWT_SECRET）
3. **我写第一期代码**（OAuth 登录 + JWT 会话 + 用户数据扩展）
4. **测试通过后**，进入第二期（License 系统）
