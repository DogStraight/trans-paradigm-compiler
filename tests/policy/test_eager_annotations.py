"""tests/policy/test_eager_annotations.py — 注解不得引用未定义名字（Python ≤3.13 兼容门禁）。

**为什么需要这道门禁**（2026-09-26 实测）：本机是 **Python 3.14**，注解默认**惰性求值**
（PEP 649），于是 `def f(x: Any)` 里 `Any` 忘了导入也照样 import 成功；而
`pyproject.toml` 承诺 `requires-python = ">=3.11"`、CI 矩阵是 **3.11/3.12/3.13**——
那里注解**在 def/class 创建时立即求值**，同一条注解直接 `NameError`，**整个模块导入失败**。

实测两例（已修）：`parser/_production.py:788`、`preprocessor/_expand.py:713-715` 用了
`Any` 却没导入。证据（3.14 下也能证伪，只是求值时机不同）：

    >>> parser._production._slots_of.__annotations__
    NameError: name 'Any' is not defined
    （traceback 指到 preprocessor/_expand.py:713 的 __annotate__）

即这条注解**根本求值不了**；3.14 只是把它推迟到了访问时。这类缺陷**本地 3.14 结构性
测不出**，所以必须由门禁守：只静态解析（不 import，避免副作用），把每条注解表达式在
"模块级可见名字 + 内建"里 eval，`NameError` 即违规。

刻意保守（宁可漏也不要误报）：
- 带 `from __future__ import annotations` 的模块**跳过**（注解是字符串，不求值，安全）；
- 含 `import *` 的模块**跳过**（静态解析不出可见名字，会误报）；
- `if TYPE_CHECKING:` 分支里的绑定**不算可见**——那正是运行期不存在的绑定（真 bug）。
"""

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent

_SKIP_DIRS = {"_drafts", "dist", "build", "coverage_html", "__pycache__", ".git",
              ".venv", "node_modules"}


def _iter_py():
    for path in _ROOT.rglob("*.py"):
        rel = path.relative_to(_ROOT)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        yield path, rel


def _has_future_annotations(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(a.name == "annotations" for a in node.names):
                return True
    return False


def _is_type_checking_guard(node: ast.If) -> bool:
    """`if TYPE_CHECKING:`（含 `if typing.TYPE_CHECKING:`）——运行期不成立的分支。"""
    test = node.test
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _module_level_names(body: list[ast.stmt]) -> set[str]:
    """模块级可见名字（递归进 if/try/with/for/while 体；排除 TYPE_CHECKING 分支）。"""
    names: set[str] = set()
    for node in body:
        if isinstance(node, ast.Import):
            names |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names |= {a.asname or a.name for a in node.names}
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
        elif isinstance(node, ast.If):
            if not _is_type_checking_guard(node):
                names |= _module_level_names(node.body) | _module_level_names(node.orelse)
        elif isinstance(node, (ast.Try, ast.With, ast.AsyncWith)):
            names |= _module_level_names(node.body)
            for handler in getattr(node, "handlers", []):
                names |= _module_level_names(handler.body)
            names |= _module_level_names(getattr(node, "orelse", []))
            names |= _module_level_names(getattr(node, "finalbody", []))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            names |= _module_level_names(node.body) | _module_level_names(node.orelse)
    return names


def _has_star_import(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names)
        for node in ast.walk(tree)
    )


def _annotation_exprs(tree: ast.Module):
    """产出 (行号, 表达式源码)——函数参数/返回值 + 变量（含类体与 dataclass 字段）注解。"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs,
                        args.vararg, args.kwarg]:
                if arg is not None and arg.annotation is not None:
                    yield arg.annotation.lineno, ast.unparse(arg.annotation)
            if node.returns is not None:
                yield node.returns.lineno, ast.unparse(node.returns)
        elif isinstance(node, ast.AnnAssign):
            yield node.annotation.lineno, ast.unparse(node.annotation)


def _violations() -> list[str]:
    bad: list[str] = []
    for path, rel in _iter_py():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        if _has_future_annotations(tree) or _has_star_import(tree):
            continue
        names = _module_level_names(tree.body)
        for lineno, expr in _annotation_exprs(tree):
            try:
                eval(expr, {"__builtins__": __builtins__}, {n: None for n in names})
            except NameError as exc:
                bad.append(f"{rel}:{lineno} 注解引用未定义名字：{expr}  →  {exc}")
            except Exception:
                continue  # 其它异常（属性不存在等）不属本门禁
    return bad


def test_no_annotation_uses_undefined_name() -> None:
    """注解里的名字必须在模块级可见（否则 3.11–3.13 上 def/class 创建即 NameError）。"""
    bad = _violations()
    assert not bad, (
        "以下注解引用了运行期不存在的名字——本机 3.14 因 PEP 649 惰性求值不会报，"
        "但 CI 的 3.11/3.12/3.13 会**导入即 NameError**。补导入或改用字符串注解：\n  "
        + "\n  ".join(bad)
    )


def test_gate_actually_catches_missing_import() -> None:
    """反向自检：临时造一个"注解引用未定义名字"的模块，门禁必须报出来。

    没有这条，门禁可能因为解析逻辑失效而**恒绿**（本仓已有"门禁假装有效"的教训）。
    """
    import tempfile

    src = "def f(x: NotImported) -> None:\n    pass\n"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        target = tmp_path / "bad_mod.py"
        target.write_text(src, encoding="utf-8")
        tree = ast.parse(src)
        names = _module_level_names(tree.body)
        hits = []
        for lineno, expr in _annotation_exprs(tree):
            try:
                eval(expr, {"__builtins__": __builtins__}, {n: None for n in names})
            except NameError as exc:
                hits.append((lineno, expr, str(exc)))
        assert hits, "门禁的解析/求值逻辑失效了——连显然的未定义注解都没抓到"
        assert hits[0][1] == "NotImported"
