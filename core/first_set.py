"""first_set.py — FIRST / nullable 的**单一实现**（引擎通用，无语言知识）。

为什么在 core（D10 尾项，作者 2026-11-09 批准）：同一组递归方程曾有两份实现——
`parser/follow.py` 的规则级不动点（FIRST+nullable 表）与 `linter/first_set.py` 的
元素树递归。两份吃同一套元素树（`{"type": "token"|"seq"|"choice"|"call"|
"optional"|"repeat"|"plus"}`）、解同一组方程；本模块合并二者，差异用参数表达：

  nullable=False  强制起始（保守）：optional 视为空集；seq 只看首元素；call 不越过
                  可空前缀。用于**前缀判别**（lookahead / slicer）。
  nullable=True   可能起始：optional/repeat 下钻；seq 按可空前缀传播；call 在首元素
                  可空时并入后续元素。用于**候选筛选**（matcher）。

输入是**规则视图**（不依赖 `GrammarRule`）：

    view: dict[str, {"prods": list[elem_tree], "block_start": str}]

  - parser 侧构造器只对 `is_block` 规则填 `block_start`；
  - linter 侧 `_slice_entry` 原样提供（本模块只读 `prods` / `block_start`）。

FOLLOW 方程**不在本模块**：它读 `is_statement`/`is_atom`/`inline`/`pratt` 等引擎
角色，属 parser 上层知识；`parser/follow.py` 保留 FOLLOW，用本模块的
`_elem_first` / `_elem_nullable` / `_seq_first_nullable` 基元做传播。
Doc: linter/linter_architecture.md（FIRST/nullable 两口径）
"""
from __future__ import annotations

from core.token_protocol import split_token_types

#: 可空元素类型：nullable=True 时其"后面那个元素"也算可能起始
_NULLABLE_TYPES = ("optional", "repeat")
#: 可下钻到 elem 的包装类型
_WRAPPER_TYPES = ("optional", "repeat", "plus")


def _token_types(feat: dict) -> set[str]:
    """token 元素的类型集合（`token_type` 多候选拆开；空声明 = 空集）。"""
    decl = str(feat.get("token_type") or "")
    return split_token_types(decl) if decl else set()


def first_tokens(
    feat: dict | None,
    view: dict | None,
    *,
    nullable: bool,
    visited: frozenset[str] = frozenset(),
) -> set[str]:
    """计算 feature 的起始 token 集合；`nullable` 两口径见模块 docstring。"""
    if not isinstance(feat, dict):
        return set()
    typ = str(feat.get("type") or "")
    if typ == "token":
        return _token_types(feat)
    handler = {"choice": _choice_firsts, "seq": _seq_firsts, "call": _call_firsts}.get(typ)
    if handler is not None:
        return handler(feat, view, nullable=nullable, visited=visited)
    if typ in _WRAPPER_TYPES:
        return _wrapper_firsts(feat, view, typ, nullable=nullable, visited=visited)
    return set()


def nullable_after(
    items: list, view: dict | None, visited: frozenset[str]
) -> set[str]:
    """可空前缀传播：从首元素起逐个并入 first，遇非可空元素停止。"""
    out: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            break
        out |= first_tokens(item, view, nullable=True, visited=visited)
        if item.get("type") not in _NULLABLE_TYPES:
            break
    return out


def _choice_firsts(
    feat: dict, view: dict | None, *, nullable: bool, visited: frozenset[str]
) -> set[str]:
    out: set[str] = set()
    for alt in feat.get("alternatives", []) or []:
        out |= first_tokens(alt, view, nullable=nullable, visited=visited)
    return out


def _seq_firsts(
    feat: dict, view: dict | None, *, nullable: bool, visited: frozenset[str]
) -> set[str]:
    items = feat.get("items", []) or []
    if not items:
        return set()
    if nullable:
        return nullable_after(items, view, visited)
    return first_tokens(items[0], view, nullable=False, visited=visited)


def _wrapper_firsts(
    feat: dict, view: dict | None, typ: str, *, nullable: bool, visited: frozenset[str]
) -> set[str]:
    if typ == "optional" and not nullable:
        return set()  # 保守语义：可选元素的首 token 不是强制起始
    return first_tokens(feat.get("elem"), view, nullable=nullable, visited=visited)


def _call_firsts(
    feat: dict, view: dict | None, *, nullable: bool, visited: frozenset[str]
) -> set[str]:
    """`@rule` 引用：并入 block_start（块起始已从 production 剥离）+ 首个 production。"""
    if view is None:
        return set()
    name = feat.get("name", "")
    if not name or name in visited:
        return set()
    info = view.get(name)
    if not info:
        return set()
    out: set[str] = set()
    block_start = info.get("block_start") or ""
    if block_start:
        out.add(block_start)
    prods = info.get("prods", []) or []
    first = prods[0] if prods and isinstance(prods[0], dict) else None
    if first is None:
        return out
    deeper = visited | {name}
    out |= first_tokens(first, view, nullable=nullable, visited=deeper)
    if nullable and first.get("type") in _NULLABLE_TYPES:
        out |= nullable_after(prods[1:], view, deeper)
    return out


# ── 规则级不动点（parser 口径；供 compute_first_map / compute_follows 复用）──


def _elem_first(elem: dict, first_map: dict, nullable_map: dict) -> set[str]:
    """元素树在已知 FIRST/nullable 表上的 FIRST（不含 ε）。"""
    typ = elem.get("type")
    if typ == "token":
        return _token_types(elem)
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
    if typ in _WRAPPER_TYPES:
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
        return all(_elem_nullable(i, nullable_map) for i in elem.get("items", []))
    if typ == "choice":
        return any(_elem_nullable(a, nullable_map) for a in elem.get("alternatives", []))
    if typ in _NULLABLE_TYPES:
        return True
    if typ == "plus":
        return _elem_nullable(elem.get("elem", {}), nullable_map)
    return False


def _seq_first_nullable(
    elems: list[dict], first_map: dict[str, set[str]], nullable_map: dict[str, bool]
) -> tuple[set[str], bool]:
    """序列的 `(FIRST 并集, 是否整体可空)`；遇首个不可空元素即停。"""
    first: set[str] = set()
    nullable = True
    for elem in elems:
        first |= _elem_first(elem, first_map, nullable_map)
        if not _elem_nullable(elem, nullable_map):
            nullable = False
            break
    return first, nullable


def _seed_maps(
    view: dict[str, dict], seeds: dict[str, set[str]] | None
) -> tuple[dict[str, set[str]], dict[str, bool]]:
    """初始表：块规则 block_start 种子 + 调用方注入的 seeds（如 pratt 运算符）。"""
    names = set(view)
    first_map: dict[str, set[str]] = {n: set() for n in names}
    nullable_map: dict[str, bool] = {n: False for n in names}
    for name in names:
        block_start = view[name].get("block_start") or ""
        if block_start:
            first_map[name] = {block_start}
        if seeds:
            first_map[name] |= set(seeds.get(name, ()))
    return first_map, nullable_map


def _relax_once(
    view: dict[str, dict], first_map: dict[str, set[str]], nullable_map: dict[str, bool]
) -> bool:
    """一轮不动点松弛；返回是否有变化（终止条件）。"""
    changed = False
    for name, info in view.items():
        if info.get("block_start"):
            continue  # 块规则：FIRST 已种子化，跳过迭代覆盖
        new_first, nullable = _seq_first_nullable(
            list(info.get("prods") or []), first_map, nullable_map
        )
        new_first |= first_map[name]  # 保留种子
        if new_first != first_map[name]:
            first_map[name] = new_first
            changed = True
        if nullable != nullable_map[name]:
            nullable_map[name] = nullable
            changed = True
    return changed


def rule_first_nullable(
    view: dict[str, dict], seeds: dict[str, set[str]] | None = None
) -> tuple[dict[str, set[str]], dict[str, bool]]:
    """规则级 FIRST / nullable 不动点（处理递归引用）。

    `seeds`：调用方注入的额外 FIRST 种子（parser 用它注入 pratt 运算符家族；
    linter 不传）。块规则种子 = `block_start`，且**不参与迭代覆盖**。
    """
    first_map, nullable_map = _seed_maps(view, seeds)
    while _relax_once(view, first_map, nullable_map):
        pass
    return first_map, nullable_map
