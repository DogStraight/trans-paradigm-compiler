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

语言无关边界：本模块**不含任何语言语义知识**——"端口名存在性/参数覆盖
合法性/字面量宽度 vs 参数化端口"等规则是 grammar/<lang>/plugins/*/
postpass 的职责。本引擎只提供跨文件上下文，经
`AnalysisTraversal._external_extra` 注入每个文件的
context.extra：`module_index`（全工程模块表）与 `inst_sites`（本文件
实例化点列表）。
"""

import os
import re
from dataclasses import dataclass, field

from core.define import Node, DEFAULT_RULES_DIR, DEFAULT_EXT_DIRS


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class ModulePort:
    """模块端口声明（声明形态，供实例化联动比对）。"""

    name: str
    direction: str = ""      # input / output / inout（旧风格裸名可空）
    width_expr: str = ""     # 宽度表达式文本（如 "DATA_W-1:0"、"7:0"；无范围空）
    decl_node: Node | None = None   # 端口声明节点（related 链定位）


@dataclass
class ModuleParam:
    """模块参数声明。"""

    name: str
    value_expr: str = ""     # 默认值表达式文本（如 "8"、"DATA_W"）


@dataclass
class ModuleInfo:
    """一个模块定义（跨文件索引条目）。"""

    name: str
    file: str
    node: Node                                       # ModuleDecl 节点（定位）
    ports: dict[str, ModulePort] = field(default_factory=dict)
    params: dict[str, ModuleParam] = field(default_factory=dict)


@dataclass
class FileResult:
    """单文件检查结果（两阶段诊断的承载）。"""

    path: str
    source: str
    lint_diags: list = field(default_factory=list)   # stage=syntax（LintDiagnostic）
    parse_ok: bool = False
    parse_error: str = ""
    ast: Node | None = None
    analyzer: object | None = None                   # AnalysisTraversal（stage=semantic）
    modules: dict[str, ModuleInfo] = field(default_factory=dict)
    inst_sites: list = field(default_factory=list)   # ModuleInst 节点


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
    ):
        self._rules_dir = rules_dir
        self._ext_dirs = ext_dirs or []
        self._include_dirs = [os.path.abspath(d) for d in (include_dirs or [])]
        self._memo: dict[str, FileResult] = {}
        self._module_index: dict[str, ModuleInfo] = {}

    # ── 共享组件 ──

    def _ensure_shared(self) -> dict:
        key = self._rules_dir
        if key in ProjectChecker._SHARED:
            return ProjectChecker._SHARED[key]
        from core.config_registry import ConfigRegistry
        from core.define import GrammarRulesRegister
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
        ConfigRegistry.load_all(rules_dir, ext_dirs=self._ext_dirs, plugins_dir=plugins_dir)
        from core.plugin_loader import load_all_components

        load_all_components()

        rules = setup_grammar(
            rules_dir, GrammarRulesRegister.get_default(), ext_dirs=self._ext_dirs
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
            "linter": LinterScanner(rules_dir=rules_dir, ext_dirs=self._ext_dirs),
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

        # 1) 递归发现 + parse（模块索引逐步建立）
        self._discover(entry, set())

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
        fr.inst_sites = self._collect_nodes(ast, "ModuleInst")
        fr.parse_ok = True
        return fr

    def _analyze(self, fr: FileResult) -> None:
        if fr.ast is None:
            return
        from analyzer import AnalysisTraversal

        shared = self._ensure_shared()
        analyzer = AnalysisTraversal(shared["rules"])
        # 跨文件上下文注入（analyze() 重建 context 后合并进 extra）
        analyzer._external_extra["module_index"] = self._module_index
        analyzer._external_extra["inst_sites"] = fr.inst_sites
        analyzer.analyze(fr.ast)
        fr.analyzer = analyzer

    # ── AST 提取（模块定义表 / 实例化点）──

    def _extract_modules(self, ast: Node, path: str) -> dict[str, ModuleInfo]:
        modules: dict[str, ModuleInfo] = {}
        for node in self._iter_nodes(ast):
            if node.node_name != "ModuleDecl":
                continue
            name_node = getattr(node, "module_name", None)
            if not isinstance(name_node, Node) or not name_node.content:
                continue
            info = ModuleInfo(name=name_node.content, file=path, node=node)
            node._file = path  # related 链跨文件定位
            self._fill_ports(info, node)
            self._fill_params(info, node)
            modules[info.name] = info
        return modules

    def _fill_ports(self, info: ModuleInfo, module_node: Node) -> None:
        """从 ModuleDecl 提取端口声明形态（ANSI 风格 + 旧风格裸名）。"""
        ports_node = self._unwrap(getattr(module_node, "ports", None))
        items = getattr(ports_node, "items", None) if ports_node else None
        if not items:
            return
        for item in items:
            if not isinstance(item, Node):
                continue
            if item.node_name == "Identifier":
                # 旧风格裸名端口（方向/类型在 body 声明，此处仅登记名字）
                if item.content:
                    info.ports[item.content] = ModulePort(name=item.content)
                continue
            # ANSI 风格：AnsiPortDecl inline 展平，item 即 AnsiInput/Output/
            # InoutDecl（防御：也可能是未展平的 AnsiPortDecl，取其 decl）
            decl = getattr(item, "decl", None)
            if isinstance(decl, Node):
                item = decl
            direction = getattr(item, "direction", "") or ""
            pr = getattr(item, "packed_range", None)
            width = self._render_subtree(pr) if isinstance(pr, Node) else ""
            dlist = getattr(item, "items", None)
            d_items = getattr(dlist, "items", None) if dlist else None
            for d in d_items or []:
                if not isinstance(d, Node):
                    continue
                dn = getattr(d, "name", None)
                if isinstance(dn, Node) and dn.content:
                    d._file = info.file
                    info.ports[dn.content] = ModulePort(
                        name=dn.content,
                        direction=direction,
                        width_expr=width,
                        decl_node=d,
                    )

    def _fill_params(self, info: ModuleInfo, module_node: Node) -> None:
        params_node = self._unwrap(getattr(module_node, "params", None))
        params = getattr(params_node, "params", None) if params_node else None
        if not params:
            return
        for p in params:
            if not isinstance(p, Node):
                continue
            p = self._unwrap(p)   # ParamDecl 可能被 optional 包装
            if not isinstance(p, Node):
                continue
            pn = getattr(p, "param_name", None)
            if not isinstance(pn, Node) or not pn.content:
                continue
            val = getattr(p, "value", None)
            info.params[pn.content] = ModuleParam(
                name=pn.content,
                value_expr=self._render_subtree(val) if isinstance(val, Node) else "",
            )

    def _render_subtree(self, node: Node) -> str:
        """把 AST 子树渲染回文本（宽度表达式等）。"""
        try:
            return self._ensure_shared()["renderer"].render(node).strip()
        except Exception:
            return ""

    # ── 模块定义文件查找 ──

    def _find_module_file(self, module_name: str, from_file: str) -> str | None:
        """按名字找模块定义文件：同名文件优先，再扫描目录文本匹配。"""
        dirs = [os.path.dirname(from_file)] + self._include_dirs
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for ext in (".v", ".sv"):
                cand = os.path.join(d, module_name + ext)
                if os.path.isfile(cand):
                    return cand
        pattern = re.compile(r"\bmodule\s+" + re.escape(module_name) + r"\b")
        for d in dirs:
            if not os.path.isdir(d):
                continue
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for fname in names:
                if not fname.endswith((".v", ".sv")):
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

    @staticmethod
    def _inst_module_name(site: Node) -> str:
        mn = getattr(site, "module_name", None)
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
                    "end": {"line": line - 1 if line else 0, "character": (col or 0) + 1},
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
