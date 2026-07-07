"""
node_parsers.py — 生产式子句对应的 _parse_* 方法

职责：处理 token/call/seq/choice/repeat/optional/plus 等
production feature 类型的递归解析。
"""

from core.define import Node
from .parser_core import ParseContext


def parse_token(self, node: dict, context: ParseContext) -> Node | None:
    """匹配一个普通 token"""
    token_type: str = node["token_type"]
    self._log_state(f"解析token: {token_type}")

    if not context.has_more_tokens():
        self._log_state("无更多token可解析")
        return None

    current_token = context.peek_token(offset=0)
    if current_token is None:
        return None

    if token_type != current_token.type:
        self._log_state(lambda: f"token类型不匹配: 期望 {token_type}, 实际 {current_token.type} | {self._debug_token_info(context)}")
        return None

    parsed_node = Node(token_type)
    parsed_node.add_attr("value", current_token.content)
    context.advance_token()

    # 收集紧随当前 token 的 inline comment（仅限同行的注释）
    while True:
        nxt = context.peek_token(offset=0)
        if nxt and nxt.type == "comment":
            self._comment_anchors.append({
                "anchor": current_token.content,
                "text": nxt.content,
                "line": nxt.line,
                "type": token_type,
            })
            context.advance_token()
        else:
            break

    self._log_state(lambda: f"token {token_type} ok | {self._debug_token_info(context)}")
    return parsed_node


def parse_call(self, node: dict, context: ParseContext) -> Node | None:
    """调用另一个语法规则，带 Packrat 记忆化

    缓存 (rule_name, position) → (result, new_position)，
    避免回溯导致同一规则在同一位置被反复尝试。
    缓存仅在同一次 parse() 调用期间有效，不同文件间不共享。
    """
    rule_name = node["name"]
    pos = context.token_pointer

    # Packrat 记忆化：命中则跳过执行直接恢复位置
    cache = self._parse_call_cache
    key = (rule_name, pos)
    if key in cache:
        result, new_pos = cache[key]
        context.token_pointer = new_pos
        return result

    self._log_state(lambda: f"调用规则: {rule_name} | {self._debug_token_info(context)}")
    snapshot = context.create_snapshot()

    target_rule = self.grammar_rules.get(rule_name)
    if target_rule is None:
        context.restore_snapshot(snapshot)
        cache[key] = (None, context.token_pointer)
        return None

    result_node = self._try_rule_productions(context, target_rule)
    if result_node is None:
        context.restore_snapshot(snapshot)
        cache[key] = (None, context.token_pointer)
        return None

    cache[key] = (result_node, context.token_pointer)
    return result_node


def parse_seq(self, node: dict, context: ParseContext) -> Node | None:
    """顺序序列：所有子项依次匹配"""
    items = node["items"]
    self._log_state(lambda: f"解析序列节点 | {self._debug_token_info(context)}")
    with context:
        seq_node = Node("seq")
        for idx, item in enumerate(items):
            result = self._process_production_node(item, context)
            if result is None:
                return None
            seq_node.add_sub_node(result)
        self._log_state(lambda: f"序列解析成功 | {self._debug_token_info(context)}")
        return seq_node


def parse_choice(self, node: dict, context: ParseContext) -> Node | None:
    """分支选择：依次尝试每个分支"""
    alternatives = node["alternatives"]
    self._log_state(lambda: f"解析分支节点 | {self._debug_token_info(context)}")
    original_pointer = context.token_pointer
    for idx, alt in enumerate(alternatives):
        context.token_pointer = original_pointer
        with context:
            result = self._process_production_node(alt, context)
            if result is not None:
                return result
    context.token_pointer = original_pointer
    self._log_state(lambda: f"所有分支匹配失败 | {self._debug_token_info(context)}")
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
    self._log_state(lambda: f"解析重复节点 | {self._debug_token_info(context)}")
    nodes = repeat_loop(self, elem, context) or []
    self._log_state(lambda: f"重复完成, cnt={len(nodes)} | {self._debug_token_info(context)}")
    r = Node("repeat", items=nodes)
    r.sub_node = nodes[:]
    return r


def parse_optional(self, node: dict, context: ParseContext) -> Node | None:
    """可选（零次或一次）"""
    elem = node["elem"]
    self._log_state(lambda: f"解析可选节点 | {self._debug_token_info(context)}")
    nodes = repeat_loop(self, elem, context, min_count=0, max_count=1)
    optional_node = Node("optional")
    if nodes and nodes[0] is not None:
        optional_node.add_sub_node(nodes[0])
    return optional_node


def parse_plus(self, node: dict, context: ParseContext) -> Node | None:
    """至少一次重复"""
    elem = node["elem"]
    self._log_state(lambda: f"解析至少一次重复节点 | {self._debug_token_info(context)}")
    nodes = repeat_loop(self, elem, context, min_count=1)
    if nodes is None:
        return None
    plus_node = Node("plus", items=nodes)
    for child in nodes:
        plus_node.add_sub_node(child) if child is not None else None
    return plus_node
