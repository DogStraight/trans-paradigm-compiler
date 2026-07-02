"""
block_parser.py — 块 & 语句级解析

职责：parse_sentence, _resolve_block_rule, _consume_start_token,
_parse_block_body, parse_block。
"""

from typing import Optional, Tuple, Callable
from core.define import Node, GrammarRule
from .parser_context import ParseContext

# 块级恢复策略分发表
_BLOCK_RECOVERY_STRATEGIES: dict[str, Callable] = {}


def _register_strategy(name: str):
    """装饰器：注册块恢复策略"""
    def decorator(fn: Callable) -> Callable:
        _BLOCK_RECOVERY_STRATEGIES[name] = fn
        return fn
    return decorator


@_register_strategy("consume_line")
def _recover_consume_line(
    self, context: ParseContext, block_node: Node
) -> bool:
    """吞掉当前行作为 Error 节点，返回 True（继续循环）"""
    err = self._consume_error_line(context)
    if err is not None and getattr(err, "raw", ""):
        block_node.add_sub_node(err)
    return True


def consume_error_line(self, context: ParseContext) -> Node:
    """吞掉当前行并输出 Error 节点（行级错误隔离）。

    当所有候选规则都无法匹配时触发，将无法解析的 token 行包装为 Error 节点，
    让 parse_block_body 可以继续解析后续行，实现行间错误隔离。
    """
    error_node = Node("Error")
    error_node.add_attr("raw", "")

    if not context.has_more_tokens():
        return error_node

    tokens = []
    while context.has_more_tokens():
        t = context.peek_token()
        assert t is not None
        if t.type == "newline":
            context.advance_token()  # 吞掉换行
            break
        tokens.append(t)
        context.advance_token()  # advance 不返回值，需先 peek

    raw = " ".join(t.content for t in tokens)
    error_node.add_attr("raw", raw)
    return error_node


def parse_sentence(self, context: ParseContext) -> Optional[Node]:
    """解析一条语句：根据当前 token 选择候选规则并尝试匹配。"""
    if not context.has_more_tokens():
        return None

    current = context.peek_token()
    if current is None:
        return None

    candidates = self.rule_selector.get_candidate_rules(
        current,
        self.pre_symbols,
        self.pre_hints,
        self.scope_stack.lookup,
    )
    self._log_state(
        f"parse_sentence: {self._debug_token_info(context)} "
        f"candidates={[r.name for r in candidates]}",
        context=context,
    )
    if not candidates:
        return None

    for rule in candidates:
        snapshot = context.create_snapshot()
        scope_depth = self.scope_stack.snapshot()
        node = self._try_rule_productions(context, rule)
        if node is not None:
            return node
        self.scope_stack.restore(scope_depth)
        context.restore_snapshot(snapshot)

    # 所有候选规则都匹配失败 → 简略警告
    rule_hint = ", ".join(r.name for r in candidates[:5])
    if len(candidates) > 5:
        rule_hint += f" ... ({len(candidates)} 个候选)"
    self._warn(
        f"匹配失败: '{current.content}' Ln {current.line} " f"→ 尝试过: {rule_hint}",
        context=context,
    )
    return None


def _get_block_end(rule: GrammarRule) -> str:
    """从规则的 end_case 中提取块结束符（第一个正匹配项，无则返回空字符串）"""
    for item in getattr(rule, "end_case", []):
        if isinstance(item, str) and not item.startswith("!"):
            return item
    return ""


def resolve_block_rule(
    self, start_token: Optional[str]
) -> Optional[Tuple[GrammarRule, str, str]]:
    """查找起始符对应的块规则，返回 (matched_rule, block_name, end_token) 或 None"""
    block_rule_name = (
        self.rule_selector.get_block_rule(start_token)
        if start_token is not None
        else None
    )
    self._log_state(f"找到块规则: {block_rule_name}")
    matched_rule = self.grammar_rules.get(block_rule_name) if block_rule_name else None
    if matched_rule is None:
        self._log_state(f"未找到匹配的块规则: {start_token}")
        return None
    block_name = matched_rule.name
    end_token = _get_block_end(matched_rule)
    return matched_rule, block_name, end_token


def consume_start_token(self, context: ParseContext, start_token: str) -> bool:
    """跳过空白并消费起始符，成功返回 True"""
    self._skip_tokens(context, tuple(self.skip_types))
    current = context.peek_token()
    if not current:
        self._log_state(f"期望块开始标记 {start_token}，文件已结束")
        return False
    if current.type == start_token:
        context.advance_token()
        return True
    self._log_state(f"期望块开始标记 {start_token}，实际为 {current.type}")
    return False


def collect_line_comments(self, context: ParseContext, block_node: Node) -> None:
    """收集行尾注释（comment → newline），并清除后续空白行"""
    while context.has_more_tokens():
        cur = context.peek_token()
        if cur and cur.type == "comment":
            nxt = context.peek_token(offset=1)
            if nxt and nxt.type == "newline":
                comment_node = Node("Comment")
                comment_node.add_attr("value", cur.content)
                block_node.add_sub_node(comment_node)
                context.advance_token()  # 跳过 comment
                context.advance_token()  # 跳过 newline
                continue
        break
    # 清除后续空白行 vs 下一句之间的空行
    self._skip_tokens(context, tuple(self.skip_types))


def _block_recovery_cfg(self, block_node: Node) -> Optional[dict]:
    """读取块规则的 recovery 配置（从 rule.parser 字典中）"""
    rule = (
        self.grammar_rules.get(block_node.node_name)
        if hasattr(self, "grammar_rules")
        else None
    )
    if rule:
        p = getattr(rule, "parser", {})
        if isinstance(p, dict):
            return p.get("recovery")
    return None


def _try_block_recovery(
    self,
    context: ParseContext,
    block_node: Node,
    rule: GrammarRule,
) -> bool:
    """尝试行级恢复，成功返 True（继续循环），否则返 False（终止块）"""
    if not context.has_more_tokens():
        return False
    nxt = context.peek_token()
    if nxt is None:
        return False

    end_case = getattr(rule, "end_case", [])
    has_end_token = any(isinstance(e, str) and not e.startswith("!") for e in end_case)

    # 有明确结束符 → 到达时正常终止
    if has_end_token and nxt.type in end_case:
        return False

    # 无明确结束符时遇到 end 类关键字 → 消费为 ErrorNode 后终止（仅 Root）
    if not has_end_token and nxt.type in getattr(self, "_block_end_types", ()):
        if block_node.node_name == "Root":
            err = self._consume_error_line(context)
            if err is not None and getattr(err, "raw", ""):
                block_node.add_sub_node(err)
        return False

    # 有 consume_line 恢复配置 → 吞行继续
    cfg = _block_recovery_cfg(self, block_node)
    if cfg and isinstance(cfg, dict):
        strategy = cfg.get("strategy")
        if isinstance(strategy, str):
            handler = _BLOCK_RECOVERY_STRATEGIES.get(strategy)
            if handler:
                return handler(self, context, block_node)

    return False


def parse_block_body(
    self,
    context: ParseContext,
    block_node: Node,
    rule: GrammarRule,
) -> None:
    """循环解析句子直到遇到结束符或文件末尾，将子句添加到 block_node"""
    end_token = _get_block_end(rule)

    while context.has_more_tokens():
        self._skip_tokens(context, tuple(self.skip_types))
        if not context.has_more_tokens():
            break
        self._collect_line_comments(context, block_node)
        if not context.has_more_tokens():
            break

        current = context.peek_token()
        assert current is not None
        if current.type == end_token:
            # 不消费 end_token，留给调用方的 production 匹配
            break

        stmt_node = parse_sentence(self, context)
        if stmt_node is None:
            if not getattr(self, "error_recovery", True):
                break
            if _try_block_recovery(self, context, block_node, rule):
                continue
            break
        block_node.add_sub_node(stmt_node)


def parse_block(
    self,
    context: ParseContext,
    start_token: Optional[str] = None,
    rule: Optional[GrammarRule] = None,
) -> Optional[Node]:
    """解析一个代码块。"""
    if rule is not None:
        matched_rule = rule
        block_name = rule.name
    else:
        resolved = resolve_block_rule(self, start_token)
        if resolved is None:
            return None
        matched_rule, block_name, _ = resolved

    self._log_state(
        f"进入 parse_block, block={block_name}, start_token={start_token}, "
        f"当前 token: {context.peek_token() if context.has_more_tokens() else 'EOF'}"
    )

    if start_token and not consume_start_token(self, context, start_token):
        return None

    block_node = Node(block_name)
    parse_block_body(self, context, block_node, matched_rule)
    return block_node
