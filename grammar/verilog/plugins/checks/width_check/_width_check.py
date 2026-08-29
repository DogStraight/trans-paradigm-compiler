"""_width_check.py — 位宽一致性检查 postpass（width_check 插件，P1.10 分期）

阶段 A1：符号宽度表——从 analyzer.all_symbols 提取每符号的宽度表达式
文本（wire/reg/integer/ANSI+body 端口；类型级 packed_range 优先，声明符
级按 Declarator 名对齐；无范围标量 = 1 bit；integer = 32 bit 固定）。

后续阶段（A2 求值 / A3 推断 / A4 WIDTH 规则 / B 参数化 / C 进阶）在此表
基础上推进。语言知识（Verilog 宽度语义）集中在本插件层，引擎零硬编码。

对标：Verilator WIDTH/WIDTHEXPAND/WIDTHTRUNC/SELRANGE 家族（references.md
「主流 lint 机制调研」核心集合第 3 类）。
"""

from core.define import Node

# 参与宽度分析的符号 kind（语言知识：Verilog 内部信号/端口）
_WIDTH_KINDS = {"wire", "reg", "integer", "port"}
# integer = 32 位有符号（IEEE 1364-2005 A.2.1.3；语言知识，插件层）
_INTEGER_WIDTH = "32"


def run_width_check(analyzer, context) -> None:
    """postpass 入口：A1 构建符号宽度表（后续阶段挂接点）。

    A1 阶段不产诊断（纯基础设施）——宽度表挂 analyzer 供后续阶段
    （求值器/推断器/规则）消费。
    """
    analyzer._width_table = symbol_width_table(analyzer)


def symbol_width_table(analyzer) -> dict[str, str]:
    """A1：符号宽度表 {符号名 → 宽度表达式文本}。

    无范围标量 → "1"（1 bit）；integer → "32"（固定位宽）。
    宽度文本保持原样（"7:0" / "WIDTH-1:0" / "3"），数值求值属 A2。
    """
    table: dict[str, str] = {}
    for sym in getattr(analyzer, "all_symbols", None) or []:
        if sym.kind not in _WIDTH_KINDS:
            continue
        w = extract_width(sym)
        table[sym.name] = w or "1"
    return table


def extract_width(sym) -> str:
    """从符号声明节点提取宽度文本。

    多声明符（wire a, b;）共享同一 decl_node——按符号名在 DeclaratorList
    中定位对应声明符的 packed_range（声明符级形态 `wire a [7:0]`）。
    """
    if sym.kind == "integer":
        return _INTEGER_WIDTH
    node = sym.decl_node
    if node is None:
        return ""
    # 类型级 packed_range（wire [7:0] a / input wire [7:0] a）
    pr = getattr(node, "packed_range", None)
    w = range_text(pr)
    if w:
        return w
    # 声明符级 packed_range（wire a [7:0]；多声明符按名对齐）
    items = getattr(node, "items", None)
    if isinstance(items, Node):
        for it in getattr(items, "items", None) or []:
            if not isinstance(it, Node):
                continue
            name = getattr(getattr(it, "name", None), "content", "")
            if name == sym.name:
                w2 = range_text(getattr(it, "packed_range", None))
                if w2:
                    return w2
    return ""


def range_text(range_node) -> str:
    """Range 节点 → 宽度文本（"7:0" / "3"）；非 Range/空 → ""。

    穿透 optional 包装：`@Range?` 绑定的 packed_range 是 optional 壳，
    Range 在 sub_node[0]（与 analyzer/checker.py 的 _unwrap 同款）。
    """
    range_node = _unwrap_optional(range_node)
    if not isinstance(range_node, Node):
        return ""
    msb = getattr(range_node, "msb", None)
    msb_t = node_text(msb) if isinstance(msb, Node) else ""
    if not msb_t:
        return ""
    lsb = getattr(range_node, "lsb", None)
    lsb_t = node_text(lsb) if isinstance(lsb, Node) else ""
    return f"{msb_t}:{lsb_t}" if lsb_t else msb_t


def _unwrap_optional(node):
    """穿透 parser 的 optional 包装节点（内容在 sub_node[0]）。"""
    while isinstance(node, Node) and node.node_name == "optional":
        sub = getattr(node, "sub_node", None) or []
        node = sub[0] if sub else None
    return node


def node_text(node) -> str:
    """Node → 源码文本（content 优先；token 节点文本在 value；合成二元
    节点 op 是 str 属性插 left/right 间；否则按子节点绑定序拼接）。

    iter_children 的 vars 遍历按 parser.node 绑定顺序（Python dict
    保序）——表达式树（BinaryOp left/right、Range msb/lsb 等）可可靠
    还原文本（宽度表达式原样保留，A2 求值）。
    """
    if not isinstance(node, Node):
        return str(node) if node else ""
    c = getattr(node, "content", None)
    if isinstance(c, str) and c:
        return c
    # token 节点（literal.number / symbol.* 等）：文本在 value 属性
    v = getattr(node, "value", None)
    if isinstance(v, str) and v:
        return v
    if isinstance(v, Node):
        t = node_text(v)
        if t:
            return t
    # 合成二元节点（pratt 表达式：op 是 str 属性，插 left/right 之间）
    op = getattr(node, "op", None)
    left = getattr(node, "left", None)
    right = getattr(node, "right", None)
    if isinstance(op, str) and isinstance(left, Node) and isinstance(right, Node):
        lt, rt = node_text(left), node_text(right)
        if lt and rt:
            return f"{lt}{op}{rt}"
    parts = []
    for child in node.iter_children():
        t = node_text(child)
        if t:
            parts.append(t)
    return "".join(parts)
