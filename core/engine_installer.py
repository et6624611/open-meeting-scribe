"""
core/engine_installer.py — 本地引擎组件一键落位（R8 / WP-G G-4b，D-G4 L2 层）

职责（mac 与 Windows 应用内安装共用；Win Inno [Components] 为另一条通道，G-4）：
  下载引擎包 zip → SHA256 校验 → 解包到临时目录 → 逐文件校验 engine-manifest.json
  → 原子换入 ``<运行时锚点>/engine/``（D-G3）→ 就绪（权重可下载态）。

设计约束：
  - 由已签名主程序自行下载落位的文件不会被打 quarantine 标记（D-G4 §3.1 L2 依据），
    因此 mac 侧不依赖 pkg/公证即可交付；
  - 安装目录只放只读代码包（D-G3 (a)）：目标锚点 Win
    ``%LOCALAPPDATA%\\OpenMeetingScribe\\engine``、mac
    ``~/Library/Application Support/OpenMeetingScribe/engine``；
  - 三条安装通道共用同一目录布局与 manifest（D-G1 子项①），政企离线包走
    :func:`install_from_zip`；
  - 安装进度以模块级状态字典暴露（与 core/model_downloader.py 的轮询模式一致），
    UI 经 /api/engine/component/* 轮询（G-5 首启引导数据源）。
"""

import hashlib
import json
import logging
import os
import shutil
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CHUNK = 1024 * 1024

# 默认发布通道：GitHub Releases 资产命名约定（build-engine.yml 产出）
# OMSEngine-<platform>.zip + OMSEngine-<platform>.zip.sha256
DEFAULT_RELEASE_BASE = "https://github.com/et6624611/open-meeting-scribe/releases/latest/download"

# 模块级安装状态（进程内单实例：同时只允许一个安装任务）
_install_lock = threading.Lock()
_install_state: dict = {
    "running": False,
    "stage": "idle",  # idle | downloading | verifying | extracting | swapping | done | failed | canceled
    "percent": 0.0,
    "bytes_done": 0,
    "bytes_total": 0,
    "ok": None,
    "error": None,
    "error_code": None,
    "target_dir": None,
    "finished_at": None,
}
_cancel_flag = threading.Event()


def get_install_state() -> dict:
    with _install_lock:
        return dict(_install_state)


def cancel_install() -> dict:
    _cancel_flag.set()
    return {"ok": True}


def _platform_tag() -> str:
    """平台标签（与 build/make_engine_manifest.py 同规则，不 import build 包以免路径依赖）。"""
    import platform as _pf
    system = _pf.system().lower()
    machine = _pf.machine().lower()
    if system == "windows":
        machine = "amd64" if machine in ("amd64", "x86_64") else machine
    return f"{system}-{machine}"


def resolve_download_url(explicit_url: str | None = None) -> str:
    """下载 URL 解析序：显式入参 → settings engine.local.component_url → GitHub Release 约定。"""
    if explicit_url:
        return explicit_url.strip()
    try:
        from app.settings_store import get_engine_config
        cfg_url = (get_engine_config()["local"].get("component_url") or "").strip()
        if cfg_url:
            return cfg_url
    except Exception:
        pass
    return f"{DEFAULT_RELEASE_BASE}/OMSEngine-{_platform_tag()}.zip"


def _set_stage(stage: str, **kw) -> None:
    with _install_lock:
        _install_state["stage"] = stage
        _install_state.update(kw)


def _fail(error_code: str, message: str) -> None:
    logger.error(f"[引擎组件安装] 失败 {error_code}: {message}")
    with _install_lock:
        _install_state.update({
            "running": False,
            "stage": "failed",
            "ok": False,
            "error": message,
            "error_code": error_code,
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })


def _finish_ok(target: Path) -> None:
    with _install_lock:
        _install_state.update({
            "running": False,
            "stage": "done",
            "percent": 100.0,
            "ok": True,
            "error": None,
            "error_code": None,
            "target_dir": str(target),
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    logger.info(f"[引擎组件安装] 完成，落位 {target}")


def verify_manifest_files(root: Path, manifest: dict) -> list[str]:
    """按 manifest 逐文件校验 SHA256，返回损坏文件的相对路径列表。"""
    bad: list[str] = []
    files = manifest.get("files") or {}
    for rel, meta in files.items():
        p = root / rel
        if not p.is_file():
            bad.append(rel)
            continue
        h = hashlib.sha256()
        with p.open("rb") as f:
            while chunk := f.read(CHUNK):
                h.update(chunk)
        if h.hexdigest() != meta.get("sha256"):
            bad.append(rel)
    return bad


def install_from_zip(zip_path: str | Path, expected_sha256: str | None = None) -> dict:
    """政企离线包通道：从本地 zip 安装（校验 → 解包 → 原子换入锚点 engine/）。

    同步执行（本地文件无下载耗时，解包 1GB 约 1–3 分钟）；返回 {"ok": ...}。
    """
    zip_path = Path(zip_path).expanduser()
    if not zip_path.is_file():
        return {"ok": False, "error_code": "zip_not_found", "error": f"引擎包不存在: {zip_path}"}

    with _install_lock:
        if _install_state["running"]:
            return {"ok": False, "error_code": "install_in_progress", "error": "已有安装任务进行中"}
        _install_state.update({"running": True, "stage": "verifying", "percent": 0.0,
                               "ok": None, "error": None, "error_code": None, "finished_at": None})

    try:
        return _install_zip_sync(zip_path, expected_sha256)
    except Exception as e:
        _fail("install_error", f"引擎组件安装失败: {e}")
        return get_install_state()


def _install_zip_sync(zip_path: Path, expected_sha256: str | None) -> dict:
    from core.engine_paths import ENGINE_MANIFEST_NAME, get_runtime_anchor

    # 1) zip 整体 SHA256（若提供期望值）
    if expected_sha256:
        h = hashlib.sha256()
        with zip_path.open("rb") as f:
            while chunk := f.read(CHUNK):
                h.update(chunk)
        if h.hexdigest().lower() != expected_sha256.lower():
            _fail("checksum_mismatch", f"引擎包 SHA256 校验失败（期望 {expected_sha256[:16]}…，实际 {h.hexdigest()[:16]}…），拒绝安装")
            return get_install_state()

    # 2) 解包到临时目录（zip-slip 防护：拒绝绝对路径/上跳成员）
    anchor = get_runtime_anchor()
    stage_dir = anchor / "engine.new"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)

    total = zip_path.stat().st_size
    _set_stage("extracting", bytes_total=total)
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.infolist()
        # 支持 zip 内含单层顶级目录（OMSEngine/...）或平铺。
        # 仅当所有文件成员都位于同一顶级目录下才剥壳；平铺包中混有根级文件
        # （如 OMSEngine 可执行体）时不得剥壳，否则子目录前缀会被误剥。
        prefixes = {m.filename.split("/")[0] for m in members if "/" in m.filename}
        has_root_files = any(not m.is_dir() and "/" not in m.filename for m in members)
        strip_top = (
            len(prefixes) == 1
            and not has_root_files
            and not any(m.filename == next(iter(prefixes)) for m in members)
        )
        top = next(iter(prefixes)) if strip_top else ""
        done_bytes = 0
        for m in members:
            if _cancel_flag.is_set():
                shutil.rmtree(stage_dir, ignore_errors=True)
                _fail("canceled", "安装已取消")
                return get_install_state()
            if m.is_dir():
                continue
            rel = m.filename
            if strip_top and rel.startswith(top + "/"):
                rel = rel[len(top) + 1:]
            if not rel or rel.startswith(("/", "..")) or ".." in Path(rel).parts:
                _fail("bad_archive", f"引擎包含非法路径成员，拒绝解包: {m.filename}")
                return get_install_state()
            dest = stage_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(m) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out, length=CHUNK)
            done_bytes += m.file_size
            _set_stage("extracting", percent=round(done_bytes / max(total, 1) * 100, 1),
                       bytes_done=done_bytes)

    # 3) manifest 存在性 + 逐文件 SHA256 校验
    _set_stage("verifying", percent=99.0)
    manifest_path = stage_dir / ENGINE_MANIFEST_NAME
    if not manifest_path.is_file():
        shutil.rmtree(stage_dir, ignore_errors=True)
        _fail("manifest_missing", f"引擎包缺少 {ENGINE_MANIFEST_NAME}，不是合法的引擎组件包")
        return get_install_state()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        shutil.rmtree(stage_dir, ignore_errors=True)
        _fail("manifest_invalid", f"engine-manifest.json 解析失败: {e}")
        return get_install_state()

    bad = verify_manifest_files(stage_dir, manifest)
    if bad:
        shutil.rmtree(stage_dir, ignore_errors=True)
        _fail("checksum_mismatch", f"引擎包 {len(bad)} 个文件校验失败（如 {bad[0]}），拒绝安装")
        return get_install_state()

    # 4) 原子换入 <anchor>/engine/（旧版本先挪到 engine.old，成功后删除）
    _set_stage("swapping")
    engine_dir = anchor / "engine"
    old_dir = anchor / "engine.old"
    if old_dir.exists():
        shutil.rmtree(old_dir, ignore_errors=True)
    if engine_dir.exists():
        os.replace(engine_dir, old_dir)
    try:
        os.replace(stage_dir, engine_dir)
    except OSError as e:
        # 跨卷等场景 replace 失败 → 退化为 copytree
        logger.warning(f"[引擎组件安装] os.replace 失败（{e}），改用 copytree")
        shutil.copytree(stage_dir, engine_dir)
        shutil.rmtree(stage_dir, ignore_errors=True)
    if old_dir.exists():
        shutil.rmtree(old_dir, ignore_errors=True)

    # 5) Unix 下确保可执行位
    from core.engine_paths import engine_exe_name
    exe = engine_dir / engine_exe_name()
    if exe.is_file() and os.name != "nt":
        exe.chmod(exe.stat().st_mode | 0o111)

    _finish_ok(engine_dir)
    return get_install_state()


def start_download_install(source_url: str | None = None, expected_sha256: str | None = None) -> dict:
    """应用内一键安装（mac L2 / Win 应用内通道）：后台线程下载 + 安装，立即返回。

    进度经 :func:`get_install_state` 轮询。sha256 期望值缺省时尝试拉取
    ``<url>.sha256`` sidecar（build-engine.yml 产出）；拉不到则跳过整体校验
    （manifest 逐文件校验仍然强制）。
    """
    with _install_lock:
        if _install_state["running"]:
            return {"ok": False, "error_code": "install_in_progress", "error": "已有安装任务进行中"}
        _install_state.update({"running": True, "stage": "downloading", "percent": 0.0,
                               "bytes_done": 0, "bytes_total": 0, "ok": None, "error": None,
                               "error_code": None, "target_dir": None, "finished_at": None})
    _cancel_flag.clear()

    thread = threading.Thread(
        target=_download_install_worker,
        args=(source_url, expected_sha256),
        daemon=True,
        name="engine-component-install",
    )
    thread.start()
    return {"ok": True, "started": True}


def _download_install_worker(source_url: str | None, expected_sha256: str | None) -> None:
    import requests

    from core.engine_paths import get_runtime_anchor

    try:
        url = resolve_download_url(source_url)
    except Exception as e:
        _fail("bad_url", f"引擎包下载地址解析失败: {e}")
        return

    anchor = get_runtime_anchor()
    download_dir = anchor / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    zip_path = download_dir / Path(url.split("?")[0]).name
    part_path = zip_path.with_suffix(zip_path.suffix + ".part")

    # sha256 sidecar（若发布通道提供）
    if not expected_sha256:
        try:
            r = requests.get(url + ".sha256", timeout=30)
            if r.status_code == 200 and r.text.strip():
                expected_sha256 = r.text.strip().split()[0]
        except Exception:
            expected_sha256 = None

    try:
        with requests.get(url, stream=True, timeout=(15, 120)) as r:
            if r.status_code != 200:
                _fail("download_failed", f"引擎包下载失败（HTTP {r.status_code}）: {url}。"
                                         "内网环境请改用离线引擎包导入。")
                return
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            _set_stage("downloading", bytes_total=total)
            with part_path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=CHUNK):
                    if _cancel_flag.is_set():
                        _fail("canceled", "安装已取消")
                        return
                    if chunk:
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            _set_stage("downloading", percent=round(done / total * 95, 1),
                                       bytes_done=done)
        os.replace(part_path, zip_path)
    except Exception as e:
        _fail("download_failed", f"引擎包下载失败: {e}")
        return

    try:
        _install_zip_sync(zip_path, expected_sha256)
    except Exception as e:
        _fail("install_error", f"引擎组件安装失败: {e}")
    finally:
        # 成功与否都清理下载缓存（zip 体积 ~1GB，不留垃圾）
        try:
            zip_path.unlink(missing_ok=True)
        except Exception:
            pass
