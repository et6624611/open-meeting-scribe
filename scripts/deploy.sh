#!/bin/bash
# ============================================================
# Open Meeting Scribe — 云服务器一键部署脚本
# 目标系统：Ubuntu 24.04 LTS（2核4G）
# 用法：ssh root@<服务器IP> 'bash -s' < deploy.sh
# ============================================================

set -e

echo "=========================================="
echo "  Open Meeting Scribe — 云服务器部署"
echo "=========================================="

# ── 1. 系统更新 + 基础依赖 ──
echo ""
echo "[1/7] 安装系统依赖..."
apt update && apt upgrade -y
apt install -y \
    python3 python3-venv python3-pip \
    ffmpeg \
    git \
    curl \
    build-essential

# 验证 Python 版本
python3 --version
echo "✓ 系统依赖安装完成"

# ── 2. 创建项目目录 ──
echo ""
echo "[2/7] 创建项目目录..."
APP_DIR=/opt/meeting-scribe
mkdir -p $APP_DIR
cd $APP_DIR

# ── 3. 创建 Python 虚拟环境 ──
echo ""
echo "[3/7] 创建虚拟环境..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
echo "✓ 虚拟环境就绪"

# ── 4. 安装 Python 依赖 ──
echo ""
echo "[4/7] 安装 Python 依赖（首次较慢，约 2-3 分钟）..."
pip install -r requirements.txt
echo "✓ Python 依赖安装完成"

# ── 5. 创建数据目录 ──
echo ""
echo "[5/7] 创建数据目录..."
mkdir -p data/{output,uploads,recordings,tasks,project_index,usage}
echo "✓ 数据目录就绪"

# ── 6. 配置 systemd 服务（开机自启 + 崩溃重启） ──
echo ""
echo "[6/7] 配置系统服务..."

cat > /etc/systemd/system/meeting-scribe.service << 'EOF'
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
EOF

# 管理后台服务
cat > /etc/systemd/system/meeting-scribe-admin.service << 'EOF'
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
EOF

systemctl daemon-reload
echo "✓ 系统服务配置完成"

# ── 7. 防火墙 ──
echo ""
echo "[7/7] 配置防火墙..."
if command -v ufw &> /dev/null; then
    ufw allow 8000/tcp
    ufw allow 8001/tcp
    ufw allow 22/tcp
    ufw --force enable
    echo "✓ UFW 防火墙已放行 8000/8001 端口"
else
    echo "⚠ 未安装 UFW，请确保阿里云安全组已放行 8000/8001 端口"
fi

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "接下来需要做的："
echo "  1. 上传代码：scp -r ./* root@<服务器IP>:/opt/meeting-scribe/"
echo "  2. 配置密钥：在服务器上编辑 /opt/meeting-scribe/.env"
echo "  3. 启动服务："
echo "     systemctl start meeting-scribe"
echo "     systemctl enable meeting-scribe"
echo "  4. 访问：http://<服务器IP>:8000"
echo ""
