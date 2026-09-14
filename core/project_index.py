"""
core/project_index.py — 项目索引与检索 / Project index and retrieval

职责 / Responsibilities:
  1. 文本提取（md/txt/docx/pdf） / Text extraction (md/txt/docx/pdf)
  2. 关键词提取（轻量实现） / Keyword extraction (lightweight)
  3. 文件夹扫描与索引构建 / Folder scanning and index building
  4. 基于关键词的检索（供 AI 对话注入上下文） / Keyword-based retrieval (for AI chat context injection)

数据文件 / Data files:
  data/project_index/{id}.json — 索引缓存 / Index cache

依赖 / Dependencies:
  core.projects — 项目 CRUD（get_project）及常量 / Project CRUD (get_project) and constants
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 数据路径 / Data paths
DATA_DIR = Path("data")
INDEX_DIR = DATA_DIR / "project_index"

# 支持的文件类型 / Supported file types
SUPPORTED_EXTENSIONS = {".md", ".txt", ".docx", ".pdf"}

# 排除的目录
EXCLUDED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".DS_Store", ".Trash", "dist", "build", ".tox", ".mypy_cache",
}


# ============================================================
# 文本提取
# ============================================================

def _extract_text_md(file_path: Path) -> str:
    """读取 Markdown / 纯文本文件"""
    try:
        return file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_text_docx(file_path: Path) -> str:
    """读取 DOCX 文件文本"""
    try:
        from docx import Document
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        logger.warning("python-docx 未安装，跳过 DOCX: %s", file_path.name)
        return ""
    except Exception as e:
        logger.warning("读取 DOCX 失败 %s: %s", file_path.name, e)
        return ""


def _extract_text_pdf(file_path: Path) -> str:
    """读取 PDF 文件文本"""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(str(file_path))
        texts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
        return "\n".join(texts)
    except ImportError:
        logger.warning("PyPDF2 未安装，跳过 PDF: %s", file_path.name)
        return ""
    except Exception as e:
        logger.warning("读取 PDF 失败 %s: %s", file_path.name, e)
        return ""


def extract_text(file_path: Path) -> str:
    """根据文件类型提取文本"""
    ext = file_path.suffix.lower()
    if ext in (".md", ".txt"):
        return _extract_text_md(file_path)
    elif ext == ".docx":
        return _extract_text_docx(file_path)
    elif ext == ".pdf":
        return _extract_text_pdf(file_path)
    return ""


# ============================================================
# 关键词提取（轻量实现，不引入分词库）
# ============================================================

def _extract_keywords(text: str, max_keywords: int = 10) -> list[str]:
    """
    从文本中提取关键词。

    策略：
      1. Markdown 标题行
      2. 大写英文术语
      3. 中文书名号 / 引号内容
    """
    keywords = []

    # 1. Markdown 标题
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            if title and len(title) < 50:
                keywords.append(title)

    # 2. 英文术语（首字母大写的词）
    english = re.findall(r'\b[A-Z][a-zA-Z]{2,}\b', text[:3000])
    keywords.extend(english[:5])

    # 3. 中文书名号 / 引号内容
    cn_quoted = re.findall(r'[《「](.+?)[》」]', text[:3000])
    keywords.extend(cn_quoted[:3])

    # 去重
    seen = set()
    unique = []
    for kw in keywords:
        key = kw.lower()
        if key not in seen:
            seen.add(key)
            unique.append(kw)

    return unique[:max_keywords]


# ============================================================
# 文件扫描与索引
# ============================================================

def _scan_folder(folder_path: str, exclude_dirs: set[str] | None = None) -> list[dict]:
    """扫描文件夹，返回文件信息列表"""
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        logger.warning("文件夹不存在: %s", folder_path)
        return []

    # 合并静态排除目录与动态排除目录（同步子目录）
    effective_excludes = EXCLUDED_DIRS | (exclude_dirs or set())

    files = []
    for root, dirs, filenames in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in effective_excludes]

        for fname in filenames:
            if fname.startswith("."):
                continue
            fpath = Path(root) / fname
            ext = fpath.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            try:
                stat = fpath.stat()
                text = extract_text(fpath)

                # 摘要：前 200 字符
                summary = text[:200].replace("\n", " ").strip() if text else ""

                # 关键词
                keywords = _extract_keywords(text)

                # 标题：第一个 Markdown 标题或文件名
                title = fname
                for line in text.split("\n"):
                    line = line.strip()
                    if line.startswith("#"):
                        title = line.lstrip("#").strip()
                        break

                files.append({
                    "path": str(fpath),
                    "relative_path": str(fpath.relative_to(folder)),
                    "name": fname,
                    "type": ext.lstrip("."),
                    "title": title,
                    "summary": summary,
                    "keywords": keywords,
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "text_length": len(text),
                })
            except Exception as e:
                logger.warning("扫描文件失败 %s: %s", fpath, e)

    return files


def scan_project(project_id: str) -> dict:
    """扫描项目所有文件夹，构建索引"""
    # 延迟导入避免循环依赖
    from core.projects import DEFAULT_SYNC_SUBFOLDER_NAME, get_project

    project = get_project(project_id)
    if not project:
        raise ValueError(f"项目不存在: {project_id}")

    # 收集所有同步子目录名称，扫描时动态排除
    sync_subfolder_names = set()
    sync_subfolder_names.add(DEFAULT_SYNC_SUBFOLDER_NAME)
    for folder_info in project.get("folders", []):
        custom_name = folder_info.get("sync_subfolder_name")
        if custom_name:
            sync_subfolder_names.add(custom_name)

    all_files = []
    for folder_info in project.get("folders", []):
        folder_path = folder_info["path"]
        files = _scan_folder(folder_path, exclude_dirs=sync_subfolder_names)
        all_files.extend(files)
        logger.info("扫描文件夹 %s: %d 个文件", folder_path, len(files))

    # 保存索引
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    index_data = {
        "project_id": project_id,
        "files": all_files,
        "indexed_at": datetime.now().isoformat(),
        "total_files": len(all_files),
        "total_size": sum(f["size"] for f in all_files),
    }
    index_file = INDEX_DIR / f"{project_id}.json"
    from core.fs_atomic import atomic_write_json
    atomic_write_json(index_file, index_data)

    logger.info("项目索引构建完成: %s, %d 个文件", project["name"], len(all_files))
    return index_data


def get_project_index(project_id: str) -> dict | None:
    """获取项目索引"""
    index_file = INDEX_DIR / f"{project_id}.json"
    if not index_file.exists():
        return None
    try:
        with open(index_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("加载索引失败: %s", e)
        return None


def is_index_stale(project_id: str) -> bool:
    """
    检查索引是否过期（文件夹内有文件变更）。

    策略：比较每个关联文件夹的最新 mtime 与索引构建时间，
    任一文件夹有更新则判定为过期。
    """
    from core.projects import get_project

    project = get_project(project_id)
    if not project:
        return False

    index = get_project_index(project_id)
    if not index:
        return True  # 无索引，视为过期

    try:
        indexed_at = datetime.fromisoformat(index["indexed_at"])
    except (ValueError, KeyError):
        return True

    for folder_info in project.get("folders", []):
        folder = Path(folder_info["path"])
        if not folder.exists():
            continue
        # 递归查找最新修改时间
        try:
            latest_mtime = max(
                (p.stat().st_mtime for p in folder.rglob("*") if p.is_file()),
                default=0,
            )
            if datetime.fromtimestamp(latest_mtime) > indexed_at:
                return True
        except Exception:
            continue

    return False


# ============================================================
# 检索
# ============================================================

def search_project(project_id: str, query: str, limit: int = 5) -> list[dict]:
    """
    在项目索引中搜索相关文件。

    基于的文件名 / 标题 / 关键词 / 摘要的关键词匹配。
    """
    index = get_project_index(project_id)
    if not index:
        return []

    query_lower = query.lower()
    query_terms = query_lower.split()

    scored = []
    for f in index.get("files", []):
        score = 0

        # 文件名匹配（权重最高）
        if query_lower in f["name"].lower():
            score += 10
        for term in query_terms:
            if term in f["name"].lower():
                score += 3

        # 标题匹配
        if query_lower in f.get("title", "").lower():
            score += 8
        for term in query_terms:
            if term in f.get("title", "").lower():
                score += 2

        # 关键词匹配
        for kw in f.get("keywords", []):
            for term in query_terms:
                if term in kw.lower():
                    score += 4

        # 摘要匹配
        if query_lower in f.get("summary", "").lower():
            score += 3
        for term in query_terms:
            if term in f.get("summary", "").lower():
                score += 1

        if score > 0:
            scored.append((score, f))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:limit]]


def _build_project_overview(project: dict, index: dict | None) -> str:
    """
    构建项目概览文本（始终注入，不依赖搜索命中）。

    包含项目名称、关联文件夹、已索引文件清单。
    """
    project_name = project.get("name", "未知项目")
    folders = project.get("folders", [])
    folder_lines = "\n".join(
        f"- {f['path']}" for f in folders
    ) if folders else "- （未关联文件夹）"

    parts = [
        f"## 当前项目：{project_name}",
        f"\n### 关联文件夹\n{folder_lines}",
    ]

    if index and index.get("files"):
        total = index.get("total_files", len(index["files"]))
        parts.append(f"\n### 已索引文件（共 {total} 个）")
        for f in index["files"]:
            title = f.get("title", "")
            label = f"{f['name']}" + (f" — {title}" if title and title != f["name"] else "")
            parts.append(f"- {label}（{f.get('relative_path', f['name'])}）")
    else:
        parts.append("\n### 已索引文件\n- （尚未扫描索引，无法列出文件内容）")

    return "\n".join(parts)


def get_project_context_for_chat(
    project_id: str,
    query: str,
    max_chars: int = 6000,
) -> tuple[str, list[dict]]:
    """
    获取项目上下文文本，用于注入 AI 对话系统提示词。

    始终返回项目元数据（名称、文件夹、文件清单），
    搜索命中时追加相关文件的完整内容（而非仅摘要）。

    Returns:
        (context_text, source_files)
        context_text: 注入系统提示词的文本
        source_files: 引用的文件列表（供前端展示来源）
    """
    from core.projects import get_project

    if not project_id:
        return "", []

    project = get_project(project_id)
    if not project:
        return "", []

    # 索引过期时自动重建（文件夹内有文件变更）
    if is_index_stale(project_id):
        logger.info("索引已过期，自动重建: %s", project_id)
        try:
            scan_project(project_id)
        except Exception as e:
            logger.error("自动索引重建失败: %s, %s", project_id, e)

    index = get_project_index(project_id)

    # 始终构建项目概览（名称 + 文件夹 + 文件清单）
    overview = _build_project_overview(project, index)
    context_parts = [overview]
    source_files: list[dict] = []

    # 尝试按关键词搜索，命中则追加文件完整内容（而非仅摘要）
    results = search_project(project_id, query, limit=5)
    if results:
        context_parts.append(f"\n## 与「{query}」相关的资料（完整内容）")
        total_chars = len(overview)
        for f in results:
            file_path = Path(f["path"])
            if not file_path.exists():
                continue

            text = extract_text(file_path)
            if not text:
                continue

            # 读取完整文件内容（而非仅前800字符），让AI深入理解
            # 限制单个文件最大2000字符，避免上下文过长
            full_content = text[:2000].strip()
            entry = f"\n### {f['title']}\n来源: {f['relative_path']}\n\n{full_content}"

            if total_chars + len(entry) > max_chars:
                # 如果超出总限制，尝试截取
                remaining = max_chars - total_chars
                if remaining > 200:  # 至少保留200字符
                    entry = entry[:remaining]
                    context_parts.append(entry)
                break

            context_parts.append(entry)
            total_chars += len(entry)
            source_files.append({
                "title": f["title"],
                "path": f["relative_path"],
                "name": f["name"],
            })

    return "\n".join(context_parts), source_files
