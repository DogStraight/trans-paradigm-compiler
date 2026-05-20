import re
import toml
from typing import Optional, List, Dict, Any
from define import Node, Token, GrammarRule, GrammarRulesRegister, FileManager
from parser.feature_analyze import analyze_production_features
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

        self.statement_rule_names = [
            name for name in self.grammar_rules if name not in self.pratt_rules
        ]

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
        self, node: dict, token: Token, visited: set
    ) -> bool:
        typ = node["type"]
        if typ == "token":
            return node["value"] == token.type
        elif typ == "call":
            rule_name = node["name"]
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
        elif typ == "seq":
            items = node.get("items", [])
            if not items:
                return False
            return self._features_can_start_with_token(items[0], token, visited)
        elif typ == "choice":
            for alt in node.get("alternatives", []):
                if self._features_can_start_with_token(alt, token, visited):
                    return True
            return False
        elif typ in ("repeat", "optional"):
            elem = node.get("elem")
            if elem is None:
                return False
            return self._features_can_start_with_token(elem, token, visited)
        else:
            return False

    def _get_candidate_rules(self, token: Token) -> List[GrammarRule]:
        """根据 token 返回可能匹配的语句规则列表，顺序由 statement_rule_names 决定"""
        possible = self._search_grammar_rule(token)
        if not possible:
            return []
        # 构建名称到规则的映射
        rule_map = {rule.name: rule for rule in possible}
        # 按照 statement_rule_names 的顺序筛选出存在的规则
        ordered = [
            rule_map[name] for name in self.statement_rule_names if name in rule_map
        ]
        return ordered

    def _process_production_node(
        self, node: dict, context: ParseContext
    ) -> Optional[Node]:
        typ = node["type"]
        if typ == "token":
            return self._parse_normal(node["value"], context)
        elif typ == "call":
            return self._parse_grammar_call(node["name"], context)
        elif typ == "seq":
            return self._parse_sequence_items(node["items"], context)
        elif typ == "choice":
            return self._parse_choice_alternatives(node["alternatives"], context)
        elif typ == "repeat":
            return self._parse_repeat_elem(node["elem"], context)
        elif typ == "optional":
            return self._parse_optional_elem(node["elem"], context)
        elif typ == "plus":  # 如果支持了 '+'
            return self._parse_plus_elem(node["elem"], context)
        else:
            self._log_state(f"未知节点类型: {typ}")
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

    def _parse_sequence_items(
        self, items: List[dict], context: ParseContext
    ) -> Optional[Node]:
        self.parser_current_state = "sequence"
        self._log_state("解析序列节点")
        try:
            with context:
                seq_node = Node("sequence")
                for item in items:
                    result = self._process_production_node(item, context)
                    if result is None:
                        raise _SequenceMatchError()
                    seq_node.add_child(result)
                self._log_state("序列解析成功")
                return seq_node
        except _SequenceMatchError:
            self._log_state("序列项匹配失败")
            return None

    def _parse_choice_alternatives(
        self, alternatives: List[dict], context: ParseContext
    ) -> Optional[Node]:
        self.parser_current_state = "branch"
        self._log_state("解析分支节点")
        original_pointer = context.token_pointer
        for alt in alternatives:
            try:
                with context:
                    context.token_pointer = original_pointer
                    result = self._process_production_node(alt, context)
                    if result is not None:
                        self._log_state("分支匹配成功")
                        return result
                    raise _BranchMatchError()
            except _BranchMatchError:
                continue
        context.token_pointer = original_pointer
        self._log_state("所有分支匹配失败")
        return None

    def _parse_repeat_elem(self, elem: dict, context: ParseContext) -> Optional[Node]:
        self.parser_current_state = "repeat"
        self._log_state("解析重复节点（零次或多次）")
        repeat_node = Node("repeat")
        while True:
            with context:
                result = self._process_production_node(elem, context)
                if result is None:
                    break
                repeat_node.add_child(result)
        self._log_state(f"重复解析完成，匹配次数: {len(repeat_node.child)}")
        return repeat_node

    def _parse_optional_elem(self, elem: dict, context: ParseContext) -> Optional[Node]:
        self.parser_current_state = "optional"
        self._log_state("解析可选节点")
        optional_node = Node("optional")
        with context:
            result = self._process_production_node(elem, context)
            if result is not None:
                optional_node.add_child(result)
        return optional_node

    def _parse_plus_elem(self, elem: dict, context: ParseContext) -> Optional[Node]:
        self.parser_current_state = "repeat"  # 复用 repeat 状态
        self._log_state("解析至少一次重复节点")
        plus_node = Node("plus")
        # 至少匹配一次
        with context:
            result = self._process_production_node(elem, context)
            if result is None:
                return None
            plus_node.add_child(result)
        # 继续匹配零次或多次
        while True:
            with context:
                result = self._process_production_node(elem, context)
                if result is None:
                    break
                plus_node.add_child(result)
        return plus_node

    def parse_sentence(self, context: ParseContext) -> Optional[Node]:
        current = context.peek_token()
        if not current:
            return None

        candidate_rules = self._get_candidate_rules(current)
        for rule in candidate_rules:
            snapshot = context.create_snapshot()
            node = self._try_rule_productions(context, rule)
            if node is not None:
                # 匹配成功，返回节点
                return node
            else:
                # 失败，回滚快照
                context.restore_snapshot(snapshot)

        return None

    def parse_block(
        self, context: ParseContext, end_tokens: set | None = None
    ) -> Optional[Node]:
        """
        解析一个语句块，直到遇到 end_tokens 或 token 耗尽。
        end_tokens: 表示块结束的 token 类型集合（如 {"newline", "r_curly_bracket"}），默认仅为文件结束。
        返回一个 Node("Block")，其 child 包含所有成功解析的语句节点。
        """
        if end_tokens is None:
            end_tokens = set()  # 默认仅遇到文件末尾结束

        block_node = Node("Block")
        skip_types = {"newline", "comment"}

        while context.has_more_tokens():
            current = context.peek_token()
            if current and current.type in end_tokens:
                # 遇到结束符，停止解析（但不消费该 token，由上层处理）
                break

            # 跳过空白/注释
            if current and current.type in skip_types:
                context.advance_token()
                continue

            # 尝试解析一条语句
            stmt_node = self.parse_sentence(context)
            if stmt_node is None:
                # 无法解析任何语句，可能是语法错误
                self._log_state(
                    f"无法解析的 token: {current.content if current else 'EOF'}"
                )
                break
            block_node.add_child(stmt_node)

        return block_node

    def parse(self, tokens: List[Token]) -> Optional[Node]:
        if not tokens:
            return None
        context = ParseContext(tokens, self.root_node)
        block_node = self.parse_block(context)
        if block_node and block_node.child:
            self.root_node.add_child(block_node)
            return self.root_node
        return None
