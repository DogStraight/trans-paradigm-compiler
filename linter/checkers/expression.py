"""checkers/expression.py — 表达式检查器（借力 parser 的 pratt 部分）。

复用 parser/pratt_parser.parse_with_count 做表达式解析，并通过独立原子
匹配器（_match_atom）处理 pratt 内置不认识的 Verilog 原子：
    - BitWidthLiteral  32'hFF（number ' id）
    - SelectExpr       a[3:0]、a[i][j]
    - ConcatExpr       {a, b}
    - ReplicateExpr    {4{1'b0}}
    - CallExpr         foo(a, b)
    - SysFuncCall      $clog2(x)

架构：表达式解析完全在 EC 域内自洽（原子内部 @Expression 递归走 EC），
matcher 不参与表达式递归，避免 PrimaryExpr ↔ EC 互相调用导致指数重入。

决策 3：表达式是 pratt 引用，借力解析器现有实现。
"""

from __future__ import annotations

from core.define import Token

from .. import LintDiagnostic, Position

_TRIVIA = frozenset({"space.fold", "space", "comment"})


class ExpressionChecker:
    """表达式验证器：consume() 返回 (错误列表, 消费数)。"""

    # 递归深度保护：表达式嵌套（SelectSuffix/Concat 内 @Expression）可能病态
    # 递归，超过阈值时截断（仅影响病态输入，正常表达式深度远小于此）。
    _MAX_DEPTH = 40
    _DEPTH = {"n": 0}

    def __init__(self, operator_defs: list, atom_matcher=None) -> None:
        self._op_defs = operator_defs
        self._atom_matcher = atom_matcher  # 兼容注入入口（实际用 _match_atom）
        # pratt 解析依赖 token 分类器（is_number/is_string/...），需安装
        from core.config_registry import ConfigRegistry
        from parser.pratt_parser import install_token_classifier

        categories = ConfigRegistry._loaded.get("parser.token_categories", {})
        install_token_classifier(categories)

    def set_atom_matcher(self, fn) -> None:
        """兼容注入（表达式原子由 EC 自洽处理，不再依赖外部 matcher）。"""
        self._atom_matcher = fn

    def _atom_parser(self, tokens: list[Token], idx: int):
        """pratt 的原子解析器回调：优先自定义原子，回退 None 交给 pratt 内置。"""
        return self._match_atom(tokens, idx)

    def consume(
        self,
        tokens: list[Token],
        idx: int,
        stop_tokens: set[str] | None = None,
    ) -> tuple[list[LintDiagnostic], int]:
        """从 idx 解析一个表达式。

        Returns:
            (errors, consumed) — 错误列表与消费的 token 数（至少 1）。
        """
        ExpressionChecker._DEPTH["n"] += 1
        if ExpressionChecker._DEPTH["n"] > ExpressionChecker._MAX_DEPTH:
            ExpressionChecker._DEPTH["n"] -= 1
            return [], 1  # 深度保护：仅前进 1 个 token，避免病态递归
        try:
            return self._consume_inner(tokens, idx, stop_tokens)
        finally:
            ExpressionChecker._DEPTH["n"] -= 1

    def _consume_inner(
        self,
        tokens: list[Token],
        idx: int,
        stop_tokens: set[str] | None,
    ) -> tuple[list[LintDiagnostic], int]:
        from parser.pratt_parser import parse_with_count

        if idx >= len(tokens):
            return [], 0
        try:
            _, consumed = parse_with_count(
                tokens,
                idx,
                operator_defs=self._op_defs,
                atom_parser=self._atom_parser,
                stop_tokens=stop_tokens,
            )
            if consumed <= 0:
                t = tokens[idx]
                return [
                    LintDiagnostic(
                        range=(Position(t.line, t.column), Position(t.line, t.column)),
                        message=f"expected expression, got '{t.type}'",
                        severity=1,
                        code="phase-expr",
                    )
                ], 1
            return [], consumed
        except ValueError as exc:
            t = tokens[idx]
            return [
                LintDiagnostic(
                    range=(Position(t.line, t.column), Position(t.line, t.column)),
                    message=str(exc),
                    severity=1,
                    code="phase-expr",
                )
            ], 1
        except Exception:
            t = tokens[idx]
            return [
                LintDiagnostic(
                    range=(Position(t.line, t.column), Position(t.line, t.column)),
                    message=f"invalid expression at '{t.content}'",
                    severity=1,
                    code="phase-expr",
                )
            ], 1

    # ── 独立原子匹配（表达式域自洽）────────────────

    def _match_atom(self, tokens: list[Token], idx: int):
        """尝试匹配一个 Verilog 原子表达式，返回 (node, consumed) 或 (None, 0)。"""
        n = len(tokens)
        j = self._skip_trivia(tokens, idx, n)
        if j >= n:
            return None, 0
        t = tokens[j]
        tt = t.type

        if tt == "bracket.l_curly_bracket":
            return self._match_concat(tokens, j, n)
        if tt == "literal.number":
            return self._match_number(tokens, j, n)
        if tt == "id":
            return self._match_identifier(tokens, j, n)
        if tt == "symbol.base.dollar":
            return self._match_syscall(tokens, j, n)
        return None, 0

    def _match_number(self, tokens: list[Token], j: int, n: int):
        """literal.number 或位宽字面量（number ' id）。"""
        k = self._skip_trivia(tokens, j + 1, n)
        if k < n and tokens[k].type == "symbol.base.single_quote":
            k2 = self._skip_trivia(tokens, k + 1, n)
            if k2 < n and tokens[k2].type == "id":
                return object(), k2 + 1 - j  # 位宽字面量 32'hFF
        return object(), 1  # 纯数字

    def _match_identifier(self, tokens: list[Token], j: int, n: int):
        """id 开头：SelectExpr / CallExpr / 简单 Identifier。"""
        k = self._skip_trivia(tokens, j + 1, n)
        if k < n and tokens[k].type == "bracket.l_square_bracket":
            return self._match_select(tokens, j, n)
        if k < n and tokens[k].type == "bracket.l_parentheses":
            return self._match_call(tokens, j, n)
        return object(), 1

    def _match_select(self, tokens: list[Token], j: int, n: int):
        """SelectExpr: id [ suffix ] ( [ suffix ] )*"""
        i = j + 1  # 已消费 id
        while i < n:
            i = self._skip_trivia(tokens, i, n)
            if i >= n or tokens[i].type != "bracket.l_square_bracket":
                break
            i = self._skip_trivia(tokens, i + 1, n)  # 消费 [
            c = self._consume_expr(
                tokens, i, {"symbol.base.colon", "bracket.r_square_bracket"}
            )
            i = self._skip_trivia(tokens, i + c, n)
            if i < n and tokens[i].type == "symbol.base.colon":
                c2 = self._consume_expr(tokens, i + 1, {"bracket.r_square_bracket"})
                i = self._skip_trivia(tokens, i + 1 + c2, n)
            if i >= n or tokens[i].type != "bracket.r_square_bracket":
                break
            i += 1
        return object(), i - j

    def _match_call(self, tokens: list[Token], j: int, n: int):
        """CallExpr: id ( args? )"""
        i = self._skip_trivia(tokens, j + 1, n)
        i = self._skip_trivia(tokens, i + 1, n)  # ( 之后
        first = self._consume_expr(
            tokens, i, {"symbol.base.comma", "bracket.r_parentheses"}
        )
        i = self._skip_trivia(tokens, i + first, n)
        while i < n and tokens[i].type == "symbol.base.comma":
            c = self._consume_expr(
                tokens, i + 1, {"symbol.base.comma", "bracket.r_parentheses"}
            )
            i = self._skip_trivia(tokens, i + 1 + c, n)
        if i < n and tokens[i].type == "bracket.r_parentheses":
            i += 1
        return object(), i - j

    def _match_syscall(self, tokens: list[Token], j: int, n: int):
        """SysFuncCall: $ id ( args? )"""
        i = self._skip_trivia(tokens, j + 1, n)
        if i >= n or tokens[i].type != "id":
            return object(), i - j
        i = self._skip_trivia(tokens, i + 1, n)
        if i >= n or tokens[i].type != "bracket.l_parentheses":
            return object(), i - j
        i = self._skip_trivia(tokens, i + 1, n)
        first = self._consume_expr(
            tokens, i, {"symbol.base.comma", "bracket.r_parentheses"}
        )
        i = self._skip_trivia(tokens, i + first, n)
        while i < n and tokens[i].type == "symbol.base.comma":
            c = self._consume_expr(
                tokens, i + 1, {"symbol.base.comma", "bracket.r_parentheses"}
            )
            i = self._skip_trivia(tokens, i + 1 + c, n)
        if i < n and tokens[i].type == "bracket.r_parentheses":
            i += 1
        return object(), i - j

    def _match_concat(self, tokens: list[Token], j: int, n: int):
        """ConcatExpr: { expr (, expr)* } 或 ReplicateExpr: { n { expr } }"""
        i = self._skip_trivia(tokens, j + 1, n)
        # ReplicateExpr: { number { expr } }
        if i < n and tokens[i].type == "literal.number":
            k = self._skip_trivia(tokens, i + 1, n)
            if k < n and tokens[k].type == "bracket.l_curly_bracket":
                k2 = self._consume_expr(tokens, k + 1, {"bracket.r_curly_bracket"})
                k3 = self._skip_trivia(tokens, k + 1 + k2, n)
                if k3 < n and tokens[k3].type == "bracket.r_curly_bracket":
                    k4 = self._skip_trivia(tokens, k3 + 1, n)
                    if k4 < n and tokens[k4].type == "bracket.r_curly_bracket":
                        return object(), k4 + 1 - j
        # ConcatExpr: { expr (, expr)* }
        first = self._consume_expr(
            tokens, i, {"symbol.base.comma", "bracket.r_curly_bracket"}
        )
        i = self._skip_trivia(tokens, i + first, n)
        while i < n and tokens[i].type == "symbol.base.comma":
            c = self._consume_expr(
                tokens, i + 1, {"symbol.base.comma", "bracket.r_curly_bracket"}
            )
            i = self._skip_trivia(tokens, i + 1 + c, n)
        if i < n and tokens[i].type == "bracket.r_curly_bracket":
            i += 1
        return object(), i - j

    # ── 辅助 ────────────────────────────────────

    def _consume_expr(self, tokens: list[Token], idx: int, stop: set[str]) -> int:
        """消费一个表达式（内部走 EC 递归），返回消费数。"""
        if idx >= len(tokens):
            return 0
        _, consumed = self.consume(tokens, idx, stop_tokens=stop)
        return consumed

    @staticmethod
    def _skip_trivia(tokens: list[Token], i: int, n: int) -> int:
        while i < n and tokens[i].type in _TRIVIA:
            i += 1
        return i
