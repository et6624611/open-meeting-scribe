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

import sys
import json
import argparse
import logging
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

# 默认服务地址
DEFAULT_SERVER = "http://127.0.0.1:8000"


def _api_request(method: str, path: str, data: dict | None = None, files: dict | None = None) -> dict:
    """发送 HTTP 请求到本地服务"""
    import requests
    url = f"{DEFAULT_SERVER}{path}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=10)
        elif method == "POST":
            if files:
                resp = requests.post(url, data=data, files=files, timeout=300)
            else:
                resp = requests.post(url, json=data, timeout=30)
        elif method == "PUT":
            resp = requests.put(url, json=data, timeout=10)
        elif method == "DELETE":
            resp = requests.delete(url, timeout=10)
        else:
            raise ValueError(f"不支持的 HTTP 方法: {method}")

        if resp.status_code >= 400:
            try:
                err = resp.json()
                raise RuntimeError(err.get("detail", f"HTTP {resp.status_code}"))
            except json.JSONDecodeError:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

        return resp.json()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(f"无法连接到服务 {DEFAULT_SERVER}，请先运行 `python cli.py server`")


# ============================================================
# 转写命令
# ============================================================

def cmd_transcribe(args):
    """转写 + 生成纪要"""
    from core.pipeline import run_pipeline, PipelineProgress

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
    from core.audio import normalize_audio, get_audio_duration

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
    from app.server import app

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
    """构建前端（Vue 3 + Vite）"""
    import subprocess

    frontend_dir = Path(__file__).parent / "frontend"
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
    if dist_dir.exists():
        print(f"✓ 构建完成: {dist_dir}")
        print("  启动服务后将自动使用新版前端")
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


# ============================================================
# 录音控制命令
# ============================================================

def cmd_record_start(args):
    """开始录音"""
    try:
        result = _api_request("POST", "/api/record/start")
        print("✓ 录音已开始")
        print(f"  任务 ID: {result['task_id']}")
        print(f"  状态: {result['status']}")
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


def cmd_record_stop(args):
    """停止录音"""
    try:
        result = _api_request("POST", "/api/record/stop")
        print("✓ 录音已停止")
        if result.get("task_id"):
            print(f"  任务 ID: {result['task_id']}")
        if result.get("duration"):
            print(f"  时长: {result['duration']:.1f} 秒")
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


def cmd_record_pause(args):
    """暂停录音"""
    try:
        _api_request("POST", "/api/record/pause")
        print("✓ 录音已暂停")
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


def cmd_record_resume(args):
    """恢复录音"""
    try:
        _api_request("POST", "/api/record/resume")
        print("✓ 录音已恢复")
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


def cmd_record_status(args):
    """查看录音状态"""
    try:
        result = _api_request("GET", "/api/record/status")
        if result.get("recording"):
            print("录制状态: 进行中")
            print(f"  设备: {result.get('device', '未知')}")
            print(f"  时长: {result.get('duration', 0):.1f} 秒")
            if result.get("task_id"):
                print(f"  任务 ID: {result['task_id']}")
        else:
            print("录制状态: 未录制")
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


# ============================================================
# 任务管理命令
# ============================================================

def cmd_tasks_list(args):
    """列出所有任务"""
    try:
        result = _api_request("GET", "/api/tasks")
        tasks = result.get("tasks", [])
        if not tasks:
            print("暂无任务")
            return 0

        print(f"共 {len(tasks)} 个任务：\n")
        for t in tasks:
            status_map = {
                "recording": " 录制中",
                "pending": " 待处理",
                "processing": " 处理中",
                "completed": " 已完成",
                "failed": " 失败",
            }
            status = status_map.get(t.get("status", ""), t.get("status", ""))
            title = t.get("title") or t.get("audio_name") or "未命名"
            created = t.get("created_at", "")[:16]
            print(f"  {title}")
            print(f"    ID: {t['task_id'][:12]}...  状态: {status}  创建: {created}")
            if t.get("audio_duration"):
                print(f"    时长: {t['audio_duration']:.1f} 秒")
            print()
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


def cmd_tasks_show(args):
    """查看任务详情"""
    try:
        result = _api_request("GET", f"/api/tasks/{args.task_id}")
        print(f"任务详情: {args.task_id}\n")
        print(f"  标题: {result.get('title') or result.get('audio_name') or '未命名'}")
        print(f"  状态: {result.get('status')}")
        print(f"  创建: {result.get('created_at')}")
        if result.get("audio_duration"):
            print(f"  时长: {result['audio_duration']:.1f} 秒")
        if result.get("speaker_count"):
            print(f"  说话人: {result['speaker_count']} 位")
        if result.get("summary"):
            print(f"\n纪要内容:\n{'─' * 40}")
            print(result["summary"][:2000])
            if len(result["summary"]) > 2000:
                print(f"\n... (共 {len(result['summary'])} 字)")
        if result.get("todos"):
            print(f"\n待办事项 ({len(result['todos'])} 条):")
            for todo in result["todos"]:
                done = "x" if todo.get("done") else " "
                print(f"  [{done}] {todo['text']}")
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


def cmd_tasks_delete(args):
    """删除任务"""
    try:
        _api_request("DELETE", f"/api/tasks/{args.task_id}")
        print(f"✓ 任务 {args.task_id} 已删除")
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


# ============================================================
# 说话人管理命令
# ============================================================

def cmd_speakers_list(args):
    """列出所有说话人"""
    from core import speakers
    speaker_list = speakers.load_speakers()
    if not speaker_list:
        print("暂无说话人")
        return 0

    print(f"共 {len(speaker_list)} 位说话人：\n")
    for s in speaker_list:
        print(f"  {s.name}")
        if s.role:
            print(f"    角色: {s.role}")
        if s.note:
            print(f"    备注: {s.note}")
        print()
    return 0


def cmd_speakers_add(args):
    """添加说话人"""
    from core import speakers
    from core.speakers import Speaker

    name = args.name
    role = args.role or ""
    note = args.note or ""

    speaker = Speaker(name=name, role=role, note=note)
    speakers.save_speaker(speaker)
    print(f"✓ 已添加说话人: {name}")
    return 0


# ============================================================
# 热词管理命令
# ============================================================

def cmd_hotwords_list(args):
    """列出热词"""
    from core import hotwords
    HOTWORDS_FILE = Path("data/hotwords.txt")
    words = hotwords.load_hotwords(HOTWORDS_FILE)
    if not words:
        print("暂无热词")
        return 0

    print(f"共 {len(words)} 个热词：\n")
    for w in words:
        print(f"  - {w}")
    return 0


def cmd_hotwords_add(args):
    """添加热词"""
    from core import hotwords
    HOTWORDS_FILE = Path("data/hotwords.txt")

    words = hotwords.load_hotwords(HOTWORDS_FILE)
    new_words = args.words
    added = []
    for w in new_words:
        if w not in words:
            words.append(w)
            added.append(w)

    hotwords.save_hotwords(HOTWORDS_FILE, words)
    if added:
        print(f"✓ 已添加 {len(added)} 个热词: {', '.join(added)}")
    else:
        print("这些热词已存在")
    return 0


# ============================================================
# 设置管理命令
# ============================================================

def cmd_settings_show(args):
    """查看设置"""
    try:
        result = _api_request("GET", "/api/settings")
        print("当前设置:\n")
        for k, v in result.items():
            if k == "api_key":
                # 隐藏 API 密钥
                if v:
                    print(f"  {k}: {'*' * 8}...{v[-4:]}")
                else:
                    print(f"  {k}: (未设置)")
            else:
                print(f"  {k}: {v}")
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


def cmd_settings_set(args):
    """修改设置"""
    try:
        # 先获取当前设置
        current = _api_request("GET", "/api/settings")
        current[args.key] = args.value
        _api_request("POST", "/api/settings", data=current)
        print(f"✓ 已设置 {args.key} = {args.value}")
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


# ============================================================
# AI 对话命令
# ============================================================

def cmd_chat(args):
    """发送消息给 AI 助手"""
    message = args.message
    if not message:
        print("错误: 消息不能为空")
        return 1

    try:
        result = _api_request("POST", "/api/chat", data={
            "message": message,
            "task_id": args.task_id,
            "project_id": args.project_id,
        })

        print(f"AI 回复:\n{'─' * 40}")
        print(result.get("reply", "（无回复）"))

        # 显示动作结果
        action = result.get("action")
        if action:
            print(f"\n[动作执行] {action.get('name', '')}: {'成功' if action.get('success') else '失败'}")

        # 显示来源
        sources = result.get("sources", [])
        if sources:
            print(f"\n[来源] {', '.join(s.get('name', '') for s in sources)}")

        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


# ============================================================
# 主入口
# ============================================================

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

    # ─ record 命令组 ──
    p_record = subparsers.add_parser("record", help="录音控制")
    record_sub = p_record.add_subparsers(dest="record_command", help="录音操作")

    p_rec_start = record_sub.add_parser("start", help="开始录音")
    p_rec_start.set_defaults(func=cmd_record_start)

    p_rec_stop = record_sub.add_parser("stop", help="停止录音")
    p_rec_stop.set_defaults(func=cmd_record_stop)

    p_rec_pause = record_sub.add_parser("pause", help="暂停录音")
    p_rec_pause.set_defaults(func=cmd_record_pause)

    p_rec_resume = record_sub.add_parser("resume", help="恢复录音")
    p_rec_resume.set_defaults(func=cmd_record_resume)

    p_rec_status = record_sub.add_parser("status", help="查看录音状态")
    p_rec_status.set_defaults(func=cmd_record_status)

    # ── tasks 命令组 ──
    p_tasks = subparsers.add_parser("tasks", help="任务管理")
    tasks_sub = p_tasks.add_subparsers(dest="tasks_command", help="任务操作")

    p_tasks_list = tasks_sub.add_parser("list", help="列出所有任务")
    p_tasks_list.set_defaults(func=cmd_tasks_list)

    p_tasks_show = tasks_sub.add_parser("show", help="查看任务详情")
    p_tasks_show.add_argument("task_id", help="任务 ID")
    p_tasks_show.set_defaults(func=cmd_tasks_show)

    p_tasks_del = tasks_sub.add_parser("delete", help="删除任务")
    p_tasks_del.add_argument("task_id", help="任务 ID")
    p_tasks_del.set_defaults(func=cmd_tasks_delete)

    # ── speakers 命令组 ──
    p_speakers = subparsers.add_parser("speakers", help="说话人管理")
    speakers_sub = p_speakers.add_subparsers(dest="speakers_command", help="说话人操作")

    p_spk_list = speakers_sub.add_parser("list", help="列出所有说话人")
    p_spk_list.set_defaults(func=cmd_speakers_list)

    p_spk_add = speakers_sub.add_parser("add", help="添加说话人")
    p_spk_add.add_argument("name", help="姓名")
    p_spk_add.add_argument("--role", help="角色/职位")
    p_spk_add.add_argument("--note", help="备注")
    p_spk_add.set_defaults(func=cmd_speakers_add)

    # ── hotwords 命令组 ──
    p_hotwords = subparsers.add_parser("hotwords", help="热词管理")
    hotwords_sub = p_hotwords.add_subparsers(dest="hotwords_command", help="热词操作")

    p_hw_list = hotwords_sub.add_parser("list", help="列出热词")
    p_hw_list.set_defaults(func=cmd_hotwords_list)

    p_hw_add = hotwords_sub.add_parser("add", help="添加热词")
    p_hw_add.add_argument("words", nargs="+", help="热词列表")
    p_hw_add.set_defaults(func=cmd_hotwords_add)

    # ── settings 命令组 ──
    p_settings = subparsers.add_parser("settings", help="设置管理")
    settings_sub = p_settings.add_subparsers(dest="settings_command", help="设置操作")

    p_set_show = settings_sub.add_parser("show", help="查看设置")
    p_set_show.set_defaults(func=cmd_settings_show)

    p_set_set = settings_sub.add_parser("set", help="修改设置")
    p_set_set.add_argument("key", help="设置键名")
    p_set_set.add_argument("value", help="设置值")
    p_set_set.set_defaults(func=cmd_settings_set)

    # ── chat 命令 ──
    p_chat = subparsers.add_parser("chat", help="AI 对话")
    p_chat.add_argument("message", help="消息内容")
    p_chat.add_argument("--task-id", help="关联任务 ID")
    p_chat.add_argument("--project-id", help="关联项目 ID")
    p_chat.set_defaults(func=cmd_chat)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # 对于子命令，检查是否指定了具体操作
    if args.command in ("record", "tasks", "speakers", "hotwords", "settings"):
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
