"""
grammar_slicer.py — 从语法规则推导切分层级映射。

职责：
    读取 GrammarRule 的 structure/production/end_case 字段，
    用 parser.rule_selector.analyze_production_features 解析 production，
    为 linter 构建按语法边界切分所需的层级映射。

Doc: linter/linter_architecture.md
"""

from core.define import GrammarRule
from parser.rule_selector import analyze_production_features


def build_slice_tree(rules: dict[str, GrammarRule]) -> dict[str, dict]:
    """从 GrammarRule 构建层级切片树。

    使用 parser 已有的 analyze_production_features 解析 production 字符串。
    """
    tree: dict[str, dict] = {}
    for name, rule in rules.items():
        # 块规则用内容部分（block_prods，不含 block_start/block_end）——linter
        # 匹配块头/定位块 body 基于内容 production（block_start/block_end 另有
        # 字段）；普通规则用完整 production。方案 B 下块规则 production 保留完整，
        # 故此处显式取内容部分保持 linter 语义不变。
        if getattr(rule, "is_block", False):
            prods_raw = getattr(rule, "block_prods", [])
        else:
            prods_raw = getattr(rule, "production", [])
        parsed = []
        for p in prods_raw:
            if isinstance(p, str):
                feat = analyze_production_features(p)
                if feat is not None:
                    parsed.append(feat)
            elif isinstance(p, tuple):
                parts = []
                for alt_text in p:
                    for part in alt_text.split("|"):
                        part = part.strip()
                        if part:
                            feat = analyze_production_features(part)
                            if feat is not None:
                                parts.append(feat)
                if len(parts) == 1:
                    parsed.append(parts[0])
                elif parts:
                    parsed.append({"type": "choice", "alternatives": parts})
        tree[name] = {
            "prods": parsed,
            "exclude": set(getattr(rule, "exclude", []) or []),
            "is_block": getattr(rule, "is_block", False),
            "is_statement": getattr(rule, "is_statement", False),
            "is_atom": getattr(rule, "is_atom", False),
            "pratt": getattr(rule, "pratt", False),
            "inline": getattr(rule, "inline", False),
            "block_start": getattr(rule, "block_start", "") or "",
            "block_end": getattr(rule, "block_end", "") or "",
        }
    return tree


def get_start_tokens(parsed: list[dict], tree: dict | None = None) -> set[str]:
    """从解析后的 production 列表中提取起始字面量 token 集合。

    只取第一个 top-level 元素的可达 token 类型。
    对于 choice 展开所有分支，可选元素不展开。
    """
    if not parsed:
        return set()
    return _collect_first_start_tokens(parsed[0], tree)


def _collect_first_start_tokens(feat: dict | None, tree: dict | None = None) -> set[str]:
    """递归收集单个元素的起始 token。"""
    if feat is None:
        return set()
    typ = feat.get("type")
    if typ == "token":
        return {feat["token_type"]}
    if typ == "call":
        if tree is None:
            return set()
        name = feat.get("name", "")
        info = tree.get(name)
        if info is None:
            return set()
        # 块规则：block_start 已从 production 剥离（如 BeginEnd 的 keyword.begin），
        # 需并入 firsts——否则 @BeginEnd 等块候选的首 token 收集缺失，导致
        # Stmt/CtrlStmt firsts 漏掉 begin（matcher @Stmt 起始校验失灵）。
        result: set[str] = set()
        bs = info.get("block_start") or ""
        if bs:
            result.add(bs)
        # inline 规则取第一个 production 的 First 集
        prods = info.get("prods", [])
        if not prods:
            return result
        result |= _collect_first_start_tokens(prods[0], tree)
        return result
    if typ == "optional":
        # 可选元素的第一 token 不是强制起始
        return set()
    if typ == "choice":
        result: set[str] = set()
        for alt in feat.get("alternatives", []):
            result |= _collect_first_start_tokens(alt, tree)
        return result
    if typ == "seq":
        items = feat.get("items", [])
        if items:
            return _collect_first_start_tokens(items[0], tree)
        return set()
    if typ in ("repeat", "plus"):
        elem = feat.get("elem")
        if elem:
            return _collect_first_start_tokens(elem, tree)
        return set()
    return set()
