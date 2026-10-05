"""
Open Meeting Scribe — Windows 打包脚本
在 Windows 上执行：python build/build_windows.py

职责：
1. 创建虚拟环境 + 安装依赖
2. 下载 ffmpeg（Windows 版）
3. 运行 PyInstaller 打包
4. 组装分发物（exe + ffmpeg + 启动器）
"""

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────
PYTHON_MIN_VERSION = (3, 11)
FFMPEG_VERSION = "7.1"
FFMPEG_URL = "https://github.com/BtbN/ffmpeg-builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
DIST_DIR = Path("dist/OpenMeetingScribe")
# ─────────────────────────────────────────────────────


def check_python_version():
    """检查 Python 版本"""
    v = sys.version_info[:2]
    if v < PYTHON_MIN_VERSION:
        print(f"错误：需要 Python {PYTHON_MIN_VERSION[0]}.{PYTHON_MIN_VERSION[1]}+，当前 {v[0]}.{v[1]}")
        sys.exit(1)
    print(f"Python {v[0]}.{v[1]} ✓")


def setup_venv():
    """创建虚拟环境并安装依赖"""
    venv_dir = Path("build_venv")
    if venv_dir.exists():
        print("虚拟环境已存在，跳过创建")
    else:
        print("创建虚拟环境...")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])

    pip = venv_dir / "Scripts" / "pip.exe"
    print("安装依赖...")
    subprocess.check_call([str(pip), "install", "--upgrade", "pip"])
    subprocess.check_call([str(pip), "install", "-r", "requirements.txt"])
    subprocess.check_call([str(pip), "install", "pyinstaller"])
    print("依赖安装完成 ✓")
    return venv_dir


def download_ffmpeg():
    """下载 ffmpeg Windows 版"""
    ffmpeg_dir = DIST_DIR / "ffmpeg"
    ffmpeg_exe = ffmpeg_dir / "ffmpeg.exe"

    if ffmpeg_exe.exists():
        print("ffmpeg 已存在，跳过下载")
        return

    print("下载 ffmpeg...")
    zip_path = Path("build/ffmpeg.zip")
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    urllib.request.urlretrieve(FFMPEG_URL, zip_path)
    print(f"下载完成：{zip_path.stat().st_size / 1024 / 1024:.1f} MB")

    print("解压 ffmpeg...")
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for name in zf.namelist():
            if name.endswith('/bin/ffmpeg.exe'):
                data = zf.read(name)
                ffmpeg_exe.write_bytes(data)
                print("ffmpeg.exe 提取完成 ✓")
                break
        else:
            print("警告：未在压缩包中找到 ffmpeg.exe，请手动放置")

    zip_path.unlink()


def run_pyinstaller(venv_dir):
    """运行 PyInstaller 打包"""
    pyinstaller = venv_dir / "Scripts" / "pyinstaller.exe"
    spec_file = Path("build/pyinstaller.spec")

    print("运行 PyInstaller...")
    subprocess.check_call([
        str(pyinstaller),
        "--clean",
        "--noconfirm",
        str(spec_file),
    ])
    print("PyInstaller 打包完成 ✓")


def assemble_distribution():
    """组装分发物"""
    print("组装分发物...")

    # 创建分发目录
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 移动 PyInstaller 输出
    exe_src = Path("dist/OpenMeetingScribe.exe")
    exe_dst = DIST_DIR / "OpenMeetingScribe.exe"
    if exe_src.exists():
        shutil.move(str(exe_src), str(exe_dst))
        print("OpenMeetingScribe.exe 就位 ✓")

    # 复制启动器
    launcher_src = Path("build/launcher.bat")
    launcher_dst = DIST_DIR / "启动.bat"
    if launcher_src.exists():
        shutil.copy(str(launcher_src), str(launcher_dst))
        print("启动器就位 ✓")

    # 复制 .env 模板
    env_src = Path(".env.example")
    env_dst = DIST_DIR / ".env"
    if env_src.exists() and not env_dst.exists():
        shutil.copy(str(env_src), str(env_dst))
        print(".env 模板就位 ✓")

    # 创建数据目录
    (DIST_DIR / "data").mkdir(exist_ok=True)
    (DIST_DIR / "data" / "output").mkdir(exist_ok=True)
    (DIST_DIR / "data" / "recordings").mkdir(exist_ok=True)
    (DIST_DIR / "data" / "tasks").mkdir(exist_ok=True)
    (DIST_DIR / "data" / "uploads").mkdir(exist_ok=True)
    print("数据目录创建完成 ✓")

    # 创建使用说明
    readme = DIST_DIR / "使用说明.txt"
    readme.write_text(
        "会议助手 — 使用说明\n"
        "════════════════════\n\n"
        "1. 双击「启动.bat」启动服务\n"
        "2. 浏览器自动打开 http://127.0.0.1:8000\n"
        "3. 首次使用需配置 DashScope API Key\n"
        "   编辑 .env 文件，填入你的 Key\n\n"
        "注意事项：\n"
        "- 需要联网使用（ASR 和纪要生成走云端）\n"
        "- 声纹识别走云端服务，无需本地模型\n"
        "- 录音文件保存在 data/ 目录下\n"
        "- 关闭控制台窗口即停止服务\n",
        encoding="utf-8"
    )
    print("使用说明生成 ✓")


def create_zip():
    """创建分发 ZIP"""
    zip_name = "OpenMeetingScribe-Windows.zip"
    print(f"创建分发包：{zip_name}")

    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(DIST_DIR):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(DIST_DIR.parent)
                zf.write(file_path, arcname)

    size_mb = Path(zip_name).stat().st_size / 1024 / 1024
    print(f"分发包创建完成：{zip_name} ({size_mb:.1f} MB) ✓")


def main():
    print("=" * 50)
    print("Open Meeting Scribe — Windows 打包")
    print("=" * 50)

    check_python_version()
    venv_dir = setup_venv()
    run_pyinstaller(venv_dir)
    download_ffmpeg()
    assemble_distribution()
    create_zip()

    print("\n" + "=" * 50)
    print("打包完成！")
    print(f"分发目录：{DIST_DIR.resolve()}")
    print(f"分发包：{Path('OpenMeetingScribe-Windows.zip').resolve()}")
    print("=" * 50)


if __name__ == "__main__":
    main()
