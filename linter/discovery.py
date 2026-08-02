"""discovery.py — 发现阶段：token 流 → 自动注册的扁平检查器列表。

把源 token 流"变形"为轻量 AST（DiscoveredNode 列表），每个节点描述
一种被发现的语法结构及其 token 区间。检查阶段据此实例化对应 Checker。

发现策略（决策 1：动态前瞻逐步缩小范围）：
    - 用块边界维护上下文栈（top / module_body / proc_body / gen_body）
    - 在上下文中逐 token 扫描：
        关键字/具体符号触发 → 直接注册（A 类）
        标识符触发 → 上下文过滤 + 下一 token 前瞻消歧（B 类）
    - 注册语句后跳到其 end_case 边界，继续扫描（嵌套语句被自然发现，
      因为 body 区间在后续扫描中会再次命中）
"""

from __future__ import annotations

from core.define import Token

from .checker import (
    CTX_PROC_BODY,
    CTX_TOP,
    DiscoveredNode,
)
from .lookahead import LookaheadTable

# 通用词法常量（语言无关，自包含于引用处；原 linter/_constants.py 已删）
_TRIVIA = frozenset({"space.fold", "space", "comment", "newline"})
from lexer.lexer_utils import semicolon_token_type

# 分号 token 类型（句子终止符，从 lexer.token_base 配置推导，构造期已加载）。
_SEMICOLON_TYPE: str | None = None


def _semicolon_type() -> str:
    global _SEMICOLON_TYPE
    if _SEMICOLON_TYPE is None:
        _SEMICOLON_TYPE = semicolon_token_type()
    return _SEMICOLON_TYPE


class Discovery:
    """发现器：产出自动注册的扁平节点列表。"""

    def __init__(
        self,
        tree: dict,
        block_openers: frozenset[str],
        block_closers: frozenset[str],
        bracket_openers: frozenset[str],
        bracket_closers: frozenset[str],
        module_item_rule: str,
        stmt_rule: str,
        opener_ctx: dict[str, str] | None = None,
        matcher=None,
    ) -> None:
        self._tree = tree
        self._lookahead = LookaheadTable(
            tree, module_item_rule, stmt_rule, matcher=matcher
        )
        # 过程体语句入口选择器名（配置驱动，用于引用式容器 body 上下文判断）
        self._stmt_rule = stmt_rule
        self._block_openers = block_openers
        self._block_closers = block_closers
        self._bracket_openers = bracket_openers
        self._bracket_closers = bracket_closers
        # 块 opener → 消歧上下文（配置驱动，缺省沿用当前上下文）
        self._opener_ctx = opener_ctx or {}
        # 块结束符集合：作为语句扫描的终止符（替代硬编码 endmodule 等）
        self._block_ends = frozenset(
            info["block_end"]
            for info in tree.values()
            if isinstance(info, dict) and info.get("block_end")
        )

    def discover(self, tokens: list[Token]) -> list[DiscoveredNode]:
        """扫描 token 流，递归发现嵌套节点，返回树（children 填充）。"""
        return self._discover_range(tokens, 0, len(tokens), CTX_TOP, 0)

    def _discover_range(
        self,
        tokens: list[Token],
        start: int,
        end: int,
        context: str,
        depth: int,
    ) -> list[DiscoveredNode]:
        """在 [start, end) 区间内扫描语句；块容器递归产出 children。

        层级最多到句子级：递归进入块 body 发现句子节点，不深入句子内部
        （表达式/字面量等黑盒）。句子结束边界由 production 推导（见
        _statement_end），不依赖 end_case 手写值。
        """
        nodes: list[DiscoveredNode] = []
        i = start
        while i < end:
            i = self._skip(tokens, i, end)
            if i >= end:
                break
            t = tokens[i]

            if t.type == "newline":
                i += 1
                continue

            # 括号内容整体跳过（端口列表/参数列表等），避免内部 token 误判
            if t.type in self._bracket_openers:
                i = self._skip_balanced(tokens, i, end)
                continue

            # 块边界 → 注册块节点 + 递归 body 产出 children
            if t.type in self._block_openers:
                candidates = self._lookahead.classify(tokens, i, context)
                end_idx = i + 1
                if candidates:
                    rule = candidates[0] if len(candidates) == 1 else candidates
                    be = (
                        self._tree.get(candidates[0], {}) or {}
                    ).get("block_end") or ""
                    end_idx = self._skip_to_end(tokens, i, {be}, end) if be else i + 1
                    if end_idx > i:
                        node = DiscoveredNode(
                            type="statement",
                            rule=rule,
                            start=i,
                            end=end_idx,
                            context=context,
                        )
                        body_start, body_end = self._block_body(
                            tokens, i, end_idx, candidates[0], end
                        )
                        if body_start < body_end:
                            node.children = self._discover_range(
                                tokens,
                                body_start,
                                body_end,
                                self._opener_ctx.get(t.type, context),
                                depth + 1,
                            )
                        nodes.append(node)
                i = end_idx
                continue

            if t.type in self._block_closers:
                i += 1
                continue

            # 语句发现：上下文 + 动态两级消歧
            candidates = self._lookahead.classify(tokens, i, context)
            if candidates:
                rule = candidates[0] if len(candidates) == 1 else candidates
                if isinstance(candidates[0], str) and self._is_nested_container(
                    candidates[0]
                ):
                    # 容器节点边界 = body 语句的显式终止符（分号/块结束，depth 0），
                    # 覆盖单语句 body（如 for 的单语句/if 的 else 链）而非在头行尾
                    # 截断——头内分号（for 的 init/cond）在括号 depth>0 被跳过。
                    e = self._skip_to_end(
                        tokens,
                        i,
                        {_semicolon_type()} | self._block_ends,
                        end,
                    )
                else:
                    e = self._statement_end(tokens, i, candidates[0], end)
                if e > i:
                    node = DiscoveredNode(
                        type="statement",
                        rule=rule,
                        start=i,
                        end=e,
                        context=context,
                    )
                    # 引用式容器（production 含 @Stmt/@BeginEnd）→ 定位 body 递归
                    if isinstance(candidates[0], str) and self._is_nested_container(
                        candidates[0]
                    ):
                        body = self._locate_stmt_body(tokens, i, candidates[0], e)
                        if body is not None:
                            bs, _, entry = body
                            # body 入口是过程体语句选择器（配置 stmt_rule）→ proc_body；
                            # 否则继承当前上下文（if/for/case 在 proc 内维持 proc）。
                            bctx = (
                                CTX_PROC_BODY
                                if entry == self._stmt_rule
                                else context
                            )
                            if bs < e:
                                node.children = self._discover_range(
                                    tokens, bs, e, bctx, depth + 1
                                )
                    nodes.append(node)
                    i = e
                    continue
            i += 1
        return nodes

    # ── 辅助 ────────────────────────────────────

    def _is_nested_container(self, rule: str) -> bool:
        """规则是否引用式容器：production 含 @Stmt/@BeginEnd 类语句/块 call。

        配置驱动（不硬编码规则名）：call 目标 is_statement 或 is_block 即容器。
        """
        info = self._tree.get(rule, {})
        return any(self._feat_calls_stmt(f) for f in info.get("prods", []))

    def _feat_calls_stmt(self, feat) -> bool:
        """feature 是否（直接/穿透包装规则）引用语句或块规则。"""
        if not isinstance(feat, dict):
            return False
        typ = feat.get("type")
        if typ == "call":
            tinfo = self._tree.get(feat.get("name", ""), {})
            if tinfo.get("is_statement") or tinfo.get("is_block"):
                return True
            # 包装规则（纯 @ 分派选择器，如 ForBodyStmt → @Stmt|@BeginEnd）→ 穿透
            return self._inner_stmt_entry(feat.get("name", "")) is not None
        if typ in ("optional", "repeat", "plus"):
            return self._feat_calls_stmt(feat.get("elem"))
        if typ == "seq":
            return any(self._feat_calls_stmt(x) for x in feat.get("items", []))
        if typ == "choice":
            return any(
                self._feat_calls_stmt(x) for x in feat.get("alternatives", [])
            )
        return False

    def _inner_stmt_entry(self, name: str) -> str | None:
        """包装规则（纯 @ 分派选择器）→ 内部首个语句/块入口名（如 ForBodyStmt→Stmt）。"""
        info = self._tree.get(name, {})
        prods = info.get("prods", [])
        if len(prods) == 1:
            return self._find_stmt_in_feat(prods[0])
        return None

    def _find_stmt_in_feat(self, feat):
        """在 feature 内递归找首个语句/块入口名（穿透包装）。"""
        if not isinstance(feat, dict):
            return None
        typ = feat.get("type")
        if typ == "call":
            tinfo = self._tree.get(feat.get("name", ""), {})
            if tinfo.get("is_statement") or tinfo.get("is_block"):
                return feat["name"]
            return self._inner_stmt_entry(feat.get("name", ""))
        if typ == "choice":
            for alt in feat.get("alternatives", []):
                r = self._find_stmt_in_feat(alt)
                if r:
                    return r
            return None
        if typ == "seq":
            for item in feat.get("items", []):
                r = self._find_stmt_in_feat(item)
                if r:
                    return r
            return None
        if typ in ("optional", "repeat", "plus"):
            return self._find_stmt_in_feat(feat.get("elem"))
        return None

    def _locate_stmt_body(
        self, tokens: list[Token], i: int, rule: str, end: int
    ) -> tuple[int, int, str] | None:
        """定位引用式容器 production 中首个语句/块元素的 token 区间。

        用共享 matcher 逐元素匹配 production，遇到 is_statement/is_block 的
        call（@Stmt/@BeginEnd 等）即记录其起始位置。返回 (body_start, body_end, 入口规则名)。
        """
        matcher = self._lookahead._matcher
        if matcher is None:
            return None
        info = self._tree.get(rule, {})
        j = i
        for feat in info.get("prods", []):
            if j >= end or not isinstance(feat, dict):
                break
            name = feat.get("name") if feat.get("type") == "call" else ""
            if name:
                tinfo = self._tree.get(name, {})
                if tinfo.get("is_statement") or tinfo.get("is_block"):
                    return j, end, name
                # 包装规则穿透：body 起始 = 该 call 匹配起始，入口 = 内部语句名
                inner = self._inner_stmt_entry(name)
                if inner:
                    return j, end, inner
            trial: list = []
            try:
                k = matcher.match(tokens, j, feat, trial, end, strict=True)
            except Exception:
                break
            j = k if k > j else j + 1
        return None

    def _statement_end(self, tokens: list[Token], i: int, rule: str, n: int) -> int:
        """确定语句的粗略边界（production 推导结束符，其次 end_case）。

        单 token 语句（如 NullStmt 的分号）只消费起始 token，
        避免 end_case=["newline"] 在单行文件里延伸吞掉后续语句。
        """
        if self._is_single_token_rule(rule):
            return i + 1
        # 结束符优先从 production 推导（production 即真相）：结尾纯字面 token
        # （如分号）是句子天然结束边界，不依赖手写 end_case。
        ec = self._derived_end_case(rule)
        if not ec:
            ec = self._lookahead.end_case(rule)
        if ec:
            return self._skip_to_end(tokens, i, ec, n)
        # 无 end_case → 跳到分号或行尾
        return self._skip_to_statement_end(tokens, i, n)

    def _derived_end_case(self, rule: str) -> set[str]:
        """从 production 推导结束符：结尾纯字面 token（非 @、无 ?*+ 后缀）。

        仅对非容器规则推导——容器（case/if/for 等含 @Stmt body）内部有分号，
        结尾字面 token 不是唯一终止，强行推导会截断在内部语句处。容器回退到
        配置 end_case。返回空集表示无可推导结束符。
        """
        if self._is_nested_container(rule):
            return set()
        info = self._tree.get(rule, {})
        prods = info.get("prods", [])
        if not prods:
            return set()
        last = prods[-1]
        if isinstance(last, dict) and last.get("type") == "token":
            return {last["token_type"]}
        return set()

    def _is_single_token_rule(self, rule: str) -> bool:
        """production 只有单个字面 token（如 NullStmt 的 ';'）。"""
        info = self._tree.get(rule, {})
        prods = info.get("prods", [])
        if len(prods) != 1:
            return False
        first = prods[0]
        if first.get("type") != "token":
            return False
        # 含 "|" 的多 token 候选（如 keyword.case|casex）不算单 token
        return "|" not in first.get("token_type", "")

    def _block_body(
        self,
        tokens: list[Token],
        i: int,
        end_idx: int,
        rule: str,
        n: int,
    ) -> tuple[int, int]:
        """块 body 区间：块头 production 匹配结束后 ~ block_end 前。

        块头即块规则 production 内容（剥离 block_start/block_end 后），复用共享
        matcher 做生成式分析：有深度的 @call 递归匹配，无深度的字面 token 作为
        同步词消费（分号无深度 → 天然同步信号，无需"头结束符"语义假设）。匹配
        到 production 末尾即 body 起点。end_idx 是 block_end token 之后的位置，
        body_end = end_idx - 1（不含 end）。
        """
        matcher = self._lookahead._matcher
        start = i + 1
        if matcher is not None:
            prods = (self._tree.get(rule, {}) or {}).get("prods", [])
            if prods:
                trial: list = []
                try:
                    j = matcher.match_rule(tokens, i + 1, prods, trial, end_idx)
                except Exception:
                    j = i + 1
                if j > i + 1:
                    start = j
        end = max(start, end_idx - 1)
        return start, end

    def _skip_to_statement_end(self, tokens: list[Token], i: int, n: int) -> int:
        depth = 0
        while i < n:
            t = tokens[i]
            if t.type in self._bracket_openers:
                depth += 1
            elif t.type in self._bracket_closers:
                depth = max(0, depth - 1)
            elif depth == 0 and (
                t.type in (_semicolon_type(), "newline")
                or t.type in self._block_ends
            ):
                return i + 1
            i += 1
        return n

    def _skip_to_end(
        self, tokens: list[Token], i: int, end_set: set[str], n: int
    ) -> int:
        depth = 0
        exclude = {s[1:] for s in end_set if s.startswith("!")}
        positive = {s for s in end_set if not s.startswith("!")}
        if not positive:
            j = self._skip(tokens, i + 1, n)
            return j if j <= n else n
        while i < n:
            t = tokens[i]
            if t.type in exclude:
                i += 1
                continue
            if t.type in positive and depth == 0:
                return i + 1
            if t.type in _TRIVIA:
                i += 1
                continue
            if t.type in self._block_openers:
                depth += 1
            elif t.type in self._block_closers:
                depth = max(0, depth - 1)
            i += 1
        return n

    def _skip_balanced(
        self,
        tokens: list[Token],
        i: int,
        n: int,
    ) -> int:
        """从开括号位置跳过配对的括号内容（含嵌套）。"""
        depth = 1
        i += 1
        while i < n and depth > 0:
            t = tokens[i]
            if t.type in self._bracket_openers:
                depth += 1
            elif t.type in self._bracket_closers:
                depth -= 1
            i += 1
        return i

    @staticmethod
    def _next_type(tokens: list[Token], i: int, n: int) -> str:
        while i < n and tokens[i].type in _TRIVIA:
            i += 1
        return tokens[i].type if i < n else ""

    @staticmethod
    def _skip(tokens: list[Token], i: int, n: int) -> int:
        while i < n and tokens[i].type in _TRIVIA:
            i += 1
        return i
