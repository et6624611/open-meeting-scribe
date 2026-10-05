"""
cli_remote.py — 远程 API 命令（需服务运行中） / Remote API commands (server must be running)

职责 / Responsibilities:
  通过 HTTP 请求与本地 Web 服务交互，提供录音控制、任务管理、
  说话人管理、热词管理、设置管理、AI 对话等 CLI 子命令。
  Interact with local Web server via HTTP requests, providing recording control,
  task management, speaker management, hotwords management, settings, and AI chat CLI subcommands.

用法 / Usage:
    python cli.py record start|stop|pause|resume|status
    python cli.py tasks list|show|delete
    python cli.py speakers list|add
    python cli.py hotwords list|add
    python cli.py settings show|set
    python cli.py chat <消息>
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 默认服务地址 / Default server address
DEFAULT_SERVER = "http://127.0.0.1:8000"


def _api_request(method: str, path: str, data: dict | None = None, files: dict | None = None) -> dict:
    """发送 HTTP 请求到本地服务 / Send HTTP request to local server"""
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
# 录音控制命令 / Recording control commands
# ============================================================

def cmd_record_start(args):
    """开始录音 / Start recording"""
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
    """停止录音 / Stop recording"""
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
    """暂停录音 / Pause recording"""
    try:
        _api_request("POST", "/api/record/pause")
        print("✓ 录音已暂停")
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


def cmd_record_resume(args):
    """恢复录音 / Resume recording"""
    try:
        _api_request("POST", "/api/record/resume")
        print("✓ 录音已恢复")
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


def cmd_record_status(args):
    """查看录音状态 / Check recording status"""
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
# 任务管理命令 / Task management commands
# ============================================================

def cmd_tasks_list(args):
    """列出所有任务 / List all tasks"""
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
    """查看任务详情 / Show task details"""
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
    """删除任务 / Delete task"""
    try:
        _api_request("DELETE", f"/api/tasks/{args.task_id}")
        print(f"✓ 任务 {args.task_id} 已删除")
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


# ============================================================
# 说话人管理命令 / Speaker management commands
# ============================================================

def cmd_speakers_list(args):
    """列出所有说话人 / List all speakers"""
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
    """添加说话人 / Add speaker"""
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
# 热词管理命令 / Hotwords management commands
# ============================================================

def cmd_hotwords_list(args):
    """列出热词 / List hotwords"""
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
    """添加热词 / Add hotwords"""
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
# 设置管理命令 / Settings management commands
# ============================================================

def cmd_settings_show(args):
    """查看设置 / Show settings"""
    try:
        result = _api_request("GET", "/api/settings")
        print("当前设置:\n")
        for k, v in result.items():
            if k == "api_key":
                # 隐藏 API 密钥 / Hide API key
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
    """修改设置 / Modify settings"""
    try:
        # 先获取当前设置 / Get current settings first
        current = _api_request("GET", "/api/settings")
        current[args.key] = args.value
        _api_request("POST", "/api/settings", data=current)
        print(f"✓ 已设置 {args.key} = {args.value}")
        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


# ============================================================
# AI 对话命令 / AI chat commands
# ============================================================

def cmd_chat(args):
    """发送消息给 AI 助手 / Send message to AI assistant"""
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

        # 显示动作结果 / Show action result
        action = result.get("action")
        if action:
            print(f"\n[动作执行] {action.get('name', '')}: {'成功' if action.get('success') else '失败'}")

        # 显示来源 / Show sources
        sources = result.get("sources", [])
        if sources:
            print(f"\n[来源] {', '.join(s.get('name', '') for s in sources)}")

        return 0
    except RuntimeError as e:
        print(f"错误: {e}")
        return 1


# ============================================================
# argparse 注册（供 cli.py main() 调用） / argparse registration (called by cli.py main())
# ============================================================

def register_remote_commands(subparsers):
    """注册所有远程 API 子命令到 argparse / Register all remote API subcommands to argparse"""

    # ─ record 命令组 / record command group ─
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

    # ─ tasks 命令组 / tasks command group ─
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

    # ─ speakers 命令组 / speakers command group ─
    p_speakers = subparsers.add_parser("speakers", help="说话人管理")
    speakers_sub = p_speakers.add_subparsers(dest="speakers_command", help="说话人操作")

    p_spk_list = speakers_sub.add_parser("list", help="列出所有说话人")
    p_spk_list.set_defaults(func=cmd_speakers_list)

    p_spk_add = speakers_sub.add_parser("add", help="添加说话人")
    p_spk_add.add_argument("name", help="姓名")
    p_spk_add.add_argument("--role", help="角色/职位")
    p_spk_add.add_argument("--note", help="备注")
    p_spk_add.set_defaults(func=cmd_speakers_add)

    # ─ hotwords 命令组 / hotwords command group ─
    p_hotwords = subparsers.add_parser("hotwords", help="热词管理")
    hotwords_sub = p_hotwords.add_subparsers(dest="hotwords_command", help="热词操作")

    p_hw_list = hotwords_sub.add_parser("list", help="列出热词")
    p_hw_list.set_defaults(func=cmd_hotwords_list)

    p_hw_add = hotwords_sub.add_parser("add", help="添加热词")
    p_hw_add.add_argument("words", nargs="+", help="热词列表")
    p_hw_add.set_defaults(func=cmd_hotwords_add)

    # ─ settings 命令组 / settings command group ─
    p_settings = subparsers.add_parser("settings", help="设置管理")
    settings_sub = p_settings.add_subparsers(dest="settings_command", help="设置操作")

    p_set_show = settings_sub.add_parser("show", help="查看设置")
    p_set_show.set_defaults(func=cmd_settings_show)

    p_set_set = settings_sub.add_parser("set", help="修改设置")
    p_set_set.add_argument("key", help="设置键名")
    p_set_set.add_argument("value", help="设置值")
    p_set_set.set_defaults(func=cmd_settings_set)

    # ─ chat 命令 / chat command ─
    p_chat = subparsers.add_parser("chat", help="AI 对话")
    p_chat.add_argument("message", help="消息内容")
    p_chat.add_argument("--task-id", help="关联任务 ID")
    p_chat.add_argument("--project-id", help="关联项目 ID")
    p_chat.set_defaults(func=cmd_chat)
