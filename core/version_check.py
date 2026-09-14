"""
core/version_check.py — 版本检查与比对 / Version checking and comparison

职责 / Responsibilities:
  1. 读取本地 VERSION 文件获取当前版本 / Read local VERSION file for current version
  2. 从远端（GitHub Releases 或自定义 API）获取最新版本 / Fetch latest version from remote (GitHub Releases or custom API)
  3. 语义化版本比对（semver） / Semantic version comparison (semver)
  4. 返回结构化的版本检查结果 / Return structured version check result

设计说明 / Design notes:
  - 远端来源可配置：优先使用 settings.json 中的 update_url / Remote source configurable: prefer update_url in settings.json,
    默认回退到 GitHub Releases API / fallback to GitHub Releases API by default
  - 结果缓存 30 分钟，避免频繁请求 / Results cached for 30 minutes to avoid frequent requests
  - 网络失败时静默降级，不影响应用正常使用 / Silent degradation on network failure; does not affect normal app usage
"""

import json
import logging
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# 本地 VERSION 文件路径 / Local VERSION file path
VERSION_FILE = Path(__file__).parent.parent / "VERSION"

# 默认 GitHub Releases API（项目发布后替换为实际地址） / Default GitHub Releases API (replace after project release)
DEFAULT_RELEASES_URL = "https://api.github.com/repos/open-meeting-scribe/open-meeting-scribe/releases/latest"

# 缓存有效期（秒） / Cache TTL (seconds)
CACHE_TTL = 1800  # 30 分钟 / 30 minutes

# 请求超时（秒） / Request timeout (seconds)
REQUEST_TIMEOUT = 8

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


def _get_release_url(settings: dict | None = None) -> str:
    """从设置中获取远端版本检查 URL / Get remote version check URL from settings."""
    if settings:
        update_cfg = settings.get("update", {})
        url = update_cfg.get("releases_url", "").strip()
        if url:
            return url
    return DEFAULT_RELEASES_URL


def _fetch_latest_from_github(url: str) -> dict | None:
    """
    从 GitHub Releases API 获取最新版本信息 / Fetch latest version info from GitHub Releases API.
    返回格式 / Returns:
      {
        "version": "2.1.0",
        "release_url": "https://github.com/.../releases/tag/v2.1.0",
        "changelog": "...",
        "published_at": "2026-09-07T..."
      }
    """
    try:
        resp = requests.get(
            url,
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("GitHub Releases API 返回 %d", resp.status_code)
            return None

        data = resp.json()
        tag = data.get("tag_name", "")
        version = tag.lstrip("v").strip()
        if not version:
            return None

        return {
            "version": version,
            "release_url": data.get("html_url", ""),
            "changelog": data.get("body", ""),
            "published_at": data.get("published_at", ""),
        }
    except requests.RequestException as e:
        logger.warning("获取最新版本信息失败: %s", e)
        return None
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("解析版本信息失败: %s", e)
        return None


def check_for_update(settings: dict | None = None, force: bool = False) -> dict:
    """
    检查是否有新版本可用 / Check if a new version is available.

    Args:
        settings: 应用设置（可选），用于获取自定义 releases_url / App settings (optional); for custom releases_url
        force: 是否强制刷新（忽略缓存） / Force refresh (ignore cache)

    Returns:
        {
            "current_version": "1.0.0",
            "latest_version": "2.1.0" | null,
            "update_available": true | false,
            "release_url": "https://...",
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

    # 从远端获取最新版本 / Fetch latest version from remote
    release_url = _get_release_url(settings)
    latest_info = _fetch_latest_from_github(release_url)

    if not latest_info:
        result = {
            "current_version": current,
            "latest_version": None,
            "update_available": False,
            "release_url": "",
            "changelog": "",
            "published_at": "",
            "checked_at": now,
            "error": "无法获取最新版本信息",
        }
    else:
        latest_ver = latest_info["version"]
        result = {
            "current_version": current,
            "latest_version": latest_ver,
            "update_available": compare_versions(current, latest_ver) > 0,
            "release_url": latest_info.get("release_url", ""),
            "changelog": latest_info.get("changelog", ""),
            "published_at": latest_info.get("published_at", ""),
            "checked_at": now,
            "error": None,
        }

    # 更新缓存 / Update cache
    _cache = result.copy()
    _cache_time = now

    return result
