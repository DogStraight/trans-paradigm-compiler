"""Linter 检查器注册表（CheckerRegistry）单元测试 — 扁平容错 + internal-error。

固化 validate_all 的契约：
    - 单个检查器崩溃不影响其他（扁平架构的解耦收益）
    - 崩溃转 linter-internal-error 诊断（不静默吞——否则合法样本因检查器
      崩溃而"不报错=绿"假绿，生产事故温床，2026-08-08 隐患修复机制）
    - 空 token 流时位置回退 (0,0)，不越界
"""

from linter import LintDiagnostic, Position
from linter.checker import CheckerRegistry


class _GoodChecker:
    """正常检查器：返回一个可配置 code 的错误。"""

    start = 0
    end = 1

    def __init__(self, code="phase-statement", message="test"):
        self._code = code
        self._message = message

    def validate(self, tokens):
        return [
            LintDiagnostic(
                range=(Position(0, 0), Position(0, 0)),
                message=self._message,
                severity=1,
                code=self._code,
            )
        ]


class _BrokenChecker:
    """崩溃检查器：validate 抛异常（模拟检查器内部 bug / 未覆盖输入）。"""

    start = 0
    end = 1

    def validate(self, tokens):
        raise RuntimeError("boom")


def test_broken_checker_produces_internal_error():
    """崩溃检查器 → linter-internal-error 诊断（崩溃可见，不静默吞）。"""
    reg = CheckerRegistry()
    reg.add(_BrokenChecker())
    errs = reg.validate_all([])
    assert any(e.code == "linter-internal-error" for e in errs)
    # message 含检查器类型与异常，便于定位
    assert any(
        "_BrokenChecker" in e.message and "boom" in e.message for e in errs
    )


def test_broken_checker_does_not_hide_others():
    """扁平容错：崩溃检查器不影响其他检查器，但崩溃仍可见（防假绿）。"""
    reg = CheckerRegistry()
    reg.add(_GoodChecker(code="phase-statement"))
    reg.add(_BrokenChecker())
    errs = reg.validate_all([])
    codes = {e.code for e in errs}
    assert "phase-statement" in codes  # 正常检查器的错误保留
    assert "linter-internal-error" in codes  # 崩溃也可见（防假绿）


def test_empty_tokens_position_fallback():
    """空 token 流 + 崩溃 → 位置回退 (0,0)，不越界崩溃冒泡。"""
    reg = CheckerRegistry()
    reg.add(_BrokenChecker())
    errs = reg.validate_all([])
    assert errs
    assert errs[0].range[0] == Position(0, 0)


def test_validation_flat_merge():
    """多个正常检查器的错误扁平合并。"""
    reg = CheckerRegistry()
    reg.add(_GoodChecker(code="phase-statement", message="a"))
    reg.add(_GoodChecker(code="phase-expr", message="b"))
    errs = reg.validate_all([])
    assert {e.code for e in errs} == {"phase-statement", "phase-expr"}
