"""企业实例数据层 CLI（契约 §7 / DevOps 冻结点）：

    python -m app.db migrate
    python -m app.db admin reset-password --account <登录名/手机号>
    python -m app.db backup-snapshot <dest.db>

DATA_ROOT 由环境变量 OMS_DATA_ROOT 指定（compose bind mount 根）。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys

from .config import resolve_data_root
from .dao import EnterpriseStore, NotFoundError
from .database import migrate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.db")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migrate", help="应用未执行的 schema 迁移（幂等、失败中止不切流）")

    p_admin = sub.add_parser("admin", help="服务器本机管理命令（需本机可访问 DATA_ROOT）")
    p_admin_sub = p_admin.add_subparsers(dest="admin_cmd", required=True)
    p_reset = p_admin_sub.add_parser("reset-password", help="作废旧凭据并打印一次性重置邀请码（不经手密码）")
    p_reset.add_argument("--account", required=True, help="登录名或手机号")

    p_backup = sub.add_parser("backup-snapshot", help="sqlite3 在线备份 API 的一致性快照")
    p_backup.add_argument("dest", help="目标 .db 文件路径")

    args = parser.parse_args(argv)
    dr = resolve_data_root()

    if args.cmd == "migrate":
        from .database import connect

        conn = connect(dr)
        applied = migrate(conn)
        conn.close()
        print("migrate: no-op（schema 已是最新）" if not applied else "migrate applied: " + ", ".join(applied))
        return 0

    if args.cmd == "admin" and args.admin_cmd == "reset-password":
        if not dr.db_path.exists():
            print(f"错误：本机 DATA_ROOT 无实例库（{dr.db_path}），拒绝执行", file=sys.stderr)
            return 2
        store = EnterpriseStore(dr)
        try:
            code = store.reset_password_local_admin(login_account=args.account)
        except NotFoundError:
            print(f"错误：账号不存在 {args.account}", file=sys.stderr)
            return 2
        finally:
            store.close()
        print("重置邀请码（一次性展示，有效期以 invites.expires_at 为准，明文不落库）：")
        print(code)
        return 0

    if args.cmd == "backup-snapshot":
        if not dr.db_path.exists():
            print(f"错误：实例库不存在（{dr.db_path}）", file=sys.stderr)
            return 2
        dest = sqlite3.connect(args.dest)
        src = sqlite3.connect(dr.db_path)
        try:
            src.backup(dest)  # 在线备份 API：WAL 下一致性快照（DevOps sidecar 依赖点）
        finally:
            dest.close()
            src.close()
        print(f"backup-snapshot: {dr.db_path} -> {args.dest}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
