@echo off
chcp 65001 >nul 2>&1
title 会议助手

echo ════════════════════════════════════════
echo   会议助手 — 启动中...
echo ════════════════════════════════════════
echo.

:: 检查 .env 是否存在
if not exist ".env" (
    echo [警告] 未找到 .env 配置文件
    echo 请复制 .env.example 为 .env 并填入 DashScope API Key
    echo.
    if exist ".env.example" (
        copy .env.example .env >nul
        echo 已自动从模板创建 .env，请编辑后重新启动
        notepad .env
        exit /b 1
    )
)

:: 检查 ffmpeg
set FFMPEG_DIR=%~dp0ffmpeg
if exist "%FFMPEG_DIR%\ffmpeg.exe" (
    set PATH=%FFMPEG_DIR%;%PATH%
    echo [OK] ffmpeg 已加载
) else (
    echo [警告] 未找到 ffmpeg，音频归一化功能不可用
)

:: 启动服务
echo.
echo 启动服务：http://127.0.0.1:8000
echo 按 Ctrl+C 停止服务
echo.

:: 延迟打开浏览器（等待服务启动）
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8000"

:: 运行主程序
MeetingScribe.exe server

echo.
echo 服务已停止
pause
