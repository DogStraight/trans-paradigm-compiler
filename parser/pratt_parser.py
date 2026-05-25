# parser/pratt_parser.py
import toml
from typing import List, Tuple, Dict, Any
from define import Node, Token, FileManager


def load_operator_defs() -> List[Tuple[int, dict]]:
    """加载运算符优先级和结合性定义"""
    path = FileManager.get_full_path(FileManager.symbol_level_file)
    with open(path, "r", encoding="utf-8") as f:
        data = toml.load(f)
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
                # 后缀运算符放入中缀表
                infix_priority[sym] = prio
                infix_attrs[sym] = props
        else:
            infix_priority[sym] = prio
            infix_attrs[sym] = props
    return prefix_priority, prefix_attrs, infix_priority, infix_attrs


# ========== pratt解析器 ==========
def parse_expression(
    tokens: List[Token],
    idx: int,
    rbp: int,
    prefix_priority: Dict[str, int],
    prefix_attrs: Dict[str, Any],
    infix_priority: Dict[str, int],
    infix_attrs: Dict[str, Any],
) -> Tuple[Node, int]:
    """
    递归解析表达式，返回 (Node, 新索引)
    """
    if idx >= len(tokens):
        raise ValueError("表达式不完整")

    token = tokens[idx]

    # ---------- 前缀（nud）----------
    if is_number(token):
        # 根据是否包含小数点决定转换为 int 还是 float
        if "." in token.content:
            value = float(token.content)
        else:
            value = int(token.content)
        node = Node("Number", value=value)
        idx += 1
    elif is_string(token):
        s = token.content[1:-1] if len(token.content) >= 2 else token.content
        node = Node("String", value=s)
        idx += 1
    elif is_bool(token):
        node = Node("Bool", value=(token.content == "True"))
        idx += 1
    elif is_identifier(token):
        node = Node("Identifier", content=token.content)
        idx += 1
    elif is_paren(token) and token.content == "(":
        idx += 1
        node, idx = parse_expression(
            tokens, idx, 0, prefix_priority, prefix_attrs, infix_priority, infix_attrs
        )
        if idx >= len(tokens) or not (
            is_paren(tokens[idx]) and tokens[idx].content == ")"
        ):
            raise ValueError("缺少右括号")
        idx += 1
    elif is_operator(token) and token.content in prefix_attrs:
        props = prefix_attrs[token.content]
        # 处理一元前缀运算符
        if props.get("arity") == 1 and props.get("position") == "prefix":
            op = token.content
            idx += 1
            # 一元前缀的右绑定权设为很高（例如 100）
            right, idx = parse_expression(
                tokens,
                idx,
                100,
                prefix_priority,
                prefix_attrs,
                infix_priority,
                infix_attrs,
            )
            node = Node("UnaryOp", op=op, operand=right, position="prefix")
        else:
            # 后缀或未预期的，按普通前缀处理？这里报错
            raise ValueError(f"不支持的前缀运算符: {token.content}")
    elif is_none(token):
        node = Node("NoneLiteral")
        idx += 1
    else:
        raise ValueError(f"意外的 token: {token.content} (type: {token.type})")

    # ---------- 中缀（led）----------
    while idx < len(tokens):
        token = tokens[idx]
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
            # 一元后缀运算符
            idx += 1
            node = Node("UnaryOp", op=op, operand=node, position="postfix")
            # 后缀运算符优先级高，不递归右操作数，继续循环
            continue
        elif arity == 2:
            idx += 1
            assoc = props.get("assoc", "left")
            if assoc == "right":
                right_node, idx = parse_expression(
                    tokens,
                    idx,
                    lbp - 1,
                    prefix_priority,
                    prefix_attrs,
                    infix_priority,
                    infix_attrs,
                )
            else:
                right_node, idx = parse_expression(
                    tokens,
                    idx,
                    lbp,
                    prefix_priority,
                    prefix_attrs,
                    infix_priority,
                    infix_attrs,
                )
            node = Node("BinaryOp", op=op, left=node, right=right_node)
        elif arity == 3:
            second_sym = props.get("second")
            if not second_sym:
                raise ValueError(f"三元运算符缺少第二个符号: {op}")
            idx += 1  # 消费第一个符号
            middle, idx = parse_expression(
                tokens,
                idx,
                0,
                prefix_priority,
                prefix_attrs,
                infix_priority,
                infix_attrs,
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
            )
            node = Node(
                "TernaryOp",
                op1=op,
                op2=second_sym,
                first=node,
                second=middle,
                third=right,
            )
        else:
            raise ValueError(f"不支持的运算符元数: {arity}")

    return node, idx


def parse(tokens: List[Token], operator_defs: List[Tuple[int, Dict[str, Any]]]) -> Node:
    """
    解析 token 列表，返回 AST 根节点
    """
    prefix_priority, prefix_attrs, infix_priority, infix_attrs = build_priority_maps(
        operator_defs
    )
    ast, idx = parse_expression(
        tokens, 0, 0, prefix_priority, prefix_attrs, infix_priority, infix_attrs
    )
    if idx != len(tokens):
        raise ValueError("解析后有多余的 token")
    return ast


# ========== 辅助函数：判断 token 类型 ==========
def is_number(token: Token) -> bool:
    return token.type == "literal.number"


def is_string(token: Token) -> bool:
    return token.type == "literal.string"


def is_bool(token: Token) -> bool:
    return token.type in ("literal.bool_true", "literal.bool_false")


def is_identifier(token: Token) -> bool:
    return token.type == "id" or token.type.startswith("id.")


def is_operator(token: Token) -> bool:
    return token.type.startswith("symbol.base.") or token.type.startswith(
        "symbol.extend."
    )


def is_paren(token: Token) -> bool:
    return token.type.startswith("bracket.")


def is_none(token: Token) -> bool:
    return token.type == "literal.none"
