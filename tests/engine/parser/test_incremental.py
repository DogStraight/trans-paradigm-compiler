"""增量重解析（块 7 P1 解析层）——单文件、单顶层单元、保守回退。

口径见 `docs/gaps/gap-incremental-parse.md`：判不准一律回退全量；"增量诊断 = 全量"
由 **AST 逐节点相等** 承载（分析是 AST + 配置的纯函数），并给出真实语料 ≥5x 的实测。

Doc: docs/gaps/gap-incremental-parse.md
"""

import io
import contextlib
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from analyzer.shared_components import SharedComponents
from parser import Parser
from parser.incremental import incremental_reparse

RULES = "grammar/verilog"
_REF = _ROOT / "tests" / "e2e" / "samples" / "real" / "ref"


def _load(rules=RULES):
    shared = SharedComponents.get(rules, [], None)
    parser = Parser(
        rules_dir=rules,
        rules=shared["rules"],
        rule_selector=shared["rule_selector"],
    )
    return shared["lexer"], parser


def _fingerprint(node) -> tuple:
    """AST 结构指纹（node_name / content / 子节点序；行号与注释锚不计）。"""
    return (
        node.node_name,
        getattr(node, "content", "") or "",
        tuple(_fingerprint(child) for child in getattr(node, "sub_node", []) or []),
    )


def _expand(lexer, parser, src: str, rules=RULES):
    """真实语料走与 check 同路的宏展开 → token/AST（tv80 原文含 `define，不能直接 parse）。"""
    from preprocessor import scan_directives, expand_tokens

    events: list = []
    macro_table, func_macros, _, _, _, clean, clean_to_raw = scan_directives(
        src, rules, search_dirs=[], out_macro_events=events
    )
    if macro_table:
        clean, _, _, _ = expand_tokens(
            clean,
            macro_table,
            rules_dir=rules,
            func_macros=func_macros,
            events=events,
            clean_to_raw=clean_to_raw,
        )
    tokens = lexer.tokenize(clean)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        ast = parser.parse(tokens)
    return clean, tokens, ast


_TWO_MODULES = (
    "module a;\n  wire w;\nendmodule\n"
    "module b;\n  wire v;\nendmodule\n"
)


def test_no_change_reuses_same_ast():
    """新旧 token 相同 → 0 重解析、返回同一 AST 对象。"""
    lexer, parser = _load()
    tokens = lexer.tokenize(_TWO_MODULES)
    ast = parser.parse(tokens)
    res = incremental_reparse(parser, tokens, tokens, ast)
    assert res.fallback == ""
    assert res.tokens_reparsed == 0
    assert res.ast is ast


def test_single_unit_edit_matches_full_parse():
    """单单元编辑 → 增量 AST 与全量 parse 逐节点相等，且只重解析该单元。"""
    lexer, parser = _load()
    old_tokens = lexer.tokenize(_TWO_MODULES)
    old_ast = parser.parse(old_tokens)
    new_tokens = lexer.tokenize(_TWO_MODULES.replace("wire w;", "wire w2;"))
    res = incremental_reparse(parser, old_tokens, new_tokens, old_ast)

    assert res.fallback == "", res.fallback
    assert 0 < res.tokens_reparsed < res.tokens_total
    full_ast = parser.parse(new_tokens)
    assert _fingerprint(res.ast) == _fingerprint(full_ast)


def test_multi_unit_change_falls_back_to_full():
    """改动跨两个顶层单元 → 保守回退全量，结果仍等于全量。"""
    lexer, parser = _load()
    old_tokens = lexer.tokenize(_TWO_MODULES)
    old_ast = parser.parse(old_tokens)
    edited = _TWO_MODULES.replace("wire w;", "wire w2;").replace("wire v;", "wire v2;")
    new_tokens = lexer.tokenize(edited)
    res = incremental_reparse(parser, old_tokens, new_tokens, old_ast)

    assert res.fallback != ""
    assert _fingerprint(res.ast) == _fingerprint(parser.parse(new_tokens))


def test_symbol_gated_language_falls_back():
    """C 包声明 parser.symbol_namespaces（typedef 消歧）→ P1 一律回退全量。"""
    lexer, parser = _load("grammar/c")
    assert getattr(parser, "symbol_namespaces", None), "C 包应声明符号命名空间"
    old_tokens = lexer.tokenize("int main(void){return 0;}\n")
    old_ast = parser.parse(old_tokens)
    new_tokens = lexer.tokenize("int main(void){return 1;}\n")
    res = incremental_reparse(parser, old_tokens, new_tokens, old_ast)
    assert res.fallback == "full:symbol-gate"


@pytest.mark.timeout(300)
def test_real_corpus_speedup_at_least_5x():
    """tv80（展开后 170KB / 22.6k tokens / 127 顶层单元）改一个标识符：≥5x、AST 相等。"""
    lexer, parser = _load()
    src = (_REF / "ref_tv80_core.v").read_text(encoding="utf-8")
    expanded, old_tokens, old_ast = _expand(lexer, parser, src)
    assert not getattr(parser, "_parse_truncated", False)

    idx = expanded.find("clk")
    assert idx > 200, "编辑点应落在单元内部（避开首尾边界）"
    edited = expanded[:idx] + "clk_x" + expanded[idx + len("clk"):]
    new_tokens = lexer.tokenize(edited)

    t0 = time.perf_counter()
    full_ast = parser.parse(new_tokens)
    t_full = time.perf_counter() - t0
    t0 = time.perf_counter()
    res = incremental_reparse(parser, old_tokens, new_tokens, old_ast)
    t_inc = time.perf_counter() - t0

    assert res.fallback == "", res.fallback
    assert res.level in {"fragment", "unit"}, res.level
    assert 0 < res.tokens_reparsed < res.tokens_total
    assert _fingerprint(res.ast) == _fingerprint(full_ast)
    assert t_full / max(t_inc, 1e-9) >= 5.0, f"full={t_full:.3f}s inc={t_inc:.3f}s"

def test_fragment_level_reparse_is_finer_than_unit():
    """语句级编辑 → 片段级（level=fragment），重解析 token 数 < 整个顶层单元。"""
    lexer, parser = _load()
    src = (
        "module m;\n"
        "  always @(*) begin\n"
        "    q = d;\n"
        "  end\n"
        "endmodule\n"
    ).replace("\\n", "\n")
    old_tokens = lexer.tokenize(src)
    old_ast = parser.parse(old_tokens)
    new_tokens = lexer.tokenize(src.replace("q = d;", "q = e;"))
    res = incremental_reparse(parser, old_tokens, new_tokens, old_ast)
    assert res.fallback == "", res.fallback
    assert res.level == "fragment", res.level
    assert res.tokens_reparsed < res.tokens_total
    assert _fingerprint(res.ast) == _fingerprint(parser.parse(new_tokens))


def test_comment_inside_region_fragment_equals_full():
    """片段区间含注释 → 仍走片段级（实测等价；注释锚边界另靠等价测试盯住）。"""
    lexer, parser = _load()
    src = "module m;\n  wire w; // keep\nendmodule\n".replace("\\n", "\n")
    old_tokens = lexer.tokenize(src)
    old_ast = parser.parse(old_tokens)
    new_tokens = lexer.tokenize(src.replace("wire w;", "wire w2;"))
    res = incremental_reparse(parser, old_tokens, new_tokens, old_ast)
    assert res.fallback == "", res.fallback
    assert res.level == "fragment", res.level
    assert _fingerprint(res.ast) == _fingerprint(parser.parse(new_tokens))

@pytest.mark.timeout(300)
def test_real_corpus_statement_level_fragment():
    """tv80 语句级编辑 → 片段级（level=fragment）、重解析 <400 tokens、AST = 全量。"""
    lexer, parser = _load()
    src = (_REF / "ref_tv80_core.v").read_text(encoding="utf-8")
    expanded, old_tokens, old_ast = _expand(lexer, parser, src)
    idx = expanded.find("1'b0")
    assert idx > 200
    edited = expanded[:idx] + "1'b1" + expanded[idx + len("1'b0"):]
    new_tokens = lexer.tokenize(edited)
    res = incremental_reparse(parser, old_tokens, new_tokens, old_ast)
    assert res.fallback == "", res.fallback
    assert res.level == "fragment", res.level
    assert res.tokens_reparsed < 400, res.tokens_reparsed
    assert _fingerprint(res.ast) == _fingerprint(parser.parse(new_tokens))
