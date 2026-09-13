#!/usr/bin/env python3
"""
cli.py — Open Meeting Scribe 命令行助手

作者：王永亮
创建：2026-09-03
版本：1.0.0

用法：
    python cli.py transcribe <音频文件>     # 转写 + 生成纪要
    python cli.py normalize <音频文件>      # 仅归一化音频
    python cli.py upload <音频文件>         # 仅上传（测试用）
    python cli.py server                    # 启动 Web UI 服务

    # 录音控制（需服务运行中）
    python cli.py record start              # 开始录音
    python cli.py record stop               # 停止录音
    python cli.py record pause              # 暂停录音
    python cli.py record resume             # 恢复录音
    python cli.py record status             # 查看录音状态

    # 任务管理
    python cli.py tasks list                # 列出所有任务
    python cli.py tasks show <task_id>      # 查看任务详情
    python cli.py tasks delete <task_id>    # 删除任务

    # 说话人管理
    python cli.py speakers list             # 列出所有说话人
    python cli.py speakers add <姓名>       # 添加说话人

    # 热词管理
    python cli.py hotwords list             # 列出热词
    python cli.py hotwords add <词> [<词>...]  # 添加热词

    # 设置管理
    python cli.py settings show             # 查看设置
    python cli.py settings set <键> <值>    # 修改设置

    # AI 对话
    python cli.py chat <消息>               # 发送消息给 AI 助手

示例：
    python cli.py transcribe samples/会议.mp3
    python cli.py transcribe samples/会议.mp3 -o output/纪要.md
    python cli.py record start
    python cli.py tasks list
    python cli.py chat "提取待办事项"
"""

import argparse
import logging
import sys
from pathlib import Path

# 加载环境变量
from dotenv import load_dotenv

load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# 转写命令
# ============================================================

def cmd_transcribe(args):
    """转写 + 生成纪要"""
    from core.pipeline import PipelineProgress, run_pipeline

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"错误: 文件不存在 {audio_path}")
        return 1

    output_path = Path(args.output) if args.output else None

    def on_progress(p: PipelineProgress):
        if p.percent >= 0:
            print(f"[{p.percent:3d}%] {p.message}")
        else:
            print(f"[错误] {p.message}")

    print(f"开始处理: {audio_path}")
    print("-" * 50)

    try:
        result = run_pipeline(
            audio_path=audio_path,
            output_path=output_path,
            on_progress=on_progress,
        )

        print("-" * 50)
        print("✓ 完成！")
        print(f"  音频时长: {result['audio_duration']:.1f} 秒")
        print(f"  说话人: {len(result['dialogue'])} 位")
        print(f"  纪要: {result['output_path']}")

        if args.show:
            print("\n" + "=" * 50)
            print("纪要内容：")
            print("=" * 50)
            print(result["summary"])

        return 0

    except Exception as e:
        print(f"\n处理失败: {e}")
        logger.exception("管线执行异常")
        return 1


def cmd_normalize(args):
    """仅归一化音频"""
    from core.audio import get_audio_duration, normalize_audio

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"错误: 文件不存在 {audio_path}")
        return 1

    try:
        output = normalize_audio(audio_path)
        duration = get_audio_duration(output)
        size_mb = output.stat().st_size / 1024 / 1024

        print("归一化完成:")
        print(f"  输出: {output}")
        print(f"  时长: {duration:.1f} 秒")
        print(f"  大小: {size_mb:.1f} MB")
        return 0

    except Exception as e:
        print(f"归一化失败: {e}")
        return 1


def cmd_upload(args):
    """仅上传音频（测试用）"""
    from core.audio import normalize_audio
    from core.upload import upload_file

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"错误: 文件不存在 {audio_path}")
        return 1

    try:
        # 先归一化
        print("归一化音频...")
        normalized = normalize_audio(audio_path)

        # 上传
        print("上传到 DashScope...")
        oss_url = upload_file(normalized)
        print(f"上传成功: {oss_url}")
        return 0

    except Exception as e:
        print(f"上传失败: {e}")
        return 1


def cmd_server(args):
    """启动 Web UI 服务"""
    import uvicorn

    host = args.host
    port = args.port
    reload = args.reload

    print(f"启动服务: http://{host}:{port}")
    print("按 Ctrl+C 停止")

    uvicorn.run(
        "app.server:app",
        host=host,
        port=port,
        reload=reload,
    )
    return 0


def cmd_build(args):
    """构建前端（Vue 3 + Vite）并部署到 app/static/"""
    import shutil
    import subprocess

    frontend_dir = Path(__file__).parent / "frontend"
    static_dir = Path(__file__).parent / "app" / "static"
    if not frontend_dir.exists():
        print("错误: frontend/ 目录不存在")
        return 1

    # 检查 node_modules
    if not (frontend_dir / "node_modules").exists():
        print("安装前端依赖...")
        result = subprocess.run(["npm", "install"], cwd=frontend_dir)
        if result.returncode != 0:
            print("错误: npm install 失败")
            return 1

    print("构建前端...")
    result = subprocess.run(["npm", "run", "build"], cwd=frontend_dir)
    if result.returncode != 0:
        print("错误: 构建失败")
        return 1

    dist_dir = frontend_dir / "dist"
    if not dist_dir.exists():
        print("错误: 构建产物目录 frontend/dist/ 不存在")
        return 1

    # 部署到 app/static/
    print("部署到 app/static/...")
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        shutil.rmtree(assets_dir)
    shutil.copytree(dist_dir / "assets", assets_dir)
    shutil.copy2(dist_dir / "index.html", static_dir / "index.html")

    print(f"✓ 构建并部署完成: {static_dir}")
    print("  刷新浏览器即可使用新版前端（Ctrl+Shift+R 强刷）")
    return 0


def cmd_admin(args):
    """启动管理后台"""
    import uvicorn

    host = args.host
    port = args.port
    reload = args.reload

    print(f"启动管理后台: http://{host}:{port}")
    print("按 Ctrl+C 停止")

    uvicorn.run(
        "app.admin_server:admin_app",
        host=host,
        port=port,
        reload=reload,
    )
    return 0


def cmd_app(args):
    """启动桌面应用（原生窗口模式）"""
    from desktop import main as desktop_main

    host = args.host
    port = args.port

    print(f"启动桌面应用: http://{host}:{port}")
    print("关闭窗口即可退出")

    return desktop_main(host=host, port=port)


# ============================================================
# 主入口
# ============================================================

# 远程 API 命令组名称（用于帮助提示）
_REMOTE_COMMAND_GROUPS = ("record", "tasks", "speakers", "hotwords", "settings")


def main():
    parser = argparse.ArgumentParser(
        description="Open Meeting Scribe — 会议助手命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # ── transcribe 命令 ──
    p_transcribe = subparsers.add_parser("transcribe", help="转写音频 + 生成纪要")
    p_transcribe.add_argument("audio", help="音频文件路径")
    p_transcribe.add_argument("-o", "--output", help="输出纪要路径")
    p_transcribe.add_argument("--show", action="store_true", help="显示纪要内容")
    p_transcribe.set_defaults(func=cmd_transcribe)

    # ── normalize 命令 ──
    p_normalize = subparsers.add_parser("normalize", help="归一化音频（16kHz/单声道）")
    p_normalize.add_argument("audio", help="音频文件路径")
    p_normalize.set_defaults(func=cmd_normalize)

    # ── upload 命令 ──
    p_upload = subparsers.add_parser("upload", help="上传音频到 DashScope（测试用）")
    p_upload.add_argument("audio", help="音频文件路径")
    p_upload.set_defaults(func=cmd_upload)

    # ── server 命令 ──
    p_server = subparsers.add_parser("server", help="启动 Web UI 服务")
    p_server.add_argument("--host", default="127.0.0.1", help="监听地址")
    p_server.add_argument("--port", type=int, default=8000, help="监听端口")
    p_server.add_argument("--reload", action="store_true", help="开发模式（自动重载）")
    p_server.set_defaults(func=cmd_server)

    # ── build 命令 ──
    p_build = subparsers.add_parser("build", help="构建前端（Vue 3 + Vite）")
    p_build.set_defaults(func=cmd_build)

    # ── admin 命令 ──
    p_admin = subparsers.add_parser("admin", help="启动管理后台")
    p_admin.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    p_admin.add_argument("--port", type=int, default=8001, help="监听端口（默认 8001）")
    p_admin.add_argument("--reload", action="store_true", help="开发模式（自动重载）")
    p_admin.set_defaults(func=cmd_admin)

    # ── app 命令（桌面应用模式） ──
    p_app = subparsers.add_parser("app", help="启动桌面应用（原生窗口）")
    p_app.add_argument("--host", default="127.0.0.1", help="服务地址（默认 127.0.0.1）")
    p_app.add_argument("--port", type=int, default=8000, help="服务端口（默认 8000）")
    p_app.set_defaults(func=cmd_app)

    # ── 注册远程 API 命令（录音/任务/说话人/热词/设置/对话） ──
    from cli_remote import register_remote_commands
    register_remote_commands(subparsers)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # 对于远程子命令组，检查是否指定了具体操作
    if args.command in _REMOTE_COMMAND_GROUPS:
        sub_command = getattr(args, f"{args.command}_command", None)
        if not sub_command:
            # 打印子命令帮助
            for action in parser._subparsers._actions:
                if hasattr(action, '_name_parser_map') and args.command in action._name_parser_map:
                    action._name_parser_map[args.command].print_help()
                    break
            return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
