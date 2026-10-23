"""C 块内诊断粒度：每条坏语句各报一条位置正确的 phase-statement。

背景：`CompoundStmt` 不是 block 规则、`@Stmt*` 的 trial 错误曾被
`matcher._match_repeat` 丢弃，整块只剩一条 coarse 诊断。修复后
`{...}` 作为括号定界语句容器递归发现子语句，父容器检查器让位给子检查器。

Doc: docs/gaps/gap-parser-linter-approximation.md
"""

from __future__ import annotations

from linter.scanner import LinterScanner

PACK = "grammar/c"


def _scan(src: str):
    return LinterScanner(PACK).scan(src)


def test_each_bad_statement_gets_positioned_diagnostic() -> None:
    src = "void f(void) { a + ; b + ; }\n"
    diags = _scan(src)
    assert len(diags) == 2
    assert {d.code for d in diags} == {"phase-statement"}
    chars = sorted(d.range[0].character for d in diags)
    # 两个错误分别落在第一条/第二条坏语句的 `+` 位置；不是块起点/`}` 位置
    assert chars == [17, 23]


def test_single_bad_statement_reports_once() -> None:
    src = "void f(void) { a + ; b; }\n"
    diags = _scan(src)
    assert len(diags) == 1
    assert diags[0].range[0].character == 17


def test_valid_block_stays_clean() -> None:
    assert _scan("int f(void) { int n; return n; }\n") == []
