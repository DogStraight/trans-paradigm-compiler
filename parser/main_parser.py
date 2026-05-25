# parser/main_parser.py
import re
from typing import Optional, List, Dict, Any
from define import Node, Token, GrammarRule, GrammarRulesRegister, FileManager
from parser.feature_analyze import analyze_production_features
from parser.parser_context import ParseContext
from err import _SequenceMatchError, _BranchMatchError
from parser.rule_selector import RuleSelector
import parser.pratt_parser as pratt_parser


class Parser:
    def __init__(self) -> None:
        self.grammar_rules: Dict[str, GrammarRule] = (
            GrammarRulesRegister().rules_registration()
        )
        self.root_node = Node("root")
        self.debug_log_file = FileManager.get_full_path(FileManager.debug_log_file)
        self.operator_defs = pratt_parser.load_operator_defs()
        self.statement_rule_names = [
            name
            for name, rule in self.grammar_rules.items()
            if rule.end_case  # 只有定义了结束符的规则才作为语句
        ]
        self.rule_selector = RuleSelector(self.grammar_rules, self.statement_rule_names)

        self.skip_types = ["newline", "comment", "space.indent_keep"]

    def _log_state(self, action: str):
        with open(self.debug_log_file, "a", encoding="utf-8") as f:
            f.write(f"[{action}]\n")

    def _process_production_node(
        self, node: dict, context: ParseContext
    ) -> Optional[Node]:
        typ = node.get("type")
        method_name = f"_parse_{typ}"
        method = getattr(self, method_name, None)
        if method is None:
            self._log_state(f"未知节点类型: {typ}")
            return None
        return method(node, context)

    def _flatten_node(self, node: Node) -> Any:
        # 1. 内联规则节点：去掉外层包装，提取内容
        if node.name in self.grammar_rules and self.grammar_rules[node.name].inline:
            # 获取除 name 和 child 外的所有自定义属性
            attrs = {k: v for k, v in vars(node).items() if k not in ("name", "child")}
            # 情况A：只有一个自定义属性 -> 返回该属性值（可能是基本类型、节点、列表等）
            if len(attrs) == 1:
                return list(attrs.values())[0]
            # 情况B：没有自定义属性，但有 child 列表 -> 返回展平后的 child 列表（递归展平每个子节点）
            child = getattr(node, "child", None)
            if not attrs and isinstance(child, list):
                # 如果 child 只有一个元素，也可以考虑直接返回它？但按照要求，返回列表更通用
                return [self._flatten_node(c) for c in child]
            # 情况C：既没有自定义属性也没有 child -> 返回 None（空节点）
            if not attrs and not child:
                return None
            # 其他情况（如既有属性又有 child）：返回原节点
            return node

        # 2. 普通 token 节点（不在 grammar_rules 中）：压平为基本值
        if node.name not in self.grammar_rules:
            attrs = {k: v for k, v in vars(node).items() if k not in ("name", "child")}
            if len(attrs) == 1:
                only_value = list(attrs.values())[0]
                if not isinstance(only_value, (Node, list, dict)):
                    return only_value
            # 如果本身没有属性，则返回节点本身（例如 NoneLiteral 无属性）
            return node

        # 3. 普通语法规则节点（非内联）：保留原样
        return node

    def _try_rule_productions(
        self, context: ParseContext, rule: GrammarRule
    ) -> Optional[Node]:
        # Pratt 规则特殊处理：直接返回 Pratt 解析结果
        if rule.pratt:
            return self._try_pratt_rule(context, rule)

        if "Block" in rule.name:
            end_tokens = set(rule.end_case) if rule.end_case else set()
            start_token = getattr(rule, "block_start", None)
            return self.parse_block(
                context, end_tokens=end_tokens, start_token=start_token
            )

        self._log_state(f"尝试匹配规则: {rule.name}")
        # 设置当前规则，用于 _parse_token 中的属性绑定
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
                    # 特殊处理：如果 sub_node 是 list 节点，直接取其 items 属性
                    if sub_node.name == "list":
                        attr_value = sub_node.items
                    # 也可以处理 repeat 节点为列表，但 repeat 保留原样
                    if attr_name == "name":
                        attr_name = "identifier"
                    rule_node.add_attr(attr_name, attr_value)
            except (ValueError, IndexError):
                continue

        # 检查结束符（仅当规则定义了结束符且非空）
        if rule.end_case and context.has_more_tokens():
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
        # 对于 Pratt 规则，不需要设置 current_rule（因为不经过 _parse_token）
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

    # 对应生成式的类型的处理方法
    def _parse_token(self, node: dict, context: ParseContext) -> Optional[Node]:
        token_type: str = node["token_type"]
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

        parsed_node = Node(token_type)
        parsed_node.add_attr("value", current_token.content)

        context.advance_token()

        self._log_state(f"普通token {token_type} 解析成功")
        return parsed_node

    def _parse_call(self, node: dict, context: ParseContext) -> Optional[Node]:
        rule_name = node["name"]
        old_node = context.current_node
        snapshot = context.create_snapshot()

        target_rule = self.grammar_rules[rule_name]
        result_node = self._try_rule_productions(context, target_rule)
        if result_node is None:
            context.restore_snapshot(snapshot)
            return None

        context.update_current_node(old_node)

        if target_rule.inline:
            return result_node
        else:
            return result_node

    def _parse_seq(self, node: dict, context: ParseContext) -> Optional[Node]:
        items = node["items"]
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

    def _parse_choice(self, node: dict, context: ParseContext) -> Optional[Node]:
        alternatives = node["alternatives"]
        self._log_state("解析分支节点")
        original_pointer = context.token_pointer
        for alt in alternatives:
            # 重置指针到分支开始前的位置
            context.token_pointer = original_pointer
            try:
                with context:
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

    # 辅助方法用于处理 repeat、optional、plus 的循环匹配逻辑
    def _repeat_loop(
        self,
        elem: dict,
        context: ParseContext,
        min_count: int = 0,
        max_count: Optional[int] = None,
    ) -> Optional[List[Node]]:
        """循环匹配 elem，返回压平后的节点列表；若少于 min_count 则返回 None。"""
        nodes = []
        while True:
            with context:
                result = self._process_production_node(elem, context)
                if result is None:
                    break
                nodes.append(self._flatten_node(result))
                if max_count is not None and len(nodes) >= max_count:
                    break
        return nodes if len(nodes) >= min_count else None

    def _parse_repeat(self, node: dict, context: ParseContext) -> Optional[Node]:
        elem = node["elem"]
        # 检测是否为分隔列表模式
        is_separated = False
        item_elem: dict = {}
        sep_elem: dict = {}
        if elem.get("type") == "seq":
            items = elem.get("items", [])
            if len(items) == 2:
                first = items[0]
                second = items[1]
                if second.get("type") == "token":
                    is_separated = True
                    item_elem = first
                    sep_elem = second

        if is_separated:
            self._log_state("解析分隔列表（零次或多次）")
            collected = []
            with context:
                first_node = self._process_production_node(item_elem, context)
                if first_node is None:
                    return Node("list", items=[])
                collected.append(self._flatten_node(first_node))

            while True:
                snapshot = context.create_snapshot()
                sep_node = self._process_production_node(sep_elem, context)
                if sep_node is None:
                    context.restore_snapshot(snapshot)
                    break
                next_node = self._process_production_node(item_elem, context)
                if next_node is None:
                    break
                collected.append(self._flatten_node(next_node))
            return Node("list", items=collected)
        else:
            self._log_state("解析重复节点（零次或多次）")
            repeat_node = Node("repeat")
            while True:
                with context:
                    result = self._process_production_node(elem, context)
                    if result is None:
                        break
                    repeat_node.add_child(result)
            self._log_state(
                f"重复解析完成，匹配次数: {len(getattr(repeat_node, 'child', []))}"
            )
            return repeat_node

    def _parse_optional(self, node: dict, context: ParseContext) -> Optional[Node]:
        elem = node["elem"]
        self._log_state("解析可选节点")
        nodes = self._repeat_loop(elem, context, min_count=0, max_count=1)
        optional_node = Node("optional")
        if nodes:
            optional_node.add_child(nodes[0])
        return optional_node

    def _parse_plus(self, node: dict, context: ParseContext) -> Optional[Node]:
        elem = node["elem"]
        self._log_state("解析至少一次重复节点")
        nodes = self._repeat_loop(elem, context, min_count=1)
        if nodes is None:
            return None
        plus_node = Node("plus")
        for child in nodes:
            plus_node.add_child(child)
        return plus_node

    # 解析器的主要输出方法 sentence
    def parse_sentence(self, context: ParseContext) -> Optional[Node]:
        """解析一条语句：根据当前 token 选择候选规则并尝试匹配。"""
        if not context.has_more_tokens():
            return None

        current = context.peek_token()
        if current is None:
            return None

        candidates = self.rule_selector.get_candidate_rules(current)
        if not candidates:
            self._log_state(f"没有匹配的语句规则: {current.type}")
            return None

        for rule in candidates:
            snapshot = context.create_snapshot()
            node = self._try_rule_productions(context, rule)
            if node is not None:
                return node
            context.restore_snapshot(snapshot)

        self._log_state(f"所有候选规则匹配失败: {current.type}")
        return None

    # 解析器的主要输出方法 block
    def parse_block(
        self,
        context: ParseContext,
        end_tokens: set | None = None,
        start_token: str | None = None,
    ) -> Optional[Node]:
        """
        解析一个语句块，直到遇到 end_tokens 或 token 耗尽。
        - end_tokens: 块结束的 token 类型集合。
        - start_token: 块开始的 token 类型（如 "space.indent" 或 "bracket.l_curly_bracket"），如果提供则先消费它。
        返回 Node("Block")，其 child 包含所有成功解析的语句节点。
        """
        if start_token:
            current = context.peek_token()
            if not current or current.type != start_token:
                self._log_state(f"期望块开始标记 {start_token}，未找到")
                return None
            context.advance_token()  # 消费开始标记

        if end_tokens is None:
            end_tokens = set()

        block_node = Node("Block")
        while context.has_more_tokens():
            current = context.peek_token()
            if current and current.type in end_tokens:
                break
            if current and current.type in self.skip_types:
                context.advance_token()
                continue
            stmt_node = self.parse_sentence(context)
            if stmt_node is None:
                self._log_state(
                    f"无法解析的 token: {current.content if current else 'EOF'}"
                )
                break
            block_node.add_child(stmt_node)
        return block_node

    # 解析器的入口
    def parse(self, tokens: List[Token]) -> Optional[Node]:
        if not tokens:
            return None
        context = ParseContext(tokens, self.root_node)

        while context.has_more_tokens():
            current = context.peek_token()
            # 跳过空白/注释
            if current and current.type in self.skip_types:
                context.advance_token()
                continue

            stmt_node = self.parse_sentence(context)
            if stmt_node is None:
                # 无法解析，可能是语法错误
                self._log_state(
                    f"无法解析的 token: {current.content if current else 'EOF'}"
                )
                break
            self.root_node.add_child(stmt_node)

        return self.root_node if getattr(self.root_node, "child", None) else None
