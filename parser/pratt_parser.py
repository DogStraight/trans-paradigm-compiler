"""Pratt parser — operator-precedence expression parsing.

Loads operator definitions from _symbol_level.toml and handles
infix/prefix/postfix operators with proper precedence and associativity.
Doc: docs/language_walkthrough.md（Pratt 表达式解析）
"""

from typing import Any
from core.define import Node, Token
from ._constants import COMMENT_TOKEN_TYPE, NEWLINE_TOKEN_TYPE



def process_operator_data(data: list) -> list[tuple[int, dict]]:
    """处理原始运算符 TOML 配置为 (priority, props) 列表。"""
    operator_defs = []
    for idx, op in enumerate(data, start=1):
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


# ── Token 分类 ──
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
            checks[name] = lambda t, p=prefixes: isinstance(
                t, Token
            ) and t.type.startswith(p)
    return checks


# 模块级分类器（由 install_token_classifier 设置）
_token_checks: dict = {}

# 位宽字面量解析钩子：由语言层注入（None = 不识别位宽字面量）
_bit_width_literal_parser = None

# 布尔真值 token 类型（由 token_category.bool 配置推导）
_bool_true_type = None

# 原子规则名映射：{token_type: 规则名}，由语言层注入（从 is_atom 单字面 token
# production 规则推导，如 literal.string → StringLiteral/StringLit）。内置前缀
# 兜底产出的节点名据此与语言包规则名对齐（A2）——语言定义原子规则即自动对齐，
# 无规则时才回退内置名。
_atom_name_map: dict[str, str] = {}


def install_atom_name_map(mapping: dict) -> None:
    """注入原子 token → 规则名映射（保持本模块语言无关）。"""
    global _atom_name_map
    _atom_name_map = dict(mapping)


def _check(name: str, token) -> bool:
    fn = _token_checks.get(name)
    return fn(token) if fn else False

def is_number(token) -> bool:
    return _check("number", token)


def is_string(token) -> bool:
    return _check("string", token)


def is_bool(token) -> bool:
    return _check("bool", token)


def is_identifier(token) -> bool:
    return _check("identifier", token)


def is_operator(token) -> bool:
    return _check("operator", token)


def is_none(token) -> bool:
    return _check("none", token)


def install_bit_width_literal_parser(fn) -> None:
    """注入位宽字面量解析器 fn(content) -> Node | None。

    None 返回值表示该 token 不是位宽字面量，回退到通用数字解析。
    由语言层在初始化时调用，保持本模块语言无关。
    """
    global _bit_width_literal_parser
    _bit_width_literal_parser = fn


def install_token_classifier(categories: dict) -> None:
    """从 [token_category] 配置安装分类函数，替换模块级 is_* 的行为"""
    if not categories:
        raise ValueError(
            "[pratt] token categories is empty — check base/_lexer.toml [token_category]"
        )
    global _token_checks, _bool_true_type
    _token_checks = build_token_classifier(categories)
    # 从 bool 分类配置推导真值 token 类型（约定：types 列表第一个为真值）
    bool_cfg = categories.get("bool")
    if isinstance(bool_cfg, dict):
        bool_types = bool_cfg.get("types") or []
        _bool_true_type = bool_types[0] if bool_types else None
    else:
        _bool_true_type = None


# ── 字面量解析辅助 ──
def parse_number_literal(token: Token) -> Node:
    content = token.content
    # 位宽字面量（如 8'hff）：由语言层注入的解析器处理
    if _bit_width_literal_parser is not None:
        node = _bit_width_literal_parser(content)
        if node is not None:
            return node
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


# ── Pratt 解析核心 ──
def _skip_gap_comments(
    tokens: list[Token],
    idx: int,
    anchor: str,
    comment_sink=None,
) -> tuple[int, list[tuple[str, int]]]:
    """跳过 operator 消费后、操作数解析前的 trivia，收集行中注释（ADR-0013 决策 5）。

    语义：`a + /* c */ b` 的 `/* c */` 位于 operator（`+`）与右操作数之间
    ——由消费 operator 的调用点在递归操作数前先行跳过并收集，注释随即将构造
    的 BinaryOp/TernaryOp/UnaryOp 节点上挂（inline_after，锚 = operator）。
    与 parse_expression 入口的前缀 while 互补：入口 while 处理"表达式开头"
    的注释（无 operator 上下文）；本函数处理"operator 间隙"的注释。

    行中/行尾判定（与 parser collect_following_comments 同语义）：
      - 行中（注释后同行有代码）→ 返回收集，调用方挂节点 inline_after；
      - 行尾（注释后即换行，`//` 行注释典型形态）→ 维持 comment_sink
        现状语义（行尾注释不挂 inline_after——行中断行会吞后续代码）。
        注意：sink 条目按旧 pratt 前缀 while 语义标 midline=True（错插
        由既有 restore 边界处理，不在此改动——见 references.md「同行
        多注释局限」相邻边界）。

    Returns: (新 idx, 行中注释 [(text, line)] 列表)
    """
    collected: list[tuple[str, int]] = []
    while idx < len(tokens):
        t = tokens[idx]
        if not isinstance(t, Token):
            break
        if t.type == COMMENT_TOKEN_TYPE:
            # 注释后跳过注释/换行，找第一个代码 token 判同行（midline）
            off = 1
            nxt = None
            while idx + off < len(tokens):
                cand = tokens[idx + off]
                if isinstance(cand, Token) and cand.type in (
                    COMMENT_TOKEN_TYPE,
                    NEWLINE_TOKEN_TYPE,
                ):
                    off += 1
                    continue
                nxt = cand
                break
            if nxt is not None and getattr(nxt, "line", -1) == t.line:
                collected.append((t.content, t.line))
            elif comment_sink is not None and anchor:
                comment_sink(
                    {
                        "anchor": anchor,
                        "text": t.content,
                        "line": t.line,
                        "midline": True,
                    }
                )
            idx += 1
            continue
        if t.type == NEWLINE_TOKEN_TYPE:
            idx += 1
            continue
        break
    return idx, collected


def _mount_op_comments(
    node: Node,
    op: str,
    gap_comments: list[tuple[str, int]],
) -> None:
    """将 operator 间隙行中注释挂到表达式节点（ADR-0013 决策 5）。

    `_comment_slots["inline_after"][op] = [(text, line), ...]`——与
    parse_token 侧 collect_following_comments 的 inline_after 协议一致
    （锚 = 注释前 token 内容），renderer line 原语按锚定位消费。
    空列表不挂（无属性噪音）。语言无关：`_comment_slots` 是引擎协议
    （下划线属性，normalizer 保留、dump 过滤）。
    """
    if not gap_comments:
        return
    slots = getattr(node, "_comment_slots", None)
    if slots is None:
        slots = {}
        node.add_attr("_comment_slots", slots)
    ia = slots.setdefault("inline_after", {})
    existing = ia.setdefault(op, [])
    for entry in gap_comments:
        if entry not in existing:
            existing.append(entry)


def parse_expression(
    tokens: list[Token],
    idx: int,
    rbp: int,
    prefix_priority: dict[str, int],
    prefix_attrs: dict[str, Any],
    infix_priority: dict[str, int],
    infix_attrs: dict[str, Any],
    max_infix_prio: int,
    unary_prefix_rbp: int,
    atom_parser=None,
    stop_tokens: set | None = None,
    comment_sink=None,
) -> tuple[Node, int]:
    """递归解析表达式，返回 (Node, 新索引)

    atom_parser: (tokens, idx) → (node, consumed) | None 原子规则回调
    stop_tokens: set[str | None] 遇到这些 token 类型时停止中缀循环
    comment_sink: Callable[[dict], None] | None 前缀位置跳过的行内注释
        回调（条目 {anchor, text, line, midline}，与 parser._comment_anchors
        同构）——pratt 表达式内的注释（`a + /* c */ b` 的 `/* c */`）被本
        循环跳过时经此通道记录，渲染后锚点回插防丢（注释节点模型 2b-2
        兜底路径）。语言无关：引擎不收集，由调用方决定去向。
    """
    if idx >= len(tokens):
        raise ValueError("表达式不完整")

    # ── 前缀处理（先原子解析器，后内置前缀）──
    node = None
    # 跳过行内注释与换行（不纳入表达式 AST）。
    # 换行跳过只发生在前缀位置（表达式/操作数开头）：三目 `cond ? a :` 后接
    # 续行、行尾运算符（wrap 折行 `&&` 留行尾）后接操作数等，newline 是续行
    # 分隔符。表达式"结束"仍由中缀循环控制（遇 newline 非运算符自然 break），
    # 前缀跳过不吞掉结束信号——`expr1\n expr2` 在 expr1 的中缀循环即退出。
    # 注释不纳入 AST 但不得静默丢失（P1.5）：跳过时经 comment_sink 记录，
    # 锚 = 注释前最后一个 token（与 parse_token 行中注释语义一致，连续注释
    # 共用同一锚，restore 去重兜底）。无 sink 或锚不可得（前无 token /
    # 预解析 Node）时保持原行为跳过（Node 前的注释由外层规则收集）。
    _anchor_tok = tokens[idx - 1] if idx > 0 else None
    while (
        idx < len(tokens)
        and isinstance(tokens[idx], Token)
        and tokens[idx].type in (COMMENT_TOKEN_TYPE, NEWLINE_TOKEN_TYPE)
    ):
        if (
            tokens[idx].type == COMMENT_TOKEN_TYPE
            and comment_sink is not None
            and isinstance(_anchor_tok, Token)
            and _anchor_tok.content
        ):
            comment_sink(
                {
                    "anchor": _anchor_tok.content,
                    "text": tokens[idx].content,
                    "line": tokens[idx].line,
                    "midline": True,
                }
            )
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
            node = Node("Bool", value=(token.type == _bool_true_type))
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
                # 前缀一元 operator 间隙注释（`- /* c */ a`）：跳过并收集，
                # 挂到将构造的 UnaryOp（ADR-0013 决策 5）
                idx, gap_comments = _skip_gap_comments(
                    tokens, idx, op, comment_sink
                )
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
                    comment_sink,
                )
                node = Node("UnaryOp", op=op, operand=right, position="prefix")
                _mount_op_comments(node, op, gap_comments)
            else:
                raise ValueError(f"不支持的前缀运算符: {token.content}")
        elif is_none(token):
            node = Node("NoneLiteral")
            idx += 1
        else:
            raise ValueError(f"意外的 token: {token.content} (type: {token.type})")

    # ── 中缀（led）──
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
            # operator 间隙注释（`a + /* c */ b`）：跳过并收集，挂到将构造
            # 的 BinaryOp（ADR-0013 决策 5）——原由 RHS 递归入口 while sink
            idx, gap_comments = _skip_gap_comments(tokens, idx, op, comment_sink)
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
                comment_sink,
            )
            node = Node("BinaryOp", op=op, left=node, right=right_node)
            _mount_op_comments(node, op, gap_comments)
        elif arity == 3:
            second_sym = props.get("second")
            if not second_sym:
                raise ValueError(f"三元运算符缺少第二个符号: {op}")
            idx += 1
            # 三目 op1（`?`）间隙注释（`cond ? /* 真 */ a : b`）：
            # 跳过并收集，挂到将构造的 TernaryOp
            idx, gap_comments1 = _skip_gap_comments(tokens, idx, op, comment_sink)
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
                comment_sink,
            )
            if idx >= len(tokens) or tokens[idx].content != second_sym:
                raise ValueError(f"缺少三元运算符的第二个符号: {second_sym}")
            idx += 1
            # 三目 op2（`:`）间隙注释（`cond ? a : /* 假 */ b`）：
            # 跳过并收集，挂到将构造的 TernaryOp
            idx, gap_comments2 = _skip_gap_comments(
                tokens, idx, second_sym, comment_sink
            )
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
                comment_sink,
            )
            node = Node(
                "TernaryOp",
                op1=op,
                op2=second_sym,
                cond=node,
                true_val=middle,
                false_val=right,
            )
            _mount_op_comments(node, op, gap_comments1)
            _mount_op_comments(node, second_sym, gap_comments2)
        else:
            raise ValueError(f"不支持的运算符元数: {arity}")

    if node is None:
        raise ValueError("解析失败，未生成 AST 节点")
    return node, idx


def parse_with_count(
    tokens: list,
    start_idx: int = 0,
    operator_defs: list | None = None,
    atom_parser=None,
    stop_tokens: set | None = None,
    comment_sink=None,
) -> tuple[Node | None, int]:
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
        comment_sink,
    )
    if ast is None:
        return None, 0
    return ast, idx - start_idx
