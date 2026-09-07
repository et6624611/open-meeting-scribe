# DEPLOYMENT — 云服务器部署与运维

> 云服务器操作信息的唯一事实源。服务器变更先更新这里。

## 一、服务器信息

| 项目 | 值 |
|------|-----|
| 服务商 | 阿里云轻量应用服务器 |
| 规格 | 通用型 2 vCPU / 4 GiB / 50 GiB 系统盘 |
| 系统 | Ubuntu 24.04 LTS |
| 公网 IP | `47.116.10.194` |
| 地域 | 华东（上海） |
| SSH 用户 | root（密码认证） |
| 项目目录 | `/opt/meeting-scribe` |
| Python | 3.12（系统自带） + venv |

## 二、服务端口

| 服务 | 端口 | 用途 | 开机自启 |
|------|------|------|----------|
| Web UI + API | 8000 | 用户访问界面 + REST/WS API | ✅ |
| 管理后台 | 8001 | 运维管理面板 | ✅ |

### 防火墙规则（阿里云控制台 → 实例 → 防火墙）

| 协议 | 端口 | 用途 |
|------|------|------|
| TCP | 8000 | Web 服务 |
| TCP | 8001 | 管理后台 |
| TCP | 22 | SSH（默认已开） |

## 三、访问地址

- Web UI 👉 **http://47.116.10.194:8000**
- 管理后台 👉 **http://47.116.10.194:8001**

## 四、SSH 连接

```bash
# 本地连接（密码在 .env 或口头传达，不写入文件）
ssh root@47.116.10.194
```

## 五、服务管理

```bash
# ── Web 服务 ──
systemctl status meeting-scribe       # 查看状态
systemctl restart meeting-scribe      # 重启
systemctl stop meeting-scribe         # 停止
journalctl -u meeting-scribe -f       # 实时日志

# ── 管理后台 ──
systemctl status meeting-scribe-admin # 查看状态
systemctl restart meeting-scribe-admin
journalctl -u meeting-scribe-admin -f

# ── 通用 ──
systemctl daemon-reload               # 修改 service 文件后重载
```

## 六、代码更新流程

本地改完代码后，推送到服务器：

```bash
# 1. 打包（排除缓存/数据/虚拟环境）
cd <项目根目录>
tar czf /tmp/meeting-scribe-src.tar.gz \
  --exclude='__pycache__' --exclude='venv' --exclude='data' \
  --exclude='logs' --exclude='.qoder' --exclude='*.png' \
  --exclude='samples' --exclude='docs' --exclude='tests' \
  --exclude='.pytest_cache' --exclude='scripts/_ssh*' \
  app core cli.py requirements.txt .env .env.example

# 2. 上传
scp /tmp/meeting-scribe-src.tar.gz root@47.116.10.194:/tmp/

# 3. 服务器端解压 + 重启（主服务 + 管理后台）
ssh root@47.116.10.194
cd /opt/meeting-scribe
tar xzf /tmp/meeting-scribe-src.tar.gz
systemctl restart meeting-scribe
systemctl restart meeting-scribe-admin
```

## 七、API 调用路径

本地开发与云服务器**各自独立调用 DashScope API**，互不影响：

```
本地开发:  本机(127.0.0.1:8000) ──公网──→ DashScope API
云服务器:  47.116.10.194:8000   ──公网──→ DashScope API
```

- 代码在哪台机器运行，API 就从哪台机器发出
- 两套环境用同一个 `.env` 中的 `DASHSCOPE_API_KEY`，同一个阿里云账号计费
- 浏览器只是前端，音频 POST 给服务器后由服务器调 DashScope

## 八、systemd 服务文件

### meeting-scribe.service

```ini
[Unit]
Description=Open Meeting Scribe Web Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/meeting-scribe
Environment=PATH=/opt/meeting-scribe/venv/bin:/usr/bin:/bin
ExecStart=/opt/meeting-scribe/venv/bin/python cli.py server --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### meeting-scribe-admin.service

```ini
[Unit]
Description=Open Meeting Scribe Admin Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/meeting-scribe
Environment=PATH=/opt/meeting-scribe/venv/bin:/usr/bin:/bin
ExecStart=/opt/meeting-scribe/venv/bin/python cli.py admin --host 0.0.0.0 --port 8001
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## 九、部署历史

| 日期 | 操作 |
|------|------|
| 2026-09-06 | 首次部署：Ubuntu 24.04 重置 + 系统依赖 + venv + pip install + systemd 服务 + 防火墙放行 |
