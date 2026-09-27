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
from core.token_protocol import KEYWORD_PREFIX, TRIVIA_TOKEN_TYPES, skip_trivia, split_token_types

from . import LintDiagnostic, token_span
from .checker import (
    CTX_TOP,
    DiscoveredNode,
)
from .lookahead import LookaheadTable

# discovery 递归深度上限（坏输入收敛防御，见 _discover_range 注释）
_MAX_DISCOVER_DEPTH = 64


def _split_end_set(
    end_set: frozenset[str] | set[str],
) -> tuple[set[str], set[str]]:
    """结束符声明集 → (排除集, 正向集)：`!` 前缀项为排除项。"""
    exclude = {s[1:] for s in end_set if s.startswith("!")}
    positive = {s for s in end_set if not s.startswith("!")}
    return exclude, positive


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
        # 容器结构延续关键字（配置驱动推导，不硬编码；理由见
        # `_derive_continuation_openers`）
        self._continuation_openers = self._derive_continuation_openers(tree)
        # 未识别语句诊断（本次 discover 累积，scan 后由 scanner 合并）。
        self._unrecognized: list[LintDiagnostic] = []

    def _derive_continuation_openers(self, tree: dict) -> frozenset[str]:
        """容器结构延续关键字（配置驱动推导，不硬编码）。

        production 以纯 keyword token 开头、但不启动任何语句/块的规则——如
        else（if 链延续）、default（case 项延续）。children 递归遇到时跳过：
        延续关键字不单独成语句，其 body（块/语句）由后续扫描自然发现；不跳过
        会把 else 当"有语句特征但无匹配"的未识别语句误报。

        精确化：延续关键字 = production **引用语句/块**的容器延续（else →
        @Stmt、default → @StmtOrNull、impl → 块成员）。仅凭"keyword 起始 +
        非语句/块"会把 input/output/parameter/invert 等声明规则误当延续——
        它们在块头内侥幸不触发，但在 body 语境出现会被跳过漏检。引用判定复用
        `_feat_calls_stmt`（穿透包装选择器）。
        """
        stmt_block_firsts: set[str] = set()
        continuation: set[str] = set()
        for info in tree.values():
            if not isinstance(info, dict):
                continue
            prods = info.get("prods") or []
            if not prods or prods[0].get("type") != "token":
                continue
            tok = prods[0].get("token_type", "")
            if info.get("is_statement") or info.get("is_block"):
                stmt_block_firsts.add(tok)
                continue
            if not tok.startswith(KEYWORD_PREFIX):
                continue
            if any(self._feat_calls_stmt(f) for f in prods):
                continuation.add(tok)
        return frozenset(continuation - stmt_block_firsts)

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

        主循环只做分派（按 token 类型四路），每路一个 `_discover_*` 方法：
        括号开启符 / 块开启符 / 闭合与延续关键字 / 语句。
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
            i = skip_trivia(tokens, i, end)
            if i >= end:
                break
            t = tokens[i]

            if t.type == "newline":
                i += 1
                continue

            # 括号内容：先尝试语句分类——`{` 拼接可作赋值 lvalue（{a,b} = expr; ，
            # BlockingAssign 的 first 含 bracket.l_curly_bracket，由 keyword_map
            # 触发），命中即按语句发现；否则整体跳过括号区间（端口/参数列表等）。
            # 仅对无 block_end 的纯语句规则走语句分支（块规则转块分支，见
            # `_discover_bracket`——块规则在此**不能**整体跳过，否则块内语句
            # 既不解析也不诊断）。
            if t.type in self._bracket_openers:
                i = self._discover_bracket(tokens, i, end, context, depth, nodes)
                continue

            # 块边界 → 注册块节点 + 递归 body 产出 children
            if t.type in self._block_openers:
                i = self._discover_block(tokens, i, end, context, depth, nodes)
                continue

            # 块闭合符（end/`}` 等）与容器结构延续关键字（else/default 等，
            # 配置驱动推导）：不单独成语句，跳过——其 body（块/语句）由后续
            # 扫描自然发现。不跳过会把 else 当"有语句特征但无匹配"的未识别
            # 语句误报。
            if t.type in self._block_closers or t.type in self._continuation_openers:
                i += 1
                continue

            i = self._discover_statement(tokens, i, end, context, depth, nodes)
        return nodes

    def _discover_bracket(
        self,
        tokens: list[Token],
        i: int,
        end: int,
        context: str,
        depth: int,
        nodes: list[DiscoveredNode],
    ) -> int:
        """括号开启符：属性对 / 块规则 / 语句分类 / 整体跳过，按序分流。

        Returns: 下一个扫描位置（必定 > i，防死循环）。
        """
        t = tokens[i]
        # 属性对 (* ... *)：整体跳过，不注册语句节点。属性是元数据，
        # 其 body（case/赋值）由后续扫描独立发现——注册 AttrStmt 会因
        # checker 需匹配跨行 body、边界难定而误报。
        if (
            self._attr_openers
            and t.type == self._attr_openers[0]
            and self._next_type(tokens, i + 1, end) == self._attr_openers[1]
        ):
            return self._skip_balanced(tokens, i, end)
        candidates = self._lookahead.classify(tokens, i)
        # 块规则（有 block_end）：括号开启符同时是块开启符（scanner 把括号并入
        # block 起止符集），故此处**必须转块分支**注册块节点并递归 body。此前
        # 落进下面的"整体跳过括号区间"，块内语句既不解析也不诊断（静默漏检）；
        # c4 之所以未暴露，是因为 `_advance_match` 的 `j + 1` 兜底把 body 起点
        # 错算到 `{` 之后一格，绕开了括号分支（偶然生效）。
        if candidates and isinstance(candidates[0], str):
            info = self._tree.get(candidates[0], {}) or {}
            if info.get("block_end"):
                return self._discover_block(tokens, i, end, context, depth, nodes)
        if candidates:
            e = self._statement_end(tokens, i, candidates[0], end)
            if e > i:
                nodes.append(
                    self._make_stmt_node(self._rule_of(candidates), i, e, context)
                )
                return e
        return self._skip_balanced(tokens, i, end)

    def _discover_block(
        self,
        tokens: list[Token],
        i: int,
        end: int,
        context: str,
        depth: int,
        nodes: list[DiscoveredNode],
    ) -> int:
        """块开启符：注册块节点 + 递归 body 产出 children。

        块头 production 不匹配 → 未识别块诊断；块结束符缺失 → 只跳过关键字。
        Returns: 下一个扫描位置（必定 > i）。
        """
        candidates = self._lookahead.classify(tokens, i)
        end_idx = i + 1
        if candidates is None:
            return end_idx
        if not candidates:
            # 块关键字存在但块头 production 不匹配 → 未识别块
            self._record_unrecognized(tokens, i)
            return end_idx
        rule = self._rule_of(candidates)
        be = (self._tree.get(candidates[0], {}) or {}).get("block_end") or ""
        end_idx = self._skip_to_end(tokens, i, {be}, end) if be else i + 1
        if end_idx > i:
            node = self._make_stmt_node(rule, i, end_idx, context)
            body_start, body_end = self._block_body(
                tokens, i, end_idx, candidates[0], end
            )
            if body_start < body_end:
                node.children = self._discover_range(
                    tokens, body_start, body_end, context, depth + 1
                )
            nodes.append(node)
        return end_idx

    def _discover_statement(
        self,
        tokens: list[Token],
        i: int,
        end: int,
        context: str,
        depth: int,
        nodes: list[DiscoveredNode],
    ) -> int:
        """语句发现：动态两级消歧（引用式容器 / 普通语句），必要时递归 body。

        容器式语句（production 含 @Stmt/@BeginEnd）定位 body 后递归；普通语句
        只注册区间不深入（表达式黑盒）。Returns: 下一个扫描位置（必定 > i）。
        """
        candidates = self._lookahead.classify(tokens, i)
        if candidates is None:
            return i + 1
        if not candidates:
            # 有语句起点特征但无任何已知语句规则匹配（拼错关键字/残缺结构头）
            # → 记录未识别诊断，不静默吞错。
            self._record_unrecognized(tokens, i)
            return i + 1
        rule_name = candidates[0]
        nested = isinstance(rule_name, str) and self._is_nested_container(rule_name)
        if nested:
            e = self._container_end(tokens, i, rule_name, end)
        else:
            e = self._statement_end(tokens, i, rule_name, end)
        if e <= i:
            return i + 1
        node = self._make_stmt_node(self._rule_of(candidates), i, e, context)
        if nested:
            self._attach_container_body(node, tokens, i, rule_name, e, context, depth)
        nodes.append(node)
        return e

    def _attach_container_body(
        self,
        node: DiscoveredNode,
        tokens: list[Token],
        i: int,
        rule_name: str,
        e: int,
        context: str,
        depth: int,
    ) -> None:
        """引用式容器（production 含 @Stmt/@BeginEnd）→ 定位 body 递归填 children。"""
        body = self._locate_stmt_body(tokens, i, rule_name, e)
        if body is None:
            return
        bs = body[0]
        # body 上下文继承当前上下文（不假设 stmt_rule → proc_body）。
        bctx = context
        # body 起点必须**严格在规则起点之后**（2026-08-28 坏输入收敛根因防御）：
        # 容器的 body 结构上位于头部 token 之后（if/for 的 body 在 `if (x)` 后），
        # body 起点 == 规则起点意味着"body"即规则自身——inline 语句分派器
        # （如 SimCtrlStmt = choice of 语句规则）的 _locate_stmt_body 返回 choice
        # 起点 == 规则起点，递归区间与自身完全重叠 → 每层注册同一节点直至递归
        # 上限（`assign a = ;` 977 条重复诊断）。语义上语句分派器的嵌套语句由
        # 后续扫描独立发现（扁平化策略），不递归。
        if i < bs < e:
            node.children = self._discover_range(tokens, bs, e, bctx, depth + 1)

    @staticmethod
    def _rule_of(candidates: list) -> "str | list":
        """候选规则 → 节点 rule 值（唯一命中取字符串，多命中取列表）。"""
        return candidates[0] if len(candidates) == 1 else candidates

    @staticmethod
    def _make_stmt_node(
        rule: "str | list", start: int, end: int, context: str
    ) -> DiscoveredNode:
        """构造语句/块区间节点（四处调用点共用字段组合）。"""
        return DiscoveredNode(
            type="statement", rule=rule, start=start, end=end, context=context
        )

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

    def _call_entry(self, name: str) -> str | None:
        """call 元素 → 语句/块入口名（本体即语句/块 → 自身；否则穿透包装）。"""
        tinfo = self._tree.get(name, {})
        if tinfo.get("is_statement") or tinfo.get("is_block"):
            return name
        return self._inner_stmt_entry(name)

    def _first_entry(self, feats) -> str | None:
        """元素序列内首个语句/块入口名（无 → None）。"""
        for feat in feats:
            r = self._find_stmt_in_feat(feat)
            if r:
                return r
        return None

    def _find_stmt_in_feat(self, feat):
        """在 feature 内递归找首个语句/块入口名（穿透包装）。"""
        if not isinstance(feat, dict):
            return None
        typ = feat.get("type")
        if typ == "call":
            return self._call_entry(feat.get("name", ""))
        if typ == "choice":
            return self._first_entry(feat.get("alternatives", []))
        if typ == "seq":
            return self._first_entry(feat.get("items", []))
        if typ in ("optional", "repeat", "plus"):
            return self._find_stmt_in_feat(feat.get("elem"))
        return None

    def _stmt_entry_at(self, feat: dict) -> str | None:
        """当前元素若是语句/块引用 → 入口规则名；否则 None。

        call：本体即语句/块 → 自身名；包装规则 → 内部语句名。
        choice 内直接引用语句/块（如传播产生的 (@AttrStmt|@Stmt)）：entry 仅用于
        标记，递归由 `_discover_range` 独立扫描 [bs, e)，不依赖具体入口名。
        """
        typ = feat.get("type")
        if typ == "call":
            return self._call_entry(feat.get("name", ""))
        if typ == "choice":
            return self._find_stmt_in_feat(feat)
        return None

    def _advance_match(self, tokens: list[Token], j: int, feat, end: int) -> int | None:
        """用共享 matcher 推进一个元素 → 新位置；匹配抛错 → None（停止推进）。

        错误恢复近似（同 `_container_end` / `_skip_to_statement_end`）：匹配抛错时
        停止逐元素推进，让检查阶段报错，discovery 仍能推进。

        ⚠ **零进展时返回 j 本身，不做 `j + 1` 兜底**：调用方 `_locate_stmt_body`
        按 `for feat in prods` 逐元素推进（循环有界，无死循环风险），而
        `@SpecRest*` / `@X?` 这类元素匹配到空是**合法且常见**的。此前的 +1 兜底
        把"空匹配"当成"跳过一格"，于是紧随其后的 `@Declarator` 从 `SpecRest*`
        之后的**下一个** token 起匹配——实测 C 包 `void f(void) { … }`：`f` 被跳过、
        `(void)` 被当 ParenDeclarator 解析（内部报 `unexpected 'void'`），
        `_locate_stmt_body` 因而把 body 起点算到参数位，FuncDef 多注册一个
        `Declaration [3,14)` 子节点并报 `expected ';', got ')'`。
        """
        trial: list = []
        try:
            matcher = self._lookahead._matcher
            if matcher is None:  # 未装载匹配器：与既有 except 同义地放弃该元素
                return None
            return matcher.match(tokens, j, feat, trial, end, strict=True)
        except Exception:
            return None

    def _locate_stmt_body(
        self, tokens: list[Token], i: int, rule: str, end: int
    ) -> tuple[int, int, str] | None:
        """定位引用式容器 production 中首个语句/块元素的 token 区间。

        用共享 matcher 逐元素匹配 production，遇到 is_statement/is_block 的
        call（@Stmt/@BeginEnd 等）即记录其起始位置。返回 (body_start, body_end, 入口规则名)。
        """
        if self._lookahead._matcher is None:
            return None
        info = self._tree.get(rule, {})
        j = i
        for feat in info.get("prods", []):
            if j >= end or not isinstance(feat, dict):
                break
            entry = self._stmt_entry_at(feat)
            if entry:
                return j, end, entry
            j_next = self._advance_match(tokens, j, feat, end)
            if j_next is None:
                break
            j = j_next
        return None

    def _container_end(
        self, tokens: list[Token], i: int, rule: str, end: int
    ) -> int:
        """容器语句边界：头 production 匹配 + 尾部嵌套语句/块的区间延伸。

        容器（if/for/while/always/函数定义等含语句或块 body）production 末尾是
        变长元素（optional/choice/call），结束点由 body 结构决定而非固定 token。
        用 matcher 匹配 production 可正确覆盖尾部结构（如 if 的 else chain）；
        回退 _stmt_ends 会在 then 块 keyword.end 处截断、把 else chain 甩出
        节点（漏检/误报）。匹配失败（无进展/有结构错误）回退 _stmt_ends——
        错误恢复近似（非语法判定）：让检查阶段报错、discovery 仍能推进。

        ⚠ **匹配结果之外的补算**：matcher 对 `@Stmt` / 具体语句规则（is_statement）
        按扁平化策略**不消费**（嵌套语句由发现阶段注册的独立 checker 负责），故
        `match_rule` 的结果可能止于 body 之前。父 checker 的区间若照此截断，
        production 的必选尾部元素仍在 → 报 `unexpected end of statement` 假红
        （C 包实测：`void f(void) { … }` 的 FuncDef 区间止于 `f(void)`）。
        verilog 的容器都经 `@Stmt` 分派器（is_statement=false → 内联匹配）绕过
        该形态，故此前未暴露。此处用 `_stmt_tail_end` 补算尾部语句/块的终点。
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
                    return max(j, self._stmt_tail_end(tokens, i, rule, end))
        return self._skip_to_end(tokens, i, self._lookahead._stmt_ends, end)

    def _stmt_tail_end(self, tokens: list[Token], i: int, rule: str, end: int) -> int:
        """规则 production 内首个语句/块引用元素的自身终点（≤ i 表示无此元素）。

        区间起点严格在规则起点之后才算（body 结构上位于头部 token 之后）；
        body 起点 == 规则起点的分派器（如 `Stmt = choice of 语句`）不补算，
        其嵌套语句由后续扫描独立发现（扁平化策略，同 `_attach_container_body`）。
        """
        body = self._locate_stmt_body(tokens, i, rule, end)
        if body is None:
            return i
        body_start, _, entry = body
        if body_start <= i:
            return i
        return self._stmt_extent(tokens, body_start, entry, end)

    def _stmt_extent(self, tokens: list[Token], pos: int, entry: str, end: int) -> int:
        """语句/块入口在 pos 处的区间终点（块跳 block_end / 容器递归 / 其余推导）。"""
        info = self._tree.get(entry, {}) or {}
        be = info.get("block_end") or ""
        if be:
            return self._skip_to_end(tokens, pos, {be}, end)
        if self._is_nested_container(entry):
            return self._container_end(tokens, pos, entry, end)
        return self._statement_end(tokens, pos, entry, end)

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

    def _terminator_from_call(self, last: dict) -> set[str]:
        """末尾是 call：递归查其 production 是否以语句终结符收尾。

        语句终结符集合 = 所有语句规则末尾字面 token（`_stmt_ends`）减去块结束符
        ——call 内部以"语句终结符"收尾即语句边界。Verilog 为分号
        （symbol.base.semicolon），语言无关：其他语言的分号类终结符同样被推导，
        替代硬编码。
        """
        inner = self._tree.get(last.get("name", ""), {})
        iprods = inner.get("prods", [])
        if not iprods:
            return set()
        ilast = iprods[-1]
        if not isinstance(ilast, dict) or ilast.get("type") != "token":
            return set()
        terminators = self._lookahead._stmt_ends - self._lookahead._block_ends
        if ilast.get("token_type") not in terminators:
            return set()
        return {ilast["token_type"]}

    def _derived_end_case(self, rule: str) -> set[str]:
        """从 production 推导结束符：结尾纯字面 token（非 @、无 ?*+ 后缀）。

        仅对非容器规则推导——容器（case/if/for 等含 @Stmt body）内部有分号，
        结尾字面 token 不是唯一终止，强行推导会截断在内部语句处。容器返回
        空集（回退 _skip_to_statement_end 的通用跳过）。返回空集表示无可
        推导结束符。

        额外：production 末尾是 call（如 ModuleInst 的 @PortConnection 展开
        为 `(...);`）→ 交 `_terminator_from_call` 递归推导，使跨行语句（模块名/
        参数/实例名分多行）以分号为可靠终止（depth 跟踪保证括号内分号不误判）。
        """
        if self._is_nested_container(rule):
            return set()
        prods = (self._tree.get(rule, {}) or {}).get("prods", [])
        if not prods:
            return set()
        return self._end_case_of_last(prods)

    def _end_case_of_last(self, prods: list) -> set[str]:
        """production 末尾元素 → 结束符集（token 字面 / call 递归 / 其余空集）。"""
        last = prods[-1]
        if not isinstance(last, dict):
            return set()
        if last.get("type") == "token":
            # 含 "|" 的多候选 token（如 keyword.case|casex）拆分为精确成员，
            # 否则 _skip_to_end 的精确匹配扫不到（原 _is_single_token_rule 用
            # "|" 排除整个规则，导致这类语句边界退化为通用跳过）。
            return split_token_types(last["token_type"])
        if last.get("type") == "call":
            return self._terminator_from_call(last)
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
                    # 错误恢复近似：匹配无法完成 → 块体起点保持 i+1（不抛给调用方，
                    # 语法错由检查阶段报；同 `_container_end` 的取舍）。
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

    def _is_attr_prefix(self, tokens: list[Token], i: int, n: int) -> bool:
        """位置 i 是否属性对开括号（`(*`）——属性对整体跳过（不改变块 depth）。

        属性后的行尾换行也属于属性前缀（body 从下一行开始），调用方一并跳过
        ——否则换行会被 end_case 当语句边界截断（(* x *) 后换行 case 的边界
        只到属性行）。
        """
        if not self._attr_openers:
            return False
        return (
            tokens[i].type == self._attr_openers[0]
            and self._next_type(tokens, i + 1, n) == self._attr_openers[1]
        )

    def _advance_block_depth(
        self, t: Token, depth: int, positive: frozenset[str] | set[str]
    ) -> tuple[int, bool]:
        """块开/闭符推进深度 → (新深度, 是否命中目标闭合符)。

        命中 = positive 闭合符（如 keyword.end）且当前深度 ≤1：该 token 就是
        目标块结束符。此前缺失该分支：depth 1→0 的 end 被跳过（positive 检查
        在 depth 更新前），容器边界越过正确 end 延伸到 EOF，把后续语句吞进块体。
        """
        if t.type in self._block_openers:
            return depth + 1, False
        if t.type in self._block_closers:
            if t.type in positive and depth <= 1:
                return depth, True
            return max(0, depth - 1), False
        return depth, False

    def _skip_to_end(
        self, tokens: list[Token], i: int, end_set: frozenset[str] | set[str], n: int
    ) -> int:
        """按 end_set 跳过 token 到最后位置（`!` 前缀 = 排除项）。

        `positive` 为空时退化为"跳过一个 trivia 后的位置"；循环内逐 token
        判定排除/命中/空自/属性对/块深度（块深度推进见 `_advance_block_depth`）。
        """
        depth = 0
        exclude, positive = _split_end_set(end_set)
        if not positive:
            j = skip_trivia(tokens, i + 1, n)
            return j if j <= n else n
        while i < n:
            t = tokens[i]
            if t.type in exclude:
                i += 1
                continue
            if t.type in positive and depth == 0:
                return i + 1
            if t.type in TRIVIA_TOKEN_TYPES:
                i += 1
                continue
            if self._is_attr_prefix(tokens, i, n):
                i = skip_trivia(tokens, self._skip_balanced(tokens, i, n), n)
                continue
            depth, hit = self._advance_block_depth(t, depth, positive)
            if hit:
                return i + 1
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
        i = skip_trivia(tokens, i, n)
        return tokens[i].type if i < n else ""
