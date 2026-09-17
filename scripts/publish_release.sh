#!/usr/bin/env bash
# ============================================================
# publish_release.sh — 发布版本到自建下载中转服务器
# Publish release to self-hosted download relay server
#
# 用法 / Usage:
#   ./scripts/publish_release.sh <版本号> <构建产物目录> [服务器地址] [--base-url=<URL>]
#
# 示例 / Examples:
#   # 本地发布（文件复制到本地 data/downloads/） / Local publish (copy to local data/downloads/)
#   ./scripts/publish_release.sh 7.5.0 /path/to/build/artifacts
#
#   # 远程发布（rsync 到服务器） / Remote publish (rsync to server)
#   ./scripts/publish_release.sh 7.5.0 /path/to/build/artifacts root@47.160.10.194
#
#   # 指定下载基址 URL（生成绝对链接，桌面客户端需要） /
#   # Specify base URL for downloads (generates absolute URLs; required for desktop clients)
#   ./scripts/publish_release.sh 7.5.0 ./dist root@47.160.10.194 --base-url=http://47.160.10.194:8000
#
# 构建产物目录应包含 / Build artifacts directory should contain:
#   OpenMeetingScribe-7.5.0.exe      — Windows 安装器 / Windows installer
#   OpenMeetingScribe-7.5.0-mac.zip  — macOS 压缩包 / macOS archive
#
# 脚本会 / This script will:
#   1. 将构建产物复制到 data/downloads/ / Copy build artifacts to data/downloads/
#   2. 更新 remote_config.json 中的 latest_release 字段 / Update latest_release in remote_config.json
#   3. （远程模式）通过 rsync 同步到服务器 / (Remote mode) Sync to server via rsync
# ============================================================

set -euo pipefail

# ── 参数检查 / Argument validation ──
if [ $# -lt 2 ]; then
  echo "用法: $0 <版本号> <构建产物目录> [服务器地址]"
  echo "示例: $0 7.5.0 ./build/dist"
  echo "      $0 7.5.0 ./build/dist root@47.160.10.194"
  exit 1
fi

VERSION="$1"
BUILD_DIR="$2"
SERVER="${3:-}"
BASE_URL=""

# 解析 --base-url 参数 / Parse --base-url argument
for arg in "$@"; do
  case $arg in
    --base-url=*)
      BASE_URL="${arg#*=}"
      # 去掉末尾斜杠 / Strip trailing slash
      BASE_URL="${BASE_URL%/}"
      ;;
  esac
done

# 项目根目录 / Project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DOWNLOADS_DIR="$PROJECT_ROOT/data/downloads"
CONFIG_FILE="$PROJECT_ROOT/data/remote_config.json"

echo "============================================================"
echo "  发布版本 / Publishing release: v${VERSION}"
echo "  构建产物 / Build artifacts: ${BUILD_DIR}"
echo "  下载目录 / Downloads dir: ${DOWNLOADS_DIR}"
if [ -n "$SERVER" ]; then
  echo "  目标服务器 / Target server: ${SERVER}"
fi
if [ -n "$BASE_URL" ]; then
  echo "  下载基址 / Download base URL: ${BASE_URL}"
fi
echo "============================================================"
echo ""

# ── 1. 检查构建产物 / Check build artifacts ──
WINDOWS_FILE=""
MACOS_FILE=""

# 查找 Windows 安装包（.exe） / Find Windows installer (.exe)
for f in "$BUILD_DIR"/*.exe; do
  [ -f "$f" ] && WINDOWS_FILE="$(basename "$f")" && break
done

# 查找 macOS 压缩包（.zip） / Find macOS archive (.zip)
for f in "$BUILD_DIR"/*.zip; do
  [ -f "$f" ] && MACOS_FILE="$(basename "$f")" && break
done

if [ -z "$WINDOWS_FILE" ] && [ -z "$MACOS_FILE" ]; then
  echo "❌ 构建产物目录中未找到 .exe 或 .zip 文件"
  echo "   No .exe or .zip files found in build artifacts directory"
  exit 1
fi

echo "检测到构建产物 / Detected build artifacts:"
[ -n "$WINDOWS_FILE" ] && echo "  Windows: $WINDOWS_FILE"
[ -n "$MACOS_FILE" ] && echo "  macOS:   $MACOS_FILE"
echo ""

# ── 2. 复制到 data/downloads/ / Copy to data/downloads/ ──
mkdir -p "$DOWNLOADS_DIR"

if [ -n "$WINDOWS_FILE" ]; then
  cp "$BUILD_DIR/$WINDOWS_FILE" "$DOWNLOADS_DIR/"
  echo "✅ 已复制 / Copied: $WINDOWS_FILE → data/downloads/"
fi

if [ -n "$MACOS_FILE" ]; then
  cp "$BUILD_DIR/$MACOS_FILE" "$DOWNLOADS_DIR/"
  echo "✅ 已复制 / Copied: $MACOS_FILE → data/downloads/"
fi

echo ""

# ── 3. 更新 remote_config.json / Update remote_config.json ──
# 使用 Python 更新 JSON（保留 messages、feature_flags 等其他字段） /
# Use Python to update JSON (preserving messages, feature_flags, etc.)
python3 - "$CONFIG_FILE" "$VERSION" "$WINDOWS_FILE" "$MACOS_FILE" "$BASE_URL" <<'PYEOF'
import json
import sys
from datetime import datetime, timezone

config_file = sys.argv[1]
version = sys.argv[2]
windows_file = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else ""
macos_file = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else ""
base_url = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else ""

# 读取现有配置 / Read existing config
try:
    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {"messages": [], "feature_flags": [], "version": 0}

# 构造下载链接 / Build download URLs
# 有 base_url 时生成绝对链接（桌面客户端需要在系统浏览器中打开） /
# With base_url: generate absolute URLs (desktop client needs to open in system browser)
# 无 base_url 时使用相对路径（Web 客户端自动解析到当前服务器） /
# Without base_url: use relative paths (web client resolves to current server)
downloads = {}
if windows_file:
    path = f"/api/download/{windows_file}"
    downloads["windows"] = f"{base_url}{path}" if base_url else path
if macos_file:
    path = f"/api/download/{macos_file}"
    downloads["macos"] = f"{base_url}{path}" if base_url else path

# 更新 latest_release / Update latest_release
data.setdefault("latest_release", {})
data["latest_release"]["version"] = version
data["latest_release"]["downloads"] = downloads
data["latest_release"]["published_at"] = datetime.now(timezone.utc).isoformat()

# release_url 保留兼容（可手动填写 GitHub Release 页面） /
# release_url kept for compatibility (can be manually set to GitHub Release page)
if not data["latest_release"].get("release_url"):
    data["latest_release"]["release_url"] = ""

# 版本号递增 / Increment config version
data["version"] = data.get("version", 0) + 1

# 写回 / Write back
with open(config_file, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"✅ remote_config.json 已更新 / Updated:")
print(f"   version: {version}")
if windows_file:
    print(f"   downloads.windows: /api/download/{windows_file}")
if macos_file:
    print(f"   downloads.macos: /api/download/{macos_file}")
PYEOF

echo ""

# ── 4. 远程同步（可选） / Remote sync (optional) ──
if [ -n "$SERVER" ]; then
  echo "正在同步到服务器 / Syncing to server: ${SERVER} ..."

  # 同步下载文件 / Sync download files
  rsync -avz --progress "$DOWNLOADS_DIR/" "${SERVER}:/opt/meeting-scribe/data/downloads/"

  # 同步 remote_config.json / Sync remote_config.json
  rsync -avz "$CONFIG_FILE" "${SERVER}:/opt/meeting-scribe/data/remote_config.json"

  echo ""
  echo "✅ 已同步到服务器 / Synced to server: ${SERVER}"
  echo ""
  echo "如需重启服务使配置生效 / Restart service to apply changes:"
  echo "  ssh ${SERVER} 'systemctl restart meeting-scribe'"
else
  echo "💡 本地发布完成 / Local publish complete."
  echo "   如需同步到服务器，请运行 / To sync to server, run:"
  echo "   $0 ${VERSION} ${BUILD_DIR} root@<服务器IP>"
fi

echo ""
echo "============================================================"
echo "  ✅ 发布完成 / Publish complete!"
echo "============================================================"
