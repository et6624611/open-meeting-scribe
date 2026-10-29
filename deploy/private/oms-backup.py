#!/usr/bin/env python3
"""EP0-OPS 备份 sidecar：SQLite 在线快照 + blobs/secrets 打包 + 按天轮转。
升级脚本以 --once 做升级前强制备份；日常由 oms-backup 容器 --daemon 循环执行。
备份包含实例加密主密钥（secrets/），必须与 enterprise 数据同等保密，禁止外发云。"""
import os
import sqlite3
import tarfile
import time
from datetime import datetime
from pathlib import Path

SRC = Path("/data/oms")
OUT = Path("/data/backups")
INTERVAL = int(os.environ.get("OMS_BACKUP_INTERVAL_SEC", "86400"))
KEEP_DAYS = int(os.environ.get("OMS_BACKUP_KEEP_DAYS", "14"))


def backup_once() -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = OUT / f"instance_{ts}.db"
    db = SRC / "instance.db"
    if db.exists():
        src = sqlite3.connect(db)
        dst = sqlite3.connect(dest)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
    else:
        dest.touch()  # 尚未初始化，留占位保持轮转与审计节奏
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
