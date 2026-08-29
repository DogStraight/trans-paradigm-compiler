"""_unused_check.py — 未使用声明检查 postpass（unused_check 插件）

遍历后链式走查（ADR-0004 postpass 机制）：统计本文件 AST 中所有
`_symbol_ref` 引用（identifier_resolve 原语挂载），对声明了但从未被
引用的内部信号报未使用。

语言知识（哪些 kind 算"内部信号"）集中在此插件层，引擎零硬编码：
- wire/reg/integer/parameter/localparam：内部信号/常量，声明应被使用
- 端口（kind=port）是接口，不报；`_` 前缀符号豁免（显式"故意不用"）

对标：Veryl unused_variable（W）/ Verilator UNUSEDSIGNAL / slang
unused-* / HDL Checker Unused——tpc 用真符号表引用计数（遍历 AST 收集
_symbol_ref），避免 HDL Checker 词频式判定的误报。
"""

from core.define import Node

# 插件层语言知识：内部信号 kind（声明后应被引用）；其余 kind（port/
# module/function/task/...）不参与未使用判定。
# parameter/localparam 不查：参数未使用在模块接口场景常见（预留接口/
# 条件编译），误报率高（对标 Verilator UNUSEDPARAM 默认关闭）。
_INTERNAL_KINDS = {"wire", "reg", "integer"}


def run_unused_check(analyzer, context) -> None:
    """postpass 入口：收集引用 → 统计 → 报未使用声明。"""
    symbols = getattr(analyzer, "all_symbols", None) or []
    if not symbols:
        return
    root = getattr(analyzer, "_ast", None)
    # 声明节点自身的 Identifier 不视为"使用"（symbol_declare 与
    # identifier_resolve 都跑在声明节点上）。注意共享声明节点：
    # `wire a, b;` 的 a/b decl_node 是同一个 WireDecl，子树含所有声明符
    # Identifier——只排除"ref 指向同名符号"的节点，跨名 ref（共享节点
    # 里的其他符号）不排除。
    self_decl_ids = _collect_self_decl_ids(symbols)
    refs = _collect_symbol_refs(root, self_decl_ids)
    used: set[int] = set()
    for sym in refs:
        used.add(id(sym))
    for sym in symbols:
        if sym.kind not in _INTERNAL_KINDS:
            continue
        if not sym.name or sym.name.startswith("_"):
            continue
        if id(sym) in used:
            continue
        context.report(
            f"信号 '{sym.name}' 声明后从未被引用（未使用声明）",
            code="UN001",
            level="warning",
            node=sym.decl_node,
        )


def _collect_self_decl_ids(symbols: list) -> set[int]:
    """收集每个符号"声明标识符"节点 id（排除共享声明节点的跨名 ref）。

    `wire a, b;` 的 a/b decl_node 是同一 WireDecl，子树含两个声明符
    Identifier（ref 分别指向 a、b）。对每个符号遍历其 decl_node 子树，
    只把 ref 指向该符号自身的节点 id 记入排除集——共享节点里 a 的声明
    Identifier（ref→a）与 b 的（ref→b）天然区分，互不误排除。
    """
    ids: set[int] = set()
    for s in symbols:
        decl = s.decl_node
        if decl is None:
            continue
        stack = [decl]
        while stack:
            node = stack.pop()
            if not isinstance(node, Node):
                continue
            ref = getattr(node, "_symbol_ref", None)
            if ref is not None and ref is s:
                ids.add(id(node))
            for child in node.iter_children():
                stack.append(child)
    return ids


def _collect_symbol_refs(root, exclude_ids: set[int]) -> list:
    """DFS 收集 AST 的 _symbol_ref 引用（排除声明标识符节点）。"""
    refs: list = []
    if root is None:
        return refs
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, Node):
            if id(node) in exclude_ids:
                continue  # 声明标识符不算使用
            ref = getattr(node, "_symbol_ref", None)
            if ref is not None:
                refs.append(ref)
            for child in node.iter_children():
                stack.append(child)
    return refs
