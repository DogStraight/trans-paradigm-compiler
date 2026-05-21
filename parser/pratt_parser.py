# -*- coding: utf-8 -*-
from typing import List, Tuple, Dict, Any
from define import Node, Token

from parser.utils import (
    is_number,
    is_string,
    is_bool,
    is_identifier,
    is_operator,
    is_paren,
    is_none,
)


class MockToken:
    def __init__(self, content, typ):
        self.content = content
        self.type = typ


# ========== 运算符定义加载 ==========
def read_operator_defs(filename: str) -> List[Tuple[int, Dict[str, Any]]]:
    """
    从文件读取运算符定义。
    每行格式：{symbol:"+", arity:2, assoc:"left"}, {symbol:"-", arity:2, assoc:"left"}
    行号即优先级（数字越大优先级越高）。
    返回列表，每个元素为 (优先级, 属性字典)
    """
    operators = []
    with open(filename, "r") as f:
        line_no = 1
        for line in f:
            line = line.strip()
            if not line:
                line_no += 1
                continue
            # 按逗号分割每个条目
            parts = line.split(",")
            i = 0
            while i < len(parts):
                # 合并可能被逗号分隔的键值对（因为一个条目内有多个键值对）
                item_str = parts[i].strip()
                if item_str.startswith("{"):
                    j = i
                    depth = 0
                    while j < len(parts):
                        seg = parts[j]
                        depth += seg.count("{") - seg.count("}")
                        if depth == 0 and j > i:
                            break
                        j += 1
                    full_item = ",".join(parts[i : j + 1])
                    i = j + 1
                else:
                    full_item = item_str
                    i += 1

                full_item = full_item.strip()
                if not full_item.startswith("{") or not full_item.endswith("}"):
                    continue
                inner = full_item[1:-1].strip()
                if not inner:
                    continue

                # 解析键值对
                props = {}
                pairs = []
                current = []
                in_quote = False
                for ch in inner:
                    if ch == '"':
                        in_quote = not in_quote
                        current.append(ch)
                    elif ch == "," and not in_quote:
                        pair_str = "".join(current).strip()
                        if pair_str:
                            pairs.append(pair_str)
                        current = []
                    else:
                        current.append(ch)
                if current:
                    pair_str = "".join(current).strip()
                    if pair_str:
                        pairs.append(pair_str)

                for pair in pairs:
                    if ":" not in pair:
                        continue
                    key, val = pair.split(":", 1)
                    key = key.strip()
                    val = val.strip()
                    if val.startswith('"') and val.endswith('"'):
                        val = val[1:-1]
                    else:
                        try:
                            if "." in val:
                                val = float(val)
                            else:
                                val = int(val)
                        except:
                            pass
                    props[key] = val
                if "symbol" in props:
                    operators.append((line_no, props))
    return operators


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


# ========== 测试 ==========
def test():
    import tempfile
    import os

    config_content = """
{symbol:"+", arity:2, assoc:"left"}
{symbol:"-", arity:2, assoc:"left"}
{symbol:"*", arity:2, assoc:"left"}
{symbol:"/", arity:2, assoc:"left"}
{symbol:"**", arity:2, assoc:"right"}
{symbol:"!", arity:1, position:"postfix"}
{symbol:"-", arity:1, position:"prefix"}
{symbol:"+", arity:1, position:"prefix"}
{symbol:"?", arity:3, second:":", assoc:"right"}
    """
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write(config_content.strip())
        temp_filename = f.name

    try:
        operator_defs = read_operator_defs(temp_filename)
        print("运算符定义 (优先级, 属性):")
        for prio, props in operator_defs:
            print("  ", prio, props)

        def tok(content, typ):
            return MockToken(content, typ)

        # 测试 1: 一元前缀负号 + 二元运算
        tokens1 = [
            tok("-", "symbol.base.sub"),
            tok("1", "literal.number"),
            tok("+", "symbol.base.add"),
            tok("2", "literal.number"),
            tok("*", "symbol.base.multiple"),
            tok("3", "literal.number"),
        ]
        # 测试 2: 一元后缀阶乘
        tokens2 = [
            tok("5", "literal.number"),
            tok("!", "symbol.base.not"),
            tok("+", "symbol.base.add"),
            tok("3", "literal.number"),
        ]
        # 测试 3: 三元条件表达式
        tokens3 = [
            tok("1", "literal.number"),
            tok("?", "symbol.base.question_mark"),
            tok("2", "literal.number"),
            tok(":", "symbol.base.colon"),
            tok("3", "literal.number"),
        ]
        # 测试 4: 乘方右结合
        tokens4 = [
            tok("2", "literal.number"),
            tok("**", "symbol.extend.power"),
            tok("3", "literal.number"),
            tok("**", "symbol.extend.power"),
            tok("2", "literal.number"),
        ]
        # 测试 5: 一元正号（前缀）与二元加号同时存在
        tokens5 = [
            tok("+", "symbol.base.add"),
            tok("3", "literal.number"),
            tok("+", "symbol.base.add"),
            tok("4", "literal.number"),
        ]

        for i, toks in enumerate([tokens1, tokens2, tokens3, tokens4, tokens5], 1):
            try:
                ast = parse(toks, operator_defs)  # type: ignore
                print(f"\n测试 {i} AST:", ast.dump())
            except Exception as e:
                print(f"\n测试 {i} 出错:", e)

    finally:
        os.unlink(temp_filename)


if __name__ == "__main__":
    test()
