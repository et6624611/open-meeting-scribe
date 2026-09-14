#!/bin/bash
# ASR 代理服务部署脚本
# 目标服务器：<your-server-ip>
# 用法：ssh root@<your-server-ip> 'bash -s' < deploy.sh

set -e

SERVICE_DIR="/opt/asr-proxy"
SERVICE_NAME="asr-proxy"

echo "=== ASR 代理服务部署 ==="

# 创建服务目录
mkdir -p "$SERVICE_DIR"
cd "$SERVICE_DIR"

# 复制文件（假设从项目根目录执行）
echo "复制服务文件..."
cp -r asr-proxy/* "$SERVICE_DIR/"

# 创建虚拟环境（如果不存在）
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

# 安装依赖
echo "安装依赖..."
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# 创建 .env（如果不存在）
if [ ! -f ".env" ]; then
    echo "创建 .env 配置文件..."
    cp .env.example .env
    echo "⚠️  请编辑 $SERVICE_DIR/.env 填入 DashScope API Key"
fi

# 创建 systemd 服务
echo "配置 systemd 服务..."
cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=ASR Proxy Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$SERVICE_DIR
Environment="PATH=$SERVICE_DIR/venv/bin"
ExecStart=$SERVICE_DIR/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8200
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 重载 systemd 并启动服务
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

echo ""
echo "=== 部署完成 ==="
echo "服务状态: systemctl status $SERVICE_NAME"
echo "查看日志: journalctl -u $SERVICE_NAME -f"
echo "健康检查: curl http://localhost:8200/health"
echo ""
echo "⚠️  重要：请编辑 $SERVICE_DIR/.env 填入以下配置："
echo "   - ASR_PROXY_TOKEN（与客户端一致）"
echo "   - DASHSCOPE_API_KEY（平台 DashScope Key）"
