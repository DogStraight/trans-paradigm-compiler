"""
rule_matcher.py — 生产式匹配核心 + 结束符检查

职责：_process_production_node（dispatch），
_match_productions（循环匹配产生式列表），
_try_rule_productions（单规则匹配全流程），
_prepare_production / _check_end_case（结束符检查）。
"""

from core.define import Node, GrammarRule
from .parser_core import ParseContext


def process_production_node(self, node: dict, context: ParseContext) -> Node | None:
    """dispatch 到 _parse_* 方法"""
    typ = node.get("type")
    method_name = f"_parse_{typ}"
    method = getattr(self, method_name, None)
    if method is None:
        self._log_state(f"未知节点类型: {typ}")
        return None
    return method(node, context)


def _get_recovery_cfg(self, rule: GrammarRule) -> dict | None:
    """读取规则的 recovery 配置"""
    p = getattr(rule, "parser", {})
    if isinstance(p, dict):
        return p.get("recovery")
    return None


def _get_prod_features(self, rule: GrammarRule, prod: str) -> dict | None:
    """获取产生式特征，带缓存"""
    cache = getattr(rule, "_prod_cache", None)
    if cache is None:
        cache = {}
        setattr(rule, "_prod_cache", cache)
    if prod not in cache:
        from .rule_selector import analyze_production_features

        cache[prod] = analyze_production_features(prod)
    return cache[prod]


def _try_production(
    self, context: ParseContext, prod: str, rule: GrammarRule, committed: bool
) -> Node | None:
    """尝试匹配单个产生式，失败时如果已提交则产 ErrorNode（吞行）"""
    features = _get_prod_features(self, rule, prod)
    if not features:
        return None
    if not self._prepare_production(context, features):
        return None

    snapshot = context.create_snapshot()
    result = process_production_node(self, features, context)
    if result is not None:
        return result

    # 匹配失败
    context.restore_snapshot(snapshot)

    # 已提交 → 产 ErrorNode（吞行）
    if committed:
        err = Node("Error")
        tokens = []
        # 如果是在匹配具体 token 时失败，也停在该 token 类型上
        stop_types = {"newline"}
        expected_token = None
        if features.get("type") == "token":
            expected_token = features["token_type"]
            stop_types.add(expected_token)
        while context.has_more_tokens():
            t = context.peek_token()
            if t is not None and t.type in stop_types:
                if t.type == expected_token:
                    context.advance_token()  # 消费预期的终止符（如 )），上层不用再管
                break
            if t is not None:
                tokens.append(t)
                context.advance_token()
            else:
                break
        if tokens:
            err.add_attr("raw", " ".join(t.content for t in tokens))
        return err

    return None


def match_productions(
    self, context: ParseContext, rule: GrammarRule
) -> tuple[list[Node | None] | None, Node | None]:
    """匹配规则的所有产生式。

    返回 (matched_nodes, error_node)：
        matched_nodes=None & error_node=None → 全部失败（未提交）
        matched_nodes=[] & error_node=Node   → 提交后部分失败
        matched_nodes=[...] & error_node=None → 完全成功
    """
    recovery = _get_recovery_cfg(self, rule)
    after = None
    committed = False  # 无 recovery → 严格回溯
    if recovery and isinstance(recovery, dict):
        after = recovery.get("after")
        committed = after is not None  # 有 after 显式指定时才提交

    all_matched_nodes = []
    for prod in getattr(rule, "production", []):
        self._log_state(
            f"处理产生式: {prod} | {self._debug_token_info(context)}",
            context=context,
        )

        result_node = _try_production(self, context, prod, rule, committed)
        if result_node is None:
            # 未提交且匹配失败 → 全部失败
            return None, None

        if result_node.node_name == "Error" and committed:
            # 已提交后产出的 ErrorNode → 部分成功
            all_matched_nodes.append(result_node)
            return all_matched_nodes, result_node

        all_matched_nodes.append(result_node)

        # 检查是否到达提交点
        if not committed and after and after in prod:
            committed = True

    return all_matched_nodes, None


def try_rule_productions(self, context: ParseContext, rule: GrammarRule) -> Node | None:
    """尝试匹配一个语法规则的全部逻辑"""
    # Pratt 规则
    if getattr(rule, "pratt", False):
        return self._try_pratt_rule(context, rule)

    # 作用域推入（如规则有 scope 声明）
    rule_parser = getattr(rule, "parser", {})
    scope_def = rule_parser.get("scope") if isinstance(rule_parser, dict) else None
    scope_pushed = False
    if scope_def and isinstance(scope_def, dict):
        scope_kind = scope_def.get("kind", rule.name)
        scope_name = rule.name
        self.scope_stack.push(scope_name, scope_kind)
        scope_pushed = True

    # 语义路径：规则自然序 +1，入栈（block 规则也走此路径）
    sn = context.sibling_counter.get(rule.name, 0)
    context.sibling_counter[rule.name] = sn + 1
    seg = f"{rule.name}[{sn}]"
    context.path_stack.append(seg)

    # 块规则
    if getattr(rule, "is_block", False):
        result = self.parse_block(context, start_token="", rule=rule)
        context.path_stack.pop()
        if scope_pushed:
            self.scope_stack.pop()
        return result

    # 记录失败尝试（仅调试收集模式）
    current_token = context.peek_token()
    if getattr(self, "_collect_failures", False):
        self._failure_attempts.append(
            {
                "rule": rule.name,
                "token": str(current_token.content) if current_token else "EOF",
                "token_index": context.token_pointer,
                "token_type": current_token.type if current_token else "EOF",
                "path": "/".join(context.path_stack),
            }
        )

    self._log_state(
        f"尝试匹配规则: {rule.name} | {self._debug_token_info(context)}",
        context=context,
    )
    context.update_current_rule(rule)

    rule_node = Node(rule.name)
    old_node = context.current_node
    context.update_current_node(rule_node)

    all_matched_nodes, error_node = match_productions(self, context, rule)
    if all_matched_nodes is None and error_node is None:
        context.path_stack.pop()
        if scope_pushed:
            self.scope_stack.pop()
        return None

    # 部分成功：有 error_node 时标记规则节点
    if error_node is not None:
        rule_node.add_attr("_error", error_node)

    # 属性绑定
    self._bind_attributes(rule_node, rule, all_matched_nodes or [])

    # 有 error 的规则跳过 end_case 检查（已处于错误状态）
    if error_node is None and not self._check_end_case(context, rule):
        self._restore_current_node(old_node, context)
        context.path_stack.pop()
        if scope_pushed:
            self.scope_stack.pop()
        return None

    # Inline 扁平化（不扁平包含 error 的规则）
    if error_node is None:
        inline_result = self._try_inline_rule(
            rule, all_matched_nodes, old_node, context
        )
        if inline_result is not None:
            context.path_stack.pop()
            if scope_pushed:
                self.scope_stack.pop()
            return inline_result

    self._restore_current_node(old_node, context)
    self._log_state(f"✓ 规则 {rule.name} 匹配成功", context=context)
    context.path_stack.pop()
    if scope_pushed:
        self.scope_stack.pop()
    return rule_node


# parser/end_case_checker.py
"""
end_case_checker.py — 生产式准备 & 结束符检查

职责：_prepare_production（匹配前跳空白），
_check_end_case（检查结束符是否匹配）。
"""

from core.define import GrammarRule
from .parser_core import ParseContext
from .rule_selector import analyze_production_features


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
