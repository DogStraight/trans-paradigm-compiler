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
    first_map, nullable_map = _seed_first(names, rules, operator_members)
    changed = True
    while changed:
        changed = False
        for name in names:
            if _has_block_start(rules, name):
                continue  # 有 block_start 的块规则：FIRST 已种子化，跳过迭代覆盖
            f, nullable = _seq_first_nullable(trees[name], first_map, nullable_map)
            f |= first_map[name]  # 保留种子（block_start / pratt 运算符注入）
            if _update_first_nullable(first_map, nullable_map, name, f, nullable):
                changed = True
    return first_map, nullable_map


def _seed_first(
    names: set[str],
    rules: dict[str, GrammarRule],
    operator_members: list[str] | None,
) -> tuple[dict[str, set[str]], dict[str, bool]]:
    """FIRST / nullable 初始表：块规则 block_start 种子 + pratt 运算符种子。

    - block_start 种子（确定性事实，不参与迭代）：块规则剥离后 prods 是内容
      部分，但它作为 @call/语句候选时的首 token 是 block_start。
    - pratt 规则种子：内置前缀运算符（`|` `~` `!` `+` `-` `^` `&` 等）不在
      任何 production 里（由 pratt 解析器处理），但它们是合法的表达式起始——
      如 case item 以 `|{...}:` 开头的 reduction OR。注入**整个运算符家族**
      （家族级无法按 content 区分前缀/中缀，过度包含是 fail-open 方向）。
    """
    first_map: dict[str, set[str]] = {n: set() for n in names}
    nullable_map: dict[str, bool] = {n: False for n in names}
    for n in names:
        rule = rules.get(n)
        if rule is None:
            continue
        bs = getattr(rule, "block_start", "") or ""
        if getattr(rule, "is_block", False) and bs:
            first_map[n] = {bs}
        if operator_members and getattr(rule, "pratt", False):
            first_map[n] |= set(operator_members)
    return first_map, nullable_map


def _has_block_start(rules: dict[str, GrammarRule], name: str) -> bool:
    """该规则是否带 block_start（FIRST 已种子化）。"""
    rule = rules.get(name)
    if rule is None or not getattr(rule, "is_block", False):
        return False
    return bool(getattr(rule, "block_start", ""))


def _seq_first_nullable(
    elems: list[dict], first_map: dict[str, set[str]], nullable_map: dict[str, bool]
) -> tuple[set[str], bool]:
    """序列的 `(FIRST 并集, 是否整体可空)`。

    遇第一个不可空元素即停——其后元素既不在 FIRST 里，也不影响可空性。
    """
    first: set[str] = set()
    nullable = True
    for elem in elems:
        first |= _elem_first(elem, first_map, nullable_map)
        if not _elem_nullable(elem, nullable_map):
            nullable = False
            break
    return first, nullable


def _update_first_nullable(
    first_map: dict[str, set[str]],
    nullable_map: dict[str, bool],
    name: str,
    f: set[str],
    nullable: bool,
) -> bool:
    """写回 FIRST/nullable；返回是否有变化（不动点终止条件）。"""
    changed = False
    if f != first_map[name]:
        first_map[name] = f
        changed = True
    if nullable != nullable_map[name]:
        nullable_map[name] = nullable
        changed = True
    return changed


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
            beta_first, beta_nullable = _seq_first_nullable(
                elems[i + 1 :], first_map, nullable_map
            )
            # repeat/plus 的内部循环后继：下一次迭代的 FIRST。
            # 注意 beta_nullable 仍由后续元素（beta 侧）决定——repeat 自身
            # 可空（0 次迭代），owner FOLLOW 传播条件与循环无关。
            if elem.get("type") in ("repeat", "plus"):
                beta_first |= _elem_first(elem, first_map, nullable_map)
            if body_first is not None:
                beta_first |= body_first
            if _merge_follow(follows, member, owner, beta_first, beta_nullable):
                changed = True
    return changed


def _merge_follow(
    follows: dict[str, set[str]],
    member: str,
    owner: str,
    beta_first: set[str],
    beta_nullable: bool,
) -> bool:
    """把 beta 侧 FIRST（+ 可空时 owner 的 FOLLOW）并入 member 的 FOLLOW。

    member 不在表内（未注册规则名）→ 不写、无变化。
    """
    if member not in follows:
        return False
    before = len(follows[member])
    follows[member] |= beta_first
    if beta_nullable:
        follows[member] |= follows[owner]
    return len(follows[member]) != before


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
    _t = _trace_printer(trace)
    names = set(rules)
    trees = _rule_trees_map(names, rules)
    first_map, nullable_map = _compute_first_nullable(
        names, trees, rules, operator_members
    )

    follows: dict[str, set[str]] = {n: set() for n in names}

    statements, atoms, inline_rules, block_rules = _role_sets(names, rules)

    _t(
        f"rules={len(names)} statements={len(statements)} "
        f"atoms={len(atoms)} inline={len(inline_rules)} block={len(block_rules)}"
    )

    # 块结束符集合（语句循环的后继之一）
    block_ends = _block_end_tokens(block_rules, rules)
    # 语句候选 FIRST 全集（语句循环：任一语句可跟随任一语句）
    stmt_first = _stmt_first_union(statements, first_map)
    _t(f"stmt_first={sorted(stmt_first)} block_ends={sorted(block_ends)}")

    body_first = stmt_first | block_ends
    _inject_statement_loop(follows, statements, body_first)
    if operator_members:
        _inject_operator_members(follows, atoms, operator_members, _t)
    _propagate_fixpoint(
        follows, names, trees, block_rules, first_map, nullable_map, body_first
    )
    _propagate_inline(follows, inline_rules, trees)

    if trace:
        for n in sorted(follows):
            _t(f"FOLLOW({n}) = {sorted(follows[n])}")

    return {n: frozenset(s) for n, s in follows.items()}


def _trace_printer(trace: bool):
    """trace 打印器；关闭时返回空操作（各调用点无需自行判 trace）。"""
    if not trace:
        return lambda _msg: None

    import sys as _sys

    def _t(msg: str) -> None:
        print(f"[follow-trace] {msg}", file=_sys.stderr)

    return _t


def _rule_trees_map(names: set[str], rules: dict[str, GrammarRule]) -> dict[str, list[dict]]:
    """每规则的生产式树；块规则用**内容部分**（`block_prods`）。

    块规则用内容部分建模——block_start/block_end 由块路径单独消费，不是内容
    生产式的一部分（body 循环由 `body_first` 单独注入），与剥离形态保持一致，
    避免块头内部元素 FOLLOW 混入 block_end。
    """
    trees: dict[str, list[dict]] = {}
    for n in names:
        r = rules[n]
        if getattr(r, "is_block", False):
            trees[n] = _prods_trees(
                getattr(r, "block_prods", None) or getattr(r, "prods", []) or []
            )
        else:
            trees[n] = _rule_trees(r)
    return trees


def _role_sets(
    names: set[str], rules: dict[str, GrammarRule]
) -> tuple[set[str], set[str], set[str], set[str]]:
    """角色集合：`(语句, 原子, inline, 块)`。"""
    statements: set[str] = set()
    atoms: set[str] = set()
    inline_rules: set[str] = set()
    block_rules: set[str] = set()
    for n in names:
        r = rules[n]
        if getattr(r, "is_statement", False):
            statements.add(n)
        if getattr(r, "is_atom", False):
            atoms.add(n)
        if getattr(r, "inline", False):
            inline_rules.add(n)
        if getattr(r, "is_block", False):
            block_rules.add(n)
    return statements, atoms, inline_rules, block_rules


def _block_end_tokens(block_rules: set[str], rules: dict[str, GrammarRule]) -> set[str]:
    """块结束符集合（语句循环的后继之一）。"""
    ends: set[str] = set()
    for n in block_rules:
        be = getattr(rules[n], "block_end", "") or ""
        if be:
            ends.add(be)
    return ends


def _stmt_first_union(statements: set[str], first_map: dict) -> set[str]:
    """语句候选 FIRST 全集（语句循环：任一语句可跟随任一语句）。"""
    stmt_first: set[str] = set()
    for s in statements:
        stmt_first |= first_map.get(s, set())
    return stmt_first


def _inject_statement_loop(
    follows: dict[str, set[str]], statements: set[str], body_first: set[str]
) -> None:
    """语句循环注入：每个语句可跟任一语句 FIRST 或块结束符。"""
    for s in statements:
        follows[s] |= body_first


def _inject_operator_members(
    follows: dict[str, set[str]],
    atoms: set[str],
    operator_members: list[str],
    t,
) -> None:
    """pratt 运算符注入：atom 后可跟任意运算符 token。"""
    for a in atoms:
        follows[a] |= set(operator_members)
    t(f"operator injection: {len(atoms)} atoms <- {sorted(operator_members)}")


def _propagate_fixpoint(
    follows: dict[str, set[str]],
    names: set[str],
    trees: dict[str, list[dict]],
    block_rules: set[str],
    first_map: dict,
    nullable_map: dict,
    body_first: set[str],
) -> None:
    """主体方程不动点：逐规则 `_propagate_seq` 直到不再变化。

    块规则：内容 production 之后附 body 循环（nullable 虚拟元素）。
    """
    changed = True
    while changed:
        changed = False
        for name in names:
            if name in block_rules:
                changed |= _propagate_seq(
                    follows,
                    trees[name],
                    name,
                    first_map,
                    nullable_map,
                    body_first=body_first,
                )
            else:
                changed |= _propagate_seq(
                    follows, trees[name], name, first_map, nullable_map
                )


def _propagate_inline(
    follows: dict[str, set[str]], inline_rules: set[str], trees: dict[str, list[dict]]
) -> None:
    """inline 传播：inline 展开后成员直接面对 inline 规则的后继。"""
    for i in inline_rules:
        fi = follows.get(i, set())
        for elem in trees[i]:
            for member in _elem_calls(elem):
                if member in follows:
                    follows[member] |= fi


def token_in_follow(tok_type: str, follow: frozenset[str]) -> bool:
    """检查 token 类型是否属于 FOLLOW 集合（含前缀家族成员）。"""
    for member in follow:
        if member == tok_type:
            return True
        if member.endswith(".") and tok_type.startswith(member):
            return True
    return False
