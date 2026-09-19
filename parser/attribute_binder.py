"""
attribute_binder.py — 属性映射绑定 & 路径提取

职责：将 matched_nodes 按规则 node 映射绑定到 rule_node，
以及内联规则扁平化（inline）。
Doc: docs/language_walkthrough.md（node 绑定捕获）
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


def _collect_map(
    items: list, path: str, keep_comments: bool, retain_comments: bool
) -> list | None:
    """逐个 item 递归提取并展平；空结果 → None。

    retain_comments（list-spec 的 `items[*]` 提取）：路径解不出但 item 自身是
    `_comment` 引擎标记时保留该项——repeat 项间上浮的独占注释无 sub_node 等
    结构路径可解，保留自身才能进容器 items（renderer join 作独立行段渲染，
    ADR-0013 B1）。`keep_comments` 只是原样下传（影响更深层的同判据）。
    """
    results: list = []
    for item in items:
        val = get_attr_by_path(item, path, keep_comments)
        if val is None:
            if retain_comments and keep_comments and getattr(item, "_comment", False):
                results.append(item)
            continue
        if isinstance(val, list):
            results.extend(val)
        else:
            results.append(val)
    return results if results else None


def _by_index_spec(
    obj: Any, attr_name: str, index_spec: str, rest: str, keep_comments: bool
) -> Any:
    """`name[N]` / `name[*]` 形态：先取属性，再按索引或逐项 map。"""
    sub = obj
    if attr_name:
        sub = getattr(sub, attr_name, None)
        if sub is None:
            return None
    if index_spec == "*":
        if not isinstance(sub, list):
            return None
        return _collect_map(sub, rest, keep_comments, retain_comments=True)
    idx = int(index_spec)
    if isinstance(sub, list) and 0 <= idx < len(sub):
        return get_attr_by_path(sub[idx], rest, keep_comments)
    return None


def get_attr_by_path(obj: Any, path: str, keep_comments: bool = False) -> Any:
    """递归路径提取，支持：
    - value.content      → 嵌套属性
    - items[0]           → 列表索引
    - items[*]           → 列表 map

    keep_comments（ADR-0013 B1）：list-spec 提取（列表容器 items 绑定）
    时，repeat 迭代项间上浮的 Comment 迭代项（`_comment` 引擎标记）无
    sub_node 等结构路径可解——解析为 None 时保留 Comment 项自身，使其
    进入容器 items（renderer join 识别 _comment 项作独立行段渲染）。
    """
    if obj is None or not path:
        return obj

    first, _, rest = path.partition(".")

    m = _RE_INDEX_PATH.match(first)
    if m:
        return _by_index_spec(obj, m.group(1), m.group(2), rest, keep_comments)

    sub = getattr(obj, first, None)
    if sub is not None:
        return get_attr_by_path(sub, rest, keep_comments)
    if isinstance(obj, list):
        return _collect_map(obj, path, keep_comments, retain_comments=False)
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


def extract_from_spec(
    self, spec: str, all_matched_nodes: list[Node], keep_comments: bool = False
) -> Any:
    """从属性映射规约中提取值，例如 "$3" 或 "$4.items"；非 $ 引用直接作为字面值返回"""
    del self  # 模块级函数，self 命名仅为兼容旧调用，实际不使用
    if not isinstance(spec, str):
        return None
    parsed = _parse_pos_spec(spec)
    if parsed is None:
        return spec
    pos, path = parsed
    if 0 <= pos < len(all_matched_nodes):
        sub = all_matched_nodes[pos]
        if path:
            return get_attr_by_path(sub, path, keep_comments)
        return sub
    return None


class _AttrBinder:
    """把一条规则的 node 映射绑定到规则节点上（含失败诊断）。

    诊断（不改变提取语义，只负责定位绑定失败）：
      - slot 越界（匹配节点列表短于 production）→ WARN。正常匹配流程中
        match_productions 全成功时列表与 production 等长，越界仅出现在
        匹配器缺陷场景，值得暴露而非静默。静态越界（$N > production
        声明 slot 数）已在 GrammarRule 加载时 fail-fast。
      - 路径提取失败（slot 存在但子路径无此属性）→ 按 `_BIND_DIAG` 输出
        DEBUG 级诊断（含 slot 节点现有属性，帮助区分"choice 分支形态
        差异"与"绑定名拼写错误"）。默认静默。
    """

    __slots__ = (
        "parser",
        "nodes",
        "warn",
        "log_state",
        "debug_level",
        "rule_name",
    )

    def __init__(self, parser: Any, rule: GrammarRule, all_matched_nodes: list[Node]):
        self.parser = parser
        self.nodes = all_matched_nodes
        self.warn = getattr(parser, "_warn", None)
        self.log_state = getattr(parser, "_log_state", None)
        self.debug_level = getattr(parser, "LOG_DEBUG", 0)
        self.rule_name = getattr(rule, "name", "?")

    def bind_all(self, rule_node: Node, node_map: dict) -> None:
        """逐属性绑定：list-spec 走合并路径，其余走单值路径。"""
        for attr_name, spec in node_map.items():
            if isinstance(spec, list):
                self._bind_list(rule_node, attr_name, spec)
            else:
                self._bind_one(rule_node, attr_name, spec)

    def _bind_list(self, rule_node: Node, attr_name: str, specs: list) -> None:
        """list-spec（列表容器 items 绑定）：逐个提取并合并。

        保留 Comment 迭代项（ADR-0013 B1：repeat 项间独占注释进 items）。
        """
        merged: list = []
        for item_spec in specs:
            extracted = extract_from_spec(
                self.parser, item_spec, self.nodes, keep_comments=True
            )
            if extracted is None:
                continue
            if isinstance(extracted, list):
                merged.extend(extracted)
            else:
                merged.append(extracted)
        if merged:
            rule_node.add_attr(attr_name, merged)

    def _bind_one(self, rule_node: Node, attr_name: str, spec: Any) -> None:
        """单值 spec：提取 → optional 解壳 → 挂载；失败走诊断。"""
        extracted = extract_from_spec(self.parser, spec, self.nodes)
        if extracted is None:
            self._diagnose(attr_name, spec)
            return
        if isinstance(extracted, Node) and extracted.node_name == "optional":
            children = getattr(extracted, CHILDREN_FIELD, None)
            if not children:
                return
            extracted = children[0]
        rule_node.add_attr(attr_name, extracted)

    def _diagnose(self, attr_name: str, spec: Any) -> None:
        """提取失败定位：slot 越界 → WARN；路径提取失败 → DEBUG（默认静默）。"""
        parsed = _parse_pos_spec(spec) if isinstance(spec, str) else None
        if parsed is None:
            return
        pos, path = parsed
        slot = self.nodes[pos] if 0 <= pos < len(self.nodes) else None
        if slot is None:
            self._warn_slot_missing(attr_name, spec, pos)
        else:
            self._log_path_failed(attr_name, spec, pos, slot, path)

    def _warn_slot_missing(self, attr_name: str, spec: Any, pos: int) -> None:
        """production slot 无匹配节点 → WARN（值得暴露而非静默）。"""
        if self.warn is None:
            return
        self.warn(
            f"属性绑定 {self.rule_name}.{attr_name} = {spec!r} 失败："
            f"第 {pos + 1} 个 production slot 无匹配节点，属性未挂载"
        )

    def _log_path_failed(
        self, attr_name: str, spec: Any, pos: int, slot: Node, path: str | None
    ) -> None:
        """子路径无此属性 → DEBUG 级诊断（含 slot 现有属性）。"""
        if not _BIND_DIAG or self.log_state is None:
            return
        existing = ", ".join(sorted(vars(slot))) or "(none)"
        self.log_state(
            f"节点属性绑定 {self.rule_name}.{attr_name} = {spec!r} "
            f"提取为 None（slot {pos + 1} 节点属性: {existing}；"
            f"路径: {path or '(直接引用)'}）",
            level=self.debug_level,
        )


def bind_attributes(
    self,
    rule_node: Node,
    rule: GrammarRule,
    all_matched_nodes: list[Node],
) -> None:
    """将规则中的属性映射绑定到规则节点上（判据与诊断见 `_AttrBinder`）。"""
    node_map = getattr(rule, "node", None)
    if not isinstance(node_map, dict):
        return
    _AttrBinder(self, rule, all_matched_nodes).bind_all(rule_node, node_map)


def try_inline_rule(
    self,
    rule: GrammarRule,
    all_matched_nodes: list[Node],
    old_node: Node | None,
    context: ParseContext,
) -> Node | None:
    """若规则标记为内联且只有一个属性映射，则返回被映射的子节点，否则返回 None。

    内联展开会**丢弃规则节点**（本规则节点不在 AST 里，父节点直接持有 inner）
    ——挂在它 `_comment_slots` 上的注释（行中 `inline` / 行尾 `trailing` /
    前置 `leading`）会随之消失（实测：`wire a = /* c */ b;` 与
    `wire a = // why\n b;` 两处注释整条丢失，但 `assign` 语句走非 inline
    路径所以不丢）。故展开前把注释槽**迁移到替身节点**（inner）——注释随
    进 AST 的节点一起被渲染器消费。
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
        _transfer_comment_slots(context.current_node, inner)
        self._restore_current_node(old_node, context)
        self._log_state(
            f"规则 {rule.name} 内联展开成功 -> "
            f"{inner.node_name if hasattr(inner, 'node_name') else type(inner)}"
        )
        return inner
    return None


def _merge_into(bucket: list, items) -> None:
    """逐条去重追加（同一注释可能在回溯中重复挂到多处）。"""
    for item in items:
        if item not in bucket:
            bucket.append(item)


def _ensure_slot_dict(target: Node) -> dict:
    """目标节点的注释槽字典（无则挂空字典）。"""
    dst_slots = getattr(target, "_comment_slots", None)
    if dst_slots is None:
        dst_slots = {}
        target.add_attr("_comment_slots", dst_slots)
    return dst_slots


def _merge_slot(dst_slots: dict, key: str, value) -> None:
    """单个槽的迁移：`trailing` 转 `leading`（理由见 `_transfer_comment_slots`），
    dict 形状（锚 → 条目）逐锚合并，list 形状逐条去重，其余原样补缺。"""
    if key == "trailing" and isinstance(value, list):
        _merge_into(dst_slots.setdefault("leading", []), value)
        return
    if isinstance(value, dict):
        dst_map = dst_slots.setdefault(key, {})
        for anchor, entries in value.items():
            _merge_into(dst_map.setdefault(anchor, []), entries)
        return
    if isinstance(value, list):
        _merge_into(dst_slots.setdefault(key, []), value)
        return
    dst_slots.setdefault(key, value)


def _transfer_comment_slots(source: Node | None, target: Node | None) -> None:
    """把即将被丢弃节点的注释槽迁移到替身节点（内联展开用）。

    槽位名与形状原样搬运（`{槽名: [文本]}` / `{槽名: {锚: [(文本, 行)]}}`），
    逐条去重（同一注释可能在回溯中重复挂到多处）。目标已有槽位时合并（源序
    保持：已在场的在前）。

    例外：`trailing`（LineSuffix）在替身节点上会在**该节点 doc 的末尾**落地
    ——排在父布局后续 token（`;`）之前 → 行注释会吞掉终结符（实测
    `wire a = // why\n b;` 输出 `wire a = b // why;`，语法损坏）。故迁移时把
    `trailing` 转为 `leading`（注释 + 换行后接替身节点）：`wire a = // why`
    换行 `b;`，位置与源一致。块注释（行内、不停行）不受此影响——但迁移场景
    下的注释都是行终止型（注释后同行无代码），统一转 `leading`。
    """
    if not isinstance(source, Node) or not isinstance(target, Node):
        return
    src_slots = getattr(source, "_comment_slots", None)
    if not src_slots:
        return
    dst_slots = _ensure_slot_dict(target)
    for key, value in src_slots.items():
        _merge_slot(dst_slots, key, value)
