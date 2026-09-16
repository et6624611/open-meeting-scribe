"""
core/agent_workspace.py — Agent 角色工作区

作者 / Author: Yongliang Wang
创建 / Created: 2026-09-15
版本 / Version: 1.0.0

职责 / Responsibilities:
  - 角色定义加载（resolve_agent_role） / Role definition loading
  - 角色文件解析（load_role_files） / Role file parsing
  - 角色列表枚举（list_roles） / Role listing
  - YAML front matter 解析 / YAML front matter parsing

角色文件目录结构 / Role file directory structure:
  data/agent/_roles/
    _builtin/          # 预定义角色（系统内置） / Built-in roles
      meeting-minutes/
        AGENT.md       # 人格 + 能力边界（必须） / Personality + capabilities (required)
        *.md           # 附带规则文件（可选） / Additional rule files (optional)
    {custom_name}/     # 用户自定义角色 / User custom roles
      _forked-from     # 溯源标记 / Fork source marker
      AGENT.md
      *.md

查找优先级 / Lookup priority:
  1. 用户自定义区 data/agent/_roles/{role_name}/
  2. 预定义区 data/agent/_roles/_builtin/{role_name}/
  3. 硬编码兜底（Python 常量，由调用方提供） / Hardcoded fallback (provided by caller)

设计文档 / Design doc: docs/design/AGENT_ROLE_SYSTEM.md
架构决策 / ADR: docs/adr/0017-agent角色系统从硬编码提示词到md工作区.md
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# 角色工作区根目录 / Role workspace root
_ROLES_DIR = Path("data/agent/_roles")
_BUILTIN_DIR = _ROLES_DIR / "_builtin"

# 默认角色 / Default role
DEFAULT_ROLE = "meeting-minutes"

# YAML front matter 正则 / YAML front matter regex
_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_front_matter(content: str) -> tuple[dict, str]:
    """
    解析 Markdown 文件的 YAML front matter。

    Returns:
        (metadata_dict, body_without_front_matter)
        若无 front matter，返回 ({}, original_content)
    """
    m = _FRONT_MATTER_RE.match(content)
    if not m:
        return {}, content

    raw_yaml = m.group(1)
    body = content[m.end():]

    # 简易 YAML 解析（避免引入 pyyaml 依赖） / Simple YAML parse (avoid pyyaml dependency)
    meta: dict = {}
    for line in raw_yaml.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # 去除引号 / Strip quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        # 简易列表解析 [a, b, c] / Simple list parse
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            value = [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
        meta[key] = value

    return meta, body


def _read_md_file(path: Path) -> tuple[dict, str] | None:
    """
    读取 .md 文件，返回 (front_matter, body)。
    文件不存在返回 None。
    """
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("读取角色文件失败 %s: %s", path, e)
        return None
    meta, body = _parse_front_matter(content)
    return meta, body


def _find_role_dir(role_name: str) -> tuple[Path, str] | None:
    """
    按优先级查找角色目录：用户自定义 > 预定义。

    Returns:
        (role_dir, source) 或 None
        source: "custom" | "builtin"
    """
    # 安全检查：角色名只允许字母、数字、连字符、下划线 / Security: role name whitelist
    if not re.match(r"^[a-zA-Z0-9_-]+$", role_name):
        logger.warning("角色名包含非法字符，已忽略: %s", role_name)
        return None

    # 1. 用户自定义区 / User custom
    custom_dir = _ROLES_DIR / role_name
    if custom_dir.is_dir() and (custom_dir / "AGENT.md").is_file():
        return custom_dir, "custom"

    # 2. 预定义区 / Built-in
    builtin_dir = _BUILTIN_DIR / role_name
    if builtin_dir.is_dir() and (builtin_dir / "AGENT.md").is_file():
        return builtin_dir, "builtin"

    return None


def load_role_files(role_dir: Path) -> dict:
    """
    加载指定角色目录下的所有 .md 文件（含 insights/ 子目录）。

    Returns:
        {
            "agent_md": str,          # AGENT.md 正文（去除 front matter）
            "agent_meta": dict,        # AGENT.md 的 front matter 元数据
            "extra_files": {           # 其他 .md 文件 {文件名: 正文}
                "summary-template.md": "...",
                "insights/context.md": "...",
            },
        }
    """
    result: dict = {
        "agent_md": "",
        "agent_meta": {},
        "extra_files": {},
    }

    if not role_dir.is_dir():
        return result

    for md_file in sorted(role_dir.glob("*.md")):
        parsed = _read_md_file(md_file)
        if parsed is None:
            continue
        meta, body = parsed

        if md_file.name == "AGENT.md":
            result["agent_md"] = body.strip()
            result["agent_meta"] = meta
        else:
            result["extra_files"][md_file.name] = body.strip()

    # 扫描 insights/ 子目录 / Scan insights/ subdirectory
    insights_dir = role_dir / "insights"
    if insights_dir.is_dir():
        for md_file in sorted(insights_dir.glob("*.md")):
            parsed = _read_md_file(md_file)
            if parsed is None:
                continue
            _meta, body = parsed
            result["extra_files"][f"insights/{md_file.name}"] = body.strip()

    return result


def resolve_agent_role(role_name: str | None = None) -> dict | None:
    """
    解析指定角色的完整定义。

    Args:
        role_name: 角色标识（如 "meeting-minutes"）。
                   None 时返回默认角色。

    Returns:
        {
            "role_name": str,
            "source": "custom" | "builtin",
            "agent_md": str,
            "agent_meta": dict,
            "extra_files": dict,
        }
        角色不存在时返回 None（调用方应回退到硬编码常量）。
    """
    name = role_name or DEFAULT_ROLE
    found = _find_role_dir(name)
    if found is None:
        logger.info("角色文件不存在: %s（将使用硬编码兜底）", name)
        return None

    role_dir, source = found
    files = load_role_files(role_dir)

    if not files["agent_md"]:
        logger.warning("角色 %s 的 AGENT.md 为空，使用硬编码兜底", name)
        return None

    return {
        "role_name": name,
        "source": source,
        "agent_md": files["agent_md"],
        "agent_meta": files["agent_meta"],
        "extra_files": files["extra_files"],
    }


def list_roles() -> list[dict]:
    """
    列出所有可用角色（预定义 + 用户自定义），含元数据。

    Returns:
        [
            {
                "name": "meeting-minutes",
                "source": "builtin",
                "title": "会议纪要员",
                "description": "...",
                "category": "meeting",
                "tags": [...],
            },
            ...
        ]
    """
    roles: list[dict] = []

    # 扫描两个层级的目录 / Scan both levels
    for source, scan_dir in [("builtin", _BUILTIN_DIR), ("custom", _ROLES_DIR)]:
        if not scan_dir.is_dir():
            continue
        for role_dir in sorted(scan_dir.iterdir()):
            if not role_dir.is_dir():
                continue
            # 自定义区跳过 _builtin 子目录本身 / Skip _builtin dir itself in custom scan
            if source == "custom" and role_dir.name.startswith("_"):
                continue
            agent_md_path = role_dir / "AGENT.md"
            if not agent_md_path.is_file():
                continue

            parsed = _read_md_file(agent_md_path)
            if parsed is None:
                continue
            meta, _body = parsed

            roles.append({
                "name": role_dir.name,
                "source": source,
                "title": meta.get("title", role_dir.name),
                "description": meta.get("description", ""),
                "category": meta.get("category", ""),
                "tags": meta.get("tags", []),
                "version": meta.get("version", ""),
            })

    return roles


def get_role_summary_prompt(role_name: str | None = None) -> str | None:
    """
    获取角色的纪要生成模板（summary-template.md 正文）。

    Args:
        role_name: 角色标识，None 时使用默认角色。

    Returns:
        模板正文（去除 front matter），或 None（调用方回退到硬编码 SYSTEM_PROMPT）。
    """
    name = role_name or DEFAULT_ROLE
    found = _find_role_dir(name)
    if found is None:
        return None

    role_dir, _source = found
    template_path = role_dir / "summary-template.md"
    parsed = _read_md_file(template_path)
    if parsed is None:
        return None

    _meta, body = parsed
    return body.strip() or None


def get_role_insight_prompt(role_name: str | None = None) -> str | None:
    """
    获取角色的综合洞察分析提示词（insights.md 正文）。

    查找优先级 / Lookup priority:
      1. 角色目录 insights.md / Role dir insights.md
      2. None（调用方回退到内置默认 prompt） / None (caller falls back to built-in default)

    Args:
        role_name: 角色标识，None 时使用默认角色。

    Returns:
        提示词正文（去除 front matter），或 None。
    """
    name = role_name or DEFAULT_ROLE
    found = _find_role_dir(name)
    if found is None:
        return None

    role_dir, _source = found
    prompt_path = role_dir / "insights.md"
    parsed = _read_md_file(prompt_path)
    if parsed is None:
        return None

    _meta, body = parsed
    return body.strip() or None


def fork_role(source_name: str, target_name: str) -> dict:
    """
    从预定义角色 fork 为用户自定义角色。

    Args:
        source_name: 源角色名（必须是预定义角色）
        target_name: 新角色名（用户自定义）

    Returns:
        {"role_name": str, "files": [str]}

    Raises:
        ValueError: 参数不合法
    """
    import shutil

    # 安全校验 / Security validation
    if not re.match(r"^[a-zA-Z0-9_-]+$", target_name):
        raise ValueError(f"角色名包含非法字符: {target_name}")
    if target_name.startswith("_"):
        raise ValueError(f"角色名不能以下划线开头: {target_name}")

    # 源角色必须存在于预定义区 / Source must exist in builtin
    source_dir = _BUILTIN_DIR / source_name
    if not source_dir.is_dir():
        raise ValueError(f"源角色不存在: {source_name}")

    # 目标不能已存在 / Target must not already exist
    target_dir = _ROLES_DIR / target_name
    if target_dir.exists():
        raise ValueError(f"角色已存在: {target_name}")

    # 复制所有文件 / Copy all files
    shutil.copytree(source_dir, target_dir)

    # 写入溯源标记 / Write fork source marker
    marker = target_dir / "_forked-from"
    marker.write_text(source_name, encoding="utf-8")

    copied_files = [f.name for f in target_dir.iterdir() if f.is_file()]
    logger.info("角色 fork 完成: %s -> %s (%d 个文件)", source_name, target_name, len(copied_files))

    return {
        "role_name": target_name,
        "source": source_name,
        "files": copied_files,
    }


def save_role_file(role_name: str, filename: str, content: str) -> dict:
    """
    保存用户自定义角色的 .md 文件。

    仅允许修改用户自定义区的角色（不可修改预定义角色）。

    Args:
        role_name: 角色名
        filename: 文件名（如 AGENT.md）
        content: 文件内容

    Returns:
        {"role_name": str, "filename": str, "size": int}
    """
    # 安全校验 / Security validation
    if not re.match(r"^[a-zA-Z0-9_-]+$", role_name):
        raise ValueError(f"角色名包含非法字符: {role_name}")
    if not filename.endswith(".md"):
        raise ValueError(f"仅支持 .md 文件: {filename}")
    # 允许 insights/ 子目录前缀 / Allow insights/ subdirectory prefix
    if filename.startswith("insights/"):
        inner = filename[len("insights/"):]
        if ".." in inner or "/" in inner or not inner:
            raise ValueError(f"文件名不合法: {filename}")
    elif ".." in filename or "/" in filename:
        raise ValueError(f"文件名不合法: {filename}")

    # 必须是用户自定义角色（不可修改预定义） / Must be custom role
    custom_dir = _ROLES_DIR / role_name
    builtin_dir = _BUILTIN_DIR / role_name
    if builtin_dir.is_dir() and not custom_dir.is_dir():
        raise ValueError(f"不可修改预定义角色: {role_name}")

    # 角色目录必须存在 / Role dir must exist
    if not custom_dir.is_dir():
        raise ValueError(f"角色不存在: {role_name}")

    file_path = custom_dir / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)  # 确保 insights/ 子目录存在
    file_path.write_text(content, encoding="utf-8")
    logger.info("角色文件已保存: %s/%s (%d 字符)", role_name, filename, len(content))

    return {
        "role_name": role_name,
        "filename": filename,
        "size": len(content),
    }


def delete_role(role_name: str) -> dict:
    """
    删除用户自定义角色。

    预定义角色不可删除。

    Args:
        role_name: 角色名

    Returns:
        {"role_name": str, "deleted_files": int}
    """
    import shutil

    # 安全校验 / Security validation
    if not re.match(r"^[a-zA-Z0-9_-]+$", role_name):
        raise ValueError(f"角色名包含非法字符: {role_name}")

    custom_dir = _ROLES_DIR / role_name
    builtin_dir = _BUILTIN_DIR / role_name

    # 不可删除预定义角色 / Cannot delete builtin roles
    if builtin_dir.is_dir() and not custom_dir.is_dir():
        raise ValueError(f"不可删除预定义角色: {role_name}")

    if not custom_dir.is_dir():
        raise ValueError(f"角色不存在: {role_name}")

    # 统计文件数 / Count files
    file_count = sum(1 for f in custom_dir.iterdir() if f.is_file())

    # 删除目录 / Delete directory
    shutil.rmtree(custom_dir)
    logger.info("角色已删除: %s (%d 个文件)", role_name, file_count)

    return {
        "role_name": role_name,
        "deleted_files": file_count,
    }


def get_role_files(role_name: str) -> dict | None:
    """
    获取角色的所有文件内容（用于编辑器加载，含 insights/ 子目录）。

    Returns:
        {"role_name": str, "source": str, "files": {filename: content}}
        或 None（角色不存在）
    """
    found = _find_role_dir(role_name)
    if found is None:
        return None

    role_dir, source = found
    files: dict[str, str] = {}
    for md_file in sorted(role_dir.glob("*.md")):
        try:
            files[md_file.name] = md_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("读取角色文件失败 %s: %s", md_file, e)

    # 扫描 insights/ 子目录 / Scan insights/ subdirectory
    insights_dir = role_dir / "insights"
    if insights_dir.is_dir():
        for md_file in sorted(insights_dir.glob("*.md")):
            try:
                files[f"insights/{md_file.name}"] = md_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("读取角色文件失败 %s: %s", md_file, e)

    # 读取 fork 标记 / Read fork marker
    fork_marker = role_dir / "_forked-from"
    forked_from = fork_marker.read_text(encoding="utf-8").strip() if fork_marker.is_file() else None

    return {
        "role_name": role_name,
        "source": source,
        "forked_from": forked_from,
        "files": files,
    }
