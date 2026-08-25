"""引擎内建遍测试（ADR-0006 阶段 4b）：PassKind 枚举 + 量化拒绝准则。

pass 从"自由 handler 函数"升格为"类型化内建遍"：
  - kind 字符串 → PassKind 兼容映射（handler→CUSTOM、category→ALIGN）
  - criterion 量化拒绝准则：不满足 → 跳过该遍（布局决策显式化）
"""

import pytest

from grammar.verilog.plugins.formatter.boundary import LineContext
from grammar.verilog.plugins.formatter.engine import (
    FormatterEngine,
    FormatterPass,
    PassKind,
)


def _ctx(line_number: int, scope_depth: int = 1) -> LineContext:
    return LineContext(
        line_number=line_number,
        text="",
        scope_path=[],
        scope_depth=scope_depth,
        in_ifdef=False,
        ifdef_condition="",
    )


class TestPassKind:
    def test_enum_values(self):
        assert PassKind.INDENT.value == "indent"
        assert PassKind.ALIGN.value == "align"
        assert PassKind.WRAP.value == "wrap"

    def test_handler_kind_maps_custom(self):
        """旧 kind="handler" → PassKind.CUSTOM（兼容映射）。"""
        p = FormatterPass(name="x", kind="handler", handler=lambda l, c: l)
        assert p.pass_kind == PassKind.CUSTOM

    def test_category_kind_maps_align(self):
        """旧 kind="category" → PassKind.ALIGN（品类对齐遍）。"""
        p = FormatterPass(name="x", kind="category")
        assert p.pass_kind == PassKind.ALIGN

    def test_named_kind_maps_directly(self):
        p = FormatterPass(name="x", kind="wrap")
        assert p.pass_kind == PassKind.WRAP


class TestCriterion:
    def test_min_group_size_rejects(self):
        """参与行数 < min_group_size → 跳过该遍。"""
        seen = []

        def _spy_pass(lines, ctxs):
            seen.append(list(lines))
            return [l + "!" for l in lines]

        eng = FormatterEngine([
            FormatterPass(
                name="spy", kind="handler", handler=_spy_pass,
                criterion={"min_group_size": 3},
            ),
        ])
        # 2 行 < 3 → 跳过
        out = eng.run(["a", "b"], [_ctx(1), _ctx(2)])
        assert out == ["a", "b"]
        assert seen == []  # 未运行

    def test_min_group_size_passes(self):
        seen = []

        def _spy_pass(lines, ctxs):
            seen.append(list(lines))
            return [l + "!" for l in lines]

        eng = FormatterEngine([
            FormatterPass(
                name="spy", kind="handler", handler=_spy_pass,
                criterion={"min_group_size": 2},
            ),
        ])
        out = eng.run(["a", "b"], [_ctx(1), _ctx(2)])
        assert out == ["a!", "b!"]
        assert seen == [["a", "b"]]

    def test_max_width_rejects(self):
        """无超宽行 → 跳过折行遍（wrap 的实际准则）。"""
        seen = []

        def _spy_pass(lines, ctxs):
            seen.append(list(lines))
            return [l + "!" for l in lines]

        eng = FormatterEngine([
            FormatterPass(
                name="spy", kind="handler", handler=_spy_pass,
                criterion={"max_width": 100},
            ),
        ])
        out = eng.run(["short", "also short"], [_ctx(1), _ctx(2)])
        assert out == ["short", "also short"]
        assert seen == []

    def test_max_width_passes_on_wide_line(self):
        seen = []

        def _spy_pass(lines, ctxs):
            seen.append(list(lines))
            return list(lines)

        eng = FormatterEngine([
            FormatterPass(
                name="spy", kind="handler", handler=_spy_pass,
                criterion={"max_width": 10},
            ),
        ])
        out = eng.run(["this is a long line"], [_ctx(1)])
        assert out == ["this is a long line"]
        assert seen == [["this is a long line"]]

    def test_max_span_rejects(self):
        """参与行跨度 > max_span → 拒绝（组间有大量空行/其他内容）。"""
        seen = []

        def _spy_pass(lines, ctxs):
            seen.append(list(lines))
            return list(lines)

        eng = FormatterEngine([
            FormatterPass(
                name="spy", kind="handler", handler=_spy_pass,
                criterion={"max_span": 2},
            ),
        ])
        # 首尾参与行跨度 4 > 2 → 拒绝
        out = eng.run(["a", "", "", "d"], [_ctx(1), _ctx(2), _ctx(3), _ctx(4)])
        assert out == ["a", "", "", "d"]
        assert seen == []


class TestEngineIntegration:
    def test_build_engine_pass_kinds(self):
        """build_engine 的 pass 都能映射到 PassKind（类型化）。"""
        from grammar.verilog.plugins.formatter import build_engine
        eng = build_engine([])
        for p in eng._passes:
            # 不抛异常即映射成功
            assert isinstance(p.pass_kind, PassKind)
        names = [p.name for p in eng._passes]
        assert "wrap" in names

    def test_wrap_criterion_present(self):
        """wrap pass 带 max_width 拒绝准则。"""
        from grammar.verilog.plugins.formatter import build_engine
        eng = build_engine([])
        wrap = next(p for p in eng._passes if p.name == "wrap")
        assert wrap.criterion == {"max_width": 100}

    def test_category_criterion_present(self):
        """品类对齐 pass 带 min_group_size=2 拒绝准则。"""
        from grammar.verilog.plugins.formatter import build_engine
        eng = build_engine([{"name": "decl", "matcher": {"first_token": ["reg"]}}])
        decl = next(p for p in eng._passes if p.name == "decl")
        assert decl.criterion == {"min_group_size": 2}

    def test_comment_kind_maps_directly(self):
        """wrap_comments 升格为 COMMENT 内建遍（kind="comment"）。"""
        p = FormatterPass(
            name="wrap_comments", kind="comment",
            handler=lambda lines, ctxs: lines,
            criterion={"max_width": 100},
        )
        assert p.pass_kind == PassKind.COMMENT

    def test_comment_pass_engine_dispatch(self):
        """comment 遍带 handler 时引擎正常执行（handler 优先 dispatch）。"""
        def _comment_pass(lines, ctxs):
            return [l + " // c" for l in lines]

        eng = FormatterEngine([
            FormatterPass(
                name="wrap_comments", kind="comment", handler=_comment_pass,
                criterion={"max_width": 0},  # 任何行都超宽 → 运行
            ),
        ])
        out = eng.run(["a"], [_ctx(1)])
        assert out == ["a // c"]

    def test_comment_criterion_skips(self):
        """无超宽注释行 → COMMENT 遍被 max_width 拒绝跳过。"""
        seen = []

        def _comment_pass(lines, ctxs):
            seen.append(list(lines))
            return list(lines)

        eng = FormatterEngine([
            FormatterPass(
                name="wrap_comments", kind="comment", handler=_comment_pass,
                criterion={"max_width": 100},
            ),
        ])
        out = eng.run(["// short"], [_ctx(1)])
        assert out == ["// short"]
        assert seen == []
