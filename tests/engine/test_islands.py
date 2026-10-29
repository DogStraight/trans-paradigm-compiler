"""片段模式（islands）组件测试 — 语法配置驱动的岛式分片与合成。

契约（作者 2026-10-30 定稿，见 `docs/gaps/gap-fragment-mode.md`）：
- 岛 = 语法配置推导出的语法单元（无声明面/无记号）；water 逐字节原样保留；
- 岛内只走真实管线；自顶向下成功即停，失败递归子节点；
- 后验默认开（岛级重解析 + 双跑逐字幂等）；无岛/零变化逐字节返回原 bytes。
"""

from __future__ import annotations

import pytest

from islands import rewrite_bytes

_VERILOG = "grammar/verilog"
_C = "grammar/c"

_SAMPLE = (
    b"module m(input clk);\n"
    b"  always @(*) begin\n"
    b"    q = d;\n"
    b"  end\n"
    b"endmodule\n"
)


class TestIdentity:
    """无岛/零变化 ⇒ 逐字节返回原 bytes（BOM/CRLF/无尾换行保真）。"""

    @pytest.mark.parametrize(
        "data",
        [
            b"",
            b"\n\n",
            b"class C; endclass\n",          # 语法里没有的构造 = water
            b"// only comment\r\n",
        ],
    )
    def test_no_island_is_byte_identical(self, data: bytes) -> None:
        r = rewrite_bytes(data, _VERILOG)
        assert r.output == data
        assert not r.changed

    def test_bom_and_crlf_preserved(self) -> None:
        src = b"\xef\xbb\xbf" + _SAMPLE.replace(b"\n", b"\r\n")
        r = rewrite_bytes(src, _VERILOG)
        assert r.output.startswith(b"\xef\xbb\xbf")
        assert b"\r\n" in r.output
        assert r.changed


class TestIslandProcessing:
    def test_module_island_goes_through_pipeline(self) -> None:
        r = rewrite_bytes(_SAMPLE, _VERILOG)
        assert r.processed and "ModuleDecl" in r.processed
        assert r.changed
        # 真实管线渲染（与本仓 format 同源）
        assert b"always @(*) begin" in r.output
        assert b"    always @(*) begin" in r.output

    def test_water_text_is_preserved(self) -> None:
        src = (
            b"module m;\n"
            b"  always @(*) begin\n"
            b"    q = d;\n"
            b"  end\n"
            b"  class C; endclass\n"     # 语法里没有：water
            b"endmodule\n"
        )
        r = rewrite_bytes(src, _VERILOG)
        assert b"class C; endclass" in r.output
        assert b"  always @(*) begin" in r.output   # 部分可解析：岛保留原基线

    def test_c_pack_uses_same_mechanism(self) -> None:
        src = b"int f(void) {\n  int x = 0;\n  return x;\n}\n"
        r = rewrite_bytes(src, _C)
        assert r.processed and "FuncDef" in r.processed
        assert r.changed


class TestPostVerification:
    def test_double_run_is_idempotent(self) -> None:
        r1 = rewrite_bytes(_SAMPLE, _VERILOG)
        r2 = rewrite_bytes(r1.output, _VERILOG)
        assert r2.output == r1.output

    def test_macro_island_is_water(self) -> None:
        """含宏的岛不进管线（展开会改原文）⇒ 整文件不动。"""
        src = (
            b"module m;\n"
            b"`define X 1\n"
            b"  always @(*) begin\n"
            b"    q = `X;\n"
            b"  end\n"
            b"endmodule\n"
        )
        r = rewrite_bytes(src, _VERILOG)
        assert r.output == src
