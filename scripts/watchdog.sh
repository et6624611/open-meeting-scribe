#!/bin/bash
# open-meeting-scribe 服务自动重启脚本
# 服务崩溃后自动重启，间隔 2 秒

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"

cd "$PROJECT_DIR"

#  stdin 自保险：启动终端被回收后 fd 0 会失效（revoked），
# 子进程将在解释器初始化阶段 EBADF 即死；统一重定向到 /dev/null
exec </dev/null

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 启动 watchdog..."

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 启动服务..."
    "$VENV_PYTHON" cli.py server --host 127.0.0.1 --port 8000 &
    server_pid=$!

    # 健康检查：进程"活着但不响应"（如被 SIGTTIN 挂起）时也能自愈
    fail=0
    while kill -0 "$server_pid" 2>/dev/null; do
        sleep 5
        if curl -s -m 3 -o /dev/null http://127.0.0.1:8000/; then
            fail=0
        else
            fail=$((fail + 1))
            if [ "$fail" -ge 3 ]; then
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] 健康检查连续 3 次失败，强杀服务 (pid=$server_pid)..."
                kill -9 "$server_pid" 2>/dev/null
                break
            fi
        fi
    done

    wait "$server_pid" 2>/dev/null
    exit_code=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 服务退出 (code=$exit_code)，2 秒后重启..."
    sleep 2
done
