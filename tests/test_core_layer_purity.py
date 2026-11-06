"""
tests/test_core_layer_purity.py — 分层守护：core/ 不得反向依赖 app/

T-13 验收：`grep -rn "^from app\\|^import app" core/ --include="*.py"` 输出为空。
2026-11-06 遗留清零：函数级懒加载亦已全部改指 core.*，守护升级为全深度禁止。

两条 AST 规则：
1. 模块级 import 不得出现 app.*（含顶层 if/try/with 块内）；
2. 任意深度（含函数/类体懒加载）不得出现 app.*。
"""

import ast
import re
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent / "core"
GREP_PATTERN = re.compile(r"^(?:from|import)\s+app(?:[.\s]|$)")

FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _is_app_module(module: str | None) -> bool:
    return bool(module) and (module == "app" or module.startswith("app."))


def _module_level_imports(tree: ast.Module) -> list[str]:
    """收集模块级 import 的模块名（跳过函数/类体）。"""
    found: list[str] = []
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, FUNC_NODES):
            continue
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # 相对导入（level > 0）不可能指向 app 顶层包
            if node.level == 0:
                found.append(node.module or "")
        else:
            stack.extend(ast.iter_child_nodes(node))
    return found


def _core_files() -> list[Path]:
    return sorted(CORE_DIR.rglob("*.py"))


def test_core_dir_has_files():
    """守卫：路径失配时不要假绿灯。"""
    assert CORE_DIR.is_dir()
    assert len(_core_files()) > 0


def test_no_module_level_app_imports():
    violations = []
    for path in _core_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hits = [m for m in _module_level_imports(tree) if _is_app_module(m)]
        if hits:
            violations.append(f"{path.relative_to(CORE_DIR.parent)} -> {hits}")
    assert not violations, "core/ 存在模块级反向依赖 app：\n" + "\n".join(violations)


def test_no_app_imports_anywhere():
    """全深度扫描：函数/类体内的懒加载同样禁止引用 app.*。"""
    violations = []
    for path in _core_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                hits = [a.name for a in node.names if _is_app_module(a.name)]
            elif isinstance(node, ast.ImportFrom):
                hits = [node.module or ""] if node.level == 0 and _is_app_module(node.module) else []
            else:
                continue
            if hits:
                rel = path.relative_to(CORE_DIR.parent)
                violations.append(f"{rel}:{node.lineno} -> {hits}")
    assert not violations, "core/ 存在反向依赖 app（含函数级懒加载）：\n" + "\n".join(violations)


def test_grep_acceptance_is_empty():
    """复刻验收命令的文本层语义（逐行匹配，不看缩进）。"""
    hits = []
    for path in _core_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if GREP_PATTERN.match(line):
                hits.append(f"{path.relative_to(CORE_DIR.parent)}:{lineno}: {line.strip()}")
    assert not hits, "grep 验收未通过：\n" + "\n".join(hits)
