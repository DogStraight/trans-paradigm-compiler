"""
scanner.py — 四阶管线 Linter。

P0: Token 检查 — 未定义宏等非法 token
P1: 块边界配对 — bound.start/end 栈追踪
P2: 语句识别 — start_tokens → end_case 边界
P3: 字面量匹配 — production 中 token 精确匹配

每层可独立开关。LinterScanner(...) 构造时通过 enable_phase0/1/2/3 控制。
"""

import os
from core.define import Token, GrammarRule
from core.config_registry import ConfigRegistry
from lexer import Lexer
from parser import setup_grammar
from preprocessor._expand import scan_directives, expand_tokens, _load_config

from . import LintDiagnostic, Position
from .grammar_slicer import build_slice_tree, get_start_tokens

_TRIVIA = frozenset({"newline", "space.fold", "comment", "space"})


def _is_better_match(
    best_errors: list | None,
    trial: list,
    best_is_stmt: bool,
    is_stmt: bool,
    result: int,
    best_i: int,
) -> bool:
    """判断 trial 是否优于当前最佳匹配。

    优先级：首次候选 > 更少错误 > 语句规则优先 > 更长匹配。
    """
    if best_errors is None:
        return True
    if len(trial) < len(best_errors):
        return True
    if len(trial) > len(best_errors):
        return False
    # 错误数相同：语句规则优先
    if is_stmt and not best_is_stmt:
        return True
    if not is_stmt and best_is_stmt:
        return False
    # 语句状态相同：取更长匹配
    return result > best_i


class LinterScanner:
    def __init__(
        self,
        rules_dir: str,
        ext_dirs: list[str] | None = None,
        enable_phase0: bool = True,
        enable_phase1: bool = True,
        enable_phase2: bool = True,
        enable_phase3: bool = False,
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
        self._grammar_rules = rules
        self.lexer = Lexer(rules_dir=rules_dir, ext_dirs=ext_list)

        self._start_map: dict[str, list[dict]] = {}
        for name, info in self._tree.items():
            if not info["prods"]:
                continue
            for tt in get_start_tokens(info["prods"]):
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

        self.enable_phase0 = enable_phase0
        self.enable_phase1 = enable_phase1
        self.enable_phase2 = enable_phase2
        self.enable_phase3 = enable_phase3
        self._p3_depth = 0
        self._p3_trace_log: list[str] = []

    # ── P3 调试追踪 ────────────────────────────────

    @property
    def debug_p3(self) -> bool:
        return getattr(self, "_debug_p3", False)

    @debug_p3.setter
    def debug_p3(self, value: bool):
        self._debug_p3 = value
        if not value:
            self._p3_trace_log.clear()

    def _p3_trace(self, event: str, i: int, detail: str = "", **kw):
        """记录 P3 递归追踪。仅在 debug_p3=True 时生效。

        event — 事件名（enter/exit/decision/error）
        i     — 当前 token 位置
        detail — 人类可读描述
        kw     — 额外结构信息
        """
        if not self.debug_p3:
            return
        indent = "  " * self._p3_depth
        parts = [f"{indent}{event:8s} i={i:3d}"]
        if detail:
            parts.append(detail)
        for k, v in kw.items():
            parts.append(f"{k}={v}")
        self._p3_trace_log.append(" ".join(parts))

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
        skeleton: dict = {"type": "root", "start": 0, "end": len(tokens), "children": []}
        if self.enable_phase1:
            p1_errors, skeleton = self._phase1_boundary(tokens)
            errors += p1_errors

        # ── P2: 语句识别 ────────────────────
        if self.enable_phase2:
            errors += self._phase2_statement(tokens, skeleton)

        # ── P3: 字面量匹配 ─────────────────
        # （待重构）

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

    def _phase1_boundary(self, tokens: list[Token]) -> tuple[list, dict]:
        """扫描 block start/end 配对，返回 (errors, skeleton)。

        skeleton 为嵌套的边界树，每个 bound 节点含规则名称：
            {
                "type": "root",
                "rule": "",
                "start": 0, "end": 100,
                "children": [
                    {
                        "type": "bound",
                        "rule": "ModuleDecl",
                        "start": 2, "end": 96,
                        "children": [...]
                    }
                ]
            }
        """
        errors: list = []
        raw_regions: list[tuple[int, int, str]] = []
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
            actual, start_idx = stack.pop()
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
            # 记录闭合区域（含规则名称）
            rule_name = self._opener_to_rule.get(actual, actual)
            raw_regions.append((start_idx, idx, rule_name))
        if stack:
            errors.append(
                LintDiagnostic(
                    range=(Position(0, 0), Position(0, 0)),
                    message=f"unclosed block: {len(stack)} unclosed block(s) at EOF",
                    severity=1,
                    code="phase1-boundary",
                )
            )

        skeleton = self._build_skeleton(raw_regions, len(tokens))
        return errors, skeleton

    @staticmethod
    def _build_skeleton(
        regions: list[tuple[int, int, str]], total: int
    ) -> dict:
        """从 (start, end, rule_name) 列表构建嵌套骨架树。"""
        regions.sort(key=lambda r: r[0])
        root: dict = {
            "type": "root",
            "rule": "",
            "start": 0,
            "end": total,
            "children": [],
        }
        stack: list[dict] = [root]

        for start, end, rule_name in regions:
            node: dict = {
                "type": "bound",
                "rule": rule_name,
                "start": start,
                "end": end,
                "children": [],
            }
            while stack and not (
                stack[-1]["start"] <= start and end <= stack[-1]["end"]
            ):
                stack.pop()
            if stack:
                stack[-1]["children"].append(node)
            stack.append(node)

        return root

    # ── Phase 2: 复用解析器做句验证 ─────────────

    def _phase2_statement(self, tokens: list, skeleton: dict) -> list:
        """复用 parser 的句解析函数，验证每行是否为合法语句开始。

        1. 利用 P1 骨架跳过 bound 区域
        2. 对非 bound token 调用 parser.parse_sentence 尝试解析
        3. 解析失败 → 报行级错误，跳到换行
        4. 解析成功 → 推进到解析结束位置
        """
        from parser.parser_core import Parser, ParseContext
        from parser.rule_selector import RuleSelector

        # 延迟初始化 parser 实例
        if not hasattr(self, "_p2_parser"):
            rules_dict = self._grammar_rules
            stmt_names = [
                n for n, r in rules_dict.items()
                if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
            ]
            rs = RuleSelector(rules_dict, stmt_names)
            self._p2_parser = Parser(rules=rules_dict, rule_selector=rs)

        parser = self._p2_parser
        context = ParseContext(tokens)
        errors: list = []

        i = 0
        bracket_depth = 0
        # 模块头等待关闭：跳过 module name #(...) (...); 区域
        skip_until_semi = False

        while i < len(tokens):
            i = self._skip(tokens, i)
            if i >= len(tokens):
                break
            t = tokens[i]

            # 括号/方括号深度
            if t.type in ("bracket.l_parentheses", "bracket.l_square_bracket"):
                bracket_depth += 1
                i += 1
                continue
            if t.type in ("bracket.r_parentheses", "bracket.r_square_bracket"):
                bracket_depth = max(0, bracket_depth - 1)
                i += 1
                continue

            # 关键字 bound 起止符
            if t.type in self._block_openers:
                # module/function/task 后跳过到 `;`（模块/函数头）
                if t.type in ("keyword.module", "keyword.function", "keyword.task"):
                    skip_until_semi = True
                i += 1
                continue
            if t.type in self._block_closers:
                i += 1
                continue

            # 括号/方括号内部 → 跳过
            if bracket_depth > 0:
                i += 1
                continue

            # 模块头跳过模式
            if skip_until_semi:
                if t.type == "symbol.base.semicolon":
                    skip_until_semi = False
                i += 1
                continue

            # 调用 parser 尝试解析一条句子
            context.token_pointer = i
            context.match_length = 0
            context.current_node = None
            context.current_rule = None
            context.sibling_counter.clear()
            context.path_stack.clear()

            try:
                node = parser.parse_sentence(context)
            except Exception:
                node = None

            if node is not None:
                # 解析成功，跳到句子末尾
                i = context.token_pointer
                continue

            # 解析失败：报行级错误，跳到换行
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
            ) and tokens[i].type not in self._block_closers and tokens[i].type not in (
                "bracket.r_parentheses", "bracket.r_square_bracket"
            ):
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

    # ── Phase 3: 字面量匹配（递归岛式）────────────

    def _phase3_literal(self, tokens: list) -> list:
        """字面量匹配：逐 token 推进，在每个位置尝试语句规则匹配。

        岛屿边界由规则的 end_case 定义，不依赖 _match_island
        返回值跳跃，确保内层语句不被外层 block skip 吞掉。
        """
        errors: list = []
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t.type.startswith("macro."):
                i += 1
                continue
            self._p3_trace("scan", i, f"token={t.type}({t.content})")
            candidates = self._start_map.get(t.type, [])
            if candidates:
                self._p3_trace(
                    "candidates", i, f"token={t.type}", count=len(candidates)
                )
            best_errors: list | None = None
            best_i = i
            best_is_stmt = False
            best_name = ""
            for info in candidates:
                prods = info.get("prods", [])
                if not prods:
                    continue
                name = info.get("_name", "?")
                trial: list = []
                # block 规则：block.start token 已被 parser 消费，
                # P3 需跳过当前 token 再从 production 起始匹配
                start_i = i
                if info.get("is_block") and info.get("_block_start"):
                    bs = info["_block_start"]
                    if start_i < len(tokens) and tokens[start_i].type == bs:
                        start_i += 1
                result = self._match_island(tokens, start_i, prods, trial)
                is_stmt = info.get("is_statement", False)
                self._p3_trace(
                    "trial",
                    i,
                    f"rule={name}",
                    result=result,
                    errs=len(trial),
                    is_stmt=is_stmt,
                )
                # 未推进的候选视为不匹配，不参与选择
                if result <= i:
                    continue
                if _is_better_match(
                    best_errors, trial, best_is_stmt, is_stmt, result, best_i
                ):
                    best_i = result
                    best_errors = trial
                    best_is_stmt = is_stmt
                    best_name = name
            if best_errors is not None:
                self._p3_trace(
                    "best", i, f"rule={best_name}", i_next=best_i, errs=len(best_errors)
                )
                errors += best_errors
                i = best_i  # 岛屿边界已可靠，直接跳跃
            else:
                i += 1
        return errors

    def _match_island(
        self,
        tokens: list,
        i: int,
        prods: list,
        errors: list,
        stop_on: set | None = None,
    ) -> int:
        """递归匹配 production 列表。

        语句岛屿：end_case 是岛屿边界，block 内容不扩展岛屿。
        返回岛屿末尾（end_case 处或 block 开始前），block 及其后的元素只验证不跳位。

        stop_on — 父层 end_case，当前 token 在其中时停止匹配（解决逗号歧义）。
        """
        if not prods or i >= len(tokens):
            return i
        # 首元素静默检查：未推进才算匹配失败
        # choice 的成功分支会附带失败分支的 silent 错误，不视为整体失败
        first_silent: list = []
        result = self._match_deep(tokens, i, prods[0], first_silent, stop_on=stop_on)
        if result <= i:
            self._p3_trace("exit", i, "first_elem_errored", result=result)
            return i
        i = result
        self._p3_trace("island", i, f"first_ok, stop_on={stop_on}", prods=len(prods))
        # 找到第一个 block call 的索引
        block_start = len(prods)
        for idx, feat in enumerate(prods[1:], start=1):
            if feat.get("type") != "call":
                continue
            info = self._tree.get(feat.get("name", ""))
            if info and self._depth_for(info) == "block":
                block_start = idx
                break
        # 岛屿元素：正常匹配，影响 i
        for feat in prods[1:block_start]:
            if i >= len(tokens):
                break
            # 当前 token 是父层 end_case 边界 → 停
            if stop_on and tokens[i].type in stop_on:
                self._p3_trace("stop", i, f"hit stop_on {tokens[i].type}")
                break
            i = self._match_deep(tokens, i, feat, errors, stop_on=stop_on)
        self._p3_trace("island_end", i, f"block_start={block_start}")
        # block 及之后：独立验证，不影响岛屿边界
        j = i
        for feat in prods[block_start:]:
            if j >= len(tokens):
                break
            if stop_on and tokens[j].type in stop_on:
                break
            j = self._match_deep(tokens, j, feat, errors, stop_on=stop_on)
        return i

    def _match_deep(
        self,
        tokens: list,
        i: int,
        node: dict,
        errors: list,
        stop_on: set | None = None,
    ) -> int:
        """递归匹配一个元素 — 按 type 分发到对应处理器。

        匹配前跳过 trivia（newline/space/comment），与 parser 的 _skip_tokens 一致。
        """
        if i >= len(tokens):
            return i
        if stop_on and tokens[i].type in stop_on:
            self._p3_trace("boundary", i, f"hit stop_on {tokens[i].type}")
            return i
        # 跳过 trivia，确保匹配时指向有效 token
        i = self._skip(tokens, i)
        if i >= len(tokens):
            return i
        if stop_on and tokens[i].type in stop_on:
            return i
        typ = node.get("type", "")
        self._p3_trace(
            "enter", i, f"type={typ}", node=node.get("name", node.get("token_type", ""))
        )

        handler = {
            "token": self._match_token,
            "call": self._match_call,
            "optional": self._match_optional,
            "choice": self._match_choice,
            "seq": self._match_seq,
            "repeat": self._match_repeat,
            "plus": self._match_plus,
        }.get(typ)
        if handler:
            return handler(tokens, i, node, errors, stop_on)
        return i + 1

    # ── _match_deep 子分发器 ──────────────────────

    def _match_token(
        self,
        tokens: list[Token],
        i: int,
        node: dict,
        errors: list,
        stop_on: set | None = None,
    ) -> int:
        """精确匹配 token。"""
        tok = node["token_type"]
        if node.get("optional"):
            if i < len(tokens) and tokens[i].type == tok:
                return i + 1
            return i
        if i < len(tokens) and tokens[i].type == tok:
            return i + 1
        t = tokens[i]
        errors.append(
            LintDiagnostic(
                range=(Position(t.line, t.column), Position(t.line, t.column)),
                message=f"expected '{tok}', got '{t.type}'",
                severity=1,
                code="phase3-literal",
            )
        )
        self._p3_trace("token_err", i, f"want={tok} got={t.type}")
        return i + 1

    def _match_call(
        self,
        tokens: list[Token],
        i: int,
        node: dict,
        errors: list,
        stop_on: set | None = None,
    ) -> int:
        """@SubRule 调用，按 depth 分发。

        optional 的 @SubRule? 先静默尝试匹配，成功则前进。
        """
        if node.get("optional"):
            info = self._tree.get(node["name"])
            if info:
                silent: list = []
                result = self._match_call_impl(
                    tokens, i, info, silent, stop_on, node["name"]
                )
                if result > i and not silent:
                    return result
            return i
        return self._match_call_impl(
            tokens, i, self._tree.get(node["name"]), errors, stop_on, node["name"]
        )

    def _match_call_impl(
        self,
        tokens: list[Token],
        i: int,
        info: dict | None,
        errors: list,
        stop_on: set | None = None,
        name: str = "",
    ) -> int:
        """@SubRule 调用实现（按 depth 分发），供 _match_call 和 optional 路径共用。"""
        if info is None:
            return i + 1
        depth = self._depth_for(info)
        self._p3_trace("branch", i, f"call {name}", depth=depth)
        prods = info.get("prods", [])
        if depth == "block":
            ec = info.get("end_case", set())
            if not ec:
                return i + 1
            end_pos = self._skip_to_end(tokens, i, ec)
            return max(i, end_pos - 1)
        if not prods:
            return i + 1
        if depth == "atom":
            return i + 1
        if depth == "shallow":
            return self._match_shallow(tokens, i, prods, errors)
        # full
        stop = set(info.get("end_case", set()))
        if stop_on:
            stop |= stop_on
        self._p3_trace("full", i, f"recurse {name}", stop=stop)
        return self._match_island(tokens, i, prods, errors, stop_on=stop)

    def _match_optional(
        self,
        tokens: list[Token],
        i: int,
        node: dict,
        errors: list,
        stop_on: set | None = None,
    ) -> int:
        """optional：静默尝试，失败不推进。"""
        inner = node.get("elem", {})
        silent: list = []
        result = self._match_deep(tokens, i, inner, silent, stop_on=stop_on)
        if result > i and not silent:
            self._p3_trace("optional", i, "matched", result=result)
            return result
        self._p3_trace("optional", i, "skipped")
        return i

    def _match_choice(
        self,
        tokens: list[Token],
        i: int,
        node: dict,
        errors: list,
        stop_on: set | None = None,
    ) -> int:
        """choice：试所有路径，取错误最少的。"""
        best_i = i
        best_silent: list = []
        for alt_idx, alt in enumerate(node.get("alternatives", [])):
            silent_errs: list = []
            result = self._match_deep(tokens, i, alt, silent_errs, stop_on=stop_on)
            self._p3_trace(
                "choice", i, f"alt#{alt_idx}", result=result, errs=len(silent_errs)
            )
            if result < best_i:
                continue
            if result > best_i:
                best_i = result
                best_silent = silent_errs
            elif len(silent_errs) < len(best_silent):
                best_silent = silent_errs
        if best_i > i:
            errors += best_silent
            return best_i
        t = tokens[i]
        errors.append(
            LintDiagnostic(
                range=(Position(t.line, t.column), Position(t.line, t.column)),
                message=f"unexpected '{t.content}'",
                severity=1,
                code="phase3-literal",
            )
        )
        return i + 1

    def _match_seq(
        self,
        tokens: list,
        i: int,
        node: dict,
        errors: list,
        stop_on: set | None = None,
    ) -> int:
        """seq：顺序组，每个元素依次匹配。"""
        for item in node.get("items", []):
            if i >= len(tokens):
                break
            i = self._match_deep(tokens, i, item, errors, stop_on=stop_on)
        return i

    def _match_repeat(
        self,
        tokens: list,
        i: int,
        node: dict,
        errors: list,
        stop_on: set | None = None,
    ) -> int:
        """repeat：贪婪重复，直到无法推进。"""
        count = 0
        while i < len(tokens):
            prev_i = i
            silent: list = []
            result = self._match_deep(
                tokens, i, node.get("elem", {}), silent, stop_on=stop_on
            )
            if result <= prev_i or silent:
                break
            i = result
            count += 1
        self._p3_trace("repeat", i, f"matched {count}x")
        return i

    def _match_plus(
        self,
        tokens: list,
        i: int,
        node: dict,
        errors: list,
        stop_on: set | None = None,
    ) -> int:
        """plus：至少匹配一次。"""
        silent: list = []
        first = self._match_deep(
            tokens, i, node.get("elem", {}), silent, stop_on=stop_on
        )
        if first <= i or silent:
            t = tokens[i]
            errors.append(
                LintDiagnostic(
                    range=(Position(t.line, t.column), Position(t.line, t.column)),
                    message="expected at least one match",
                    severity=1,
                    code="phase3-literal",
                )
            )
            self._p3_trace("plus_err", i, "no_match")
            return i + 1
        i = first
        count = 1
        while i < len(tokens):
            prev_i = i
            i = self._match_deep(
                tokens, i, node.get("elem", {}), errors, stop_on=stop_on
            )
            if i <= prev_i:
                break
            count += 1
        self._p3_trace("plus", i, f"matched {count}x")
        return i

    def _depth_for(self, info: dict) -> str:
        """根据 structure + pratt + is_atom 决定匹配深度。"""
        if info.get("pratt") or info.get("is_atom"):
            return "atom"
        if info.get("is_block"):
            return "block"
        if info.get("is_statement"):
            return "shallow"
        if info.get("prods"):
            return "full"
        return "atom"

    def _match_shallow(self, tokens: list, i: int, prods: list, errors: list) -> int:
        """浅匹配：匹配字面量 token，@SubRule 做边界跳过。

        入口跳过 trivia，与 _match_deep 一致。
        """
        i = self._skip(tokens, i)
        for feat in prods:
            if i >= len(tokens):
                break
            i = self._match_shallow_elem(tokens, i, feat, errors)
        return i

    def _match_shallow_elem(
        self, tokens: list[Token], i: int, node: dict, errors: list
    ) -> int:
        if i >= len(tokens):
            return i
        typ = node.get("type", "")
        if typ == "token":
            tok = node["token_type"]
            if node.get("optional"):
                if tokens[i].type == tok:
                    return i + 1
                return i
            if tokens[i].type == tok:
                return i + 1
            t = tokens[i]
            errors.append(
                LintDiagnostic(
                    range=(Position(t.line, t.column), Position(t.line, t.column)),
                    message=f"expected '{tok}', got '{t.type}'",
                    severity=1,
                    code="phase3-literal",
                )
            )
            return i + 1
        if typ == "call":
            if node.get("optional"):
                return i
            info = self._tree.get(node["name"])
            sub_ec = info.get("end_case", set()) if info else set()
            if sub_ec:
                return self._skip_to_end(tokens, i, sub_ec)
            # 无 end_case 的 call：默认只匹配下一个非 trivia token
            return self._skip(tokens, i + 1)
        if typ == "optional":
            inner = node.get("elem", {})
            result = self._match_shallow_elem(tokens, i, inner, errors)
            if result is not None and result > i:
                return result
            return i
        # choice/seq/repeat/plus 等复合类型：浅匹配不深入，不消费
        return i

    # ── 辅助 ─────────────────────────────────────────

    def _skip_to_end(self, tokens: list, i: int, end_set: set[str]) -> int:
        depth = 0
        # 分离 ! 前缀的排除项
        exclude = {s[1:] for s in end_set if s.startswith("!")}
        positive = {s for s in end_set if not s.startswith("!")}
        # 没有正项止步条件时，只前进 1 token（避免吞掉整个语句）
        if not positive:
            return self._skip(tokens, i + 1)
        while i < len(tokens):
            t = tokens[i]
            if t.type in _TRIVIA:
                i += 1
                continue
            # ! 前缀表示遇到该 token 时不停止（继续前进）
            if t.type in exclude:
                i += 1
                continue
            if "newline" in positive and t.type == "newline":
                return i + 1
            if t.type in positive and depth == 0:
                return i + 1
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
