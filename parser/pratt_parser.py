# parser/pratt_parser.py
import tomllib
from typing import List, Tuple, Dict, Any
from core.define import Node, Token, FileManager


# ========== 运算符定义加载 ==========
def load_operator_defs() -> List[Tuple[int, dict]]:
    """加载运算符优先级和结合性定义"""
    content = FileManager.read_file(FileManager.symbol_level_file)
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


def parse_brace_expr(
    tokens: List[Token],
    idx: int,
    prefix_priority: Dict[str, int],
    prefix_attrs: Dict[str, Any],
    infix_priority: Dict[str, int],
    infix_attrs: Dict[str, Any],
    max_infix_prio: int,
    unary_prefix_rbp: int,
) -> Tuple[Node, int]:
    """解析花括号表达式 { ... }，支持串联和复制模式"""
    idx += 1  # 跳过 '{'
    items = []
    is_replication = False
    node = None

    while idx < len(tokens):
        if is_paren(tokens[idx]) and tokens[idx].content == "}":
            break
        if tokens[idx].content == ",":
            idx += 1
            continue

        item_node, idx = parse_expression(
            tokens,
            idx,
            0,
            prefix_priority,
            prefix_attrs,
            infix_priority,
            infix_attrs,
            max_infix_prio,
            unary_prefix_rbp,
        )
        if item_node is None:
            break
        items.append(item_node)

        # 检测复制模式: {count{value}}
        if idx < len(tokens) and is_paren(tokens[idx]) and tokens[idx].content == "{":
            inner_node, idx = parse_expression(
                tokens,
                idx,
                0,
                prefix_priority,
                prefix_attrs,
                infix_priority,
                infix_attrs,
                max_infix_prio,
                unary_prefix_rbp,
            )
            node = Node("ReplicateExpr", count=item_node, value=inner_node)
            is_replication = True
            break

    # 消费右花括号
    if idx >= len(tokens) or not (is_paren(tokens[idx]) and tokens[idx].content == "}"):
        raise ValueError("缺少右花括号")
    idx += 1

    if is_replication:
        assert node is not None, "复制模式未生成节点"
        return node, idx
    else:
        # 使用 first/rest 结构（与语法规则一致）
        if not items:
            return Node("ConcatExpr", first=None, rest=None), idx
        first = items[0]
        if len(items) > 1:
            rest_items = []
            for item in items[1:]:
                rest_items.append(Node("symbol.base.comma", value=","))
                rest_items.append(item)
            rest = Node("sequence", sub_node=rest_items)
        else:
            rest = None
        return Node("ConcatExpr", first=first, rest=rest), idx


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
) -> Tuple[Node, int]:
    """递归解析表达式，返回 (Node, 新索引)"""
    if idx >= len(tokens):
        raise ValueError("表达式不完整")

    token = tokens[idx]

    # ---------- 括号处理器注册表 ----------
    def handle_parentheses(tokens, cur_idx):
        # 圆括号: ( expr )
        cur_idx += 1  # 跳过 '('
        inner_node, cur_idx = parse_expression(
            tokens,
            cur_idx,
            0,
            prefix_priority,
            prefix_attrs,
            infix_priority,
            infix_attrs,
            max_infix_prio,
            unary_prefix_rbp,
        )
        current_token: Token = tokens[cur_idx]
        if cur_idx >= len(tokens) or not (
            is_paren(current_token) and current_token.content == ")"
        ):
            raise ValueError("缺少右括号")
        cur_idx += 1
        pe = Node("ParenthesizedExpr", expr=inner_node)

        return pe, cur_idx

    def handle_braces(tokens, cur_idx):
        # 花括号: { ... } 支持串联和复制模式
        return parse_brace_expr(
            tokens,
            cur_idx,
            prefix_priority,
            prefix_attrs,
            infix_priority,
            infix_attrs,
            max_infix_prio,
            unary_prefix_rbp,
        )

    bracket_handlers = {
        "(": handle_parentheses,
        "{": handle_braces,
    }

    # ---------- 前缀处理函数（返回 (Node, new_idx)）----------
    def handle_number(cur_idx):
        node = parse_number_literal(tokens[cur_idx])
        cur_idx += 1
        return node, cur_idx

    def handle_string(cur_idx):
        s = (
            tokens[cur_idx].content[1:-1]
            if len(tokens[cur_idx].content) >= 2
            else tokens[cur_idx].content
        )
        node = Node("String", value=s)
        cur_idx += 1
        return node, cur_idx

    def handle_bool(cur_idx):
        node = Node("Bool", value=(tokens[cur_idx].type == "literal.bool_true"))

        cur_idx += 1
        return node, cur_idx

    def handle_identifier(cur_idx):
        name = tokens[cur_idx].content
        node = Node("Identifier", content=name)

        cur_idx += 1
        # 处理 id[expr] 索引访问
        if (
            cur_idx < len(tokens)
            and is_paren(tokens[cur_idx])
            and tokens[cur_idx].content == "["
        ):
            cur_idx += 1  # 跳过 '['
            index_node, cur_idx = parse_expression(
                tokens,
                cur_idx,
                0,
                prefix_priority,
                prefix_attrs,
                infix_priority,
                infix_attrs,
                max_infix_prio,
                unary_prefix_rbp,
            )
            if cur_idx >= len(tokens) or not (
                is_paren(tokens[cur_idx]) and tokens[cur_idx].content == "]"
            ):
                raise ValueError("缺少右方括号")
            cur_idx += 1
            node = Node("IndexedId", id_name=name, index=index_node)
        return node, cur_idx

    def handle_bracket(cur_idx):
        current_token: Token = tokens[cur_idx]
        handler = bracket_handlers[current_token.content]
        node, new_idx = handler(tokens, cur_idx)
        return node, new_idx

    def handle_prefix_op(cur_idx):
        current_token: Token = tokens[cur_idx]
        props = prefix_attrs[current_token.content]
        if props.get("arity") == 1 and props.get("position") == "prefix":
            op = current_token.content
            cur_idx += 1
            right, cur_idx = parse_expression(
                tokens,
                cur_idx,
                unary_prefix_rbp,
                prefix_priority,
                prefix_attrs,
                infix_priority,
                infix_attrs,
                max_infix_prio,
                unary_prefix_rbp,
            )
            uo = Node("UnaryOp", op=op, operand=right, position="prefix")
            return uo, cur_idx
        else:
            raise ValueError(f"不支持的前缀运算符: {tokens[cur_idx].content}")

    def handle_none(cur_idx):
        cur_idx += 1
        return Node("NoneLiteral"), cur_idx

    # 匹配条件与处理函数的映射（顺序重要）
    prefix_handlers = [
        (lambda idx: is_number(tokens[idx]), handle_number),
        (lambda idx: is_string(tokens[idx]), handle_string),
        (lambda idx: is_bool(tokens[idx]), handle_bool),
        (lambda idx: is_identifier(tokens[idx]), handle_identifier),
        (lambda idx: is_paren(tokens[idx]), handle_bracket),
        (
            lambda idx: is_operator(tokens[idx])
            and tokens[idx].content in prefix_attrs,
            handle_prefix_op,
        ),
        (lambda idx: is_none(tokens[idx]), handle_none),
    ]

    # 匹配并执行前缀处理
    node = None
    for cond, handler in prefix_handlers:
        if cond(idx):
            node, idx = handler(idx)
            break
    else:
        raise ValueError(
            f"意外的 token: {tokens[idx].content} (type: {tokens[idx].type})"
        )

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

    if node is None:
        raise ValueError("解析失败，未生成 AST 节点")
    return node, idx


# ========== 对外接口 ==========
def parse(tokens: List[Token], operator_defs: List[Tuple[int, Dict[str, Any]]]) -> Node:
    """解析 token 列表，返回 AST 根节点"""
    prefix_priority, prefix_attrs, infix_priority, infix_attrs = build_priority_maps(
        operator_defs
    )
    max_infix_prio = max(infix_priority.values()) if infix_priority else 0
    unary_prefix_rbp = max_infix_prio + 1

    ast, _ = parse_expression(
        tokens,
        0,
        0,
        prefix_priority,
        prefix_attrs,
        infix_priority,
        infix_attrs,
        max_infix_prio,
        unary_prefix_rbp,
    )
    return ast


def parse_with_count(
    tokens: List[Token], operator_defs: List[Tuple[int, Dict[str, Any]]]
) -> Tuple[Node, int]:
    """解析 token 列表，返回 (AST 节点, 实际消费的 token 数量)"""
    prefix_priority, prefix_attrs, infix_priority, infix_attrs = build_priority_maps(
        operator_defs
    )
    max_infix_prio = max(infix_priority.values()) if infix_priority else 0
    unary_prefix_rbp = max_infix_prio + 1

    ast, idx = parse_expression(
        tokens,
        0,
        0,
        prefix_priority,
        prefix_attrs,
        infix_priority,
        infix_attrs,
        max_infix_prio,
        unary_prefix_rbp,
    )
    return ast, idx
