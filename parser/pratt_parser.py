# -*- coding: utf-8 -*-
from define import Node, Token
from parser.utils import (
    is_number,
    is_string,
    is_bool,
    is_identifier,
    is_operator,
    is_paren,
)


def read_operator_defs(filename):
    """
    从文件读取运算符定义。
    每行格式：{symbol:"+", arity:2, assoc:"left"}, {symbol:"-", arity:2, assoc:"left"}
    行号即优先级（数字越大优先级越高）。
    返回列表，每个元素为 (优先级, 属性字典)
    """
    operators = []  # 列表元素为 (优先级, 属性字典)
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
                    # 开始一个新的条目，收集直到匹配的 '}'
                    j = i
                    depth = 0
                    while j < len(parts):
                        seg = parts[j]
                        depth += seg.count("{") - seg.count("}")
                        if depth == 0 and j > i:
                            # 找到闭合的 '}'
                            break
                        j += 1
                    # 将 parts[i:j+1] 用逗号重新连接
                    full_item = ",".join(parts[i : j + 1])
                    i = j + 1
                else:
                    full_item = item_str
                    i += 1

                full_item = full_item.strip()
                if not full_item.startswith("{") or not full_item.endswith("}"):
                    continue
                # 去掉首尾大括号
                inner = full_item[1:-1].strip()
                if not inner:
                    continue

                # 解析内部的键值对（键:值）
                props = {}
                # 手动分割，注意值可能包含引号或嵌套
                pairs = []
                current = []
                in_quote = False
                for ch in inner:
                    if ch == '"':
                        in_quote = not in_quote
                        current.append(ch)
                    elif ch == "," and not in_quote:
                        # 分割键值对
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
                    # 去除值的引号（如果是字符串）
                    if val.startswith('"') and val.endswith('"'):
                        val = val[1:-1]
                    else:
                        # 尝试转换为数字
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


def build_priority_map(operator_defs):
    """从运算符定义列表构建优先级字典 {符号: 优先级} 和属性字典 {符号: 属性}"""
    priority = {}
    attrs = {}
    for prio, props in operator_defs:
        sym = props["symbol"]
        priority[sym] = prio
        attrs[sym] = props
    return priority, attrs


def parse_expression(tokens: list[Token], idx, rbp, priority, attrs):
    """
    递归解析表达式，返回 (Node, 新索引)
    - tokens: Token 列表
    - idx: 当前索引
    - rbp: 右绑定权
    - priority: {符号: 优先级} 字典
    - attrs: {符号: 属性字典} 字典
    """
    if idx >= len(tokens):
        raise ValueError("表达式不完整")
    token: Token = tokens[idx]

    # ---------- 前缀（nud） ----------
    if is_number(token):
        node = Node("Number", value=int(token.content))
        idx += 1
    elif is_string(token):
        # 字符串字面量，去除首尾引号
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
        node, idx = parse_expression(tokens, idx, 0, priority, attrs)
        if idx >= len(tokens) or not (
            is_paren(tokens[idx]) and tokens[idx].content == ")"
        ):
            raise ValueError("缺少右括号")
        idx += 1
    elif is_operator(token) and token.content in attrs:
        # 可能是一元前缀运算符
        props = attrs[token.content]
        if props.get("arity") == 1 and props.get("position") == "prefix":
            op = token.content
            idx += 1
            # 递归解析右操作数（一元前缀的右绑定权可设为很高，或使用特殊值）
            right, idx = parse_expression(
                tokens, idx, 100, priority, attrs
            )  # 100 表示很高优先级
            node = Node("UnaryOp", op=op, operand=right, position="prefix")
        else:
            raise ValueError("意外的前缀运算符: " + token.content)
    else:
        raise ValueError(
            "意外的 token: " + token.content + " (type: " + token.type + ")"
        )

    # ---------- 中缀（led） ----------
    while idx < len(tokens):
        token = tokens[idx]
        if not is_operator(token):
            break
        op = token.content
        if op not in attrs:
            break
        props = attrs[op]
        arity = props.get("arity", 2)  # 默认二元
        lbp = priority.get(op, 0)
        if lbp <= rbp:
            break

        if arity == 1 and props.get("position") == "postfix":
            # 一元后缀运算符
            idx += 1
            node = Node("UnaryOp", op=op, operand=node, position="postfix")
            # 后缀通常优先级高，不递归右操作数，继续循环检查下一个运算符
            continue
        elif arity == 2:
            # 二元运算符
            idx += 1
            assoc = props.get("assoc", "left")
            if assoc == "right":
                right_node, idx = parse_expression(
                    tokens, idx, lbp - 1, priority, attrs
                )
            else:
                right_node, idx = parse_expression(tokens, idx, lbp, priority, attrs)
            node = Node("BinaryOp", op=op, left=node, right=right_node)
        elif arity == 3:
            # 三元运算符（如 ? :）
            # 假设第一个符号为 op，第二个符号由 props['second'] 指定
            second_sym = props.get("second")
            if not second_sym:
                raise ValueError("三元运算符缺少第二个符号: " + op)
            idx += 1  # 消费第一个符号
            # 解析中间操作数
            middle, idx = parse_expression(
                tokens, idx, 0, priority, attrs
            )  # 中间操作数优先级为0
            # 检查第二个符号
            if idx >= len(tokens) or tokens[idx].content != second_sym:
                raise ValueError("缺少三元运算符的第二个符号: " + second_sym)
            idx += 1  # 消费第二个符号
            # 解析右操作数
            right, idx = parse_expression(
                tokens, idx, rbp, priority, attrs
            )  # 使用当前 rbp
            node = Node(
                "TernaryOp",
                op1=op,
                op2=second_sym,
                first=node,
                second=middle,
                third=right,
            )
        else:
            raise ValueError("不支持的运算符元数: " + str(arity))
    return node, idx


def parse(tokens, operator_defs):
    """解析 token 列表，返回 AST 根节点"""
    priority, attrs = build_priority_map(operator_defs)
    ast, idx = parse_expression(tokens, 0, 0, priority, attrs)
    if idx != len(tokens):
        raise ValueError("解析后有多余的 token")
    return ast


# ----------------------------------------------------------------------
# 测试（修改以适配分层 token 类型）
# ----------------------------------------------------------------------
def test():
    import tempfile
    import os

    # 创建临时配置文件（包含一元、二元、三元运算符）
    config_content = """
{symbol:"+", arity:2, assoc:"left"}
{symbol:"-", arity:2, assoc:"left"}
{symbol:"*", arity:2, assoc:"left"}
{symbol:"/", arity:2, assoc:"left"}
{symbol:"**", arity:2, assoc:"right"}
{symbol:"!", arity:1, position:"postfix"}
{symbol:"-", arity:1, position:"prefix"}
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

        # 模拟 Token 对象（包含 type 和 content）
        class MockToken:
            def __init__(self, content, typ):
                self.content = content
                self.type = typ

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
            tok("!", "symbol.base.not"),  # 假设 ! 作为后缀一元
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

        for i, toks in enumerate([tokens1, tokens2, tokens3, tokens4], 1):
            try:
                ast = parse(toks, operator_defs)
                print(f"\n测试 {i} AST:", ast.dump())
            except Exception as e:
                print(f"\n测试 {i} 出错:", e)

    finally:
        os.unlink(temp_filename)


if __name__ == "__main__":
    test()
