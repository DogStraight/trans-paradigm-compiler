"""Pratt parser — operator-precedence expression parsing.

Loads operator definitions from _symbol_level.toml and handles
infix/prefix/postfix operators with proper precedence and associativity.
"""

import os
import tomllib
from typing import List, Tuple, Dict, Any, Optional
from core.define import Node, Token, FileManager


# ========== 运算符定义加载 ==========
def load_operator_defs(rules_dir: str) -> List[Tuple[int, dict]]:
    """加载运算符优先级和结合性定义"""
    path = os.path.join(rules_dir, "_symbol_level.toml")
    content = FileManager.read_file(path)
    data = tomllib.loads(content)
    operators = data.get("operator", [])
    operator_defs = []
    for idx, op in enumerate(operators, start=1):
        props = {
            "symbol": op["symbol"],
            "arity": op["arity"],
            "assoc": op.get("assoc", "left"),
        }
        if "position" in op:
            props["position"] = op["position"]
        if "second" in op:
            props["second"] = op["second"]
        operator_defs.append((idx, props))
    return operator_defs


def build_priority_maps(operator_defs):
    prefix_priority = {}
    prefix_attrs = {}
    infix_priority = {}
    infix_attrs = {}

    for prio, props in operator_defs:
        sym = props["symbol"]
        arity = props.get("arity", 2)
        if arity == 1 and "position" in props:
            if props["position"] == "prefix":
                prefix_priority[sym] = prio
                prefix_attrs[sym] = props
            elif props["position"] == "postfix":
                infix_priority[sym] = prio
                infix_attrs[sym] = props
        else:
            infix_priority[sym] = prio
            infix_attrs[sym] = props
    return prefix_priority, prefix_attrs, infix_priority, infix_attrs


# ========== Token 分类（从 _token.toml 加载）==========
def load_token_categories(rules_dir: str) -> dict:
    """从 base/_lexer.toml 加载 [token_category] 配置"""
    try:
        base_path = os.path.join(rules_dir, "base", "_lexer.toml")
        content = FileManager.read_file(base_path)
        data = tomllib.loads(content)
        return data.get("token_category", {})
    except Exception:
        return {}


def build_token_classifier(categories: dict) -> dict:
    """从分类配置构建 {name: check_fn(token) -> bool} 映射"""
    checks = {}
    for name, cfg in categories.items():
        match = cfg.get("match", "exact")
        types = cfg.get("types", [])
        if match == "exact":
            type_set = set(types)
            checks[name] = lambda t, s=type_set: isinstance(t, Token) and t.type in s
        elif match == "prefix":
            prefixes = tuple(types)
            checks[name] = lambda t, p=prefixes: isinstance(t, Token) and t.type.startswith(p)
    return checks


# 模块级分类器（由 install_token_classifier 设置）
_token_checks: dict = {}
def _check(name: str, token) -> bool:
    fn = _token_checks.get(name)
    return fn(token) if fn else False

def is_number(token) -> bool:    return _check("number", token)
def is_string(token) -> bool:    return _check("string", token)
def is_bool(token) -> bool:      return _check("bool", token)
def is_identifier(token) -> bool: return _check("identifier", token)
def is_operator(token) -> bool:   return _check("operator", token)
def is_none(token) -> bool:      return _check("none", token)

def install_token_classifier(categories: dict) -> None:
    """从 [token_category] 配置安装分类函数，替换模块级 is_* 的行为"""
    global _token_checks
    _token_checks = build_token_classifier(categories)


# ========== 字面量解析辅助 ==========
def parse_number_literal(token: Token) -> Node:
    content = token.content
    if "'" in content:
        parts = content.split("'", 1)
        width_part = parts[0].strip()
        rest = parts[1] if len(parts) > 1 else ""
        # 宽度部分可能为空（自动位宽）或数字
        width = None
        if width_part:
            try:
                width = int(width_part)
            except ValueError:
                # 非法宽度，按自动处理
                width = None
        if rest and rest[0] in ("b", "o", "d", "h"):
            base = rest[0]
            value = rest[1:] if len(rest) > 1 else ""
            node = Node("BitWidthLiteral", width=width, base=base, value=value)
            return node
        # 格式错误：回退为普通数字
        return Node("Number", value=content)
    # 浮点数
    if "." in content:
        try:
            return Node("Number", value=float(content))
        except ValueError:
            pass
    # 普通整数
    try:
        return Node("Number", value=int(content))
    except ValueError:
        # 无法识别的字面量，作为字符串保留
        return Node("Number", value=content)


# ========== Pratt 解析核心 ==========
def parse_expression(
    tokens: List[Token],
    idx: int,
    rbp: int,
    prefix_priority: Dict[str, int],
    prefix_attrs: Dict[str, Any],
    infix_priority: Dict[str, int],
    infix_attrs: Dict[str, Any],
    max_infix_prio: int,
    unary_prefix_rbp: int,
    atom_parser=None,
    stop_tokens: Optional[set] = None,
) -> Tuple[Node, int]:
    """递归解析表达式，返回 (Node, 新索引)

    atom_parser: Optional[(tokens, idx) → (node, consumed)] 原子规则回调
    stop_tokens: Optional[set[str]] 遇到这些 token 类型时停止中缀循环
    """
    if idx >= len(tokens):
        raise ValueError("表达式不完整")

    # ---------- 前缀处理（先原子解析器，后内置前缀）----------
    node = None
    # 跳过行内注释（不纳入表达式 AST）
    while idx < len(tokens) and isinstance(tokens[idx], Token) and tokens[idx].type == "comment":
        idx += 1
    if idx >= len(tokens):
        raise ValueError("表达式不完整")

    # 1. 原子解析器
    if atom_parser is not None:
        node, consumed = atom_parser(tokens, idx)
        if node is not None:
            idx += consumed

    # 2. 内置前缀（原子未命中时启用）
    if node is None:
        token = tokens[idx]
        if isinstance(token, Node):
            node, idx = token, idx + 1
        elif is_number(token):
            node = parse_number_literal(token)
            idx += 1
        elif is_string(token):
            s = token.content[1:-1] if len(token.content) >= 2 else token.content
            node = Node("String", value=s)
            idx += 1
        elif is_bool(token):
            node = Node("Bool", value=(token.type == "literal.bool_true"))
            idx += 1
        elif is_identifier(token):
            name = token.content
            node = Node("Identifier", content=name)
            idx += 1
        elif is_operator(token) and token.content in prefix_attrs:
            props = prefix_attrs[token.content]
            if props.get("arity") == 1 and props.get("position") == "prefix":
                op = token.content
                idx += 1
                right, idx = parse_expression(
                    tokens,
                    idx,
                    unary_prefix_rbp,
                    prefix_priority,
                    prefix_attrs,
                    infix_priority,
                    infix_attrs,
                    max_infix_prio,
                    unary_prefix_rbp,
                    atom_parser,
                    stop_tokens,
                )
                node = Node("UnaryOp", op=op, operand=right, position="prefix")
            else:
                raise ValueError(f"不支持的前缀运算符: {token.content}")
        elif is_none(token):
            node = Node("NoneLiteral")
            idx += 1
        else:
            raise ValueError(f"意外的 token: {token.content} (type: {token.type})")

    # ---------- 中缀（led）----------
    while idx < len(tokens):
        token = tokens[idx]
        # 停止符集合：遇到则终止表达式解析（如右括号、逗号等）
        if (
            stop_tokens is not None
            and isinstance(token, Token)
            and token.type in stop_tokens
        ):
            break
        if not is_operator(token):
            break
        op = token.content
        if op not in infix_attrs:
            break
        props = infix_attrs[op]
        arity = props.get("arity", 2)
        lbp = infix_priority.get(op, 0)
        if lbp <= rbp:
            break

        if arity == 1 and props.get("position") == "postfix":
            idx += 1
            node = Node("UnaryOp", op=op, operand=node, position="postfix")
            continue
        elif arity == 2:
            idx += 1
            assoc = props.get("assoc", "left")
            right_rbp = lbp - 1 if assoc == "right" else lbp
            right_node, idx = parse_expression(
                tokens,
                idx,
                right_rbp,
                prefix_priority,
                prefix_attrs,
                infix_priority,
                infix_attrs,
                max_infix_prio,
                unary_prefix_rbp,
                atom_parser,
                stop_tokens,
            )
            node = Node("BinaryOp", op=op, left=node, right=right_node)
        elif arity == 3:
            second_sym = props.get("second")
            if not second_sym:
                raise ValueError(f"三元运算符缺少第二个符号: {op}")
            idx += 1
            middle, idx = parse_expression(
                tokens,
                idx,
                0,
                prefix_priority,
                prefix_attrs,
                infix_priority,
                infix_attrs,
                max_infix_prio,
                unary_prefix_rbp,
                atom_parser,
                stop_tokens,
            )
            if idx >= len(tokens) or tokens[idx].content != second_sym:
                raise ValueError(f"缺少三元运算符的第二个符号: {second_sym}")
            idx += 1
            right, idx = parse_expression(
                tokens,
                idx,
                rbp,
                prefix_priority,
                prefix_attrs,
                infix_priority,
                infix_attrs,
                max_infix_prio,
                unary_prefix_rbp,
                atom_parser,
                stop_tokens,
            )
            node = Node(
                "TernaryOp",
                op1=op,
                op2=second_sym,
                cond=node,
                true_val=middle,
                false_val=right,
            )
        else:
            raise ValueError(f"不支持的运算符元数: {arity}")

    if node is None:
        raise ValueError("解析失败，未生成 AST 节点")
    return node, idx



def parse_with_count(
    tokens: list,
    start_idx: int = 0,
    operator_defs: Optional[list] = None,
    atom_parser=None,
    stop_tokens: Optional[set] = None,
) -> Tuple[Optional[Node], int]:
    """解析 token 列表，返回 (AST 节点, 实际消费的 token 数量)

    tokens 可包含 Token 或预解析的 Node（如 CallExpr），
    Node 作为原子表达式直接返回。
    """
    prefix_priority, prefix_attrs, infix_priority, infix_attrs = build_priority_maps(
        operator_defs
    )
    max_infix_prio = max(infix_priority.values()) if infix_priority else 0
    unary_prefix_rbp = max_infix_prio + 1

    ast, idx = parse_expression(
        tokens,
        start_idx,
        0,
        prefix_priority,
        prefix_attrs,
        infix_priority,
        infix_attrs,
        max_infix_prio,
        unary_prefix_rbp,
        atom_parser,
        stop_tokens,
    )
    if ast is None:
        return None, 0
    return ast, idx - start_idx
