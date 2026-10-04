"""
app/server.py — FastAPI 应用入口 / FastAPI application entry point

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-03
版本 / Version: 1.0.0

职责 / Responsibilities:
  1. 创建 FastAPI 应用实例 / Create FastAPI application instance
  2. 注册各功能域路由模块（12 个） / Register domain router modules (12)
  3. 管理应用生命周期（启动/关闭事件） / Manage application lifecycle (startup/shutdown events)
  4. 安全审计中间件（请求日志 + 可疑行为检测） / Security audit middleware (request logging + suspicious behavior detection)
  5. 托管前端静态页面 / Host frontend static pages

路由模块（app/routers/） / Router modules (app/routers/):
  tasks     — 转录提交 + 任务 CRUD + 音频/下载 / Transcription submit + task CRUD + audio/download
  record    — 录制控制 + 实时总结/绑定 / Recording control + realtime summary/binding
  ws_transcript — WebSocket 实时转写端点 / WebSocket realtime transcription endpoint
  speakers  — 说话人 CRUD + 会议级绑定/纪要生成 / Speaker CRUD + meeting-level binding/summary generation
  projects  — 项目管理 + 文件系统浏览 / Project management + file system browsing
  chat      — AI 对话 + 动作检测/执行 / AI chat + action detection/execution
  user      — 用户信息 + 说话人绑定 / User info + speaker binding
  hotwords  — 热词 + 映射管理 / Hotwords + mapping management
  settings  — 设置读写 / Settings read/write
  notes     — 笔记 + AI 注入 + 待办 / Notes + AI injection + todos
  voiceprint — 声纹注册 + 自动识别（V4 CAM++） / Voiceprint registration + auto-identification (V4 CAM++)
  philosophy — 理念传播（随机展示设计者理念） / Philosophy dissemination (random designer philosophy display)
  auth      — GitHub OAuth 登录 + JWT 会话 + 登出 / GitHub OAuth login + JWT session + logout
  usage     — 用量计量查询 + 配额预检 / Usage metering query + quota pre-check
  config    — 远程配置拉取（公告/横幅消息） / Remote config fetch (announcements/banner messages)
  update    — 版本更新检查 / Version update check
"""

import asyncio
import logging
import os
import re
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

# 配置日志输出到文件（便于崩溃后诊断） / Configure logging to file (for post-crash diagnosis)
# PyInstaller 打包后，日志写入 exe 所在目录而非临时解压目录 / After packaging, logs go to exe dir, not temp extract dir
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    LOG_DIR = Path(sys.executable).parent / "logs"
else:
    LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
# 日志轮转：单文件上限 5MB，保留 5 个历史备份，防止无限制增长耗尽磁盘 / Log rotation: 5MB per file, 5 backups, prevents disk exhaustion
_LOG_MAX_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 5

# BUG-006 修复：在 frozen 模式下 sys.stdout 可能被重定向到 devnull，
# 且 root logger 可能已被其他模块配置，导致 basicConfig() 无效。
# 使用 force=True 强制重新配置，确保 server.log 能正常写入。
# Fix: In frozen mode sys.stdout may be redirected to devnull,
# and root logger may already be configured, making basicConfig() no-op.
# Use force=True to ensure server.log is properly written.
_file_handler = RotatingFileHandler(
    LOG_DIR / "server.log",
    maxBytes=_LOG_MAX_BYTES,
    backupCount=_LOG_BACKUP_COUNT,
    encoding="utf-8",
)
_stream_handler = logging.StreamHandler(sys.stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[_file_handler, _stream_handler],
    force=True,
)

# ── 安全审计日志（独立文件，仅记录安全相关事件）── / Security audit log (separate file; security events only) ──
audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)
audit_handler = RotatingFileHandler(
    LOG_DIR / "audit.log",
    maxBytes=_LOG_MAX_BYTES,
    backupCount=_LOG_BACKUP_COUNT,
    encoding="utf-8",
)
audit_handler.setFormatter(logging.Formatter("%(asctime)s [AUDIT] %(message)s"))
audit_logger.addHandler(audit_handler)
audit_logger.propagate = False  # 不重复写入 server.log / Don't duplicate to server.log

from app.routers import (
    agent,
    agent_tools,
    auth,
    chat,
    cloud_api,
    config,
    decision_statuses,
    decisions,
    engine_component,
    hotwords,
    import_tasks,
    insights,
    models,
    notes,
    philosophy,
    projects,
    record,
    settings,
    speakers,
    tasks,
    update,
    usage,
    user,
    voiceprint,
    ws_transcript,
)
from app.store import STATIC_DIR, cleanup_orphaned_intermediate_files, load_tasks_from_disk, recover_interrupted_tasks
from core.auth import verify_jwt
from core.i18n import I18nMiddleware
from core.llm import close_async_client
from core.users import set_request_user_id

logger = logging.getLogger(__name__)

# ============================================================
# 应用实例 / Application Instance
# ============================================================

app = FastAPI(
    title="Open Meeting Scribe",
    description="会议纪要生成工具",
    version="0.1.0",
)


# ============================================================
# CORS 中间件 / CORS Middleware
# ============================================================

# 允许的跨域来源列表，通过环境变量 CORS_ORIGINS 配置（逗号分隔） /
# Allowed cross-origin sources, configurable via CORS_ORIGINS env var (comma-separated).
# 未配置时默认允许 localhost 各端口（开发模式） / Defaults to localhost ports when unset (dev mode).
_CORS_ORIGINS_RAW = os.getenv("CORS_ORIGINS", "")
if _CORS_ORIGINS_RAW.strip():
    _cors_origins = [o.strip() for o in _CORS_ORIGINS_RAW.split(",") if o.strip()]
else:
    # 开发模式默认允许 localhost 常见端口 / Dev-mode defaults: common localhost ports
    _cors_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8080",
    ]

# 注意：CORSMiddleware 在所有中间件之后注册（见下方），确保其为最外层，
# 以便正确处理 OPTIONS 预检请求，避免被认证中间件拦截。
# Note: CORSMiddleware is registered after all other middleware (see below),
# ensuring it's the outermost layer to properly handle OPTIONS preflight requests
# and prevent interception by auth middleware.


# ============================================================
# BUG-003 修复：自定义 HTTPException 处理器，确保错误响应体始终非空
# BUG-003 fix: Custom HTTPException handler to ensure error response body is never empty
# ============================================================

@app.exception_handler(Exception)
async def http_exception_handler(request: Request, exc: Exception):
    """全局 HTTPException 处理器：始终返回结构化 JSON 响应体。
    Global HTTPException handler: always return structured JSON response body.
    """
    from fastapi import HTTPException as FastAPIHTTPException
    if isinstance(exc, FastAPIHTTPException):
        # 确保 detail 始终存在 / Ensure detail is always present
        detail = exc.detail if exc.detail else f"HTTP {exc.status_code}"
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail},
            headers=exc.headers,
        )
    # 非 HTTPException 的未处理异常 / Unhandled non-HTTP exceptions
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ============================================================
# BUG-005: /api/health 健康检查端点 / Health check endpoint
# ============================================================

@app.get("/api/health")
async def health_check(request: Request):
    """健康检查端点，供前端和监控探测服务存活状态。
    Health check endpoint for frontend and monitoring liveness probe.

    DEF-01: 附带会话探测结果（auth.logged_in），前端据此决定是否调用
    /auth/me，避免本地/匿名模式下每页产生一次 401 控制台噪音。
    判定逻辑与 /auth/me 保持一致：有效 JWT cookie 或本地 current_user_id。
    auth.logged_in mirrors /auth/me's success condition so the frontend can
    skip the /auth/me probe (and its 401 console noise) when no session exists.
    """
    logged_in = False
    token = request.cookies.get(_SESSION_COOKIE)
    if token:
        payload = verify_jwt(token)
        if payload and payload.get("sub"):
            logged_in = True
    if not logged_in:
        from core.users import _load_user_data
        logged_in = bool(_load_user_data().get("current_user_id"))
    return {"status": "ok", "auth": {"logged_in": logged_in}}


# ============================================================
# 国际化中间件（解析语言偏好，注入 request.state.locale） / I18n middleware (parse language preference, inject request.state.locale)
# ============================================================

app.add_middleware(I18nMiddleware)

# ============================================================
# 用户身份中间件（从 JWT cookie 解析，写入 ContextVar） / User identity middleware (parse from JWT cookie, write to ContextVar)
# ============================================================

# JWT cookie 的名称（与 auth.py 保持一致） / JWT cookie name (consistent with auth.py)
_SESSION_COOKIE = "oms_session"


@app.middleware("http")
async def user_identity_middleware(request: Request, call_next):
    """
    从请求的 JWT cookie 中解析用户 ID，写入 ContextVar，
    使 get_current_user() 能按会话区分用户身份 / Parse user ID from JWT cookie into ContextVar;
    enables get_current_user() to distinguish users by session.
    """
    token = request.cookies.get(_SESSION_COOKIE)
    if token:
        payload = verify_jwt(token)
        if payload:
            set_request_user_id(payload.get("sub"))
    try:
        response = await call_next(request)
    finally:
        # 请求结束后清理，避免连接池复用时状态泄漏 / Cleanup after request; prevents state leakage on connection pool reuse
        set_request_user_id(None)
    return response


# ============================================================
# 认证强制中间件（多用户/服务器部署时启用） / Auth enforcement middleware (enabled for multi-user/server deployment)
# ============================================================

# REQUIRE_AUTH=true 时强制所有业务 API 校验 JWT 会话； / When REQUIRE_AUTH=true, enforce JWT session validation for all business APIs;
# 本地个人使用（默认 false）保持免登录，符合「本地数据·云端智能」定位 / Local personal use (default false) remains login-free; aligns with "local data, cloud intelligence" positioning.
_REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

# REQUIRE_AUTH=true 时无需用户 JWT 即可访问的路径前缀 / Path prefixes exempt from JWT requirement when REQUIRE_AUTH=true:
#   - /auth/       登录流程本身（GitHub OAuth / SMS） / Login flow itself (GitHub OAuth / SMS)
#   - /api/admin/  管理后台，有独立的 require_admin 认证 / Admin backend; has independent require_admin auth
#   - /api/config/ 公告、版本等公开配置 / Announcements, version, and public config
#   - /api/models  可用模型列表（公开只读） / Available model list (public read-only)
#   - /api/health  存活/会话探测（DEF-01：前端据此决定是否调用 /auth/me） /
#                  Liveness & session probe (DEF-01: frontend gates /auth/me on it)
_AUTH_EXEMPT_PREFIXES = (
    "/auth/",
    "/api/admin/",
    "/api/agent-tools/",   # 反向工具面：用进程内短时 bearer 保护（非 JWT），仅本机回环使用
    "/api/cloud/",
    "/api/config/",
    "/api/download/",
    "/api/health",
    "/api/models",
)


@app.middleware("http")
async def enforce_auth_middleware(request: Request, call_next):
    """
    多用户部署认证网关 / Multi-user deployment auth gateway: REQUIRE_AUTH=true 时，除白名单外的所有 /api/*
    请求必须携带有效的 JWT 会话 cookie，否则返回 401 / all /api/* requests (except whitelisted) must carry valid JWT session cookie; returns 401 otherwise.
    本地模式（REQUIRE_AUTH=false）直接放行，不做任何拦截 / Local mode (REQUIRE_AUTH=false) passes through without interception.
    """
    if _REQUIRE_AUTH:
        # CORS 预检请求（OPTIONS）直接放行，由 CORSMiddleware 处理响应头 /
        # Let CORS preflight (OPTIONS) pass through; CORSMiddleware handles response headers.
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path
        if path.startswith("/api/") and not path.startswith(_AUTH_EXEMPT_PREFIXES):
            token = request.cookies.get(_SESSION_COOKIE)
            payload = verify_jwt(token) if token else None
            if not payload:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required"},
                )
    return await call_next(request)


# ============================================================
# 安全审计中间件 / Security Audit Middleware
# ============================================================

# 可疑路径模式（路径遍历、敏感文件探测） / Suspicious path patterns (path traversal, sensitive file probing)
_SUSPICIOUS_PATH_PATTERNS = [
    re.compile(r'\.\./'),                          # 路径遍历 / Path traversal
    re.compile(r'^/\.(env|git|ssh|aws)', re.I),    # 敏感隐藏文件 / Sensitive hidden files
    re.compile(r'sk-[A-Za-z0-9_\-]{20,}'),         # API Key 出现在 URL 中 / API Key appearing in URL
]


# 慢请求告警阈值（毫秒），超过此值的请求会在主日志中以 WARNING 级别记录 / Slow request warning threshold (ms); requests exceeding this are logged as WARNING
SLOW_REQUEST_THRESHOLD_MS = 3000  # 3 秒 / 3 seconds


@app.middleware("http")
async def security_audit_middleware(request: Request, call_next):
    """
    记录所有请求的审计信息，检测可疑行为 / Log audit info for all requests; detect suspicious behavior.
    写入 logs/audit.log，不影响正常请求流程 / Writes to logs/audit.log; does not affect normal request flow.
    慢请求（>3s）同时在主日志中输出 WARNING 告警 / Slow requests (>3s) also emit WARNING in main log.
    """
    start = time.time()
    client_ip = request.client.host if request.client else "unknown"
    method = request.method
    path = request.url.path

    # 检测可疑路径 / Detect suspicious paths
    for pattern in _SUSPICIOUS_PATH_PATTERNS:
        if pattern.search(path):
            audit_logger.warning(
                f"SUSPICIOUS_PATH | ip={client_ip} | {method} {path} | "
                f"pattern={pattern.pattern}"
            )

    # 执行请求 / Execute request
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000

    # 记录请求审计（仅非静态资源请求） / Log request audit (non-static resource requests only)
    if not path.startswith("/static"):
        status = response.status_code
        audit_logger.info(
            f"REQUEST | ip={client_ip} | {method} {path} | "
            f"status={status} | {duration_ms:.0f}ms"
        )

        # 4xx/5xx 错误记录告警 / Log warning for 4xx/5xx errors
        if status >= 400:
            audit_logger.warning(
                f"HTTP_ERROR | ip={client_ip} | {method} {path} | "
                f"status={status} | {duration_ms:.0f}ms"
            )

        # 慢请求告警（写入主日志） / Slow request warning (write to main log)
        if duration_ms > SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                f"[PERF] 慢请求: {method} {path} | "
                f"{duration_ms:.0f}ms (>{SLOW_REQUEST_THRESHOLD_MS}ms)"
            )

    return response


# ============================================================
# CORS 中间件（最外层） / CORS Middleware (outermost layer)
# ============================================================

# CORSMiddleware 必须作为最外层中间件注册（最后添加），确保：
# 1. OPTIONS 预检请求在到达认证中间件之前就被处理并返回 CORS 头
# 2. 所有响应都能正确添加 Access-Control-Allow-Origin 等头
# 3. 跨域部署（如前端 localhost:5173 访问后端 localhost:8000）正常工作
# CORSMiddleware must be registered as the outermost middleware (added last) to ensure:
# 1. OPTIONS preflight requests are handled and return CORS headers before reaching auth middleware
# 2. All responses correctly include Access-Control-Allow-Origin and other CORS headers
# 3. Cross-origin deployment (e.g., frontend localhost:5173 to backend localhost:8000) works properly
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 注册路由 / Register Routes
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
app.include_router(decisions.router)
app.include_router(decision_statuses.router)
app.include_router(voiceprint.router)
app.include_router(philosophy.router)
app.include_router(auth.router)
app.include_router(usage.router)
app.include_router(config.router)
app.include_router(update.router)
app.include_router(insights.router)
app.include_router(agent.router)
app.include_router(agent_tools.router)
app.include_router(cloud_api.router)
app.include_router(ws_transcript.router)
app.include_router(import_tasks.router)
app.include_router(models.router)
app.include_router(engine_component.router)

# ============================================================
# 软件下载分发（自建下载中转） / Software download distribution (self-hosted relay)
# ============================================================

# 下载文件存放目录（PyInstaller 打包后存放在 exe 同级目录） /
# Directory for download files (PyInstaller: stored next to the executable)
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    DOWNLOADS_DIR = Path(sys.executable).parent / "data" / "downloads"
else:
    DOWNLOADS_DIR = Path(__file__).parent.parent / "data" / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """
    下载软件安装包 / Download software installation package.

    从 data/downloads/ 目录提供文件下载，用于私库场景下的自建分发。
    Serve files from data/downloads/ for self-hosted distribution in private repo scenarios.
    客户端通过 remote_config.json 的 downloads 字段获取对应平台的下载链接。
    Clients get platform-specific download URLs from remote_config.json's downloads field.
    """
    # 路径遍历防护：确保文件在 DOWNLOADS_DIR 内 /
    # Path traversal protection: ensure file is within DOWNLOADS_DIR
    safe_path = (DOWNLOADS_DIR / filename).resolve()
    if not str(safe_path).startswith(str(DOWNLOADS_DIR.resolve())):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not Found")
    if not safe_path.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(safe_path),
        filename=filename,
        media_type="application/octet-stream",
    )

# ============================================================
# 自动归档 / Auto Archive
# ============================================================

_AUTO_ARCHIVE_INTERVAL = 24 * 3600  # 24 小时 / 24 hours


async def _auto_archive_loop():
    """定时检查并归档已完成任务的音频文件（每 24 小时执行一次） / Periodically check and archive completed task audio files (once per 24h)."""
    while True:
        try:
            await asyncio.sleep(_AUTO_ARCHIVE_INTERVAL)
            _run_auto_archive()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"自动归档任务失败: {e}")


def _run_auto_archive():
    """执行一次自动归档：删除超过阈值的已完成任务的音频文件 / Run one auto-archive: delete audio files of completed tasks exceeding threshold."""
    from app.settings_store import get_storage_config
    from app.task_store import save_task_to_disk, tasks

    config = get_storage_config()
    archive_days = config.get("auto_archive_days", 0)
    if archive_days <= 0:
        return

    now = time.time()
    archived_count = 0

    for task_id, task in list(tasks.items()):
        if task.get("status") != "completed":
            continue
        if task.get("audio_archived"):
            continue

        # 检查任务创建时间是否超过阈值 / Check if task creation time exceeds threshold
        created_at = task.get("created_at", "")
        if not created_at:
            continue
        try:
            from datetime import datetime
            created_dt = datetime.fromisoformat(created_at)
            age_days = (now - created_dt.timestamp()) / 86400
            if age_days < archive_days:
                continue
        except (ValueError, TypeError):
            continue

        # 删除音频文件（原始 + 归一化 + raw） / Delete audio files (original + normalized + raw)
        audio_path = task.get("audio_path")
        if audio_path:
            ap = Path(audio_path)
            if ap.exists():
                ap.unlink()
            # 归一化文件 / Normalized file
            normalized_path = task.get("normalized_path")
            if normalized_path:
                np = Path(normalized_path)
                if np.exists():
                    np.unlink(missing_ok=True)
            # 按命名规则查找归一化文件 / Find normalized files by naming convention
            if ap.exists() or True:  # 即使原始文件已删除也尝试清理 / Try cleanup even if original file is deleted
                for suffix in ["_normalized.wav", "_normalized_normalized.wav"]:
                    candidate = ap.with_stem(f"{ap.stem}{suffix.replace('.wav', '')}").with_suffix(".wav")
                    if candidate.exists():
                        candidate.unlink(missing_ok=True)
            # raw 文件 / Raw file
            raw_candidate = ap.with_suffix(".raw")
            if raw_candidate.exists():
                raw_candidate.unlink(missing_ok=True)

        # 标记已归档 / Mark as archived
        task["audio_archived"] = True
        save_task_to_disk(task_id)
        archived_count += 1

    if archived_count:
        logger.info(f"[自动归档] 已归档 {archived_count} 个超过 {archive_days} 天的已完成任务的音频文件")


# ============================================================
# 生命周期 / Lifecycle
# ============================================================


@app.on_event("startup")
async def startup():
    """捕获主事件循环引用；从磁盘恢复任务；自动恢复中断的任务；同步 API Key / Capture main event loop ref; restore tasks from disk; auto-recover interrupted tasks; sync API Key."""
    import app.realtime_store as rt_store
    rt_store.event_loop = asyncio.get_running_loop()

    # 从 settings.json 同步 API Key 到环境变量（确保重启后仍有效） / Sync API Key from settings.json to env var (ensure validity after restart)
    try:
        from app.settings_store import get_active_api_key
        api_key = get_active_api_key()
        if api_key:
            os.environ["DASHSCOPE_API_KEY"] = api_key
    except Exception:
        pass

    # 逐能力迁移：把存量 access_mode 映射为 capability_source 并移除该字段（旧字段投影保留支持回滚）
    try:
        from app.settings_store import run_percap_migration
        run_percap_migration()
    except Exception as e:
        logger.warning(f"启动逐能力迁移失败（不影响服务）: {e}")

    load_tasks_from_disk()
    recover_interrupted_tasks()

    # 启动时清理冗余/孤儿中间文件 / Cleanup orphaned intermediate files on startup
    try:
        cleanup_orphaned_intermediate_files()
    except Exception as e:
        logger.warning(f"启动清理中间文件失败（不影响服务）: {e}")

    # 智能体引擎过期工作区按保留期清理（含会议上下文，R7/§3.10；不影响服务）
    try:
        from app.settings_store import get_chat_engine_config
        from core.cli_engine import sweep_expired_workspaces
        _retention = get_chat_engine_config().get("retention_days", 7)
        sweep_expired_workspaces(_retention)
        # AI 写回快照 sidecar 与工作区同一保留期口径（PROPOSAL §5.3）
        from core.rewrite_snapshots import sweep_expired_snapshots
        sweep_expired_snapshots(_retention)
    except Exception as e:
        logger.warning(f"启动清理智能体工作区失败（不影响服务）: {e}")

    # 启动自动归档定时任务（每 24 小时检查一次） / Start auto-archive scheduled task (check once per 24h)
    asyncio.create_task(_auto_archive_loop())


@app.on_event("shutdown")
async def shutdown():
    """应用关闭时清理异步资源 / Cleanup async resources on application shutdown."""
    await close_async_client()


# ============================================================
# PyInstaller 兼容路径 / PyInstaller compatible paths
# ============================================================

# PyInstaller 打包后，资源文件解压到临时目录 sys._MEIPASS /
# After packaging, resource files are extracted to temp dir sys._MEIPASS
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    _BUNDLE_BASE = Path(sys._MEIPASS)
else:
    _BUNDLE_BASE = Path(__file__).parent.parent

# ============================================================
# 前端页面 / Frontend Pages
# ============================================================

# Vue 构建产物目录（优先级高于旧版 app/static/） / Vue build output directory (takes priority over legacy app/static/)
FRONTEND_DIST = _BUNDLE_BASE / "frontend" / "dist"

if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    # ── 新版：Vue SPA（生产模式）── / New: Vue SPA (production mode) ──
    logger.info(f"前端使用 Vue 构建产物: {FRONTEND_DIST}")

    # 挂载 Vite 构建的静态资源（带 hash 的文件） / Mount Vite build static assets (hashed files)
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend_assets")

    # OBS-01: 显式注册 HEAD，使 HEAD / 与 GET / 返回相同 content-type
    # （FastAPI 的 @app.get 不像 Starlette Route 那样自动附带 HEAD）/
    # Register HEAD explicitly so HEAD / matches this route with the same
    # content-type as GET (FastAPI's @app.get does not auto-add HEAD).
    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], response_class=HTMLResponse)
    async def frontend_catch_all(full_path: str):
        """Vue Router history 模式：所有非 API 路由返回 index.html / Vue Router history mode: all non-API routes return index.html."""
        # 跳过 API 和 WebSocket 路径 / Skip API and WebSocket paths
        if full_path.startswith(("api/", "ws/", "auth/")):
            from fastapi import HTTPException
            raise HTTPException(404, "Not Found")
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>前端构建产物损坏</h1><p>请重新运行 npm run build</p>")
else:
    # ── 旧版：app/static/index.html（Vue 构建产物同步或历史单文件模式）── /
    # Legacy: app/static/index.html (synced Vue build output or historical single-file mode)
    logger.info("前端使用 app/static/index.html")

    # 挂载 Vite 构建的 /assets 路径（index.html 中引用的 JS/CSS 资源） /
    # Mount Vite build /assets path (JS/CSS resources referenced in index.html)
    _STATIC_ASSETS_DIR = STATIC_DIR / "assets"
    if _STATIC_ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(_STATIC_ASSETS_DIR)), name="static_assets")

    # 挂载静态文件（CSS/JS/图片等） / Mount static files (CSS/JS/images etc.)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # SPA catch-all：Vue Router history 模式下，任何非 API/WS/静态资源路径都返回 index.html，
    # 保证在 /settings、/library 等子页面按 F5 刷新时不会命中 404 JSON。
    # SPA catch-all: under Vue Router history mode, all non-API/WS/static paths return index.html,
    # ensuring F5 refresh on subpages like /settings, /library does not hit the 404 JSON.
    _LEGACY_INDEX = STATIC_DIR / "index.html"

    # OBS-01: 同上，显式注册 HEAD / Same as above: register HEAD explicitly
    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], response_class=HTMLResponse)
    async def legacy_frontend_catch_all(full_path: str):
        """旧版 SPA catch-all：非 API 路径返回 app/static/index.html。
        Legacy SPA catch-all: non-API paths return app/static/index.html.
        """
        # 跳过 API、WebSocket、认证回调路径 / Skip API, WebSocket, auth callback paths
        if full_path.startswith(("api/", "ws/", "auth/")):
            from fastapi import HTTPException
            raise HTTPException(404, "Not Found")
        # 已挂载的静态资源前缀由 StaticFiles 处理，此处不应到达；
        # 若到达则视为 SPA 路由，返回 index.html 让前端 router 接管。
        # Mounted static prefixes are handled by StaticFiles and should not reach here;
        # if reached, treat as SPA route and return index.html for frontend router.
        if not _LEGACY_INDEX.exists():
            return HTMLResponse(
                "<h1>前端页面未找到 / Frontend not found</h1>"
                "<p>请构建前端 (cd frontend && npm run build) 并同步到 app/static/。</p>"
            )
        return HTMLResponse(_LEGACY_INDEX.read_text(encoding="utf-8"))


# ============================================================
# 全局异常处理（捕获未处理异常，记录日志后进程退出） / Global exception handler (catch unhandled exceptions; log then exit)
# ============================================================

def _global_exception_handler(exc_type, exc_value, exc_traceback):
    """全局未捕获异常处理器：写入日志后允许进程正常退出 / Global uncaught exception handler: log then allow graceful exit."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("未捕获异常导致服务退出", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = _global_exception_handler


# ============================================================
# 启动入口 / Startup Entry
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
