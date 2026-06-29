# parser/end_case_checker.py
"""
end_case_checker.py — 生产式准备 & 结束符检查

职责：_prepare_production（匹配前跳空白），
_check_end_case（检查结束符是否匹配）。
"""

from core.define import GrammarRule
from .parser_context import ParseContext
from .feature_analyze import analyze_production_features


def prepare_production(self, context: ParseContext, features: dict) -> bool:
    """为匹配产生式做准备：跳过空白/注释。返回 False 表示 token 不足。"""
    should_skip = True
    
    if features.get("type") == "token" and features.get("token_type") == "comment":
        should_skip = False
    elif features.get("type") == "call":
        ref_rule = self.grammar_rules.get(features["name"])
        if ref_rule and getattr(ref_rule, "is_block", False):
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
    """检查当前 token 是否匹配规则的终止条件。

    end_case 列表中的 token 支持极性前缀：
      无前缀  — 正匹配：token 在此集合中 → 匹配成功
      ! 前缀  — 反匹配：token 在此集合中 → 匹配失败

    例如: end_case = ["symbol.base.comma", "!symbol.base.dot"]
    """
    if not context.has_more_tokens():
        return True

    token = context.peek_token()
    raw_list = getattr(rule, "end_case", [])

    if token:
        # 分离正/反匹配集合
        pass_tokens: list[str] = []
        fail_tokens: list[str] = []
        for item in raw_list:
            if isinstance(item, str) and item.startswith("!"):
                fail_tokens.append(item[1:])
            else:
                pass_tokens.append(item)

        # 反匹配优先
        if token.type in fail_tokens:
            self._log_state(
                f"✗ end_case(!) 触发: 规则 {rule.name} 遇 '{token.content}' "
                f"(type={token.type})，反匹配 {fail_tokens}",
                context=context,
            )
            return False

        # 正匹配
        if pass_tokens and token.type in pass_tokens:
            return True

    # 没有正匹配项则不检查（非语句级规则）
    if not [t for t in raw_list if not (isinstance(t, str) and t.startswith("!"))]:
        return True

    # 说明 body 由 parse_block 管理，end_case 仅作辅助验证
    for prod in getattr(rule, "production", []):
        try:
            feats = analyze_production_features(prod)
        except Exception:
            continue
        if feats and feats.get("type") == "call":
            inner = self.grammar_rules.get(feats["name"])
            if inner and getattr(inner, "is_block", False):
                return True

    # 增强诊断
    if token:
        self._log_state(
            f"✗ end_case 不匹配: 规则 {rule.name} "
            f"期望 {raw_list}, 实际 '{token.content}' (type={token.type}) "
            f"Ln {token.line}",
            context=context,
        )
    return False
