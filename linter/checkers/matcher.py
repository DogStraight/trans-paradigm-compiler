"""checkers/matcher.py — 共享规则匹配器（RuleMatcher）。

从 production 树内联匹配规则，供两个检查器复用：
    - StatementChecker：在语句区间内按 production 精确匹配
    - ExpressionChecker：pratt 的 atom_parser 回调经 match_atom 识别 Verilog 原子
      （BitWidthLiteral / ConcatExpr / ReplicateExpr / SelectExpr / CallExpr ...），
      原子由 is_atom 规则 production 驱动（参考 parser atomic_rules），不手写。

Doc: linter/linter_architecture.md
Doc: linter/linter_architecture.md

strict 语境约定：
    - strict=True  — 必选位置（production 顶层）：token 失败报错 + 跳过恢复
    - strict=False — 可选语境（choice/optional/repeat 内）：失败不推进
      防止"吞 token 推进"的错误分支在 choice 中胜出。
"""

from __future__ import annotations

from contextlib import contextmanager

from core.define import Token
from core.token_protocol import TRIVIA_TOKEN_TYPES, skip_trivia

from .. import LintDiagnostic, token_span

# trivia token 集合（引擎 token 协议，单一事实源 core/token_protocol.py）
_TRIVIA = TRIVIA_TOKEN_TYPES

# 表达式根（借力 pratt，不内联展开）：按 pratt 标识 / 原子选择器推导识别，不硬编码
# 规则名（Expression/PrimaryExpr 换语言即失效）。PrimaryExpr 身份由 _is_atom_selector
# 从 is_atom 结构推导；原子匹配走 match_atom（is_atom 规则集合 + production 降序）。


def _is_atom_selector(info: dict, tree: dict) -> bool:
    """推导"表达式原子入口"：production 是纯 @ 分派（choice of calls）且全部
    分支都是 is_atom 规则（如 PrimaryExpr = @BitWidthLiteral|@Number|...）。
    不显式标记——从 is_atom 结构正交推导，与 is_atom 共享同一维度。
    """
    prods = info.get("prods", [])
    if len(prods) != 1:
        return False
    feat = prods[0]
    if not feat or feat.get("type") != "choice":
        return False
    for alt in feat.get("alternatives", []):
        if alt.get("type") != "call":
            return False
        sub = tree.get(alt.get("name"))
        if sub is None or not sub.get("is_atom"):
            return False
    return True


def _token_firsts(feat: dict) -> set[str]:
    """token 类型声明 → 首 token 集合（`A|B` 多候选拆开）。"""
    tt = feat.get("token_type", "")
    if "|" in tt:
        return set(tt.split("|"))
    return {tt}


def _no_progress_ok(feat: dict, sub_errs: list, before: int) -> bool:
    """元素匹配成功但不推进时，是否算合法（跳过继续而非回滚）。

    optional 可不存在；全可选 call（如 TypeSpecNoReg）与 0 次 repeat（如
    RangeBracket*）匹配成功但不消费也属合法。token/choice/plus 等失败仍回滚，
    防止前一元素失败后后续 @Expression 在未推进位置假匹配。
    """
    if feat.get("type") == "optional":
        return True
    return feat.get("type") in ("call", "repeat") and len(sub_errs) == before


class RuleMatcher:
    """从 production 树内联匹配规则的共享匹配器。"""

    def __init__(
        self,
        tree: dict,
        expr_checker,
        block_openers: frozenset[str],
        block_closers: frozenset[str],
    ) -> None:
        self._tree = tree
        self._expr = expr_checker
        self._block_openers = block_openers
        self._block_closers = block_closers
        # 试探模式（probe）：Level 2 消歧试解析（lookahead._try_parse）的 limit
        # 是人为截断的（句子边界+1），语句区间在 EOF 处耗尽是正常截断而非残缺
        # ——此时 EOF 报错会把截断试探误判为匹配失败（合法 for 被报未识别）。
        # 试探语境置 True，EOF 不报错；真实检查（StatementChecker）保持报错。
        self._probe_eof = False
        # 原子规则集合（参考 parser.atomic_rules）：is_atom 规则按 production
        # 长度降序（长的先试，ReplicateExpr 先于 ConcatExpr，避免被误吞）。
        self._atom_rules = sorted(
            (
                name
                for name, info in tree.items()
                if isinstance(info, dict) and info.get("is_atom")
            ),
            key=lambda n: len(tree[n].get("prods", [])),
            reverse=True,
        )
        # match_atom 位置级记忆化（packrat 式）：同一 token 位置 i 的原子匹配
        # 结果缓存——pratt 表达式检查对同一位置反复遍历全部 is_atom 规则
        # （choice 失败回溯/嵌套表达式），无缓存时同一 (i, rule) 组合被指数级
        # 重复求值（cProfile：matcher 占管线 97%）。match_atom 是纯函数
        # （silent 路径无错误副作用，同输入必同输出），记忆化安全。
        # key = token 位置 i；value = consumed（0 表示无原子命中——失败同样
        # 缓存，packrat 语义）。memo 按 token 流身份隔离（_memo_tokens）：
        # 直接调用方（单元测试绕过 scan）与跨文件复用都不串文件。
        self._atom_memo: dict[int, int] = {}
        self._memo_tokens: list | None = None  # 当前 memo 所属 token 流
        # _is_atom_selector 静态缓存：规则名 → 是否为"纯 @ 分派原子选择器"。
        # 该判定只读 info/tree（构造后不变），是纯静态函数——cProfile 显示
        # 298 万次调用（每 _match_call_impl 一次），预计算一次即可。
        self._atom_selector_cache: dict[str, bool] = {
            name: _is_atom_selector(info, tree)
            for name, info in tree.items()
            if isinstance(info, dict)
        }
        # optional call 位置级 memo：_match_call 的 optional 分支（silent=True
        # 纯函数，无错误副作用）按 (i, name, limit) 缓存匹配结果——同一语句
        # 区间内同位置同规则的 optional 试探被反复求值（cProfile：_match_call
        # 295 万次）。token 流身份守卫同 _atom_memo。
        self._optional_call_memo: dict[tuple, int] = {}
        self._memo_tokens_opt: list | None = None
        # _match_call_impl packrat 缓存：key = (i, name, limit, strict, silent)，
        # value = (匹配结果 j, 本次新增错误快照)。命中时重放错误快照保持
        # 诊断语义。probe 模式（_probe_eof）不参与缓存。token 流身份守卫同前。
        self._call_impl_memo: dict[tuple, tuple] = {}
        self._memo_tokens_impl: list | None = None

    # ── 对外接口 ────────────────────────────────

    @contextmanager
    def probe_mode(self):
        """probe 截断试探模式（C1 重构，2026-08-28）：EOF 不报错 + 绕过缓存。

        lookahead._try_parse 用 `with matcher.probe_mode():` 包裹——上下文
        退出必恢复实例状态（即使匹配内部抛异常），消除"手动设置/恢复"裸
        try/finally 的污染风险（实例可变状态跨调用残留会让真实检查误入
        probe 语义：EOF 不报错、缓存绕过）。
        """
        old = self._probe_eof
        self._probe_eof = True
        try:
            yield
        finally:
            self._probe_eof = old

    def _memo_for(self, memo_attr: str, tokens_attr: str, tokens: list[Token]) -> dict:
        """按 token 流身份返回 memo dict（token 流切换即清空）。

        三层 packrat 缓存（_atom_memo/_optional_call_memo/_call_impl_memo）
        的守卫逻辑统一收口：`_memo_tokens_X is not tokens` → clear + 换身份。
        直接调用方（单元测试绕过 scan）或跨文件复用都不串文件命中。
        """
        if getattr(self, tokens_attr) is not tokens:
            getattr(self, memo_attr).clear()
            setattr(self, tokens_attr, tokens)
        return getattr(self, memo_attr)

    def reset_atom_memo(self) -> None:
        """清空 match_atom 位置级缓存（含 token 流身份标记）。

        scan() 每次新 token 流前调用；token 流身份守卫（match_atom 内
        `_memo_tokens is not tokens` 检查）也兜底——直接调用方（单元测试
        绕过 scan）或跨文件复用都不会串文件命中。
        """
        self._atom_memo.clear()
        self._memo_tokens = None
        self._optional_call_memo.clear()
        self._memo_tokens_opt = None
        self._call_impl_memo.clear()
        self._memo_tokens_impl = None

    def match_rule(
        self,
        tokens: list[Token],
        i: int,
        prods: list[dict],
        errors: list,
        limit: int,
    ) -> int:
        """按 production 列表匹配，返回消费位置。

        顶层 production 是顺序列表：optional 元素不推进是合法的（结构可
        不存在），应跳过继续；非 optional 元素不推进才视为失败回滚（防止
        前一元素失败后后续元素在未推进位置假匹配）。
        """
        start = i
        for pos, feat in enumerate(prods):
            if i >= limit:
                # 语句区间在 token 流末尾耗尽而 production 仍有必选元素 → 语句
                # 不完整（残缺：缺分号/缺语句体，缺失 token 处恰为文件末尾无换行
                # 时即 EOF）。仅 optional 元素可合法缺失。报一次错即终止，不静默。
                # probe 语境（_try_parse 截断试探）不报——那是正常截断非残缺。
                if not self._probe_eof and self._has_required_tail(prods, pos):
                    self._report_eof(tokens, limit, errors)
                break
            before = len(errors)
            j = self._match_element(tokens, i, feat, prods, pos, errors, limit)
            if j <= i:
                # optional 可不存在；全可选 call（如 TypeSpecNoReg）匹配成功但
                # 不消费也属合法——两者都跳过继续，仅真正失败（有错误）才回滚
                if feat.get("type") == "optional" or len(errors) == before:
                    continue
                return start
            i = j
        return i

    @staticmethod
    def _has_required_tail(prods: list[dict], pos: int) -> bool:
        """pos 及其后是否还有必选（非 optional）元素。"""
        return any(f.get("type") != "optional" for f in prods[pos:])

    def _match_element(
        self,
        tokens: list[Token],
        i: int,
        feat: dict,
        prods: list[dict],
        pos: int,
        errors: list,
        limit: int,
    ) -> int:
        """单元素匹配；optional 在"后续元素 first 与之重叠"时走 overlap 变体。

        first 与后续元素重叠（如门级实例 (strength)? 与无名实例的 "("）→
        overlap 变体：失败且首 token 命中时静默交还后续元素，不报 incomplete
        不跳过（见 `_match_optional_overlap`）。
        """
        if feat.get("type") != "optional":
            return self.match(tokens, i, feat, errors, limit, strict=True)
        nxt = self._optional_overlap_firsts(prods, pos)
        if not nxt:
            return self.match(tokens, i, feat, errors, limit, strict=True)
        return self._match_optional_overlap(tokens, i, feat, errors, limit, nxt)

    def _optional_overlap_firsts(self, prods: list[dict], pos: int) -> frozenset[str]:
        """pos 之后各元素的 first 并集（overlap 判据集）。"""
        nxt: frozenset[str] = frozenset()
        for later in prods[pos + 1 :]:
            nxt |= self._first_tokens(later, set())
        return nxt

    # ── 分发器 ──────────────────────────────────

    def match(
        self,
        tokens: list[Token],
        i: int,
        node: dict,
        errors: list,
        limit: int,
        strict: bool = False,
    ) -> int:
        """匹配一个 feature。strict=True 表示必选（失败报错+跳过恢复）。"""
        if i >= limit:
            return i
        typ = node.get("type", "")
        if typ == "token":
            return self._match_token(tokens, i, node, errors, limit, strict)
        if typ == "call":
            return self._match_call(tokens, i, node, errors, limit, strict)
        if typ == "choice":
            return self._match_choice(tokens, i, node, errors, limit, strict)
        if typ == "optional":
            return self._match_optional(tokens, i, node, errors, limit)
        if typ == "seq":
            return self._match_seq(tokens, i, node, errors, limit, strict)
        if typ == "repeat":
            return self._match_repeat(tokens, i, node, errors, limit, False)
        if typ == "plus":
            return self._match_repeat(tokens, i, node, errors, limit, True)
        return i

    def match_atom(self, tokens: list[Token], i: int):
        """匹配一个表达式原子，返回 (node, consumed) 或 (None, 0)。

        consumed 从入参 i 起算（含内部跳过的 trivia）——即调用方直接
        `idx += consumed` 即可推进到原子之后。若不含 trivia，pratt 在
        运算符后换行位置（如 `b +\\n c` 的右操作数）递归调用本回调时，
        `idx += consumed` 会错位一格、把表达式截断在 `b +`（多行 RHS 误报）。

        参考 parser 的 _atom_parser_impl / atomic_rules 流程：按 production 长度
        降序逐个尝试 is_atom 规则，返回第一个有进展者。只消费操作数、不消费
        运算符（避免 `a <= b` 赋值 vs 比较歧义）；production 内遇 @Expression /
        pratt 规则由 _match_call_impl 交回 ExpressionChecker.consume（pratt 切断
        左递归环，binding power + stop_tokens 保证终止）。

        记忆化：纯函数（silent 路径不产生错误副作用），同一 (tokens, i) 结果
        确定——按位置 i 缓存 consumed，拦截 pratt 对同一位置的反复全规则遍历。
        token 流身份守卫：memo 只对同一 tokens 列表有效（不同文件/不同测试
        的 token 流位置 i 含义不同），流切换即清空。
        """
        memo = self._memo_for("_atom_memo", "_memo_tokens", tokens)
        if i in memo:
            consumed = memo[i]
            return (object(), consumed) if consumed > 0 else (None, 0)
        n = len(tokens)
        j = skip_trivia(tokens, i, n)
        if j >= n:
            memo[i] = 0
            return None, 0
        # 最长匹配（2026-08-28，层次化引用交错形态，与 parser._atom_parser_impl
        # 同语义）：遍历全部 is_atom 规则取消费最多者（等长取先——_atom_rules
        # production 长度降序，`a[0]` 纯下标先试的 SelectExpr 胜）。原"第一个
        # 有进展即返回"使 SelectExpr 先命中 `a[0]` → `a[0].b` 残留 `.b` 报错。
        best_k = j
        for name in self._atom_rules:
            trial: list = []
            k = self._match_call_impl(
                tokens, j, name, trial, n, strict=False, silent=True
            )
            if k > best_k:
                best_k = k
        memo[i] = best_k - i
        if best_k > j:
            # consumed 从 i 起算（含 _skip 跳过的 trivia），保证 pratt
            # 递归层的 `idx += consumed` 推进到原子之后不错位。
            return object(), best_k - i
        return None, 0

    def _match_token(
        self,
        tokens: list[Token],
        i: int,
        node: dict,
        errors: list,
        limit: int,
        strict: bool,
    ) -> int:
        tok = node.get("token_type", "")
        # token_type 可能含 "|"（如 keyword.case|casex|casez）
        j = skip_trivia(tokens, i, limit)
        if j >= limit:
            # 区间内 token 耗尽（无更多非 trivia token）→ 必选 token 缺失
            # （如缺分号且语句区间在 EOF 结尾）。可选语境静默，必选报错。
            # probe 语境（_try_parse 截断试探）不报——那是正常截断非残缺。
            if strict and not self._probe_eof:
                self._report_eof(tokens, limit, errors)
            return i
        actual = tokens[j].type
        if actual in tok.split("|"):
            return j + 1
        if strict:
            t = tokens[j]
            errors.append(
                LintDiagnostic(
                    range=token_span(t),
                    message=f"expected '{tok}', got '{actual}'",
                    severity=1,
                    code="phase-statement",
                )
            )
            return j + 1  # 错误恢复：跳过坏 token
        return i  # 可选语境：失败不推进

    def _match_call(
        self,
        tokens: list[Token],
        i: int,
        node: dict,
        errors: list,
        limit: int,
        strict: bool,
    ) -> int:
        name = node.get("name", "")
        if node.get("optional"):
            # optional call：silent=True 纯函数（无错误副作用），同语句区间内
            # 同位置同规则的 optional 试探被反复求值——按 (i, name, limit)
            # 记忆化（token 流身份守卫，跨文件/跨测试隔离）。
            opt_memo = self._memo_for(
                "_optional_call_memo", "_memo_tokens_opt", tokens
            )
            key = (i, name, limit)
            cached = opt_memo.get(key)
            if cached is not None:
                return cached if cached > i else i
            j = self._match_call_impl(
                tokens, i, name, errors, limit, strict=False, silent=True
            )
            opt_memo[key] = j
            return j if j > i else i
        return self._match_call_impl(
            tokens, i, name, errors, limit, strict, silent=False
        )

    def _match_call_impl(
        self,
        tokens: list[Token],
        i: int,
        name: str,
        errors: list,
        limit: int,
        strict: bool,
        silent: bool = False,
    ) -> int:
        """_match_call_impl 的 packrat 包装层。

        实测（tv80 165KB）：298 万次调用中同 (i, name, limit, strict, silent)
        重复率 98.1%（唯一 5.7 万）——同一位置同一规则被 choice/optional/嵌套
        反复求值。匹配本身是纯函数（依赖 tokens/i/name/limit/strict/silent +
        构造期固定的 tree/block 集合），仅 silent=False 时向 errors 追加诊断
        （副作用）。缓存 (key → (j, 新增错误快照))，命中时重放错误快照，
        保持诊断语义与不缓存完全一致。

        probe 模式（_probe_eof=True，lookahead 截断试探）改变 EOF 报错行为，
        不参与缓存（避免 probe 与真实检查串缓存）。
        """
        if self._probe_eof:
            return self._match_call_impl_raw(
                tokens, i, name, errors, limit, strict, silent
            )
        impl_memo = self._memo_for("_call_impl_memo", "_memo_tokens_impl", tokens)
        key = (i, name, limit, strict, silent)
        cached = impl_memo.get(key)
        if cached is not None:
            j, errs = cached
            if errs:
                errors.extend(errs)
            return j
        before = len(errors)
        j = self._match_call_impl_raw(
            tokens, i, name, errors, limit, strict, silent
        )
        impl_memo[key] = (j, errors[before:])
        return j

    def _match_call_impl_raw(
        self,
        tokens: list[Token],
        i: int,
        name: str,
        errors: list,
        limit: int,
        strict: bool,
        silent: bool = False,
    ) -> int:
        info = self._tree.get(name)
        if info is None:
            return i

        # 表达式根（pratt 标识 / 原子选择器推导）→ 交 ExpressionChecker
        is_atom_sel = self._atom_selector_cache.get(name, False)
        if info.get("pratt") or is_atom_sel:
            return self._match_expr_call(
                tokens, i, name, info, is_atom_sel, errors, limit, strict, silent
            )

        # 块类（@BeginEnd 等）→ 校验 block_start 后跳到块结束
        if info.get("is_block"):
            return self._match_block_call(tokens, i, info, limit)

        # 语句类（@Stmt / @IfBlock 等嵌套语句）→ strict 语境跳过 end_case（扁平化）
        # strict=False（choice/optional 试探，如 PortList 里的 TypedPortDecl）落到
        # 普通内联匹配，避免"双角色"规则在端口列表被 end_case 错误跳过吞掉内容
        if info.get("is_statement") and strict:
            return self._match_stmt_call(
                tokens, i, name, info, errors, limit, strict, silent
            )

        # 普通子规则（含 is_atom 原子）→ 内联匹配其 production
        return self._match_plain_call(tokens, i, info, errors, limit, strict, silent)

    def _match_expr_call(
        self,
        tokens: list[Token],
        i: int,
        name: str,
        info: dict,
        is_atom_sel: bool,
        errors: list,
        limit: int,
        strict: bool,
        silent: bool,
    ) -> int:
        """表达式根（@Expression / @PrimaryExpr / pratt 链）→ 交 ExpressionChecker。"""
        del name, info  # 内部方法参数，本分支不消费
        if is_atom_sel:
            # @PrimaryExpr（is_atom 规则集合选择器，可推导）只匹配原子操作数
            # （赋值目标/操作数），不消费运算符——避免 `a <= b` 被当比较表达式
            # 吞掉（NonBlockingAssign 的 <= 赋值歧义）。@Expression 才完整 pratt。
            j = skip_trivia(tokens, i, limit)
            if j >= limit:
                return i
            _, consumed = self.match_atom(tokens, j)
            if consumed <= 0:
                if strict and not silent:
                    t = tokens[j]
                    errors.append(
                        LintDiagnostic(
                            range=token_span(t),
                            message=f"expected expression, got '{t.type}'",
                            severity=1,
                            code="phase-expr",
                        )
                    )
                    return j + 1
                return i
            return j + consumed
        # @Expression / pratt 链：先跳过 trivia——从行首 newline 等 trivia
        # 位置 consume 时，pratt 的 consumed 不含已跳过的 trivia，会与后续
        # 元素错位（多行表达式 RHS 误报）。
        j = skip_trivia(tokens, i, limit)
        sub_errors, consumed = self._expr.consume(
            tokens, j
        )
        if not silent:
            errors += sub_errors
        # consume 失败（sub_errors 非空）→ 不推进：ExpressionChecker 失败时
        # 返回 consumed=1 的错误恢复推进，会令 `@Expression?`（如 `.name()`
        # 空端口）误判"空表达式匹配成功"并吞掉后续 `)`；optional 语境应
        # 静默不推进（错误已记录），必选语境由上层回滚报错。
        if sub_errors:
            return i
        return j + consumed

    def _match_block_call(
        self, tokens: list[Token], i: int, info: dict, limit: int
    ) -> int:
        """块类（@BeginEnd 等）→ 校验 block_start 后跳到块结束。"""
        # 先校验起始 token：块规则必须由 block_start 触发（如 BeginEnd 的
        # keyword.begin）。不校验会导致 @BeginEnd 对任意 token（如
        # `always @(*) endmodule` 的 endmodule）也"跳到结束符"把坏 body
        # 静默吞掉——@Stmt 位置非块起点时应视为失败，让上层报错。
        bs = info.get("block_start") or ""
        if bs:
            k = skip_trivia(tokens, i, limit)
            if k >= limit or tokens[k].type != bs:
                return i
        # 优先用 block_end（精确配对结束符，如 BeginEnd 的 keyword.end）：
        # 块边界由结构决定（block_start/block_end 从 production 首尾字面
        # token 推导），无 block_end 的匿名块不跳过。
        be = info.get("block_end") or ""
        if be:
            return self._skip_to_end(tokens, i, {be}, limit)
        return i

    def _match_stmt_call(
        self,
        tokens: list[Token],
        i: int,
        name: str,
        info: dict,
        errors: list,
        limit: int,
        strict: bool,
        silent: bool,
    ) -> int:
        """语句类（@Stmt / @IfBlock 等）→ 验证起始 token，不跳过。

        嵌套语句由发现阶段注册的独立检查器负责（父 checker 区间内遇
        @Stmt 位置不消费，production 匹配到此自然结束）。原 end_case 跳过
        已移除——语句终点由结构推导（block_end/句子结束符），非手写数据。
        """
        del info, strict  # 内部方法参数，本分支不消费
        # 先验证起始 token，防止非嵌套语句上下文误跳过
        firsts = self._first_tokens_of_rule(name, set())
        k = skip_trivia(tokens, i, limit)
        if k >= limit:
            return i
        if firsts and tokens[k].type not in firsts:
            # 起始不匹配。区分两种"@Stmt 位置非语句开头"：
            # - 块 opener（begin/fork 等，firsts 未覆盖的块 body）：合法，
            #   由发现阶段独立发现 BeginEnd 块 → 静默不跳过。
            # - 其他（块结束符/句子结束符/无关 token）：语句 body 缺失
            #   （如 `always @(*) endmodule`）→ 报错，不再静默吞掉。
            if tokens[k].type in self._block_openers:
                return i
            if not silent:
                t = tokens[k]
                errors.append(
                    LintDiagnostic(
                        range=token_span(t),
                        message=f"expected statement, got '{t.content}'",
                        severity=1,
                        code="phase-statement",
                    )
                )
                return k + 1
            return i
        return i

    def _match_plain_call(
        self,
        tokens: list[Token],
        i: int,
        info: dict,
        errors: list,
        limit: int,
        strict: bool,
        silent: bool,
    ) -> int:
        """普通子规则（含 is_atom 原子）→ 内联匹配其 production。"""
        prods = info.get("prods", [])
        if not prods:
            return i
        sub_errs: list = []
        start = i
        j = i
        for feat in prods:
            if j >= limit:
                break
            before = len(sub_errs)
            k = self.match(tokens, j, feat, sub_errs, limit, strict)
            if k <= j:
                if not _no_progress_ok(feat, sub_errs, before):
                    return start
                continue
            j = k
        if not silent:
            errors += sub_errs
        if j > start and self._hits_exclude(tokens, j, info, limit):
            return start
        return j

    @staticmethod
    def _hits_exclude(tokens: list[Token], j: int, info: dict, limit: int) -> bool:
        """内联匹配后检查 exclude 负向前瞻（如 Declarator 的 symbol.base.dot）。

        命中排除 token 视为失败回滚（防止声明器吞掉后续端口/点语法）。注意：
        exclude 是消歧必需的负向前瞻，与派生 FOLLOW 正交（非后继集）。
        """
        exclude: set = info.get("exclude") or set()
        if not exclude:
            return False
        k = skip_trivia(tokens, j, limit)
        return k < limit and tokens[k].type in exclude

    def _match_choice(
        self,
        tokens: list[Token],
        i: int,
        node: dict,
        errors: list,
        limit: int,
        strict: bool,
    ) -> int:
        # 失败路径必须返回**原位置**：试分支的内部起点会前移到首个非 trivia
        # token（见下），若失败时沿用该内部位置，被跳过的 trivia 就被计入
        # "已消费"——上层 seq/repeat/optional 的 `j > i` 判据全部据此误判为
        # 推进，下游随之错位（如 Identifier 的 production 含 token 备选后，
        # 端口列表把逗号后的换行当消费，第二个端口项被跳过 → 块头提前收尾）。
        orig = i
        best_i = i
        best_errs: list | None = None
        # 先跳过 trivia：choice 从第一个非 trivia token 开始尝试分支，避免
        # 内部分支（如 @Expression 的 pratt consume）在 trivia 位置消费错位
        # （consumed 不含已跳过的 trivia，导致 case item 等从行首 newline 失败）。
        i = skip_trivia(tokens, i, limit)
        if i >= limit:
            if strict:
                # 区间在 token 流末尾耗尽：锚定最后一个非 trivia token（残缺
                # 语句缺失 token 的位置），避免指到区间末的 newline 等 trivia。
                errors.append(
                    LintDiagnostic(
                        range=token_span(self._last_non_trivia(tokens, limit)),
                        message="unexpected end of statement",
                        severity=1,
                        code="phase-statement",
                    )
                )
            return orig
        for alt in node.get("alternatives", []):
            trial: list = []
            j = self.match(tokens, i, alt, trial, limit, strict=False)
            # 优先错误少，再比推进远（防止吞 token 的错误分支胜出）
            if best_errs is None:
                best_i, best_errs = j, trial
            elif len(trial) < len(best_errs):
                best_i, best_errs = j, trial
            elif len(trial) == len(best_errs) and j > best_i:
                best_i = j
        if best_errs is not None and best_i > i:
            errors += best_errs
            return best_i
        # 所有分支都无进展：仅在必选位置（strict）报 unexpected 并吞 token 恢复；
        # 可选语境（optional/repeat 内）失败不推进，防止吞 token 造成误匹配。
        if strict:
            j = skip_trivia(tokens, i, limit)
            if j < limit:
                t = tokens[j]
                errors.append(
                    LintDiagnostic(
                        range=token_span(t),
                        message=f"unexpected '{t.content}'",
                        severity=1,
                        code="phase-statement",
                    )
                )
                return j + 1
        return orig

    def _match_optional(
        self,
        tokens: list[Token],
        i: int,
        node: dict,
        errors: list,
        limit: int,
    ) -> int:
        inner = node.get("elem", {})
        trial: list = []
        j = self.match(tokens, i, inner, trial, limit, strict=False)
        if j > i:
            return j
        # 失败但必然首 token 出现在当前位置 → 结构存在但不完整
        # （如 `@PortParens?` 遇到 `(` 但端口列表坏），报错并跳过恢复
        ft = self._first_tokens(inner, set())
        if ft:
            k = skip_trivia(tokens, i, limit)
            if k < limit and tokens[k].type in ft:
                t = tokens[k]
                errors.append(
                    LintDiagnostic(
                        range=token_span(t),
                        message=(
                            f"incomplete structure, expected one of: "
                            f"{', '.join(sorted(ft))}"
                        ),
                        severity=1,
                        code="phase-statement",
                    )
                )
                return k + 1
        return i

    def _match_optional_overlap(
        self,
        tokens: list[Token],
        i: int,
        node: dict,
        errors: list,
        limit: int,
        next_firsts: frozenset[str],
    ) -> int:
        """optional 变体（first 与后续元素重叠时用）：试匹配失败且首 token
        命中时，**不报 incomplete、不跳过**——该 token 可能是后续元素的合法
        开头（如门级实例 gate_type (strength)? (terminals) 的括号：strength
        失败后左括号属于无名实例）。静默交还，后续元素继续匹配。"""
        inner = node.get("elem", {})
        trial: list = []
        j = self.match(tokens, i, inner, trial, limit, strict=False)
        if j > i:
            return j
        ft = self._first_tokens(inner, set())
        if ft and ft & next_firsts:
            return i  # 首 token 与后续元素 first 重叠 → 静默（机会留给后续）
        # 不重叠：走原恢复（报 incomplete + 跳过）
        return self._match_optional(tokens, i, node, errors, limit)

    def _first_tokens(self, feat: dict, visited: set) -> set[str]:
        """递归计算 feature 的必然首 token 类型集合（防环）。

        逐类型实现分在 `_first_of_*`：call 带块起始/可空传播（最重）、
        seq/choice 为并集、optional·repeat·plus 取其 elem。
        """
        typ = feat.get("type", "")
        if typ == "call":
            return self._first_of_call(feat, visited)
        if typ == "seq":
            return self._nullable_after(feat.get("items", []), visited)
        if typ == "choice":
            return self._first_of_choice(feat, visited)
        if typ in ("optional", "repeat", "plus"):
            return self._first_tokens(feat.get("elem", {}) or {}, visited)
        if typ == "token":
            return _token_firsts(feat)
        return set()

    def _first_of_call(self, feat: dict, visited: set) -> set[str]:
        """call：目标规则首元素 firsts + block_start + **可空前缀传播**。

        块规则：block_start 已从 production 剥离（如 BeginEnd 的
        keyword.begin），需并入 firsts，否则 @BeginEnd 等块候选的
        首 token 收集缺失（Stmt/CtrlStmt firsts 漏 begin）。
        """
        name = feat.get("name", "")
        if name in visited:
            return set()
        info = self._tree.get(name)
        if not info:
            return set()
        result: set[str] = set()
        bs = info.get("block_start") or ""
        if bs:
            result.add(bs)
        prods = info.get("prods", [])
        first = prods[0] if prods and isinstance(prods[0], dict) else None
        if first is None:
            return result
        result |= self._first_tokens(first, visited | {name})
        if first.get("type") in ("optional", "repeat"):
            result |= self._nullable_after(prods[1:], visited | {name})
        return result

    def _nullable_after(self, items: list, visited: set) -> set[str]:
        """可空前缀传播：从 items 首元素起逐个并入 firsts，遇非可空元素停。

        首元素是可空形态（optional/repeat）时，first 还要含"空之后那一元素"
        的 first（如 GateInstance 的 @Identifier? 空 → first 应含 "("；
        否则 overlap 判据漏判）。call / seq 两处共用。
        """
        result: set[str] = set()
        for it in items:
            result |= self._first_tokens(it, visited)
            if it.get("type") not in ("optional", "repeat"):
                break
        return result

    def _first_of_choice(self, feat: dict, visited: set) -> set[str]:
        """choice：各分支 firsts 并集。"""
        result: set[str] = set()
        for a in feat.get("alternatives", []):
            result |= self._first_tokens(a, visited)
        return result

    def _first_tokens_of_rule(self, name: str, visited: set) -> set[str]:
        """规则 production 首元素的必然首 token 集合。"""
        info = self._tree.get(name)
        if not info:
            return set()
        prods = info.get("prods", [])
        if not prods or not isinstance(prods[0], dict):
            return set()
        return self._first_tokens(prods[0], visited | {name})

    def _match_seq(
        self,
        tokens: list[Token],
        i: int,
        node: dict,
        errors: list,
        limit: int,
        strict: bool,
    ) -> int:
        start = i
        items = node.get("items", [])
        for idx, item in enumerate(items):
            if i >= limit:
                break
            if item.get("type") == "optional":
                # optional 的 first 与后续元素 first 重叠（如门级实例的
                # (strength)? 与无名实例的 "("）→ 用 overlap 变体：匹配
                # 失败且首 token 命中时静默交还后续元素，不报 incomplete。
                nxt: frozenset[str] = frozenset()
                for later in items[idx + 1 :]:
                    nxt |= self._first_tokens(later, set())
                if nxt:
                    j = self._match_optional_overlap(
                        tokens, i, item, errors, limit, nxt
                    )
                else:
                    j = self.match(tokens, i, item, errors, limit, strict)
            else:
                j = self.match(tokens, i, item, errors, limit, strict)
            if j <= i:
                # 某个元素未推进 → seq 整体失败（回滚到起点），
                # 防止后续元素在未推进位置假匹配（如 Range 的 l_square 失败
                # 后 @Expression 误吞 = 导致 repeat 无限推进）
                return start
            i = j
        return i

    def _match_repeat(
        self,
        tokens: list[Token],
        i: int,
        node: dict,
        errors: list,
        limit: int,
        require_one: bool,
    ) -> int:
        elem = node.get("elem", {})
        count = 0
        while i < limit:
            trial: list = []
            j = self.match(tokens, i, elem, trial, limit, strict=False)
            if j <= i:
                if require_one and count == 0:
                    j = skip_trivia(tokens, i, limit)
                    if j < limit:
                        t = tokens[j]
                        errors.append(
                            LintDiagnostic(
                                range=token_span(t),
                                message="expected at least one match",
                                severity=1,
                                code="phase-statement",
                            )
                        )
                break
            if trial:
                # 重复项不应产生错误；若产生则停止
                break
            i = j
            count += 1
        return i

    # ── 辅助 ────────────────────────────────────

    @staticmethod
    def _last_non_trivia(tokens: list[Token], limit: int) -> Token:
        """区间 [0, limit) 内最后一个非 trivia token（残缺语句 EOF 锚点）。

        limit 取 min(end, len(tokens))，区间末可能是 newline 等 trivia，直接取
        tokens[limit-1] 会把诊断指到换行符上。
        """
        j = min(limit, len(tokens)) - 1
        while j >= 0 and tokens[j].type in _TRIVIA:
            j -= 1
        return tokens[max(0, j)]

    def _report_eof(self, tokens: list[Token], limit: int, errors: list) -> None:
        """语句区间在 token 流末尾耗尽：production 仍有必选元素 → 语句不完整。

        残缺语句（缺分号/缺语句体/缺右括号）缺失的 token 处恰为文件末尾且无
        末尾换行时，token 流即在此耗尽——此前静默返回导致全部漏检。现统一报
        错（位置取区间最后一个非 trivia token），语言无关（不假设具体 token
        类型）。
        """
        t = self._last_non_trivia(tokens, limit)
        errors.append(
            LintDiagnostic(
                range=token_span(t),
                message="unexpected end of statement",
                severity=1,
                code="phase-statement",
            )
        )

    def _skip_to_end(
        self, tokens: list[Token], i: int, end_set: set[str], limit: int
    ) -> int:
        """跳过到结束符之后（end_set 可含 `!` 前缀排除项）。"""
        exclude = {s[1:] for s in end_set if s.startswith("!")}
        positive = {s for s in end_set if not s.startswith("!")}
        if not positive:
            return self._skip_to_limit(tokens, i + 1, limit)
        return self._scan_to_end(tokens, i, positive, exclude, limit)

    @staticmethod
    def _skip_to_limit(tokens: list[Token], i: int, limit: int) -> int:
        """无正选集：只跳 trivia，越界即夹到 limit。"""
        j = skip_trivia(tokens, i, limit)
        return j if j <= limit else limit

    def _scan_to_end(
        self, tokens: list[Token], i: int, positive: set[str], exclude: set[str],
        limit: int,
    ) -> int:
        """逐 token 扫描：排除集过、正选集在深度 0 命中即收、块内继续。"""
        depth = 0
        while i < limit:
            t = tokens[i]
            if t.type in exclude:
                i += 1
                continue
            if t.type in positive and depth == 0:
                return i + 1
            if t.type in _TRIVIA:
                i = skip_trivia(tokens, i, limit)
                continue
            if self._closes_target_block(t, positive, depth):
                return i + 1
            depth = self._block_depth_step(t, depth)
            i += 1
        return limit

    def _closes_target_block(self, t: Token, positive: set[str], depth: int) -> bool:
        """闭合符是否即目标块结束符（正选闭合符且深度 ≤ 1）。

        对齐 discovery._skip_to_end：缺失此判据时 depth 1→0 的 end 被跳过，
        块分支用 block_end 跳过会越过正确 end 延伸（`end else` 同行吞掉 else 链）。
        """
        return t.type in self._block_closers and t.type in positive and depth <= 1

    def _block_depth_step(self, t: Token, depth: int) -> int:
        """块开/闭符号 → 新嵌套深度（闭合符不低于 0）。"""
        if t.type in self._block_openers:
            return depth + 1
        if t.type in self._block_closers:
            return max(0, depth - 1)
        return depth
