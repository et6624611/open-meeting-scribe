"""AC-7 — 云包冻结依赖图侵入扫描（WP-G G-6 / ci-local-engine-v2 体积守护）。

对 PyInstaller 构建产生的 Analysis TOC（build/**/Analysis-*.toc）做结构化解析，
确认云精简主包冻结图不含本地引擎组件（torch / torchaudio / funasr / modelscope）。

为什么不用 Select-String 直接 grep（历史缺陷）：TOC 里同时序列化了 spec 的
``excludes=['torch','torchaudio',...]`` 列表——文本 grep 会把「排除项」误报为
「侵入项」（2026-09-24 首次绿灯运行的实测误报）。本脚本只统计 TOC 条目元组
``(name, path, typecode)`` 的 name 字段，天然跳过 excludes 字符串列表。

用法：
    python toc_scan.py --build-dir build
退出码：0=无侵入；1=发现侵入；2=未找到 TOC（守护降级，由体积阈值兜底，打印 WARN）。
"""

import argparse
import ast
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

FORBIDDEN = ("torch", "torchaudio", "funasr", "modelscope")


def iter_entry_names(node):
    """递归收集 TOC 条目名：只取元组首元素（(name, path, typecode) 形态）。

    纯字符串列表（如 excludes）与 dict 中 excludes 键下的内容一律跳过。
    """
    if isinstance(node, tuple):
        if node and isinstance(node[0], str) and all(isinstance(x, str) for x in node):
            yield node[0]
            return
        for child in node:
            yield from iter_entry_names(child)
    elif isinstance(node, list):
        for child in node:
            yield from iter_entry_names(child)
    elif isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and key.lower() in ("excludes", "hookspath", "hooksconfig"):
                continue
            yield from iter_entry_names(value)


def scan_toc(path: Path) -> list[str]:
    data = ast.literal_eval(path.read_text(encoding="utf-8"))
    violations = []
    for name in iter_entry_names(data):
        root = name.split(".")[0]
        if root in FORBIDDEN:
            violations.append(name)
    return violations


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", default="build")
    args = ap.parse_args()

    tocs = sorted(Path(args.build_dir).rglob("Analysis-*.toc"))
    if not tocs:
        print("[GUARD] WARN: 未找到 Analysis TOC，冻结图扫描降级跳过（体积阈值仍兜底）")
        return 2

    total = 0
    for toc in tocs:
        try:
            violations = scan_toc(toc)
        except (SyntaxError, ValueError) as e:
            print(f"[GUARD] WARN: {toc} 解析失败（{e}），按文本兜底扫描")
            text = toc.read_text(encoding="utf-8", errors="replace")
            violations = [
                f"text-fallback:{pkg}" for pkg in FORBIDDEN
                if f"('{pkg}." in text or f"('{pkg}'," in text
            ]
        total += len(violations)
        if violations:
            print(f"[GUARD] FAIL: {toc} 冻结图侵入 {len(violations)} 条（前 20）:")
            for v in violations[:20]:
                print(f"  {v}")
        else:
            print(f"[GUARD] {toc}: 无本地引擎组件侵入")

    if total:
        print(f"[GUARD] 冻结图侵入扫描 FAIL（共 {total} 条）")
        return 1
    print("[GUARD] 冻结图侵入扫描 PASS")
    return 0


if __name__ == "__main__":
    code = main()
    sys.exit(0 if code in (0, 2) else code)
