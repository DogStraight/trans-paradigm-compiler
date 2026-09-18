"""structure.py — 结构提取底座（elaboration）：单元/实例/端口/驱动的跨文件索引。

定位：**通用设施**，不是检查专用——消费方包括各 postpass/插件（它们读底座
注入的 `context.extra`：`module_index` / `inst_sites` / 信号图）。

语言无关边界：本模块**零语言知识**。单元/实例化的规则名、节点字段、文件
扩展名、关键字全部来自语言包声明的 `[structure] protocol`
（grammar/<lang>/base/_structure.toml）；未声明该段 = 该语言不支持结构提取，
调用方退化为单文件 lint + analyze（`_has_structure` 判定）。

三层（ADR-0008）：
  层 1  单元注册表——递归发现（实例化链 + 目录内关键字文本扫描兜底）+
        端口/参数/宽度声明形态提取
  层 2  端口连接展开——实例化点连接 vs 端口声明（W104 类检查的基础）
  层 3  信号驱动/负载图——连续/过程赋值驱动源 + 层次驱动穿透（W105 类检查的基础）

本类由 `analyzer/checker.py` 的 ProjectChecker 继承（门面只做检查编排与诊断
汇总，不碰结构提取细节）。实例字段（`_memo` / `_module_index` / `_signal_graph`
/ `_struct` / `_fields`）由门面 `__init__` 统一初始化——与检查共享同一对象。

Doc: analyzer/semantic_checks.md（跨文件语义检查）
"""

import bisect
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from core.define import Node
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
    # 展开行（0-based，索引展开后文本）→ 原始源行（1-based）；None = 不可
    # 映射（include 拼接行）；空表 = 未展开（诊断行号原样）。两级复合：
    # scan_directives（原始→clean）+ expand_tokens（clean→展开后）。
    line_map: list = field(default_factory=list)
    # 宏区间（语义展开）：[{name, line_start, line_end, call_line}]——宏体铺进
    # 文本的展开行区间（1-based）+ 宏调用原文行（1-based，不可映射 None）；
    # 诊断归因（加 "macro" 字段）反查用。顿路径（非 semantic）空表。
    macro_regions: list = field(default_factory=list)


# ── 常量表达式求值 ────────────────────────────────────────

# 只认中性形态（数字/括号/四则/比较——多数语言同形）；位运算、逻辑运算、
# 标识符、三目一律不可判：那是语言层的事（语言包侧另有求值器，如 verilog 的
# latch_check/_latch_check._eval_const）。
_CONST_TOK_RE = re.compile(r"[ ]*(?:(\d+)|(<=|>=|==|!=|\+|-|\*|/|%|\(|\)|<|>))")
_CMP_OPS = ("<", "<=", ">", ">=", "==", "!=")


def _tokenize_const(text: str) -> list[tuple[str, str]] | None:
    """常量表达式 → token 列表；出现未声明的字符 → None（不可判）。"""
    toks: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        m = _CONST_TOK_RE.match(text, pos)
        if m is None:
            return None
        pos = m.end()
        toks.append(("num", m.group(1)) if m.group(1) is not None else ("op", m.group(2)))
    return toks


def _eval_const_expr(text: str) -> bool | None:
    """纯常量表达式求值 → 布尔｜None（不可判，保守）。

    显式递归下降，**不用 `eval`**：源码文本进 `eval` 是 RCE 面（与语言包侧
    `_eval_const` 同理由）；且 Python 词法与目标语言不一致——`!`/`&&`/`||`
    在 Python 里是语法错，只会静默落回不可判，写进白名单反而看不出真实可达面。

    语法：表达式 := 比较；比较 := 加减 (比较符 加减)*；加减 := 乘除
    (('+'|'-') 乘除)*；乘除 := 一元 (('*'|'/'|'%') 一元)*；一元 := ('+'|'-')*
    基本项；基本项 := 数字 | '(' 表达式 ')'。
    """
    toks = _tokenize_const(text.strip())
    if toks is None:
        return None
    pos = 0

    def peek() -> tuple[str, str] | None:
        return toks[pos] if pos < len(toks) else None

    def eat() -> tuple[str, str]:
        nonlocal pos
        tok = toks[pos]
        pos += 1
        return tok

    def parse_primary() -> float | None:
        cur = peek()
        if cur is None:
            return None
        kind, tok = cur
        if tok == "(":
            eat()
            val = parse_cmp()
            nxt = peek()
            if val is None or nxt is None or nxt[1] != ")":
                return None
            eat()
            return val
        if kind == "num":
            eat()
            return float(tok)
        return None

    def parse_unary() -> float | None:
        cur = peek()
        if cur is not None and cur[1] in ("+", "-"):
            sign = eat()[1]
            val = parse_unary()
            if val is None:
                return None
            return -val if sign == "-" else val
        return parse_primary()

    def parse_term() -> float | None:
        left = parse_unary()
        if left is None:
            return None
        while True:
            cur = peek()
            if cur is None or cur[1] not in ("*", "/", "%"):
                return left
            op = eat()[1]
            right = parse_unary()
            if right is None or (op in ("/", "%") and right == 0):
                return None
            if op == "*":
                left *= right
            elif op == "/":
                left /= right
            else:
                left %= right

    def parse_sum() -> float | None:
        left = parse_term()
        if left is None:
            return None
        while True:
            cur = peek()
            if cur is None or cur[1] not in ("+", "-"):
                return left
            op = eat()[1]
            right = parse_term()
            if right is None:
                return None
            left = left + right if op == "+" else left - right

    def parse_cmp() -> float | None:
        left = parse_sum()
        if left is None:
            return None
        while True:
            cur = peek()
            if cur is None or cur[1] not in _CMP_OPS:
                return left
            op = eat()[1]
            right = parse_sum()
            if right is None:
                return None
            ok = {
                "<": left < right,
                "<=": left <= right,
                ">": left > right,
                ">=": left >= right,
                "==": left == right,
                "!=": left != right,
            }[op]
            left = 1.0 if ok else 0.0  # 布尔参与后续比较：真=1 / 假=0

    val = parse_cmp()
    if val is None or pos != len(toks):
        return None
    return bool(val)


# ── 引擎 ─────────────────────────────────────────────────


class _StructureBase:
    """结构提取底座（elaboration）。字段初始化见 ProjectChecker.__init__。"""

    # 门面（ProjectChecker）持有的共享状态与共享组件入口——底座各方法直接
    # 访问，初始化在门面 __init__ / _ensure_shared（两者共用同一对象）。
    _memo: dict[str, FileResult]
    _module_index: dict[str, ModuleInfo]
    _rules_dir: str
    _include_dirs: list[str]
    _expand_macros: bool
    _ensure_shared: Callable[[], dict]

    def _refresh_structure(self) -> None:
        """load_all 后刷新结构协议（_structure_cfg 模块变量被推入真实值）。"""
        self._struct = _structure_cfg or {}
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
        # parse 全在展开后文本上）。无宏文件空表零影响。同时接收行映射
        # （展开行→原始源行）与宏区间表（展开行区间，诊断归因用）。
        if self._expand_macros:
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
                self._rules_dir,
                source_path=path,
                search_dirs=self._include_dirs,
                predefined=None,
                undefine=None,
            )
            if macro_table:
                # 语句体宏展开宏体（check 需宏体语义，不要保真注释锚——否则宏体
                # 不可分析 + 注释锚被 W002 误报）
                clean, _, regions, exp_to_clean = expand_tokens(
                    clean,
                    macro_table,
                    rules_dir=self._rules_dir,
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
        """层 3：全工程信号驱动/负载图（ADR-0008，含实例树层次展开）。

        汇总所有文件的端口连接展开 + 连续赋值目标，按 **(模块, 信号名)**
        建立（2026-08-29 修复：跨模块同名信号隔离——真实语料 ice40 的
        SB_LUT4/ICESTORM_LC/SB_MAC16 各有端口 O，按裸信号名合并会误报
        多驱动）：
            (module, signal) → {"drivers": [驱动源标识], "loads": [..]}
        驱动源三类（语言知识全部来自配置协议）：
        - 实例 output/inout 端口连接该信号 → **穿透**到被实例化模块
          内部对该端口的真实驱动源（2026-08-31 P2.7 层 3 扩展）：
          模块内 assign/过程赋值目标 == 端口名 → "路径:assign#N"；
          更深实例 output 连接 == 端口名 → 递归穿透；无驱动（悬空
          output）→ 不计驱动源。路径形如 "top/u_a/u_b"。
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
        # P2.7 层 3：实例树层次展开底座（per-module 实例表 + 驱动穿透）
        module_insts = self._build_module_insts()
        # (模块, 端口) → 裸驱动源列表（无路径前缀：assign#N / proc /
        # inst:{实例名}:{子端口}）——路径由调用方拼，跨实例化点可复用缓存
        src_cache: dict = {}

        def _port_sources(module: str, port: str, seen: set) -> tuple[list | None, bool]:
            """模块内端口驱动源（裸源，无路径）→ (sources, 模块是否定义)。

            遍历**目标模块子树**（ModuleInfo.node）而非文件全树——同文件
            多模块同名 assign 不能污染（2026-08-31 探针暴露）。返回
            (None, False) = 模块未定义（黑盒，调用方兜底原子源）；
            ([], True) = 模块定义但端口悬空（无驱动 → 不记）。
            """
            cache_key = (module, port)
            if cache_key in src_cache:
                return src_cache[cache_key]
            if module in seen:
                return [], True
            seen = seen | {module}
            info = self._module_index.get(module)
            if info is None or info.node is None:
                return None, False
            fr = self._fr_by_module.get(module)
            if fr is None or fr.ast is None:
                return None, False
            mnode = info.node
            sources: list[str] = []
            # 1) 模块内连续赋值目标 == 端口（限定模块子树）
            if assign_rule:
                idx = 0
                for node in self._iter_nodes(mnode):
                    if node.node_name != assign_rule:
                        continue
                    idx += 1
                    if not self._in_active_generate(fr, node):
                        continue
                    for tgt in self._iter_assign_targets(
                        node, target_field, extras_field, extra_target_field
                    ):
                        sig = self._render_subtree(tgt)
                        if sig == port:
                            sources.append(f"assign#{idx}")
            # 2) 模块内更深实例 output/inout 连接 == 端口 → 子引用（递归）
            for inst_name, inst_mod, conn in module_insts.get(module, []):
                if conn is None:
                    continue
                for pname, sig in conn.connects.items():
                    if sig != port:
                        continue
                    dirn = ""
                    im = self._module_index.get(inst_mod)
                    if im is not None and pname in im.ports:
                        dirn = im.ports[pname].direction
                    if dirn in out_dirs or dirn in inout_dirs:
                        sources.append(f"inst:{inst_name}:{pname}")
            # 3) 模块内过程赋值目标 == 端口（always 驱动 output 端口）
            proc_rules = self._struct.get("proc_assign_rules") or []
            proc_blocks = self._struct.get("proc_block_rules") or []
            if proc_rules and proc_blocks:
                for node in self._iter_nodes(mnode):
                    if node.node_name not in proc_rules:
                        continue
                    if not self._in_active_generate(fr, node):
                        continue
                    tgt = getattr(node, target_field, None)
                    sig = self._render_subtree(tgt) if isinstance(tgt, Node) else ""
                    if sig == port:
                        sources.append("proc")
            uniq: list[str] = []
            for s in sources:
                if s not in uniq:
                    uniq.append(s)
            result = (uniq, True)
            src_cache[cache_key] = result
            return result

        def _resolve_port_drivers(
            module: str, port: str, path: str, seen: set
        ) -> tuple[list, bool]:
            """端口驱动源 → (完整路径标识列表, 模块是否定义)（层 3 穿透）。

            裸源拼实例链路径；inst 子引用递归——子模块黑盒（未定义）→
            保守记实例源；子模块悬空（无驱动）→ 不记（悬空 output 不
            驱动，对齐 Verilator elaboration 后视角）。
            """
            sources, defined = _port_sources(module, port, seen)
            if sources is None:
                return [], defined
            out: list[str] = []
            for src in sources:
                if src.startswith("inst:"):
                    _, iname, iport = src.split(":", 2)
                    inst_mod = ""
                    for i_name, i_mod, _ in module_insts.get(module, []):
                        if i_name == iname:
                            inst_mod = i_mod
                            break
                    if inst_mod:
                        sub, sub_defined = _resolve_port_drivers(
                            inst_mod, iport, f"{path}/{iname}", seen
                        )
                        if sub:
                            out.extend(sub)
                        elif not sub_defined:
                            out.append(f"{path}/{iname}")  # 黑盒保守
                        # 悬空（sub 空且 defined）→ 不记
                else:
                    out.append(f"{path}:{src}")
            return out, defined

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
            # 过程赋值驱动（always/initial 内阻塞/非阻塞赋值目标）——
            # 2026-08-29 注入器暴露：`always @* y = c;` + `assign y = d;`
            # 双驱动此前漏检（信号图只收连续赋值 + 实例 output）。
            # 对标 Verilator MULTIDRIVEN（过程 + 连续驱动同判）。
            # 驱动源 = **过程块**（同一 always 内多赋值算一个驱动者——
            # 如 always @(posedge clk) 内分支赋值同一 reg 合法；不同块或
            # always+assign 才冲突）。
            proc_rules = self._struct.get("proc_assign_rules") or []
            proc_blocks = self._struct.get("proc_block_rules") or []
            if proc_rules and proc_blocks and fr.ast is not None:
                # 一次遍历建 赋值节点 → 所属过程块节点 映射
                # （blk 可为 None：赋值不在任何过程块内，如模块级 assign）
                assign_block: dict[int, Node | None] = {}
                todo: list[tuple[Node | None, Node | None]] = [(fr.ast, None)]
                while todo:
                    node, blk = todo.pop()
                    if node is None:
                        continue
                    if node.node_name in proc_blocks:
                        blk = node
                    if node.node_name in proc_rules:
                        assign_block[id(node)] = blk
                    for child in node.iter_children():
                        todo.append((child, blk))
                # 按 过程块 → 信号 收集驱动（块内多赋值去重为同一驱动源）
                block_sigs: dict[int, tuple[Node, set[str]]] = {}
                for node in self._iter_nodes(fr.ast):
                    if node.node_name not in proc_rules:
                        continue
                    blk = assign_block.get(id(node))
                    if blk is None:
                        continue
                    if not self._in_active_generate(fr, node):
                        continue
                    tgt = getattr(node, target_field, None)
                    sig = self._render_subtree(tgt) if isinstance(tgt, Node) else ""
                    if not sig or not _is_signal_expr(sig):
                        continue
                    if id(blk) not in block_sigs:
                        block_sigs[id(blk)] = (blk, set())
                    block_sigs[id(blk)][1].add(sig)
                block_idx = 0
                for blk_node, sigs in block_sigs.values():
                    block_idx += 1
                    mod_name = self._module_of(fr, blk_node)
                    inst_ref = f"{os.path.basename(fr.path)}:always#{block_idx}"
                    for sig in sigs:
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
                        # P2.7 层 3：驱动源穿透到模块内部真实源（带实例路径）。
                        # 穿透成功 → 用穿透源；悬空 output（模块定义但无
                        # 驱动）→ 不记（对齐 Verilator elaboration）；黑盒
                        # （模块未定义）→ 原子源兜底（保守）。
                        pen, pen_defined = _resolve_port_drivers(
                            conn.module_name, port_name, inst_ref, set()
                        )
                        if pen:
                            for s in pen:
                                if s not in entry["drivers"]:
                                    entry["drivers"].append(s)
                        elif not pen_defined:
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


    # ── P2.7 层 3 扩展：实例树层次展开底座（2026-08-31） ──

    def _build_module_insts(self) -> dict:
        """{模块名: [(实例名, 被实例化模块名, PortConnection)]}——per-module
        实例表（层 3 驱动穿透用）。

        从全工程 connections（层 2 展开）按实例化点所属模块归组——实例
        化点 = 连接表达式所在模块（_module_of 语义）。模块内实例顺序
        保持连接展开顺序（assign#N 对齐用不上，此处仅穿透）。
        """
        out: dict[str, list] = {}
        for fr in self._memo.values():
            for conn in fr.connections:
                mod_name = self._module_of(fr, conn.inst_node)
                if not mod_name:
                    continue
                out.setdefault(mod_name, []).append(
                    (conn.inst_name, conn.module_name, conn)
                )
        return out


    @property
    def _fr_by_module(self) -> dict:
        """{模块名: FileResult}——驱动穿透查模块定义文件（惰性构建）。"""
        cache = getattr(self, "_fr_by_module_cache", None)
        if cache is None:
            cache = {}
            for fr in self._memo.values():
                for mname in (fr.modules or {}):
                    cache.setdefault(mname, fr)
            self._fr_by_module_cache = cache
        return cache


    def _in_active_generate(self, fr, node) -> bool:
        """节点是否在**选中**的 generate 互斥分支内（对齐 Verilator）。

        Verilator 在 V3Param::visit(AstGenIf) 求值 generate 条件，未选中
        分支的 AST 物理删除（deleteTree）——后续多驱动检测只看到选中分支
        的驱动源。tpc 不展开 generate，信号图平铺收集会同时计入互斥分支
        （如 picorv32 `generate if (ENABLE_MUL) 实例 else assign`：两个
        分支都驱动 pcpi_mul_ready → 8 条 W105 假阳性，Verilator 0 报）。

        实现：per-file 预计算 {id(node): bool}（一次 DFS 维护 generate
        条件栈，O(树)）；查询 O(1)。此前每节点全树扫描定位 generate +
        _subtree_contains 判定分支是 O(节点×树) 平方级——picorv32 过程
        赋值驱动收集（2026-08-29）后单次 check 103s，预计算后恢复秒级。
        """
        if fr.ast is None or node is None:
            return True
        memo = getattr(fr, "_gen_active_map", None)
        if memo is None:
            memo = self._precompute_generate_active(fr)
            fr._gen_active_map = memo
        return memo.get(id(node), True)


    def _precompute_generate_active(self, fr) -> dict:
        """per-file 预计算 {id(node): bool}——节点是否在选中的 generate 分支。

        单栈迭代（无递归）：栈元素 = (node, stack, params)。普通节点标记
        活性后子节点入栈；GenerateBlock 内 IfBlock/ElseIfBlock 求值条件，
        then/else 分支以「追加/弹出活性」展开入栈（else-if 链循环）。
        节点活性 = 所在分支全部选中。O(树)，查询 O(1)。纯迭代实现避免
        深 AST/嵌套 generate 递归爆栈（picorv32 等大文件，2026-08-29）。
        """
        active: dict[int, bool] = {}
        decl_rule = self._rule("module_decl_rule")
        root = fr.ast
        if root is None:
            return active

        def expand_if(ifb, stack: list, params: dict, todo: list) -> None:
            """IfBlock/ElseIfBlock：条件求值，then/else 分支展开入栈。

            else-if 链：外层条件为假时进入链，链内条件独立求值但活性
            叠加外层"假"（FAST=0 且 MUL=1 → MUL 分支选中）。条件不可判
            → 整块按当前活性展开（保守）。纯迭代无递归。
            """
            # 链入口：当前栈 + 之前所有 else-if 的条件取假（首块无前置）
            base = list(stack)
            cur = ifb
            while isinstance(cur, Node) and cur.node_name in (
                "IfBlock", "ElseIfBlock"
            ):
                cond_val = self._eval_gen_cond(cur, params)
                then_node = getattr(cur, "then_stmt", None)
                chain = getattr(cur, "else_chain", None)
                if cond_val is None:
                    todo.append((cur, base, params))
                    return
                # then 分支：base（外层全假）+ 本条件真
                todo.append((then_node, base + [cond_val], params))
                if isinstance(chain, Node) and chain.node_name in (
                    "IfBlock", "ElseIfBlock"
                ):
                    # 进入链：外层再加"本条件假"
                    base = base + [not cond_val]
                    cur = chain
                    continue
                # 最终 else：base（外层全假）+ 本条件假
                todo.append((chain, base + [not cond_val], params))
                return

        todo = []
        for child in root.iter_children():
            todo.append((child, [], {}))
        while todo:
            node, stack, params = todo.pop()
            if node is None:
                continue
            active[id(node)] = all(stack)
            if node.node_name == "GenerateBlock":
                for sub in getattr(node, "sub_node", None) or []:
                    if not isinstance(sub, Node):
                        continue
                    if sub.node_name in ("IfBlock", "ElseIfBlock"):
                        # GenerateBlock 内的条件分支：求值展开（互斥）
                        expand_if(sub, stack, params, todo)
                    else:
                        todo.append((sub, stack, params))
                continue
            # 普通 IfBlock/ElseIfBlock（always 内 if 等）：非 generate
            # 条件——按普通子节点遍历（不展开互斥，活性继承当前栈）
            if node.node_name == decl_rule:
                info = self._module_index.get(
                    getattr(getattr(node, "module_name", None), "content", "")
                    or ""
                )
                params2: dict[str, str] = {}
                if info is not None:
                    params2 = {p.name: p.value_expr for p in info.params.values()}
                for child in node.iter_children():
                    todo.append((child, [], params2))
                continue
            for child in node.iter_children():
                todo.append((child, stack, params))
        return active


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
        # 一元 ! 参数（`!OUTPUT_FIFO_ENABLE` 等，2026-08-31 补：axis_fifo
        # generate else 分支此前不可判 → 双分支全 active → 9 条 W105 误报）
        m = re.fullmatch(r"!\s*([A-Za-z_][A-Za-z0-9_]*)", text)
        if m and m.group(1) in params:
            v = params[m.group(1)].strip()
            if v.isdigit():
                return int(v) == 0
            return None
        # 含运算的纯常量表达式（`1+0` / `2*3<7` 等）→ 显式求值（不用 eval，
        # 见 _eval_const_expr）；标识符/位运算/逻辑运算等一律不可判 → None
        return _eval_const_expr(text)


    def _module_of(self, fr, node) -> str:
        """节点所属模块名（所在 ModuleDecl；文件级/未命中 → ""）。

        per-file 预计算映射（2026-08-31 性能修复）：一次 DFS 建立
        {id(节点): 模块名}，查询 O(1)。此前逐节点全树扫描
        `_subtree_contains` 是 O(N×树) 平方级——elaboration 层 3
        `_build_signal_graph` 对每个 assign/过程块/实例节点调用，picorv32
        实测 76 次调用 7.5s（占单次 check 21.6s 的 35%，profile 定位）。
        与 `_in_active_generate` 预计算同款手法（2026-08-29 先例：
        103s → 秒级）。映射挂在 fr 上，check() 每文件重建（AST 不变，
        一次构建全文件复用）。
        """
        if fr.ast is None or node is None:
            return ""
        memo = getattr(fr, "_module_map", None)
        if memo is None:
            memo = self._precompute_module_map(fr)
            fr._module_map = memo
        return memo.get(id(node), "")


    def _precompute_module_map(self, fr) -> dict:
        """per-file 预计算 {id(node): 模块名}（一次 DFS，O(树)）。

        栈元素 = (node, 当前模块名)；ModuleDecl 进入时更新模块名，
        子树内节点继承。嵌套模块罕见（SV 特性），内层覆盖外层名——
        与 _iter_nodes_with_module 同语义。
        """
        mapping: dict[int, str] = {}
        decl_rule = self._rule("module_decl_rule")
        name_field = self._field("module_name")
        root = fr.ast
        if root is None:
            return mapping
        stack = [(root, "")]
        while stack:
            node, mod = stack.pop()
            if node.node_name == decl_rule:
                nm = getattr(node, name_field, None)
                mod = nm.content if isinstance(nm, Node) else ""
            mapping[id(node)] = mod
            for child in node.iter_children():
                stack.append((child, mod))
        return mapping


    @staticmethod
    def _subtree_contains(root: Node | None, target: Node) -> bool:
        """target 是否在 root 子树内（含自身）。root 为 None 时 False。"""
        if root is None:
            return False
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
            # 渲染失败 → 空串：调用方（条件/宽度提取）按"拿不到文本 = 不可判"
            # 保守处理，不影响正确性；此处不报错是设计（非静默错乱）。
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
        return [n for n in _StructureBase._iter_nodes(root) if n.node_name == node_name]


    def _inst_module_name(self, site: Node) -> str:
        mn = getattr(site, self._field("module_name"), None)
        if isinstance(mn, Node) and mn.content:
            return mn.content
        return ""
