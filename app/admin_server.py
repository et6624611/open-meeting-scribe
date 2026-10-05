"""
app/admin_server.py — 管理后台独立服务 / Admin backend standalone service

职责 / Responsibilities:
  1. 创建独立的 FastAPI 应用实例（与用户端 server.py 完全隔离） / Create independent FastAPI app instance (fully isolated from user-facing server.py)
  2. 注册管理后台路由 / Register admin routes
  3. 托管管理后台前端页面 / Host admin frontend pages

启动方式 / Startup:
  python cli.py admin                    # 默认 / default 127.0.0.1:8001
  python cli.py admin --port 9000        # 自定义端口 / Custom port
  python cli.py admin --host 0.0.0.0     # 允许远程访问（注意安全） / Allow remote access (mind security)

安全建议 / Security recommendations:
  - 默认只监听 127.0.0.1，不暴露到公网 / Default listens only on 127.0.0.1, not exposed to public network
  - 通过 ADMIN_PASSWORD 环境变量设置管理员密码 / Set admin password via ADMIN_PASSWORD env var
  - 生产环境建议配合反向代理 + HTTPS / Production: recommend reverse proxy + HTTPS
"""

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

# ── 日志（独立日志文件）── / Logging (separate log file) ──
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "admin.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ── 静态文件目录 / Static file directory ──
ADMIN_STATIC_DIR = Path(__file__).parent / "admin_static"
ADMIN_STATIC_DIR.mkdir(exist_ok=True)

# ============================================================
# 应用实例 / Application Instance
# ============================================================

admin_app = FastAPI(
    title="Open Meeting Scribe — 管理后台",
    description="用户管理、订阅管理、系统概览",
    version="0.1.0",
)

# ============================================================
# 注册路由 / Register Routes
# ============================================================

from app.routers import admin as admin_router
from app.routers import admin_config as admin_config_router

admin_app.include_router(admin_router.router)
admin_app.include_router(admin_config_router.router)

# ============================================================
# 前端页面 / Frontend Pages
# ============================================================

ADMIN_HTML = Path(__file__).parent / "admin_static" / "admin.html"


@admin_app.get("/", response_class=HTMLResponse)
async def admin_index():
    """返回管理后台前端页面 / Return admin backend frontend page."""
    if ADMIN_HTML.exists():
        return ADMIN_HTML.read_text(encoding="utf-8")
    return "<h1>管理后台页面未找到</h1><p>请创建 app/admin_static/admin.html</p>"


# 挂载静态文件 / Mount static files
admin_app.mount("/static", StaticFiles(directory=str(ADMIN_STATIC_DIR)), name="admin_static")
