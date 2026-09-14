"""tools/analyze_macro_positions.py — 宏位置透明性覆盖量化（不变量测量工具）。

Doc: docs/decisions/0017-macro-in-syntax-position.md（宏在语法位的处置决策）

不变量（期望性质）：宏是**文本任意位置**的透明替换——把源里任一 token 换成等价
宏（`` `define M <token 原文> `` + 该位置改写成 `` `M ``），格式化输出应与未替换时
**逐字相同**（宏调用原文还原、不被格式化展开）。

本工具逐 token 位置验证这条不变量，统计"通过/总位置"与失败分布——用来量化"宏能
在哪些位置透明替换"这一边界（ADR-0017 的 54/135=40% 即由此测出），而不是当门禁
用（未通过的位置是**已知边界**：语法关键字/括号等结构位不支持，属决策记录）。

用法：
    python tools/analyze_macro_positions.py                     # 内置样本，报告到 stdout
    python tools/analyze_macro_positions.py --source x.v        # 指定源文件
    python tools/analyze_macro_positions.py --max-positions 12  # 抽样（自测用，省时间）
    python tools/analyze_macro_positions.py --out report.txt    # 报告落文件
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import os
import sys
from collections import Counter

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
# 副作用导入（项目根已在 sys.path）：导入即完成 stdout/stderr UTF-8 重配置
importlib.import_module("tests._bootstrap")
from core.define import DEFAULT_EXT_DIRS, DEFAULT_RULES_DIR  # noqa: E402
from core.token_protocol import TRIVIA_TOKEN_TYPES  # noqa: E402
from lexer import Lexer  # noqa: E402
from pipeline import run_pipeline_on_source  # noqa: E402

# 内置样本：覆盖端口/参数/声明/表达式/条件/循环/函数等结构位
_BUILTIN_SRC = (
    "module top #(parameter W = 8) (\n"
    "    input wire clk,\n"
    "    input wire [W-1:0] d,\n"
    "    output reg [W-1:0] q\n"
    ");\n"
    "    wire [W-1:0] tmp;\n"
    "    reg [3:0] cnt;\n"
    "    assign tmp = d + 1'b1;\n"
    "    always @(posedge clk) begin\n"
    "        if (cnt == 4'd0)\n"
    "            q <= tmp;\n"
    "        else begin\n"
    "            case (cnt)\n"
    "                4'd1: q <= ~tmp;\n"
    "                default: q <= 0;\n"
    "            endcase\n"
    "        end\n"
    "    end\n"
    "    function [W-1:0] f(input [W-1:0] x);\n"
    "        f = x ^ {W{1'b1}};\n"
    "    endfunction\n"
    "endmodule\n"
)

_MACRO_CALL = "`M"


def _run(src: str) -> dict:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return run_pipeline_on_source(source=src, quiet=True, expand_macros=True, no_lint=True)


def _positions(src: str, tokens: list) -> list[tuple[str, int, int, str]]:
    """(token_type, 行索引, 起始列, 原文)——只取源切片与 content 相符者。"""
    lines = src.split("\n")
    out: list[tuple[str, int, int, str]] = []
    for tok in tokens:
        if tok.type in TRIVIA_TOKEN_TYPES or tok.type.startswith("space"):
            continue
        idx = tok.line - 1
        if not (0 <= idx < len(lines)):
            continue
        start = tok.column
        if lines[idx][start:start + len(tok.content)] != tok.content:
            continue  # 切片不符（转义/多字符形态）→ 跳过
        out.append((tok.type, idx, start, tok.content))
    return out


def _strip_define_line(text: str, define_line: str) -> str:
    """去掉输出里的 `define 行（指令行原位还原出现在输出中，不算差异）。"""
    keep = define_line.strip()
    return "\n".join(ln for ln in text.split("\n") if ln.strip() != keep)


def _norm(text: str) -> str:
    """空白归一（对齐填充宽度随宏调用原文长度变化，不是结构差异）。"""
    return " ".join(text.split())


def analyze(source: str, max_positions: int | None = None) -> tuple[list[str], int, int]:
    """跑一遍基线 + 逐位置替换，返回 (报告行, 通过数, 总位置数)。"""
    lines = [f"源: 行数={len(source.splitlines())}"]
    base = _run(source)
    lines.append(f"基线: success={base['success']} 输出长度={len(base.get('output') or '')}")
    if not base["success"]:
        lines.append(f"  基线失败: {base.get('error')}")
        return lines, 0, 0

    tokens = Lexer(rules_dir=DEFAULT_RULES_DIR, ext_dirs=DEFAULT_EXT_DIRS).tokenize(source)
    positions = _positions(source, tokens)
    if max_positions is not None:
        positions = positions[:max_positions]
    lines.append(f"可测位置: {len(positions)}")

    src_lines = source.split("\n")
    base_norm = _norm(_strip_define_line(base["output"] or "", "`define M x"))
    fails: Counter = Counter()
    fail_examples: list[str] = []
    passed = 0

    for ttype, idx, start, content in positions:
        line = src_lines[idx]
        mutated = list(src_lines)
        mutated[idx] = line[:start] + _MACRO_CALL + line[start + len(content):]
        define_line = f"`define M {content}"
        src2 = define_line + "\n" + "\n".join(mutated)

        res = _run(src2)
        out_norm = _norm(_strip_define_line(res.get("output") or "", define_line))
        restored = (res.get("output") or "").count(_MACRO_CALL) == 1
        ok = res.get("success") and restored and out_norm.replace(_MACRO_CALL, content) == base_norm
        if ok:
            passed += 1
            continue

        fails[ttype] += 1
        if len(fail_examples) < 15:
            if not res.get("success"):
                reason = (res.get("error") or "")[:70]
            elif not restored:
                reason = f"宏未还原（`M 出现 {(res.get('output') or '').count(_MACRO_CALL)} 次）"
            else:
                i = next(
                    (k for k in range(min(len(out_norm), len(base_norm)))
                     if out_norm[k] != base_norm[k]),
                    0,
                )
                reason = (f"输出差异: got {out_norm[max(0, i - 20):i + 30]!r}"
                          f" vs want {base_norm[max(0, i - 20):i + 30]!r}")
            fail_examples.append(f"  [{ttype}] L{idx}:{start} 原文={content!r} → {reason}")

    lines.append(f"通过: {passed}/{len(positions)}")
    lines.append("失败按 token 类型分布:")
    lines.extend(f"  {ttype}: {n}" for ttype, n in fails.most_common())
    lines.append("失败样例:")
    lines.extend(fail_examples)
    return lines, passed, len(positions)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="analyze_macro_positions",
        description="宏位置透明性覆盖量化（不变量测量，非门禁）",
    )
    ap.add_argument("--source", default=None, help="源文件（默认内置样本）")
    ap.add_argument("--max-positions", type=int, default=None, help="只测前 N 个位置")
    ap.add_argument("--out", default=None, help="报告落文件（默认 stdout）")
    args = ap.parse_args(argv)

    source = _BUILTIN_SRC
    if args.source:
        with open(args.source, encoding="utf-8") as f:
            source = f.read()
    lines, passed, total = analyze(source, args.max_positions)
    report = "\n".join(lines)
    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"[written] {args.out}")
    # 非门禁：未通过的位置是**已知边界**（决策记录见 ADR-0017），不影响退出码；
    # 只有"跑不起来/基线就挂"才算工具失败。
    print(f"[summary] 透明通过 {passed}/{total}（未通过属已知边界，非门禁）")
    return 0 if total else 2


if __name__ == "__main__":
    sys.exit(main())
