"""tests/policy/test_no_syntax_warnings.py — 全仓 py 不得有 SyntaxWarning（非法转义等）。

**为什么需要**：`"\\p"` / `"\\<"` 这类**非法转义序列**在字符串里是编译期警告——本机
Python 3.14 会报、CI 的 pytest 汇总只显示"N warnings"不点名，而 Python 官方已把它标为
"such sequences will not work in the future"（未来版本升为错误）。本仓已咬过两次：
`lexer/capture_runner.py` 的 docstring `\\<换行>`、`tests/policy/test_check_test_isolation.py`
的 docstring 里写了 Windows 路径 `%TEMP%\\pytest-of-…`（`\\p` 非法）——两次都是靠"恰好看到
警告"发现的，不是靠门禁。

⚠ **类别随版本变（2026-09-30 CI 3.11 ubuntu 实测）**：非法转义的警告类别在
**Python 3.12 起是 `SyntaxWarning`**（3.14 消息形如 `"\\p" is an invalid escape
sequence…`），**3.11 及以前是 `DeprecationWarning`**（消息形如
`invalid escape sequence 'p'`）。只认 `SyntaxWarning` 会让门禁在 3.11 上**恒绿**
（反向自检 `hits == []` 红，CI 3.11 ubuntu 的活现场）——故判据按"类别或消息"双判：
任何 `SyntaxWarning`，或消息含 `invalid escape sequence` 的警告（覆盖 3.11）。

判据：把仓库内每个 .py **编译一遍**（`compile()`，警告不收手），一处都不许有。
只编译不导入 ⇒ 无副作用、无语言装载态污染。含反向自检（造一段非法转义，机制必须报出来）。
"""

import warnings
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent

_SKIP_DIRS = {"_drafts", "dist", "build", "coverage_html", "__pycache__", ".git", ".venv",
              "node_modules"}

# 3.11 及以前非法转义的 DeprecationWarning 消息标记（3.12+ 走 SyntaxWarning 类别）
_ESCAPE_MARK = "invalid escape sequence"


def _is_invalid_escape(category: type[Warning], message: object) -> bool:
    """该编译警告算不算"非法转义序列"——跨版本判据（见模块 docstring 的类别边界）。"""
    return issubclass(category, SyntaxWarning) or _ESCAPE_MARK in str(message)


def _py_files():
    for path in _ROOT.rglob("*.py"):
        rel = path.relative_to(_ROOT)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        yield path, rel


def _syntax_warnings(text: str, filename: str) -> list[str]:
    """编译源码，返回非法转义类警告的文本（不导入、不执行）。"""
    out: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            compile(text, filename, "exec")
        except SyntaxError:
            return out  # 语法错另有门禁；此处只收警告
    for w in caught:
        if _is_invalid_escape(w.category, w.message):
            out.append(f"{filename}:{w.lineno}  {w.message}")
    return out


def test_no_syntax_warnings_in_repo() -> None:
    """全仓 py 编译零 SyntaxWarning（非法转义序列会随 Python 版本升级变成错误）。"""
    bad: list[str] = []
    for path, rel in _py_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        bad.extend(_syntax_warnings(text, str(rel)))
    assert not bad, (
        "以下文件的字符串里有非法转义序列（SyntaxWarning，未来 Python 会报错）——"
        "改用原始字符串 r\"…\" 或写成 \\\\ 转义：\n  " + "\n  ".join(bad)
    )


def test_gate_catches_invalid_escape() -> None:
    """反向自检：造一段非法转义，机制必须报出来（否则门禁可能因编译方式变化而恒绿）。"""
    hits = _syntax_warnings('X = "C:\\path\\to"\n', "<self-check>")
    assert hits, "自检失败：非法转义序列未被抓到，门禁已失效"
    assert "invalid escape sequence" in hits[0]


def test_escape_predicate_covers_pre_312_deprecation_warning() -> None:
    """跨版本判据：3.11 是 `DeprecationWarning`，3.12+ 是 `SyntaxWarning`——两类都算命中。

    没有这条会退化：在 3.11 上"只认 SyntaxWarning"的判据永远返回空 ⇒ 全仓门禁恒绿
    （CI 3.11 ubuntu 的 `test_gate_catches_invalid_escape` 就是这样红的）。
    """
    assert _is_invalid_escape(DeprecationWarning, "invalid escape sequence 'p'")
    assert _is_invalid_escape(SyntaxWarning, '"\\p" is an invalid escape sequence')
    # 非非法转义的警告不受影响（免得把门禁放宽成"任何警告都算"）
    assert not _is_invalid_escape(UserWarning, "unrelated warning")
    assert not _is_invalid_escape(DeprecationWarning, "invalid decimal literal")
