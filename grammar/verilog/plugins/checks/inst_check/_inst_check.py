"""_inst_check.py — 模块实例化联动检查 postpass（inst_check 插件）

遍历结束后的链式走查（ADR-0004 postpass 机制）：比对"实例化点"与
"被实例化模块的声明形态"（端口/参数/宽度），报跨文件联动错误范式。

语言知识（Verilog 语义规则）集中在此插件层，引擎零硬编码：
- 端口连接名必须存在于模块端口列表（W102）
- 参数覆盖名必须存在于模块参数列表（W103）
- 字面量连接参数化宽度端口 = 配置敏感死值风险（WC001，related 链）
- 实例化一个定义缺失的模块（W101，定义文件未找到）
"""

import re

from core.define import Node

_LITERAL_RE = re.compile(r"^\d+'\s*[hdb]?[0-9a-fA-F_]*$")


def run_inst_check(analyzer, context) -> None:
    """postpass 入口：本文件实例化点 × 全工程模块表 联动检查。"""
    del analyzer  # postpass 协议签名参数，本 pass 从 context 取数据
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
