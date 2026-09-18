"""_always_check.py — always 写法风格检查 postpass（always_check 插件）

时序/组合 always 的过程体赋值纪律（L2 结构规则，默认关——default=false
经 rules/always.toml 声明，激活逻辑复用引擎 active_rule_ids）：

  - AW001：时序 always（posedge/negedge）内阻塞赋值（=）——时序块惯例
    用非阻塞（<=），阻塞赋值有仿真竞态/综合差异风险
    （对齐 Verilator BLKSEQ / svlint blocking_assignment_in_always_ff /
    Verible always-ff-non-blocking）。
  - AW002：同一 always 块内同一信号混用阻塞（=）与非阻塞（<=）——仿真
    调度未定义（对齐 Verilator BLKANDNBLK 简化版：同块同信号判定，
    不做跨块子位重叠证明）。

裸 always 无事件控制（仿真无限循环）不做（Verilog-2005 无 always_comb/
always_ff 语义，误报高——调研结论）。语言知识（时序判定 / 赋值运算符
收集 / 信号名提取）集中在此插件层，引擎零硬编码。
"""

from core.define import Node, iter_nodes

from analyzer.checks import active_rule_ids
from grammar.verilog.plugins.checks._shared import is_timing_always, target_sig

_ALWAYS_RULE = "AlwaysStmt"


_ASSIGN_RULES = {"BlockingAssign": "=", "NonBlockingAssign": "<="}


def run_always_check(analyzer, context) -> None:
    """postpass 入口：按启用集执行 AW001/AW002（默认关，未启用零开销）。"""
    active = active_rule_ids(analyzer)
    need_aw001 = "AW001" in active
    need_aw002 = "AW002" in active
    if not need_aw001 and not need_aw002:
        return
    root = getattr(analyzer, "_ast", None)
    if root is None:
        return
    for node in iter_nodes(root):
        if node.node_name != _ALWAYS_RULE:
            continue
        timing = is_timing_always(node)
        if need_aw001 and timing:
            _check_blocking_in_timing(node, context)
        if need_aw002:
            _check_mixed_assign(node, context)


def _check_blocking_in_timing(always_node: Node, context) -> None:
    """时序 always 体内阻塞赋值 → AW001（每处一条）。"""
    body = getattr(always_node, "body", None)
    if body is None:
        return
    for n in iter_nodes(body):
        if n.node_name != "BlockingAssign":
            continue
        lhs = _target_text(getattr(n, "target", None))
        context.report(
            "时序 always 内阻塞赋值"
            + (f"（{lhs} = …）" if lhs else "")
            + "：建议用非阻塞 <=（避免仿真竞态；Verilator BLKSEQ 同规则）",
            code="AW001",
            level="warning",
            node=n,
        )


def _check_mixed_assign(always_node: Node, context) -> None:
    """同一 always 内同一信号混用 =/<= → AW002（每信号一条）。"""
    body = getattr(always_node, "body", None)
    if body is None:
        return
    seen: dict[str, set] = {}
    for n in iter_nodes(body):
        op = _ASSIGN_RULES.get(n.node_name)
        if op is None:
            continue
        sig = target_sig(getattr(n, "target", None))
        if not sig:
            continue
        ops = seen.setdefault(sig, set())
        if op not in ops:
            ops.add(op)
            if len(ops) > 1:
                context.report(
                    f"同一 always 内信号 {sig} 混用阻塞（=）与非阻塞（<=）"
                    "赋值（仿真调度未定义；Verilator BLKANDNBLK 同规则）",
                    code="AW002",
                    level="warning",
                    node=n,
                )


def _target_text(target) -> str:
    """赋值目标 → 短文本（报告用；未知 → ""）。"""
    if not isinstance(target, Node):
        return ""
    if target.node_name == "Identifier":
        return getattr(target, "content", "") or ""
    parts = getattr(target, "parts", None)
    if parts and isinstance(parts[0], Node):
        return getattr(parts[0], "content", "") or ""
    return target.node_name


