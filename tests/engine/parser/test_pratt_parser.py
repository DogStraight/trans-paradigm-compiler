"""Pratt 表达式解析器框架测试 — 纯合成数据，零语言配置依赖。

所有测试用例用人工构造的 Token 对象和合成运算符定义，
验证 Pratt 算法本身的正确性（优先级/结合性/前缀一元/count）。
换语言配置不影响这些测试。"""

import pytest
from typing import Any

from core.define import Token, Node


# ═══════════════════════════════════════════════════════
# 合成测试数据
# ═══════════════════════════════════════════════════════

# 合成 token 分类器（无需加载任何语言配置）
_SYNTH_CATEGORIES = {
    "number":     {"match": "exact", "types": ["number"]},
    "string":     {"match": "exact", "types": ["string"]},
    "identifier": {"match": "exact", "types": ["id"]},
    "operator":   {"match": "prefix", "types": ["op."]},
    "none":       {"match": "exact", "types": []},
}

# 合成运算符定义（processed_operator_data 格式）
# 优先级值越大绑定越紧
_SYNTH_OPS = [
    (1, {"symbol": "+",  "arity": 2, "assoc": "left"}),
    (1, {"symbol": "-",  "arity": 2, "assoc": "left"}),
    (2, {"symbol": "*",  "arity": 2, "assoc": "left"}),
    (2, {"symbol": "/",  "arity": 2, "assoc": "left"}),
    (3, {"symbol": "**", "arity": 2, "assoc": "right"}),   # 右结合
    (5, {"symbol": "!",  "arity": 1, "assoc": "left", "position": "prefix"}),  # 前缀一元
    (5, {"symbol": "~",  "arity": 1, "assoc": "left", "position": "prefix"}),  # 前缀一元
    (1, {"symbol": "?",  "arity": 3, "assoc": "left", "second": ":"}),  # 三目（合成，注释挂载测试用）
]


# ═══════════════════════════════════════════════════════
# 模块级 fixture（自动安装合成分类器）
# ═══════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def pratt() -> tuple[Any, Any]:
    """返回 (pratt_module, operator_defs)，分类器已用合成数据安装。"""
    import parser.pratt_parser as pp
    pp.install_token_classifier(_SYNTH_CATEGORIES)
    return pp, _SYNTH_OPS


# ═══════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════

def T(type_: str, content: str) -> Token:
    """快速构造 Token。"""
    return Token(type=type_, content=content, line=0, column=0)


def op(symbol: str) -> Token:
    """快速构造运算符 Token。"""
    return Token(type=f"op.{symbol}", content=symbol, line=0, column=0)


def _atom(tokens, idx):
    """合成原子解析器：id → Ident, number → Num。"""
    t = tokens[idx]
    if t.type == "id":
        return Node("Ident", name=t.content), 1
    if t.type == "number":
        return Node("Num", value=t.content), 1
    return None, 0


def parse(pratt: tuple[Any, Any], tokens: list[Token], **kwargs):
    """辅助：解析 token 列表返回 (ast, consumed)。"""
    pp, op_defs = pratt
    return pp.parse_with_count(
        tokens, operator_defs=op_defs, atom_parser=_atom, **kwargs
    )


# ═══════════════════════════════════════════════════════
# 基本二元运算
# ═══════════════════════════════════════════════════════

class TestBinaryOps:
    def test_add(self, pratt):
        ast, c = parse(pratt, [T("id","a"), op("+"), T("id","b")])
        assert ast.node_name == "BinaryOp" and ast.op == "+" and c == 3

    def test_sub(self, pratt):
        ast, c = parse(pratt, [T("id","a"), op("-"), T("id","b")])
        assert ast.node_name == "BinaryOp" and ast.op == "-" and c == 3

    def test_mul(self, pratt):
        ast, c = parse(pratt, [T("id","a"), op("*"), T("id","b")])
        assert ast.node_name == "BinaryOp" and ast.op == "*" and c == 3

    def test_div(self, pratt):
        ast, c = parse(pratt, [T("id","a"), op("/"), T("id","b")])
        assert ast.node_name == "BinaryOp" and ast.op == "/" and c == 3


# ═══════════════════════════════════════════════════════
# 优先级
# ═══════════════════════════════════════════════════════

class TestPrecedence:
    """优先级高的运算符绑定更紧。"""

    def test_mul_over_add(self, pratt):
        """a + b * c  →  +(a, *(b, c))"""
        ast, _ = parse(pratt, [T("id","a"), op("+"), T("id","b"), op("*"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "+"
        assert ast.left.node_name == "Ident"
        assert ast.right.node_name == "BinaryOp" and ast.right.op == "*"

    def test_add_over_mul_reversed(self, pratt):
        """a * b + c  →  +(*(a, b), c)"""
        ast, _ = parse(pratt, [T("id","a"), op("*"), T("id","b"), op("+"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "+"
        assert ast.left.node_name == "BinaryOp" and ast.left.op == "*"

    def test_mul_over_sub(self, pratt):
        """a - b * c  →  -(a, *(b, c))"""
        ast, _ = parse(pratt, [T("id","a"), op("-"), T("id","b"), op("*"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "-"
        assert ast.right.node_name == "BinaryOp" and ast.right.op == "*"

    def test_same_precedence_left_assoc(self, pratt):
        """a + b - c  →  -(+ (a, b), c) — 左结合，同级左优先。"""
        ast, _ = parse(pratt, [T("id","a"), op("+"), T("id","b"), op("-"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "-"
        assert ast.left.node_name == "BinaryOp" and ast.left.op == "+"


# ═══════════════════════════════════════════════════════
# 结合性
# ═══════════════════════════════════════════════════════

class TestAssociativity:
    def test_minus_left_assoc(self, pratt):
        """a - b - c  →  -(-(a, b), c)"""
        ast, _ = parse(pratt, [T("id","a"), op("-"), T("id","b"), op("-"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "-"
        assert ast.left.node_name == "BinaryOp" and ast.left.op == "-"

    def test_mul_left_assoc(self, pratt):
        """a * b * c  →  *(*(a, b), c)"""
        ast, _ = parse(pratt, [T("id","a"), op("*"), T("id","b"), op("*"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "*"
        assert ast.left.node_name == "BinaryOp" and ast.left.op == "*"

    def test_pow_right_assoc(self, pratt):
        """a ** b ** c  →  **(a, **(b, c)) — 右结合！"""
        ast, _ = parse(pratt, [T("id","a"), op("**"), T("id","b"), op("**"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "**"
        assert ast.right.node_name == "BinaryOp" and ast.right.op == "**"


# ═══════════════════════════════════════════════════════
# 前缀一元运算
# ═══════════════════════════════════════════════════════

class TestPrefixUnary:
    def test_not(self, pratt):
        ast, _ = parse(pratt, [op("!"), T("id","a")])
        assert ast.node_name == "UnaryOp"
        assert ast.op == "!" and ast.position == "prefix"

    def test_bitwise_not(self, pratt):
        ast, _ = parse(pratt, [op("~"), T("id","a")])
        assert ast.node_name == "UnaryOp"
        assert ast.op == "~" and ast.position == "prefix"

    def test_double_unary(self, pratt):
        """!!a  →  UnaryOp(!, UnaryOp(!, a))"""
        ast, _ = parse(pratt, [op("!"), op("!"), T("id","a")])
        assert ast.node_name == "UnaryOp" and ast.op == "!"
        assert ast.operand.node_name == "UnaryOp" and ast.operand.op == "!"

    def test_unary_in_right_operand(self, pratt):
        """a + !b  →  BinaryOp(+, Ident(a), UnaryOp(!, Ident(b)))"""
        ast, _ = parse(pratt, [T("id","a"), op("+"), op("!"), T("id","b")])
        assert ast.node_name == "BinaryOp" and ast.op == "+"
        assert ast.left.node_name == "Ident"
        assert ast.right.node_name == "UnaryOp" and ast.right.op == "!"

    def test_prefix_binds_tighter_than_infix(self, pratt):
        """!a + b  →  +(!(a), b) — 一元优先级高于二元"""
        ast, _ = parse(pratt, [op("!"), T("id","a"), op("+"), T("id","b")])
        assert ast.node_name == "BinaryOp" and ast.op == "+"
        assert ast.left.node_name == "UnaryOp" and ast.left.op == "!"


# ═══════════════════════════════════════════════════════
# consumed_count
# ═══════════════════════════════════════════════════════

class TestConsumedCount:
    def test_single_ident(self, pratt):
        _, c = parse(pratt, [T("id","a")])
        assert c == 1

    def test_single_number(self, pratt):
        _, c = parse(pratt, [T("number","42")])
        assert c == 1

    def test_binary_3(self, pratt):
        _, c = parse(pratt, [T("id","a"), op("+"), T("id","b")])
        assert c == 3

    def test_chain_5(self, pratt):
        _, c = parse(pratt, [T("id","a"), op("+"), T("id","b"), op("+"), T("id","c")])
        assert c == 5

    def test_unary_2(self, pratt):
        _, c = parse(pratt, [op("!"), T("id","a")])
        assert c == 2

    def test_unary_binary_4(self, pratt):
        _, c = parse(pratt, [T("id","a"), op("+"), op("!"), T("id","b")])
        assert c == 4

    def test_stop_token(self, pratt):
        """遇到 stop_token 停止，不包括 stop_token。"""
        ast, c = parse(pratt, [T("id","a"), op("+"), T("id","b"), T(";",";")],
                       stop_tokens={";"})
        assert c == 3
        assert ast.node_name == "BinaryOp" and ast.op == "+"


# ═══════════════════════════════════════════════════════
# 边界条件
# ═══════════════════════════════════════════════════════

class TestEdgeCases:
    def test_single_ident(self, pratt):
        ast, c = parse(pratt, [T("id","x")])
        assert ast.node_name == "Ident" and c == 1

    def test_single_number(self, pratt):
        ast, c = parse(pratt, [T("number","99")])
        assert ast.node_name == "Num" and c == 1

    def test_empty_raises(self, pratt):
        with pytest.raises(ValueError, match="表达式不完整"):
            parse(pratt, [])

    def test_unknown_token_type_raises(self, pratt):
        """无法识别的 token 类型（既非原子也非运算符）→ ValueError。"""
        with pytest.raises(ValueError):
            parse(pratt, [T("unknown","???")])


# ═══════════════════════════════════════════════════════
# 语言无关性：位宽字面量注入 + bool 配置驱动
# ═══════════════════════════════════════════════════════

class TestLanguageNeutrality:
    """pratt_parser 不内置语言语法：位宽字面量由注入回调处理，bool 由配置驱动。"""

    def test_bit_width_injection(self):
        """注入位宽解析器后，8'hff 被解析为 BitWidthLiteral。"""
        import parser.pratt_parser as pp

        def _verilog_bw(content):
            if "'" in content:
                parts = content.split("'", 1)
                rest = parts[1] if len(parts) > 1 else ""
                if rest and rest[0] in ("b", "o", "d", "h"):
                    return Node("BitWidthLiteral", width=None, base=rest[0], value=rest[1:])
            return None

        pp.install_bit_width_literal_parser(_verilog_bw)
        try:
            n = pp.parse_number_literal(T("number", "8'hff"))
            assert n.node_name == "BitWidthLiteral"
            assert n.base == "h" and n.value == "ff"
        finally:
            pp.install_bit_width_literal_parser(None)

    def test_no_injection_fallback_generic(self):
        """无注入时位宽样式数字回退为通用 Number（语言无关）。"""
        import parser.pratt_parser as pp

        pp.install_bit_width_literal_parser(None)
        n = pp.parse_number_literal(T("number", "8'hff"))
        assert n.node_name == "Number"
        assert n.value == "8'hff"

    def test_bool_true_type_from_config(self):
        """bool 真值类型从 token_category 配置推导，而非硬编码。"""
        import parser.pratt_parser as pp

        cats = {"bool": {"match": "exact",
                         "types": ["literal.bool_true", "literal.bool_false"]}}
        pp.install_token_classifier(cats)
        try:
            assert pp._bool_true_type == "literal.bool_true"
            assert pp.is_bool(T("literal.bool_true", "true"))
            assert not pp.is_bool(T("number", "1"))
        finally:
            pp.install_token_classifier(_SYNTH_CATEGORIES)


# ═══════════════════════════════════════════════════════
# 注释挂载（ADR-0013 决策 5）：operator 间隙注释上挂表达式节点
# ═══════════════════════════════════════════════════════

def C(text: str) -> Token:
    """快速构造注释 token（line=0 与相邻代码同行 → midline 判定成立）。"""
    return Token(type="comment", content=text, line=0, column=0)


def C_eol(text: str, line: int) -> Token:
    """行尾注释 token（指定行号，供行尾判定测试）。"""
    return Token(type="comment", content=text, line=line, column=0)


def parse_with_comments(pratt, tokens, comment_sink=None):
    """辅助：解析含注释 token 的表达式，返回 (ast, consumed, sink_entries)。"""
    pp, op_defs = pratt
    seen = []
    ast, c = pp.parse_with_count(
        tokens, operator_defs=op_defs, atom_parser=_atom,
        comment_sink=comment_sink or (lambda e: seen.append(e)),
    )
    return ast, c, seen


class TestOperatorGapCommentMount:
    """operator 间隙行中注释挂 BinaryOp/UnaryOp/TernaryOp 节点（ADR-0013
    决策 5，纯合成数据语言无关验证——不依赖 verilog 语法）。"""

    def test_infix_gap_mounted_on_binary_op(self, pratt):
        """`a + /* c */ b`：注释挂 BinaryOp inline_after（锚 `+`）。"""
        ast, c, seen = parse_with_comments(
            pratt,
            [T("id", "a"), op("+"), C("/* c */"), T("id", "b")],
        )
        assert ast.node_name == "BinaryOp" and c == 4
        slots = getattr(ast, "_comment_slots", None)
        assert slots == {"inline_after": {"+": [("/* c */", 0)]}}
        assert seen == [], "operator 间隙注释应上挂节点，不进 sink"

    def test_multiple_gaps_each_mounted(self, pratt):
        """`a + /* c1 */ b * /* c2 */ c`：每层 operator 各自挂载。"""
        ast, c, seen = parse_with_comments(
            pratt,
            [T("id", "a"), op("+"), C("/* c1 */"), T("id", "b"),
             op("*"), C("/* c2 */"), T("id", "c")],
        )
        assert ast.node_name == "BinaryOp" and ast.op == "+"
        assert ast.op == "+"
        outer = getattr(ast, "_comment_slots", None)
        assert outer == {"inline_after": {"+": [("/* c1 */", 0)]}}
        inner = getattr(ast.right, "_comment_slots", None)
        assert inner == {"inline_after": {"*": [("/* c2 */", 0)]}}

    def test_prefix_unary_gap_mounted(self, pratt):
        """`! /* c */ a`：注释挂 UnaryOp（锚 `!`；`!` 是合成前缀一元）。"""
        ast, c, seen = parse_with_comments(
            pratt, [op("!"), C("/* c */"), T("id", "a")]
        )
        assert ast.node_name == "UnaryOp" and c == 3
        slots = getattr(ast, "_comment_slots", None)
        assert slots == {"inline_after": {"!": [("/* c */", 0)]}}

    def test_ternary_both_gaps_mounted(self, pratt):
        """`c ? /* 真 */ a : /* 假 */ b`：op1/op2 间隙各自挂载。"""
        ast, c, seen = parse_with_comments(
            pratt,
            [T("id", "c"), op("?"), C("/* 真 */"), T("id", "a"),
             T(":", ":"), C("/* 假 */"), T("id", "b")],
        )
        assert ast.node_name == "TernaryOp"
        slots = getattr(ast, "_comment_slots", None)
        assert slots == {
            "inline_after": {
                "?": [("/* 真 */", 0)],
                ":": [("/* 假 */", 0)],
            }
        }

    def test_line_end_comment_mounted_on_rhs_leading(self, pratt):
        """行尾注释（注释后换行）挂后续 RHS leading（ADR-0014 方向 B）。

        旧语义：行尾注释走 sink（行中断行会吞代码）。方向 B：挂 RHS
        子节点 leading——`//` 注释在重排表达式内必处行尾，只能随操作数
        独立断行，机械安全（`a || // c\\n b` → right(b) leading）。

        line 约定：注释在 0 行、换行 1 行、续行操作数 2 行——注释与后随
        代码不同行 → 行尾判定（其余测试 T/op/C 均 line=0 同行 → midline）。
        """
        a = Token(type="id", content="a", line=0, column=0)
        plus = Token(type="op.+", content="+", line=0, column=0)
        cmt = C_eol("// 行尾", 0)
        nl = Token(type="newline", content="\n", line=1, column=0)
        b = Token(type="id", content="b", line=2, column=0)
        ast, c, seen = parse_with_comments(
            pratt, [a, plus, cmt, nl, b]
        )
        assert ast.node_name == "BinaryOp"
        assert not hasattr(ast, "_comment_slots"), "行尾注释不挂 op inline_after"
        # 挂 RHS（right = Ident b）leading
        rhs = getattr(ast, "right", None)
        slots = getattr(rhs, "_comment_slots", None) if rhs is not None else None
        assert slots and slots.get("leading") == ["// 行尾"], (
            f"行尾注释应挂 RHS leading: {slots!r}"
        )
        assert seen == [], "行尾注释不再走 sink（方向 B 挂 RHS leading）"

    def test_no_sink_when_none_given(self, pratt):
        """comment_sink=None（linter 场景）：行中注释仍挂节点，行尾跳过不崩。"""
        ast, c, seen = parse_with_comments(
            pratt,
            [T("id", "a"), op("+"), C("/* c */"), T("id", "b")],
            comment_sink=None,
        )
        slots = getattr(ast, "_comment_slots", None)
        assert slots == {"inline_after": {"+": [("/* c */", 0)]}}
