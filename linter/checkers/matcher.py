"""checkers/matcher.py — 共享规则匹配器（RuleMatcher）。

从 production 树内联匹配规则，供两个检查器复用：
    - StatementChecker：在语句区间内按 production 精确匹配
    - ExpressionChecker：pratt 的 atom_parser 回调经 match_atom 识别 Verilog 原子
      （BitWidthLiteral / ConcatExpr / ReplicateExpr / SelectExpr / CallExpr ...），
      原子由 is_atom 规则 production 驱动（参考 parser atomic_rules），不手写。

strict 语境约定：
    - strict=True  — 必选位置（production 顶层）：token 失败报错 + 跳过恢复
    - strict=False — 可选语境（choice/optional/repeat 内）：失败不推进
      防止"吞 token 推进"的错误分支在 choice 中胜出。
"""

from __future__ import annotations

from core.define import Token

from .. import LintDiagnostic, Position
from .._constants import TRIVIA as _TRIVIA

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


def _skip(tokens: list[Token], i: int, limit: int) -> int:
    while i < limit and tokens[i].type in _TRIVIA:
        i += 1
    return i


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

    # ── 对外接口 ────────────────────────────────

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
        for feat in prods:
            if i >= limit:
                break
            before = len(errors)
            j = self.match(tokens, i, feat, errors, limit, strict=True)
            if j <= i:
                # optional 可不存在；全可选 call（如 TypeSpecNoReg）匹配成功但
                # 不消费也属合法——两者都跳过继续，仅真正失败（有错误）才回滚
                if feat.get("type") == "optional" or len(errors) == before:
                    continue
                return start
            i = j
        return i

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

        参考 parser 的 _atom_parser_impl / atomic_rules 流程：按 production 长度
        降序逐个尝试 is_atom 规则，返回第一个有进展者。只消费操作数、不消费
        运算符（避免 `a <= b` 赋值 vs 比较歧义）；production 内遇 @Expression /
        pratt 规则由 _match_call_impl 交回 ExpressionChecker.consume（pratt 切断
        左递归环，binding power + stop_tokens 保证终止）。
        """
        n = len(tokens)
        j = _skip(tokens, i, n)
        if j >= n:
            return None, 0
        for name in self._atom_rules:
            trial: list = []
            k = self._match_call_impl(
                tokens, j, name, trial, n, strict=False, silent=True
            )
            if k > j:
                return object(), k - j
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
        j = _skip(tokens, i, limit)
        if j >= limit:
            return i
        actual = tokens[j].type
        if actual in tok.split("|"):
            return j + 1
        if strict:
            t = tokens[j]
            errors.append(
                LintDiagnostic(
                    range=(Position(t.line, t.column), Position(t.line, t.column)),
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
            j = self._match_call_impl(
                tokens, i, name, errors, limit, strict=False, silent=True
            )
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
        info = self._tree.get(name)
        if info is None:
            return i

        # 表达式根（pratt 标识 / 原子选择器推导）→ 交 ExpressionChecker
        is_atom_sel = _is_atom_selector(info, self._tree)
        if info.get("pratt") or is_atom_sel:
            if is_atom_sel:
                # @PrimaryExpr（is_atom 规则集合选择器，可推导）只匹配原子操作数
                # （赋值目标/操作数），不消费运算符——避免 `a <= b` 被当比较表达式
                # 吞掉（NonBlockingAssign 的 <= 赋值歧义）。@Expression 才完整 pratt。
                j = i
                while j < limit and tokens[j].type in _TRIVIA:
                    j += 1
                if j >= limit:
                    return i
                _, consumed = self.match_atom(tokens, j)
                if consumed <= 0:
                    if strict and not silent:
                        t = tokens[j]
                        errors.append(
                            LintDiagnostic(
                                range=(
                                    Position(t.line, t.column),
                                    Position(t.line, t.column),
                                ),
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
            j = i
            while j < limit and tokens[j].type in _TRIVIA:
                j += 1
            sub_errors, consumed = self._expr.consume(
                tokens, j, stop_tokens=self._stop_for(name)
            )
            if not silent:
                errors += sub_errors
            return j + consumed

        # 块类（@BeginEnd 等）→ 跳到 end_case
        if info.get("is_block"):
            ec_block: set[str] = set(info.get("end_case") or ())
            if ec_block:
                return self._skip_to_end(tokens, i, ec_block, limit)
            return i

        # 语句类（@Stmt / @IfBlock 等嵌套语句）→ strict 语境跳过 end_case（扁平化）
        # strict=False（choice/optional 试探，如 PortList 里的 TypedPortDecl）落到
        # 普通内联匹配，避免"双角色"规则在端口列表被 end_case 错误跳过吞掉内容
        if info.get("is_statement") and strict:
            # 先验证起始 token，防止非嵌套语句上下文误跳过
            firsts = self._first_tokens_of_rule(name, set())
            k = _skip(tokens, i, limit)
            if k >= limit:
                return i
            if firsts and tokens[k].type not in firsts:
                return i  # 起始不匹配 → 视为失败（不跳过）
            ec_stmt: set[str] = set(info.get("end_case") or ())
            if ec_stmt:
                return self._skip_to_end(tokens, i, ec_stmt, limit)
            return i

        # 普通子规则（含 is_atom 原子）→ 内联匹配其 production
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
                # optional 可不存在；全可选 call（如 TypeSpecNoReg）与 0 次
                # repeat（如 RangeBracket*）匹配成功但不消费也属合法——都跳过
                # 继续。token/choice/plus 等失败仍回滚，防止前一元素失败后
                # 后续 @Expression 在未推进位置假匹配
                if feat.get("type") == "optional":
                    continue
                if feat.get("type") in ("call", "repeat") and len(sub_errs) == before:
                    continue
                return start
            j = k
        if not silent:
            errors += sub_errs
        # 内联匹配后检查 end_case 排除项（如 Declarator 的 !symbol.base.dot），
        # 命中排除 token 视为失败回滚（防止声明器吞掉后续端口/点语法）
        if j > start:
            ec: list = info.get("end_case") or []
            exclude = {s[1:] for s in ec if isinstance(s, str) and s.startswith("!")}
            if exclude:
                k = _skip(tokens, j, limit)
                if k < limit and tokens[k].type in exclude:
                    return start
        return j

    def _match_choice(
        self,
        tokens: list[Token],
        i: int,
        node: dict,
        errors: list,
        limit: int,
        strict: bool,
    ) -> int:
        best_i = i
        best_errs: list | None = None
        # 先跳过 trivia：choice 从第一个非 trivia token 开始尝试分支，避免
        # 内部分支（如 @Expression 的 pratt consume）在 trivia 位置消费错位
        # （consumed 不含已跳过的 trivia，导致 case item 等从行首 newline 失败）。
        i = _skip(tokens, i, limit)
        if i >= limit:
            if strict:
                errors.append(
                    LintDiagnostic(
                        range=(Position(tokens[limit - 1].line, tokens[limit - 1].column), Position(tokens[limit - 1].line, tokens[limit - 1].column)),
                        message="unexpected end of statement",
                        severity=1,
                        code="phase-statement",
                    )
                )
            return i
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
            j = _skip(tokens, i, limit)
            if j < limit:
                t = tokens[j]
                errors.append(
                    LintDiagnostic(
                        range=(Position(t.line, t.column), Position(t.line, t.column)),
                        message=f"unexpected '{t.content}'",
                        severity=1,
                        code="phase-statement",
                    )
                )
                return j + 1
        return i

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
            k = _skip(tokens, i, limit)
            if k < limit and tokens[k].type in ft:
                t = tokens[k]
                errors.append(
                    LintDiagnostic(
                        range=(Position(t.line, t.column), Position(t.line, t.column)),
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

    def _first_tokens(self, feat: dict, visited: set) -> set[str]:
        """递归计算 feature 的必然首 token 类型集合（防环）。"""
        typ = feat.get("type", "")
        if typ == "token":
            tt = feat.get("token_type", "")
            if "|" in tt:
                return set(tt.split("|"))
            return {tt}
        if typ == "call":
            name = feat.get("name", "")
            if name in visited:
                return set()
            info = self._tree.get(name)
            if info:
                prods = info.get("prods", [])
                if prods and isinstance(prods[0], dict):
                    return self._first_tokens(prods[0], visited | {name})
            return set()
        if typ == "seq":
            items = feat.get("items", [])
            if items:
                return self._first_tokens(items[0], visited)
            return set()
        if typ == "choice":
            result: set[str] = set()
            for a in feat.get("alternatives", []):
                result |= self._first_tokens(a, visited)
            return result
        if typ in ("optional", "repeat", "plus"):
            return self._first_tokens(feat.get("elem", {}) or {}, visited)
        return set()

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
        for item in node.get("items", []):
            if i >= limit:
                break
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
                    j = _skip(tokens, i, limit)
                    if j < limit:
                        t = tokens[j]
                        errors.append(
                            LintDiagnostic(
                                range=(
                                    Position(t.line, t.column),
                                    Position(t.line, t.column),
                                ),
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

    def _stop_for(self, name: str) -> set[str] | None:
        """表达式在给定规则上下文下的停止 token 集。"""
        info = self._tree.get(name, {})
        ec: set[str] = {s for s in (info.get("end_case") or [])}
        return ec or None

    def _skip_to_end(
        self, tokens: list[Token], i: int, end_set: set[str], limit: int
    ) -> int:
        depth = 0
        exclude = {s[1:] for s in end_set if s.startswith("!")}
        positive = {s for s in end_set if not s.startswith("!")}
        if not positive:
            j = _skip(tokens, i + 1, limit)
            return j if j <= limit else limit
        while i < limit:
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
        return limit
