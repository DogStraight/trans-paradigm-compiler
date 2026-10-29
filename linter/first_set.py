"""first_set.py — FIRST 集的**单一实现**（可空传播由开关控制）。

历史：同一事实有两份实现（`grammar_slicer` 的保守版 = 强制起始；`matcher` 的
可空传播版 = 可能起始），语义不同却都叫 first，且 matcher 的 docstring 说"必然"
而实现对 optional 按"可能"处理（自相矛盾）。合并为一份，用 `nullable` 开关表达
两种语义：

  nullable=False  强制起始（保守）：optional 视为空集；seq 只看首元素；
                  call 不越过可空前缀。用于**前缀判别**（lookahead/slicer）。
  nullable=True   可能起始：optional/repeat 下钻；seq 按可空前缀传播；
                  call 在首元素可空时并入后续元素。用于**候选筛选**（matcher）。

两者都不是"错"的——错的是让它们各自长大且互不知情。
Doc: linter/linter_architecture.md（前瞻消歧 / 匹配器 first 口径）
"""
from __future__ import annotations

from core.token_protocol import split_token_types

# 可空元素类型：nullable=True 时其"后面那个元素"也算可能起始
_NULLABLE_TYPES = ("optional", "repeat")
# 可下钻到 elem 的包装类型
_WRAPPER_TYPES = ("optional", "repeat", "plus")


def nullable_after(items: list, tree: dict | None, visited: frozenset[str]) -> set[str]:
    """可空前缀传播：从首元素起逐个并入 first，遇非可空元素停止。"""
    out: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            break
        out |= first_tokens(item, tree, nullable=True, visited=visited)
        if item.get("type") not in _NULLABLE_TYPES:
            break
    return out


def first_tokens(
    feat: dict | None,
    tree: dict | None,
    *,
    nullable: bool,
    visited: frozenset[str] = frozenset(),
) -> set[str]:
    """计算 feature 的起始 token 集合；`nullable` 见模块 docstring。"""
    if not isinstance(feat, dict):
        return set()
    typ = str(feat.get("type") or "")
    if typ == "token":
        return split_token_types(feat.get("token_type", ""))
    handler = {"choice": _choice_firsts, "seq": _seq_firsts, "call": _call_firsts}.get(typ)
    if handler is not None:
        return handler(feat, tree, nullable=nullable, visited=visited)
    if typ in _WRAPPER_TYPES:
        return _wrapper_firsts(feat, tree, typ, nullable=nullable, visited=visited)
    return set()


def _choice_firsts(
    feat: dict, tree: dict | None, *, nullable: bool, visited: frozenset[str]
) -> set[str]:
    out: set[str] = set()
    for alt in feat.get("alternatives", []) or []:
        out |= first_tokens(alt, tree, nullable=nullable, visited=visited)
    return out


def _seq_firsts(
    feat: dict, tree: dict | None, *, nullable: bool, visited: frozenset[str]
) -> set[str]:
    items = feat.get("items", []) or []
    if not items:
        return set()
    if nullable:
        return nullable_after(items, tree, visited)
    return first_tokens(items[0], tree, nullable=False, visited=visited)


def _wrapper_firsts(
    feat: dict, tree: dict | None, typ: str, *, nullable: bool, visited: frozenset[str]
) -> set[str]:
    if typ == "optional" and not nullable:
        return set()  # 保守语义：可选元素的首 token 不是强制起始
    return first_tokens(feat.get("elem"), tree, nullable=nullable, visited=visited)


def _call_firsts(
    feat: dict, tree: dict | None, *, nullable: bool, visited: frozenset[str]
) -> set[str]:
    """`@rule` 引用：并入 block_start（块起始已从 production 剥离）+ 首个 production。"""
    if tree is None:
        return set()
    name = feat.get("name", "")
    if not name or name in visited:
        return set()
    info = tree.get(name)
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
    out |= first_tokens(first, tree, nullable=nullable, visited=deeper)
    if nullable and first.get("type") in _NULLABLE_TYPES:
        out |= nullable_after(prods[1:], tree, deeper)
    return out
