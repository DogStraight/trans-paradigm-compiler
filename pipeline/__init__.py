"""pipeline — 管线编排（run_pipeline_on_source）。

从 tests/e2e/run_pipeline.py 提取的正式管线核心（CLI 与测试共用）：
CLI（main.py）与测试共用，故移入正式包，wheel 安装后 CLI 可用。

与测试版的差异：
- 去掉 sys.path 插入 / stdout 重定向（测试环境特定）
- samples 输出目录从 input_path 推断（不依赖 __file__ 定位 tests/）
- collect_callbacks 改为可选导入（非 verilog 语言不硬依赖 typed_ports 插件）

结构：run_pipeline_on_source 是入口（参数解析 + 阶段编排），每个管线阶段
拆为独立函数（_stage_*），共享状态通过 _PipelineContext 传递。
analyze/transform 由编排调度执行（ADR-0007，pipeline/schedule.py）：
归一化后按命名 schedule 跑 pass 序列（缺省 [analyze, transform]），
时点由序列器分配（order/after/声明序），冲突 fail-fast。
Doc: docs/api.md（管线 API：run_pipeline_on_source/format_output）
Doc: docs/decisions/0007-pipeline-schedule.md（编排调度）
"""

import os
import sys
from dataclasses import dataclass, field
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

# ── 编排调度（ADR-0007）──
from .schedule import (
    PassState,
    PassDecl,
    build_schedules,
    DEFAULT_SCHEDULE_NAME,
)

# ── 语言配置（组件系统收集）──
from core.plugin_loader import get_component_mapping_config

# 变换回调收集（typed_ports 插件，可选——非 verilog 语言无此插件时跳过）
try:
    from grammar.verilog.plugins.typed_ports._mapping import collect_callbacks
except ImportError:  # pragma: no cover — 非 verilog 语言包
    def collect_callbacks(scope):  # type: ignore[no-redef]
        del scope  # fallback：非 verilog 语言无回调，签名与真实函数保持一致
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


# ── 管线共享上下文 ──────────────────────────────────────────
@dataclass
class _PipelineContext:
    """管线阶段间共享的状态（替代单函数内的局部变量堆叠）。"""

    source: str
    input_path: str | None
    rules_dir: str
    ext_dirs: list[str] | None
    quiet: bool | None
    stage: str | None
    expand_macros: bool | None
    inline_comments: bool | None
    analyzer_enabled: bool | None
    transform_enabled: bool | None
    renderer_enabled: bool | None
    no_lint: bool | None
    parse_enabled: bool | None
    format_output: bool | None
    expand_enhanced: bool
    include_dirs: list[str] | None
    predefined: dict[str, str] | None
    undefine: set[str] | None
    check_idempotent: bool | None
    enable_line_comment_restore: bool
    fidelity: str = "full"
    """保真度分级（ADR-0006 阶段 5）：full 完全重排 / keep_blank 保留空行。"""

    # 输出目录（由 _resolve_output_paths 填充）
    gen_dir: str | None = None
    ast_dir: str | None = None
    sym_dir: str | None = None
    lex_dir: str | None = None
    cb_dir: str | None = None
    base_name: str = "input"
    gen_file: str | None = None
    ast_json: str | None = None
    sym_json: str | None = None
    cb_json: str | None = None

    # 共享组件（由 _ensure_shared 填充）
    rules: Any = None
    rule_selector: Any = None
    lexer: Any = None
    linter: Any = None
    renderer: Any = None

    # 宏/预处理状态
    macro_table: dict = field(default_factory=dict)
    func_macros: dict = field(default_factory=dict)
    placeholders: dict = field(default_factory=dict)
    directive_lines: list = field(default_factory=list)
    restore_stack: Any = None
    tpc_src_map: dict = field(default_factory=dict)

    # 结果
    result: dict = field(default_factory=dict)

    def log(self, msg: str, *args, **kwargs) -> None:
        if not self.quiet:
            print(msg, *args, **kwargs)


# ── Core Pipeline ──
def format_generated(
    content: str, rules: Any, lexer: Any, rule_selector: Any = None, rules_dir: str | None = None
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


def _load_pipeline_defaults() -> dict[str, Any]:
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


# ── 阶段函数 ──────────────────────────────────────────────

def _resolve_paths(ctx: _PipelineContext) -> None:
    """解析输出目录与中间文件路径。"""
    if ctx.input_path and "samples" in ctx.input_path:
        parts = ctx.input_path.replace("\\", "/").split("/")
        group = (
            "normal"
            if "normal" in parts
            else ("errors" if "errors" in parts else "normal")
        )
        # 从 input_path 推断 samples 目录（.../samples/<group>/ref/file.v）
        # 不依赖 __file__ 定位 tests/（pipeline 是正式包，不在 tests 下）。
        samples_dir = os.path.dirname(os.path.dirname(os.path.dirname(ctx.input_path)))
        ctx.gen_dir = os.path.join(samples_dir, group, "gen")
        ctx.ast_dir = os.path.join(samples_dir, group, "ast")
        ctx.sym_dir = os.path.join(samples_dir, group, "symbols")
        ctx.lex_dir = os.path.join(samples_dir, group, "lex")
        ctx.cb_dir = os.path.join(samples_dir, group, "trans_callback")
    else:
        ctx.gen_dir = ctx.ast_dir = ctx.sym_dir = ctx.lex_dir = ctx.cb_dir = None

    for d in (ctx.gen_dir, ctx.ast_dir, ctx.sym_dir, ctx.lex_dir, ctx.cb_dir):
        if d:
            ensure_dir(d)

    if ctx.input_path:
        stem = os.path.splitext(os.path.basename(ctx.input_path))[0]
        ctx.base_name = stem.replace("ref_", "")
    else:
        ctx.base_name = "input"

    ctx.gen_file = os.path.join(ctx.gen_dir, f"gen_{ctx.base_name}.v") if ctx.gen_dir else None
    ctx.ast_json = os.path.join(ctx.ast_dir, f"{ctx.base_name}.json") if ctx.ast_dir else None
    ctx.sym_json = os.path.join(ctx.sym_dir, f"{ctx.base_name}.json") if ctx.sym_dir else None
    ctx.cb_json = os.path.join(ctx.cb_dir, f"{ctx.base_name}.json") if ctx.cb_dir else None


def _ensure_shared(ctx: _PipelineContext) -> None:
    """初始化/复用按 rules_dir 缓存的共享组件。"""
    # 配置加载（只执行一次，缓存后跳过）
    if "_config_loaded" not in _PIPELINE_SHARED:
        ConfigRegistry.load_all(
            ctx.rules_dir,
            ext_dirs=ctx.ext_dirs,
            plugins_dir=os.path.join(ctx.rules_dir, "plugins"),
        )
        _PIPELINE_SHARED["_config_loaded"] = True

    if ctx.rules_dir not in _PIPELINE_SHARED:
        # 语法规则（含 EXT 注入）
        rules = setup_grammar(
            ctx.rules_dir, GrammarRulesRegister.get_default(), ext_dirs=ctx.ext_dirs
        )
        stmt_names = [
            n
            for n, r in rules.items()
            if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
        ]
        rule_selector = RuleSelector(rules, stmt_names)
        lexer = Lexer(rules_dir=ctx.rules_dir, ext_dirs=ctx.ext_dirs)
        linter = LinterScanner(rules_dir=ctx.rules_dir, ext_dirs=ctx.ext_dirs)
        renderer = Renderer(rules_dir=ctx.rules_dir)
        # 组件映射配置按 rules_dir 缓存：get_component_mapping_config 读全局
        # _loaded_components，而其他语言包的 setup_grammar 会 clear+重载它——
        # 复用本缓存时若再读全局会拿到别的语言包组件（typed_ports mapping 丢失）。
        mp_entries, rv_entries = get_component_mapping_config()
        mapping_cfg: dict = {}
        mapping_cfg.update(mp_entries)
        mapping_cfg.update(rv_entries)
        # 编排调度按 rules_dir 缓存（同一原因：声明来自 _loaded_components）。
        schedules = build_schedules()
        _PIPELINE_SHARED[ctx.rules_dir] = {
            "rules": rules,
            "rule_selector": rule_selector,
            "lexer": lexer,
            "linter": linter,
            "renderer": renderer,
            "mapping_cfg": mapping_cfg,
            "schedules": schedules,
        }
    shared = _PIPELINE_SHARED[ctx.rules_dir]
    ctx.rules = shared["rules"]
    ctx.rule_selector = shared["rule_selector"]
    ctx.lexer = shared["lexer"]
    ctx.linter = shared["linter"]
    ctx.renderer = shared["renderer"]


def _stage_macro_scan(ctx: _PipelineContext) -> None:
    """宏指令扫描（仅提取宏表，不展开字符串）。"""
    if not ctx.expand_macros:
        return
    (
        ctx.macro_table,
        ctx.func_macros,
        _,
        ctx.placeholders,
        ctx.directive_lines,
        ctx.source,
    ) = scan_directives(
        ctx.source,
        ctx.rules_dir,
        source_path=ctx.input_path,
        search_dirs=ctx.include_dirs,
        predefined=ctx.predefined,
        undefine=ctx.undefine,
    )
    ctx.log(f"[preprocessor] macros defined: {len(ctx.macro_table)}")
    # 扫描 clean_source 中 tpc marker 的源行号（restore_line_comments 对被吞
    # marker 用已渲染 marker 分段线性插值定位，需要源行号锚点）
    for _i, _l in enumerate(ctx.source.split("\n"), 1):
        if "// <tpc:" in _l:
            _start = _l.find("tpc:")
            _end = _l.find(">", _start)
            if _end > _start:
                ctx.tpc_src_map[_l[_start:_end]] = _i


def _stage_expand(ctx: _PipelineContext) -> None:
    """宏展开（纯文本，在 lex 之前）。"""
    if ctx.expand_macros and ctx.macro_table:
        ctx.source, ctx.restore_stack = expand_tokens(
            ctx.source, ctx.macro_table, func_macros=ctx.func_macros
        )
        ctx.log("[preprocessor] macros expanded")


def _stage_lex(ctx: _PipelineContext) -> list:
    """词法分析（tokenize 预处理后的文本）。"""
    tokens = ctx.lexer.tokenize(ctx.source)
    if not ctx.quiet and ctx.lex_dir:
        tok_path = os.path.join(ctx.lex_dir, f"tokens_{ctx.base_name}.txt")
        with open(tok_path, "w", encoding="utf-8") as f:
            for tok in tokens:
                f.write(f"{tok.column},{tok.line}:{tok.type} {tok.content}\n")
    ctx.log(f"[lexer] tokens: {len(tokens)}")
    return tokens


def _stage_prescan(ctx: _PipelineContext) -> tuple[Any, Any]:
    """Pre-scan（符号预检测，供 parser 提示）。"""
    pre_scan_config = load_pre_scan_config(ctx.rules_dir)
    pre_symbols = pre_scan(ctx.source, pre_scan_config)
    if pre_symbols:
        ctx.log(f"[prescan] symbols: {len(pre_symbols)}")
    return pre_scan_config, pre_symbols


def _stage_lint(ctx: _PipelineContext) -> bool:
    """前置语法检查（失败时截断管线）。返回是否通过。"""
    if ctx.no_lint:
        return True
    lint_errors = ctx.linter.scan(ctx.source)
    if lint_errors:
        for err in lint_errors:
            ctx.log(
                f"[linter] {err.message} at L{err.range[0].line}:{err.range[0].character}"
            )
        ctx.result["error"] = f"lint failed: {len(lint_errors)} error(s)"
        return False
    return True


def _stage_parse(
    ctx: _PipelineContext, pre_scan_config: Any, pre_symbols: Any, tokens: list
) -> Any | None:
    """解析。返回 AST（失败返回 None）。"""
    parser = Parser(
        rules_dir=ctx.rules_dir,
        pre_symbols=pre_symbols,
        rules=ctx.rules,
        rule_selector=ctx.rule_selector,
    )
    parser.pre_hints = pre_scan_config.get("hints", {})
    try:
        ast = parser.parse(tokens)
    except ParseError as e:
        ctx.result["error"] = str(e)
        print(f"\n[parser] Parse failed:\n{e}", file=sys.stderr)
        return None
    if ast is None:
        ctx.result["error"] = "parser returned None"
        ctx.log("[parser] parse failed")
        return None
    # 截断 = 失败（不是软成功）：lint 门禁是启发式的，变异/畸形输入可能漏过
    # lint 后进 parser；此时 parser 软失败只返回部分 AST，若继续渲染会**静默
    # 丢内容还报 success=True**（fuzz 发现的真实缺陷，2026-08-22）。
    # formatter wrap pass 与幂等检查本就认 _parse_truncated，入口应一致。
    if getattr(parser, "_parse_truncated", False):
        ctx.result["error"] = "parse truncated (unconsumed tokens) — pipeline stopped"
        ctx.log("[parser] parse truncated, stopping pipeline")
        return None
    ctx.result["parser"] = parser
    return ast


def _run_pass_analyze(state: "PassState") -> None:
    """kind=analyze pass：跑一轮 AnalysisTraversal，覆盖 scope。

    error 级诊断 → 置 ctx.result["error"] 并抛 _ScheduleStop（停调度停管线）。
    """
    ctx = state.ctx
    analyzer = AnalysisTraversal(ctx.rules)
    state.ast = analyzer.analyze(state.ast)
    state.analyzer = analyzer
    state.scope = analyzer.root_scope
    if analyzer.root_scope is None:
        ctx.log("[analyzer] warning: no scope produced")
    else:
        if not ctx.quiet:
            if ctx.sym_json:
                save_json(
                    analyzer.root_scope.to_dict(), ctx.sym_json, "symbols",
                    log_fn=ctx.log
                )
            # Dump transform callbacks (_ref_callbacks) to trans_callback/
            callbacks = collect_callbacks(analyzer.root_scope)
            if callbacks and ctx.cb_json:
                save_json(callbacks, ctx.cb_json, "callbacks", log_fn=ctx.log)
        ctx.log(f"[symbols] {len(analyzer.all_symbols)} symbols")
    if analyzer.has_errors:
        for d in analyzer.diagnostics:
            ctx.log(f"[analyzer] {d}")
        if any(d.level == "error" for d in analyzer.diagnostics):
            ctx.result["error"] = "; ".join(
                str(d) for d in analyzer.diagnostics if d.level == "error"
            )
            ctx.log("[analyzer] semantic errors, stopping pipeline")
            raise _ScheduleStop()


def _run_pass_transform(state: "PassState") -> None:
    """kind=transform pass：跑一轮 AstTransformer（消费 scope，None 跳过）。"""
    ctx = state.ctx
    if state.scope is None:
        ctx.log("[transform] skipped (no scope)")
        return
    # 通过共享上下文传递规则和映射配置，插件自动从注册表实例化
    # mapping_cfg 从按 rules_dir 的缓存读（_ensure_shared 已算好），
    # 不依赖全局 _loaded_components（可能被其他语言包污染）。
    mapping_cfg = _PIPELINE_SHARED[ctx.rules_dir]["mapping_cfg"]
    AstTransformer.set_shared("rules", ctx.rules)
    AstTransformer.set_shared("mapping_cfg", mapping_cfg)
    transformer = AstTransformer()
    state.transformer = transformer

    # 一次 transform 完成：映射表构建 + 配置变换
    state.ast = transformer.transform(state.ast, state.scope)

    # 收集变换统计
    parts = []
    for plugin in transformer.plugins:
        if hasattr(plugin, "stats"):
            s = plugin.stats
            for k, v in s.items():
                if v:
                    parts.append(f"{k}={v}")
    if parts:
        ctx.log(f"[transform] {' '.join(parts)}")


def _run_pass_custom(state: "PassState", decl: "PassDecl") -> None:
    """kind=custom pass：执行插件 handler（fn(state) -> None）。"""
    assert decl.handler is not None
    decl.handler(state)


class _ScheduleStop(Exception):
    """内部控制流：pass 请求终止调度（analyze 报 error 级诊断）。"""


_LEGACY_PASS_STAGES = ("analyze", "transform")


def _run_schedule(
    ctx: _PipelineContext, ast: Any, scope: Any, schedule_name: str
) -> tuple[Any, Any]:
    """按命名 schedule 执行 pass 序列（ADR-0007）。返回 (ast, scope)。

    - expand_enhanced=False → 跳过整个调度（保留增强语法直渲）。
    - 开关过滤：analyzer_enabled=False 滤 kind=analyze；transform_enabled
      同理。
    - stage 命中 pass 名 → 执行该 pass 后截断（legacy "analyze"/
      "transform" 按内置 pass 名匹配）。
    - _ScheduleStop → 截断调度（error 已写入 ctx.result）。
    """
    if not ctx.expand_enhanced:
        ctx.log("[pipeline] enhanced-expansion disabled: preserving enhanced syntax")
        return ast, None

    schedules = _PIPELINE_SHARED[ctx.rules_dir]["schedules"]
    if schedule_name not in schedules:
        raise ValueError(
            f"[pipeline] schedule '{schedule_name}' 未声明"
            f"（可用: {', '.join(sorted(schedules)) or '(空)'}）"
        )
    state = PassState(ast=ast, scope=scope, ctx=ctx)
    for decl in schedules[schedule_name]:
        if decl.kind == "analyze" and not ctx.analyzer_enabled:
            ctx.log(f"[pipeline] pass '{decl.name}' skipped (analyze disabled)")
            continue
        if decl.kind == "transform" and not ctx.transform_enabled:
            ctx.log(f"[pipeline] pass '{decl.name}' skipped (transform disabled)")
            continue
        ctx.log(f"[pipeline] pass: {decl.name}")
        try:
            if decl.kind == "analyze":
                _run_pass_analyze(state)
            elif decl.kind == "transform":
                _run_pass_transform(state)
            else:
                _run_pass_custom(state, decl)
        except _ScheduleStop:
            break
        if ctx.stage == decl.name:
            break
    return state.ast, state.scope


def _restore_comments(ctx: _PipelineContext, content: str, parser: Any) -> str:
    """注释回插（inline + line + 宏还原 + 条件块）。"""
    # Inline comment restoration（锚点匹配，宏展开后亦可用）
    # 展开路径（restore_stack 非空）→ only_tpc：宏 marker（`/*<tpc:macro:N>*/`）
    # 是块注释，被 parse_token 收集进 _comment_anchors，不回注则
    # protect_and_reverse 找不到 marker 宏调用丢失（tv80 `TV80DELAY`）；
    # 但普通注释锚点漂移（渲染行号与源行号错位）会错插到端口/参数行——
    # 只回插 tpc，普通注释跳过（与 line 通道 only_tpc 语义对称）。
    if ctx.inline_comments:
        anchors = getattr(parser, "_comment_anchors", None)
        if anchors:
            content, n = restore_comments(content, anchors)
            ctx.log(f"[comments] inline anchor restoration: {n} items")
    elif ctx.restore_stack:
        anchors = getattr(parser, "_comment_anchors", None)
        if anchors:
            content, n = restore_comments(content, anchors, only_tpc=True)
            ctx.log(f"[comments] tpc inline marker restoration: {n} items")

    # Line comment restoration（列表结构内被 production skip 吞掉的注释，渲染后回插）
    # 变换路径（expand_enhanced=True 增强展开）禁用普通注释恢复：变换改变
    # 了代码结构（impl → ModuleInst、类型端口 → 具体端口），源行号/锚点必然
    # 漂移，恢复会误匹配拆坏注释行（如含 `spi.slave` 的注释从 `.` 处劈开）。
    # 但 tpc marker（宏/条件块还原依赖）是唯一性插值定位、
    # 不依赖锚点窗口，仍必须回插——否则 protect_and_reverse 找不到 marker，
    # 宏还原失效。有宏/条件块时降级 only_tpc，无则整个跳过。
    line_anchors = getattr(parser, "_line_comment_anchors", None)
    if line_anchors and ctx.enable_line_comment_restore:
        content, n = restore_line_comments(
            content, line_anchors, tpc_src_map=ctx.tpc_src_map
        )
        ctx.log(f"[comments] line anchor restoration: {n} items")
    elif line_anchors and (ctx.restore_stack or ctx.placeholders):
        content, n = restore_line_comments(
            content, line_anchors, tpc_src_map=ctx.tpc_src_map, only_tpc=True
        )
        ctx.log(f"[comments] tpc marker restoration: {n} items")

    # Reverse macro protection — 必须放在 line-comment restore 之后：
    # 宏 line 锚（`// <tpc:macro:N>`）是注释行，被 parser 收集进
    # line_comment_anchors，由 restore_line_comments 回插后 protect_and_reverse
    # 才能定位 marker 并替换为整行原文残片。
    if ctx.restore_stack:
        content = protect_and_reverse(
            content,
            restoration_stack=ctx.restore_stack,
        )
        ctx.log("[preprocessor] macros reversed")

    # Restore conditional blocks（占位注释 → 原文，inactive 分支 + 块边界）
    # 必须放在 line-comment restore 之后：占位符 `// <tpc:cond:N>` 本身是注释行，
    # 可能被 production skip 吞掉并记入 line_comment_anchors，若先 restore 条件块、
    # 后回插行注释，占位符会被再次插回而残留。
    if ctx.placeholders:
        content = restore_condition_blocks(content, ctx.placeholders)
        ctx.log(f"[preprocessor] condition blocks restored: {len(ctx.placeholders)}")
    return content


def _check_idempotent(ctx: _PipelineContext, content: str) -> bool:
    """幂等检查：生成文本再走一遍管线（跳过 analyze/transform——生成
    文本已是最终形态，无增强节点），能再次被完整管线稳定处理则幂等。

    替代后置 lint：完整 parser 比 linter 近似更强，且不依赖 linter 对
    format 后文本的行号/结构敏感。坏文本（如 `= =` 或缺分号）
    会导致第二遍 parse truncated → idempotent=False。

    展开路径（宏表/占位符/指令行任一非空）跳过：宏体替换、条件分支选择、
    注释锚点漂移都使第二遍内容必然不同——那是展开语义，不是幂等性问题。
    只有非展开路径（内容应稳定）才检查。
    """
    expanded_path = bool(ctx.macro_table) or bool(ctx.func_macros) or bool(
        ctx.placeholders
    ) or bool(ctx.directive_lines)
    if not ctx.check_idempotent or expanded_path or not content.strip():
        return True
    ctx.log("[idempotency] re-running pipeline on generated output")
    r2 = run_pipeline_on_source(
        source=content,
        input_path=ctx.input_path,
        quiet=True,
        expand_macros=ctx.expand_macros,
        inline_comments=ctx.inline_comments,
        analyzer_enabled=False,
        transform_enabled=False,
        renderer_enabled=True,
        no_lint=True,
        format_output=ctx.format_output,
        expand_enhanced=False,
        rules_dir=ctx.rules_dir,
        ext_dirs=ctx.ext_dirs,
        include_dirs=ctx.include_dirs,
        predefined=ctx.predefined,
        undefine=ctx.undefine,
        check_idempotent=False,
    )
    p2 = r2.get("parser")
    truncated = bool(getattr(p2, "_parse_truncated", False)) if p2 else True
    idempotent = bool(r2.get("success")) and not truncated
    if not idempotent:
        ctx.log(
            f"[idempotency] FAIL: output re-parse "
            f"truncated={truncated} success={r2.get('success')}"
        )
    return idempotent


def _stage_render(ctx: _PipelineContext, ast: Any, parser: Any) -> None:
    """渲染 + 注释回插 + 格式化 + 输出 + 幂等检查。"""
    if not ctx.renderer_enabled:
        print("[renderer] skipped")
        ctx.result["ast"] = ast
        return

    content = ctx.renderer.render(ast)

    # 保真度分级（ADR-0006 阶段 5）：keep_blank 按源结构位置回插空行。
    # 在注释回插/格式化之前做——回插的空行是源空行，后续 restore 与
    # formatter 基于它继续（formatter 保留空行，不重排空行分布）。
    if ctx.fidelity == "keep_blank":
        from renderer.fidelity import keep_blank_lines

        content = keep_blank_lines(ctx.source, content)
        ctx.log("[renderer] fidelity=keep_blank: blank lines restored")

    # Restore directive lines（副作用指令 define/undef/include）
    if ctx.directive_lines:
        content = "\n".join(ctx.directive_lines) + "\n" + content
        ctx.log(f"[preprocessor] directives restored: {len(ctx.directive_lines)}")

    content = _restore_comments(ctx, content, parser)

    # 格式化生成文本（缩进/品类对齐/实例端口对齐）— 所有 restore 之后，
    # 让 formatter 处理还原后的最终文本（含宏/条件块原文），便于与 ref 对比。
    if ctx.format_output and content.strip():
        content = format_generated(
            content, ctx.rules, ctx.lexer,
            rule_selector=ctx.rule_selector, rules_dir=ctx.rules_dir,
        )
        ctx.log("[formatter] formatted output")

    # Write output (no header — gen file is raw content for clean diffing)
    if ctx.gen_file:
        with open(ctx.gen_file, "w", encoding="utf-8") as f:
            f.write(content)
        ctx.log(f"[output] {ctx.gen_file}")

    # Render extra ASTs as separate files
    extra_asts: list[tuple[str, Node]] = collect_extra_asts()
    if extra_asts:
        ctx.log(f"[remapper] extracted {len(extra_asts)} extra AST(s)")
    extra_outputs: list[tuple[str, str]] = []
    for out_name, extra_root in extra_asts:
        extra_content = ctx.renderer.render(extra_root)
        # extra 输出与主输出一致：format 开启时也过 formatter（否则品类对齐/
        # 缩进/换行不统一，trans/ 的包装模块文件格式与主文件不一致）
        if ctx.format_output and extra_content.strip():
            extra_content = format_generated(
                extra_content, ctx.rules, ctx.lexer,
                rule_selector=ctx.rule_selector, rules_dir=ctx.rules_dir,
            )
        extra_outputs.append((out_name, extra_content))
        if ctx.gen_dir:
            extra_file = os.path.join(ctx.gen_dir, f"gen_{out_name}.v")
            with open(extra_file, "w", encoding="utf-8") as f:
                f.write(extra_content)
            ctx.log(f"[remapper] extra output: {extra_file}")

    ctx.result["output"] = content
    ctx.result["ast"] = ast
    ctx.result["extra_asts"] = extra_asts
    ctx.result["extra_outputs"] = extra_outputs
    ctx.result["success"] = True
    ctx.result["idempotent"] = _check_idempotent(ctx, content)


# ── 入口 ──────────────────────────────────────────────────
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
    fidelity: str = "full",
    schedule: str | None = None,
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

    # 参数默认值解析（None → 配置默认）
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
    if format_output is None:
        format_output = _cfg.get("format_output", True)

    ctx = _PipelineContext(
        source=source,
        input_path=input_path,
        rules_dir=rules_dir,
        ext_dirs=ext_dirs,
        quiet=quiet,
        stage=stage,
        expand_macros=expand_macros,
        inline_comments=inline_comments,
        analyzer_enabled=analyzer_enabled,
        transform_enabled=transform_enabled,
        renderer_enabled=renderer_enabled,
        no_lint=no_lint,
        parse_enabled=parse_enabled,
        format_output=format_output,
        expand_enhanced=expand_enhanced,
        include_dirs=include_dirs,
        predefined=predefined,
        undefine=undefine,
        check_idempotent=check_idempotent,
        enable_line_comment_restore=enable_line_comment_restore,
        fidelity=fidelity,
    )
    ctx.result = {
        "success": False,
        "output": "",
        "ast": None,
        "extra_asts": [],
        "error": "",
        "parser": None,
        "idempotent": True,
    }

    # 输出路径 + 共享组件
    _resolve_paths(ctx)
    _ensure_shared(ctx)

    # 宏扫描 + 展开
    _stage_macro_scan(ctx)
    _stage_expand(ctx)

    # 词法
    tokens = _stage_lex(ctx)
    if stage == "lex":
        ctx.result["success"] = True
        return ctx.result

    # Pre-scan + lint
    pre_scan_config, pre_symbols = _stage_prescan(ctx)
    if not _stage_lint(ctx):
        return ctx.result
    if not parse_enabled:
        ctx.result["success"] = True
        return ctx.result

    # 解析
    ast = _stage_parse(ctx, pre_scan_config, pre_symbols, tokens)
    if ast is None:
        return ctx.result
    if stage == "parse":
        ctx.result["success"] = True
        ctx.result["ast"] = ast
        return ctx.result

    # 归一化
    ast = normalize_ast(ast)
    if not quiet and ctx.ast_json:
        save_json(ast.dump(), ctx.ast_json, "ast", log_fn=ctx.log)

    # 编排调度（ADR-0007）：schedule 内 pass 序列（analyze/transform/custom），
    # 统一锚定在归一化后；pass 内报 error 或 stage 命中即截断。
    schedule_name: str = (
        schedule
        if schedule is not None
        else _cfg.get("schedule", DEFAULT_SCHEDULE_NAME)
    )
    ast, _ = _run_schedule(ctx, ast, None, schedule_name)
    if ctx.result.get("error"):
        return ctx.result
    if stage in _LEGACY_PASS_STAGES:
        ctx.result["success"] = True
        ctx.result["ast"] = ast
        return ctx.result

    # 渲染
    _stage_render(ctx, ast, ctx.result.get("parser"))

    return ctx.result
