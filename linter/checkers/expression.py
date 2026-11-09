"""checkers/expression.py — 表达式检查器（复用 parser 的 pratt 部分）。

设计：表达式处理完全复用解析器能力，不在代码中固化任何组合逻辑。
    - 运算符链 / 中缀 / 优先级：parse_with_count + parser.operator_defs（配置驱动）。
    - 原子（Number / SelectExpr / ConcatExpr / ReplicateExpr /
      CallExpr / SysFuncCall / ParenthesizedExpr / 括号）：交给共享 RuleMatcher
      按 is_atom 规则的 production 内联匹配，参考 parser 的 atomic_rules 流程
      （收集 is_atom 规则、按 production 长度降序逐个尝试），不手写。

Doc: linter/linter_architecture.md

左递归约束：表达式文法暗含（间接）左递归环（@Expression ⇄ @PrimaryExpr ⇄
@SelectSuffix/@ParenthesizedExpr/...），LL 解析流程无法跳出调用循环，必须由
pratt 切断。因此 production 内凡遇 @Expression / pratt 规则一律交回 consume
（pratt 的 binding power + stop_tokens 保证终止）；原子匹配只消费操作数、不
消费运算符（避免 a <= b 赋值 vs 比较歧义）。
"""

from __future__ import annotations

from core.config_registry import ConfigRegistry
from core.define import Token

from .. import LintDiagnostic, token_span
from parser.pratt_parser import install_token_classifier, parse_with_count


class ExpressionChecker:
    """表达式验证器：consume() 返回 (错误列表, 消费数)。"""

    # 递归深度保护：表达式嵌套（SelectSuffix/Concat 内 @Expression）可能病态
    # 递归，超过阈值时截断（仅影响病态输入，正常表达式深度远小于此）。
    _MAX_DEPTH = 40
    _DEPTH = {"n": 0}

    def __init__(self, operator_defs: list, atom_matcher=None) -> None:
        self._op_defs = operator_defs
        # 原子匹配器（共享 RuleMatcher）由 scanner 后置注入：pratt 的原子回调
        # 按 is_atom 规则 production 匹配（参考 parser atomic_rules），不固化。
        self._atom_matcher = atom_matcher
        # 注释过滤视图缓存（key=(id(tokens), len)）：注释是 trivia，但 pratt 只
        # 跳过 space/newline 类；三元 `?:` 前/后夹注释（宏体尾注释被铺进流，
        # 真实语料 crc32 `POLY` 命中）会让 pratt 在 comment 处失配 ⇒ 整句误报。
        # 每次 consume 都重建视图会 O(n²)（大文件全量套件卡死），故按 token 流
        # 缓存一次；consumed 通过原下标映射回原流。
        self._comment_views: dict[tuple[int, int], tuple[list, list[int]]] = {}
        # pratt 解析依赖 token 分类器（is_number/is_string/...），需安装
        categories = ConfigRegistry._loaded.get("parser.token_categories", {})
        install_token_classifier(categories)

    def set_atom_matcher(self, matcher) -> None:
        """注入共享原子匹配器（RuleMatcher.match_atom，production 驱动）。"""
        self._atom_matcher = matcher

    def _atom_parser(self, tokens: list[Token], idx: int):
        """pratt 的原子解析器回调：交共享原子匹配器，未注入/未命中回退 pratt 内置。"""
        if self._atom_matcher is None:
            return None, 0
        return self._atom_matcher.match_atom(tokens, idx)

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

    def _comment_view(self, tokens: list[Token]) -> tuple[list, list[int]] | None:
        """含注释的 token 流 → (滤注释视图, 视图下标→原下标)；无注释 → None。"""
        key = (id(tokens), len(tokens))
        cached = self._comment_views.get(key)
        if cached is not None:
            return cached
        if not any(t.type == "comment" for t in tokens):
            return None
        view: list = []
        pos_map: list[int] = []
        for i, tok in enumerate(tokens):
            if tok.type == "comment":
                continue
            view.append(tok)
            pos_map.append(i)
        if len(self._comment_views) > 8:  # 会话内少量 token 流（防缓存无界）
            self._comment_views.clear()
        self._comment_views[key] = (view, pos_map)
        return view, pos_map

    def _comment_fallback(
        self, tokens: list[Token], idx: int, stop_tokens: set[str] | None
    ) -> int | None:
        """滤注释视图重试：成功返回原流消费数，失败/无注释返回 None。"""
        view_info = self._comment_view(tokens)
        if view_info is None:
            return None
        view, pos_map = view_info
        import bisect

        start = bisect.bisect_left(pos_map, idx)
        if start >= len(view):
            return None
        try:
            _, consumed_view = parse_with_count(
                view,
                start,
                operator_defs=self._op_defs,
                atom_parser=self._atom_parser,
                stop_tokens=stop_tokens,
            )
        except ValueError:
            return None
        if consumed_view <= 0:
            return None
        return pos_map[start + consumed_view - 1] + 1 - idx

    def _consume_inner(
        self,
        tokens: list[Token],
        idx: int,
        stop_tokens: set[str] | None,
    ) -> tuple[list[LintDiagnostic], int]:
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
                        range=token_span(t),
                        message=f"expected expression, got '{t.type}'",
                        severity=1,
                        code="phase-expr",
                    )
                ], 1
            # 表达式在 comment 处停住（注释是 trivia，pratt 不跳过）⇒ 用缓存
            # 滤注释视图再试一次；只有"成功且消费更多"才采用（不改变原本成功的
            # 解析面，真实语料 crc32 `POLY` 尾注释进三元 `?:` 命中）。
            if idx + consumed < len(tokens) and tokens[idx + consumed].type == "comment":
                more = self._comment_fallback(tokens, idx, stop_tokens)
                if more is not None and more > consumed:
                    consumed = more
            return [], consumed
        except ValueError as exc:
            # 注释夹在 `?:` 中间时 pratt 可能直接抛"意外 token"（不是停在
            # comment 上）⇒ 同样用缓存滤注释视图重试；失败才保留原诊断。
            more = self._comment_fallback(tokens, idx, stop_tokens)
            if more is not None:
                return [], more
            t = tokens[idx]
            return [
                LintDiagnostic(
                    range=token_span(t),
                    message=str(exc),
                    severity=1,
                    code="phase-expr",
                )
            ], 1
        except Exception:  # noqa: BLE001 — 取 token 失败返回空结果，检查器按不可判处理
            t = tokens[idx]
            return [
                LintDiagnostic(
                    range=token_span(t),
                    message=f"invalid expression at '{t.content}'",
                    severity=1,
                    code="phase-expr",
                )
            ], 1


