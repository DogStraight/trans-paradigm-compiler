"""structure.py — 结构提取的**文件层**：单元索引 + 依赖发现（引擎侧最小面）。

定位：**通用设施**，不是检查专用——消费方包括各 postpass/插件（它们读引擎注入的
`context.extra`：`module_index` / `inst_sites`，以及 `CTX_ELABORATION` 里的精化产物）。

语言无关边界：本模块**零语言知识**。单元/实例化的规则名、节点字段、文件
扩展名、关键字全部来自语言包声明的 `[structure] protocol`
（grammar/<lang>/base/_structure.toml）；未声明该段 = 该语言不支持结构提取，
调用方退化为单文件 lint + analyze（`ctx.has_structure()` 判定）。

⚠ **层 2/3 与 generate 求值均已迁出**（ADR-0019 P3）：端口连接展开、信号驱动/负载图、
generate 条件求值都是**语言知识**，现归语言包插件精化项
（`grammar/verilog/plugins/elaboration/`：`port_decls` / `connections` / `signal_graph` /
`gen_activity`）；引擎按**角色位**取自己要用的产物（现仅 `gen_activity`），其余产物由
插件**直接读容器**。

本模块剩下的协作者（引擎唯一可视单位 = **文件**）：

    StructureCtx        会话上下文：环境开关 + 索引 + 协议读取（唯一状态归属点）
    ModuleIndexer       发现：入口 → 实例化链（+ 目录关键字文本扫描兜底）→ 索引
    FilePipeline        单文件装配：读源 → 宏展开 → 解析 → 提单元（名字/文件/节点）
    ModuleExtractor     单元注册表（**只剩**名字 / 文件 / 声明节点——语言形状全在插件）

组合方向（无环）：`FilePipeline` 含 `ModuleExtractor`；`ModuleIndexer` 含 `FilePipeline`；
全部共享同一个 `StructureCtx`。组合根是门面
`analyzer/checker.py::ProjectChecker`（原先的门面继承底座已改为组合）。

为什么是组合而不是继承（2026-09-19 实测依据）：① 底座原先只有 1 个子类且**零方法
覆盖**——继承没承担任何多态语义，只是借命名空间共享 `self.*`；② 49 个方法只共享
9 个字段，收成 `StructureCtx` 后状态归属唯一（失效点 `invalidate()` 与缓存成对）；
③ 按职责分簇后**簇间无反向调用边**（有向无环），故各簇可独立成类、依赖用构造注入
表达，跨簇调用在类型检查下可见（原先同为一个 self 上的方法，谁调谁看不出来）。

Doc: analyzer/semantic_checks.md（跨文件语义检查）
"""

import bisect
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from core.define import CHILDREN_FIELD, Node, collect_nodes, iter_nodes, unwrap_optional
from core.token_protocol import IDENT_RE
from core.config_registry import declare_cfg

if TYPE_CHECKING:
    from analyzer.traversal import AnalysisTraversal

# ── 配置需求（来自语言包 tpc.toml [structure]） ────────────
# structure.protocol: 结构提取协议——单元/实例化的规则名、节点字段、
# 文件扩展名、关键字全部由语言包声明（grammar/<lang>/base/_structure.toml）。
# 未声明 = 语言包不支持结构提取（check 退化为 lint+analyze）。
_structure_cfg: dict = declare_cfg("structure.protocol", {}, __name__, "_structure_cfg")


# ── 数据模型 ──────────────────────────────────────────────

# 连接表达式是否为"简单信号名"（层 3 建图过滤：常量/拼接/带位选的复杂
# 表达式不入驱动/负载图——信号解析交给上层规则，此处只记简单标识符）。



@dataclass
class _ModulePort:
    """模块端口声明（声明形态，供实例化联动比对）。"""

    name: str
    direction: str = ""  # input / output / inout（旧风格裸名可空）
    width_expr: str = ""  # 宽度表达式文本（如 "DATA_W-1:0"、"7:0"；无范围空）
    net_type: str = ""  # 数据类型/网络类型（wire/tri/reg/...；协议字段声明）
    decl_node: Node | None = None  # 端口声明节点（related 链定位）


@dataclass
class ModuleInfo:
    """一个模块定义（跨文件索引条目）。"""

    name: str
    file: str
    node: Node  # ModuleDecl 节点（定位）
    ports: dict[str, _ModulePort] = field(default_factory=dict)
    # 参数默认值**不在引擎侧**：它是语言知识 → 精化产物 `param_default`
    # （ADR-0019，`grammar/verilog/plugins/elaboration/`；消费方读产物容器）。
    # ⚠ 曾有 `insts`（模块内实例化点）——**只有写入、从无读取**的死字段，
    #    2026-09-25 连同唯一写入点（`FilePipeline.parse_file` 的挂回循环）删除。





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
    # 展开行（0-based，索引展开后文本）→ 原始源行（1-based）；None = 不可
    # 映射（include 拼接行）；空表 = 未展开（诊断行号原样）。两级复合：
    # scan_directives（原始→clean）+ expand_tokens（clean→展开后）。
    line_map: list = field(default_factory=list)
    # 宏区间（语义展开）：[{name, line_start, line_end, call_line}]——宏体铺进
    # 文本的展开行区间（1-based）+ 宏调用原文行（1-based，不可映射 None）；
    # 诊断归因（加 "macro" 字段）反查用。顿路径（非 semantic）空表。
    macro_regions: list = field(default_factory=list)


# ── 常量表达式求值 ────────────────────────────────────────




# ── 引擎 ─────────────────────────────────────────────────


@dataclass
class StructureCtx:
    """结构提取会话上下文：环境开关 + 会话状态 + 结构协议读取。

    组合根（`ProjectChecker.__init__`）构造一次并注入各协作者——把原先靠
    "大家是同一个 self" 隐式共享的状态收成显式对象：

    - 环境开关（`rules_dir` / `ext_dirs` / `include_dirs` / `expand_macros` /
      `ensure_shared`）：构造后不变。
    - 会话状态（`memo` / `module_index` / `dir_module_files`）：
      每次 check 起始由 `invalidate()` 清空（前三者**成对失效**——键都由 memo 派生；
      `dir_module_files` 缓存磁盘目录内容，同一次运行内文件不变，一并清）。
    - 结构协议（`struct` / `fields`）：`refresh()` 在 `load_all` 之后推入
      （语言知识仅来自 grammar/<lang> TOML；未声明 = 不支持结构提取）。

    协议读取与两个共享读取助手（`render_subtree` / `inst_module_name`）放在
    这里而非某个功能簇：它们被多个簇共用，且只依赖本对象的环境/协议。
    """

    rules_dir: str
    ext_dirs: list[str]
    include_dirs: list[str]
    expand_macros: bool
    ensure_shared: Callable[[], dict]
    memo: dict[str, FileResult] = field(default_factory=dict)
    module_index: dict[str, ModuleInfo] = field(default_factory=dict)
    struct: dict = field(default_factory=dict)
    fields: dict = field(default_factory=dict)
    dir_module_files: dict[str, dict[str, str]] = field(default_factory=dict)
    # 精化产物：generate 分支活性（ADR-0019 角色位 gen_activity；由 ProjectChecker
    # 从插件容器按角色取入）。形状 = {文件路径: {id(节点): bool}}——引擎不再自己求值
    # generate 条件（那是语言知识，已归语言包精化项）。层 3 迁入协议后随之退场。
    gen_activity: dict[str, dict[int, bool]] = field(default_factory=dict)

    # ── 会话状态失效（每次 check 起始调用）──

    def invalidate(self) -> None:
        """清本次运行的索引与派生缓存。"""
        self.memo.clear()
        self.module_index.clear()
        self.dir_module_files.clear()
        self.gen_activity.clear()

    def refresh(self) -> None:
        """load_all 后刷新结构协议（_structure_cfg 模块变量被推入真实值）。

        ⚠ 不再校验"条件求值面"：generate 的块/分支规则名、条件字段、逻辑非前缀已随
        gen 族搬迁（ADR-0019 P3-①）删除——那些形态现在归**语言包插件**自己持有，引擎
        不认（故也无需在此 fail-fast）。此处只留仍属引擎读取面的项。
        """
        self.struct = _structure_cfg or {}
        self.fields = (self.struct.get("fields") or {}) if self.struct else {}

    # ── 结构协议读取（语言知识仅来自 grammar/<lang> TOML）──

    def rule(self, key: str) -> str:
        """规则名/关键字等标量协议项（如 module_decl_rule）。"""
        return str(self.struct.get(key) or "")

    def field(self, key: str) -> str:
        """节点字段名协议项（如 module_name / ports）。"""
        return str(self.fields.get(key) or "")

    def exts(self) -> list[str]:
        exts = self.struct.get("file_exts") or []
        return [str(e) for e in exts] if isinstance(exts, list) else []

    def dirs(self, key: str) -> set[str]:
        """端口方向值集合（层 3 信号图判定；语言包声明，引擎零语言知识）。"""
        vals = (self.struct.get(key) or []) if self.struct else []
        return {str(v) for v in vals} if isinstance(vals, list) else set()

    def has_structure(self) -> bool:
        """语言包是否声明了跨文件结构协议（模块/实例化形态）。"""
        return bool(self.struct and self.rule("module_decl_rule"))



    def render_subtree(self, node: Node) -> str:
        """把 AST 子树渲染回文本（宽度表达式/连接信号等）。"""
        try:
            return self.ensure_shared()["renderer"].render(node).strip()
        except Exception:
            # 渲染失败 → 空串：调用方（条件/宽度提取）按"拿不到文本 = 不可判"
            # 保守处理，不影响正确性；此处不报错是设计（非静默错乱）。
            return ""

    def inst_module_name(self, site: Node) -> str:
        mn = getattr(site, self.field("module_name"), None)
        if isinstance(mn, Node) and mn.content:
            return mn.content
        return ""





@dataclass(frozen=True)
class _PortFields:
    """端口提取用到的结构协议字段名（一次读出、多处复用；名字全部来自声明）。"""

    ports: str
    items: str
    bare_rule: str
    decl: str
    direction: str
    width: str
    port_type: str
    name: str





class ModuleExtractor:
    """层 1 单元提取：AST → ModuleInfo（端口/参数声明形态 + 名字/方向/宽度）。

    语言知识全部走 ctx 协议（`module_decl_rule` / 节点字段名 / `has_structure`），
    故换语言包即换形态。产出挂 `FileResult.modules`（层 2/3 与 postpass 消费）。

    只依赖 ctx（协议读取 + 渲染助手），不持有会话状态。
    """

    def __init__(self, ctx: StructureCtx) -> None:
        self._ctx = ctx

    # ── AST 提取（模块定义表 / 实例化点）──

    def extract_modules(self, ast: Node, path: str) -> dict[str, ModuleInfo]:
        modules: dict[str, ModuleInfo] = {}
        if not self._ctx.has_structure():
            return modules  # 语言包未声明结构协议 → 无模块提取
        decl_rule = self._ctx.rule("module_decl_rule")
        name_field = self._ctx.field("module_name")
        for node in iter_nodes(ast):
            if node.node_name != decl_rule:
                continue
            name_node = getattr(node, name_field, None)
            if not isinstance(name_node, Node) or not name_node.content:
                continue
            info = ModuleInfo(name=name_node.content, file=path, node=node)
            node._file = path  # related 链跨文件定位
            self._fill_ports(info, node)
            modules[info.name] = info
        return modules

    def _decl_name_nodes(
        self, decl_node: Node, items_field: str, name_field: str
    ) -> list[tuple[Node, Node]]:
        """声明节点 → [(名字声明节点, 名字节点)]（端口/body 端口回填共用）。

        端口与参数的声明同形：外层声明节点的 `items` 再套一层声明列表
        （内层元素挂 `name`）。列表缺失 / 元素非节点 / 名字为空 → 不计。
        """
        dlist = getattr(decl_node, items_field, None) if items_field else None
        d_items = getattr(dlist, items_field, None) if isinstance(dlist, Node) else None
        out: list[tuple[Node, Node]] = []
        for d in d_items or []:
            if not isinstance(d, Node):
                continue
            dn = getattr(d, name_field, None) if name_field else None
            if isinstance(dn, Node) and dn.content:
                out.append((d, dn))
        return out

    def _register_port(
        self,
        info: ModuleInfo,
        name_node: Node,
        decl_node: Node,
        direction: str,
        width: str,
        net_type: str = "",
    ) -> None:
        """登记端口（同名覆盖：ANSI 头部声明优先于 body 回填）。"""
        decl_node._file = info.file
        info.ports[name_node.content] = _ModulePort(
            name=name_node.content,
            direction=direction,
            width_expr=width,
            net_type=net_type,
            decl_node=decl_node,
        )

    def _backfill_port(
        self,
        info: ModuleInfo,
        name_node: Node,
        decl_node: Node,
        direction: str,
        width: str,
    ) -> None:
        """按名回填端口方向/宽度；未登记则补登记（body 声明不带 net_type）。"""
        p = info.ports.get(name_node.content)
        if p is None:
            self._register_port(info, name_node, decl_node, direction, width)
            return
        p.direction = p.direction or direction
        p.width_expr = p.width_expr or width
        if p.decl_node is None:
            p.decl_node = decl_node

    def _port_fields(self) -> "_PortFields":
        """端口提取用到的结构协议字段名（一次读取，多处复用）。"""
        f = self._ctx.field
        return _PortFields(
            ports=f("ports"),
            items=f("items"),
            bare_rule=f("bare_rule"),
            decl=f("decl"),
            direction=f("direction"),
            width=f("width"),
            port_type=f("port_type"),
            name=f("name"),
        )

    def _register_bare_port(
        self, info: ModuleInfo, item: Node, bare_rule: str
    ) -> bool:
        """裸名端口（方向/类型在 body 声明，此处仅登记名字）；命中裸名规则返回 True。"""
        if not bare_rule or item.node_name != bare_rule:
            return False
        if item.content:
            info.ports[item.content] = _ModulePort(name=item.content)
        return True

    def _register_ansi_item(
        self, info: ModuleInfo, item: Node, fl: "_PortFields"
    ) -> None:
        """ANSI 端口项 → 逐名登记（方向/宽度/网络类型）。

        ANSI 风格：端口声明规则 inline 展平，item 即具体声明；防御：也可能是
        未展平的包装节点（取其 decl 字段）。
        """
        decl = getattr(item, fl.decl, None) if fl.decl else None
        if isinstance(decl, Node):
            item = decl
        direction = (getattr(item, fl.direction, "") or "") if fl.direction else ""
        pr = getattr(item, fl.width, None) if fl.width else None
        width = self._ctx.render_subtree(pr) if isinstance(pr, Node) else ""
        pt = getattr(item, fl.port_type, None) if fl.port_type else None
        net_type = self._ctx.render_subtree(pt) if isinstance(pt, Node) else ""
        for d, dn in self._decl_name_nodes(item, fl.items, fl.name):
            self._register_port(info, dn, d, direction, width, net_type)

    def _fill_ports(self, info: ModuleInfo, module_node: Node) -> None:
        """按结构协议提取端口声明形态（ANSI 风格 + 裸名风格 + body 声明）。"""
        fl = self._port_fields()
        ports_node = unwrap_optional(getattr(module_node, fl.ports, None))
        items = getattr(ports_node, fl.items, None) if ports_node else None
        for item in items or []:
            if not isinstance(item, Node):
                continue
            if not self._register_bare_port(info, item, fl.bare_rule):
                self._register_ansi_item(info, item, fl)
        # body 端口声明（旧式 `input [7:0] x;` 在模块体）→ 按名补方向/宽度；
        # 无端口列表（纯 body 端口声明）也要走这一段（旧式风格）
        # （2026-08-29 修复：tv80 旧式端口方向/宽度缺失——影响 W104 方向
        # 判定与 B3 端口连接宽度）。
        self._fill_body_ports(info, module_node)

    def _backfill_body_port_node(
        self,
        info: ModuleInfo,
        node: Node,
        direction_field: str,
        width_field: str,
        items_field: str,
        name_field: str,
    ) -> None:
        """单个 body 端口声明节点 → 按名回填方向/宽度。"""
        direction = getattr(node, direction_field, "") or ""
        pr = getattr(node, width_field, None)
        width = self._ctx.render_subtree(pr) if isinstance(pr, Node) else ""
        for d, dn in self._decl_name_nodes(node, items_field, name_field):
            self._backfill_port(info, dn, d, direction, width)

    def _fill_body_ports(self, info: ModuleInfo, module_node: Node) -> None:
        """body 端口声明补全：方向/宽度按名回填裸名端口或补登记。

        只扫模块体顶层声明，**跳过函数/任务子树**——函数参数（input
        [3:0] A）与模块体端口同节点名（BodyInputDecl），全子树遍历会把
        函数局部 input 误当模块端口（2026-08-29 对标测试暴露：tv80_alu
        的 AddSub4 函数参数 A/B/Sub/Carry_In 被误登记为模块端口，8 条
        W104 假阳性；Verilator 0 报 PINMISSING）。
        """
        rules = self._ctx.struct.get("body_port_rules") or []
        if not rules:
            return
        direction_field = self._ctx.field("body_direction") or "direction"
        width_field = self._ctx.field("width")
        items_field = self._ctx.field("items")
        name_field = self._ctx.field("name")
        _FUNC_OR_TASK = (
            "FuncDecl",
            "FuncDeclOld",
            "TaskDecl",
            "FunctionDecl",
            "TaskDeclStmt",
        )
        stack = list(module_node.iter_children())
        while stack:
            node = stack.pop()
            if not isinstance(node, Node):
                continue
            if node.node_name in _FUNC_OR_TASK:
                continue  # 函数/任务子树整体跳过（参数非模块端口）
            if node.node_name in rules:
                self._backfill_body_port_node(
                    info, node, direction_field, width_field, items_field, name_field
                )
            # 继续下钻（Body*Decl 自身无端口子节点，正常下钻函数兄弟）
            for child in node.iter_children():
                stack.append(child)


class FilePipeline:
    """单文件装配流水线：读源 → 宏展开 → 解析 → 单元注册。

    阶段顺序在这里（而不是散在调用方）：解析产 AST 后才能提单元。层 2/3 已迁语言包
    插件（ADR-0019 P3），故本类只组合 `ModuleExtractor`，其余依赖走 ctx。

    产出 `FileResult`（ast / modules / inst_sites / line_map / macro_regions），
    由调用方（发现阶段）收进 ctx.memo 与 ctx.module_index。
    """

    def __init__(
        self,
        ctx: StructureCtx,
        extractor: ModuleExtractor,
    ) -> None:
        self._ctx = ctx
        self._extract = extractor

    def parse_file(self, path: str) -> FileResult:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        fr = FileResult(path=path, source=source)
        shared = self._ctx.ensure_shared()

        # 宏展开（真实工程含 `ifdef/`define；对齐 run_pipeline 语义——
        # scan_directives 提取宏表 + expand_tokens 纯文本展开，lex/lint/
        # parse 全在展开后文本上）。无宏文件空表零影响。同时接收行映射
        # （展开行→原始源行）与宏区间表（展开行区间，诊断归因用）。
        if self._ctx.expand_macros:
            source, fr.line_map, fr.macro_regions = self._expand_source(source, path)

        # 阶段 1：语法检查（token 级）。有**阻断类**诊断 → 语义阶段跳过
        # （用户决策——保留原语义“语法错则语义不可靠”）；卫生/风格类
        # （blocking=False，如 ST 族排版提示）不影响解析，继续跑。
        fr.lint_diags = shared["linter"].scan(source)
        if any(d.blocking for d in fr.lint_diags):
            return fr

        # 解析
        from lexer import pre_scan, load_pre_scan_config
        from parser import Parser
        from parser.parser_core import ParseError

        pre_scan_config = load_pre_scan_config(self._ctx.rules_dir)
        pre_symbols = pre_scan(source, pre_scan_config)
        parser = Parser(
            rules_dir=self._ctx.rules_dir,
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
        fr.modules = self._extract.extract_modules(ast, path)
        fr.inst_sites = collect_nodes(ast, self._ctx.rule("module_inst_rule"))
        fr.parse_ok = True
        return fr

    def _expand_source(self, source: str, path: str) -> tuple[str, list, list]:
        """宏展开（scan_directives 提取宏表 + expand_tokens 纯文本展开）。

        与 run_pipeline 的 _stage_macro_scan/_stage_expand 同语义；无宏
        文件空表 → 原样返回。返回 (展开文本, 行映射, 宏区间表)：行映射 =
        **展开行（0-based）→ 原始源行（1-based）**，由两级变换的行表复合
        （scan_directives 删条件编译行 → clean；expand_tokens 铺多行宏体
        → 展开后）；不可映射（include 拼接行）为 None，消费方保守回退
        展开行号，不做错误回填（映射可能不准时宁保留诚实偏移）。宏区间表
        （语义展开时 = _macro_line_spans 产出）：宏体铺进的展开行区间 +
        宏调用原始行，诊断归因（加 "macro" 字段）反查用。
        """
        try:
            from preprocessor import expand_tokens, scan_directives

            macro_table, func_macros, _, _, _, clean, clean_to_raw = scan_directives(
                source,
                self._ctx.rules_dir,
                source_path=path,
                search_dirs=self._ctx.include_dirs,
                predefined=None,
                undefine=None,
            )
            if macro_table:
                # 语句体宏展开宏体（check 需宏体语义，不要保真注释锚——否则宏体
                # 不可分析 + 注释锚被 W002 误报）
                clean, _, regions, exp_to_clean = expand_tokens(
                    clean,
                    macro_table,
                    rules_dir=self._ctx.rules_dir,
                    func_macros=func_macros,
                )
                exp_to_raw = [
                    clean_to_raw[c - 1] if 1 <= c <= len(clean_to_raw) else None
                    for c in exp_to_clean
                ]
                spans = self._macro_line_spans(clean, regions, clean_to_raw)
                return clean, exp_to_raw, spans
            return clean, clean_to_raw, []
        except Exception:  # noqa: BLE001 — 展开失败回退原文（lint 兜底）
            return source, [], []

    @staticmethod
    def _macro_line_spans(text: str, regions: list, clean_to_raw: list) -> list:
        """宏区间（字符偏移）→ 展开行区间（诊断宏归因用）。

        regions 来自 expand_tokens（铺宏体）：offset/end_offset 为展开
        文本的绝对字符偏移。行号由行首偏移表二分求得；call_line = 宏调用
        原文行（clean 坐标经行表回源；不可映射为 None）。
        """
        line_starts = [0]
        line_starts += [i + 1 for i, ch in enumerate(text) if ch == "\n"]
        out = []
        for r in regions:
            start = bisect.bisect_right(line_starts, r["offset"])
            tail = r["end_offset"] - 1 if r["end_offset"] > r["offset"] else r["offset"]
            end = bisect.bisect_right(line_starts, tail)
            src_line = r.get("src_line")
            call_line = (
                clean_to_raw[src_line - 1]
                if isinstance(src_line, int) and 1 <= src_line <= len(clean_to_raw)
                else None
            )
            out.append(
                {
                    "name": r["name"],
                    "line_start": start,
                    "line_end": end,
                    "call_line": call_line,
                }
            )
        return out


class ModuleIndexer:
    """递归发现：入口 → 实例化链（+ 目录内关键字文本扫描兜底）→ 单元索引。

    每个新文件交给 `FilePipeline` 解析（构造注入），产物收进
    `ctx.memo`（按路径）与 `ctx.module_index`（首个定义者优先：同名单元在多个
    文件重复定义时先发现的赢，与既有语义一致）。`seen` 由调用方跨入口共享，
    重复入口不重复解析。
    """

    def __init__(self, ctx: StructureCtx, pipeline: FilePipeline) -> None:
        self._ctx = ctx
        self._pipeline = pipeline

    # ── 递归发现 ──

    def discover(self, path: str, seen: set[str]) -> None:
        if path in self._ctx.memo or path in seen:
            return
        seen.add(path)
        fr = self._pipeline.parse_file(path)
        self._ctx.memo[path] = fr
        for name, info in fr.modules.items():
            if name not in self._ctx.module_index:
                self._ctx.module_index[name] = info
        for site in fr.inst_sites:
            mod_name = self._ctx.inst_module_name(site)
            if not mod_name or mod_name in self._ctx.module_index:
                continue
            def_path = self._find_module_file(mod_name, path)
            if def_path:
                self.discover(def_path, seen)

    # ── 模块定义文件查找 ──

    def _find_module_file(self, module_name: str, from_file: str) -> str | None:
        """按名字找模块定义文件：同名文件优先，再查目录内单元名索引。

        扩展名与模块关键字来自语言包结构协议（file_exts / module_keyword）。
        """
        exts = self._ctx.exts()
        dirs = [os.path.dirname(from_file)] + self._ctx.include_dirs
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for ext in exts:
                cand = os.path.join(d, module_name + ext)
                if os.path.isfile(cand):
                    return cand
        if not self._ctx.rule("module_keyword"):
            return None
        for d in dirs:
            if not os.path.isdir(d):
                continue
            hit = self._dir_module_index(d).get(module_name)
            if hit:
                return hit
        return None

    def _dir_module_index(self, d: str) -> dict[str, str]:
        """目录内「单元名 → 定义文件」文本索引（按目录建一次，随会话失效）。

        关键字与扩展名来自语言包结构协议。此前是逐次查找重读整个目录（未命中时
        整目录被反复读），审计 `performance.file-read-in-loop`；建表后同一目录每
        文件至多读一次。名字位形态用引擎级 `IDENT_RE`（与 lexer 的 id 扫描同源，
        不另写字符类）；查询名来自 AST，必满配该形态，故键查得全。

        未命中的目录缓存空表——同一次运行内文件不变，不重复扫。
        """
        cache = self._ctx.dir_module_files
        cached = cache.get(d)
        if cached is not None:
            return cached
        table: dict[str, str] = {}
        keyword = self._ctx.rule("module_keyword")
        exts = self._ctx.exts()
        pattern = re.compile(
            r"\b" + re.escape(keyword) + r"\s+(" + IDENT_RE.pattern + r")"
        )
        try:
            names = sorted(os.listdir(d))
        except OSError:
            cache[d] = table
            return table
        for fname in names:
            if not any(fname.endswith(ext) for ext in exts):
                continue
            fp = os.path.join(d, fname)
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            for name in pattern.findall(text):
                # 先发现者优先（与 discover 的单元索引语义一致）
                table.setdefault(name, fp)
        cache[d] = table
        return table



