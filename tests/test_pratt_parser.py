"""Pratt 表达式解析器框架测试 — 纯合成数据，零语言配置依赖。

所有测试用例用人工构造的 Token 对象和合成运算符定义，
验证 Pratt 算法本身的正确性（优先级/结合性/前缀一元/count）。
换语言配置不影响这些测试。"""

import pytest
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
]


# ═══════════════════════════════════════════════════════
# 模块级 fixture（自动安装合成分类器）
# ═══════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def pratt():
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


def parse(pp, op_defs, tokens, **kwargs):
    """辅助：解析 token 列表返回 (ast, consumed)。"""
    return pp.parse_with_count(
        tokens, operator_defs=op_defs, atom_parser=_atom, **kwargs
    )


# ═══════════════════════════════════════════════════════
# 基本二元运算
# ═══════════════════════════════════════════════════════

class TestBinaryOps:
    def test_add(self, pratt):
        ast, c = parse(*pratt, [T("id","a"), op("+"), T("id","b")])
        assert ast.node_name == "BinaryOp" and ast.op == "+" and c == 3

    def test_sub(self, pratt):
        ast, c = parse(*pratt, [T("id","a"), op("-"), T("id","b")])
        assert ast.node_name == "BinaryOp" and ast.op == "-" and c == 3

    def test_mul(self, pratt):
        ast, c = parse(*pratt, [T("id","a"), op("*"), T("id","b")])
        assert ast.node_name == "BinaryOp" and ast.op == "*" and c == 3

    def test_div(self, pratt):
        ast, c = parse(*pratt, [T("id","a"), op("/"), T("id","b")])
        assert ast.node_name == "BinaryOp" and ast.op == "/" and c == 3


# ═══════════════════════════════════════════════════════
# 优先级
# ═══════════════════════════════════════════════════════

class TestPrecedence:
    """优先级高的运算符绑定更紧。"""

    def test_mul_over_add(self, pratt):
        """a + b * c  →  +(a, *(b, c))"""
        ast, _ = parse(*pratt, [T("id","a"), op("+"), T("id","b"), op("*"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "+"
        assert ast.left.node_name == "Ident"
        assert ast.right.node_name == "BinaryOp" and ast.right.op == "*"

    def test_add_over_mul_reversed(self, pratt):
        """a * b + c  →  +(*(a, b), c)"""
        ast, _ = parse(*pratt, [T("id","a"), op("*"), T("id","b"), op("+"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "+"
        assert ast.left.node_name == "BinaryOp" and ast.left.op == "*"

    def test_mul_over_sub(self, pratt):
        """a - b * c  →  -(a, *(b, c))"""
        ast, _ = parse(*pratt, [T("id","a"), op("-"), T("id","b"), op("*"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "-"
        assert ast.right.node_name == "BinaryOp" and ast.right.op == "*"

    def test_same_precedence_left_assoc(self, pratt):
        """a + b - c  →  -(+ (a, b), c) — 左结合，同级左优先。"""
        ast, _ = parse(*pratt, [T("id","a"), op("+"), T("id","b"), op("-"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "-"
        assert ast.left.node_name == "BinaryOp" and ast.left.op == "+"


# ═══════════════════════════════════════════════════════
# 结合性
# ═══════════════════════════════════════════════════════

class TestAssociativity:
    def test_minus_left_assoc(self, pratt):
        """a - b - c  →  -(-(a, b), c)"""
        ast, _ = parse(*pratt, [T("id","a"), op("-"), T("id","b"), op("-"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "-"
        assert ast.left.node_name == "BinaryOp" and ast.left.op == "-"

    def test_mul_left_assoc(self, pratt):
        """a * b * c  →  *(*(a, b), c)"""
        ast, _ = parse(*pratt, [T("id","a"), op("*"), T("id","b"), op("*"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "*"
        assert ast.left.node_name == "BinaryOp" and ast.left.op == "*"

    def test_pow_right_assoc(self, pratt):
        """a ** b ** c  →  **(a, **(b, c)) — 右结合！"""
        ast, _ = parse(*pratt, [T("id","a"), op("**"), T("id","b"), op("**"), T("id","c")])
        assert ast.node_name == "BinaryOp" and ast.op == "**"
        assert ast.right.node_name == "BinaryOp" and ast.right.op == "**"


# ═══════════════════════════════════════════════════════
# 前缀一元运算
# ═══════════════════════════════════════════════════════

class TestPrefixUnary:
    def test_not(self, pratt):
        ast, _ = parse(*pratt, [op("!"), T("id","a")])
        assert ast.node_name == "UnaryOp"
        assert ast.op == "!" and ast.position == "prefix"

    def test_bitwise_not(self, pratt):
        ast, _ = parse(*pratt, [op("~"), T("id","a")])
        assert ast.node_name == "UnaryOp"
        assert ast.op == "~" and ast.position == "prefix"

    def test_double_unary(self, pratt):
        """!!a  →  UnaryOp(!, UnaryOp(!, a))"""
        ast, _ = parse(*pratt, [op("!"), op("!"), T("id","a")])
        assert ast.node_name == "UnaryOp" and ast.op == "!"
        assert ast.operand.node_name == "UnaryOp" and ast.operand.op == "!"

    def test_unary_in_right_operand(self, pratt):
        """a + !b  →  BinaryOp(+, Ident(a), UnaryOp(!, Ident(b)))"""
        ast, _ = parse(*pratt, [T("id","a"), op("+"), op("!"), T("id","b")])
        assert ast.node_name == "BinaryOp" and ast.op == "+"
        assert ast.left.node_name == "Ident"
        assert ast.right.node_name == "UnaryOp" and ast.right.op == "!"

    def test_prefix_binds_tighter_than_infix(self, pratt):
        """!a + b  →  +(!(a), b) — 一元优先级高于二元"""
        ast, _ = parse(*pratt, [op("!"), T("id","a"), op("+"), T("id","b")])
        assert ast.node_name == "BinaryOp" and ast.op == "+"
        assert ast.left.node_name == "UnaryOp" and ast.left.op == "!"


# ═══════════════════════════════════════════════════════
# consumed_count
# ═══════════════════════════════════════════════════════

class TestConsumedCount:
    def test_single_ident(self, pratt):
        _, c = parse(*pratt, [T("id","a")])
        assert c == 1

    def test_single_number(self, pratt):
        _, c = parse(*pratt, [T("number","42")])
        assert c == 1

    def test_binary_3(self, pratt):
        _, c = parse(*pratt, [T("id","a"), op("+"), T("id","b")])
        assert c == 3

    def test_chain_5(self, pratt):
        _, c = parse(*pratt, [T("id","a"), op("+"), T("id","b"), op("+"), T("id","c")])
        assert c == 5

    def test_unary_2(self, pratt):
        _, c = parse(*pratt, [op("!"), T("id","a")])
        assert c == 2

    def test_unary_binary_4(self, pratt):
        _, c = parse(*pratt, [T("id","a"), op("+"), op("!"), T("id","b")])
        assert c == 4

    def test_stop_token(self, pratt):
        """遇到 stop_token 停止，不包括 stop_token。"""
        ast, c = parse(*pratt, [T("id","a"), op("+"), T("id","b"), T(";",";")],
                       stop_tokens={";"})
        assert c == 3
        assert ast.node_name == "BinaryOp" and ast.op == "+"


# ═══════════════════════════════════════════════════════
# 边界条件
# ═══════════════════════════════════════════════════════

class TestEdgeCases:
    def test_single_ident(self, pratt):
        ast, c = parse(*pratt, [T("id","x")])
        assert ast.node_name == "Ident" and c == 1

    def test_single_number(self, pratt):
        ast, c = parse(*pratt, [T("number","99")])
        assert ast.node_name == "Num" and c == 1

    def test_empty_raises(self, pratt):
        with pytest.raises(ValueError, match="表达式不完整"):
            parse(*pratt, [])

    def test_unknown_token_type_raises(self, pratt):
        """无法识别的 token 类型（既非原子也非运算符）→ ValueError。"""
        with pytest.raises(ValueError):
            parse(*pratt, [T("unknown","???")])
