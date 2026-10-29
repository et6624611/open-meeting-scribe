"""助手本地数据目录面（EP0-BE 增量5 前置片，契约 §1.8/§4 v1.1）。

边界（如实口径）：个人版全部存储路径现仍相对进程 CWD 的 data/ 目录（v10 债务，不在今晚重构）；
本片提供 只读用量 + 安全迁移（复制-校验-保留源）+ 切换意向登记，
真正把助手数据根切到目标目录由重启时注入 OMS_DATA_ROOT 完成（DevOps 手册/桌面启动参数）。
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from app.db.config import resolve_data_root


def _dir_bytes(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and f.is_symlink() is False)


def storage_snapshot(dr=None) -> dict:
    dr = dr or resolve_data_root()
    root = Path(dr.root)
    recordings = root / "recordings"
    tasks = root / "tasks"
    st = None
    try:
        st = shutil.disk_usage(root if root.exists() else root.parent)
    except OSError:
        pass
    return {
        "data_dir": str(root),
        "exists": root.exists(),
        "writable": _writable(root),
        "total_bytes": _dir_bytes(root) if root.exists() else 0,
        "recordings_bytes": _dir_bytes(recordings) if recordings.exists() else 0,
        "tasks_files": len(list(tasks.glob("*.json"))) if tasks.exists() else 0,
        "disk_free_bytes": st.free if st else None,
    }


def _writable(root: Path) -> bool:
    try:
        probe = (root if root.exists() else root.parent) / ".oms_write_probe"
        probe.write_text("1")
        probe.unlink()
        return True
    except OSError:
        return False


def migrate_data_dir(*, target: str, dr=None) -> dict:
    """复制-校验-保留源迁移当前数据目录到 target；登记切换意向供重启生效。幂等：同名同大小文件跳过。"""
    src = Path((dr or resolve_data_root()).root).resolve()
    dst = Path(target).expanduser().resolve()
    if not src.exists():
        raise ValueError("源数据目录不存在")
    if dst == src:
        raise ValueError("目标目录与当前目录相同")
    if str(dst).startswith(str(src) + "/") or str(src).startswith(str(dst) + "/"):
        raise ValueError("目标目录与当前目录嵌套，拒绝迁移")
    dst.mkdir(parents=True, exist_ok=True)
    copied = skipped = 0
    failed: list[str] = []
    for f in sorted(src.rglob("*")):
        if not f.is_file() or f.name == ".oms_migrated":
            continue
        rel = f.relative_to(src)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and out.stat().st_size == f.stat().st_size and _sha_head(f) == _sha_head(out):
            skipped += 1
            continue
        try:
            tmp = out.with_name(out.name + ".tmp")
            shutil.copy2(f, tmp)
            tmp.replace(out)
            copied += 1
        except OSError as exc:
            failed.append(f"{rel}: {type(exc).__name__}")
    report = {
        "source": str(src),
        "target": str(dst),
        "copied": copied,
        "skipped_identical": skipped,
        "failed": failed,
        "source_retained": True,
        "activation": "重启助手进程并注入 OMS_DATA_ROOT=<target>（DevOps 手册/桌面启动参数）后生效",
    }
    if not failed:
        (dst / ".oms_migrated").write_text(repr(report), encoding="utf-8")
    return report


def _sha_head(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        h.update(fh.read(1 << 16))
        h.update(str(p.stat().st_size).encode())
    return h.hexdigest()
