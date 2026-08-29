"""_inst_check.py — 模块实例化联动检查 postpass（inst_check 插件）

遍历结束后的链式走查（ADR-0004 postpass 机制）：比对"实例化点"与
"被实例化模块的声明形态"（端口/参数/宽度），报跨文件联动错误范式。

语言知识（Verilog 语义规则）集中在此插件层，引擎零硬编码：
- 端口连接名必须存在于模块端口列表（W102）
- 参数覆盖名必须存在于模块参数列表（W103）
- 字面量连接参数化宽度端口 = 配置敏感死值风险（WC001，related 链）
- 实例化一个定义缺失的模块（W101，定义文件未找到）
"""

import os
import re

from core.define import Node

_LITERAL_RE = re.compile(r"^\d+'\s*[hdb]?[0-9a-fA-F_]*$")


def run_inst_check(analyzer, context) -> None:
    """postpass 入口：本文件实例化点 × 全工程模块表 联动检查。"""
    module_index = context.extra.get("module_index", {}) or {}
    inst_sites = context.extra.get("inst_sites", []) or []
    # elaboration 层 2（ADR-0008）：实例化点端口连接展开——未连接端口判定
    connections = context.extra.get("connections", []) or []
    conn_by_inst = {c.inst_name: c for c in connections}
    for site in inst_sites:
        mod_name = _text(getattr(site, "module_name", None))
        if not mod_name:
            continue
        info = module_index.get(mod_name)
        if info is None:
            context.report(
                f"实例化的模块 '{mod_name}' 未找到定义"
                "（同目录/--include 搜索无果，或模块名拼写错误）",
                code="W101",
                level="warning",
                node=site,
            )
            continue
        related_def = [("模块 '%s' 定义处" % mod_name, info.node)]
        _check_ports(context, site, info, related_def)
        _check_params(context, site, info, related_def)
        _check_missing_ports(context, site, info, related_def, conn_by_inst)

    # inout 端口须 tri（对标 svlint inout_with_tri = Veryl missing_tri，
    # 调研重合刚需第 4 条）——本文件模块定义的 inout 端口检查（遍历
    # 本文件 AST，避免跨文件重复报）。
    _check_inout_tri(analyzer, context)

    # elaboration 层 3（ADR-0008）：多驱动检查（对标 Verilator MULTIDRIVEN
    # / Spyglass W415——同一信号被多个驱动源驱动：实例 output 连接 +
    # 模块级 assign 连续赋值目标）。
    _check_multi_driver(analyzer, context, connections)


def _check_ports(context, site, info, related_def) -> None:
    """命名端口连接 × 模块端口表。"""
    nl = _unwrap(getattr(site, "ports", None))   # NamedPortList
    conns = getattr(nl, "items", None) if nl else None
    for conn in conns or []:
        if not isinstance(conn, Node):
            continue
        pn = _text(getattr(conn, "port_name", None))
        if not pn:
            continue
        port = info.ports.get(pn)
        if port is None:
            context.report(
                f"实例化 '{info.name}' 连接了不存在的端口 '{pn}'",
                code="W102",
                level="error",
                node=conn,
                related=related_def,
            )
            continue
        # WC001：参数化宽度端口 + 字面量连接（配置敏感死值）
        if port.width_expr and _is_parameterized(port.width_expr):
            value = getattr(conn, "value", None)
            if _is_literal(value):
                related = list(related_def)
                if port.decl_node is not None:
                    related.append(("端口 '%s' 声明处" % pn, port.decl_node))
                context.report(
                    f"字面量 {_text(value)} 连接参数化宽度端口 '{pn}'"
                    f"（[{port.width_expr}]）——端口宽度由配置决定，"
                    "配置变更时该字面量可能成为死值",
                    code="WC001",
                    level="warning",
                    node=conn,
                    related=related,
                )


def _check_missing_ports(
    context, site, info, related_def, conn_by_inst
) -> None:
    """未连接端口检查（对标 Veryl missing_port / Verilator PINMISSING）。

    模块的 input/output 端口在实例化时未连接 → 报未连接。判定基于
    elaboration 层 2 的连接展开（connects 键 = 已连接端口名）+ 模块
    端口方向（module_index 端口声明）：
    - input/output 未连接 → W104（输入悬空/输出悬空都是设计错误范式）
    - inout 未连接不报（三态悬空可能是有意设计，保守豁免）
    位置连接（ordered）无法按名匹配，跳过（需按序对端口表，留给后续）。
    """
    conn = conn_by_inst.get(_text(getattr(site, "inst_name", None)))
    if conn is None:
        return
    connected = set(conn.connects.keys())
    # 语言知识：端口方向值（input/output/inout）来自语言包 checker 结构
    # 协议（本插件读 context.extra 注入的方向集——由引擎按协议注入）。
    out_dirs = set(context.extra.get("output_dirs", []) or [])
    in_dirs = set(context.extra.get("input_dirs", []) or [])
    check_dirs = in_dirs | out_dirs
    for pname, port in info.ports.items():
        if not port.direction or port.direction not in check_dirs:
            continue
        if pname in connected:
            continue
        context.report(
            f"实例化 '{info.name}' 未连接端口 '{pname}'"
            f"（{port.direction} 端口悬空）",
            code="W104",
            level="warning",
            node=site,
            related=related_def,
        )


def _check_multi_driver(analyzer, context, connections) -> None:
    """多驱动检查（对标 Verilator MULTIDRIVEN / Spyglass W415）。

    基于 elaboration 层 3 信号图（context.extra["signal_graph"]，键 =
    (模块, 信号名)——跨模块同名信号隔离，2026-08-29 修复 ice40 误报）：
    信号被 ≥2 个驱动源驱动（实例 output 连接 / 本文件 assign 连续赋值
    目标）→ 多驱动错误范式（并发驱动汇聚）。
    归属：驱动源含本文件（assign 或实例连接）才报——避免跨文件重复；
    本文件 assign 目标优先定位，否则实例连接处。
    """
    signal_graph = context.extra.get("signal_graph", {}) or {}
    if not signal_graph:
        return
    this_file = ""
    for conn in connections:
        this_file = os.path.basename(conn.file)
        break
    # 本文件 assign 驱动目标 → 信号名 → 节点（归属判定 + 定位）
    assign_nodes = _collect_assign_targets(analyzer)
    # 本文件出现的信号（连接展开里的连接信号名）
    local_sigs: set[str] = set()
    for conn in connections:
        local_sigs.update(conn.connects.values())
        local_sigs.update(conn.ordered)
    for (_mod, sig), entry in signal_graph.items():
        drivers = entry.get("drivers", [])
        if len(drivers) < 2:
            continue
        # 归属：驱动源含本文件才报（避免每文件重复报同一跨文件信号）
        if this_file and not any(d.startswith(this_file + ":") for d in drivers):
            continue
        node = assign_nodes.get(sig)
        if node is None and sig not in local_sigs:
            continue  # 信号未在本文件连接/赋值（驱动在别处）——跳过
        if node is None:
            node = _find_signal_node(connections, sig)
        driver_desc = ", ".join(drivers)
        context.report(
            f"信号 '{sig}' 被多个驱动源驱动（{len(drivers)} 个: {driver_desc}）"
            "——多驱动错误范式",
            code="W105",
            level="error",
            node=node,
        )


def _collect_assign_targets(analyzer) -> dict:
    """本文件连续赋值目标：AssignStmt.target / AssignExtra.target → 节点。

    语言知识（AssignStmt 形态）在本插件层（与 _check_inout_tri 同款）。
    目标信号名 = 合成包装（PrimaryExpr）下首个有 content 的叶子——与引擎
    侧信号图（renderer 渲染 + 简单信号名过滤）同语义，仅收集标识符形态
    （位选/拼接等复杂目标引擎侧不进图，此处也不收集，避免归属误判）。
    """
    root = getattr(analyzer, "_ast", None)
    out: dict[str, Node] = {}
    if root is None:
        return out
    for node in _iter_nodes(root):
        if node.node_name != "AssignStmt":
            continue
        tgt = getattr(node, "target", None)
        sig = _sig_text(tgt)
        if sig and sig not in out:
            out[sig] = tgt if isinstance(tgt, Node) else node
        for ex in getattr(node, "extras", None) or []:
            et = getattr(ex, "target", None)
            esig = _sig_text(et)
            if esig and esig not in out:
                out[esig] = et if isinstance(et, Node) else ex
    return out


_SIG_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sig_text(node) -> str:
    """赋值目标 → 简单信号名（标识符形态；合成包装穿透取首段 content）。"""
    if not isinstance(node, Node):
        return ""
    content = getattr(node, "content", "") or ""
    if content and _SIG_RE.match(content):
        return content
    for child in node.iter_children():
        t = _sig_text(child)
        if t:
            return t
    return ""


def _find_signal_node(connections, sig):
    """找本文件连接该信号的实例节点（定位用）。"""
    for conn in connections:
        for s in conn.connects.values():
            if s == sig:
                return conn.inst_node
        for s in conn.ordered:
            if s == sig:
                return conn.inst_node
    return None


def _check_inout_tri(analyzer, context) -> None:
    """inout 端口须 tri（对标 svlint inout_with_tri = Veryl missing_tri）。

    本文件模块定义的 inout 端口，其网络类型须为 tri（inout 是三态总线，
    wire 默认单驱动语义与 inout 冲突）。遍历本文件 AST 的 inout 端口
    声明节点（AnsiInoutDecl/BodyInoutDecl），检查其 port_type 是否为
    tri。语言知识（tri 是 inout 期望类型）集中在插件层。
    """
    root = getattr(analyzer, "_ast", None)
    if root is None:
        return
    inout_rules = {"AnsiInoutDecl", "BodyInoutDecl"}
    for node in _iter_nodes(root):
        if node.node_name not in inout_rules:
            continue
        pt = getattr(node, "port_type", None)
        net_type = ""
        if isinstance(pt, Node):
            net_type = getattr(pt, "content", "") or ""
            if not net_type:
                # keyword.wire 等 token 节点 content 为空，用节点名取末段
                net_type = getattr(pt, "node_name", "").split(".")[-1]
        elif isinstance(pt, str):
            net_type = pt.split(".")[-1]
        if net_type and net_type != "tri":
            context.report(
                f"inout 端口数据类型应为 tri（当前 {net_type}——"
                "三态总线语义）",
                code="W106",
                level="warning",
                node=node,
            )


def _iter_nodes(root):
    """DFS 迭代整棵 AST。"""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        for child in node.iter_children():
            stack.append(child)


def _check_params(context, site, info, related_def) -> None:
    """命名参数覆盖 × 模块参数表。"""
    po = getattr(site, "params", None)         # ParamOverride
    pl = getattr(po, "params", None) if po else None   # ParamOverrideList
    items = getattr(pl, "items", None) if pl else None
    for item in items or []:
        if not isinstance(item, Node) or item.node_name != "NamedParamOverride":
            continue
        pn = _text(getattr(item, "param_name", None))
        if pn and pn not in info.params:
            context.report(
                f"实例化 '{info.name}' 覆盖了不存在的参数 '{pn}'",
                code="W103",
                level="error",
                node=item,
                related=related_def,
            )


# ── 工具 ──


def _text(node) -> str:
    """Node → 源码文本（防御非 Node；BitWidthLiteral 等合成节点无 content，
    从 value/base/width 属性拼回）。"""
    if not isinstance(node, Node):
        return str(node) if node else ""
    content = getattr(node, "content", "") or ""
    if content:
        return content
    value = getattr(node, "value", None)
    if value is not None and getattr(node, "base", None) is not None:
        width = getattr(node, "width", None)
        base = getattr(node, "base", "")
        return f"{width}'{base}{value}" if width is not None else f"{base}{value}"
    if value is not None:
        if isinstance(value, Node):
            return _text(value)   # 嵌套合成节点（Number → literal.number 等）
        return str(value)
    return ""


def _unwrap(node):
    """穿透 optional 包装节点（与 analyzer/checker.py 的 _unwrap 同逻辑）。"""
    while isinstance(node, Node) and node.node_name == "optional":
        sub = getattr(node, "sub_node", None) or []
        node = sub[0] if sub else None
    return node


def _is_parameterized(width_expr: str) -> bool:
    """宽度表达式含非数字字符（如 DATA_W-1:0）→ 参数化。纯数字（7:0）不算。"""
    return any(ch.isalpha() for ch in width_expr)


def _is_literal(node) -> bool:
    """节点是否为数字字面量（Number / BitWidthLiteral / 数字或进制字面量文本）。"""
    if not isinstance(node, Node):
        return False
    if node.node_name in ("Number", "BitWidthLiteral"):
        return True
    content = getattr(node, "content", "") or ""
    return bool(_LITERAL_RE.match(content.strip()))
