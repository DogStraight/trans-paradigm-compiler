"""pipeline — 管线编排（run_pipeline_on_source）。

从 tests/e2e/run_pipeline.py 提取的正式管线核心（CLI 与测试共用）：
CLI（main.py）与测试共用，故移入正式包，wheel 安装后 CLI 可用。

与测试版的差异：
- 去掉 sys.path 插入 / stdout 重定向（测试环境特定）
- samples 输出目录从 input_path 推断（不依赖 __file__ 定位 tests/）
- collect_callbacks 改为可选导入（非 verilog 语言不硬依赖 typed_ports 插件）
"""

import os
import sys
from typing import Any

from core.define import Node

# ── 预加载组件（确保组件插件先于引擎插件注册）──
from core.plugin_loader import load_all_components

load_all_components()

# ── 词法 / 语法 / 配置 ──
from lexer import Lexer, pre_scan, load_pre_scan_config
from parser import Parser, setup_grammar
from core.define import (
    ParseError,
    GrammarRulesRegister,
    DEFAULT_RULES_DIR,
    DEFAULT_EXT_DIRS,
)
from core.config_registry import ConfigRegistry
from core.utils import ensure_dir, save_json
from parser.rule_selector import RuleSelector

# ── 分析器 ──
from analyzer import AnalysisTraversal

# ── 语言配置（组件系统收集）──
from core.plugin_loader import get_component_mapping_config

# 变换回调收集（typed_ports 插件，可选——非 verilog 语言无此插件时跳过）
try:
    from grammar.verilog.plugins.typed_ports._mapping import collect_callbacks
except ImportError:  # pragma: no cover — 非 verilog 语言包
    def collect_callbacks(scope):  # type: ignore[no-redef]
        return {}

# ── 变换器 ──
from transform import AstTransformer, collect_extra_asts
from transform.normalizer import normalize_ast

# ── 渲染器 ──
from renderer.renderer import Renderer
from renderer.inline_comment import restore_comments, restore_line_comments

# ── Linter（前置语法检查）──
from linter.scanner import LinterScanner

# ── 预处理器（可选）──
from preprocessor import (
    scan_directives,
    expand_tokens,
    protect_and_reverse,
    restore_condition_blocks,
)

# 模块级共享状态：rules/lexer/renderer/transformer 按 rules_dir 缓存，避免重复初始化
_PIPELINE_SHARED: dict = {}


# ── Core Pipeline ──
def format_generated(
    content: str, rules: Any, lexer: Any, rule_selector: Any = None, rules_dir: str = None
) -> str:
    """对生成文本跑 formatter（缩进/品类对齐/实例端口对齐）。

    复用管线已加载的 rules/lexer/rule_selector，避免重复初始化；失败时不阻断管线，
    返回原文本并记录 warning（formatter 是增强 pass，不影响主流程）。
    """
    try:
        from grammar.verilog.plugins.formatter.boundary import BoundaryScanner
        from grammar.verilog.plugins.formatter import (
            build_engine,
            split_port_close_lines,
            split_inst_tail_lines,
        )

        # 先拆粘连行（端口尾行 + 参数化实例化尾行），再扫描，避免 contexts 错位
        lines = split_port_close_lines(content.split("\n"))
        lines = split_inst_tail_lines(lines)
        split_content = "\n".join(lines)

        scanner = BoundaryScanner(rules, lexer)
        contexts = scanner.scan(split_content)
        # 语法感知 wrap：复用管线已加载的 rule_selector/rules 建 parser（不重复
        # 初始化），wrap 对超宽行现场解析拿 AST 断点；失败回退文本启发式
        parser = None
        try:
            from parser.parser_core import Parser
            parser = Parser(
                rules_dir=rules_dir, rules=rules, rule_selector=rule_selector, log_file=""
            )
            parser.lexer = lexer  # wrap 的 AST 断点用它现场解析超宽行
        except Exception:  # noqa: BLE001 — parser 可选，构建失败回退启发式
            parser = None
        engine = build_engine(parser=parser)
        formatted = engine.run(lines, contexts)
        return "\n".join(l.rstrip() for l in formatted)
    except Exception as e:  # noqa: BLE001 — 增强 pass 失败不阻断管线
        print(f"[formatter] skipped ({e})", file=sys.stderr)
        return content


def _load_pipeline_defaults() -> dict:
    """从 tpc_config.json 读 pipeline 段，作为 run_pipeline_on_source 参数默认值。

    项目级默认参数（tpc_config.json 提供） + 调用方/CLI 显式传入覆盖
    （None 表示未传，取配置默认）。找不到配置/解析失败时回退空 dict。
    """
    import json
    from core.config_registry import _find_user_config

    path = _find_user_config()
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg.get("pipeline", {})
        except Exception:
            pass
    return {}


def run_pipeline_on_source(
    source: str,
    input_path: str | None = None,
    out_dir: str | None = None,
    expand_macros: bool | None = None,
    inline_comments: bool | None = None,
    quiet: bool | None = None,
    analyzer_enabled: bool | None = None,
    transform_enabled: bool | None = None,
    renderer_enabled: bool | None = None,
    stage: str | None = None,
    no_lint: bool | None = None,
    parse_enabled: bool | None = None,
    format_output: bool | None = None,
    expand_enhanced: bool = True,
    rules_dir: str = DEFAULT_RULES_DIR,
    ext_dirs: list[str] | None = DEFAULT_EXT_DIRS,
    include_dirs: list[str] | None = None,
    predefined: dict[str, str] | None = None,
    undefine: set[str] | None = None,
    check_idempotent: bool | None = None,
    enable_line_comment_restore: bool = True,
) -> dict[str, Any]:
    """
    Core pipeline: process Verilog source and return results.

    Returns dict:
        success: bool
        output: str (generated Verilog code, if renderer enabled)
        ast: Any (final AST)
        error: str (error message if any)
        parser: Parser instance (for comment table, etc.)
    """

    # 默认参数来源：tpc_config.json 的 pipeline 段（项目级默认值），
    # 调用方显式传入时覆盖（None 表示"未传，取配置默认"）。
    _cfg = _load_pipeline_defaults()

    # rules_dir 相对路径 → 基于项目根解析为绝对路径。wheel 安装后从任意
    # 目录运行，相对路径（如 "grammar/verilog"）会解析到 CWD 下失败。
    # 项目根 = 本包目录的父级（editable=项目根 / wheel=site-packages，
    # grammar 作为包在 site-packages/grammar/，两种模式均可定位）。
    if rules_dir and not os.path.isabs(rules_dir):
        _pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rules_dir = os.path.join(_pkg_root, rules_dir)
    if ext_dirs:
        ext_dirs = [
            d if os.path.isabs(d) else os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), d
            )
            for d in ext_dirs
        ]

    if out_dir is None:
        out_dir = _cfg.get("out_dir")
    if expand_macros is None:
        expand_macros = _cfg.get("expand_macros", False)
    if inline_comments is None:
        inline_comments = _cfg.get("inline_comments", False)
    if quiet is None:
        quiet = _cfg.get("quiet", False)
    if analyzer_enabled is None:
        analyzer_enabled = _cfg.get("analyzer", True)
    if transform_enabled is None:
        transform_enabled = _cfg.get("transform", True)
    if renderer_enabled is None:
        renderer_enabled = _cfg.get("renderer", True)
    if stage is None:
        stage = _cfg.get("stage")
    if no_lint is None:
        no_lint = not _cfg.get("lint", True)
    if include_dirs is None:
        include_dirs = _cfg.get("include_dirs")
    if predefined is None:
        predefined = _cfg.get("define")
    if undefine is None:
        undefine = _cfg.get("undefine")
    if check_idempotent is None:
        check_idempotent = _cfg.get("check_idempotent", True)
    if parse_enabled is None:
        parse_enabled = _cfg.get("parse", True)

    # Quiet-aware logger
    def _log(msg: str, *args, **kwargs) -> None:
        if not quiet:
            print(msg, *args, **kwargs)

    result = {
        "success": False,
        "output": "",
        "ast": None,
        "extra_asts": [],
        "error": "",
        "parser": None,
        "idempotent": True,
    }

    original_source = source

    # format_output 默认 True：展开/保留两条路都过 formatter（boundary 已支持
    # curly 块，增强语法缩进可格式化）；显式传 False 可关。
    if format_output is None:
        format_output = _cfg.get("format_output", True)

    # Determine output directory
    if out_dir is None:
        if input_path and "samples" in input_path:
            parts = input_path.replace("\\", "/").split("/")
            group = (
                "normal"
                if "normal" in parts
                else ("errors" if "errors" in parts else "normal")
            )
            # 从 input_path 推断 samples 目录（.../samples/<group>/ref/file.v）
            # 不依赖 __file__ 定位 tests/（pipeline 是正式包，不在 tests 下）。
            samples_dir = os.path.dirname(os.path.dirname(os.path.dirname(input_path)))
            out_dir = os.path.join(samples_dir, group)
        else:
            out_dir = None  # 无合法输出目录，跳过文件写入
    if out_dir:
        gen_dir = os.path.join(out_dir, "gen")
        ast_dir = os.path.join(out_dir, "ast")
        sym_dir = os.path.join(out_dir, "symbols")
        lex_dir = os.path.join(out_dir, "lex")
        ensure_dir(gen_dir)
        ensure_dir(ast_dir)
        ensure_dir(sym_dir)
        ensure_dir(lex_dir)
        cb_dir = os.path.join(out_dir, "trans_callback")
        ensure_dir(cb_dir)
    else:
        gen_dir = ast_dir = sym_dir = lex_dir = cb_dir = None

    # Base filename for intermediate files
    if input_path:
        stem = os.path.splitext(os.path.basename(input_path))[0]
        base_name = stem.replace("ref_", "")
    else:
        base_name = "input"

    gen_file = os.path.join(gen_dir, f"gen_{base_name}.v") if gen_dir else None
    ast_json = os.path.join(ast_dir, f"{base_name}.json") if ast_dir else None
    sym_json = os.path.join(sym_dir, f"{base_name}.json") if sym_dir else None
    cb_json = os.path.join(cb_dir, f"{base_name}.json") if cb_dir else None

    # ---- Stage: 配置加载（只执行一次，缓存后跳过）----
    if "_config_loaded" not in _PIPELINE_SHARED:
        ConfigRegistry.load_all(
            rules_dir,
            ext_dirs=ext_dirs,
            plugins_dir=os.path.join(rules_dir, "plugins"),
        )
        _PIPELINE_SHARED["_config_loaded"] = True

    # ---- Stage: 宏指令扫描（仅提取宏表，不展开字符串）----
    macro_table = {}
    func_macros = {}
    placeholders = {}
    directive_lines = []
    restore_stack = None
    tpc_src_map = None
    if expand_macros:
        macro_table, func_macros, _, placeholders, directive_lines, source = scan_directives(
            source,
            rules_dir,
            source_path=input_path,
            search_dirs=include_dirs,
            predefined=predefined,
            undefine=undefine,
        )
        _log(f"[preprocessor] macros defined: {len(macro_table)}")
        # 扫描 clean_source 中 tpc marker 的源行号（restore_line_comments 对被吞
        # marker 用已渲染 marker 分段线性插值定位，需要源行号锚点）
        tpc_src_map = {}
        for _i, _l in enumerate(source.split("\n"), 1):
            if "// <tpc:" in _l:
                _start = _l.find("tpc:")
                _end = _l.find(">", _start)
                if _end > _start:
                    tpc_src_map[_l[_start:_end]] = _i

    # ---- Stage: Shared pipeline context (rules, lexer, renderer, etc.) ----
    # 所有按 rules_dir 可复用的组件集中初始化并缓存
    ctx = _PIPELINE_SHARED
    if rules_dir not in ctx:

        # 语法规则（含 EXT 注入）
        rules = setup_grammar(
            rules_dir, GrammarRulesRegister.get_default(), ext_dirs=ext_dirs
        )
        stmt_names = [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        rule_selector = RuleSelector(rules, stmt_names)
        lexer = Lexer(rules_dir=rules_dir, ext_dirs=ext_dirs)
        linter = LinterScanner(rules_dir=rules_dir, ext_dirs=ext_dirs)
        renderer = Renderer(rules_dir=rules_dir)
        ctx[rules_dir] = {
            "rules": rules,
            "rule_selector": rule_selector,
            "lexer": lexer,
            "linter": linter,
            "renderer": renderer,
        }
    shared = ctx[rules_dir]
    rules = shared["rules"]
    rule_selector = shared["rule_selector"]
    lexer = shared["lexer"]
    linter = shared["linter"]
    renderer = shared["renderer"]

    # ---- Stage: 预处理（宏展开，纯文本，在 lex 之前）----
    if expand_macros and macro_table:
        source, restore_stack = expand_tokens(
            source, macro_table, func_macros=func_macros
        )
        _log("[preprocessor] macros expanded")

    # ---- Stage: Lexical analysis（tokenize 预处理后的文本）----
    tokens = lexer.tokenize(source)
    if not quiet and lex_dir:
        tok_path = os.path.join(lex_dir, f"tokens_{base_name}.txt")
        with open(tok_path, "w", encoding="utf-8") as f:
            for tok in tokens:
                f.write(f"{tok.column},{tok.line}:{tok.type} {tok.content}\n")
    _log(f"[lexer] tokens: {len(tokens)}")
    if stage == "lex":
        result["success"] = True
        return result

    # ---- Stage: Pre-scan ----
    pre_scan_config = load_pre_scan_config(rules_dir)
    pre_symbols = pre_scan(source, pre_scan_config)
    if pre_symbols:
        _log(f"[prescan] symbols: {len(pre_symbols)}")

    # ---- Stage: Lint（前置语法检查，失败时截断管线）----
    if not no_lint:
        lint_errors = linter.scan(source)
        if lint_errors:
            for err in lint_errors:
                _log(
                    f"[linter] {err.message} at L{err.range[0].line}:{err.range[0].character}"
                )
            result["error"] = f"lint failed: {len(lint_errors)} error(s)"
            return result

    # parse 开关：只 lint 不 parse（如 lint 指令：lint 通过即成功）
    if not parse_enabled:
        result["success"] = True
        return result

    # ---- Stage: Parse ----
    # Instantiate Parser with injected rules and rule_selector
    parser = Parser(
        rules_dir=rules_dir,
        pre_symbols=pre_symbols,
        rules=rules,
        rule_selector=rule_selector,
    )
    parser.pre_hints = pre_scan_config.get("hints", {})

    # No longer need to manually assign parser.grammar_rules,
    # statement_rule_names, rule_selector, or atomic_rules — all are set internally.

    try:
        ast = parser.parse(tokens)
    except ParseError as e:
        result["error"] = str(e)
        print(f"\n[parser] Parse failed:\n{e}", file=sys.stderr)
        return result
    if ast is None:
        result["error"] = "parser returned None"
        _log("[parser] parse failed")
        return result
    result["parser"] = parser
    if stage == "parse":
        result["success"] = True
        result["ast"] = ast
        return result

    # ---- Stage: AST normalization ----
    ast = normalize_ast(ast)

    if not quiet and ast_json:
        save_json(ast.dump(), ast_json, "ast", log_fn=_log)

    # ---- Stage: Semantic analysis ----
    # expand_enhanced=False：保留增强语法路径（格式化增强源码），跳过
    # analyze/transform——增强节点（TypedPortDecl/TypeDecl 等）不经 expand，
    # 由 renderer 的增强节点 layout 直出；render() 内部自带 normalize。
    analyzer = None
    scope = None
    if not expand_enhanced:
        _log("[pipeline] enhanced-expansion disabled: preserving enhanced syntax")
    elif analyzer_enabled:
        analyzer = AnalysisTraversal(rules)
        ast = analyzer.analyze(ast)
        if analyzer.root_scope is None:
            _log("[analyzer] warning: no scope produced")
        else:
            if not quiet:
                if sym_json:
                    save_json(
                        analyzer.root_scope.to_dict(), sym_json, "symbols", log_fn=_log
                    )
                # Dump transform callbacks (_ref_callbacks) to trans_callback/
                callbacks = collect_callbacks(analyzer.root_scope)
                if callbacks and cb_json:
                    save_json(callbacks, cb_json, "callbacks", log_fn=_log)
            _log(f"[symbols] {len(analyzer.all_symbols)} symbols")
        if analyzer.has_errors:
            for d in analyzer.diagnostics:
                _log(f"[analyzer] {d}")
            if any(d.level == "error" for d in analyzer.diagnostics):
                result["error"] = "; ".join(
                    str(d) for d in analyzer.diagnostics if d.level == "error"
                )
                _log("[analyzer] semantic errors, stopping pipeline")
                return result
        scope = analyzer.root_scope
    else:
        _log("[analyzer] skipped")
    if stage == "analyze":
        result["success"] = True
        result["ast"] = ast
        return result

    # ---- Stage: AST transform ----
    if transform_enabled and analyzer is not None and scope is not None:
        # 通过共享上下文传递规则和映射配置，插件自动从注册表实例化
        mp_entries, rv_entries = get_component_mapping_config()
        mapping_cfg: dict = {}
        mapping_cfg.update(mp_entries)
        mapping_cfg.update(rv_entries)
        AstTransformer.set_shared("rules", rules)
        AstTransformer.set_shared("mapping_cfg", mapping_cfg)
        transformer = AstTransformer()

        # 一次 transform 完成：映射表构建 + 配置变换
        ast = transformer.transform(ast, scope)

        # 收集变换统计
        parts = []
        for plugin in transformer.plugins:
            if hasattr(plugin, "stats"):
                s = plugin.stats
                for k, v in s.items():
                    if v:
                        parts.append(f"{k}={v}")
        if parts:
            _log(f"[transform] {' '.join(parts)}")
    elif transform_enabled:
        _log("[transform] skipped (analyzer=None or no scope)")
    if stage == "transform":
        result["success"] = True
        result["ast"] = ast
        return result

    # ---- Stage: 收集虚拟逻辑分发（TransformPlugin 已将提取结果存入共享上下文）----
    extra_asts: list[tuple[str, Node]] = collect_extra_asts()
    if extra_asts:
        _log(f"[remapper] extracted {len(extra_asts)} extra AST(s)")

    # ---- Stage: Render ----
    if renderer_enabled:
        content = renderer.render(ast)

        # Restore directive lines（副作用指令 define/undef/include）
        if directive_lines:
            content = "\n".join(directive_lines) + "\n" + content
            _log(f"[preprocessor] directives restored: {len(directive_lines)}")

        # Inline comment restoration（锚点匹配，宏展开后亦可用）
        # 展开路径（restore_stack 非空）→ only_tpc：宏 marker（`/*<tpc:macro:N>*/`）
        # 是块注释，被 parse_token 收集进 _comment_anchors，不回注则
        # protect_and_reverse 找不到 marker 宏调用丢失（tv80 `TV80DELAY`）；
        # 但普通注释锚点漂移（渲染行号与源行号错位）会错插到端口/参数行——
        # 只回插 tpc，普通注释跳过（与 line 通道 only_tpc 语义对称）。
        if inline_comments:
            anchors = getattr(parser, "_comment_anchors", None)
            if anchors:
                content, n = restore_comments(content, anchors)
                _log(f"[comments] inline anchor restoration: {n} items")
        elif restore_stack:
            anchors = getattr(parser, "_comment_anchors", None)
            if anchors:
                content, n = restore_comments(content, anchors, only_tpc=True)
                _log(f"[comments] tpc inline marker restoration: {n} items")

        # Line comment restoration（列表结构内被 production skip 吞掉的注释，渲染后回插）
        # 变换路径（expand_enhanced=True 增强展开）禁用普通注释恢复：变换改变
        # 了代码结构（impl → ModuleInst、类型端口 → 具体端口），源行号/锚点必然
        # 漂移，恢复会误匹配拆坏注释行（如含 `spi.slave` 的注释从 `.` 处劈开）。
        # 但 tpc marker（宏/条件块还原依赖）是唯一性插值定位、
        # 不依赖锚点窗口，仍必须回插——否则 protect_and_reverse 找不到 marker，
        # 宏还原失效。有宏/条件块时降级 only_tpc，无则整个跳过。
        line_anchors = getattr(parser, "_line_comment_anchors", None)
        if line_anchors and enable_line_comment_restore:
            content, n = restore_line_comments(
                content, line_anchors, tpc_src_map=tpc_src_map
            )
            _log(f"[comments] line anchor restoration: {n} items")
        elif line_anchors and (restore_stack or placeholders):
            content, n = restore_line_comments(
                content, line_anchors, tpc_src_map=tpc_src_map, only_tpc=True
            )
            _log(f"[comments] tpc marker restoration: {n} items")

        # Reverse macro protection — 必须放在 line-comment restore 之后：
        # 宏 line 锚（`// <tpc:macro:N>`）是注释行，被 parser 收集进
        # line_comment_anchors，由 restore_line_comments 回插后 protect_and_reverse
        # 才能定位 marker 并替换为整行原文残片。
        if restore_stack:
            content = protect_and_reverse(
                content,
                restoration_stack=restore_stack,
            )
            _log("[preprocessor] macros reversed")

        # Restore conditional blocks（占位注释 → 原文，inactive 分支 + 块边界）
        # 必须放在 line-comment restore 之后：占位符 `// <tpc:cond:N>` 本身是注释行，
        # 可能被 production skip 吞掉并记入 line_comment_anchors，若先 restore 条件块、
        # 后回插行注释，占位符会被再次插回而残留。
        if placeholders:
            content = restore_condition_blocks(content, placeholders)
            _log(f"[preprocessor] condition blocks restored: {len(placeholders)}")

        # 格式化生成文本（缩进/品类对齐/实例端口对齐）— 所有 restore 之后，
        # 让 formatter 处理还原后的最终文本（含宏/条件块原文），便于与 ref 对比。
        if format_output and content.strip():
            content = format_generated(
                content, rules, lexer, rule_selector=shared["rule_selector"], rules_dir=rules_dir
            )
            _log("[formatter] formatted output")

        # Write output (no header — gen file is raw content for clean diffing)
        if gen_file:
            with open(gen_file, "w", encoding="utf-8") as f:
                f.write(content)
            _log(f"[output] {gen_file}")

        # Render extra ASTs as separate files
        extra_outputs: list[tuple[str, str]] = []
        for out_name, extra_root in extra_asts:
            extra_content = renderer.render(extra_root)
            # extra 输出与主输出一致：format 开启时也过 formatter（否则品类对齐/
            # 缩进/换行不统一，trans/ 的包装模块文件格式与主文件不一致）
            if format_output and extra_content.strip():
                extra_content = format_generated(
                    extra_content, rules, lexer,
                    rule_selector=shared["rule_selector"], rules_dir=rules_dir,
                )
            extra_outputs.append((out_name, extra_content))
            if gen_dir:
                extra_file = os.path.join(gen_dir, f"gen_{out_name}.v")
                with open(extra_file, "w", encoding="utf-8") as f:
                    f.write(extra_content)
                _log(f"[remapper] extra output: {extra_file}")

        result["output"] = content
        result["ast"] = ast
        result["extra_asts"] = extra_asts
        result["extra_outputs"] = extra_outputs
        result["success"] = True

        # ── 幂等检查：生成文本再走一遍管线（跳过 analyze/transform——生成
        # 文本已是最终形态，无增强节点），能再次被完整管线稳定处理则幂等。
        # 替代后置 lint：完整 parser 比 linter 近似更强，且不依赖 linter 对
        # format 后文本的行号/结构敏感。坏文本（如 `= =` 或缺分号）
        # 会导致第二遍 parse truncated → idempotent=False。
        # 展开路径（宏表/占位符/指令行任一非空）跳过：宏体替换、条件分支选择、
        # 注释锚点漂移都使第二遍内容必然不同——那是展开语义，不是幂等性问题。
        # 只有非展开路径（内容应稳定）才检查。
        expanded_path = bool(macro_table) or bool(func_macros) or bool(
            placeholders
        ) or bool(directive_lines)
        if check_idempotent and not expanded_path and content.strip():
            _log("[idempotency] re-running pipeline on generated output")
            r2 = run_pipeline_on_source(
                source=content,
                input_path=input_path,
                quiet=True,
                expand_macros=expand_macros,
                inline_comments=inline_comments,
                analyzer_enabled=False,
                transform_enabled=False,
                renderer_enabled=True,
                no_lint=True,
                format_output=format_output,
                expand_enhanced=False,
                rules_dir=rules_dir,
                ext_dirs=ext_dirs,
                include_dirs=include_dirs,
                predefined=predefined,
                undefine=undefine,
                check_idempotent=False,
            )
            p2 = r2.get("parser")
            truncated = bool(getattr(p2, "_parse_truncated", False)) if p2 else True
            result["idempotent"] = bool(r2.get("success")) and not truncated
            if not result["idempotent"]:
                _log(
                    f"[idempotency] FAIL: output re-parse "
                    f"truncated={truncated} success={r2.get('success')}"
                )
        else:
            result["idempotent"] = True
    else:
        print("[renderer] skipped")
        result["ast"] = ast

    return result
