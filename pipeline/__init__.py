"""pipeline — 管线编排（run_pipeline_on_source）。

从 tests/e2e/run_pipeline.py 提取的正式管线核心（CLI 与测试共用）：
CLI（main.py）与测试共用，故移入正式包，wheel 安装后 CLI 可用。

与测试版的差异：
- 去掉 sys.path 插入 / stdout 重定向（测试环境特定）
- samples 输出目录从 input_path 推断（不依赖 __file__ 定位 tests/）

结构：run_pipeline_on_source 是入口（参数解析 + 阶段编排），每个管线阶段
拆为独立函数（_stage_*），共享状态通过 _PipelineContext 传递。
analyze/transform 由编排调度执行（pipeline/schedule.py——
编排器一个文件闭环：声明处理 + 时点排序 + _run_schedule 执行，
共享实例由本模块按 rules_dir 缓存后注入）。
Doc: api.md（管线 API：run_pipeline_on_source/format_output）
Doc: docs/pipeline_stages.md（编排调度）
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

# ── 编排调度（ADR-0007）：编排器在 schedule.py（声明+排序+执行）──
from .schedule import (
    build_schedules,
    _run_schedule,
    _LEGACY_PASS_STAGES,
    DEFAULT_SCHEDULE_NAME,
)

# ── 语言配置（组件系统收集）──
from core.plugin_loader import get_capability, get_component_mapping_config

# ── 变换器 ──
from transform import collect_extra_asts
from transform.normalizer import normalize_ast

# ── 渲染器 ──
from renderer.renderer import Renderer
from renderer.comment_restore import restore_all_comments

# ── Linter（前置语法检查）──
from linter.scanner import LinterScanner

# ── 预处理器（可选）──
from preprocessor import (
    scan_directives,
    expand_tokens,
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
    render_handler: Any = None  # 渲染插件覆盖式入口（[plugins].render 声明，
    #                           启用后直接产出最终文本，跳过主管线渲染）

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
        # formatter 能力经插件协议接入（P2.5 插件回调能力化）：组件在
        # tpc.toml [capabilities] 声明能力入口，引擎按名查找——pipeline
        # 不直接 import grammar.<lang> 插件。非 verilog 语言（无 formatter
        # 组件）时 get_capability 返回 None，跳过格式化（增强 pass）。
        formatter_entry = get_capability("formatter")
        if formatter_entry is None:
            print(
                "[formatter] skipped (capability 'formatter' not declared)",
                file=sys.stderr,
            )
            return content
        caps = formatter_entry()
        BoundaryScanner = caps["BoundaryScanner"]
        build_engine = caps["build_engine"]
        split_port_close_lines = caps["split_port_close_lines"]
        split_inst_tail_lines = caps["split_inst_tail_lines"]

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


def _resolve_render_handler(rules_dir: str):
    """解析渲染插件覆盖式入口：语言包 tpc.toml `[plugins].render` → 组件 handler。

    渲染插件 = 覆盖式输出（与 analyze/transform 叠加式不同）：产出中间
    表示（如 c4 asm_gen → 汇编文本），启用后管线渲染阶段直接调用 handler
    产出最终文本，跳过主管线源端渲染（输出唯一性）。未声明 → None（主管线
    源端渲染）。fail-fast（ADR-0003）：声明的组件不存在 / 无 [render] handler
    直接报错，不静默降级。
    """
    import tomllib
    from core.plugin_loader import get_render_handler

    tpc_path = os.path.join(rules_dir, "tpc.toml")
    if not os.path.isfile(tpc_path):
        return None
    with open(tpc_path, "rb") as f:
        meta = tomllib.load(f)
    comp_name = (meta.get("plugins") or {}).get("render")
    if not comp_name:
        return None
    handler = get_render_handler(comp_name)
    if handler is None:
        raise ValueError(
            f"[pipeline] 语言包 {rules_dir} 声明 [plugins].render = "
            f"{comp_name!r}，但该组件不存在或无 [render] handler"
        )
    return handler


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
    # 配置加载与组件构建统一按 rules_dir 键控：原 _config_loaded 是全局
    # 标记（第一个语言决定配置，后续语言跳过加载——多语言进程的机制缺陷，
    # 2026-08-28 与测试隔离机制一并修复）。
    if ctx.rules_dir not in _PIPELINE_SHARED:
        ConfigRegistry.load_all(
            ctx.rules_dir,
            ext_dirs=ctx.ext_dirs,
            plugins_dir=os.path.join(ctx.rules_dir, "plugins"),
        )

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
        mapping_cfg = get_component_mapping_config()
        # 编排调度按 rules_dir 缓存（同一原因：声明来自 _loaded_components）。
        schedules = build_schedules()
        # 渲染插件覆盖式（[plugins].render = 组件名）：渲染插件产出中间表示
        # （如 c4 asm_gen → 汇编文本），启用后**直接不走主管线源端渲染**——
        # 渲染阶段由插件 handler 接管（覆盖式；与 analyze/transform 的叠加式
        # 不同）。未声明 → None（主管线源端渲染）。
        render_handler = _resolve_render_handler(ctx.rules_dir)
        _PIPELINE_SHARED[ctx.rules_dir] = {
            "rules": rules,
            "rule_selector": rule_selector,
            "lexer": lexer,
            "linter": linter,
            "renderer": renderer,
            "mapping_cfg": mapping_cfg,
            "schedules": schedules,
            "render_handler": render_handler,
        }
    shared = _PIPELINE_SHARED[ctx.rules_dir]
    ctx.rules = shared["rules"]
    ctx.rule_selector = shared["rule_selector"]
    ctx.lexer = shared["lexer"]
    ctx.linter = shared["linter"]
    ctx.renderer = shared["renderer"]
    ctx.render_handler = shared["render_handler"]


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
    """渲染 + 注释回插 + 格式化 + 输出 + 幂等检查。

    渲染插件覆盖式分支：语言包声明 [plugins].render 时，渲染阶段由插件
    handler 接管（产出中间表示文本，如 c4 汇编）——**不走主管线源端渲染**，
    直接输出 handler 结果（覆盖式；输出唯一性）。注释回插/保真度/格式化
    等源端还原步骤对中间表示无意义，一并跳过。
    """
    if not ctx.renderer_enabled:
        print("[renderer] skipped")
        ctx.result["ast"] = ast
        return

    if ctx.render_handler is not None:
        content = ctx.render_handler(ast, ctx)
        ctx.log("[renderer] render plugin: output via handler")
        # Write output (no header — raw content for clean diffing)
        if ctx.gen_file:
            with open(ctx.gen_file, "w", encoding="utf-8") as f:
                f.write(content)
            ctx.log(f"[output] {ctx.gen_file}")
        ctx.result["output"] = content
        ctx.result["ast"] = ast
        ctx.result["success"] = True
        ctx.result["idempotent"] = True  # 中间表示输出无源端幂等语义
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

    content = restore_all_comments(
        content,
        comment_anchors=getattr(parser, "_comment_anchors", None),
        line_anchors=getattr(parser, "_line_comment_anchors", None),
        restoration_stack=ctx.restore_stack,
        placeholders=ctx.placeholders,
        tpc_src_map=ctx.tpc_src_map,
        log_fn=ctx.log,
    )

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

    # 编排调度（ADR-0007）：schedule 内 pass 序列（analyze/transform/check），
    # 统一锚定在归一化后；pass 内报 error 或 stage 命中即截断。
    schedule_name: str = (
        schedule
        if schedule is not None
        else _cfg.get("schedule", DEFAULT_SCHEDULE_NAME)
    )
    # schedules / mapping_cfg 由管线按 rules_dir 缓存后注入编排器
    # （schedule.py 不触碰 _PIPELINE_SHARED，保持可独立复用）。
    _shared = _PIPELINE_SHARED[ctx.rules_dir]
    ast, _ = _run_schedule(
        ctx, ast, None, schedule_name,
        _shared["schedules"], _shared["mapping_cfg"],
    )
    if ctx.result.get("error"):
        return ctx.result
    if stage in _LEGACY_PASS_STAGES:
        ctx.result["success"] = True
        ctx.result["ast"] = ast
        return ctx.result

    # 渲染
    _stage_render(ctx, ast, ctx.result.get("parser"))

    return ctx.result
