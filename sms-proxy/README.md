# SMS 代理服务

持有阿里云 AccessKey，为客户端提供短信发送/核验中转服务。

**部署位置**：<your-server-ip>:8080

## 架构

```
客户端 (open-meeting-scribe)
    ↓ HTTP POST + HMAC-SHA256 签名
SMS 代理 (<your-server-ip>:8080)
    ↓ 阿里云 PNVS SDK
阿里云短信服务
```

## 安全机制

- 客户端请求须携带 `X-SMS-Timestamp` 和 `X-SMS-Sign` 头
- 签名 = HMAC-SHA256(token, timestamp)，token 为共享密钥
- timestamp 超过 TTL（默认 5 分钟）视为过期拒绝
- 常量时间比较，防时序攻击

## 部署

### 1. 准备配置

```bash
cd sms-proxy
cp .env.example .env
# 编辑 .env 填入：
#   - SMS_PROXY_TOKEN（与客户端一致）
#   - ALIBABA_CLOUD_ACCESS_KEY_ID
#   - ALIBABA_CLOUD_ACCESS_KEY_SECRET
```

### 2. 一键部署

```bash
# 从项目根目录执行
ssh root@<your-server-ip> 'bash -s' < sms-proxy/deploy.sh
```

### 3. 手动部署

```bash
# 登录服务器
ssh root@<your-server-ip>

# 创建服务目录
mkdir -p /opt/sms-proxy
cd /opt/sms-proxy

# 上传文件（从本地）
scp -r sms-proxy/* root@<your-server-ip>:/opt/sms-proxy/

# 创建虚拟环境并安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 配置 .env
cp .env.example .env
nano .env  # 填入配置

# 启动服务（测试）
uvicorn server:app --host 0.0.0.0 --port 8080

# 或配置为 systemd 服务（生产）
# 参考 deploy.sh 中的 systemd 配置
```

## API

### POST /sms/send

发送验证码短信。

**请求头**：
- `X-SMS-Timestamp`: Unix 时间戳（秒）
- `X-SMS-Sign`: HMAC-SHA256 签名

**请求体**：
```json
{"phone": "13800138000"}
```

**响应**：
```json
{"success": true, "expire_minutes": 5}
```

### POST /sms/verify

核验验证码。

**请求头**：同上

**请求体**：
```json
{"phone": "13800138000", "code": "123456"}
```

**响应**：
```json
{"success": true}
```

### GET /health

健康检查。

**响应**：
```json
{"status": "ok", "service": "sms-proxy"}
```

## 运维

```bash
# 查看服务状态
systemctl status sms-proxy

# 查看日志
journalctl -u sms-proxy -f

# 重启服务
systemctl restart sms-proxy

# 停止服务
systemctl stop sms-proxy
```

## 文件结构

```
sms-proxy/
├── server.py          # 主程序
├── requirements.txt   # Python 依赖
├── .env.example       # 环境变量模板
├── deploy.sh          # 部署脚本
└── README.md          # 本文档
```
