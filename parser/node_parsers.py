"""
node_parsers.py — 生产式子句对应的 _parse_* 方法

职责：处理 token/call/seq/choice/repeat/optional/plus 等
production feature 类型的递归解析。
"""

from . import rule_matcher
from core.define import Node
from .parser_core import ParseContext


def _try_recovery_by_path(self, context: ParseContext) -> Node | None:
    """子元素级恢复：_parse_call / _parse_choice 内单个引用失败时触发。

    只处理非 skip_to_end 的显式策略（skip_one / skip_to_matching / skip_to_newline），
    skip_to_end 由外层 _try_production 统一处理双路径同步。
    """
    if not getattr(self, "global_recovery", False):
        return None
    rule = getattr(context, "_recovery_rule", None)
    path = getattr(context, "_recovery_path", "")
    if not rule or not path:
        return None
    # 从路径 "$3" 或 "$3.$1" 提取 prod_index
    parts = path.strip("$").split(".")
    try:
        prod_index = int(parts[0]) - 1
    except ValueError:
        return None
    prods = rule.prods
    if prod_index < 0 or prod_index >= len(prods):
        return None
    prod_features = rule_matcher._get_prod_features(self, rule, prods[prod_index])
    if prod_features is None:
        return None
    strategy = rule_matcher._find_recovery_strategy(rule, prod_features, prod_index)
    if strategy is None or strategy == "skip_to_end":
        return None  # skip_to_end 归 _try_production 处理

    t = context.peek_token()
    first_raw = t.content if t else ""
    end_case_tokens = rule_matcher._compute_end_case_tokens(rule, context)
    return rule_matcher._recover_skip_strategy(
        self, context, strategy, first_raw, end_case_tokens,
    )


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

            # 锚点记录：将 inline comment 视为"特殊宏"，锚点为紧前 token 内容
            # 渲染后通过锚点匹配回注，复用宏恢复的文本级替换思路
            self._comment_anchors.append(
                {
                    "anchor": current_token.content,  # 刚消费的 token 内容（锚点）
                    "text": nxt.content,               # 注释文本
                    "line": nxt.line,                  # 源行号，用于搜索窗口
                    "type": token_type,                # 锚点 token 类型
                }
            )

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
        result = _try_recovery_by_path(self, context) or None
        cache[key] = (result, context.token_pointer)
        return result

    result_node = self._try_rule_productions(context, target_rule)
    if result_node is None:
        context.restore_snapshot(snapshot)
        result = _try_recovery_by_path(self, context) or None
        cache[key] = (result, context.token_pointer)
        return result

    cache[key] = (result_node, context.token_pointer)
    return result_node


def parse_seq(self, node: dict, context: ParseContext) -> Node | None:
    """顺序序列：所有子项依次匹配，带 recovery 寻址"""
    items = node["items"]
    self._log_state(lambda: f"解析序列节点 | {self._debug_token_info(context)}")
    with context:
        seq_node = Node("seq")
        for idx, item in enumerate(items):
            old_path = context._recovery_path
            context._recovery_path = (
                f"{old_path}.${idx + 1}" if old_path else f"${idx + 1}"
            )
            result = self._process_production_node(item, context)
            context._recovery_path = old_path
            if result is None:
                return None
            seq_node.add_sub_node(result)
        self._log_state(lambda: f"序列解析成功 | {self._debug_token_info(context)}")
        return seq_node


def parse_choice(self, node: dict, context: ParseContext) -> Node | None:
    """分支选择：依次尝试每个分支，带 recovery 寻址"""
    alternatives = node["alternatives"]
    self._log_state(lambda: f"解析分支节点 | {self._debug_token_info(context)}")
    original_pointer = context.token_pointer
    for idx, alt in enumerate(alternatives):
        context.token_pointer = original_pointer
        old_path = context._recovery_path
        context._recovery_path = f"{old_path}.${idx + 1}" if old_path else f"${idx + 1}"
        with context:
            result = self._process_production_node(alt, context)
            context._recovery_path = old_path
            if result is not None:
                return result
        # 当前分支失败，检查 sub-element recovery
        if context._recovery_path:
            err = self._try_recovery_by_path(context)
            if err is not None:
                context._recovery_path = old_path
                return err
        context._recovery_path = old_path
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
