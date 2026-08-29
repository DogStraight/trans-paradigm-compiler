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
    """postpass 入口：遍历 AST 找 case 无 default 分支。"""
    root = getattr(analyzer, "_ast", None)
    if root is None:
        return
    for node in _iter_nodes(root):
        if node.node_name != _CASE_RULE:
            continue
        if _has_default(node):
            continue
        context.report(
            "case 语句无 default 分支（组合逻辑未覆盖全分支，"
            "有锁存/仿真综合不一致风险）",
            code="CC001",
            level="warning",
            node=node,
        )


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
