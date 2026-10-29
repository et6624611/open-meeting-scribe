"""oms-migrate：存量单机数据 → 企业实例（契约 §5，裁决④：默认归手机账号 13373013103）。

设计要点：
- 告知即过：无用户确认回执端点（裁决 #3）；本工具只读源目录、复制入库，绝不删除/改动源数据（可回滚）。
- 搬运范围=定稿文本白名单：转写定稿/纪要/决策流/笔记 + 本人热词/发言人别名/决策状态字典；
  不搬运：音频文件与路径引用、声纹、凭据、projects、agent-workspace（§2.3）。
- 幂等：legacy_import_ledger 按 legacy_id 去重；同源文件重复执行 = skip already_migrated。
- 对账单：迁移结束写 DATA_ROOT/logs/migration_report_<ts>.json（QA 升级回归门禁物证）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DataRoot, resolve_data_root
from .dao import EnterpriseStore

# 白名单外的 legacy 键一律不读取（防御性：音频路径/声纹/凭据天然不出本机）
_TEXT_DECISION_KEYS = ("id", "decision_id", "text", "content", "status", "status_id", "superseded_by", "source")


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def flatten_dialogue(task: dict) -> str | None:
    dialogue = task.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        return None
    mapping = task.get("speaker_mapping") or {}
    if not isinstance(mapping, dict):
        mapping = {}
    lines: list[str] = []
    for seg in dialogue:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        label = mapping.get(str(seg.get("speaker_id"))) or mapping.get(seg.get("speaker_id")) or f"说话人{seg.get('speaker_id', '?')}"
        lines.append(f"{label}: {text}")
    return "\n".join(lines) or None


def build_snapshot_payload(task_id: str, task: dict) -> dict | None:
    """legacy task dict → 契约 §1.4 快照白名单 payload；无定稿文本内容返回 None（skip）。"""
    formal = flatten_dialogue(task)
    summary = task.get("summary") if isinstance(task.get("summary"), str) else None
    user_summary = task.get("user_summary") if isinstance(task.get("user_summary"), str) else None
    notes = task.get("user_notes") if isinstance(task.get("user_notes"), str) else None
    decisions = [
        {k: v for k, v in d.items() if k in _TEXT_DECISION_KEYS and isinstance(v, (str, int, bool))}
        for d in (task.get("decisions") or [])
        if isinstance(d, dict)
    ]
    if not any([formal, summary, user_summary, notes, decisions]):
        return None
    roster = task.get("roster")
    participants = "、".join(str(r) for r in roster) if isinstance(roster, list) else None
    meta = {
        "title": str(task.get("title") or task_id)[:200],
        "meeting_time": task.get("meeting_date"),
        "participants_text": participants,
        "source": "client",
        "legacy_id": task_id,
    }
    return {
        "meta": meta,
        "formal": formal,
        "summary": user_summary or summary,
        "decisions": decisions,
        "notes": notes,
        "insights_html": None,
    }


class LegacyImporter:
    def __init__(self, store: EnterpriseStore, source_dir: Path, account: str):
        self.store = store
        self.source = Path(source_dir)
        row = store.conn.execute("SELECT user_id FROM users WHERE login_account=?", (account,)).fetchone()
        if row is None:
            raise SystemExit(f"错误：目标账号不存在（{account}）——请先完成初始化向导（裁决④默认 13373013103）")
        self.actor_user_id = row["user_id"]

    def run(self) -> dict:
        report: dict[str, Any] = {
            "account": self.actor_user_id,
            "source_dir": str(self.source),
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "scanned": 0,
            "migrated_tasks": 0,
            "skipped": {},
            "assets": [],
            "spot_check": {"checked": 0, "ok": 0},
        }
        tasks_dir = self.source / "tasks"
        ledger = {r["legacy_id"]: dict(r) for r in self.store.conn.execute("SELECT * FROM legacy_import_ledger")}
        for f in sorted(tasks_dir.glob("*.json")):
            if f.name.endswith((".insights.json", ".formal.json")):
                continue
            report["scanned"] += 1
            try:
                task = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                report["skipped"]["unreadable"] = report["skipped"].get("unreadable", 0) + 1
                continue
            legacy_id = str(task.get("task_id") or f.stem)
            source_hash = _sha256_file(f)
            if legacy_id in ledger:
                if ledger[legacy_id]["source_hash"] == source_hash:
                    report["skipped"]["already_migrated"] = report["skipped"].get("already_migrated", 0) + 1
                    continue
            payload = build_snapshot_payload(legacy_id, task)
            if payload is None:
                report["skipped"]["no_text_content"] = report["skipped"].get("no_text_content", 0) + 1
                continue
            target = ledger.get(legacy_id, {}).get("target_id") or self.store.new_task_for(self.actor_user_id)
            mutation = f"legacy-{legacy_id}-{source_hash[:12]}"
            base = self.store.task_current_rev(self.actor_user_id, target)
            result = self.store.apply_snapshot(
                actor_user_id=self.actor_user_id, task_id=target, client_mutation_id=mutation,
                base_rev=base, payload=payload,
            )
            with self.store.conn:
                self.store.conn.execute(
                    "INSERT INTO legacy_import_ledger(legacy_id, target_table, target_id, source_hash, migrated_at)"
                    " VALUES (?,'ctx_tasks',?,?,?)"
                    " ON CONFLICT(legacy_id) DO UPDATE SET source_hash=excluded.source_hash, migrated_at=excluded.migrated_at",
                    (legacy_id, target, source_hash, result.stored_at),
                )
            # 对账抽检：源 payload 与入库 rev 内容哈希一致性
            report["spot_check"]["checked"] += 1
            stored = self.store.get_task(actor_user_id=self.actor_user_id, task_id=target)
            if stored["content_hash"] == result.content_hash:
                report["spot_check"]["ok"] += 1
            report["migrated_tasks"] += 1

        self._migrate_assets(report)
        report["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._write_report(report)
        return report

    def _migrate_assets(self, report: dict) -> None:
        hw = self.source / "hotwords.txt"
        if hw.exists():
            lines = [ln.strip() for ln in hw.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
            if lines:
                self.store.apply_asset(
                    actor_user_id=self.actor_user_id, kind="hotwords",
                    client_mutation_id=f"legacy-hotwords-{_sha256_file(hw)[:12]}",
                    base_rev=self.store.asset_current_rev(self.actor_user_id, "hotwords"),
                    payload=lines,
                )
                report["assets"].append("hotwords")
        sp = self.source / "speakers.json"
        if sp.exists():
            try:
                data = json.loads(sp.read_text(encoding="utf-8"))
                aliases = {
                    str(x.get("speaker_id")): str(x.get("name"))
                    for x in data
                    if isinstance(x, dict) and x.get("speaker_id") and x.get("name")
                }
                if aliases:
                    self.store.apply_asset(
                        actor_user_id=self.actor_user_id, kind="speaker_aliases",
                        client_mutation_id=f"legacy-speakers-{_sha256_file(sp)[:12]}",
                        base_rev=self.store.asset_current_rev(self.actor_user_id, "speaker_aliases"),
                        payload=aliases,
                    )
                    report["assets"].append("speaker_aliases")  # 仅显示名映射；embedding 不读
            except (json.JSONDecodeError, OSError):
                report["skipped"]["speakers_unreadable"] = 1
        ds = self.source / "decision_statuses.json"
        if ds.exists():
            try:
                statuses = json.loads(ds.read_text(encoding="utf-8"))
                self.store.apply_asset(
                    actor_user_id=self.actor_user_id, kind="decision_statuses",
                    client_mutation_id=f"legacy-decstat-{_sha256_file(ds)[:12]}",
                    base_rev=self.store.asset_current_rev(self.actor_user_id, "decision_statuses"),
                    payload=statuses,
                )
                report["assets"].append("decision_statuses")
            except (json.JSONDecodeError, OSError):
                report["skipped"]["decision_statuses_unreadable"] = 1

    def _write_report(self, report: dict) -> None:
        logs = self.store.dr.root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        ts = report["started_at"].replace(":", "").replace("+0000", "Z")
        path = logs / f"migration_report_{ts}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.db migrate-legacy")
    parser.add_argument("--source", required=True, help="单机版 data 目录（只读，不修改）")
    parser.add_argument("--account", default="13373013103", help="归属账号（裁决④默认）")
    args = parser.parse_args(argv)
    dr = resolve_data_root()
    if not dr.db_path.exists():
        print(f"错误：实例库不存在（{dr.db_path}），请先执行 migrate 与初始化向导", file=sys.stderr)
        return 2
    store = EnterpriseStore(dr)
    importer = LegacyImporter(store, Path(args.source), args.account)
    report = importer.run()
    print(json.dumps({k: report[k] for k in ("scanned", "migrated_tasks", "skipped", "assets", "spot_check", "report_path")},
                     ensure_ascii=False, indent=2))
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
