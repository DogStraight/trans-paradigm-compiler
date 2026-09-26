"""tests/policy/test_no_syntax_warnings.py — 全仓 py 不得有 SyntaxWarning（非法转义等）。

**为什么需要**：`"\\p"` / `"\\<"` 这类**非法转义序列**在字符串里是 SyntaxWarning——本机
Python 3.14 会报、CI 的 pytest 汇总只显示"N warnings"不点名，而 Python 官方已把它标为
"such sequences will not work in the future"（未来版本升为错误）。本仓已咬过两次：
`lexer/capture_runner.py` 的 docstring `\\<换行>`、`tests/policy/test_check_test_isolation.py`
的 docstring 里写了 Windows 路径 `%TEMP%\\pytest-of-…`（`\\p` 非法）——两次都是靠"恰好看到
警告"发现的，不是靠门禁。

判据：把仓库内每个 .py **编译一遍**（`compile()`，`SyntaxWarning` 升为错误），一处都不许有。
只编译不导入 ⇒ 无副作用、无语言装载态污染。含反向自检（造一段非法转义，机制必须报出来）。
"""

import os
import warnings
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent

_SKIP_DIRS = {"_drafts", "dist", "build", "coverage_html", "__pycache__", ".git", ".venv",
              "node_modules"}


def _py_files():
    for path in _ROOT.rglob("*.py"):
        rel = path.relative_to(_ROOT)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        yield path, rel


def _syntax_warnings(text: str, filename: str) -> list[str]:
    """编译源码，返回 SyntaxWarning 文本（不导入、不执行）。"""
    out: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            compile(text, filename, "exec")
        except SyntaxError:
            return out  # 语法错另有门禁；此处只收警告
    for w in caught:
        if issubclass(w.category, SyntaxWarning):
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
