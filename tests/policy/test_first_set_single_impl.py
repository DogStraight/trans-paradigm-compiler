"""D10 尾项守卫：FIRST/nullable 只允许一份实现（`core/first_set.py`）。

背景（作者 2026-11-09 批准，规格 `.scratch/audit/D10-first-follow-single-impl.md`）：
同一组递归方程曾在 `parser/follow.py`（规则级不动点）与 `linter/first_set.py`（元素
树递归）各写一份；两份吃同一套元素树、解同一方程，只是**口径开关不同**。已合并为
`core/first_set.py` 单一实现，两侧只留调用/适配。

本文件锁三件事（防"哪天又被各写一份"）：
1. `_elem_first` / `_elem_nullable` / `_seq_first_nullable` / `_compute_first_nullable`
   的定义只允许出现在 `core/first_set.py`（`_compute_first_nullable` 已并入
   `rule_first_nullable`，全仓应为 0 处）；
2. `parser/follow.py` 与 `linter/first_set.py` 都必须改为调用 `core.first_set`；
3. `core/first_set.py` 不得 import 上层（parser/linter/grammar）——依赖方向单向。
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "core" / "first_set.py"
PARSER = ROOT / "parser" / "follow.py"
LINTER = ROOT / "linter" / "first_set.py"

#: 只允许在 core/first_set.py 出现的 FIRST 私有实现名（`_compute_first_nullable`
#: 已并入公开 `rule_first_nullable`，全仓应 0 处）。
FORBIDDEN_DEFS = frozenset({
    "_elem_first",
    "_elem_nullable",
    "_seq_first_nullable",
    "_compute_first_nullable",
})

SKIP_DIRS = frozenset({
    ".git", "__pycache__", ".pytest_cache", "_drafts", ".scratch",
    ".agents", ".venv", "dist", "build", "node_modules",
})
SKIP_PARTS_SUFFIX = (".egg-info",)


def _walk_py_files() -> list[Path]:
    """仓库内受控 Python 文件（跳过 VCS/缓存/草稿/构建产物）。"""
    files: list[Path] = []
    for path in ROOT.rglob("*.py"):
        parts = path.relative_to(ROOT).parts
        if any(part in SKIP_DIRS or part.endswith(SKIP_PARTS_SUFFIX) for part in parts):
            continue
        files.append(path)
    return sorted(files)


def _module_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_first_helpers_defined_only_in_core() -> None:
    """四个 FIRST 私有实现名只允许在 core/first_set.py 定义（单实现判据）。"""
    duplicates: list[str] = []
    for path in _walk_py_files():
        if path == CORE:
            continue
        defined = _module_functions(path) & FORBIDDEN_DEFS
        if defined:
            duplicates.append(f"{path.relative_to(ROOT).as_posix()}: {sorted(defined)}")
    assert not duplicates, (
        "FIRST 私有实现在 core/first_set.py 之外出现（应改为调 core.first_set）：\n  "
        + "\n  ".join(duplicates)
    )


def test_core_exposes_single_public_surface() -> None:
    """core/first_set.py 的公开面：`first_tokens` + `rule_first_nullable`。"""
    names = _module_functions(CORE)
    assert "first_tokens" in names and "rule_first_nullable" in names


def test_callers_route_through_core() -> None:
    """parser 与 linter 两侧都必须调用 core.first_set（删接线即红）。"""
    assert "core.first_set" in PARSER.read_text(encoding="utf-8"), (
        "parser/follow.py 未接 core.first_set（FIRST 又被本地实现？）"
    )
    assert "core.first_set" in LINTER.read_text(encoding="utf-8"), (
        "linter/first_set.py 未接 core.first_set（re-export 被破坏？）"
    )


def _imports_upper_layer(path: Path) -> list[str]:
    """模块顶层 import 的目标里、属于上层（parser/linter/grammar）的项。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in {"parser", "linter", "grammar"}:
                    bad.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in {"parser", "linter", "grammar"}:
                bad.append(node.module)
    return bad


def test_core_first_set_has_no_upward_imports() -> None:
    """依赖方向：core 不得 import parser/linter/grammar（否则下沉位置错了）。"""
    bad = _imports_upper_layer(CORE)
    assert not bad, f"core/first_set.py 反向依赖上层：{bad}"
