"""录音助手本地控制面（EP0-BE 增量4，契约 §1.4/§1.8 v1.1）。

职责：本机与企业关系——配对注册、handshake/local_token、定稿 outbox 队列（pending→syncing→synced/error）
与向企业实例的快照推送（Bearer device token）。个人版进程不挂载本模块。

P0 合并策略（登记于契约 v1.1）：409 时以服务端 current_rev 为新 base、同 mutation 重推（last-writer-wins），
即"断网期间同一 task 的本地编辑合并为最终快照"的助手侧落地；冲突细分合并留 P1。
"""
from __future__ import annotations

import json
import secrets as _secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from app.db.config import DataRoot, resolve_data_root

LOCAL_TOKEN_TTL = 3600  # 秒；仅内存态，重启重握手（token 不落任何持久层，与前端纪律一致）


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _client() -> httpx.Client:
    """助手→实例通道固定直连：不采纳环境代理变量（trust_env=False）。

    安全口径：与"数据出境白名单"一致，代理会构成不可枚举出网点；企业若需代理出站属 P1 显式配置项。
    """
    return httpx.Client(trust_env=False, timeout=30)


class AssistantPlane:
    """assistant 形态的单例运行态：state.json（配对凭据）+ outbox/ + 内存 local_token。"""

    def __init__(self, dr: DataRoot | None = None):
        self.dr = dr or resolve_data_root()
        self.base = self.dr.root / "assistant"
        self.outbox_dir = self.base / "outbox"
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self._tokens: dict[str, float] = {}
        self._lock = threading.RLock()

    # ---------- 状态 ----------

    @property
    def state_path(self) -> Path:
        return self.base / "state.json"

    def state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        return {}

    def _save_state(self, st: dict) -> None:
        self.state_path.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        self.state_path.chmod(0o600)  # device token 属凭据

    @property
    def paired(self) -> bool:
        st = self.state()
        return bool(st.get("server_url") and st.get("device_token"))

    # ---------- handshake ----------

    def handshake(self) -> dict:
        with self._lock:
            token = _secrets.token_urlsafe(24)
            deadline = time.time() + LOCAL_TOKEN_TTL
            self._tokens = {t: d for t, d in self._tokens.items() if d > time.time()}
            self._tokens[token] = deadline
        st = self.state()
        return {
            "local_token": token,
            "paired": self.paired,
            "paired_user_id": st.get("paired_user_id"),
            "server_url": st.get("server_url"),
        }

    def verify_local_token(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            deadline = self._tokens.get(token)
            return deadline is not None and deadline > time.time()

    # ---------- 配对注册（代持邀请流程：Web 展示 pairing_code → 助手兑换 device token） ----------

    def register(self, *, server_url: str, pairing_code: str, device_name: str = "OMS录音助手") -> dict:
        url = server_url.rstrip("/")
        try:
            with _client() as c:
                r = c.post(
                    f"{url}/api/v1/auth/device-activate",
                    json={"pairing_code": pairing_code, "device_name": device_name},
                )
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            raise ValueError(f"实例不可达：{type(exc).__name__}") from exc
        if r.status_code == 404:
            raise ValueError("配对码无效或已过期")
        r.raise_for_status()
        data = r.json()
        self._save_state(
            {
                "server_url": url,
                "device_token": data["device_token"],
                "device_id": data["device_id"],
                "paired_user_id": data.get("user_id"),
                "registered_at": _now(),
            }
        )
        return {"device_id": data["device_id"], "paired": True}

    # ---------- outbox ----------

    def enqueue(self, *, task_id: str, payload: dict, base_rev: int = 0) -> dict:
        item = {
            "mutation_id": str(uuid.uuid4()),
            "task_id": task_id,
            "base_rev": base_rev,
            "payload": payload,
            "status": "pending",
            "attempts": 0,
            "last_error": None,
            "queued_at": _now(),
        }
        (self.outbox_dir / f"{item['mutation_id']}.json").write_text(
            json.dumps(item, ensure_ascii=False), encoding="utf-8"
        )
        return item

    def queue_view(self) -> list[dict]:
        out: list[dict] = []
        for f in sorted(self.outbox_dir.glob("*.json")):
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            out.append(
                {
                    "task_id": it["task_id"],
                    "mutation_id": it["mutation_id"],
                    "status": it["status"],
                    "queued_at": it["queued_at"],
                    "last_error": it["last_error"],
                    "retry_after": it.get("retry_after"),
                }
            )
        return out

    def _update_item(self, mutation_id: str, **fields: Any) -> dict:
        p = self.outbox_dir / f"{mutation_id}.json"
        it = json.loads(p.read_text(encoding="utf-8"))
        it.update(fields)
        p.write_text(json.dumps(it, ensure_ascii=False), encoding="utf-8")
        return it

    def flush_once(self, *, max_items: int = 20) -> dict:
        """一轮推送：pending / 到期的 error 重试项依次上传；返回计数摘要。"""
        pushed = {"synced": 0, "failed": 0, "skipped_unpaired": 0}
        if not self.paired:
            for f in self.outbox_dir.glob("*.json"):
                it = json.loads(f.read_text(encoding="utf-8"))
                if it["status"] in ("pending", "error"):
                    pushed["skipped_unpaired"] += 1
            return pushed
        st = self.state()
        headers_base = {"Authorization": f"Bearer {st['device_token']}"}
        done = 0
        for f in list(self.outbox_dir.glob("*.json"))[: max_items * 3]:
            it = json.loads(f.read_text(encoding="utf-8"))
            if it["status"] == "synced":
                continue
            if it["status"] == "error" and it.get("retry_after") and it["retry_after"] > _now():
                continue
            if done >= max_items:
                break
            done += 1
            self._push_item(st["server_url"], headers_base, it, pushed)
        return pushed

    def _push_item(self, server_url: str, headers: dict, it: dict, counters: dict) -> None:
        mid = it["mutation_id"]
        self._update_item(mid, status="syncing")
        url = f"{server_url}/api/v1/context/tasks/{it['task_id']}/snapshot"

        def _put(client: httpx.Client, base: int):
            return client.put(
                url,
                json=it["payload"],
                headers={**headers, "Idempotency-Key": mid, "If-Match-Rev": str(base)},
            )

        try:
            with _client() as c:
                r = _put(c, it["base_rev"])
                if r.status_code == 409:
                    # P0 合并策略：采纳服务端 rev 为 base，同 mutation 重推（last-writer-wins）
                    cur = (r.json().get("error") or {}).get("current_rev")
                    new_base = int(cur) if cur is not None else it["base_rev"]
                    self._update_item(mid, base_rev=new_base)
                    r = _put(c, new_base)
            if r.status_code in (200, 201):
                body = r.json()
                self._update_item(
                    mid, status="synced", last_error=None, server_rev=body.get("server_rev"), synced_at=_now()
                )
                counters["synced"] += 1
            else:
                try:
                    err = r.json().get("error", {})
                except (json.JSONDecodeError, ValueError):
                    err = {"message": r.text[:200]}
                self._set_backoff(mid, f"{r.status_code}:{err.get('code', 'http')}")
                counters["failed"] += 1
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            self._set_backoff(mid, f"network:{type(exc).__name__}")
            counters["failed"] += 1

    def _read_item(self, mutation_id: str) -> dict:
        return json.loads((self.outbox_dir / f"{mutation_id}.json").read_text(encoding="utf-8"))

    def _set_backoff(self, mutation_id: str, error: str) -> None:
        it = self._read_item(mutation_id)
        attempts = it["attempts"] + 1
        delay = min(300, 5 * 2 ** min(attempts, 5))  # 指数退避封顶 5 分钟
        retry_after = datetime.now(timezone.utc).timestamp() + delay
        self._update_item(
            mutation_id,
            status="error",
            attempts=attempts,
            last_error=error,
            retry_after=datetime.fromtimestamp(retry_after, tz=timezone.utc).isoformat(timespec="seconds"),
        )


_plane: AssistantPlane | None = None
_plane_lock = threading.Lock()


def get_plane(dr: DataRoot | None = None) -> AssistantPlane:
    global _plane
    with _plane_lock:
        if _plane is None:
            _plane = AssistantPlane(dr)
        return _plane


def reset_plane() -> None:
    global _plane
    with _plane_lock:
        _plane = None
