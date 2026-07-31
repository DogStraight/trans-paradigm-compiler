"""checkers/matcher.py — 共享规则匹配器（RuleMatcher）。

从 production 树内联匹配规则，供两个检查器复用：
    - StatementChecker：在语句区间内按 production 精确匹配
    - ExpressionChecker：通过 atom_parser 回调识别 Verilog 原子表达式
      （BitWidthLiteral / ConcatExpr / ReplicateExpr / SelectExpr / CallExpr ...）

strict 语境约定：
    - strict=True  — 必选位置（production 顶层）：token 失败报错 + 跳过恢复
    - strict=False — 可选语境（choice/optional/repeat 内）：失败不推进
      防止"吞 token 推进"的错误分支在 choice 中胜出。
"""

from __future__ import annotations

from core.define import Token

from .. import LintDiagnostic, Position

_TRIVIA = frozenset({"space.fold", "comment", "space", "newline"})

# 表达式根（借力 pratt，不内联展开）：Expression / PrimaryExpr / pratt 链
# PrimaryExpr 由 EC 独立原子匹配器处理，避免 matcher ↔ EC 互相递归。
_EXPR_RULES = {"Expression", "PrimaryExpr"}


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

        与 _match_seq 相同：某个元素未推进则整体回滚，防止前一元素失败后
        后续元素（如 @Expression）在未推进位置假匹配。
        """
        start = i
        for feat in prods:
            if i >= limit:
                break
            j = self.match(tokens, i, feat, errors, limit, strict=True)
            if j <= i:
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
            return self._match_optional(tokens, i, node, limit)
        if typ == "seq":
            return self._match_seq(tokens, i, node, errors, limit, strict)
        if typ == "repeat":
            return self._match_repeat(tokens, i, node, errors, limit, False)
        if typ == "plus":
            return self._match_repeat(tokens, i, node, errors, limit, True)
        return i

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

        # 表达式根（Expression / pratt 链）→ 交 ExpressionChecker
        if name in _EXPR_RULES or info.get("pratt"):
            sub_errors, consumed = self._expr.consume(
                tokens, i, stop_tokens=self._stop_for(name)
            )
            if not silent:
                errors += sub_errors
            return i + consumed

        # 块类（@BeginEnd 等）→ 跳到 end_case
        if info.get("is_block"):
            ec: set[str] = {s for s in (info.get("end_case") or [])}
            if ec:
                return self._skip_to_end(tokens, i, ec, limit)
            return i

        # 语句类（@Stmt / @IfBlock 等嵌套语句）→ 跳到 end_case（扁平化）
        if info.get("is_statement"):
            ec: set[str] = {s for s in (info.get("end_case") or [])}
            if ec:
                return self._skip_to_end(tokens, i, ec, limit)
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
            k = self.match(tokens, j, feat, sub_errs, limit, strict)
            if k <= j:
                # 某元素未推进 → 整体回滚（防止前一元素失败后
                # 后续 @Expression 在未推进位置假匹配）
                return start
            j = k
        if not silent:
            errors += sub_errs
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
        self, tokens: list[Token], i: int, node: dict, limit: int
    ) -> int:
        inner = node.get("elem", {})
        trial: list = []
        j = self.match(tokens, i, inner, trial, limit, strict=False)
        return j if j > i else i

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
