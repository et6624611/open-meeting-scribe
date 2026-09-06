"""
app/server.py — FastAPI 应用入口

职责：
  1. 创建 FastAPI 应用实例
  2. 注册各功能域路由模块（12 个）
  3. 管理应用生命周期（启动/关闭事件）
  4. 安全审计中间件（请求日志 + 可疑行为检测）
  5. 托管前端静态页面

路由模块（app/routers/）：
  tasks     — 转录提交 + 任务 CRUD + 音频/下载
  record    — 录制控制 + 实时转写 WS + 实时总结/绑定
  speakers  — 说话人 CRUD + 会议级绑定/纪要生成
  projects  — 项目管理 + 文件系统浏览
  chat      — AI 对话 + 动作检测/执行
  user      — 用户信息 + 说话人绑定
  hotwords  — 热词 + 映射管理
  settings  — 设置读写
  notes     — 笔记 + AI 注入 + 待办
  voiceprint — 声纹注册 + 自动识别（V4 CAM++）
  philosophy — 理念传播（随机展示设计者理念）
  auth      — GitHub OAuth 登录 + JWT 会话 + 登出
  usage     — 用量计量查询 + 配额预检
  config    — 远程配置拉取（公告/横幅消息）
"""

import asyncio
import logging
import os
import re
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from dotenv import load_dotenv
load_dotenv()

# 配置日志输出到文件（便于崩溃后诊断）
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "server.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

# ── 安全审计日志（独立文件，仅记录安全相关事件）──
audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)
audit_handler = logging.FileHandler(LOG_DIR / "audit.log", encoding="utf-8")
audit_handler.setFormatter(logging.Formatter("%(asctime)s [AUDIT] %(message)s"))
audit_logger.addHandler(audit_handler)
audit_logger.propagate = False  # 不重复写入 server.log

from app.store import STATIC_DIR, load_tasks_from_disk, recover_interrupted_tasks, event_loop
from app.routers import tasks, record, speakers, projects, chat, user, hotwords, settings, notes, voiceprint, philosophy, auth, usage, config
from core.llm import close_async_client

logger = logging.getLogger(__name__)

# ============================================================
# 应用实例
# ============================================================

app = FastAPI(
    title="Open Meeting Scribe",
    description="会议纪要生成工具",
    version="0.1.0",
)

# ============================================================
# 安全审计中间件
# ============================================================

# 可疑路径模式（路径遍历、敏感文件探测）
_SUSPICIOUS_PATH_PATTERNS = [
    re.compile(r'\.\./'),                          # 路径遍历
    re.compile(r'^/\.(env|git|ssh|aws)', re.I),    # 敏感隐藏文件
    re.compile(r'sk-[A-Za-z0-9_\-]{20,}'),         # API Key 出现在 URL 中
]


@app.middleware("http")
async def security_audit_middleware(request: Request, call_next):
    """
    记录所有请求的审计信息，检测可疑行为。
    写入 logs/audit.log，不影响正常请求流程。
    """
    start = time.time()
    client_ip = request.client.host if request.client else "unknown"
    method = request.method
    path = request.url.path

    # 检测可疑路径
    for pattern in _SUSPICIOUS_PATH_PATTERNS:
        if pattern.search(path):
            audit_logger.warning(
                f"SUSPICIOUS_PATH | ip={client_ip} | {method} {path} | "
                f"pattern={pattern.pattern}"
            )

    # 执行请求
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000

    # 记录请求审计（仅非静态资源请求）
    if not path.startswith("/static"):
        status = response.status_code
        audit_logger.info(
            f"REQUEST | ip={client_ip} | {method} {path} | "
            f"status={status} | {duration_ms:.0f}ms"
        )

        # 4xx/5xx 错误记录告警
        if status >= 400:
            audit_logger.warning(
                f"HTTP_ERROR | ip={client_ip} | {method} {path} | "
                f"status={status} | {duration_ms:.0f}ms"
            )

    return response


# ============================================================
# 注册路由
# ============================================================

app.include_router(tasks.router)
app.include_router(record.router)
app.include_router(speakers.router)
app.include_router(projects.router)
app.include_router(chat.router)
app.include_router(user.router)
app.include_router(hotwords.router)
app.include_router(settings.router)
app.include_router(notes.router)
app.include_router(voiceprint.router)
app.include_router(philosophy.router)
app.include_router(auth.router)
app.include_router(usage.router)
app.include_router(config.router)

# ============================================================
# 生命周期
# ============================================================


@app.on_event("startup")
async def startup():
    """捕获主事件循环引用；从磁盘恢复任务；自动恢复中断的任务；同步 API Key"""
    import app.store as store
    store.event_loop = asyncio.get_running_loop()

    # 从 settings.json 同步 API Key 到环境变量（确保重启后仍有效）
    try:
        api_key = store.get_active_api_key()
        if api_key:
            os.environ["DASHSCOPE_API_KEY"] = api_key
    except Exception:
        pass

    load_tasks_from_disk()
    recover_interrupted_tasks()


@app.on_event("shutdown")
async def shutdown():
    """应用关闭时清理异步资源"""
    await close_async_client()


# ============================================================
# 前端页面
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def index():
    """返回前端页面"""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return "<h1>前端页面未找到</h1><p>请创建 app/static/index.html</p>"
    return index_path.read_text(encoding="utf-8")


# 挂载静态文件（CSS/JS/图片等）
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ============================================================
# 全局异常处理（捕获未处理异常，记录日志后进程退出）
# ============================================================

def _global_exception_handler(exc_type, exc_value, exc_traceback):
    """全局未捕获异常处理器：写入日志后允许进程正常退出"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("未捕获异常导致服务退出", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = _global_exception_handler


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
