"""tests/e2e/test_comment_restore.py — e2e 注释恢复门禁（样本级，直接断言文本）。

背景：normal 组的 run_all fidelity 检测依赖 gitignored 的本地缓存
（.fidelity_cache.json，不入库）——干净 clone 上无缓存时 `prev is None`
不触发 drop 检测，注释丢失不会 FAIL。本文件对注释样本做**直接文本断言**
（不依赖缓存），让注释恢复成为硬门禁：

样本（tests/e2e/samples/normal/ref/）：
- ref_comments.v      文件头/行内/行尾/独立行/嵌入 注释形态
- ref_inline_test.v   端口/声明/if/else/语句 注释 + pratt operator 间隙注释
  （`led <= ~led + /* 中缀注释 */ 1'b0;` —— P1.5 修复后 pratt 表达式内
  注释唯一仍走锚点回插轨的形态，见 docs/references.md「pratt 前缀吞注释」）

断言策略：
1. 每条源注释文本都出现在输出中（不丢失）；
2. pratt 内注释用去空白比较断言**相对位置**（在 `+` 与 `1'b0` 之间，
   而非漂到行尾）——与 test_pratt_comment_keep 同风格；
3. 行尾注释锚定在含对应代码 token 的行（不漂移到其它语句行）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # noqa: E402
from tests import _bootstrap  # noqa: E402  # pyright: ignore[reportUnusedImport]

from tests.e2e.run_pipeline import run_pipeline_on_source  # noqa: E402

_NORMAL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", "normal", "ref")


def _read(name: str) -> str:
    with open(os.path.join(_NORMAL_DIR, name), encoding="utf-8") as f:
        return f.read()


def _run(src: str, fmt: bool):
    r = run_pipeline_on_source(
        source=src, rules_dir="grammar/verilog", quiet=True, no_lint=True,
        format_output=fmt, expand_macros=False,
    )
    assert r["success"], r.get("error", "")
    return r.get("output", "")


def _run_both(src: str):
    """两种模式都跑：format 关（世界 A 渲染原样）与 format 开（e2e 默认，
    formatter 品类对齐路径——曾把声明行 `[31:0]` 挪进注释文本）。"""
    return _run(src, False), _run(src, True)


def _flat(text: str) -> str:
    return "".join(text.split())


def _line_comments(text: str) -> list[str]:
    """源中所有 `//` 注释文本（含 `/* */` 单行块注释不做此处收集）。"""
    return [ln.split("//", 1)[1].strip() for ln in text.splitlines() if "//" in ln]


def _for_each_out(src, fn):
    """两种模式输出都过 fn（不丢注释 + 位置断言双保险）。"""
    for fmt, out in zip(("format-off", "format-on"), _run_both(src)):
        fn(out, fmt)


class TestCommentsSample:
    def test_all_comments_survive(self):
        """ref_comments.v：每条注释文本都出现在输出（不丢失）。"""
        src = _read("ref_comments.v")

        def check(out, fmt):
            for comment in (
                "// 文件头注释",
                "// 多行文件头",
                "// 行内注释",
                "/* 块注释 */",
                "// 语句前注释",
                "/* 块注释单独一行 */",
                "// 行尾注释",
                "/* 嵌入注释 */",
            ):
                assert comment in out, f"[{fmt}] 注释丢失: {comment}"

        _for_each_out(src, check)

    def test_midline_embed_in_place(self):
        """`assign b = /* 嵌入注释 */ rst_n;`：注释在 `=` 与 `rst_n` 之间。"""
        src = _read("ref_comments.v")

        def check(out, fmt):
            flat = _flat(out)
            assert "=/*嵌入注释*/rst_n" in flat, f"[{fmt}] 嵌入注释应留在 = 与 rst_n 之间"
            assert not flat.rstrip().endswith("/*嵌入注释*/"), f"[{fmt}] 嵌入注释不得漂到行尾"

        _for_each_out(src, check)

    def test_line_end_comment_on_own_stmt(self):
        """行尾注释锚定在对应语句行，不漂移到其它语句。"""
        src = _read("ref_comments.v")

        def check(out, fmt):
            lines = out.splitlines()
            # 品类对齐会加列 padding（`wire a;` → `wire   a;`）——
            # 用"注释前代码段去空白"匹配对应语句行
            def code_compact(line: str) -> str:
                return "".join(line.split("//", 1)[0].split())

            port_line = next(l for l in lines if code_compact(l).startswith("inputclk,"))
            assert "// 行内注释" in port_line, f"[{fmt}] 行内注释应在 input clk 行"
            assign_line = next(
                l for l in lines if code_compact(l).startswith("assigna=clk")
            )
            assert "// 行尾注释" in assign_line, f"[{fmt}] 行尾注释应在 assign a = clk 行"

        _for_each_out(src, check)


class TestInlineSample:
    def test_all_comments_survive(self):
        """ref_inline_test.v：每条注释文本都出现在输出（不丢失）。"""
        src = _read("ref_inline_test.v")

        def check(out, fmt):
            for comment in (
                "/* port comment */",
                "/* decl comment */",
                "/* if comment */",
                "/* else comment */",
                "/* stmt comment */",
                "/* 中缀注释 */",
            ):
                assert comment in out, f"[{fmt}] 注释丢失: {comment}"

        _for_each_out(src, check)

    def test_pratt_midline_in_place(self):
        """pratt operator 间隙注释：`~led + /* 中缀注释 */ 1'b0` 中注释
        在 `+` 与 `1'b0` 之间（不得漂到语句行尾/其它行）。"""
        src = _read("ref_inline_test.v")

        def check(out, fmt):
            flat = _flat(out)
            assert "+/*中缀注释*/1'b0" in flat, (
                f"[{fmt}] pratt 内注释应留在 + 与 1'b0 之间, tail: {flat[-120:]}"
            )

        _for_each_out(src, check)

    def test_decl_comment_stays_inline(self):
        """`reg [31:0] counter /* decl comment */;`：位宽在名字前、注释
        留在声明行（formatter 品类对齐回归守卫——曾把 `[31:0]` 挪进注释）。"""
        src = _read("ref_inline_test.v")

        def check(out, fmt):
            lines = out.splitlines()
            decl_line = next(l for l in lines if "counter" in l)
            assert "[31:0] counter /* decl comment */" in decl_line, (
                f"[{fmt}] 位宽/注释位置异常: {decl_line!r}"
            )

        _for_each_out(src, check)

    def test_idempotent(self):
        """输出再走一遍管线，注释仍保留且稳定（format 关模式）。"""
        src = _read("ref_inline_test.v")
        out1 = _run(src, False)
        out2 = _run(out1, False)
        assert _flat(out2) == _flat(out1)
        assert "/* 中缀注释 */" in out2
