"""Linter 发现阶段（Discovery）单元测试 — 节点树与未识别诊断。

固定发现器的当前行为，独立于 lint_err 样本集：
    - 块式/引用式容器的多层级节点树（module → always → begin → 语句）
    - 未识别语句诊断（phase-unrecognized）

通过 LinterScanner 暴露的内部 Discovery 直接断言 discover() 产出。
"""

import pytest
from core.define import DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS


@pytest.fixture(scope="module")
def scanner(config_loaded):
    from linter.scanner import LinterScanner

    return LinterScanner(DEFAULT_RULES_DIR, ext_dirs=DEFAULT_EXT_DIRS)


def _nodes(scanner, src):
    """discover 源码，返回 (节点列表, 未识别诊断列表)。"""
    tokens = scanner.lexer.tokenize(src)
    nodes = scanner._discovery.discover(tokens)
    return nodes, scanner._discovery.unrecognized_diagnostics()


def _find_rule(nodes, rule):
    """在节点列表（含递归）中找第一个指定规则名的节点。"""
    for n in nodes:
        if n.rule == rule:
            return n
    found = None
    for n in nodes:
        found = _find_rule(n.children, rule)
        if found:
            return found
    return None


class TestBlockDiscovery:
    """块式容器 → 多层级节点树。"""

    def test_module_decl_root(self, scanner):
        nodes, _ = _nodes(scanner, "module m;\nendmodule\n")
        assert len(nodes) == 1
        assert nodes[0].rule == "ModuleDecl"

    def test_always_begin_block_hierarchy(self, scanner):
        # module → always → begin → blocking assign 四层
        src = "module m;\n    always @(*) begin\n        a = 1;\n    end\nendmodule\n"
        nodes, _ = _nodes(scanner, src)
        mod = nodes[0]
        assert mod.rule == "ModuleDecl"
        always = mod.children[0]
        assert always.rule == "AlwaysStmt"
        begin = always.children[0]
        assert begin.rule == "BeginEnd"
        assert begin.children[0].rule == "BlockingAssign"


class TestStatementDiscovery:
    """语句发现。"""

    def test_assign_stmt_discovered(self, scanner):
        src = "module m;\n    assign a = b;\nendmodule\n"
        nodes, _ = _nodes(scanner, src)
        assert _find_rule(nodes, "AssignStmt") is not None


class TestUnrecognized:
    """未识别语句诊断（本次新增 phase-unrecognized）。"""

    def test_typo_keyword_records_diagnostic(self, scanner):
        # e07: alwayss 拼错 → 记录 phase-unrecognized
        src = "module m;\n    alwayss @(*) begin\n    end\nendmodule\n"
        _, diags = _nodes(scanner, src)
        assert any(d.code == "phase-unrecognized" for d in diags)

    def test_valid_code_no_unrecognized(self, scanner):
        src = "module m;\n    always @(*) begin\n        a = 1;\n    end\nendmodule\n"
        _, diags = _nodes(scanner, src)
        assert diags == []

    def test_unrecognized_diagnostic_includes_token_window(self, scanner):
        # 拼错关键字 → 诊断 message 附带 token 窗口（前后文定位）
        src = "module m;\n    alwayss @(*) begin\n    end\nendmodule\n"
        _, diags = _nodes(scanner, src)
        unrec = [d for d in diags if d.code == "phase-unrecognized"]
        assert unrec
        assert ">>" in unrec[0].message  # 当前 token 标记
        assert "alwayss" in unrec[0].message  # 出错 token 内容

    def test_dump_nodes_has_rule_and_range(self, scanner):
        # c) 节点树 token 区间 dump：rule + [start,end) → 行号
        src = "module m;\n    always @(*) begin\n        a = 1;\n    end\nendmodule\n"
        tokens = scanner.lexer.tokenize(src)
        nodes = scanner._discovery.discover(tokens)
        dump = scanner._discovery.dump_nodes(tokens, nodes)
        assert "ModuleDecl [0," in dump
        assert "AlwaysStmt" in dump
        assert "L1-" in dump  # 行号信息
        assert "span0 L" in dump  # 0-based span 对账信息
