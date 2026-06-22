# parser/main_parser.py
import re
import sys
from typing import Optional, List, Dict, Any
from core.define import Node, Token, GrammarRule, GrammarRulesRegister, FileManager
from parser.feature_analyze import analyze_production_features
from parser.parser_context import ParseContext
from core.err import _SequenceMatchError, _BranchMatchError
from parser.rule_selector import RuleSelector
import parser.pratt_parser as pratt_parser


class Parser:
    def __init__(self, rules_dir: str | None = None) -> None:
        self.grammar_rules: Dict[str, GrammarRule] = {}
        try:
            self.grammar_rules = GrammarRulesRegister().rules_registration()
        except FileNotFoundError:
            pass  # 默认规则不存在，稍后由调用方设置
        if FileManager.debug_log_file is not None:
            self.debug_log_file = FileManager.get_full_path(FileManager.debug_log_file)
        self.operator_defs = pratt_parser.load_operator_defs(rules_dir)
        self.statement_rule_names = [
            name
            for name, rule in self.grammar_rules.items()
            if getattr(rule, "end_case", None)  # 只有定义了结束符的规则才作为语句
        ]
        self.rule_selector = RuleSelector(self.grammar_rules, self.statement_rule_names)

        self.skip_types = ["newline", "comment", "space.indent_keep"]

        # 从 token 定义加载 Pratt 分类器，替换 pratt_parser 中的硬编码 is_* 函数
        if rules_dir:
            categories = pratt_parser.load_token_categories(rules_dir)
            if categories:
                pratt_parser.install_token_classifier(categories)

        # 收集原子规则列表（顺序敏感：较长的 production 优先）
        self.atomic_rules: List[GrammarRule] = sorted(
            (
                rule
                for rule in self.grammar_rules.values()
                if getattr(rule, "atomic", False)
            ),
            key=lambda r: len(getattr(r, "production", [])),
            reverse=True,
        )

        self._log_state("Parser initialized", mode="w")

    def _log_state(self, action: str, mode: str = "a") -> None:
        if hasattr(self, "debug_log_file"):
            with open(self.debug_log_file, mode, encoding="utf-8") as f:
                f.write(f"[{action}]\n")

    def _warn(self, message: str) -> None:
        """输出解析警告到 stderr（同时写入 debug 日志）"""
        self._log_state(f"警告: {message}")
        print(f"⚠️ [解析器] {message}", file=sys.stderr)

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

    @staticmethod
    def _get_attr_by_path(obj: Any, path: str) -> Any:
        """支持点号路径的属性提取，如 'value.content'"""
        if obj is None:
            return None
        parts = path.split(".")
        current = obj
        for part in parts:
            if current is None:
                return None
            if hasattr(current, part):
                current = getattr(current, part)
            else:
                return None
        return current

    def _extract_from_spec(self, spec: str, all_matched_nodes: List[Node]) -> Any:
        """从属性映射规约中提取值，例如 "$3" 或 "$4.items"；非 $ 引用直接作为字面值返回"""
        if not isinstance(spec, str):
            return None
        try:
            if "." in spec:
                base_part, path = spec.split(".", 1)
                pos = int(base_part.strip("$")) - 1
            else:
                pos = int(spec.strip("$")) - 1
                path = None
        except ValueError:
            return spec  # 硬编码字面值，如 direction = "output"
        if 0 <= pos < len(all_matched_nodes):
            sub = all_matched_nodes[pos]
            if path:
                return self._get_attr_by_path(sub, path)
            return sub
        return None

    def _bind_attributes(
        self, rule_node: Node, rule: GrammarRule, all_matched_nodes: List[Node]
    ) -> None:
        """将规则中的属性映射绑定到规则节点上"""
        if not isinstance(getattr(rule, "node", None), dict):
            return
        for attr_name, spec in getattr(rule, "node", {}).items():
            if isinstance(spec, list):
                merged = []
                for item_spec in spec:
                    extracted = self._extract_from_spec(item_spec, all_matched_nodes)
                    if extracted is not None:
                        if isinstance(extracted, list):
                            merged.extend(extracted)
                        else:
                            merged.append(extracted)
                if merged:
                    rule_node.add_attr(attr_name, merged)
            else:
                extracted = self._extract_from_spec(spec, all_matched_nodes)
                if extracted is not None:
                    # 解包 optional 包装节点：空的跳过，非空的取其子节点
                    if (
                        isinstance(extracted, Node)
                        and extracted.node_name == "optional"
                    ):
                        if not hasattr(extracted, "sub_node") or not extracted.sub_node:
                            continue
                        extracted = extracted.sub_node[0]
                    rule_node.add_attr(attr_name, extracted)

    def _try_inline_rule(
        self,
        rule: GrammarRule,
        all_matched_nodes: List[Node],
        old_node: Optional[Node],
        context: ParseContext,
    ) -> Optional[Node]:
        """若规则标记为内联且只有一个属性映射，则返回被映射的子节点，否则返回 None。"""
        if not getattr(rule, "inline", False) or len(getattr(rule, "node", {})) != 1:
            return None

        for _, pos_str in getattr(rule, "node", {}).items():
            if not isinstance(pos_str, str):
                continue
            # 提取路径（如果有）
            if "." in pos_str:
                base_part, _ = pos_str.split(".", 1)
                try:
                    pos = int(base_part.strip("$")) - 1
                except ValueError:
                    continue
            else:
                try:
                    pos = int(pos_str.strip("$")) - 1
                except ValueError:
                    continue
            if not (0 <= pos < len(all_matched_nodes)):
                continue
            inner = all_matched_nodes[pos]
            # 恢复父节点
            self._restore_current_node(old_node, context)
            self._log_state(
                f"规则 {rule.name} 内联展开成功 -> {inner.node_name if hasattr(inner, 'node_name') else type(inner)}"
            )
            return inner

        return None

    def _skip_tokens(self, context: ParseContext, skip_types: tuple) -> None:
        """跳过指定类型的 token"""
        while context.has_more_tokens():
            cur = context.peek_token()
            if cur and cur.type in skip_types:
                context.advance_token()
            else:
                break

    @staticmethod
    def _restore_current_node(old_node: Optional[Node], context: ParseContext) -> None:
        if old_node is None:
            context.current_node = None
        else:
            context.update_current_node(old_node)

    def _prepare_production(
        self, context: ParseContext, features: dict
    ) -> bool:
        """为匹配产生式做准备：跳过空白/注释，条件跳过 indent/dedent。返回 False 表示 token 不足。"""
        self._skip_tokens(context, tuple(self.skip_types))
        if not context.has_more_tokens():
            return False
        should_skip = True
        # 非可选的规则调用 (@Rule)：如果目标规则有 block_start 则不跳过 indent/dedent
        if features.get("type") == "call":
            ref_rule = self.grammar_rules.get(features["name"])
            if ref_rule and getattr(ref_rule, "block_start", None):
                should_skip = False
        # 可选产生式 (...?)：不跳过 indent/dedent
        elif features.get("type") == "optional":
            should_skip = False
        if should_skip:
            self._skip_tokens(context, ("space.indent", "space.dedent"))
        return True

    def _check_end_case(self, context: ParseContext, rule: GrammarRule) -> bool:
        """检查当前 token 是否匹配规则的结束符。匹配返回 True，不匹配返回 False。"""
        if not getattr(rule, "end_case", None) or not context.has_more_tokens():
            return True
        token = context.peek_token()
        if token and token.type in getattr(rule, "end_case", []):
            return True
        if (
            getattr(rule, "block_start", None)
            and str(getattr(rule, "block_start", "")).strip()
        ):
            return True
        # 检查是否包含引用块规则的产生式（如 @Block）
        for prod in getattr(rule, "production", []):
            try:
                feats = analyze_production_features(prod)
            except Exception:
                continue
            if feats and feats.get("type") == "call":
                inner = self.grammar_rules.get(feats["name"])
                if inner and getattr(inner, "block_start", None):
                    return True
        return False

    def _match_productions(
        self, context: ParseContext, rule: GrammarRule
    ) -> Optional[List[Node]]:
        """匹配规则的所有产生式。成功返回节点列表，任一产生式失败返回 None。"""
        all_matched_nodes = []
        for prod in getattr(rule, "production", []):
            self._log_state(f"处理产生式: {prod}")
            features = analyze_production_features(prod)
            if not features:
                continue
            if not self._prepare_production(context, features):
                break

            snapshot = context.create_snapshot()
            result_node = self._process_production_node(features, context)
            if result_node is None:
                context.restore_snapshot(snapshot)
                self._log_state(f"产生式 {prod} 匹配失败")
                return None
            all_matched_nodes.append(result_node)
        return all_matched_nodes

    def _try_rule_productions(
        self, context: ParseContext, rule: GrammarRule
    ) -> Optional[Node]:
        # Pratt 规则特殊处理：直接返回 Pratt 解析结果
        if getattr(rule, "pratt", False):
            return self._try_pratt_rule(context, rule)

        # 块规则：有非空 block_start 属性，调用 parse_block
        block_start = getattr(rule, "block_start", None)
        if block_start and isinstance(block_start, str) and block_start.strip():
            return self.parse_block(context, start_token=block_start)

        self._log_state(f"尝试匹配规则: {rule.name}")
        context.update_current_rule(rule)

        rule_node = Node(rule.name)
        old_node = context.current_node
        context.update_current_node(rule_node)

        all_matched_nodes = self._match_productions(context, rule)
        if all_matched_nodes is None:
            return None

        # 属性绑定
        self._bind_attributes(rule_node, rule, all_matched_nodes)

        # 检查结束符
        if not self._check_end_case(context, rule):
            self._restore_current_node(old_node, context)
            return None

        # Inline 规则扁平化：复用 _try_inline_rule
        inline_result = self._try_inline_rule(
            rule, all_matched_nodes, old_node, context
        )
        if inline_result is not None:
            return inline_result

        # 恢复父节点
        self._restore_current_node(old_node, context)
        self._log_state(f"规则 {rule.name} 匹配成功")
        return rule_node

    # ──────────────────────────────────────────────
    # 动态原子解析
    # ──────────────────────────────────────────────

    def _parse_atom(self, context: ParseContext) -> tuple[Optional[Node], int]:
        """尝试按顺序匹配原子规则，返回 (node, consumed) 或 (None, 0)。"""
        start_ptr = context.token_pointer
        for rule in self.atomic_rules:
            snapshot = context.create_snapshot()
            node = self._try_rule_productions(context, rule)
            if node is not None:
                consumed = context.token_pointer - start_ptr
                return node, consumed
            context.restore_snapshot(snapshot)
        return None, 0

    def _try_pratt_rule(
        self, context: ParseContext, rule: GrammarRule
    ) -> Optional[Node]:
        self._log_state(f"使用 Pratt 解析器解析规则: {rule.name}")
        if not context.has_more_tokens():
            self._log_state("Pratt 解析: 没有可用 token")
            return None

        start = context.token_pointer
        stop_tokens: Optional[set] = (
            set(getattr(rule, "end_case", []))
            if getattr(rule, "end_case", None)
            else None
        )

        # 原子解析器闭包：供 Pratt 回调，适配 (tokens, idx) → (node, consumed)
        def atom_parser(tokens_list, idx):
            old_ptr = context.token_pointer
            context.token_pointer = idx
            node, consumed = self._parse_atom(context)
            context.token_pointer = old_ptr  # Pratt 自己管理指针
            return node, consumed

        try:
            ast_node, consumed = pratt_parser.parse_with_count(
                context.tokens,
                start,
                self.operator_defs,
                atom_parser=atom_parser,
                stop_tokens=stop_tokens,
            )
        except ValueError as e:
            self._log_state(f"Pratt 解析: 不适合作为表达式 - {e}")
            return None
        except Exception as e:
            self._log_state(f"Pratt 解析失败: {e}")
            self._warn(f"Pratt 表达式解析失败: {e}")
            return None

        if ast_node is None or consumed == 0:
            self._log_state("Pratt 解析: 未消费任何 token")
            return None

        context.token_pointer = start + consumed
        self._log_state(f"Pratt 解析成功，消耗 {consumed} 个 token")
        return ast_node

    # 对应生成式的类型的处理方法
    def _parse_token(self, node: dict, context: ParseContext) -> Optional[Node]:
        token_type: str = node["token_type"]
        self._log_state(f"解析普通token: {token_type}")

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

        # 统一创建基础节点，不再区分 id 等特殊类型
        parsed_node = Node(token_type)
        parsed_node.add_attr("value", current_token.content)
        context.advance_token()

        self._log_state(f"普通token {token_type} 解析成功")
        return parsed_node

    def _parse_call(self, node: dict, context: ParseContext) -> Optional[Node]:
        rule_name = node["name"]
        self._log_state(f"调用规则: {rule_name}")
        snapshot = context.create_snapshot()

        target_rule = self.grammar_rules[rule_name]
        result_node = self._try_rule_productions(context, target_rule)
        if result_node is None:
            context.restore_snapshot(snapshot)
            return None

        return result_node

    def _parse_seq(self, node: dict, context: ParseContext) -> Optional[Node]:
        items = node["items"]
        self._log_state("解析序列节点")
        try:
            with context:
                seq_node = Node("seq")
                for item in items:
                    result = self._process_production_node(item, context)
                    if result is None:
                        raise _SequenceMatchError()
                    seq_node.add_sub_node(result)
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
            snapshot = context.create_snapshot()
            result = self._process_production_node(elem, context)
            if result is None:
                context.restore_snapshot(snapshot)
                break
            nodes.append(result)
            if max_count is not None and len(nodes) >= max_count:
                break
        return nodes if len(nodes) >= min_count else None

    def _parse_repeat(self, node: dict, context: ParseContext) -> Optional[Node]:
        elem = node["elem"]
        # 检测分隔列表模式，支持 (item sep)* 和 (sep item)* 两种顺序
        item_elem = sep_elem = None
        sep_first = False
        if elem.get("type") == "seq":
            items = elem.get("items", [])
            if len(items) == 2:
                if items[0].get("type") == "token":
                    sep_elem, item_elem = items[0], items[1]  # (sep, item)*
                    sep_first = True
                elif items[1].get("type") == "token":
                    item_elem, sep_elem = items[0], items[1]  # (item, sep)*

        if sep_elem is not None:
            assert item_elem is not None
            self._log_state("解析分隔列表（零次或多次）")
            collected = []
            if not sep_first:
                # (item, sep)*: 先匹配第一个 item
                with context:
                    first = self._process_production_node(item_elem, context)
                    if first is None:
                        r = Node("repeat", items=[])
                        r.sub_node = []
                        return r
                    collected.append(first)
            # 循环匹配 (sep item) 对
            while True:
                with context:
                    if self._process_production_node(sep_elem, context) is None:
                        break
                    next_item = self._process_production_node(item_elem, context)
                    if next_item is None:
                        break
                    collected.append(next_item)
            r = Node("repeat", items=collected)
            r.sub_node = collected[:]
            return r
        self._log_state("解析重复节点（零次或多次）")
        nodes = self._repeat_loop(elem, context) or []
        self._log_state(f"重复解析完成，匹配次数: {len(nodes)}")
        r = Node("repeat", items=nodes)
        r.sub_node = nodes[:]
        return r

    def _parse_optional(self, node: dict, context: ParseContext) -> Optional[Node]:
        elem = node["elem"]
        self._log_state("解析可选节点")
        nodes = self._repeat_loop(elem, context, min_count=0, max_count=1)
        optional_node = Node("optional")
        if nodes:
            optional_node.add_sub_node(nodes[0])
        return optional_node

    def _parse_plus(self, node: dict, context: ParseContext) -> Optional[Node]:
        elem = node["elem"]
        self._log_state("解析至少一次重复节点")
        nodes = self._repeat_loop(elem, context, min_count=1)
        if nodes is None:
            return None
        plus_node = Node("plus")
        for child in nodes:
            plus_node.add_sub_node(child)
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
            self._warn(
                f"没有匹配的语句规则: '{current.content}' (type: {current.type})"
            )
            return None

        for rule in candidates:
            snapshot = context.create_snapshot()
            node = self._try_rule_productions(context, rule)
            if node is not None:
                return node
            context.restore_snapshot(snapshot)

        self._warn(f"所有候选规则匹配失败: '{current.content}' (type: {current.type})")
        return None

    # 解析器的主要输出方法 block
    def _resolve_block_rule(
        self, start_token: Optional[str]
    ) -> Optional[tuple[GrammarRule, str, Optional[str]]]:
        """查找起始符对应的块规则，返回 (matched_rule, block_name, end_token) 或 None"""
        block_rule_name = (
            self.rule_selector.get_block_rule(start_token)
            if start_token is not None
            else None
        )
        self._log_state(f"找到块规则: {block_rule_name}")
        matched_rule = (
            self.grammar_rules.get(block_rule_name) if block_rule_name else None
        )
        if matched_rule is None:
            self._log_state(f"未找到匹配的块规则: {start_token}")
            return None
        block_name = matched_rule.name
        end_token = getattr(matched_rule, "block_end", None)
        return matched_rule, block_name, end_token

    def _consume_start_token(self, context: ParseContext, start_token: str) -> bool:
        """跳过空白并消费起始符，成功返回 True"""
        self._skip_tokens(context, tuple(self.skip_types))
        current = context.peek_token()
        if not current:
            self._log_state(f"期望块开始标记 {start_token}，文件已结束")
            return False
        if current.type == start_token:
            context.advance_token()
            return True
        # 如果期待 space.indent 但遇到了 space.dedent，说明延续行对齐
        if start_token == "space.indent":
            while current and current.type == "space.dedent":
                context.advance_token()
                current = context.peek_token()
            if current and current.type == "space.indent":
                context.advance_token()
            return True
        self._log_state(f"期望块开始标记 {start_token}，实际为 {current.type}")
        return False

    def _parse_block_body(
        self, context: ParseContext, block_node: Node, end_token: Optional[str]
    ) -> None:
        """循环解析句子直到遇到结束符或文件末尾，将子句添加到 block_node"""
        while context.has_more_tokens():
            self._skip_tokens(context, tuple(self.skip_types))
            if not context.has_more_tokens():
                break
            current = context.peek_token()
            assert current is not None
            if current.type == end_token:
                context.advance_token()  # 消费结束符
                break
            stmt_node = self.parse_sentence(context)
            if stmt_node is None:
                self._warn(
                    f"无法解析的 token: '{current.content}' (type: {current.type})"
                )
                break
            block_node.add_sub_node(stmt_node)

    def parse_block(
        self, context: ParseContext, start_token: Optional[str] = None
    ) -> Optional[Node]:
        """
        解析一个代码块。

        1. 根据起始符 start_token 查找匹配的块规则
        2. 消费起始符
        3. 循环解析句子直到遇到结束符，返回块节点
        """
        self._log_state(
            f"进入 parse_block, start_token={start_token}, 当前 token: {context.peek_token() if context.has_more_tokens() else 'EOF'}"
        )
        resolved = self._resolve_block_rule(start_token)
        if resolved is None:
            return None
        _, block_name, end_token = resolved

        if start_token and not self._consume_start_token(context, start_token):
            return None

        block_node = Node(block_name)
        self._parse_block_body(context, block_node, end_token)
        return block_node

    # 解析器的入口
    def parse(self, tokens: List[Token]) -> Optional[Node]:
        context = ParseContext(tokens)
        block_node = self.parse_block(context, start_token="")
        return block_node if block_node else None
