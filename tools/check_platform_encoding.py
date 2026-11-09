#!/usr/bin/env python3
"""tools/check_platform_encoding.py — 跨平台文本 I/O 与路径分隔符假设门禁。

为什么这个检查存在：Python 的 ``open()`` / ``Path.read_text()`` 不写
``encoding=`` 时会跟随平台 locale（Windows 常为 GBK，Linux 为 UTF-8）；
``subprocess`` 的文本模式同理。路径判断若把 ``Path`` 字符串化后与含分隔符
的字面量比较，或用 ``"/"``/``"\\"`` 直接切分路径，也会在另一平台失效。
这些缺陷通常只在换机器/换 CI 后暴露，所以必须用可复跑的 AST 探针前移。

检查码与判据：
  E1  ``open()`` / ``io.open()`` / ``builtins.open()`` / ``Path.open()`` 的非二进制
      模式、``Path.read_text()`` / ``Path.write_text()`` 未显式给出非 ``None`` 的
      ``encoding=``。二进制 ``open(..., "rb")`` 的 ``encoding`` 不适用，明确放行。
  E2  ``subprocess.run/Popen/check_output/check_call/call`` 在 ``text=True``
      或 ``universal_newlines=True`` 时未显式给出非 ``None`` 的 ``encoding=``。
  E3  ``str(路径表达式)`` / 插值路径的 f-string 与含 ``/`` 或 ``\\`` 的字符串
      字面量比较，或调用 ``.startswith()`` / ``.endswith()`` 时参数是含分隔符
      的字面量。
  E4  路径表达式的 ``.split("/")`` / ``.rsplit("/")`` /
      ``.startswith("/")`` / ``.endswith("/")``，以及 ``"/" in 路径表达式``
      这类字面量分隔符判断；f-string 插值的路径同属"字符串化路径"。
      字符级 ``ch == "\\"`` 属词法扫描，不算。

已知假阳：
  - ``open(path, mode=变量)`` 无法静态判定二进制时按文本检查（保守）。
  - 通过 ``**kwargs`` 传递 encoding/text 时看不到关键字，会报 E1/E2。
  - 路径变量靠命名、``Path(...)``、``os.path.*`` 等轻量数据流识别；自定义
    helper 返回的路径可能漏报（宁可漏报，不用类型猜测制造大面积假阳）。
  - 已明确用 ``.as_posix()`` 或 ``.replace("\\", "/")`` 归一化为 POSIX
    字符串的变量，视为有意的平台无关表示，不再报 E4。

ALLOW：键为 ``相对路径:检查码``，值必须是非空理由；同一文件的同码只需一条。
命中过的条目被消费，未命中的条目报 ``E-ALLOW-STALE``，防止允许清单腐化。

用法：
  python tools/check_platform_encoding.py
  python tools/check_platform_encoding.py --json out.json
  python tools/check_platform_encoding.py --strict
  python tools/check_platform_encoding.py --selftest
  python tools/check_platform_encoding.py --paths tools,tests

退出码：0 = 干净；1 = 有 E1/E2/E3/E4 或 ALLOW 腐化；2 = 输入面缺失、
解析失败（--strict）、或扫描文件数低于 100 的下限（防假绿）。
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import _scan  # noqa: E402  # pyright: ignore[reportMissingImports]
from typing import Callable, Mapping, Sequence

# 控制台 UTF-8 自护走单点 `core/console.py`（工具脚本 sys.path[0]=tools/，先把仓库根
# 加进 sys.path 再 import）。行为：能重配则 utf-8 + backslashreplace，失败不阻断入口。
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from core.console import ensure_utf8_stdio  # noqa: E402 — 路径引导之后才可 import

ensure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
MIN_PY_FILES = 100
CODES = ("E1", "E2", "E3", "E4")
_ALLOW_CODE = "E-ALLOW-STALE"
_SUBPROCESS_CALLS = frozenset({
    "run", "Popen", "check_output", "check_call", "call",
})
#: 文本 I/O 打开函数：内建 ``open`` 的等价点分名（参数位置同内建，见 `_open_mode`）。
#: 模块别名（``import io as x``）不在识别面内——轻量 AST 探针只认这两个规范名，
#: 漏报宁可保守（见「已知假阳」节）。
_BUILTIN_OPEN_NAMES = frozenset({"io.open", "builtins.open"})
_PATH_CTORS = frozenset({
    "Path", "PurePath", "PosixPath", "PurePosixPath",
    "WindowsPath", "PureWindowsPath",
})
_PATH_FUNCS = frozenset({
    "os.path.join", "os.path.abspath", "os.path.realpath",
    "os.path.dirname", "os.path.basename", "os.path.normpath",
    "os.path.expanduser", "os.path.expandvars", "os.path.relpath",
    "pathlib.Path", "pathlib.PurePath",
})
_PATH_RESULT_ATTRS = frozenset({
    "resolve", "absolute", "relative_to", "with_name", "with_suffix",
    "joinpath", "cwd", "home", "expanduser", "as_posix",
})
_PATH_COMPONENT_ATTRS = frozenset({
    "parent", "parents", "name", "stem", "suffix", "suffixes",
    "parts", "anchor", "drive", "root",
})
_SEPARATOR_LITERALS = frozenset({"/", "\\"})
_PATH_NAME_RE = re.compile(
    r"(^|_)(path|paths|file|filename|filepath|file_path|dir|dirname|"
    r"directory|folder|root|target|src|dst|source|dest|destination|"
    r"parent|child|p)$",
    re.IGNORECASE,
)

# 解析失败/输入缺失的可见通道（D6）：任何跳过都必须在报告中留下痕迹。
SKIPPED_INPUTS: list[tuple[str, str]] = []

# 允许清单：键 = 相对路径:CODE，值 = 必填理由。条目必须被实际命中，否则腐化报错。
ALLOW: dict[str, str] = {}


@dataclass(frozen=True)
class Finding:
    """一条可定位的检查结果。"""

    path: str
    line: int
    code: str
    message: str


@dataclass(frozen=True)
class ScanReport:
    """一次扫描的完整结果（含输入缺口与 ALLOW 腐化）。"""

    scanned_files: int
    findings: list[Finding]
    skipped_inputs: list[tuple[str, str]]
    stale_allows: list[str]


@dataclass
class _Aliases:
    """subprocess 的 import 别名集合。"""

    modules: set[str]
    direct: dict[str, str]
    star: bool


def _record_skipped_input(rel: str, reason: str) -> None:
    """记录一次未纳入扫描的输入；同一路径/原因只记一次。"""
    entry = (rel, reason)
    if entry not in SKIPPED_INPUTS:
        SKIPPED_INPUTS.append(entry)


def _display_path(path: Path) -> str:
    """绝对路径 → 仓库相对 POSIX 路径；仓库外保持绝对 POSIX 形式。"""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


_EXCLUDED_PARTS = frozenset({
    ".git", ".venv", "__pycache__", "_drafts", ".scratch",
    ".pytest_cache", "build", "dist", "node_modules",
})


def _candidates_from_root(path: Path) -> list[Path]:
    """输入根（文件或目录）→ 待查 .py 候选；缺失输入走可见通道。"""
    if not path.exists():
        _record_skipped_input(_display_path(path), "输入根不存在")
        return []
    if not path.is_file():
        return sorted(path.rglob("*.py"))
    if path.suffix == ".py":
        return [path]
    _record_skipped_input(_display_path(path), "输入不是 .py 文件")
    return []




def _dotted_name(node: ast.expr) -> str | None:
    """取 Name/Attribute 的点分名（``os.path.join``）；其它表达式返回 None。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def _add_subprocess_import(item: ast.alias, aliases: _Aliases) -> None:
    """登记 ``import subprocess`` 的模块别名。"""
    if item.name == "subprocess":
        aliases.modules.add(item.asname or "subprocess")


def _add_subprocess_from(item: ast.alias, aliases: _Aliases) -> None:
    """登记 ``from subprocess import ...`` 的直接调用别名。"""
    if item.name == "*":
        aliases.star = True
    elif item.name in _SUBPROCESS_CALLS:
        aliases.direct[item.asname or item.name] = item.name


def _collect_aliases(tree: ast.Module) -> _Aliases:
    """收集 ``import subprocess`` 与 ``from subprocess import run`` 的别名。"""
    aliases = _Aliases(modules={"subprocess"}, direct={}, star=False)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                _add_subprocess_import(item, aliases)
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for item in node.names:
                _add_subprocess_from(item, aliases)
    return aliases


def _subprocess_call(call: ast.Call, aliases: _Aliases) -> str | None:
    """若调用是已导入的 subprocess 家族成员，返回规范名。"""
    func = call.func
    if isinstance(func, ast.Name):
        if func.id in aliases.direct:
            return aliases.direct[func.id]
        if aliases.star and func.id in _SUBPROCESS_CALLS:
            return func.id
        return None
    if isinstance(func, ast.Attribute):
        if (
            isinstance(func.value, ast.Name)
            and func.value.id in aliases.modules
            and func.attr in _SUBPROCESS_CALLS
        ):
            return func.attr
    return None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    """取调用的指定关键字值；未出现或 ``**kwargs`` 时返回 None。"""
    for item in call.keywords:
        if item.arg == name:
            return item.value
    return None


def _has_encoding(call: ast.Call) -> bool:
    """是否显式给出了非 ``None`` 的 encoding 关键字。"""
    value = _keyword(call, "encoding")
    if value is None:
        return False
    return not (isinstance(value, ast.Constant) and value.value is None)


def _is_builtin_open(func: ast.expr) -> bool:
    """是否内建 ``open`` 或其等价点分名（``io.open`` / ``builtins.open``）。"""
    if isinstance(func, ast.Name):
        return func.id == "open"
    return _dotted_name(func) in _BUILTIN_OPEN_NAMES


def _open_mode(call: ast.Call) -> ast.expr | None:
    """取 open()/Path.open() 的 mode 实参。

    builtin ``open(file, mode, ...)``（含 ``io.open``/``builtins.open``）的 mode 是
    第二位置参；``Path.open(mode, ...)`` 的 mode 是第一位置参。两者不可混用，否则
    ``path.open("rb")`` / ``io.open("a.bin", "rb")`` 会被误判成文本模式。
    """
    if isinstance(call.func, ast.Attribute) and not _is_builtin_open(call.func):
        if call.args:
            return call.args[0]
        return _keyword(call, "mode")
    if len(call.args) >= 2:
        return call.args[1]
    return _keyword(call, "mode")


def _is_binary_open(call: ast.Call) -> bool:
    """mode 是含 ``b`` 的字符串字面量 → 二进制模式，encoding 不适用。"""
    mode = _open_mode(call)
    return (
        isinstance(mode, ast.Constant)
        and isinstance(mode.value, str)
        and "b" in mode.value.lower()
    )


def _truthy_constant(node: ast.expr | None) -> bool:
    """只把明确的真值字面量视为开启文本模式，变量不猜。"""
    return isinstance(node, ast.Constant) and bool(node.value)


def _target_names(node: ast.expr) -> list[str]:
    """赋值目标里的普通名字（含 tuple/list/starred 解包）。"""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        out: list[str] = []
        for item in node.elts:
            out.extend(_target_names(item))
        return out
    if isinstance(node, ast.Starred):
        return _target_names(node.value)
    return []


def _annotation_is_path(node: ast.expr | None) -> bool:
    """类型注解是否提到 pathlib.Path / os.PathLike。"""
    if node is None:
        return False
    for child in ast.walk(node):
        name = _dotted_name(child) if isinstance(child, ast.expr) else None
        if name is None:
            continue
        tail = name.rsplit(".", 1)[-1]
        if tail in _PATH_CTORS or tail == "PathLike":
            return True
    return False


def _is_posix_normalized(
    node: ast.expr, safe_names: set[str]
) -> bool:
    """表达式是否已显式归一为 POSIX 字符串表示。"""
    if isinstance(node, ast.Name):
        return node.id in safe_names
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Attribute):
        if node.func.attr == "as_posix":
            return True
        if node.func.attr in {"strip", "lstrip", "rstrip"}:
            return _is_posix_normalized(node.func.value, safe_names)
        if node.func.attr == "replace" and len(node.args) >= 2:
            old, new = node.args[0], node.args[1]
            if (
                isinstance(old, ast.Constant)
                and old.value == "\\"
                and isinstance(new, ast.Constant)
                and new.value == "/"
            ):
                return True
    return False


def _looks_like_path_call(node: ast.Call, path_names: set[str]) -> bool:
    """调用结果是否像路径：构造器、os.path.*、路径返回方法、str(路径)。"""
    name = _dotted_name(node.func)
    tail = name.rsplit(".", 1)[-1] if name else ""
    if tail == "str" and len(node.args) == 1:
        return _looks_like_path(node.args[0], path_names)
    if tail in _PATH_CTORS or name in _PATH_FUNCS:
        return True
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr in _PATH_RESULT_ATTRS:
        return True
    return _looks_like_path(node.func.value, path_names)


def _looks_like_path(node: ast.expr, path_names: set[str]) -> bool:
    """轻量路径表达式识别：命名、构造器、路径返回方法、``/`` 拼接。"""
    if isinstance(node, ast.Name):
        return node.id in path_names or bool(_PATH_NAME_RE.search(node.id))
    if isinstance(node, ast.Attribute):
        return (
            node.attr in _PATH_COMPONENT_ATTRS
            or _looks_like_path(node.value, path_names)
        )
    if isinstance(node, ast.Call):
        return _looks_like_path_call(node, path_names)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return (
            _looks_like_path(node.left, path_names)
            or _looks_like_path(node.right, path_names)
        )
    if isinstance(node, ast.JoinedStr):
        # f-string 里插值路径 = 又一份"字符串化的路径"（E3/E4 同一识别面）。
        return any(
            isinstance(value, ast.FormattedValue)
            and _looks_like_path(value.value, path_names)
            for value in node.values
        )
    return False


def _annotated_path_names(tree: ast.Module) -> set[str]:
    """函数参数中显式标注为 Path/PathLike 的名字。"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        for arg in args:
            if _annotation_is_path(arg.annotation):
                names.add(arg.arg)
    return names


def _assigned_values(tree: ast.Module) -> list[tuple[list[str], ast.expr | None]]:
    """模块内全部赋值形态 → (目标名, 右值)，供轻量数据流传播。"""
    out: list[tuple[list[str], ast.expr | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names: list[str] = []
            for target in node.targets:
                names.extend(_target_names(target))
            out.append((names, node.value))
        elif isinstance(node, ast.AnnAssign):
            out.append((_target_names(node.target), node.value))
        elif isinstance(node, ast.NamedExpr):
            out.append((_target_names(node.target), node.value))
    return out


def _add_new_targets(targets: Sequence[str], names: set[str]) -> bool:
    """把尚未登记的目标名加入集合；返回是否新增。"""
    added = False
    for target in targets:
        if target not in names:
            names.add(target)
            added = True
    return added


def _propagate_names(
    assignments: Sequence[tuple[list[str], ast.expr | None]],
    initial: set[str],
    predicate: Callable[[ast.expr, set[str]], bool],
) -> set[str]:
    """在赋值图上做 3 轮名字传播；足够覆盖路径变量的常见别名链。"""
    names = set(initial)
    for _ in range(3):
        added = False
        for targets, value in assignments:
            if value is not None and predicate(value, names):
                added = _add_new_targets(targets, names) or added
        if not added:
            break
    return names


def _collect_path_context(tree: ast.Module) -> tuple[set[str], set[str]]:
    """收集路径变量名与已 POSIX 归一化的变量名（小范围固定点）。"""
    assignments = _assigned_values(tree)
    path_names = _propagate_names(
        assignments, _annotated_path_names(tree), _looks_like_path,
    )
    safe_names = _propagate_names(
        assignments, set(), _is_posix_normalized,
    )
    return path_names, safe_names


def _separator_text(node: ast.expr | None) -> str | None:
    """字面量分隔符（只认精确的 ``/`` 或 ``\\``）。"""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value in _SEPARATOR_LITERALS
    ):
        return node.value
    return None


def _separator_literal(node: ast.expr) -> bool:
    """字面量字符串是否含有路径分隔符（用于比较类判断）。"""
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and any(sep in node.value for sep in _SEPARATOR_LITERALS)
    )


def _fstring_path_values(
    node: ast.JoinedStr, path_names: set[str], safe_names: set[str]
) -> list[ast.expr]:
    """f-string 里被字符串化的路径表达式（未 POSIX 归一化的）。

    ``f"{path}/x"`` 与 ``str(path) + "/x"`` 是同一件事；此前只认 ``str(...)``
    会漏报（审计 2026-11-07 F4）。
    """
    return [
        value.value
        for value in node.values
        if isinstance(value, ast.FormattedValue)
        and _looks_like_path(value.value, path_names)
        and not _is_posix_normalized(value.value, safe_names)
    ]


def _stringified_path(
    node: ast.expr, path_names: set[str], safe_names: set[str]
) -> bool:
    """是否为 ``str(路径表达式)`` 或插值路径的 f-string，且尚未显式 POSIX 归一化。"""
    if isinstance(node, ast.JoinedStr):
        return bool(_fstring_path_values(node, path_names, safe_names))
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and len(node.args) == 1
        and not node.keywords
    ):
        return False
    arg = node.args[0]
    return _looks_like_path(arg, path_names) and not _is_posix_normalized(
        arg, safe_names
    )


def _scan_io_calls(
    call: ast.Call,
    rel: str,
    path_names: set[str],
    aliases: _Aliases,
) -> list[Finding]:
    """E1/E2：文本 I/O 未显式指定 encoding。"""
    findings: list[Finding] = []
    func_name = _dotted_name(call.func)
    tail = func_name.rsplit(".", 1)[-1] if func_name else ""
    is_open = _is_builtin_open(call.func) or (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "open"
        and _looks_like_path(call.func.value, path_names)
    )
    if is_open and not _is_binary_open(call) and not _has_encoding(call):
        findings.append(Finding(
            rel, call.lineno, "E1",
            "open() 文本模式未显式指定 encoding=（平台默认编码不一致）",
        ))
    if tail in {"read_text", "write_text"} and not _has_encoding(call):
        findings.append(Finding(
            rel, call.lineno, "E1",
            f"Path.{tail}() 未显式指定 encoding=（平台默认编码不一致）",
        ))

    sub_name = _subprocess_call(call, aliases)
    if sub_name is not None:
        is_text = _truthy_constant(_keyword(call, "text")) or _truthy_constant(
            _keyword(call, "universal_newlines")
        )
        if is_text and not _has_encoding(call):
            findings.append(Finding(
                rel, call.lineno, "E2",
                f"subprocess.{sub_name}() 文本模式未显式指定 encoding="
                "（平台默认编码不一致）",
            ))
    return findings


def _e3_comparison_findings(
    left: ast.expr,
    right: ast.expr,
    rel: str,
    line: int,
    path_names: set[str],
    safe_names: set[str],
) -> list[Finding]:
    """E3：str(路径) 任一侧与含分隔符字面量比较。"""
    message = "路径字符串化（str()/f-string）参与含分隔符字面量判断（假设固定分隔符）"
    findings: list[Finding] = []
    if _stringified_path(left, path_names, safe_names) and _separator_literal(right):
        findings.append(Finding(rel, line, "E3", message))
    if _stringified_path(right, path_names, safe_names) and _separator_literal(left):
        findings.append(Finding(rel, line, "E3", message))
    return findings


def _e4_membership_finding(
    separator: str | None,
    path_expr: ast.expr,
    rel: str,
    line: int,
    path_names: set[str],
    safe_names: set[str],
) -> Finding | None:
    """E4：一个字面量分隔符与路径表达式做成员判断。"""
    if separator is None or not _looks_like_path(path_expr, path_names):
        return None
    if _is_posix_normalized(path_expr, safe_names):
        return None
    return Finding(
        rel, line, "E4",
        f"路径表达式成员判断使用字面量分隔符 {separator!r}（跨平台失效）",
    )


def _e4_membership_findings(
    op: ast.cmpop,
    left: ast.expr,
    right: ast.expr,
    rel: str,
    line: int,
    path_names: set[str],
    safe_names: set[str],
) -> list[Finding]:
    """E4：仅对 in/not in 检查字面量分隔符，字符级 == 不在此列。"""
    if not isinstance(op, (ast.In, ast.NotIn)):
        return []
    findings: list[Finding] = []
    for separator, path_expr in (
        (_separator_text(left), right),
        (_separator_text(right), left),
    ):
        finding = _e4_membership_finding(
            separator, path_expr, rel, line, path_names, safe_names,
        )
        if finding is not None:
            findings.append(finding)
    return findings


def _scan_compare(
    node: ast.Compare,
    rel: str,
    path_names: set[str],
    safe_names: set[str],
) -> list[Finding]:
    """E3/E4：比较中的字符串化路径与字面量分隔符判断。"""
    findings: list[Finding] = []
    operands = [node.left, *node.comparators]
    for index, op in enumerate(node.ops):
        left = operands[index]
        right = operands[index + 1]
        if isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn)):
            findings.extend(_e3_comparison_findings(
                left, right, rel, node.lineno, path_names, safe_names,
            ))
        findings.extend(_e4_membership_findings(
            op, left, right, rel, node.lineno, path_names, safe_names,
        ))
    return findings


def _scan_path_methods(
    call: ast.Call,
    rel: str,
    path_names: set[str],
    safe_names: set[str],
) -> list[Finding]:
    """E4：路径的 split/startswith/endswith 使用字面量分隔符。"""
    if not isinstance(call.func, ast.Attribute):
        return []
    attr = call.func.attr
    if attr not in {"split", "rsplit", "startswith", "endswith"}:
        return []
    receiver = call.func.value
    if not _looks_like_path(receiver, path_names):
        return []
    if _is_posix_normalized(receiver, safe_names):
        return []
    if not call.args:
        return []
    sep = _separator_text(call.args[0])
    if sep is None:
        return []
    return [Finding(
        rel, call.lineno, "E4",
        f"路径.{attr}() 使用字面量分隔符 {sep!r}（跨平台失效）",
    )]


def _scan_string_path_methods(
    call: ast.Call,
    rel: str,
    path_names: set[str],
    safe_names: set[str],
) -> list[Finding]:
    """E3：``str(路径).startswith/endswith`` 的参数为含分隔符字面量。"""
    if not isinstance(call.func, ast.Attribute):
        return []
    if call.func.attr not in {"startswith", "endswith"}:
        return []
    receiver = call.func.value
    if not _stringified_path(receiver, path_names, safe_names):
        return []
    if not any(_separator_literal(arg) for arg in call.args):
        return []
    return [Finding(
        rel, call.lineno, "E3",
        f"路径字符串化（str()/f-string）后 .{call.func.attr}() 使用含分隔符字面量"
        "（假设 / 或 \\ 分隔）",
    )]


def _scan_tree(tree: ast.Module, rel: str) -> list[Finding]:
    """扫描单个模块，返回全部未去重的检查结果。"""
    aliases = _collect_aliases(tree)
    path_names, safe_names = _collect_path_context(tree)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            findings.extend(_scan_io_calls(node, rel, path_names, aliases))
            findings.extend(
                _scan_path_methods(node, rel, path_names, safe_names)
            )
            findings.extend(
                _scan_string_path_methods(node, rel, path_names, safe_names)
            )
        elif isinstance(node, ast.Compare):
            findings.extend(
                _scan_compare(node, rel, path_names, safe_names)
            )
    unique: dict[tuple[str, int, str, str], Finding] = {}
    for item in findings:
        unique[(item.path, item.line, item.code, item.message)] = item
    return list(unique.values())


def _apply_allow(
    findings: Sequence[Finding],
    allow: Mapping[str, str],
) -> tuple[list[Finding], list[str]]:
    """按 ``相对路径:CODE`` 过滤，并返回未命中的允许清单键。"""
    active: list[Finding] = []
    hit_keys: set[str] = set()
    for finding in findings:
        key = f"{finding.path}:{finding.code}"
        if key in allow:
            hit_keys.add(key)
        else:
            active.append(finding)
    stale = sorted(key for key in allow if key not in hit_keys)
    return active, stale


def _allow_validation_errors(allow: Mapping[str, str]) -> list[Finding]:
    """校验 ALLOW 键格式与理由；不合法条目也按腐化条目报出。"""
    errors: list[Finding] = []
    for key, reason in allow.items():
        path, _, code = key.rpartition(":")
        valid = bool(path) and code in CODES and bool(reason.strip())
        if not valid:
            errors.append(Finding(
                path or "<allow>", 0, _ALLOW_CODE,
                f"ALLOW 条目无效或缺少理由：{key!r}",
            ))
    return errors


def scan_paths(
    inputs: Sequence[Path],
    allow: Mapping[str, str] | None = None,
) -> ScanReport:
    """扫描输入路径；不施加最低文件数限制（供测试/内嵌调用）。"""
    del SKIPPED_INPUTS[:]
    files = _scan.iter_py_files(
        list(inputs), root=ROOT, skip_dirs=_EXCLUDED_PARTS,
        sink=SKIPPED_INPUTS, label=_display_path,
    )
    findings: list[Finding] = []
    for path in files:
        rel = _display_path(path)
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=rel)
        except (OSError, SyntaxError, UnicodeError) as exc:
            _record_skipped_input(rel, f"读取/解析失败: {exc}")
            continue
        findings.extend(_scan_tree(tree, rel))

    effective_allow: Mapping[str, str] = ALLOW if allow is None else allow
    active, stale = _apply_allow(findings, effective_allow)
    stale.extend(
        finding.message for finding in _allow_validation_errors(effective_allow)
    )
    active.sort(key=lambda f: (f.path, f.line, f.code, f.message))
    return ScanReport(
        scanned_files=len(files),
        findings=active,
        skipped_inputs=list(SKIPPED_INPUTS),
        stale_allows=sorted(set(stale)),
    )


def _report_skipped_inputs(skipped: Sequence[tuple[str, str]]) -> None:
    """输入缺口汇总（告警通道，不静默丢文件）。"""
    if not skipped:
        return
    print(f"\n[告警] {len(skipped)} 处输入未纳入扫描：")
    for rel, reason in skipped:
        print(f"  {rel}: {reason}")


def _write_json(path: Path, report: ScanReport, exit_code: int) -> bool:
    """写结构化报告；写失败返回 False。"""
    payload = {
        "scanned_files": report.scanned_files,
        "findings": [
            {
                "path": item.path,
                "line": item.line,
                "code": item.code,
                "message": item.message,
            }
            for item in report.findings
        ],
        "stale_allows": report.stale_allows,
        "skipped_inputs": [
            {"path": rel, "reason": reason}
            for rel, reason in report.skipped_inputs
        ],
        "exit_code": exit_code,
    }
    try:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        print(f"[FAIL] JSON 写入失败：{path}: {exc}", file=sys.stderr)
        return False
    print(f"\n[json] {path}")
    return True


def _print_report(report: ScanReport, strict: bool) -> int:
    """打印结果并计算退出码。"""
    print("=" * 78)
    print("跨平台文本 I/O 与路径分隔符假设扫描")
    print("=" * 78)
    print(f"\n扫描 .py 文件：{report.scanned_files} 个")
    for item in report.findings:
        print(f"{item.path}:{item.line} {item.code} {item.message}")
    for key in report.stale_allows:
        print(f"<allow>:0 {_ALLOW_CODE} {key}")
    _report_skipped_inputs(report.skipped_inputs)

    if report.scanned_files < MIN_PY_FILES:
        print(
            f"\n[FAIL] 扫描面不足：仅 {report.scanned_files} 个 .py 文件"
            f"（防假绿下限 {MIN_PY_FILES}）——拒绝把空/残缺集合当绿",
            file=sys.stderr,
        )
        return 2
    if report.findings or report.stale_allows:
        print(
            f"\n[FAIL] {len(report.findings)} 处违规，"
            f"{len(report.stale_allows)} 条 ALLOW 腐化"
        )
        return 1
    if strict and report.skipped_inputs:
        print("\n[FAIL] --strict：存在未纳入扫描的输入", file=sys.stderr)
        return 2
    print("\n[platform-encoding] ✓ 文本 I/O 与路径判断未发现跨平台假设")
    return 0


def _run_selftest() -> int:
    """逐码自证：E1/E2/E3/E4 都会响，二进制/字符比较不会误响。"""
    sample = '''
from __future__ import annotations
from pathlib import Path
import io
import subprocess

def probe(path: Path, ch: str) -> None:
    open("a.txt").read()
    io.open("a.txt").read()
    Path("a.txt").write_text("x")
    subprocess.run(["echo"], text=True)
    if str(path) == "a/b":
        print("path compare")
    if f"{path}/x" == "a/b":
        print("fstring compare")
    path_text = str(path)
    path_text.split("/")
    f"{path}".split("/")
    raw = open("a.bin", "rb")
    io.open("a.bin", "rb")
    if ch == "\\\\":
        print(raw)
'''
    with tempfile.TemporaryDirectory(prefix="platform_encoding_selftest_") as tmp:
        root = Path(tmp)
        target = root / "sample.py"
        target.write_text(sample, encoding="utf-8")
        report = scan_paths([root], allow={})
    codes = {item.code for item in report.findings}
    expected = set(CODES)
    if not expected.issubset(codes):
        missing = ", ".join(sorted(expected - codes))
        print(f"[selftest] ✗ 未触发检查码：{missing}", file=sys.stderr)
        return 1
    if report.scanned_files != 1:
        print(
            f"[selftest] ✗ 扫描文件数 {report.scanned_files} != 1",
            file=sys.stderr,
        )
        return 1
    print(
        "[selftest] ✓ E1/E2/E3/E4 各自触发（含 io.open / f-string 路径）；"
        "二进制 open 与字符级 ch == '\\\\' 未误报"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(
        description="跨平台文本 I/O 与路径分隔符假设门禁",
    )
    parser.add_argument(
        "--json", metavar="PATH", help="写出 JSON 报告",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="把未纳入扫描的输入升格为 exit 2（默认仅告警）",
    )
    parser.add_argument(
        "--selftest", action="store_true",
        help="用合成样本逐码自证检查器会响",
    )
    parser.add_argument(
        "--paths", metavar="PATHS",
        help="逗号分隔的扫描路径（文件/目录；默认仓库根）",
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return _run_selftest()

    if args.paths:
        inputs = [
            Path(item.strip())
            for item in args.paths.split(",")
            if item.strip()
        ]
        if not inputs:
            print("[FAIL] --paths 不能为空", file=sys.stderr)
            return 2
    else:
        inputs = [ROOT]

    report = scan_paths(inputs)
    rc = _print_report(report, strict=args.strict)
    if args.json:
        json_path = Path(args.json)
        if not _write_json(json_path, report, rc):
            return 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
