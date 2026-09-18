"""_width_check.py — 位宽一致性检查 postpass（width_check 插件，P1.10 分期）

阶段 A1：符号宽度表——从 analyzer.all_symbols 提取每符号的宽度表达式
文本（wire/reg/integer/ANSI+body 端口；类型级 packed_range 优先，声明符
级按 Declarator 名对齐；无范围标量 = 1 bit；integer = 32 bit 固定）。

后续阶段（A2 求值 / A3 推断 / A4 WIDTH 规则 / B 参数化 / C 进阶）在此表
基础上推进。语言知识（Verilog 宽度语义）集中在本插件层，引擎零硬编码。

对标：Verilator WIDTH/WIDTHEXPAND/WIDTHTRUNC/SELRANGE 家族（references.md
「主流 lint 机制调研」核心集合第 3 类）。
"""

from typing import Any

from core.define import Node, iter_nodes, unwrap_optional

# 参与宽度分析的符号 kind（语言知识：Verilog 内部信号/端口）
_WIDTH_KINDS = {"wire", "reg", "integer", "port"}
# integer = 32 位有符号（IEEE 1364-2005 A.2.1.3；语言知识，插件层）
_INTEGER_WIDTH = "32"
# B4 走查目标模块 node 的声明节点形态（与 hier_check _DECL_RULES 同款）
_DECL_NODE_RULES = {"WireDecl", "RegDecl"}


def run_width_check(analyzer, context) -> None:
    """postpass 入口：A1 宽度表 + B1 参数表 + A4 赋值 + B3 端口连接宽度。"""
    table = symbol_width_table(analyzer)
    # B1 模块参数表：全工程两层结构 → 当前文件模块单层（本文件模块的
    # 宽度求值只用自己模块的参数；跨模块传播 B3）。内嵌 "_params" 键
    # 供 infer 查表（符号名不会与 "_params" 冲突——参数不在宽度表）。
    params_all = _module_params(context)
    params = _file_params(analyzer, params_all)
    analyzer._param_table = params
    # _params 是内部元数据键（参数表），非符号宽度——表值类型为 Any
    table["_params"] = params
    analyzer._width_table = table
    # _hier 解析器：跨模块成员宽度（a.b 中 a 是实例）——hier_check 插件
    # 服务（2026-08-29，references.md「层次引用解析机制调研」）；同语言
    # 包插件互引，引擎零语言知识
    try:
        from grammar.verilog.plugins.checks.hier_check import _hier_check as hier

        table["_hier"] = lambda n: hier.resolve_member_width(n, analyzer, context)
    except ImportError:
        table["_hier"] = None
    _check_assignment_widths(analyzer, context, table)
    _check_port_connections(analyzer, context, table, params_all)
    _check_inst_internal_widths(context, table, params_all)
    _check_select_ranges(analyzer, context, table)


# ── C1 SELRANGE：位选/下标越界（W202） ─────────────────────
# 位选/下标/切片索引超出符号宽度 → 越界报 W202（error——越界是硬错误，
# 仿真/综合行为未定义）。常量索引才可判（变量索引保守跳过）。
# 对标：Verilator SELRANGE / slang index-out-of-bounds。


def _check_select_ranges(analyzer, context, table: dict) -> None:
    root = getattr(analyzer, "_ast", None)
    if root is None:
        return
    for node, module in _iter_nodes_with_module(root):
        if node.node_name != "SelectExpr":
            continue
        base = getattr(node, "base", None)
        base_name = getattr(base, "content", "") if isinstance(base, Node) else ""
        bw = table_width_to_num_params(
            _lookup_width(table, module, base_name), table.get("_params")
        )
        if bw is None:
            continue  # base 宽度未知（跨模块/未声明/参数化未知）保守
        suffixes = [getattr(node, "first_suffix", None)]
        suffixes.extend(getattr(node, "extra_suffixes", None) or [])
        for sf in suffixes:
            if isinstance(sf, Node):
                _check_suffix_bounds(sf, bw, base_name, context)


def _check_suffix_bounds(sf, bw: int, base_name: str, context) -> None:
    idx = eval_const_expr(node_text(getattr(sf, "index", None)))
    info = _range_info(getattr(sf, "range_suffix", None))
    if info is None:
        # 纯索引 [idx]：idx ∈ [0, bw-1]
        if idx is not None and idx >= bw:
            context.report(
                f"位选越界：{base_name}[{idx}] 超出 {bw} 位范围",
                code="W202",
                level="error",
                node=sf,
            )
        return
    op, val_node = info
    op = node_text(op)
    val = eval_const_expr(node_text(val_node))
    if idx is None or val is None:
        return  # 变量索引/宽度保守
    if op == ":":
        if max(idx, val) >= bw:
            context.report(
                f"位选越界：{base_name}[{idx}:{val}] 超出 {bw} 位范围",
                code="W202",
                level="error",
                node=sf,
            )
    elif op in (":+", "+:", "-:"):
        if idx >= bw or idx + val > bw:
            context.report(
                f"切片越界：{base_name}[{idx}{op}{val}] 超出 {bw} 位范围",
                code="W202",
                level="error",
                node=sf,
            )


def _file_params(analyzer, module_params: dict) -> dict[str, str]:
    """当前文件各模块参数合并（单层；多模块同名参数取先——罕见，保守）。"""
    out: dict[str, str] = {}
    root = getattr(analyzer, "_ast", None)
    if root is None:
        return out
    for node in iter_nodes(root):
        if node.node_name != "ModuleDecl":
            continue
        mn = getattr(getattr(node, "module_name", None), "content", "")
        if mn and mn in module_params:
            out.update(module_params[mn])
    return out


# ── B1 模块参数表 ────────────────────────────────────────
# 参数化宽度（WIDTH-1:0）求值需要模块参数值。来源：模块定义 ParamDecl
# 默认值（module_index 的 ModuleParam.value_expr）。实例化覆盖
# （#(.P(v))）对模块内宽度的传播属 B3（跨模块视角）。


def _module_params(context) -> dict[str, dict[str, str]]:
    """{模块名: {参数名: 值表达式文本}}——全工程模块定义参数默认值。"""
    module_index = context.extra.get("module_index", {}) or {}
    out: dict[str, dict[str, str]] = {}
    for mname, info in module_index.items():
        params = getattr(info, "params", None) or {}
        out[mname] = {p.name: p.value_expr for p in params.values()}
    return out


# ── B2 参数化宽度求值（符号化常量求值） ───────────────────
# eval_expr_params：常量表达式 + 参数表 → 数值（标识符查参数表，值可含
# 嵌套参数链）。与 A2 eval_const_expr 的关系：纯数字域走 A2；含标识符
# 走本函数（递归下降，ident 查表递归求值）。


def eval_expr_params(
    text: str, params: dict[str, str], _seen: frozenset | None = None
) -> int | None:
    """常量表达式 + 参数表 → 数值。

    "8" → 8；"WIDTH-1"（WIDTH=8）→ 7；"DATA_W/2"（DATA_W=16）→ 8；
    "A+B"（A=2,B=3）→ 5；"W"（W="DATA_W/2", DATA_W=16）→ 8（链式）；
    含未知标识符/循环引用（WIDTH=WIDTH）→ None。
    """
    toks = _expr_tokenize(text)
    if toks is None:
        return None
    pos = 0

    def peek() -> tuple:
        return toks[pos] if pos < len(toks) else ("eof", "")

    def advance() -> tuple:
        nonlocal pos
        t = toks[pos]
        pos += 1
        return t

    def parse_expr():
        left = parse_term()
        if left is None:
            return None
        while peek()[0] in ("+", "-"):
            op = advance()[0]
            right = parse_term()
            if right is None:
                return None
            left = left + right if op == "+" else left - right
        return left

    def parse_term():
        left = parse_factor()
        if left is None:
            return None
        while peek()[0] in ("*", "/", "%"):
            op = advance()[0]
            right = parse_factor()
            if right is None:
                return None
            if op == "*":
                left = left * right
            elif op == "/":
                if right == 0:
                    return None
                left = left // right
            else:
                if right == 0:
                    return None
                left = left % right
        return left

    def parse_factor():
        t = peek()
        if t[0] == "-":
            advance()
            v = parse_factor()
            return -v if v is not None else None
        if t[0] == "+":
            advance()
            return parse_factor()
        if t[0] == "(":
            advance()
            v = parse_expr()
            if v is None or peek()[0] != ")":
                return None
            advance()
            return v
        if t[0] == "num":
            advance()
            return t[1]
        if t[0] == "ident":
            advance()
            v = params.get(t[1])
            if v is None:
                return None  # 未知标识符（非本模块参数/信号）
            if _seen is not None and t[1] in _seen:
                return None  # 循环引用（WIDTH=WIDTH）防递归死循环
            return eval_expr_params(
                v, params, frozenset(_seen or ()) | {t[1]}
            )  # 参数值递归求值（链式；环防护）
        return None

    v = parse_expr()
    if v is None or peek()[0] != "eof":
        return None
    return v


def eval_width_text_params(text: str, params: dict[str, str]) -> int | None:
    """宽度文本 + 参数表 → 数值（B2）。

    先纯常量（A2 eval_width_text）；含参数 → 符号化求值：
    "WIDTH-1:0"（WIDTH=8）→ 8；"3"（单表达式）→ 4；"" → 1。
    """
    v = eval_width_text(text)
    if v is not None:
        return v
    if ":" in text:
        msb_s, lsb_s = text.split(":", 1)
        msb = eval_expr_params(msb_s, params)
        lsb = eval_expr_params(lsb_s, params)
        if msb is None or lsb is None:
            return None
        return abs(msb - lsb) + 1
    v2 = eval_expr_params(text, params)
    if v2 is None:
        return None
    return v2 + 1  # 单表达式 [n] = n+1 位


def _expr_tokenize(text: str) -> list | None:
    """常量表达式 tokenize（数字/标识符/括号/四则/一元；未知字符 None）。"""
    toks: list = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit():
            j = i
            while j < n and text[j].isdigit():
                j += 1
            toks.append(("num", int(text[i:j])))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            toks.append(("ident", text[i:j]))
            i = j
            continue
        if ch in "+-*/%()":
            toks.append((ch, ch))
            i += 1
            continue
        return None
    toks.append(("eof", ""))
    return toks


# ── A4 WIDTH 赋值对比 ────────────────────────────────────
# assign/阻塞/非阻塞赋值的 LHS vs RHS 宽度：RHS>LHS 截断报 W201（warning）；
# RHS<LHS 扩展不报（Verilog 扩展是安全的，Verilator WIDTH 也只在截断报
# 严重问题）；unsized 常量按最小宽度参与（'0 自适应、'hFF→8、5→3）；
# 参数化/跨模块等真未知 → 保守不报。
# 对标：Verilator WIDTH / WIDTHEXPAND（仅截断）/ slang width-*。

_ASSIGN_RULES = {"AssignStmt", "BlockingAssign", "NonBlockingAssign"}


def _check_assignment_widths(analyzer, context, table: dict) -> None:
    root = getattr(analyzer, "_ast", None)
    if root is None:
        return
    for node, module in _iter_nodes_with_module(root):
        if node.node_name not in _ASSIGN_RULES:
            continue
        _check_one(node, context, table, module)
        if node.node_name == "AssignStmt":
            # 多目标连续赋值：assign a = x, b = y;
            for ex in getattr(node, "extras", None) or []:
                if isinstance(ex, Node):
                    _check_one(ex, context, table, module)


def _check_one(node, context, table: dict, module: str = "") -> None:
    lw = infer_expr_width(getattr(node, "target", None), table, module)
    rw = infer_expr_width(getattr(node, "value", None), table, module)
    if lw is None or rw is None:
        return  # 任一侧未知 → 保守不报（sized 域）
    if rw > lw:
        # 自引用位选（a[x:y] = a / a[x:y] = a + ... 且主信号同基）：
        # 截断的是自身位（显式部分赋值语义），无害——不报
        # （2026-08-29 修复：picorv32 active[3:1] = active 误报）。
        if _self_select_assign(node):
            return
        lhs_t = node_text(getattr(node, "target", None))
        rhs_t = node_text(getattr(node, "value", None))
        context.report(
            f"赋值宽度截断：RHS {rw} 位 → LHS {lw} 位"
            f"（{lhs_t} = {rhs_t}）",
            code="W201",
            level="warning",
            node=node,
        )


def _self_select_assign(node) -> bool:
    """LHS 是位选且与 RHS 主信号同基（a[x:y] = a…）→ 截断无害。

    RHS 取主信号（Identifier/HierExpr 单段）文本，与 LHS SelectExpr 的
    base 比较；相同 → True。
    """
    lhs = getattr(node, "target", None)
    rhs = getattr(node, "value", None)
    if not isinstance(lhs, Node) or lhs.node_name != "SelectExpr":
        return False
    base = getattr(lhs, "base", None)
    base_name = getattr(base, "content", "") if isinstance(base, Node) else ""
    if not base_name:
        return False
    if isinstance(rhs, Node) and rhs.node_name == "Identifier":
        return getattr(rhs, "content", "") == base_name
    if isinstance(rhs, Node) and rhs.node_name == "HierExpr":
        parts = getattr(rhs, "parts", None) or []
        if parts and isinstance(parts[0], Node):
            return getattr(parts[0], "content", "") == base_name
    return False


_MODULE_DECL_RULES = ("ModuleDecl", "MacroModuleDecl")


def _iter_nodes_with_module(root: Node):
    """DFS 迭代 (node, 模块名)——ModuleDecl 子树内节点带其模块名。

    多模块文件内符号查表需要模块上下文（跨模块同名符号污染修复，
    2026-08-29 对标测试暴露）。非模块内/未知模块 → ""。
    """
    stack = [(root, "")]
    while stack:
        node, mod = stack.pop()
        if node.node_name in _MODULE_DECL_RULES:
            mn = getattr(node, "module_name", None)
            mod = getattr(mn, "content", "") if isinstance(mn, Node) else ""
        yield node, mod
        for child in node.iter_children():
            stack.append((child, mod))


# ── B3 跨模块参数传播：实例化点端口连接宽度 ──────────────────
# 被实例化模块的端口宽度可能含参数（[WIDTH-1:0]）——求值用**覆盖后**
# 参数表：本文件参数（调用者上下文，覆盖值可能引用）→ 模块默认 →
# 实例化点覆盖（最高优先）。连接表达式宽度（本文件信号/字面量/拼接）
# vs 端口宽度：连接 > 端口 → 截断报 W201（对标 Verilator WIDTH 端口
# 连接同码）。


def _check_port_connections(analyzer, context, table: dict, params_all: dict) -> None:
    module_index = context.extra.get("module_index", {}) or {}
    inst_sites = context.extra.get("inst_sites", []) or []
    caller_params = table.get("_params", {}) or {}
    # 实例化点 → 所属模块（连接表达式是本模块信号，查表要带模块上下文
    # 防跨模块同名污染；2026-08-29 对标测试暴露）
    site_module: dict[int, str] = {}
    root = getattr(analyzer, "_ast", None)
    if root is not None:
        for node, module in _iter_nodes_with_module(root):
            site_module[id(node)] = module
    for site in inst_sites:
        mod_name = node_text(getattr(site, "module_name", None))
        if not mod_name:
            continue
        info = module_index.get(mod_name)
        if info is None:
            continue
        caller_mod = site_module.get(id(site), "")
        ov_params = _override_params(site, params_all.get(mod_name, {}), caller_params)
        nl = unwrap_optional(getattr(site, "ports", None))
        if nl is None:
            continue
        if nl.node_name == "OrderedPortList":
            # 位置连接：第 i 个连接表达式 ↔ 模块第 i 个端口（声明序），
            # 覆盖参数走 B3 三层合并（2026-08-29 补齐——tv80/旧风格实例）
            ordered_ports = list(info.ports.values())
            for i, val in enumerate(getattr(nl, "items", None) or []):
                if i >= len(ordered_ports):
                    break
                if not isinstance(val, Node):
                    continue
                _check_conn_width(context, mod_name, ordered_ports[i], val,
                                  table, ov_params, caller_mod)
            continue
        conns = getattr(nl, "items", None) if nl else None
        for conn in conns or []:
            if not isinstance(conn, Node) or conn.node_name != "NamedPortConnect":
                continue
            pn = node_text(getattr(conn, "port_name", None))
            if not pn:
                continue
            port = info.ports.get(pn)
            if port is None:
                continue
            _check_conn_width(context, mod_name, port,
                              getattr(conn, "value", None), table, ov_params,
                              caller_mod)


def _check_conn_width(context, mod_name: str, port, val, table: dict,
                      ov_params: dict, caller_mod: str = "") -> None:
    """单条端口连接宽度对比：连接 > 端口 → 截断报 W201。"""
    pw = (
        eval_width_text_params(port.width_expr, ov_params)
        if getattr(port, "width_expr", None)
        else 1
    )
    cw = infer_expr_width(val, table, caller_mod)
    if pw is None or cw is None:
        return
    if cw > pw:
        context.report(
            f"端口连接宽度截断：{mod_name}.{port.name} {pw} 位 ← 连接 {cw} 位"
            f"（{node_text(val)}）",
            code="W201",
            level="warning",
            node=val,
        )


def _override_params(site, module_defaults: dict, caller_params: dict) -> dict:
    """实例化点覆盖后参数表：调用者参数 → 模块默认 → site 覆盖（最高）。"""
    out = dict(caller_params)
    out.update(module_defaults or {})
    po = getattr(site, "params", None)
    pl = getattr(po, "params", None) if isinstance(po, Node) else None
    items = getattr(pl, "items", None) if isinstance(pl, Node) else None
    for item in items or []:
        if not isinstance(item, Node) or item.node_name != "NamedParamOverride":
            continue
        pn = node_text(getattr(item, "param_name", None))
        pv = node_text(getattr(item, "value", None))
        if pn and pv:
            out[pn] = pv
    return out


# ── B4 实例化覆盖 → 目标模块内部赋值重算（2026-08-31 补） ──────
# B3 只查"端口连接宽度"（外层表达式 vs 端口宽度），**不回传被实例化
# 模块内部**的赋值——用户场景：模块 A 内 `reg [3:0] y; wire [W-1:0] x;
# assign y = x;` 默认 W=4 不截断，外层 `A #(.W(16))` 覆盖后 16→4 截断，
# 模块定义处检查（用默认参数）漏检。Verilator 靠 elaboration 每实例化
# 点独立展开能报（WIDTHTRUNC In instance 'B.u_a'）。
#
# 本步：对有**有效覆盖**（覆盖值 ≠ 模块默认值）的实例化点，用覆盖后
# 参数表重算目标模块内部赋值截断。符号宽度表从 ModuleInfo.node 走查
# （跨文件目标模块无 analyzer 符号表）；不设 _hier 回调——跨文件层次
# 引用宽度求值留给 hier 插件，此处保守 None 防误判。
# 仅当目标模块内部存在**参数化宽度**（含字母的宽度表达式）才重算——
# 固定宽度模块覆盖参数不影响内部赋值，跳过省遍历（单元库空壳模块）。


def _check_inst_internal_widths(context, table: dict, params_all: dict) -> None:
    """B4：实例化点覆盖参数 → 目标模块内部赋值截断重算（W201）。"""
    module_index = context.extra.get("module_index", {}) or {}
    inst_sites = context.extra.get("inst_sites", []) or []
    caller_params = table.get("_params", {}) or {}
    for site in inst_sites:
        mod_name = node_text(getattr(site, "module_name", None))
        if not mod_name:
            continue
        info = module_index.get(mod_name)
        if info is None or getattr(info, "node", None) is None:
            continue
        defaults = params_all.get(mod_name, {})
        if not _override_changes_params(site, defaults):
            continue  # 无覆盖或覆盖值 == 默认 → 模块定义处检查已覆盖，跳过
        ov_params = _override_params(site, defaults, caller_params)
        _recheck_module_assigns(info, site, ov_params, context)


def _override_changes_params(site, defaults: dict) -> bool:
    """site 是否有参数覆盖且覆盖值 ≠ 模块默认值（有效覆盖判据）。"""
    po = getattr(site, "params", None)
    pl = getattr(po, "params", None) if isinstance(po, Node) else None
    items = getattr(pl, "items", None) if isinstance(pl, Node) else None
    for item in items or []:
        if not isinstance(item, Node) or item.node_name != "NamedParamOverride":
            continue
        pn = node_text(getattr(item, "param_name", None))
        pv = node_text(getattr(item, "value", None))
        if pn and pv and pv != defaults.get(pn):
            return True
    return False


def _module_width_table(info) -> dict:
    """目标模块符号宽度表（从 ModuleInfo.node 走查，B4 用）。

    端口宽度取 checker 已提取的 width_expr（ANSI + body 端口已合并）；
    内部声明走查 WireDecl/RegDecl/IntegerDecl（类型级 packed_range 优先、
    声明符级按名对齐——与 A1 extract_width 同判据）；数组符号集随表。
    返回表只含符号宽度文本 + "_arrays"，_params 由调用方按覆盖表设置。
    """
    table: dict[str, Any] = {}
    arrays: set[str] = set()
    for pname, port in (getattr(info, "ports", None) or {}).items():
        table[pname] = getattr(port, "width_expr", None) or ""
    node = getattr(info, "node", None)
    if node is None:
        table["_arrays"] = arrays
        return table
    for n in iter_nodes(node):
        if n.node_name == "IntegerDecl":
            for it in _declarator_names(n):
                table[it] = _INTEGER_WIDTH
            continue
        if n.node_name not in _DECL_NODE_RULES:
            continue
        type_w = range_text(getattr(n, "packed_range", None))
        items = getattr(n, "items", None)
        if not isinstance(items, Node):
            continue
        for it in getattr(items, "items", None) or []:
            if not isinstance(it, Node):
                continue
            nm = getattr(getattr(it, "name", None), "content", "")
            if not nm:
                continue
            w2 = range_text(getattr(it, "packed_range", None))
            table[nm] = w2 or type_w or ""
            if _declarator_is_array(it):
                arrays.add(nm)
    table["_arrays"] = arrays
    return table


def _declarator_names(decl_node: Node) -> list[str]:
    """声明节点 items → 声明符名列表。"""
    items = getattr(decl_node, "items", None)
    if not isinstance(items, Node):
        return []
    return [
        getattr(getattr(it, "name", None), "content", "")
        for it in getattr(items, "items", None) or []
        if isinstance(it, Node) and getattr(getattr(it, "name", None), "content", "")
    ]


def _declarator_is_array(declarator: Node) -> bool:
    """声明符是否含 array_range（存储器/数组）。"""
    return isinstance(getattr(declarator, "array_range", None), Node)


def _recheck_module_assigns(info, site, ov_params: dict, context) -> None:
    """目标模块内部赋值用覆盖参数表重算截断（B4 核心）。"""
    node = getattr(info, "node", None)
    if node is None:
        return
    sub_table = _module_width_table(info)
    # 无参数化宽度（全部固定宽度）→ 覆盖参数不影响内部赋值，跳过
    if not any(_is_parameterized_text(t) for t in sub_table.values()):
        return
    sub_table["_params"] = ov_params
    for n in iter_nodes(node):
        if n.node_name not in _ASSIGN_RULES:
            continue
        _recheck_one(n, info, site, sub_table, context)
        if n.node_name == "AssignStmt":
            for ex in getattr(n, "extras", None) or []:
                if isinstance(ex, Node):
                    _recheck_one(ex, info, site, sub_table, context)


def _is_parameterized_text(text: str) -> bool:
    """宽度文本含字母 → 参数化（非纯数字/范围形态）。"""
    return any(ch.isalpha() for ch in text)


def _recheck_one(node, info, site, sub_table: dict, context) -> None:
    """单条内部赋值重算：RHS > LHS → 报 W201（主 node = 实例化点）。"""
    lw = infer_expr_width(getattr(node, "target", None), sub_table, info.name)
    rw = infer_expr_width(getattr(node, "value", None), sub_table, info.name)
    if lw is None or rw is None:
        return  # 任一侧未知 → 保守不报（与 A4 同策略）
    if rw <= lw:
        return
    if _self_select_assign(node):
        return
    lhs_t = node_text(getattr(node, "target", None))
    rhs_t = node_text(getattr(node, "value", None))
    node._file = info.file  # related 跨文件定位（checker 同款）
    context.report(
        f"实例化 '{info.name}'（参数覆盖后）模块内赋值宽度截断："
        f"RHS {rw} 位 → LHS {lw} 位（{lhs_t} = {rhs_t}）",
        code="W201",
        level="warning",
        node=site,
        related=[("模块内赋值处", node)],
    )


def symbol_width_table(analyzer) -> dict[str, Any]:
    """A1：符号宽度表 {符号名 → 宽度表达式文本}。

    原始文本原样保留：""（无范围标量）/ "7:0" / "WIDTH-1:0" / "32"。
    数值转换用 table_width_to_num（A3 消费；空 = 标量 1 bit——与
    eval_width_text 的 "1"→2（单表达式 [1]）语义区分开）。
    内嵌 "_arrays" 键：数组符号集（Declarator.array_range 非空——存储器
    word 选择宽度 = word 宽，非位选 1；2026-08-29 修复 ice40 误报）。

    多模块隔离（2026-08-29 对标测试暴露）：同名符号跨模块宽度不同时，
    平面键被后声明者覆盖（SB_MAC16 的 [15:0] D 污染 20 个 SB_DFF 的
    标量 D，20 条 W201 全 FP——Verilator 对这些 0 报）。加模块限定键
    (scope.name, sym_name)；查表走 _lookup_width 优先限定键，平面键
    仅作无模块上下文（测试直接构造表）的回退。
    """
    table: dict[str, Any] = {}
    arrays: set[str] = set()
    arrays_by_module: dict[str, set] = {}
    for sym in getattr(analyzer, "all_symbols", None) or []:
        if sym.kind not in _WIDTH_KINDS:
            continue
        table[sym.name] = extract_width(sym)
        if _is_array_symbol(sym):
            arrays.add(sym.name)
        # 模块限定键：符号所属模块作用域（端口/声明都在模块 scope 下）
        mod = ""
        if sym.scope is not None and sym.scope.kind == "module":
            mod = sym.scope.name or ""
        table[(mod, sym.name)] = extract_width(sym)  # type: ignore[index]
        if _is_array_symbol(sym):
            arrays_by_module.setdefault(mod, set()).add(sym.name)
    table["_arrays"] = arrays
    table["_arrays_by_module"] = arrays_by_module
    return table


def _lookup_width(table: dict, module: str, name: str):
    """查宽度表：模块限定键优先，平面键回退（无模块上下文/测试表）。

    多模块文件内查符号宽度必须带模块名——否则同名符号跨模块污染
    （对标测试 2026-08-29：SB_MAC16 D 污染 SB_DFF D）。
    """
    if module:
        v = table.get((module, name))
        if v is not None:
            return v
    return table.get(name)


def _lookup_arrays(table: dict, module: str) -> set:
    """数组符号集查表：模块限定集优先，平面集回退。"""
    if module:
        s = table.get("_arrays_by_module")
        if isinstance(s, dict) and module in s:
            return s[module]  # type: ignore[return-value]
    return table.get("_arrays") or set()


def _is_array_symbol(sym) -> bool:
    """符号是否为数组（存储器）：Declarator.array_range 非空。"""
    node = sym.decl_node
    items = getattr(node, "items", None)
    if not isinstance(items, Node):
        return False
    for it in getattr(items, "items", None) or []:
        if not isinstance(it, Node):
            continue
        if getattr(getattr(it, "name", None), "content", "") != sym.name:
            continue
        ar = getattr(it, "array_range", None)
        return isinstance(ar, Node) and bool(getattr(ar, "items", None))
    return False


def table_width_to_num(text: str | None) -> int | None:
    """A1 宽度表文本 → 数值（空 = 标量 1 bit；None = 查不到 → None 保守）。

    区分：表值 ""（标量 1 bit）与查表 None（符号未知——不推断，防误报）
    与 eval_width_text 的 "1"→2（单表达式 [1]）语义。
    """
    if text is None:
        return None
    if text == "":
        return 1
    return eval_width_text(text)


def table_width_to_num_params(text: str | None, params: dict | None) -> int | None:
    """B2：宽度表文本 + 参数表 → 数值（参数化宽度求值版）。"""
    if text is None:
        return None
    if text == "":
        return 1
    return eval_width_text_params(text, params or {})


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
    range_node = unwrap_optional(range_node)
    if not isinstance(range_node, Node):
        return ""
    msb = getattr(range_node, "msb", None)
    msb_t = node_text(msb) if isinstance(msb, Node) else ""
    if not msb_t:
        return ""
    lsb = getattr(range_node, "lsb", None)
    lsb_t = node_text(lsb) if isinstance(lsb, Node) else ""
    return f"{msb_t}:{lsb_t}" if lsb_t else msb_t


def node_text(node) -> str:
    """Node → 源码文本（通用文本化：content 优先；token 节点文本在 value；
    合成/结构节点按类型补结构字符——拼接 {}、复制 {{n{}}、位选 []、
    一元 op 前缀、三目 ?:、调用 $f(args)、二元 op 紧凑插入）。

    iter_children 的 vars 遍历按 parser.node 绑定顺序（Python dict
    保序）——未显式处理的节点按子节点绑定序拼接。A4 诊断消息复用。
    """
    if not isinstance(node, Node):
        return str(node) if node else ""
    c = getattr(node, "content", None)
    if isinstance(c, str) and c:
        return c
    name = node.node_name
    if name == "ConcatExpr":
        parts = [node_text(ch) for ch in getattr(node, "sub_node", None) or []]
        return "{" + ",".join(p for p in parts if p) + "}"
    if name == "ReplicateExpr":
        cnt = node_text(getattr(node, "count", None))
        val = node_text(getattr(node, "value", None))
        return f"{{{cnt}{{{val}}}}}" if cnt and val else ""
    if name == "UnaryOp":
        op = getattr(node, "op", "") or ""
        return f"{op}{node_text(getattr(node, 'operand', None))}"
    if name == "BinaryOp":
        op = getattr(node, "op", "") or ""
        lt = node_text(getattr(node, "left", None))
        rt = node_text(getattr(node, "right", None))
        return f"{lt}{op}{rt}" if lt and rt else ""
    if name == "TernaryOp":
        cd = node_text(getattr(node, "cond", None))
        tv = node_text(getattr(node, "true_val", None))
        fv = node_text(getattr(node, "false_val", None))
        return f"{cd}?{tv}:{fv}" if cd and tv and fv else ""
    if name == "SelectExpr":
        base = node_text(getattr(node, "base", None))
        suf = _suffix_text(getattr(node, "first_suffix", None))
        extra = "".join(
            _suffix_text(s)
            for s in getattr(node, "extra_suffixes", None) or []
        )
        return f"{base}[{suf}]{extra}" if base and suf else ""
    if name == "HierExpr":
        parts = [node_text(p) for p in getattr(node, "parts", None) or []]
        return "".join(p for p in parts if p)
    if name == "SysFuncCall":
        callee = node_text(getattr(node, "callee", None))
        args = _args_text(node)
        return f"${callee}({args})"
    if name == "CallExpr":
        callee = node_text(getattr(node, "callee", None))
        args = _args_text(node)
        return f"{callee}({args})"
    # token 节点（literal.number / symbol.* 等）：文本在 value 属性
    # （放在显式分派之后——业务属性 value（如 ReplicateExpr.value）不能被误当）
    v = getattr(node, "value", None)
    if isinstance(v, str) and v:
        return v
    if isinstance(v, Node):
        t = node_text(v)
        if t:
            return t
    parts = []
    for child in node.iter_children():
        t = node_text(child)
        if t:
            parts.append(t)
    return "".join(parts)


def _suffix_text(suffix) -> str:
    """SelectSuffix → 内部文本（index / index:msb / index+:w，不含 []）。"""
    if not isinstance(suffix, Node):
        return ""
    idx = node_text(getattr(suffix, "index", None))
    info = _range_info(getattr(suffix, "range_suffix", None))
    if info is not None:
        op, val_node = info
        return f"{idx}{node_text(op)}{node_text(val_node)}"
    return idx


def _args_text(node) -> str:
    """ArgumentList → "a, b" 文本。"""
    args = getattr(node, "args", None)
    if not isinstance(args, Node):
        return ""
    items = getattr(args, "items", None) or []
    parts = [node_text(it) for it in items if isinstance(it, Node)]
    return ",".join(p for p in parts if p)


# ── A2 常量宽度求值器 ────────────────────────────────────
# 宽度表达式文本 → 数值（纯函数）。常量域：纯数字表达式可求值；
# 含标识符（参数名等）→ None（参数化留 B 阶段）。手写递归下降求值
# （不用 eval——源码文本求值有 RCE 风险）。


def eval_width_text(text: str) -> int | None:
    """A2：宽度表达式文本 → 数值。

    "7:0" → 8（abs(msb-lsb)+1）、"0:7" → 8、"3" → 4（单表达式惯例
    [n:0]）、"" → 1（标量）；含参数/未知 → None（B 阶段参数化求值）。
    """
    text = (text or "").strip()
    if not text:
        return 1
    if ":" in text:
        msb_s, lsb_s = text.split(":", 1)
        msb = eval_const_expr(msb_s)
        lsb = eval_const_expr(lsb_s)
        if msb is None or lsb is None:
            return None
        return abs(msb - lsb) + 1
    v = eval_const_expr(text)
    if v is None:
        return None
    return v + 1  # 单表达式 [n] = n+1 位（惯例 [n:0]）


def eval_const_expr(text: str) -> int | None:
    """A2：常量表达式求值（数字 + 括号 + 一元 +/- + 四则 * / %）。

    纯数字域 → 数值；含标识符/未知字符 → None（参数化留 B 阶段）。
    递归下降：expr → term(+-) → factor(* / %) → 一元/括号/数字。
    """
    toks = _const_tokenize(text)
    if toks is None:
        return None
    pos = 0

    def peek() -> tuple:
        return toks[pos] if pos < len(toks) else ("eof", "")

    def advance() -> tuple:
        nonlocal pos
        t = toks[pos]
        pos += 1
        return t

    def parse_expr():
        left = parse_term()
        if left is None:
            return None
        while peek()[0] in ("+", "-"):
            op = advance()[0]
            right = parse_term()
            if right is None:
                return None
            left = left + right if op == "+" else left - right
        return left

    def parse_term():
        left = parse_factor()
        if left is None:
            return None
        while peek()[0] in ("*", "/", "%"):
            op = advance()[0]
            right = parse_factor()
            if right is None:
                return None
            if op == "*":
                left = left * right
            elif op == "/":
                if right == 0:
                    return None
                left = left // right
            else:
                if right == 0:
                    return None
                left = left % right
        return left

    def parse_factor():
        t = peek()
        if t[0] == "-":
            advance()
            v = parse_factor()
            return -v if v is not None else None
        if t[0] == "+":
            advance()
            return parse_factor()
        if t[0] == "(":
            advance()
            v = parse_expr()
            if v is None or peek()[0] != ")":
                return None
            advance()
            return v
        if t[0] == "num":
            advance()
            return t[1]
        return None

    v = parse_expr()
    if v is None or peek()[0] != "eof":
        return None
    return v


def _const_tokenize(text: str) -> list | None:
    """数字表达式 tokenize：数字/括号/四则/一元；标识符或未知 → None。"""
    toks: list = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit():
            j = i
            while j < n and text[j].isdigit():
                j += 1
            toks.append(("num", int(text[i:j])))
            i = j
            continue
        if ch in "+-*/%()":
            toks.append((ch, ch))
            i += 1
            continue
        return None  # 标识符/未知字符 → 常量域外（参数化）
    toks.append(("eof", ""))
    return toks


def literal_width(text: str) -> int | None:
    """A2：字面量文本 → 位宽（"8'd5" → 8、"4'b1010" → 4）。

    unsized 常量按**最小宽度**追踪（Verilator WIDTH 同思路：够容纳则不报、
    容纳不下报截断；对标 references.md「三主题实现机制调研」位宽一节）：
      - '0/'1/'x/'z 填充常量 → 0（自适应上下文宽度，永不截断）
      - 数值 0（"0"/'d0/'h0）→ 0（任何宽度都容纳）
      - 其余 unsized（"'hFF"→8、"5"→3、"255"→8）→ 容纳该值所需最小位数
    含 x/z 位（"'hFFx"）或未知形态 → None（保守不推断，避免误报）。
    """
    t = (text or "").strip()
    if not t:
        return None
    if "'" not in t:
        # unsized 十进制整数：最小位宽 = 容纳值所需位数（0 → 0 自适应）
        digits = t.replace("_", "")
        if digits.startswith("-"):
            digits = digits[1:]
        if not digits.isdigit():
            return None
        v = int(digits, 10)
        return _min_bits(v)
    w = t.split("'", 1)[0].strip()
    if w.isdigit():
        return int(w)  # sized："8'd5" → 8
    # unsized 带基数常量（'hFF / 'b101 / 'd5 / '0 / 'shFF…）
    body = t.split("'", 1)[1]
    if not body:
        return None
    if body[0] in "sS":
        body = body[1:]  # signed 前缀（'shFF）——最小位宽同无符号
    if not body:
        return None
    if len(body) == 1 and body in "01xXzZ":
        return 0  # 填充常量：'0/'1/'x/'z 自适应上下文
    base_ch = body[0].lower()
    if base_ch not in "bohd":
        return None  # 未知形态
    digits = body[1:].replace("_", "")
    if not digits:
        return None
    if any(c in "xXzZ" for c in digits):
        return None  # 含未知位 → 保守（宽度无法精确）
    try:
        v = int(digits, {"b": 2, "o": 8, "h": 16, "d": 10}[base_ch])
    except ValueError:
        return None
    return _min_bits(v)


def _min_bits(v: int) -> int:
    """非负整数 → 容纳所需最小位数（0 → 0：任意宽度都容纳）。"""
    if v <= 0:
        return 0
    return v.bit_length()


# ── A3 表达式宽度推断 ────────────────────────────────────
# 遍历表达式 AST 节点 → 宽度（Verilog 宽度语义，IEEE 1364-2005 5.5 节，
# 插件层语言知识）。原子查符号宽度表（A1）+ 字面量（A2）；结构节点
# （拼接/复制/位选/层次）与运算合成节点（UnaryOp/BinaryOp/TernaryOp）
# 递归推断。未知/跨模块/函数返回宽度 → 保守 None（不误报）。

# 二元运算按结果宽度分派（语言知识）
_ARITH_OPS = {"+", "-", "*", "/", "%"}
_CMP_OPS = {"==", "!=", "===", "!==", "<", "<=", ">", ">="}
_SHIFT_OPS = {"<<", ">>"}
_BIT_OPS = {"&", "|", "^", "~&", "~|", "~^", "^~"}
_LOGIC_OPS = {"&&", "||"}
# 一元归约（结果 1 bit）vs 一元保持（! ~ 同宽）
_REDUCTION_OPS = {"&", "|", "^", "~&", "~|", "~^", "^~"}


def infer_expr_width(node, width_table: dict, module: str = "") -> int | None:
    """A3：表达式节点 → 宽度（纯函数；未知 → None 保守）。

    原子：Identifier（查宽度表）/ Number|BitWidthLiteral（字面量位宽）
    / StringLiteral（保守 None）
    结构：ParenthesizedExpr（内层）/ SelectExpr（位选：索引 1、范围
    abs+1、+:/-: 切片宽度——最内层 suffix 决定）/ ConcatExpr（和）/
    ReplicateExpr（count×宽）/ HierExpr（末段下标 1，纯成员链查末段名）
    运算：UnaryOp（归约 → 1，! ~ → 同宽）/ BinaryOp（算术 max、比较 1、
    移位 LHS、位运算 max、逻辑 1）/ TernaryOp（max 分支）
    调用：$signed/$unsigned（同参数宽）；其他/用户函数 → None

    module：当前模块名（多模块文件内符号查表用限定键，防跨模块同名
    污染——2026-08-29 对标测试暴露 SB_MAC16 D 污染 SB_DFF D）。
    """
    if not isinstance(node, Node):
        return None
    name = node.node_name

    if name == "Identifier":
        return table_width_to_num_params(
            _lookup_width(width_table, module, getattr(node, "content", "") or ""),
            width_table.get("_params"),
        )
    if name in ("Number", "BitWidthLiteral"):
        return literal_width(node_text(node))
    if name == "StringLiteral":
        return None  # 字符串宽度语义罕见，保守
    if name == "ParenthesizedExpr":
        return infer_expr_width(getattr(node, "expr", None), width_table, module)
    if name == "SelectExpr":
        return _select_width(node, width_table, module)
    if name == "ConcatExpr":
        return _sum_width(getattr(node, "sub_node", None) or [], width_table, module)
    if name == "ReplicateExpr":
        count = eval_const_expr(node_text(getattr(node, "count", None)))
        vw = infer_expr_width(getattr(node, "value", None), width_table, module)
        if count is None or vw is None:
            return None
        return count * vw
    if name == "HierExpr":
        return _hier_width(node, width_table, module)
    if name == "UnaryOp":
        op = getattr(node, "op", "")
        if op in _REDUCTION_OPS:
            return 1  # 一元归约 → 1 bit
        if op == "!":
            return 1  # 逻辑非 → 1 bit（IEEE 1364-2005 5.5.2 逻辑运算；
            # 2026-08-29 对拍 Verilator：!x 结果 1 位，此前按操作数宽误报）
        return infer_expr_width(getattr(node, "operand", None), width_table, module)
    if name == "BinaryOp":
        return _binary_width(node, width_table, module)
    if name == "TernaryOp":
        tw = infer_expr_width(getattr(node, "true_val", None), width_table, module)
        fw = infer_expr_width(getattr(node, "false_val", None), width_table, module)
        if tw is None or fw is None:
            return None
        return max(tw, fw)
    if name == "SysFuncCall":
        callee = node_text(getattr(node, "callee", None))
        if callee in ("signed", "unsigned"):
            # 单参数系统函数：宽度不变（仅改符号性）
            return _first_arg_width(node, width_table, module)
        return None
    if name == "CallExpr":
        return None  # 用户函数返回宽度需函数表（C 阶段）
    return None


def _binary_width(node, width_table: dict, module: str = "") -> int | None:
    """BinaryOp 宽度（按 op 分派）。"""
    op = getattr(node, "op", "") or ""
    left = infer_expr_width(getattr(node, "left", None), width_table, module)
    right = infer_expr_width(getattr(node, "right", None), width_table, module)
    if op in _CMP_OPS or op in _LOGIC_OPS:
        return 1
    if op in _SHIFT_OPS:
        return left  # 移位结果宽 = LHS 宽
    if left is None or right is None:
        return None
    if op in _ARITH_OPS or op in _BIT_OPS:
        return max(left, right)
    return None


def _select_width(node, width_table: dict, module: str = "") -> int | None:
    """SelectExpr：链式后缀最内层决定宽度。

    范围/切片 → _suffix_width；纯索引 → 数组（存储器）word 选择返回
    word 宽（查表），向量位选 1 bit（base 宽度不参与越界判定属 C1）。
    """
    suffixes = [getattr(node, "first_suffix", None)]
    suffixes.extend(getattr(node, "extra_suffixes", None) or [])
    suffixes = [s for s in suffixes if isinstance(s, Node)]
    if not suffixes:
        return None
    last = suffixes[-1]
    rs = getattr(last, "range_suffix", None)
    if _range_info(rs) is None:
        # 纯索引：数组 word 选择（宽 = word 宽）vs 向量位选（1 bit）
        base = getattr(node, "base", None)
        bn = getattr(base, "content", "") if isinstance(base, Node) else ""
        arrays = _lookup_arrays(width_table, module)
        if bn in arrays:
            return table_width_to_num_params(
                _lookup_width(width_table, module, bn),
                width_table.get("_params"),
            )
        return 1
    return _suffix_width(last)


def _suffix_width(suffix) -> int | None:
    """SelectSuffix → 宽度：纯索引 1；range_suffix 按运算符分派。"""
    info = _range_info(getattr(suffix, "range_suffix", None))
    if info is None:
        return 1  # 纯索引 → 1 bit
    op, val_node = info
    op = node_text(op)  # ":" / "+:" / "-:"
    val = eval_const_expr(node_text(val_node))
    if op == ":":
        idx = eval_const_expr(node_text(getattr(suffix, "index", None)))
        if idx is None or val is None:
            return None
        return abs(idx - val) + 1
    if op in (":+", "+:", "-:"):
        # 切片 a[base +: width] / a[base -: width]：宽度 = width
        return val
    return 1


def _range_info(rs):
    """range_suffix → (op, value_node)｜None（兼容 list 与 seq 两形态）。

    SelectSuffix 的 $2 组合捕获实测为 list（[':', Number]）；部分形态为
    seq 节点（sub_node）。op 元素可能是 str（token 文本）或 Node。
    """
    if isinstance(rs, list) and len(rs) >= 2:
        return rs[0], rs[1]
    if isinstance(rs, Node) and getattr(rs, "sub_node", None):
        sub = list(getattr(rs, "sub_node", None) or [])
        if len(sub) >= 2:
            return sub[0], sub[1]
    return None


def _sum_width(items: list, width_table: dict, module: str = "") -> int | None:
    """拼接元素宽度和（任一 None → None）。"""
    total = 0
    for it in items:
        w = infer_expr_width(it, width_table, module)
        if w is None:
            return None
        total += w
    return total


def _hier_width(node, width_table: dict, module: str = "") -> int | None:
    """HierExpr（a / a.b / a[0].b）：单段查表；末段带下标 → 1；
    纯成员链查末段名（本地表）；查不到且为多段链 → 回调 hier 插件做
    跨模块成员宽度解析（2026-08-29 补齐——a.b 中 a 是实例时按需解析）。
    """
    parts = getattr(node, "parts", None) or []
    if not parts:
        return None
    last = parts[-1]
    if not isinstance(last, Node):
        return None
    if last.node_name == "Identifier":
        # 单段（a）或末段是标识符：查宽度表
        return table_width_to_num_params(
            _lookup_width(width_table, module, getattr(last, "content", "") or ""),
            width_table.get("_params"),
        )
    if last.node_name == "HierSuffix":
        return 1  # 末段下标选择 → 1 bit
    if last.node_name == "HierMember":
        w = table_width_to_num_params(
            _lookup_width(
                width_table, module,
                getattr(getattr(last, "name", None), "content", "") or "",
            ),
            width_table.get("_params"),
        )
        if w is not None or len(parts) < 2:
            return w
        # 本地表查不到的多段链 → 跨模块成员宽度（hier 插件按需解析）
        hier = width_table.get("_hier")
        if hier is not None:
            return hier(node)
        return None
    return None


def _first_arg_width(node, width_table: dict, module: str = "") -> int | None:
    """SysFuncCall 首参数宽度（$signed/$unsigned 单参数）。"""
    args = getattr(node, "args", None)
    if not isinstance(args, Node):
        return None
    items = getattr(args, "items", None) or []
    for it in items:
        if isinstance(it, Node):
            return infer_expr_width(it, width_table, module)
    return None
