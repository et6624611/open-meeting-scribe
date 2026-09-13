"""
core/fs_atomic.py — 原子文件写入工具

职责：
  以「写同目录临时文件 → flush + fsync → 原子 rename 覆盖」的方式落盘，
  避免进程崩溃/断电时产生半截 JSON 文件导致持久化数据损坏；
  并对同一文件的并发写做进程内串行化，减少互相覆盖的风险。

设计：
  - 临时文件与目标文件同目录，保证 os.replace 是同一文件系统内的原子操作。
  - 按解析后的绝对路径持有一把 threading.Lock，串行化同文件写入。
  - 写入失败时清理临时文件，异常向上冒泡（不吞掉业务错误）。
"""

import json
import os
import tempfile
import threading
from pathlib import Path

# 按文件绝对路径持有的写入锁，串行化同一文件的并发写
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _get_lock(path: Path) -> threading.Lock:
    """获取（或惰性创建）指定路径的写入锁"""
    key = str(path.resolve())
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def atomic_write_text(path, content: str, encoding: str = "utf-8") -> None:
    """
    原子写入文本文件。

    先写入同目录下的临时文件并 fsync 落盘，再通过 os.replace 原子覆盖目标，
    确保读者要么看到旧内容、要么看到完整新内容，不会读到半截文件。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _get_lock(path)
    with lock:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding=encoding) as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            # 写入失败清理临时文件，避免残留垃圾
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise


def atomic_write_json(path, data, encoding: str = "utf-8", indent: int = 2) -> None:
    """原子写入 JSON 文件（ensure_ascii=False，保留中文可读性）"""
    content = json.dumps(data, ensure_ascii=False, indent=indent)
    atomic_write_text(path, content, encoding=encoding)
