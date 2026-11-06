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

import pytest

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


# ============================================================
# T-23 守护：禁止聚合层回指 getter（_ce/_sm/_rec/_t/_ib/_chat_mod/_get_tasks）
# ============================================================

APP_DIR = Path(__file__).resolve().parent.parent / "app"

# 曾经的运行时回指 getter：子模块借此读取父聚合模块命名空间，供测试打桩穿透。
# 已全部改为直连真实来源模块，此处永久禁止复活。
FORBIDDEN_BACKPOINTER_GETTERS = {
    "_ce", "_sm", "_rec", "_t", "_ib", "_chat_mod", "_get_tasks",
}

# 聚合父模块 -> 其拆出的子模块（子模块不得反向 import 父聚合模块）
AGGREGATOR_SUBMODULES = {
    "core.cli_engine.context_export": {
        "core/cli_engine/context_paths",
        "core/cli_engine/context_render",
        "core/cli_engine/context_index",
    },
    "core.audio_recording": {
        "core.audio_devices",
        "core.audio_record",
        "core.audio_stream",
    },
}


def _module_name(path: Path, root: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _resolve_import(node: ast.ImportFrom, current: str) -> str | None:
    """把 ImportFrom 解析成绝对模块名（仅处理单级 target：from x import y）。"""
    if node.level == 0:
        return node.module
    parts = current.split(".")
    # 当前模块 core.a.b → 包 core.a；level=1 指向该包，level=2 指向其父
    base = parts[:-1]
    for _ in range(node.level - 1):
        base = base[:-1]
    if node.module:
        return ".".join(base + node.module.split("."))
    return ".".join(base)


# ============================================================
# T-24 守护：router 之间禁止互调（聚合父 → 子路由除外）
# ============================================================

ROUTERS_DIR = APP_DIR / "routers"

# 聚合父路由 -> 其拆出的子路由（父仅负责汇总注册；业务写在各子模块）
AGGREGATOR_CHILDREN = {
    "chat": {"chat_history_routes", "chat_stream_routes", "chat_actions_routes"},
    "record": {"record_devices", "record_lifecycle", "record_speakers", "record_state", "record_summary"},
    "settings": {"settings_core", "settings_engines", "settings_extras", "settings_test"},
}


def _router_modules() -> dict[str, ast.Module]:
    """收集声明了 router = APIRouter(...) 的模块。"""
    out: dict[str, ast.Module] = {}
    for path in sorted(ROUTERS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "router" for t in node.targets)
            ):
                out[path.stem] = tree
                break
    return out


def test_routers_do_not_cross_import():
    routers = _router_modules()
    violations = []
    for name, tree in routers.items():
        allowed = AGGREGATOR_CHILDREN.get(name, set())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            target = _resolve_import(node, f"app.routers.{name}")
            if not target or not target.startswith("app.routers."):
                continue
            dep = target.split(".")[2]
            if dep in routers and dep not in allowed:
                violations.append(f"app/routers/{name}.py:{node.lineno} -> {dep}")
    assert not violations, (
        "router 互调（仅允许聚合父 → 子路由）：\n" + "\n".join(violations)
    )


def _iter_py_files(root: Path):
    return sorted(root.rglob("*.py"))


def test_no_backpointer_getters():
    violations = []
    for root in (CORE_DIR, APP_DIR):
        for path in _iter_py_files(root):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, FUNC_NODES) and node.name in FORBIDDEN_BACKPOINTER_GETTERS:
                    rel = path.relative_to(root.parent)
                    violations.append(f"{rel}:{node.lineno} def {node.name}()")
    assert not violations, "聚合层回指 getter 复活：\n" + "\n".join(violations)


def test_core_does_not_import_pipeline_runner():
    """T-25：执行编排层只能由启动入口注入，存储/检测/动作层不得反向 import。"""
    violations = []
    for path in _core_files():
        if path.name == "pipeline_runner.py":
            continue
        current = _module_name(path, CORE_DIR.parent)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if _resolve_import(node, current) == "core.pipeline_runner":
                    rel = path.relative_to(CORE_DIR.parent)
                    violations.append(f"{rel}:{node.lineno} from core.pipeline_runner import ...")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "core.pipeline_runner":
                        rel = path.relative_to(CORE_DIR.parent)
                        violations.append(f"{rel}:{node.lineno} import core.pipeline_runner")
    assert not violations, "core 反向依赖 pipeline_runner：\n" + "\n".join(violations)


def test_submodules_do_not_import_aggregator_parent():
    violations = []
    for aggregator, submodules in AGGREGATOR_SUBMODULES.items():
        for path in _core_files():
            current = _module_name(path, CORE_DIR.parent)
            if current not in submodules:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                target = _resolve_import(node, current)
                if target == aggregator:
                    rel = path.relative_to(CORE_DIR.parent)
                    violations.append(f"{rel}:{node.lineno} -> {target}")
    assert not violations, "子模块反向 import 聚合父模块：\n" + "\n".join(violations)


# ============================================================
# T-25 钩子契约：注册后转调注入实现；未注册时明确报错（不静默）
# ============================================================

class TestPipelineHooks:
    def test_registered_hook_delegates_to_injected_impl(self, monkeypatch):
        from core import pipeline_hooks

        calls = []
        monkeypatch.setattr(pipeline_hooks, "_run_pipeline_task", None)
        monkeypatch.setattr(pipeline_hooks, "_run_stage2_task", None)
        pipeline_hooks.register(
            run_pipeline_task=lambda *a, **k: calls.append(("stage1", a, k)),
            run_stage2_task=lambda *a, **k: calls.append(("stage2", a, k)),
        )
        assert pipeline_hooks.is_registered()
        pipeline_hooks.run_pipeline_task("tid", "/tmp/a.wav", "a.wav", None, None)
        pipeline_hooks.run_stage2_task("tid", "/tmp/a.wav", {0: "甲"})
        assert calls == [
            ("stage1", ("tid", "/tmp/a.wav", "a.wav", None, None), {}),
            ("stage2", ("tid", "/tmp/a.wav", {0: "甲"}), {}),
        ]

    def test_unregistered_hook_raises_with_actionable_message(self, monkeypatch):
        from core import pipeline_hooks

        monkeypatch.setattr(pipeline_hooks, "_run_pipeline_task", None)
        monkeypatch.setattr(pipeline_hooks, "_run_stage2_task", None)
        assert not pipeline_hooks.is_registered()
        with pytest.raises(pipeline_hooks.PipelineHookNotRegisteredError, match="pipeline_hooks.register"):
            pipeline_hooks.run_pipeline_task("tid")
        with pytest.raises(pipeline_hooks.PipelineHookNotRegisteredError, match="pipeline_hooks.register"):
            pipeline_hooks.run_stage2_task("tid")
