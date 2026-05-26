# parser/main_parser.py
import re
from typing import Optional, List, Dict
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
        self.debug_log_file = FileManager.get_full_path(FileManager.debug_log_file)
        self.operator_defs = pratt_parser.load_operator_defs()
        self.statement_rule_names = [
            name
            for name, rule in self.grammar_rules.items()
            if rule.end_case  # 只有定义了结束符的规则才作为语句
        ]
        self.rule_selector = RuleSelector(self.grammar_rules, self.statement_rule_names)

        self.skip_types = ["newline", "comment", "space.indent_keep"]

        self._log_state("Parser initialized", mode="w")

    def _log_state(self, action: str, mode: str = "a") -> None:
        with open(self.debug_log_file, mode, encoding="utf-8") as f:
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

    def _try_rule_productions(
        self, context: ParseContext, rule: GrammarRule
    ) -> Optional[Node]:
        # Pratt 规则特殊处理：直接返回 Pratt 解析结果
        if rule.pratt:
            return self._try_pratt_rule(context, rule)

        # 块规则：有非空 block_start 属性，调用 parse_block
        block_start = getattr(rule, "block_start", None)
        if block_start and isinstance(block_start, str) and block_start.strip():
            return self.parse_block(context, start_token=block_start)

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
                # 恢复父节点
                if old_node is None:
                    context.current_node = None
                else:
                    context.update_current_node(old_node)
                self._log_state(f"产生式 {prod} 匹配失败")
                return None
            all_matched_nodes.append(result_node)

        # 绑定属性
        for attr_name, pos_str in rule.node.items():
            if not isinstance(pos_str, str):
                continue
            try:
                pos = int(pos_str.strip("$")) - 1
                if 0 <= pos < len(all_matched_nodes):
                    sub_node = all_matched_nodes[pos]
                    rule_node.add_attr(attr_name, sub_node)
            except (ValueError, IndexError):
                continue

        # 检查结束符（仅当规则定义了结束符且非空）
        if rule.end_case and context.has_more_tokens():
            token = context.peek_token()
            if token and token.type not in rule.end_case:
                if old_node is None:
                    context.current_node = None
                else:
                    context.update_current_node(old_node)
                return None

        # 恢复父节点
        if old_node is None:
            context.current_node = None
        else:
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
        self._log_state(f"调用规则: {rule_name}")
        old_node = context.current_node
        snapshot = context.create_snapshot()

        target_rule = self.grammar_rules[rule_name]
        result_node = self._try_rule_productions(context, target_rule)
        if result_node is None:
            context.restore_snapshot(snapshot)
            return None

        if old_node is None:
            context.current_node = None
        else:
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
                nodes.append(result)
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
                collected.append(first_node)

            while True:
                snapshot = context.create_snapshot()
                sep_node = self._process_production_node(sep_elem, context)
                if sep_node is None:
                    context.restore_snapshot(snapshot)
                    break
                next_node = self._process_production_node(item_elem, context)
                if next_node is None:
                    break
                collected.append(next_node)
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
        self, context: ParseContext, start_token: Optional[str] = None
    ) -> Optional[Node]:
        """
        解析一个代码块。

        1. 根据起始符 start_token 查找匹配的块规则（block_start == start_token）
        2. 使用匹配规则的名称作为块节点名称
        3. 从匹配规则中提取结束符集合（block_end 和 end_case）
        4. 消费起始符，循环解析句子直到遇到结束符，返回块节点
        """
        # 1. 根据起始符获取块规则名称
        self._log_state(
            f"进入 parse_block, start_token={start_token}, 当前 token: {context.peek_token() if context.has_more_tokens() else 'EOF'}"
        )
        block_rule_name = (
            self.rule_selector.get_block_rule(start_token)
            if start_token is not None
            else None
        )
        self._log_state(f"找到块规则: {block_rule_name}")
        matched_rule = (
            self.grammar_rules.get(block_rule_name) if block_rule_name else None
        )

        # 2. 确定块节点名称
        if matched_rule is None:
            self._log_state(f"未找到匹配的块规则: {start_token}")
            return None
        block_name = matched_rule.name

        # 3. 确定结束符
        end_token = getattr(matched_rule, "block_end", None)

        # 4. 处理起始符（跳过分隔符、消费起始符）
        if start_token:
            # 跳过空白、注释等
            while context.has_more_tokens():
                current = context.peek_token()
                if current and current.type in self.skip_types:
                    context.advance_token()
                else:
                    break
            current = context.peek_token()
            if not current or current.type != start_token:
                self._log_state(f"期望块开始标记 {start_token}，未找到")
                return None
            context.advance_token()  # 消费开始标记

        # 5. 创建块节点
        block_node = Node(block_name)

        # 6. 循环解析句子直到遇到结束符或文件末尾
        while context.has_more_tokens():
            current = context.peek_token()
            if current and current.type == end_token:
                context.advance_token()  # 消费结束符
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

        # 7. 返回块节点
        return block_node

    # 解析器的入口
    def parse(self, tokens: List[Token]) -> Optional[Node]:
        context = ParseContext(tokens)
        block_node = self.parse_block(context, start_token="")
        return block_node if block_node else None
