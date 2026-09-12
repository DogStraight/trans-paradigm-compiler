"""
scanner.py — 两阶段 Linter 编排器。

发现阶段（discovery.py）：
    token 流 → 自动注册的扁平节点列表（轻量 AST）

检查阶段（checkers/）：
    每个节点实例化对应 Checker，扁平 validate，合并错误
        boundary.py    — 块边界配对（原 P1）
        macro_token.py — 非法 token（原 P0）
        statement.py   — 语句结构（从 production 编译）
        expression.py  — 表达式（借力 parser pratt）

每层可独立开关。LinterScanner(...) 构造时通过 enable_phase0/1/2 控制。

Doc: linter/linter_architecture.md
Doc: linter/linter_architecture.md
"""

import os

from core.define import GrammarRule, Token
from core.config_registry import ConfigRegistry, declare_cfg
from core.token_protocol import (
    BRACKET_L_PREFIX,
    BRACKET_R_PREFIX,
    COMMENT_TOKEN_TYPE,
    bracket_left,
    bracket_right,
)
from lexer import Lexer
from parser import setup_grammar
from preprocessor._expand import scan_directives, expand_tokens, _load_config

from . import LintDiagnostic, Position
from .grammar_slicer import build_slice_tree
from .discovery import Discovery
from .checker import CheckerRegistry
from .checkers.boundary import BoundaryChecker
from .checkers.macro_hygiene import MacroHygieneChecker
from .checkers.macro_token import MacroTokenChecker
from .checkers.statement import StatementChecker
from .checkers.expression import ExpressionChecker

# linter.macro_hygiene
#   #sym:config = [macro_hygiene]
#   格式: dict — { enabled, define_directive, undef_directive,
#                  nettype_directive, nettype_restore, continuation }
# 语言包未声明（或 enabled=false）→ MH 检查器不注册（零开销）。
# 关键字缺省 → 对应子检查自行跳过（见 MacroHygieneChecker）。
_macro_hygiene_cfg: dict = declare_cfg(
    "linter.macro_hygiene", {}, __name__, "_macro_hygiene_cfg"
)


def _derive_opener_prev_excludes(tree: dict) -> dict[str, frozenset[str]]:
    """语法推导块 opener 的非起始前驱 token 集（供 BoundaryChecker）。

    production 树中 (symbol.base.colon, keyword.X) 相邻 token 对（X 是块
    opener）→ X 的前驱排除 colon：该位置的 X 是子句终结形态（如 config
    插件的 use 子句 use lib.cell:config），不是块起始。BoundaryChecker
    压栈时命中排除即不压——避免 :config 被当 config 块 opener 造成
    unclosed 误报。推导是通用结构（不硬编码关键字名），语言知识留 TOML。
    """
    excludes: dict[str, set[str]] = {}

    def walk(feat):
        """返回 feature 可能的末尾 token 集合（call 截断）。"""
        if feat is None:
            return {None}
        typ = feat.get("type")
        if typ == "token":
            return {feat.get("token_type", "")}
        if typ == "call":
            return {None}
        if typ == "seq":
            ends = {None}
            for item in feat.get("items", []):
                starts = walk(item)
                for e in ends:
                    for st in starts:
                        if st and e == "symbol.base.colon" and st.startswith("keyword."):
                            excludes.setdefault(st, set()).add(e)
                ends = starts
            return ends
        if typ in ("repeat", "optional", "plus"):
            return walk(feat.get("elem")) | {None}
        if typ == "choice":
            acc = set()
            for alt in feat.get("alternatives", []):
                acc |= walk(alt)
            return acc
        return {None}

    for info in tree.values():
        if not isinstance(info, dict):
            continue
        for prod in info.get("prods", []):
            walk(prod)
    return {k: frozenset(v) for k, v in excludes.items()}


class LinterScanner:
    def __init__(
        self,
        rules_dir: str,
        ext_dirs: list[str] | None = None,
        enable_phase0: bool = True,
        enable_phase1: bool = True,
        enable_phase2: bool = True,
        register=None,
        trace_discovery: bool | None = None,
    ):
        """register: GrammarRulesRegister 实例。默认全局单例；多语言场景
        （如 c4 测试）应传独立实例——单例的 self.rules 累积多目录规则，
        切语言时旧语言规则会混入新语言规则表。
        trace_discovery: 消歧决策 trace 开关（None = 环境变量
        TPC_LINT_TRACE；True/False 显式覆盖）——classify 返回非预期结果
        时输出 Level 1/Level 2 决策过程到 stderr 定位。"""
        self._rules_dir = rules_dir
        ext_list = ext_dirs or []
        ConfigRegistry.load_all(
            rules_dir,
            ext_dirs=ext_list,
            plugins_dir=os.path.join(rules_dir, "plugins"),
        )
        from core.define import GrammarRulesRegister

        if register is None:
            register = GrammarRulesRegister.get_default()
        rules = setup_grammar(
            rules_dir, register, ext_dirs=ext_list
        )
        self._tree = build_slice_tree(rules)
        self.lexer = Lexer(rules_dir=rules_dir, ext_dirs=ext_list)

        self._macro_prefix, _ = _load_config()

        # ── 动态收集 block 起止符 ─────────────────
        _openers, _closers, self._block_pairs, _ = self._build_block_delimiters(rules)

        # 括号配对单一来源：lexer.bracket_map（规则侧 bracket bound 已移除，
        # 括号由 [bracket].pairs 统一定义）。括号同时加入 block 起止符集，
        # 使 BoundaryChecker 的栈式配对与 matcher 的括号上下文检查正常生效。
        _raw_pairs = ConfigRegistry._loaded.get("lexer.bracket_map", {}).get("pairs", [])
        _bracket_pairs: dict[str, set[str]] = {}
        for _, _, _name in _raw_pairs:
            _lt = bracket_left(_name)
            _rt = bracket_right(_name)
            _openers.add(_lt)
            _closers.add(_rt)
            _bracket_pairs.setdefault(_rt, set()).add(_lt)

        self._block_openers = frozenset(_openers)
        self._block_closers = frozenset(_closers)
        for _rt, _ls in _bracket_pairs.items():
            self._block_pairs.setdefault(_rt, set()).update(_ls)
        self._bracket_openers = frozenset(
            t for t in self._block_openers if t.startswith(BRACKET_L_PREFIX)
        )
        self._bracket_closers = frozenset(
            t for t in self._block_closers if t.startswith(BRACKET_R_PREFIX)
        )
        self._all_bracket_openers = self._bracket_openers
        self._all_bracket_closers = self._bracket_closers

        # 表达式检查器（借力 pratt）+ 共享规则匹配器
        from parser.pratt_parser import process_operator_data

        raw_ops = ConfigRegistry._loaded.get("parser.operator_defs", [])
        self._expr_checker = ExpressionChecker(process_operator_data(raw_ops))
        from .checkers.matcher import RuleMatcher

        self._matcher = RuleMatcher(
            self._tree,
            self._expr_checker,
            self._block_openers,
            self._block_closers,
        )
        # 后置注入：ExpressionChecker 的 pratt 原子回调复用共享 matcher 的
        # production 驱动原子匹配（参考 parser atomic_rules 流程，不手写原子逻辑）
        self._expr_checker.set_atom_matcher(self._matcher)

        self._discovery = Discovery(
            self._tree,
            self._block_openers,
            self._block_closers,
            self._all_bracket_openers,
            self._all_bracket_closers,
            matcher=self._matcher,
            trace=trace_discovery,
        )

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
            bs = getattr(rule, "block_start", "") or ""
            be = getattr(rule, "block_end", "") or ""
            if not bs and not be:
                continue
            if bs:
                openers.add(bs)
                # 第一个声明该 block 的规则胜出
                if bs not in opener_to_rule:
                    opener_to_rule[bs] = name
            if be:
                closers.add(be)
            if bs and be:
                closer_to_openers.setdefault(be, set()).add(bs)
        return openers, closers, closer_to_openers, opener_to_rule

    def scan(
        self,
        source: str,
        *,
        predefined: dict[str, str] | None = None,
        undefine: set[str] | None = None,
    ) -> list[LintDiagnostic]:
        """扫源文本产出诊断。"""
        errors: list = []
        macro_defs, func_macros, _, _, _, clean_source = scan_directives(
            source, self._rules_dir, predefined=predefined, undefine=undefine
        )
        if macro_defs:
            lex_source, _, _ = expand_tokens(
                clean_source, macro_defs, prefix=self._macro_prefix,
                func_macros=func_macros,
            )
        elif clean_source != source:
            lex_source = clean_source
        else:
            lex_source = source

        try:
            tokens = self.lexer.tokenize(lex_source)
        except Exception as exc:
            # 通用防御：lexer 无法处理输入（不支持的字符/行尾风格/BOM 等）时
            # 转诊断而非崩溃冒泡——否则调用方（CLI/编辑器集成）直接异常。
            # 不硬编码具体格式（CRLF/BOM 等由 lexer 侧支持），此处只对
            # "lexer 异常"这一通用情况做响应；lexer 修复后输入自然正常解析。
            return [
                LintDiagnostic(
                    range=(Position(0, 0), Position(0, 0)),
                    message=f"lexer error: {exc}",
                    severity=1,
                    code="lexer-error",
                )
            ]
        if not tokens:
            return errors

        # match_atom 位置级 memo 按 token 流隔离：scan 可能被复用（同一
        # scanner 实例扫多文件），新 token 流必须清空，避免跨文件位置串命中。
        self._matcher.reset_atom_memo()

        registry = CheckerRegistry()

        # ── P1: 块边界配对 ──────────────────────
        if self.enable_phase1:
            registry.add(
                BoundaryChecker(
                    0,
                    len(tokens),
                    self._block_openers,
                    self._block_closers,
                    self._block_pairs,
                    opener_prev_exclude=_derive_opener_prev_excludes(self._tree),
                )
            )

        # ── P0: 非法 token 检查 ─────────────────
        if self.enable_phase0:
            registry.add(MacroTokenChecker(0, len(tokens)))
            # 宏/指令卫生（MH 族）：扫**原始源码**（指令行已从 token 流剥离）
            if _macro_hygiene_cfg.get("enabled", True):
                prefix, _directives = _load_config()
                registry.add(
                    MacroHygieneChecker(source, prefix, _macro_hygiene_cfg)
                )

        # ── P2: 语句发现 + 扁平检查 ─────────────
        # discovery 产出多层级树（children 嵌套）；深度优先遍历把每个节点
        # 注册为独立 StatementChecker——父节点按 production 匹配（@Stmt 由
        # matcher 用 end_case 扁平跳过），子节点独立检查自身区间，扁平验证。
        if self.enable_phase2:
            def register(node) -> None:
                registry.add(
                    StatementChecker(
                        node.rule,
                        node.start,
                        node.end,
                        self._matcher,
                    )
                )
                for child in node.children:
                    register(child)

            for node in self._discovery.discover(tokens):
                register(node)

        # 未识别语句诊断（发现阶段记录）与各 Checker 诊断合并输出。
        errors = self._discovery.unrecognized_diagnostics()
        errors += registry.validate_all(tokens)
        return errors
