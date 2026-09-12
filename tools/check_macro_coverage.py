"""check_macro_coverage.py — 宏位置覆盖自查（ADR-0017 决策 3/4 的验收标尺）。

不变量：宏是**文本任意位置**的透明替换。取 `` `define M <token 原文> ``，把该
token 替换为 `` `M ``，则格式化输出必须与未替换时一致——宏调用原文原样保留
（不被展开、不被重排），其余内容格式化结果不变。

这条不变量把"宏的位置支持"从"我声明了哪些槽位"变成**可测的数字**：任一位置
失败即该机制在该位置不支持。逐槽位声明 `@MacroCall` 只买到 4 个位置
（54/135 → 撤销后 50/135），故已撤销（见 ADR-0017 决策 2/3）。

用法：
    python tools/check_macro_coverage.py                # 内置样本
    python tools/check_macro_coverage.py --file f.v     # 指定源文件
    python tools/check_macro_coverage.py --json         # 机器可读

不进日常门禁（人工/按需跑，与 tools/ 其他自查工具同）。机制就位后本工具应给出
高覆盖且不回退；失败面按 token 类型分布用于定位机制缺口。
Doc: docs/decisions/0017-macro-in-syntax-position.md
"""

import argparse
import contextlib
import io
import json
import os
import sys
from collections import Counter

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.define import DEFAULT_EXT_DIRS, DEFAULT_RULES_DIR, Token  # noqa: E402
from core.token_protocol import TRIVIA_TOKEN_TYPES  # noqa: E402
from lexer import Lexer  # noqa: E402
from pipeline import run_pipeline_on_source  # noqa: E402

SAMPLE = (
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


def _run(source: str) -> dict:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return run_pipeline_on_source(
            source=source, quiet=True, expand_macros=True, no_lint=True
        )


def _positions(source: str, tokens: list[Token]) -> list[tuple[str, int, int, str]]:
    """(token_type, line_idx, start_col, content)：仅取切片与 content 相符者。"""
    lines = source.split("\n")
    out: list[tuple[str, int, int, str]] = []
    for t in tokens:
        if t.type in TRIVIA_TOKEN_TYPES or t.type.startswith("space"):
            continue
        idx = t.line - 1
        if not (0 <= idx < len(lines)):
            continue
        start = t.column
        end = start + len(t.content)
        if lines[idx][start:end] != t.content:
            continue  # 转义/多字符形态，切片不可靠 → 跳过
        out.append((t.type, idx, start, t.content))
    return out


def _strip_define_line(text: str, define_line: str) -> str:
    keep = define_line.strip()
    return "\n".join(x for x in text.split("\n") if x.strip() != keep)


def _norm(text: str) -> str:
    """空白归一（对齐填充宽度随宏调用原文长度变化，不是结构差异）。"""
    return " ".join(text.split())


def measure(source: str) -> dict:
    base = _run(source)
    if not base["success"]:
        raise SystemExit(f"基线不可解析，无法测量：{base.get('error')}")
    base_norm = _norm(_strip_define_line(base["output"], "`define M x"))
    tokens = Lexer(rules_dir=DEFAULT_RULES_DIR, ext_dirs=DEFAULT_EXT_DIRS).tokenize(
        source
    )
    lines = source.split("\n")
    positions = _positions(source, tokens)

    passed = 0
    fails: Counter = Counter()
    examples: list[dict] = []
    for ttype, idx, start, content in positions:
        line = lines[idx]
        lines2 = list(lines)
        lines2[idx] = line[:start] + "`M" + line[start + len(content):]
        define_line = "`define M " + content
        res = _run(define_line + "\n" + "\n".join(lines2))
        out_norm = _norm(_strip_define_line(res["output"], define_line))
        restored = res["output"].count("`M") == 1
        ok = (
            res["success"]
            and restored
            and out_norm.replace("`M", content) == base_norm
        )
        if ok:
            passed += 1
            continue
        fails[ttype] += 1
        if len(examples) < 15:
            if not res["success"]:
                why = res.get("error", "")[:70]
            elif not restored:
                why = f"宏未原样保留（`M 出现 {res['output'].count('`M')} 次）"
            else:
                why = "输出与原内容不一致"
            examples.append(
                {"type": ttype, "line": idx, "col": start, "text": content,
                 "why": why}
            )
    return {
        "source": source.splitlines()[0][:40],
        "positions": len(positions),
        "passed": passed,
        "coverage": round(passed / len(positions), 4) if positions else 0.0,
        "fails_by_type": dict(fails.most_common()),
        "examples": examples,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", help="待测源文件（默认内置样本）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    source = open(args.file, encoding="utf-8").read() if args.file else SAMPLE
    result = measure(source)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"宏位置覆盖：{result['passed']}/{result['positions']} "
          f"= {result['coverage'] * 100:.1f}%")
    print("失败面（按 token 类型，机制缺口定位用）：")
    for ttype, n in result["fails_by_type"].items():
        print(f"  {ttype}: {n}")
    if result["examples"]:
        print("失败样例：")
        for e in result["examples"]:
            print(f"  [{e['type']}] L{e['line']}:{e['col']} {e['text']!r} → {e['why']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
