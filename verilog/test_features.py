#!/usr/bin/env python3
"""
Parser feature health checks — independent of normal/error test groups.

These tests verify internal parser mechanisms that are not exercised
by E2E pipeline tests alone. Each check targets a specific past bug.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.define import GrammarRulesRegister
from parser import setup_grammar
from parser.rule_selector import build_start_token_map_names
from parser.parser_core import Parser, ParseContext
from lexer import Lexer
import parser.pratt_parser as pratt_parser

from core.define import DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS as EXT_DIRS

RULES_DIR = DEFAULT_RULES_DIR
from core.define import DEFAULT_EXT_DIRS as EXT_DIRS


def load_rules():
    return setup_grammar(RULES_DIR, GrammarRulesRegister.get_default(), ext_dirs=EXT_DIRS)


# ──────────────────────────────────────────────
# Check 1: Token classifier installed
# ──────────────────────────────────────────────


def _parse_quiet(parser, tokens):
    import io

    old = sys.stderr
    sys.stderr = io.StringIO()
    try:
        return parser.parse(tokens)
    finally:
        sys.stderr = old


def test_token_classifier_installed():
    """Pratt 解析器的 is_operator/is_identifier 必须可用。"""
    assert pratt_parser.is_operator is not None
    rules = load_rules()
    stmt_names = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    from parser.rule_selector import RuleSelector

    rs = RuleSelector(rules, stmt_names, cache_enabled=False)
    parser = Parser(
        rules_dir=RULES_DIR,
        cache_enabled=False,
        rules=rules,
        rule_selector=rs,
    )
    lexer = Lexer(rules_dir=RULES_DIR)
    tokens = lexer.tokenize("module m; wire a; endmodule")
    ast = _parse_quiet(parser, tokens)
    assert ast is not None, "基础解析应成功"


def test_pratt_parses_not_operator():
    """!rst_n 必须能被 Pratt 解析为 UnaryOp。"""
    rules = load_rules()
    stmt_names = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    from parser.rule_selector import RuleSelector

    rs = RuleSelector(rules, stmt_names, cache_enabled=False)
    parser = Parser(
        rules_dir=RULES_DIR,
        cache_enabled=False,
        rules=rules,
        rule_selector=rs,
    )

    lexer = Lexer(rules_dir=RULES_DIR)
    src = "module t(input a); always @(*) begin if (!a) ; end endmodule"
    tokens = lexer.tokenize(src)
    ast = _parse_quiet(parser, tokens)
    assert ast is not None, "包含 ! 表达式的 module 应解析成功"


def test_pratt_parses_addition():
    """a + b 必须能被 Pratt 解析为 BinaryOp。"""
    rules = load_rules()
    stmt_names = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    from parser.rule_selector import RuleSelector

    rs = RuleSelector(rules, stmt_names, cache_enabled=False)
    parser = Parser(
        rules_dir=RULES_DIR,
        cache_enabled=False,
        rules=rules,
        rule_selector=rs,
    )

    lexer = Lexer(rules_dir=RULES_DIR)
    src = "module t; wire a; wire b; assign a = b; assign a = a + b; endmodule"
    tokens = lexer.tokenize(src)
    ast = _parse_quiet(parser, tokens)
    assert ast is not None, "包含 + 表达式的 module 应解析成功"


# ──────────────────────────────────────────────
# Check 2: First set correctness
# ──────────────────────────────────────────────


def test_first_set_keyword_reg():
    """keyword.reg 不应包含 AnsiInputDecl 等端口规则。"""
    rules = load_rules()
    stmt_names = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    name_map = build_start_token_map_names(rules, stmt_names)
    reg_candidates = name_map.get("keyword.reg", [])
    assert "RegDecl" in reg_candidates, "keyword.reg 至少应包含 RegDecl"
    # 端口声明规则不应出现在 keyword.reg 的候选集中
    port_rules = {
        "AnsiInputDecl",
        "AnsiOutputDecl",
        "AnsiInoutDecl",
        "BodyInputDecl",
        "BodyOutputDecl",
        "BodyInoutDecl",
    }
    overlap = port_rules & set(reg_candidates)
    assert not overlap, f"keyword.reg 不应包含端口规则，实际包含: {overlap}"


def test_first_set_keyword_input():
    """keyword.input 应包含端口声明规则。"""
    rules = load_rules()
    stmt_names = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    name_map = build_start_token_map_names(rules, stmt_names)
    input_candidates = name_map.get("keyword.input", [])
    assert (
        "BodyInputDecl" in input_candidates
    ), "keyword.input 应包含 BodyInputDecl（语句级 input 声明）"
    assert (
        "AnsiInputDecl" not in input_candidates
    ), "keyword.input 不应包含 AnsiInputDecl（已标记 statement=false）"


# ──────────────────────────────────────────────
# Check 3: Atomic rules are strict
# ──────────────────────────────────────────────


def test_atomic_rules_exist():
    """原子规则（Number/Identifier）应正确标记。"""
    rules = load_rules()
    # 检查 atomic 标记的规则
    atomic_rules = [
        name for name, rule in rules.items() if getattr(rule, "is_atom", False)
    ]
    assert "Number" in atomic_rules, "Number 应是原子规则"
    assert "Identifier" in atomic_rules, "Identifier 应是原子规则"
    # atomic 规则生产式数量应合理（非空）
    for name in atomic_rules:
        rule = rules[name]
        prods = rule.prods
        assert len(prods) > 0, f"原子规则 {name} 不应有空的 production"


def test_bit_width_literal_not_greedy():
    """bit_widthLiteral 匹配 literal.number 失败后不应吞后续 token。"""
    rules = load_rules()
    stmt_names = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    from parser.rule_selector import RuleSelector

    rs = RuleSelector(rules, stmt_names, cache_enabled=False)
    parser = Parser(
        rules_dir=RULES_DIR,
        cache_enabled=False,
        rules=rules,
        rule_selector=rs,
    )

    lexer = Lexer(rules_dir=RULES_DIR)
    src = "module t; wire a; assign a = 32'd1000; endmodule"
    tokens = lexer.tokenize(src)
    ast = _parse_quiet(parser, tokens)
    assert ast is not None, "含 bit_widthLiteral 的 module 应解析成功"


# ──────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────

CHECKS = [
    ("token_classifier_installed", test_token_classifier_installed),
    ("pratt_parses_not_operator", test_pratt_parses_not_operator),
    ("pratt_parses_addition", test_pratt_parses_addition),
    ("first_set_keyword_reg", test_first_set_keyword_reg),
    ("first_set_keyword_input", test_first_set_keyword_input),
    ("atomic_rules_exist", test_atomic_rules_exist),
    ("bit_width_literal_not_greedy", test_bit_width_literal_not_greedy),
]


def run_checks(verbose: bool = False) -> bool:
    passed = 0
    failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            status = "OK"
            passed += 1
        except Exception as e:
            status = f"FAIL ({e})"
            failed += 1
        print(f"  {name:40s} {status}")
    print(f"\n  Total: {passed + failed}  OK: {passed}  FAIL: {failed}")
    return failed == 0


if __name__ == "__main__":
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    ok = run_checks(verbose)
    sys.exit(0 if ok else 1)
