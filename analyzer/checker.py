"""checker.py — 工程检查门面（ProjectChecker）。

定位：`tpc check` 的执行入口。继承**结构提取底座**（`analyzer/structure.py`，
协议见语言包 `[structure] protocol`）建立跨文件索引，再对每个文件跑语义分析
（插件 postpass 做联动检查），汇总**分阶段**错误：

    stage=syntax   — linter 产出（token 级语法错误，阶段 1）
    stage=semantic — analyzer 插件产出（parse 成功后符号级 + 跨文件联动检查）

本文件只做**检查编排**：结构提取在 `analyzer/structure.py`（`_StructureBase`），
那里也是语言包 `[structure]` 协议的声明点——门面不再声明结构协议。
Doc: analyzer/semantic_checks.md（跨文件语义检查）
"""

import os

from core.define import GrammarRulesRegister, DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS

from analyzer.structure import (
    FileResult,
    ModuleInfo,
    _StructureBase,
)

class ProjectChecker(_StructureBase):
    """跨文件语义检查引擎。

    Usage:
        checker = ProjectChecker()
        report = checker.check("rtl/top.sv")
    """

    # 按 rules_dir 缓存的共享组件（与 pipeline 的 _PIPELINE_SHARED 分离，
    # check 是独立入口，不耦合 pipeline 内部状态）
    _SHARED: dict = {}


    def __init__(
        self,
        rules_dir: str = DEFAULT_RULES_DIR,
        ext_dirs: list[str] | None = DEFAULT_EXT_DIRS,
        include_dirs: list[str] | None = None,
        register: "GrammarRulesRegister | None" = None,
        expand_macros: bool = True,
        enabled_rules: list[str] | None = None,
    ):
        self._rules_dir = rules_dir
        self._ext_dirs = ext_dirs or []
        self._include_dirs = [os.path.abspath(d) for d in (include_dirs or [])]
        # 宏展开（真实工程含 `ifdef/`define；无宏文件 scan_directives 空表
        # 零影响）。默认开——check 语义对齐 run_pipeline（展开后分析）。
        self._expand_macros = expand_macros
        # 显式规则启用集（None = 语言包 default + 用户配置；评测/测试用
        # 注入——如 check_accuracy 的 focus 规则，含默认关闭的 NC 族）。
        self._enabled_rules = enabled_rules
        # 独立规则实例：测试跨语言（c4 等）时传入，避免污染全局单例
        # （模式同 tests/languages/c4/test_c4_linter.py 的 fixture 注释）。
        self._register = register
        self._memo: dict[str, FileResult] = {}
        self._module_index: dict[str, ModuleInfo] = {}
        # elaboration 层 3（ADR-0008）：全工程信号图（check() 时构建）
        self._signal_graph: dict = {}
        # 语言包结构协议（全部语言知识来自配置；缺失 = 无跨文件检查）。
        # 注意：配置在 _ensure_shared（load_all）之后才推入 _structure_cfg，
        # 因此 __init__ 只置空，check() 里 _ensure_shared 后刷新。
        self._struct: dict = {}
        self._fields: dict = {}

    # ── 共享组件 ──

    def _ensure_shared(self) -> dict:
        key = self._rules_dir
        if key in ProjectChecker._SHARED:
            return ProjectChecker._SHARED[key]
        from core.config_registry import ConfigRegistry
        from parser import setup_grammar
        from parser.rule_selector import RuleSelector
        from lexer import Lexer
        from linter.scanner import LinterScanner
        from renderer import Renderer

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rules_dir = (
            self._rules_dir
            if os.path.isabs(self._rules_dir)
            else os.path.join(root, self._rules_dir)
        )
        plugins_dir = os.path.join(rules_dir, "plugins")
        # 配置加载 + 插件组件发现（postpass/原语注册依赖此步骤；
        # 与 pipeline 一致——pipeline 在模块导入时顶层调用）
        ConfigRegistry.load_all(
            rules_dir, ext_dirs=self._ext_dirs, plugins_dir=plugins_dir
        )
        from core.plugin_loader import load_all_components

        load_all_components()

        rules = setup_grammar(
            rules_dir,
            self._register or GrammarRulesRegister.get_default(),
            ext_dirs=self._ext_dirs,
        )
        stmt_names = [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        shared = {
            "rules": rules,
            "rule_selector": RuleSelector(rules, stmt_names),
            "lexer": Lexer(rules_dir=rules_dir, ext_dirs=self._ext_dirs),
            "linter": LinterScanner(
                rules_dir=rules_dir,
                ext_dirs=self._ext_dirs,
                # 独立 register 必须透传：LinterScanner 内部 setup_grammar
                # 默认用全局单例 get_default()，跨语言（c4）检查会把 c4 规则
                # 灌进单例且无法靠 ConfigRegistry 恢复（test_c4_linter 同款坑）。
                register=self._register or GrammarRulesRegister.get_default(),
            ),
            "renderer": Renderer(rules_dir=rules_dir),
        }
        ProjectChecker._SHARED[key] = shared
        return shared

    # ── 入口 ──

    def check(self, entry_path: str | list[str]) -> dict:
        """检查入口文件（可多入口）及其递归可达的定义文件。

        Args:
            entry_path: 入口文件路径；或**多入口列表**（同一工程的多个顶层
                文件）。多入口共享 module_index 与层 2/3 图——单元定义的
                发现范围是「入口所在目录 + include 目录」（`_find_module_file`
                先找同名文件、再在该目录内做关键字文本扫描兜底），所以
                **跨目录**的工程或分布在多目录的顶层文件必须一次 check；
                分别 check 时各自的索引互不可见，对方的单元会报成未知单元。

        Returns:
            dict: {
                "files": [ {path, parse_ok, parse_error, syntax: [..], semantic: [..]}, .. ],
                "modules": {name: file},
                "exit_code": 0 | 1,
            }
        """
        raw = [entry_path] if isinstance(entry_path, str) else list(entry_path)
        entries = [os.path.abspath(p) for p in raw]
        self._memo.clear()
        self._module_index.clear()
        self._fr_by_module_cache = None  # P2.7 层 3：穿透查模块文件缓存随 check 重建
        self._ensure_shared()
        self._refresh_structure()

        # 1) 递归发现 + parse（模块索引逐步建立；多入口共享 seen，
        #    重复入口不会重复 parse）
        seen: set[str] = set()
        for entry in entries:
            self._discover(entry, seen)

        # 1b) elaboration 层 3（ADR-0008）：全工程信号驱动/负载图 + 层次
        self._signal_graph = self._build_signal_graph()

        # 2) 每个文件跑语义分析（postpass 拿到完整 module_index）
        for fr in self._memo.values():
            self._analyze(fr)

        # 3) 汇总两阶段诊断
        files = []
        any_error = False
        for path, fr in self._memo.items():
            if any(d.blocking for d in fr.lint_diags):
                any_error = True  # 语法错误（stage=syntax，阻断类）→ exit 1
            semantic = []
            if fr.analyzer is not None:
                for d in fr.analyzer.diagnostics:
                    semantic.append(self._semantic_diag(fr, d))
                    if d.level == "error":
                        any_error = True
            files.append(
                {
                    "path": path,
                    "parse_ok": fr.parse_ok,
                    "parse_error": fr.parse_error,
                    "syntax": [self._syntax_diag(fr, d) for d in fr.lint_diags],
                    "semantic": semantic,
                }
            )
        return {
            "files": files,
            "modules": {n: i.file for n, i in self._module_index.items()},
            "exit_code": 1 if any_error else 0,
        }

    def _analyze(self, fr: FileResult) -> None:
        if fr.ast is None:
            return
        from analyzer import AnalysisTraversal

        shared = self._ensure_shared()
        analyzer = AnalysisTraversal(shared["rules"], rules_dir=self._rules_dir)
        # 显式规则启用集（默认关闭的规则——如 NC 族——测试/评测注入）
        if self._enabled_rules is not None:
            analyzer._checks_enabled = list(self._enabled_rules)
        # 跨文件上下文注入（analyze() 重建 context 后合并进 extra）
        analyzer._external_extra["module_index"] = self._module_index
        analyzer._external_extra["inst_sites"] = fr.inst_sites
        # elaboration 层 2（ADR-0008）：本文件实例化点端口连接展开
        analyzer._external_extra["connections"] = fr.connections
        # elaboration 层 3（ADR-0008）：全工程信号驱动/负载图
        analyzer._external_extra["signal_graph"] = self._signal_graph
        # 端口方向值集（插件规则消费：未连接端口/驱动负载判定；语言包声明）
        analyzer._external_extra["output_dirs"] = sorted(self._dirs("output_dirs"))
        analyzer._external_extra["input_dirs"] = sorted(self._dirs("input_dirs"))
        analyzer._external_extra["inout_dirs"] = sorted(self._dirs("inout_dirs"))
        analyzer.analyze(fr.ast)
        fr.analyzer = analyzer

    # ── 诊断序列化（LSP 兼容 + stage 字段）──

    @staticmethod
    def _map_diag_line(fr: FileResult, line0: int | None) -> int | None:
        """展开坐标（0-based）→ 原始源坐标（0-based）；无表/不可映射时原样保留。

        行表来自 ``_expand_source`` 的两级复合（展开→clean→原始）；None/越界
        一律回退展开行号——映射可能不准时宁保留诚实偏移，不给错误的源行号。
        """
        lm = fr.line_map
        if not lm or line0 is None or not (0 <= line0 < len(lm)):
            return line0
        src = lm[line0]
        return src - 1 if src is not None else line0

    @staticmethod
    def _macro_of_line(fr: FileResult, line0: int | None) -> str:
        """诊断行（展开坐标 0-based）落在某宏展开区间 → 宏名；否则空串。

        区间表由 `_expand_source` 在语义展开时换算（展开行区间 + 宏调用
        原始行）；未展开/顿路径无表 → 恒空。归因是**行级**的（宏体多行
        则其内诊断均归该宏）。
        """
        if line0 is None or not fr.macro_regions:
            return ""
        line1 = line0 + 1
        for r in fr.macro_regions:
            if r["line_start"] <= line1 <= r["line_end"]:
                return str(r["name"])
        return ""

    @staticmethod
    def _syntax_diag(fr: FileResult, d) -> dict:
        span = getattr(d, "range", None)
        if span:
            rng = {
                "start": {
                    "line": ProjectChecker._map_diag_line(fr, span[0].line),
                    "character": span[0].character,
                },
                "end": {
                    "line": ProjectChecker._map_diag_line(fr, span[1].line),
                    "character": span[1].character,
                },
            }
        else:
            rng = None
        out = {
            "stage": "syntax",
            "file": fr.path,
            "severity": getattr(d, "severity", 1),
            "code": getattr(d, "code", "parse-error"),
            "message": d.message,
            "range": rng,
        }
        macro = ProjectChecker._macro_of_line(fr, span[0].line) if span else ""
        if macro:
            out["macro"] = macro
        return out

    @staticmethod
    def _semantic_diag(fr: FileResult, d) -> dict:
        node = d.node
        line = getattr(node, "_pos_line", None)
        col = getattr(node, "_pos_col", None)
        sev = {"error": 1, "warning": 2, "info": 3}.get(d.level, 2)
        # 行号回源：仅对本文件节点用行表（跨文件节点行号属另一文件坐标系）
        same_file = getattr(node, "_file", None) in (None, fr.path)
        if line is not None:
            line0 = (line - 1) if line else 0
            if same_file:
                line0 = ProjectChecker._map_diag_line(fr, line0)
            rng = {
                "start": {"line": line0, "character": col or 0},
                "end": {"line": line0, "character": (col or 0) + 1},
            }
        else:
            rng = None
        out = {
            "stage": "semantic",
            "file": fr.path,
            "severity": sev,
            "code": d.code or "semantic",
            "message": d.message,
            "level": d.level,
            "range": rng,
        }
        if line is not None and same_file:
            macro = ProjectChecker._macro_of_line(fr, (line - 1) if line else 0)
            if macro:
                out["macro"] = macro
        related = []
        for msg, rnode in d.related:
            rl = getattr(rnode, "_pos_line", None)
            rc = getattr(rnode, "_pos_col", None)
            if rl is not None and getattr(rnode, "_file", None) in (None, fr.path):
                mapped = ProjectChecker._map_diag_line(fr, rl - 1)
                if mapped is not None:
                    rl = mapped + 1
            related.append(
                {
                    "message": msg,
                    "file": getattr(rnode, "_file", None) or fr.path,
                    "line": rl,
                    "column": rc,
                }
            )
        if related:
            out["related"] = related
        return out
