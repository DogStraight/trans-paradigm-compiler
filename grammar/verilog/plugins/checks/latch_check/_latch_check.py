"""_latch_check.py — 锁存风险检查 postpass（latch_check 插件）

遍历后链式走查（ADR-0004 postpass 机制）：找**组合 always**（@* 或电平
敏感，无 posedge/negedge）内的 if 语句，无 else 分支 → 报 LC001（条件
不满足时信号保持 → 推断锁存）。

语言知识（组合 always 判定 / if 无 else 形态）集中在此插件层，引擎零
硬编码。时序 always 内 if 无 else 是合法复位写法，不报。

对标：svlint explicit_if_else / Verilator LATCH / Veryl uncovered_branch
/ slang inferred-latch。有限版：只查"if 无 else"可静态判定的锁存形态，
不做完整控制流路径分析。
"""

from core.define import Node

_ALWAYS_RULE = "AlwaysStmt"
_IF_RULES = {"IfBlock", "IfStmt"}
_EDGE_KEYWORDS = ("posedge", "negedge")


def run_latch_check(analyzer, context) -> None:
    """postpass 入口：组合 always 内 if 无 else → 锁存风险。"""
    root = getattr(analyzer, "_ast", None)
    if root is None:
        return
    for node in _iter_nodes(root):
        if node.node_name != _ALWAYS_RULE:
            continue
        if _is_timing_always(node):
            continue  # 时序 always：if 无 else 是合法复位写法
        _check_combinational_ifs(node, context)


def _is_timing_always(always_node: Node) -> bool:
    """always 是否为时序敏感（含 posedge/negedge）。

    event_control → EventCtrlParen → SensitivityList → EdgeSense（edge=
    posedge/negedge）。@* 或电平敏感列表 = 组合；含边沿 = 时序。
    """
    ec = getattr(always_node, "event_control", None)
    if ec is None:
        return False  # 裸 always（无事件控制）按组合处理
    # 遍历事件控制子树找边沿关键字
    for n in _iter_nodes(ec):
        edge = getattr(n, "edge", None)
        if isinstance(edge, Node):
            e = getattr(edge, "content", "") or edge.node_name or ""
            if e in _EDGE_KEYWORDS or e.split(".")[-1] in _EDGE_KEYWORDS:
                return True
    return False


def _check_combinational_ifs(always_node: Node, context) -> None:
    """组合 always 体内：if 无 else → LC001。"""
    body = getattr(always_node, "body", None)
    if body is None:
        return
    for n in _iter_nodes(body):
        if n.node_name not in _IF_RULES:
            continue
        # 跳过嵌套在时序敏感内的 if（已由 _is_timing_always 排除整个
        # always；这里直接检查 if 自身）
        if _has_else(n):
            continue
        context.report(
            "组合逻辑 if 无 else 分支（条件不满足时信号保持，"
            "有推断锁存/仿真综合不一致风险）",
            code="LC001",
            level="warning",
            node=n,
        )


def _has_else(if_node: Node) -> bool:
    """if 是否有 else 链。"""
    ec = getattr(if_node, "else_chain", None)
    return ec is not None


def _iter_nodes(root: Node):
    """DFS 迭代整棵 AST。"""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        for child in node.iter_children():
            stack.append(child)
