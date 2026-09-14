#!/bin/bash
# launcher_macos.sh — Open Meeting Scribe macOS 启动器
# 将 ffmpeg 加入 PATH 后启动应用
#
# 用法：双击「启动会议助手.command」或在终端执行

set -e

# 切换到脚本所在目录（即分发物根目录）
cd "$(dirname "$0")"

echo "═══════════════════════════════════════"
echo "  Open Meeting Scribe — 启动中..."
echo "═══════════════════════════════════════"
echo

# 检查 .env 是否存在
if [ ! -f ".env" ]; then
    echo "[警告] 未找到 .env 配置文件"
    echo "请复制 .env.example 为 .env 并填入 DashScope API Key"
    echo
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "已自动从模板创建 .env，请编辑后重新启动"
        open -t .env
        exit 1
    fi
fi

# 检查 ffmpeg
FFMPEG_DIR="./ffmpeg"
if [ -d "$FFMPEG_DIR" ] && [ -x "$FFMPEG_DIR/ffmpeg" ]; then
    export PATH="$FFMPEG_DIR:$PATH"
    echo "[OK] ffmpeg 已加载"
else
    # 也检查系统 PATH 中是否有 ffmpeg
    if command -v ffmpeg &>/dev/null; then
        echo "[OK] 使用系统 ffmpeg"
    else
        echo "[警告] 未找到 ffmpeg，音频归一化和录音功能不可用"
    fi
fi

# 检查 .app 是否存在
APP_PATH="./OpenMeetingScribe.app"
if [ ! -d "$APP_PATH" ]; then
    echo "[错误] 未找到 OpenMeetingScribe.app"
    echo "请确保应用文件完整"
    exit 1
fi

echo
echo "启动桌面应用..."
echo

# 打开 .app 包
open "$APP_PATH"
