"""DATA_ROOT 解析（契约 §2.1）。

- 企业实例：环境变量 ``OMS_DATA_ROOT`` 指定（compose bind mount 到该目录根）。
- 个人版兼容：未设置时回退 ``Path("data")`` 相对 CWD，行为与现状一致。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_DATA_ROOT = "OMS_DATA_ROOT"


@dataclass(frozen=True)
class DataRoot:
    root: Path

    @property
    def db_path(self) -> Path:
        return self.root / "instance.db"

    @property
    def blobs_dir(self) -> Path:
        return self.root / "blobs"

    @property
    def secrets_dir(self) -> Path:
        return self.root / "secrets"

    @property
    def instance_key_path(self) -> Path:
        return self.secrets_dir / "instance.key"

    def blob_path(self, user_id: str, task_id: str, rev: int) -> Path:
        # 隔离在 DB 行级；blobs/<user_id>/ 前缀 + 归属校验后路径才可访问（契约 §2.1）
        return self.blobs_dir / user_id / task_id / f"rev{rev}.json.gz"


def resolve_data_root(env: dict[str, str] | None = None) -> DataRoot:
    env = os.environ if env is None else env
    raw = env.get(ENV_DATA_ROOT, "").strip()
    root = Path(raw) if raw else Path("data")
    return DataRoot(root=root)
