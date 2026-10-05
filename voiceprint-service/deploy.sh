#!/bin/bash
# ============================================================
# deploy.sh — 声纹服务一键部署脚本
#
# 用法：
#   在云服务器上执行：bash deploy.sh
#
# 前提：
#   - Ubuntu/Debian 系统
#   - Python 3.11+ 已安装（apt install python3.11 python3.11-venv）
#   - 以 root 或 sudo 执行
# ============================================================

set -euo pipefail

SERVICE_NAME="voiceprint-service"
SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${SERVICE_DIR}/venv"
USER="${VOICEPRINT_USER:-voiceprint}"

echo "=========================================="
echo " 声纹嵌入提取服务 — 部署"
echo "=========================================="

# ── 1. 创建运行用户 ──
if ! id -u "$USER" &>/dev/null; then
    echo "[1/6] 创建用户: $USER"
    useradd -r -s /bin/false -d "$SERVICE_DIR" "$USER"
else
    echo "[1/6] 用户 $USER 已存在，跳过"
fi

# ── 2. 创建虚拟环境 ──
if [ ! -d "$VENV_DIR" ]; then
    echo "[2/6] 创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
else
    echo "[2/6] 虚拟环境已存在，跳过"
fi

# ── 3. 安装依赖（CPU-only torch）──
echo "[3/6] 安装依赖（CPU-only torch）..."
"${VENV_DIR}/bin/pip" install --upgrade pip -q
# 先装 CPU-only torch（避免拉 CUDA 版本）
"${VENV_DIR}/bin/pip" install torch torchaudio --index-url https://download.pytorch.org/whl/cpu -q
# 再装其余依赖
"${VENV_DIR}/bin/pip" install -r "${SERVICE_DIR}/requirements.txt" -q

# ── 4. 配置环境变量 ──
if [ ! -f "${SERVICE_DIR}/.env" ]; then
    echo "[4/6] 创建 .env 配置文件..."
    cp "${SERVICE_DIR}/.env.example" "${SERVICE_DIR}/.env"
    echo "  ⚠ 请编辑 ${SERVICE_DIR}/.env 填入 VOICEPRINT_API_KEY"
else
    echo "[4/6] .env 已存在，跳过"
fi

# ── 5. 安装 systemd 服务 ──
echo "[5/6] 安装 systemd 服务..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=声纹嵌入提取服务（CAM++ Cloud）
After=network.target

[Service]
Type=simple
User=${USER}
Group=${USER}
WorkingDirectory=${SERVICE_DIR}
EnvironmentFile=${SERVICE_DIR}/.env
ExecStart=${VENV_DIR}/bin/python run.py --host 0.0.0.0 --port 8100 --workers 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# 安全加固
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=${SERVICE_DIR}
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# ── 6. 验证 ──
echo "[6/6] 等待服务启动..."
sleep 3

if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo ""
    echo "=========================================="
    echo " ✓ 部署成功！"
    echo "=========================================="
    echo ""
    echo " 服务状态:  systemctl status $SERVICE_NAME"
    echo " 查看日志:  journalctl -u $SERVICE_NAME -f"
    echo " 健康检查:  curl http://localhost:8100/health"
    echo ""
    echo " 客户端配置："
    echo "   VOICEPRINT_BASE_URL=http://<服务器IP>:8100/api/v1"
    echo "   VOICEPRINT_API_KEY=<.env 中设置的值>"
    echo ""
else
    echo ""
    echo " ✗ 服务启动失败，请检查日志："
    echo "   journalctl -u $SERVICE_NAME -n 50 --no-pager"
    echo ""
    systemctl status "$SERVICE_NAME" --no-pager
    exit 1
fi
