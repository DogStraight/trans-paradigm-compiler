"""
rule_matcher.py — 生产式匹配核心 + 结束符检查

职责：_process_production_node（dispatch），
_match_productions（循环匹配产生式列表），
_try_rule_productions（单规则匹配全流程），
_prepare_production / _check_end_case（结束符检查）。
"""

from core.define import Node, GrammarRule
from .parser_core import ParseContext


def _first_token_of_spec(spec: str, grammar_rules: dict) -> set[str]:
    """计算一个产生式规格字符串的起始 token 类型集合。

    支持:
        "symbol.base.semicolon" → {"symbol.base.semicolon"}
        "@Identifier"          → 查找规则的第一个 token
        "keyword.module"       → {"keyword.module"}
        "@PortParens?"         → 去除 ? 后查找规则
    """
    raw = spec.rstrip("?+*")
    if raw.startswith("@"):
        rule = grammar_rules.get(raw[1:])
        if rule:
            prods = getattr(rule, "production", [])
            if prods:
                return _first_token_of_spec(prods[0], grammar_rules)
        return set()
    return {raw}


def _find_sync_token(rule: GrammarRule, from_index: int, grammar_rules: dict) -> set[str]:
    """从产生式列表中查找第 from_index 个元素之后的同步 token 集合。

    跳过 optional/repeat 元素，找到第一个非可选产生式的起始 token。
    如果到末尾都没有找到，使用规则的 end_case。
    """
    prods = getattr(rule, "production", [])
    for i in range(from_index, len(prods)):
        prod = prods[i]
        # 跳过带 ? 的可选元素和 * 的重复元素
        if prod.endswith("?") or prod.endswith("*"):
            continue
        tokens = _first_token_of_spec(prod, grammar_rules)
        if tokens:
            return tokens
    # 兜底：使用 end_case
    ec = getattr(rule, "end_case", [])
    return {t for t in ec if isinstance(t, str) and not t.startswith("!")}


# 括号匹配映射
_BRACKET_MAP = {
    "bracket.l_parentheses": "bracket.r_parentheses",
    "bracket.l_brace": "bracket.r_brace",
    "bracket.l_bracket": "bracket.r_bracket",
}
_INVERSE_BRACKET_MAP = {v: k for k, v in _BRACKET_MAP.items()}


def _find_current_end(spec: str, grammar_rules: dict) -> set[str]:
    """计算一个产生式规格字符串的自然结束 token。

    例如:
        "@PortParens?"  → {"bracket.r_parentheses"}
        "symbol.base.semicolon"  → {"symbol.base.semicolon"}
        "@Identifier"  → {"id"}
        "@ParameterList?"  → {"bracket.r_parentheses"}
    """
    raw = spec.rstrip("?+*")
    # 1. 显式括号闭合：如 bracket.l_parentheses → bracket.r_parentheses
    close = _BRACKET_MAP.get(raw)
    if close:
        return {close}

    # 2. 规则引用：查找规则的最后一个生产式元素
    if raw.startswith("@"):
        rule = grammar_rules.get(raw[1:])
        if rule:
            prods = getattr(rule, "production", [])
            if prods:
                return _find_current_end(prods[-1], grammar_rules)
        return set()

    # 3. 普通 token → 自身就是结束
    return {raw}


def process_production_node(self, node: dict, context: ParseContext) -> Node | None:
    """dispatch 到 _parse_* 方法"""
    typ = node.get("type")
    method_name = f"_parse_{typ}"
    method = getattr(self, method_name, None)
    if method is None:
        self._log_state(f"未知节点类型: {typ}")
        return None
    return method(node, context)


def _get_recovery_cfg(self, rule: GrammarRule) -> bool:
    """规则级 recovery 检查：局部 recovery=true 优先，否则回退全局。"""
    p = getattr(rule, "parser", {})
    if isinstance(p, dict) and p.get("recovery"):
        return True
    return getattr(self, "global_recovery", False)


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
    self, context: ParseContext, prod: str, rule: GrammarRule, committed: bool,
    sync_tokens: set[str] | None = None,
) -> Node | None:
    """尝试匹配单个产生式，失败时如果已提交则产 ErrorNode（吞行）。

    Args:
        sync_tokens: 后继生产式的起始 token 集合。失败时 recovery 吞到这些 token 停止。
    """
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

    # 已提交 → 产 ErrorNode（双路径同步：后继生产式起始 vs 当前生产式结束）
    if committed:
        err = Node("Error")

        # 路径 A — 后继生产式起始 token（next-start 同步）
        next_start = sync_tokens or set()

        # 路径 B — 当前生产式的自然结束 token（current-end 同步）
        current_end = _find_current_end(prod, self.grammar_rules)

        # 兜底：规则 end_case
        end_case_tokens: set[str] = set()
        for ec in getattr(rule, "end_case", []):
            if isinstance(ec, str) and not ec.startswith("!"):
                end_case_tokens.add(ec)

        # 扫描阶段：不消费 token，只记录位置
        scan_ptr = context.token_pointer
        pos_next: int | None = None      # 路径 A 的匹配位置
        pos_current: int | None = None   # 路径 B 的匹配位置
        scan_len = 0
        while scan_ptr < len(context.tokens):
            t = context.tokens[scan_ptr]
            if t.type in end_case_tokens:
                break
            scan_len += 1
            if pos_next is None and next_start and t.type in next_start:
                pos_next = scan_len
            if pos_current is None and current_end and t.type in current_end:
                pos_current = scan_len
            scan_ptr += 1

        # 决策：选择最佳停止位置
        stop: int | None = None
        if pos_next is not None and pos_current is not None:
            if pos_next == pos_current:
                stop = pos_next   # 同位置 → 无争议
            else:
                shorter_pos, longer_pos = sorted([pos_next, pos_current])
                # 检查后继生产式起始 token 是否在较长路径的范围内出现
                # 如果在 → 截断在较短位置（后继生产式可以接手）
                # 不在 → 用较长位置（避免跳过头错过同步点）
                scan_ptr = context.token_pointer
                found = False
                for i in range(longer_pos):
                    if i < len(context.tokens) and context.tokens[scan_ptr + i].type in next_start:
                        found = True
                        break
                if found:
                    stop = shorter_pos  # 后继 token 在长路径内 → 截断用短路径
                else:
                    stop = longer_pos   # 不在 → 用长路径
        elif pos_next is not None:
            stop = pos_next
        elif pos_current is not None:
            stop = pos_current

        # 消费阶段：从当前位置消费到决策位置
        if stop is not None:
            tokens = []
            for _ in range(stop):
                if context.has_more_tokens():
                    tokens.append(context.peek_token())
                    context.advance_token()
                else:
                    break
            if tokens:
                err.add_attr("raw", " ".join(t.content for t in tokens))
        else:
            # 没有找到任何停止标记，消费到 end_case 边界
            while context.has_more_tokens():
                t = context.peek_token()
                if t is not None and t.type in end_case_tokens:
                    break
                context.advance_token()
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
    # 原子规则始终严格回溯，不受 recovery 影响
    if getattr(rule, "atomic", False):
        recovery = False
    else:
        recovery = _get_recovery_cfg(self, rule)
    committed = bool(recovery)

    # 同步 committed 标志到 context，供子规则（如 optional）查询
    context._committed = committed

    prods = getattr(rule, "production", [])
    all_matched_nodes = []
    error_node = None
    for i, prod in enumerate(prods):
        self._log_state(
            f"处理产生式: {prod} | {self._debug_token_info(context)}",
            context=context,
        )

        # 预先计算下一个生产式的同步 token，传给当前元素作为 recovery 停止边界
        next_sync = _find_sync_token(rule, i + 1, self.grammar_rules)

        result_node = _try_production(
            self, context, prod, rule, committed, sync_tokens=next_sync,
        )
        if result_node is None:
            # 未提交且匹配失败 → 全部失败
            return None, None

        if result_node.node_name == "Error" and committed:
            # 已提交后产出的 ErrorNode：记录错误，继续匹配后续产生式
            all_matched_nodes.append(result_node)
            error_node = result_node
            # 快进到下一个非可选产生式的起始 token
            if next_sync:
                while context.has_more_tokens():
                    t = context.peek_token()
                    if t is not None and t.type in next_sync:
                        break
                    context.advance_token()
            continue

        all_matched_nodes.append(result_node)

    return all_matched_nodes, error_node


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
