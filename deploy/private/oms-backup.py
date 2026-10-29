#!/usr/bin/env python3
"""EP0-OPS 备份 sidecar：SQLite 在线快照 + blobs/secrets 打包 + 按天轮转。
升级脚本以 --once 做升级前强制备份；日常由 oms-backup 容器 --daemon 循环执行。
备份包含实例加密主密钥（secrets/），必须与 enterprise 数据同等保密，禁止外发云。
快照一致性优先走后端冻结封装 `python -m app.db backup-snapshot <dest>`（契约 cmsg_01m63g5cjyn5pb3j7gqxycsedn），
封装缺失时回退 python sqlite3 在线备份 API（同为 .backup 语义，不裸拷 .db，不依赖 sqlite3 CLI）。"""
import os
import sqlite3
import subprocess
import tarfile
import time
from datetime import datetime
from pathlib import Path

SRC = Path("/data/oms")
OUT = Path("/data/backups")
INTERVAL = int(os.environ.get("OMS_BACKUP_INTERVAL_SEC", "86400"))
KEEP_DAYS = int(os.environ.get("OMS_BACKUP_KEEP_DAYS", "14"))


def snapshot_instance_db(dest: Path) -> None:
    db = SRC / "instance.db"
    if not db.exists():
        dest.touch()  # 尚未初始化，留占位保持轮转与审计节奏
        return
    r = subprocess.run(
        ["python", "-m", "app.db", "backup-snapshot", str(dest)],
        env={**os.environ, "OMS_DATA_ROOT": str(SRC)},
        capture_output=True,
        text=True,
    )
    if r.returncode == 0 and dest.exists():
        return
    if dest.exists():
        dest.unlink()
    src = sqlite3.connect(db)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()


def backup_once() -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = OUT / f"instance_{ts}.db"
    snapshot_instance_db(dest)
    snap = OUT / f"snap_{ts}.tar.gz"
    with tarfile.open(snap, "w:gz") as tf:
        for name in ("blobs", "secrets"):
            p = SRC / name
            if p.exists():
                tf.add(p, arcname=name)
    cutoff = time.time() - KEEP_DAYS * 86400
    for f in list(OUT.glob("instance_*.db")) + list(OUT.glob("snap_*.tar.gz")):
        if f.stat().st_mtime < cutoff:
            f.unlink()
    print(f"[oms-backup] {ts}: {dest.name} + {snap.name} 完成", flush=True)


if __name__ == "__main__":
    import sys

    OUT.mkdir(parents=True, exist_ok=True)
    if "--daemon" in sys.argv:
        while True:
            try:
                backup_once()
            except Exception as exc:  # noqa: BLE001
                print(f"[oms-backup] 错误：{exc}", flush=True)
            time.sleep(INTERVAL)
    else:
        backup_once()
