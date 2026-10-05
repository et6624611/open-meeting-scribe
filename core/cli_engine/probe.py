"""
core/cli_engine/probe.py — CLI 引擎可用性探针 / Engine availability probe

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

职责 / Responsibilities:
  - which/version/login 三段探针，输出结构化结论供前端就地引导（方案 §2.3、R2）
  - 任一步失败即返回 available=False + 失败原因码，调用方据此自动回退内置链路

注意 / Note:
  - 探针以同步 subprocess 执行，调用方须在事件循环外或线程池中运行（勿在 async 路径直接调用阻塞）。
  - 对应方案 §3.10-② ：软件只做探针与登录态"展示"，绝不读写 CLI 自有配置目录（~/.qoder）。
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT = 8  # 单条探针命令超时（秒）/ per probe command timeout


def _parse_version(text: str) -> tuple[int, ...]:
    """从任意输出中提取 x.y.z 语义版本元组。 / Extract a semantic version tuple from free text."""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    if not m:
        return ()
    return tuple(int(x) for x in m.groups())


def _min_version_tuple(min_version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", min_version or "")
    return tuple(int(p) for p in parts[:3]) if parts else ()


def probe_engine(manifest: dict, cli_path_override: str | None = None) -> dict:
    """
    执行三段探针，返回结构化可用性结论。 / Run the 3-stage probe, return structured availability.

    Returns:
        {
          "available": bool,
          "reason": "ok"|"not_installed"|"version_low"|"not_logged_in"|"probe_error",
          "path": str|None,
          "version": str|None,
          "logged_in": bool,
          "display_name": str,
          "hint": str,          # 面向用户的就地引导文案键（前端 i18n 映射）
        }
    """
    display_name = manifest.get("display_name", "CLI")
    result = {
        "available": False, "reason": "probe_error", "path": None,
        "version": None, "logged_in": False, "display_name": display_name, "hint": "",
        # 登录段被显式跳过（login_cmd=null）：可用性只代表路径+版本，登录缺失由运行期错误浮现
        "login_skipped": False,
        # 引擎展示名的 i18n 键（品牌名不翻译；含本地化后缀的引擎由前端按键翻译）
        "name_key": manifest.get("name_key", ""),
        # 三段探针失败段定位（REQ-EXPERT-MODE §2.2：详情卡/对话面板直接可见哪段挂了）
        # path=可执行解析 · version=版本下限 · login=登录态；None=未失败
        "failed_stage": None,
    }

    # ① 路径解析（探针命令来自 manifest，v1 仅本机 CLI；--version 与 status 为无头安全只读命令）
    binary = cli_path_override or manifest.get("binary", "qoder")
    path = binary if cli_path_override else shutil.which(binary)
    if not path:
        result["reason"] = "not_installed"
        result["failed_stage"] = "path"
        result["hint"] = "chatEngine.notInstalled"
        return result
    result["path"] = path

    # ② 版本校验
    version_cmd = manifest.get("probe", {}).get("version_cmd") or [binary, "--version"]
    version_cmd = [path if c == binary else c for c in version_cmd]
    try:
        vr = subprocess.run(version_cmd, capture_output=True, text=True, timeout=_PROBE_TIMEOUT,
                            stdin=subprocess.DEVNULL)
        version_text = (vr.stdout or vr.stderr).strip()
    except Exception as e:  # noqa: BLE001 - 探针任何异常都应降级为不可用，绝不抛出
        logger.warning("[CLI引擎探针] 版本命令失败 %s: %s", display_name, e)
        result["reason"] = "probe_error"
        result["failed_stage"] = "version"
        result["hint"] = "chatEngine.probeError"
        return result

    got = _parse_version(version_text)
    need = _min_version_tuple(manifest.get("min_version", "0.0.0"))
    result["version"] = version_text.splitlines()[0][:40] if version_text else None
    if need and got < need:
        result["reason"] = "version_low"
        result["failed_stage"] = "version"
        result["hint"] = "chatEngine.versionLow"
        return result

    # ③ 登录态校验（探针命令均来自受控 manifest，无用户输入）
    # 显式 "login_cmd": null = 该 CLI 无安全的无头登录探针（如 traecli/kimi 仅交互式 /login），
    # 跳过登录段：可用性以路径+版本为准，绝不伪造已登录，登录缺失由运行期错误事件浮现
    probe_cfg = manifest.get("probe", {})
    if "login_cmd" in probe_cfg and probe_cfg["login_cmd"] is None:
        result["available"] = True
        result["reason"] = "ok"
        result["logged_in"] = None
        result["login_skipped"] = True
        return result
    login_cmd = probe_cfg.get("login_cmd") or [binary, "status"]
    login_cmd = [path if c == binary else c for c in login_cmd]
    signature = manifest.get("probe", {}).get("login_signature", "Username:")
    try:
        lr = subprocess.run(login_cmd, capture_output=True, text=True, timeout=_PROBE_TIMEOUT,
                           stdin=subprocess.DEVNULL)
        logged_in = signature in (lr.stdout or "")
    except Exception as e:  # noqa: BLE001
        logger.warning("[CLI引擎探针] 登录态命令失败 %s: %s", display_name, e)
        logged_in = False
    result["logged_in"] = logged_in
    if not logged_in:
        result["reason"] = "not_logged_in"
        result["failed_stage"] = "login"
        result["hint"] = "chatEngine.notLoggedIn"
        return result

    result["available"] = True
    result["reason"] = "ok"
    return result


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# 表头/分隔行（非模型名）：整行仅由分隔符或常见表头词构成
_SEP_RE = re.compile(r"^[-=*·—\s|:]+$")
_HEADER_WORDS = ("available model", "model name", "modelid", "list of model", "usage", "current")
# 表头列名单元（整行首列为这些大写词时视为表头行，非模型名）
_HEADER_TOKENS = {"MODEL", "MODELS", "ID", "NAME", "CONTEXT", "WINDOW", "COST",
                  "PRICE", "CURRENCY", "DESCRIPTION", "STATUS", "PROVIDER", "ENABLED", "DEFAULT", "ALIAS"}
# 模型名 token：以字母/数字开头，含字母，允许 . - _ / 等
_MODEL_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-:]*$")


def _extract_model_name(line: str) -> str | None:
    """从一行输出中抽取模型名：去列表符号/表头，取首个像模型 id 的 token。"""
    text = _ANSI_RE.sub("", line).strip()
    if not text or _SEP_RE.match(text):
        return None
    if any(w in text.lower() for w in _HEADER_WORDS):
        return None
    # 去常见列表前缀："- " / "* " / "• " / "1. " / ") "
    text = re.sub(r"^(?:[-*•]\s+|\d+[.)]\s+)", "", text).strip()
    # 名称与描述常以制表符或 2+ 空格分隔，取首字段
    first = re.split(r"\t|  +", text)[0].strip()
    cand = first.split(" ", 1)[0].strip()
    if cand.upper() in _HEADER_TOKENS:
        return None
    if _MODEL_TOKEN_RE.match(cand) and any(c.isalpha() for c in cand):
        return cand
    return None


def list_models(manifest: dict, cli_path_override: str | None = None) -> dict:
    """
    运行 manifest 声明的 models_cmd（如 `qoder --list-models`），返回该引擎当前用户可用模型清单。

    Returns:
        {"ok": bool, "models": [str], "reason": "ok"|"unsupported"|"not_installed"|"not_logged_in"|"probe_error"}
    未声明 models_cmd 的引擎返回 unsupported（前端降级为仅「引擎默认」+ 跳设置）。
    """
    binary = manifest.get("binary", "qoder")
    models_cmd = manifest.get("probe", {}).get("models_cmd")
    if not models_cmd:
        return {"ok": False, "models": [], "reason": "unsupported"}

    path = cli_path_override or shutil.which(binary)
    if not path:
        return {"ok": False, "models": [], "reason": "not_installed"}
    cmd = [path if c == binary else c for c in models_cmd]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=_PROBE_TIMEOUT,
                           stdin=subprocess.DEVNULL)
    except Exception as e:  # noqa: BLE001 - 列模型任何异常降级，绝不抛出
        logger.warning("[CLI引擎列模型] 命令失败 %s: %s", manifest.get("display_name", "CLI"), e)
        return {"ok": False, "models": [], "reason": "probe_error"}

    combined = f"{r.stdout or ''}\n{r.stderr or ''}"
    if "not logged in" in combined.lower():
        return {"ok": False, "models": [], "reason": "not_logged_in"}

    models: list[str] = []
    seen: set[str] = set()
    for line in (r.stdout or "").splitlines():
        name = _extract_model_name(line)
        if name and name not in seen:
            seen.add(name)
            models.append(name)
        if len(models) >= 40:
            break
    return {"ok": True, "models": models, "reason": "ok" if models else "probe_error"}
