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
"""

import os

from core.define import GrammarRule, Token
from core.config_registry import ConfigRegistry, declare_cfg
from core.token_protocol import (
    BRACKET_L_PREFIX,
    BRACKET_R_PREFIX,
    bracket_left,
    bracket_right,
)
from lexer import Lexer, load_pre_scan_config
from parser import setup_grammar
from preprocessor._expand import scan_directives, expand_tokens, _load_config

from . import LintDiagnostic, Position, token_pos
from .grammar_slicer import build_slice_tree
from .discovery import Discovery
from .checker import CheckerRegistry
from .checkers.boundary import BoundaryChecker
from .checkers.macro_hygiene import MacroHygieneChecker
from .checkers.macro_token import MacroTokenChecker
from .macro_syntax import macro_syntax_diagnostics
from .checkers.statement import StatementChecker
from .checkers.expression import ExpressionChecker
from .checkers.style import StyleChecker

# M2 窄档可摘的**结构类**诊断码（判据见 `LinterScanner._apply_narrow_downgrade`）：
# 只这两类"语句/未识别"结构码；`phase1-boundary`（块配对）、`lexer-error`、宏卫生与
# ST* 样式码一律保留 ⇒ 真错不被摘（R6/R7 反例锁定）。
_DOWNGRADABLE_CODES = frozenset({"phase-statement", "phase-unrecognized"})

# linter.macro_hygiene
#   #sym:config = [macro_hygiene]
#   格式: dict — { enabled, define_directive, undef_directive,
#                  nettype_directive, nettype_restore, continuation }
# 语言包未声明（或 enabled=false）→ MH 检查器不注册（零开销）。
# 关键字缺省 → 对应子检查自行跳过（见 MacroHygieneChecker）。
_macro_hygiene_cfg: dict = declare_cfg(
    "linter.macro_hygiene", {}, __name__, "_macro_hygiene_cfg"
)

# linter.style_check
#   #sym:config = [style_check]
#   格式: dict — { enabled, trailing_whitespace, tab_character, max_line_width }
# 语言包未声明（或 enabled=false）→ ST 检查器不注册（零开销）——
# 与 MH 的区别：ST 子检查以布尔开关驱动（无“关键字缺省即空转”形态），
# 故缺省取 False（未声明的语言包明确不检，而非注册后空转）。
_style_check_cfg: dict = declare_cfg(
    "linter.style_check", {}, __name__, "_style_check_cfg"
)


def _seq_end_tokens(feat: dict, excludes: dict[str, set[str]]) -> set:
    """seq 的末尾 token 集（= 末元素的末尾集）。

    顺带做排除推导：逐位比较"上一元素的末尾集 × 当前元素的起始集"，命中
    (symbol.base.colon, keyword.X) 相邻对即登记 X 的前驱排除 colon。
    """
    ends = {None}
    for item in feat.get("items", []):
        starts = _feature_end_tokens(item, excludes)
        for e in ends:
            for st in starts:
                if st and e == "symbol.base.colon" and st.startswith("keyword."):
                    excludes.setdefault(st, set()).add(e)
        ends = starts
    return ends


def _feature_end_tokens(feat, excludes: dict[str, set[str]]) -> set:
    """返回 feature 可能的末尾 token 集合（call 截断）。"""
    if feat is None:
        return {None}
    typ = feat.get("type")
    if typ == "token":
        return {feat.get("token_type", "")}
    if typ == "call":
        return {None}
    if typ == "seq":
        return _seq_end_tokens(feat, excludes)
    if typ in ("repeat", "optional", "plus"):
        return _feature_end_tokens(feat.get("elem"), excludes) | {None}
    if typ == "choice":
        acc = set()
        for alt in feat.get("alternatives", []):
            acc |= _feature_end_tokens(alt, excludes)
        return acc
    return {None}


def _derive_opener_prev_excludes(tree: dict) -> dict[str, frozenset[str]]:
    """语法推导块 opener 的非起始前驱 token 集（供 BoundaryChecker）。

    production 树中 (symbol.base.colon, keyword.X) 相邻 token 对（X 是块
    opener）→ X 的前驱排除 colon：该位置的 X 是子句终结形态（如 config
    插件的 use 子句 use lib.cell:config），不是块起始。BoundaryChecker
    压栈时命中排除即不压——避免 :config 被当 config 块 opener 造成
    unclosed 误报。推导是通用结构（不硬编码关键字名），语言知识留 TOML。
    """
    excludes: dict[str, set[str]] = {}
    for info in tree.values():
        if not isinstance(info, dict):
            continue
        for prod in info.get("prods", []):
            _feature_end_tokens(prod, excludes)
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

        self._macro_prefix, _ = _load_config(rules_dir)

        # ── 动态收集 block 起止符 ─────────────────
        _openers, _closers, self._block_pairs, _ = self._build_block_delimiters(rules)

        # 括号配对单一来源：lexer.bracket_map（规则侧 bracket bound 已移除，
        # 括号由 [bracket].pairs 统一定义）。括号同时加入 block 起止符集，
        # 使 BoundaryChecker 的栈式配对与 matcher 的括号上下文检查正常生效。
        _raw_pairs = ConfigRegistry._loaded.get("lexer.bracket_map", {}).get("pairs", [])
        _bracket_pairs: dict[str, set[str]] = {}
        # 深度守卫（资格判定 ③ 的**作用域**面）用：`{`/`}` 的 token 型。按**字符**
        # 定位配对（同 `core/utils.square_bracket_types` 判据：字符是词法数据，
        # 不依赖配对命名）。语言包未声明该配对 ⇒ None，守卫空转（不误判）。
        self._depth_pair: tuple[str, str] | None = None
        for _open_char, _close_char, _name in _raw_pairs:
            _lt = bracket_left(_name)
            _rt = bracket_right(_name)
            _openers.add(_lt)
            _closers.add(_rt)
            _bracket_pairs.setdefault(_rt, set()).add(_lt)
            if _open_char == "{":
                self._depth_pair = (_lt, _rt)

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
        # 内部 warning 旁路（用户不可见；scan() 每次按次重置后填充）
        self._internal_warnings: list[dict] = []

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
        """扫源文本产出诊断。

        ⚠ **返回值只含用户诊断**。另有一路**内部 warning 旁路**（候选未收敛位点，
        用户不可见、不进 `--json`/exit code/落盘）：每次 scan 开头按次重置，
        由 `internal_warnings()` 取用（消费链见该方法 docstring）。
        """
        self._internal_warnings = []
        errors: list = []
        macro_defs, func_macros, _, _, _, clean_source, _ = scan_directives(
            source, self._rules_dir, predefined=predefined, undefine=undefine
        )
        if macro_defs:
            # 宏体文本铺进流（与 pipeline 的 lint 输入、analyzer 的
            # `_expand_source` 同一条路）：语法是否成立由语法自己判。token 替身形态
            # 会让值体宏退化成“相邻原子”——如 `input NAME `M`（body `= 1'b1`）变
            # `input NAME tpc_marker_N` 两个相邻 id → ice40 语料实测 34 条
            # `phase-statement` 误报（曾经靠 `[macro_shape] suffix_leads` 形态特判
            # 绕开，形态特判与声明均已删）。
            lex_source, _, _, _ = expand_tokens(
                clean_source,
                macro_defs,
                rules_dir=self._rules_dir,
                prefix=self._macro_prefix,
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

        # ── 符号提示（P2b/P3b）：把 `pre_scan` 名（含 kind/声明位置）喂给消歧表 ──
        # 语言知识在包声明（`[lexer] pre_scan`：`[pre_scan.decl.*].type_name` /
        # `trial_as`），引擎只做"括号内类型名形态 + 换 token 型重跑试解析"的
        # **中性能力**（判据见 `lookahead._type_name_hits` / `_substitution_trial`）。
        # 预扫描不精确（`lexer/pre_scan.py:1-5` 自述）⇒ 只作提示、不作语法判据。
        pre_cfg = load_pre_scan_config(self._rules_dir)
        # raw 互斥（P3c/M2）：包侧 `[pre_scan] raw_exclude_rules`（声明类规则名）。
        # 走与 `lexer.bracket_map` 同一条既有读取面（`ConfigRegistry._loaded` 的合并表）
        # ——`load_pre_scan_config` 只搬运它认识的键，该键不经引擎编译，引擎只做集合交。
        self._discovery.set_symbol_hints(
            self._pre_scan_symbols(lex_source, pre_cfg),
            self._all_bracket_openers,
            self._all_bracket_closers,
            type_name_kinds=pre_cfg.get("type_name_kinds", frozenset()),
            trial_as=pre_cfg.get("trial_as", {}),
            depth_pair=self._depth_pair,
            raw_exclude_rules=self._raw_exclude_rules(),
        )

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
                prefix, _ = _load_config(self._rules_dir)
                registry.add(
                    MacroHygieneChecker(source, prefix, _macro_hygiene_cfg)
                )
            # 排版卫生（ST 族）：扫**原始源码行**（排版事实在字符层，
            # token 化不提供尾随空白/行长信息）
            if _style_check_cfg.get("enabled", False):
                registry.add(StyleChecker(source, _style_check_cfg))

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

        # 内部 warning 旁路快照（用户不可见）：候选未收敛位点，供 pipeline → P3 消费。
        self._internal_warnings = self._discovery.internal_warnings()

        # 未识别语句诊断（发现阶段记录）与各 Checker 诊断合并输出。
        # 宏定义的**形式化语法**约束在此层（AST 前）：指令行已被扫指令消费、不进 lint
        # 流，故必须对**原始源码**检查；语言包未声明 `check_syntax` ⇒ 空（语言无关）。
        errors = macro_syntax_diagnostics(source, self._rules_dir)
        errors += self._discovery.unrecognized_diagnostics()
        errors += registry.validate_all(tokens)
        # M2 窄档摘诊断（与 parser 侧 raw 承载**同批**）：只摘 `eligible` 位点 region
        # 内的两类**结构类**码；其余码（phase1-boundary / lexer-error / 宏卫生 / ST*）
        # 一律保留 ⇒ 真错不被静默。两批缺一不可（只摘不 raw ⇒ 更差的含糊截断报错）。
        return self._apply_narrow_downgrade(errors, tokens)

    def _apply_narrow_downgrade(
        self, errors: list[LintDiagnostic], tokens: list[Token]
    ) -> list[LintDiagnostic]:
        """窄档摘诊断：`eligible` 位点 region 内的**结构类**诊断摘成内部 warning。

        三条同时成立才摘（缺一不摘 ⇒ 保持 blocking）：
          ① 位点条目 `eligible=True`（资格判定，见 `lookahead._record_convergence`；
             含 raw 互斥 ④：关键字触发的声明类候选句一律不 eligible）；
          ② 诊断码 ∈ `_DOWNGRADABLE_CODES`（结构类；样式/宏卫生/边界/lexer 一律不动）；
          ③ 诊断起点落在该位点的**句子区间** `region` 内（token 下标；`region` 由
             `lookahead._find_boundary` → `_stmt_ends` 推导——与 parser 侧区间等式同源）。
        被摘的诊断不返回 ⇒ 不再阻断管线；位点由内部 warning 旁路承载（`downgraded`/
        `suppressed` 回填），pipeline 同批把位点交给 parser 走 raw 暂缓建树。安全网 =
        P4 的 analyze 精确符号面校验（校验不过 ⇒ 报错，不静默）。
        """
        sites = [w for w in self._internal_warnings if w.get("eligible") and w.get("region")]
        if not sites:
            return errors
        kept: list[LintDiagnostic] = []
        for diag in errors:
            hit = None
            if diag.code in _DOWNGRADABLE_CODES:
                start_pos = diag.range[0]
                for w in sites:
                    start, end = int(w["region"][0]), int(w["region"][1])
                    # 位置比对统一走 `token_pos`（token 1-based → LSP 0-based）。
                    if any(
                        token_pos(t) == start_pos
                        for t in tokens[start : min(end + 1, len(tokens))]
                    ):
                        hit = w
                        break
            if hit is None:
                kept.append(diag)
            else:
                hit["downgraded"] = True
                hit["suppressed"] = int(hit.get("suppressed", 0)) + 1
        return kept

    def _raw_exclude_rules(self) -> frozenset[str]:
        """包侧 `[pre_scan] raw_exclude_rules`（声明类规则名；raw 互斥用）。

        读法与 `lexer.bracket_map` 同一既有面（`ConfigRegistry._loaded` 的合并表）：
        `load_pre_scan_config` 只搬运引擎认识的键，该键由语言包声明、引擎只做集合交
        （语言知识不进代码）。未声明 ⇒ 空集（互斥不生效，行为与声明前一致）。
        """
        table = ConfigRegistry._loaded.get("lexer.pre_scan", {}) or {}
        declared = table.get("raw_exclude_rules", [])
        if not isinstance(declared, list):
            return frozenset()
        return frozenset(str(x) for x in declared)

    def _pre_scan_symbols(self, source: str, config: dict | None = None) -> dict[str, dict]:
        """本轮 `pre_scan` 名字（含 kind + 声明位置；**只作提示**）。

        走**并行读取面** `pre_scan_with_lines`（引擎 `[lexer] pre_scan`；语言知识在
        包声明，引擎不解释 kind 语义、不硬编码任何语言名）；未声明 `[lexer]
        pre_scan` 的语言包 → 空表（零影响）。配置错误按 fail-fast 冒泡（不静默降级）。

        消费点：未收敛位点的 ② 类型名 kind 过滤与 ③ 声明顺序判定
        （见 `lookahead._type_name_hits` / `_record_convergence`），**不参与**诊断计算。
        既有 `pre_scan()` 签名/行为不变（并行面，旧调用方零影响）。
        """
        from lexer import load_pre_scan_config
        from lexer.pre_scan import pre_scan_with_lines

        cfg = config if config is not None else load_pre_scan_config(self._rules_dir)
        return pre_scan_with_lines(source, cfg)

    def internal_warnings(self) -> list[dict]:
        """本次 `scan()` 的内部 warning（拷贝；**用户不可见**）。

        消费链：`LookaheadTable`（Level 2 收敛判定，按次重置）→ `Discovery` →
        `LinterScanner.scan()` → `pipeline._stage_lint` → `_PipelineContext.
        internal_warnings`（后续"歧义位点 raw 暂缓建树"按行/列消费）。

        与 `scan()` 返回值的边界：本列表**不进** `LintDiagnostic`、不进
        `tpc lint --json` / LSP 输出、不影响 exit code、不落盘——用户可见面
        与本次机制引入前逐字节相同。条目形态见
        `lookahead.LookaheadTable._record_convergence`。
        """
        return list(self._internal_warnings)
