#!/usr/bin/env python3
"""
build/make_engine_manifest.py — 引擎包 engine-manifest.json 生成器（R8 / WP-G，D-G1 子项①）

用法（引擎包构建完成后）：
    python build/make_engine_manifest.py --dist dist/OMSEngine [--protocol-version 1]

产物：<引擎根>/engine-manifest.json，字段：
    component         固定 "oms-local-engine"
    engine_version    取自项目根 VERSION 文件
    protocol_version  与 core/engine_worker.py PROTOCOL_VERSION 同源（默认从源码读取）
    platform          win-amd64 / macos-arm64 / macos-x86_64 / linux-x86_64 ...
    entry             引擎可执行体文件名（OMSEngine.exe / OMSEngine）
    built_at          UTC ISO 时间戳
    total_size_bytes  全部文件体积和
    files             {相对路径: {"sha256":..., "size":...}}（含可执行体与 _internal/ 全量）

三条安装通道（应用内引导下载 / Win Inno 组件 / 内网离线包）共用本 manifest：
安装侧按 files 逐文件校验 SHA256（core/engine_installer.py）。
"""

import argparse
import hashlib
import json
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHUNK = 1024 * 1024


def read_engine_version() -> str:
    version_file = ROOT / "VERSION"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    return "0.0.0"


def read_protocol_version() -> int:
    """从 core/engine_worker.py 源码读取 PROTOCOL_VERSION（不 import，避免拉起重依赖）。"""
    src = (ROOT / "core" / "engine_worker.py").read_text(encoding="utf-8")
    m = re.search(r"^PROTOCOL_VERSION\s*=\s*(\d+)", src, re.MULTILINE)
    if not m:
        raise SystemExit("无法从 core/engine_worker.py 解析 PROTOCOL_VERSION")
    return int(m.group(1))


def platform_tag() -> str:
    system = platform.system().lower()  # windows / darwin / linux
    machine = platform.machine().lower()  # amd64 / arm64 / x86_64 / aarch64
    if system == "windows":
        machine = "amd64" if machine in ("amd64", "x86_64") else machine
    return f"{system}-{machine}"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(dist_dir: Path, protocol_version: int | None = None) -> dict:
    if not dist_dir.is_dir():
        raise SystemExit(f"引擎包目录不存在: {dist_dir}")

    entry = "OMSEngine.exe" if sys.platform == "win32" else "OMSEngine"
    if not (dist_dir / entry).is_file():
        # 允许在异平台 CI 上生成（如 win 产物在 mac 上打包 zip）：按实际文件探测
        found = [p.name for p in dist_dir.iterdir() if p.name.startswith("OMSEngine") and p.is_file()]
        if not found:
            raise SystemExit(f"引擎可执行体不存在于 {dist_dir}（期望 {entry}）")
        entry = found[0]

    files: dict[str, dict] = {}
    total = 0
    for p in sorted(dist_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(dist_dir).as_posix()
        if rel == "engine-manifest.json":
            continue  # manifest 自身不参与自校验
        digest = sha256_of(p)
        size = p.stat().st_size
        total += size
        files[rel] = {"sha256": digest, "size": size}

    return {
        "component": "oms-local-engine",
        "engine_version": read_engine_version(),
        "protocol_version": protocol_version if protocol_version is not None else read_protocol_version(),
        "platform": platform_tag(),
        "entry": entry,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_size_bytes": total,
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成引擎包 engine-manifest.json")
    parser.add_argument("--dist", default="dist/OMSEngine", help="onedir 引擎包根目录")
    parser.add_argument("--protocol-version", type=int, default=None, help="覆盖协议版本（默认读源码）")
    parser.add_argument("--out", default=None, help="manifest 输出路径（默认 <dist>/engine-manifest.json）")
    args = parser.parse_args()

    dist_dir = Path(args.dist).resolve()
    manifest = build_manifest(dist_dir, args.protocol_version)
    out = Path(args.out) if args.out else dist_dir / "engine-manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"[manifest] {out} — version={manifest['engine_version']} "
        f"protocol={manifest['protocol_version']} platform={manifest['platform']} "
        f"files={len(manifest['files'])} total={manifest['total_size_bytes']/1024/1024:.1f}MB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
