"""_latch_check.py — 锁存风险检查 postpass（latch_check 插件）

组合 always（@* 或电平敏感、无 posedge/negedge）内，若某信号**并非在
所有控制路径上都赋值**（存在保持路径）→ 推断锁存，报 LC001。实现为
**全路径判定**（Verilator V3Active LatchDetectGraph 同思路，references.md
「三主题实现机制调研」锁存一节）：对被赋值信号做 must-assign 前向分析——

  - 赋值语句 → 目标信号必赋值
  - 顺序复合（begin…end/块）→ 并集（每句都执行）
  - if/else → 两分支交集（无 else → ∅）
  - case → 各臂交集；**无 default 但常量值全覆盖 → 视为完备**（解码器
    全值 case 合法，不误报）；`(* full_case *)` 属性 → 同样视为完备
    （综合语义：未列值 don't-care）
  - 循环 → init 值代入条件可判"至少执行一次"则体内必赋值，否则 ∅
    （可能执行 0 次；for init 本身算必赋值）

时序 always 内 if 无 else 是合法复位写法，跳过。语言知识（组合 always
判定 / 控制流形态 / 信号名提取 / full_case 语义）集中在此插件层，引擎
零硬编码。

对标：Verilator LATCH / slang inferred-latch（visitPartiallyAssigned）/
Yosys proc_dlatch（综合视角）/ SpyGlass W442aL。升级自有限版（只查
"if 无 else"，2026-08-29 调研后落地全路径判定）。
"""

from core.define import Node, iter_nodes
from grammar.verilog.plugins.checks._shared import const_eval, const_value, is_timing_always, target_sig

_ALWAYS_RULE = "AlwaysStmt"


# 过程赋值规则（锁存判定只看过程体内赋值）
_ASSIGN_RULES = {"BlockingAssign", "NonBlockingAssign"}
# if 家族（IfBlock/IfStmt 与 else if 变体同构：condition/then_stmt/else_chain）
_IF_RULES = {"IfBlock", "IfStmt", "ElseIfBlock", "ElseIfStmt"}
# else 分支体（无 else if 的平铺 else）
_ELSE_RULES = {"ElseBlockBranch", "ElseBranch"}
# 循环族（体可能执行 0 次 → 不贡献必赋值；for 的 init 单独处理）
_LOOP_RULES = {"ForLoop", "ForLoopBlock", "WhileLoop", "RepeatLoop", "ForeverLoop"}


def run_latch_check(analyzer, context) -> None:
    """postpass 入口：组合 always 全路径判定 → 锁存风险。"""
    root = getattr(analyzer, "_ast", None)
    if root is None:
        return
    # 按模块分组：循环边界参数求值需要当前模块参数表
    for module in iter_nodes(root):
        if module.node_name not in ("ModuleDecl", "MacroModuleDecl"):
            continue
        params = _module_params(context, module)
        for node in iter_nodes(module):
            if node.node_name != _ALWAYS_RULE:
                continue
            if is_timing_always(node):
                continue  # 时序 always：if 无 else 是合法复位写法
            _check_combinational(node, context, params)


def _module_params(context, module: Node) -> dict:
    """当前模块参数默认值：头参数（module_index）+ 模块体参数声明。"""
    out: dict = {}
    mn = getattr(getattr(module, "module_name", None), "content", "") or ""
    if mn:
        info = (context.extra.get("module_index", {}) or {}).get(mn)
        if info is not None:
            out.update({p: mp.value_expr for p, mp in (info.params or {}).items()})
    # 模块体 parameter 声明（`parameter STEPS_AT_ONCE = 1;` 等，实例可覆盖）
    for n in iter_nodes(module):
        if n.node_name != "ParamDeclStmt":
            continue
        for d in _declarators(n):
            name = _node_text(getattr(d, "name", None))
            init = _node_text(getattr(d, "init", None))
            if name and init:
                out.setdefault(name, init)
    return out


def _declarators(stmt: Node) -> list:
    """ParamDeclStmt → Declarator 列表（items 为 DeclaratorList 包裹）。"""
    items = getattr(stmt, "items", None)
    if isinstance(items, Node) and items.node_name == "DeclaratorList":
        return [d for d in (getattr(items, "items", None) or [])
                if isinstance(d, Node)]
    return [items] if isinstance(items, Node) else []


def _check_combinational(always_node: Node, context, params: dict) -> None:
    """组合 always 体内：未全路径赋值的信号 → LC001（每信号一条）。"""
    body = getattr(always_node, "body", None)
    if body is None:
        return
    assigned = _collect_assigned(body)
    if not assigned:
        return
    must = _must_assign(body, params)
    for sig, first_node in assigned.items():
        if sig in must:
            continue
        context.report(
            f"组合逻辑信号 {sig} 未在所有控制路径上赋值"
            "（存在保持路径 → 推断锁存/仿真综合不一致风险）",
            code="LC001",
            level="warning",
            node=first_node,
        )


def _collect_assigned(body: Node) -> dict:
    """块内全部过程赋值目标 → {信号名: 首次赋值节点}（嵌套不穿透）。"""
    out: dict = {}
    for node in iter_nodes(body):
        if node.node_name not in _ASSIGN_RULES:
            continue
        sig = target_sig(getattr(node, "target", None))
        if sig:
            out.setdefault(sig, node)
    return out


def _must_assign(node, params: dict, full_case: bool = False) -> set:
    """前向 must-assign：语句 → 全路径必赋值信号集合（纯函数）。

    顺序复合 = 并集；if/else = 交集（无 else → ∅）；case = 各臂交集
    （无 default 且未全覆盖且无 full_case → ∅）；循环 = init 值代入条件
    可判"至少执行一次"则体内必赋值，否则 ∅（init 除外）。
    """
    if node is None or not isinstance(node, Node):
        return set()
    name = node.node_name
    if name in _ASSIGN_RULES:
        sig = target_sig(getattr(node, "target", None))
        return {sig} if sig else set()
    if name == "BeginEnd":
        acc: set = set()
        for ch in node.iter_children():
            if isinstance(ch, Node):
                acc |= _must_assign(ch, params, full_case)
        return acc
    if name in _IF_RULES:
        then = _must_assign(getattr(node, "then_stmt", None), params, full_case)
        return then & _must_assign(_else_branch(node), params, full_case)
    if name in _ELSE_RULES:
        return _must_assign(getattr(node, "body", None), params, full_case)
    if name == "CaseStmt":
        return _case_must(node, params, full_case)
    if name == "AttrStmt":
        # (* full_case *) case … → 视为完备（合成语义：未列值 don't-care）
        return _must_assign(
            getattr(node, "stmt", None), params,
            full_case or "full_case" in _attr_names(node),
        )
    if name in _LOOP_RULES:
        if _loop_executes(node, params):
            return _must_assign(getattr(node, "body", None), params, full_case)
        init = getattr(node, "init", None)
        if isinstance(init, Node):
            return _must_assign(init, params, full_case)
        return set()
    if name == "ForInit":
        sig = target_sig(getattr(node, "target", None))
        return {sig} if sig else set()
    if name == "StmtOrNull":
        return _must_assign(getattr(node, "stmt", None), params, full_case)
    if name == "AssignStmt":
        return set()  # 连续赋值不出现在过程体内（防御）
    return set()


def _else_branch(node) -> Node | None:
    """if 的 else 链 → 分支节点（无 else → None）。"""
    ec = getattr(node, "else_chain", None)
    if ec is None:
        return None
    if isinstance(ec, Node) and ec.node_name == "ElseChain":
        br = getattr(ec, "branch", None)
        return br if isinstance(br, Node) else None
    return ec


def _attr_names(node) -> set:
    """AttrStmt/AttrDecl 的属性名集合（(* full_case *) → {"full_case"}）。"""
    out: set = set()
    attrs = getattr(node, "attrs", None)
    if not isinstance(attrs, Node):
        return out
    specs = getattr(attrs, "specs", None)
    if not isinstance(specs, Node):
        return out
    for it in getattr(specs, "items", None) or []:
        if isinstance(it, Node) and it.node_name == "AttrSpec":
            nm = getattr(getattr(it, "name", None), "content", "") or ""
            if nm:
                out.add(nm)
    return out


def _case_must(node: Node, params: dict, full_case: bool) -> set:
    """case 的 must-assign：各臂交集；无 default 需常量覆盖完备/属性才非 ∅。"""
    items = _case_items(node)
    if not items:
        return set()
    has_default = any(it.node_name == "DefaultItem" for it in items)
    if not has_default and not full_case and not _case_covered(items):
        return set()  # 未覆盖所有值 → 存在保持路径
    must: set | None = None
    for it in items:
        stmt = getattr(it, "stmt", None)
        m = _must_assign(stmt, params, full_case)
        must = m if must is None else (must & m)
    return must or set()


def _case_items(node: Node) -> list:
    """CaseStmt → CaseItem/DefaultItem 列表（兼容 CaseItemList 包裹）。"""
    lst = getattr(node, "items", None)
    if isinstance(lst, Node):
        if lst.node_name == "CaseItemList":
            return [it for it in (getattr(lst, "items", None) or [])
                    if isinstance(it, Node)]
        return [lst]
    return []


def _case_covered(items: list) -> bool:
    """无 default 的 case 是否常量全覆盖（解码器全值 case 合法）。

    全部臂值为常量（无变量/范围/wildcard），且并集覆盖 [0, 2^w)——
    w 取各臂值最大位宽。含 casez/casex 通配符或非纯常量 → 视为未覆盖
    （保守报锁存）。
    """
    values: set = set()
    width = 0
    for it in items:
        if it.node_name != "CaseItem":
            return False
        vals = getattr(it, "values", None) or []
        for v in vals:
            if not isinstance(v, Node):
                return False
            cv = const_value(_node_text(v))
            if cv is None:
                return False
            value, w = cv
            values.add(value)
            width = max(width, w)
    if width == 0:
        return False
    return values == set(range(1 << width))


def _loop_executes(node: Node, params: dict) -> bool | None:
    """循环是否**至少执行一次**：init 值代入条件求值（含参数）。

    `for (i=0; i<STEPS_AT_ONCE; …)` 且 STEPS_AT_ONCE=1 → 0<1 真 → 执行；
    `for (i=0; i<0; …)` → 假 → 可能 0 次；while/边界不可判 → None（保守）。
    """
    init = getattr(node, "init", None)
    cond = getattr(node, "condition", None)
    if not isinstance(init, Node) or not isinstance(cond, Node):
        return None  # while/repeat/forever：边界不可判
    target = getattr(init, "target", None)
    name = getattr(target, "content", "") if isinstance(target, Node) else ""
    iv = const_eval(_node_text(getattr(init, "value", None)), params)
    if not name or iv is None:
        return None
    env = {**params, name: str(iv)}  # 循环变量代换为 init 值
    if cond.node_name == "BinaryOp":
        op = getattr(cond, "op", "") or ""
        if op in ("<", "<=", ">", ">=", "==", "!="):
            l = const_eval(_node_text(getattr(cond, "left", None)), env)
            r = const_eval(_node_text(getattr(cond, "right", None)), env)
            if l is not None and r is not None:
                return {
                    "<": l < r, "<=": l <= r, ">": l > r,
                    ">=": l >= r, "==": l == r, "!=": l != r,
                }[op]
    # 非比较条件（while (1) 等）→ 整体常量求值
    ev = const_eval(_cond_text(cond), env)
    if ev is None:
        return None
    return ev != 0


def _cond_text(cond: Node | None) -> str:
    """条件表达式 → 文本（BinaryOp 渲染 left op right；叶节点取文本）。"""
    if not isinstance(cond, Node):
        return ""
    if cond.node_name == "BinaryOp":
        op = getattr(cond, "op", "") or ""
        l = _node_text(getattr(cond, "left", None))
        r = _node_text(getattr(cond, "right", None))
        return f"{l} {op} {r}" if l and r else ""
    if cond.node_name == "ParenthesizedExpr":
        return _cond_text(getattr(cond, "expr", None))
    return _node_text(cond)


def _node_text(node) -> str:
    """节点 → 源码文本（Identifier 类在 content；HierExpr 拼 parts；
    token 节点 value 是嵌套 Node 或字符串，递归取到叶子文本）。"""
    if not isinstance(node, Node):
        return ""
    c = getattr(node, "content", "") or ""
    if c:
        return c
    if node.node_name == "HierExpr":
        parts = [_node_text(p) for p in getattr(node, "parts", None) or []]
        return "".join(p for p in parts if p)
    v = getattr(node, "value", None)
    if isinstance(v, str) and v:
        return v
    if isinstance(v, Node):
        t = _node_text(v)
        if t:
            return t
    return ""


