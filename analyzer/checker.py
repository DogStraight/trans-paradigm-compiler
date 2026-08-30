"""checker.py — 跨文件语义检查引擎（ProjectChecker）

定位：`tpc check` 的执行引擎。单文件入口 + 递归发现被实例化模块的定义
文件，建立跨文件模块索引，对每个文件跑语义分析（插件 postpass 做联动
检查），汇总**分阶段**错误：

    stage=syntax   — linter 产出（token 级语法错误，阶段 1）
    stage=semantic — analyzer 插件产出（parse 成功后，符号级 + 跨文件
                     联动检查，阶段 2）

决策（用户拍板 + ADR-0001/0004）：
- 语法有错的文件**跳过语义阶段**（parser 只解析合法输入，不基于残缺
  AST 报语义误报）。
- 递归带 memo（文件级去重）与环防护（模块 A 文件实例化 B、B 文件实例
  化 A 的定义文件时不死循环）。
- 模块定义表从 AST 提取（端口/参数/宽度声明形态），不依赖符号表——
  联动检查只需要"声明形态 vs 实例化点"的比对。

语言无关边界：本模块**不含任何语言语义知识**。结构知识（模块/实例化的
规则名、节点字段、文件扩展名、关键字）全部来自语言包声明的
`[checker] structure` 配置（grammar/<lang>/base/_checker.toml），未声明
该段 = 该语言不支持跨文件结构检查（check 退化为 lint+analyze）。
语义规则（端口/参数存在性、字面量宽度 vs 参数化端口）是
grammar/<lang>/plugins/*/ postpass 的职责。本引擎只提供跨文件上下文，
经 `AnalysisTraversal._external_extra` 注入每个文件的
context.extra：`module_index`（全工程模块表）与 `inst_sites`（本文件
实例化点列表）。
Doc: docs/decisions/0005-cross-file-semantic-check.md（跨文件语义检查 ProjectChecker）
"""

import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.define import Node, GrammarRulesRegister, DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS
from core.config_registry import declare_cfg

if TYPE_CHECKING:
    from analyzer.traversal import AnalysisTraversal

# ── 配置需求（来自语言包 tpc.toml [checker]） ──────────────
# checker.structure: 跨文件结构提取协议——模块/实例化的规则名、节点字段、
# 文件扩展名、关键字全部由语言包声明（grammar/<lang>/base/_checker.toml）。
# 未声明 = 语言包不支持跨文件结构检查（check 退化为 lint+analyze）。
_checker_cfg: dict = declare_cfg("checker.structure", {}, __name__, "_checker_cfg")


# ── 数据模型 ──────────────────────────────────────────────

# 连接表达式是否为"简单信号名"（层 3 建图过滤：常量/拼接/带位选的复杂
# 表达式不入驱动/负载图——信号解析交给上层规则，此处只记简单标识符）。
_SIGNAL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_signal_expr(text: str) -> bool:
    """简单信号名（标识符形态）→ True；常量/拼接/位选/层次引用 → False。"""
    return bool(_SIGNAL_RE.match(text.strip()))


@dataclass
class ModulePort:
    """模块端口声明（声明形态，供实例化联动比对）。"""

    name: str
    direction: str = ""  # input / output / inout（旧风格裸名可空）
    width_expr: str = ""  # 宽度表达式文本（如 "DATA_W-1:0"、"7:0"；无范围空）
    net_type: str = ""  # 数据类型/网络类型（wire/tri/reg/...；协议字段声明）
    decl_node: Node | None = None  # 端口声明节点（related 链定位）


@dataclass
class ModuleParam:
    """模块参数声明。"""

    name: str
    value_expr: str = ""  # 默认值表达式文本（如 "8"、"DATA_W"）


@dataclass
class ModuleInfo:
    """一个模块定义（跨文件索引条目）。"""

    name: str
    file: str
    node: Node  # ModuleDecl 节点（定位）
    ports: dict[str, ModulePort] = field(default_factory=dict)
    params: dict[str, ModuleParam] = field(default_factory=dict)
    # elaboration 层 2/3（ADR-0008）：模块的端口连接展开 + 实例树
    insts: list = field(default_factory=list)  # 模块内实例化点（已展开连接）


@dataclass
class PortConnection:
    """层 2：一个实例化点的端口连接（展开后）。"""

    inst_name: str  # 实例名（如 u1）
    module_name: str  # 被实例化模块名
    inst_node: Node  # ModuleInst 节点（定位）
    file: str
    connects: dict[str, str] = field(default_factory=dict)  # 端口名 → 连接信号名
    ordered: list[str] = field(default_factory=list)  # 位置连接信号（有序）


@dataclass
class FileResult:
    """单文件检查结果（两阶段诊断的承载）。"""

    path: str
    source: str
    lint_diags: list = field(default_factory=list)  # stage=syntax（LintDiagnostic）
    parse_ok: bool = False
    parse_error: str = ""
    ast: Node | None = None
    analyzer: "AnalysisTraversal | None" = None  # stage=semantic 诊断源
    modules: dict[str, ModuleInfo] = field(default_factory=dict)
    inst_sites: list = field(default_factory=list)  # ModuleInst 节点
    connections: list = field(default_factory=list)  # PortConnection（层 2）


# ── 引擎 ─────────────────────────────────────────────────


class ProjectChecker:
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
        # 注意：配置在 _ensure_shared（load_all）之后才推入 _checker_cfg，
        # 因此 __init__ 只置空，check() 里 _ensure_shared 后刷新。
        self._struct: dict = {}
        self._fields: dict = {}

    def _refresh_structure(self) -> None:
        """load_all 后刷新结构协议（_checker_cfg 模块变量被推入真实值）。"""
        self._struct = _checker_cfg or {}
        self._fields = (self._struct.get("fields") or {}) if self._struct else {}

    # ── 结构协议读取（语言知识仅来自 grammar/<lang> TOML）──

    def _rule(self, key: str) -> str:
        """规则名/关键字等标量协议项（如 module_decl_rule）。"""
        return str(self._struct.get(key) or "")

    def _field(self, key: str) -> str:
        """节点字段名协议项（如 module_name / ports）。"""
        return str(self._fields.get(key) or "")

    def _exts(self) -> list[str]:
        exts = self._struct.get("file_exts") or []
        return [str(e) for e in exts] if isinstance(exts, list) else []

    def _dirs(self, key: str) -> set[str]:
        """端口方向值集合（层 3 信号图判定；语言包声明，引擎零语言知识）。"""
        vals = (self._struct.get(key) or []) if self._struct else []
        return {str(v) for v in vals} if isinstance(vals, list) else set()

    def _has_structure(self) -> bool:
        """语言包是否声明了跨文件结构协议（模块/实例化形态）。"""
        return bool(self._struct and self._rule("module_decl_rule"))

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

    def check(self, entry_path: str) -> dict:
        """检查入口文件及其递归可达的模块定义文件。

        Returns:
            dict: {
                "files": [ {path, parse_ok, parse_error, syntax: [..], semantic: [..]}, .. ],
                "modules": {name: file},
                "exit_code": 0 | 1,
            }
        """
        entry = os.path.abspath(entry_path)
        self._memo.clear()
        self._module_index.clear()
        self._ensure_shared()
        self._refresh_structure()

        # 1) 递归发现 + parse（模块索引逐步建立）
        self._discover(entry, set())

        # 1b) elaboration 层 3（ADR-0008）：全工程信号驱动/负载图 + 层次
        self._signal_graph = self._build_signal_graph()

        # 2) 每个文件跑语义分析（postpass 拿到完整 module_index）
        for fr in self._memo.values():
            self._analyze(fr)

        # 3) 汇总两阶段诊断
        files = []
        any_error = False
        for path, fr in self._memo.items():
            if fr.lint_diags:
                any_error = True  # 语法错误（stage=syntax）→ exit 1
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

    # ── 递归发现 ──

    def _discover(self, path: str, seen: set[str]) -> None:
        if path in self._memo or path in seen:
            return
        seen.add(path)
        fr = self._parse_file(path)
        self._memo[path] = fr
        for name, info in fr.modules.items():
            if name not in self._module_index:
                self._module_index[name] = info
        for site in fr.inst_sites:
            mod_name = self._inst_module_name(site)
            if not mod_name or mod_name in self._module_index:
                continue
            def_path = self._find_module_file(mod_name, path)
            if def_path:
                self._discover(def_path, seen)

    def _parse_file(self, path: str) -> FileResult:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        fr = FileResult(path=path, source=source)
        shared = self._ensure_shared()

        # 宏展开（真实工程含 `ifdef/`define；对齐 run_pipeline 语义——
        # scan_directives 提取宏表 + expand_tokens 纯文本展开，lex/lint/
        # parse 全在展开后文本上）。无宏文件空表零影响。
        if self._expand_macros:
            source = self._expand_source(source, path)

        # 阶段 1：语法检查（token 级）。有错 → 语义阶段跳过（用户决策）。
        fr.lint_diags = shared["linter"].scan(source)
        if fr.lint_diags:
            return fr

        # 解析
        from lexer import pre_scan, load_pre_scan_config
        from parser import Parser
        from parser.parser_core import ParseError

        pre_scan_config = load_pre_scan_config(self._rules_dir)
        pre_symbols = pre_scan(source, pre_scan_config)
        parser = Parser(
            rules_dir=self._rules_dir,
            pre_symbols=pre_symbols,
            rules=shared["rules"],
            rule_selector=shared["rule_selector"],
        )
        parser.pre_hints = pre_scan_config.get("hints", {})
        try:
            tokens = shared["lexer"].tokenize(source)
            ast = parser.parse(tokens)
        except ParseError as e:
            fr.parse_error = str(e)
            return fr
        if ast is None or getattr(parser, "_parse_truncated", False):
            fr.parse_error = "parse failed (truncated tokens)"
            return fr

        fr.ast = ast
        fr.modules = self._extract_modules(ast, path)
        fr.inst_sites = self._collect_nodes(ast, self._rule("module_inst_rule"))
        fr.connections = self._elaborate_connections(path, fr.inst_sites)
        # 层 1 补充：模块内实例挂回 ModuleInfo（实例树展开的入口）
        for conn in fr.connections:
            mod = fr.modules.get(conn.module_name)
            if mod is None:
                # 被实例化模块可能定义在别的文件（本文件只有实例化点）
                continue
            mod.insts.append(conn)
        fr.parse_ok = True
        return fr

    def _expand_source(self, source: str, path: str) -> str:
        """宏展开（scan_directives 提取宏表 + expand_tokens 纯文本展开）。

        与 run_pipeline 的 _stage_macro_scan/_stage_expand 同语义；无宏
        文件空表 → 原样返回。诊断行号基于展开后文本（宏 span 反向映射
        属 P3.3 范畴，语义正确性优先）。
        """
        try:
            from preprocessor import expand_tokens, scan_directives

            macro_table, func_macros, _, _, _, clean = scan_directives(
                source,
                self._rules_dir,
                source_path=path,
                search_dirs=self._include_dirs,
                predefined=None,
                undefine=None,
            )
            if macro_table:
                # semantic=True：语句体宏展开宏体（check 需语义，不要保真锚
                # marker——否则宏体不可分析 + marker 被 W002 误报）
                clean, _ = expand_tokens(
                    clean, macro_table, func_macros=func_macros, semantic=True
                )
            return clean
        except Exception:  # noqa: BLE001 — 展开失败回退原文（lint 兜底）
            return source

    def _elaborate_connections(self, path: str, inst_sites: list) -> list[PortConnection]:
        """层 2：实例化点端口连接展开（ADR-0008）。

        从 ModuleInst 节点提取端口连接 → (端口名, 连接信号名) 映射：
        - NamedPortList（命名连接 .p(sig)）→ 按 port_name 收集
        - OrderedPortList（位置连接 a,b,c）→ 按序收集
        连接信号名 = 端口连接表达式的文本（信号/拼接/常量；解析交给
        上层规则 handler，此处只展开结构）。语言无关：端口连接节点形态
        由结构协议声明（connects_field/value_field/ordered_rule）。
        """
        if not self._has_structure():
            return []
        out: list[PortConnection] = []
        ports_field = self._field("connects") or "ports"
        value_field = self._field("value")
        conn_name_field = self._field("port_name")
        items_field = self._field("items")
        for site in inst_sites:
            mod_name = self._inst_module_name(site)
            inst_name_node = getattr(site, self._field("inst_name"), None)
            inst_name = (
                inst_name_node.content
                if isinstance(inst_name_node, Node) and inst_name_node.content
                else ""
            )
            conn = PortConnection(
                inst_name=inst_name,
                module_name=mod_name,
                inst_node=site,
                file=path,
            )
            ports_node = self._unwrap(getattr(site, ports_field, None))
            items = getattr(ports_node, items_field, None) if ports_node else None
            for item in items or []:
                if not isinstance(item, Node):
                    continue
                # 命名连接：.port_name(value) 形态（NamedPortConnect 有 port_name）
                pn = getattr(item, conn_name_field, None) if conn_name_field else None
                pn_text = pn.content if isinstance(pn, Node) and pn.content else ""
                if pn_text:
                    val = getattr(item, value_field, None) if value_field else None
                    conn.connects[pn_text] = self._render_subtree(val) if isinstance(
                        val, Node
                    ) else ""
                    continue
                # 其余项 = 位置连接（Expression/HierExpr 等，渲染回文本）
                conn.ordered.append(self._render_subtree(item))
            out.append(conn)
        return out

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

    # ── AST 提取（模块定义表 / 实例化点）──

    def _extract_modules(self, ast: Node, path: str) -> dict[str, ModuleInfo]:
        modules: dict[str, ModuleInfo] = {}
        if not self._has_structure():
            return modules  # 语言包未声明结构协议 → 无模块提取
        decl_rule = self._rule("module_decl_rule")
        name_field = self._field("module_name")
        for node in self._iter_nodes(ast):
            if node.node_name != decl_rule:
                continue
            name_node = getattr(node, name_field, None)
            if not isinstance(name_node, Node) or not name_node.content:
                continue
            info = ModuleInfo(name=name_node.content, file=path, node=node)
            node._file = path  # related 链跨文件定位
            self._fill_ports(info, node)
            self._fill_params(info, node)
            modules[info.name] = info
        return modules

    def _fill_ports(self, info: ModuleInfo, module_node: Node) -> None:
        """按结构协议提取端口声明形态（ANSI 风格 + 裸名风格 + body 声明）。"""
        ports_field = self._field("ports")
        items_field = self._field("items")
        bare_rule = self._field("bare_rule")
        decl_field = self._field("decl")
        direction_field = self._field("direction")
        width_field = self._field("width")
        port_type_field = self._field("port_type")
        name_field = self._field("name")
        ports_node = self._unwrap(getattr(module_node, ports_field, None))
        items = getattr(ports_node, items_field, None) if ports_node else None
        if not items:
            # 无端口列表（纯 body 端口声明）也补 body（旧式风格）
            self._fill_body_ports(info, module_node)
            return
        for item in items:
            if not isinstance(item, Node):
                continue
            if bare_rule and item.node_name == bare_rule:
                # 裸名端口（方向/类型在 body 声明，此处仅登记名字）
                if item.content:
                    info.ports[item.content] = ModulePort(name=item.content)
                continue
            # ANSI 风格：端口声明规则 inline 展平，item 即具体声明；
            # 防御：也可能是未展平的包装节点（取其 decl 字段）
            decl = getattr(item, decl_field, None) if decl_field else None
            if isinstance(decl, Node):
                item = decl
            direction = ""
            if direction_field:
                direction = getattr(item, direction_field, "") or ""
            pr = getattr(item, width_field, None) if width_field else None
            width = self._render_subtree(pr) if isinstance(pr, Node) else ""
            pt = getattr(item, port_type_field, None) if port_type_field else None
            net_type = self._render_subtree(pt) if isinstance(pt, Node) else ""
            dlist = getattr(item, items_field, None) if items_field else None
            d_items = getattr(dlist, items_field, None) if dlist else None
            for d in d_items or []:
                if not isinstance(d, Node):
                    continue
                dn = getattr(d, name_field, None) if name_field else None
                if isinstance(dn, Node) and dn.content:
                    d._file = info.file
                    info.ports[dn.content] = ModulePort(
                        name=dn.content,
                        direction=direction,
                        width_expr=width,
                        net_type=net_type,
                        decl_node=d,
                    )
        # body 端口声明（旧式 `input [7:0] x;` 在模块体）→ 按名补方向/宽度
        # （2026-08-29 修复：tv80 旧式端口方向/宽度缺失——影响 W104 方向
        # 判定与 B3 端口连接宽度）。
        self._fill_body_ports(info, module_node)

    def _fill_body_ports(self, info: ModuleInfo, module_node: Node) -> None:
        """body 端口声明补全：方向/宽度按名回填裸名端口或补登记。

        只扫模块体顶层声明，**跳过函数/任务子树**——函数参数（input
        [3:0] A）与模块体端口同节点名（BodyInputDecl），全子树遍历会把
        函数局部 input 误当模块端口（2026-08-29 对标测试暴露：tv80_alu
        的 AddSub4 函数参数 A/B/Sub/Carry_In 被误登记为模块端口，8 条
        W104 假阳性；Verilator 0 报 PINMISSING）。
        """
        rules = self._struct.get("body_port_rules") or []
        if not rules:
            return
        direction_field = self._field("body_direction") or "direction"
        width_field = self._field("width")
        items_field = self._field("items")
        name_field = self._field("name")
        _FUNC_OR_TASK = ("FuncDecl", "FuncDeclOld", "TaskDecl", "FunctionDecl",
                         "TaskDeclStmt")
        stack = list(module_node.iter_children())
        while stack:
            node = stack.pop()
            if not isinstance(node, Node):
                continue
            if node.node_name in _FUNC_OR_TASK:
                continue  # 函数/任务子树整体跳过（参数非模块端口）
            if node.node_name in rules:
                direction = getattr(node, direction_field, "") or ""
                pr = getattr(node, width_field, None)
                width = self._render_subtree(pr) if isinstance(pr, Node) else ""
                dlist = getattr(node, items_field, None)
                d_items = getattr(dlist, items_field, None) if dlist else None
                for d in d_items or []:
                    if not isinstance(d, Node):
                        continue
                    dn = getattr(d, name_field, None)
                    if not (isinstance(dn, Node) and dn.content):
                        continue
                    p = info.ports.get(dn.content)
                    if p is None:
                        d._file = info.file
                        info.ports[dn.content] = ModulePort(
                            name=dn.content,
                            direction=direction,
                            width_expr=width,
                            decl_node=d,
                        )
                    else:
                        p.direction = p.direction or direction
                        p.width_expr = p.width_expr or width
                        if p.decl_node is None:
                            p.decl_node = d
            # 继续下钻（Body*Decl 自身无端口子节点，正常下钻函数兄弟）
            for child in node.iter_children():
                stack.append(child)

    def _fill_params(self, info: ModuleInfo, module_node: Node) -> None:
        params_field = self._field("params")
        param_name_field = self._field("param_name")
        value_field = self._field("value")
        params_node = self._unwrap(getattr(module_node, params_field, None))
        params = getattr(params_node, params_field, None) if params_node else None
        if params:
            for p in params:
                if not isinstance(p, Node):
                    continue
                p = self._unwrap(p)  # 参数声明可能被 optional 包装
                if not isinstance(p, Node):
                    continue
                pn = getattr(p, param_name_field, None) if param_name_field else None
                if not isinstance(pn, Node) or not pn.content:
                    continue
                val = getattr(p, value_field, None) if value_field else None
                info.params[pn.content] = ModuleParam(
                    name=pn.content,
                    value_expr=self._render_subtree(val) if isinstance(val, Node) else "",
                )
        # 模块体内参数声明（`parameter P = v;` 语句形态，非头部 #(..) 列表）：
        # ice40 单元库 SB_RAM40_4K 等大量使用 body 参数——只收头部参数会让
        # W103（覆盖不存在参数）误报（2026-08-29 对标测试暴露，79 条 FP）。
        # 扫描 module_node 子树内全部 ParamDeclStmt（含 generate/ifdef 内）。
        self._fill_body_params(info, module_node)

    def _fill_body_params(self, info: ModuleInfo, module_node: Node) -> None:
        """扫描模块体 ParamDeclStmt，补 body 参数进 module_index。

        ParamDeclStmt → items(DeclaratorList) → Declarator(name, init)。
        头部参数已填过（同名保留头部——body 同名参数属重复声明，取先）。
        """
        for node in self._iter_nodes(module_node):
            if node.node_name != "ParamDeclStmt":
                continue
            items = getattr(node, "items", None)
            dl = getattr(items, "items", None) if isinstance(items, Node) else None
            for d in dl or []:
                if not isinstance(d, Node) or d.node_name != "Declarator":
                    continue
                name_node = getattr(d, "name", None)
                if not isinstance(name_node, Node) or not name_node.content:
                    continue
                if name_node.content in info.params:
                    continue  # 头部已填（body 同名重复声明，取先）
                val = getattr(d, "init", None)
                info.params[name_node.content] = ModuleParam(
                    name=name_node.content,
                    value_expr=self._render_subtree(val) if isinstance(val, Node) else "",
                )

    def _build_signal_graph(self) -> dict:
        """层 3：全工程信号驱动/负载图（ADR-0008）。

        汇总所有文件的端口连接展开 + 连续赋值目标，按 **(模块, 信号名)**
        建立（2026-08-29 修复：跨模块同名信号隔离——真实语料 ice40 的
        SB_LUT4/ICESTORM_LC/SB_MAC16 各有端口 O，按裸信号名合并会误报
        多驱动）：
            (module, signal) → {"drivers": [驱动源标识], "loads": [..]}
        驱动源两类（语言知识全部来自配置协议）：
        - 实例 output/inout 端口连接该信号 → 实例驱动（"file:inst"）
        - 本文件连续赋值目标（assign_rule 协议 + 多目标 AssignExtra）→
          assign 驱动（"file:assign#N"）
        驱动/负载源标识含文件名，消费方按"驱动源所在文件"归属（避免
        跨文件重复报）。输出注入 context.extra["signal_graph"]。
        """
        graph: dict[tuple, dict] = {}
        out_dirs = self._dirs("output_dirs")
        inout_dirs = self._dirs("inout_dirs")
        assign_rule = self._rule("assign_rule")
        target_field = self._field("assign_target")
        extras_field = self._field("assign_extras")
        extra_target_field = self._field("assign_extra_target")

        def _ensure(key: tuple) -> dict:
            if key not in graph:
                graph[key] = {"drivers": [], "loads": []}
            return graph[key]

        for fr in self._memo.values():
            # 连续赋值驱动（模块级 assign 并发驱动；多目标 AssignExtra 展开）
            if assign_rule and fr.ast is not None:
                assign_idx = 0
                for node in self._iter_nodes(fr.ast):
                    if node.node_name != assign_rule:
                        continue
                    assign_idx += 1
                    mod_name = self._module_of(fr, node)
                    if not self._in_active_generate(fr, node):
                        continue  # 所在 generate 互斥分支未选中（2026-08-29）
                    inst_ref = f"{os.path.basename(fr.path)}:assign#{assign_idx}"
                    for tgt in self._iter_assign_targets(
                        node, target_field, extras_field, extra_target_field
                    ):
                        sig = self._render_subtree(tgt)
                        if not sig or not _is_signal_expr(sig):
                            continue
                        entry = _ensure((mod_name, sig))
                        if inst_ref not in entry["drivers"]:
                            entry["drivers"].append(inst_ref)
            for conn in fr.connections:
                mod_name = self._module_of(fr, conn.inst_node)
                if not self._in_active_generate(fr, conn.inst_node):
                    continue  # 实例化点所在 generate 分支未选中
                inst_ref = f"{os.path.basename(conn.file)}:{conn.inst_name}"
                mod = self._module_index.get(conn.module_name)
                for port_name, sig in conn.connects.items():
                    if not sig or not _is_signal_expr(sig):
                        continue
                    entry = _ensure((mod_name, sig))
                    direction = ""
                    if mod is not None and port_name in mod.ports:
                        direction = mod.ports[port_name].direction
                    if direction in out_dirs:
                        if inst_ref not in entry["drivers"]:
                            entry["drivers"].append(inst_ref)
                    elif direction in inout_dirs:
                        if inst_ref not in entry["drivers"]:
                            entry["drivers"].append(inst_ref)
                        if inst_ref not in entry["loads"]:
                            entry["loads"].append(inst_ref)
                    else:  # input / 未知 → 负载
                        if inst_ref not in entry["loads"]:
                            entry["loads"].append(inst_ref)
                for sig in conn.ordered:
                    if not sig or not _is_signal_expr(sig):
                        continue
                    # 位置连接：方向靠模块端口表按序匹配；未知方向保守记负载
                    entry = _ensure((mod_name, sig))
                    if inst_ref not in entry["loads"]:
                        entry["loads"].append(inst_ref)
        return graph

    def _in_active_generate(self, fr, node) -> bool:
        """节点是否在**选中**的 generate 互斥分支内（对齐 Verilator）。

        Verilator 在 V3Param::visit(AstGenIf) 求值 generate 条件，未选中
        分支的 AST 物理删除（deleteTree）——后续多驱动检测只看到选中分支
        的驱动源。tpc 不展开 generate，信号图平铺收集会同时计入互斥分支
        （如 picorv32 `generate if (ENABLE_MUL) 实例 else assign`：两个
        分支都驱动 pcpi_mul_ready → 8 条 W105 假阳性，Verilator 0 报）。

        本方法：沿祖先链找 GenerateBlock→IfBlock，条件可求值（模块参数
        表）且节点不在选中分支 → False（跳过该驱动源）；条件不可判 →
        True 保守保留（不因无法判定而漏报真多驱动）。
        """
        if fr.ast is None or node is None:
            return True
        # 模块参数表（头部 + body 参数，_fill_params 已合并）→ 求值环境
        mod_name = self._module_of(fr, node)
        info = self._module_index.get(mod_name)
        params: dict[str, str] = {}
        if info is not None:
            params = {p.name: p.value_expr for p in info.params.values()}
        # 找节点所在模块声明，沿其子树内 generate 结构判定
        decl_rule = self._rule("module_decl_rule")
        for mnode in self._iter_nodes(fr.ast):
            if mnode.node_name != decl_rule:
                continue
            if not self._subtree_contains(mnode, node):
                continue
            return self._branch_active(mnode, node, params)
        return True

    def _branch_active(self, mod_node: Node, target: Node, params: dict) -> bool:
        """模块内 target 是否处于选中的 generate 分支（递归沿祖先）。

        遍历模块子树找 GenerateBlock→IfBlock/ElseIfBlock；若 target 在某
        个条件分支块内，求值 condition（参数表），判定该分支是否选中；
        未选中 → False。else-if 链递归（ElseIfBlock 与 IfBlock 同构）。
        多个嵌套 generate 全部选中才 True。条件不可判 → True 保守保留
        （不因无法判定而漏报真多驱动，对齐 Verilator V3Param 语义的
        保守侧）。
        """
        for gnode in self._iter_nodes(mod_node):
            if gnode.node_name != "GenerateBlock":
                continue
            for sub in getattr(gnode, "sub_node", None) or []:
                if not isinstance(sub, Node):
                    continue
                if sub.node_name == "IfBlock" and self._subtree_contains(sub, target):
                    return self._if_branch_active(sub, target, params)
                # ElseIfBlock 也可能直接挂在 GenerateBlock 下（罕见）
                if sub.node_name == "ElseIfBlock" and self._subtree_contains(sub, target):
                    return self._if_branch_active(sub, target, params)
        return True

    def _if_branch_active(self, ifb: Node, target: Node, params: dict) -> bool:
        """IfBlock/ElseIfBlock：target 所在分支是否选中（else-if 链递归）。

        - target 在 then 分支 → 条件为真才选中
        - target 在 else 分支（else_chain 内）→ 条件为假**且**后续链判定
        - else_chain 是 ElseIfBlock → 递归（其 then/else 判定）
        - else_chain 是 ElseBlockBranch（最终 else）→ 前面全假才选中
        """
        in_then = self._subtree_contains(getattr(ifb, "then_stmt", None), target)
        cond_val = self._eval_gen_cond(ifb, params)
        if in_then:
            return cond_val is True if cond_val is not None else True
        # else 分支：条件为假 + 链内判定
        if cond_val is not None and cond_val:
            return False  # 条件为真，else 分支未选中
        chain = getattr(ifb, "else_chain", None)
        if not isinstance(chain, Node):
            return True  # 无 else → 条件为假时无分支；保守保留
        if chain.node_name == "ElseIfBlock":
            return self._if_branch_active(chain, target, params)
        # ElseBlockBranch（最终 else）：前面条件全假 → 选中
        return self._subtree_contains(chain, target)

    def _eval_gen_cond(self, ifb: Node, params: dict):
        """IfBlock.condition → 布尔｜None（不可判）。

        条件文本（HierExpr/Identifier/常量表达式）→ 查参数表 → 数值求值
        转布尔。不可判（无参数值/非纯常量/引用未定义）→ None 保守。
        """
        cond = getattr(ifb, "condition", None)
        text = self._render_subtree(cond) if isinstance(cond, Node) else ""
        text = (text or "").strip()
        if not text:
            return None
        if text.isdigit():
            return int(text) != 0
        if text in params:
            v = params[text].strip()
            if v.isdigit():
                return int(v) != 0
            return None  # 参数值本身非纯数字 → 不可判
        # 含运算的简单常量表达式（1+0 / 0 && 1 等）——求值器在 width_check
        # 插件层（语言知识），引擎层只处理纯标识符/数字；复杂表达式保守
        try:
            if re.fullmatch(r"[0-9+\-*/()<>=!&| ]+", text):
                return bool(eval(text, {"__builtins__": {}}, {}))
        except Exception:
            return None
        return None

    def _module_of(self, fr, node) -> str:
        """节点所属模块名（所在 ModuleDecl；文件级/未命中 → ""）。

        嵌套模块罕见——用子树包含判定（模块声明节点是否含目标节点）。
        """
        if fr.ast is None or node is None:
            return ""
        decl_rule = self._rule("module_decl_rule")
        name_field = self._field("module_name")
        for mnode in self._iter_nodes(fr.ast):
            if mnode.node_name != decl_rule:
                continue
            if self._subtree_contains(mnode, node):
                nm = getattr(mnode, name_field, None)
                return nm.content if isinstance(nm, Node) else ""
        return ""

    @staticmethod
    def _subtree_contains(root: Node, target: Node) -> bool:
        """target 是否在 root 子树内（含自身）。"""
        stack = [root]
        while stack:
            node = stack.pop()
            if node is target:
                return True
            for child in node.iter_children():
                stack.append(child)
        return False

    def _iter_assign_targets(
        self, node: Node, target_field: str, extras_field: str, extra_target_field: str
    ):
        """按协议提取赋值语句的驱动目标节点（主目标 + 多目标后缀）。"""
        tgt = getattr(node, target_field, None)
        if isinstance(tgt, Node):
            yield tgt
        for ex in getattr(node, extras_field, None) or []:
            if not isinstance(ex, Node):
                continue
            et = getattr(ex, extra_target_field, None)
            if isinstance(et, Node):
                yield et

    def _render_subtree(self, node: Node) -> str:
        """把 AST 子树渲染回文本（宽度表达式/连接信号等）。"""
        try:
            return self._ensure_shared()["renderer"].render(node).strip()
        except Exception:
            return ""

    # ── 模块定义文件查找 ──

    def _find_module_file(self, module_name: str, from_file: str) -> str | None:
        """按名字找模块定义文件：同名文件优先，再扫描目录文本匹配。

        扩展名与模块关键字来自语言包结构协议（file_exts / module_keyword）。
        """
        exts = self._exts()
        keyword = self._rule("module_keyword")
        dirs = [os.path.dirname(from_file)] + self._include_dirs
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for ext in exts:
                cand = os.path.join(d, module_name + ext)
                if os.path.isfile(cand):
                    return cand
        if not keyword:
            return None
        pattern = re.compile(
            r"\b" + re.escape(keyword) + r"\s+" + re.escape(module_name) + r"\b"
        )
        for d in dirs:
            if not os.path.isdir(d):
                continue
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for fname in names:
                if not any(fname.endswith(ext) for ext in exts):
                    continue
                fp = os.path.join(d, fname)
                try:
                    with open(fp, "r", encoding="utf-8", errors="replace") as f:
                        if pattern.search(f.read()):
                            return fp
                except OSError:
                    continue
        return None

    # ── 通用 AST 工具 ──

    @staticmethod
    def _unwrap(node):
        """穿透 parser 的 optional 包装节点（$N 捕获可选组时是 optional 节点，
        内容在 sub_node[0]；inline 规则展平后可能仍保留 optional 壳）。"""
        while isinstance(node, Node) and node.node_name == "optional":
            sub = getattr(node, "sub_node", None) or []
            node = sub[0] if sub else None
        return node

    @staticmethod
    def _iter_nodes(root: Node):
        """DFS 迭代整棵 AST（含属性挂载的子节点）。"""
        stack = [root]
        while stack:
            node = stack.pop()
            yield node
            for child in node.iter_children():
                stack.append(child)

    @staticmethod
    def _collect_nodes(root: Node, node_name: str) -> list:
        return [n for n in ProjectChecker._iter_nodes(root) if n.node_name == node_name]

    def _inst_module_name(self, site: Node) -> str:
        mn = getattr(site, self._field("module_name"), None)
        if isinstance(mn, Node) and mn.content:
            return mn.content
        return ""

    # ── 诊断序列化（LSP 兼容 + stage 字段）──

    @staticmethod
    def _syntax_diag(fr: FileResult, d) -> dict:
        span = getattr(d, "range", None)
        return {
            "stage": "syntax",
            "file": fr.path,
            "severity": 1,
            "code": getattr(d, "code", "parse-error"),
            "message": d.message,
            "range": (
                {
                    "start": {"line": span[0].line, "character": span[0].character},
                    "end": {"line": span[1].line, "character": span[1].character},
                }
                if span
                else None
            ),
        }

    @staticmethod
    def _semantic_diag(fr: FileResult, d) -> dict:
        node = d.node
        line = getattr(node, "_pos_line", None)
        col = getattr(node, "_pos_col", None)
        sev = {"error": 1, "warning": 2, "info": 3}.get(d.level, 2)
        out = {
            "stage": "semantic",
            "file": fr.path,
            "severity": sev,
            "code": d.code or "semantic",
            "message": d.message,
            "level": d.level,
            "range": (
                {
                    "start": {"line": line - 1 if line else 0, "character": col or 0},
                    "end": {
                        "line": line - 1 if line else 0,
                        "character": (col or 0) + 1,
                    },
                }
                if line is not None
                else None
            ),
        }
        related = []
        for msg, rnode in d.related:
            rl = getattr(rnode, "_pos_line", None)
            rc = getattr(rnode, "_pos_col", None)
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
