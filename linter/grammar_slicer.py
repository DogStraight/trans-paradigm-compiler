"""
grammar_slicer.py — 从语法规则推导切片策略

职责：
    读取语法规则（GrammarRule 表），为每个规则推导出"切片模式"，
    供 linter 在扫描时按语法结构精准切分 token 流。

切片模式类型：
    - BlockSlice:  块规则（module→endmodule, always→end），整体跳过
    - DeclSlice:   声明头部规则（module 头, function 头），跳过到分号
    - StmtSlice:   语句规则，由 parse_sentence 处理
    - SkipSlice:   非语句构造，静默跳过
"""

from typing import Any
from core.define import GrammarRule
from parser.block_parser import _get_block_end
from parser.rule_selector import analyze_production_features, _compute_start_tokens

# ── 切片模式类型 ──────────────────────────────────────


class DeclSlice:
    """声明头部切片：从起始 token 到下一个分号（如 module 头 ... ;）"""

    __slots__ = ("start",)

    def __init__(self, start: str):
        self.start = start


class StmtSlice:
    """语句切片：由 parse_sentence 处理"""

    __slots__ = ()


class SkipSlice:
    """跳过切片：静默跳过"""

    __slots__ = ()


# ── 分析入口 ──────────────────────────────────────────


def build_slicing_map(
    rules: dict[str, GrammarRule], stmt_names: list[str]
) -> tuple[dict[str, Any], set[str]]:
    """构建 token 类型 → 切片模式的映射表。

    Args:
        rules: 全部语法规则 {name: GrammarRule}
        stmt_names: 语句级规则名列表（has_pass_end_case=True）

    Returns:
        {token_type: BlockSlice | DeclSlice | StmtSlice | SkipSlice, ...}
    """
    mapping: dict[str, Any] = {}

    # 语句起始 token → StmtSlice
    stmt_starts: set[str] = set()
    for r_name in stmt_names:
        rule = rules.get(r_name)
        if not rule or not rule.prods:
            continue
        feat = analyze_production_features(rule.prods[0])
        if feat:
            stmt_starts |= _compute_start_tokens(feat, rules, set())

    # 块规则 → 块起始为 DeclSlice（跳过头部到终止符），块结束为 SkipSlice
    for rule in rules.values():
        if not getattr(rule, "is_block", False):
            continue
        end = _get_block_end(rule)
        if end:
            mapping.setdefault(end, SkipSlice())
        if not end or not rule.prods:
            continue
        feat = analyze_production_features(rule.prods[0])
        if feat and feat.get("type") == "token":
            tt = feat.get("token_type", "")
            for t in tt.split("|"):
                t = t.strip()
                if t.startswith("keyword."):
                    mapping.setdefault(t, DeclSlice(t))

    # 语句起始 token 覆盖为 StmtSlice（语句规则优先级高于块规则）
    for t in stmt_starts:
        mapping[t] = StmtSlice()

    # 非语句规则 → DeclSlice（有 end_case 但非语句的规则）
    for rule in rules.values():
        if getattr(rule, "is_block", False):
            continue
        name = rule.name
        if name in stmt_names:
            continue
        ec = getattr(rule, "end_case", None)
        if not ec:
            continue
        prods = rule.prods
        if not prods:
            continue
        # 只有在 production 首 token 是 keyword 时才作为 DeclSlice
        feat = analyze_production_features(prods[0])
        if feat and feat.get("type") == "token":
            tt = feat.get("token_type", "")
            for t in tt.split("|"):
                t = t.strip()
                if t.startswith("keyword.") and t not in mapping:
                    mapping.setdefault(t, DeclSlice(t))

    # 终止符：end_case token 中不属于"列表分隔符"的
    # 分隔符检测：扫描所有 production，找 repeat/plus 内 seq 中的非 call 元素
    separators: set[str] = set()
    for rule in rules.values():
        for prod in getattr(rule, "production", []):
            if isinstance(prod, str):
                _find_separators(prod, separators)

    terminators: set[str] = set()
    for rule in rules.values():
        if getattr(rule, "is_block", False):
            continue
        for item in getattr(rule, "end_case", []):
            if isinstance(item, str) and item not in separators and item != "newline":
                terminators.add(item)

    return mapping, terminators


def _find_separators(production: str, result: set[str]) -> None:
    """从 production 字符串中找出列表分隔符 token。"""
    feat = analyze_production_features(production)
    if feat is None:
        return
    _walk_separators(feat, result)


def _walk_separators(feat: dict, result: set[str]) -> None:
    """递归遍历 feature 树，找 repeat/plus 内 seq 中的 token 元素。"""
    typ = feat.get("type")
    if typ in ("repeat", "plus"):
        elem = feat.get("elem")
        if elem and elem.get("type") == "seq":
            for item in elem.get("items", []):
                if item.get("type") == "token":
                    tt = item.get("token_type", "")
                    for t in tt.split("|"):
                        t = t.strip()
                        if t:
                            result.add(t)
    if typ in ("seq", "choice"):
        items = feat.get("items", []) if typ == "seq" else feat.get("alternatives", [])
        for item in items:
            _walk_separators(item, result)
    elif typ in ("repeat", "plus", "optional"):
        elem = feat.get("elem")
        if elem:
            _walk_separators(elem, result)


def build_block_nest_map(rules: dict[str, GrammarRule]) -> tuple[set[str], set[str]]:
    """从块规则推导嵌套起止 token 集合。

    Returns:
        (nest_ins, nest_outs): 进入/退出嵌套时增减 depth 的 token 类型集合
    """
    nest_ins: set[str] = set()
    nest_outs: set[str] = set()
    for rule in rules.values():
        if not getattr(rule, "is_block", False):
            continue
        end = _get_block_end(rule)
        if not end or not rule.prods:
            continue
        feat = analyze_production_features(rule.prods[0])
        if feat and feat.get("type") == "token":
            tt = feat.get("token_type", "")
            for t in tt.split("|"):
                t = t.strip()
                if t.startswith("keyword."):
                    nest_ins.add(t)
        nest_outs.add(end)
    return nest_ins, nest_outs
