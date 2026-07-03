"""
node_parsers.py — 生产式子句对应的 _parse_* 方法

职责：处理 token/call/seq/choice/repeat/optional/plus 等
production feature 类型的递归解析。
"""

from typing import Optional, List
from core.define import Node
from .parser_core import ParseContext


class _SequenceMatchError(Exception):
    """序列匹配失败时抛出的内部异常"""

    pass


class _BranchMatchError(Exception):
    """分支匹配失败时抛出的内部异常"""

    pass


def parse_token(self, node: dict, context: ParseContext) -> Optional[Node]:
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


def parse_call(self, node: dict, context: ParseContext) -> Optional[Node]:
    """调用另一个语法规则"""
    rule_name = node["name"]
    self._log_state(f"调用规则: {rule_name} | {self._debug_token_info(context)}")
    snapshot = context.create_snapshot()

    target_rule = self.grammar_rules[rule_name]
    result_node = self._try_rule_productions(context, target_rule)
    if result_node is None:
        context.restore_snapshot(snapshot)
        return None
    return result_node


def parse_seq(self, node: dict, context: ParseContext) -> Optional[Node]:
    """顺序序列：所有子项依次匹配"""
    items = node["items"]
    self._log_state(f"解析序列节点 | {self._debug_token_info(context)}")
    try:
        with context:
            seq_node = Node("seq")
            for item in items:
                result = self._process_production_node(item, context)
                if result is None:
                    raise _SequenceMatchError()
                seq_node.add_sub_node(result)
            self._log_state(f"序列解析成功 | {self._debug_token_info(context)}")
            return seq_node
    except _SequenceMatchError:
        self._log_state(f"序列项匹配失败 | {self._debug_token_info(context)}")
        return None


def parse_choice(self, node: dict, context: ParseContext) -> Optional[Node]:
    """分支选择：依次尝试每个分支"""
    alternatives = node["alternatives"]
    self._log_state(f"解析分支节点 | {self._debug_token_info(context)}")
    original_pointer = context.token_pointer
    for alt in alternatives:
        context.token_pointer = original_pointer
        try:
            with context:
                result = self._process_production_node(alt, context)
                if result is not None:
                    self._log_state(f"分支匹配成功 | {self._debug_token_info(context)}")
                    return result
                raise _BranchMatchError()
        except _BranchMatchError:
            continue
    context.token_pointer = original_pointer
    self._log_state(f"所有分支匹配失败 | {self._debug_token_info(context)}")
    return None


def repeat_loop(
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


def parse_repeat(self, node: dict, context: ParseContext) -> Optional[Node]:
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


def parse_optional(self, node: dict, context: ParseContext) -> Optional[Node]:
    """可选（零次或一次）"""
    elem = node["elem"]
    self._log_state(f"解析可选节点 | {self._debug_token_info(context)}")
    nodes = repeat_loop(self, elem, context, min_count=0, max_count=1)
    optional_node = Node("optional")
    if nodes:
        optional_node.add_sub_node(nodes[0])
    return optional_node


def parse_plus(self, node: dict, context: ParseContext) -> Optional[Node]:
    """至少一次重复"""
    elem = node["elem"]
    self._log_state(f"解析至少一次重复节点 | {self._debug_token_info(context)}")
    nodes = repeat_loop(self, elem, context, min_count=1)
    if nodes is None:
        return None
    plus_node = Node("plus", items=nodes)
    for child in nodes:
        plus_node.add_sub_node(child)
    return plus_node
