import re
import toml
from typing import Optional, List, Dict, Any
from define import Node, Token, GrammarRule, GrammarRulesRegister, FileManager
from parser.feature_analyze import analyze_production_features, ProductionNode
from parser.parser_context import ParseContext
from err import _SequenceMatchError, _BranchMatchError
import parser.pratt_parser as pratt_parser


class Parser:
    def __init__(self) -> None:
        self.grammar_rules: Dict[str, GrammarRule] = (
            GrammarRulesRegister().rules_registration()
        )
        self.root_node = Node("root")

        self.parser_states = [
            "normal",
            "branch",
            "repeat",
            "optional",
            "sequence",
            "grammar_call",
        ]
        self.parser_current_state = "normal"

        self.debug_log_file = "parser_debug.log"
        with open(self.debug_log_file, "w") as f:
            f.write("=== Parser Debug Log ===\n")

        self.operator_defs = self._load_operator_defs()

        self.pratt_rules = {
            "Expression",
            "AddExpr",
            "MulExpr",
            "CompareExpr",
            "BoolExpr",
        }

    def _load_operator_defs(self) -> List[tuple]:
        path = FileManager.get_full_path("pyv_compiler/grammar/symbol_level.toml")
        with open(path, "r", encoding="utf-8") as f:
            data = toml.load(f)
        operators = data.get("operator", [])
        operator_defs = []
        for idx, op in enumerate(operators, start=1):
            props = {
                "symbol": op["symbol"],
                "arity": op["arity"],
                "assoc": op.get("assoc", "left"),
            }
            if "position" in op:
                props["position"] = op["position"]
            if "second" in op:
                props["second"] = op["second"]
            operator_defs.append((idx, props))
        return operator_defs

    def _log_state(self, action: str):
        with open(self.debug_log_file, "a", encoding="utf-8") as f:
            f.write(f"[{action}]\n")

    def _search_grammar_rule(self, first_token: Token) -> Optional[List[GrammarRule]]:
        possible_rules = []
        for rule in self.grammar_rules.values():
            for prod in rule.production:
                try:
                    features = analyze_production_features(prod)
                except Exception:
                    continue
                if features and self._features_can_start_with_token(
                    features, first_token, set()
                ):
                    possible_rules.append(rule)
                    break
        return possible_rules if possible_rules else None

    def _features_can_start_with_token(
        self, node: ProductionNode, token: Token, visited: set
    ) -> bool:
        """递归判断 ProductionNode 树是否可能以给定 token 开始"""
        if node.type == "normal":
            return node.value == token.type
        elif node.type == "grammar_call":
            rule_name = node.value
            if rule_name in visited:
                return False
            if rule_name not in self.grammar_rules:
                return False
            visited.add(rule_name)
            rule = self.grammar_rules[rule_name]
            for prod in rule.production:
                prod_node = analyze_production_features(prod)
                if prod_node and self._features_can_start_with_token(
                    prod_node, token, visited.copy()
                ):
                    return True
            return False
        elif node.type == "sequence":
            if not node.child:
                return False
            return self._features_can_start_with_token(node.child[0], token, visited)
        elif node.type == "branch":
            for child in node.child:
                if self._features_can_start_with_token(child, token, visited):
                    return True
            return False
        elif node.type in ("repeat", "optional"):
            if not node.child:
                return False
            return self._features_can_start_with_token(node.child[0], token, visited)
        else:
            return False

    def _process_production_node(
        self, node: ProductionNode, context: ParseContext
    ) -> Optional[Node]:
        """递归处理产生式树节点，返回解析后的 Node 或 None"""
        if node.type == "normal":
            return self._parse_normal(node.value, context)
        elif node.type == "grammar_call":
            return self._parse_grammar_call(node.value, context)
        elif node.type == "sequence":
            return self._parse_sequence_nodes(node.child, context)
        elif node.type == "branch":
            return self._parse_branch_nodes(node.child, context)
        elif node.type == "repeat":
            return self._parse_repeat_nodes(node.child, context)
        elif node.type == "optional":
            return self._parse_optional_nodes(node.child, context)
        else:
            self._log_state(f"未知节点类型: {node.type}")
            return None

    def _flatten_node(self, node: Node) -> Any:
        """
        将叶子节点（token 节点或只有单个属性的节点）转换为基本类型。
        """
        # 如果是语法规则节点，保留原样（除非内联标记处理过）
        if node.name in self.grammar_rules:
            return node

        # 获取除 name 和 child 外的所有属性
        attrs = {k: v for k, v in vars(node).items() if k not in ("name", "child")}

        # 如果只有一个属性且该属性是基本类型，返回该属性值
        if len(attrs) == 1:
            only_value = list(attrs.values())[0]
            if not isinstance(only_value, (Node, list, dict)):
                return only_value

        # 否则返回原节点
        return node

    def _try_rule_productions(
        self, context: ParseContext, rule: GrammarRule
    ) -> Optional[Node]:
        # Pratt 规则特殊处理：直接返回 Pratt 解析结果
        if rule.name in self.pratt_rules:
            return self._try_pratt_rule(context, rule)

        self._log_state(f"尝试匹配规则: {rule.name}")
        # 设置当前规则，用于 _parse_normal 中的属性绑定
        context.update_current_rule(rule)

        # 为当前规则创建新节点
        rule_node = Node(rule.name)
        old_node = context.current_node
        context.update_current_node(rule_node)

        all_matched_nodes = []

        for prod in rule.production:
            if not context.has_more_tokens():
                break
            self._log_state(f"处理产生式: {prod}")
            features = analyze_production_features(prod)
            if not features:
                continue

            snapshot = context.create_snapshot()
            result_node = self._process_production_node(features, context)
            if result_node is None:
                context.restore_snapshot(snapshot)
                # 恢复父节点并清除 current_rule ？不必，因为会返回 None 并恢复快照，快照会恢复 current_rule
                context.update_current_node(old_node)
                self._log_state(f"产生式 {prod} 匹配失败")
                return None
            all_matched_nodes.append(result_node)

        # 绑定属性（根据 rule.node 映射）
        for attr_name, pos_str in rule.node.items():
            if not isinstance(pos_str, str):
                continue
            try:
                pos = int(pos_str.strip("$")) - 1
                if 0 <= pos < len(all_matched_nodes):
                    sub_node = all_matched_nodes[pos]
                    # 压平节点
                    attr_value = self._flatten_node(sub_node)
                    if attr_name == "name":  # 避免覆盖节点类型名
                        attr_name = "identifier"
                    rule_node.add_attr(attr_name, attr_value)
            except (ValueError, IndexError):
                continue

        # 检查结束符
        if context.has_more_tokens():
            token = context.peek_token()
            if token and token.type not in rule.end_case:
                context.update_current_node(old_node)
                return None

        # 恢复父节点
        context.update_current_node(old_node)
        self._log_state(f"规则 {rule.name} 匹配成功")
        return rule_node

    def _try_pratt_rule(
        self, context: ParseContext, rule: GrammarRule
    ) -> Optional[Node]:
        self._log_state(f"使用 Pratt 解析器解析规则: {rule.name}")
        # 对于 Pratt 规则，不需要设置 current_rule（因为不经过 _parse_normal）
        start_idx = context.token_pointer
        if not context.has_more_tokens():
            self._log_state("Pratt 解析: 没有可用 token")
            return None

        expr_tokens = []
        ptr = start_idx
        skip_types = {"newline", "comment"}
        while ptr < len(context.tokens):
            tok = context.tokens[ptr]
            if tok.type in rule.end_case:
                break
            if tok.type in skip_types or tok.type.startswith("space"):
                ptr += 1
                continue
            expr_tokens.append(tok)
            ptr += 1

        if not expr_tokens:
            self._log_state("Pratt 解析: 没有可用于解析的 token")
            return None

        try:
            ast_node = pratt_parser.parse(expr_tokens, self.operator_defs)
        except Exception as e:
            self._log_state(f"Pratt 解析失败: {e}")
            return None

        context.token_pointer = ptr
        self._log_state(f"Pratt 解析成功，消耗了 {ptr - start_idx} 个 token")
        return ast_node

    def _parse_normal(self, token_type: str, context: ParseContext) -> Optional[Node]:
        self.parser_current_state = "normal"
        self._log_state(f"解析普通token: {token_type}")

        if not re.match(r"^[a-zA-Z0-9_\.]+$", token_type):
            self._log_state(f"无效的普通token格式: {token_type}")
            return None

        if not context.has_more_tokens():
            self._log_state("无更多token可解析")
            return None

        current_token = context.peek_token(offset=0)
        if current_token is None:
            self._log_state("peek_token 返回 None")
            return None

        if token_type != current_token.type:
            self._log_state(
                f"token类型不匹配: 期望 {token_type}, 实际 {current_token.type}"
            )
            return None

        node = Node(token_type)
        assert context.current_rule is not None

        node_pos = "$" + str(context.production_pointer + 1)
        for key, value in context.current_rule.node.items():
            if value == node_pos:
                node.add_attr(key, current_token.content)

        context.advance_token()
        context.advance_production()
        context.update_match_length(1)

        self._log_state(f"普通token {token_type} 解析成功")
        return node

    def _parse_grammar_call(
        self, rule_name: str, context: ParseContext
    ) -> Optional[Node]:
        old_node = context.current_node
        snapshot = context.create_snapshot()

        target_rule = self.grammar_rules[rule_name]
        result_node = self._try_rule_productions(context, target_rule)
        if result_node is None:
            context.restore_snapshot(snapshot)
            return None

        context.update_current_node(old_node)
        return result_node

    def _parse_sequence_nodes(
        self, child: List[ProductionNode], context: ParseContext
    ) -> Optional[Node]:
        self.parser_current_state = "sequence"
        self._log_state("解析序列节点")

        try:
            with context:
                seq_node = Node("sequence")
                for c in child:
                    result = self._process_production_node(c, context)
                    if result is None:
                        raise _SequenceMatchError()
                    seq_node.add_child(result)
                # 序列全部匹配成功
                self._log_state("序列解析成功")
                return seq_node
        except _SequenceMatchError:
            # 异常触发回滚后，with 块已恢复快照，我们只需返回 None
            self._log_state("序列项匹配失败")
            return None

    def _parse_branch_nodes(
        self, child: List[ProductionNode], context: ParseContext
    ) -> Optional[Node]:
        self.parser_current_state = "branch"
        self._log_state("解析分支节点")

        original_pointer = context.token_pointer

        for c in child:
            # 每个分支独立尝试，失败则回滚，成功则提交
            try:
                with context:
                    # 注意：进入 with 前需重置指针（但 with 会保存当前状态快照）
                    # 为了让每个分支从相同起点开始，需要手动重置指针
                    context.token_pointer = original_pointer
                    result = self._process_production_node(c, context)
                    if result is not None:
                        self._log_state("分支匹配成功")
                        return result
                    # 匹配失败，抛异常触发回滚
                    raise _BranchMatchError()
            except _BranchMatchError:
                # 自动回滚已完成，继续尝试下一个分支
                continue

        # 所有分支失败，确保指针回到原始位置（虽然回滚已做，但防御性重置）
        context.token_pointer = original_pointer
        self._log_state("所有分支匹配失败")
        return None

    def _parse_repeat_nodes(
        self, child: List[ProductionNode], context: ParseContext
    ) -> Optional[Node]:
        self.parser_current_state = "repeat"
        self._log_state("解析重复节点（零次或多次）")

        if not child:
            return Node("repeat")

        c = child[0]
        repeat_node = Node("repeat")

        while True:
            with context:
                result = self._process_production_node(c, context)
                if result is None:
                    # 匹配失败，with 自动回滚，跳出循环
                    break
                repeat_node.add_child(result)
                # 匹配成功，with 正常结束，提交本次匹配

        # 零次或多次均成功
        match_times = len(getattr(repeat_node, "child", []))
        self._log_state(f"重复解析完成，匹配次数: {match_times}")
        return repeat_node

    def _parse_optional_nodes(
        self, child: List[ProductionNode], context: ParseContext
    ) -> Optional[Node]:
        self.parser_current_state = "optional"
        self._log_state("解析可选节点")

        optional_node = Node("optional")

        if not child:
            return optional_node

        c = child[0]
        with context:
            result = self._process_production_node(c, context)
            if result is not None:
                optional_node.add_child(result)
                # 匹配成功：with 块正常结束，提交更改（指针前进，节点添加）
            # 匹配失败：with 块自动回滚，指针不动，不添加子节点

        return optional_node

    def parse(self, tokens: List[Token]) -> Optional[Node]:
        if not tokens:
            return None
        context = ParseContext(tokens, self.root_node)
        first_token = tokens[0]
        possible_rules = self._search_grammar_rule(first_token)
        if not possible_rules:
            self._log_state(f"无匹配的顶层规则 for token: {first_token.type}")
            return None
        for rule in possible_rules:
            snapshot = context.create_snapshot()
            result_node = self._try_rule_productions(context, rule)
            if result_node is not None:
                self.root_node.add_child(result_node)
                self._log_state(f"成功匹配顶层规则: {rule.name}")
                return self.root_node
            else:
                context.restore_snapshot(snapshot)
        self._log_state("所有顶层规则匹配失败")
        return None
