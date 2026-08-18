"""
attribute_binder.py — 属性映射绑定 & 路径提取

职责：将 matched_nodes 按规则 node 映射绑定到 rule_node，
以及内联规则扁平化（inline）。
"""

import re
from typing import Any
from core.define import Node, GrammarRule, CHILDREN_FIELD
from .parser_core import ParseContext

# 预编译路径解析正则（避免每调用重新编译）
_RE_INDEX_PATH = re.compile(r"^(\w*)\[(\d+|\*)\]$")

# 绑定诊断开关：0 = 静默（默认）——choice 分支形态差异导致的路径提取失败
# 是设计语义（真实样本单文件上千处，见 parser/attribute_binder 绑定诊断）；
# 1 = 路径提取失败时输出 DEBUG 级诊断（写入 parser 日志文件，供语法包
# 作者排查绑定失败根因，区分"分支形态差异"与"绑定名拼写错误"）。
_BIND_DIAG = 0


def get_attr_by_path(obj: Any, path: str) -> Any:
    """递归路径提取，支持：
    - value.content      → 嵌套属性
    - items[0]           → 列表索引
    - items[*]           → 列表 map
    """
    if obj is None or not path:
        return obj

    first, _, rest = path.partition(".")

    m = _RE_INDEX_PATH.match(first)
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


def _parse_pos_spec(spec: str) -> tuple[int, str | None] | None:
    """解析 $N 或 $N.path 位置规约 → (pos_index, path)。非法返回 None。"""
    if not spec:
        return None
    try:
        if "." in spec:
            base_part, path = spec.split(".", 1)
            return int(base_part.strip("$")) - 1, path
        return int(spec.strip("$")) - 1, None
    except ValueError:
        return None


def extract_from_spec(self, spec: str, all_matched_nodes: list[Node]) -> Any:
    """从属性映射规约中提取值，例如 "$3" 或 "$4.items"；非 $ 引用直接作为字面值返回"""
    if not isinstance(spec, str):
        return None
    parsed = _parse_pos_spec(spec)
    if parsed is None:
        return spec
    pos, path = parsed
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
    all_matched_nodes: list[Node],
) -> None:
    """将规则中的属性映射绑定到规则节点上。

    诊断（不改变提取语义，只负责定位绑定失败）：
      - slot 越界（匹配节点列表短于 production）→ WARN。正常匹配流程中
        match_productions 全成功时列表与 production 等长，越界仅出现在
        匹配器缺陷场景，值得暴露而非静默。静态越界（$N > production
        声明 slot 数）已在 GrammarRule 加载时 fail-fast。
      - 路径提取失败（slot 存在但子路径无此属性）→ 按 _BIND_DIAG 输出
        DEBUG 级诊断（含 slot 节点现有属性，帮助区分"choice 分支形态
        差异"与"绑定名拼写错误"）。默认静默。
    """
    node_map = getattr(rule, "node", None)
    if not isinstance(node_map, dict):
        return
    warn = getattr(self, "_warn", None)
    log_state = getattr(self, "_log_state", None)
    debug_level = getattr(self, "LOG_DEBUG", 0)
    rule_name = getattr(rule, "name", "?")
    for attr_name, spec in node_map.items():
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
            continue
        extracted = extract_from_spec(self, spec, all_matched_nodes)
        if extracted is None:
            parsed = _parse_pos_spec(spec) if isinstance(spec, str) else None
            if parsed is not None:
                pos, path = parsed
                slot = (
                    all_matched_nodes[pos]
                    if 0 <= pos < len(all_matched_nodes)
                    else None
                )
                if slot is None and warn is not None:
                    warn(
                        f"属性绑定 {rule_name}.{attr_name} = {spec!r} 失败："
                        f"第 {pos + 1} 个 production slot 无匹配节点，属性未挂载"
                    )
                elif slot is not None and _BIND_DIAG and log_state is not None:
                    existing = ", ".join(sorted(vars(slot))) or "(none)"
                    log_state(
                        f"节点属性绑定 {rule_name}.{attr_name} = {spec!r} "
                        f"提取为 None（slot {pos + 1} 节点属性: {existing}；"
                        f"路径: {path or '(直接引用)'}）",
                        level=debug_level,
                    )
            continue
        if isinstance(extracted, Node) and extracted.node_name == "optional":
            if not hasattr(extracted, CHILDREN_FIELD) or not getattr(
                extracted, CHILDREN_FIELD
            ):
                continue
            extracted = getattr(extracted, CHILDREN_FIELD)[0]
        rule_node.add_attr(attr_name, extracted)


def try_inline_rule(
    self,
    rule: GrammarRule,
    all_matched_nodes: list[Node],
    old_node: Node | None,
    context: ParseContext,
) -> Node | None:
    """若规则标记为内联且只有一个属性映射，则返回被映射的子节点，否则返回 None。

    内联前：如果当前规则节点（即将被丢弃）有 Comment 子节点，
    将它们转发到 old_node（父节点），避免行间注释丢失。
    """
    if not getattr(rule, "inline", False) or len(getattr(rule, "node", {})) != 1:
        return None

    for _, pos_str in getattr(rule, "node", {}).items():
        if not isinstance(pos_str, str):
            continue
        parsed = _parse_pos_spec(pos_str)
        if parsed is None:
            continue
        pos, _ = parsed
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
