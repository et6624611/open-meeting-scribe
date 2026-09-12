"""
app/server.py — FastAPI 应用入口

作者：王永亮
创建：2026-09-03
版本：1.0.0

职责：
  1. 创建 FastAPI 应用实例
  2. 注册各功能域路由模块（12 个）
  3. 管理应用生命周期（启动/关闭事件）
  4. 安全审计中间件（请求日志 + 可疑行为检测）
  5. 托管前端静态页面

路由模块（app/routers/）：
  tasks     — 转录提交 + 任务 CRUD + 音频/下载
  record    — 录制控制 + 实时总结/绑定
  ws_transcript — WebSocket 实时转写端点
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
  update    — 版本更新检查
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
from app.routers import tasks, record, ws_transcript, speakers, projects, chat, user, hotwords, settings, notes, voiceprint, philosophy, auth, usage, config, update, insights
from core.auth import verify_jwt
from core.i18n import I18nMiddleware
from core.llm import close_async_client
from core.users import set_request_user_id

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
# 国际化中间件（解析语言偏好，注入 request.state.locale）
# ============================================================

app.add_middleware(I18nMiddleware)

# ============================================================
# 用户身份中间件（从 JWT cookie 解析，写入 ContextVar）
# ============================================================

# JWT cookie 名称（与 auth.py 保持一致）
_SESSION_COOKIE = "oms_session"


@app.middleware("http")
async def user_identity_middleware(request: Request, call_next):
    """
    从请求的 JWT cookie 中解析用户 ID，写入 ContextVar，
    使 get_current_user() 能按会话区分用户身份。
    """
    token = request.cookies.get(_SESSION_COOKIE)
    if token:
        payload = verify_jwt(token)
        if payload:
            set_request_user_id(payload.get("sub"))
    try:
        response = await call_next(request)
    finally:
        # 请求结束后清理，避免连接池复用时状态泄漏
        set_request_user_id(None)
    return response


# ============================================================
# 安全审计中间件
# ============================================================

# 可疑路径模式（路径遍历、敏感文件探测）
_SUSPICIOUS_PATH_PATTERNS = [
    re.compile(r'\.\./'),                          # 路径遍历
    re.compile(r'^/\.(env|git|ssh|aws)', re.I),    # 敏感隐藏文件
    re.compile(r'sk-[A-Za-z0-9_\-]{20,}'),         # API Key 出现在 URL 中
]


# 慢请求告警阈值（毫秒），超过此值的请求会在主日志中以 WARNING 级别记录
SLOW_REQUEST_THRESHOLD_MS = 3000  # 3 秒


@app.middleware("http")
async def security_audit_middleware(request: Request, call_next):
    """
    记录所有请求的审计信息，检测可疑行为。
    写入 logs/audit.log，不影响正常请求流程。
    慢请求（>3s）同时在主日志中输出 WARNING 告警。
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

        # 慢请求告警（写入主日志）
        if duration_ms > SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                f"[PERF] 慢请求: {method} {path} | "
                f"{duration_ms:.0f}ms (>{SLOW_REQUEST_THRESHOLD_MS}ms)"
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
app.include_router(update.router)
app.include_router(insights.router)
app.include_router(ws_transcript.router)

# ============================================================
# 生命周期
# ============================================================


@app.on_event("startup")
async def startup():
    """捕获主事件循环引用；从磁盘恢复任务；自动恢复中断的任务；同步 API Key"""
    import app.realtime_store as rt_store
    rt_store.event_loop = asyncio.get_running_loop()

    # 从 settings.json 同步 API Key 到环境变量（确保重启后仍有效）
    try:
        from app.settings_store import get_active_api_key
        api_key = get_active_api_key()
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

# Vue 构建产物目录（优先级高于旧版 app/static/）
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    # ── 新版：Vue SPA（生产模式）──
    logger.info(f"前端使用 Vue 构建产物: {FRONTEND_DIST}")

    # 挂载 Vite 构建的静态资源（带 hash 的文件）
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend_assets")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def frontend_catch_all(full_path: str):
        """Vue Router history 模式：所有非 API 路由返回 index.html"""
        # 跳过 API 和 WebSocket 路径
        if full_path.startswith(("api/", "ws/", "auth/")):
            from fastapi import HTTPException
            raise HTTPException(404, "Not Found")
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>前端构建产物损坏</h1><p>请重新运行 npm run build</p>")
else:
    # ── 旧版：单文件 index.html（兼容模式）──
    logger.info("前端使用旧版 app/static/index.html")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        """返回前端页面"""
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            return "<h1>前端页面未找到</h1><p>请创建 app/static/index.html 或构建前端 (cd frontend && npm run build)</p>"
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
