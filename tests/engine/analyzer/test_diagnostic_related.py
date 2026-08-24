"""Diagnostic.related 链（ADR-0004）与 report 扩展的单测。"""

import pytest
from analyzer.context import AnalysisContext
from analyzer.diagnostic import Diagnostic
from core.define import Node


class TestDiagnosticRelated:
    def test_related_default_empty(self):
        d = Diagnostic("msg", code="W001")
        assert d.related == []

    def test_related_carries_pairs(self):
        n1 = Node("ModuleDecl")
        n2 = Node("Declarator")
        d = Diagnostic(
            "dead value",
            code="WC001",
            level="warning",
            node=n1,
            related=[("模块定义处", n2)],
        )
        assert d.related == [("模块定义处", n2)]

    def test_to_dict_with_positions(self):
        n1 = Node("ModuleDecl")
        n1._pos_line = 2
        n1._pos_col = 0
        n2 = Node("Declarator")
        n2._pos_line = 5
        n2._pos_col = 28
        d = Diagnostic("msg", code="WC001", level="warning", node=n1,
                       related=[("端口声明处", n2)])
        out = d.to_dict()
        assert out["line"] == 2
        assert out["column"] == 0
        assert out["related"] == [
            {"message": "端口声明处", "node_name": "Declarator", "line": 5, "column": 28}
        ]

    def test_to_dict_no_related(self):
        d = Diagnostic("msg", code="E001")
        out = d.to_dict()
        assert "related" not in out


class TestReportRelated:
    def test_report_with_related(self):
        ctx = AnalysisContext()
        ctx.node = Node("ModuleInst")
        related_node = Node("ModuleDecl")
        ctx.report(
            "unknown port", code="W102", level="error",
            related=[("模块定义处", related_node)],
        )
        assert len(ctx.diagnostics) == 1
        d = ctx.diagnostics[0]
        assert d.code == "W102"
        assert d.related == [("模块定义处", related_node)]

    def test_report_node_override(self):
        ctx = AnalysisContext()
        ctx.node = Node("current")
        other = Node("target")
        ctx.report("msg", node=other)
        assert ctx.diagnostics[0].node is other
