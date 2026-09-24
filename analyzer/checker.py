"""checker.py — 工程检查门面（ProjectChecker，组合根）。

定位：`tpc check` 的执行入口。**组合**结构提取的各阶段协作者
（`analyzer/structure.py`，协议见语言包 `[structure] protocol`）建立跨文件索引，
再对每个文件跑语义分析（插件 postpass 做联动检查），汇总**分阶段**错误：

    stage=syntax   — linter 产出（token 级语法错误，阶段 1）
    stage=semantic — analyzer 插件产出（parse 成功后符号级 + 跨文件联动检查）

本文件只做**检查编排与诊断汇总**：结构提取的六个协作者（见 structure.py）、
会话上下文 `StructureCtx`、语言包 `[structure]` 协议声明点全在那里；门面把它们
装配起来并驱动阶段顺序（prepare → discover → 信号图 → analyze → collect）。
共享组件装载在 `shared_components.py`，诊断形状序列化在 `diag_serialize.py`。
Doc: analyzer/semantic_checks.md（跨文件语义检查）
"""

import os

from core.define import GrammarRulesRegister, DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS

from analyzer.structure import (
    ConnectionElaborator,
    FilePipeline,
    FileResult,
    GenerateEvaluator,
    ModuleExtractor,
    ModuleIndexer,
    SignalGraphBuilder,
    StructureCtx,
)
from analyzer.shared_components import SharedComponents
from analyzer.diag_serialize import semantic_diag, syntax_diag
from analyzer.elaboration import (
    ROLE_UNIT_CONSTANTS,
    Elaborator,
    ElaborationService,
    StructureAtomSource,
    load_elaborator_spec,
)


class ProjectChecker:
    """跨文件语义检查引擎。

    组合根：构造 `StructureCtx`（会话上下文）与六个阶段协作者，`check()` 只做
    阶段编排与诊断汇总（结构提取细节全在 `analyzer/structure.py` 的协作者里，
    共享组件装载在 `analyzer/shared_components.py`）。

    Usage:
        checker = ProjectChecker()
        report = checker.check("rtl/top.sv")
    """

    def __init__(
        self,
        rules_dir: str = DEFAULT_RULES_DIR,
        ext_dirs: list[str] | None = DEFAULT_EXT_DIRS,
        include_dirs: list[str] | None = None,
        register: "GrammarRulesRegister | None" = None,
        expand_macros: bool = True,
        enabled_rules: list[str] | None = None,
    ):
        # 会话上下文（环境开关 + 索引 + 结构协议）：状态与协议读取的单一
        # 归属点，各阶段协作者共享同一实例（原先靠"同一个 self"隐式共享）。
        self._ctx = StructureCtx(
            rules_dir=rules_dir,
            ext_dirs=list(ext_dirs or []),
            include_dirs=[os.path.abspath(d) for d in (include_dirs or [])],
            # 宏展开（真实工程含 `ifdef/`define；无宏文件 scan_directives 空表
            # 零影响）。默认开——check 语义对齐 run_pipeline（展开后分析）。
            expand_macros=expand_macros,
            ensure_shared=self._ensure_shared,
        )
        # 显式规则启用集（None = 语言包 default + 用户配置；评测/测试用
        # 注入——如 check_accuracy 的 focus 规则，含默认关闭的 NC 族）。
        self._enabled_rules = enabled_rules
        # 独立规则实例：测试跨语言（c4 等）时传入，避免污染全局单例
        # （模式同 tests/languages/c4/test_c4_linter.py 的 fixture 注释）。
        self._register = register
        # elaboration 层 3（ADR-0008）：全工程信号图（check() 时构建）
        self._signal_graph: dict = {}
        # 精化（ADR-0019）：能力面在 _prepare_run 装载语言包后建（未声明 → 降级）；
        # 产物容器随每次运行重置，注入 analyzer._external_extra 供插件消费。
        self._elaborator = Elaborator(None)
        self._elab_extra: dict = {}
        # 各阶段协作者按依赖链接线：门面**只持有会话上下文 + 两个阶段入口**
        # （发现 / 信号图），中间协作者（连接展开 / 提取 / 单文件流水线 /
        # 条件求值）作为构造链局部量注入下游——DAG 只在构造处显式，之后不必
        # 经门面中转（原先"一个 self 上的 49 个方法"正因缺这层表达）。
        gen = GenerateEvaluator(self._ctx)
        conn = ConnectionElaborator(self._ctx)
        extract = ModuleExtractor(self._ctx)
        # 单文件流水线组合提取器 + 连接展开器（阶段顺序在它内部）
        pipeline = FilePipeline(self._ctx, extract, conn)
        # 递归发现组合单文件流水线
        self._indexer = ModuleIndexer(self._ctx, pipeline)
        # 层 3 信号图组合连接展开器 + generate 求值器
        self._graph = SignalGraphBuilder(self._ctx, conn, gen)
        # 结构协议在 _ensure_shared（load_all）之后才就绪——__init__ 不推入，
        # check() 起始的 _ctx.refresh() 负责（缺失 = 无跨文件检查）。

    # ── 共享组件 ──

    def _ensure_shared(self) -> dict:
        """按 rules_dir 缓存的共享组件（装载细节见 analyzer/shared_components.py）。"""
        return SharedComponents.get(
            self._ctx.rules_dir, self._ctx.ext_dirs, self._register
        )

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

        四阶段各走一个方法：`_prepare_run`（归一化 + 重置本次运行状态）→
        `_discover_all`（递归发现 + parse）→ 层 3 信号图 → `_analyze_all`
        （postpass）→ `_collect_files`（两阶段诊断汇总）。
        """
        entries = self._prepare_run(entry_path)

        # 1) 递归发现 + parse（模块索引逐步建立；多入口共享 seen，
        #    重复入口不会重复 parse）
        self._discover_all(entries)

        # 1a) 精化（ADR-0019）：按语言包项列表建产物容器（文件 / 单元作用域）。
        #     须在信号图之前——层 3 的 generate 活性判定要用单元常量绑定。
        self._elaborate()

        # 1b) elaboration 层 3（ADR-0008）：全工程信号驱动/负载图 + 层次
        self._signal_graph = self._graph.build()

        # 2) 每个文件跑语义分析（postpass 拿到完整 module_index）
        self._analyze_all()

        # 3) 汇总两阶段诊断
        files, any_error = self._collect_files()
        return {
            "files": files,
            "modules": {n: i.file for n, i in self._ctx.module_index.items()},
            "exit_code": 1 if any_error else 0,
        }

    def _prepare_run(self, entry_path: str | list[str]) -> list[str]:
        """入口归一化为绝对路径，并重置本次运行的索引与缓存。

        多入口共享同一次运行的状态（memo / module_index / 层 3 穿透缓存），
        否则跨入口的单元定义互不可见。
        """
        raw = [entry_path] if isinstance(entry_path, str) else list(entry_path)
        entries = [os.path.abspath(p) for p in raw]
        # memo / module_index / 派生缓存成对失效（缓存键由 memo 派生）
        self._ctx.invalidate()
        self._ensure_shared()
        self._ctx.refresh()
        # 精化能力面（ADR-0019）：须在语言包装载后解析（未声明 → 降级为 None）
        self._elaborator = Elaborator(load_elaborator_spec(self._ctx.rules_dir))
        self._elab_extra = {}
        return entries

    def _discover_all(self, entries: list[str]) -> None:
        """递归发现 + parse 全部入口（多入口共享 seen，重复入口不重复 parse）。"""
        seen: set[str] = set()
        for entry in entries:
            self._indexer.discover(entry, seen)

    def _analyze_all(self) -> None:
        """对已发现文件跑语义分析（postpass 需要完整 module_index）。"""
        for fr in self._ctx.memo.values():
            self._analyze(fr)

    def _collect_files(self) -> tuple[list, bool]:
        """汇总两阶段诊断 → (files 列表, 是否存在阻断级诊断)。

        阻断判定：语法侧 `blocking` 诊断、语义侧 `error` 级诊断任一出现即
        退出码 1（与 check 返回的 exit_code 对应）。
        """
        files = []
        any_error = False
        for path, fr in self._ctx.memo.items():
            if any(d.blocking for d in fr.lint_diags):
                any_error = True  # 语法错误（stage=syntax，阻断类）→ exit 1
            semantic = []
            if fr.analyzer is not None:
                for d in fr.analyzer.diagnostics:
                    semantic.append(semantic_diag(fr, d))
                    if d.level == "error":
                        any_error = True
            files.append(
                {
                    "path": path,
                    "parse_ok": fr.parse_ok,
                    "parse_error": fr.parse_error,
                    "syntax": [syntax_diag(fr, d) for d in fr.lint_diags],
                    "semantic": semantic,
                }
            )
        return files, any_error

    def _elaborate(self) -> None:
        """跑语言包精化项列表（ADR-0019）：建产物容器 + 取引擎角色位产物。

        - **容器**：`self._elab_extra[CTX_ELABORATION]`（条目名与值形状由插件定）；
          未声明能力的语言包 → 不产生该键（降级，与旧行为一致）。
        - **角色位**：引擎自己要用的产物**不按插件条目名**寻址，按引擎角色位问
          （`ROLE_UNIT_CONSTANTS` → 单元常量绑定，过渡期供 generate 条件求值）。
        """
        source = StructureAtomSource(self._ctx)
        service = ElaborationService(self._ctx.render_subtree)
        result = self._elaborator.run(source, self._elab_extra, service)
        role_key = self._elaborator.role_key(ROLE_UNIT_CONSTANTS)
        if role_key is not None:
            self._ctx.unit_constants = dict(result.products.get(role_key, {}))

    def _analyze(self, fr: FileResult) -> None:
        if fr.ast is None:
            return
        from analyzer import AnalysisTraversal

        shared = self._ensure_shared()
        analyzer = AnalysisTraversal(shared["rules"], rules_dir=self._ctx.rules_dir)
        # 显式规则启用集（默认关闭的规则——如 NC 族——测试/评测注入）
        if self._enabled_rules is not None:
            analyzer._checks_enabled = list(self._enabled_rules)
        # 跨文件上下文注入（analyze() 重建 context 后合并进 extra）
        analyzer._external_extra["module_index"] = self._ctx.module_index
        analyzer._external_extra["inst_sites"] = fr.inst_sites
        # elaboration 层 2（ADR-0008）：本文件实例化点端口连接展开
        analyzer._external_extra["connections"] = fr.connections
        # elaboration 层 3（ADR-0008）：全工程信号驱动/负载图
        analyzer._external_extra["signal_graph"] = self._signal_graph
        # 端口方向值集（插件规则消费：未连接端口/驱动负载判定；语言包声明）
        analyzer._external_extra["output_dirs"] = sorted(self._ctx.dirs("output_dirs"))
        analyzer._external_extra["input_dirs"] = sorted(self._ctx.dirs("input_dirs"))
        analyzer._external_extra["inout_dirs"] = sorted(self._ctx.dirs("inout_dirs"))
        # 精化产物容器（ADR-0019）：条目名与值形状由插件定，引擎只保证容器；
        # 未声明精化能力 → 无此键（插件侧按 .get 缺省处理）。
        analyzer._external_extra.update(self._elab_extra)
        analyzer.analyze(fr.ast)
        fr.analyzer = analyzer


