"""Pratt 表达式解析器框架测试 — 纯合成数据，零语言配置依赖。

所有测试用例用人工构造的 Token 对象和合成运算符定义，
验证 Pratt 算法本身的正确性（优先级/结合性/前缀一元/count）。
换语言配置不影响这些测试。"""

import pytest
from typing import Any

from core.define import Token, Node

pytestmark = pytest.mark.smoke  # smoke：parser 组代表（Pratt 框架，纯合成零依赖）


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
# 语言无关性：数字字面量无语言语法 + bool 配置驱动
# ═══════════════════════════════════════════════════════

class TestLanguageNeutrality:
    """pratt_parser 不内置语言语法：数字只走通用整数/浮点，bool 由配置驱动。

    Verilog 的带宽度基数形态（`8'hFF`）走**语法规则面**（lexer 按
    `[[number.based]]` 捕为单 token → 语言包的 Number 规则接住），
    引擎侧没有也不该有第二种扩展机制（曾经有过一个注入式钩子，经实测
    在三个语言包下不可达——原子解析器先手接住数字——已删）。
    """

    def test_number_literal_is_generic_only(self):
        """无语言语法时，位宽样式数字按通用 Number 保留原文（不报错、不猜语义）。"""
        import parser.pratt_parser as pp

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
        ast, _, _ = parse_with_comments(
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
        ast, c, _ = parse_with_comments(
            pratt, [op("!"), C("/* c */"), T("id", "a")]
        )
        assert ast.node_name == "UnaryOp" and c == 3
        slots = getattr(ast, "_comment_slots", None)
        assert slots == {"inline_after": {"!": [("/* c */", 0)]}}

    def test_ternary_both_gaps_mounted(self, pratt):
        """`c ? /* 真 */ a : /* 假 */ b`：op1/op2 间隙各自挂载。"""
        ast, _, _ = parse_with_comments(
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
        ast, _, seen = parse_with_comments(
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
        ast, _, _ = parse_with_comments(
            pratt,
            [T("id", "a"), op("+"), C("/* c */"), T("id", "b")],
            comment_sink=None,
        )
        slots = getattr(ast, "_comment_slots", None)
        assert slots == {"inline_after": {"+": [("/* c */", 0)]}}


class TestEntryCommentMount:
    """表达式**入口**注释落位（P1.5）：挂前缀操作数节点 + 锚点通道兜底。

    与 operator 间隙注释的区别：入口注释在操作数之前（无 operator 上下文），
    按“独占行 / 其余”分槽：独占行 → `leading_own_line`（硬换行独占成行），
    其余（行尾型）→ `leading`（注释 + 断行后接节点）。**同时**登记 comment_sink
    （挂树失败/节点未被渲染时 marker 仍可回插——marker 文本承载条件块原文，
    只挂树不兜底会静默丢块）。
    """

    def test_eol_comment_at_entry_mounted_and_sunk(self, pratt):
        """入口行尾型注释（同行前已有代码）→ 前缀节点 `leading` + sink 兜底。"""
        pp, _ = pratt
        a = Token(type="id", content="a", line=0, column=0)
        cmt = Token(type="comment", content="/* c */", line=0, column=2)
        b = Token(type="id", content="b", line=0, column=8)
        seen: list = []
        ast, consumed = pp.parse_expression(
            [a, cmt, b], 1, 0, {}, {}, {}, {}, 0, 0, _atom, None,
            lambda e: seen.append(e),
        )
        assert ast.node_name == "Ident" and consumed == 3
        assert getattr(ast, "_comment_slots", None) == {"leading": ["/* c */"]}
        assert seen and seen[0]["text"] == "/* c */", "入口注释必须同时登记 sink 兜底"

    def test_own_line_comment_at_entry_mounted_own_line(self, pratt):
        """入口独占行注释 → 前缀节点 `leading_own_line` + sink 兜底。"""
        pp, _ = pratt
        a = Token(type="id", content="a", line=0, column=0)
        nl1 = Token(type="newline", content="\n", line=0, column=1)
        cmt = Token(type="comment", content="// c", line=1, column=0)
        nl2 = Token(type="newline", content="\n", line=1, column=4)
        b = Token(type="id", content="b", line=2, column=0)
        seen: list = []
        ast, _ = pp.parse_expression(
            [a, nl1, cmt, nl2, b], 2, 0, {}, {}, {}, {}, 0, 0, _atom, None,
            lambda e: seen.append(e),
        )
        assert ast.node_name == "Ident"
        assert getattr(ast, "_comment_slots", None) == {
            "leading_own_line": ["// c"]
        }
        assert seen and seen[0]["text"] == "// c"
        assert seen[0]["midline"] is False

    def test_non_node_atom_only_sinks(self, pratt):
        """原子解析器返回非 Node（linter 占位）→ 挂不上树，仅 sink 兜底。"""
        pp, _ = pratt
        a = Token(type="id", content="a", line=0, column=0)
        cmt = Token(type="comment", content="/* c */", line=0, column=2)
        nl = Token(type="newline", content="\n", line=0, column=5)
        b = Token(type="id", content="b", line=1, column=0)
        seen: list = []
        ast, _ = pp.parse_expression(
            [a, cmt, nl, b], 1, 0, {}, {}, {}, {}, 0, 0,
            lambda t, i: (object(), 1), None, lambda e: seen.append(e),
        )
        assert not hasattr(ast, "_comment_slots")
        assert seen and seen[0]["text"] == "/* c */"
