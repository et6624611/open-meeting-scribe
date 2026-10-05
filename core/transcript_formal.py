"""
core/transcript_formal.py — AI 书面版（PLAN-TRANSCRIPT-LAYERING WP-2）

仅会后运行：对已完成会议的逐字稿逐句书面化，结果落独立 sidecar
``data/tasks/{task_id}.formal.json``，绝不写回 task.dialogue（原文永不改）。

锚点 = ``sentence_id``；``source_sig``（句数 + 原文 sha1）失效时 API 返回
``status: "stale"``，前端要求重新生成，不展示错位书面版。

路由闸门完全复用 ``core.routing.get_routing_decision("llm")``，不新增任何
静默切付费逻辑；trial 路径的配额计量与纪要生成同路径（云端代理内部完成）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from core.fs_atomic import atomic_write_json

logger = logging.getLogger(__name__)

SIDECAR_VERSION = 1
CHUNK_SIZE = 25
TEMPERATURE = 0.2

# 路由判定中不可用的 reason（空 reason = 正常可用；byok_key_missing + auto_switched
# 表示用户已全局同意改用体验配额，属可用）
_BLOCKED_REASONS = {
    "source_not_set",
    "trial_requires_login",
    "trial_quota_exhausted",
    "trial_quota_exhausted_no_fallback",
    "byok_key_missing_cloud_unavailable",
    "local_endpoint_misconfigured",
    "local_unsupported",
}

# 同任务生成去重锁（进程内） / Per-task in-flight guard
_inflight: set[str] = set()
_inflight_guard = threading.Lock()


class FormalizeError(Exception):
    """书面化前置条件失败（路由层映射为 4xx）。"""

    def __init__(self, code: str, reason: str = "", http_status: int = 409):
        super().__init__(code)
        self.code = code
        self.reason = reason
        self.http_status = http_status


# ============================================================
# 提示词契约（单测锁定，不得随意改口径）
# ============================================================

SYSTEM_PROMPT = (
    "你是会议转写稿的书面化编辑，只把口语表达改写为规范书面语。\n"
    "规则：\n"
    "1. 去除啰嗦、重复与口语填充，可补主语、可把碎句连为通顺复句；\n"
    "2. 不得增删任何事实、观点或结论；数字、日期、人名、机构名、专名必须原样保留；\n"
    "3. 不做语音识别纠错，不替换同音字或你认为的错别字；\n"
    "4. 原文含犹豫、勉强、让步、否定条件或态度保留（如“行吧”“再说吧”“原则上同意”"
    "“我不是说不行”“可能吧”），书面句必须保留同等弱化语气，且 tone_flag 置 \"weakened\"；"
    "语气明确肯定的正常句子 tone_flag 置 null；你不确定是否弱化时一律置 \"weakened\"；\n"
    "5. 只输出 JSON 数组，与输入同 sentence_id、同数量、同顺序；禁止输出 Markdown 代码块、"
    "注释或任何解释。"
)


def build_user_prompt(chunk: list[dict]) -> str:
    payload = [{"sentence_id": s["sentence_id"], "text": s["text"]} for s in chunk]
    return (
        "把下面的口语句子数组书面化，逐句回填。\n"
        "输入：\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n输出格式："
        "[{\"sentence_id\": 整数, \"text\": \"书面句\", \"tone_flag\": null 或 \"weakened\"}]"
    )


# ============================================================
# 句子扁平化与签名
# ============================================================

def flatten_sentences(dialogue: list[dict] | None) -> list[dict]:
    """dialogue → 扁平句列表 [{sentence_id, begin_time, text}]，按说话人段落/句序。

    sentence_id 缺失（极旧任务）时退化为顺序下标，保证锚点在同一文件内稳定。
    """
    flat: list[dict] = []
    any_missing = False
    for block in dialogue or []:
        if not isinstance(block, dict):
            continue
        for s in block.get("sentences") or []:
            if not isinstance(s, dict):
                continue
            if not isinstance(s.get("sentence_id"), int):
                any_missing = True
            flat.append({
                "sentence_id": s.get("sentence_id"),
                "begin_time": s.get("begin_time", 0) or 0,
                "text": s.get("text", "") or "",
            })
    if any_missing:
        for i, s in enumerate(flat):
            s["sentence_id"] = i
    return flat


def source_signature(dialogue: list[dict] | None) -> dict:
    """原文签名：句数 + 逐句 sha1（锚点 id、时间戳、文本均参与）。"""
    flat = flatten_sentences(dialogue)
    h = hashlib.sha1()
    for s in flat:
        h.update(f"{s['sentence_id']}|{int(s['begin_time'])}|{s['text']}\n".encode("utf-8"))
    return {"count": len(flat), "hash": h.hexdigest()}


# ============================================================
# sidecar 读写
# ============================================================

def _tasks_dir() -> Path:
    try:
        from app.store import TASKS_DIR
        return Path(TASKS_DIR)
    except Exception:
        return Path("data/tasks")


def formal_sidecar_path(task_id: str) -> Path:
    return _tasks_dir() / f"{task_id}.formal.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _base_doc(*, scope: str, auto: bool, sig: dict, model: str, source: str) -> dict:
    return {
        "version": SIDECAR_VERSION,
        "status": "running",
        "scope": scope,
        "auto": bool(auto),
        "source_sig": sig,
        "model": model,
        "source": source,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "created_at": _now(),
        "finished_at": "",
        "error": "",
        "progress": {"done": 0, "total": 0},
        "items": [],
    }


def write_running_sidecar(
    task_id: str, *, scope: str, auto: bool, sig: dict,
    model: str, source: str, total: int, items: list[dict] | None = None,
) -> dict:
    """路由层先写 running 再返回；items 为选区生成时带入的合并基底。"""
    doc = _base_doc(scope=scope, auto=auto, sig=sig, model=model, source=source)
    doc["progress"]["total"] = total
    doc["items"] = items or []
    atomic_write_json(formal_sidecar_path(task_id), doc)
    return doc


def load_formal(task_id: str, dialogue: list[dict] | None = None) -> dict | None:
    """读 sidecar；给 dialogue 时实时做 staleness 判定（不改文件）。无文件 → None。"""
    path = formal_sidecar_path(task_id)
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[书面版] task={task_id[:8]} sidecar 解析失败: {e}")
        return {
            "version": SIDECAR_VERSION, "status": "error", "scope": "full",
            "auto": False, "source_sig": {"count": 0, "hash": ""},
            "model": "", "source": "",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "created_at": "", "finished_at": "",
            "error": "formal_sidecar_corrupt", "items": [],
        }
    if dialogue is not None and doc.get("status") == "done":
        sig = doc.get("source_sig") or {}
        current = source_signature(dialogue)
        if sig.get("count") != current["count"] or sig.get("hash") != current["hash"]:
            doc = {**doc, "status": "stale"}
    return doc


# ============================================================
# 路由闸门
# ============================================================

def llm_route_guard() -> dict:
    """返回可用的 llm 路由判定；不可用抛 FormalizeError（带 routing reason）。"""
    from core.routing import get_routing_decision

    d = get_routing_decision("llm")
    if d.get("route") in ("cloud", "direct") and d.get("reason") not in _BLOCKED_REASONS:
        return d
    raise FormalizeError(
        "formalize_route_unavailable",
        reason=d.get("reason") or "route_unavailable",
    )


# ============================================================
# LLM 回填解析
# ============================================================

def _strip_fence(content: str) -> str:
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def parse_chunk_response(content: str, expected_ids: list[int]) -> list[dict]:
    """解析单块回填，严格校验同 id/同数量/同顺序。失败抛 ValueError（调用方重试一次）。"""
    try:
        data = json.loads(_strip_fence(content))
    except json.JSONDecodeError as e:
        raise ValueError(f"json_parse_failed: {e}") from e
    if not isinstance(data, list):
        raise ValueError("response_not_array")
    if len(data) != len(expected_ids):
        raise ValueError(f"count_mismatch: {len(data)} != {len(expected_ids)}")
    items: list[dict] = []
    for i, raw in enumerate(data):
        if not isinstance(raw, dict):
            raise ValueError(f"item_not_object@{i}")
        sid = raw.get("sentence_id")
        if sid != expected_ids[i]:
            raise ValueError(f"id_mismatch@{i}: {sid!r} != {expected_ids[i]}")
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"empty_text@{i}")
        flag = raw.get("tone_flag")
        if flag not in ("weakened", None):
            flag = "weakened" if flag else None
        items.append({"sentence_id": sid, "text": text.strip(), "tone_flag": flag})
    return items


# ============================================================
# 生成主流程（后台线程执行）
# ============================================================

def _merge_items(base: list[dict], new: list[dict]) -> list[dict]:
    merged = {it["sentence_id"]: it for it in base if isinstance(it, dict)}
    for it in new:
        merged[it["sentence_id"]] = it
    return list(merged.values())


def _prepare_generation(
    task_id: str,
    sentence_ids: list[int] | None,
    *,
    auto: bool,
    reserve: bool,
) -> dict:
    """全部前置校验 + running sidecar。reserve=True 时占用 in-flight 锁（由生成方释放）。"""
    from app.store import get_llm_config, tasks

    task = tasks.get(task_id)
    if task is None:
        raise FormalizeError("task_not_found", http_status=404)
    if task.get("status") != "completed":
        raise FormalizeError("formalize_requires_postmeeting")

    if reserve:
        with _inflight_guard:
            if task_id in _inflight:
                raise FormalizeError("formalize_already_running")
            _inflight.add(task_id)

    try:
        decision = llm_route_guard()
        model = get_llm_config().get("model", "qwen-plus")
        source = decision.get("source") or ""

        flat = flatten_sentences(task.get("dialogue"))
        if not flat:
            raise FormalizeError("formalize_no_sentences")

        if sentence_ids:
            wanted = set(sentence_ids)
            targets = [s for s in flat if s["sentence_id"] in wanted]
            if not targets:
                raise FormalizeError("formalize_no_sentences")
            scope = "selection"
        else:
            targets = flat
            scope = "full"

        sig = source_signature(task.get("dialogue"))

        # 选区生成：同签名旧 sidecar 的 items 作为 upsert 基底；否则从空开始
        base_items: list[dict] = []
        if scope == "selection":
            old = load_formal(task_id, task.get("dialogue"))
            if old and old.get("status") in ("done", "running") and old.get("items"):
                old_sig = old.get("source_sig") or {}
                if old_sig.get("hash") == sig["hash"]:
                    base_items = old.get("items") or []

        doc = write_running_sidecar(
            task_id, scope=scope, auto=auto, sig=sig,
            model=model, source=source, total=len(targets), items=base_items,
        )
    except Exception:
        # 占锁后预检/写 running 失败：释放锁，避免任务永久不可生成
        if reserve:
            with _inflight_guard:
                _inflight.discard(task_id)
        raise
    return {"task": task, "flat": flat, "targets": targets, "scope": scope,
            "base_items": base_items, "doc": doc, "model": model}


def prepare_formalize(task_id: str, sentence_ids: list[int] | None = None) -> dict:
    """路由层同步预检：校验 + 占锁 + 先写 running sidecar（随后后台执行生成）。"""
    return _prepare_generation(task_id, sentence_ids, auto=False, reserve=True)


def generate_formal_version(
    task_id: str,
    sentence_ids: list[int] | None = None,
    *,
    auto: bool = False,
    _reserve: bool = True,
) -> dict:
    """生成书面版并落 sidecar。前置条件失败抛 FormalizeError；LLM 失败落 error sidecar。

    auto=True 且设置关闭时直接返回 {"skipped": "auto_disabled"}，不发起任何调用。
    _reserve=False 表示锁已由 prepare_formalize 占用（后台任务复用同一次预检口径）。
    """
    if auto:
        try:
            from app.store import get_transcript_config
            auto_on = bool(
                get_transcript_config().get("formal", {}).get("auto_generate", False)
            )
        except Exception:
            auto_on = False
        if not auto_on:
            return {"skipped": "auto_disabled"}

    try:
        # reserve=False 时锁由 prepare_formalize 预占，预检失败同样要释放
        prep = _prepare_generation(task_id, sentence_ids, auto=auto, reserve=_reserve)
    except FormalizeError as e:
        with _inflight_guard:
            _inflight.discard(task_id)
        # 路由已先写 running：后台预检失败（如状态/路由中途变化）收口为 error
        if not _reserve:
            _mark_running_error(task_id, f"aborted: {e.code}")
        raise

    try:
        flat = prep["flat"]
        targets = prep["targets"]
        scope = prep["scope"]
        base_items = prep["base_items"]
        doc = prep["doc"]
        model = prep["model"]

        from core.llm import chat_completion_full

        usage_sum = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        new_items: list[dict] = []
        chunks = [targets[i:i + CHUNK_SIZE] for i in range(0, len(targets), CHUNK_SIZE)]

        for ci, chunk in enumerate(chunks):
            expected_ids = [s["sentence_id"] for s in chunk]
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(chunk)},
            ]
            parsed: list[dict] | None = None
            last_err = ""
            for attempt in (1, 2):  # 块失败重试 1 次
                try:
                    result = chat_completion_full(messages, model=model, temperature=TEMPERATURE)
                    for k in usage_sum:
                        usage_sum[k] += int(result.usage.get(k, 0) or 0)
                    parsed = parse_chunk_response(result.content, expected_ids)
                    break
                except Exception as e:  # 传输/解析/校验失败均允许一次重试
                    last_err = str(e)
                    logger.warning(
                        f"[书面版] task={task_id[:8]} 块 {ci + 1}/{len(chunks)} "
                        f"第 {attempt} 次失败: {e}"
                    )
            if parsed is None:
                return _finish_error(task_id, doc, base_items, f"chunk_failed: {last_err}")

            new_items.extend(parsed)

            # 进度落盘（running 态允许半截 items，崩溃后用户重新生成即可）
            doc["items"] = _merge_items(base_items, new_items)
            doc["usage"] = usage_sum
            doc["progress"] = {"done": min(len(new_items), len(targets)), "total": len(targets)}
            atomic_write_json(formal_sidecar_path(task_id), doc)

        order = {s["sentence_id"]: i for i, s in enumerate(flat)}
        final_items = _merge_items(base_items, new_items)
        final_items.sort(key=lambda it: order.get(it["sentence_id"], 1 << 30))

        doc.update({
            "status": "done",
            "items": final_items,
            "usage": usage_sum,
            "progress": {"done": len(targets), "total": len(targets)},
            "finished_at": _now(),
            "error": "",
        })
        atomic_write_json(formal_sidecar_path(task_id), doc)
        logger.info(
            f"[书面版] task={task_id[:8]} 完成 scope={scope} "
            f"{len(final_items)} 句，tone={sum(1 for i in final_items if i.get('tone_flag'))}，"
            f"tokens={usage_sum['total_tokens']}，source={doc.get('source')}"
        )
        return doc
    finally:
        with _inflight_guard:
            _inflight.discard(task_id)


def _mark_running_error(task_id: str, error: str) -> None:
    """后台启动前预检失败：把已存在的 running sidecar 收口为 error。"""
    try:
        path = formal_sidecar_path(task_id)
        if not path.exists():
            return
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("status") != "running":
            return
        doc.update({"status": "error", "finished_at": _now(), "error": error[:500]})
        atomic_write_json(path, doc)
    except Exception as e:
        logger.warning(f"[书面版] task={task_id[:8]} running 收口失败: {e}")


def _finish_error(task_id: str, doc: dict, base_items: list[dict], error: str) -> dict:
    """整任务失败：保留生成前的 items 基底（不留半截新 items），落 error 态。"""
    doc.update({
        "status": "error",
        "items": base_items,
        "finished_at": _now(),
        "error": error[:500],
    })
    try:
        atomic_write_json(formal_sidecar_path(task_id), doc)
    except Exception as e:
        logger.error(f"[书面版] task={task_id[:8]} error sidecar 写入失败: {e}")
    logger.error(f"[书面版] task={task_id[:8]} 失败: {error}")
    return doc


def maybe_auto_formalize(task_id: str) -> None:
    """stage2 完成后的自动钩子：设置关/路由不可用/生成失败都不影响会议产物。

    守护线程执行，不阻塞管线 worker。
    """
    def _run() -> None:
        try:
            result = generate_formal_version(task_id, None, auto=True)
            if result.get("skipped"):
                return
            logger.info(f"[书面版] task={task_id[:8]} 自动生成完成")
        except FormalizeError as e:
            logger.info(f"[书面版] task={task_id[:8]} 自动生成跳过: {e.code}/{e.reason}")
        except Exception as e:
            logger.warning(f"[书面版] task={task_id[:8]} 自动生成失败（不影响会议产物）: {e}")

    threading.Thread(target=_run, daemon=True, name=f"auto-formal-{task_id[:8]}").start()
