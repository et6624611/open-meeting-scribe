"""
core/version_check.py — 版本检查与比对 / Version checking and comparison

职责 / Responsibilities:
  1. 读取本地 VERSION 文件获取当前版本 / Read local VERSION file for current version
  2. 从 remote_config.json 获取最新版本 / Fetch latest version from remote_config.json
  3. 语义化版本比对（semver） / Semantic version comparison (semver)
  4. 返回结构化的版本检查结果 / Return structured version check result

设计说明 / Design notes:
  - 版本信息来源为 data/remote_config.json 的 latest_release 字段 /
    Version info source is the latest_release field in data/remote_config.json
  - 发布新版本时，手动更新 remote_config.json 中的 latest_release 即可 /
    When releasing a new version, simply update latest_release in remote_config.json
  - 结果缓存 30 分钟，避免频繁读取 / Results cached for 30 minutes to avoid frequent reads
  - 无网络依赖，纯本地文件读取 / No network dependency; pure local file read
"""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# 本地 VERSION 文件路径 / Local VERSION file path
VERSION_FILE = Path(__file__).parent.parent / "VERSION"

# 远程配置文件路径 / Remote config file path
REMOTE_CONFIG_FILE = Path("data/remote_config.json")

# 缓存有效期（秒） / Cache TTL (seconds)
CACHE_TTL = 1800  # 30 分钟 / 30 minutes

# 缓存 / Cache
_cache: dict | None = None
_cache_time: float = 0


def get_current_version() -> str:
    """读取本地 VERSION 文件，返回当前版本号 / Read local VERSION file; return current version number."""
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        logger.warning("无法读取 VERSION 文件: %s", VERSION_FILE)
        return "0.0.0"


def _parse_semver(version: str) -> tuple[int, int, int]:
    """
    解析语义化版本号，返回 (major, minor, patch) 元组 / Parse semantic version; return (major, minor, patch) tuple.
    忽略前缀 'v' 和预发布后缀 / Ignores 'v' prefix and pre-release suffix.
    """
    v = version.lstrip("v").strip()
    # 去掉预发布后缀（如 -beta.1, -rc.2） / Strip pre-release suffix (e.g. -beta.1, -rc.2)
    v = v.split("-")[0]
    parts = v.split(".")
    try:
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        major, minor, patch = 0, 0, 0
    return (major, minor, patch)


def compare_versions(current: str, latest: str) -> int:
    """
    比对两个版本号 / Compare two version strings.
    返回 / Returns:
      1  — latest > current（有新版本 / new version available）
      0  — 相同 / Identical
     -1  — latest < current（本地更新 / local is newer）
    """
    c = _parse_semver(current)
    lat = _parse_semver(latest)
    if lat > c:
        return 1
    elif lat < c:
        return -1
    return 0


def _read_latest_release() -> dict | None:
    """
    从 remote_config.json 读取最新版本信息 / Read latest version info from remote_config.json.

    返回格式 / Returns:
      {
        "version": "7.3.0",
        "release_url": "https://github.com/.../releases/tag/v7.3.0",
        "downloads": {
          "windows": "https://your-server.com/api/download/OpenMeetingScribe-7.3.0.exe",
          "macos": "https://your-server.com/api/download/OpenMeetingScribe-7.3.0.zip"
        },
        "changelog": "...",
        "published_at": "2026-09-17T..."
      }
    """
    try:
        if not REMOTE_CONFIG_FILE.exists():
            logger.warning("remote_config.json 不存在: %s", REMOTE_CONFIG_FILE)
            return None

        data = json.loads(REMOTE_CONFIG_FILE.read_text(encoding="utf-8"))
        release = data.get("latest_release", {})
        version = release.get("version", "").strip()
        if not version:
            return None

        return {
            "version": version.lstrip("v").strip(),
            "release_url": release.get("release_url", ""),
            "downloads": release.get("downloads", {}),
            "changelog": release.get("changelog", ""),
            "published_at": release.get("published_at", ""),
        }
    except Exception as e:
        logger.warning("读取 remote_config.json 版本信息失败: %s", e)
        return None


def check_for_update(settings: dict | None = None, force: bool = False) -> dict:
    """
    检查是否有新版本可用 / Check if a new version is available.

    Args:
        settings: 应用设置（可选，保留兼容） / App settings (optional, kept for compatibility)
        force: 是否强制刷新（忽略缓存） / Force refresh (ignore cache)

    Returns:
        {
            "current_version": "1.0.0",
            "latest_version": "2.1.0" | null,
            "update_available": true | false,
            "release_url": "https://...",
            "downloads": {"windows": "...", "macos": "..."},
            "changelog": "...",
            "published_at": "...",
            "checked_at": 1234567890.0,
            "error": null | "error description"
        }
    """
    global _cache, _cache_time

    current = get_current_version()

    # 检查缓存 / Check cache
    now = time.time()
    if not force and _cache and (now - _cache_time) < CACHE_TTL:
        result = _cache.copy()
        result["current_version"] = current
        result["checked_at"] = now
        # 重新比对（可能本地版本变了） / Re-compare (local version may have changed)
        if result.get("latest_version"):
            result["update_available"] = compare_versions(current, result["latest_version"]) > 0
        return result

    # 从 remote_config.json 读取最新版本 / Read latest version from remote_config.json
    latest_info = _read_latest_release()

    if not latest_info:
        result = {
            "current_version": current,
            "latest_version": None,
            "update_available": False,
            "release_url": "",
            "downloads": {},
            "changelog": "",
            "published_at": "",
            "checked_at": now,
            "error": None,
        }
    else:
        latest_ver = latest_info["version"]
        result = {
            "current_version": current,
            "latest_version": latest_ver,
            "update_available": compare_versions(current, latest_ver) > 0,
            "release_url": latest_info.get("release_url", ""),
            "downloads": latest_info.get("downloads", {}),
            "changelog": latest_info.get("changelog", ""),
            "published_at": latest_info.get("published_at", ""),
            "checked_at": now,
            "error": None,
        }

    # 更新缓存 / Update cache
    _cache = result.copy()
    _cache_time = now

    return result
