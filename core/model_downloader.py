"""
core/model_downloader.py — 本地引擎模型引导下载器（R5 / WP-B）

能力（PRD R5）：
  - 引导下载：进度 / 速度 / 剩余量，后台线程执行，不阻塞 Web 服务
  - 断点续传：HTTP Range 基于 .part 分片续传
  - 可取消：取消保留 .part，供后续续传
  - SHA256 校验：下载中增量计算；与远端清单不一致自动重下 ≤1 次后转人工提示
  - 篡改拒载：下载成功后写入完整性清单；verify_model() 供加载前校验
  - 磁盘空间预检：剩余空间 < 待下载量 + 缓冲 时拒绝开始
  - 存储位置可配置：core.model_registry.get_model_dir()（settings engine.local.model_dir）

不内置分发权重（许可 + 包体）；来源为 ModelScope 文件 API。
"""

import hashlib
import json
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import requests

from core.model_registry import (
    MODEL_BY_KEY,
    get_disk_free_bytes,
    get_model_dir,
    get_model_root,
    load_integrity_manifest,
    save_integrity_entry,
)

logger = logging.getLogger(__name__)

# ModelScope API 根（测试可覆写）/ ModelScope API base (overridable in tests)
MODELSCOPE_API_BASE = "https://modelscope.cn"

CHUNK_SIZE = 1024 * 1024            # 1MB 流式分块 / streaming chunk
DISK_BUFFER_BYTES = 500 * 1024 * 1024  # 磁盘预检缓冲 / disk pre-check buffer
MAX_CHECKSUM_RETRIES = 1            # 校验失败自动重下次数（PRD R5 边界：≤1 次后转人工）
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 60

# 任务状态 / Job states
STATE_PENDING = "pending"
STATE_DOWNLOADING = "downloading"
STATE_VERIFYING = "verifying"
STATE_READY = "ready"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"


@dataclass
class DownloadJob:
    """单个模型的下载任务 / Download job for one model."""
    id: str
    model_key: str
    state: str = STATE_PENDING
    total_bytes: int = 0
    downloaded_bytes: int = 0
    speed_bps: float = 0.0
    error: str = ""
    error_code: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    _samples: deque = field(default_factory=lambda: deque(maxlen=64), repr=False)

    def remaining_bytes(self) -> int:
        return max(0, self.total_bytes - self.downloaded_bytes)

    def touch(self):
        self.updated_at = time.time()

    def to_dict(self) -> dict:
        remaining = self.remaining_bytes()
        eta_seconds = int(remaining / self.speed_bps) if self.speed_bps > 0 else None
        return {
            "id": self.id,
            "model_key": self.model_key,
            "state": self.state,
            "total_bytes": self.total_bytes,
            "downloaded_bytes": self.downloaded_bytes,
            "remaining_bytes": remaining,
            "speed_bps": round(self.speed_bps, 1),
            "eta_seconds": eta_seconds,
            "percent": round(self.downloaded_bytes * 100 / self.total_bytes, 1) if self.total_bytes else 0,
            "error": self.error,
            "error_code": self.error_code,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# 进程内任务表（下载为设备级操作，不跨进程共享）/ In-process job table
_jobs: dict[str, DownloadJob] = {}
_jobs_lock = threading.Lock()


# ============================================================
# 远端清单 / Remote manifest
# ============================================================


def _files_url(modelscope_id: str) -> str:
    return f"{MODELSCOPE_API_BASE}/api/v1/models/{modelscope_id}/repo/files?Revision=master&Recursive=true"


def _file_url(modelscope_id: str, file_path: str) -> str:
    return f"{MODELSCOPE_API_BASE}/api/v1/models/{modelscope_id}/repo?Revision=master&FilePath={quote(file_path)}"


def list_remote_files(modelscope_id: str) -> list[dict]:
    """获取模型仓库文件清单 [{path, size, sha256}] / List model repo files."""
    resp = requests.get(_files_url(modelscope_id), timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    resp.raise_for_status()
    payload = resp.json()
    files = (payload.get("Data") or {}).get("Files") or []
    result = []
    for f in files:
        if f.get("Type") != "blob":
            continue
        result.append({
            "path": f.get("Path", ""),
            "size": int(f.get("Size", 0)),
            "sha256": (f.get("Sha256") or "").lower(),
        })
    if not result:
        raise RuntimeError(f"ModelScope 文件清单为空: {modelscope_id}")
    return result


# ============================================================
# 下载执行 / Download execution
# ============================================================


def _record_sample(job: DownloadJob, total_downloaded: int):
    job._samples.append((time.monotonic(), total_downloaded))
    if len(job._samples) >= 2:
        t0, b0 = job._samples[0]
        t1, b1 = job._samples[-1]
        dt = t1 - t0
        if dt > 0:
            job.speed_bps = max(0.0, (b1 - b0) / dt)


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_one_file(
    job: DownloadJob,
    modelscope_id: str,
    remote: dict,
    dest: Path,
) -> str:
    """下载单个文件（断点续传 + 增量 SHA256），返回实际 sha256。
    Download one file with resume + incremental sha256; returns computed digest.

    取消时抛出 _Cancelled。校验失败由调用方处理重试。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    resume_offset = part.stat().st_size if part.exists() else 0
    hasher = hashlib.sha256()
    headers = {}
    mode = "wb"
    if resume_offset > 0:
        # 续传：先哈希已有分片 / Resume: hash existing part first
        with open(part, "rb") as f:
            for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
                hasher.update(chunk)
        headers["Range"] = f"bytes={resume_offset}-"
        mode = "ab"

    url = _file_url(modelscope_id, remote["path"])
    resp = requests.get(url, headers=headers, stream=True, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    resp.raise_for_status()

    if resume_offset > 0 and resp.status_code == 200:
        # 服务端不支持 Range：从头重下 / Server ignored Range: restart from scratch
        resume_offset = 0
        hasher = hashlib.sha256()
        mode = "wb"

    written = resume_offset
    with open(part, mode) as f:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            if job.cancel_event.is_set():
                raise _Cancelled()
            if not chunk:
                continue
            f.write(chunk)
            hasher.update(chunk)
            written += len(chunk)
            job.downloaded_bytes += len(chunk)
            _record_sample(job, job.downloaded_bytes)
            job.touch()

    part.replace(dest)
    return hasher.hexdigest()


class _Cancelled(Exception):
    """内部：任务被取消 / Internal: job cancelled."""


def _invalidate_engine_models_check() -> None:
    """丢弃引擎侧必装模型完整性校验缓存（延迟导入避开与 engine_host 的循环依赖）。"""
    try:
        from core.engine_host import invalidate_models_check
        invalidate_models_check()
    except Exception as e:  # 仅影响观测面时效，不得打断下载收尾
        logger.warning(f"[模型下载] 引擎校验缓存失效调用失败（下一次将按 TTL 过期）: {e}")


def _run_model_download(job: DownloadJob):
    """后台线程主体：下载一个模型的全部文件 / Thread body: download all files of one model."""
    meta = MODEL_BY_KEY[job.model_key]
    modelscope_id = meta["modelscope_id"]
    try:
        job.state = STATE_DOWNLOADING
        job.touch()

        files = list_remote_files(modelscope_id)
        job.total_bytes = sum(f["size"] for f in files)

        # 磁盘空间预检 / Disk space pre-check
        model_root = get_model_root(job.model_key)
        already = 0
        for f in files:
            p = model_root / f["path"]
            part = p.with_suffix(p.suffix + ".part")
            if p.exists():
                already += p.stat().st_size
            elif part.exists():
                already += part.stat().st_size
        need = max(0, job.total_bytes - already)
        free = get_disk_free_bytes(get_model_dir())
        if free < need + DISK_BUFFER_BYTES:
            job.state = STATE_FAILED
            job.error_code = "insufficient_disk"
            job.error = (
                f"磁盘空间不足：需要约 {(need + DISK_BUFFER_BYTES) / 1024 / 1024:.0f}MB"
                f"（含 {DISK_BUFFER_BYTES // 1024 // 1024}MB 缓冲），当前剩余 {free / 1024 / 1024:.0f}MB。"
                f"请清理磁盘或在设置中更换模型存储位置。"
            )
            job.touch()
            return

        integrity: dict[str, dict] = {}
        local_manifest = load_integrity_manifest().get(job.model_key, {})

        for remote in files:
            if job.cancel_event.is_set():
                raise _Cancelled()
            rel = remote["path"]
            dest = model_root / rel

            # 已就绪文件跳过（完整性清单内且 sha 一致）/ Skip files already verified
            if dest.exists() and rel in local_manifest:
                recorded = local_manifest[rel].get("sha256", "")
                if recorded and _sha256_of(dest) == recorded:
                    integrity[rel] = local_manifest[rel]
                    job.downloaded_bytes += dest.stat().st_size
                    continue

            attempt = 0
            while True:
                actual_sha = _download_one_file(job, modelscope_id, remote, dest)
                expected_sha = remote.get("sha256", "")
                if not expected_sha or actual_sha == expected_sha:
                    integrity[rel] = {"sha256": actual_sha, "size": dest.stat().st_size}
                    break
                attempt += 1
                logger.warning(
                    f"[模型下载] SHA256 不一致: {job.model_key}/{rel} "
                    f"(expected={expected_sha[:12]}…, actual={actual_sha[:12]}…), 重试 {attempt}/{MAX_CHECKSUM_RETRIES}"
                )
                if attempt > MAX_CHECKSUM_RETRIES:
                    raise RuntimeError(
                        f"SHA256 校验连续失败（{rel}），文件可能被篡改或网络损坏。"
                        f"已自动重下 {MAX_CHECKSUM_RETRIES} 次，请检查网络环境或手动重新下载。"
                    )
                dest.unlink(missing_ok=True)
                job.downloaded_bytes = max(0, job.downloaded_bytes - remote["size"])

        job.state = STATE_VERIFYING
        job.touch()
        save_integrity_entry(job.model_key, integrity)
        job.state = STATE_READY
        job.touch()
        logger.info(f"[模型下载] 完成: {job.model_key} ({job.total_bytes / 1024 / 1024:.1f}MB)")

    except _Cancelled:
        job.state = STATE_CANCELLED
        job.touch()
        logger.info(f"[模型下载] 已取消: {job.model_key}（.part 分片保留，可续传）")
    except Exception as e:
        job.state = STATE_FAILED
        job.error_code = job.error_code or "download_failed"
        job.error = str(e)[:500]
        job.touch()
        logger.error(f"[模型下载] 失败: {job.model_key}: {e}")
    finally:
        # 本轮无论成败都可能改动了模型目录（写入新权重、校验失败前 unlink 重下），
        # 丢弃引擎侧缓存，使徽章 / status 下一次即反映真实状态而非等 TTL 到期。
        _invalidate_engine_models_check()


def start_download(model_key: str) -> dict:
    """启动一个模型的下载任务 / Start a download job for one model.

    model_key 支持 "all"（为每个未就绪模型建任务）。
    返回 {"ok": True, "jobs": [job_dict...]} 或 {"ok": False, "error_code", "error"}。
    """
    if model_key == "all":
        keys = [m["key"] for m in MODEL_BY_KEY.values() if model_status(m["key"])["status"] != "ready"]
        if not keys:
            return {"ok": True, "jobs": []}
    elif model_key in MODEL_BY_KEY:
        keys = [model_key]
    else:
        return {"ok": False, "error_code": "unknown_model", "error": f"未知模型: {model_key}"}

    started = []
    for key in keys:
        # model_status() 自身会获取 _jobs_lock 并可能做磁盘/SHA256 I/O，
        # 必须在锁外调用，避免非重入锁自死锁与锁内重 I/O 阻塞进度轮询。
        # Call model_status() outside the lock: it re-acquires _jobs_lock and may
        # do disk/SHA256 I/O; holding the (non-reentrant) lock here would deadlock.
        if model_status(key)["status"] == "ready":
            continue
        with _jobs_lock:
            # 已在下载/校验中的模型不重复启动 / Deduplicate active jobs
            if any(j.model_key == key and j.state in (STATE_PENDING, STATE_DOWNLOADING, STATE_VERIFYING) for j in _jobs.values()):
                continue
            job = DownloadJob(id=uuid.uuid4().hex[:12], model_key=key)
            _jobs[job.id] = job
            started.append(job)

    for job in started:
        t = threading.Thread(target=_run_model_download, args=(job,), daemon=True, name=f"model-dl-{job.model_key}")
        t.start()

    return {"ok": True, "jobs": [j.to_dict() for j in started]}


def cancel_download(job_id: str) -> dict:
    """取消下载任务（保留 .part 供续传）/ Cancel a job, keeping .part for resume."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return {"ok": False, "error_code": "not_found", "error": f"任务不存在: {job_id}"}
    if job.state not in (STATE_PENDING, STATE_DOWNLOADING, STATE_VERIFYING):
        return {"ok": False, "error_code": "not_cancellable", "error": f"任务状态为 {job.state}，无法取消"}
    job.cancel_event.set()
    return {"ok": True, "job": job.to_dict()}


def get_jobs() -> list[dict]:
    with _jobs_lock:
        return [j.to_dict() for j in sorted(_jobs.values(), key=lambda x: x.created_at)]


# ============================================================
# 完整性校验（篡改拒载）/ Integrity verification (tamper rejection)
# ============================================================


def verify_model(model_key: str) -> dict:
    """校验已安装模型的完整性 / Verify installed model integrity.

    返回 status：
      - ready：完整性清单齐全且全部文件 sha256 一致
      - tampered：清单内文件被修改（拒载）
      - missing：无完整性清单或文件缺失（未下载完整）
    """
    if model_key not in MODEL_BY_KEY:
        return {"status": "unknown", "mismatched": [], "missing": []}

    recorded = load_integrity_manifest().get(model_key)
    if not recorded:
        return {"status": "missing", "mismatched": [], "missing": []}

    model_root = get_model_root(model_key)
    mismatched, missing = [], []
    for rel, meta in recorded.items():
        path = model_root / rel
        if not path.exists():
            missing.append(rel)
            continue
        expected = meta.get("sha256", "")
        if expected and _sha256_of(path) != expected:
            mismatched.append(rel)

    if missing:
        return {"status": "missing", "mismatched": mismatched, "missing": missing}
    if mismatched:
        return {"status": "tampered", "mismatched": mismatched, "missing": []}
    return {"status": "ready", "mismatched": [], "missing": []}


def model_status(model_key: str) -> dict:
    """聚合模型当前状态（供路由/引擎预检使用）。"""
    meta = MODEL_BY_KEY[model_key]
    with _jobs_lock:
        active = next(
            (j for j in _jobs.values()
             if j.model_key == model_key and j.state in (STATE_PENDING, STATE_DOWNLOADING, STATE_VERIFYING)),
            None,
        )
    if active:
        return {"status": "downloading", "job": active.to_dict()}

    integrity = load_integrity_manifest().get(model_key)
    if not integrity:
        # 无清单但存在 .part → 部分下载（可续传）/ No manifest but .part exists → partial
        model_root = get_model_root(model_key)
        has_part = model_root.exists() and any(model_root.rglob("*.part"))
        return {"status": "partial" if has_part else "not_downloaded"}

    verified = verify_model(model_key)
    return {"status": verified["status"], "detail": verified}


def models_overview() -> dict:
    """全量模型清单 + 状态 + 磁盘信息（只读，供所有用户查看）。"""
    model_dir = get_model_dir()
    models = []
    for meta in MODEL_BY_KEY.values():
        status = model_status(meta["key"])
        models.append({
            "key": meta["key"],
            "name": meta["name"],
            "modelscope_id": meta["modelscope_id"],
            "size_bytes": meta["size_bytes"],
            "purpose": meta["purpose"],
            "optional": meta["optional"],
            "license": meta["license"],
            "status": status["status"],
            "job": status.get("job"),
        })
    return {
        "model_dir": str(model_dir),
        "disk_free_bytes": get_disk_free_bytes(model_dir),
        "total_size_all_bytes": sum(m["size_bytes"] for m in MODEL_BY_KEY.values()),
        "total_size_required_bytes": sum(m["size_bytes"] for m in MODEL_BY_KEY.values() if not m["optional"]),
        "models": models,
        "downloads": get_jobs(),
    }
