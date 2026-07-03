"""
node_parsers.py — 生产式子句对应的 _parse_* 方法

职责：处理 token/call/seq/choice/repeat/optional/plus 等
production feature 类型的递归解析。
"""

from core.define import Node
from .parser_core import ParseContext
from .rule_matcher import _find_recovery_strategy, _get_prod_features


def _try_recovery_by_path(self, context: ParseContext) -> Node | None:
    """根据当前 context._recovery_path 检查 recovery 配置，返回 ErrorNode 或 None。"""
    rule = getattr(context, "_recovery_rule", None)
    if rule is None:
        return None
    path = getattr(context, "_recovery_path", "")
    if not path:
        return None
    # 解析路径提取 prod_index：路径如 "$3" 或 "$3.$1" → 提取 3
    parts = path.strip("$").split(".")
    try:
        prod_index = int(parts[0]) - 1  # 1-based → 0-based
    except ValueError:
        return None
    # 从缓存中获取 flat 列表
    prods = getattr(rule, "production", [])
    if prod_index < 0 or prod_index >= len(prods):
        return None
    prod_str = prods[prod_index]
    prod_features = _get_prod_features(self, rule, prod_str)
    if prod_features is None:
        return None
    strategy = _find_recovery_strategy(rule, prod_features, prod_index)
    if strategy is None or strategy == "end_case":
        return None
    # 执行策略
    err = Node("Error")
    t = context.peek_token()
    if t is not None:
        err.add_attr("raw", t.content)
        if strategy == "single":
            context.advance_token()
        elif strategy == "bracket":
            depth = 0
            end_case_tokens = set(getattr(rule, "end_case", []))
            end_case_tokens.update(getattr(context, "_end_case_chain", set()))
            while context.has_more_tokens():
                tk = context.peek_token()
                assert tk is not None
                if tk.type in end_case_tokens:
                    break
                from .rule_matcher import _BRACKET_MAP, _INVERSE_BRACKET_MAP
                if tk.type in _BRACKET_MAP:
                    depth += 1
                elif tk.type in _INVERSE_BRACKET_MAP:
                    if depth == 0:
                        break
                    depth -= 1
                context.advance_token()
    return err


class _SequenceMatchError(Exception):
    """序列匹配失败时抛出的内部异常"""

    pass


class _BranchMatchError(Exception):
    """分支匹配失败时抛出的内部异常"""

    pass


def parse_token(self, node: dict, context: ParseContext) -> Node | None:
    """匹配一个普通 token"""
    token_type: str = node["token_type"]
    self._log_state(f"解析普通token: {token_type}")

    if not context.has_more_tokens():
        self._log_state("无更多token可解析")
        return None

    current_token = context.peek_token(offset=0)
    if current_token is None:
        return None

    if token_type != current_token.type:
        self._log_state(
            f"token类型不匹配: 期望 {token_type}, 实际 {current_token.type} "
            f"| {self._debug_token_info(context)}"
        )
        return None

    parsed_node = Node(token_type)
    parsed_node.add_attr("value", current_token.content)
    context.advance_token()

    # 语义路径：消费并记录紧随当前 token 的 inline comment
    # inline comment 不是行尾注释（后继不是 newline），需要跳过以不阻塞生产式匹配
    while True:
        nxt = context.peek_token(offset=0)
        if nxt and nxt.type == "comment":
            path = "/" + "/".join(context.path_stack) + f"/{token_type}/after"
            if path in context.comment_table:
                # 同一槽位多个 comment 按原序合并
                context.comment_table[path] += " " + nxt.content
            else:
                context.comment_table[path] = nxt.content

            # 指纹收集：记录 token 索引（解析后用源 token 流回溯取指纹）
            self._inline_comments.append(
                {
                    "token_index": context.token_pointer - 1,  # 刚消费的 token
                    "text": nxt.content,
                    "line": nxt.line,
                    "column": nxt.column,  # 源列号，用于精确定位
                }
            )

            context.advance_token()
        else:
            break

    self._log_state(
        f"普通token {token_type} 解析成功 | {self._debug_token_info(context)}"
    )
    return parsed_node


def parse_call(self, node: dict, context: ParseContext) -> Node | None:
    """调用另一个语法规则，失败时按 recovery 路径创建 ErrorNode"""
    rule_name = node["name"]
    self._log_state(f"调用规则: {rule_name} | {self._debug_token_info(context)}")
    snapshot = context.create_snapshot()

    target_rule = self.grammar_rules.get(rule_name)
    if target_rule is None:
        context.restore_snapshot(snapshot)
        return _try_recovery_by_path(self, context) or None

    result_node = self._try_rule_productions(context, target_rule)
    if result_node is None:
        context.restore_snapshot(snapshot)
        return _try_recovery_by_path(self, context) or None
    return result_node


def parse_seq(self, node: dict, context: ParseContext) -> Node | None:
    """顺序序列：所有子项依次匹配，带 recovery 寻址"""
    items = node["items"]
    self._log_state(f"解析序列节点 | {self._debug_token_info(context)}")
    try:
        with context:
            seq_node = Node("seq")
            for idx, item in enumerate(items):
                # 扩展 recovery 路径（$1, $2, ...）
                old_path = context._recovery_path
                context._recovery_path = f"{old_path}.${idx + 1}" if old_path else f"${idx + 1}"
                result = self._process_production_node(item, context)
                context._recovery_path = old_path
                if result is None:
                    raise _SequenceMatchError()
                seq_node.add_sub_node(result)
            self._log_state(f"序列解析成功 | {self._debug_token_info(context)}")
            return seq_node
    except _SequenceMatchError:
        self._log_state(f"序列项匹配失败 | {self._debug_token_info(context)}")
        return None


def parse_choice(self, node: dict, context: ParseContext) -> Node | None:
    """分支选择：依次尝试每个分支，带 recovery 寻址"""
    alternatives = node["alternatives"]
    self._log_state(f"解析分支节点 | {self._debug_token_info(context)}")
    original_pointer = context.token_pointer
    for idx, alt in enumerate(alternatives):
        context.token_pointer = original_pointer
        # 扩展 recovery 路径（$1, $2, ...）
        old_path = context._recovery_path
        context._recovery_path = f"{old_path}.${idx + 1}" if old_path else f"${idx + 1}"
        try:
            with context:
                result = self._process_production_node(alt, context)
                if result is not None:
                    context._recovery_path = old_path
                    self._log_state(f"分支匹配成功 | {self._debug_token_info(context)}")
                    return result
                raise _BranchMatchError()
        except _BranchMatchError:
            # 当前分支失败，检查 sub-element recovery
            if context._recovery_path:
                err = self._try_recovery_by_path(context)
                if err is not None:
                    context._recovery_path = old_path
                    self._log_state(f"分支 recovery | {self._debug_token_info(context)}")
                    return err
            continue
        finally:
            context._recovery_path = old_path
    context.token_pointer = original_pointer
    self._log_state(f"所有分支匹配失败 | {self._debug_token_info(context)}")
    return None


def repeat_loop(
    self,
    elem: dict,
    context: ParseContext,
    min_count: int = 0,
    max_count: int | None = None,
) -> list[Node | None] | None:
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


def parse_repeat(self, node: dict, context: ParseContext) -> Node | None:
    """零次或多次重复"""
    elem = node["elem"]
    self._log_state(f"解析重复节点（零次或多次）| {self._debug_token_info(context)}")
    nodes = repeat_loop(self, elem, context) or []
    self._log_state(
        f"重复解析完成，匹配次数: {len(nodes)} | {self._debug_token_info(context)}"
    )
    r = Node("repeat", items=nodes)
    r.sub_node = nodes[:]
    return r


def parse_optional(self, node: dict, context: ParseContext) -> Node | None:
    """可选（零次或一次）"""
    elem = node["elem"]
    self._log_state(f"解析可选节点 | {self._debug_token_info(context)}")
    nodes = repeat_loop(self, elem, context, min_count=0, max_count=1)
    optional_node = Node("optional")
    if nodes and nodes[0] is not None:
        optional_node.add_sub_node(nodes[0])
    return optional_node


def parse_plus(self, node: dict, context: ParseContext) -> Node | None:
    """至少一次重复"""
    elem = node["elem"]
    self._log_state(f"解析至少一次重复节点 | {self._debug_token_info(context)}")
    nodes = repeat_loop(self, elem, context, min_count=1)
    if nodes is None:
        return None
    plus_node = Node("plus", items=nodes)
    for child in nodes:
        plus_node.add_sub_node(child) if child is not None else None
    return plus_node
