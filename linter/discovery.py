"""discovery.py — 发现阶段：token 流 → 自动注册的扁平检查器列表。

把源 token 流"变形"为轻量 AST（DiscoveredNode 列表），每个节点描述
一种被发现的语法结构及其 token 区间。检查阶段据此实例化对应 Checker。

Doc: linter/linter_architecture.md
Doc: linter/linter_architecture.md

发现策略（决策 1：动态前瞻逐步缩小范围）：
    - 用块边界维护上下文栈（顶层 CTX_TOP + opener_context 配置的块内上下文）
    - 在上下文中逐 token 扫描：
        关键字/具体符号触发 → 直接注册（A 类）
        标识符触发 → 上下文过滤 + 下一 token 前瞻消歧（B 类）
    - 注册语句后跳到其句子结束边界（production 推导 _stmt_ends/_derived_end_case），
      继续扫描（嵌套语句被自然发现，因为 body 区间在后续扫描中会再次命中）
"""

from __future__ import annotations

from core.define import Token
from core.token_protocol import KEYWORD_PREFIX, TRIVIA_TOKEN_TYPES

from . import LintDiagnostic, token_span
from .checker import (
    CTX_TOP,
    DiscoveredNode,
)
from .lookahead import LookaheadTable

# 通用词法常量（引擎 token 协议，单一事实源 core/token_protocol.py）
_TRIVIA = TRIVIA_TOKEN_TYPES

# discovery 递归深度上限（坏输入收敛防御，见 _discover_range 注释）
_MAX_DISCOVER_DEPTH = 64


def _derive_attr_openers(tree: dict) -> tuple[str, str] | None:
    """从语法树推导属性对开括号（如 (* ... *)）。

    配置驱动：找 production 以 "(" + "*" 两个纯 token 开头的规则
    （如 AttrInstance），返回 (开括号 token, 次 token)。无则 None。
    """
    for info in tree.values():
        if not isinstance(info, dict):
            continue
        prods = info.get("prods") or []
        if len(prods) < 2:
            continue
        p0, p1 = prods[0], prods[1]
        if (
            isinstance(p0, dict)
            and p0.get("type") == "token"
            and p0.get("token_type") == "bracket.l_parentheses"
            and isinstance(p1, dict)
            and p1.get("type") == "token"
            and p1.get("token_type") == "symbol.base.multiple"
        ):
            return ("bracket.l_parentheses", "symbol.base.multiple")
    return None


class Discovery:
    """发现器：产出自动注册的扁平节点列表。"""

    def __init__(
        self,
        tree: dict,
        block_openers: frozenset[str],
        block_closers: frozenset[str],
        bracket_openers: frozenset[str],
        bracket_closers: frozenset[str],
        matcher=None,
        trace: bool | None = None,
    ) -> None:
        self._tree = tree
        self._lookahead = LookaheadTable(
            tree,
            matcher=matcher,
            trace=trace,
        )
        self._block_openers = block_openers
        self._block_closers = block_closers
        self._bracket_openers = bracket_openers
        self._bracket_closers = bracket_closers
        # 属性对开括号推导（配置驱动，不硬编码规则名）：找 production 以
        # "(" + "*" 开头的规则（如 AttrInstance 的 (* ... *)）。_skip_to_end
        # 据此整体跳过属性对，使带属性的语句（如 (* parallel_case *) case ...）
        # 边界不被属性内的括号/newline 截断。
        self._attr_openers = _derive_attr_openers(tree)
        # 容器结构延续关键字（配置驱动推导，不硬编码）：production 以纯
        # keyword token 开头、但不启动任何语句/块的规则——如 else（if 链
        # 延续）、default（case 项延续）。children 递归遇到时跳过：延续
        # 关键字不单独成语句，其 body（块/语句）由后续扫描自然发现；不跳过
        # 会把 else 当"有语句特征但无匹配"的未识别语句误报。
        _stmt_block_firsts: set[str] = set()
        _continuation: set[str] = set()
        for _info in tree.values():
            if not isinstance(_info, dict):
                continue
            _prods = _info.get("prods") or []
            if not _prods or _prods[0].get("type") != "token":
                continue
            _tok = _prods[0].get("token_type", "")
            if _info.get("is_statement") or _info.get("is_block"):
                _stmt_block_firsts.add(_tok)
                continue
            if not _tok.startswith(KEYWORD_PREFIX):
                continue
            # 精确化：延续关键字 = production **引用语句/块**的容器延续
            # （else → @Stmt、default → @StmtOrNull、impl → 块成员）。仅凭
            # "keyword 起始 + 非语句/块"会把 input/output/parameter/invert 等
            # 声明规则误当延续——它们在块头内侥幸不触发，但在 body 语境出现
            # 会被跳过漏检。引用判定复用 _feat_calls_stmt（穿透包装选择器）。
            if any(self._feat_calls_stmt(f) for f in _prods):
                _continuation.add(_tok)
        self._continuation_openers = frozenset(
            _continuation - _stmt_block_firsts
        )
        # 未识别语句诊断（本次 discover 累积，scan 后由 scanner 合并）。
        self._unrecognized: list[LintDiagnostic] = []

    def discover(self, tokens: list[Token]) -> list[DiscoveredNode]:
        """扫描 token 流，递归发现嵌套节点，返回树（children 填充）。"""
        self._unrecognized = []
        return self._discover_range(tokens, 0, len(tokens), CTX_TOP, 0)

    def unrecognized_diagnostics(self) -> list[LintDiagnostic]:
        """本次 discover 期间记录的"未识别语句"诊断。"""
        return list(self._unrecognized)

    def dump_nodes(
        self,
        tokens: list[Token],
        nodes: list[DiscoveredNode] | None = None,
    ) -> str:
        """把发现节点树 dump 为文本：rule + [start,end) → 行号。

        行号同时给 1-based（token.line，lexer/parser 惯例）与 0-based
        （token_span.start.line，LSP 诊断惯例），便于与诊断位置对账。
        """
        if nodes is None:
            nodes = self.discover(tokens)
        lines: list[str] = []

        def walk(items: list[DiscoveredNode], depth: int) -> None:
            for n in items:
                rule = n.rule if isinstance(n.rule, str) else "/".join(n.rule)
                s = n.start
                e = max(n.start, n.end - 1)
                s_line = tokens[s].line if s < len(tokens) else "?"
                e_line = tokens[e].line if e < len(tokens) else "?"
                s_span0 = token_span(tokens[s])[0].line if s < len(tokens) else "?"
                lines.append(
                    f"{'  ' * depth}{rule} [{n.start},{n.end}) "
                    f"L{s_line}-{e_line} (span0 L{s_span0})"
                )
                walk(n.children, depth + 1)

        walk(nodes, 0)
        return "\n".join(lines)

    def _record_unrecognized(self, tokens: list[Token], i: int) -> None:
        """记录"未识别语句"诊断：有语句起点特征但无任何已知规则匹配。

        诊断 message 附带 token 窗口（前后文），覆盖"涉及上下文才触发"
        的错误——单点 token 往往无法定位根因。
        """
        from core.debug_report import format_token_window

        t = tokens[i]
        self._unrecognized.append(
            LintDiagnostic(
                range=token_span(t),
                message=(
                    "unrecognized statement: no grammar rule matches here "
                    f"| {format_token_window(tokens, i)}"
                ),
                severity=1,
                code="phase-unrecognized",
            )
        )

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
        # 递归深度上限（纵深防御，2026-08-28 坏输入收敛）：容器递归与自身
        # 区间重叠等病态输入曾触发 ~978 层递归（受 Python 递归上限约束，
        # 每层注册同一区间节点 → `assign a = ;` 977 条重复诊断）。正常
        # 语句嵌套深度远小于此（begin/end 逐层 +1），阈值截断只影响病态
        # 输入——被截断的子树由检查阶段兜底（缺失区间不注册，不吞错）。
        if depth > _MAX_DISCOVER_DEPTH:
            return []
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

            # 括号内容：先尝试语句分类——`{` 拼接可作赋值 lvalue（{a,b} = expr; ，
            # BlockingAssign 的 first 含 bracket.l_curly_bracket，由 keyword_map
            # 触发），命中即按语句发现；否则整体跳过括号区间（端口/参数列表等）。
            # 仅对无 block_end 的纯语句规则走语句分支（块规则仍由块分支处理）。
            if t.type in self._bracket_openers:
                # 属性对 (* ... *)：整体跳过，不注册语句节点。属性是元数据，
                # 其 body（case/赋值）由后续扫描独立发现——注册 AttrStmt 会因
                # checker 需匹配跨行 body、边界难定而误报。
                if (
                    self._attr_openers
                    and t.type == self._attr_openers[0]
                    and self._next_type(tokens, i + 1, end) == self._attr_openers[1]
                ):
                    i = self._skip_balanced(tokens, i, end)
                    continue
                candidates = self._lookahead.classify(tokens, i)
                if candidates and not (
                    isinstance(candidates[0], str)
                    and (self._tree.get(candidates[0], {}) or {}).get("block_end")
                ):
                    rule = candidates[0] if len(candidates) == 1 else candidates
                    e = self._statement_end(tokens, i, candidates[0], end)
                    if e > i:
                        nodes.append(
                            DiscoveredNode(
                                type="statement",
                                rule=rule,
                                start=i,
                                end=e,
                                context=context,
                            )
                        )
                        i = e
                        continue
                i = self._skip_balanced(tokens, i, end)
                continue

            # 块边界 → 注册块节点 + 递归 body 产出 children
            if t.type in self._block_openers:
                candidates = self._lookahead.classify(tokens, i)
                end_idx = i + 1
                if candidates is None:
                    i = end_idx
                    continue
                if not candidates:
                    # 块关键字存在但块头 production 不匹配 → 未识别块
                    self._record_unrecognized(tokens, i)
                    i = end_idx
                    continue
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
                                context,
                                depth + 1,
                            )
                        nodes.append(node)
                i = end_idx
                continue

            if t.type in self._block_closers:
                i += 1
                continue

            # 容器结构延续关键字（else/default 等，配置驱动推导）：不单独
            # 成语句，跳过——其 body（块/语句）由后续扫描自然发现。不跳过会
            # 把 else 当"有语句特征但无匹配"的未识别语句误报。
            if t.type in self._continuation_openers:
                i += 1
                continue

            # 语句发现：动态两级消歧
            candidates = self._lookahead.classify(tokens, i)
            if candidates is None:
                i += 1
                continue
            if not candidates:
                # 有语句起点特征但无任何已知语句规则匹配（拼错关键字/残缺结构头）
                # → 记录未识别诊断，不静默吞错。
                self._record_unrecognized(tokens, i)
                i += 1
                continue
            if candidates:
                rule = candidates[0] if len(candidates) == 1 else candidates
                if isinstance(candidates[0], str) and self._is_nested_container(
                    candidates[0]
                ):
                    e = self._container_end(tokens, i, candidates[0], end)
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
                            bs, _, _ = body
                            # 实验：body 上下文继承当前上下文（不假设 stmt_rule → proc_body）。
                            bctx = context
                            # body 起点必须**严格在规则起点之后**（2026-08-28
                            # 坏输入收敛根因防御）：容器的 body 结构上位于
                            # 头部 token 之后（if/for 的 body 在 `if (x)` 后），
                            # body 起点 == 规则起点意味着"body"即规则自身——
                            # inline 语句分派器（如 SimCtrlStmt = choice of
                            # 语句规则）的 _locate_stmt_body 返回 choice 起点
                            # == 规则起点，递归区间与自身完全重叠 → 每层注册
                            # 同一节点直至递归上限（`assign a = ;` 977 条
                            # 重复诊断）。语义上语句分派器的嵌套语句由后续
                            # 扫描独立发现（扁平化策略），不递归。
                            if i < bs < e:
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
            typ = feat.get("type")
            name = feat.get("name") if typ == "call" else ""
            if name:
                tinfo = self._tree.get(name, {})
                if tinfo.get("is_statement") or tinfo.get("is_block"):
                    return j, end, name
                # 包装规则穿透：body 起始 = 该 call 匹配起始，入口 = 内部语句名
                inner = self._inner_stmt_entry(name)
                if inner:
                    return j, end, inner
            elif typ == "choice":
                # choice 内直接引用语句/块（如传播产生的 (@AttrStmt|@Stmt)）：
                # body 起始 = choice 起始。entry 仅用于标记，递归由 _discover_range
                # 独立扫描 [bs, e)，不依赖具体入口名。
                inner = self._find_stmt_in_feat(feat)
                if inner:
                    return j, end, inner
            trial: list = []
            try:
                k = matcher.match(tokens, j, feat, trial, end, strict=True)
            except Exception:
                break
            j = k if k > j else j + 1
        return None

    def _container_end(
        self, tokens: list[Token], i: int, rule: str, end: int
    ) -> int:
        """容器语句边界：优先用 matcher 按完整 production 匹配确定。

        容器（if/for/while/always 等含语句/块 body）production 末尾是变长元素
        （optional/choice/call），结束点由 body 结构决定而非固定 token。用
        matcher 匹配 production 可正确覆盖尾部结构（如 if 的 else chain）；
        回退 _stmt_ends 会在 then 块 keyword.end 处截断、把 else chain 甩出
        节点（漏检/误报）。匹配失败（无进展/有结构错误）回退 _stmt_ends——
        错误恢复近似（非语法判定）：让检查阶段报错、discovery 仍能推进。
        """
        matcher = self._lookahead._matcher
        if matcher is not None:
            info = self._tree.get(rule, {}) or {}
            prods = info.get("prods") or []
            if prods:
                trial: list = []
                try:
                    j = matcher.match_rule(tokens, i, prods, trial, end)
                except Exception:
                    j = i
                if j > i and not trial:
                    return j
        return self._skip_to_end(tokens, i, self._lookahead._stmt_ends, end)

    def _statement_end(self, tokens: list[Token], i: int, rule: str, n: int) -> int:
        """确定语句的粗略边界（production 推导结束符）。

        结束符从 production 推导（production 即真相）：结尾纯字面 token
        （如分号）是句子天然结束边界。单字面 token 语句（如 NullStmt 的
        ';'）结束符即自身——_skip_to_end 从起始位置直接命中，等价于"只
        消费起始 token"（原 _is_single_token_rule 特判的语义），无需单独分支。
        """
        ec = self._derived_end_case(rule)
        if ec:
            return self._skip_to_end(tokens, i, ec, n)
        # 无可推导结束符（容器语句等）→ 跳到语句终结符集合/行尾
        return self._skip_to_statement_end(tokens, i, n)

    def _derived_end_case(self, rule: str) -> set[str]:
        """从 production 推导结束符：结尾纯字面 token（非 @、无 ?*+ 后缀）。

        仅对非容器规则推导——容器（case/if/for 等含 @Stmt body）内部有分号，
        结尾字面 token 不是唯一终止，强行推导会截断在内部语句处。容器返回
        空集（回退 _skip_to_statement_end 的通用跳过）。返回空集表示无可
        推导结束符。

        额外：production 末尾是 call（如 ModuleInst 的 @PortConnection 展开
        为 `(...);`）——递归查 call 的 production 是否以分号收尾，是则推导
        分号。这使跨行语句（模块名/参数/实例名分多行）以分号为可靠终止
        （depth 跟踪保证括号内分号不误判）。
        """
        if self._is_nested_container(rule):
            return set()
        info = self._tree.get(rule, {})
        prods = info.get("prods", [])
        if not prods:
            return set()
        last = prods[-1]
        if isinstance(last, dict) and last.get("type") == "token":
            tt = last["token_type"]
            # 含 "|" 的多候选 token（如 keyword.case|casex）拆分为精确成员，
            # 否则 _skip_to_end 的精确匹配扫不到（原 _is_single_token_rule 用
            # "|" 排除整个规则，导致这类语句边界退化为通用跳过）。
            return set(tt.split("|"))
        # 末尾是 call：递归查其 production 是否以语句终结符收尾。语句终结符
        # 集合 = 所有语句规则末尾字面 token（_stmt_ends）减去块结束符——call
        # 内部以"语句终结符"收尾即语句边界。Verilog 为分号（symbol.base.
        # semicolon），语言无关：其他语言的分号类终结符同样被推导，替代硬编码。
        if isinstance(last, dict) and last.get("type") == "call":
            inner = self._tree.get(last.get("name", ""), {})
            iprods = inner.get("prods", [])
            if iprods:
                ilast = iprods[-1]
                stmt_terminators = (
                    self._lookahead._stmt_ends - self._lookahead._block_ends
                )
                if (
                    isinstance(ilast, dict)
                    and ilast.get("type") == "token"
                    and ilast.get("token_type") in stmt_terminators
                ):
                    return {ilast["token_type"]}
        return set()

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
        # 块体终点：end_idx 是 block_end 之后的位置，正常时 end = end_idx - 1
        # （不含 block_end）。若扫描到 EOF（end_idx == n）且末尾 token 不是本
        # 规则 block_end，说明块未正常关闭（如缺 endmodule）——块体应延伸到
        # EOF，而非 end_idx - 1（那会把最后一个 token 误切出块体，使块内末尾
        # 残缺语句的终止检查点丢失 → 缺分号/坏语句体漏检）。
        be = (self._tree.get(rule, {}) or {}).get("block_end") or ""
        if end_idx < n or (end_idx == n and be and tokens[end_idx - 1].type == be):
            end = max(start, end_idx - 1)
        else:
            end = max(start, n)
        return start, end

    def _skip_to_statement_end(self, tokens: list[Token], i: int, n: int) -> int:
        # 错误恢复近似（非语法判定）：无 production 推导结束符时的最终回退。
        # 句子终止 = depth 0 处的"语句终结符集合"（从 production 机械推导：
        # 所有语句规则末尾字面 token ∪ 块结束符，见 LookaheadTable._stmt_ends，
        # 对标 yacc panic mode 的同步 token）∪ 行尾 newline（跨语言 C-like 惯例
        # 近似——语句通常以行分隔，跨行语句由分号等终结符优先终止。此假设不可
        # 从 production/配置推导，是语言建模残差，显式标注而非伪装成引擎协议）。
        # 替代原硬编码 symbol.base.semicolon / newline / block_ends。
        # depth 跟踪保证括号内分号（for 的 init/cond）不截断。
        terminators = self._lookahead._stmt_ends
        depth = 0
        while i < n:
            t = tokens[i]
            if t.type in self._bracket_openers:
                depth += 1
            elif t.type in self._bracket_closers:
                depth = max(0, depth - 1)
            elif depth == 0 and (t.type in terminators or t.type == "newline"):
                return i + 1
            i += 1
        return n

    def _skip_to_end(
        self, tokens: list[Token], i: int, end_set: frozenset[str] | set[str], n: int
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
            # 属性对 (* ... *)：整体跳过（不改变块 depth）。属性后的行尾换行
            # 也属于属性前缀（body 从下一行开始），一并跳过——否则换行会被
            # end_case 当语句边界截断（(* x *) 后换行 case 的边界只到属性行）。
            if (
                self._attr_openers
                and t.type == self._attr_openers[0]
                and self._next_type(tokens, i + 1, n) == self._attr_openers[1]
            ):
                i = self._skip_balanced(tokens, i, n)
                i = self._skip(tokens, i, n)
                continue
            if t.type in self._block_openers:
                depth += 1
            elif t.type in self._block_closers:
                # positive 闭合符（如 keyword.end）使深度归零 → 该 token 就是
                # 目标块结束符，返回其之后位置。此前缺失此分支：depth 1→0 的
                # end 被跳过（positive 检查在 depth 更新前），容器边界越过正确
                # end 延伸到 EOF，把后续语句吞进块体。
                if t.type in positive and depth <= 1:
                    return i + 1
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
