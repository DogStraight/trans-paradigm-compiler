"""
_production.py — 生产式解析全流程（合并 rule_matcher + node_parsers）

职责：
    production 元素 dispatch → _parse_token / _parse_call / _parse_seq / etc.
    _try_production → _match_productions → _try_rule_productions（全流程）
    _prepare_production → _check_end_case（辅助检查）
Doc: docs/language_walkthrough.md（production 求值引擎）
"""

from core.define import Node, Token, GrammarRule, CHILDREN_FIELD
from .parser_core import ParseContext
from ._constants import BLOCK_NODE_NAME, COMMENT_TOKEN_TYPE, NEWLINE_TOKEN_TYPE
from .rule_selector import analyze_production_features, flatten_production_features
from .follow import token_in_follow

import contextlib

# ── production 元素 dispatch 表 ──
# 取代 getattr(self, f"_parse_{typ}") 的动态查找
_DISPATCH: dict[str, str] = {
    "token": "_parse_token",
    "call": "_parse_call",
    "seq": "_parse_seq",
    "choice": "_parse_choice",
    "repeat": "_parse_repeat",
    "optional": "_parse_optional",
    "plus": "_parse_plus",
}


def process_production_node(self, node: dict, context: ParseContext) -> Node | None:
    """dispatch 到 _parse_* 方法（查表而非 getattr）"""
    # 用 [] 直接索引代替 .get() 避免两次 dict 查找
    typ = node["type"] if "type" in node else None
    if typ is None:
        return None
    method_name = _DISPATCH.get(typ)
    if method_name is None:
        return None
    method = getattr(self, method_name, None)
    if method is None:
        return None
    return method(node, context)


# ── 生产式特征缓存 ──

_prod_feat_cache: dict[str, dict | None] = {}


def _get_prod_features(rule: GrammarRule, prod: str) -> dict | None:
    """获取产生式特征（带缓存）。"""
    key = f"{rule.name}::{prod}"
    cached = _prod_feat_cache.get(key)
    if cached is not None:
        return cached
    feat = analyze_production_features(prod)
    if feat is not None:
        result = {
            "tree": feat,
            "flat": flatten_production_features(prod),
        }
    else:
        result = None
    _prod_feat_cache[key] = result
    return result


# ── 产生式匹配 ──


def _try_production(
    self,
    context: ParseContext,
    rule: GrammarRule,
    prod: str,
) -> Node | None:
    """尝试匹配单个产生式。"""
    features = _get_prod_features(rule, prod)
    if not features:
        return None
    feature_tree = features["tree"]
    if not self._prepare_production(context, feature_tree):
        return None

    snapshot = context.create_snapshot()
    result = process_production_node(self, feature_tree, context)
    if result is not None:
        return result

    context.restore_snapshot(snapshot)
    return None


def match_productions(
    self, context: ParseContext, rule: GrammarRule, prods: list | None = None
) -> list[Node | None] | None:
    """匹配规则的所有产生式。返回 matched_nodes 列表，失败返回 None。

    prods 缺省用 rule.prods（普通规则）；块规则块分支传 rule.block_prods
    （内容部分，block_start/block_end 由块路径单独消费）。
    """
    prods = rule.prods if prods is None else prods
    all_matched_nodes: list[Node | None] = []

    for _, prod in enumerate(prods):
        self._log_state(lambda: f"产生式: {prod} | {self._debug_token_info(context)}")

        result_node = _try_production(self, context, rule, prod)
        if result_node is None:
            return None

        all_matched_nodes.append(result_node)

    return all_matched_nodes


def _first_token_of_spec(spec: str, grammar_rules: dict) -> set[str]:
    """计算一个产生式规格字符串的起始 token 类型集合。"""
    raw = spec.rstrip("?+*")
    if raw.startswith("@"):
        rule = grammar_rules.get(raw[1:])
        if rule:
            prods = getattr(rule, "production", [])
            if prods:
                return _first_token_of_spec(prods[0], grammar_rules)
        return set()
    return {raw}


# ── 规则匹配全流程 ──


@contextlib.contextmanager
def rule_frame(self, context: ParseContext, rule: GrammarRule):
    """规则执行帧：作用域 + 语义路径推入，退出自动恢复。

    收敛 try_rule_productions 原先每个 return 分支的手动
    path_stack.pop()/scope_stack.pop()（~8 处重复，易漏一处致栈泄漏）。
    pratt 规则不推帧（原语义：pratt 分支在作用域推入前 return）。
    """
    rule_parser = getattr(rule, "parser", {})
    scope_def = rule_parser.get("scope") if isinstance(rule_parser, dict) else None
    scope_pushed = False
    if scope_def and isinstance(scope_def, dict):
        scope_kind = scope_def.get("kind", rule.name)
        self.scope_stack.push(rule.name, scope_kind)
        scope_pushed = True

    # 语义路径
    sn = context.sibling_counter.get(rule.name, 0)
    context.sibling_counter[rule.name] = sn + 1
    context.path_stack.append(f"{rule.name}[{sn}]")
    try:
        yield
    finally:
        context.path_stack.pop()
        if scope_pushed:
            self.scope_stack.pop()


def try_block_rule(self, context: ParseContext, rule: GrammarRule) -> Node | None:
    """块规则匹配：起止符消费 + 块头内容 + 块体 + FOLLOW 检查。

    有显式 block_start（如 BeginEnd）：自行消费起止符；匿名块（无 block_start）
    由 parse_block 处理、结束符由父规则负责。帧清理（path_stack/scope_stack）
    由调用方 rule_frame 统一处理，本函数只负责节点恢复。
    """
    bs = getattr(rule, "block_start", None)

    if not bs:
        # 匿名块（无 block.start）：由父规则 production 中的 @ 调用触发
        # 块体由 parse_block 处理，结束符由父规则负责消费
        return self.parse_block(context, start_token="", rule=rule)

    # 1) 消费起始符
    self._skip_tokens(context, tuple(self.skip_types))
    _start_idx = context.token_pointer
    tok = context.peek_token()
    if not tok or tok.type != bs:
        self._record_fail_site(
            context,
            rule=rule.name,
            reason=f"block start mismatch: expected {bs}",
        )
        return None
    context.advance_token()

    # 2) 匹配块头内容 production（block_prods，不含 block_start/block_end）
    rule_node = Node(rule.name)
    if tok is not None:
        # 源位置元数据（语义诊断定位用）：块规则锚定起始符
        rule_node._pos_line = tok.line
        rule_node._pos_col = tok.column
    old_node = context.current_node
    context.update_current_node(rule_node)
    all_matched = match_productions(self, context, rule, rule.block_prods)
    if all_matched is None:
        self._record_fail_site(
            context,
            rule=rule.name,
            reason="block header production failed",
        )
        # 恢复 previous current_node（允许 None——fuzz 发现：畸形 ANSI 端口
        # （如 `input [7:0]` 缺端口名）在句子解析上下文里 current_node 可为
        # None，原 assert 直接崩溃。恢复 None 是合法状态，不得用断言兜错误
        # 路径——用户输入必须软失败（截断/解析错误），不能崩。）
        context.update_current_node(old_node)
        return None
    self._bind_attributes(rule_node, rule, all_matched)

    # 2b) 块头行尾注释迁槽（`module m; // c`，2026-09-13）
    # 块体解析**之前**挂到本节点的 trailing 属于"块头那一行"，不是块尾：
    # 渲染时 trailing 随 tail（`endmodule`/`end`）输出，注释会漂到块末。
    # 迁到 head_trailing，renderer 紧跟 head 输出（同行行尾）。
    _head_slots = getattr(rule_node, "_comment_slots", None)
    if _head_slots and _head_slots.get("trailing"):
        _head_slots["head_trailing"] = _head_slots.pop("trailing")

    # 3) 解析块体
    block_body = Node(BLOCK_NODE_NAME)
    from .block_parser import parse_block_body

    parse_block_body(self, context, block_body, rule)
    body_children = getattr(block_body, CHILDREN_FIELD, [])
    for child in body_children:
        rule_node.add_sub_node(child)

    # 4) 消费结束符
    be = getattr(rule, "block_end", None) or _get_block_end_for(rule)
    if be:
        self._skip_tokens(context, tuple(self.skip_types))
        tok = context.peek_token()
        if tok and tok.type == be:
            context.advance_token()
            # 结束符后行内注释（`end // comment`）一并消费：
            # 块规则结束符不走 parse_token，注释若残留会停在 token 流，
            # 使外层规则的后继检查（FOLLOW）失败回滚。
            while context.has_more_tokens():
                nxt = context.peek_token()
                if nxt and nxt.type == COMMENT_TOKEN_TYPE:
                    if nxt.line == tok.line:
                        # 行尾形态（`end // comment` 同行）→ 挂块规则节点
                        # trailing 槽（结构序渲染 LineSuffix，ADR-0013 注释
                        # 节点元信息）。仅记 inline anchor 的话 restore 只
                        # 回 midline/tpc（宏/非宏均不回行尾普通注释）→ 注释
                        # 丢失（tv80 `end // case: ...` 203 条实测）。
                        slots = getattr(rule_node, "_comment_slots", None)
                        if slots is None:
                            slots = {}
                            rule_node.add_attr("_comment_slots", slots)
                        slots.setdefault("trailing", []).append(nxt.content)
                    else:
                        # 独占形态（结束符后新行注释）→ 现状：inline anchor
                        # 记录（restore 窗口回插），注释不属于本块结束行。
                        self._record_anchor(
                            {
                                "anchor": tok.content,
                                "text": nxt.content,
                                "line": nxt.line,
                                "type": be,
                            },
                            "inline",
                        )
                    context.advance_token()
                else:
                    break

    # 5) FOLLOW 检查（方案 B+）：块规则消费完 block_end 后，下一个 token
    #    也必须是派生 FOLLOW 中的合法后继——与普通规则统一（不再跳过）。
    #    块规则自身 production 完整（首尾字面 token），check_end_case 的
    #    "引用块规则"guard 不触发，走派生 FOLLOW 硬检查。
    if not self._check_end_case(context, rule):
        self._record_fail_site(
            context,
            rule=rule.name,
            reason="block FOLLOW mismatch",
        )
        self._restore_current_node(old_node, context)
        return None

    self._restore_current_node(old_node, context)
    # token 范围（半开 [start, end)）：含 block_start..block_end
    rule_node._tok_span = (_start_idx, context.token_pointer)
    return rule_node


def _starts_line(self, context: ParseContext, tok_idx: int) -> bool:
    """tokens[tok_idx] 是否行首 token（前一非空白/非注释 token 是换行）。

    向前跳过 space.* 与注释（被 production skip 吞掉的注释 token 仍留在
    tokens 流中——`( // head\n input` 的 input 前是已吞注释，行首判定
    需越过它再看 newline）。tok_idx = 规则入口时 peek 的 token 索引
    （匹配完成后 pointer 已移动，不能取当前 token_pointer）。
    """
    if tok_idx < 0:
        return False
    i = tok_idx - 1
    while i >= 0:
        prev = context.tokens[i]
        if prev.type == NEWLINE_TOKEN_TYPE:
            return True
        if prev.type in ("space.fold", "space") or prev.type.startswith("space"):
            i -= 1
            continue
        if prev.type == COMMENT_TOKEN_TYPE:
            i -= 1
            continue
        return False
    return True


def _claim_head_comments(
    self, context: ParseContext, node: Node, end_line: int
) -> None:
    """行首规则成功：领规则内容之前的独占行注释挂节点 Comment 子节点。

    ADR-0013（B1 兜底）：repeat 列表容器**首元素前**的独占行注释
    （`module m (\n // head\n input a`）不在 repeat 迭代窗口（首元素非
    repeat 迭代项），line 通道普通回插删除后无兜底 → 丢失。此类注释被
    production skip 吞进 line 通道（行 < 首元素匹配范围）——由**行首开始
    的规则**成功时领取挂 Comment 子节点（sub_node 首位，独立行注释 =
    Comment 节点，ADR 模型；renderer join 拆段渲染）。

    ADR-0014（①）第二来源：容器**开括号同行**的行内 line comment
    （`sub u (//RF interface\n .port...`）——与 `(` 同行非独占行，B1/B1.3
    窗口不收；行尾注释进 inline 通道（_comment_anchors）、渲染 restore 只
    处理 tpc marker → 不进树即丢。按"紧前 token type 以 bracket.l_ 开头"
    识别容器开括号锚（BRACKET_L_PREFIX，语言无关），与 B1.3 同判据（首
    元素前形态）、同窗口（line < 本规则匹配末行）领取挂 Comment 子节点。

    嵌套安全：
    - 行中开始的规则（如 AnsiInputDecl 内 DeclaratorList 的 declarator）
      不领（_starts_line=False）；
    - 领窗口 = 注释行 < 本规则**匹配末行**——规则内容之后的注释（如 b 行
      尾逗号后的 `// Data`，行 > b 末行）留给后续行首规则（c），源序
      正确；规则入口 peek 可能捕获被吞的注释 token（行号偏小），故不用
      入口行；
    - B1 repeat 上浮 / 已领注释 mark 移除不在列表 → 不重复领（repeat
      迭代项场景由 B1 上浮为 Comment 迭代项，claim 只处理其后的首元素
      前残留——两者 mark 互斥不双份）；行尾漏网（line_only=False）不领。
    """
    subs = getattr(node, "sub_node", None)
    if subs is None:
        subs = []
        setattr(node, "sub_node", subs)

    def _insert(cmt_list: list[dict]) -> None:
        from .block_parser import _derive_comment_node_name, _make_comment_node

        cmt_name = getattr(self, "_gap_comment_node_name", None)
        if cmt_name is None:
            cmt_name = _derive_comment_node_name(self, COMMENT_TOKEN_TYPE)
            self._gap_comment_node_name = cmt_name
        for e in sorted(cmt_list, key=lambda x: x.get("line", 0)):
            cmt = _make_comment_node(cmt_name, e["text"])
            subs.insert(0, cmt)

    # 来源 1（line 通道，B1.3 既有）：独占行注释
    if getattr(self, "_line_comment_anchors", None):
        anchors = self._line_comment_anchors
        lift = [
            e
            for e in anchors
            if e.get("line_only")
            and "tpc:" not in e.get("text", "")
            and e.get("line", -1) < end_line
        ]
        if lift:
            _insert(lift)
            mark = getattr(self, "_mark_comment_collected", None)
            if mark is not None:
                for e in lift:
                    mark(e["text"], e.get("line", 0))

    # 来源 2（inline 通道，ADR-0014 ①）：容器开括号起始的行尾注释
    from core.token_protocol import BRACKET_L_PREFIX

    if getattr(self, "_comment_anchors", None):
        anchors2 = self._comment_anchors
        lift2 = [
            e
            for e in anchors2
            if "tpc:" not in e.get("text", "")
            and e.get("type", "").startswith(BRACKET_L_PREFIX)
            and e.get("line", -1) < end_line
        ]
        if lift2:
            _insert(lift2)
            # 从 inline 通道消除：restore 对普通注释本就跳过（ADR-0013
            # 目标④）——消除是防 pipeline 其它消费路径 + 与 _anchor_seen_
            # inline 一致防回溯重录/外层规则双份（与 line 通道 mark 同语义）
            seen = set((e["text"], e.get("line", 0)) for e in lift2)
            self._anchor_seen_inline.update(seen)
            self._comment_anchors[:] = [
                e
                for e in self._comment_anchors
                if (e["text"], e.get("line", 0)) not in seen
            ]


def try_plain_rule(self, context: ParseContext, rule: GrammarRule) -> Node | None:
    """普通规则匹配链：production 匹配 → 属性绑定 → FOLLOW 检查 → inline。

    帧清理（path_stack/scope_stack）由调用方 rule_frame 统一处理，本函数
    只负责节点恢复。
    """
    self._log_state(
        lambda: f"尝试规则: {rule.name} | {self._debug_token_info(context)}",
        context=context,
    )
    context.update_current_rule(rule)

    rule_node = Node(rule.name)
    _start_tok = context.peek_token()
    _start_idx = context.token_pointer
    if _start_tok is not None:
        # 源位置元数据（语义诊断定位用）：普通规则锚定 production 首个 token
        rule_node._pos_line = _start_tok.line
        rule_node._pos_col = _start_tok.column
    old_node = context.current_node
    context.update_current_node(rule_node)

    all_matched_nodes = match_productions(self, context, rule)
    if all_matched_nodes is None:
        self._record_fail_site(
            context,
            rule=rule.name,
            reason="production match failed",
        )
        return None

    # exclude 负向前瞻（消歧，与 linter matcher 同语义）：规则匹配成功后，
    # 若下一个非 trivia token 命中 exclude 集（如 Declarator 的
    # symbol.base.dot，防声明器吞掉 `spi.slave` 点语法/后续端口），整体
    # 失败回滚。与派生 FOLLOW 正交：FOLLOW 是"后继集合"（宽松），exclude
    # 是"明确拒绝"（严格）——FOLLOW 含运算符家族前缀（symbol.base.）时
    # 家族成员会误放行 exclude token，故 exclude 检查必须先于 FOLLOW。
    _excludes = getattr(rule, "exclude", None) or []
    if _excludes:
        self._skip_tokens(context, tuple(self.skip_types))
        _nxt = context.peek_token()
        if _nxt is not None and _nxt.type in _excludes:
            self._record_fail_site(
                context,
                rule=rule.name,
                reason=f"exclude negative lookahead hit {_nxt.type}",
            )
            self._restore_current_node(old_node, context)
            return None

    # 属性绑定
    self._bind_attributes(rule_node, rule, all_matched_nodes)

    # 后继检查（派生 FOLLOW 硬检查）
    if not self._check_end_case(context, rule):
        self._record_fail_site(
            context,
            rule=rule.name,
            reason="FOLLOW mismatch",
        )
        self._restore_current_node(old_node, context)
        return None

    # Inline 扁平化
    inline_result = self._try_inline_rule(rule, all_matched_nodes, old_node, context)
    if inline_result is not None:
        # 行首规则领前置独占注释（B1.3 兜底，容器首元素前形态）——
        # 仅非 repeat 迭代上下文（repeat 迭代项间注释由 _lift_gap_comments
        # 上浮为 Comment 迭代项，claim 不抢）。inline 弃 rule_node，挂返回
        # 的 inner（Comment 子节点随 inner 进 AST，join 拆段渲染）。
        if _starts_line(self, context, _start_idx) and not getattr(
            self, "_repeat_iter_depth", 0
        ):
            _ptr = context.token_pointer
            _end = context.tokens[_ptr - 1].line if _ptr > 0 else 0
            _claim_head_comments(self, context, inline_result, _end)
        return inline_result

    self._restore_current_node(old_node, context)
    # token 范围（半开 [start, end)）：匹配起始指针 + 结束指针，供增量定位
    rule_node._tok_span = (_start_idx, context.token_pointer)
    self._log_state(f"✓ 规则 {rule.name} 匹配成功", context=context)
    if _starts_line(self, context, _start_idx) and not getattr(
        self, "_repeat_iter_depth", 0
    ):
        _ptr = context.token_pointer
        _end = context.tokens[_ptr - 1].line if _ptr > 0 else 0
        _claim_head_comments(self, context, rule_node, _end)
    return rule_node


def try_rule_productions(self, context: ParseContext, rule: GrammarRule) -> Node | None:
    """尝试匹配一个语法规则的全部逻辑（薄调度器）。

    三形态分派：pratt / 块（_try_block_rule）/ 普通（_try_plain_rule）。
    帧管理（作用域 + 语义路径）由 rule_frame 统一收敛——原单函数 ~180 行、
    8 处重复栈清理（path_stack.pop/scope_stack.pop）易漏，拆后各职责独立。
    """
    # 停点/trace：按规则名或 token 位置过滤（仅真实 Parser 有此方法）
    trace_fn = getattr(self, "_maybe_trace", None)
    if trace_fn is not None:
        trace_fn(context, rule.name)

    # Pratt 规则（不推帧，原语义：pratt 分支在作用域推入前 return）
    if getattr(rule, "pratt", False):
        return self._try_pratt_rule(context, rule)

    with self._rule_frame(context, rule):
        if getattr(rule, "is_block", False):
            return self._try_block_rule(context, rule)
        return self._try_plain_rule(context, rule)


# ── 生产式准备 & 结束符检查 ──


def _is_line_only_comment(context: ParseContext, t: Token) -> bool:
    """独占行注释判定：注释 token 之前（跳过空白/缩进 token）是换行或文件首。

    用于区分：
      - 独占行注释（`\n // State\n`）→ 进树为 Comment 节点（ADR-0013 B1）
      - 行尾注释漏网（`port, // c\n`——collect_following_comments 因中间
        trivia token 未收走而残留到 production skip）→ 保持 line 通道回插
    """
    idx = context.token_pointer
    i = idx - 1
    while i >= 0:
        prev = context.tokens[i]
        if prev.type == NEWLINE_TOKEN_TYPE:
            return True
        if prev.type in ("space.fold", "space") or prev.type.startswith("space"):
            i -= 1
            continue
        return False
    return True


def prepare_production(self, context: ParseContext, features: dict) -> bool:
    """为匹配产生式做准备：跳过空白/注释。"""
    ftype = features["type"] if "type" in features else None
    should_skip = True

    if ftype == "token":
        if features.get("token_type") == COMMENT_TOKEN_TYPE:
            should_skip = False
    elif ftype == "call":
        ref_rule = self.grammar_rules.get(features["name"])
        if ref_rule and getattr(ref_rule, "is_block", False):
            should_skip = False
    elif ftype == "optional":
        should_skip = False
    elif ftype == "repeat" and features.get("min", 0) == 0:
        should_skip = False
    if should_skip:
        self._skip_tokens(context, tuple(self.skip_types))
        while context.has_more_tokens():
            t = context.peek_token()
            if t and t.type == COMMENT_TOKEN_TYPE:
                # 独占行标记（B1 上浮判据）：advance 前判定——向前扫描
                # 注释前一个非空白 token（newline/文件首 = 独占行）。
                # 独占行且非 tpc marker 的注释由所在列表容器的 repeat
                # 上浮为 Comment 迭代项（行号窗口，见 _repeat_loop）；
                # tpc marker（`// <tpc:*>`）排除——宏/条件块还原依赖
                # only_tpc 通道，不进树。
                line_only = _is_line_only_comment(context, t)
                context.advance_token()
                self._skip_tokens(context, tuple(self.skip_types))
                nxt = context.peek_token()
                anchor = nxt.content if nxt else None
                # 锚点精确化（注释节点模型补丁）：端口组间行尾注释（`//Control`）
                # 后常跟 `.o_port` 形态——首 token 是符号 `.`（独立 token），
                # restore 窗口内 `anchor='.'` 命中所有端口行（插错位 + 多注释
                # 竞争 → 非幂等振荡 + 注释丢失）。`.` 后跟标识符（端口名形态）
                # 时拼接成 `.o_x` 唯一锚；restore 匹配失败时回退行首 `.` 匹配
                # （src 未格式化场景行号偏移大，精确锚可能落空）。
                nxt2 = context.peek_token(offset=1)
                if (
                    anchor == "."
                    and nxt2 is not None
                    and nxt2.type not in (COMMENT_TOKEN_TYPE, "newline")
                    and nxt2.content
                    and nxt2.content[0].isalpha()
                ):
                    anchor = anchor + nxt2.content
                self._record_anchor(
                    {
                        "text": t.content,
                        "line": t.line,
                        "anchor": anchor,
                        "line_only": line_only,
                    },
                    "line",
                )
            else:
                break
        if not context.has_more_tokens():
            return False
    return True


def check_end_case(self, context: ParseContext, rule: GrammarRule) -> bool:
    """检查规则匹配后当前 token 是否为合法后继（派生 FOLLOW 硬性检查）。

    判定顺序：
      1. 跳过 trivia（newline/space.fold/comment）后取检查 token——FOLLOW
         是 token 级后继集，trivia 不是语法后继
      2. 块 body 辅助验证（production 引用块规则、body 由 parse_block 管理
         的规则）→ 接受——块边界由结构决定，FOLLOW 检查不适用
      3. 派生 FOLLOW 硬性检查（token ∉ FOLLOW → 拒绝）——parser/follow.py
         从 production 结构机械推导，语法是唯一真相源
      4. 无派生 FOLLOW（不可达规则，到不了此检查）→ 接受
    """
    if not context.has_more_tokens():
        return True

    # 1. peek 跳过 trivia（不消费 token，检查后指针不动）
    token = None
    offset = 0
    while True:
        tok = context.peek_token(offset)
        if tok is None:
            return True
        if tok.type in self.skip_types or tok.type == COMMENT_TOKEN_TYPE:
            offset += 1
            continue
        token = tok
        break

    # 2. 若 body 由 parse_block 管理，边界由结构决定，FOLLOW 检查不适用。
    #    复用 _get_prod_features 缓存（key = rule.name::prod）——原直接
    #    analyze_production_features 每次运行期重新解析 production 字符串
    #    （picorv32 单管线 11.7 万次 build_tree，最大热点）。
    for prod in rule.prods:
        feats = _get_prod_features(rule, prod)
        tree = feats["tree"] if feats else None
        if tree and tree.get("type") == "call":
            inner = self.grammar_rules.get(tree["name"])
            if inner and getattr(inner, "is_block", False):
                return True

    # 3. 派生 FOLLOW 硬性检查
    follows = getattr(self, "_follows", None)
    follow = follows.get(rule.name) if follows is not None else None
    if follow:
        if token_in_follow(token.type, follow):
            return True
        self._log_state(
            f"✗ 后继检查(FOLLOW): 规则 {rule.name} "
            f"后继 '{token.content}' (type={token.type}) "
            f"Ln {token.line} 不在派生 FOLLOW 中",
            context=context,
        )
        return False

    # 4. 无派生 FOLLOW（不可达规则）→ 接受
    return True


# ── 原子解析器：_parse_token / _parse_call / _parse_seq / etc. ──


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
        self._log_state(
            lambda: f"token类型不匹配: 期望 {token_type}, 实际 {current_token.type} | {self._debug_token_info(context)}"
        )
        return None

    parsed_node = Node(token_type)
    parsed_node.add_attr("value", current_token.content)
    context.advance_token()

    # 收集紧随当前 token 的 inline comment（注释节点模型 2b-2，C5 重构提取）
    self._collect_following_comments(context, current_token, token_type)

    self._log_state(
        lambda: f"token {token_type} ok | {self._debug_token_info(context)}"
    )
    return parsed_node


def collect_following_comments(
    self, context: ParseContext, current_token: Token, token_type: str
) -> None:
    """收集紧随 token 的行内注释（注释节点模型 2b-2，C5 重构 2026-08-28）。

    三通道归属（与 renderer 注释模型对应）：
      - 行中注释（注释后同行有非注释 token）：后跟终结符（`;`/`)`/`,`）→
        挂当前节点 trailing 槽位（无后续规则节点可挂）；后跟代码 → 挂
        inline_after 槽位（{锚 token: [(注释, 源行号)]}，token 标注定位，
        渲染端按锚文本插入，无文本锚时 pipeline 兜底 anchors 回插）
      - 行尾注释（注释后 newline）→ 挂当前节点 _comment_slots["trailing"]
        （renderer LineSuffix 结构序渲染）+ _comment_anchors（tpc marker
        还原通道），按 (text, line) 全局去重（parser 回溯双收集 +
        current_node 回溯变化防渲染双份）
    不挂子规则节点：子规则匹配可能回溯重建，注释会随丢弃节点丢失。
    """
    while True:
        nxt = context.peek_token(offset=0)
        if not (nxt and nxt.type == COMMENT_TOKEN_TYPE):
            break
        # 行中注释判定（注释节点模型 2b-2）：注释之后还有同行的非注释
        # token（如 `assign b = /* 嵌入 */ rst_n;` 的注释在 `=` 与 `rst_n`
        # 之间）→ 行中注释，进 pending 队列——由下一个规则节点（parse_call
        # 成功）挂 inline 槽位、或下一终结符挂 trailing（结构序渲染，
        # 替代锚点回插）；不进 _comment_anchors（防 restore 双份）。
        # newline 是独立 token 且与注释同行（行尾注释的正常形态），跳过。
        is_midline = False
        off = 1
        while True:
            after = context.peek_token(offset=off)
            if after is None:
                break
            if after.type in (COMMENT_TOKEN_TYPE, "newline"):
                off += 1
                continue
            is_midline = after.line == nxt.line
            break
        if is_midline:
            if after is not None and after.type.startswith("symbol"):
                # 尾注归属：注释后第一个 token 是终结符（`;`/`)`/`,` 等），
                # 无后续规则节点可挂（如 `assign b = c /* c2 */;` 的注释在
                # `c` 与 `;` 之间）→ 挂当前节点 trailing 槽位。
                cur_node = getattr(context, "current_node", None)
                if isinstance(cur_node, Node):
                    slots = getattr(cur_node, "_comment_slots", None)
                    if slots is None:
                        slots = {}
                        cur_node.add_attr("_comment_slots", slots)
                    slots.setdefault("trailing", []).append(nxt.content)
            else:
                # 行中归属（注释节点模型 2b-2，token 标注定位）：注释在
                # `= /* c */ rst_n` 的 `=` 与 `rst_n` 之间——挂**当前规则
                # 节点**（匹配注释前 token 的 production 节点，确定成功）
                # 的 inline_after 槽位（{锚 token: [(注释, 源行号)]}），
                # 渲染端在布局 line 元素序列里按锚 token 文本定位插入
                # （`=` 后）；布局无文本锚（如 pratt 表达式内的 `+`）时
                # 渲染后未消费 → pipeline 兜底补 anchors 回插。
                cur_node = getattr(context, "current_node", None)
                if isinstance(cur_node, Node):
                    slots = getattr(cur_node, "_comment_slots", None)
                    if slots is None:
                        slots = {}
                        cur_node.add_attr("_comment_slots", slots)
                    ia = slots.setdefault("inline_after", {})
                    ia.setdefault(current_token.content, []).append(
                        (nxt.content, nxt.line)
                    )
        else:
            self._record_anchor(
                {
                    "anchor": current_token.content,
                    "text": nxt.content,
                    "line": nxt.line,
                    "type": token_type,
                },
                "inline",
            )
            # 行尾注释（ADR-0013 目标④后普通注释进树结构序渲染）：挂当前
            # 节点 _comment_slots["trailing"]，render_node 用 LineSuffix 渲染
            # 为 Doc 一等公民（与块结束符行尾/终结符尾注同槽）。下划线属性
            # 穿过 normalizer（transform/normalizer.py 保留）、Node.dump 过滤。
            # 全局去重：parser 回溯会对同一注释重复进入本分支（_comment_anchors
            # 双收集同源），且 current_node 回溯变化会把同一注释挂到多个节点
            # （如列表项 + 列表容器）→ 渲染双份。按 (text, line) 只挂第一处。
            cur_node = getattr(context, "current_node", None)
            if isinstance(cur_node, Node):
                seen = getattr(self, "_trailing_seen", None)
                if seen is None:
                    seen = set()
                    self._trailing_seen = seen
                key = (nxt.content, nxt.line)
                if key not in seen:
                    seen.add(key)
                    slots = getattr(cur_node, "_comment_slots", None)
                    if slots is None:
                        slots = {}
                        cur_node.add_attr("_comment_slots", slots)
                    slots.setdefault("trailing", []).append(nxt.content)
        context.advance_token()


def parse_call(self, node: dict, context: ParseContext) -> Node | None:
    """调用另一个语法规则。"""
    rule_name = node["name"]
    self._log_state(
        lambda: f"调用规则: {rule_name} | {self._debug_token_info(context)}"
    )
    snapshot = context.create_snapshot()

    target_rule = self.grammar_rules.get(rule_name)
    if target_rule is None:
        context.restore_snapshot(snapshot)
        return None

    result_node = self._try_rule_productions(context, target_rule)
    if result_node is None:
        context.restore_snapshot(snapshot)
        return None

    return result_node


def parse_seq(self, node: dict, context: ParseContext) -> Node | None:
    """顺序序列：所有子项依次匹配"""
    items = node["items"]
    self._log_state(lambda: f"解析序列节点 | {self._debug_token_info(context)}")
    # 入口跳过 trivia（newline/space.fold）：seq 是嵌套元素（repeat 迭代项、
    # 括号组等），其子 token 遇换行（多行敏感列表 `a or b\n or c`）需能继续；
    # 规则级跳过由 _try_production 的 prepare_production 负责，嵌套 seq 在此补齐。
    if hasattr(self, "_skip_tokens"):
        self._skip_tokens(context, tuple(self.skip_types))
    with context:
        seq_node = Node("seq")
        for _, item in enumerate(items):
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
    # 入口跳过 trivia：choice 内分支 token 从非 trivia 位置尝试，避免行首
    # newline 使所有分支（纯 token 分支）失配（多行表达式/列表的续行元素）。
    if hasattr(self, "_skip_tokens"):
        self._skip_tokens(context, tuple(self.skip_types))
    for _, alt in enumerate(alternatives):
        context.token_pointer = original_pointer
        with context:
            result = self._process_production_node(alt, context)
            if result is not None:
                return result
    context.token_pointer = original_pointer
    self._log_state(lambda: f"所有分支匹配失败 | {self._debug_token_info(context)}")
    return None


def _lift_gap_comments(
    self, nodes: list, last_end_line: int | None, end_line: int
) -> None:
    """repeat 迭代项间独占行注释上浮为 Comment 迭代项（ADR-0013 B1）。

    列表容器（PortList / NamedPortList / DeclaratorList / CaseItemList 等）
    迭代项之间（如 `input a, // State\n output b` 的 `,` 与下一端口之间）
    的独占行注释，此前被 production skip（prepare_production）吞进
    _line_comment_anchors、渲染后时域回插。现按**源行号窗口**归属：

      上一迭代匹配末行 < 注释行 <= 本次迭代匹配末行 → 注释在本次迭代
      内容之前（项间）→ 上浮为 Comment 迭代项，插在本次迭代结果之前
      （nodes 序列即容器 items 源序——renderer join 识别 _comment 项
      作独立行段渲染）。

    行号窗口解决"嵌套失败迭代吞注释"的归属错位：`input a, // State\n
    output b` 的 `// State` 在 a 的 DeclaratorList 尝试 `, b` 时被吞
    （Declarator 不匹配 output，失败回滚）——注释行在 a 行与 b 行之间，
    由 PortList 的 b 迭代窗口（a 行, b 行] 收走，挂 b 前（源序正确）；
    b 行尾逗号后的 `// Data` 行 > b 行，留给 c 迭代。排除非独占行
    （line_only=False，行尾漏网保持 line 通道）与 tpc marker（only_tpc
    通道，宏/条件块还原依赖）。
    """
    if not getattr(self, "_line_comment_anchors", None):
        return
    anchors = self._line_comment_anchors
    if last_end_line is None:
        lo = -1
    else:
        lo = last_end_line
    lift = [
        e
        for e in anchors
        if e.get("line_only")
        and "tpc:" not in e.get("text", "")
        and e.get("line", -1) > lo
        and e.get("line", -1) <= end_line
    ]
    if not lift:
        return
    from .block_parser import _derive_comment_node_name, _make_comment_node

    cmt_name = getattr(self, "_gap_comment_node_name", None)
    if cmt_name is None:
        cmt_name = _derive_comment_node_name(self, COMMENT_TOKEN_TYPE)
        self._gap_comment_node_name = cmt_name
    for e in lift:
        cmt = _make_comment_node(cmt_name, e["text"])
        nodes.append(cmt)
        # 从 line 通道移除 + 登记 seen（_mark_comment_collected）：注释已由
        # Comment 节点结构序承载，防止后续回溯 re-吞再 append 冗余条目。
        # restore_line_comments 另有 existing_lines 已渲染跳过（双保险）——
        # 若绑定未保留 Comment（非 list-spec 消费的 repeat）则注释未渲染，
        # line 条目仍在可 restore 兜底回插。
        mark = getattr(self, "_mark_comment_collected", None)
        if mark is not None:
            mark(e["text"], e.get("line", 0))


def _repeat_loop(
    self,
    elem: dict,
    context: ParseContext,
    min_count: int = 0,
    max_count: int | None = None,
    lift_gap_comments: bool = True,
) -> list[Node | None] | None:
    """循环匹配 elem，返回压平后的节点列表。

    lift_gap_comments（ADR-0013 B1）：迭代项间独占行注释上浮为 Comment
    迭代项——仅列表容器 repeat（parse_repeat/parse_plus，项有容器 items
    消费端）。parse_optional（单值槽，如 PortParens 的 `@PortList?`）不
    lift：上浮的 Comment 会挤占 optional 的单个内容槽（PortList 被丢弃、
    端口丢失）——optional 内注释保持 line 通道时域回插。
    """
    nodes = []
    # B1 窗口下界：repeat 进入时的源行——本 repeat 之前元素吞的独占注释
    # （行 <= 起点行）不归属本容器；嵌套 repeat（如端口 AnsiOutputDecl 内
    # 的 DeclaratorList）起点行在内层，不会误收外层迭代项间注释。
    start_tok = context.peek_token()
    last_end_line: int | None = start_tok.line if start_tok else 0
    while True:
        snapshot = context.create_snapshot()
        # repeat 迭代深度（B1.3 协调）：迭代项规则（行首）在迭代内匹配，
        # try_plain_rule 的 claim 跳过（迭代项间注释由 _lift_gap_comments
        # 上浮为 Comment 迭代项，ADR 模型优先）；容器首元素（非 repeat）
        # 不在迭代内 → claim 处理首元素前注释。仅 lift 场景标记深度
        # （optional 的单值槽不算迭代项上下文——PortParens `@PortList?`
        # 的首元素 claim 需放行）。
        if lift_gap_comments:
            self._repeat_iter_depth = getattr(self, "_repeat_iter_depth", 0) + 1
        try:
            result = self._process_production_node(elem, context)
        finally:
            if lift_gap_comments:
                self._repeat_iter_depth = getattr(self, "_repeat_iter_depth", 1) - 1
        if result is None:
            context.restore_snapshot(snapshot)
            break
        # B1：迭代成功——行号窗口内独占行注释上浮为 Comment 迭代项
        # （插本次迭代结果之前）。匹配末行 = 本次迭代消费的最后一个
        # token 的源行（失败迭代回滚不更新窗口下界，其吞的注释由后续
        # 成功迭代按行号窗口收走）。
        if lift_gap_comments:
            tokens = context.tokens
            ptr = context.token_pointer
            end_line = tokens[ptr - 1].line if ptr > 0 else 0
            _lift_gap_comments(self, nodes, last_end_line, end_line)
            last_end_line = end_line
        nodes.append(result)
        if max_count is not None and len(nodes) >= max_count:
            break
    return nodes if len(nodes) >= min_count else None


def parse_repeat(self, node: dict, context: ParseContext) -> Node | None:
    """零次或多次重复"""
    elem = node["elem"]
    self._log_state(lambda: f"解析重复节点 | {self._debug_token_info(context)}")
    nodes = _repeat_loop(self, elem, context) or []
    self._log_state(
        lambda: f"重复完成, cnt={len(nodes)} | {self._debug_token_info(context)}"
    )
    r = Node("repeat", items=nodes)
    setattr(r, CHILDREN_FIELD, nodes[:])
    return r


def parse_optional(self, node: dict, context: ParseContext) -> Node | None:
    """可选（零次或一次）"""
    elem = node["elem"]
    self._log_state(lambda: f"解析可选节点 | {self._debug_token_info(context)}")
    nodes = _repeat_loop(
        self, elem, context, min_count=0, max_count=1, lift_gap_comments=False
    )
    optional_node = Node("optional")
    if nodes and nodes[0] is not None:
        optional_node.add_sub_node(nodes[0])
    return optional_node


def parse_plus(self, node: dict, context: ParseContext) -> Node | None:
    """至少一次重复"""
    elem = node["elem"]
    self._log_state(lambda: f"解析至少一次重复节点 | {self._debug_token_info(context)}")
    nodes = _repeat_loop(self, elem, context, min_count=1)
    if nodes is None:
        return None
    plus_node = Node("plus", items=nodes)
    for child in nodes:
        plus_node.add_sub_node(child) if child is not None else None
    return plus_node


def _get_block_end_for(rule) -> str:
    """从规则提取块结束符（block_end 由 production 首尾字面 token 推导）。"""
    if hasattr(rule, "block_end") and rule.block_end:
        return rule.block_end
    return ""


# 公开别名（保持与 parser_core 中 _repeat_loop = repeat_loop 的兼容）
repeat_loop = _repeat_loop
