"""parser/follow.py — FOLLOW 集派生（对标 yacc/bison LALR 构造的副产品）。

从 production 结构机械推导每条规则的后继 token 集。语法是唯一真相源，
FOLLOW 是派生数据——check_end_case 的硬性依据（token ∉ FOLLOW → 拒绝）。

手写 end_case 字段已整体移除（2026-08-19）：后继合法性全部由本模块推导；
仅 `exclude`（负向前瞻，消歧用）保留为独立字段，与 FOLLOW 正交。

语境建模（tpc 解析器的三个非 production 结构）：
  1. 语句循环：is_block 规则 body 循环 parse_sentence——FOLLOW(语句规则)
     ⊇ 所有语句候选的 FIRST ∪ 所有块结束符
  2. pratt 运算符：is_atom 规则在 pratt 内部可后跟任意运算符 token——
     运算符 token 家族从 token_category 配置读取（语言数据），注入 atom
     的 FOLLOW
  3. inline 展开：inline 规则（choice 选择器）的成员直接面对 inline 规则
     的后继——FOLLOW(成员) ⊇ FOLLOW(inline 规则)

FOLLOW 成员两种形式：
  精确 token 类型（"id"、"keyword.if"）
  前缀 token 家族（"symbol.base."——以 "." 结尾，匹配整个家族）
Doc: docs/language_walkthrough.md（规则形态分类）
"""

from core.define import GrammarRule
from .rule_selector import analyze_production_features


def _prods_trees(prods: list) -> list[dict]:
    """production 元素列表 → 元素树列表（seq 的 items）。"""
    trees = []
    for prod in prods or []:
        if not isinstance(prod, str):
            continue
        tree = analyze_production_features(prod)
        if tree is not None:
            trees.append(tree)
    return trees


def _rule_trees(rule: GrammarRule) -> list[dict]:
    """规则 production 列表 → 元素树列表。"""
    return _prods_trees(getattr(rule, "prods", []) or [])


def _elem_calls(elem: dict) -> list[str]:
    """收集 elem 树中所有 @call 引用的规则名。"""
    names: list[str] = []
    typ = elem.get("type")
    if typ == "call":
        names.append(elem["name"])
    elif typ == "seq":
        for item in elem.get("items", []):
            names.extend(_elem_calls(item))
    elif typ == "choice":
        for alt in elem.get("alternatives", []):
            names.extend(_elem_calls(alt))
    elif typ in ("repeat", "plus", "optional"):
        names.extend(_elem_calls(elem.get("elem", {})))
    return names


def _elem_first(elem: dict, first_map: dict, nullable_map: dict) -> set[str]:
    """元素树的 FIRST（不含 ε；ε 由 nullable_map 表达）。"""
    typ = elem.get("type")
    if typ == "token":
        tt = elem.get("token_type")
        return {tt} if tt else set()
    if typ == "call":
        return set(first_map.get(elem.get("name"), ()))
    if typ == "seq":
        out: set[str] = set()
        for item in elem.get("items", []):
            out |= _elem_first(item, first_map, nullable_map)
            if not _elem_nullable(item, nullable_map):
                break
        return out
    if typ == "choice":
        out = set()
        for alt in elem.get("alternatives", []):
            out |= _elem_first(alt, first_map, nullable_map)
        return out
    if typ in ("repeat", "plus", "optional"):
        return _elem_first(elem.get("elem", {}), first_map, nullable_map)
    return set()


def _elem_nullable(elem: dict, nullable_map: dict) -> bool:
    """元素树是否可空。"""
    typ = elem.get("type")
    if typ == "token":
        return False
    if typ == "call":
        return nullable_map.get(elem.get("name"), False)
    if typ == "seq":
        return all(
            _elem_nullable(i, nullable_map) for i in elem.get("items", [])
        )
    if typ == "choice":
        return any(
            _elem_nullable(a, nullable_map) for a in elem.get("alternatives", [])
        )
    if typ in ("repeat", "optional"):
        return True
    if typ == "plus":
        return _elem_nullable(elem.get("elem", {}), nullable_map)
    return False


def _compute_first_nullable(
    names: set[str],
    trees: dict[str, list[dict]],
    rules: dict[str, GrammarRule],
    operator_members: list[str] | None = None,
) -> tuple[dict[str, set[str]], dict[str, bool]]:
    """FIRST / nullable 不动点迭代（处理递归引用）。

    块规则的 FIRST 特判：is_block 规则剥离后 prods 是"内容部分"（起止符由
    块路径单独消费），其作为 @call 引用/语句候选时的首 token 是 block_start
    （如 BeginEnd 剥离后 prods=[] 但 FIRST 应为 {keyword.begin}）。
    """
    first_map: dict[str, set[str]] = {n: set() for n in names}
    nullable_map: dict[str, bool] = {n: False for n in names}
    # 块规则 FIRST 种子（不参与迭代——block_start 是确定性事实）
    for n in names:
        rule = rules.get(n)
        if rule is not None and getattr(rule, "is_block", False):
            bs = getattr(rule, "block_start", "") or ""
            if bs:
                first_map[n] = {bs}
    # pratt 规则 FIRST 种子：内置前缀运算符（| ~ ! + - ^ & 等）不在任何
    # production 里（由 pratt 解析器处理），但它们是合法的表达式起始——
    # 如 case item 以 `|{...}:` 开头的 reduction OR。注入整个运算符家族
    # （家族级无法按 content 区分前缀/中缀，过度包含是 fail-open 方向）。
    if operator_members:
        for n in names:
            rule = rules.get(n)
            if rule is not None and getattr(rule, "pratt", False):
                first_map[n] |= set(operator_members)
    changed = True
    while changed:
        changed = False
        for name in names:
            if rules.get(name) is not None and getattr(
                rules[name], "is_block", False
            ) and getattr(rules[name], "block_start", ""):
                # 有 block_start 的块规则：FIRST 已种子化，跳过迭代覆盖
                continue
            f = set(first_map[name])  # 保留种子（block_start / pratt 运算符注入）
            nullable = True
            for elem in trees[name]:
                f |= _elem_first(elem, first_map, nullable_map)
                if not _elem_nullable(elem, nullable_map):
                    nullable = False
                    break
            if f != first_map[name]:
                first_map[name] = f
                changed = True
            if nullable != nullable_map[name]:
                nullable_map[name] = nullable
                changed = True
    return first_map, nullable_map


def _propagate_seq(
    follows: dict[str, set[str]],
    elems: list[dict],
    owner: str,
    first_map: dict[str, set[str]],
    nullable_map: dict[str, bool],
    body_first: set[str] | None = None,
) -> bool:
    """按 seq 方程传播 FOLLOW：每个 call 元素 B 的后继 = 后续元素 FIRST。

    body_first：块规则 body 循环（语句候选 FIRST ∪ 块结束符）的 FIRST，
    作为序列末尾的虚拟 nullable 元素参与传播。
    返回是否有变化。
    """
    changed = False
    for i, elem in enumerate(elems):
        for member in _elem_calls(elem):
            beta_first: set[str] = set()
            beta_nullable = True
            for later in elems[i + 1 :]:
                beta_first |= _elem_first(later, first_map, nullable_map)
                if not _elem_nullable(later, nullable_map):
                    beta_nullable = False
                    break
            # repeat/plus 的内部循环后继：下一次迭代的 FIRST。
            # 注意 beta_nullable 仍由后续元素（beta 侧）决定——repeat 自身
            # 可空（0 次迭代），owner FOLLOW 传播条件与循环无关。
            if elem.get("type") in ("repeat", "plus"):
                beta_first |= _elem_first(elem, first_map, nullable_map)
            if body_first is not None:
                beta_first |= body_first
            if member not in follows:
                continue
            before = len(follows[member])
            follows[member] |= beta_first
            if beta_nullable:
                follows[member] |= follows[owner]
            if len(follows[member]) != before:
                changed = True
    return changed


def compute_follows(
    rules: dict[str, GrammarRule],
    operator_members: list[str] | None = None,
    trace: bool = False,
) -> dict[str, frozenset[str]]:
    """计算所有规则的 FOLLOW 集。

    Args:
        rules: 语法规则表（规则名 → GrammarRule，production 为块剥离后形态）
        operator_members: pratt 运算符 token 成员（来自 token_category 的
            operator 分类 types；前缀成员以 "." 结尾）。None = 不注入。
        trace: 配置推导可视化（C8，2026-08-28）——输出阶段汇总（语句/原子/
            运算符注入）与每条规则最终 FOLLOW 到 stderr。默认 False 零影响；
            语法规则变化导致解析回归时，`FOLLOW(X)` 的内容可见（来自语句
            循环注入 / pratt 运算符 / 方程传播），配合规则生产式定位来源。

    Returns:
        {规则名: frozenset[token 成员]}。FOLLOW 为空的规则（不可达且无
        语句/原子角色）由调用方回退旧行为。
    """
    if trace:
        import sys as _sys

        def _t(msg: str) -> None:
            print(f"[follow-trace] {msg}", file=_sys.stderr)
    else:

        def _t(msg: str) -> None:  # pyright: ignore[reportUnusedFunction] — trace 关闭时的兜底定义
            del msg  # trace 关闭：调用点在 if trace 内不执行，兜底空操作

    names = set(rules)
    # 块规则用内容部分（block_prods）建模——block_start/block_end 由块路径
    # 单独消费，不是内容生产式的一部分（body 循环由 body_first 单独注入），
    # 与剥离形态保持一致，避免块头内部元素 FOLLOW 混入 block_end。
    trees = {}
    for n in names:
        r = rules[n]
        if getattr(r, "is_block", False):
            trees[n] = _prods_trees(
                getattr(r, "block_prods", None)
                or getattr(r, "prods", []) or []
            )
        else:
            trees[n] = _rule_trees(r)
    first_map, nullable_map = _compute_first_nullable(
        names, trees, rules, operator_members
    )

    follows: dict[str, set[str]] = {n: set() for n in names}

    statements = {n for n in names if getattr(rules[n], "is_statement", False)}
    atoms = {n for n in names if getattr(rules[n], "is_atom", False)}
    inline_rules = {n for n in names if getattr(rules[n], "inline", False)}
    block_rules = {n for n in names if getattr(rules[n], "is_block", False)}

    if trace:
        _t(
            f"rules={len(names)} statements={len(statements)} "
            f"atoms={len(atoms)} inline={len(inline_rules)} block={len(block_rules)}"
        )

    # 块结束符集合（语句循环的后继之一）
    block_ends: set[str] = set()
    for n in block_rules:
        be = getattr(rules[n], "block_end", "") or ""
        if be:
            block_ends.add(be)

    # 语句候选 FIRST 全集（语句循环：任一语句可跟随任一语句）
    stmt_first: set[str] = set()
    for s in statements:
        stmt_first |= first_map.get(s, set())

    if trace:
        _t(f"stmt_first={sorted(stmt_first)} block_ends={sorted(block_ends)}")

    # 语句循环注入
    for s in statements:
        follows[s] |= stmt_first | block_ends

    # pratt 运算符注入：atom 后可跟任意运算符 token
    if operator_members:
        for a in atoms:
            follows[a] |= set(operator_members)
        if trace:
            _t(f"operator injection: {len(atoms)} atoms <- {sorted(operator_members)}")

    # 主体方程不动点
    changed = True
    while changed:
        changed = False
        for name in names:
            if name in block_rules:
                # 块规则：内容 production 后附 body 循环（nullable 虚拟元素）
                changed |= _propagate_seq(
                    follows,
                    trees[name],
                    name,
                    first_map,
                    nullable_map,
                    body_first=stmt_first | block_ends,
                )
            else:
                changed |= _propagate_seq(
                    follows, trees[name], name, first_map, nullable_map
                )

    # inline 传播：inline 展开后成员直接面对 inline 规则的后继
    for i in inline_rules:
        fi = follows.get(i, set())
        for elem in trees[i]:
            for member in _elem_calls(elem):
                if member in follows:
                    follows[member] |= fi

    if trace:
        for n in sorted(follows):
            _t(f"FOLLOW({n}) = {sorted(follows[n])}")

    return {n: frozenset(s) for n, s in follows.items()}


def token_in_follow(tok_type: str, follow: frozenset[str]) -> bool:
    """检查 token 类型是否属于 FOLLOW 集合（含前缀家族成员）。"""
    for member in follow:
        if member == tok_type:
            return True
        if member.endswith(".") and tok_type.startswith(member):
            return True
    return False
