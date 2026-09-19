"""opt 原语 — 条件可选

Doc: renderer/renderer_architecture.md（opt 可选元素原语）
"""
from typing import Any
from core.define import Node
from ..doc import Doc, Empty
from .registry import register


@register("opt")
def eval_opt(expr: dict, node: Node, parent_layout: dict | None,
             renderer: Any) -> Doc:
    """opt 原语：内层引用全部存在才渲染，任一缺失 → Empty（整体省略）。"""
    inner = expr["opt"]
    if _refs_missing(node, _opt_refs(inner)):
        return Empty()
    inner_doc = renderer._eval(inner, node, parent_layout)
    return inner_doc if inner_doc is not None else Empty()


def _opt_refs(inner) -> list[str]:
    """内层表达式引用的节点属性名（缺失即整体省略）。

    引用可能出现在两处：`line` 各元素（每元素至多一个 ref / join.items），
    以及内层表达式自身（ref / join.items）。
    """
    if not isinstance(inner, dict):
        return []
    refs: list[str] = []
    if "line" in inner:
        for e in inner["line"]:
            refs.extend(_entry_refs(e))
    refs.extend(_entry_refs(inner))
    return refs


def _entry_refs(e) -> list[str]:
    """单个布局字典项的引用名：`ref` 或 `join.items`（非字典项 → 空）。"""
    if not isinstance(e, dict):
        return []
    refs: list[str] = []
    if "ref" in e:
        refs.append(e["ref"])
    if "join" in e and "items" in e:
        refs.append(e["items"])
    return refs


def _refs_missing(node: Node, refs: list[str]) -> bool:
    """任一引用在 node 上取不到（None）→ 该 opt 整体省略。"""
    return any(getattr(node, r, None) is None for r in refs)
