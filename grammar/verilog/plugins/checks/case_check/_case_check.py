"""_case_check.py — case 完整性检查 postpass（case_check 插件）

遍历后链式走查（ADR-0004 postpass 机制）：找 AST 中所有 CaseStmt，
检查其 items（CaseItemList）是否含 DefaultItem——无 default 分支的
case 报 CC001（组合逻辑未覆盖全分支 → 锁存风险/仿真综合不一致）。

语言知识（CaseStmt/DefaultItem 节点名）集中在此插件层，引擎零硬编码。
对标：svlint case_default / Verible case-missing-default /
Verilator CASEINCOMPLETE / slang case-* / Spyglass W527。
Verilog-2005 无 unique/priority 限定（SV 才有），不处理 unique 豁免。
"""

from core.define import Node

_CASE_RULE = "CaseStmt"
_DEFAULT_RULE = "DefaultItem"


def run_case_check(analyzer, context) -> None:
    """postpass 入口：遍历 AST 找 case 无 default 分支。

    对齐 Verilator CASEINCOMPLETE（2026-08-29 对标测试修正）：无 default
    但**常量全覆盖**（解码器全值 case）不报——全覆盖无保持路径，无锁存
    风险。此前只看"有无 default 关键字"：tv80 `case(cc)` 8 值全覆盖、
    ice40 `case(WRITE_MODE)` 2 位 0-3 全覆盖被误报（Verilator 0 报）。
    """
    root = getattr(analyzer, "_ast", None)
    if root is None:
        return
    for node in _iter_nodes(root):
        if node.node_name != _CASE_RULE:
            continue
        items = getattr(node, "items", None)
        if _has_default(node):
            continue
        if _case_covered(items):
            continue  # 无 default 但常量全覆盖（对齐 Verilator CASEINCOMPLETE）
        context.report(
            "case 语句无 default 分支（组合逻辑未覆盖全分支，"
            "有锁存/仿真综合不一致风险）",
            code="CC001",
            level="warning",
            node=node,
        )


def _case_covered(items) -> bool:
    """无 default 的 case 是否常量全覆盖（解码器全值 case 合法）。

    全部臂值为常量（无变量/范围/wildcard），且并集覆盖 [0, 2^w)——
    w 取各臂值最大位宽。含 casez/casex 通配符或非纯常量 → 视为未覆盖
    （保守报 CC001）。与 latch_check 的 _case_covered 同判据（语言知识
    在插件层，两个插件各自实现，引擎零硬编码）。
    """
    if not isinstance(items, Node):
        return False
    values: set = set()
    width = 0
    for it in _case_items(items):
        if it.node_name != "CaseItem":
            return False
        vals = getattr(it, "values", None) or []
        for v in vals:
            if not isinstance(v, Node):
                return False
            cv = _const_value(_node_text(v))
            if cv is None:
                return False
            value, w = cv
            values.add(value)
            width = max(width, w)
    if width == 0:
        return False
    return values == set(range(1 << width))


def _case_items(items: Node) -> list:
    """CaseItemList → CaseItem 列表（兼容 items 直接挂 vs 子列表）。"""
    if items.node_name == "CaseItemList":
        return [n for n in (getattr(items, "items", None) or [])
                if isinstance(n, Node)]
    return [items]


def _const_value(text: str):
    """case 臂常量文本 → (值, 位宽)；变量/通配符/x/z → None。"""
    t = (text or "").strip()
    if "'" not in t:
        if not t.isdigit():
            return None
        v = int(t)
        return (v, v.bit_length() if v else 1)
    body = t.split("'", 1)[1]
    if not body:
        return None
    if body[0] in "sS":
        body = body[1:]
    if not body:
        return None
    if len(body) == 1 and body in "01xXzZ?":
        return None  # 填充/通配符常量不算覆盖
    base_ch = body[0].lower()
    if base_ch not in "bohd":
        return None
    digits = body[1:].replace("_", "")
    if not digits or any(c in "xXzZ?" for c in digits):
        return None
    try:
        v = int(digits, {"b": 2, "o": 8, "h": 16, "d": 10}[base_ch])
    except ValueError:
        return None
    w = int(t.split("'", 1)[0]) if t.split("'", 1)[0].strip().isdigit() \
        else (v.bit_length() if v else 1)
    return (v, w)


def _node_text(node) -> str:
    """Node → 文本（content 优先；token 值在 value；HierExpr 渲染 parts）。"""
    if not isinstance(node, Node):
        return str(node) if node else ""
    c = getattr(node, "content", None)
    if isinstance(c, str) and c:
        return c
    v = getattr(node, "value", None)
    if isinstance(v, str) and v:
        return v
    if node.node_name == "HierExpr":
        parts = getattr(node, "parts", None) or []
        return "".join(_node_text(p) for p in parts)
    return "".join(_node_text(ch) for ch in node.iter_children())


def _has_default(case_node: Node) -> bool:
    """case 的 items（CaseItemList）是否含 DefaultItem。"""
    items = getattr(case_node, "items", None)
    if items is None:
        return False
    stack = [items]
    while stack:
        node = stack.pop()
        if not isinstance(node, Node):
            continue
        if node.node_name == _DEFAULT_RULE:
            return True
        for child in node.iter_children():
            stack.append(child)
    return False


def _iter_nodes(root: Node):
    """DFS 迭代整棵 AST。"""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        for child in node.iter_children():
            stack.append(child)
