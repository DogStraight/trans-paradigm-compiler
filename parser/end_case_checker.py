"""
end_case_checker.py — 生产式准备 & 结束符检查

职责：_prepare_production（匹配前跳空白），
_check_end_case（检查结束符是否匹配）。
"""

from typing import Optional
from core.define import GrammarRule
from .parser_context import ParseContext
from .feature_analyze import analyze_production_features


def prepare_production(self, context: ParseContext, features: dict) -> bool:
    """为匹配产生式做准备：跳过空白/注释。返回 False 表示 token 不足。"""
    should_skip = True
    if features.get("type") == "call":
        ref_rule = self.grammar_rules.get(features["name"])
        if ref_rule and getattr(ref_rule, "block_start", None):
            should_skip = False
    elif features.get("type") in ("optional",):
        should_skip = False
    elif features.get("type") == "repeat" and features.get("min", 0) == 0:
        should_skip = False
    if should_skip:
        self._skip_tokens(context, tuple(self.skip_types))
        if not context.has_more_tokens():
            return False
    return True


def check_end_case(self, context: ParseContext, rule: GrammarRule) -> bool:
    """检查当前 token 是否匹配规则的结束符。匹配返回 True，不匹配返回 False。"""
    if not getattr(rule, "end_case", None) or not context.has_more_tokens():
        return True

    token = context.peek_token()
    if token and token.type in getattr(rule, "end_case", []):
        return True

    # 说明 body 由 parse_block 管理，end_case 仅作辅助验证
    for prod in getattr(rule, "production", []):
        try:
            feats = analyze_production_features(prod)
        except Exception:
            continue
        if feats and feats.get("type") == "call":
            inner = self.grammar_rules.get(feats["name"])
            if inner and isinstance(getattr(inner, "block_start", None), str):
                return True
    return False
