---
title: 部署指南
description: Open Meeting Scribe 云服务器部署参考，适用于自建实例或订阅服务运维。
tags: ["deployment", "server", "systemd", "运维"]
created_at: "2026-09-06"
updated_at: "2026-09-10"
version: "2.0.0"
---

# DEPLOYMENT — 云服务器部署指南

> 本文档提供通用的云服务器部署参考，不含任何特定实例的地址或凭据。

## 一、服务器要求

| 项目 | 最低要求 |
|------|----------|
| 系统 | Ubuntu 22.04+ / Debian 12+ |
| 规格 | 2 vCPU / 4 GiB RAM / 50 GiB 磁盘 |
| Python | 3.11+（推荐 3.12） |
| 网络 | 公网 IP（用于 Web 服务 + 代理中转） |

## 二、服务架构

```
客户端 ──HTTP/WS──→ Web UI + API (:8000)
                  → 管理后台 (:8001)
                  → ASR 代理 (:8200) ──→ DashScope API
                  → 声纹服务 (:8100)
                  → SMS 代理 (:8080) ──→ 阿里云短信
```

| 服务 | 端口 | 用途 |
|------|------|------|
| Web UI + API | 8000 | 用户访问界面 + REST/WS API |
| 管理后台 | 8001 | 运维管理面板 |
| SMS 代理 | 8080 | 短信发送/核验中转 |
| 声纹服务 | 8100 | CAM++ 声纹嵌入提取 |
| ASR 代理 | 8200 | 语音转写中转（持有 DashScope Key） |

## 三、安装步骤

### 3.1 系统依赖

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip ffmpeg
```

### 3.2 项目部署

```bash
# 克隆仓库
git clone https://github.com/your-org/open-meeting-scribe.git
cd open-meeting-scribe

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 API Key 和配置
```

### 3.3 构建前端

```bash
cd frontend
npm install
npm run build
cd ..
```

## 四、systemd 服务配置

### meeting-scribe.service

```ini
[Unit]
Description=Open Meeting Scribe Web Service
After=network.target

[Service]
Type=simple
User=www-data
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
User=www-data
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

### asr-proxy.service

```ini
[Unit]
Description=ASR Proxy Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/asr-proxy
Environment=PATH=/opt/asr-proxy/venv/bin:/usr/bin:/bin
ExecStart=/opt/asr-proxy/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8200
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 启用服务

```bash
sudo cp meeting-scribe.service meeting-scribe-admin.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now meeting-scribe meeting-scribe-admin
```

## 五、防火墙配置

根据你的云服务商控制台或 `ufw` 放行对应端口：

```bash
sudo ufw allow 8000/tcp  # Web 服务
sudo ufw allow 8001/tcp  # 管理后台
sudo ufw allow 8080/tcp  # SMS 代理
sudo ufw allow 8100/tcp  # 声纹服务
sudo ufw allow 8200/tcp  # ASR 代理
sudo ufw allow 22/tcp    # SSH
sudo ufw enable
```

## 六、代码更新

```bash
# 1. 拉取最新代码
cd /opt/meeting-scribe
git pull origin main

# 2. 更新依赖
source venv/bin/activate
pip install -r requirements.txt

# 3. 重建前端（如有变更）
cd frontend && npm install && npm run build && cd ..

# 4. 重启服务
sudo systemctl restart meeting-scribe meeting-scribe-admin
```

## 七、服务管理

```bash
# 查看状态
systemctl status meeting-scribe
systemctl status meeting-scribe-admin

# 重启
systemctl restart meeting-scribe

# 查看实时日志
journalctl -u meeting-scribe -f
```

## 八、安全建议

1. **使用非 root 用户运行服务**（上述示例使用 `www-data`）
2. **SSH 禁用密码认证**，改用密钥登录
3. **定期轮换 API Key**（DashScope、阿里云 AccessKey）
4. **启用 HTTPS**（通过 Nginx 反向代理 + Let's Encrypt）
5. **设置强管理员密码**（`ADMIN_PASSWORD` 环境变量）
