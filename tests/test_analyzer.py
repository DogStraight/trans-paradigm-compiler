"""Analyzer 单元测试 — Scope/Symbol/Diagnostic，不依赖 parser/lexer。"""

import pytest
from analyzer.scope import Scope, Symbol
from analyzer.diagnostic import Diagnostic
from core.define import Node


class TestScope:
    """作用域的声明、解析、子域查找。"""

    def test_create_scope(self):
        s = Scope("root", kind="module")
        assert s.name == "root"
        assert s.kind == "module"
        assert s.parent is None
        assert s.symbols == {}
        assert s.children == []

    def test_declare_symbol(self):
        s = Scope("m")
        node = Node("WireDecl")
        sym = s.declare("clk", "wire", node, {"width": 1})
        assert sym.name == "clk"
        assert sym.kind == "wire"
        assert sym.decl_node is node
        assert sym.scope is s
        assert sym.attrs == {"width": 1}

    def test_resolve_local(self):
        s = Scope("m")
        node = Node("id")
        s.declare("x", "reg", node)
        assert s.resolve("x") is not None
        assert s.resolve("x").name == "x"

    def test_resolve_parent(self):
        parent = Scope("parent")
        child = Scope("child", parent=parent)
        parent.declare("y", "wire", Node("id"))
        assert child.resolve("y") is not None
        assert child.resolve("y").kind == "wire"

    def test_resolve_unknown(self):
        s = Scope("m")
        assert s.resolve("nonexistent") is None

    def test_resolve_prefers_local(self):
        parent = Scope("parent")
        child = Scope("child", parent=parent)
        parent.declare("x", "wire", Node("a"))
        child.declare("x", "reg", Node("b"))
        assert child.resolve("x").kind == "reg"

    def test_find_child_scope(self):
        parent = Scope("top")
        child = Scope("gen", parent=parent)
        parent.children.append(child)
        assert parent.find_child_scope("gen") is child

    def test_find_child_scope_with_kind(self):
        parent = Scope("top")
        c1 = Scope("g", kind="gen", parent=parent)
        c2 = Scope("g", kind="block", parent=parent)
        parent.children = [c1, c2]
        assert parent.find_child_scope("g", kind="gen") is c1
        assert parent.find_child_scope("g", kind="block") is c2

    def test_scope_to_dict(self):
        s = Scope("m", kind="module")
        s.declare("clk", "input", Node("id"))
        d = s.to_dict()
        assert d["name"] == "m"
        assert d["kind"] == "module"
        assert len(d["symbols"]) == 1
        assert d["symbols"][0]["name"] == "clk"


class TestSymbol:
    """符号的创建和序列化。"""

    def test_create_symbol(self):
        node = Node("id", value="x")
        sym = Symbol("x", "wire", node, None)
        assert sym.name == "x"
        assert sym.kind == "wire"
        assert sym.decl_node is node

    def test_to_dict_minimal(self):
        sym = Symbol("x", "wire", Node("id"), None)
        d = sym.to_dict()
        assert d == {"name": "x", "kind": "wire"}

    def test_to_dict_with_scope(self):
        scope = Scope("m")
        sym = Symbol("x", "reg", Node("id"), scope)
        d = sym.to_dict()
        assert d["scope"] == "m"

    def test_to_dict_with_attrs(self):
        sym = Symbol("x", "wire", Node("id"), None, {"width": 8})
        d = sym.to_dict()
        assert d["width"] == 8


class TestDiagnostic:
    """诊断信息结构。"""

    def test_create_diagnostic(self):
        d = Diagnostic("something wrong", code="E001")
        assert d.message == "something wrong"
        assert d.code == "E001"
        assert d.level == "error"
        assert d.node is None

    def test_default_level(self):
        d = Diagnostic("warning msg", level="warning")
        assert d.level == "warning"

    def test_to_dict(self):
        d = Diagnostic("bad", code="E002", level="error")
        dumped = d.to_dict()
        assert dumped["message"] == "bad"
        assert dumped["code"] == "E002"
        assert dumped["level"] == "error"

    def test_str_format(self):
        d = Diagnostic("test error", code="E003")
        assert "E003" in str(d)
        assert "test error" in str(d)
