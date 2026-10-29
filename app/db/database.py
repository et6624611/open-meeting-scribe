"""SQLite 连接与迁移 runner（契约 §2.1/§7：additive-only、幂等、事务化）。"""
from __future__ import annotations

import datetime as _dt
import re
import sqlite3
from pathlib import Path
from typing import Iterable

from .config import DataRoot

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_MIGRATION_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


def utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def connect(dr: DataRoot) -> sqlite3.Connection:
    dr.root.mkdir(parents=True, exist_ok=True)
    dr.blobs_dir.mkdir(parents=True, exist_ok=True)
    # 企业实例经 FastAPI 线程池执行同步端点：连接跨线程共享（CPython libsqlite3 为 serialized 模式），
    # 写路径另以 WAL + busy_timeout 串行化；个人版代码路径不经本模块。
    conn = sqlite3.connect(dr.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "  version INTEGER PRIMARY KEY,"
        "  name TEXT NOT NULL,"
        "  applied_at TEXT NOT NULL)"
    )


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    _ensure_meta(conn)
    return {r["version"] for r in conn.execute("SELECT version FROM schema_version")}


def discover_migrations(migrations_dir: Path | None = None) -> list[tuple[int, str, Path]]:
    d = migrations_dir or MIGRATIONS_DIR
    out: list[tuple[int, str, Path]] = []
    for p in sorted(d.glob("*.sql")):
        m = _MIGRATION_NAME.match(p.name)
        if not m:
            raise ValueError(f"非法迁移文件名: {p.name}（需 0001_name.sql）")
        out.append((int(m.group(1)), p.stem, p))
    versions = [v for v, _, _ in out]
    if len(set(versions)) != len(versions):
        raise ValueError("迁移版本号重复")
    return out


def _split_sql_statements(sql: str) -> Iterable[str]:
    """按完整语句切分（sqlite3.complete_statement），避免 executescript 的隐式 commit 破坏事务原子性。"""
    buf: list[str] = []
    for line in sql.splitlines(keepends=True):
        buf.append(line)
        joined = "".join(buf)
        if sqlite3.complete_statement(joined):
            stmt = joined.strip().rstrip(";").strip()
            if stmt:
                yield stmt
            buf = []
    rest = "".join(buf).strip()
    if rest and sqlite3.complete_statement(rest + ";"):
        yield rest.rstrip(";").strip()


def migrate(conn: sqlite3.Connection, migrations_dir: Path | None = None) -> list[str]:
    """按序应用未执行的迁移；每个迁移单事务，失败即回滚中止（不切流）。

    幂等：重复执行为 no-op。返回本次应用的迁移名列表。
    """
    _ensure_meta(conn)
    done = applied_versions(conn)
    applied: list[str] = []
    for version, name, path in discover_migrations(migrations_dir):
        if version in done:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            conn.execute("BEGIN")
            for stmt in _split_sql_statements(sql):
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO schema_version(version, name, applied_at) VALUES (?,?,?)",
                (version, name, utcnow()),
            )
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise RuntimeError(f"迁移 {name} 失败，已中止（数据库保持上一版本可读）: {exc}")
        applied.append(name)
    return applied


def instance_key(dr: DataRoot) -> bytes:
    """实例主密钥：secrets/instance.key；缺失则生成 32 字节（初始化向导职责，CLI 兜底）。"""
    p = dr.instance_key_path
    if p.exists():
        key = p.read_bytes()
        if len(key) < 32:
            raise ValueError("instance.key 长度不足 32 字节")
        return key[:32]
    import secrets as _secrets

    dr.secrets_dir.mkdir(parents=True, exist_ok=True)
    key = _secrets.token_bytes(32)
    p.write_bytes(key)
    p.chmod(0o600)
    return key
