"""
app/admin_server.py — 管理后台独立服务

职责：
  1. 创建独立的 FastAPI 应用实例（与用户端 server.py 完全隔离）
  2. 注册管理后台路由
  3. 托管管理后台前端页面

启动方式：
  python cli.py admin                    # 默认 127.0.0.1:8001
  python cli.py admin --port 9000        # 自定义端口
  python cli.py admin --host 0.0.0.0     # 允许远程访问（注意安全）

安全建议：
  - 默认只监听 127.0.0.1，不暴露到公网
  - 通过 ADMIN_PASSWORD 环境变量设置管理员密码
  - 生产环境建议配合反向代理 + HTTPS
"""

import logging
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from dotenv import load_dotenv
load_dotenv()

# ── 日志（独立日志文件）──
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

# ── 静态文件目录 ──
ADMIN_STATIC_DIR = Path(__file__).parent / "admin_static"
ADMIN_STATIC_DIR.mkdir(exist_ok=True)

# ============================================================
# 应用实例
# ============================================================

admin_app = FastAPI(
    title="Open Meeting Scribe — 管理后台",
    description="用户管理、订阅管理、系统概览",
    version="0.1.0",
)

# ============================================================
# 注册路由
# ============================================================

from app.routers import admin as admin_router
from app.routers import admin_config as admin_config_router

admin_app.include_router(admin_router.router)
admin_app.include_router(admin_config_router.router)

# ============================================================
# 前端页面
# ============================================================

ADMIN_HTML = Path(__file__).parent / "admin_static" / "admin.html"


@admin_app.get("/", response_class=HTMLResponse)
async def admin_index():
    """返回管理后台前端页面"""
    if ADMIN_HTML.exists():
        return ADMIN_HTML.read_text(encoding="utf-8")
    return "<h1>管理后台页面未找到</h1><p>请创建 app/admin_static/admin.html</p>"


# 挂载静态文件
admin_app.mount("/static", StaticFiles(directory=str(ADMIN_STATIC_DIR)), name="admin_static")
