"""
grammar_slicer.py — 从语法规则推导切分层级映射。

职责：
    读取 GrammarRule 的 structure/production/end_case 字段，
    用 parser.rule_selector.analyze_production_features 解析 production，
    为结构消费方（linter 的反解析器 / islands 的片段分片）构建按语法边界切分
    所需的层级映射。

Doc: structure/README.md
"""

from typing import Any

from core.define import GrammarRule
from parser.rule_selector import analyze_production_features
from structure.first_set import first_tokens


def _rule_prods_raw(rule: GrammarRule) -> Any:
    """取规则的 production 源列表。

    块规则用内容部分（block_prods，不含 block_start/block_end）——linter
    匹配块头/定位块 body 基于内容 production（block_start/block_end 另有
    字段）；普通规则用完整 production。方案 B 下块规则 production 保留完整，
    故此处显式取内容部分保持 linter 语义不变。
    """
    if getattr(rule, "is_block", False):
        return getattr(rule, "block_prods", [])
    return getattr(rule, "production", [])


def _parse_alternation(alt: tuple) -> list[dict]:
    """tuple 形态 production（配置层已按 alternation 拆元组）：按 `|` 展开。"""
    parts: list[dict] = []
    for alt_text in alt:
        for part in alt_text.split("|"):
            part = part.strip()
            if not part:
                continue
            feat = analyze_production_features(part)
            if feat is not None:
                parts.append(feat)
    return parts


def _parse_rule_productions(prods_raw: Any) -> list[dict]:
    """规则 production 字段 → 特征树列表。

    str 形态直接解析；tuple 形态展开为分支后，单分支去壳、多分支合成 choice。
    """
    parsed: list[dict] = []
    for p in prods_raw:
        if isinstance(p, str):
            feat = analyze_production_features(p)
            if feat is not None:
                parsed.append(feat)
        elif isinstance(p, tuple):
            parts = _parse_alternation(p)
            if len(parts) == 1:
                parsed.append(parts[0])
            elif parts:
                parsed.append({"type": "choice", "alternatives": parts})
    return parsed


def _slice_entry(rule: GrammarRule) -> dict:
    """单规则 → 切片树条目（字段缺省一律取空，保持 linter 原语义）。"""
    return {
        "prods": _parse_rule_productions(_rule_prods_raw(rule)),
        "exclude": set(getattr(rule, "exclude", []) or []),
        "is_block": getattr(rule, "is_block", False),
        "is_statement": getattr(rule, "is_statement", False),
        "is_atom": getattr(rule, "is_atom", False),
        "pratt": getattr(rule, "pratt", False),
        "inline": getattr(rule, "inline", False),
        "block_start": getattr(rule, "block_start", "") or "",
        "block_end": getattr(rule, "block_end", "") or "",
    }


def build_slice_tree(rules: dict[str, GrammarRule]) -> dict[str, dict]:
    """从 GrammarRule 构建层级切片树。

    使用 parser 已有的 analyze_production_features 解析 production 字符串。
    """
    return {name: _slice_entry(rule) for name, rule in rules.items()}


def get_start_tokens(parsed: list[dict], tree: dict | None = None) -> set[str]:
    """从解析后的 production 列表中提取起始字面量 token 集合。

    只取第一个 top-level 元素的可达 token 类型。
    对于 choice 展开所有分支，可选元素不展开。
    """
    if not parsed:
        return set()
    return _collect_first_start_tokens(parsed[0], tree)


def _collect_first_start_tokens(feat: dict | None, tree: dict | None = None) -> set[str]:
    """强制起始 token（保守语义）——薄封装单一实现，见 structure/first_set.py。"""
    return first_tokens(feat, tree, nullable=False)
