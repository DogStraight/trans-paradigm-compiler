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


def _find_sync_token(
    rule: GrammarRule, from_index: int, grammar_rules: dict
) -> set[str]:
    """从产生式列表中查找第 from_index 个元素之后的同步 token 集合（结果缓存）。"""
    cache = getattr(rule, "_sync_cache", None)
    if cache is None:
        cache = {}
        setattr(rule, "_sync_cache", cache)
    if from_index in cache:
        return cache[from_index]
    prods = rule.prods
    for i in range(from_index, len(prods)):
        prod = prods[i]
        if prod.endswith("?") or prod.endswith("*"):
            continue
        tokens = _first_token_of_spec(prod, grammar_rules)
        if tokens:
            cache[from_index] = tokens
            return tokens
    ec = getattr(rule, "end_case", [])
    result = {t for t in ec if isinstance(t, str) and not t.startswith("!")}
    cache[from_index] = result
    return result


def _find_recovery_strategy(
    rule: GrammarRule,
    prod_features: dict | None,
    prod_index: int | None,
) -> str | None:
    """从 recovery 字典中查找当前产生式的恢复策略。

    key 采用 $N 路径语法（与 attribute_binder 一致），如：
        "$3"          — 第 3 个 production 元素（1-based）
        "$3.$1"       — 第 3 个元素的第 1 个子元素

    可选值（策略名）：
        "skip_to_end"             — （默认）同步到 end_case / 后继生产式 / 当前生产式自然结束
        "skip_one"                — 只跳过当前一个 token，不向前扫描
        "skip_to_matching"        — 括号感知扫描：维护嵌套深度，遇到匹配的关闭括号时停止
        "skip_to_newline"         — 跳到下一个换行，用于语句级恢复（吞掉本行剩余内容）
        "skip_then_retry_until"   — 两阶段：先 skip_to_end 到同步点，然后重新尝试匹配同一产生式。
                                    重试成功则用真实解析结果替代 ErrorNode，失败则回退为 ErrorNode。
                                    类似 Chumsky 的 skip_then_retry_until 策略。
    """
    recovery_cfg = getattr(rule, "recovery", {})
    if not isinstance(recovery_cfg, dict) or prod_index is None:
        return None

    # 1. 精确匹配 $N（1-based）
    key = f"${prod_index + 1}"
    if key in recovery_cfg:
        return recovery_cfg[key]

    # 2. 子元素匹配：遍历 flattened 叶子，检查 $N.$m 路径
    if prod_features is not None:
        flat = prod_features.get("flat", [])
        for leaf_path, _leaf_feat in flat:
            sub_key = f"{key}.{leaf_path}"
            if sub_key in recovery_cfg:
                return recovery_cfg[sub_key]
    return None


def _find_current_end(spec: str, grammar_rules: dict, bracket_map: dict[str, str] | None = None) -> set[str]:
    """计算一个产生式规格字符串的自然结束 token。

    例如:
        "@PortParens?"  → {"bracket.r_parentheses"}
        "symbol.base.semicolon"  → {"symbol.base.semicolon"}
        "@Identifier"  → {"id"}
        "@ParameterList?"  → {"bracket.r_parentheses"}
    """
    raw = spec.rstrip("?+*")
    # 1. 显式括号闭合：如 bracket.l_parentheses → bracket.r_parentheses
    if bracket_map:
        close = bracket_map.get(raw)
        if close:
            return {close}

    # 2. 规则引用：查找规则的最后一个生产式元素
    if raw.startswith("@"):
        rule = grammar_rules.get(raw[1:])
        if rule:
            prods = rule.prods
            if prods:
                return _find_current_end(prods[-1], grammar_rules, bracket_map)
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
    """规则级 recovery 检查。

    全局开关 (global_recovery) 为 master switch：
    - False → 所有 recovery 禁用（包括局部 recovery=true）
    - True  → 规则级 recovery=truedict 生效
    """
    if not getattr(self, "global_recovery", False):
        return False
    p = getattr(rule, "parser", {})
    if isinstance(p, dict):
        val = p.get("recovery")
        if isinstance(val, dict):
            return True  # dict = 有子策略配置（如 PortParens）
        return bool(val)
    return False


def _get_prod_features(self, rule: GrammarRule, prod: str) -> dict | None:
    """获取产生式特征，带缓存。返回 {"tree": ..., "flat": [...]} 或 None。"""
    cache = getattr(rule, "_prod_cache", None)
    if cache is None:
        cache = {}
        setattr(rule, "_prod_cache", cache)
    if prod not in cache:
        from .rule_selector import (
            analyze_production_features,
            flatten_production_features,
        )

        feat = analyze_production_features(prod)
        if feat is not None:
            cache[prod] = {
                "tree": feat,
                "flat": flatten_production_features(prod),
            }
        else:
            cache[prod] = None
    return cache[prod]


def _try_production(
    self,
    context: ParseContext,
    prod: str,
    rule: GrammarRule,
    committed: bool,
    sync_tokens: set[str] | None = None,
    prod_index: int | None = None,
) -> Node | None:
    """尝试匹配单个产生式，失败时如果已提交则产 ErrorNode（吞行）。

    Args:
        sync_tokens: 后继生产式的起始 token 集合。
        prod_index: 该生产式在规则 production 数组中的索引，用于寻址 recovery 配置。
    """
    features = _get_prod_features(self, rule, prod)
    if not features:
        return None
    feature_tree = features["tree"]
    if not self._prepare_production(context, feature_tree):
        return None

    # 设置当前 recovery 寻址路径（$N 1-based）
    old_path = context._recovery_path
    old_rule = context._recovery_rule
    if prod_index is not None:
        context._recovery_path = f"${prod_index + 1}"
    context._recovery_rule = rule

    snapshot = context.create_snapshot()
    result = process_production_node(self, feature_tree, context)
    if result is not None:
        context._recovery_path = old_path
        context._recovery_rule = old_rule
        return result

    context._recovery_path = old_path
    context._recovery_rule = old_rule

    # 匹配失败
    context.restore_snapshot(snapshot)

    # 已提交 → 产 ErrorNode
    if committed:
        err = Node("Error")
        first_bad = context.peek_token()
        first_raw = first_bad.content if first_bad else ""

        strategy = _find_recovery_strategy(rule, features, prod_index) or "skip_to_end"

        end_case_tokens: set[str] = set()
        for ec in getattr(rule, "end_case", []):
            if isinstance(ec, str) and not ec.startswith("!"):
                end_case_tokens.add(ec)
        end_case_tokens.update(getattr(context, "_end_case_chain", set()))

        if strategy == "skip_one":
            if first_bad is not None:
                context.advance_token()
            err.add_attr("raw", first_raw)
            return err

        elif strategy == "skip_to_matching":
            depth = 0
            while context.has_more_tokens():
                t = context.peek_token()
                assert t is not None
                if t.type in end_case_tokens:
                    break
                if t.type in self._bracket_map:
                    depth += 1
                elif t.type in self._inverse_bracket_map:
                    if depth == 0:
                        break
                    depth -= 1
                context.advance_token()
            err.add_attr("raw", first_raw)
            return err

        elif strategy == "skip_to_newline":
            while context.has_more_tokens():
                t = context.peek_token()
                assert t is not None
                if t.type in end_case_tokens or t.type == "newline":
                    break
                context.advance_token()
            err.add_attr("raw", first_raw)
            return err

        # 策略：skip_to_end（默认）— 双路径同步扫描
        next_start = sync_tokens or set()
        current_end = _find_current_end(prod, self.grammar_rules, self._bracket_map)

        scan_ptr = context.token_pointer
        pos_next: int | None = None
        pos_current: int | None = None
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

        # 决策最佳停止位置
        stop: int | None = None
        if pos_next is not None and pos_current is not None:
            if pos_next == pos_current:
                stop = pos_next
            else:
                shorter_pos, longer_pos = sorted([pos_next, pos_current])
                scan_ptr = context.token_pointer
                found = False
                for i in range(longer_pos):
                    if (
                        i < len(context.tokens)
                        and context.tokens[scan_ptr + i].type in next_start
                    ):
                        found = True
                        break
                stop = shorter_pos if found else longer_pos
        elif pos_next is not None:
            stop = pos_next
        elif pos_current is not None:
            stop = pos_current

        if stop is not None:
            for _ in range(stop):
                if context.has_more_tokens():
                    context.advance_token()
                else:
                    break
        else:
            while context.has_more_tokens():
                t = context.peek_token()
                if t is not None and t.type in end_case_tokens:
                    break
                context.advance_token()

        # skip_then_retry_until: skip 后重新尝试匹配同一产生式
        if strategy == "skip_then_retry_until":
            retry_snmp = context.create_snapshot()
            if self._prepare_production(context, feature_tree):
                retry_result = process_production_node(self, feature_tree, context)
                if retry_result is not None:
                    return retry_result  # 恢复成功！
            # 重试失败，回退到 skip-stop 位置
            context.restore_snapshot(retry_snmp)

        err.add_attr("raw", first_raw)
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
    if getattr(rule, "is_atom", False):
        recovery = False
    else:
        recovery = _get_recovery_cfg(self, rule)
    committed = bool(recovery)

    # 同步 committed 标志到 context，供子规则（如 optional）查询
    context._committed = committed

    prods = rule.prods
    all_matched_nodes = []
    error_node = None

    # 如果本规则 committed 且有 end_case，推入 end_case 链供深度嵌套使用
    _pushed_end_case = False
    if committed:
        ec_tokens = set()
        for ec in getattr(rule, "end_case", []):
            if isinstance(ec, str) and not ec.startswith("!"):
                ec_tokens.add(ec)
        if ec_tokens:
            context._end_case_chain.update(ec_tokens)
            _pushed_end_case = True

    for i, prod in enumerate(prods):
        self._log_state(lambda: f"产生式: {prod} | {self._debug_token_info(context)}")

        # 预先计算下一个生产式的同步 token，传给当前元素作为 recovery 停止边界
        next_sync = _find_sync_token(rule, i + 1, self.grammar_rules)

        result_node = _try_production(
            self,
            context,
            prod,
            rule,
            committed,
            sync_tokens=next_sync,
            prod_index=i,
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
                    if t is not None:
                        if t.type in next_sync:
                            break
                        # 遇到 end_case 链 token → 停止快进，让上级 recovery 接手
                        if t.type in getattr(context, "_end_case_chain", set()):
                            break
                    context.advance_token()
            continue

        all_matched_nodes.append(result_node)

    # 恢复 end_case 链
    if _pushed_end_case:
        ec_tokens = set()
        for ec in getattr(rule, "end_case", []):
            if isinstance(ec, str) and not ec.startswith("!"):
                ec_tokens.add(ec)
        context._end_case_chain.difference_update(ec_tokens)

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
        lambda: f"尝试规则: {rule.name} | {self._debug_token_info(context)}",
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
    for prod in rule.prods:
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
