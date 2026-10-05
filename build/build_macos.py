"""
Open Meeting Scribe — macOS 打包脚本
在 macOS 上执行：python build/build_macos.py

职责：
1. 检查环境（Python 版本、iconutil）
2. 转换图标（.ico → .icns）
3. 下载 ffmpeg（macOS 版）
4. 运行 PyInstaller 打包
5. 组装分发物（.app + ffmpeg + 启动器）
6. 创建 ZIP 分发包
"""

import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────
PYTHON_MIN_VERSION = (3, 11)
DIST_DIR = Path("dist/OpenMeetingScribe-macOS")
# ffmpeg 下载 URL（macOS 64-bit，来自 evermeet.cx — macOS 专用 ffmpeg 发布）
FFMPEG_URL = "https://evermeet.cx/ffmpeg/getrelease/zip"
# ─────────────────────────────────────────────────────


def check_environment():
    """检查构建环境"""
    # Python 版本
    v = sys.version_info[:2]
    if v < PYTHON_MIN_VERSION:
        print(f"错误：需要 Python {PYTHON_MIN_VERSION[0]}.{PYTHON_MIN_VERSION[1]}+，当前 {v[0]}.{v[1]}")
        sys.exit(1)
    print(f"Python {v[0]}.{v[1]} ✓")

    # 平台检查
    if sys.platform != "darwin":
        print(f"错误：macOS 打包脚本不能在 {sys.platform} 上运行")
        sys.exit(1)
    print(f"平台: macOS {platform.mac_ver()[0]} ({platform.machine()}) ✓")

    # iconutil 检查
    if shutil.which("iconutil") is None:
        print("错误：iconutil 不可用，请安装 Xcode Command Line Tools")
        print("  xcode-select --install")
        sys.exit(1)
    print("iconutil ✓")


def convert_icon():
    """将 icon.ico 转换为 icon.icns"""
    icns_path = Path("build/icon.icns")
    if icns_path.exists():
        print("icon.icns 已存在，跳过转换")
        return

    print("转换图标 .ico → .icns...")
    subprocess.check_call([sys.executable, "build/convert_icon.py"])
    if not icns_path.exists():
        print("错误：图标转换失败，icon.icns 未生成")
        sys.exit(1)
    print("图标转换完成 ✓")


def download_ffmpeg():
    """下载 ffmpeg macOS 版"""
    ffmpeg_dir = DIST_DIR / "ffmpeg"
    ffmpeg_bin = ffmpeg_dir / "ffmpeg"

    if ffmpeg_bin.exists():
        print("ffmpeg 已存在，跳过下载")
        return

    print("下载 ffmpeg (macOS)...")
    zip_path = Path("build/ffmpeg-macos.zip")
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        urllib.request.urlretrieve(FFMPEG_URL, str(zip_path))
        print(f"下载完成：{zip_path.stat().st_size / 1024 / 1024:.1f} MB")
    except Exception as e:
        print(f"下载失败: {e}")
        print("请手动下载 ffmpeg 并放置到 dist/OpenMeetingScribe-macOS/ffmpeg/ffmpeg")
        return

    print("解压 ffmpeg...")
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith("/ffmpeg") or name == "ffmpeg":
                    data = zf.read(name)
                    ffmpeg_bin.write_bytes(data)
                    # 设置可执行权限
                    ffmpeg_bin.chmod(0o755)
                    print("ffmpeg 提取完成 ✓")
                    break
            else:
                print("警告：未在压缩包中找到 ffmpeg，请手动放置")
    except zipfile.BadZipFile:
        # evermeet.cx 可能直接返回二进制而非 zip
        print("下载文件非 ZIP 格式，尝试直接使用...")
        ffmpeg_bin.write_bytes(zip_path.read_bytes())
        ffmpeg_bin.chmod(0o755)
        print("ffmpeg 就位 ✓")

    if zip_path.exists():
        zip_path.unlink()


def run_pyinstaller():
    """运行 PyInstaller 打包"""
    spec_file = Path("build/pyinstaller_macos.spec")

    print("运行 PyInstaller...")
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_file),
    ])

    # 检查 .app 是否生成
    app_path = Path("dist/OpenMeetingScribe.app")
    if not app_path.exists():
        print("错误：OpenMeetingScribe.app 未生成")
        sys.exit(1)

    size_mb = sum(f.stat().st_size for f in app_path.rglob("*") if f.is_file()) / 1024 / 1024
    print(f"PyInstaller 打包完成 ✓ ({size_mb:.1f} MB)")


def assemble_distribution():
    """组装分发物"""
    print("组装分发物...")

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 移动 .app 到分发目录
    app_src = Path("dist/OpenMeetingScribe.app")
    app_dst = DIST_DIR / "OpenMeetingScribe.app"
    if app_dst.exists():
        shutil.rmtree(app_dst)
    shutil.move(str(app_src), str(app_dst))
    print("OpenMeetingScribe.app 就位 ✓")

    # 复制启动器
    launcher_src = Path("build/launcher_macos.sh")
    launcher_dst = DIST_DIR / "启动会议助手.command"
    if launcher_src.exists():
        shutil.copy(str(launcher_src), str(launcher_dst))
        # 设置可执行权限
        launcher_dst.chmod(0o755)
        print("启动器就位 ✓")

    # 复制 .env 模板
    env_src = Path(".env.example")
    env_dst = DIST_DIR / ".env"
    if env_src.exists() and not env_dst.exists():
        shutil.copy(str(env_src), str(env_dst))
        print(".env 模板就位 ✓")

    # 创建数据目录
    for subdir in ["data/output", "data/recordings", "data/tasks", "data/uploads"]:
        (DIST_DIR / subdir).mkdir(parents=True, exist_ok=True)
    print("数据目录创建完成 ✓")

    # 创建使用说明
    readme = DIST_DIR / "使用说明.txt"
    readme.write_text(
        "Open Meeting Scribe — 使用说明\n"
        "════════════════════════════════\n\n"
        "1. 双击「启动会议助手.command」启动应用\n"
        "2. 首次使用需配置 DashScope API Key\n"
        "   编辑 .env 文件，填入你的 Key\n\n"
        "注意事项：\n"
        "- 需要联网使用（ASR 和纪要生成走云端）\n"
        "- 声纹识别走云端服务，无需本地模型\n"
        "- 录音文件保存在 data/ 目录下\n"
        "- 系统内录需要安装 BlackHole 2ch 虚拟声卡\n"
        "- 首次打开如被 Gatekeeper 拦截，请右键→打开\n",
        encoding="utf-8",
    )
    print("使用说明生成 ✓")


def create_zip():
    """创建分发 ZIP"""
    zip_name = "OpenMeetingScribe-macOS.zip"
    print(f"创建分发包：{zip_name}")

    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(DIST_DIR):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(DIST_DIR.parent)
                zf.write(file_path, arcname)

    size_mb = Path(zip_name).stat().st_size / 1024 / 1024
    print(f"分发包创建完成：{zip_name} ({size_mb:.1f} MB) ✓")


def main():
    print("=" * 50)
    print("Open Meeting Scribe — macOS 打包")
    print("=" * 50)

    check_environment()
    convert_icon()
    run_pyinstaller()
    assemble_distribution()
    download_ffmpeg()
    create_zip()

    print("\n" + "=" * 50)
    print("打包完成！")
    print(f"分发目录：{DIST_DIR.resolve()}")
    print(f"分发包：{Path('OpenMeetingScribe-macOS.zip').resolve()}")
    print("=" * 50)
    print()
    print("提示：如首次打开被 Gatekeeper 拦截，请右键→打开")


if __name__ == "__main__":
    main()
