"""
scanner.py — 三阶管线 Linter。

P0: Token 检查 — 未定义宏等非法 token
P1: 块边界配对 — bound.start/end 栈追踪
P2: 语句识别 — start_tokens → end_case 边界

每层可独立开关。LinterScanner(...) 构造时通过 enable_phase0/1/2 控制。
"""

import os
from core.define import Token, GrammarRule
from core.config_registry import ConfigRegistry
from lexer import Lexer
from parser import setup_grammar
from preprocessor._expand import scan_directives, expand_tokens, _load_config

from . import LintDiagnostic, Position
from .grammar_slicer import build_slice_tree, get_start_tokens

_TRIVIA = frozenset({"space.fold", "comment", "space"})


class LinterScanner:
    def __init__(
        self,
        rules_dir: str,
        ext_dirs: list[str] | None = None,
        enable_phase0: bool = True,
        enable_phase1: bool = True,
        enable_phase2: bool = True,
    ):
        self._rules_dir = rules_dir
        ext_list = ext_dirs or []
        ext_list = ext_dirs or []
        ConfigRegistry.load_all(
            rules_dir,
            ext_dirs=ext_list,
            plugins_dir=os.path.join(rules_dir, "plugins"),
        )
        from core.define import GrammarRulesRegister

        rules = setup_grammar(
            rules_dir, GrammarRulesRegister.get_default(), ext_dirs=ext_list
        )
        self._tree = build_slice_tree(rules)
        self.lexer = Lexer(rules_dir=rules_dir, ext_dirs=ext_list)

        self._start_map: dict[str, list[dict]] = {}
        for name, info in self._tree.items():
            if not info["prods"]:
                continue
            for tt in get_start_tokens(info["prods"], self._tree):
                if tt not in info.get("end_case", set()):
                    entry: dict = {**info, "_name": name}
                    if info.get("is_block"):
                        bs = getattr(rules.get(name), "block_start", "") or ""
                        if bs:
                            entry["_block_start"] = bs
                    self._start_map.setdefault(tt, []).append(entry)

        # 补充：将 block.start 也注册为起始 token
        # 允许多个规则共享同一 block.start（如 FuncDeclANSI + FuncDeclOld）
        for name, rule in rules.items():
            bs = getattr(rule, "block_start", "") or ""
            if not bs:
                continue
            # 跳过已通过 production 起始 token 注册的同名规则
            existing = self._start_map.get(bs, [])
            if any(e.get("_name") == name for e in existing):
                continue
            info = self._tree.get(name)
            if info and info["prods"]:
                self._start_map.setdefault(bs, []).append(
                    {**info, "_name": name, "_block_start": bs}
                )

        self._macro_prefix, _ = _load_config()

        # ── 动态收集 block 起止符 ─────────────────
        self._block_openers, self._block_closers, self._block_pairs, self._opener_to_rule = (
            self._build_block_delimiters(rules)
        )
        # 从 bound 配置推导括号起止符集 + 需跳过头的 bound
        self._bracket_openers = frozenset(
            t for t in self._block_openers if t.startswith("bracket.")
        )
        self._bracket_closers = frozenset(
            t for t in self._block_closers if t.startswith("bracket.")
        )
        self._header_bounds = frozenset(
            t for t in self._block_openers
            if not t.startswith("bracket.")
            and t not in ("keyword.begin", "keyword.generate")
        )

        # 从 bracket_map 配置推导所有括号 token（含非 bound 的花括号）
        _all_open = set(self._bracket_openers)
        _all_close = set(self._bracket_closers)
        _raw_pairs = ConfigRegistry._loaded.get("lexer.bracket_map", {}).get("pairs", [])
        for _, _, _name in _raw_pairs:
            _all_open.add(f"bracket.l_{_name}")
            _all_close.add(f"bracket.r_{_name}")
        self._all_bracket_openers = frozenset(_all_open)
        self._all_bracket_closers = frozenset(_all_close)

        self.enable_phase0 = enable_phase0
        self.enable_phase1 = enable_phase1
        self.enable_phase2 = enable_phase2

    # ── 动态 block delimiter 收集 ─────────────────

    @staticmethod
    def _build_block_delimiters(
        rules: dict,
    ) -> tuple[set[str], set[str], dict[str, set[str]], dict[str, str]]:
        """从语法规则的 bound 字段收集起止符集合及配对映射。

        Returns: (openers, closers, closer_to_openers, opener_to_rule)
            closer_to_openers — 每个 closer token 对应的有效 opener token 集合。
            opener_to_rule    — 每个 opener token 对应的规则名称（用于骨架上上文）。
        """
        openers: set[str] = set()
        closers: set[str] = set()
        closer_to_openers: dict[str, set[str]] = {}
        opener_to_rule: dict[str, str] = {}
        for name, rule in rules.items():
            if not isinstance(rule, GrammarRule):
                continue
            bs = getattr(rule, "bound_start", "") or ""
            be = getattr(rule, "bound_end", "") or ""
            if not bs and not be:
                continue
            if bs:
                openers.add(bs)
                # 第一个声明该 bound 的规则胜出
                if bs not in opener_to_rule:
                    opener_to_rule[bs] = name
            if be:
                closers.add(be)
            if bs and be:
                closer_to_openers.setdefault(be, set()).add(bs)
        return openers, closers, closer_to_openers, opener_to_rule

    def scan(self, source: str) -> list[LintDiagnostic]:
        errors: list = []
        macro_defs, _, clean_source = scan_directives(source, self._rules_dir)
        if macro_defs:
            lex_source, _ = expand_tokens(
                clean_source, macro_defs, prefix=self._macro_prefix
            )
        elif clean_source != source:
            lex_source = clean_source
        else:
            lex_source = source

        tokens = self.lexer.tokenize(lex_source)
        if not tokens:
            return errors

        # ── P0: Token 检查 ────────────────────────
        if self.enable_phase0:
            errors += self._phase0_token_check(tokens)

        # ── P1: 块边界 ────────────────────────
        if self.enable_phase1:
            p1_errors = self._phase1_boundary(tokens)
            errors += p1_errors

        # ── P2: 语句识别 ────────────────────
        if self.enable_phase2:
            errors += self._phase2_statement(tokens)

        return errors

    # ── P0: Token 检查 ─────────────────────────

    def _phase0_token_check(self, tokens: list[Token]) -> list:
        """检测 token 流中不应存在的 token 类型（如未展开的宏）。"""
        errors: list = []
        for t in tokens:
            if t.type.startswith("macro."):
                errors.append(
                    LintDiagnostic(
                        range=(Position(t.line, t.column), Position(t.line, t.column)),
                        message=f"undefined macro '{t.content}'",
                        severity=1,
                        code="undefined-macro",
                    )
                )
        return errors

    # ── P1: 块边界 ──────────────────────────────

    def _phase1_boundary(self, tokens: list[Token]) -> list:
        """扫描 block start/end 配对，返回错误列表。"""
        errors: list = []
        stack: list[tuple[str, int]] = []
        for idx, t in enumerate(tokens):
            if t.type in _TRIVIA:
                continue
            if t.type in self._block_openers:
                stack.append((t.type, idx))
                continue
            if t.type not in self._block_closers:
                continue
            if not stack:
                errors.append(
                    LintDiagnostic(
                        range=(Position(t.line, t.column), Position(t.line, t.column)),
                        message=f"unmatched '{t.content}' without block start",
                        severity=1,
                        code="phase1-boundary",
                    )
                )
                continue
            expected_openers = self._block_pairs.get(t.type, set())
            actual, _ = stack.pop()
            if expected_openers and actual not in expected_openers:
                errors.append(
                    LintDiagnostic(
                        range=(Position(t.line, t.column), Position(t.line, t.column)),
                        message=f"mismatched block closer '{t.content}'",
                        severity=1,
                        code="phase1-boundary",
                    )
                )
                continue
        if stack:
            errors.append(
                LintDiagnostic(
                    range=(Position(0, 0), Position(0, 0)),
                    message=f"unclosed block: {len(stack)} unclosed block(s) at EOF",
                    severity=1,
                    code="phase1-boundary",
                )
            )

        return errors

    # ── Phase 2: 轻量句边界扫描 ─────────────────

    def _phase2_statement(self, tokens: list) -> list:
        """轻量版句扫描：用 _start_map + _consume 确定语句边界。

        括号深度从 _all_bracket_openers/_all_bracket_closers 推导。
        该集合合并了 bound 配置中的括号 + bracket_map 配置中的额外括号。
        """
        errors: list = []
        bracket_depth = 0
        skip_until_semi = False

        i = 0
        while i < len(tokens):
            i = self._skip(tokens, i)
            if i >= len(tokens):
                break
            t = tokens[i]

            if t.type == "newline":
                i += 1
                continue

            # 括号深度（从 _all_bracket_openers/_all_bracket_closers 推导）
            if t.type in self._all_bracket_openers:
                bracket_depth += 1
                i += 1
                continue
            if t.type in self._all_bracket_closers:
                bracket_depth = max(0, bracket_depth - 1)
                i += 1
                continue

            # 关键字 bound（非括号 bound）
            if t.type in self._block_openers:
                if t.type in self._header_bounds:
                    skip_until_semi = True
                i += 1
                continue
            if t.type in self._block_closers:
                i += 1
                continue

            if bracket_depth > 0:
                i += 1
                continue

            if skip_until_semi:
                if t.type == "symbol.base.semicolon":
                    skip_until_semi = False
                i += 1
                continue

            # 尝试 _start_map 匹配（轻量、无 AST）
            candidates = self._start_map.get(t.type, [])
            best_i = i
            for info in candidates:
                result = self._consume(tokens, i, info)
                if result is not None and result > best_i:
                    best_i = result
            if best_i > i:
                i = best_i
                continue

            # 无候选规则匹配 → 行级错误
            errors.append(
                LintDiagnostic(
                    range=(Position(t.line, t.column), Position(t.line, t.column)),
                    message=f"syntax error: unexpected '{t.content}'",
                    severity=1,
                    code="phase2-statement",
                )
            )
            i += 1
            while i < len(tokens) and tokens[i].type not in (
                "newline",
            ) and tokens[i].type not in self._block_closers and tokens[i].type not in self._all_bracket_closers:
                i += 1

        return errors

    def _consume(self, tokens: list, i: int, info: dict) -> int | None:
        ec = info.get("end_case", set())
        is_block = info.get("is_block", False)
        has_prods = bool(info.get("prods"))
        if is_block and not has_prods:
            return self._skip_to_end(tokens, i, ec) if ec else None
        if not ec:
            return i + 1
        return self._skip_to_end(tokens, i + 1, ec)

    # ── 辅助 ─────────────────────────────────────────

    def _skip_to_end(self, tokens: list[Token], i: int, end_set: set[str]) -> int:
        depth = 0
        exclude = {s[1:] for s in end_set if s.startswith("!")}
        positive = {s for s in end_set if not s.startswith("!")}
        if not positive:
            return self._skip(tokens, i + 1)
        while i < len(tokens):
            t = tokens[i]
            if t.type in exclude:
                i += 1
                continue
            # end_case 匹配优先于 trivia 跳过
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
        return i

    def _skip(self, tokens: list, i: int) -> int:
        while i < len(tokens) and tokens[i].type in _TRIVIA:
            i += 1
        return i
