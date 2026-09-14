#!/usr/bin/env python3
"""
convert_icon.py — 将 icon.ico 转换为 macOS 所需的 icon.icns

在 macOS 上执行：python build/convert_icon.py
依赖 macOS 自带的 iconutil 工具（Xcode Command Line Tools）。

输出：build/icon.icns
"""

import struct
import sys
from pathlib import Path

# iconset 所需的标准 macOS 图标尺寸
ICON_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def extract_pngs_from_ico(ico_path: Path) -> dict[int, bytes]:
    """从 ICO 文件中提取各尺寸的 PNG 数据。

    ICO 格式：每个条目包含尺寸信息和 PNG/JPEG 压缩数据。
    现代 ICO 文件（如本项目的 icon.ico）内部存储的是完整 PNG 图像。

    Returns:
        {size: png_bytes} 字典
    """
    data = ico_path.read_bytes()

    # 解析 ICO 头部（6 字节）
    reserved, img_type, img_count = struct.unpack_from("<HHH", data, 0)
    if img_type != 1:
        raise ValueError(f"不是有效的 ICO 文件（type={img_type}）")

    results: dict[int, bytes] = {}

    for i in range(img_count):
        offset = 6 + i * 16
        w, h, colors, reserved2, planes, bpp, size, img_offset = struct.unpack_from(
            "<BBBBHHIH", data, offset
        )
        # ICO 中 0 表示 256
        actual_w = w if w != 0 else 256
        actual_h = h if h != 0 else 256

        # 检查是否为 PNG（以 PNG 签名开头）
        png_sig = b"\x89PNG\r\n\x1a\n"
        if data[img_offset : img_offset + 8] == png_sig:
            png_data = data[img_offset : img_offset + size]
            results[actual_w] = png_data

    return results


def create_iconset(pngs: dict[int, bytes], iconset_dir: Path) -> None:
    """创建 .iconset 目录，包含 macOS 所需的所有尺寸 PNG。

    macOS iconutil 要求的文件命名：
      icon_16x16.png, icon_16x16@2x.png, icon_32x32.png, ...
    """
    iconset_dir.mkdir(exist_ok=True)

    # 标准映射：(文件名, 源尺寸)
    mappings = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]

    written = set()
    for filename, needed_size in mappings:
        # 找到 >= needed_size 的最小可用尺寸
        available = sorted(pngs.keys())
        source_size = None
        for s in available:
            if s >= needed_size:
                source_size = s
                break
        if source_size is None and available:
            source_size = available[-1]  # 使用最大可用尺寸
        if source_size is None:
            continue

        out_path = iconset_dir / filename
        out_path.write_bytes(pngs[source_size])
        written.add(filename)

    print(f"  已写入 {len(written)} 个 PNG 到 {iconset_dir}")


def convert_ico_to_icns(ico_path: Path, icns_path: Path) -> bool:
    """将 .ico 转换为 .icns。

    流程：ICO → 提取 PNG → 创建 .iconset → iconutil 编译为 .icns

    Returns:
        True 表示成功
    """
    import shutil
    import subprocess

    print(f"读取 ICO: {ico_path}")
    pngs = extract_pngs_from_ico(ico_path)
    if not pngs:
        print("错误：未能从 ICO 中提取任何 PNG 图像")
        return False

    print(f"  提取到尺寸: {sorted(pngs.keys())}")

    # 创建临时 .iconset 目录
    iconset_dir = ico_path.parent / "icon.iconset"
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)

    create_iconset(pngs, iconset_dir)

    # 使用 macOS iconutil 编译为 .icns
    print("运行 iconutil 编译 .icns...")
    if icns_path.exists():
        icns_path.unlink()

    result = subprocess.run(
        ["iconutil", "--convert", "icns", "--output", str(icns_path), str(iconset_dir)],
        capture_output=True,
        text=True,
    )

    # 清理临时目录
    shutil.rmtree(iconset_dir, ignore_errors=True)

    if result.returncode != 0:
        print(f"iconutil 失败: {result.stderr}")
        return False

    size_kb = icns_path.stat().st_size / 1024
    print(f"✓ 生成 {icns_path} ({size_kb:.1f} KB)")
    return True


def main():
    root = Path(__file__).parent.parent
    ico_path = root / "build" / "icon.ico"
    icns_path = root / "build" / "icon.icns"

    if not ico_path.exists():
        print(f"错误：找不到 {ico_path}")
        sys.exit(1)

    # 检查 iconutil 是否可用
    if shutil.which("iconutil") is None:
        print("错误：iconutil 不可用（需要 macOS + Xcode Command Line Tools）")
        sys.exit(1)

    success = convert_ico_to_icns(ico_path, icns_path)
    if not success:
        sys.exit(1)

    print("图标转换完成 ✓")


if __name__ == "__main__":
    import shutil

    main()
