"""
attribute_binder.py — 属性映射绑定 & 路径提取

职责：将 matched_nodes 按规则 node 映射绑定到 rule_node，
以及内联规则扁平化（inline）。
"""

import re
from typing import Any, List, Optional
from core.define import Node, GrammarRule
from .parser_context import ParseContext


def get_attr_by_path(obj: Any, path: str) -> Any:
    """递归路径提取，支持：
    - value.content      → 嵌套属性
    - items[0]           → 列表索引
    - items[*]           → 列表 map
    """
    if obj is None or not path:
        return obj

    first, _, rest = path.partition(".")

    m = re.match(r"^(\w*)\[(\d+|\*)\]$", first)
    if m:
        attr_name = m.group(1)
        index_spec = m.group(2)
        sub = obj
        if attr_name:
            sub = getattr(sub, attr_name, None)
            if sub is None:
                return None
        if index_spec == "*":
            if not isinstance(sub, list):
                return None
            results = []
            for item in sub:
                val = get_attr_by_path(item, rest)
                if val is not None:
                    if isinstance(val, list):
                        results.extend(val)
                    else:
                        results.append(val)
            return results if results else None
        else:
            idx = int(index_spec)
            if isinstance(sub, list) and 0 <= idx < len(sub):
                return get_attr_by_path(sub[idx], rest)
            return None

    sub = getattr(obj, first, None)
    if sub is not None:
        return get_attr_by_path(sub, rest)
    if isinstance(obj, list):
        results = []
        for item in obj:
            val = get_attr_by_path(item, path)
            if val is not None:
                if isinstance(val, list):
                    results.extend(val)
                else:
                    results.append(val)
        return results if results else None
    return None


def extract_from_spec(
    self, spec: str, all_matched_nodes: List[Node]
) -> Any:
    """从属性映射规约中提取值，例如 "$3" 或 "$4.items"；非 $ 引用直接作为字面值返回"""
    if not isinstance(spec, str):
        return None
    try:
        if "." in spec:
            base_part, path = spec.split(".", 1)
            pos = int(base_part.strip("$")) - 1
        else:
            pos = int(spec.strip("$")) - 1
            path = None
    except ValueError:
        return spec
    if 0 <= pos < len(all_matched_nodes):
        sub = all_matched_nodes[pos]
        if path:
            return get_attr_by_path(sub, path)
        return sub
    return None


def bind_attributes(
    self,
    rule_node: Node,
    rule: GrammarRule,
    all_matched_nodes: List[Node],
) -> None:
    """将规则中的属性映射绑定到规则节点上"""
    if not isinstance(getattr(rule, "node", None), dict):
        return
    for attr_name, spec in getattr(rule, "node", {}).items():
        if isinstance(spec, list):
            merged = []
            for item_spec in spec:
                extracted = extract_from_spec(self, item_spec, all_matched_nodes)
                if extracted is not None:
                    if isinstance(extracted, list):
                        merged.extend(extracted)
                    else:
                        merged.append(extracted)
            if merged:
                rule_node.add_attr(attr_name, merged)
        else:
            extracted = extract_from_spec(self, spec, all_matched_nodes)
            if extracted is not None:
                if (
                    isinstance(extracted, Node)
                    and extracted.node_name == "optional"
                ):
                    if not hasattr(extracted, "sub_node") or not extracted.sub_node:
                        continue
                    extracted = extracted.sub_node[0]
                rule_node.add_attr(attr_name, extracted)


def try_inline_rule(
    self,
    rule: GrammarRule,
    all_matched_nodes: List[Node],
    old_node: Optional[Node],
    context: ParseContext,
) -> Optional[Node]:
    """若规则标记为内联且只有一个属性映射，则返回被映射的子节点，否则返回 None。"""
    if not getattr(rule, "inline", False) or len(getattr(rule, "node", {})) != 1:
        return None

    for _, pos_str in getattr(rule, "node", {}).items():
        if not isinstance(pos_str, str):
            continue
        if "." in pos_str:
            base_part, _ = pos_str.split(".", 1)
            try:
                pos = int(base_part.strip("$")) - 1
            except ValueError:
                continue
        else:
            try:
                pos = int(pos_str.strip("$")) - 1
            except ValueError:
                continue
        if not (0 <= pos < len(all_matched_nodes)):
            continue
        inner = all_matched_nodes[pos]
        self._restore_current_node(old_node, context)
        self._log_state(
            f"规则 {rule.name} 内联展开成功 -> "
            f"{inner.node_name if hasattr(inner, 'node_name') else type(inner)}"
        )
        return inner
    return None
