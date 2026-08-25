#!/usr/bin/env python3
"""
调试工具：分段解析 + 并树（Segmented parse + AST merge）。

痛点：调试 picorv32 这类大文件时，每次全量 tokenize + parse 开销大，
verbose 日志能到十万行。本工具把源码按 module 边界切成若干段，
每段独立 tokenize + parse，再把各段 AST 合并为完整 Root 树。

用法：
    python tests/e2e/debug_segment_parse.py <file.v> [--expand] [--predefined K=V,...]
        [--segment N] [--breaks L1,L2,...] [--render] [--verbose]

分段点：
    - 默认按 module/endmodule 边界切段（每段含 module 前的注释行）。
    - --breaks 可硬编码行号（1-based，从文本直接切）作为分段点，覆盖 module 边界，
      用于只重看某个区间（例如 --breaks 352,431）。
"""

import sys
import os
import io
import re
import argparse
import contextlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tests import _bootstrap  # noqa: E402  # pyright: ignore[reportUnusedImport] — 副作用导入（sys.path + UTF-8）

from core.plugin_loader import load_all_components

load_all_components()

from core.config_registry import ConfigRegistry
from core.define import (
    Node,
    GrammarRulesRegister,
    DEFAULT_RULES_DIR,
    DEFAULT_EXT_DIRS,
)
from parser import Parser, setup_grammar
from parser._constants import ROOT_RULE_NAME
from parser.rule_selector import RuleSelector
from lexer import Lexer, pre_scan, load_pre_scan_config
from preprocessor import scan_directives, expand_tokens
from renderer.renderer import Renderer

# Force stdout to UTF-8
sys.stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)

_MODULE_RE = re.compile(r"^\s*module\s+\w")


# ── 分段 ──
def split_by_module(text: str):
    """按 module/endmodule 边界把文本切成若干段。

    每段 = [上一个 endmodule 之后, 本 module 的 endmodule]（含 module 前注释）。
    返回 [(name, text, start_line, end_line)]，行号为 0-based [start, end)。
    """
    lines = text.split("\n")
    module_lines = [i for i, l in enumerate(lines) if _MODULE_RE.match(l)]
    end_lines = [i for i, l in enumerate(lines) if l.strip().startswith("endmodule")]

    segments = []
    prev_end = -1
    for m in module_lines:
        # 取该 module 之后最近的一个 endmodule
        e = next((x for x in end_lines if x > m), None)
        if e is None:
            break
        start = prev_end + 1
        seg_text = "\n".join(lines[start : e + 1])
        name = _module_name(lines[m])
        segments.append((f"module:{name}", seg_text, start, e + 1))
        prev_end = e
    if prev_end + 1 < len(lines) and "\n".join(lines[prev_end + 1 :]).strip():
        segments.append(
            ("tail", "\n".join(lines[prev_end + 1 :]), prev_end + 1, len(lines))
        )
    return segments


def split_by_breaks(text: str, breaks: list[int]):
    """按硬编码行号（1-based）切段，覆盖 module 边界。"""
    lines = text.split("\n")
    n = len(lines)
    pts = sorted({max(0, min(b - 1, n)) for b in breaks})
    starts = [0] + pts + [n]
    starts = sorted(set(starts))
    segments = []
    for k in range(len(starts) - 1):
        a, b = starts[k], starts[k + 1]
        if a >= b:
            continue
        segments.append((f"seg{k + 1}", "\n".join(lines[a:b]), a, b))
    return segments


def _module_name(line: str) -> str:
    m = re.search(r"module\s+(\w+)", line)
    return m.group(1) if m else "?"


# ── 解析 ──
def build_components(rules_dir: str, ext_dirs: list[str]):
    ConfigRegistry.load_all(
        rules_dir, ext_dirs=ext_dirs, plugins_dir=os.path.join(rules_dir, "plugins")
    )
    rules = setup_grammar(rules_dir, GrammarRulesRegister.get_default(), ext_dirs=ext_dirs)
    stmt_names = [
        n
        for n, r in rules.items()
        if hasattr(r, "has_pass_end_case") and r.has_pass_end_case()
    ]
    rule_selector = RuleSelector(rules, stmt_names)
    lexer = Lexer(rules_dir=rules_dir, ext_dirs=ext_dirs)
    renderer = Renderer(rules_dir=rules_dir)
    pre_cfg = load_pre_scan_config(rules_dir)
    return rules, rule_selector, lexer, renderer, pre_cfg


def parse_segment(lexer, rules, rule_selector, text, pre_symbols, verbose, pre_hints):
    tokens = lexer.tokenize(text)
    parser = Parser(
        rules_dir=None,
        rules=rules,
        rule_selector=rule_selector,
        verbose=verbose,
    )
    parser.pre_symbols = pre_symbols
    parser.pre_hints = pre_hints
    err_buf = io.StringIO()
    with contextlib.redirect_stdout(err_buf), contextlib.redirect_stderr(err_buf):
        ast = parser.parse(tokens)
    warns = [
        l.strip()
        for l in err_buf.getvalue().splitlines()
        if "WARN" in l or "匹配失败" in l
    ]
    return tokens, ast, warns, parser


def merge_segments(seg_results):
    """把各段 AST 的 Root.sub_node 依次合并到一颗 Root。"""
    root = Node(ROOT_RULE_NAME)
    for _, ast, _ in seg_results:
        if ast is None:
            continue
        for sub in ast.sub_node:
            root.add_sub_node(sub)
    return root


# ── 主流程 ──
def main() -> int:
    ap = argparse.ArgumentParser(description="分段解析 + 并树")
    ap.add_argument("file", help="Verilog 源文件")
    ap.add_argument("--expand", action="store_true", help="宏展开后再分段")
    ap.add_argument("--predefined", default="", help="预定义宏，逗号分隔 K=V")
    ap.add_argument("--segment", type=int, default=0, help="只解析第 N 段（1-based）")
    ap.add_argument("--breaks", default="", help="硬编码分段点行号，逗号分隔（1-based）")
    ap.add_argument("--render", action="store_true", help="并树后渲染输出")
    ap.add_argument("--verbose", action="store_true", help="parser verbose 日志")
    args = ap.parse_args()

    rules_dir = DEFAULT_RULES_DIR
    ext_dirs = DEFAULT_EXT_DIRS

    # 先加载配置再展开（与 run_pipeline 顺序一致：ConfigRegistry.load_all 在
    # scan_directives 之前）。若先 expand 后 load，宏展开会用到未加载的配置，
    # 结果与生产管线不一致（实测会差一行，导致分段与解析结果失真）。
    rules, rule_selector, lexer, renderer, pre_cfg = build_components(
        rules_dir, ext_dirs
    )

    source = open(args.file, encoding="utf-8").read()

    # 可选宏展开
    if args.expand:
        predefined = {}
        for kv in args.predefined.split(","):
            if "=" in kv:
                k, v = kv.split("=", 1)
                predefined[k] = v
        mt, fm, _, _, _, clean = scan_directives(
            source,
            rules_dir,
            source_path=args.file,
            predefined=predefined or None,
        )
        source, _ = expand_tokens(clean, mt, func_macros=fm)

    # 分段
    if args.breaks:
        breaks = [int(x) for x in args.breaks.split(",") if x.strip()]
        segments = split_by_breaks(source, breaks)
    else:
        segments = split_by_module(source)
    if not segments:
        print("[debug] 未切出任何段（无 module / 空文件）")
        return 1
    # 全文件预扫描符号表（跨段共享，比逐段 pre_scan 更准）
    pre_symbols = pre_scan(source, pre_cfg) or {}
    pre_hints = pre_cfg.get("hints", {})

    print(f"[debug] 分段数: {len(segments)}  总行数: {len(source.splitlines())}")
    seg_results = []
    for idx, (name, seg_text, sl, el) in enumerate(segments, start=1):
        if args.segment and idx != args.segment:
            continue
        tokens, ast, warns, _parser = parse_segment(
            lexer, rules, rule_selector, seg_text, pre_symbols, args.verbose, pre_hints
        )
        # 段可能 parse 出空块（0 句子），此时 Root 没有 sub_node 属性
        subs = len(getattr(ast, "sub_node", []) or []) if ast else 0
        seg_results.append((name, ast, warns))
        print(
            f"  seg#{idx:<2} {name:<24} L{sl + 1}-{el} "
            f"tokens={len(tokens):<6} subs={subs:<4} WARN={len(warns)}"
        )
        if subs == 0 and ast is not None:
            first = seg_text.splitlines()[0].strip() if seg_text.splitlines() else ""
            print(
                f"        ! 空块：段首 {first[:40]!r} 不是合法语句起点，"
                f"可能切在结构中间（如 case 分支标签），试试把断点移到语句边界"
            )
        for w in warns[:6]:
            print(f"        {w[:150]}")
        if len(warns) > 6:
            print(f"        ... 还有 {len(warns) - 6} 条 WARN")

        # --segment 模式：打印段 AST 结构详情（第一层 + ModuleDecl 内部）
        if args.segment and ast is not None:
            print(f"  [segment {args.segment}] AST 结构:")
            for sub in getattr(ast, "sub_node", []) or []:
                nm = getattr(sub, "node_name", "?")
                if nm == "ModuleDecl":
                    inner = [getattr(c, "node_name", "?") for c in getattr(sub, "sub_node", []) or []]
                    print(f"    ModuleDecl 子节点 {len(inner)}: {inner}")
                else:
                    print(f"    {nm}")

    # 并树
    if args.segment:
        return 0
    root = merge_segments(seg_results)
    names = [getattr(n, "node_name", "?") for n in root.sub_node]
    mods = [n for n in root.sub_node if getattr(n, "node_name", "") == "ModuleDecl"]
    print(f"[merge] Root.sub_node={len(names)}  ModuleDecl={len(mods)}")
    print(f"[merge] 节点序列: {names}")

    if args.render:
        content = renderer.render(root)
        out = os.path.splitext(args.file)[0] + ".merged.v"
        with open(out, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[render] 并树渲染 {len(content.splitlines())} 行 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
