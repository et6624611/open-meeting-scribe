"""
core/cli_engine/event_bridge.py — CLI stream-json 事件 → 软件 SSE 规范事件翻译层
Translate Qoder CLI stream-json NDJSON into the app's canonical SSE event vocabulary.

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

对应取证 / See: CLI 引擎 Spike 报告 §1（协议形状）、§4-M1（打字机需合成）。

设计：
  - 纯函数式：每行原始事件 → 0..N 个规范事件，无内部状态；会话/配对状态由 runner 维护
  - 宽容解析：未知类型/子类型一律忽略，绝不因单行异常中断整个流（R1）
  - 成败判定读 result 事件（is_error/error_code），不信退出码（§4 关键陷阱）
  - M1：CLI 的 text 为整段 block，本层不切分；切分交给 runner 的 chunk_text 合成打字机
  - i18n：面向用户的文案一律携带 hint_key/hint_params（前端 ai-panel 命名空间），
    label/content 仅作中文兜底；工具标签同时携带 label(zh) + label_en
  - 多 CLI 适配：manifest 可选声明 event_schema（语义角色→字段路径映射），
    非 stream-json 形状的事件流按 schema 提取；缺省即 Qoder/Claude 的 stream-json 形状
"""

from __future__ import annotations

import json

# 事件语义常量（与前端 api/chat.ts StreamCallbacks 对齐）
EV_TOKEN = "token"
EV_STAGE = "stage"
EV_TOOL_CALL = "tool_call"
EV_TOOL_RESULT = "tool_result"
EV_DONE = "done"
EV_ERROR = "error"

# 额度耗尽专项映射（§4）
_CREDIT_EXHAUSTED_CODE = "118"


def parse_line(raw_line: str, manifest: dict) -> list[dict]:
    """
    解析一行 stream-json，返回规范事件列表。 / Parse one NDJSON line into canonical events.

    单行解析失败静默跳过（宽容），绝不抛出。 / Malformed lines are silently skipped, never raised.
    """
    raw_line = raw_line.strip()
    if not raw_line or not raw_line.startswith("{"):
        return []
    try:
        evt = json.loads(raw_line)
    except json.JSONDecodeError:
        return []

    etype = evt.get("type")
    subtype = evt.get("subtype")
    ignore_subtypes = set(manifest.get("ignore_subtypes", []))

    # ⓪ 非 stream-json 形状：按 manifest.event_schema 声明的字段路径解释（Gemini/Codex 等预留扩展点）
    schema = manifest.get("event_schema")
    if schema:
        return _parse_by_schema(evt, schema, manifest)

    # ① system 事件：仅 init 有价值（回显 session/工具集），其余噪声丢弃
    if etype == "system":
        if subtype == "artifacts_update" or subtype in ignore_subtypes or subtype is None:
            if subtype is None:
                return []
            return []
        if subtype == "init":
            return [{
                EV_TYPE_KEY: EV_STAGE, "stage": "thinking",
                "label": "引擎已启动", "hint_key": "cli_engine_started",
                "engine_init": {
                    "session_id": evt.get("session_id"),
                    "model": evt.get("model"),
                    "mcp_servers": evt.get("mcp_servers", []),
                    "protocol_version": evt.get("protocol_version"),
                },
            }]
        # permission_denied 作为可解释提示（§2 dont_ask 档）
        if subtype == "permission_denied":
            msg = str(evt.get("message") or evt.get("stderr") or "")
            return [{EV_TYPE_KEY: EV_STAGE, "stage": "thinking", "label": f"⛔ {msg[:80]}",
                     "hint_key": "cli_engine_permission_denied",
                     "hint_params": {"detail": msg[:80]}}]
        return []

    # ② assistant 事件：thinking → stage；text → token（整段，runner 再切）；tool_use → tool_call
    if etype == "assistant":
        out: list[dict] = []
        content = (evt.get("message") or {}).get("content") or []
        for block in content:
            btype = block.get("type")
            if btype == "thinking":
                txt = (block.get("thinking") or "").strip()
                if txt:
                    out.append({EV_TYPE_KEY: EV_STAGE, "stage": "thinking", "label": txt[:80] or "思考中…",
                                "hint_params": {"detail": txt[:80]}})
            elif btype == "text":
                txt = block.get("text") or ""
                if txt.strip():
                    out.append({EV_TYPE_KEY: EV_TOKEN, "content": txt})
            elif btype == "tool_use":
                out.append(_tool_call_event(block, manifest))
        return out

    # ③ user 事件：tool_result → tool_result（按 tool_use_id 关联，runner 侧配对）
    if etype == "user":
        out = []
        content = (evt.get("message") or {}).get("content") or []
        for block in content:
            if block.get("type") == "tool_result":
                is_err = bool(block.get("is_error"))
                summary = _flatten_result(block.get("content"))
                out.append({
                    EV_TYPE_KEY: EV_TOOL_RESULT,
                    "tool_use_id": block.get("tool_use_id"),
                    "success": not is_err,
                    "summary": summary[:200],
                })
        return out

    # ④ result 事件：done / error（成败以此为准）
    if etype == "result":
        return _result_events(evt, manifest)

    return []


EV_TYPE_KEY = "type"  # 规范事件类型字段名


def _tool_call_event(block: dict, manifest: dict) -> dict:
    from core.cli_engine.manifest import resolve_tool_label
    name = block.get("name") or "Unknown"
    label, label_en, icon = resolve_tool_label(manifest, name)
    args = block.get("input") or {}
    return {
        EV_TYPE_KEY: EV_TOOL_CALL,
        "id": block.get("id"),
        "name": name,
        "label": label,
        "label_en": label_en,
        "icon": icon,
        "args": args,
    }


def _flatten_result(content) -> str:
    """tool_result.content 可能是字符串或 [{type:text,...}] 列表。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text", ""))
            elif isinstance(c, str):
                parts.append(c)
        return " ".join(p for p in parts if p)
    return json.dumps(content, ensure_ascii=False) if content is not None else ""


def _result_events(evt: dict, manifest: dict) -> list[dict]:
    usage = evt.get("usage") or {}
    metadata = {
        "model": (evt.get("modelUsage") or {}),
        "usage": usage,
        "finish_reason": evt.get("stop_reason"),
        "id": evt.get("uuid"),
    }
    latency = evt.get("duration_ms")
    is_error = bool(evt.get("is_error"))
    error_code = str(evt.get("error_code")) if evt.get("error_code") is not None else ""
    denials = evt.get("permission_denials") or []

    if is_error:
        errors = evt.get("errors") or []
        first_err = errors[0] if errors else "引擎执行失败"
        mapped = _map_error(error_code, manifest)
        hint_key = "cli_engine_error"
        if mapped == "credit_exhausted":
            first_err = f"本机 {manifest.get('display_name', 'CLI')} 额度不足，请检查账户额度或改用其它模型/内置问答。"
            hint_key = "cli_engine_credit_exhausted"
        return [{EV_TYPE_KEY: EV_ERROR, "content": str(first_err)[:300],
                 "hint_key": hint_key,
                 "hint_params": {"engine": display_name_of(manifest), "detail": str(first_err)[:200]},
                 "engine_error": mapped, "permission_denials": denials}]

    done = {
        EV_TYPE_KEY: EV_DONE,
        "metadata": metadata,
        "latency_ms": latency,
        "engine_iterations": evt.get("num_turns"),
    }
    if denials:
        done["permission_denials"] = denials
    return [done]


def display_name_of(manifest: dict) -> str:
    """引擎品牌展示名（不翻译；本地化后缀由前端 name_key 承担）。"""
    return manifest.get("display_name", "CLI")


def _dig(obj, path: str):
    """按点分路径从嵌套 dict 取值（event_schema 用）；任一段缺失返回 None。"""
    if not path:
        return None
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _parse_by_schema(evt: dict, schema: dict, manifest: dict) -> list[dict]:
    """
    通用事件解释器：按 manifest.event_schema 声明的语义角色→字段路径映射产出规范事件。

    支持的语义角色（均为点分路径）：
      type_path   — 事件类型字段（缺省 "type"）
      done_types / error_types — 判定终态的类型值列表
      text_path   — 回复正文（非空即产出 token）
      error_path  — 错误文案（随 error 事件 content 兜底）
    未知形状宽容忽略（R1）。stream-json 引擎（Qoder/Claude）无需 schema，走主路径。
    """
    etype = _dig(evt, schema.get("type_path", "type"))
    etype = str(etype) if etype is not None else ""
    out: list[dict] = []

    if etype in (schema.get("error_types") or []):
        detail = str(_dig(evt, schema.get("error_path", "")) or "引擎执行失败")[:300]
        return [{EV_TYPE_KEY: EV_ERROR, "content": detail,
                 "hint_key": "cli_engine_error",
                 "hint_params": {"engine": display_name_of(manifest), "detail": detail},
                 "engine_error": _map_error(str(evt.get("error_code") or ""), manifest)}]

    text = _dig(evt, schema.get("text_path", "")) if schema.get("text_path") else None
    if isinstance(text, str) and text.strip():
        out.append({EV_TYPE_KEY: EV_TOKEN, "content": text})

    if etype in (schema.get("done_types") or []):
        out.append({EV_TYPE_KEY: EV_DONE, "metadata": {"model": _dig(evt, schema.get("model_path", ""))},
                    "latency_ms": _dig(evt, schema.get("latency_path", "")) if schema.get("latency_path") else None})
    return out


def _map_error(error_code: str, manifest: dict) -> str:
    return (manifest.get("error_codes", {}) or {}).get(error_code, "engine_error")


def chunk_text(text: str, size: int = 16) -> list[str]:
    """
    将整段文本切成小片以合成打字机效果（M1）。 / Slice a whole text block to fake typewriter streaming.

    按码点切片，保留换行结构。 / Slice by codepoints, preserving newlines.
    """
    if not text:
        return []
    if len(text) <= size:
        return [text]
    return [text[i:i + size] for i in range(0, len(text), size)]
