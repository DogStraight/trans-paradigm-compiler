# parser/rule_selector.py
import json
import os
from typing import List, Dict, Optional, Set
from core.define import Token, GrammarRule
from parser.feature_analyze import analyze_production_features


def _compute_start_tokens(
    feat: dict,
    grammar_rules: Dict[str, GrammarRule],
    visited: Set[str],
) -> Set[str]:
    """递归计算一个 feature 可能起始的 token 类型集合 (First Set)。"""
    typ = feat.get("type")

    if typ == "token":
        tt = feat.get("token_type", "")
        if "|" in tt:
            return set(tt.split("|"))
        return {tt}

    if typ == "call":
        name = feat.get("name", "")
        if name in visited or name not in grammar_rules:
            return set()
        visited.add(name)
        rule = grammar_rules[name]
        bs = getattr(rule, "block_start", None)
        if bs and isinstance(bs, str) and bs.strip():
            return {bs}
        result: Set[str] = set()
        for prod in getattr(rule, "production", []):
            try:
                pf = analyze_production_features(prod)
            except Exception:
                continue
            if pf:
                result.update(_compute_start_tokens(pf, grammar_rules, visited.copy()))
        return result

    if typ == "choice":
        alts = feat.get("alternatives", [])
        result: Set[str] = set()
        for alt in alts:
            result.update(_compute_start_tokens(alt, grammar_rules, visited.copy()))
        return result

    if typ == "seq":
        items = feat.get("items", [])
        if not items:
            return set()
        return _compute_start_tokens(items[0], grammar_rules, visited.copy())

    if typ in ("repeat", "optional", "plus"):
        elem = feat.get("elem")
        if elem:
            return _compute_start_tokens(elem, grammar_rules, visited.copy())

    return set()


def build_start_token_map_names(
    grammar_rules: Dict[str, GrammarRule],
    statement_rule_names: List[str],
) -> Dict[str, List[str]]:
    """预计算起始 token → 规则名称列表的映射表（可序列化为 JSON）。"""
    name_map: Dict[str, List[str]] = {}
    for name in statement_rule_names:
        if name not in grammar_rules:
            continue
        rule = grammar_rules[name]
        prods = getattr(rule, "production", [])
        if not prods:
            continue
        first_prod_str = prods[0]
        try:
            feat = analyze_production_features(first_prod_str)
        except Exception:
            continue
        if feat is None:
            continue
        starts = _compute_start_tokens(feat, grammar_rules, set())
        for tok in starts:
            if tok not in name_map:
                name_map[tok] = []
            name_map[tok].append(name)
    return name_map


def save_token_map(
    name_map: Dict[str, List[str]], cache_path: str
) -> None:
    """将起始 token 映射表保存到 JSON 文件。"""
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(name_map, f, indent=2, ensure_ascii=False)


def load_token_map(cache_path: str) -> Optional[Dict[str, List[str]]]:
    """从 JSON 文件加载起始 token 映射表。"""
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


_DEFAULT_CACHE_PATH: Optional[str] = None


def set_default_cache_path(path: str) -> None:
    global _DEFAULT_CACHE_PATH
    _DEFAULT_CACHE_PATH = path


class RuleSelector:
    def __init__(
        self,
        grammar_rules: Dict[str, GrammarRule],
        statement_rule_names: List[str],
        cache_path: Optional[str] = None,
    ):
        self.grammar_rules = grammar_rules
        self.statement_rule_names = statement_rule_names
        self.start_token_map: Dict[str, List[str]] = {}
        self._names_to_rules: Optional[Dict[str, GrammarRule]] = None

        # 尝试从缓存加载
        path = cache_path or _DEFAULT_CACHE_PATH
        loaded = load_token_map(path) if path else None
        if loaded:
            self.start_token_map = loaded
        else:
            self.start_token_map = build_start_token_map_names(
                grammar_rules, statement_rule_names
            )
            if path:
                save_token_map(self.start_token_map, path)

    def select_candidates(self, token: Token) -> List[GrammarRule]:
        if token is None:
            return []
        rule_names = self.start_token_map.get(token.type, [])
        if not rule_names:
            return []
        # 按 statement_rule_names 排序
        order = {name: i for i, name in enumerate(self.statement_rule_names)}
        rule_names.sort(key=lambda n: order.get(n, 9999))
        # 名称 → 对象
        result = []
        for name in rule_names:
            if name in self.grammar_rules:
                result.append(self.grammar_rules[name])
        return result

    get_candidate_rules = select_candidates

    def get_block_rule(self, start_token: str) -> Optional[str]:
        for rule_name, rule in self.grammar_rules.items():
            if getattr(rule, "block_start", None) == start_token:
                return rule_name
        return None
