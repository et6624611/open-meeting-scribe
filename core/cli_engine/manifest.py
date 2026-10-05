"""
core/cli_engine/manifest.py — CLI 引擎声明式清单加载与工具标签解析
Manifest loading and tool-label resolution for the multi-CLI engine adapter layer.

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-25
版本 / Version: 1.0.0

职责 / Responsibilities:
  - 按 engine_id 加载 manifests/<engine_id>.json / Load manifest by engine_id
  - 提供工具名 → 双语标签/lucide 图标解析（含 mcp__<server>__<tool> 归一） / Resolve tool name to bilingual label/icon, incl. mcp__ normalization
  - 授权档位 → CLI argv 片段编译（方案 §3.9-3 / SPIKE M2） / Compile auth tier to argv fragments

国际化 / i18n:
  - tool_labels 条目形如 {"zh": …, "en": …, "icon": <lucide 图标名>}；缺失语言回退另一语言，
    不阻断解析。事件分发时同时携带 label(zh) 与 label_en，由前端按当前 locale 选取。
  - 引擎展示名：display_name 为品牌原文（不翻译）；需本地化后缀的引擎（如国内版）
    以 name_key 字段交给前端 i18n 键翻译。

对应方案 / See: Qoder CLI 引擎方案 §3.11（多 CLI 引擎适配层）、CLI 引擎 Spike 报告 §4。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

MANIFEST_DIR = Path(__file__).resolve().parent / "manifests"

# MCP 工具全名格式（SPIKE §3.2 取证）：mcp__<serverName>__<toolName>
_MCP_PREFIX = "mcp__"


@lru_cache(maxsize=8)
def load_manifest(engine_id: str) -> dict:
    """加载指定引擎清单；缺失时抛 FileNotFoundError（调用方须捕获并回退内置链路）。"""
    path = MANIFEST_DIR / f"{engine_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"CLI 引擎清单缺失 / manifest not found: {engine_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def available_engines() -> list[str]:
    """列出已交付的引擎清单 id（v1 仅 qoder-cli，§3.11-4 防腐设计）。"""
    return sorted(p.stem for p in MANIFEST_DIR.glob("*.json"))


def resolve_tool_label(manifest: dict, tool_name: str, locale: str = "zh") -> tuple[str, str, str]:
    """
    将 CLI 工具名解析为 (主标签, 英文标签, lucide 图标名)。 / Map a CLI tool name to (label, en label, lucide icon).

    归一规则：
      - mcp__server__tool → 取 _mcp 通用标签并附工具本名，避免裸显英文（§3.9-4）
      - 未知内置工具 → _unknown 降级样式（禁止裸显英文 name + 🔧）
      - locale 主标签缺失时回退另一语言（双语均缺才退工具本名）
    """
    labels = manifest.get("tool_labels", {}) or {}

    def _pair(entry: dict, fallback_name: str) -> tuple[str, str]:
        zh = entry.get("zh") or entry.get("en") or fallback_name
        en = entry.get("en") or entry.get("zh") or fallback_name
        return zh, en

    if tool_name.startswith(_MCP_PREFIX):
        parts = tool_name.split("__", 2)
        base = labels.get("_mcp", {"zh": "调用集成工具", "en": "Call integration tool", "icon": "plug"})
        tool_part = parts[2] if len(parts) >= 3 else tool_name
        zh, en = _pair(base, tool_name)
        return f"{zh} · {tool_part}", f"{en} · {tool_part}", base.get("icon", "plug")
    entry = labels.get(tool_name) or labels.get("_unknown", {"zh": tool_name, "icon": "wrench"})
    zh, en = _pair(entry, tool_name)
    return zh, en, entry.get("icon", "wrench")


def compile_auth_argv(manifest: dict, auth_tier: str) -> list[str]:
    """
    将授权档位编译为 CLI argv 片段（前置授权，消除运行时询问）。 / Compile auth tier into argv (pre-authorization).

    SPIKE M2 结论：不使用 --allowed-tools（实测未生效），改用 --permission-mode + --disallowed-tools。
    未知档位安全回退到 readonly（最小权限原则）。

    多 CLI 适配：权限标志名逐厂商不同（如 Claude Code 用 --disallowedTools 而非
    --disallowed-tools），档位内可用 permission_flag / disallowed_flag 覆盖顶层 argv 默认值。
    """
    argv = manifest.get("argv", {}) or {}
    tiers = manifest.get("auth_tiers", {}) or {}
    tier = tiers.get(auth_tier) or tiers.get("readonly", {})
    out: list[str] = []
    mode = tier.get("permission_mode")
    if mode:
        out += [tier.get("permission_flag") or argv.get("permission_flag", "--permission-mode"), mode]
    disallowed = tier.get("disallowed_tools") or []
    if disallowed:
        # 禁止工具标志接受多值；用空格分隔追加
        out += [tier.get("disallowed_flag") or argv.get("disallowed_flag", "--disallowed-tools"), *disallowed]
    return out
